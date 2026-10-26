r"""항목 실행 로그 → **케이스별 결과**.

실행 이력은 시나리오 단위로만 PASS/FAIL 을 안다. 48케이스짜리 `04_Menu_History` 가
FAIL 이라고만 적히면 **어느 케이스에서 깨졌는지** 로그를 끝까지 읽어야 알 수 있다.

어떻게 케이스를 가르나 — **로그의 최상위 스텝 순서 ↔ yaml 의 최상위 커맨드 순서**를 맞춘다.
  · 로그는 들여쓰기 0 이 최상위 스텝이고, 실행 순서 그대로 찍힌다.
  · yaml 은 `- ` 로 시작하는 줄이 최상위 커맨드고, 그 앞의 `# [NN] [Pri] 제목` 주석이
    그 커맨드가 속한 케이스다.
  · 플로우가 중간에 죽으면 로그 스텝이 거기서 끊긴다 → **끊긴 자리의 케이스가 깨진 케이스**다.

⛔ `takeScreenshot` 이름(`[02-1]_...`)으로 가르려 했으나 **396 케이스 중 112개(28%)**만
  마커가 있어 못 쓴다(14개 플로우는 0건). 이 방식은 마커 없이 전 플로우에 걸린다.
⛔ maestro 의 `commands.json` 에는 **소스 줄 정보가 없다**(status·timestamp·duration·
  sequenceNumber·depth 뿐) → 커맨드를 yaml 줄로 되짚을 수 없다. 그래서 순서로 맞춘다.

정렬이 맞는다는 근거 — 완주한 실행에서는 **로그 스텝 수 == yaml 커맨드 수**다
(2026-10-23 실행의 완주 25개 전부 일치). 어긋나면 귀속하지 않고 사유를 돌려준다.

※ docs/CHECKLIST.md §10 단계 4 의 `label:` 마커가 들어오면 이 추정은 필요 없어진다.
  그때까지의 다리다 — **추정이라는 것을 화면에도 적는다.**
"""

from __future__ import annotations

import re
from pathlib import Path

MAESTRO_DIR = Path(__file__).resolve().parent.parent / "Maestro"

# `... COMPLETED` 같은 꼬리. 이 줄이 곧 "그 스텝이 끝났다" 는 뜻이다.
_STATUS = re.compile(r"\.\.\.\s+(COMPLETED|FAILED|SKIPPED|WARNED|PENDING)\s*$")
_FLOW_HDR = re.compile(r"^\s*>\s*Flow\s")
# `# [NN] [High] 제목` / `# [33-1] 제목` — 중요도는 없을 수도 있다.
#   ⛔ **숫자로 시작하는 것만** 케이스로 본다. 느슨하게 받으면 `# [History] …` 같은 구역
#     주석까지 케이스로 잡혀 없는 케이스가 표에 생긴다(04_Menu_History 에서 실제로 그랬다).
#     케이스 번호는 `01` · `33-1` · `01-3` 처럼 숫자와 하이픈뿐이다.
_CASE_HDR = re.compile(r"^#\s*\[(\d[\d\-]*)\]\s*(?:\[(?:Low|Medium|High)\]\s*)?(.*)$")
# 로그에 적힌 실제 실행 커맨드. 파일명에 **공백이 있다**(`02_01_Overseas_Send now_old.yaml`)
# → `[^ ]+` 로 끊으면 안 된다. `.yaml` 까지 비탐욕으로 받는다.
_RAN_YAML = re.compile(r"\btest\s+(.+?\.ya?ml)(?:\s|$)")


class NoCases(RuntimeError):
    """케이스로 가를 수 없다. 사유를 그대로 화면에 보여준다."""


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def flow_path_from_log(lines: list[str]) -> Path | None:
    """로그에 적힌 `maestro … test Old\\X_old.yaml` 에서 **그때 실제로 돈 파일**을 집는다.

    이름으로 추측하지 않는 이유: 항목 이름과 파일명이 다른 경우가 있다
    (`02_01_Overseas_SendNow` → `Old\\02_01_Overseas_Send now_old.yaml`).
    표가 그 뒤로 바뀌었어도 **그 실행이 돌린 파일**이 정답이다.
    """
    for line in lines[:40]:
        m = _RAN_YAML.search(line)
        if m:
            return MAESTRO_DIR / m.group(1).replace("\\", "/")
    return None


def log_steps(lines: list[str]) -> tuple[list[tuple[str, str]], str | None]:
    """(끝난 최상위 스텝들, 끝내 안 닫힌 커맨드).

    ⚠️ 시작 줄과 종료 줄을 **텍스트로 짝지으면 안 된다.** 시작 줄에는 `${ASK_ME_LATER_TEXT}`
      원문이, 종료 줄에는 치환된 `"나중에 하기"` 가 찍힌다 → 같은 커맨드인데 글자가 다르다.
      그래서 **상태가 붙은 줄만 센다**(그 줄이 커맨드 하나의 끝이다).
    ⚠️ 마지막에 상태 없이 `...` 로 끝난 줄이 남으면 **그 커맨드를 돌다가 죽은 것**이다
      (`Assert that "${TOPUP_FAIL_ANY}" is visible...` 뒤에 바로 오류 블록). FAILED 가
      안 찍히는 실패가 실제로 있어서 이걸 같이 본다.
    """
    started, steps, open_text = False, [], None
    for line in lines:
        if not started:
            if _FLOW_HDR.match(line):
                started = True
            continue
        if line.startswith("===="):       # ==== Debug output … 부터는 산출물 안내다
            break
        if not line.strip() or line.startswith("WARNING:"):
            continue
        if line[:1].isspace():            # 들여쓰기 = 중첩 스텝
            continue
        m = _STATUS.search(line)
        if m:
            steps.append((m.group(1), _STATUS.sub("", line).strip()))
            open_text = None
        elif line.endswith("..."):
            open_text = line[:-3].strip()
    return steps, open_text


