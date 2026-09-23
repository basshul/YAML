# web-runner 데모 서버 실행
#   .\start.ps1
# 처음 한 번은 아래로 환경을 만든다:
#   python -m venv .venv
#   .venv\Scripts\python.exe -m pip install -r requirements.txt
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "가상환경이 없습니다. README.md 의 '처음 한 번' 절을 보세요."
    exit 1
}
& $py (Join-Path $here "server.py")
