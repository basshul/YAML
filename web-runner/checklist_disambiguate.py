r"""문구가 같아 못 갈랐던 행을 **이미 안착한 매핑에서 배운 규칙**으로 가른다.

    python checklist_disambiguate.py            # 예행 — 무엇을 어떻게 갈랐는지 보여준다
    python checklist_disambiguate.py --apply    # 사본의 I·J·K 에 쓴다

문제: 신규 문서에 같은 문구가 둘 있으면(예 `Chat 화면 이동 확인` 이 INI-006 과 LGN-004)
      문구만으로는 못 가른다. 찍으면 절반은 틀리고, 틀려도 화면엔 "매핑됨" 으로 보인다.

푸는 법 — **이미 1:1 로 붙은 284건이 정답지다.** 거기서 두 가지를 배운다:
  · 접두사 → 기존 1Depth   (INI 는 어떤 영역인가)
  · 접두사 → yaml 시나리오 (INI 는 어떤 파일들과 붙는가)
그 다음 애매한 행의 **기존 1Depth / 기존 yaml 시나리오**가 어느 후보와 맞는지 본다.

⛔ **한쪽이 확실히 이길 때만** 고른다. 비기거나 둘 다 0점이면 그대로 비워 사람에게 남긴다.
   자동화가 애매한 것을 메우기 시작하면, 틀린 매핑이 '사람이 확인한 것' 사이에 섞여 버린다.
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

import gme_excel as G                  # noqa: E402
import checklist_migrate as M          # noqa: E402
import checklist_sync as cs            # noqa: E402
import checklist_fill_copy as F        # noqa: E402
import checklist_layout as L           # noqa: E402
import checklist_guard as guard        # noqa: E402

CFG = json.loads((WEB_RUNNER_DIR / "config.local.json").read_text(encoding="utf-8"))["checklist"]
PREFIX = re.compile(r"^([A-Za-z]+)")


def prefix_of(case_id: str) -> str:
    m = PREFIX.match(case_id or "")
    return m.group(1).upper() if m else ""


def scenario_of(yaml_file: str) -> str:
    return re.sub(r"\s+", "", (yaml_file or "")).lower()


def main(argv: list[str]) -> int:
    dry = "--apply" not in argv
    # 시트명은 여는 문서의 것 — 아래는 사본(copy_url)을 연다(2026-10-23 next_sheet 에서 교정).
    sheet = CFG["sheet"]

    # ⛔ 대조 기준은 **구 문서(V2.1)** 다 → `prev_*` 로 읽는다.
    #   `url`/`sheet` 는 2026-10-13 전환 이후 **사본(V2.2)** 을 가리킨다 —
    #   그걸 쓰면 사본을 사본과 대조해 조용히 0건이 된다.
    _, cur = M.load(CFG["prev_url"], CFG["prev_sheet"])
    new = cs.fetch(CFG["copy_url"], sheet)

    # ── 1) 이미 안착한 것에서 규칙을 배운다 ───────────────────────────
    #    (사본에 이미 기입된 행 = 문구로 1:1 확정된 것들)
    depth_of = collections.defaultdict(collections.Counter)   # 접두사 → 기존 1Depth 분포
    scen_of = collections.defaultdict(collections.Counter)    # 접두사 → yaml 시나리오 분포
    cur_by_map = collections.defaultdict(list)
    for r in cur:
        if (r.get("yaml_file") or "").strip():
            cur_by_map[f'{r["yaml_file"].strip()} {r["yaml_case"].strip()}'].append(r)

    for r in new:
        if not r.get("yaml_file"):
            continue
        p = prefix_of(r.get("case_id", ""))
        scen_of[p][scenario_of(r["yaml_file"])] += 1
        for src in cur_by_map.get(f'{r["yaml_file"]} {r["yaml_case"]}', []):
            depth_of[p][M.norm(src.get("d1"))] += 1
    print(f"학습 — 접두사 {len(scen_of)}종 (안착한 행에서)")

    # ── 2) 애매했던 행을 다시 본다 ────────────────────────────────────
    by_text = M.build_index(new, lambda r: M.norm(r.get("text")))
    landed = {f'{r["yaml_file"]} {r["yaml_case"]}' for r in new if r.get("yaml_file")}

    picks, ties = [], []
    for r in cur:
        s = f'{r["yaml_file"].strip()} {r["yaml_case"].strip()}'
        if not r.get("yaml_file") or s in landed:
            continue
        cands = [c for c in by_text[M.norm(r.get("text"))] if not c.get("yaml_file")]
        if len(cands) < 2:
            continue
        scored = []
        for c in cands:
            p = prefix_of(c.get("case_id", ""))
            pt = (2 if scen_of[p].get(scenario_of(r["yaml_file"])) else 0) \
                + (1 if depth_of[p].get(M.norm(r.get("d1"))) else 0)
            scored.append((pt, c))
        scored.sort(key=lambda x: -x[0])
        top = scored[0]
        if top[0] > 0 and (len(scored) == 1 or top[0] > scored[1][0]):
            picks.append((r, top[1], top[0], [(p, c["case_id"]) for p, c in scored]))
        else:
            ties.append((r, [(p, c["case_id"]) for p, c in scored]))

    print(f"\n갈라진 것 {len(picks)}건 / 여전히 비김 {len(ties)}건")
    for r, c, pt, sc in picks:
        print(f"  행{r['row']:>4} {re.sub(r'[|s]+',' ',r.get('text',''))[:34]:<36}"
              f" → {c['case_id']:<9} ({pt}점, 후보 {sc})")
        print(f"        기존 매핑 {r['yaml_file']} {r['yaml_case'][:28]}")
    for r, sc in ties:
        print(f"  [비김] 행{r['row']:>4} {re.sub(r'\\s+',' ',r.get('text',''))[:34]:<36} 후보 {sc}")

    if dry or not picks:
        print("\n(예행 — 쓰지 않았습니다)" if dry else "\n쓸 것이 없습니다.")
        return 0

    F.copy_ids()   # 원본에 쓰지 않는지 확인


    wb = F.workbook_of_copy()

    def read(a1):
        return G._req(G._range(wb, sheet, a1), headers=G.H())["values"]
    lay = L.detect(read)
    col_i = L.col_letter(lay.idx["cover"])
    col_k = L.col_letter(lay.idx["yaml_case"])
    rng_all = f"{col_i}{lay.first_row}:{col_k}{lay.first_row + len(new) - 1}"
    # ⛔ 우리가 마지막으로 쓴 뒤 바뀌었으면 멈춘다
    guard.ensure_unchanged(f"{sheet}!{rng_all}", read(rng_all), force="--force" in argv)
    for r, c, _pt, _sc in picks:
        rng = f"{col_i}{c['row']}:{col_k}{c['row']}"
        G._req(G._range(wb, sheet, rng), "PATCH",
               {"values": [[r.get("cover", ""), r["yaml_file"], r["yaml_case"]]]},
               headers=G.H())
    print(f"\n기입 완료 — {len(picks)}행")
    guard.record(f"{sheet}!{rng_all}", read(rng_all), "disambiguate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
