# ================================================================
# report_daily.ps1 — 데일리 리포트 생성 (본인 기록용)
#
#   .\report_daily.ps1                      # 오늘 자 리포트
#   .\report_daily.ps1 -Date 2026-09-28     # 날짜 지정
#   .\report_daily.ps1 -BundleOnly          # 번들만 만들고 멈춘다(검증용)
#
# 기본값이 '오늘'인 이유: 스케줄러가 **22:00** 에 돈다. 그날 작업이 끝난 뒤라
#   그날 자를 쓰는 게 맞다. (아침 실행으로 옮기면 기본값을 '어제'로 되돌릴 것.)
# ⚠️ 단, **00~06시에 실행되면 '어제' 자로 잡는다.** 작업에 `StartWhenAvailable` 이 켜져 있어
#   22:00 에 PC 가 자고 있으면 **깨어난 뒤 밀려서 실행된다** → 자정을 넘기면 날짜가 하루 밀려
#   그날치 자료가 0건인 빈 리포트가 나온다(2026-09-30 01:34 실제 발생).
#
# 왜 이 구조인가 —
#   ★ 옛 `Automation Report.bat` 은 `claude -p` 에게 "첨부한 qa_report.json 을 읽고" 라고만
#     말하고 **경로도 첨부도 주지 않았다.** 그 파일은 존재하지도 않았다.
#     → 여기서는 **스크립트가 번들 파일을 직접 만들어 절대경로를 프롬프트에 박아 넘긴다.**
#   ★ 회귀 스위트는 하루 1회가 아니라 **10~15회씩 짧게** 돈다(2026-09-28 실측 15회).
#     그래서 실행별로 나열하지 않고 **항목별 '마지막 결과'로 접어서** 넘긴다.
#   ★ 작업 성격이 "yaml 을 새로 써서 커버리지를 늘리는 것" 에서
#     "무엇이 왜 깨졌고 어떻게 고쳤나" 로 바뀌었다 → 커버리지 델타가 아니라 **원인 분류**가 축이다.
#
# 입력(이미 디스크에 다 있다 — 중간 산출물 불필요):
#   Maestro\suite_logs\<시각>\SUMMARY.md   집계 + 환경
#   Maestro\suite_logs\<시각>\<항목>.log    실패 원인
#   git log (Maestro\ / web-runner\ 분리)   조치 + 도구 개발 트랙
# ================================================================
param(
    # 00~06시 실행은 '밀려서 돈 어제 22:00 분' 으로 본다 (위 주석 참고).
    [string]$Date = $(if ((Get-Date).Hour -lt 6) { (Get-Date).AddDays(-1).ToString("yyyy-MM-dd") }
                      else                      { (Get-Date).ToString("yyyy-MM-dd") }),
    [switch]$BundleOnly,
    [switch]$NoUpload,                              # 리포트만 만들고 ClickUp 업로드는 건너뛴다
    [string]$OutDir = "artifacts\daily_report",
    # ClickUp 대상 — 문서 `2kzmx95r-78` 안의 최상위 페이지
    #   `2kzmx95r-1738` = "스위트 생성, 호환성 검증, Web-runner" (2026-09-29 신설).
    #   형제 섹션: `-38` 개편UI(~08-10) / `-818` 구 UI(~09-28, **다른 PC 의 08:50 스케줄러가 쓰는 곳**).
    #   ⚠️ 문서를 새로 만들 권한이 없다(`Failed to create document: not_found_or_authorized`) →
    #      문서는 사람이 UI 에서 만들고, 여기엔 **페이지만** 쌓는다.
    [string]$DocId        = "2kzmx95r-78",
    [string]$ParentPageId = "2kzmx95r-1738"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

# ⛔ 지우지 말 것 — 이 프로세스가 **네이티브 명령(git) 출력을 무슨 인코딩으로 읽을지**를 못 박는다.
#   cp949 로 읽히면 한글 커밋 메시지가 깨진 채 번들에 들어가고(2026-09-30 실측),
#   깨진 바이트가 줄바꿈까지 삼켜 **커밋 두 건이 한 줄로 붙는다**. 번들 검증은 이를 못 잡는다.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$utf8 = [System.Text.UTF8Encoding]::new($false)
function Write-Utf8([string]$p, [string]$t) { [System.IO.File]::WriteAllText($p, $t, $utf8) }

# ---------------------------------------------------------------- claude 호출 (타임아웃)
# ⚠️ 스케줄 작업에는 `ExecutionTimeLimit` 이 걸려 있다. `claude -p` 가 응답 없이 매달리면
#   작업이 통째로 강제 종료되고(결과코드 0x41306) 로그엔 "리포트 생성 중..." 한 줄만 남는다
#   — 무엇이 멈췄는지 알 수 없다(2026-09-30 01:34 실제 발생).
#   → 호출 단위로 먼저 끊어서 **어느 단계가 몇 분 만에 멈췄는지 남기고** 정상 실패시킨다.
# 작업은 별도 pwsh 프로세스로 돈다 → 호출 전 저장소로 이동시켜 둔다(claude 의 프로젝트 문맥).
function Invoke-ClaudeWithTimeout {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [string[]]$AllowedTools = @("Read"),
        [int]$TimeoutMinutes = 20
    )
    $job = Start-Job -ScriptBlock {
        param($p, $tools, $cwd)
        Set-Location $cwd
        # ⛔ 이 줄을 지우지 말 것 — 백그라운드 작업의 `[Console]::OutputEncoding` 은
        #   부모(UTF-8)와 달리 **cp949** 다. 그대로 두면 claude 가 뱉은 UTF-8 을 cp949 로 읽어
        #   리포트 전체가 깨진 한글(`?먮룞???곗씪由?`)로 저장된다 — 2026-09-30 실측.
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $OutputEncoding           = [Console]::OutputEncoding
        $out = & claude -p $p --allowedTools $tools 2>&1 | Out-String
        [pscustomobject]@{ Output = $out; ExitCode = $LASTEXITCODE }
    } -ArgumentList $Prompt, $AllowedTools, $repo

    if (Wait-Job $job -Timeout ($TimeoutMinutes * 60)) {
        $r = Receive-Job $job
        Remove-Job $job -Force -ErrorAction SilentlyContinue
        return $r
    }
    # 시간 초과 — 작업을 끊는다(자식 claude 프로세스가 남을 수 있다. 남으면 다음 실행에 영향은 없다).
    Stop-Job   $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    return [pscustomobject]@{ Output = "TIMEOUT: claude 가 $TimeoutMinutes 분 안에 끝나지 않았다"; ExitCode = 124 }
}

