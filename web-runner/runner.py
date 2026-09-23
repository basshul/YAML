"""PowerShell 스크립트(run_test.ps1 / run_suite.ps1)를 부르는 **유일한** 창구.

⚠️ 설계 규칙 — 이 파일 밖에서는 run_test.ps1 / run_suite.ps1 을 직접 부르지 않는다.
   서버(server.py)든 화면이든 전부 이 모듈의 함수를 거친다. 나중에 Mac 으로 옮길 때
   고쳐야 할 곳이 여기 하나로 끝나게 하려는 것이다(PowerShell → shell 치환).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_RUNNER_DIR.parent
MAESTRO_DIR = REPO_ROOT / "Maestro"
SUITE_SCRIPT = MAESTRO_DIR / "run_suite.ps1"

# 화면에 보이는 "서버" 선택지 → run_*.ps1 의 -Build 값.
# 사용자 기준은 빌드가 아니라 **어느 서버에 붙는가**다. stag 빌드는 플로우가 서버를
# LIVETEST 로 강제하고, 운영 빌드는 실서비스에 붙는다.
SERVER_CHOICES = {
    "livetest": {"label": "LiveTest", "build": "stag", "live": False},
    "live": {"label": "운영(Live)", "build": "live", "live": True},
}

# 그룹 태그의 사람용 설명. 태그의 뜻(계정·순서 제약)은 run_suite.ps1 주석이 정본이다.
GROUP_LABELS = {
    "G1": "로그인 불필요",
    "G2": "한국인 계정 (seungsoo818)",
    "G3": "외국인 계정 (test123 → test251024)",
    "G4": "설정 변경 — 반드시 맨 뒤",
    "G9": "파괴적 — admin 개입 필요 (목록에서 제외)",
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


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True,
        encoding="utf-8", errors="replace", timeout=60,
    )


def list_tests(include_destructive: bool = False) -> list[dict]:
    """run_suite.ps1 -DumpJson 으로 스위트 표를 읽어온다.

    표(`$Suite`)가 유일한 정본이다 — 목록을 여기에 따로 적지 않는다.
    G9(파괴적: 계정 잠금·비밀번호 초기화)는 기본으로 뺀다.
    """
    cfg = load_config()
    proc = _run([cfg["pwsh"], "-NoProfile", "-File", str(SUITE_SCRIPT), "-DumpJson"], MAESTRO_DIR)
    if proc.returncode != 0:
        raise RuntimeError(f"run_suite.ps1 -DumpJson 실패 (exit={proc.returncode})\n{proc.stderr.strip()}")

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
