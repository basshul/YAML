# fill_result.ps1 — 자동화 결과를 작업본에 기입하고 마스터 붙여넣기용 블록을 뽑는다.
#
# 마스터(GME-IT-Korea)는 직접 건드리지 않는다. 작업본에만 쓰고, 값은 사용자가 손으로 옮긴다.
# 결과 열은 라운드마다 이동하므로(현재 마스터의 마지막 라운드는 7.19.1) 열을 고정하지 않고
# -Col 로 받는다. 행 순서는 라운드가 바뀌어도 그대로다.
#
# 사용법:
#   .\fill_result.ps1 -Results .\results.json -Col BB
#   .\fill_result.ps1 -Results .\results.json -Col BB -WhatIfOnly    # 기입 없이 미리보기만
#
# results.json 형식 (yaml/case 는 _bb_mapping.json 과 정확히 일치해야 한다):
#   [ { "yaml": "08_MyQR", "case": "[01] ...", "result": "Pass" }, ... ]

param(
  [Parameter(Mandatory=$true)][string]$Results,
  [string]$Col = "BB",
  [string]$Book = "$PSScriptRoot\GME QA Checklist V2.1_WORK.xlsx",
  [string]$Mapping = "$PSScriptRoot\_bb_mapping.json",
  [string]$Sheet = "Checklist(Livetest)",
  [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'
function Write-Utf8($path, $text) {
  [IO.File]::WriteAllText($path, $text, [Text.UTF8Encoding]::new($false))
}

foreach ($p in @($Results, $Mapping, $Book)) {
  if (-not (Test-Path $p)) { throw "파일을 찾을 수 없다: $p" }
}

$map = Get-Content $Mapping -Raw -Encoding UTF8 | ConvertFrom-Json
$res = Get-Content $Results -Raw -Encoding UTF8 | ConvertFrom-Json

# (yaml, case) -> result 조회표
$lookup = @{}
foreach ($r in $res) { $lookup["$($r.yaml)`u{1}$($r.case)"] = $r.result }

# 매핑에 결과를 붙인다
$rows = @()
foreach ($m in $map) {
  $key = "$($m.yaml)`u{1}$($m.case)"
  $rows += [pscustomobject]@{
    Row    = [int]$m.row
    Yaml   = $m.yaml
    Case   = $m.case
    Result = if ($lookup.ContainsKey($key)) { $lookup[$key] } else { $null }
  }
}
$rows = $rows | Sort-Object Row

$hit  = @($rows | Where-Object { $_.Result })
$miss = @($rows | Where-Object { -not $_.Result })

# 결과에는 있는데 매핑에 없는 항목 (오타·케이스명 변경 탐지)
$mapKeys = @{}; foreach ($m in $map) { $mapKeys["$($m.yaml)`u{1}$($m.case)"] = $true }
$orphan = @($res | Where-Object { -not $mapKeys.ContainsKey("$($_.yaml)`u{1}$($_.case)") })

Write-Host ""
Write-Host "매핑 $($rows.Count)행 / 결과 반영 $($hit.Count)행 / 결과 없음 $($miss.Count)행" -ForegroundColor Cyan
if ($orphan.Count) {
  Write-Host "[경고] 매핑에 없는 결과 $($orphan.Count)건 — 케이스명 확인 필요:" -ForegroundColor Yellow
  $orphan | ForEach-Object { Write-Host "   $($_.yaml)  $($_.case)" -ForegroundColor Yellow }
}

# ── 붙여넣기용 블록 (연속 행끼리 묶는다. 빈 셀로 기존 값을 덮지 않도록 결과 있는 행만) ──
$blocks = @(); $cur = $null
foreach ($r in $hit) {
  if ($cur -and $r.Row -eq $cur.End + 1) { $cur.End = $r.Row; $cur.Vals += $r.Result }
  else {
    if ($cur) { $blocks += $cur }
    $cur = [pscustomobject]@{ Start = $r.Row; End = $r.Row; Vals = @($r.Result) }
  }
}
if ($cur) { $blocks += $cur }

$sb = [Text.StringBuilder]::new()
[void]$sb.AppendLine("# 마스터 $Sheet 시트 $Col 열에 아래 블록을 각각 붙여넣는다.")
[void]$sb.AppendLine("# 결과가 있는 행만 담았다 — 빈 셀로 기존 값을 덮어쓰지 않는다.")
[void]$sb.AppendLine("# 붙여넣기 전 '값만 붙여넣기'(Ctrl+Alt+V → 값)를 쓸 것. 서식이 밀리지 않는다.")
[void]$sb.AppendLine("")
foreach ($b in $blocks) {
  [void]$sb.AppendLine("=== $Col$($b.Start):$Col$($b.End)  ($($b.Vals.Count)행) ===")
  foreach ($v in $b.Vals) { [void]$sb.AppendLine($v) }
  [void]$sb.AppendLine("")
}
Write-Utf8 "$PSScriptRoot\paste_$Col.txt" $sb.ToString()
Write-Host "붙여넣기용 블록 $($blocks.Count)개 -> paste_$Col.txt" -ForegroundColor Green

# ── 대조표 (행 정렬이 맞는지 눈으로 확인하는 용도) ──
$tsv = [Text.StringBuilder]::new()
[void]$tsv.AppendLine("Row`tResult`tYaml`tCase")
foreach ($r in $rows) { [void]$tsv.AppendLine("$($r.Row)`t$($r.Result)`t$($r.Yaml)`t$($r.Case)") }
Write-Utf8 "$PSScriptRoot\preview_$Col.tsv" $tsv.ToString()
Write-Host "대조표 -> preview_$Col.tsv" -ForegroundColor Green

if ($WhatIfOnly) { Write-Host "`n-WhatIfOnly: 작업본에는 기입하지 않았다." -ForegroundColor Yellow; return }

# ── 작업본에 기입 (Excel COM — openpyxl 은 스레드 댓글·customXml·조건부서식을 파괴한다) ──
$bak = "$Book.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $Book $bak -Force
Write-Host "`n작업본 백업: $(Split-Path $bak -Leaf)" -ForegroundColor DarkGray

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open($Book)
  $ws = $wb.Worksheets.Item($Sheet)
  foreach ($r in $hit) { $ws.Range("$Col$($r.Row)").Value2 = $r.Result }
  $wb.Save(); $wb.Close($true)
  Write-Host "작업본 기입 완료: $($hit.Count)셀 -> $Col" -ForegroundColor Green
}
finally {
  $xl.Quit()
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
  [GC]::Collect()
}