$suiteRoot = Join-Path $repo "Maestro\suite_logs"
$outFull   = Join-Path $repo $OutDir
New-Item -ItemType Directory -Force -Path $outFull | Out-Null

$bundlePath = Join-Path $outFull "$($Date)_bundle.md"
$reportPath = Join-Path $outFull "$($Date)_report.md"

Write-Host "=== 데일리 리포트 수집 — $Date ===" -ForegroundColor Cyan

# ---------------------------------------------------------------- 1) 실행 수집
$runs = @()
if (Test-Path $suiteRoot) {
    $runs = Get-ChildItem $suiteRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "$Date*" } | Sort-Object Name
}
$done    = @($runs | Where-Object { Test-Path (Join-Path $_.FullName "SUMMARY.md") })
$aborted = @($runs | Where-Object { -not (Test-Path (Join-Path $_.FullName "SUMMARY.md")) })

Write-Host ("  실행 {0}회 (완주 {1} / 중단·미완 {2})" -f $runs.Count, $done.Count, $aborted.Count)

# ---------------------------------------------------------------- 2) 항목별 최종 상태
# 같은 항목이 하루에 여러 번 돈다 → 시각순으로 덮어써서 **마지막 결과**만 남긴다.
$items = [ordered]@{}
$envLines = @()
foreach ($d in $done) {
    $md = Get-Content (Join-Path $d.FullName "SUMMARY.md") -Encoding UTF8
    foreach ($line in $md) {
        # | G2 | 25_Profile | FAIL | 285 | 10:19 | 사유 |
        if ($line -match '^\|\s*(G\d)\s*\|\s*([^\s|]+)\s*\|\s*(PASS|FAIL|SKIP)\s*\|\s*(\d+)\s*\|\s*([\d:]+)\s*\|(.*)\|\s*$') {
            $items[$Matches[2]] = [pscustomobject]@{
                Group = $Matches[1]; Name = $Matches[2]; Status = $Matches[3]
                Steps = $Matches[4]; Elapsed = $Matches[5]
                Reason = $Matches[6].Trim(); Run = $d.Name
            }
        }
    }
    # 환경 줄은 마지막 실행 것만 쓴다
    $envLines = $md | Where-Object { $_ -match '^- (기기|빌드|접속 호스트|시작 잔액)' }
}

