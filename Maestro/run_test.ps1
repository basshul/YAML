# run_test.ps1
# Usage:
#   .\run_test.ps1 -lang ko -flow 01_Login_screen.yaml
#   .\run_test.ps1 -lang en -flow 01_Login_screen.yaml
#   .\run_test.ps1 -lang ko -flow 01_Login_screen.yaml -device 27dbf1ec440d7ece
#   .\run_test.ps1 -lang ko -flow ... -Build live      # 운영(Live) 빌드로 돌릴 때만
#
# -device를 생략하면 연결된 기기를 자동 감지한다. 2대 이상 연결돼 있으면 실행을 거부한다.
#
# ★ 빌드 정책 (2026-09-03 사용자 선언)
#   기본       = `.stag` 빌드 + **서버는 LIVETEST 지정**  → `-Build stag` (기본값)
#   운영/Live  = `com.gmeremit.online.gmeremittance_native` → `-Build live` (요청이 있을 때만)
#   `.livetest` 빌드는 **더 이상 쓰지 않는다** — 기기에서 이미 삭제됐다(2026-09-03 adb 확인).

param(
    [Parameter(Mandatory=$true)][string]$lang,
    [Parameter(Mandatory=$true)][string]$flow,
    [string]$device = "",
    [ValidateSet("stag","live")][string]$Build = "stag",
    [string]$AppId = "",     # 임의 패키지 지정. 주면 -Build 보다 우선한다.
    # 자격정보처럼 파일에 적을 수 없는 값을 실행 시 넘긴다. KEY=VALUE 를 쉼표로.
    #   예) -ExtraEnv CVC_1=1,CVC_2=2,CVC_3=3   (21_Card [12] 의 카드 CVC)
    # env 파일에 있는 키와 겹치게 주지 말 것 — maestro 가 어느 쪽을 쓸지 보장되지 않는다.
    [string[]]$ExtraEnv = @()
)

# -Build → 패키지명. `-AppId`를 직접 준 경우에는 그쪽이 이긴다.
$BuildMap = @{
    stag = "com.gmeremit.online.gmeremittance_native.stag"
    live = "com.gmeremit.online.gmeremittance_native"
}
if (-not $AppId) { $AppId = $BuildMap[$Build] }

# 기기 자동 감지 (-device 미지정 시)
#
# 기기를 2대 이상 연결한 채로 실행하면 maestro가 어느 쪽을 잡을지 보장되지 않는다.
# 실계좌 송금·충전 플로우가 엉뚱한 기기에서 도는 사고를 막으려고 여기서 끊는다.
# (2026-08-20 추가: 상위 폴더 run_test.ps1과 동일한 가드. 기존엔 기기 처리가 아예 없어서
#  --device도 넘기지 않고 maestro 기본 선택에 맡기고 있었음)
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

# ----------------------------------------------------------------
# 자동 로그아웃 잠금 화면 선검사 (2026-09-15 신설)
#
# 유휴 ~10분이면 `autologout.AutoLogoutActivity` 가 뜬다 — "Enter password to unlock" +
# 보안 키패드(transkey) 화면이다. ★ 이 창은 **접근성 트리에 노출되지 않는다**:
# `uiautomator dump` 와 Maestro 둘 다 **직전 화면의 트리를 그대로 반환**한다.
#   → 플로우가 엉뚱한 화면으로 오진하고, 그 좌표의 탭·back 이 **보안 키패드 위에 떨어진다.**
#     (2026-09-15 실제로 04_02 진입부가 카드 화면으로 오진하고 키패드를 눌렀다)
# 자동화로는 풀 수 없는 화면이므로 **여기서 끊고** 사람이 복구 순서를 밟게 한다.
# ⚠️ 예외: `clearState: true` 플로우(`01_01_Login_Success_old` 등)는 앱 데이터를 지우고
#   로그인 화면부터 시작하므로 이 화면과 무관하다 → 막으면 **복구 수단 자체가 막힌다.**
$isClearState = (Test-Path $flow) -and
                (Select-String -LiteralPath $flow -Pattern 'clearState:\s*true' -Quiet)
