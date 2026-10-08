r"""사용자 프로파일(`Maestro\env\user.<이름>.env`)을 읽는 **유일한** 창구.

왜 러너와 같은 파일을 읽나:
  maestro 플로우는 `-User` 로 이 파일을 env 에 싣고, admin 사전 점검은 같은 값으로
  대상 계정을 정한다. **두 군데에 적으면 반드시 어긋난다** — 계정 하나를 바꾸고
  한쪽만 고치는 순간, 점검은 통과하는데 플로우는 다른 계정으로 도는 상태가 된다.
  그래서 정체성은 env 파일 한 곳에 두고 양쪽이 그걸 읽는다.

⚠️ 이름은 **파일 경로의 일부**가 된다 → `runner.USER_CHOICES` 허용 목록으로만 받는다.
   여기서도 한 번 더 막는다(이 모듈만 따로 쓰는 경우가 생길 수 있다).
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
ENV_DIR = WEB_RUNNER_DIR.parent / "Maestro" / "env"

# 이름에 경로 문자가 섞이면 상위 폴더로 빠져나갈 수 있다 → 글자·숫자만 받는다.
SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


class ProfileUnavailable(RuntimeError):
    """프로파일이 없거나 읽을 수 없다. 화면은 이 사유를 그대로 보여준다."""


def path_of(user: str) -> Path:
    if not SAFE_NAME.match(user or ""):
        raise ProfileUnavailable(f"사용자 이름이 올바르지 않습니다: {user!r}")
    return ENV_DIR / f"user.{user}.env"


def load(user: str) -> dict[str, str]:
    """KEY=VALUE 를 그대로 읽는다. 주석(`#`)과 빈 줄은 건너뛴다.

    ★ 값 뒤의 `# 설명` 은 **주석이 아니다.** 러너(`Add-EnvFile`)가 줄 전체를 값으로
      넘기므로 여기서도 똑같이 다뤄야 양쪽이 같은 값을 본다. 줄 끝 주석을 쓰려면
      러너부터 고쳐야 한다 — 지금은 쓰지 않는 것이 규칙이다.
    """
    p = path_of(user)
    if not p.exists():
        raise ProfileUnavailable(f"사용자 프로파일이 없습니다: {p.name}")
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def accounts(user: str) -> dict[str, str]:
    """계정 키만 추려 돌려준다. **빈 값은 뺀다** — 아직 계정이 없다는 뜻이다."""
    prof = load(user)
    keys = ("ACCT_MAIN", "ACCT_FOREIGN", "ACCT_GMEPAY", "ACCT_SIGNUP_1", "ACCT_SIGNUP_2")
    return {k: prof[k] for k in keys if prof.get(k)}