$pass = @($items.Values | Where-Object Status -eq "PASS").Count
$fail = @($items.Values | Where-Object Status -eq "FAIL").Count
$skip = @($items.Values | Where-Object Status -eq "SKIP").Count
Write-Host ("  항목 {0}개 — PASS {1} / FAIL {2} / SKIP {3}" -f $items.Count, $pass, $fail, $skip)

# ---------------------------------------------------------------- 3) 실패 근거 발췌
# ⚠️ 로그 전문을 넘기지 않는다 — 계정ID·잔액·실이메일이 들어 있고 번들만 커진다.
#    실패 지점 앞뒤만 잘라 '원인 판단에 필요한 만큼'만 싣는다.
$evidence = @()
foreach ($it in @($items.Values | Where-Object Status -eq "FAIL")) {
    $log = Join-Path (Join-Path $suiteRoot $it.Run) "$($it.Name).log"
    if (-not (Test-Path $log)) { continue }
    $lines = Get-Content $log -Encoding UTF8
    $idx = -1
    for ($i = $lines.Count - 1; $i -ge 0; $i--) { if ($lines[$i] -match 'FAILED') { $idx = $i; break } }
    if ($idx -lt 0) { continue }
    $from = [Math]::Max(0, $idx - 18)
    $evidence += [pscustomobject]@{ Name = $it.Name; Lines = ($lines[$from..$idx] -join "`n") }
}

# ---------------------------------------------------------------- 4) 커밋 두 트랙
$since = "$Date 00:00"
$until = "{0} 00:00" -f ([datetime]$Date).AddDays(1).ToString("yyyy-MM-dd")
function Get-Commits([string]$path) {
    # --no-merges: 머지 커밋은 두 트랙에 모두 잡혀 중복된다
    @(git log --all --no-merges --since=$since --until=$until --pretty=format:"%h %s" -- $path 2>$null) |
        Where-Object { $_ } | Select-Object -Unique
}
$commitsQA   = Get-Commits "Maestro"
$commitsTool = Get-Commits "web-runner"
Write-Host ("  커밋 — 회귀 {0}건 / web-runner {1}건" -f $commitsQA.Count, $commitsTool.Count)

# ---------------------------------------------------------------- 5) 번들 작성
$b = New-Object System.Collections.Generic.List[string]
$b.Add("# 데일리 리포트 원자료 — $Date")
$b.Add("")
# ⚠️ 큰따옴표 안에서 백틱은 이스케이프 문자다(`r = CR) → 코드 인용은 작은따옴표로 쓴다.
$b.Add('> 이 파일은 `report_daily.ps1` 이 자동 생성한 **원자료**다. 사람이 읽는 리포트가 아니다.')
$b.Add("")
$b.Add("## 실행 개요")
$b.Add("- 스위트 실행 **$($runs.Count)회** (완주 $($done.Count) / 중단·미완 $($aborted.Count))")
$b.Add("- 항목 $($items.Count)개 — PASS $pass / FAIL $fail / SKIP $skip  (같은 항목 여러 번 실행 시 **마지막 결과**)")
if ($aborted.Count -gt 0) { $b.Add("- 중단된 실행: " + (($aborted | ForEach-Object { $_.Name }) -join ", ")) }
$b.Add("")
if ($envLines) { $b.Add("## 환경 (마지막 실행 기준)"); $envLines | ForEach-Object { $b.Add($_) }; $b.Add("") }

$b.Add("## 항목별 최종 상태")
if ($items.Count -eq 0) {
    $b.Add("(이 날짜에 완주한 스위트 실행이 없다)")
} else {
    $b.Add("| 그룹 | 항목 | 결과 | 스텝 | 소요 | 사유 |")
    $b.Add("|---|---|---|---|---|---|")
    foreach ($it in $items.Values) {
        $b.Add("| $($it.Group) | $($it.Name) | $($it.Status) | $($it.Steps) | $($it.Elapsed) | $($it.Reason) |")
    }
}
$b.Add("")

