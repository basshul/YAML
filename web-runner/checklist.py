r"""체크리스트 캐시를 읽는 **유일한** 창구.

서버는 SharePoint 에 직접 붙지 않는다 — 토큰이 사람 계정이고 refresh 가 만료되면
브라우저 인증이 필요한데 서버는 그걸 못 한다(docs/CHECKLIST.md §11).
받아오는 건 `checklist_sync.py`(사람이 돌린다), 서버는 그 결과만 읽는다.
→ SharePoint 가 끊겨도 **읽기 화면은 캐시로 계속 돈다.**

★ 매핑 검증(시나리오·케이스가 실제로 있는지)은 **화면에서** 한다.
  `/api/tests` 가 이미 시나리오별 케이스를 들고 있어서, 서버가 또 조회할 이유가 없다
  (그 조회는 pwsh 를 거쳐 20초쯤 걸린다).
"""

from __future__ import annotations

import json
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
CACHE_FILE = WEB_RUNNER_DIR / "checklist_cache.json"


class ChecklistUnavailable(RuntimeError):
    """캐시가 없거나 읽을 수 없다. 화면은 이 사유를 그대로 보여준다."""


def load() -> dict:
    if not CACHE_FILE.exists():
        raise ChecklistUnavailable(
            "체크리스트 캐시가 없습니다. `python checklist_sync.py` 로 먼저 받아오세요.")
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ChecklistUnavailable(f"캐시를 읽지 못했습니다: {exc}") from exc
    data["cache_file"] = CACHE_FILE.name
    return data
