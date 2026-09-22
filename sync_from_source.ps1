# ================================================================
# sync_from_source.ps1 — 정본(OneDrive) → 이 저장소 미러 동기화
#
#   .\sync_from_source.ps1                 # 계획만 출력 (아무것도 바꾸지 않는다)
#   .\sync_from_source.ps1 -Apply          # 실제 적용
#   .\sync_from_source.ps1 -Area Maestro   # 한 영역만
#
# 왜 필요한가:
#   편집 정본은 OneDrive(`개인용 - Automation\`)고 이 저장소는 **읽기 전용 사본**이다.
#   두 벌이 있으면 반드시 한쪽이 낡는다 — 2026-09-10에 9일치가 벌어져 저장소 린터가
#   **이미 고쳐진 결함 11건을 ERROR로 리포트**했다(정본은 0건). 손으로 맞추면 또 벌어진다.
#
# 방향은 **한쪽뿐이다**: 정본 → 저장소. 저장소에서 고친 것은 이 스크립트가 지운다.
#   ⛔ 저장소 사본을 편집하지 말 것. 편집은 정본에서 한다(CLAUDE.md 참고).
#
# ⚠️ 이 스크립트는 **저장소 루트**에 둔다. `Maestro\` 안에 두면 정본에 없는 파일이라
#    다음 실행에서 스스로를 삭제한다.
# ================================================================
param(
    [switch]$Apply,
    [ValidateSet("all", "Maestro", "Checklist", "Root", "docs")][string]$Area = "all",
    [string]$Source = "C:\Users\GME\Global Money Express Co., Ltd\개인용 - Automation",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path -LiteralPath $Source)) {
    Write-Error "정본 경로가 없습니다: $Source  (OneDrive 동기화 상태를 확인하세요)"
    exit 2
}

# ----------------------------------------------------------------
# 제외 규칙 — .gitignore 와 일치시킨다. 여기서 어긋나면 추적되지 않을 파일을
#   저장소에 쌓거나(그 반대로) 매번 "차이 있음"으로 뜬다.
# ----------------------------------------------------------------
function Test-IgnoredDir([string]$name) {
    # suite_logs: 실행 로그에 계정 ID·잔액·거래 내역이 그대로 남는다 → 저장소에 올리지 않는다(2026-09-11).
    return ($name -like "shots_*") -or ($name -in @(".maestro", "artifacts", ".git", "suite_logs"))
}
function Test-IgnoredFile([string]$name, [string[]]$extra) {
        if ($name -like "*.png" -or $name -like "*.zip") { return $true }
    foreach ($p in $extra) { if ($name -like $p) { return $true } }
    return $false
}

# 영역 정의
#   Root      = 개별 파일만(정본 루트에는 Maestro\·Checklist\ 도 있어 통째로 훑으면 안 된다)
#   Checklist = xlsx 는 **의도적으로 추적하지 않는다**(정본 결과 파일, 바이너리) → 백업본까지 제외
#   Maestro   = 통째로. 제외는 .gitignore 와 동일
#   docs      = 사람이 읽는 문서(2026-09-16 신설). 흩어져 있던 md 를 한곳에 모았다.
#               ⚠️ `PROGRESS.md`·`SUITE.md`·`README*.md` 는 **저장소에만 있는 파일**이라 제외한다 —
#                  빼지 않으면 정본에 없다는 이유로 매번 '삭제' 로 잡힌다.
#               ⚠️ `CLAUDE.md`(저장소 루트)와 `.claude\skills\*\SKILL.md` 는 **경로가 고정**이라
#                  여기로 옮기지 않았다. 옮기면 지침·스킬이 로드되지 않는다.
#               ⚠️ 린터 산출물 `lint_*.md` 는 문서가 아니라 **재생성되는 산출물**이라
#                  저장소에서는 `artifacts\lint\` 로 보냈다(=`.gitignore` 의 `artifacts/`).
$areas = @(
    @{ Name = "Root";      Dir = "";          Files = @("run_test.ps1", "Automation Report.bat", "Automation Report.txt") }
    @{ Name = "Checklist"; Dir = "Checklist"; Exclude = @("*.xlsx", "*.xlsx.bak_*") }
    #   lint_*.md = 린터가 **돌릴 때마다 다시 만드는 산출물**이다(문서가 아니다) → 미러하지 않는다.
    #               2026-09-16 정리 전까지 `Maestro\` 에 문서와 섞여 있어 md 를 찾기 어려웠다.
    #   _tmp_*.yaml = 큰 yaml 의 일부 구간만 잘라 돌리는 **일회용 탐색본**이다(본 파일에서 재추출한다).
    #               Test-IgnoredFile 은 파일명만 보므로 `Old\` 하위도 함께 걸린다.
    @{ Name = "Maestro";   Dir = "Maestro";   Exclude = @("lint_*.md", "_tmp_*.yaml") }
    #   README_*.md = `gme_excel.py` 안내(win/mac). 스크립트와 함께 **저장소에만** 둔다.
    #               와일드카드로 둔다 — 이름이 바뀌어도(README.md → README_mac.md) 안 지워지게.
    @{ Name = "docs";      Dir = "docs";      Exclude = @("PROGRESS.md", "SUITE.md", "README_*.md") }
)
if ($Area -ne "all") { $areas = @($areas | Where-Object { $_.Name -eq $Area }) }