if ($evidence.Count -gt 0) {
    $b.Add("## 실패 지점 발췌 (원인 판단용)")
    foreach ($e in $evidence) {
        $b.Add("### $($e.Name)"); $b.Add('```'); $b.Add($e.Lines); $b.Add('```'); $b.Add("")
    }
}

$b.Add("## 커밋 — 회귀 스위트(Maestro)")
if ($commitsQA) { $commitsQA | ForEach-Object { $b.Add("- $_") } } else { $b.Add("(없음)") }
$b.Add("")
$b.Add("## 커밋 — web-runner (도구 개발)")
if ($commitsTool) { $commitsTool | ForEach-Object { $b.Add("- $_") } } else { $b.Add("(없음)") }
$b.Add("")

Write-Utf8 $bundlePath ($b -join "`n")
Write-Host "  번들: $bundlePath" -ForegroundColor DarkGray

if ($BundleOnly) { Write-Host "-BundleOnly 지정 — 여기서 멈춘다." -ForegroundColor Yellow; exit 0 }

# ---------------------------------------------------------------- 6) 리포트 생성
$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) { Write-Error "claude CLI 를 찾을 수 없다. 번들만 만들었다: $bundlePath"; exit 1 }

# ⚠️ 경로를 **프롬프트에 박아** 넘긴다. "첨부한 파일" 같은 표현은 쓰지 않는다(옛 스크립트의 실패 원인).
$prompt = @"
$bundlePath 파일을 Read 로 읽고, GME QA 자동화 데일리 리포트($Date)를 한국어 마크다운으로 작성해라.
결과는 설명 없이 **마크다운 본문만** 출력해라.
⛔ 전체를 코드펜스(백틱 3개)로 감싸지 마라 — 그대로 ClickUp 페이지 본문이 되므로,
   감싸면 문서가 통째로 코드블록으로 렌더된다. 본문 안의 로그 인용에는 펜스를 써도 된다.

이 리포트는 **본인 기록용**이다. 나중에 내가 다시 읽고 "그때 왜 그렇게 했지"를 복원하는 게 목적이다.
홍보성 요약이나 일반론은 넣지 말고, 구체적인 셀렉터·id·수치·커밋 해시를 남겨라.

구성:
1. **한 줄 결론** — 오늘 회귀 상태와 도구 진척을 각각 한 줄.
2. **항목별 최종 상태** — 원자료의 표를 그대로 쓰되, `원인분류` 열을 **추가**해라.
   분류는 넷 중 하나: `코드결함` / `환경` / `전제미충족` / `앱결함`.
   판단 근거가 약하면 `미상`으로 두고 4번에 적어라. 추측으로 단정하지 마라.
3. **규명한 결함과 조치** — 이 리포트의 알맹이다. 건마다 `증상 -> 원인 -> 조치(커밋 해시)` 순서로.
   실패 지점 발췌와 커밋 목록을 연결해서 써라. 원인을 못 밝힌 건 못 밝혔다고 적어라.
4. **미해결 / 다음 실행 전 할 일** — 원인 미상, 사람 손이 필요한 것(계정 삭제·잔액 충전 등),
   소모된 자원(로그인 시도 횟수, 비멱등 계정) 을 적어라.
5. **web-runner (도구 개발)** — 그날 무엇을 왜 바꿨는지. 커밋 메시지를 그대로 옮기지 말고
   "무엇이 불편해서 무엇을 바꿨나"로 풀어 써라.
6. **요약 3줄**.

규칙:
- 실행이 0건인 날은 1~4를 "실행 없음" 한 줄로 접고 5번만 쓴다.
- 표와 불릿을 쓰되 2번 표는 길어지지 않게 한다. 길어져야 하는 건 3번이다.
- 원자료에 없는 내용을 지어내지 마라.
"@

Write-Host "  리포트 생성 중..." -ForegroundColor DarkGray
$res = Invoke-ClaudeWithTimeout -Prompt $prompt -AllowedTools @("Read") -TimeoutMinutes 25
$report     = $res.Output
$claudeExit = $res.ExitCode

