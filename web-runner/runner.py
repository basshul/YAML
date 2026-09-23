"""PowerShell 스크립트(run_test.ps1 / run_suite.ps1)를 부르는 **유일한** 창구.

⚠️ 설계 규칙 — 이 파일 밖에서는 run_test.ps1 / run_suite.ps1 을 직접 부르지 않는다.
   서버(server.py)든 화면이든 전부 이 모듈의 함수를 거친다. 나중에 Mac 으로 옮길 때
   고쳐야 할 곳이 여기 하나로 끝나게 하려는 것이다(PowerShell → shell 치환).
"""

from __future__ import annotations

import json
import queue
import re
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

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
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
# run_suite.ps1 의 항목 결과 줄: `▶ 09_Home   PASS   192 steps  05:43`
_ITEM_DONE = re.compile(r"^▶\s+(\S+)\s+(PASS|FAIL|SKIP)\b\s*(.*)$")
_STEPS_N = re.compile(r"(\d+)\s*steps")
_ELAPSED = re.compile(r"(\d{2}:\d{2})")


class Run:
    """한 번의 실행. 로그 줄을 모아 두고 구독자에게 흘려보낸다."""

    def __init__(self, names: list[str], device: str, server: str):
        self.names = names
        self.device = device
        self.server = server
        self.started_at = datetime.now()
        self.finished = False
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
        cfg = load_config()
        build = SERVER_CHOICES[self.server]["build"]
        inner = (
            "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
            f"& '{SUITE_SCRIPT}' -Names '{','.join(self.names)}' "
            f"-Device '{self.device}' -Build {build} -Lang {cfg['lang']}; "
            "exit $LASTEXITCODE"
        )
        cmd = [cfg["pwsh"], "-NoProfile", "-Command", inner]

        self._emit(f"$ run_suite.ps1 -Names {','.join(self.names)} "
                   f"-Device {self.device} -Build {build} -Lang {cfg['lang']}")
        self._emit("")

        self._proc = subprocess.Popen(
            cmd, cwd=str(MAESTRO_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=self._tail_item_logs, daemon=True).start()

    def _pump(self) -> None:
        """run_suite.ps1 의 콘솔 출력을 읽어 나른다."""
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
        self._stop.set()
        time.sleep(1.0)              # 마지막 항목 로그가 밀려 들어올 틈을 준다
        self.summary = self._build_summary()
        self.finished = True
        with self._lock:
            for q in self._subs:
                q.put(None)          # 스트림 종료 신호

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
            "ok": self.returncode == 0,
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
            "names": self.names,
            "device": self.device,
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


def read_history(limit: int = 50) -> list[dict]:
    """최근 실행부터 돌려준다. 폴더 이름이 곧 시각이라 이름 역순이 시간 역순이다."""
    if not SUITE_LOGS_DIR.exists():
        return []
    runs = []
    for d in sorted(SUITE_LOGS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not _STAMP.match(d.name):
            continue
        parsed = _parse_summary(d / "SUMMARY.md")
        if parsed:
            runs.append(parsed)
        if len(runs) >= limit:
            break
    return runs


def read_item_log(stamp: str, item: str) -> str:
    """이력에서 항목 하나의 실행 로그를 읽는다(경로 조작 차단을 위해 형식을 검사한다)."""
    if not _STAMP.match(stamp) or not _SAFE_NAME.match(item):
        raise ValueError("잘못된 이력 경로입니다.")
    path = SUITE_LOGS_DIR / stamp / f"{item}.log"
    if not path.exists():
        raise FileNotFoundError(f"로그가 없습니다: {stamp}/{item}.log")
    return path.read_text(encoding="utf-8", errors="replace")


_current: Run | None = None
_start_lock = threading.Lock()


def current_run() -> Run | None:
    return _current


def start_run(names: list[str], device: str, server: str) -> Run:
    """실행을 시작한다. 이미 돌고 있으면 거절한다(대기열은 이번 범위 밖)."""
    global _current

    # ⚠️ 이름·시리얼을 그대로 명령행에 넣으면 주입이 된다 → **아는 값만** 통과시킨다.
    known = {t["name"] for t in list_tests()}
    unknown = [n for n in names if n not in known or not _SAFE_NAME.match(n)]
    if not names:
        raise ValueError("테스트를 하나 이상 고르세요.")
    if unknown:
        raise ValueError(f"목록에 없는 테스트입니다: {', '.join(unknown)}")
    if server not in SERVER_CHOICES:
        raise ValueError(f"알 수 없는 서버: {server}")
    if not _SAFE_SERIAL.match(device or ""):
        raise ValueError("기기 시리얼이 올바르지 않습니다.")
    if not any(d["serial"] == device and d["ready"] for d in list_devices()):
        raise ValueError(f"기기를 쓸 수 없습니다: {device}")

    with _start_lock:
        if _current and not _current.finished:
            raise RuntimeError("이미 실행 중입니다.")
        # 스위트 표의 순서대로 돌린다 — 순서가 곧 상태 의존성이다(고른 순서가 아니다).
        order = [t["name"] for t in list_tests()]
        ordered = [n for n in order if n in set(names)]
        run = Run(ordered, device, server)
        _current = run
    run.start()
    return run
