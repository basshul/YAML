# ================================================================
# run_suite.ps1 — 구 UI(Old) 회귀 스위트 실행기  (2026-09-02 재작성)
#
#   .\run_suite.ps1 -List                      # 실행 계획 + 예상 소요만 출력
#   .\run_suite.ps1                            # 기본 = G1,G2,G3,G4 (G9 파괴적 제외)
#   .\run_suite.ps1 -Group G1                  # 그룹만
#   .\run_suite.ps1 -Balance 12000             # 잔액을 알려준다 → 모자라면 자동 충전(아래 ③)
#   .\run_suite.ps1 -Balance 1000 -AutoCharge  # ⚠️ 자동 충전 시도(미검증 — OTP로 막힐 수 있다)
#   .\run_suite.ps1 -Resume                    # 마지막 실행에서 못 끝낸 그룹부터
#   .\run_suite.ps1 -Names 08_MyQR,03_Domestic -AppId com.gmeremit.online.gmeremittance_native.stag
#
# ── 축: **계정/로그인 상태** ───────────────────────────────────
#   기능별로 섞으면 계정 전환이 9회 반복된다. 구 UI 전환은 드로어 로그아웃 → PIN 잠금화면
#   → `loginpwidhidpass` → **PIN 재등록**까지 3~4분이 든다. 계정별로 묶으면 **전환 2회**로 끝난다.
#     G1 로그인 불필요 → G2 한국인(seungsoo818) → G3 외국인(test123→test251024)
#     → G4 설정 변경(자기 원복형이지만 실패 시 뒤를 오염시킨다 → 맨 뒤) → G9 파괴적
#
# ── `est`(예상 소요)는 어디서 왔나 ───────────────────────────
#   2026-09-11 전수 대조: `suite_logs\*\SUMMARY.md` 의 **PASS 행 소요**를 모아
#   `ceil(실측 최대 × 1.1)` 로 다시 매겼다(21항목 수정 / 9항목 유지).
#   ⚠️ 손으로 적은 값은 **믿을 게 못 된다**: `11_IntlTopup` 4분(실측 9.5) ·
#      `25_Profile` 6분(실측 10.2) · `20_Booking` 5분(실측 8.6) 처럼 절반 이하로
#      적혀 있었고, 반대로 `06_Registration` 28분(실측 17.6) 처럼 부풀려진 것도 있었다.
#   ⛔ **실측이 없는 11항목은 손으로 적은 값 그대로다** — 완주 PASS 기록이 없다:
#      08_MyQR · 10_DomesticTopup · 03_Domestic · 16_ATMWithdraw · 02_01_Overseas_SendNow ·
#      21_Card · 04_06/04_01/04_02_Change_* · 01_04/01_05(G9).
#      돌려서 PASS가 남으면 같은 방식으로 갱신할 것(대조 스크립트는 일회성이라 남기지 않았다).
#   ※ 플로우를 크게 손보면 실측도 낡는다 — 케이스를 추가/삭제했으면 다음 완주 후 다시 맞춘다.
#
# ── 확정된 결정 4건 ───────────────────────────────────────────
#   ① 범위 = 전부 포함(실결제·계정소모까지). 단 **G9는 기본 세트에서 뺀다** — admin 개입이 필요하다.
#   ② 실패 시 = 계속 + 자동 복구(`_suite_recover_old.yaml`).
#      ⚠️ **복구가 2회 연속 실패하면 중단**한다. 안 그러면 남은 항목이 전부 FAIL로 찍히고
#         몇 시간이 날아간다.
#   ③ 잔액 = 부족하면 **SKIP + 리포트에 "잔액 부족" 명시**(코드 결함 FAIL과 갈라 보이게).
#      ⛔ **자동 충전은 기본 꺼짐**(2026-09-03). KFTC 계좌에서 자금을 끌어오려면 **OTP/생체인증**이
#         필요해 자동화로는 입금이 완주되지 않는다(`02_02` 헤더에 같은 취지가 이미 적혀 있었다).
#         `_suite_charge_old.yaml`은 만들어 뒀지만 **완주 확인 전이다** → `-AutoCharge`로 명시할 때만 쓴다.
#         잔액은 **사람이 미리 채우는 게 정석**이다.
#      ⚠️ **잔액을 자동으로 읽지 못한다** — 구 UI 홈은 잔액을 `XXX,XXX`로 마스킹한다.
#         그래서 `-Balance <원>`으로 **사람이 넘긴다.** 생략하면 게이트 없이 그냥 돌고
#         리포트에 "잔액 미확인"으로 남는다.
#   ④ **준비 상태는 검사하지 않는다.** 회원가입을 실제로 해보기 전에는 계정 존재 여부를 알 수 없다.
#      모든 케이스를 돌릴 수 있는 상태를 전제하고 실행한다 — 준비가 안 된 실행은 휴먼 에러다.
#      → `test006/test007` 존재·픽스처 같은 게이트를 넣지 않는다. 사람용 체크리스트는 ENVIRONMENT.md.
#
# 왜 폴더 통째 실행(`maestro test Old\`)을 쓰지 않는가:
#   ① 순서가 곧 상태 의존성이다  ② `_*.yaml` 헬퍼와 다른 빌드 파일까지 딸려 들어간다
#   ③ 계정을 소모하거나 실결제가 나가는 플로우를 기본에서 빼야 한다
# ================================================================
param(
    [string]$Lang = "ko",
    [string[]]$Group = @("G1", "G2", "G3", "G4"),
    [string]$From = "",
    [string]$Only = "",
    [string[]]$Names = @(),
    [int]$Balance = -1,
    [switch]$Resume,
    [switch]$StopOnFail,
    [switch]$NoRecover,
    [switch]$SkipLint,
    [switch]$List,
    [string]$Device = "",
    [ValidateSet("stag","live")][string]$Build = "stag",
    [switch]$AutoCharge,        # 잔액이 모자라면 자동 충전한다 — ⚠️ **미검증**(아래 ③ OTP 참고)
    [int]$MaxCharge = 30000,    # 자동 충전 총액 상한(실계좌에서 빠진다). -AutoCharge 없으면 무의미
    [string]$AppId = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandArgumentPassing = 'Legacy'   # env 값의 | 가 cmd 파이프로 해석되는 사고 방지
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# ----------------------------------------------------------------
# 스위트 정의
#   g     : 그룹(G1/G2/G3/G9)
#   acct  : 이 항목이 전제하는 계정
#   est   : 실측 소요(분). -List 가 누적 시간을 찍어 "언제 끝나는지" 알고 시작하게 한다
#   needs : 실행 전 성립해야 하는 조건. 깨지면 FAIL이 아니라 **SKIP**이다
#   push  : 실행 직전 push_test_images.ps1 필요(갤러리 index 의존)
#   blocked/na : 케이스 단위로 이미 알려진 제외분(리포트에 숫자로 표시)
# ----------------------------------------------------------------
$Suite = @(
  # ── G1 로그인 불필요 ───────────────────────────────────────────
  @{ n="05_InitialScreen";        g="G1"; acct="-";           est=5;  f="Old\05_InitialScreen_old.yaml"
     note="clearState — 로그아웃 상태에서 시작한다" }
  @{ n="06_Registration";         g="G1"; acct="-";           est=20; f="Old\06_Registration_old.yaml"; push=$true
     note="⚠️ 비멱등 — test006/test007을 소모한다. 원복 꼬리는 주석 처리돼 test006 로그인 상태로 끝난다" }
  @{ n="01_03_Login_screen_safe"; g="G1"; acct="-";           est=3;  f="Old\01_03_Login_screen_safe_old.yaml"
     note="[01]~[05] 비파괴. clearState라 앞 항목의 test006 세션을 정리한다" }
  @{ n="01_01_Login_Success";     g="G1"; acct="seungsoo818"; est=3;  f="Old\01_01_Login_Success_old.yaml"
     note="G2의 세션을 여기서 만든다" }
  @{ n="01_02_Login_Wrong_SimplePassword"; g="G1"; acct="seungsoo818"; est=4;  f="Old\01_02_Login_Wrong_SimplePassword_old.yaml"
     note="PIN 5회 오입력 → 로그아웃 → [04][05]가 자가복구 → 로그인 상태로 G2에 인계" }

  # ── G2 한국인 (부작용 없는 것부터) ─────────────────────────────
  @{ n="09_Home";                 g="G2"; acct="seungsoo818"; est=9;  f="Old\09_Home_old.yaml" }
  @{ n="07_TodaysRate";           g="G2"; acct="seungsoo818"; est=4;  f="Old\07_TodaysRate_old.yaml"
     note="진입 시 USD 계산오류 다이얼로그를 먼저 닫는다" }
  @{ n="15_Loan";                 g="G2"; acct="seungsoo818"; est=2;  f="Old\15_Loan_old.yaml"
     note="⚠️ seungsoo818이 **한국인일 때만** 통과 → G3 뒤로 밀리면 안 된다" }
  @{ n="26_Menu";                 g="G2"; acct="seungsoo818"; est=8;  f="Old\26_Menu_old.yaml"
     note="Settings + LinkBank(KFTC) 포함, 20케이스" }
  @{ n="17_WalletStatement";      g="G2"; acct="seungsoo818"; est=3;  f="Old\17_WalletStatement_old.yaml"
     note="잔액 로딩 최대 90초" }
  # ── 13 → 04 순서 고정 (2026-09-04 사용자 지시) ────────────────
  #   `04`의 인바운드 구간([16]~[19])은 **송금 받기 데이터가 있어야** 실검증이 된다.
  #   데이터가 0건이면 필터·검색이 죽어 있어도 통과한다(빈 목록에서는 "조회된 거래가
  #   없습니다"가 항상 뜨고, 탭 제목 assert도 항상 맞는다) — 거짓 통과다.
  #   `13 [12]`가 인바운드 Request를 등록해 그 데이터를 만든다 → **13이 반드시 앞에 온다.**
  #   ⚠️ 등록은 간헐적으로 IBST0003으로 실패한다. 그래서 04는 데이터 유무를 **갈라 판정**하며,
  #      13이 실패해도 04가 무너지지는 않는다(검증 범위만 줄어든다).
  # ── 13은 2026-09-07에 **7개로 분할**됐다 (사용자 지시) ────────────
  #   통짜는 약 42분이라 **10분 포그라운드 한도**를 넘겨 백그라운드로 전환되고, 그 뒤 외부에서
  #   종료되는 일이 반복됐다(9/7 실측: 전환 7건 중 6건 종료 / 10분 미만 실행은 전부 완주).
  #   → 각 조각이 10분 안에 끝나도록 잘랐다. 합계 약 48분(공통 진입이 1회→7회라 +6분).
  #   ⚠️ **순서 의존이 강하다 — 13_01~13_07을 이 순서대로 돌려야 한다.**
  #     01~03이 송금인 3국 등록 → 04가 **인도네시아**로 요청 신청 → 05가 **베트남** 정보 수정
  #     → 06이 송금인 전부 삭제 → 07은 04가 만든 **요청** 상태를 본다(송금인 무관).
  #   ⛔ 원본 `13_ReceiveOverseas_old.yaml` 은 분할본과 **중복**이므로 넣지 않는다
  #     (`14_Deposit_old.yaml` 이 `14_01/02/03` 과 중복이라 제외된 것과 같다).
  @{ n="13_01_Rate_Indonesia";    g="G2"; acct="seungsoo818"; est=6;  f="Old\13_01_Rate_Indonesia_old.yaml"
     note="[01]~[07] 환율 5케이스 + 인도네시아 송금인 등록(이 사슬의 시작)" }
  @{ n="13_02_Sender_Mongolia";   g="G2"; acct="seungsoo818"; est=5;  f="Old\13_02_Sender_Mongolia_old.yaml"
     note="[07-1] 몽골 등록 — 14필드 + 신분증 사진 3종(앱 내 촬영, 갤러리 픽스처 불필요)" }
  @{ n="13_03_Sender_Vietnam";    g="G2"; acct="seungsoo818"; est=5;  f="Old\13_03_Sender_Vietnam_old.yaml"
     note="[07-2] 베트남 등록 — 사진 3종. **등록만 하고 남긴다**(13_05가 쓴다)" }
  @{ n="13_04_Request";           g="G2"; acct="seungsoo818"; est=7;  f="Old\13_04_Request_old.yaml"
     note="[08]~[12] 인도네시아 송금요청 Confirm 실등록. **04_Menu_History의 인바운드 데이터를 여기서 만든다**" }
  @{ n="13_05_ExistingSender";    g="G2"; acct="seungsoo818"; est=7;  f="Old\13_05_ExistingSender_old.yaml"
     note="[13] 삭제 동작 + [14] 베트남 정보 수정. edit 아이콘은 **'승인 대기 중' 행에만** 뜬다 → 13_03 필수" }
  @{ n="13_06_PurgeSenders";      g="G2"; acct="seungsoo818"; est=3;  f="Old\13_06_PurgeSenders_old.yaml"
     note="등록된 송금인 일괄 삭제(사양). **반드시 13_05 뒤** — 먼저 지우면 04/05가 쓸 데이터가 사라진다. 잔재가 더 있으면 FAIL로 드러난다(수동 정리)" }
  @{ n="13_07_RequestStatus";     g="G2"; acct="seungsoo818"; est=5;  f="Old\13_07_RequestStatus_old.yaml"
     note="[15]~[20] 요청 상태. 13_04가 만든 Request(72시간 만료)가 전제. 송금인과 무관해 13_06 뒤여도 성립" }
  @{ n="04_Menu_History";         g="G2"; acct="seungsoo818"; est=13; f="Old\04_Menu_History_old.yaml"
     # 2026-09-04: **130([17] 인바운드 상세) BLOCKED 해제** — 13이 데이터를 만들면서 진입 가능해졌다.
     #   131([18] 인바운드 이력 다운로드)은 저장소 권한 앱버그라 그대로 BLOCKED다.
     blocked=@("115","117","122","127","131","135","138"); na=@("149","150","151")
     note="48케이스. 이력 다운로드 계열은 저장소 권한 앱버그로 BLOCKED. 인바운드 구간은 13 선행 전제" }
  @{ n="18_Telecom";              g="G2"; acct="seungsoo818"; est=3;  f="Old\18_Telecom_old.yaml"
     blocked=@("05","06","07"); note="[05]~[07]은 요금제 상품 미등록으로 BLOCKED" }
  @{ n="19_IssueCertificate";     g="G2"; acct="seungsoo818"; est=5;  f="Old\19_IssueCertificate_old.yaml"
     note="WeCheck 인증수단 선택까지. ⚠️ livetest:id 정리 후 stag 재검증 미완" }
  @{ n="22_Event";                g="G2"; acct="seungsoo818"; est=3;  f="Old\22_Event_old.yaml"
     note="Compose UI라 id 없음" }
  @{ n="25_Profile";              g="G2"; acct="seungsoo818"; est=12; f="Old\25_Profile_old.yaml"; push=$true
     note="⚠️ 실 Gmail 주소가 코드에 있다 — 공유 전 교체(ENVIRONMENT.md §3.5)" }
  # ── 14_01은 잔액을 쓰지도 만들지도 않는다 → 돈 쓰는 구간 **앞**에 둔다 (2026-09-03 사용자 지시) ──
  #   ⚠️ 이 파일이 "충전 플로우"라서 앞으로 당긴 게 아니다. **충전하지 않는다**:
  #      [27] 자동이체는 금액만 입력하고 표시 확인 후 back(확인·PIN 없음) /
  #      [02][05] 가상계좌는 번호 표시만 / [28][29] 편의점 입금은 10분 뒤 만료되는 요청이다.
  #      실충전은 아래 **자동 충전 단계**(`_suite_charge_old.yaml`)가 맡는다.
  @{ n="14_01_Deposit";           g="G2"; acct="seungsoo818"; est=8;  f="Old\14_01_Deposit_seungsoo818_old.yaml"
     note="Wallet/GMEPay/AutoDebit. 계좌는 목록에서 동적 선택한다" }

  # ── 여기부터 돈이 움직인다 ──
  @{ n="08_MyQR";                 g="G2"; acct="seungsoo818"; est=10; f="Old\08_MyQR_old.yaml"; push=$true
     needs=@{ balance=2000 }; note="1원 송금 완주 포함. 카카오뱅크는 [05][06] 실송금 조합이라 고정" }
  @{ n="10_DomesticTopup";        g="G2"; acct="seungsoo818"; est=4;  f="Old\10_DomesticTopup_old.yaml"
     needs=@{ balance=1000 }
     note="[04]는 **거부 동작이 케이스 정의**(테스트 번호가 선불폰 아님) → 실자금 이동 없음. 실패응답 최대 3분" }
  @{ n="03_Domestic";             g="G2"; acct="seungsoo818"; est=12; f="Old\03_Domestic_old.yaml"
     needs=@{ balance=3000 }
     note="⚠️ [03]은 타인 은행계좌라 **수수료 1,000원 이상**. 1,006원으로는 막혔다(2026-09-01 실측)" }
  @{ n="16_ATMWithdraw";          g="G2"; acct="seungsoo818"; est=4;  f="Old\16_ATMWithdraw_old.yaml"
     needs=@{ balance=13000 }; note="취소 재시도 루프 필수 + 내역 사후검증" }
  @{ n="02_01_Overseas_SendNow";  g="G2"; acct="seungsoo818"; est=8;  f="Old\02_01_Overseas_Send now_old.yaml"
     needs=@{ balance=15000 }
     note="⚠️ 최소 송금액이 **환율 연동**이라 임계값은 추정치다. `GME TEST`를 남겨야 02_02가 성립" }
  @{ n="02_02_Overseas_Schedule"; g="G2"; acct="seungsoo818"; est=16; f="Old\02_02_Overseas_Schedule_old.yaml"
     note="예약 등록/취소만, 실결제 없음. **02_01 직후여야 한다**" }
  @{ n="20_Booking";              g="G2"; acct="seungsoo818"; est=10; f="Old\20_Booking_old.yaml"
     irreversible=$true; note="🔴 실결제 + 자동취소. 날짜는 최대한 먼 미래로(취소 수수료)" }
  # ⚠️ est 8 → 30 (2026-09-11). 종전 8분은 **신청 블록이 조용히 SKIP되던 실행**을 잰 값이다
  #   ([01]의 가드가 전체매칭으로 안 맞아 [01]~[10]이 통째로 건너뛰어졌다). 실기기 실측:
  #   진입+[01]~[09] 약 7분 / [07]~[10] 약 4분 / [11][12] 약 4분 + [13]~[22]·[23]~[33-1].
  # ⚠️ push=$true 신설 — [24] Global QR이 갤러리 픽스처에 의존하는데 빠져 있었다.
  # ⚠️ needs.balance=3000 신설 — [33-1]이 CU 3,000원 쿠폰을 실제로 구매(후 취소)한다.
  #   잔액이 모자라면 **실계좌 자동충전**이 일어나므로 SKIP으로 갈라내는 게 맞다.
  @{ n="21_Card";                 g="G2"; acct="seungsoo818"; est=30; f="Old\21_Card_old.yaml"; push=$true
     irreversible=$true; needs=@{ balance=3000 }
     note="🔴 [01]~[06]이 **실제 카드 신청을 접수**하고 [10]이 취소해 원복한다 — 중간에 끊기면 신청이 남아 손으로 취소해야 한다. [12]는 카드 PIN을 바꿨다 되돌리므로 끊기면 대체 PIN으로 남는다([11]의 폴백이 1회 받아준다). 잔액부족 시 GME Shop 구매하기에서 **실계좌 자동충전**이 일어난다. [24]는 갤러리 픽스처(Global QR.jpg) 의존." }
  @{ n="11_IntlTopup";            g="G2"; acct="seungsoo818"; est=11; f="Old\11_IntlTopup_old.yaml"
     irreversible=$true; note="🔴 실결제·**취소 불가** → 돌릴 때마다 금액이 누적된다" }
  @{ n="12_BillPayment";          g="G2"; acct="seungsoo818"; est=5;  f="Old\12_BillPayment_old.yaml"
     irreversible=$true; note="🔴 실결제·취소 불가. btn_save_biller는 누르면 안 된다" }

  # ── G3 외국인 (계정 2개, 순서 고정) ────────────────────────────
  @{ n="14_02_Deposit";           g="G3"; acct="test123";     est=11; f="Old\14_02_Deposit_test123_old.yaml"
     note="ATM/Store Deposit. [29] 편의점 입금 요청은 10분 만료" }
  @{ n="25_Profile_Foreign";      g="G3"; acct="test123";     est=3;  f="Old\25_Profile_Foreign_old.yaml"; push=$true
     note="⛔ **계정 전환 코드가 없다** — 14_02 직후가 아니면 성립하지 않는다" }
  @{ n="14_03_Deposit";           g="G3"; acct="test251024";  est=7;  f="Old\14_03_Deposit_test251024_old.yaml"
     note="GMEPay Deposit. 끝에서 seungsoo818로 원복한다" }

  # ── G4 설정 변경 — 자기 원복형 (반드시 맨 뒤) ─────────────────
  #   셋 다 **끝에서 스스로 되돌린다.** 다만 중간에 실패하면 원복 전 상태로 남고,
  #   그 상태(외국어 / 바뀐 PIN / 바뀐 비밀번호)는 **뒤따르는 모든 항목의 진입을 깨뜨린다.**
  #   `_suite_recover_old.yaml` 은 앱 재시작·재로그인만 하므로 **이 셋은 복구하지 못한다.**
  #   → 그래서 G2(같은 seungsoo818)가 아니라 **전 그룹 뒤**에 둔다. 실패해도 오염될 것이 없다.
  #   전제: 직전 `14_03_Deposit` 이 끝에서 seungsoo818 로 원복한다. 셋 다 계정 전환 코드가 없다.
  #   순서 고정 이유: `04_01`(PIN 변경)은 인증에 **로그인 비밀번호**를 쓴다 → `04_02` 보다 먼저.
  #                  자격정보를 건드리는 둘을 뒤로 몰아 실패 시 남는 피해를 줄인다.
  @{ n="04_06_Change_Languages";  g="G4"; acct="seungsoo818"; est=25; f="Old\04_06_Settings_Change languages_old.yaml"
     note="24개 언어 순회 후 한국어 복귀. ⚠️ 중단되면 앱이 **외국어로 남아** 뒤 항목이 전부 깨진다(수동 복구 필요). est 는 추정치" }
  @{ n="04_01_Change_SimplePassword"; g="G4"; acct="seungsoo818"; est=8; f="Old\04_01_Change_SimplePassword_old.yaml"
     note="PIN 정상→대체→원복. ⚠️ 중단되면 **대체 PIN 으로 남아** 모든 진입 블록이 깨진다. env PW_CUR_LAST 는 04_02 와 함께 맞출 것" }
  @{ n="04_02_Change_LoginPassword";  g="G4"; acct="seungsoo818"; est=12; f="Old\04_02_Change_LoginPassword_old.yaml"
     note="[06]~[13] 로그인 비밀번호 변경→원복(멱등). ⚠️ [13] 이 실패하면 PW_NEW 로 남는다 → env 두 줄을 서로 바꿔 다음 실행을 맞춘다" }

  # ── G9 파괴적: admin 개입이 있어야 복구된다. 기본 세트에서 제외 ─
  @{ n="01_04_Login_Wrong_LoginPassword"; g="G9"; acct="-"; est=3; f="Old\01_04_Login_Wrong_LoginPassword_old.yaml"
     destructive="로그인 비밀번호 오입력 = **계정 잠금**. 자가복구 불가 → admin 해제 필요"
     note="CLI로 LOCK_ID/CONFIRM_LOCK 을 넘겨야 동작한다(파일 내 assertTrue 가드)" }
  @{ n="01_05_Login_Password_Reset";      g="G9"; acct="-"; est=4; f="Old\01_05_Login_Password_Reset_old.yaml"
     destructive="[06]이 **비밀번호를 실제 초기화**한다 → admin 재설정 전까지 모든 플로우가 깨진다" }
)

# ----------------------------------------------------------------
# 빌드 결정 (2026-09-03 사용자 선언)
# ----------------------------------------------------------------
#   기본       = `.stag` 빌드 + **서버는 LIVETEST 지정**
#   운영/Live  = 접미사 없는 패키지. **요청이 있을 때만** `-Build live`
#   `.livetest` 빌드는 더 이상 쓰지 않는다 — 기기에서 이미 삭제됐다(2026-09-03 adb 확인).
# ⚠️ stag 빌드는 Server Override 기본값이 **STAG**다. 각 플로우가 LIVETEST를 코드로 강제하지만
#    한 곳이라도 빠지면 **조용히 gmeuat로 돈다** → 아래 P0/조기검사/최종집계 3중으로 본다.
$BuildMap = @{
    stag = "com.gmeremit.online.gmeremittance_native.stag"
    live = "com.gmeremit.online.gmeremittance_native"
}
$EffAppId = if ($AppId) { $AppId } else { $BuildMap[$Build] }
$IsLive   = ($EffAppId -eq $BuildMap.live)

# ----------------------------------------------------------------
# 실행 계획
# ----------------------------------------------------------------
if ($Names.Count -gt 0) {
    # -Names 는 그룹을 무시하고 **적은 순서 그대로** 실행한다(우선순위 실행용).
    #   ⚠️ 순서가 곧 상태 의존성이다 — 계정을 바꾸는 항목 뒤에 그 계정을 전제하는 항목을 둘 것.
    # `pwsh -File ... -Names a,b` 처럼 **한 문자열로 넘어오는 호출**도 받아준다
    #   (-File 인자는 전부 문자열이라 `a,b`가 배열로 쪼개지지 않고 원소 1개로 바인딩된다).
    $Names = @($Names | ForEach-Object { $_ -split '\s*,\s*' } | Where-Object { $_ })
    $plan = @()
    foreach ($n in $Names) {
        $hit = $Suite | Where-Object { $_.n -eq $n }
        if (-not $hit) { $hit = $Suite | Where-Object { $_.n -like "*$n*" } }
        if (-not $hit) { Write-Error "-Names '$n' 에 해당하는 항목이 없습니다."; exit 1 }
        $plan += $hit
    }
} else {
    $plan = @($Suite | Where-Object { $Group -contains $_.g })
}
if ($Only) { $plan = @($plan | Where-Object { $_.n -like "*$Only*" -or $_.f -like "*$Only*" }) }

# -Resume: 지난 실행에서 **완주하지 못한 그룹**부터 재개한다.
#   ⚠️ 그룹 **경계에서만** 재개한다 — 계정 묶음(G3)이나 clearState 뒤 중간에서 재개하면
#      상태 전제가 깨진다.
$statePath = Join-Path $root "suite_logs\_last_state.json"
if ($Resume) {
    if (-not (Test-Path $statePath)) { Write-Error "-Resume: 이전 상태 파일이 없습니다 ($statePath)"; exit 1 }
    $st = Get-Content $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $doneGroups = @($st.completedGroups)
    $plan = @($plan | Where-Object { $doneGroups -notcontains $_.g })
    Write-Host ("-Resume: 완주한 그룹 [{0}] 을 건너뜁니다 (기준 {1})" -f ($doneGroups -join ','), $st.stamp) -ForegroundColor Yellow
}
if ($From) {
    # ⚠️ `[array]::FindIndex($plan, [Predicate[object]]{...})` 를 쓰지 말 것 —
    #   PowerShell이 스크립트블록을 제네릭 Predicate로 못 바꿔
    #   **"Cannot find an overload for FindIndex and the argument count: 2"** 로 죽는다
    #   (2026-09-02 실측). 항목 수가 30개뿐이라 선형 탐색이 더 낫다.
    $i = -1
    for ($k = 0; $k -lt $plan.Count; $k++) {
        if ($plan[$k].n -like "*$From*") { $i = $k; break }
    }
    if ($i -lt 0) { Write-Error "-From '$From' 에 해당하는 항목이 없습니다."; exit 1 }
    $plan = @($plan[$i..($plan.Count - 1)])
}
if ($plan.Count -eq 0) { Write-Error "실행할 항목이 없습니다. -Group/-Only/-Resume 를 확인하세요."; exit 1 }

# ----------------------------------------------------------------
# 계획 출력 (+ 예상 누적 시간)
# ----------------------------------------------------------------
$appLabel = if ($IsLive) { "$EffAppId  [운영/Live]" } else { "$EffAppId  (서버 LIVETEST 강제)" }
# -Names 는 그룹 필터를 무시하므로 헤더에 그룹을 찍으면 사실과 다르다.
$grpLabel = if ($Names.Count -gt 0) { "(-Names 지정 순서)" } else { $Group -join ',' }
$totalEst = ($plan | Measure-Object -Property est -Sum).Sum
Write-Host ""
Write-Host ("=== 실행 계획 — {0}개 / 예상 {1}시간 {2}분 / lang={3} / groups={4} / app={5} ===" -f `
    $plan.Count, [math]::Floor($totalEst / 60), ($totalEst % 60), $Lang, $grpLabel, $appLabel) -ForegroundColor Cyan
$acc = 0; $idx = 0; $lastG = ""
foreach ($t in $plan) {
    if ($t.g -ne $lastG) { Write-Host ("  ── {0} ──" -f $t.g) -ForegroundColor DarkCyan; $lastG = $t.g }
    $idx++; $acc += $t.est
    $mark = ""
    if ($t.push)         { $mark += " [push]" }
    if ($t.needs.balance){ $mark += (" [잔액 {0:N0}]" -f $t.needs.balance) }
    if ($t.irreversible) { $mark += " [🔴비가역]" }
    if ($t.destructive)  { $mark += " [⛔파괴]" }
    Write-Host ("  {0,2}. {1,-34} {2,-13} {3,3}분  누적 {4,3}분{5}" -f `
        $idx, $t.n, $t.acct, $t.est, $acc, $mark)
}
Write-Host ""
if ($plan | Where-Object { $_.destructive }) {
    Write-Host "⛔ 파괴적 항목이 계획에 있습니다 — admin 콘솔에 즉시 붙을 수 있을 때만 실행하세요." -ForegroundColor Red
    Write-Host ""
}
# ── 기기 복귀 대기 ──────────────────────────────────────────────
#   ⚠️ **USB가 실제로 자주 끊긴다.** 2026-08-31~09-01에 4회, 09-03 검증에서만 2회
#     (`device not found` / `device offline`). 끊긴 걸 모르고 계속 돌면 남은 항목이
#     전부 FAIL로 찍히고 몇 시간이 날아간다 — 실제로 11개짜리 구간이 3개에서 끝났다.
#   → 항목 실행 **전**과 복구 **전**에 기기가 `device` 상태로 돌아올 때까지 기다린다.
#     `adb reconnect offline`은 offline으로 굳은 전송을 다시 열게 만든다(실측으로 1회에 복귀).
function Wait-Device([int]$TimeoutSec = 180) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $warned = $false
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $line = @(adb devices | Select-String "^\S+\s+device$")
        if ($Device) { $line = @($line | Where-Object { $_ -match [regex]::Escape($Device) }) }
        if ($line.Count -ge 1) {
            if ($warned) { Write-Host ("    기기 복귀 ({0:N0}초 대기)" -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green }
            return $true
        }
        if (-not $warned) {
            Write-Host "`n    ⚠️ 기기가 보이지 않습니다(USB 유실) — 복귀를 기다립니다..." -ForegroundColor Yellow
            $warned = $true
        }
        adb reconnect offline 2>$null | Out-Null
        Start-Sleep -Seconds 3
    }
    return $false
}

