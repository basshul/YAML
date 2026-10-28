"""PowerShell 스크립트(run_test.ps1 / run_suite.ps1)를 부르는 **유일한** 창구.

⚠️ 설계 규칙 — 이 파일 밖에서는 run_test.ps1 / run_suite.ps1 을 직접 부르지 않는다.
   서버(server.py)든 화면이든 전부 이 모듈의 함수를 거친다. 나중에 Mac 으로 옮길 때
   고쳐야 할 곳이 여기 하나로 끝나게 하려는 것이다(PowerShell → shell 치환).
"""

from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_RUNNER_DIR.parent
MAESTRO_DIR = REPO_ROOT / "Maestro"
SUITE_SCRIPT = MAESTRO_DIR / "run_suite.ps1"
RUN_LOG_DIR = WEB_RUNNER_DIR / "run_logs"
PARAM_BLOCK_RE = r"^param\s*\((.*?)^\)"
VAR_RE = r"\$(\w+)"

# 사용자 프로파일 — `Maestro\env\user.<이름>.env` 와 **이름이 1:1로 맞아야** 한다.
#   ⚠️ 이 값은 파일 경로이자 명령행 인자가 된다 → **허용 목록으로만** 받는다.
#      화면에서 온 문자열을 그대로 넘기면 경로·명령 주입이 된다.
USER_CHOICES = ("Tomas", "Basshu", "Philip")
#   ⛔ **기본 사용자를 두지 않는다.** "안 골랐다" 를 누군가로 메우면
#      고르지 않은 사람이 남의 계정으로 돌리게 된다 → 비워 두고 또렷하게 멈춘다.

# 빌드와 서버는 **따로 고른다** (2026-10-23 분리).
#   종전에는 선택지가 하나였다 — "LiveTest" = stag 빌드 + LIVETEST 서버가 한 덩어리였다.
#   `.*LIVETEST.*` 가 42곳 yaml 에 박혀 있어 서버를 바꿀 수가 없었기 때문이다.
#   이제 yaml 이 `${SERVER_PICK}` 을 보고, 러너가 `-Build` 와 `-Server` 를 따로 받는다.
#
# ⚠️ 값은 그대로 **명령행 인자**가 된다 → 허용 목록으로만 받는다(USER_CHOICES 와 같은 이유).
BUILD_CHOICES = {
    "stag": {"label": "stag", "pkg": "com.gmeremit.online.gmeremittance_native.stag"},
    "livetest": {"label": "livetest", "pkg": "com.gmeremit.online.gmeremittance_native.livetest"},
    "live": {"label": "운영(Live)", "pkg": "com.gmeremit.online.gmeremittance_native"},
}
# 서버 = 앱이 붙는 백엔드. 플로우가 Server Override 에서 이 줄을 누른다.
#   `live` 만 실서비스다 — **빌드가 아니라 서버가 실자금 여부를 가른다.**
#   ★ `real_money` = **운영 DB 에 닿는가**. 2026-10-28 사용자 확인으로
#     `livetest` 도 운영 DB 를 본다 — 결제·접수가 실제로 일어난다.
#     그동안 `live` 만 확인을 받고 livetest 는 기본값으로 조용히 돌았다.
#     ⚠️ `live` 와 다른 개념이다. `live` 는 "운영 서버인가"(라벨·이력용),
#       `real_money` 는 "돈이 실제로 움직이는가"(확인을 받을 기준)다.
SERVER_CHOICES = {
    "livetest": {"label": "LiveTest", "host": "livetest", "live": False, "real_money": True},
    "stag": {"label": "STAG", "host": "gmeuat", "live": False, "real_money": False},
    "live": {"label": "운영(Live)", "host": "mobileapi", "live": True, "real_money": True},
}


def combo_error(build: str, server: str) -> str:
    """고를 수 없는 (빌드, 서버) 조합이면 사람이 읽을 사유를, 괜찮으면 빈 문자열을 준다.

    ⛔ 운영 빌드에는 Server Override 다이얼로그가 **없다**. 서버를 골라도 플로우의
      조건부 블록이 조용히 SKIP 되고 **고른 것과 다른 서버로 돈다** — 러너도 같은
      이유로 거부한다(run_suite.ps1 의 가드와 같은 규칙).
    """
    if build == "live" and server != "live":
        return "운영 빌드에는 Server Override 가 없어 서버를 고를 수 없습니다 — 서버도 운영(Live)이어야 합니다."
    return ""

# 그룹 태그의 사람용 설명. 태그의 뜻(계정·순서 제약)은 run_suite.ps1 주석이 정본이다.
GROUP_LABELS = {
    "G1": "로그인 불필요",
    "G2": "한국인 계정 (seungsoo818)",
    "G3": "외국인 계정 (test123 → test251024)",
    "G4": "설정 변경 — 반드시 맨 뒤",
    "G9": "파괴적 — 계정 잠금·비밀번호 초기화 (admin 해제 필요)",
}

_DEFAULT_CONFIG = {
    "port": 8765,
    "lang": "ko",
    "default_device": "",
    "pwsh": "pwsh",
    "adb": "adb",
}


def load_config() -> dict:
    """config.local.json(git 제외)을 읽어 기본값 위에 덮어쓴다."""
    cfg = dict(_DEFAULT_CONFIG)
    local = WEB_RUNNER_DIR / "config.local.json"
    if local.exists():
        loaded = json.loads(local.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in loaded.items() if not k.startswith("_")})
    return cfg


