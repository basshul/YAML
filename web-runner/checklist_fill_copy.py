r"""신규 문서 **사본**의 매핑 열(I·J·K)을 채운다.

    python checklist_fill_copy.py            # 예행 — 쓸 내용만 보여준다
    python checklist_fill_copy.py --apply

무엇을 쓰나 — `I 커버 상태` · `J YAML 파일` · `K YAML 케이스`
  현재 문서(V2.1)의 행을 **확인 문구로** 맞춰 그 값을 옮긴다.
  ⛔ 애매한 것(후보 여럿·못 찾음)은 **비워 둔다.** 억지로 붙이면 화면엔 "매핑됨" 으로 보이면서
    엉뚱한 케이스를 가리킨다 — 가장 찾기 어려운 오류다. 그 목록은 보고서에 있다.

⚠️ 원본이 아니라 **사본**에만 쓴다. 사본 id 는 config 의 checklist.copy_item_id 다.
⚠️ 406행 × 3열을 **한 번의 PATCH** 로 쓴다. 셀 단위로 쓰면 1,200번 호출이 된다.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_RUNNER_DIR))
sys.path.insert(0, str(WEB_RUNNER_DIR.parent))

import gme_excel as G                  # noqa: E402
import checklist_migrate as M          # noqa: E402
import checklist_guard as guard        # noqa: E402

CFG = json.loads((WEB_RUNNER_DIR / "config.local.json").read_text(encoding="utf-8"))["checklist"]


def copy_ids() -> tuple[str, str]:
    """(driveId, 사본 itemId). 원본 id 와 같으면 멈춘다."""
    link = CFG["next_url"]
    sid = "u!" + base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
    it = G._req(f"{G.GRAPH}/shares/{sid}/driveItem", headers=G.H())
    drive, copy_id = it["parentReference"]["driveId"], CFG["copy_item_id"]
    if copy_id == it["id"]:
        raise SystemExit("[중단] 사본 id 가 원본과 같다 — 원본에 쓸 뻔했다.")
    return drive, copy_id


def workbook_of_copy() -> str:
    link = CFG["next_url"]
    sid = "u!" + base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
    it = G._req(f"{G.GRAPH}/shares/{sid}/driveItem", headers=G.H())
    drive = it["parentReference"]["driveId"]
    copy_id = CFG["copy_item_id"]
    if copy_id == it["id"]:
        raise SystemExit("[중단] 사본 id 가 원본과 같다 — 원본에 쓸 뻔했다.")
    return f"{G.GRAPH}/drives/{drive}/items/{copy_id}/workbook"


def main(argv: list[str]) -> int:
    dry = "--apply" not in argv
    # 쓰는 대상은 **사본**이다(workbook_of_copy) → 시트명도 사본 것을 쓴다.
    #   2026-10-23 next_sheet 에서 교정. copy_ids()/workbook_of_copy() 가 next_url 을
    #   쓰는 건 그대로 둔다 — 거기선 **원본 id 와 같으면 멈추는 가드**에 원본이 필요하다.
    sheet = CFG["sheet"]

    # 현재 문서에서 '확인 문구 → (매핑, 커버 상태)' 를 만든다
    # ⛔ 대조 기준은 **구 문서(V2.1)** 다 → `prev_*` 로 읽는다.
    #   `url`/`sheet` 는 2026-10-13 전환 이후 **사본(V2.2)** 을 가리킨다 —
    #   그걸 쓰면 사본을 사본과 대조해 조용히 0건이 된다.
    _, cur = M.load(CFG["prev_url"], CFG["prev_sheet"])
    by_deep = M.build_index(cur, lambda r: (M.norm(r.get("d1")), M.norm(r.get("d2")),
                                            M.norm(r.get("d3")), M.norm(r.get("text"))))
    by_text = M.build_index(cur, lambda r: M.norm(r.get("text")))
    by_head = M.build_index(cur, lambda r: M.head(r.get("text")))

    wb = workbook_of_copy()

    def read(a1):
        return G._req(G._range(wb, sheet, a1), headers=G.H())["values"]

    import checklist_layout as L
    lay = L.detect(read)
    lay.sheet = sheet
    rows = [r for r in read(lay.range()) if lay.get(r, "text")]
    print(f"사본 {sheet} — 데이터 {len(rows)}행 (시작 {lay.first_row}행)")

    out, filled, blank = [], 0, []
    for off, raw in enumerate(rows):
        text = lay.get(raw, "text")
        cid = lay.get(raw, "case_id")
        src = None
        for cands in (by_deep[(M.norm(lay.get(raw, "d1")), M.norm(lay.get(raw, "d2")),
                               M.norm(lay.get(raw, "d3")), M.norm(text))],
                      by_text[M.norm(text)],
                      by_head[M.head(text)]):
            if len(cands) == 1:
                src = cands[0]
                break
        if src and (src.get("yaml_file") or "").strip():
            out.append([src.get("cover", ""), src.get("yaml_file", ""), src.get("yaml_case", "")])
            filled += 1
        else:
            # 매핑이 없거나 애매하다 → 비워 둔다. 커버 상태만이라도 있으면 옮긴다.
            out.append([src.get("cover", "") if src else "", "", ""])
            blank.append((cid, text[:46].replace("\n", " ")))

    last = lay.first_row + len(rows) - 1
    rng = f"I{lay.first_row}:K{last}"
    print(f"  채울 범위 {rng} — 매핑 기입 {filled}행 / 비워 둠 {len(blank)}행")
    print("  표본:")
    for r, o in list(zip(rows, out))[:3]:
        print(f"    {lay.get(r,'case_id'):<9} {o}")
    if blank:
        print(f"  비워 두는 것 {len(blank)}행 중 앞 5개 (보고서에 전체가 있다):")
        for cid, t in blank[:5]:
            print(f"    {cid:<9} {t}")

    if dry:
        print("\n(예행 — 쓰지 않았습니다. --apply 를 붙이세요)")
        return 0

    copy_ids()   # 원본에 쓰지 않는지 확인
    key = f"{sheet}!{rng}"
    # ⛔ 우리가 마지막으로 쓴 뒤 사람이 고쳤으면 멈춘다 — 그 판단을 덮어쓰면 안 된다
    guard.ensure_unchanged(key, read(rng), force="--force" in argv)
    G._req(G._range(wb, sheet, rng), "PATCH", {"values": out}, headers=G.H())
    print(f"\n기입 완료 — {rng} ({len(out)}행 × 3열, PATCH 1회)")
    guard.record(key, read(rng), "fill_copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