# ── 잔액/자동 충전 계획 출력 ────────────────────────────────────
#   ⚠️ **`-List`에서도 보여야 한다.** 이 계획은 "실계좌에서 얼마가 빠지는가"이고,
#     그걸 확인하려고 실행부터 해야 한다면 미리보기의 의미가 없다(2026-09-03).
function Write-BalancePlan([string]$Pad, [string]$Ind) {
    if ($Balance -ge 0) {
        $needMax = 0
        foreach ($t in $plan) { if ($t.needs.balance -and $t.needs.balance -gt $needMax) { $needMax = $t.needs.balance } }
        $short = [Math]::Max(0, $needMax - $Balance)
        Write-Host ($Pad + ("{0:N0}원 (최대 필요 {1:N0}원)" -f $Balance, $needMax)) -ForegroundColor Green
        if ($short -le 0) {
            Write-Host ($Ind + "충전 불필요") -ForegroundColor DarkGray
        } elseif (-not $AutoCharge) {
            Write-Host ($Ind + ("{0:N0}원 부족 — 부족한 항목은 SKIP합니다. 손으로 충전하거나 -AutoCharge(미검증)" -f $short)) -ForegroundColor DarkYellow
            foreach ($t in $plan) {
                if ($t.needs.balance -and $Balance -lt $t.needs.balance) {
                    Write-Host ($Ind + ("  · {0}: 필요 {1:N0}원" -f $t.n, $t.needs.balance)) -ForegroundColor DarkYellow
                }
            }
        } else {
            $planAmt = [Math]::Min($short, $MaxCharge)
            Write-Host ($Ind + ("{0:N0}원 부족 → 필요한 항목 직전에 **최대 {1:N0}원 자동 충전**합니다" -f $short, $planAmt)) -ForegroundColor DarkYellow
            Write-Host ($Ind + ("[REAL] 실계좌에서 빠집니다 — 1회 1,000원 x 최대 {0}회" -f [Math]::Ceiling($planAmt / 1000))) -ForegroundColor Red
            Write-Host ($Ind + "[미검증] KFTC 자금 인출에는 OTP/생체인증이 필요하다 — 이 경로는 완주 확인이 안 됐다") -ForegroundColor Red
            Write-Host ($Ind + ("상한 -MaxCharge {0:N0}원 / 충전 {1}회 ≈ {1}분이 총 소요에 더해집니다" -f $MaxCharge, [Math]::Ceiling($planAmt / 1000))) -ForegroundColor DarkGray
            if ($short -gt $MaxCharge) {
                Write-Host ($Ind + ("⚠️ 부족액이 상한보다 큽니다 — 상한까지 채우고도 모자란 항목은 SKIP됩니다")) -ForegroundColor DarkYellow
            }
        }
    } else {
        Write-Host ($Pad + "**미확인** (-Balance 미지정) — 게이트도 자동 충전도 없이 진행합니다") -ForegroundColor DarkYellow
        Write-Host ($Ind + "⚠️ 구 UI 홈은 잔액을 마스킹하므로 자동으로 읽을 수 없습니다.") -ForegroundColor DarkGray
        Write-Host ($Ind + "잔액을 넘기면(-Balance) 모자란 만큼 자동 충전합니다.") -ForegroundColor DarkGray
    }
}

