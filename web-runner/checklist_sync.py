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
import runner                                      # noqa: E402

CACHE_FILE = WEB_RUNNER_DIR / "checklist_cache.json"
SHEET = "Checklist(Livetest)"
FIRST_ROW = 10                 # 8행 머리글 / 9행 빈 줄 / 10행부터 데이터
RANGE = f"B{FIRST_ROW}:L600"   # 넉넉히 읽고 뒤쪽 빈 행은 잘라낸다

# B Priority / C 1Depth / D 2Depth / E 3Depth / F Checklist
# G 커버 상태 / H YAML 파일 / I YAML 케이스 / J 완료일 / K 커버상태(Old) / L 검토 필요
COLS = ["priority", "d1", "d2", "d3", "text",
        "cover", "yaml_file", "yaml_case", "done_date", "cover_old", "review"]

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
#   13_01_Rate_Indonesia_old.yaml(인도네시아 [07]) /
#   13_02_Sender_Mongolia_old.yaml(몽골 [07-1]) /
#   13_03_Sender_Vietnam_old.yaml(베트남 [07-2])
# → 파일마다 괄호 안에 **자기 케이스 번호**가 적혀 있다. 셀 전체를 파일명 하나로 읽으면
#   나머지 둘이 통째로 빠진다(13_01·13_02 가 '체크리스트 행 없음' 으로 보였다).
PAIR_RE = re.compile(r"([^/()]+?)\s*\(([^)]*)\)")


def split_pairs(file_cell: str, case_cell: str) -> list[dict]:
    """(파일, 케이스들) 짝의 목록을 만든다. 보통 1개, 합쳐 적힌 셀이면 여러 개."""
    groups = PAIR_RE.findall(file_cell or "")
    pairs = []
    for name, inside in groups:
        cases = []
        for tok in CASE_TOKEN_RE.findall(inside):
            num = runner.case_id(tok)
            if num and num not in cases:
                cases.append(num)
        if cases:
            pairs.append({"file": name.strip(), "cases": cases})
    if len(pairs) >= 2:
        return pairs
    # 평범한 셀 — 파일은 H, 케이스는 I 에서 읽는다
    cases = []
    for tok in CASE_TOKEN_RE.findall(case_cell or ""):
        num = runner.case_id(tok)
        if num and num not in cases:
            cases.append(num)
    return [{"file": (file_cell or "").strip(), "cases": cases}]


def _cell(row: list, i: int) -> str:
    if i >= len(row) or row[i] is None:
        return ""
    return str(row[i]).strip()


def fetch(link: str) -> list[dict]:
    wb, _ = gme_excel.workbook_url(link)
    url = gme_excel._range(wb, SHEET, RANGE)
    values = gme_excel._req(url, headers=gme_excel.H())["values"]

    rows = []
    for offset, raw in enumerate(values):
        row_no = FIRST_ROW + offset
        rec = {COLS[i]: _cell(raw, i) for i in range(len(COLS))}
        if not any(rec.values()):
            continue
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

    rows = fetch(link)
    info = summarize(rows)
    print(f"{SHEET} — 행 {info['rows']}개 / 매핑된 행 {info['mapped_rows']}개 "
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
        "sheet": SHEET,
        "first_row": FIRST_ROW,
        "summary": info,
        "rows": rows,
    }
    CACHE_FILE.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(f"→ {CACHE_FILE.name} ({CACHE_FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