# ============================================================================
# 안전장치 — 2026-09-28 사고 재발 방지
#
# `pwsh -File <script>.ps1 -없는옵션` 은 **에러가 아니다.** 그 옵션을 조용히 버리고
# 스크립트를 *기본값으로* 실행한다(실측 확인). run_suite.ps1 에 이게 일어나면
# **옵션 없는 전체 스위트 = 실기기 전 항목**이 처음부터 돌기 시작한다.
#
# 실제로 브랜치가 어긋나(-DumpJson 없는 run_suite.ps1) /api/tests 를 두 번 부른 것만으로
# 스위트가 두 번 시작됐다. 그래서 **부르기 전에** 옵션 실재를 확인한다. 사후 검사로는 늦다.
# ============================================================================

_PARAM_CACHE: dict[str, set[str]] = {}


def _script_params(script: Path) -> set[str]:
    """스크립트 `param(...)` 블록이 선언한 파라미터 이름(소문자)."""
    key = str(script)
    if key not in _PARAM_CACHE:
        text = script.read_text(encoding="utf-8", errors="replace")
        m = re.search(PARAM_BLOCK_RE, text, re.S | re.M)
        body = m.group(1) if m else ""
        _PARAM_CACHE[key] = {n.lower() for n in re.findall(VAR_RE, body)}
    return _PARAM_CACHE[key]


def require_params(script: Path, names: list[str]) -> None:
    """스크립트가 이 옵션들을 실제로 받는지 확인한다. 아니면 **부르지 않고** 끊는다."""
    missing = [n for n in names if n.lower() not in _script_params(script)]
    if missing:
        opts = ", ".join("-" + n for n in missing)
        raise RuntimeError(
            f"{script.name} 에 {opts} 옵션이 없습니다. 브랜치가 어긋났을 수 있습니다"
            "(web-runner 는 feat/web-runner-demo 전용). 그대로 부르면 옵션이 무시된 채 "
            "**실기기 전체 스위트**가 시작되므로 중단합니다."
        )