Write-Host "  잔액/충전" -ForegroundColor Cyan
Write-BalancePlan -Pad '    보유          ' -Ind '    '
Write-Host ""
if ($List) { exit 0 }

# 존재하지 않는 플로우 파일을 미리 걸러낸다(실행 도중 죽는 것보다 낫다)
$missing = $plan | Where-Object { -not (Test-Path (Join-Path $root $_.f)) }
if ($missing) {
    Write-Error ("플로우 파일을 찾을 수 없습니다:`n  " + (($missing | ForEach-Object { $_.f }) -join "`n  "))
    exit 1
}

# ----------------------------------------------------------------
# P0 전제검사 — **스위트가 실제로 볼 수 있는 것만** 본다 (결정 ④)
# ----------------------------------------------------------------
Write-Host "=== P0 전제검사 ===" -ForegroundColor Cyan
$skip = @{}

# ① 정적 검사 — 실행으로는 원리적으로 안 잡히는 부류를 여기서 막는다
if (-not $SkipLint) {
    & (Join-Path $root "lint_flows.ps1") -Quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  린터 ERROR — 돌리기 전에 고치세요 (lint_Old.md). -SkipLint 로 무시 가능" -ForegroundColor Red
        exit 1
    }
    Write-Host "  린터            OK (지적 0건)" -ForegroundColor Green
} else {
    Write-Host "  린터            건너뜀 (-SkipLint)" -ForegroundColor DarkYellow
}

