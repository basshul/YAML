r"""실행 결과(`result.json`) → 체크리스트 행별 **자동 기입값**.

엑셀에 자동으로 나가는 값은 **`Pass` 와 `NA` 둘뿐**이다(docs/CHECKLIST.md §4).

| 케이스 상태 | 어디서 오나 | 기입 |
|---|---|---|
| PASS | 시나리오가 PASS 고 그 케이스가 제외 목록에 없다 | `Pass` |
| N/A  | `run_suite.ps1` 의 `na=@(...)` | `NA` |
| FAIL · BLOCKED · SKIP · 미실행 | — | **넣지 않는다** |

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

WEB_RUNNER_DIR = Path(__file__).resolve().parent

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


def _case_states(run: dict) -> dict[str, dict[str, str]]:
    """{시나리오: {케이스번호: 상태}} + {시나리오: {"*": 시나리오상태}}.

    `blocked`/`na` 는 run_suite 의 선언값이라 **번호 문자열**이다("05" · "33-1" 등).
    앞의 0 을 떼서 맞춘다 — 시트는 `[5]` 로, 스위트는 `"05"` 로 적는 일이 있다.
    """
    out: dict[str, dict[str, str]] = {}
    for item in run.get("items") or []:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        per = {"*": (item.get("status") or "").strip().upper()}
        for key, state in (("blocked", "BLOCKED"), ("na", "N/A")):
            for c in item.get(key) or []:
                per[_norm_case(c)] = state
        out[name] = per
    return out


def _norm_case(c: str) -> str:
    """`"05"` · `"5"` · `"[05]"` → `"5"`. 분할 번호(`33-1`)는 조각마다 정규화한다."""
    parts = _NUM.findall(str(c))
    return "-".join(str(int(p)) for p in parts) if parts else str(c).strip()


def derive(run: dict, rows: list[dict]) -> list[dict]:
    """행마다 자동 기입값을 정한다. 넣을 게 없는 행은 결과에 담지 않는다.

    `rows` 는 `checklist_cache.json` 의 `rows` 다(`case_id`·`row`·`pairs` 를 쓴다).
    """
    states = _case_states(run)
    out = []
    for r in rows:
        cid = (r.get("case_id") or "").strip()
        if not cid:
            continue                      # Case ID 가 없으면 키가 없다 → 손대지 않는다
        verdicts = []
        for pair in r.get("pairs") or []:
            per = states.get((pair.get("file") or "").strip())
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
