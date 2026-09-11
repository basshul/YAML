# ================================================================
# run_test.ps1 — Maestro 다국어 테스트 실행 스크립트
#
# 사용법:
#   .\run_test.ps1                          # 한국어 기본 실행
#   .\run_test.ps1 -lang en                 # 영어로 실행
#   .\run_test.ps1 -lang ko -flow 09_Home.yaml
#   .\run_test.ps1 -lang en -flow 09_Home.yaml -device 27dbf1ec440d7ece
#
# -device를 생략하면 연결된 기기를 자동으로 감지합니다.
# (2026-08-06: 기존엔 기본값이 "R3CW90MTK9H"로 하드코딩돼 있었는데 기기가 교체되면서
#  아무것도 지정하지 않으면 항상 실패하는 상태였음 → 자동 감지로 변경)
# ================================================================
param(
    [string]$lang   = "ko",
    [string]$flow   = "09_Home.yaml",
    [string]$device = ""
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile   = Join-Path $scriptDir "Maestro\env\$lang.env"
$flowPath  = Join-Path $scriptDir "Maestro\$flow"

# 기기 자동 감지 (-device 미지정 시)
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

# 파일 존재 확인
if (-not (Test-Path $envFile)) {
    Write-Error "언어 파일을 찾을 수 없습니다: $envFile"
    Write-Host  "지원 언어: $(Get-ChildItem (Join-Path $scriptDir 'Maestro\env') -Filter '*.env' | ForEach-Object { $_.BaseName }) " -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $flowPath)) {
    Write-Error "플로우 파일을 찾을 수 없습니다: $flowPath"
    exit 1
}

