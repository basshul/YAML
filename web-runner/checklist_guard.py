r"""시트에 쓰기 전에 **그 사이 누가 고쳤는지** 확인한다.

왜 필요한가 (2026-10-12 실제로 겪었다):
  스크립트가 매핑을 쓰고 "문제 0건" 으로 보고한 뒤, 사람이 같은 파일을 열어 몇 행을 손으로
  채웠다. 다음 실행이 그걸 모른 채 다시 쓰면 **사람의 판단이 조용히 지워진다.**

⛔ `lastModifiedDateTime` 으로는 안 된다 (2026-10-12 실측).
   workbook API 로 셀을 고쳐도 driveItem 의 수정 시각이 **바로 갱신되지 않는다** →
   셀을 바꾼 직후에도 "안 바뀌었다" 로 통과했다. 파일 메타데이터는 믿을 수 없다.
⛔ `lastModifiedBy` 로도 못 가른다 — 스크립트와 사람이 **같은 계정**으로 접근한다.

→ **우리가 쓴 내용 자체**를 지문(sha256)으로 남기고, 다음에 쓰기 전에 같은 범위를 다시 읽어
  비교한다. 메타데이터가 아니라 **값**을 보므로 지연도 계정 구분 문제도 없다.

⚠️ 기록은 이 PC 전용이다(.gitignore). 기록이 없으면 그냥 통과한다 —
   막는 것이 목적이 아니라 **모르고 덮어쓰는 것**을 막는 것이 목적이다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
STATE_FILE = WEB_RUNNER_DIR / "checklist_write_state.json"


def _load() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def fingerprint(values) -> str:
    """읽어 온 2차원 값의 지문. 공백만 다른 것은 같게 본다."""
    norm = [[str(c or "").strip() for c in row] for row in (values or [])]
    blob = json.dumps(norm, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def ensure_unchanged(key: str, values, *, force: bool = False) -> None:
    """우리가 마지막으로 쓴 뒤 그 범위가 바뀌었으면 멈춘다.

    `values` 는 **지금 시트에서 읽어 온** 그 범위의 값이다(호출자가 읽어서 넘긴다).
    """
    seen = _load().get(key)
    if not seen:
        print("  (이 범위에 쓴 기록이 없습니다 — 변경 검사를 건너뜁니다)")
        return
    now = fingerprint(values)
    if now == seen["fingerprint"]:
        return
    msg = ("\n[중단] 우리가 마지막으로 쓴 뒤 이 범위가 바뀌었습니다.\n"
           f"    범위       : {key}\n"
           f"    마지막 기록 : {seen.get('at', '?')} ({seen.get('label', '')})\n"
           "  사람이 손으로 고친 내용을 덮어쓸 수 있습니다. 먼저 내용을 확인하세요.\n"
           "  확인했고 그래도 쓰려면 --force 를 붙이세요.")
    if not force:
        raise SystemExit(msg)
    print(msg.replace("[중단]", "[경고] --force 로 무시하고 진행합니다 —"))


def record(key: str, values, label: str = "") -> None:
    """쓰기 **직후**에 부른다 — 쓴 내용을 다시 읽어 넘길 것."""
    from datetime import datetime
    state = _load()
    state[key] = {
        "fingerprint": fingerprint(values),
        "at": datetime.now().isoformat(timespec="seconds"),
        "label": label,
    }
    STATE_FILE.write_bytes(
        (json.dumps(state, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(f"  (변경 기준 기록: {key})")
