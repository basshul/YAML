# ================================================================
# run_test.ps1 (저장소 루트) — 테스트 이미지 배치 + Maestro\run_test.ps1 위임
#
# 갤러리 픽스처가 필요한 케이스 전용 래퍼다.
#   · 21_Card [24] 글로벌 QR 갤러리 업로드
#   · 06_Registration 신분증/ARC/여권 OCR
# 그 외에는 `Maestro\run_test.ps1` 을 직접 쓰면 된다.
#
# 사용법(인자는 Maestro\run_test.ps1 과 동일하다):
#   .\run_test.ps1 -lang ko -flow "Old\21_Card_old.yaml"
#   .\run_test.ps1 -lang en -flow "Old\06_Registration_old.yaml" -Build live
#
# ⛔ 2026-09-23 재작성 — 종전에는 이 파일이 러너 전체를 **복사해 갖고 있었다.**
#   그래서 `Maestro\run_test.ps1` 에만 들어간 개선(플로우가 실제로 쓰는 env 만 추리는 것)이
#   여기엔 없었고, env 가 475개로 늘자 **"The command line is too long."** 으로 죽었다.
#   두 벌을 두면 반드시 한쪽이 낡는다 → 이제 이미지 배치만 하고 본 러너로 넘긴다.
# ================================================================
param(
    [Parameter(Mandatory=$true)][string]$lang,
    [Parameter(Mandatory=$true)][string]$flow,
    [string]$device = "",
    [ValidateSet("stag","live")][string]$Build = "stag",
    [string]$AppId = "",
    [string[]]$ExtraEnv = @()
)

$ErrorActionPreference = 'Stop'
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$maestroDir  = Join-Path $scriptDir "Maestro"
$innerRunner = Join-Path $maestroDir "run_test.ps1"

if (-not (Test-Path $innerRunner)) {
    Write-Error "본 러너를 찾을 수 없습니다: $innerRunner"
    exit 1
}

# ── 기기 결정 ────────────────────────────────────────────────────
#   여기서 먼저 정하는 이유는 **이미지 push 에 시리얼이 필요해서**다.
#   ⛔ 시리얼을 하드코딩하지 말 것 — 기기는 교체된다.
if (-not $device) {
    $connected = @(adb devices | Select-String '^\S+\s+device$' | ForEach-Object { ($_ -split '\s+')[0] })
    if ($connected.Count -eq 0) {
        Write-Error "연결된 기기가 없습니다. USB 연결과 adb 인식(adb devices)을 확인하세요."
        exit 1
    }
    if ($connected.Count -gt 1) {
        Write-Error "기기가 여러 대 연결되어 있습니다: $($connected -join ', ')  ->  -device <시리얼>로 지정하세요."
        exit 1
    }
    $device = $connected[0]
}

# ================================================================
# 테스트 이미지 사전 배치
#   갤러리 1번째: Global QR.jpg          → 21_Card [24] 글로벌 QR 갤러리 업로드
#   갤러리 2번째: 3. ARC.jpg            → ARC OCR
#   갤러리 3번째: 1. ID Card_Korean.jpg → 주민등록증
#   갤러리 4번째: 2. Passport.jpg       → 여권
#   ⚠️ 케이스가 "테스트 이미지 4장이 갤러리 최신 4개"라는 전제에 기대므로 순서가 곧 index 다.
#      다른 이미지가 쌓이면 앱이 "OCR이 유효하지 않습니다"로 거부한다(앱 버그가 아니다).
# ================================================================
$testFilesDir = Join-Path $maestroDir "Test Files"
if (-not (Test-Path $testFilesDir)) {
    Write-Error "테스트 이미지 폴더를 찾을 수 없습니다: $testFilesDir"
    exit 1
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " 언어  : $lang"   -ForegroundColor Cyan
Write-Host " 플로우: $flow"    -ForegroundColor Cyan
Write-Host " 기기  : $device"  -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " 테스트 이미지 배치 중..." -ForegroundColor Yellow

# 갤러리는 최신순 정렬이라 push 직전에 타임스탬프를 벌려 둔다.
$now = Get-Date
(Get-Item "$testFilesDir\2. Passport.jpg").LastWriteTime       = $now.AddSeconds(-4)
(Get-Item "$testFilesDir\1. ID Card_Korean.jpg").LastWriteTime = $now.AddSeconds(-2)
(Get-Item "$testFilesDir\3. ARC.jpg").LastWriteTime            = $now
(Get-Item "$testFilesDir\Global QR.jpg").LastWriteTime         = $now.AddSeconds(2)

$pushes = @(
    @{ src = "Global QR.jpg";          dst = "/sdcard/DCIM/test_global_qr.jpg" }
    @{ src = "3. ARC.jpg";             dst = "/sdcard/DCIM/test_arc.jpg"       }
    @{ src = "2. Passport.jpg";        dst = "/sdcard/DCIM/test_passport.jpg"  }
    @{ src = "1. ID Card_Korean.jpg";  dst = "/sdcard/DCIM/test_id_card.jpg"   }
)
foreach ($p in $pushes) {
    adb -s $device push "$testFilesDir\$($p.src)" $p.dst | Out-Null
    adb -s $device shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://$($p.dst)" | Out-Null
    Start-Sleep -Milliseconds 800
}
Write-Host " 이미지 배치 완료 (1번째: Global QR / 2번째: ARC / 3번째: ID Card / 4번째: Passport)" -ForegroundColor Green
Write-Host ""

# ── 본 러너로 위임 ───────────────────────────────────────────────
#   env 추리기·빌드 전환·자동 로그아웃 선검사·스크린샷 회수는 전부 저쪽에 있다.
#   ⚠️ CWD 를 `Maestro\` 로 옮긴다 — `-flow` 가 그 기준의 상대경로이고,
#     `takeScreenshot` 도 CWD 에 떨어진다(본 러너가 실행 직후 회수한다).
$inner = @{ lang = $lang; flow = $flow; device = $device; Build = $Build }
if ($AppId)            { $inner.AppId    = $AppId }
if ($ExtraEnv.Count)   { $inner.ExtraEnv = $ExtraEnv }

Push-Location $maestroDir
try {
    & $innerRunner @inner
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