def _kill_tree(proc: subprocess.Popen) -> None:
    """자식만 죽이면 maestro(java) 가 **고아로 살아남아 기기를 계속 조작한다.**"""
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, timeout=15)
    except Exception:
        proc.kill()


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    try:
        out, err = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.communicate()
        raise RuntimeError(
            "60초 안에 끝나지 않아 프로세스 트리를 종료했습니다. 목록 조회가 이렇게 "
            "오래 걸리면 실제로 테스트가 돌고 있는 것입니다 — 기기 상태를 확인하세요."
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


# ── 케이스 목록 ────────────────────────────────────────────────────────────
# yaml 주석에서 케이스를 읽는다. 체크리스트 매핑 단위(`시나리오 [번호]`)가 이것이다.
#
# ★ 표기가 한 가지가 아니다(2026-10-06 실측):
#     # [01] [High] Card Apply - …      중요도 태그가 붙은 줄
#     #   [01] 초기 화면 요소 노출 확인   파일 머리의 색인 블록(태그 없음)
#     # [06][07][08] 현재/새/확인 입력   한 줄이 케이스 **여럿**을 덮는다
#     # [07-1] 몽골 송금인 등록          접미사가 붙은 번호
#   ⛔ 예전에는 "중요도 태그가 있는 줄만 쓴다" 로 했는데, **한 파일에 두 표기가 섞이면**
#      태그 없는 케이스를 통째로 버렸다(04_04 에서 [06]~[11] 6개가 사라져 체크리스트
#      매핑이 "yaml 에 없는 케이스" 로 잘못 잡혔다). 이제 둘 다 읽고 **번호로 합친다.**
#
# ⚠️ 산문 속 참조와 구분하는 열쇠는 **닫는 대괄호 뒤의 공백**이다:
#      `# [12]가 카드 PIN을 …`  → `]` 뒤가 바로 글자 → 케이스가 아니다
#      `#   [06][07]은 …`       → `]` 뒤가 `[` 로 이어지다 글자 → 케이스가 아니다
COMMENT_HEAD_RE = re.compile(r"^\s*#+\s*")
# 구분선 안에 마커를 둔 파일이 있다: `# ── [07-2] 베트남 송금인 등록 … ──`
# ★ 진짜 선 문자만 넣는다. `·` 같은 글머리표를 넣었더니
#   `#   · [01-2] 직업 …` 같은 **산문**이 케이스로 새어들어왔다.
DIVIDER_CHARS = "-─━–—="
PRIORITIES = {"high": "High", "medium": "Medium", "low": "Low"}
# 글자 접두 번호: [F-01] 처럼 파일 안에서만 쓰는 네임스페이스 (25_02_프로필_외국인신분증)
ALPHA_ID_RE = re.compile(r"^([A-Za-z]{1,3})-?(\d{1,3})$")


def case_id(token: str, *, keep_suffix: bool = False) -> str:
    """케이스 토큰을 **조인 키**로 바꾼다.

    ★ 체크리스트 쪽(`checklist_sync.py`)과 **같은 규칙**이어야 한다.
      한쪽만 바꾸면 매핑이 조용히 어긋난다. (두 쪽이 이 함수를 함께 쓴다.)
        01      → 01
        07-1    → 07      (접어서 부모로)      / keep_suffix → 07-1
        16a     → 16                           / keep_suffix → 16a
        F-01    → F01     (글자 접두는 그대로 살린다 — 숫자로 바꾸면 충돌한다)

    ⛔ **접미사를 무조건 살리면 안 된다.** 접미사에는 두 종류가 섞여 있다(2026-10-13 전수 조사):
         `[16a] [High] ARC 촬영동작 확인`  중요도 있음 → **별개 케이스**
         `[27-1] 지문인증 사용 여부 → …`   중요도 없음 → `[27]` 의 **본문 단계**
       뒤엣것까지 케이스로 세면 시트에 행이 없는 케이스가 쏟아져 커버리지가 거짓으로 떨어진다.
       → 살릴지 말지는 **중요도를 아는 호출부**가 정한다(`read_cases` / `real_cases`).
    """
    t = (token or "").strip()
    if not t:
        return ""
    if t[0].isdigit():
        head = t.split("-")[0].rstrip("abcdefABCDEF")
        if not head.isdigit():
            return ""
        if keep_suffix and t != head:
            return head.zfill(2) + t[len(head):].lower()
        return head.zfill(2)
    m = ALPHA_ID_RE.match(t)
    if m:
        return m.group(1).upper() + m.group(2).zfill(2)
    return ""


def _parse_case_line(line: str):
    """주석 한 줄에서 (케이스 토큰들, 중요도, 설명) 을 뽑는다. 아니면 None.

    ★ 산문 속 참조와 가르는 기준은 **대괄호 묶음 뒤에 공백이 오는가** 다:
         `# [06][07][08] 현재/새/확인 …`  → 묶음 뒤 공백 → 케이스
         `# [01] [High] Card Apply …`     → 묶음 뒤 공백 → 케이스
         `# ── [07-2] 베트남 송금인 등록 …` → 구분선을 벗겨내면 같은 꼴 → 케이스
         `#   [10]~[12]·[14]가 이것을 …`  → 묶음 뒤가 `~`  → 아니다
         `#   [12]가 카드 PIN을 …`        → 묶음 뒤가 글자 → 아니다
    """
    m = COMMENT_HEAD_RE.match(line)
    if not m:
        return None
    rest = line[m.end():].lstrip(DIVIDER_CHARS + " 	")

    tokens, saw_space = [], False
    while rest.startswith("["):
        close = rest.find("]")
        if close < 0:
            return None
        tokens.append(rest[1:close].strip())
        rest = rest[close + 1:]
        trimmed = rest.lstrip(" 	")
        if len(trimmed) < len(rest):
            saw_space = True
        rest = trimmed
    if not tokens or not saw_space:
        return None            # 묶음 뒤에 공백이 없었다 = 산문 속 참조

    pri, ids = "", []
    for tok in tokens:
        if tok.lower() in PRIORITIES:
            pri = PRIORITIES[tok.lower()]
        elif case_id(tok):
            ids.append(tok)
    if not ids:
        return None
    text = rest.rstrip(DIVIDER_CHARS + " 	").strip()
    return ids, pri, text


def read_cases(rel_path: str) -> list[dict]:
    """플로우 yaml 에서 케이스 목록을 뽑는다. 못 읽으면 빈 목록."""
    if not rel_path:
        return []
    path = MAESTRO_DIR / rel_path
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    parsed_lines = [(p, line) for line in lines if (p := _parse_case_line(line))]

    # ★ 1차 — **중요도 태그가 붙은 접미사 토큰**을 모은다. 그것만 별개 케이스다.
    #   `[16a] [High] ARC 촬영동작 확인`   → 케이스
    #   `[27-1] 지문인증 사용 여부 → …`    → `[27]` 의 본문 단계 (중요도 없음)
    #   가르는 기준이 이것 하나로 전체 yaml 에 깨끗이 들어맞는다(2026-10-13 전수 조사).
    standalone = {
        raw for (ids, pri, _), _ in parsed_lines if pri
        for raw in ids if case_id(raw, keep_suffix=True) != case_id(raw)
    }

    found: dict[str, dict] = {}
    for (ids, pri, text), _ in parsed_lines:
        for raw in ids:
            num = case_id(raw, keep_suffix=raw in standalone)
            if not num:
                continue
            prev = found.get(num)
            # 중요도가 붙은 줄을 우선한다(색인 블록보다 본문이 정확하다)
            if prev is None or (pri and not prev["pri"]):
                found[num] = {"id": num, "raw": raw, "pri": pri, "text": text}
    return [found[k] for k in sorted(found)]


# 파일 이름 → 케이스 id 집합. 시트 쪽(`checklist_sync`)이 **같은 판단**을 쓰려고 부른다.
#   시트는 `04_01_메뉴_드로어와설정` · `02_01_해외송금_수취인관리` · `Old_01_..._old.yaml` 처럼 제각각 적는다
#   → 화면(`app.js normFile`)과 같은 방식으로 맞춘다: 경로·확장자·`_old`·공백 제거 후 소문자.
_REAL_CASES: dict[str, set[str]] = {}


def norm_flow_name(name: str) -> str:
    s = re.sub(r"^.*[\\/]", "", str(name or ""))   # ⚠️ 역슬래시도 — 시트는 `Old\13_01_...` 로도 적는다
    s = re.sub(r"\.ya?ml$", "", s, flags=re.I)
    s = re.sub(r"_old$", "", s, flags=re.I)
    return re.sub(r"\s+", "", s).lower().strip()


def real_cases(name: str) -> set[str]:
    """그 플로우가 실제로 가진 케이스 id 집합. 못 찾으면 빈 집합."""
    key = norm_flow_name(name)
    if not key:
        return set()
    if not _REAL_CASES:
        for f in sorted((MAESTRO_DIR / "Old").glob("*.yaml")):
            _REAL_CASES[norm_flow_name(f.stem)] = {
                c["id"] for c in read_cases(str(Path("Old") / f.name))
            }
    return _REAL_CASES.get(key, set())


def list_tests(include_destructive: bool = False) -> list[dict]:
    """run_suite.ps1 -DumpJson 으로 스위트 표를 읽어온다.

    표(`$Suite`)가 유일한 정본이다 — 목록을 여기에 따로 적지 않는다.
    G9(파괴적: 계정 잠금·비밀번호 초기화)는 기본으로 뺀다.
    """
    cfg = load_config()
    # ★ 부르기 전에 옵션 실재를 확인한다 — 없으면 실기기가 돈다(위 안전장치 주석 참고)
    require_params(SUITE_SCRIPT, ["DumpJson"])
    # ⚠️ `-File` 로 부르면 **리다이렉트된 stdout 이 콘솔 기본 인코딩(한국어 Windows=MS949)**
    #   으로 나온다. 항목 이름에 한글이 들어간 뒤로는 그대로 깨져서 아래 허용목록
    #   대조(`n not in known`)가 전부 실패한다 → 어떤 테스트도 시작하지 못한다.
    #   실행 경로(`Run.start`)와 같은 방식으로 OutputEncoding 을 UTF-8 로 박고 부른다.
    proc = _run([cfg["pwsh"], "-NoProfile", "-Command",
                 "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
                 f"& '{SUITE_SCRIPT}' -DumpJson"], MAESTRO_DIR)
    if proc.returncode != 0:
        raise RuntimeError(f"run_suite.ps1 -DumpJson 실패 (exit={proc.returncode})\n{proc.stderr.strip()}")

    head = proc.stdout.lstrip()[:1]
    if head not in ("[", "{"):
        raise RuntimeError(
            "run_suite.ps1 -DumpJson 이 JSON 을 주지 않았습니다. 목록 조회가 아니라 "
            "**실행**이 일어났을 수 있습니다 — 기기 상태를 확인하세요.\n"
            f"받은 출력 앞부분: {proc.stdout[:200]!r}"
        )

    data = json.loads(proc.stdout)
    if isinstance(data, dict):  # 항목이 1개면 배열이 아니라 객체로 온다
        data = [data]

    tests = []
    for item in data:
        destructive = item.get("destructive")
        if destructive and not include_destructive:
            continue
        needs = item.get("needs") or {}
        tests.append({
            "name": item["n"],
            "group": item["g"],
            "account": item.get("acct", "-"),
            "est": item.get("est", 0),
            "file": item.get("f", ""),
            "note": item.get("note", ""),
            "needs_balance": needs.get("balance"),
            "irreversible": bool(item.get("irreversible")),
            "destructive": destructive,
            "push": bool(item.get("push")),
            "cases": read_cases(item.get("f", "")),
        })
    return tests


_DEVICE_LINE = re.compile(r"^(\S+)\s+(device|offline|unauthorized)\b(.*)$")


def list_devices() -> list[dict]:
    """adb 로 연결된 기기를 조회한다.

    ⚠️ 시리얼을 코드에 박지 않는다 — 기기는 수시로 바뀐다. 항상 조회해서 고른다.
    """
    cfg = load_config()
    proc = _run([cfg["adb"], "devices", "-l"], REPO_ROOT)
    devices = []
    for line in proc.stdout.splitlines():
        m = _DEVICE_LINE.match(line.strip())
        if not m:
            continue
        serial, state, rest = m.group(1), m.group(2), m.group(3)
        model = ""
        mm = re.search(r"model:(\S+)", rest)
        if mm:
            model = mm.group(1).replace("_", " ")
        devices.append({
            "serial": serial,
            "state": state,
            "model": model,
            "ready": state == "device",
        })
    return devices


# ====================================================================
# 실행
# ====================================================================
#
# 실행은 run_suite.ps1 에 맡긴다. 순서 의존(계정 전환·13→04 같은 선행 관계),
# 실패 시 자동 복구, 서버(LIVETEST) 트래픽 검사가 전부 그 안에 있어서,
# 여기서 maestro 를 직접 부르면 그 안전장치를 다 버리게 된다.
#
# ⚠️ 실시간 로그: run_suite.ps1 은 각 항목의 maestro 출력을 콘솔이 아니라
#   `suite_logs\<시각>\<항목>.log` 로 흘린다(콘솔엔 결과 한 줄만 찍힌다).
#   그래서 콘솔 출력과 **그 로그 파일을 같이 따라 읽어** 화면에 합친다.

# 항목 이름에 **한글**이 들어간다(스위트 표의 n). 완성형 음절만 허용한다.
#   따옴표·공백·경로 구분자·PowerShell 메타문자는 여전히 전부 막힌다 →
#   아래 -Names 보간의 인자 주입과 run_item_log_path 의 경로 조작 방어가 그대로 유지된다.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-가-힣]+$")
_SAFE_SERIAL = re.compile(r"^[A-Za-z0-9_.:-]+$")

# run_test.ps1 이 찍는 maestro 커맨드 에코는 `--env` 가 수십 개라 한 줄이 4KB 를 넘는다.
# 화면에서는 어느 플로우를 도는지만 보이면 된다 → env 부분을 개수로 줄인다.
_ECHO = re.compile(r"^(\s*Running: maestro .*?test\s+\S+)\s+(--env\s.*)$")


def _shorten(line: str) -> str:
    m = _ECHO.match(line)
    if not m:
        return line
    return f"{m.group(1)}  (--env {m.group(2).count('--env')}개 생략)"


# maestro 는 스텝마다 `<설명>... COMPLETED|FAILED|SKIPPED` 한 줄을 찍는다 → 진행 표시의 재료.
_STEP = re.compile(r"^\s*(.+?)\.\.\.\s*(COMPLETED|FAILED|SKIPPED|PENDING)\s*$")
# run_suite.ps1 의 항목 결과 줄: `▶ 09_홈화면_요소와진입경로   PASS   192 steps  05:43`
_ITEM_DONE = re.compile(r"^▶\s+(\S+)\s+(PASS|FAIL|SKIP)\b\s*(.*)$")
_STEPS_N = re.compile(r"(\d+)\s*steps")
_ELAPSED = re.compile(r"(\d{2}:\d{2})")


class Run:
    """한 번의 실행. 로그 줄을 모아 두고 구독자에게 흘려보낸다."""

    def __init__(self, names: list[str], device: str, build: str, server: str, user: str):
        self.names = names
        self.device = device
        self.build = build
        self.server = server
        self.user = user
        self.started_at = datetime.now()
        self.finished = False
        # 끝은 여러 곳에서(정상 종료·중단·감시) 날 수 있다 → **한 번만** 나게 잠근다.
        self._finish_lock = threading.Lock()
        self.stopped = False
        self.returncode: int | None = None
        self.summary: dict | None = None
        self.suite_log_dir: Path | None = None

        RUN_LOG_DIR.mkdir(exist_ok=True)
        stamp = self.started_at.strftime("%Y-%m-%d_%H%M%S")
        tag = names[0] if len(names) == 1 else f"{len(names)}개"
        self.log_path = RUN_LOG_DIR / f"{stamp}_{tag}.log"

        self._events: list[dict] = []
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._started_tests: set[str] = set()

    # ------------------------------------------------------------ 이벤트
    # 화면은 로그가 아니라 **진행 상황**을 본다. 그래서 줄을 그대로 흘리지 않고
    # 여기서 종류를 갈라 이벤트로 내보낸다(로그 원문은 파일에 그대로 남는다).
    def _push(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)
            for q in self._subs:
                q.put(event)

    def _emit(self, text: str) -> None:
        """로그 한 줄: 파일에 쓰고, 이벤트로도 내보낸다."""
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
        self._push({"type": "line", "text": text})

    def subscribe(self) -> queue.Queue:
        """지금까지의 이벤트를 먼저 받고, 이후 새 이벤트를 이어받는 큐."""
        q: queue.Queue = queue.Queue()
        with self._lock:
            for event in self._events:
                q.put(event)
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    # ------------------------------------------------------------- 실행
    def start(self) -> None:
        # ⛔ 빈 -Names 는 run_suite.ps1 에서 **전체 스위트**가 된다(실결제 항목 포함).
        if not self.names:
            raise RuntimeError("실행할 테스트를 고르지 않았습니다. 전체 스위트가 도는 것을 막기 위해 중단합니다.")
        # ★ "User" 도 함께 확인한다 — pwsh 는 **모르는 옵션을 조용히 무시하고**
        #   기본값으로 본체를 실행한다(스크립트가 낡으면 남의 계정으로 돌 수 있다).
        #   "Server" 도 확인한다 — 스크립트가 낡아 -Server 를 모르면 pwsh 가 **조용히 무시하고**
        #   기본값(livetest)으로 돈다. 고른 서버와 다른 서버로 도는 쪽이 더 위험하다.
        require_params(SUITE_SCRIPT, ["Names", "Device", "Build", "Server", "Lang", "User"])

        cfg = load_config()
        build, server = self.build, self.server
        inner = (
            "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
            # 작은따옴표는 _SAFE_NAME 이 이미 막지만, 보간에 기대지 않고 한 겹 더 감싼다.
            f"& '{SUITE_SCRIPT}' -Names '{','.join(n.replace(chr(39), chr(39) * 2) for n in self.names)}' "
            f"-Device '{self.device}' -Build {build} -Server {server} -Lang {cfg['lang']} "
            f"-User {self.user}; "
            "exit $LASTEXITCODE"
        )
        cmd = [cfg["pwsh"], "-NoProfile", "-Command", inner]

        self._emit(f"$ run_suite.ps1 -Names {','.join(self.names)} "
                   f"-Device {self.device} -Build {build} -Server {server} -Lang {cfg['lang']} "
                   f"-User {self.user}")
        self._emit("")

        # POSIX 에서는 자식들을 한 묶음으로 끊을 수 있게 프로세스 그룹을 따로 연다(Mac 이전 대비).
        extra = {}
        if os.name == "posix":
            extra["start_new_session"] = True

        self._proc = subprocess.Popen(
            cmd, cwd=str(MAESTRO_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", bufsize=1, **extra,
        )
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=self._tail_item_logs, daemon=True).start()

    def stop(self) -> None:
        """실행을 끊는다.

        ⚠️ **자식까지 끊어야 한다.** 흐름이 pwsh → run_suite.ps1 → run_test.ps1 →
        maestro.bat → java 로 이어져서, pwsh 만 죽이면 **java 가 살아남아 기기를 계속 조작한다.**
        ⚠️ 중단하면 run_suite 의 자동 복구도 같이 끊긴다 → 앱은 **그 시점 화면 그대로** 남는다.
        """
        if self.finished:
            return
        self.stopped = True
        self._emit("")
        self._emit("⛔ 사용자가 실행을 중단했습니다 — 앱은 중단 시점 화면에 그대로 남습니다.")

        proc = self._proc
        # ⛔ 종전엔 **이미 죽은 프로세스면 그냥 return** 했다. 그러면 `_pump` 가 막혀 있을 때
        #   아무도 끝을 내지 않아 화면이 영영 잠긴다 → 죽어 있어도 아래 감시는 반드시 건다.
        if proc and proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True, timeout=20)
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception as exc:
                self._emit(f"[중단 실패] {exc}")

        # ★ 끝을 보장한다. `_pump` 가 정상이면 그쪽이 먼저 끝내고, 이 감시는 조용히 물러난다
        #   (`_finish` 는 멱등이다). 파이프가 안 닫히는 경우가 실재한다 — 살아남은 손자
        #   프로세스가 stdout 핸들을 쥐고 있으면 `for raw in stdout` 이 영원히 안 끝난다.
        threading.Thread(target=self._finish_after, args=(20.0,), daemon=True).start()

    def _finish_after(self, seconds: float) -> None:
        """중단 요청 뒤 주어진 시간 안에 안 끝나면 끝난 것으로 처리한다."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.finished:
                return
            time.sleep(0.5)
        self._emit(f"[강제 종료] 로그 스트림이 {int(seconds)}초 안에 닫히지 않아 "
                   f"실행을 끝난 것으로 처리합니다.")
        self._finish()

    def _pump(self) -> None:
        """run_suite.ps1 의 콘솔 출력을 읽어 나른다.

        ⛔ **반드시 끝을 낸다.** 종전엔 try 가 없어서, 여기서 예외가 나면 데몬 스레드가
          조용히 죽고 `finished` 가 영영 False 로 남았다. 그러면
            · 화면이 `done` 을 못 받아 **체크박스 잠금이 안 풀리고**
            · `start_run` 이 "이미 실행 중입니다" 로 **다음 실행까지 막는다**
          2026-10-27 에 실제로 그 상태인 실행이 있었다(stopped=true / running=true).
        """
        try:
            self._pump_lines()
        except Exception as exc:
            self._emit(f"[로그 읽기 끊김] {exc}")
        finally:
            self._stop.set()
            time.sleep(1.0)      # 마지막 항목 로그가 밀려 들어올 틈을 준다
            self._finish()

    def _pump_lines(self) -> None:
        assert self._proc and self._proc.stdout
        for raw in self._proc.stdout:
            line = raw.rstrip("\r\n")
            self._emit(line)

            # "로그: <경로>" 줄에서 이번 실행의 항목별 로그 위치를 알아낸다
            if self.suite_log_dir is None:
                m = re.search(r"로그:\s*(.+suite_logs[\\/][^\s]+)", line)
                if m:
                    self.suite_log_dir = Path(m.group(1).strip())

            # 항목 결과 줄 → 진행 표시의 "끝났다" 신호
            #   ⚠️ run_suite 는 `▶ 이름` 을 개행 없이 찍고 결과를 같은 줄에 이어 붙인다
            #     → 시작 신호로는 못 쓴다. 시작은 항목 로그 파일이 생기는 것으로 잡는다.
            done = _ITEM_DONE.match(line)
            if done:
                tail = done.group(3)
                steps = _STEPS_N.search(tail)
                elapsed = _ELAPSED.search(tail)
                self._push({
                    "type": "test_done",
                    "name": done.group(1),
                    "status": done.group(2),
                    "steps": int(steps.group(1)) if steps else None,
                    "elapsed": elapsed.group(1) if elapsed else None,
                    "reason": tail.strip() if done.group(2) == "SKIP" else "",
                })
        self.returncode = self._proc.wait()

    def _finish(self) -> None:
        """끝을 **한 번만, 반드시** 낸다(여러 스레드가 불러도 안전하다)."""
        with self._finish_lock:
            if self.finished:
                return
            try:
                self.summary = self._build_summary()
            except Exception as exc:
                # 요약을 못 만들어도 **끝은 내야 한다** — 못 끝내면 화면이 영영 잠긴다.
                self.summary = {
                    "ok": False, "stopped": self.stopped, "returncode": self.returncode,
                    "items": [], "counts": {"PASS": 0, "FAIL": 0, "SKIP": 0},
                    "elapsed": str(datetime.now() - self.started_at).split(".")[0],
                    "error": f"요약을 만들지 못했습니다: {exc}",
                }
            self._stop.set()
            self.finished = True
            with self._lock:
                for q in self._subs:
                    q.put(None)      # 스트림 종료 신호

    def _tail_item_logs(self) -> None:
        """suite_logs\\<시각>\\*.log 를 따라 읽어 maestro 진행 상황을 실시간으로 보낸다.

        항목 로그 파일이 **생기는 것**이 그 항목의 시작 신호다(콘솔의 `▶ 이름` 은
        개행 없이 찍혀 결과가 날 때까지 도착하지 않는다).
        """
        offsets: dict[Path, int] = {}
        while True:
            last = self._stop.is_set()
            if self.suite_log_dir and self.suite_log_dir.exists():
                for path in sorted(self.suite_log_dir.glob("*.log")):
                    stem = path.stem
                    if stem.startswith("_") or stem.endswith("_push"):
                        continue          # 충전·픽스처 push 로그는 진행 표시 대상이 아니다
                    recover = stem.endswith("_recover")
                    name = stem[: -len("_recover")] if recover else stem
                    try:
                        size = path.stat().st_size
                        start = offsets.get(path, 0)
                        if size <= start:
                            continue
                        if name not in self._started_tests:
                            self._started_tests.add(name)
                            self._push({"type": "test_start", "name": name})
                        with path.open("rb") as fh:
                            fh.seek(start)
                            chunk = fh.read(size - start)
                        offsets[path] = size
                        for line in chunk.decode("utf-8", "replace").splitlines():
                            if not line.strip():
                                continue
                            self._emit("   " + _shorten(line.rstrip()))
                            step = _STEP.match(line)
                            if step:
                                self._push({
                                    "type": "step",
                                    "name": name,
                                    "text": step.group(1).strip(),
                                    "status": step.group(2),
                                    "recover": recover,
                                })
                    except OSError:
                        continue
            if last:
                return
            time.sleep(0.7)

    # ------------------------------------------------------------- 요약
    def _build_summary(self) -> dict:
        """SUMMARY.md 의 표를 읽어 항목별 결과를 만든다(콘솔 표보다 깨지지 않는다)."""
        items: list[dict] = []
        if self.suite_log_dir:
            md = self.suite_log_dir / "SUMMARY.md"
            if md.exists():
                for line in md.read_text(encoding="utf-8").splitlines():
                    cells = [c.strip() for c in line.strip().strip("|").split("|")]
                    if len(cells) == 6 and cells[2] in ("PASS", "FAIL", "SKIP"):
                        items.append({
                            "group": cells[0], "name": cells[1], "status": cells[2],
                            "steps": cells[3], "elapsed": cells[4], "reason": cells[5],
                        })
        counts = {s: sum(1 for i in items if i["status"] == s) for s in ("PASS", "FAIL", "SKIP")}
        elapsed = datetime.now() - self.started_at
        return {
            "ok": self.returncode == 0 and not self.stopped,
            "stopped": self.stopped,
            "returncode": self.returncode,
            "items": items,
            "counts": counts,
            "elapsed": str(elapsed).split(".")[0],
            "log_file": str(self.log_path),
            "suite_log_dir": str(self.suite_log_dir) if self.suite_log_dir else None,
        }

    def status(self) -> dict:
        return {
            "running": not self.finished,
            "stopped": self.stopped,
            "names": self.names,
            "device": self.device,
            "build": self.build,
            "server": self.server,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "summary": self.summary,
        }


# ====================================================================
# 실행 이력
# ====================================================================
#
# 이력의 정본은 `Maestro\suite_logs\<시각>\SUMMARY.md` 다 — run_suite.ps1 이 매 실행마다 쓴다.
# 웹이 따로 기록을 쌓지 않는 이유: **웹 밖에서 돌린 실행도 이력에 나와야** 하고
# (PowerShell 로 직접 돌리는 경우가 많다), 서버를 재시작해도 남아야 한다.

SUITE_LOGS_DIR = MAESTRO_DIR / "suite_logs"
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")

_H_COUNTS = re.compile(r"항목\s*(\d+)개\s*—\s*\*\*PASS (\d+)\*\*\s*/\s*\*\*FAIL (\d+)\*\*\s*/\s*\*\*SKIP (\d+)\*\*")
_H_ELAPSED = re.compile(r"소요\s*([\d:]+)\s*/\s*예상\s*(\d+)")
_H_RES = re.compile(r"기기 해상도:\s*`([^`]+)`")
_H_BUILD = re.compile(r"빌드:\s*`([^`]+)`")
_H_HOSTS = re.compile(r"livetest\s*\*\*(\d+)\*\*건\s*/\s*gmeuat\(STAG\)\s*\*\*(\d+)\*\*건")
_H_LANG = re.compile(r"lang\s*`(\w+)`")
_H_DEVICE = re.compile(r"^- 기기:\s*`([^`]+)`", re.M)
# 2026-09-23 이전 실행에는 SUMMARY.md 에 기기 줄이 없다 → 항목 로그의 maestro 호출에서 찾는다
_LOG_DEVICE = re.compile(r"--device\s+(\S+)")


def _device_from_logs(run_dir: Path) -> str:
    for log in sorted(run_dir.glob("*.log"))[:3]:
        try:
            head = log.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            continue
        m = _LOG_DEVICE.search(head)
        if m:
            return m.group(1)
    return ""


def _parse_summary(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    items = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[2] in ("PASS", "FAIL", "SKIP"):
            items.append({
                "group": cells[0], "name": cells[1], "status": cells[2],
                "steps": cells[3], "elapsed": cells[4], "reason": cells[5],
            })

    counts = _H_COUNTS.search(text)
    elapsed = _H_ELAPSED.search(text)
    hosts = _H_HOSTS.search(text)
    res = _H_RES.search(text)
    build = _H_BUILD.search(text)
    lang = _H_LANG.search(text)
    dev = _H_DEVICE.search(text)
    stag_hosts = int(hosts.group(2)) if hosts else 0
    live_build = build and not build.group(1).endswith(".stag")

    return {
        "stamp": path.parent.name,
        "items": items,
        "counts": {
            "PASS": int(counts.group(2)) if counts else sum(1 for i in items if i["status"] == "PASS"),
            "FAIL": int(counts.group(3)) if counts else sum(1 for i in items if i["status"] == "FAIL"),
            "SKIP": int(counts.group(4)) if counts else sum(1 for i in items if i["status"] == "SKIP"),
        },
        "total": int(counts.group(1)) if counts else len(items),
        "elapsed": elapsed.group(1) if elapsed else "",
        "est": int(elapsed.group(2)) if elapsed else None,
        "device": dev.group(1) if dev else _device_from_logs(path.parent),
        "resolution": res.group(1) if res else "",
        "build": build.group(1).strip() if build else "",
        "server": "운영(Live)" if live_build else "LiveTest",
        "lang": lang.group(1) if lang else "",
        "hosts": {"livetest": int(hosts.group(1)) if hosts else 0, "stag": stag_hosts},
        "aborted": "중단됨" in text,
        # stag 빌드인데 STAG 서버 트래픽이 섞였으면 그 실행 결과는 신뢰할 수 없다
        "server_mixed": bool(not live_build and stag_hosts > 0),
    }


def _parse_result_json(path: Path) -> dict | None:
    """run_suite.ps1 이 쓰는 기계용 결과(result.json). 2026-09-30 신설.

    SUMMARY.md 는 **사람이 읽는 문서**다 — 아래 `_parse_summary` 가 그걸 정규식으로 긁는데,
    문구를 손보는 순간 조용히 깨진다. 이쪽이 정본이고 SUMMARY 파싱은 옛 실행용 폴백이다.
    이 파일만 git 에 추적되므로 **다른 PC 실행분도 git 으로 합류한다.**
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "items" not in data:
        return None

    c = data.get("counts") or {}
    h = data.get("hosts") or {}
    stag = int(h.get("stag") or 0)
    live = bool(data.get("live"))
    return {
        "stamp": data.get("stamp") or path.parent.name,
        "items": [
            {"group": i.get("group", ""), "name": i.get("name", ""),
             "status": i.get("status", ""), "steps": str(i.get("steps", "")),
             "elapsed": i.get("elapsed", ""), "reason": i.get("reason") or ""}
            for i in data.get("items") or []
        ],
        "counts": {"PASS": int(c.get("pass") or 0), "FAIL": int(c.get("fail") or 0),
                   "SKIP": int(c.get("skip") or 0)},
        "total": int(c.get("total") or 0),
        "elapsed": data.get("elapsed") or "",
        "est": data.get("estMin"),
        "device": data.get("device") or "",
        "resolution": data.get("resolution") or "",
        "build": (data.get("build") or "").strip(),
        "server": "운영(Live)" if live else "LiveTest",
        "lang": data.get("lang") or "",
        "hosts": {"livetest": int(h.get("livetest") or 0), "stag": stag},
        "aborted": bool(data.get("aborted")),
        # stag 빌드인데 STAG 서버 트래픽이 섞였으면 그 실행 결과는 신뢰할 수 없다
        "server_mixed": bool(not live and stag > 0),
    }