# ----------------------------------------------------------------
# 파일 목록 — 영역 루트 기준 상대경로
# ----------------------------------------------------------------
function Get-FileList([string]$root, [string[]]$extraExclude, [string[]]$explicit) {
    $out = New-Object System.Collections.Generic.HashSet[string]
    if (-not (Test-Path -LiteralPath $root)) { return $out }
    if ($explicit) {
        foreach ($f in $explicit) {
            if (Test-Path -LiteralPath (Join-Path $root $f)) { [void]$out.Add($f) }
        }
        return $out
    }
    $stack = New-Object System.Collections.Stack
    $stack.Push($root)
    while ($stack.Count) {
        $cur = $stack.Pop()
        foreach ($e in (Get-ChildItem -LiteralPath $cur -Force)) {
            if ($e.PSIsContainer) {
                if (-not (Test-IgnoredDir $e.Name)) { $stack.Push($e.FullName) }
            } elseif (-not (Test-IgnoredFile $e.Name $extraExclude)) {
                [void]$out.Add($e.FullName.Substring($root.Length).TrimStart('\'))
            }
        }
    }
    return $out
}

# 내용 비교 — 크기가 다르면 즉시 다름, 같으면 해시로 확인한다
function Test-SameFile([string]$a, [string]$b) {
    $fa = Get-Item -LiteralPath $a; $fb = Get-Item -LiteralPath $b
    if ($fa.Length -ne $fb.Length) { return $false }
    return ((Get-FileHash -LiteralPath $a -Algorithm SHA256).Hash -eq
            (Get-FileHash -LiteralPath $b -Algorithm SHA256).Hash)
}

$totAdd = 0; $totDel = 0; $totChg = 0; $totSame = 0
$plan = @()

foreach ($a in $areas) {
    $sRoot = if ($a.Dir) { Join-Path $Source $a.Dir } else { $Source }
    $dRoot = if ($a.Dir) { Join-Path $repo   $a.Dir } else { $repo }

    $src = Get-FileList $sRoot $a.Exclude $a.Files
    $dst = Get-FileList $dRoot $a.Exclude $a.Files

    $added   = @($src | Where-Object { -not $dst.Contains($_) } | Sort-Object)
    $removed = @($dst | Where-Object { -not $src.Contains($_) } | Sort-Object)
    $common  = @($src | Where-Object { $dst.Contains($_) })
    $changed = @($common | Where-Object {
        -not (Test-SameFile (Join-Path $sRoot $_) (Join-Path $dRoot $_)) } | Sort-Object)

    $totAdd += $added.Count; $totDel += $removed.Count
    $totChg += $changed.Count; $totSame += ($common.Count - $changed.Count)

    foreach ($f in $added)   { $plan += [pscustomobject]@{ Op="+"; Area=$a.Name; Rel=$f; S=$sRoot; D=$dRoot } }
    foreach ($f in $changed) { $plan += [pscustomobject]@{ Op="~"; Area=$a.Name; Rel=$f; S=$sRoot; D=$dRoot } }
    foreach ($f in $removed) { $plan += [pscustomobject]@{ Op="-"; Area=$a.Name; Rel=$f; S=$sRoot; D=$dRoot } }
}

Write-Host ""
Write-Host ("=== 정본 → 저장소 동기화 {0} ===" -f $(if ($Apply) { "(적용)" } else { "(계획만)" })) -ForegroundColor Cyan
Write-Host ("  정본  : {0}" -f $Source) -ForegroundColor DarkGray
Write-Host ("  저장소: {0}" -f $repo)   -ForegroundColor DarkGray
Write-Host ("  추가 {0} / 갱신 {1} / 삭제 {2} / 동일 {3}" -f $totAdd, $totChg, $totDel, $totSame)

if (-not $Quiet) {
    foreach ($grp in ($plan | Group-Object Area)) {
        Write-Host ("  ── {0} ──" -f $grp.Name) -ForegroundColor DarkCyan
        foreach ($p in $grp.Group) {
            $color = switch ($p.Op) { "+" { "Green" } "~" { "Yellow" } "-" { "Red" } }
            Write-Host ("    {0} {1}" -f $p.Op, $p.Rel) -ForegroundColor $color
        }
    }
}

if (-not $plan.Count) {
    Write-Host "  차이 없음 — 이미 일치합니다." -ForegroundColor Green
    exit 0
}
if (-not $Apply) {
    Write-Host ""
    Write-Host "  계획만 출력했습니다. 적용하려면 -Apply 를 붙이세요." -ForegroundColor Yellow
    Write-Host "  ⚠️ 삭제 항목은 대개 **이름이 바뀌었거나 옮겨진 파일**입니다 — 같은 목록의 추가에 반대편이 있는지 확인하세요." -ForegroundColor Yellow
    exit 0
}

# ----------------------------------------------------------------
# 적용
# ----------------------------------------------------------------
foreach ($p in $plan) {
    $s = Join-Path $p.S $p.Rel
    $d = Join-Path $p.D $p.Rel
    if ($p.Op -eq "-") {
        Remove-Item -LiteralPath $d -Force
    } else {
        $dir = Split-Path -Parent $d
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Copy-Item -LiteralPath $s -Destination $d -Force
    }
}

# 비게 된 디렉터리 정리.
#   ⚠️ 무시 대상 트리(shots_* 등)에는 들어가지 않는다 — 추적하지 않을 뿐 지울 대상도 아니다.
foreach ($a in $areas) {
    if (-not $a.Dir) { continue }
    $dRoot = Join-Path $repo $a.Dir
    if (-not (Test-Path -LiteralPath $dRoot)) { continue }
    $dirs = Get-ChildItem -LiteralPath $dRoot -Directory -Recurse -Force |
            Where-Object { $_.FullName.Substring($dRoot.Length) -notmatch '\\(shots_[^\\]*|\.maestro|artifacts|\.git)(\\|$)' } |
            Sort-Object { $_.FullName.Length } -Descending
    foreach ($d in $dirs) {
        if (-not (Get-ChildItem -LiteralPath $d.FullName -Force)) {
            Remove-Item -LiteralPath $d.FullName -Force
            Write-Host ("    (빈 디렉터리 제거) {0}" -f $d.FullName.Substring($repo.Length).TrimStart('\')) -ForegroundColor DarkGray
        }
    }
}

# ----------------------------------------------------------------
# 적용 후 대조 — "적용했다"와 "일치한다"는 다르다. 반드시 다시 센다.
# ----------------------------------------------------------------
$residual = 0
foreach ($a in $areas) {
    $sRoot = if ($a.Dir) { Join-Path $Source $a.Dir } else { $Source }
    $dRoot = if ($a.Dir) { Join-Path $repo   $a.Dir } else { $repo }
    $src = Get-FileList $sRoot $a.Exclude $a.Files
    $dst = Get-FileList $dRoot $a.Exclude $a.Files
    $residual += @($src | Where-Object { -not $dst.Contains($_) }).Count
    $residual += @($dst | Where-Object { -not $src.Contains($_) }).Count
    $residual += @($src | Where-Object { $dst.Contains($_) } |
                  Where-Object { -not (Test-SameFile (Join-Path $sRoot $_) (Join-Path $dRoot $_)) }).Count
}

Write-Host ""
if ($residual -eq 0) {
    Write-Host "  적용 후 대조: 차이 0 — 일치합니다." -ForegroundColor Green
} else {
    Write-Host ("  ⚠️ 적용 후에도 차이가 {0}건 남았습니다 — 파일 잠김이나 권한 문제일 수 있습니다." -f $residual) -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  다음: git status 로 확인하고 커밋하세요. 저장소 사본을 실행해 검증하려면:" -ForegroundColor DarkGray
Write-Host "    cd Maestro; .\lint_flows.ps1; .\lint_selftest.ps1" -ForegroundColor DarkGray
