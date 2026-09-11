# ================================================================
# lint_selftest.ps1 — lint_flows.ps1 자기검사
#
#   .\lint_selftest.ps1
#
# 왜 필요한가:
#   "0건"은 **코퍼스가 깨끗함**과 **규칙이 죽었음**을 구별하지 못한다.
#   실제로 `W05_HARDCODED_SERIAL`이 빈 코드줄에서 먼저 continue가 걸려
#   주석줄을 아예 못 보고 있었고, 0건이라 아무도 몰랐다.
#   → 규칙마다 결함을 심은 픽스처를 두고 **발화해야 할 때 발화하는지**를 확인한다.
#
# 판정:
#   ① lint_selftest\bad_<RULE>_*.yaml  에서 그 규칙이 **1건 이상** 나와야 한다
#   ② lint_selftest\clean.yaml         에서는 **0건**이 나와야 한다 (오탐 검출)
#
# ⚠️ bad_E02_escape.yaml 은 **의도적으로 YAML 파싱이 깨진 파일**이다(그게 E02가 잡는 것).
#    이 폴더를 maestro로 실행하지 말 것 — 픽스처지 플로우가 아니다.
# ================================================================
param(
    [string]$Fixtures = "lint_selftest",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# 픽스처는 구 UI 트랙 기준으로 검사한다(E06을 켜기 위해).
& (Join-Path $root "lint_flows.ps1") -Path $Fixtures -Track v2 -Json -Quiet | Out-Null

$slug = ($Fixtures -replace '[\\/:*?"<>|.]', '')
$jsonPath = Join-Path $root ("lint_" + $slug + ".json")
if (-not (Test-Path $jsonPath)) { Write-Error "결과 파일이 없습니다: $jsonPath"; exit 2 }
$findings = @(Get-Content $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json)

$fixDir = Join-Path $root $Fixtures
$results = @()

foreach ($f in (Get-ChildItem $fixDir -Filter "bad_*.yaml" -File | Sort-Object Name)) {
    # bad_E01_pkgid.yaml → E01
    if ($f.Name -notmatch '^bad_([EW]\d{2})_') { continue }
    $rule = $Matches[1]
    $hits = @($findings | Where-Object { $_.File -eq $f.Name -and $_.Rule -like "$rule`_*" })
    $extra = @($findings | Where-Object { $_.File -eq $f.Name -and $_.Rule -notlike "$rule`_*" })
    $results += [pscustomobject]@{
        Fixture = $f.Name
        Rule    = $rule
        Expect  = "1건 이상"
        Got     = $hits.Count
        Status  = if ($hits.Count -ge 1) { "PASS" } else { "FAIL" }
        Extra   = ($extra | ForEach-Object { $_.Rule } | Select-Object -Unique) -join ","
    }
}

# clean.yaml 은 지적이 하나도 없어야 한다
$cleanHits = @($findings | Where-Object { $_.File -eq "clean.yaml" })
$results += [pscustomobject]@{
    Fixture = "clean.yaml"
    Rule    = "(없어야 함)"
    Expect  = "0건"
    Got     = $cleanHits.Count
    Status  = if ($cleanHits.Count -eq 0) { "PASS" } else { "FAIL" }
    Extra   = ($cleanHits | ForEach-Object { $_.Rule } | Select-Object -Unique) -join ","
}

if (-not $Quiet) {
    Write-Host ""
    Write-Host "=== lint_flows 자기검사 ===" -ForegroundColor Cyan
    $results | Format-Table Fixture, Rule, Expect, Got, Status, Extra -AutoSize
}

$fail = @($results | Where-Object Status -eq "FAIL")
$pass = @($results | Where-Object Status -eq "PASS")

Write-Host ("PASS {0} / FAIL {1}" -f $pass.Count, $fail.Count) -ForegroundColor $(if ($fail.Count) { "Red" } else { "Green" })
if ($fail.Count) {
    Write-Host ""
    Write-Host "실패한 항목:" -ForegroundColor Red
    foreach ($r in $fail) {
        if ($r.Fixture -eq "clean.yaml") {
            Write-Host ("  clean.yaml 에서 지적이 나왔다(오탐): " + $r.Extra) -ForegroundColor Red
        } else {
            Write-Host ("  " + $r.Fixture + " 에서 " + $r.Rule + " 가 발화하지 않았다 → 규칙이 죽었을 수 있다") -ForegroundColor Red
        }
    }
    exit 1
}
exit 0