def yaml_cases(path: Path) -> tuple[list[str | None], list[str], dict[str, str]]:
    """(최상위 커맨드마다의 케이스번호, 케이스 순서, 케이스 제목).

    케이스 헤더보다 앞서는 커맨드는 `None` — 공통 진입부(launch·Server Override·PIN)다.
    """
    lines = _read(path)
    try:
        start = lines.index("---") + 1   # appId/env 머리 문서는 건너뛴다
    except ValueError:
        start = 0
    cur: str | None = None
    per: list[str | None] = []
    order: list[str] = []
    titles: dict[str, str] = {}
    for line in lines[start:]:
        stripped = line.lstrip()
        if stripped.startswith("# ["):
            m = _CASE_HDR.match(stripped)
            if m:
                cur = m.group(1)
                if cur not in titles:
                    titles[cur] = (m.group(2) or "").strip()
                    order.append(cur)
                continue
        if line.startswith("- "):
            per.append(cur)
    return per, order, titles


def _declared(value) -> set[str]:
    """`blocked`/`na` 선언을 케이스 번호 집합으로.

    ⚠️ **2026-10-26 이전 실행은 여기에 개수(int)가 들어 있다** — 번호 목록으로 바꾸기 전
      형식이다. 그때 실행에는 케이스 단위 선언이 없는 셈이므로 **빈 집합**으로 둔다
      (숫자를 순회하려다 `'int' object is not iterable` 로 죽던 자리다).
    시트는 `[5]`, 스위트는 `"05"` 로 적는 일이 있어 앞의 0 을 뗀다.
    """
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(c).lstrip("0") or "0" for c in value}


def analyze(log_path: Path, item: dict) -> dict:
    """항목 하나의 케이스별 결과.

    `item` 은 result.json 의 항목(`status`·`blocked`·`na`)이다.
    BLOCKED·N/A 는 **스위트 표의 선언**이라 로그 추정보다 우선한다.
    """
    if not log_path.exists():
        raise NoCases(f"로그가 없습니다: {log_path.name}")
    lines = _read(log_path)

    flow = flow_path_from_log(lines)
    if flow is None or not flow.exists():
        raise NoCases("로그에 실행한 yaml 경로가 없습니다 — 케이스를 가를 수 없습니다.")

    per, order, titles = yaml_cases(flow)
    if not order:
        raise NoCases(f"{flow.name} 에 `# [NN]` 케이스 헤더가 없습니다.")

    steps, open_text = log_steps(lines)
    if not steps and open_text is None:
        raise NoCases("로그에 실행된 스텝이 없습니다 — 시작 전에 끝났습니다.")
    # 로그가 yaml 보다 길면 순서 대응이 깨진 것이다. 억지로 귀속하면 **엉뚱한 케이스**를 지목한다.
    if len(steps) > len(per):
        raise NoCases(
            f"로그 스텝({len(steps)})이 yaml 커맨드({len(per)})보다 많습니다 — "
            "플로우가 바뀐 뒤의 로그일 수 있어 귀속하지 않습니다.")

    status = (item.get("status") or "").upper()
    fail_at: int | None = next((i for i, (s, _) in enumerate(steps) if s == "FAILED"), None)
    fail_step = steps[fail_at][1] if fail_at is not None else ""
    if fail_at is None and open_text is not None:
        fail_at, fail_step = len(steps), open_text      # 돌다가 죽은 커맨드
    fail_case = per[fail_at] if (fail_at is not None and fail_at < len(per)) else None

    blocked = _declared(item.get("blocked"))
    na = _declared(item.get("na"))

    # 실패 케이스의 위치. 공통 진입부(None)에서 깨졌으면 **모든 케이스가 미실행**이다.
    cut = order.index(fail_case) if fail_case in order else (-1 if fail_at is not None else len(order))

    out = []
    for idx, cid in enumerate(order):
        key = cid.lstrip("0") or cid
        if key in blocked:
            st = "BLOCKED"
        elif key in na:
            st = "NA"
        elif status == "PASS":
            st = "PASS"
        elif cut < 0 or idx > cut:
            st = "NOTRUN"
        elif idx == cut:
            st = "FAIL"
        else:
            st = "PASS"
        out.append({"id": cid, "title": titles.get(cid, ""), "status": st,
                    "step": fail_step if st == "FAIL" else ""})

    return {
        "flow": flow.name,
        "steps": len(steps),
        "commands": len(per),
        "entry_failed": fail_at is not None and fail_case is None,
        "fail_step": fail_step,
        "cases": out,
    }