# ② 기기 1대 — 2대 이상이면 실계좌 플로우가 엉뚱한 기기에서 돌 수 있다
$devCount = @(adb devices | Select-String "\tdevice$").Count
if ($devCount -ne 1 -and -not $Device) {
    Write-Host ("  기기            {0}대 — 1대여야 합니다(또는 -device 지정)" -f $devCount) -ForegroundColor Red
    exit 1
}
Write-Host ("  기기            {0}대" -f $devCount) -ForegroundColor Green

# ②-1 해상도 — **바뀌면 실패가 무더기로 나온다.** 2026-09-09 기기 교체(1080x2220 → 1080x2340)에서
#   7개 파일이 한꺼번에 깨졌고, 증상이 제각각이라 전부 셀렉터 버그로 오진할 뻔했다.
#   원인은 하나다: 요소가 화면 밖으로 밀리거나 키패드에 가려진다.
#   → 매 실행에서 해상도를 찍고, **지난 실행과 다르면 먼저 알린다.**
#   ⚠️ 기기가 없으면 Select-String 이 아무것도 안 돌려주고, `.Matches.Groups[1]` 이
#      "Cannot index into a null array" 로 **터진다**($ErrorActionPreference='Stop'). 반드시 배열로 받을 것.
$wmHit  = @(adb shell wm size 2>$null | Select-String 'Physical size:\s*(\S+)')
$wmSize = if ($wmHit.Count) { $wmHit[0].Matches[0].Groups[1].Value } else { "" }
$dnHit  = @(adb shell wm density 2>$null | Select-String 'Physical density:\s*(\S+)')
$wmDens = if ($dnHit.Count) { $dnHit[0].Matches[0].Groups[1].Value } else { "?" }
$devRes = if ($wmSize) { "$wmSize @ ${wmDens}dpi" } else { "미확인" }
$resPath = Join-Path $root "suite_logs\_last_resolution.txt"
$prevRes = if (Test-Path $resPath) { (Get-Content $resPath -Raw -Encoding UTF8).Trim() } else { "" }
if ($prevRes -and $wmSize -and $prevRes -ne $devRes) {
    Write-Host ("  해상도          {0}  ⚠️ 지난 실행({1})과 다릅니다" -f $devRes, $prevRes) -ForegroundColor Yellow
    Write-Host "                  실패가 무더기로 나면 **셀렉터 버그로 단정하지 마세요** — 해상도 문제일 수 있습니다." -ForegroundColor Yellow
    Write-Host "                  판정법: PROGRESS.md '기기 교체' 절 / 고치는 법: maestro-yaml 스킬" -ForegroundColor DarkGray
} else {
    Write-Host ("  해상도          {0}" -f $devRes) -ForegroundColor Green
}
if ($wmSize) {
    $resDir = Split-Path -Parent $resPath
    if (-not (Test-Path $resDir)) { New-Item -ItemType Directory -Path $resDir -Force | Out-Null }
    [System.IO.File]::WriteAllText($resPath, $devRes, [System.Text.UTF8Encoding]::new($false))
}