$fg = (adb -s $device shell dumpsys activity activities 2>$null |
       Select-String 'topResumedActivity' | Select-Object -First 1).ToString()
if ((-not $isClearState) -and $fg -match 'autologout') {
    Write-Host ""
    Write-Host "  ⛔ 앱이 자동 로그아웃 잠금 화면(AutoLogoutActivity)에 있습니다." -ForegroundColor Red
    Write-Host "     이 화면은 접근성 트리에 안 잡혀 Maestro 가 인식하지 못하고," -ForegroundColor Red
    Write-Host "     엉뚱한 탭이 보안 키패드에 떨어집니다 → 실행을 중단합니다." -ForegroundColor Red
    Write-Host "     복구: .\run_test.ps1 -lang ko -flow `"Old\01_01_Login_Success_old.yaml`"" -ForegroundColor Yellow
    Write-Host "           (clearState 로 로그인 화면부터 복구한다. 앱 언어는 한국어로 돌아간다)" -ForegroundColor DarkGray
    exit 3
}

$envFile = "env\$lang.env"
if (-not (Test-Path $envFile)) {
    Write-Error "env file not found: $envFile"
    exit 1
}

# Parse env file: skip comments and blank lines
#
# 값은 반드시 KEY="VALUE" 형태로 인용해서 넘긴다.
#   maestro는 .bat 셰임을 거쳐 실행되므로 cmd가 인자를 한 번 더 파싱한다.
#   인용하지 않으면 값에 든 |, &, <, > 같은 문자가 셸 연산자로 해석돼 실행이 죽는다.
#   실제 사고: SYS_PERMISSION_ALLOW=허용|Allow 추가 후 모든 실행이 EXIT=255로 실패
#             ("'Allow' is not recognized as an internal or external command") — 2026-08-12
$envArgs = @()
function Add-EnvFile([string]$path) {
    Get-Content $path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#')) {
            $idx = $line.IndexOf('=')
            if ($idx -gt 0) {
                $key   = $line.Substring(0, $idx)
                $value = $line.Substring($idx + 1)
                $script:envArgs += "--env"
                $script:envArgs += ('{0}="{1}"' -f $key, $value)
            }
        }
    }
}
Add-EnvFile $envFile


# -AppId 로 빌드를 바꿀 때는 env 파일의 APP_ID 항목을 **교체**한다.
#   ⚠️ 뒤에 --env 를 하나 더 붙이는 방식은 maestro가 어느 쪽을 쓸지 보장되지 않으므로 쓰지 않는다.
if ($AppId) {
    $newArgs = @()
    for ($i = 0; $i -lt $envArgs.Count; $i += 2) {
        if ($envArgs[$i + 1] -like 'APP_ID=*') { continue }
        $newArgs += $envArgs[$i]; $newArgs += $envArgs[$i + 1]
    }
    $newArgs += "--env"; $newArgs += ('APP_ID="{0}"' -f $AppId)
    $envArgs = $newArgs
    Write-Host "APP_ID = $AppId" -ForegroundColor Yellow
}

# 운영(Live) 빌드는 **실서비스**다. 조용히 넘어가지 않게 한 번 크게 찍는다.
if ($AppId -eq $BuildMap.live) {
    Write-Host "[LIVE] 운영 빌드로 실행합니다 - 실서비스 계정/실자금입니다: $AppId" -ForegroundColor Red
} else {
    Write-Host "빌드: $AppId  (서버는 플로우가 LIVETEST로 강제한다)" -ForegroundColor DarkCyan
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runStart = Get-Date
# -ExtraEnv: env 파일 뒤에 덧붙인다(값 인용은 위와 같은 이유로 필수).
$extraKeys = @{}
foreach ($pair in $ExtraEnv) {
    if ($pair -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
        Write-Error "-ExtraEnv 형식이 잘못됐습니다: '$pair' -> KEY=VALUE 로 주세요."
        exit 1
    }
    $k = $Matches[1]; $v = $Matches[2]
    for ($i = 0; $i -lt $envArgs.Count; $i += 2) {
        if ($envArgs[$i + 1] -like "$k=*") {
            Write-Error "-ExtraEnv 의 $k 가 env 파일에도 있습니다. 한쪽만 두세요."
            exit 1
        }
    }
    $envArgs += "--env"; $envArgs += ('{0}="{1}"' -f $k, $v)
    $extraKeys[$k] = $true
}

# ── 그 플로우가 실제로 쓰는 변수만 넘긴다 ──────────────────────────
# ⚠️ 2026-09-14: 다국어 적용으로 env 키가 138 → 373개가 되자 `--env` 인자가
#   **Windows 명령행 한도(~8KB)를 넘겨 "The command line is too long." 으로 전 실행이 죽었다.**
#   maestro 2.5.1 에는 --env-file 이 없다 → 플로우가 참조하는 ${VAR} 만 추려 넘긴다.
#   `runFlow:` 로 부르는 헬퍼까지 **재귀로** 훑어야 한다(헬퍼가 쓰는 변수도 필요하다).
function Get-FlowVars([string]$path, [hashtable]$seen) {
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    $full = (Resolve-Path -LiteralPath $path).Path
    if ($seen.ContainsKey($full)) { return @() }
    $seen[$full] = $true
    $text = [System.IO.File]::ReadAllText($full)
    # ⚠️ `${VAR}` 만 잡으면 **JS 표현식 안의 변수를 놓친다**(2026-09-16 실측).
    #   `01_04` 의 인터록은 `assertTrue: ${typeof CONFIRM_LOCK !== 'undefined' && ...}` 형태라
    #   `CONFIRM_LOCK` 이 수집되지 않아 `-ExtraEnv` 로 넘겨도 필터에서 탈락했고,
    #   인터록이 영원히 닫힌 채 "동의했는데 실패" 로 보였다.
    #   → `${ ... }` **블록 내부의 식별자를 전부** 거둔다. env 에 없는 이름(typeof·undefined 등)은
    #     아래 필터에서 자연히 빠지므로 과잉 수집은 무해하다.
    $vars = @([regex]::Matches($text, '\$\{([^}]*)\}') | ForEach-Object {
        [regex]::Matches($_.Groups[1].Value, '[A-Za-z_][A-Za-z0-9_]*') | ForEach-Object { $_.Value }
    })
    $dir  = Split-Path -Parent $full
    foreach ($m in [regex]::Matches($text, '(?m)(?:runFlow:[ \t]*|file:[ \t]*)"?([^"
]+\.yaml)"?')) {
        $vars += Get-FlowVars (Join-Path $dir $m.Groups[1].Value.Trim()) $seen
    }
    return $vars
}
$needed = @{}
foreach ($v in (Get-FlowVars $flow (@{}))) { $needed[$v] = $true }
$needed["APP_ID"] = $true          # 헤더 appId 가 항상 쓴다
# -ExtraEnv 는 **사람이 그 실행에만 의도적으로 주입한 값**이다 → 수집 결과와 무관하게 항상 넘긴다.
foreach ($k in $extraKeys.Keys) { $needed[$k] = $true }
# ⚠️ `-gt 1` 이면 **플로우가 ${VAR} 를 하나도 안 쓸 때 필터가 통째로 꺼져** env 423개가
#   그대로 넘어가고 명령행 길이 한도에 걸린다(2026-09-18 실측: id 만 쓰는 임시 플로우).
#   `$needed` 에는 APP_ID 가 항상 들어가므로 조건 없이 늘 거른다.
if ($needed.Count -ge 1) {
    $filtered = @()
    for ($i = 0; $i -lt $envArgs.Count; $i += 2) {
        $k = ($envArgs[$i + 1] -split '=', 2)[0]
        if ($needed.ContainsKey($k)) { $filtered += $envArgs[$i]; $filtered += $envArgs[$i + 1] }
    }
    Write-Host ("env: {0}개 중 이 플로우가 쓰는 {1}개만 전달" -f ($envArgs.Count / 2), ($filtered.Count / 2)) -ForegroundColor DarkCyan
    $envArgs = $filtered
}

$cmd = @("maestro", "--device", $device, "test", $flow) + $envArgs
Write-Host "Running: $($cmd -join ' ')"
& maestro --device $device test $flow @envArgs
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

$shotSrc = $here
$shotDst = $here
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
