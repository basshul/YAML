"""Maestro 테스트를 브라우저에서 고르고 실행하는 데모 서버.

PowerShell 호출은 전부 runner.py 가 맡는다 — 여기서는 직접 부르지 않는다.
실행:  .venv\\Scripts\\python.exe server.py     (또는 start.ps1)
"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    port = runner.load_config()["port"]
    print(f"\n  브라우저에서 열기:  http://localhost:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
