# apply_mapping.ps1 — 자동화 사본의 G·H·I 를 배치 JSON대로 채운다.
#
# ⚠️ 행은 절대 추가·삭제하지 않는다. 기존 셀에 값만 쓴다.
#
# ⚠️ 동기화 폴더의 파일을 Excel COM으로 직접 열면 Excel이 경로를 SharePoint URL로 매핑해
#    ReadOnly 로 열어버리고, 그 상태에서 Save() 는 조용히 무시된다(성공처럼 보인다).
#    → 비동기화 임시 경로로 복사해 작업한 뒤 되돌려놓는다. ReadOnly 면 즉시 중단한다.
#
# 사용법: .\apply_mapping.ps1 -Batch .\_fill_batch1.json

param(
  [string]$Batch = "$PSScriptRoot\_fill_batch1.json",
  [string]$Book  = "$(Split-Path $PSScriptRoot -Parent)\GME QA Checklist V2.1.xlsx",
  [string]$Sheet = "Checklist(Livetest)",
  [string]$Cover = "완전"
)

$ErrorActionPreference = 'Stop'
foreach ($p in @($Batch, $Book)) { if (-not (Test-Path $p)) { throw "파일 없음: $p" } }

$items = Get-Content $Batch -Raw -Encoding UTF8 | ConvertFrom-Json
$bak   = "$Book.bak_$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $Book $bak -Force
Write-Host "백업: $(Split-Path $bak -Leaf)" -ForegroundColor DarkGray

# 비동기화 임시 경로로 복사
$tmpDir = Join-Path $env:TEMP "xlfill_$(Get-Date -Format yyyyMMddHHmmss)"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$tmp = Join-Path $tmpDir "book.xlsx"
Copy-Item $Book $tmp -Force

$nBlocked = @($items | Where-Object { $_.blocked }).Count
Write-Host "기입 대상 $($items.Count)행 (G 갱신 $($items.Count - $nBlocked)행 / BLOCKED $nBlocked 행은 G 유지)" -ForegroundColor Cyan

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
$wrote = 0
try {
  $wb = $xl.Workbooks.Open($tmp, 0, $false)
  if ($wb.ReadOnly) { throw "ReadOnly 로 열렸다 — 기입 중단 (경로: $($wb.FullName))" }
  $ws = $wb.Worksheets.Item($Sheet)
  foreach ($it in $items) {
    $r = [int]$it.row
    if ($ws.Range("H$r").Value2) {
      Write-Host "  건너뜀 행$r — 이미 H 있음: $($ws.Range("H$r").Value2)" -ForegroundColor Yellow
      continue
    }
    $ws.Range("H$r").Value2 = $it.H
    $ws.Range("I$r").Value2 = $it.I
    if (-not $it.blocked) { $ws.Range("G$r").Value2 = $Cover }
    $wrote++
  }
  $wb.Save()
  # 저장이 실제로 반영됐는지 메모리가 아니라 파일로 확인
  $probe = [int]$items[0].row
  $expect = $items[0].H
  $wb.Close($true)
  $wb2 = $xl.Workbooks.Open($tmp, 0, $true)
  $got = $wb2.Worksheets.Item($Sheet).Range("H$probe").Value2
  $wb2.Close($false)
  if ("$got" -ne "$expect") { throw "저장 검증 실패: H$probe 기대='$expect' 실제='$got'" }
}
finally {
  $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl); [GC]::Collect()
}

Copy-Item $tmp $Book -Force
Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "기입 완료: $wrote 행 (원본 반영됨)" -ForegroundColor Green
Write-Host "실패 시 복원: $bak" -ForegroundColor DarkGray