# ②-2 빌드가 기기에 설치돼 있는지 — 없으면 전 항목이 launchApp에서 죽는다
$pkgHit = @(adb shell pm list packages $EffAppId 2>$null | Select-String ([regex]::Escape("package:$EffAppId") + "$")).Count
if ($pkgHit -lt 1) {
    Write-Host ("  빌드            {0} — **기기에 설치돼 있지 않습니다**" -f $EffAppId) -ForegroundColor Red
    Write-Host "                  설치된 GME 패키지: " -NoNewline -ForegroundColor DarkGray
    Write-Host (@(adb shell pm list packages 2>$null | Select-String "gmeremit" | ForEach-Object { ($_ -replace "package:","").Trim() }) -join ", ") -ForegroundColor DarkGray
    exit 1
}
if ($IsLive) {
    Write-Host ("  빌드            {0}  [운영/Live]" -f $EffAppId) -ForegroundColor Red
    Write-Host "                  실서비스 계정과 실자금이 움직입니다. 의도한 실행인지 확인하세요." -ForegroundColor Red
} else {
    Write-Host ("  빌드            {0}  (서버는 플로우가 LIVETEST로 강제)" -f $EffAppId) -ForegroundColor Green
}

# ③ 잔액 — 모자라면 **그 자리에서 충전**하고, 못 채우면 SKIP한다 (2026-09-03 변경)
#
# 종전에는 시작 잔액만 보고 SKIP을 확정했다. 그러면 시작 전에 충전을 깜빡한 실행은
# 돈이 드는 케이스가 통째로 빠진 채 3시간이 지나간다.
# → 이제 **부족한 항목 직전에 `_suite_charge_old.yaml`을 부족액만큼 반복 호출**한다(1회=1,000원).
#
# ⚠️ `14_01_Deposit`이 이 일을 대신하지 못한다(그래서 순서만 앞으로 옮기고 충전은 따로 둔다):
#    [27] 자동이체는 금액 입력·표시 확인 후 back(확인·PIN 없음) / [02][05] 가상계좌는 번호 표시만 /
#    [28][29] 편의점 입금은 10분 뒤 만료되는 요청이라 스캔 전에는 자금이 움직이지 않는다.
#
# ⚠️ 소비는 모델링하지 않는다. 각 항목이 실제로 얼마를 쓰는지(수수료·환율 연동)를 알 수 없어
#    추정하면 틀린 숫자로 SKIP/충전 판단을 하게 된다. **충전분만 더해 추적**하고,
#    실행 중 실제로 모자라면 그 항목은 앱이 거부하며 FAIL로 남는다(리포트에서 갈라 보인다).
$projBal    = $Balance          # 추적 잔액(시작 잔액 + 이 실행에서 충전한 금액)
$chargeSpent = 0                # 이 실행에서 자동 충전한 총액
$canCharge  = ($Balance -ge 0) -and $AutoCharge