# env 파일 파싱 → --env 인자 배열 생성
#
# ⚠️ 값은 반드시 큰따옴표로 감싼다(2026-08-18 수정).
#   maestro는 scoop 심(shims\maestro.cmd)이 `%*`로 넘기는 .bat이라 cmd.exe가 인자를 다시 파싱한다.
#   그래서 값에 `|`가 들어간 항목(예: SYS_PERMISSION_ALLOW=허용|Allow)이 파이프로 해석돼
#   "'Allow' is not recognized as an internal or external command"로 **모든 플로우가 즉시 죽었다**.
#   인용부호 안에 있으면 cmd가 리터럴로 취급한다. 아래 Legacy 인자 전달과 반드시 같이 써야 한다.
$envArgs = [System.Collections.Generic.List[string]]::new()
Get-Content $envFile -Encoding UTF8 | Where-Object {
    $_ -notmatch "^\s*#" -and $_ -match "="
} | ForEach-Object {
    $envArgs.Add("--env")
    $envArgs.Add('"' + $_.Trim() + '"')
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " 언어  : $lang"                         -ForegroundColor Cyan
Write-Host " 플로우: $flow"                          -ForegroundColor Cyan
Write-Host " 기기  : $device"                        -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ================================================================
# 테스트 이미지 사전 배치
# push 순서: 3→2→1 (ARC 먼저, ID Card 나중)
#   갤러리 1번째: Global QR.jpg          → 21_Card.yaml [24] 글로벌 QR 갤러리 업로드 케이스
#   갤러리 2번째: 3. ARC.jpg            → ARC OCR 케이스 (17%, 52%)
#   갤러리 3번째: 1. ID Card_Korean.jpg → 주민등록증 케이스 (50%, 52%)
#   갤러리 4번째: 2. Passport.jpg       → Passport 케이스 (83%, 52%)
# ================================================================
# 스크립트 기준 상대경로 (2026-08-06: 기존 "D:\Automation\Maestro\Test Files" 하드코딩에서 변경).
#   원본 4개는 Maestro\Test Files\ 로 복사해 두었음. 구 D: 경로는 폴백으로만 남겨둠.
$testFilesDir = Join-Path $scriptDir "Maestro\Test Files"
if (-not (Test-Path $testFilesDir)) {
    $legacyDir = "D:\Automation\Maestro\Test Files"
    if (Test-Path $legacyDir) {
        Write-Host " 테스트 이미지 폴더를 찾지 못해 구 경로를 사용합니다: $legacyDir" -ForegroundColor Yellow
        $testFilesDir = $legacyDir
    } else {
        Write-Error "테스트 이미지 폴더를 찾을 수 없습니다: $testFilesDir"
        exit 1
    }
}

Write-Host " 테스트 이미지 배치 중..." -ForegroundColor Yellow

# 갤러리 최신순 정렬 대응: push 직전 타임스탬프를 현재 시간으로 설정
$now = Get-Date
(Get-Item "$testFilesDir\2. Passport.jpg").LastWriteTime       = $now.AddSeconds(-4)
(Get-Item "$testFilesDir\1. ID Card_Korean.jpg").LastWriteTime = $now.AddSeconds(-2)
(Get-Item "$testFilesDir\3. ARC.jpg").LastWriteTime            = $now
(Get-Item "$testFilesDir\Global QR.jpg").LastWriteTime         = $now.AddSeconds(2)

adb -s $device push "$testFilesDir\Global QR.jpg" "/sdcard/DCIM/test_global_qr.jpg" | Out-Null
adb -s $device shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/DCIM/test_global_qr.jpg" | Out-Null
Start-Sleep -Milliseconds 800
adb -s $device push "$testFilesDir\3. ARC.jpg" "/sdcard/DCIM/test_arc.jpg" | Out-Null
adb -s $device shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/DCIM/test_arc.jpg" | Out-Null
Start-Sleep -Milliseconds 800
adb -s $device push "$testFilesDir\2. Passport.jpg" "/sdcard/DCIM/test_passport.jpg" | Out-Null
adb -s $device shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/DCIM/test_passport.jpg" | Out-Null
Start-Sleep -Milliseconds 800
adb -s $device push "$testFilesDir\1. ID Card_Korean.jpg" "/sdcard/DCIM/test_id_card.jpg" | Out-Null
adb -s $device shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/DCIM/test_id_card.jpg" | Out-Null
Start-Sleep -Milliseconds 800
Write-Host " 이미지 배치 완료 (갤러리 1번째: Global QR / 2번째: ARC / 3번째: ID Card / 4번째: Passport)" -ForegroundColor Green
Write-Host ""

$argsToPass = $envArgs.ToArray()

# 화면 켜기 (꺼진 상태로 실행 시 UI 인식 실패 방지)
adb -s $device shell input keyevent 224 | Out-Null

# PS7 기본 인자 전달은 위에서 붙인 큰따옴표를 이스케이프해버린다(\" 로 넘어감).
# Legacy로 두어야 따옴표가 그대로 cmd에 전달된다.
$runStart = Get-Date
$PSNativeCommandArgumentPassing = 'Legacy'

maestro --device $device test @argsToPass "`"$flowPath`""
$exitCode = $LASTEXITCODE

# ── 실행 후 스크린샷 회수 ────────────────────────────────────────────────
#   `takeScreenshot` 은 **CWD** 에 `<이름>.png` 로 떨어뜨린다(경로 지정 옵션이 없다).
#   그대로 두면 실행마다 루트에 쌓이고 **같은 이름은 조용히 덮인다**.
#   한 번 치우는 걸로는 끝나지 않는다 — 2026-09-02에 정리했는데 하루 만에 39개가 다시 쌓였고,
#   2026-09-10 정리에서는 191개(37MB)가 나왔다 → 실행 직후 **실행별 폴더**로 옮긴다.
#   ⚠️ 폴더명은 반드시 `shots_` 로 시작한다 — `.gitignore(shots_*/)` 와 `sync_from_source.ps1`
#      이 그 접두사로 걸러낸다. 다른 이름을 쓰면 산출물이 저장소에 딸려 들어간다.
#   ⚠️ maestro 의 종료 코드를 먼저 붙잡아 두고 마지막에 그대로 돌려준다 —
#      run_suite.ps1 이 `$LASTEXITCODE` 로 성패를 가른다.

$shotSrc = $scriptDir
$shotDst = (Join-Path $scriptDir "Maestro")
$shots = @(Get-ChildItem -LiteralPath $shotSrc -Filter "*.png" -File -ErrorAction SilentlyContinue |
           Where-Object { $_.LastWriteTime -ge $runStart })
if ($shots.Count) {
    $tag = [IO.Path]::GetFileNameWithoutExtension($flow) -replace '[^\w가-힣]', '_'
    $dir = Join-Path $shotDst ("shots_runs\{0}_{1}" -f $runStart.ToString("yyyyMMdd_HHmmss"), $tag)
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $shots | Move-Item -Destination $dir -Force
    Write-Host ("스크린샷 {0}장 → shots_runs\{1}" -f $shots.Count, (Split-Path -Leaf $dir)) -ForegroundColor DarkGray
}

exit $exitCode
