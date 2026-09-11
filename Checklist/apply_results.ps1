# apply_results.ps1 — 실행 결과를 체크리스트에 기입한다.
#
# ⚠️ 행은 추가·삭제하지 않는다. 열도 삽입하지 않는다. 기존 셀에 값만 쓴다.
# ⚠️ 동기화 폴더 파일은 Excel이 SharePoint URL로 매핑해 ReadOnly로 열고 Save()를 조용히 무시한다
#    → 비동기화 임시 경로로 복사해 작업한 뒤 되돌려놓는다.
#
# 기본 대상은 **작업본**이다. 마스터에 쓰려면 -Book 으로 명시해야 한다.
#
# 사용법:
#   .\apply_results.ps1 -Draft .\_draft_20260828.json
#   .\apply_results.ps1 -Draft .\_draft_20260828.json -ResultCol BB -CommentCol BC

param(
  [string]$Draft      = "$PSScriptRoot\_draft_20260828.json",
  [string]$Book       = "$PSScriptRoot\GME QA Checklist V2.1_WORK.xlsx",
  [string]$Sheet      = "Checklist(Livetest)",
  [string]$ResultCol  = "BB",
  [string]$CommentCol = "BC",
  [switch]$SkipHeader
)

$ErrorActionPreference = 'Stop'
foreach ($p in @($Draft, $Book)) { if (-not (Test-Path $p)) { throw "파일 없음: $p" } }
$d = Get-Content $Draft -Raw -Encoding UTF8 | ConvertFrom-Json

$bak = "$Book.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $Book $bak -Force
Write-Host "백업: $(Split-Path $bak -Leaf)" -ForegroundColor DarkGray

$tmpDir = Join-Path $env:TEMP "xlres_$(Get-Date -Format yyyyMMddHHmmss)"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$tmp = Join-Path $tmpDir "book.xlsx"
Copy-Item $Book $tmp -Force

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
$nRes = 0; $nCmt = 0
try {
  $wb = $xl.Workbooks.Open($tmp, 0, $false)
  if ($wb.ReadOnly) { throw "ReadOnly 로 열렸다 — 중단 ($($wb.FullName))" }
  $ws = $wb.Worksheets.Item($Sheet)

  if (-not $SkipHeader -and $d.header) {
    $ws.Range($d.header.cell).Value2 = $d.header.value
    Write-Host "헤더 갱신: $($d.header.cell)" -ForegroundColor Cyan
  }
  foreach ($r in $d.results) {
    $cell = "$ResultCol$($r.row)"
    if ($ws.Range($cell).Value2) { Write-Host "  건너뜀 $cell — 이미 값 있음: $($ws.Range($cell).Value2)" -ForegroundColor Yellow; continue }
    $ws.Range($cell).Value2 = $r.value; $nRes++
  }
  foreach ($c in $d.comments) {
    $cell = "$CommentCol$($c.row)"
    if ($ws.Range($cell).Value2) { Write-Host "  건너뜀 $cell — 이미 코멘트 있음" -ForegroundColor Yellow; continue }
    $ws.Range($cell).Value2 = $c.value; $nCmt++
  }
  $wb.Save()
  # 저장이 파일에 반영됐는지 재확인
  $probe = "$ResultCol$($d.results[0].row)"; $expect = $d.results[0].value
  $wb.Close($true)
  $wb2 = $xl.Workbooks.Open($tmp, 0, $true)
  $got = $wb2.Worksheets.Item($Sheet).Range($probe).Value2
  $wb2.Close($false)
  if ("$got" -ne "$expect") { throw "저장 검증 실패: $probe 기대='$expect' 실제='$got'" }
}
finally {
  $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl); [GC]::Collect()
  Get-Process EXCEL -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq '' } | ForEach-Object { try { $_.Kill() } catch {} }
}

Copy-Item $tmp $Book -Force
Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "기입 완료: 결과 $nRes 셀 / 코멘트 $nCmt 셀 → $(Split-Path $Book -Leaf)" -ForegroundColor Green
Write-Host "실패 시 복원: $bak" -ForegroundColor DarkGray