Write-BalancePlan -Pad '  잔액            ' -Ind '                  '

# ④ 접속 호스트 판정 준비 — 코드가 아니라 **실제 트래픽**으로 본다
adb logcat -c 2>$null | Out-Null
$earlyHostChecked = $false
Write-Host "  logcat          초기화 (종료 시 접속 호스트 집계)" -ForegroundColor Green
Write-Host ""

# ----------------------------------------------------------------
# 실행
# ----------------------------------------------------------------
$stamp  = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logDir = Join-Path $root "suite_logs\$stamp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$results = @()
$swAll = [Diagnostics.Stopwatch]::StartNew()
$recoverFail = 0
$aborted = $false

Write-Host "로그: $logDir" -ForegroundColor DarkGray
Write-Host ""

$lastG = ""
foreach ($t in $plan) {
    if ($t.g -ne $lastG) { Write-Host ("── {0} ({1}) ──" -f $t.g, $t.acct) -ForegroundColor DarkCyan; $lastG = $t.g }

    # ── 잔액이 모자라면 **여기서 채운다** (1회=1,000원, 실계좌 출금) ────────────
    if ($t.needs.balance -and $projBal -ge 0 -and $projBal -lt $t.needs.balance) {
        $gap = $t.needs.balance - $projBal
        if (-not $canCharge) {
            $skip[$t.n] = ("잔액 부족 — 보유 {0:N0}원 < 필요 {1:N0}원 (자동 충전 꺼짐)" -f $projBal, $t.needs.balance)
        } else {
            $roomLeft = $MaxCharge - $chargeSpent
            $wantN    = [Math]::Ceiling($gap / 1000)
            $canN     = [Math]::Floor($roomLeft / 1000)
            if ($canN -lt $wantN) {
                $skip[$t.n] = ("잔액 부족 — 보유 {0:N0}원 < 필요 {1:N0}원. 자동 충전 상한(-MaxCharge {2:N0}원)에 걸려 {3:N0}원만 더 넣을 수 있습니다" -f $projBal, $t.needs.balance, $MaxCharge, ($canN * 1000))
            } else {
                Write-Host ("  · 잔액 {0:N0}원 → {1:N0}원 필요. 1,000원씩 {2}회 충전합니다(실계좌 출금)" -f $projBal, $t.needs.balance, $wantN) -ForegroundColor Yellow
                $okN = 0
                for ($ci = 1; $ci -le $wantN; $ci++) {
                    $cArgs = @{ lang = $Lang; flow = "Old" + [char]92 + "_suite_charge_old.yaml"; AppId = $EffAppId }
                    if ($Device) { $cArgs['device'] = $Device }
                    $clog = Join-Path $logDir ("_charge_{0}_{1}.log" -f $t.n, $ci)
                    & (Join-Path $root "run_test.ps1") @cArgs *>&1 | Tee-Object -FilePath $clog | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        $okN++; $projBal += 1000; $chargeSpent += 1000
                    } else {
                        # 충전이 깨졌으면 **더 시도하지 않는다.** 반복하면 실계좌에서 돈만 나가고
                        # 상태가 어디까지 진행됐는지도 모른다(금액 입력 화면이 좌표 의존이라 특히).
                        Write-Host ("    ⚠️ 충전 {0}/{1}회차 실패 — 중단하고 이 항목은 SKIP합니다 ({2})" -f $ci, $wantN, $clog) -ForegroundColor Red
                        break
                    }
                }
                Write-Host ("    충전 {0}/{1}회 성공 — 추적 잔액 {2:N0}원 (이 실행 누적 {3:N0}원)" -f $okN, $wantN, $projBal, $chargeSpent) -ForegroundColor DarkGray
                if ($projBal -lt $t.needs.balance) {
                    $skip[$t.n] = ("잔액 부족 — 자동 충전이 {0}/{1}회에서 실패했습니다(추적 잔액 {2:N0}원 < 필요 {3:N0}원)" -f $okN, $wantN, $projBal, $t.needs.balance)
                }
            }
        }
    }

    # SKIP — 전제 미충족. FAIL과 갈라서 리포트한다(결정 ③)
    if ($skip.ContainsKey($t.n)) {
        Write-Host ("▶ {0,-34} SKIP    {1}" -f $t.n, $skip[$t.n]) -ForegroundColor Yellow
        $results += [pscustomobject]@{
            Group = $t.g; Name = $t.n; Status = "SKIP"; Exit = $null; Steps = 0
            Elapsed = "-"; Reason = $skip[$t.n]; Blocked = @($t.blocked).Count; Na = @($t.na).Count; Log = ""
        }
        continue
    }

    # 기기가 살아 있는지 먼저 본다 — 죽은 채로 돌리면 이 항목도, 뒤이은 복구도 무의미하게 실패한다
    if (-not (Wait-Device)) {
        Write-Host "`n⛔ 기기가 3분 안에 돌아오지 않았습니다 — 중단합니다. USB 연결을 확인하세요." -ForegroundColor Red
        $aborted = $true; break
    }

    if ($t.push) {
        Write-Host "  · 갤러리 픽스처 push..." -ForegroundColor DarkGray
        & (Join-Path $root "push_test_images.ps1") *>&1 | Out-File (Join-Path $logDir "$($t.n)_push.log") -Encoding UTF8
    }

    Write-Host ("▶ {0,-34} " -f $t.n) -NoNewline
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $log = Join-Path $logDir "$($t.n).log"

    # ⚠️ **배열 스플래팅(@arr)을 쓰지 말 것** — `-AppId`가 바인딩되지 않는다
    #   ("A positional parameter cannot be found that accepts argument '-AppId'", 2026-08-27 실측).
    #   또 변수명을 `$args`로 쓰는 것도 금지 — PowerShell 자동 변수다.
    #   → **해시테이블 스플래팅**이 이름 있는 파라미터의 정석이다.
    # 빌드는 **항상 명시**해서 넘긴다 — env 파일 기본값에 기대면 로그만 보고는 어느 빌드였는지 모른다.
    $flowArgs = @{ lang = $Lang; flow = $t.f; AppId = $EffAppId }
    if ($Device) { $flowArgs['device'] = $Device }
    & (Join-Path $root "run_test.ps1") @flowArgs *>&1 | Tee-Object -FilePath $log | Out-Null
    $code = $LASTEXITCODE
    $sw.Stop()

    $txt      = Get-Content $log -Raw -Encoding UTF8 -ErrorAction SilentlyContinue

    # ⚠️ 로그 첫 줄은 `Running: maestro … --env SESSION_EXPIRED="로그인 세션이 만료" --env TXT_BALANCE="잔액" …`
    #   형태의 **커맨드 에코**다. 이 줄을 그대로 검사하면 **env 값 자신이 매칭**된다
    #   → 2026-09-02 실측: `09_Home`이 `btnTransfer` assert로 죽었는데 리포트엔
    #     **[세션 만료(환경)]**로 찍혔고, 원인 자리엔 maestro 커맨드 전문(4KB)이 실렸다.
    #     환경 탓으로 오분류된 FAIL은 **코드 결함을 가리는** 가장 나쁜 종류의 오보다.
    #   → 분류·원인 추출은 **에코 줄을 걷어낸 본문(`$bodyLines`)**으로만 한다.
    $bodyLines = @($txt -split "`r?`n" | Where-Object { $_ -notmatch '^\s*Running:\s' -and $_ -notmatch '(^|\s)--env\s' })
    $body      = $bodyLines -join "`n"

    # ⚠️ **성공한 스텝 설명줄로 분류하지 말 것.** 에코 줄을 걷어내도 오탐이 남았다:
    #   `Assert that "로그인 세션이 만료[\s\S]*" is not visible... COMPLETED` 는 **세션이 살아 있다는 뜻**인데
    #   "세션이 만료"가 문자열로 들어 있어 2026-09-03 `21_Card` FAIL이 [세션 만료(환경)]로 찍혔다.
    #   → 분류·원인은 **COMPLETED/SKIPPED로 끝나지 않는 줄**(= 실제 실패·오류 줄)만 본다.
    $errLines = @($bodyLines | Where-Object { $_ -notmatch '(COMPLETED|SKIPPED|PENDING)\s*$' })
    $errBody  = $errLines -join "`n"

    $done     = ([regex]::Matches($body, "COMPLETED")).Count
    $failLine = ($bodyLines | Where-Object { $_ -match "FAILED\s*$" } | Select-Object -First 1)
    $reason   = ($errLines  | Where-Object { $_ -match "Element not found|Assertion is false|Screenshot returned null|insufficient|Duplicate|already exist|세션이 만료|device .* not found" } | Select-Object -First 1)

    # 환경 전제 미충족으로 죽은 것은 코드 결함과 갈라서 표시한다(진단 가능성)
    $envHint = ""
    if ($code -ne 0) {
        # ⚠️ **기기 연결이 끊긴 것을 코드 결함으로 찍지 말 것** — 2026-09-03 첫 검증 실행에서
        #   `09_Home`이 54스텝에서 `device '...' not found`(adb transport 유실)로 죽었다.
        #   USB는 실제로 자주 끊긴다(8/31~9/1에만 4회). 가장 먼저 본다.
        if     ($errBody -match "not found\)|device .* not found|Command failed \(host:transport") { $envHint = "기기 연결 끊김(환경)" }
        elseif ($errBody -match "insufficient")   { $envHint = "잔액 부족(환경)" }
        elseif ($errBody -match "세션이 만료")     { $envHint = "세션 만료(환경)" }
        elseif ($errBody -match "Duplicate|already exist") { $envHint = "테스트 데이터 소모(환경)" }
    }

    $status = if ($code -eq 0) { "PASS" } else { "FAIL" }
    $color  = if ($code -eq 0) { "Green" } else { "Red" }
    Write-Host ("{0}  {1,6} steps  {2}" -f $status, $done, $sw.Elapsed.ToString("mm\:ss")) -ForegroundColor $color
    if ($code -ne 0) {
        if ($envHint) { Write-Host ("      → [{0}] {1}" -f $envHint, $reason) -ForegroundColor DarkYellow }
        elseif ($reason) { Write-Host ("      → " + $reason.Trim()) -ForegroundColor DarkYellow }
    }

    $results += [pscustomobject]@{
        Group = $t.g; Name = $t.n; Status = $status; Exit = $code; Steps = $done
        Elapsed = $sw.Elapsed.ToString("mm\:ss")
        Reason = if ($code -ne 0) { (($envHint ? "[$envHint] " : "") + ($reason ?? $failLine ?? "")).Trim() } else { "" }
        Blocked = @($t.blocked).Count; Na = @($t.na).Count; Log = $log
    }

    # ── 조기 서버 검사: **첫 실행 직후 한 번만** 본다 ──────────────────
    # stag 빌드는 Server Override 기본값이 STAG다. 한 플로우라도 LIVETEST 강제를 빠뜨리면
    # 전 스위트가 조용히 gmeuat로 돈다(2026-08-27 사고: gmeuat 1,113건 / livetest 0건).
    # 3시간을 버리고 끝에서야 알게 되는 게 최악이라 **첫 항목에서 끊는다.**
    if (-not $earlyHostChecked) {
        $earlyHostChecked = $true
        # ⚠️ **콜드스타트 gmeuat 은 유출이 아니다** (2026-09-09 실측).
        #   `clearState` 를 쓰는 플로우(05_InitialScreen · 01_03 · 01_01 …)는 앱 데이터를 지워
        #   서버 선택이 빌드 기본값(stag=STAG)으로 돌아간다. 그래서 **Server Override 적용 전에**
        #   앱이 설정 API `ChangePasswordRule` 하나를 gmeuat 로 호출한다(요청+응답 2줄).
        #   → 그 엔드포인트만 **콜드스타트로 분류**하고, 나머지 gmeuat 는 전부 위반으로 본다.
        #     (항목마다 clearState 가 있으면 실행 중간에도 생기므로 "첫 건만 예외"로는 부족하다)
        $ehHits = @(adb logcat -d 2>$null | Select-String -Pattern '(?:-->|<--).*?(livetest|gmeuat)\.gmeremit\.com(\S*)' -AllMatches |
                ForEach-Object { $_.Matches } |
                ForEach-Object { [pscustomobject]@{ SrvHost = $_.Groups[1].Value; Path = $_.Groups[2].Value } })
        $ehLive     = @($ehHits | Where-Object { $_.SrvHost -eq 'livetest' }).Count
        $ehStagAll  = @($ehHits | Where-Object { $_.SrvHost -eq 'gmeuat' })
        $ehStagCold = @($ehStagAll | Where-Object { $_.Path -match 'ChangePasswordRule' }).Count
        $ehStag     = $ehStagAll.Count - $ehStagCold
        if ($ehStagCold -gt 0) {
            Write-Host ("      서버 확인: 콜드스타트 gmeuat {0}건(clearState 직후 설정 API — 무해)" -f $ehStagCold) -ForegroundColor DarkGray
        }
        if ($IsLive) {
            Write-Host ("      서버 확인: 운영 빌드 (livetest {0} / gmeuat {1})" -f $ehLive, $ehStag) -ForegroundColor DarkCyan
        } elseif ($ehStag -gt 0) {
            Write-Host ("`n[STOP] STAG(gmeuat) 트래픽 {0}건 — Server Override가 LIVETEST로 안 걸렸습니다." -f $ehStag) -ForegroundColor Red
            Write-Host "       여기서 멈춥니다. 이대로 두면 전 스위트가 엉뚱한 서버로 돕니다." -ForegroundColor Red
            $aborted = $true; break
        } elseif ($ehLive -gt 0) {
            Write-Host ("      서버 확인: livetest {0}건 / gmeuat 0건 — 정상" -f $ehLive) -ForegroundColor Green
        } else {
            Write-Host "      서버 확인: 호스트 로그가 안 잡혔습니다(logcat 버퍼) — 종료 시 재집계합니다." -ForegroundColor DarkYellow
        }
    }

    if ($code -ne 0 -and $StopOnFail) {
        Write-Host "`n-StopOnFail: 첫 실패에서 중단합니다." -ForegroundColor Yellow
        $aborted = $true; break
    }

    # ── 결정 ② 자동 복구 ────────────────────────────────────────
    #   다음 항목이 깨진 상태를 물려받지 않게 한다. 복구는 스크립트가 아니라 **플로우**가 한다 —
    #   화면을 볼 수 있는 건 Maestro뿐이다.
    if ($code -ne 0 -and -not $NoRecover) {
        Write-Host "  · 복구(_suite_recover_old.yaml)..." -NoNewline -ForegroundColor DarkGray
        $rlog = Join-Path $logDir "$($t.n)_recover.log"
        if (-not (Wait-Device)) {
            Write-Host "`n⛔ 기기가 돌아오지 않아 복구도 할 수 없습니다 — 중단합니다." -ForegroundColor Red
            $aborted = $true; break
        }
        $rArgs = @{ lang = $Lang; flow = "Old\_suite_recover_old.yaml" }
        if ($Device) { $rArgs['device'] = $Device }
        $rArgs['AppId'] = $EffAppId
        & (Join-Path $root "run_test.ps1") @rArgs *>&1 | Tee-Object -FilePath $rlog | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host " OK" -ForegroundColor DarkGray
            $recoverFail = 0
        } else {
            $recoverFail++
            Write-Host (" 실패 ({0}회 연속)" -f $recoverFail) -ForegroundColor Red
            # ★ 복구가 2회 연속 실패하면 중단한다. 안 그러면 남은 항목이 전부 FAIL로 찍힌다.
            if ($recoverFail -ge 2) {
                Write-Host "`n⛔ 복구 2회 연속 실패 — 중단합니다. 기기·세션 상태를 손으로 확인하세요." -ForegroundColor Red
                Write-Host "   PIN 미등록 상태라면 `01_01_Login_Success_old.yaml` 로만 빠져나옵니다." -ForegroundColor DarkYellow
                $aborted = $true; break
            }
        }
    }
}
$swAll.Stop()

