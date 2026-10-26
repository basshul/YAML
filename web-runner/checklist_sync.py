r"""SharePoint 체크리스트를 읽어 로컬 캐시(`checklist_cache.json`)로 떨군다.

    python checklist_sync.py              # config.local.json 의 링크로 받아온다
    python checklist_sync.py --dry-run    # 받아만 보고 쓰지 않는다

왜 캐시인가 (docs/CHECKLIST.md §11):
  토큰은 **사람 계정**이고 refresh 가 만료되면 브라우저 인증이 필요한데 서버는 그걸 못 한다.
  → 끊겨도 **읽기 화면은 캐시로 계속 돌아야 한다.** 그래서 서버는 캐시만 읽고,
    SharePoint 접속은 이 스크립트(사람이 돌리는 것)만 한다.

왜 gme_excel.py 의 CLI 를 안 쓰는가:
  `get` 은 셀을 탭으로 이어 붙여 출력하는데 **확인 문구에 줄바꿈이 들어 있다**
  → 줄 단위로 파싱하면 행이 깨진다. 여기서는 Graph 가 주는 `values` 2차원 배열을
    그대로 받는다.

⚠️ 시트가 둘인데 **구조가 다르다.** 매핑은 `Checklist(Livetest)` 에만 있고
   `Checklist(STG)` 는 같은 범위에 확인 문구가 들어 있다 — 같이 읽으면 열이 밀린다.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_RUNNER_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

import gme_excel                                   # noqa: E402
import checklist_layout                            # noqa: E402
import runner                                      # noqa: E402

CACHE_FILE = WEB_RUNNER_DIR / "checklist_cache.json"
SHEET = "Checklist(Livetest)"   # config 의 checklist.sheet 로 덮을 수 있다
MAPPING_FILE = WEB_RUNNER_DIR / "checklist_mapping.json"

# ★ 열 위치를 **박지 않는다.** 머리글 글자로 찾는다(`checklist_layout`).
#   종전엔 `B10:L600` + 배열 순서였는데, 신규 문서(V2.2)는 앞에 `No`·`Case ID` 두 열이
#   생겨 전부 두 칸 밀린다 → 위치를 박아 두면 **모든 열이 조용히 어긋난다.**
#   V2.2 는 매핑 열이 없고 대신 고유한 Case ID 가 있다 → 매핑은 저장소 파일에서 읽는다.

# 케이스 표기가 한 가지가 아니다(2026-10-06 실측):
#   [01] 모두동의→확인 활성화          → 01
#   [02]+[03] 필수 uncheck→…           → 02, 03   (한 행이 케이스 둘을 덮는다)
#   [16a] ARC 촬영 / [16b] ARC OCR     → 16       (yaml 케이스 하나를 둘로 쪼갠 것)
#   [01-1] 은행 계좌 연결 → …          → 01
# → 대괄호 안의 **앞쪽 숫자**가 yaml 케이스 번호다. 뒤에 붙은 a/b·-1 은 더 잘게
#   나눈 표기라 **같은 yaml 케이스**를 가리킨다.
# 대괄호 토큰을 전부 집어서 runner.case_id() 로 키를 만든다.
# ★ 키 규칙은 **runner 와 같은 함수**를 쓴다 — 양쪽이 갈리면 매핑이 조용히 어긋난다.
#   [01] → 01 / [02]+[03] → 02,03 / [16a] → 16 / [07-2] → 07 / [F-02] → F02
CASE_TOKEN_RE = re.compile(r"\[([^\]]+)\]")


# "없음" 을 뜻하는 표기들. 이걸 파일명으로 읽으면 매핑이 있는 것처럼 보인다.
EMPTY_MARKS = {"", "-", "—", "–", "n/a", "na", "없음"}


def _is_empty(v: str) -> bool:
    return v.strip().lower() in EMPTY_MARKS


# 한 셀이 **파일 여럿**을 가리키는 경우가 있다(2026-10-06 실측, 318행):
#   13_01_해외송금받기_환율과인니등록_old.yaml(인도네시아 [07]) /
#   13_02_해외송금받기_몽골송금인_old.yaml(몽골 [07-1]) /
#   13_03_해외송금받기_베트남송금인_old.yaml(베트남 [07-2])
# → 파일마다 괄호 안에 **자기 케이스 번호**가 적혀 있다. 셀 전체를 파일명 하나로 읽으면
#   나머지 둘이 통째로 빠진다(13_01·13_02 가 '체크리스트 행 없음' 으로 보였다).
PAIR_RE = re.compile(r"([^/()]+?)\s*\(([^)]*)\)")


def _cases_for(file_name: str, text: str) -> list[str]:
    """그 파일 기준으로 케이스 토큰을 키로 바꾼다.

    ⛔ 접미사(`16a`·`08-3`)를 **무조건 살리거나 무조건 접으면** 둘 다 틀린다.
       `[16a] [High] ARC 촬영` 은 별개 케이스고, `[27-1] 지문인증…` 은 `[27]` 의 본문 단계다.
       → 판단은 **yaml 이 한다**(`runner.real_cases`). 시트는 그 결과를 따른다.
         그래야 양쪽 키가 어긋나지 않는다.
    ⚠️ 그 파일을 못 찾으면(스위트 밖·G9 등) 빈 집합이 와서 **종전대로 접는다** — 안전한 쪽이다.
    """
    real = runner.real_cases(file_name)
    cases = []
    for tok in CASE_TOKEN_RE.findall(text or ""):
        kept = runner.case_id(tok, keep_suffix=True)
        num = kept if kept in real else runner.case_id(tok)
        if num and num not in cases:
            cases.append(num)
    return cases


def split_pairs(file_cell: str, case_cell: str) -> list[dict]:
    """(파일, 케이스들) 짝의 목록을 만든다. 보통 1개, 합쳐 적힌 셀이면 여러 개."""
    groups = PAIR_RE.findall(file_cell or "")
    pairs = []
    for name, inside in groups:
        cases = _cases_for(name, inside)
        if cases:
            pairs.append({"file": name.strip(), "cases": cases})
    if len(pairs) >= 2:
        return pairs
    # 평범한 셀 — 파일은 H, 케이스는 I 에서 읽는다
    return [{"file": (file_cell or "").strip(),
             "cases": _cases_for(file_cell, case_cell)}]


def _cell(row: list, i: int) -> str:
    if i >= len(row) or row[i] is None:
        return ""
    return str(row[i]).strip()


def load_mapping() -> dict:
    """Case ID → 매핑 목록. 시트에 매핑 열이 없는 판본이 쓴다."""
    if not MAPPING_FILE.exists():
        return {}
    return json.loads(MAPPING_FILE.read_text(encoding="utf-8")).get("mapping", {})


def fetch(link: str, sheet: str = SHEET) -> list[dict]:
    wb, _ = gme_excel.workbook_url(link)

    def read(a1):
        return gme_excel._req(gme_excel._range(wb, sheet, a1), headers=gme_excel.H())["values"]

    lay = checklist_layout.detect(read)
    lay.sheet = sheet
    ext = {} if lay.has_sheet_mapping else load_mapping()
    values = read(lay.range())

    rows = []
    for offset, raw in enumerate(values):
        row_no = lay.first_row + offset
        rec = {k: lay.get(raw, k) for k in lay.idx}
        if not rec.get("text"):
            continue
        # 판본에 없는 열은 빈 값으로 채워 **화면이 한 가지 모양만 다루게** 한다
        for k in ("priority", "d1", "d2", "d3", "text", "cover",
                  "yaml_file", "yaml_case", "done_date", "cover_old", "review", "case_id"):
            rec.setdefault(k, "")
        # 매핑이 시트에 없으면 저장소 파일에서 Case ID 로 가져온다
        if ext and rec["case_id"]:
            got = ext.get(rec["case_id"], [])
            if got:
                # 저장 형식은 `파일 [케이스]` 한 줄 — 아래 split_pairs 가 그대로 읽는다
                rec["yaml_file"] = got[0].rsplit(" [", 1)[0] if " [" in got[0] else got[0]
                rec["yaml_case"] = " ".join(g[len(rec["yaml_file"]):].strip() for g in got)
        # ★ 케이스 번호를 미리 뽑아 둔다. 한 행이 케이스 **여럿**을 덮는 경우가 있다
        #   (`[02]+[03] …`) — 화면이 매번 파싱하지 않게 여기서 풀어 둔다.
        rec["row"] = row_no                     # 엑셀 행 번호(결과 기입 시 I{row})
        if _is_empty(rec["yaml_file"]):
            rec["yaml_file"] = ""
        pairs = split_pairs(rec["yaml_file"], rec["yaml_case"])
        rec["pairs"] = pairs
        rec["cases"] = pairs[0]["cases"] if len(pairs) == 1 else []
        rec["case_raw"] = rec["yaml_case"]
        rec["maps"] = [f"{p['file']} [{c}]" for p in pairs for c in p["cases"]]
        rows.append(rec)
    return rows


def summarize(rows: list[dict]) -> dict:
    covers: dict[str, int] = {}
    for r in rows:
        covers[r["cover"] or "(빈칸)"] = covers.get(r["cover"] or "(빈칸)", 0) + 1
    mapped = [r for r in rows if r["maps"]]
    return {
        "rows": len(rows),
        "mapped_rows": len(mapped),
        "mappings": sum(len(r["maps"]) for r in mapped),
        "scenarios": sorted({p["file"] for r in mapped for p in r["pairs"] if p["cases"]}),
        "cover": covers,
        "file_without_case": [
            {"row": r["row"], "file": r["yaml_file"], "case": r["case_raw"][:40]}
            for r in rows if r["yaml_file"] and not r["maps"]
        ],
    }


def main(argv: list[str]) -> int:
    cfg_file = WEB_RUNNER_DIR / "config.local.json"
    cfg = json.loads(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}
    link = (cfg.get("checklist") or {}).get("url", "")
    if not link:
        print("config.local.json 의 checklist.url 이 비어 있습니다.", file=sys.stderr)
        print("매핑 완료본의 SharePoint 공유 링크를 넣으세요.", file=sys.stderr)
        return 2

    sheet = (cfg.get("checklist") or {}).get("sheet", SHEET)
    rows = fetch(link, sheet)
    info = summarize(rows)
    print(f"{sheet} — 행 {info['rows']}개 / 매핑된 행 {info['mapped_rows']}개 "
          f"/ 매핑 {info['mappings']}건 / 시나리오 {len(info['scenarios'])}종")
    print("  커버 상태: " + ", ".join(f"{k} {v}" for k, v in sorted(info["cover"].items())))
    miss = info["file_without_case"]
    if miss:
        print(f"  ⚠️ yaml 파일은 적혀 있는데 케이스 번호가 없는 행 {len(miss)}개 "
              "— 매핑에서 빠집니다")
        for m in miss[:8]:
            print(f"       row {m['row']:>4}  {m['file']:<22} {m['case']!r}")

    if "--dry-run" in argv:
        print("(dry-run — 쓰지 않았습니다)")
        return 0

    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "sheet": sheet,
        "first_row": rows[0]["row"] if rows else 0,
        "summary": info,
        "rows": rows,
    }
    CACHE_FILE.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(f"→ {CACHE_FILE.name} ({CACHE_FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