def read_history(limit: int = 50) -> list[dict]:
    """최근 실행부터 돌려준다. 폴더 이름이 곧 시각이라 이름 역순이 시간 역순이다.

    result.json 이 있으면 그걸 쓰고, 없으면 SUMMARY.md 를 파싱한다(2026-09-30 이전 실행).
    """
    if not SUITE_LOGS_DIR.exists():
        return []
    runs = []
    for d in sorted(SUITE_LOGS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not _STAMP.match(d.name):
            continue
        parsed = _parse_result_json(d / "result.json") or _parse_summary(d / "SUMMARY.md")
        if parsed:
            runs.append(parsed)
        if len(runs) >= limit:
            break
    return runs


def run_item_log_path(stamp: str, item: str) -> Path:
    """이력에서 항목 하나의 로그 경로(경로 조작 차단을 위해 형식을 검사한다)."""
    if not _STAMP.match(stamp) or not _SAFE_NAME.match(item):
        raise ValueError("잘못된 이력 경로입니다.")
    path = SUITE_LOGS_DIR / stamp / f"{item}.log"
    if not path.exists():
        raise FileNotFoundError(f"로그가 없습니다: {stamp}/{item}.log")
    return path


def read_item_log(stamp: str, item: str) -> str:
    """이력에서 항목 하나의 실행 로그를 읽는다."""
    return run_item_log_path(stamp, item).read_text(encoding="utf-8", errors="replace")


def run_result_path(stamp: str) -> Path:
    """이력 한 건의 `result.json` 경로.

    ⚠️ `read_item_log` 과 같은 이유로 **형식을 먼저 검사한다** — stamp 는 URL 에서 온다.
    ⛔ `SUMMARY.md` 로 폴백하지 않는다. 거기엔 케이스 단위 BLOCKED/N/A 가 **합계로만**
      있어서 어느 케이스가 제외인지 알 수 없다(`checklist_result.load_run` 참고).
      `read_history` 는 목록을 보여주는 게 목적이라 폴백이 맞지만, 기입값 산출은
      **틀린 값을 만드느니 없다고 하는 편**이 낫다.
    """
    if not _STAMP.match(stamp):
        raise ValueError("잘못된 이력 경로입니다.")
    path = SUITE_LOGS_DIR / stamp / "result.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{stamp} 에 result.json 이 없습니다 — 2026-09-30 이전 실행이거나, "
            "프로세스가 강제종료되어 기록이 남지 않은 실행입니다.")
    return path


