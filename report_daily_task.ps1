# ================================================================
# report_daily_task.ps1 — 스케줄러가 부르는 래퍼 (매일 22:00)
#
# 왜 래퍼가 따로 있나:
#   ① 스케줄 작업은 **화면이 없다.** 실패하면 아무 데도 안 남는다 →
#      여기서 전 출력을 날짜별 로그로 받아 둔다. 오늘 하루 겪은 사고가
#      전부 "조용히 실패하는 경로" 였다.
#   ② schtasks 인자에 리다이렉션·따옴표를 욱여넣으면 파서가 밀린다
#      (한글까지 섞이면 더). 작업은 이 파일 하나만 부르게 한다.
#
# 수동 실행도 같은 방식으로:  .\report_daily_task.ps1
# ================================================================
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

$logDir = Join-Path $repo "artifacts\daily_report"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("_task_{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 데일리 리포트 시작 ===" | Out-File $log -Append -Encoding utf8

& (Join-Path $repo "report_daily.ps1") *>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE

"=== 종료 코드: $code ($(Get-Date -Format 'HH:mm:ss')) ===" | Out-File $log -Append -Encoding utf8
exit $code