# ⛔ 결과를 그대로 파일에 쓰고 "성공" 이라고 하지 말 것 —
#   실제로 `API Error: 401 ... Please run /login` 이 리포트로 저장되고 초록 글씨가 떴다(2026-09-28).
#   이 저장소가 계속 잡아온 '거짓 통과' 와 같은 부류다. 넘어가지 말고 시끄럽게 실패시킨다.
# 인증 실패를 **exit code 보다 먼저** 본다 — 둘 다 걸릴 때 "exit=1" 보다 할 일이 적힌 쪽이 쓸모 있다.
$bad = $null
if ($report -match '^TIMEOUT: ') {
    $bad = "리포트 생성이 시간 초과됐다 — $($report.Trim())"
}
elseif ($report -match 'API Error|Please run /login|authentication_error') {
    $bad = "claude CLI 인증 실패 — 터미널에서 claude 를 실행하고 /login 할 것"
}
elseif ($claudeExit -ne 0)                      { $bad = "claude exit=$claudeExit" }
elseif ([string]::IsNullOrWhiteSpace($report))  { $bad = "출력이 비었다" }
elseif ($report.Length -lt 400)                 { $bad = "출력이 너무 짧다($($report.Length)자) — 리포트가 아니다" }
elseif ($report -notmatch '(?m)^#')             { $bad = "마크다운 제목이 없다 — 리포트 형식이 아니다" }

if ($bad) {
    Write-Host "  받은 출력(앞 300자): $($report.Substring(0, [Math]::Min(300, $report.Length)))" -ForegroundColor DarkGray
    Write-Error "리포트 생성 실패 — $bad`n번들은 남아 있다: $bundlePath"
    exit 1
}
# 프롬프트로 막았어도 모델이 전체를 펜스로 감싸는 일이 있다(2026-09-29 실측: ```markdown … ```).
#   그대로 올리면 ClickUp 에서 문서 전체가 코드블록으로 렌더된다 → 여기서 한 번 더 벗긴다.
$trimmed = $report.Trim()
if ($trimmed -match '(?s)^```[a-zA-Z]*\r?\n(.*)\r?\n```$') {
    $report = $Matches[1]
    Write-Host "  (전체를 감싼 코드펜스를 제거했다)" -ForegroundColor DarkGray
}

Write-Utf8 $reportPath $report
Write-Host "  리포트: $reportPath" -ForegroundColor Green

if ($NoUpload) { Write-Host "-NoUpload 지정 — 업로드를 건너뛴다." -ForegroundColor Yellow; exit 0 }

# ---------------------------------------------------------------- 7) ClickUp 업로드
# 생성과 업로드를 **한 번의 claude 호출로 합치지 않는다.** 나눠 두면
#   ① 위의 검증을 통과한 마크다운만 올라가고
#   ② 업로드가 실패해도 리포트가 디스크에 남으며
#   ③ 각 단계의 --allowedTools 를 좁게 줄 수 있다.
# ⚠️ CLI 의 MCP 는 데스크톱 앱 커넥터와 **별개 레지스트리**다. 여기서 쓰는 건
#    `claude mcp add --scope user --transport http clickup https://mcp.clickup.com/mcp` 로
#    등록한 것이고, `claude mcp list` 에 떠야 동작한다.
$pageName = "$Date 데일리 리포트"
$upPrompt = @"
$reportPath 파일을 Read 로 읽어, 그 내용 전체를 본문으로 하는 ClickUp 페이지를 만들어라.
- document_id: $DocId
- parent_page_id: $ParentPageId
- name: $pageName
- content_format: text/md
만든 뒤 생성된 page id 만 'page=<id>' 형식 한 줄로 출력해라. 다른 말은 하지 마라.
"@

Write-Host "  ClickUp 업로드 중..." -ForegroundColor DarkGray
$upRes  = Invoke-ClaudeWithTimeout -Prompt $upPrompt `
              -AllowedTools @("Read", "mcp__clickup__clickup_create_document_page") -TimeoutMinutes 10
$up     = $upRes.Output
$upExit = $upRes.ExitCode

# 업로드도 '조용한 실패' 를 막는다 — page id 를 실제로 받았는지로 판정한다.
$pageId = if ($up -match 'page=([A-Za-z0-9_-]+)') { $Matches[1] } else { $null }
if ($upExit -ne 0 -or -not $pageId) {
    Write-Host "  받은 출력: $($up.Trim())" -ForegroundColor DarkGray
    Write-Error "ClickUp 업로드 실패 (exit=$upExit). 리포트는 남아 있다: $reportPath"
    exit 1
}

Write-Host "  업로드 완료: page=$pageId" -ForegroundColor Green
Write-Host "  https://app.clickup.com/90182689976/v/dc/$DocId/$pageId" -ForegroundColor DarkGray