_current: Run | None = None
_start_lock = threading.Lock()


def current_run() -> Run | None:
    return _current


def start_run(names: list[str], device: str, build: str, server: str, user: str) -> Run:
    """실행을 시작한다. 이미 돌고 있으면 거절한다(대기열은 이번 범위 밖)."""
    global _current

    # ⚠️ 이름·시리얼을 그대로 명령행에 넣으면 주입이 된다 → **아는 값만** 통과시킨다.
    #   G9(파괴적)도 고를 수 있다(2026-10-27 사용자 지시). 마지막 가드는 화면의 확인 창이다.
    #   ⚠️ `01_05_로그인_비번초기화` 는 **파일 자체에 인터록이 없다** — 돌면 비밀번호가
    #     실제로 초기화되고 admin 재설정 전까지 모든 플로우가 깨진다.
    #     (`01_04` 는 `CONFIRM_LOCK` 가드가 있어 env 없이 돌리면 [01]에서 바로 멈춘다.)
    known = {t["name"] for t in list_tests(include_destructive=True)}
    unknown = [n for n in names if n not in known or not _SAFE_NAME.match(n)]
    if not names:
        raise ValueError("테스트를 하나 이상 고르세요.")
    if unknown:
        raise ValueError(f"목록에 없는 테스트입니다: {', '.join(unknown)}")
    if build not in BUILD_CHOICES:
        raise ValueError(f"알 수 없는 빌드: {build}")
    if server not in SERVER_CHOICES:
        raise ValueError(f"알 수 없는 서버: {server}")
    bad = combo_error(build, server)
    if bad:
        raise ValueError(bad)
    if not user:
        raise ValueError("먼저 사용자를 선택하세요.")
    if user not in USER_CHOICES:
        raise ValueError(f"알 수 없는 사용자: {user}")
    if not _SAFE_SERIAL.match(device or ""):
        raise ValueError("기기 시리얼이 올바르지 않습니다.")
    if not any(d["serial"] == device and d["ready"] for d in list_devices()):
        raise ValueError(f"기기를 쓸 수 없습니다: {device}")

    with _start_lock:
        if _current and not _current.finished:
            raise RuntimeError("이미 실행 중입니다.")
        # 스위트 표의 순서대로 돌린다 — 순서가 곧 상태 의존성이다(고른 순서가 아니다).
        # G9 도 고를 수 있으므로 순서 표에도 있어야 한다 — 없으면 **조용히 빠진다**.
        order = [t["name"] for t in list_tests(include_destructive=True)]
        ordered = [n for n in order if n in set(names)]
        run = Run(ordered, device, build, server, user)
        _current = run
    run.start()
    return run
