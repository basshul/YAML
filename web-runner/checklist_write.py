r"""실행 결과를 체크리스트 엑셀에 **기입**한다 (docs/CHECKLIST.md 단계 4).

지금까지는 "무엇이 나갈지" 미리보기까지만 있었다(`checklist_result.pending`).
이 모듈이 그 값을 실제 셀에 쓴다.

⛔ 자동으로 나가는 값은 **`Pass` · `NA` 둘뿐**이다. `Fail` 은 사람이 확인한 뒤에야 나간다
  (§5·§11 — 외부 요인으로 난 Fail 이 정본으로 승격되면 안 된다).
⛔ **이미 값이 있는데 다르면 덮지 않는다.** 사람이 적어 둔 값을 자동이 지우는 쪽이,
  안 쓰고 남기는 쪽보다 훨씬 나쁘다 → 그런 칸은 `conflict` 로 돌려주고 사람이 판단한다.
⛔ 열 문자를 **지어내지 않는다.** 결과 열은 그 시트의 머리글 아랫단에서 찾는다
  (`checklist_layout.Layout.result_col`). 못 찾으면 쓰지 않고 사유를 올린다.
⛔ 행 번호도 믿고 쓰지 않는다. 쓰기 직전 **그 행의 Case ID 가 맞는지 대조**한다 —
  캐시가 낡아 행이 밀려 있으면 **남의 칸에 Pass 를 적게 된다.**

⚠️ **쓰고 바로 읽으면 빈 값이 나올 수 있다**(2026-10-27 실측). 워크북 세션 없이 PATCH 하면
  Graph 쪽 반영이 한 박자 늦는다 — PATCH 응답이 성공이면 들어간 것이고, 잠시 뒤 읽으면
  보인다. **읽어서 확인되지 않는다고 다시 쓰지 말 것** — 같은 칸을 두 번 쓰게 된다.

시트는 **실행 환경이 고른다**: 같은 문서 안에 `Checklist(Live)` 와 `Checklist(Livetest)`
가 따로 있고, livetest 서버로 돈 결과를 Live 시트에 적으면 그 자체가 거짓이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_RUNNER_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

import gme_excel                                   # noqa: E402
import checklist_layout                            # noqa: E402

# 실행 서버 → 기입할 시트. config 의 `checklist.write.sheets` 로 덮을 수 있다.
#   ⛔ `stag` 는 **일부러 비워 둔다** — 그 시트가 문서에 없다. 비슷한 데 적는 것보다
#     안 적고 사유를 말하는 편이 낫다.
SHEET_BY_SERVER = {
    "livetest": "Checklist(Livetest) (2.2)",
    "live": "Checklist(Live) (2.2)",
}


class WriteBlocked(RuntimeError):
    """기입할 수 없다. 사유를 그대로 화면에 보여 준다."""


def _cfg(config: dict) -> dict:
    return ((config or {}).get("checklist") or {}).get("write") or {}


def target_sheet(server: str, config: dict) -> str:
    """이 실행을 어느 시트에 적을 것인가."""
    key = (server or "").strip().lower()
    sheets = {**SHEET_BY_SERVER, **(_cfg(config).get("sheets") or {})}
    sheet = sheets.get(key)
    if not sheet:
        raise WriteBlocked(
            f"'{key or '(없음)'}' 서버로 돈 실행은 적을 시트가 없습니다. "
            f"문서에 있는 것은 {', '.join(sorted(sheets))} 뿐입니다 — "
            "어느 시트에 넣을지는 사람이 정해야 합니다.")
    return sheet


def target_link(config: dict) -> str:
    """기입 대상 문서. 없으면 읽기와 같은 문서를 쓴다(보통 같은 파일이다)."""
    cl = (config or {}).get("checklist") or {}
    link = (_cfg(config).get("url") or cl.get("url") or "").strip()
    if not link:
        raise WriteBlocked("기입 대상 문서가 설정되지 않았습니다 "
                           "(config.local.json 의 checklist.write.url).")
    return link


def open_sheet(link: str, sheet: str):
    """(workbook 주소, 파일명, Layout). 결과 열은 이 시트의 머리글에서 찾는다."""
    wb, name = gme_excel.workbook_url(link)

    def fetch(a1):
        return gme_excel._req(gme_excel._range(wb, sheet, a1),
                              headers=gme_excel.H())["values"]

    lay = checklist_layout.detect(fetch)
    lay.sheet = sheet
    return wb, name, lay


def _col_values(wb: str, sheet: str, col: str, first: int, last: int) -> list[str]:
    vals = gme_excel._req(gme_excel._range(wb, sheet, f"{col}{first}:{col}{last}"),
                          headers=gme_excel.H())["values"]
    return [("" if not r or r[0] is None else str(r[0]).strip()) for r in vals]


def read_state(wb: str, lay, platform: str, last_row: int = 600) -> dict:
    """현재 시트 상태. `{row: {"case_id":…, "current":…}}` 와 결과 열 문자.

    Case ID 를 같이 읽는 이유는 **행이 맞는지 대조**하기 위해서다(위 ⛔).
    """
    col = lay.result_col(platform)
    cid_col = checklist_layout.col_letter(lay.idx["case_id"])
    first = lay.first_row
    ids = _col_values(wb, lay.sheet, cid_col, first, last_row)
    cur = _col_values(wb, lay.sheet, col, first, last_row)
    state = {}
    for i, cid in enumerate(ids):
        if cid:
            state[first + i] = {"case_id": cid, "current": cur[i] if i < len(cur) else ""}
    return {"col": col, "rows": state}


def plan(items: list[dict], state: dict) -> dict:
    """무엇을 쓰고 무엇을 거를지 가른다. **쓰기 전에** 전부 정해 둔다.

    - `write`    : 빈 칸 → 적는다
    - `same`     : 이미 같은 값 → 건너뛴다(§8)
    - `conflict` : 다른 값이 이미 있다 → **덮지 않는다**
    - `mismatch` : 그 행의 Case ID 가 다르다 → 캐시가 낡았다. 손대지 않는다
    """
    out = {"write": [], "same": [], "conflict": [], "mismatch": []}
    for it in items:
        row = it.get("row")
        info = state["rows"].get(row)
        cell = f"{state['col']}{row}"
        rec = {**it, "cell": cell, "sheet_case_id": info["case_id"] if info else None,
               "current": info["current"] if info else ""}
        if info is None or info["case_id"] != it.get("case_id"):
            out["mismatch"].append(rec)
        elif not info["current"]:
            out["write"].append(rec)
        elif info["current"] == it.get("value"):
            out["same"].append(rec)
        else:
            out["conflict"].append(rec)
    return out


def apply(wb: str, sheet: str, rows: list[dict], on_progress=None) -> list[dict]:
    """`plan()['write']` 를 실제로 쓴다. 한 칸씩 PATCH 한다.

    ⚠️ 범위 하나로 묶어 쓰지 않는다 — 가운데 손대면 안 되는 칸이 섞여 있고,
      범위 PATCH 는 그 칸을 **빈 값으로 덮는다.**
    """
    done = []
    for n, rec in enumerate(rows, 1):
        try:
            gme_excel._req(gme_excel._range(wb, sheet, rec["cell"]), "PATCH",
                           {"values": [[rec["value"]]]}, headers=gme_excel.H())
            done.append({**rec, "ok": True})
        except Exception as exc:                   # 한 칸이 실패해도 나머지는 계속
            done.append({**rec, "ok": False, "error": str(exc)})
        if on_progress:
            on_progress(n, len(rows), done[-1])
    return done
