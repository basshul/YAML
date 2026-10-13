r"""문구가 달라 못 찾은 행을 **기존 매핑이 가리키는 시나리오**로 좁힌다.

    python checklist_narrow.py            # 후보를 보여준다
    python checklist_narrow.py --apply    # 후보가 **하나뿐인 것만** 기입한다

왜 이 방법인가:
  남은 행들은 우리가 기존 문서에서 문구를 다듬어 놓은 것이 많다(`— 설명` 덧붙임).
  글자로는 신규 문서와 안 맞지만, **어느 시나리오를 덮는지는 이미 적혀 있다.**
  이미 맞춰진 매핑에서 `Case ID 접두사 ↔ yaml 시나리오` 대응을 배우면
  (예: `05_InitialScreen` ↔ `INI`), 후보를 그 접두사의 **아직 안 매핑된 행**으로 좁힐 수 있다.

⛔ 후보가 여럿이면 **기입하지 않는다.** 억지로 붙이면 화면엔 "매핑됨" 으로 보이면서
   엉뚱한 케이스를 가리킨다 — 가장 찾기 어려운 오류다.
"""

from __future__ import annotations

import collections
import json
import re
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parent
sys.path.insert(0, str(W))
sys.path.insert(0, str(W.parent))

import gme_excel as G                # noqa: E402
import checklist_migrate as M        # noqa: E402
import checklist_sync as cs          # noqa: E402
import checklist_fill_copy as F      # noqa: E402
import checklist_guard as guard      # noqa: E402

CFG = json.loads((W / "config.local.json").read_text(encoding="utf-8"))["checklist"]
S = CFG["next_sheet"]
PREFIX = re.compile(r"^([A-Za-z]+)")


def pre(cid: str) -> str:
    m = PREFIX.match(cid or "")
    return m.group(1).upper() if m else ""


def scen(name: str) -> str:
    n = re.sub(r"^.*[\\/]", "", str(name or ""))
    n = re.sub(r"\.ya?ml$", "", n, flags=re.I)
    return re.sub(r"_old$", "", n, flags=re.I).replace(" ", "").lower()


def toks(s: str) -> set:
    s = re.sub(r"[^\w가-힣]+", " ", str(s or "")).lower()
    return {w for w in s.split() if len(w) > 1}


def main(argv):
    dry = "--apply" not in argv
    _, cur = M.load(CFG["url"], CFG.get("sheet", "Checklist(Livetest)"))
    new = cs.fetch(CFG["copy_url"], S)

    # ① 이미 맞춰진 것에서 접두사 ↔ 시나리오를 배운다
    by_scen = collections.defaultdict(collections.Counter)
    for r in new:
        if r.get("yaml_file"):
            by_scen[scen(r["yaml_file"])][pre(r["case_id"])] += 1

    landed = {f'{r["yaml_file"]} {r["yaml_case"]}' for r in new if r.get("yaml_file")}
    free = [r for r in new if not r.get("yaml_file")]

    rows, single = [], []
    for r in cur:
        s = f'{r["yaml_file"].strip()} {r["yaml_case"].strip()}'
        if not r.get("yaml_file", "").strip() or s in landed:
            continue
        prefixes = set(by_scen.get(scen(r["yaml_file"]), {}))
        cands = [c for c in free if pre(c["case_id"]) in prefixes] if prefixes else []
        rt = toks(r.get("text"))
        scored = sorted(((len(rt & toks(c["text"])), c) for c in cands),
                        key=lambda x: -x[0])
        rows.append((r, prefixes, scored))
        if len(scored) == 1 and scored[0][0] > 0:
            single.append((r, scored[0][1]))

    print(f"문구가 달라 못 찾은 행 {len(rows)}건\n")
    for r, pfx, scored in rows:
        txt = re.sub(r"\s+", " ", r.get("text", ""))[:46]
        print(f"■ 현재 {r['row']}행  {txt}")
        print(f"    기존 {r['yaml_file']} {r['yaml_case'][:40]}   (접두사 {sorted(pfx) or '—'})")
        for n, c in scored[:3]:
            print(f"      {n}점 {c['case_id']:<9} {re.sub(chr(10),' ',c['text'])[:48]}")
        if not scored:
            print("      (그 시나리오의 빈 행이 없다 — 이미 다 찼거나 신규에 없다)")
    print(f"\n후보가 **하나뿐**인 것: {len(single)}건")
    for r, c in single:
        print(f"    {r['row']:>4} → {c['case_id']}")

    if dry or not single:
        print("\n(예행 — 쓰지 않았습니다)" if dry else "")
        return 0

    F.copy_ids()
    wb = F.workbook_of_copy()

    def read(a1):
        return G._req(G._range(wb, S, a1), headers=G.H())["values"]
    rng_all = f"I11:K{11 + len(new) - 1}"
    guard.ensure_unchanged(f"{S}!{rng_all}", read(rng_all), force="--force" in argv)
    for r, c in single:
        G._req(G._range(wb, S, f"I{c['row']}:K{c['row']}"), "PATCH",
               {"values": [[r.get("cover", ""), r["yaml_file"], r["yaml_case"]]]},
               headers=G.H())
    print(f"\n기입 완료 — {len(single)}행")
    time.sleep(4)
    guard.record(f"{S}!{rng_all}", read(rng_all), "narrow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
