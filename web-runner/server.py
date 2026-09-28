"""Maestro 테스트를 브라우저에서 고르고 실행하는 데모 서버.

PowerShell 호출은 전부 runner.py 가 맡는다 — 여기서는 직접 부르지 않는다.
실행:  .venv\\Scripts\\python.exe server.py     (또는 start.ps1)
"""

from __future__ import annotations

import json
import queue
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import runner

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Maestro Web Runner (demo)")


@app.get("/api/tests")
def api_tests():
    """스위트 표에서 읽은 테스트 목록 (G9 파괴적 항목 제외)."""
    try:
        return {"tests": runner.list_tests()}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


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
        "servers": [
            {"value": key, "label": val["label"], "live": val["live"]}
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


class RunRequest(BaseModel):
    tests: list[str]
    device: str
    server: str
    platform: str = "android"
    confirm_live: bool = False


@app.post("/api/run")
def api_run(req: RunRequest):
    """실행 시작. 한 번에 하나만 — 대기열은 이번 데모 범위 밖이다."""
    if req.platform != "android":
        return JSONResponse(status_code=400, content={"error": "iOS 실행은 아직 지원하지 않습니다."})
    # 운영(Live)은 실자금이 움직인다 → 화면에서 한 번 더 확인받은 요청만 받는다.
    if runner.SERVER_CHOICES.get(req.server, {}).get("live") and not req.confirm_live:
        return JSONResponse(status_code=400, content={"error": "운영(Live) 실행은 확인이 필요합니다."})
    try:
        run = runner.start_run(req.tests, req.device, req.server)
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