# ----------------------------------------------------------------
# 접속 호스트 집계 — 코드가 아니라 실제 트래픽으로 판정한다
# ----------------------------------------------------------------
# ⚠️ **요청/응답 줄(`-->` `<--`)만 센다.** 종전에는 logcat 전체에서 호스트 문자열을 세어
#   **LIVETEST 응답 본문에 들어 있는 gmeuat 이미지 URL**(예: RIA 파트너 아이콘
#   `https://gmeuat.gmeremit.com:5022/Images/...`)까지 STAG 트래픽으로 집계했다
#   → 2026-09-08 실행에서 gmeuat 5건이 찍혀 "서버가 뒤섞였다"는 거짓 경고가 났다.
$hostHits = @(adb logcat -d 2>$null | Select-String -Pattern '(?:-->|<--).*?(livetest|gmeuat)\.gmeremit\.com(\S*)' -AllMatches |
              ForEach-Object { $_.Matches } |
              ForEach-Object { [pscustomobject]@{ SrvHost = $_.Groups[1].Value; Path = $_.Groups[2].Value } })
# 위 조기검사와 같은 규칙: `ChangePasswordRule`(override 적용 전 호출)만 콜드스타트로 분류한다.
$hLive     = @($hostHits | Where-Object { $_.SrvHost -eq 'livetest' }).Count
$hStagAll  = @($hostHits | Where-Object { $_.SrvHost -eq 'gmeuat' })
$hStagCold = @($hStagAll | Where-Object { $_.Path -match 'ChangePasswordRule' }).Count
$hStag     = $hStagAll.Count - $hStagCold

