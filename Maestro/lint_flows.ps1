# ================================================================
# lint_flows.ps1 — Maestro 플로우 정적 검사기
#
#   .\lint_flows.ps1                      # Old\ 검사, 콘솔 + lint.md
#   .\lint_flows.ps1 -Path .              # 개편 UI(루트) 검사
#   .\lint_flows.ps1 -Level ERROR         # ERROR만 출력
#   .\lint_flows.ps1 -Json                # lint.json 도 생성
#   .\lint_flows.ps1 -WarnAsError         # WARN도 exit 1
#
# 왜 필요한가:
#   Maestro는 셀렉터가 틀려도 **조건 블록 안이면 에러 없이 SKIP하고 EXIT=0**을 준다.
#   이 검사기는 "실행으로는 원리적으로 안 잡히는 부류"만 겨냥한다.
#   좌표 오차·타이밍·앱 결함은 실행만이 잡는다 — 여기서 통과했다고 플로우가 맞다는 뜻이 아니다.
#
# 설정: lint_labels.json  (실측으로 확인된 값만 넣는다. 추측 금지)
# 예외: lint_whitelist.txt  ("RULE 파일명:줄" 또는 "RULE 파일명")
# exit: ERROR 1건 이상 = 1, 그 외 0 (화이트리스트 적용 후)
# ================================================================
param(
    [string]$Path       = "Old",
    [string[]]$Exclude  = @("_tmp_*"),
    [string]$Config     = "lint_labels.json",
    [string]$Whitelist  = "lint_whitelist.txt",
    [ValidateSet("ERROR","WARN","ALL")][string]$Level = "ALL",
    # 어느 UI 트랙인가. v2(구 UI)에서만 개편UI 전용 셀렉터 검사(E06)를 켠다.
    # auto = 경로에 'Old'가 들어가면 v2. 픽스처처럼 경로로 추론할 수 없을 때 명시한다.
    [ValidateSet("auto","v2","v3")][string]$Track = "auto",
    [switch]$Json,
    [switch]$WarnAsError,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$utf8 = [System.Text.UTF8Encoding]::new($false)

function Read-Lines([string]$p) { [System.IO.File]::ReadAllLines($p, $utf8) }
function Write-Utf8([string]$p, [string]$t) { [System.IO.File]::WriteAllText($p, $t, $utf8) }

# ----------------------------------------------------------------
# 설정 로드
# ----------------------------------------------------------------
$cfgPath = Join-Path $root $Config
if (-not (Test-Path $cfgPath)) { Write-Error "설정 파일이 없습니다: $cfgPath"; exit 2 }
$cfg = ((Read-Lines $cfgPath) -join "`n") | ConvertFrom-Json

$wlPath = Join-Path $root $Whitelist
$wl = @{}
if (Test-Path $wlPath) {
    foreach ($l in (Read-Lines $wlPath)) {
        $t = $l.Trim()
        if (-not $t -or $t.StartsWith("#")) { continue }
        $wl[$t] = $true
    }
}
function Test-Whitelisted($rule, $file, $line) {
    return ($wl.ContainsKey(($rule + " " + $file + ":" + $line)) -or $wl.ContainsKey(($rule + " " + $file)))
}

# ----------------------------------------------------------------
# 주석 제거 — 이 검사기의 정확도는 대부분 여기서 결정된다.
#   yaml에서 '#'은 **줄 시작이거나 공백 뒤**일 때만 주석이고, 인용부호 안에서는 주석이 아니다.
#   순진하게 '#' 이후를 자르면  id: "a#b"  가 깨지고,
#   순진하게 안 자르면 "범용 tapOn: \"닫기\" 를 걷어냈다" 같은 **주석이 결함으로 잡힌다**.
#   (실제로 grep으로 훑었을 때 히트 20건 중 12건이 주석이었다.)
# ----------------------------------------------------------------
function Remove-YamlComment([string]$line) {
    $sq = $false; $dq = $false
    for ($i = 0; $i -lt $line.Length; $i++) {
        $ch = $line[$i]
        if ($ch -eq "'" -and -not $dq) { $sq = -not $sq; continue }
        if ($ch -eq '"' -and -not $sq) {
            if ($dq -and $i -gt 0 -and $line[$i-1] -eq '\') { continue }   # \" 는 닫는 인용이 아니다
            $dq = -not $dq; continue
        }
        if ($ch -eq '#' -and -not $sq -and -not $dq) {
            if ($i -eq 0 -or $line[$i-1] -match '\s') { return $line.Substring(0, $i) }
        }
    }
    return $line
}

# ----------------------------------------------------------------
# 대상 파일
# ----------------------------------------------------------------
$scanDir = Join-Path $root $Path
if (-not (Test-Path $scanDir)) { Write-Error "경로가 없습니다: $scanDir"; exit 2 }
$files = Get-ChildItem -Path $scanDir -Filter "*.yaml" -File | Where-Object {
    $n = $_.Name
    -not ($Exclude | Where-Object { $n -like $_ })
} | Sort-Object Name
if ($files.Count -eq 0) { Write-Error "검사할 yaml이 없습니다: $scanDir"; exit 2 }

# env 값 사전 — ${VAR} 를 **원문으로 되돌린 확장본**을 만들기 위해 필요하다.
#   ⚠️ 2026-09-14: 다국어 적용으로 문구가 ${VAR} 로 바뀌자 **한국어 문구로 판정하던 규칙이
#      조용히 무력화**됐다(W08 PIN 가드가 24건 오탐, W10 은행명 탭도 매칭 불가).
#      규칙은 확장본(Expanded)으로 보게 해서 변수화 전/후가 같게 판정한다.
$envValues = @{}
$envDirPre = Join-Path $root "env"
if (Test-Path $envDirPre) {
    # ⚠️ ko.env 를 **나중에** 읽어 덮어쓴다. 알파벳 순으로 돌리면 en.env 가 먼저라
    #   한국어 문구 판정 규칙이 영문 값으로 확장돼 오탐이 난다(2026-09-14 실측 11건).
    $envFilesPre = @(Get-ChildItem $envDirPre -Filter "*.env" -File | Sort-Object { $_.Name -eq "ko.env" })
    foreach ($ef in $envFilesPre) {
        foreach ($l in (Read-Lines $ef.FullName)) {
            if ($l -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
                $envValues[$Matches[1]] = $Matches[2]      # 뒤에 읽은 ko.env 가 이긴다
            }
        }
    }
}
function Expand-EnvVars([string]$line) {
    if ($line -notmatch '\$\{') { return $line }
    return [regex]::Replace($line, '\$\{([A-Za-z_][A-Za-z0-9_]*)\}', {
        param($m)
        $k = $m.Groups[1].Value
        if ($envValues.ContainsKey($k)) { return $envValues[$k] } else { return $m.Value }
    })
}

$docs = @{}
foreach ($f in $files) {
    $raw  = Read-Lines $f.FullName
    $code = @($raw | ForEach-Object { Remove-YamlComment $_ })
    $exp  = @($code | ForEach-Object { Expand-EnvVars $_ })
    $docs[$f.Name] = @{ Raw = $raw; Code = $code; Expanded = $exp }
}

$findings = New-Object System.Collections.Generic.List[object]
function Add-Finding($rule, $level, $file, $line, $msg) {
    if (Test-Whitelisted $rule $file $line) { return }
    $findings.Add([pscustomobject]@{ Rule=$rule; Level=$level; File=$file; Line=$line; Msg=$msg })
}

# ================================================================
# 전역 수집 — 여러 파일을 함께 봐야 하는 규칙용
# ================================================================
# ① 정의된 env 키: env\*.env + 모든 yaml의 env: 블록(flow 레벨 / runFlow 파라미터)
$definedVars = New-Object System.Collections.Generic.HashSet[string]
foreach ($v in $cfg.injectedEnvVars) { [void]$definedVars.Add($v) }
$envDir = Join-Path $root "env"
if (Test-Path $envDir) {
    foreach ($ef in (Get-ChildItem $envDir -Filter "*.env" -File)) {
        foreach ($l in (Read-Lines $ef.FullName)) {
            if ($l -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') { [void]$definedVars.Add($Matches[1]) }
        }
    }
}
#   ⚠️ 헬퍼는 다른 폴더의 플로우가 runFlow의 env: 로 값을 넘겨줄 수 있다 →
#      -Path 와 무관하게 **루트와 Old 를 모두** 훑어야 "정의되지 않음" 판정이 정확해진다.
$envScanFiles = @()
foreach ($d in @($root, (Join-Path $root "Old"))) {
    if (Test-Path $d) { $envScanFiles += Get-ChildItem $d -Filter "*.yaml" -File }
}
#   ⚠️ CLI `--env` 로 주입하는 변수는 **일부러 flow env: 에 두지 않는다** —
#      두면 `--env` 로 넘긴 값이 무시되기 때문이다. 대신 잘 짠 플로우는
#      `assertTrue: ${typeof VAR !== 'undefined' && …}` 로 **주입 여부를 스스로 검증**한다.
#      그 계약이 있으면 "정의되지 않음"이 아니다 → 여기서 declared 로 인정한다.
#      (2026-09-02 `01_04_Login_Wrong_LoginPassword_old.yaml` 이 이 패턴이라 오탐이 났다)
foreach ($ef in $envScanFiles) {
    $codeAll = ((Read-Lines $ef.FullName) -join "`n")
    foreach ($m in [regex]::Matches($codeAll, 'typeof\s+([A-Za-z_][A-Za-z0-9_]*)')) {
        [void]$definedVars.Add($m.Groups[1].Value)
    }
    $code = @((Read-Lines $ef.FullName) | ForEach-Object { Remove-YamlComment $_ })
    $inEnv = $false; $envIndent = -1
    for ($i = 0; $i -lt $code.Count; $i++) {
        $l = $code[$i]
        if ($l -match '^(\s*)env:\s*$') { $inEnv = $true; $envIndent = $Matches[1].Length; continue }
        if ($inEnv) {
            if ($l -match '^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:' -and $Matches[1].Length -gt $envIndent) {
                [void]$definedVars.Add($Matches[2])
            } elseif ($l.Trim()) { $inEnv = $false }
        }
    }
}

# ② 한 번이라도 **긍정 검증**된 문자열 전체 집합 (W02용)
$positiveTexts = New-Object System.Collections.Generic.HashSet[string]
foreach ($name in $docs.Keys) {
    $lines = $docs[$name].Code
    for ($k = 0; $k -lt $lines.Count; $k++) {
        $l = $lines[$k]
        if ($l -match 'assertNotVisible|notVisible') { continue }
        # ⚠️ **여러 줄 형식을 놓치면 오탐이 난다**(2026-09-03).
        #   `extendedWaitUntil:` / `visible:` / `text: "..."` 처럼 3줄로 쪼개 쓰면 값이 있는 줄에는
        #   키워드가 없어서 긍정 집합에 안 들어갔고, `20_Booking`의 `SELECT DATE`가
        #   "짝 없는 assertNotVisible"로 잘못 지적됐다(위에서 분명히 긍정 검증하고 있었다).
        #   → 값만 있는 `text:`/`id:` 줄도 받되, **앞 3줄에 부정 마커가 있으면 제외**한다.
        $isKeywordLine = $l -match '(assertVisible|extendedWaitUntil|tapOn|visible|longPressOn|scrollUntilVisible|inputText)'
        $isValueLine   = $l -match '^\s*(text|id)\s*:'
        if ($isValueLine -and -not $isKeywordLine) {
            $from = [Math]::Max(0, $k - 3)
            $ctx  = ($lines[$from..$k] -join "`n")
            if ($ctx -match 'assertNotVisible|notVisible') { continue }
        }
        if ($isKeywordLine -or $isValueLine) {
            foreach ($m in [regex]::Matches($l, '"([^"]{2,})"')) { [void]$positiveTexts.Add($m.Groups[1].Value) }
            foreach ($m in [regex]::Matches($l, "'([^']{2,})'"))  { [void]$positiveTexts.Add($m.Groups[1].Value) }
        }
    }
}

# ================================================================
# 규칙
# ================================================================
$validEsc = @('0','a','b','t','n','v','f','r','e','"','\','N','_','L','P','/','x','u','U',' ')
$isV2 = if ($Track -eq "auto") { $Path -match 'Old' } else { $Track -eq "v2" }

# ----------------------------------------------------------------
# 앞뒤 **비어있지 않은 코드줄** 창 — 해상도 규칙(W11~W13)이 쓴다.
#   ⚠️ "직전 N줄"로 잡으면 안 된다. 이 저장소의 yaml은 함정 하나당 주석이 4~5줄이라
#      창이 통째로 주석에 먹힌다 — 초안이 정상 코드 9곳을 전부 오탐으로 냈다(2026-09-10).
#      주석은 이미 빈 줄로 치환돼 있으므로 **빈 줄을 건너뛰며** 센다.
# ----------------------------------------------------------------
function Get-BackWindow($code, $i, $n) {
    $w = @(); $j = $i - 1
    while ($j -ge 0 -and $w.Count -lt $n) {
        if ($code[$j].Trim()) { $w += $code[$j] }
        $j--
    }
    return ($w -join "`n")
}
function Get-FwdWindow($code, $raw, $i, $n) {
    # 다음 케이스 헤더(`# [NN]`)에서 멈춘다 — **다른 케이스의 assert**를 이 탭의 검증으로 오인하지 않기 위해.
    $w = @(); $j = $i + 1
    while ($j -lt $code.Count -and $w.Count -lt $n) {
        if ($raw[$j] -match '^\s*#\s*\[\d+\]') { break }
        if ($code[$j].Trim()) { $w += $code[$j] }
        $j++
    }
    return ($w -join "`n")
}

foreach ($f in $files) {
    $name = $f.Name
    $raw  = $docs[$name].Raw
    $code = $docs[$name].Code
    $codeX = $docs[$name].Expanded   # ${VAR} 를 원문으로 되돌린 것(문구 판정용)

    $lastSecureMarker = -999      # W03
    $stmt = 0                     # 비어있지 않은 코드줄 순번
    $prevDigitStmt = -999         # W08
    $runStart = 0; $runLen = 0    # W08 (숫자 탭 런)
    $lastAcctList = -999          # W10
    $fixtureSeen = @{}            # W06

    for ($i = 0; $i -lt $code.Count; $i++) {
        $ln = $i + 1
        $c  = $code[$i]
        $r  = $raw[$i]
        # ---- W04b 주석에 노출된 자격정보 — 코드줄 판정보다 **먼저** 본다 ----
        #   실제로 "로그인 실패(비밀번호 Xxxxx! 만료) 시 → Yyy! 로 재시도" 같은 주석이 여러 파일에 있다.
        #   값을 설정 파일에 적을 수 없으므로(그 자체가 유출이다) **문맥 + 형태**로 판정한다.
        #   ⚠️ 지적 메시지에 값을 절대 출력하지 않는다.
        #   ⚠️ 특수문자 집합에서 `*`와 `^`는 뺐다 — 주석의 마크다운 강조(`**SKIP**`)가
        #      "SKIP" + "*" 로 자격정보처럼 잡히는 오탐이 났다(2026-09-01).
        if ($r -match '비밀번호|password|PIN' -and $r -match '[A-Za-z][A-Za-z0-9]{2,}[!@#\$%&]') {
            Add-Finding "W04_CREDENTIAL" "WARN" $name $ln `
                "자격정보로 보이는 값이 노출돼 있다(주석 포함). 코드를 공유하면 그대로 나간다 → 값을 지우고 보관처만 가리킬 것 (값은 리포트에 출력하지 않는다)"
        }

        # ---- W05 하드코딩 시리얼 — 주석도 대상이므로 코드줄 판정보다 **먼저** 본다 ----
        #   ⚠️ 시리얼 **형식**으로만 잡으면 놓친다. 16자리 소문자 hex만 보다가
        #      `R3CW90MTK9H`(대문자 영숫자)를 놓쳤다(2026-09-02) → `-device <값>` 형태도 함께 잡는다.
        #      단 `-device 필수` 같은 산문에 걸리지 않게 **시리얼 모양**(영숫자 6자 이상)을 요구한다.
        if ($r -match '\b[0-9a-f]{16}\b' -or $r -match '--?device\s+[A-Za-z0-9_-]{6,}') {
            Add-Finding "W05_HARDCODED_SERIAL" "WARN" $name $ln `
                "기기 시리얼로 보이는 값이 있다(주석 포함). 기기는 교체된다 → adb devices 자동 감지에 맡길 것"
        }

        if (-not $c.Trim()) { continue }
        $stmt++

        # ---- E01 id에 패키지명 하드코딩 ----
        if ($c -match ':id/') {
            Add-Finding "E01_PKG_ID" "ERROR" $name $ln `
                "id에 패키지명이 박혀 있다 → stag 빌드에서 절대 매칭되지 않고, 조건부 블록이면 에러 없이 SKIP된다. 짧은 id만 쓸 것"
        }

        # ---- E09 pressKey 값이 Maestro가 아는 키가 아님 ----
        #   ⚠️ **유효하지 않은 값이면 Maestro가 `Parsing Failed`로 파일을 통째로 거부**한다.
        #     케이스 하나가 아니라 **플로우 전체가 실행되지 않는다** — 2026-09-03에
        #     `02_02_Overseas_Schedule_old.yaml`의 `pressKey: back`이 한글 IME 오타로 오염돼
        #     `backdhwjs`가 돼 있었고, 그 상태로 저장소 9/1 커밋본까지 들어가 있었다.
        #     스위트에서 COMPLETED 0으로 죽고 나서야 알았다 → 정적으로 잡는다.
        if ($c -match '^\s*-?\s*pressKey\s*:\s*"?([^"#]+?)"?\s*$') {
            $key = $Matches[1].Trim()
            $validKeys = @("back","enter","home","lock","volume up","volume down","backspace",
                           "power","tab","remote dpad up","remote dpad down","remote dpad left",
                           "remote dpad right","remote dpad center","remote media play pause",
                           "remote media stop","remote media next","remote media previous",
                           "remote media rewind","remote system navigation up",
                           "remote system navigation down","remote button a","remote button b")
            if ($validKeys -notcontains $key.ToLower()) {
                Add-Finding "E09_BAD_PRESSKEY" "ERROR" $name $ln `
                    ("pressKey 값 '" + $key + "' 은 Maestro가 아는 키가 아니다 → **파일 전체가 `Parsing Failed`로 거부되고 한 케이스도 실행되지 않는다.** back/enter/home/lock/backspace/tab/volume up|down 등만 쓸 것")
            }
        }

        # ---- E07 플로우 도중 launchApp 에 빌드 하드코딩 ----
        #   헤더 `appId:` 하드코딩과 성격이 다르다. 헤더는 전용 빌드 파일에선 의도적일 수 있지만,
        #   본문 launchApp 하드코딩은 -AppId 로 지정한 빌드를 **도중에 갈아버린다**.
        if ($c -match '^\s*-?\s*launchApp\s*:.*com\.gmeremit\.online') {
            Add-Finding "E07_LAUNCH_APPID" "ERROR" $name $ln `
                '플로우 도중 launchApp이 특정 빌드를 하드코딩한다 → -AppId로 stag를 지정해도 이 줄에서 다른 빌드가 실행된다. ${APP_ID} 를 쓸 것'
        }
        # ---- W09 헤더 appId 하드코딩 ----
        if ($c -match '^\s*appId\s*:.*com\.gmeremit\.online') {
            Add-Finding "W09_HEADER_APPID" "WARN" $name $ln `
                '헤더 appId가 하드코딩돼 있어 -AppId 로 빌드를 바꿀 수 없다. 전용 빌드 파일이면 의도된 것일 수 있다 → 그렇다면 화이트리스트에 넣을 것'
        }

        # ---- E02 이중인용 안의 잘못된 백슬래시 ----
        foreach ($m in [regex]::Matches($c, '"((?:[^"\\]|\\.)*)"')) {
            $s = $m.Groups[1].Value
            for ($k = 0; $k -lt $s.Length - 1; $k++) {
                if ($s[$k] -eq '\') {
                    $nx = [string]$s[$k+1]
                    if ($validEsc -notcontains $nx) {
                        Add-Finding "E02_YAML_ESCAPE" "ERROR" $name $ln `
                            ("이중인용 안의 \" + $nx + " 는 유효한 YAML 이스케이프가 아니다 → Parsing Failed로 파일이 통째로 죽는다. 백슬래시를 2겹으로 쓰거나 단일인용을 쓸 것")
                        break
                    }
                    $k++
                }
            }
        }

        # ---- W08 PIN 숫자 탭 **시작 전**에 화면 도달 대기가 없음 ----
        #
        #   ⚠️ 이 규칙은 원래 "탭 **사이**에 waitForAnimationToEnd가 없다"를 잡았다.
        #      2026-09-01 실기기 실측으로 그 전제가 **반증됐다** → 지금 형태로 다시 썼다.
        #
        #   실측(구 UI `ActivityLockScreen`, 2026-09-01):
        #   ① 키패드는 셔플되지만 **화면 진입 시**다. **탭마다가 아니다** —
        #      한 자리를 눌러 dot이 채워진 뒤에도 배열이 `2 8 7 / 1 5 4 / 9 6 0` 그대로였다.
        #      (별도로 `content-desc="재배열"` 버튼이 있다 = 재배열은 명시적 동작이다.)
        #   ② **대기 없는 연타 3회가 3/3 정확히 입력됐다.** 탭 사이 대기는 불필요하다.
        #   ③ 숫자는 `content-desc`로 노출된다(0~9). dot은 `input_dot_1`~`4`.
        #
        #   그래서 진짜 위험은 **첫 탭 전**이다. 화면 도달을 기다리지 않고 바로 숫자를 누르면
        #   PIN 화면이 아직 안 떴을 수 있고, 그때 같은 글자가 **다른 요소에 있으면 그걸 누른다.**
        #   실례: `03_Domestic`은 금액으로 "2"를 넣은 직후 대기 없이 `tapOn: "2"`로 PIN을 시작한다.
        #
        #   오탐 제외: 보안 키패드의 신분증번호 입력(`입력완료`로 끝남)은 다른 물건이다.
        if ($c -match '^\s*-?\s*tapOn:\s*"[0-9]"\s*$') {
            if ($stmt - $prevDigitStmt -ne 1) { $runStart = $ln; $runStartIdx = $i; $runLen = 0 }
            $runLen++
            $prevDigitStmt = $stmt
        } else {
            if ($runLen -ge 2) {
                # 보안 키보드(로그인 비밀번호)는 숫자·문자·특수문자를 섞어 누르고 `입력완료`로 끝난다.
                #   그 사이에 `특수문자변경`·`느낌표` 같은 탭이 끼어 `입력완료`가 멀어지므로 창을 넓게 본다.
                $tailTo = [Math]::Min($code.Count - 1, $i + 8)
                $tail   = ($codeX[$i..$tailTo] -join "`n")
                # 런 시작 앞 12줄에 PIN 화면 도달 판정이 있는가
                #   (`when: visible: ".*간편 비밀번호를 생성.*"` 같은 가드도 도달 판정으로 친다)
                $gFrom = [Math]::Max(0, $runStartIdx - 12)
                $guard = ($codeX[$gFrom..([Math]::Max(0, $runStartIdx - 1))] -join "`n")
                $hasWait = $guard -match 'input_dot_1|keypadContainer|4자리 숫자를 입력하세요|간편 비밀번호를 입력하세요|간편 비밀번호를 생성|간편 비밀번호를 다시 입력'
                if ($tail -notmatch '입력완료' -and -not $hasWait) {
                    Add-Finding "W08_PIN_NO_SCREEN_WAIT" "WARN" $name $runStart `
                        ("PIN 숫자 " + $runLen + "연타(" + $runStart + "~" + ($ln - 1) + "행) 앞에 **PIN 화면 도달 판정이 없다**. 화면이 아직 안 떴는데 누르면 같은 글자를 가진 다른 요소를 집는다 → 런 앞에 `input_dot_1`(또는 keypadContainer) 대기를 둘 것. ※ 탭 사이 대기는 불필요하다 — 키패드는 화면 진입 시에만 재배열된다(2026-09-01 실측)")
                }
            }
            $runLen = 0
            if ($c -notmatch 'waitForAnimationToEnd') { $prevDigitStmt = -999 }
        }

        # ---- E04 정의되지 않은 ${VAR} ----
        foreach ($m in [regex]::Matches($c, '\$\{([A-Za-z_][A-Za-z0-9_]*)\}')) {
            $v = $m.Groups[1].Value
            if (-not $definedVars.Contains($v)) {
                Add-Finding "E04_ENV_UNDEFINED" "ERROR" $name $ln `
                    ('${' + $v + '} 가 env\*.env 에도, 어떤 flow의 env: 블록에도 없다 → 치환되지 않은 리터럴로 남아 조용히 SKIP된다')
            }
        }

        # ---- E05 실측과 다른 라벨 ----
        #   ⚠️ `|` 가 든 문자열은 **구/개편 UI를 함께 받는 의도적 대안 매칭**이다(Maestro text는 정규식).
        #      예: "Server Override|4자리 숫자를 입력하세요|홈으로" → 오탐이므로 제외한다.
        $inAlternation = $false
        foreach ($m in [regex]::Matches($c, '"([^"]+)"')) { if ($m.Groups[1].Value -match '\|') { $inAlternation = $true } }

        if (-not $inAlternation) {
            foreach ($w in $cfg.wrongLabels) {
                $q = [regex]::Escape($w.bad)
                if ($c -match ('"' + $q + '"') -or $c -match ("'" + $q + "'")) {
                    $lvl = if ($w.level) { $w.level } else { "ERROR" }
                    Add-Finding "E05_WRONG_LABEL" $lvl $name $ln `
                        ('실측 문구와 다르다: "' + $w.bad + '" → "' + $w.good + '"  (' + $w.why + ')')
                }
            }
            foreach ($w in $cfg.wrongTapLabels) {
                $q = [regex]::Escape($w.bad)
                if ($c -match 'tapOn' -and $c -match ('"' + $q + '"')) {
                    $lvl = if ($w.level) { $w.level } else { "WARN" }
                    Add-Finding "E05_WRONG_LABEL" $lvl $name $ln `
                        ('실측 문구와 다를 수 있다: "' + $w.bad + '" → "' + $w.good + '"  (' + $w.why + ')')
                }
            }

            # ---- E06 개편 UI 전용 셀렉터가 구 UI 파일에 있음 ----
            if ($isV2) {
                foreach ($v in $cfg.v3OnlySelectors) {
                    if ($c -match $v.pat) {
                        Add-Finding "E06_V3_SELECTOR" "ERROR" $name $ln ("개편 UI 전용 셀렉터다. " + $v.why)
                    }
                }
            }
        }

        # ---- W01 범용 라벨의 **맹목적 팝업 닫기** ----
        #   CLAUDE.md가 금지하는 건 모든 "닫기" 탭이 아니라 **`visible: "닫기"` → `tapOn: "닫기"` 짝**이다.
        #   그 짝은 "무엇이 떠 있는지 모른 채 아무 X나 누른다"라서 런처 이탈 사고를 냈다.
        #   반대로 [X]를 의도적으로 누르고 **바로 결과를 단언하는** 스텝은 안전하다(26_Menu의 PIN 재설정 취소) →
        #   그래서 **자기참조 가드가 있을 때만** 잡는다.
        #   또 가드에 `notVisible: <목적 화면>` 이 함께 걸려 있으면 "아직 도달 못 했을 때만" 누르는 것이므로 제외한다.
        if ($c -match '^\s*-?\s*tapOn:\s*"?([^"]+)"?\s*$') {
            $t = $Matches[1].Trim('"').Trim()
            if ($cfg.genericLabels -contains $t) {
                $from  = [Math]::Max(0, $i - 6)
                $guard = ($code[$from..($i-1)] -join "`n")
                $selfGuarded = $guard -match ('visible:\s*"?' + [regex]::Escape($t))
                $narrowed    = $guard -match 'notVisible'
                if ($selfGuarded -and -not $narrowed) {
                    Add-Finding "W01_GENERIC_LABEL" "WARN" $name $ln `
                        ('`visible: "' + $t + '" → tapOn: "' + $t + '"` 맹목적 팝업 닫기다. 무엇이 떠 있는지 모른 채 아무 X나 누르므로 엉뚱한 X를 눌러 앱이 런처로 빠져나간 사고 이력이 있다 → id로 특정하거나(인앱 배너는 btnTwo|btnClose), 최소한 `notVisible: <목적 화면 id>`로 가드를 좁힐 것')
                }
            }
        }

        # ---- W02 아무것도 검증하지 못하는 assertNotVisible ----
        if ($c -match 'assertNotVisible') {
            foreach ($m in [regex]::Matches($c, '"([^"]{2,})"')) {
                $s = $m.Groups[1].Value
                if ($s -match '^\$\{' -or $s -match '[\\\[\]\*\|]') { continue }   # 변수·정규식은 대상 아님
                if (-not $positiveTexts.Contains($s)) {
                    Add-Finding "W02_NOTVISIBLE_UNPAIRED" "WARN" $name $ln `
                        ('"' + $s + '" 가 어떤 파일에서도 긍정 검증(assertVisible 등)된 적이 없다 → 오타여도 통과한다. 같은 화면에서 실제 라벨을 한 번은 assertVisible로 확인할 것')
                }
            }
        }

        # ---- W03 캡처 차단 화면 근처의 takeScreenshot ----
        foreach ($mk in $cfg.captureBlockedMarkers) {
            if ($c -match [regex]::Escape($mk)) { $lastSecureMarker = $ln }
        }
        # back을 누르면 그 화면을 벗어난다 → 마커를 무효화한다.
        # (이걸 안 하면 "카메라에서 back으로 빠져나온 뒤의 스크린샷"이 오탐으로 잡힌다 — 실제 4건)
        if ($c -match 'pressKey:\s*back|launchApp') { $lastSecureMarker = -999 }
        if ($c -match 'takeScreenshot' -and $ln -gt $lastSecureMarker -and ($ln - $lastSecureMarker) -le 15) {
            Add-Finding "W03_SHOT_IN_SECURE" "WARN" $name $ln `
                ("캡처 차단 화면 마커(" + $lastSecureMarker + "행) 근처의 takeScreenshot이다. FLAG_SECURE 화면에서 이 패턴이 플로우를 4회 죽였다 → assert로 대체")
        }

        # ---- W04 자격정보 리터럴 (값은 출력하지 않는다) ----
        if ($c -match '^\s*-?\s*(inputText|tapOn)\s*:\s*"[^"]+"') {
            foreach ($m in [regex]::Matches($c, '"([^"]+)"')) {
                if ($m.Groups[1].Value -match '^[A-Za-z][A-Za-z0-9]{4,}[!@#\$%\^&\*]$') {
                    Add-Finding "W04_CREDENTIAL" "WARN" $name $ln `
                        "비밀번호로 보이는 리터럴이 플로우에 박혀 있다. 값이 바뀌면 전 파일을 손으로 훑어야 한다 → flow 레벨 env: 로 뺄 것 (값은 리포트에 출력하지 않는다)"
                    break
                }
            }
        }

        # ---- W10 연동 계좌 목록에서 은행명 하드코딩 + 전제 단언 없음 ----
        #   목록 내용은 **계정 상태에 따라 바뀐다**(`케이뱅크` 소멸 실측 2026-08-28 → 08_MyQR [02] 정지).
        #   하드코딩 자체가 항상 틀린 건 아니다(실송금 조합처럼 특정 계좌가 케이스의 일부인 경우가 있다).
        #   문제는 **전제 단언이 없을 때** — 목록이 바뀌면 tapOn이 Element not found로 죽어
        #   셀렉터 버그처럼 오진하게 된다. 그래서 "assert 없는 tapOn"만 잡는다.
        foreach ($mk in $cfg.accountListMarkers) {
            if ($c -match [regex]::Escape($mk)) { $lastAcctList = $ln }
        }
        if ($lastAcctList -gt 0 -and ($ln - $lastAcctList) -le 15 -and $ln -gt $lastAcctList) {
            if ($codeX[$i] -match '^\s*-?\s*tapOn:\s*"([^"]*(은행|뱅크))"\s*$') {
                $bank = $Matches[1]
                $from = [Math]::Max(0, $i - 6)
                $win  = ($codeX[$from..($i-1)] -join "`n")
                if ($win -notmatch ('assertVisible[^\r\n]*' + [regex]::Escape($bank))) {
                    Add-Finding "W10_ACCT_HARDCODED" "WARN" $name $ln `
                        ('연동 계좌 목록(' + $lastAcctList + '행)에서 "' + $bank + '"을 전제 단언 없이 탭한다. 목록은 계정 상태에 따라 바뀐다 → 앞에 assertVisible을 두거나(특정 계좌가 케이스의 일부일 때), 목록에서 골라 쓸 것(어느 계좌든 무관할 때)')
                }
            }
        }

        # ================================================================
        # 기기·해상도가 바뀌면 깨지는 부류 (W11~W13)
        #   2026-09-09 테스트 기기 교체(1080x2220 → SM-S911N 1080x2340) 때 실제로 터진 것만 넣었다.
        #   셋 다 **실행으로는 안 잡히거나 늦게 잡힌다**: 좌표는 조용히 빗나가고,
        #   index는 조용히 다른 행을 집으며, hideKeyboard는 조용히 화면을 벗어난다.
        # ================================================================

        # ---- W11 좌표 탭인데 결과 단언이 없다 ----
        #   좌표는 해상도가 바뀌면 **에러 없이** 다른 곳을 누르거나 아무것도 안 누른다.
        #   `21_Card [19]`의 토글이 정확히 이 모양이라 안 눌려도 EXIT=0 이 된다.
        if ($c -match '^\s*point\s*:') {
            $fw = Get-FwdWindow $code $raw $i 12
            if ($fw -notmatch 'assertVisible|assertNotVisible|assertTrue|extendedWaitUntil') {
                Add-Finding "W11_COORD_NO_ASSERT" "WARN" $name $ln `
                    "좌표 탭인데 같은 케이스 안에 결과 단언이 없다. 해상도가 바뀌면 조용히 빗나가고 그대로 통과한다 → id로 바꾸거나(가능하면), 최소한 탭의 결과를 assert할 것"
            }
        }

        # ---- W12 hideKeyboard 앞에 입력이 없다 = 사실상 뒤로가기 ----
        #   Maestro의 hideKeyboard는 **키보드가 없으면 back으로 동작한다**(2026-09-08 실측).
        #   `26_Menu` 추천인 케이스에서 앱이 홈으로 튀었고, 06 탐색본은 가입 폼을 벗어났다.
        if ($c -match 'hideKeyboard') {
            $bw = Get-BackWindow $code $i 8
            if ($bw -notmatch 'inputText|eraseText|copyTextFrom|[Ee]dit[Tt]ext|when:') {
                Add-Finding "W12_HIDEKEYBOARD_AS_BACK" "WARN" $name $ln `
                    "앞 8스텝에 입력이 없는 hideKeyboard다. 키보드가 없으면 **뒤로가기로 동작해** 화면을 벗어난다 → 입력 직후에만 두거나 `when: visible: <입력 필드>` 로 가드할 것"
            }
        }

        # ---- W13 스크롤/스와이프 직후의 index 셀렉터 ----
        #   index는 행 앵커가 아니라 "그 순간 **화면에서 가장 위**의 매칭 요소"다
        #   (Filters.INDEX_COMPARATOR = bounds.y → bounds.x). 해상도가 커져 한 화면에 행이 더 보이면
        #   같은 index가 다른 행을 가리킨다 → `13_06`이 타겟이 아닌 송금인을 지웠다(2026-09-08).
        if ($c -match '^\s*index\s*:') {
            $bw = Get-BackWindow $code $i 10
            if ($bw -match 'scroll|swipe' -and $bw -notmatch 'centerElement') {
                Add-Finding "W13_INDEX_AFTER_SCROLL" "WARN" $name $ln `
                    "스크롤/스와이프 직후의 index 셀렉터다. index는 행이 아니라 **그 순간 화면 맨 위**를 가리키므로 스크롤 위치가 조금만 달라져도 다른 행을 집는다 → 이름으로 앵커하거나(`childOf: containsDescendants`) `centerElement: true`로 위치를 고정할 것"
            }
        }

        # ---- W06 파일 내 중복된 신원 픽스처 ----
        if ($c -match '^\s*-?\s*inputText\s*:\s*"([^"]+)"') {
            $val = $Matches[1]
            # 전화번호는 **신원 픽스처가 아니다** — 수취인 여럿이 같은 번호를 써도 서버가 소모하지 않는다.
            #   (02_01에서 오탐 2건의 원인이었다) → 직전 2줄에 번호 필드가 보이면 건너뛴다.
            #   **검색어**도 픽스처가 아니다 — 같은 값을 여러 번 검색하는 건 정상이다
            #   (필터 동작을 양방향으로 확인하려면 오히려 반복이 필요하다).
            $pf = ($code[([Math]::Max(0, $i - 3))..$i] -join "`n")
            $isPhone  = $pf -match 'MobileNo|Phone|휴대폰|핸드폰'
            $isSearch = $pf -match 'search|Search|검색'
            if (-not $isPhone -and -not $isSearch -and
                ($val -match '^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$' -or $val -match '^\d{8,12}$')) {
                if ($fixtureSeen.ContainsKey($val)) {
                    Add-Finding "W06_DUP_FIXTURE" "WARN" $name $ln `
                        ("신원 픽스처가 " + $fixtureSeen[$val] + "행과 중복된다. 서버가 소모하는 값이면 두 번째가 반드시 실패한다(여권/ARC 동일번호·S1/S2 동일 이메일이 실제 사고였다)")
                } else { $fixtureSeen[$val] = $ln }
            }
        }

        # ---- W07 결과 갈래 앞에 도달 강제가 없음 ----
        if ($c -match '^\s*(visible|notVisible)\s*:' -or $c -match 'runFlow') {
            $hit = $null
            foreach ($v in $cfg.resultVocabulary) { if ($c -match [regex]::Escape($v)) { $hit = $v; break } }
            if ($hit) {
                $from = [Math]::Max(0, $i - 20)
                $win  = ($code[$from..$i] -join "`n")
                if ($win -notmatch 'extendedWaitUntil') {
                    Add-Finding "W07_RESULT_NO_WAIT" "WARN" $name $ln `
                        ('결과 문구("' + $hit + '") 갈래인데 앞 20줄에 extendedWaitUntil이 없다 → 아무것도 안 떠도 EXIT=0이 된다. 결과 도달을 먼저 강제할 것')
                }
            }
        }
    }

    # ---- 파일 끝에서 끝나는 숫자 런을 flush ----
    #   W08은 "런 다음 줄"에서 보고하므로 런이 **파일 마지막 줄**이면 영영 보고되지 않았다.
    #   자기검사 픽스처가 정확히 그 모양이라 FAIL로 드러났다(2026-09-01).
    if ($runLen -ge 2) {
        $gFrom = [Math]::Max(0, $runStartIdx - 12)
        $guard = ($codeX[$gFrom..([Math]::Max(0, $runStartIdx - 1))] -join "`n")
        if ($guard -notmatch 'input_dot_1|keypadContainer|4자리 숫자를 입력하세요|간편 비밀번호를 입력하세요|간편 비밀번호를 생성|간편 비밀번호를 다시 입력') {
            Add-Finding "W08_PIN_NO_SCREEN_WAIT" "WARN" $name $runStart `
                ("PIN 숫자 " + $runLen + "연타(" + $runStart + "행~파일 끝) 앞에 **PIN 화면 도달 판정이 없다**. 화면이 아직 안 떴는데 누르면 같은 글자를 가진 다른 요소를 집는다 → 런 앞에 `input_dot_1`(또는 keypadContainer) 대기를 둘 것")
        }
    }

    # ---- E08 launchApp 하는데 Server Override(LIVETEST 강제) 처리가 없다 ----
    #   2026-09-03 사용자 선언으로 **기본 빌드가 `.stag`**가 됐다. stag는 서버 기본값이 **STAG**이고
    #   `clearState`가 그 기본값으로 되돌린다 → 강제하지 않으면 **조용히 gmeuat로 돈다.**
    #   실측 사고(2026-08-27): 스위트 전체가 STAG로 돌았다 — logcat gmeuat 1,113건 / livetest 0건.
    #   에러도 안 나고 결과도 그럴듯해서 **실행으로는 절대 못 잡는 부류**라 린터가 맡는다.
    #   판정: 헤더가 `${APP_ID}`(= 빌드 가변)이고 본문에 launchApp이 있는데
    #        인라인 항등 시퀀스도, `_server_override_old` 호출도, 그것을 품은 `_suite_recover_old` 호출도 없다.
    $codeAll = ($code -join "`n")
    $rawAll  = ($raw  -join "`n")
    if ($rawAll -match '(?m)^appId:\s*\$\{APP_ID\}' -and $codeAll -match '(?m)^\s*-?\s*launchApp') {
        $hasOverride = ($codeAll -match 'Server Override') -or
                       ($codeAll -match '_server_override_old') -or
                       ($codeAll -match '_suite_recover_old')
        if (-not $hasOverride) {
            Add-Finding "E08_NO_SERVER_OVERRIDE" "ERROR" $name 1 `
                "launchApp을 하는데 Server Override(LIVETEST 강제) 처리가 없다 → stag 빌드에서 **조용히 gmeuat(STAG) 서버로 돈다**. `- runFlow: `"_server_override_old.yaml`"` 를 launchApp 뒤에 둘 것"
        }
    }
}

# ================================================================
# 출력
# ================================================================
$order = @{ "ERROR" = 0; "WARN" = 1 }
$all = @($findings | Sort-Object { $order[$_.Level] }, File, Line)
$shown = switch ($Level) {
    "ERROR" { @($all | Where-Object { $_.Level -eq "ERROR" }) }
    "WARN"  { @($all | Where-Object { $_.Level -eq "WARN" }) }
    default { $all }
}
$errCount  = @($all | Where-Object { $_.Level -eq "ERROR" }).Count
$warnCount = @($all | Where-Object { $_.Level -eq "WARN" }).Count

if (-not $Quiet) {
    Write-Host ""
    Write-Host ("=== lint_flows: {0} ({1}개 파일) ===" -f $Path, $files.Count) -ForegroundColor Cyan
    if ($shown.Count -eq 0) { Write-Host "  지적 사항 없음" -ForegroundColor Green }
    foreach ($g in ($shown | Group-Object Rule | Sort-Object { $order[$_.Group[0].Level] }, Name)) {
        $lvl = $g.Group[0].Level
        $col = if ($lvl -eq "ERROR") { "Red" } else { "Yellow" }
        Write-Host ""
        Write-Host ("[{0}] {1} — {2}건" -f $lvl, $g.Name, $g.Count) -ForegroundColor $col
        $rows = @($g.Group | Sort-Object File, Line)
        foreach ($x in ($rows | Select-Object -First 15)) {
            Write-Host ("    {0}:{1}" -f $x.File, $x.Line) -ForegroundColor DarkGray -NoNewline
            Write-Host ("  {0}" -f $x.Msg)
        }
        if ($rows.Count -gt 15) {
            Write-Host ("    … 외 {0}건 (전체는 lint.md)" -f ($rows.Count - 15)) -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    Write-Host ("ERROR {0} / WARN {1}" -f $errCount, $warnCount) -ForegroundColor $(if ($errCount -gt 0) { "Red" } else { "Green" })
}

$md = @()
$md += "# lint_flows 결과 — " + (Get-Date -Format 'yyyy-MM-dd HH:mm')
$md += ""
$md += "- 대상: ``$Path`` / $($files.Count)개 파일"
$md += "- **ERROR $errCount** / **WARN $warnCount**"
$md += ""
$md += "> 실행으로는 원리적으로 안 잡히는 부류만 검사한다. 좌표·타이밍·앱 결함은 실행만이 잡는다."
$md += ""
foreach ($g in ($all | Group-Object Rule | Sort-Object { $order[$_.Group[0].Level] }, Name)) {
    $md += "## [$($g.Group[0].Level)] $($g.Name) — $($g.Count)건"
    $md += ""
    $md += "| 파일 | 줄 | 내용 |"
    $md += "|---|---|---|"
    foreach ($x in ($g.Group | Sort-Object File, Line)) {
        $md += "| $($x.File) | $($x.Line) | " + ($x.Msg -replace '\|', '\|') + " |"
    }
    $md += ""
}
$slug = ($Path -replace '[\\/:*?"<>|.]', '') ; if (-not $slug) { $slug = "root" }
$mdPath = Join-Path $root ("lint_" + $slug + ".md")
Write-Utf8 $mdPath ($md -join "`n")
if (-not $Quiet) { Write-Host ("리포트: " + $mdPath) -ForegroundColor DarkGray }

if ($Json) {
    $jsonPath = Join-Path $root ("lint_" + $slug + ".json")
    Write-Utf8 $jsonPath ($all | ConvertTo-Json -Depth 4)
    if (-not $Quiet) { Write-Host ("JSON:   " + $jsonPath) -ForegroundColor DarkGray }
}

if ($errCount -gt 0) { exit 1 }
if ($WarnAsError -and $warnCount -gt 0) { exit 1 }
exit 0
