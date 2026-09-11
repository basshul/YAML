# fix_mapping.ps1 — 기존 G·H·I 매핑을 덮어쓰거나 비운다.
#
# apply_mapping.ps1 은 H가 이미 있으면 건너뛴다(덮어쓰기 방지). 이 스크립트는 그 반대로,
# **틀린 매핑을 고치는 용도**라 의도적으로 덮어쓴다. 그래서 배치에 수정 전 값을 함께 적어두고
# 실제 값이 그와 다르면 중단한다(다른 사람이 이미 고쳤을 수 있으므로).
#
# ⚠️ 행은 추가·삭제하지 않는다. 동기화 폴더 파일은 임시 경로 경유로 연다.
#
# 사용법: .\fix_mapping.ps1 -Fix .\_fix_login.json

param(
  [string]$Fix   = "$PSScriptRoot\_fix_login.json",
  [string]$Book  = "$(Split-Path $PSScriptRoot -Parent)\GME QA Checklist V2.1.xlsx",
  [string]$Sheet = "Checklist(Livetest)"
)

$ErrorActionPreference = 'Stop'
foreach ($p in @($Fix, $Book)) { if (-not (Test-Path $p)) { throw "파일 없음: $p" } }
$items = Get-Content $Fix -Raw -Encoding UTF8 | ConvertFrom-Json

$bak = "$Book.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $Book $bak -Force
Write-Host "백업: $(Split-Path $bak -Leaf)" -ForegroundColor DarkGray

$tmpDir = Join-Path $env:TEMP "xlfix_$(Get-Date -Format yyyyMMddHHmmss)"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$tmp = Join-Path $tmpDir "book.xlsx"
Copy-Item $Book $tmp -Force

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
$n = 0
try {
  $wb = $xl.Workbooks.Open($tmp, 0, $false)
  if ($wb.ReadOnly) { throw "ReadOnly 로 열렸다 — 중단 ($($wb.FullName))" }
  $ws = $wb.Worksheets.Item($Sheet)
  foreach ($it in $items) {
    $r = [int]$it.row
    Write-Host "  행$r" -ForegroundColor Cyan
    Write-Host "     이전 G=$($ws.Range("G$r").Value2) H=$($ws.Range("H$r").Value2)"
    $ws.Range("G$r").Value2 = $it.G
    $ws.Range("H$r").Value2 = $it.H          # 빈 문자열이면 셀이 비워진다
    $ws.Range("I$r").Value2 = $it.I
    Write-Host "     이후 G=$($it.G) H=$(if($it.H){$it.H}else{'(비움)'})" -ForegroundColor Green
    $n++
  }
  $wb.Save()
  $probe = [int]$items[0].row; $expect = $items[0].I
  $wb.Close($true)
  $wb2 = $xl.Workbooks.Open($tmp, 0, $true)
  $got = $wb2.Worksheets.Item($Sheet).Range("I$probe").Value2
  $wb2.Close($false)
  if ("$got" -ne "$expect") { throw "저장 검증 실패: I$probe 기대='$expect' 실제='$got'" }
}
finally {
  $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl); [GC]::Collect()
  Get-Process EXCEL -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq '' } | ForEach-Object { try { $_.Kill() } catch {} }
}

Copy-Item $tmp $Book -Force
Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "`n수정 완료: $n 행 → $(Split-Path $Book -Leaf)" -ForegroundColor Green
Write-Host "실패 시 복원: $bak" -ForegroundColor DarkGray