# ----------------------------------------------------------------
# 상태 저장 (-Resume 용) — **그룹 경계**만 기록한다
# ----------------------------------------------------------------
$completed = @()
if (-not $aborted) {
    foreach ($g in ($plan | ForEach-Object { $_.g } | Select-Object -Unique)) {
        $inG = @($results | Where-Object { $_.Group -eq $g })
        $planG = @($plan | Where-Object { $_.g -eq $g })
        if ($inG.Count -eq $planG.Count -and -not ($inG | Where-Object { $_.Status -eq "FAIL" })) {
            $completed += $g
        }
    }
}
@{ stamp = $stamp; completedGroups = $completed; aborted = [bool]$aborted } |
    ConvertTo-Json | Out-File $statePath -Encoding UTF8

# ----------------------------------------------------------------
# 요약 — 4종으로 갈라야 "FAIL 0"이 의미를 갖는다
# ----------------------------------------------------------------
$pass = @($results | Where-Object Status -eq "PASS").Count
$fail = @($results | Where-Object Status -eq "FAIL").Count
$skipN = @($results | Where-Object Status -eq "SKIP").Count
$blk = ($results | Measure-Object -Property Blocked -Sum).Sum
$naN = ($results | Measure-Object -Property Na -Sum).Sum

Write-Host ""
Write-Host "=== 요약 ===" -ForegroundColor Cyan
$results | Format-Table Group, Name, Status, Steps, Elapsed, Reason -AutoSize
Write-Host ("항목 {0}개 / PASS {1} / FAIL {2} / SKIP {3}   ·   케이스 BLOCKED {4} / N/A {5}" -f `
    $results.Count, $pass, $fail, $skipN, $blk, $naN)
Write-Host ("소요 {0}   ·   접속 호스트: livetest {1}건 / gmeuat(STAG) {2}건" -f `
    $swAll.Elapsed.ToString("hh\:mm\:ss"), $hLive, $hStag)
if (-not $IsLive -and $hStag -gt 0) {
    Write-Host "⛔ STAG(gmeuat) 트래픽이 섞였습니다 — 이 실행 결과는 서버가 뒤섞였을 수 있어 신뢰할 수 없습니다." -ForegroundColor Red
    Write-Host "   원인은 대개 Server Override 강제를 빠뜨린 플로우입니다(린터 E08이 잡습니다)." -ForegroundColor DarkYellow
} elseif (-not $IsLive -and $hLive -eq 0) {
    Write-Host "⚠️ livetest 호스트 로그가 0건입니다 — logcat 버퍼가 밀렸거나 실제 통신이 없었습니다." -ForegroundColor DarkYellow
}
if ($completed.Count -gt 0) { Write-Host ("완주 그룹: {0} (-Resume 시 건너뜁니다)" -f ($completed -join ',')) -ForegroundColor DarkGray }

$md = @()
$md += "# 구 UI 회귀 스위트 결과 — $stamp"
$md += ""
$md += "- lang ``$Lang`` / groups ``$($Group -join ',')`` / app ``$appLabel``"
$md += "- 항목 $($results.Count)개 — **PASS $pass** / **FAIL $fail** / **SKIP $skipN**"
$md += "- 케이스 단위 제외: BLOCKED $blk / N/A $naN (알려진 앱버그·범위 밖)"
$md += "- 소요 $($swAll.Elapsed.ToString('hh\:mm\:ss')) / 예상 $totalEst 분"
$md += "- 기기 해상도: ``$devRes``" + $(if ($prevRes -and $wmSize -and $prevRes -ne $devRes) { "  ⚠️ **지난 실행($prevRes)과 다름** — 실패가 몰리면 해상도를 먼저 의심할 것" } else { "" })
$md += "- 빌드: ``$EffAppId``" + $(if ($IsLive) { "  **[운영/Live]**" } else { "  (서버 LIVETEST 강제)" })
$md += "- 접속 호스트: livetest **$hLive**건 / gmeuat(STAG) **$hStag**건"
if ($chargeSpent -gt 0) {
    $md += "- 🔴 자동 충전: **$('{0:N0}' -f $chargeSpent)원** (1회 1,000원 × $($chargeSpent/1000)회, 실계좌 출금)"
    $md += "  - 추적 잔액은 **시작 잔액 + 충전액**이다. 각 항목의 실제 소비는 반영하지 않는다(수수료·환율 연동이라 추정하지 않음)."
}
if ($Balance -ge 0) { $md += "- 시작 잔액: **$('{0:N0}' -f $Balance)원**" } else { $md += "- 시작 잔액: **미확인**(`-Balance` 미지정)" }
if ($aborted) { $md += "- ⛔ **중단됨** — 복구 2회 연속 실패 또는 -StopOnFail" }
$md += ""
$md += "| 그룹 | 항목 | 결과 | 스텝 | 소요 | 사유 |"
$md += "|---|---|---|---|---|---|"
foreach ($r in $results) {
    $md += "| $($r.Group) | $($r.Name) | $($r.Status) | $($r.Steps) | $($r.Elapsed) | $($r.Reason -replace '\|','\|') |"
}
$md += ""
$md += "> SKIP은 **전제 미충족**(잔액 등)이고 코드 결함이 아니다. `[환경]` 표시가 붙은 FAIL도 같다."
$mdPath = Join-Path $logDir "SUMMARY.md"
$md -join "`n" | Out-File $mdPath -Encoding UTF8
Write-Host "요약: $mdPath" -ForegroundColor DarkGray

if ($fail -gt 0 -or $aborted) { exit 1 } else { exit 0 }
