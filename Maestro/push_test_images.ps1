# push_test_images.ps1
# 갤러리 의존 케이스(신분증/ARC/여권 업로드, QR 스캔)를 돌리기 전에 실행한다.
#
# 왜 필요한가 (2026-08-20 사고):
#   `25_Profile_old [01-7]` / `25_Profile_Foreign_old [F-01][F-02]` 는 사진 피커에서
#   **`icon_thumbnail` index**로 이미지를 고른다. 그 인덱스는 "테스트 이미지 4장이
#   갤러리 최신 4개"라는 전제에 기대고 있다.
#   두 yaml 헤더에는 "run_test.ps1이 매 실행 직전 4장을 push한다"고 적혀 있었지만
#   **run_test.ps1에는 push 로직이 아예 없다**(env 파싱 + maestro 실행뿐). 기록이 틀렸다.
#   그 사이 08_MyQR이 저장한 `gmeqr (N).jpg`가 26장까지 쌓여 최신 앞자리를 차지했고,
#   index 1이 ARC가 아니라 **QR 이미지**가 되어 앱이
#   "OCR이 유효하지 않습니다"로 업로드를 거부했다.
#
# 무엇을 하는가:
#   Test Files\ 의 4장을 /sdcard/Pictures 로 push하고 **오래된 것부터 touch**해서
#   최신순 인덱스를 고정한 뒤, MediaStore에 개별 스캔시킨다.
#     index 0 = Global QR / 1 = ARC / 2 = ID Card(주민등록증) / 3 = Passport
#
#   ⚠️ 디렉터리 단위 MEDIA_SCANNER_SCAN_FILE 브로드캐스트는 먹지 않는다 —
#     **파일 하나씩** 스캔해야 피커 목록에 반영된다(2026-08-20 실측).
#   ⚠️ 피커가 이미 열려 있으면 목록이 캐시된 상태다 → 닫고 다시 열어야 보인다.
#
# 사용:
#   .\push_test_images.ps1                 # 기기 자동 감지
#   .\push_test_images.ps1 -serial <시리얼>

param(
    [string]$serial = ""
)

$srcDir = Join-Path $PSScriptRoot "Test Files"
if (-not (Test-Path $srcDir)) {
    Write-Error "Test Files 폴더가 없습니다: $srcDir"
    exit 1
}

if (-not $serial) {
    $serial = (adb devices | Select-String "device$" | ForEach-Object { ($_ -split "\s+")[0] } | Select-Object -First 1)
}
if (-not $serial) {
    Write-Error "연결된 기기가 없습니다. adb devices 를 확인하세요."
    exit 1
}
Write-Host "DEVICE = $serial"

# 오래된 것 → 최신 순서로 넣는다. 최신이 index 0 이 된다.
$order = @(
    "2. Passport.jpg",        # index 3
    "1. ID Card_Korean.jpg",  # index 2
    "3. ARC.jpg",             # index 1
    "Global QR.jpg"           # index 0
)

foreach ($f in $order) {
    $local = Join-Path $srcDir $f
    if (-not (Test-Path $local)) { Write-Error "이미지 없음: $local"; exit 1 }
    adb -s $serial push $local "/sdcard/Pictures/$f" | Out-Null
    # push는 로컬 mtime을 그대로 가져올 수 있어 순서가 흔들린다 → touch로 현재 시각으로 고정
    adb -s $serial shell "touch '/sdcard/Pictures/$f'"
    Write-Host "  pushed  $f"
    Start-Sleep -Seconds 2   # mtime 이 겹치지 않게 간격을 둔다
}

# MediaStore 반영 — 파일 단위로 스캔해야 한다
foreach ($f in $order) {
    $enc = $f -replace ' ', '%20'
    adb -s $serial shell "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d 'file:///sdcard/Pictures/$enc'" | Out-Null
}
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "=== MediaStore 최신순 (index 0 부터) ==="
adb -s $serial shell "content query --uri content://media/external/images/media --projection _display_name --sort 'date_modified DESC'" 2>$null |
    Select-Object -First 4 | ForEach-Object { $_ }
