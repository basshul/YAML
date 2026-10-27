r"""실행 결과(`result.json`) → 체크리스트 행별 **자동 기입값**.

엑셀에 자동으로 나가는 값은 **`Pass` 와 `NA` 둘뿐**이다(docs/CHECKLIST.md §4).

| 케이스 상태 | 어디서 오나 | 기입 |
|---|---|---|
| PASS | 그 **케이스**가 통과했고 제외 목록에 없다 | `Pass` |
| N/A  | `run_suite.ps1` 의 `na=@(...)` | `NA` |
| FAIL · BLOCKED · SKIP · 미실행 | — | **넣지 않는다** |

★ **시나리오가 FAIL 이어도 그 안에서 통과한 케이스는 `Pass` 로 나간다**(2026-10-27).
  종전엔 시나리오 상태 하나를 모든 케이스에 그대로 씌워서, 48케이스 중 1개가 깨지면
  **나머지 47개가 통째로 보류**됐다 — 기입할 게 0건이라 저장 버튼도 열리지 않았다.
  케이스를 가르는 것은 `case_result.analyze` 다(로그 스텝 ↔ yaml 커맨드 순서 대조).
  ⚠️ **추정이다.** 가르지 못하면(로그가 짧다·yaml 이 바뀌었다·케이스 헤더가 없다)
    **종전대로 시나리오 상태를 씌운다** — 틀린 값을 만드느니 보류가 낫다.

⛔ **자동 `Fail` 을 쓰지 않는 이유**(§5·§11): 외부 요인·셋팅 불량으로 Fail 이 나는 경우가
  실재한다. 그대로 쓰면 **거짓 결함이 정본으로 승격**된다. 사람이 확인해 최종값을 고른
  뒤에야 나간다 — 그때는 「사람 수정」 쪽이지 자동 기입이 아니다.
⛔ `Not Test` 도 자동으로 넣지 않는다. "못 했다" 는 사람만 선언할 수 있다.

한 행이 케이스 여러 개를 덮는 경우가 있다(`maps` 가 둘 이상):
  · 하나라도 FAIL·BLOCKED·SKIP·미실행 → **보류**. 행 전체를 사람에게 남긴다
  · 전부 N/A → `NA`
  · PASS 하나 이상 + 나머지가 N/A → `Pass`
    (확인할 수 있는 건 통과했고 나머지는 확인할 화면이 없다는 뜻이다)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import case_result

WEB_RUNNER_DIR = Path(__file__).resolve().parent

# `case_result` 의 케이스 상태 → 이 모듈의 판정 어휘.
#   NOTRUN·FAIL·BLOCKED 는 "PASS/N-A 가 아닌 것" 이면 충분하다(= 행 보류).
_FROM_CASE = {"PASS": "PASS", "NA": "N/A", "FAIL": "FAIL",
              "BLOCKED": "BLOCKED", "NOTRUN": "NOTRUN"}

# 케이스 번호만 뽑는다. 시트의 `[02]+[03] 설명` 같은 묶음도 캐시가 이미 ["02","03"] 로 쪼개 둔다.
_NUM = re.compile(r"\d+")

PASS = "Pass"
NA = "NA"


class NoRun(RuntimeError):
    """result.json 이 없다. 아직 한 번도 완주하지 않았을 수 있다."""


def load_run(run_dir: str | Path) -> dict:
    """`suite_logs/<시각>/result.json` 을 읽는다.

    ⚠️ SUMMARY.md 로는 대신할 수 없다 — 거기엔 **케이스 단위 blocked/na 가 합계로만** 있어서
      어느 케이스가 N/A 인지 알 수 없다(`runner._parse_summary` 도 그래서 못 쓴다).
    """
    p = Path(run_dir)
    if p.is_dir():
        p = p / "result.json"
    if not p.exists():
        raise NoRun(f"result.json 이 없습니다: {p}")
    return json.loads(p.read_text(encoding="utf-8-sig"))


def split_cases(run_dir, item: dict) -> dict[str, str] | None:
    """로그를 케이스로 갈라 `{케이스번호: 상태}`. 가르지 못하면 `None`.

    `case_result.analyze` 가 **스스로 거절**하는 경우가 있다(로그 스텝이 yaml 커맨드보다
    많다 = 그 뒤 yaml 이 바뀌었다 / 케이스 헤더가 없다 / 실행 경로가 로그에 없다).
    그때는 None 을 돌려 **종전 방식(시나리오 상태를 전부에 씌우기)** 으로 떨어진다.
    """
    if run_dir is None:
        return None
    name = (item.get("name") or "").strip()
    if not name:
        return None
    try:
        res = case_result.analyze(Path(run_dir) / f"{name}.log", item)
    except Exception:
        return None                       # 가르지 못하면 조용히 종전 방식으로
    per = {}
    for c in res.get("cases") or []:
        st = _FROM_CASE.get((c.get("status") or "").upper())
        if st:
            per[_norm_case(c.get("id"))] = st
    return per or None


def _case_states(run: dict, run_dir=None) -> dict[str, dict[str, str]]:
    """{시나리오: {케이스번호: 상태}} + {시나리오: {"*": 시나리오상태}}.

    `blocked`/`na` 는 run_suite 의 선언값이라 **번호 문자열**이다("05" · "33-1" 등).
    앞의 0 을 떼서 맞춘다 — 시트는 `[5]` 로, 스위트는 `"05"` 로 적는 일이 있다.
    ★ 시나리오가 PASS 가 아니면 로그를 케이스로 갈라 본다 — 깨진 케이스만 보류하고
      나머지는 살린다. PASS 면 전부 PASS 라 가를 이유가 없다(로그도 안 읽는다).
    """
    out: dict[str, dict[str, str]] = {}
    for item in run.get("items") or []:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        status = (item.get("status") or "").strip().upper()
        per = {"*": status}
        if status != "PASS":
            per.update(split_cases(run_dir, item) or {})
        # 선언값(BLOCKED·N/A)은 **스위트 표가 정본**이라 로그 추정을 덮는다.
        for key, state in (("blocked", "BLOCKED"), ("na", "N/A")):
            for c in item.get(key) or []:
                per[_norm_case(c)] = state
        for key in _flow_keys(run_dir, item):
            out[key] = per
    return out


def _norm_flow(name: str) -> str:
    """파일명·항목이름을 한 가지 꼴로. 경로·확장자·`_old`·공백을 떼고 소문자.
    ★ 화면(`app.js normFile`)·러너(`runner.norm_flow_name`)와 **같은 방식**이어야 한다."""
    s = re.sub(r"^.*[\\/]", "", str(name or ""))
    s = re.sub(r"\.ya?ml$", "", s, flags=re.I)
    s = re.sub(r"_old$", "", s, flags=re.I)
    return re.sub(r"\s+", "", s).lower().strip()


def _flow_keys(run_dir, item: dict) -> set[str]:
    """이 항목을 가리킬 수 있는 키들(정규화).

    항목 이름만으로는 안 된다 — 체크리스트는 **파일명**으로 적고 둘이 다른 경우가 있다
    (`14_01_Deposit` ↔ `14_01_Deposit_seungsoo818`). 이름이 바뀐 뒤의 과거 실행도 마찬가지다.
    그래서 **로그에 적힌 실제 yaml** 을 풀어 그 이름도 같이 키로 쓴다.
    """
    keys = {_norm_flow(item.get("name"))}
    name = (item.get("name") or "").strip()
    if run_dir and name:
        try:
            flow = case_result.resolve_flow(Path(run_dir) / f"{name}.log")
        except Exception:
            flow = None
        if flow is not None:
            keys.add(_norm_flow(flow.name))
    keys.discard("")
    return keys


def _norm_case(c: str) -> str:
    """`"05"` · `"5"` · `"[05]"` → `"5"`. 분할 번호(`33-1`)는 조각마다 정규화한다."""
    parts = _NUM.findall(str(c))
    return "-".join(str(int(p)) for p in parts) if parts else str(c).strip()


def derive(run: dict, rows: list[dict], run_dir=None) -> list[dict]:
    """행마다 자동 기입값을 정한다. 넣을 게 없는 행은 결과에 담지 않는다.

    `rows` 는 `checklist_cache.json` 의 `rows` 다(`case_id`·`row`·`pairs` 를 쓴다).
    `run_dir` 을 주면 FAIL 시나리오를 **케이스 단위로 갈라** 통과한 케이스를 살린다.
    """
    states = _case_states(run, run_dir)
    out = []
    for r in rows:
        cid = (r.get("case_id") or "").strip()
        if not cid:
            continue                      # Case ID 가 없으면 키가 없다 → 손대지 않는다
        verdicts = []
        for pair in r.get("pairs") or []:
            per = states.get(_norm_flow(pair.get("file")))
            if per is None:
                verdicts.append("MISS")   # 이번 실행에 없는 시나리오
                continue
            for c in pair.get("cases") or []:
                verdicts.append(per.get(_norm_case(c)) or per["*"])
        if not verdicts:
            continue                      # 매핑이 없는 행(자동화 불가 포함) — 비워 둔다
        if any(v not in ("PASS", "N/A") for v in verdicts):
            continue                      # FAIL·BLOCKED·SKIP·미실행이 섞였다 → 사람 몫
        value = NA if all(v == "N/A" for v in verdicts) else PASS
        out.append({
            "case_id": cid,
            "row": r.get("row"),
            "value": value,
            "maps": r.get("maps") or [],
            "text": r.get("text") or "",
        })
    return out


def pending(derived: list[dict], rows: list[dict], column_values: dict[str, str]) -> list[dict]:
    """엑셀에 **이미 같은 값이 있는 행은 뺀다**(§8).

    안 그러면 실행마다 417칸을 전부 PATCH 하게 된다.
    `column_values` 는 {case_id: 현재 셀 값} 이다.
    """
    out = []
    for d in derived:
        cur = (column_values.get(d["case_id"]) or "").strip()
        if cur == d["value"]:
            continue
        out.append({**d, "current": cur})
    return out
