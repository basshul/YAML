"""Maestro 테스트를 브라우저에서 고르고 실행하는 데모 서버.

PowerShell 호출은 전부 runner.py 가 맡는다 — 여기서는 직접 부르지 않는다.
실행:  .venv\\Scripts\\python.exe server.py     (또는 start.ps1)
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import runner
import checklist as checklist_cache
import checklist_result
import case_result
from admin import actions as admin_actions

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Maestro Web Runner (demo)")


@app.middleware("http")
async def no_cache_html(request, call_next):
    """HTML 은 **캐시하지 않는다**.

    css/js 는 `?v=` 로 캐시를 무효화할 수 있지만 **HTML 자신은 그럴 수가 없다.**
    그래서 화면을 고쳐도 브라우저가 옛 index.html 을 들고 있고, 그게 옛 app.js 를
    불러 **기능이 통째로 없는 화면**이 뜬다(2026-10-02·10-06 두 번 겪었다).
    로컬 데모라 HTML 재검증 비용은 무시할 만하다.
    """
    response = await call_next(request)
    path = request.url.path
    if path.endswith(".html") or path.endswith("/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@app.get("/api/tests")
def api_tests():
    """스위트 표에서 읽은 테스트 목록 (G9 파괴적 항목 제외)."""
    try:
        return {"tests": runner.list_tests()}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/checklist")
def api_checklist():
    """체크리스트 캐시를 그대로 돌려준다.

    ★ 매핑이 맞는지(시나리오·케이스가 실재하는지)는 **화면이 /api/tests 와 맞춰** 본다.
      서버가 또 조회하면 pwsh 를 한 번 더 타서 20초가 더 걸린다.
    """
    try:
        return checklist_cache.load()
    except checklist_cache.ChecklistUnavailable as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})


@app.get("/api/checklist/pending")
def api_checklist_pending(stamp: str):
    """실행 하나(`stamp`)를 체크리스트 행별 **자동 기입값**으로 바꿔 돌려준다.

    `aborted` 실행도 그대로 받는다 — 중단 전까지 끝난 시나리오의 결과는 멀쩡한데
    그걸 못 쓰면 몇 시간짜리 실행이 통째로 버려진다. 실제로 2026-10-23 실행(중단)에서
    102행이 나온다. 「어느 실행을 볼 것인가」는 화면의 `결과 기준` 셀렉트가 정한다
    (docs/CHECKLIST.md §7) — 이 엔드포인트는 그 셀렉트의 뒷단이다.

    ⚠️ **`current` 는 아직 전부 빈 값이다.** `pending()` 의 "엑셀에 이미 같은 값이 있으면
      뺀다"(§8)를 하려면 결과 열의 현재 값이 필요한데, **캐시에 그 열이 없다** —
      `checklist_layout.HEADER_ALIASES` 가 결과 열을 읽지 않아 `checklist_sync.py` 가
      받아오지 않는다. 그래서 `column_values={}` 로 돌리며 **pending == derived** 다.
      응답의 `column_source: null` 이 그 사실을 드러낸다. 열을 캐시에 실으면 여기만 바꾸면 된다.
      ⛔ 그 전까지는 저장 단계에서 **같은 값을 다시 PATCH 할 수 있다**는 뜻이다.
    """
    # ⚠️ try 를 셋으로 나눈 이유: `json.JSONDecodeError` 가 **ValueError 의 하위**라
    #   한 덩어리로 묶으면 깨진 result.json 이 "잘못된 stamp"(400)로 둔갑한다.
    try:
        path = runner.run_result_path(stamp)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    try:
        run = checklist_result.load_run(path)
    except checklist_result.NoRun as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except (OSError, ValueError) as exc:
        return JSONResponse(status_code=500,
                            content={"error": f"result.json 을 읽지 못했습니다: {exc}"})

    try:
        rows = checklist_cache.load()["rows"]
    except checklist_cache.ChecklistUnavailable as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})

    try:
        derived = checklist_result.derive(run, rows)
    except (TypeError, KeyError, AttributeError) as exc:
        # 옛 형식 result.json(blocked/na 가 **개수**)이 여기로 들어오면 터진다.
        #   2026-10-26 수정 전 실행이 그렇다 — 500 으로 숨기지 말고 사유를 그대로 준다.
        return JSONResponse(status_code=422, content={"error":
            f"이 실행의 result.json 은 기입값을 만들 수 없는 형식입니다({exc}). "
            "2026-10-26 이전 실행은 BLOCKED/N/A 를 개수로만 담고 있습니다."})

    items = checklist_result.pending(derived, rows, {})
    return {
        # ★ 파일 안의 `stamp` 가 아니라 **요청한 폴더 이름**을 그대로 돌려준다.
        #   로그·result.json 을 찾는 키가 폴더 이름이라, 둘이 어긋나면 화면이 되물을 때
        #   404 가 난다. 응답은 요청을 그대로 되비춰야 한다.
        "stamp": stamp,
        "aborted": bool(run.get("aborted")),
        "ran": len(run.get("items") or []),
        "rows": len(rows),
        "counts": {
            "derived": len(derived),
            "pending": len(items),
            "pass": sum(1 for d in items if d["value"] == checklist_result.PASS),
            "na": sum(1 for d in items if d["value"] == checklist_result.NA),
        },
        # 현재 엑셀 값의 출처. 지금은 없다(위 ⚠️) — 화면이 "중복 PATCH 가능"을 알 수 있게 내보낸다.
        "column_source": None,
        "items": items,
    }


@app.get("/api/devices")
def api_devices():
    """adb 로 조회한 연결 기기 목록."""
    try:
        return {"devices": runner.list_devices()}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/config")
def api_config():
    """화면이 그릴 때 필요한 설정값(비밀정보는 내보내지 않는다)."""
    cfg = runner.load_config()
    return {
        "lang": cfg["lang"],
        "default_device": cfg["default_device"],
        "builds": [
            {"value": key, "label": val["label"], "pkg": val["pkg"]}
            for key, val in runner.BUILD_CHOICES.items()
        ],
        "servers": [
            {"value": key, "label": val["label"], "host": val["host"], "live": val["live"]}
            for key, val in runner.SERVER_CHOICES.items()
        ],
        "group_labels": runner.GROUP_LABELS,
    }


@app.get("/api/history")
def api_history(limit: int = 50):
    """지난 실행 이력. 정본은 run_suite.ps1 이 쓰는 suite_logs\\<시각>\\SUMMARY.md 다
    (웹 밖에서 돌린 실행도 여기 들어온다)."""
    try:
        return {"runs": runner.read_history(limit)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/history/{stamp}/log")
def api_history_log(stamp: str, item: str):
    try:
        return {"text": runner.read_item_log(stamp, item)}
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})


@app.get("/api/history/{stamp}/cases")
def api_history_cases(stamp: str, item: str):
    """항목 하나의 **케이스별 결과**. 시나리오가 FAIL 일 때 어디서 깨졌는지 짚어 준다.

    ⚠️ **추정이다.** 로그의 최상위 스텝 순서를 yaml 의 최상위 커맨드 순서에 맞춰 센다
      (`case_result` 머리말 참고). 케이스 경계 마커(docs/CHECKLIST.md §10 단계 4)가
      들어오기 전까지의 다리이므로, 화면도 추정이라고 적어야 한다.
    ⛔ 가를 수 없는 경우(케이스 헤더 없음·정렬 어긋남 등)는 **지어내지 않고** 422 로
      사유를 그대로 돌려준다. 엉뚱한 케이스를 지목하는 것이 모르는 것보다 나쁘다.
    """
    try:
        log_path = runner.run_item_log_path(stamp, item)
        result_path = runner.run_result_path(stamp)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})

    try:
        run = checklist_result.load_run(result_path)
    except (checklist_result.NoRun, OSError, ValueError) as exc:
        return JSONResponse(status_code=404, content={"error": f"실행 기록을 읽지 못했습니다: {exc}"})

    entry = next((i for i in (run.get("items") or []) if (i.get("name") or "") == item), None)
    if entry is None:
        return JSONResponse(status_code=404,
                            content={"error": f"{stamp} 기록에 {item} 항목이 없습니다."})

    try:
        data = case_result.analyze(log_path, entry)
    except case_result.NoCases as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    return {"stamp": stamp, "item": item, "status": entry.get("status") or "", **data}


_admin_lock = threading.Lock()


class PreflightRequest(BaseModel):
    # 사용자 프로파일. 점검 대상 계정이 사람마다 다르다.
    user: str = ""


@app.post("/api/admin/preflight")
def api_admin_preflight(req: PreflightRequest):
    """admin 에 붙어 스위트 사전 조건(계정 5개)을 **조회만으로** 점검한다.

    로그인 → 점검 → 로그아웃을 한 세션으로 처리한다(1분 안팎 걸린다).
    한 번에 하나만 — admin 세션을 동시에 두 개 열지 않는다.
    """
    if not _admin_lock.acquire(blocking=False):
        return JSONResponse(status_code=409, content={"error": "이미 점검이 돌고 있습니다."})
    try:
        return admin_actions.run_preflight(_known_user(req.user))
    except ValueError as exc:
        # 사용자가 잘못 고른 것이다 — 서버 오류(500)가 아니다.
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        _admin_lock.release()


class FixRequest(BaseModel):
    fix: str
    user_id: str
    confirm: bool = False
    user: str = ""


@app.post("/api/admin/fix")
def api_admin_fix(req: FixRequest):
    """사전 조건의 NG 항목 하나를 처리한다. **되돌릴 수 없다.**

    처리 뒤 **그 항목만 다시 점검해서** 돌려준다(전체 재점검은 1분 걸린다).
    ⚠️ confirm 없이는 돌지 않는다 — 운영(Live) 실행과 같은 규칙이다.
    """
    if not req.confirm:
        return JSONResponse(status_code=400,
                            content={"error": "되돌릴 수 없는 처리입니다. 확인이 필요합니다."})
    if not _admin_lock.acquire(blocking=False):
        return JSONResponse(status_code=409, content={"error": "admin 작업이 이미 돌고 있습니다."})
    try:
        return admin_actions.run_fix(req.fix, req.user_id, _known_user(req.user), confirm=True)
    except (ValueError, admin_actions.AdminError) as exc:
        # 잘못 고른 사용자 / 내 프로파일이 아닌 대상 — 서버 오류가 아니다.
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        _admin_lock.release()


class FixAllRequest(BaseModel):
    items: list[dict]
    confirm: bool = False
    user: str = ""


@app.post("/api/admin/fix-all")
def api_admin_fix_all(req: FixAllRequest):
    """NG 여러 건을 **한 세션에서** 처리한다. **되돌릴 수 없다.**

    건별 /api/admin/fix 는 호출마다 로그인·로그아웃을 한 바퀴 돈다 —
    여러 건이면 로그인만 N 번이다. 이 경로는 한 번만 로그인한다.
    """
    if not req.confirm:
        return JSONResponse(status_code=400,
                            content={"error": "되돌릴 수 없는 처리입니다. 확인이 필요합니다."})
    items = []
    for it in req.items:
        fix, user_id = it.get("fix"), (it.get("user_id") or "").strip()
        # 화면이 보낸 값을 그대로 믿지 않는다 — 아는 처리·빈 계정만 통과시킨다
        if fix not in admin_actions.FIXES or not user_id:
            return JSONResponse(status_code=400,
                                content={"error": f"처리할 수 없는 항목입니다: {it}"})
        items.append({"fix": fix, "user_id": user_id})
    if not items:
        return JSONResponse(status_code=400, content={"error": "처리할 항목이 없습니다."})

    if not _admin_lock.acquire(blocking=False):
        return JSONResponse(status_code=409, content={"error": "admin 작업이 이미 돌고 있습니다."})
    try:
        return admin_actions.run_fix_all(items, _known_user(req.user), confirm=True)
    except (ValueError, admin_actions.AdminError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        _admin_lock.release()


def _known_user(user: str) -> str:
    """사용자 이름은 **파일 경로**가 된다 → 허용 목록 밖이면 거절한다.

    빈 값은 "아직 안 골랐다" 는 뜻이다. 기본값으로 메우지 않는다 —
    조용히 누군가로 정해 버리면 **남의 계정을 건드리게 된다.**
    """
    if not user:
        raise ValueError("먼저 사용자를 선택하세요.")
    if user not in runner.USER_CHOICES:
        raise ValueError(f"알 수 없는 사용자: {user}")
    return user


class RunRequest(BaseModel):
    tests: list[str]
    device: str
    # 빌드(어느 APK)와 서버(어느 백엔드)는 **독립**이다. 둘 다 받는다.
    #   build 를 안 보내는 옛 화면도 받아주되, 종전 동작(stag)으로 간다.
    build: str = "stag"
    server: str
    platform: str = "android"
    confirm_live: bool = False
    # 사용자 프로파일. 값 검증은 runner.start_run 이 허용 목록으로 한다.
    user: str = ""


@app.post("/api/run")
def api_run(req: RunRequest):
    """실행 시작. 한 번에 하나만 — 대기열은 이번 데모 범위 밖이다."""
    if req.platform != "android":
        return JSONResponse(status_code=400, content={"error": "iOS 실행은 아직 지원하지 않습니다."})
    # 운영(Live)은 실자금이 움직인다 → 화면에서 한 번 더 확인받은 요청만 받는다.
    #   ★ 기준은 **서버**다 — stag 빌드라도 LIVE 서버에 붙으면 실계정·실자금이다.
    #     운영 빌드는 서버를 고를 수 없어(combo_error) 늘 운영 서버이므로 함께 본다.
    is_live = (runner.SERVER_CHOICES.get(req.server, {}).get("live")
               or req.build == "live")
    if is_live and not req.confirm_live:
        return JSONResponse(status_code=400, content={"error": "운영(Live) 실행은 확인이 필요합니다."})
    try:
        run = runner.start_run(req.tests, req.device, req.build, req.server,
                               _known_user(req.user))
    except RuntimeError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return run.status()


@app.post("/api/run/stop")
def api_run_stop():
    """실행 중단. ⚠️ 자동 복구도 함께 끊기므로 앱은 중단 시점 화면에 남는다."""
    run = runner.current_run()
    if not run or run.finished:
        return JSONResponse(status_code=409, content={"error": "중단할 실행이 없습니다."})
    run.stop()
    return run.status()


@app.get("/api/run/status")
def api_run_status():
    run = runner.current_run()
    return run.status() if run else {"running": False}


@app.get("/api/run/stream")
def api_run_stream():
    """실행 로그를 줄 단위로 흘려보낸다(Server-Sent Events)."""
    run = runner.current_run()
    if not run:
        return JSONResponse(status_code=404, content={"error": "실행 중인 작업이 없습니다."})

    def events():
        q = run.subscribe()
        try:
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"   # 프록시·브라우저가 끊지 않게
                    continue
                if event is None:
                    event = {"type": "done", "summary": run.summary}
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    return
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            run.unsubscribe(q)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    port = runner.load_config()["port"]
    print(f"\n  브라우저에서 열기:  http://localhost:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
