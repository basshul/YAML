r"""현재 문서(V2.1)의 매핑을 신규 문서(V2.2)의 **Case ID 기준**으로 옮긴다.

    python checklist_migrate.py            # 예행 — 결과만 보여준다
    python checklist_migrate.py --apply    # checklist_mapping.json 을 쓴다

왜 Case ID 인가:
  V2.2 에는 매핑 열이 **없다**. 대신 행마다 **고유한 Case ID**(`OVS-001` 등)가 있다.
  매핑을 시트가 아니라 저장소(`checklist_mapping.json`)에 두고 Case ID 로 잇는다.
  · 시트 구조가 또 바뀌어도 매핑이 안 깨진다(이번처럼 열이 밀려도 무관하다)
  · QA 원본 시트를 자동화 메타로 오염시키지 않는다
  · 매핑이 git 에 남아 **누가 언제 왜 바꿨는지**가 추적된다

맞추는 방법 — 사람이 쓴 **확인 문구**로 잇는다(행 번호는 믿을 수 없다. 행이 추가·분리됐다):
  1차  깊이(1~3Depth) + 문구가 **정확히** 1:1
  2차  문구만 1:1 (깊이 분류가 바뀐 행)
  3차  문구 앞부분(설명 `— …` 을 떼고) 1:1 — 우리가 문구를 다듬은 행이 있다
  그 밖은 **사람이 봐야 한다** → 후보와 함께 목록으로 뽑는다. 억지로 붙이지 않는다.

⛔ 애매한 것을 자동으로 붙이면 **틀린 매핑이 조용히 들어간다.** 매핑이 틀리면
   화면에는 "매핑됨" 으로 보이면서 엉뚱한 케이스를 가리킨다 — 가장 찾기 어려운 종류다.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_RUNNER_DIR))
sys.path.insert(0, str(WEB_RUNNER_DIR.parent))

import gme_excel                       # noqa: E402
import checklist_layout as layout      # noqa: E402

MAPPING_FILE = WEB_RUNNER_DIR / "checklist_mapping.json"
REPORT_FILE = WEB_RUNNER_DIR / "checklist_migrate_report.md"


def reader(link: str, sheet: str):
    wb, _ = gme_excel.workbook_url(link)

    def f(a1):
        return gme_excel._req(gme_excel._range(wb, sheet, a1), headers=gme_excel.H())["values"]
    return f


def load(link: str, sheet: str) -> tuple[layout.Layout, list[dict]]:
    f = reader(link, sheet)
    lay = layout.detect(f)
    lay.sheet = sheet
    rows = []
    for off, raw in enumerate(f(lay.range())):
        rec = {k: lay.get(raw, k) for k in lay.idx}
        if not rec.get("text"):
            continue
        rec["row"] = lay.first_row + off
        rows.append(rec)
    return lay, rows


# ── 문구 맞추기 ────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    return re.sub(r"[\s​]+", "", str(s or "")).lower()


def head(s: str) -> str:
    """설명 꼬리(`— …` / ` - …`)를 떼고 기호를 지운 앞부분."""
    s = re.split(r"[—–]|\s-\s", str(s or ""))[0]
    return re.sub(r"[\s​()\[\]/·,.]+", "", s).lower()


def build_index(rows, keyfn):
    d = collections.defaultdict(list)
    for r in rows:
        d[keyfn(r)].append(r)
    return d


def main(argv: list[str]) -> int:
    cfg = json.loads((WEB_RUNNER_DIR / "config.local.json").read_text(encoding="utf-8"))
    cl = cfg.get("checklist", {})
    cur_link = cl.get("prev_url") or cl.get("url", "")   # 구 문서(V2.1). 전환 후엔 prev_*
    new_link = cl.get("next_url", "")
    new_sheet = cl.get("next_sheet", "Checklist(Livetest) (2.2)")
    if not cur_link or not new_link:
        print("config.local.json 의 checklist.prev_url(구 문서) 과 checklist.next_url(신규) 이 필요합니다.",
              file=sys.stderr)
        return 2

    cur_lay, cur_rows = load(cur_link, cl.get("prev_sheet") or cl.get("sheet", "Checklist(Livetest)"))
    new_lay, new_rows = load(new_link, new_sheet)
    print(f"현재 {len(cur_rows)}행 / 신규 {len(new_rows)}행")
    if not new_lay.has_case_id:
        print("신규 시트에 Case ID 열이 없습니다 — 이 방식을 쓸 수 없습니다.", file=sys.stderr)
        return 2

    by_deep = build_index(new_rows, lambda r: (norm(r.get("d1")), norm(r.get("d2")),
                                               norm(r.get("d3")), norm(r.get("text"))))
    by_text = build_index(new_rows, lambda r: norm(r.get("text")))
    by_head = build_index(new_rows, lambda r: head(r.get("text")))

    mapping: dict[str, list[str]] = {}
    how = collections.Counter()
    manual: list[dict] = []

    mapped = [r for r in cur_rows if r.get("yaml_file") and r.get("yaml_case")]
    for r in mapped:
        maps = f"{r['yaml_file'].strip()} {r['yaml_case'].strip()}"
        for tag, cands in (
            ("깊이+문구", by_deep[(norm(r.get("d1")), norm(r.get("d2")),
                                 norm(r.get("d3")), norm(r.get("text")))]),
            ("문구", by_text[norm(r.get("text"))]),
            ("문구앞부분", by_head[head(r.get("text"))]),
        ):
            if len(cands) == 1:
                cid = cands[0]["case_id"]
                mapping.setdefault(cid, [])
                if maps not in mapping[cid]:
                    mapping[cid].append(maps)
                how[tag] += 1
                break
        else:
            cands = by_head[head(r.get("text"))]
            manual.append({
                "현재행": r["row"],
                "확인항목": re.sub(r"\s+", " ", r.get("text", ""))[:60],
                "매핑": maps,
                "후보": [f'{c["case_id"]} {re.sub(chr(10), " ", c.get("text", ""))[:40]}'
                        for c in cands[:4]] or ["(없음)"],
            })
            how["사람 확인"] += 1

    # 신규에만 있는 행 — 새로 매핑해야 할 후보
    cur_heads = {head(r.get("text")) for r in cur_rows}
    only_new = [r for r in new_rows if head(r.get("text")) not in cur_heads]

    print()
    print("이전 결과:", dict(how))
    print(f"  Case ID {len(mapping)}개에 매핑 {sum(len(v) for v in mapping.values())}건")
    print(f"  사람이 볼 것 {len(manual)}건 / 신규에만 있는 행 {len(only_new)}건")

    lines = ["# 체크리스트 이전 보고 (V2.1 → V2.2)", "",
             f"- 자동 이전: **{sum(v for k, v in how.items() if k != '사람 확인')}건**"
             f" (깊이+문구 {how['깊이+문구']} · 문구 {how['문구']} · 앞부분 {how['문구앞부분']})",
             f"- 사람이 볼 것: **{len(manual)}건**",
             f"- 신규에만 있는 행: **{len(only_new)}건**", "",
             "## 사람이 볼 것 — 자동으로 붙이지 않았다", "",
             "| 현재행 | 확인 항목 | 기존 매핑 | 신규 후보 |", "|---|---|---|---|"]
    for m in manual:
        lines.append(f"| {m['현재행']} | {m['확인항목']} | `{m['매핑']}` | "
                     + "<br>".join(m["후보"]) + " |")
    lines += ["", "## 신규에만 있는 행 — 매핑이 필요하다", "",
              "| Case ID | 2Depth | 확인 항목 |", "|---|---|---|"]
    for r in only_new:
        lines.append(f"| {r['case_id']} | {r.get('d2','')[:18]} | "
                     + re.sub(r"\s+", " ", r.get("text", ""))[:60] + " |")
    REPORT_FILE.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"→ {REPORT_FILE.name}")

    if "--apply" not in argv:
        print("\n(예행 — checklist_mapping.json 을 쓰지 않았습니다. --apply 를 붙이세요)")
        return 0

    payload = {
        "_주의": "매핑의 정본이다. Case ID 로 잇는다 — 시트 구조가 바뀌어도 안 깨진다.",
        "_만든_방법": "checklist_migrate.py (V2.1 의 H·I 열을 문구로 맞춰 옮겼다)",
        "mapping": dict(sorted(mapping.items())),
    }
    MAPPING_FILE.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(f"→ {MAPPING_FILE.name} ({MAPPING_FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
