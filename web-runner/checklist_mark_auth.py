r"""생체인식·OTP 분기 행의 **커버 상태**를 `자동화 불가능` 으로 적는다.

    python checklist_mark_auth.py           # 예행 — 바꿀 행만 보여준다
    python checklist_mark_auth.py --apply

왜 자동화 불가능인가:
  생체인식은 `docs/ENVIRONMENT.md §1.1` 이 '기기 생체인증 OFF' 를 전제로 깔고 있다
  (켜면 PIN 대신 지문 시트가 떠 다른 플로우가 줄줄이 깨진다). OTP 는 물리 매체다.
  둘 다 Maestro 로 건드릴 수 없다 — 매핑 누락이 아니라 **범위 밖**이다.

⛔ 3Depth 는 **병합셀**이다. 앞값으로 통째 채우면 묶음 경계를 넘어가
   엉뚱한 행까지 'Biometric' 으로 본다(263~278행에서 실제로 그랬다).
   → 묶음은 **연속 구간**으로 끊는다: 3Depth 에 글자가 있는 행에서 시작해,
     3Depth/2Depth/1Depth 가 비어 있고 Case ID 접두사가 같은 동안만 이어진다.

⛔ **매핑된 행은 건드리지 않는다.** 묶음 안에 이미 자동화된 행이 섞여 있다
   (예: 232행 OVS-030 은 '생체인식' 묶음이지만 완료다).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parent
sys.path.insert(0, str(W))
sys.path.insert(0, str(W.parent))

import gme_excel as G                 # noqa: E402
import checklist_sync as cs           # noqa: E402
import checklist_fill_copy as F       # noqa: E402
import checklist_guard as guard       # noqa: E402

CFG = json.loads((W / "config.local.json").read_text(encoding="utf-8"))["checklist"]
S = CFG["next_sheet"]
VALUE = "자동화 불가능"

AUTH = re.compile(r"생체|지문|biometric|fingerprint|\bOTP\b", re.I)
PREFIX = re.compile(r"^([A-Za-z]+)")


def pre(cid: str) -> str:
    m = PREFIX.match(cid or "")
    return m.group(1).upper() if m else ""


def blocks(rows: list[dict]) -> None:
    """각 행에 그 행이 속한 3Depth 묶음 이름을 `_block` 으로 달아 준다."""
    cur, cur_pre = "", ""
    for r in rows:
        d3, d2, d1 = r.get("d3", ""), r.get("d2", ""), r.get("d1", "")
        if d3:                       # 새 묶음이 시작된다
            cur, cur_pre = d3, pre(r["case_id"])
        elif d2 or d1 or pre(r["case_id"]) != cur_pre:
            cur, cur_pre = "", pre(r["case_id"])   # 구간이 끊겼다
        r["_block"] = cur


def main(argv: list[str]) -> int:
    dry = "--apply" not in argv
    rows = cs.fetch(CFG["copy_url"], S)
    blocks(rows)

    hits = []
    for r in rows:
        if r.get("yaml_file"):                 # 매핑된 행은 그대로 둔다
            continue
        why = "문구" if AUTH.search(r["text"]) else ("묶음" if AUTH.search(r["_block"]) else "")
        if not why:
            continue
        if r.get("cover", "").strip() == VALUE:
            continue                           # 이미 그렇게 적혀 있다
        hits.append((r, why))

    print(f"바꿀 행 {len(hits)}건 (이미 '{VALUE}' 인 행은 뺀다)\n")
    for r, why in hits:
        t = re.sub(r"\s+", " ", r["text"])[:54]
        print(f"  {r['row']:>4} {r['case_id']:<9} {why} "
              f"[{r.get('cover','') or '빈칸'}→{VALUE}]  {r['_block'][:20]:<20} {t}")

    if dry or not hits:
        print("\n(예행 — 쓰지 않았습니다. --apply 를 붙이세요)" if dry else "\n바꿀 것이 없다.")
        return 0

    F.copy_ids()                               # 원본에 쓰지 않는지 확인
    wb = F.workbook_of_copy()
    first, last = rows[0]["row"], rows[-1]["row"]
    rng = f"I{first}:K{last}"

    def read(a1):
        return G._req(G._range(wb, S, a1), headers=G.H())["values"]

    cur = read(rng)
    guard.ensure_unchanged(f"{S}!{rng}", cur, force="--force" in argv)

    # 읽어 온 값을 그대로 두고 **커버 상태(I)만** 바꿔 한 번에 쓴다
    for r, _ in hits:
        cur[r["row"] - first][0] = VALUE
    G._req(G._range(wb, S, rng), "PATCH", {"values": cur}, headers=G.H())
    print(f"\n기입 완료 — {rng} 중 커버 상태 {len(hits)}행 (PATCH 1회)")
    time.sleep(4)
    guard.record(f"{S}!{rng}", read(rng), "mark_auth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
