# GUIDE.md — 넘겨받은 사람이 처음 돌리기까지

GME Remittance 안드로이드 앱의 **Maestro E2E 자동화**를 처음 받는 사람을 위한 문서다.
작성 2026-09-14. 대상은 실행 트랙인 **구 UI(V2) `Old\*.yaml`**.

> 이 문서는 **"어떻게 시작하는가"** 만 다룬다. 같은 내용을 두 곳에 적으면 반드시 한쪽이 낡으므로,
> 상세는 아래 문서로 넘긴다. 링크를 따라가는 것을 전제로 짧게 썼다.
>
> | 알고 싶은 것 | 문서 |
> |---|---|
> | 환경을 옮길 때 **고칠 곳 전체 지도**(사전조건 / 코드 / skill·문서) | 이 문서 **§10** |
> | yaml에 박힌 값의 **상세 인벤토리와 수정 원칙** | `ENVIRONMENT.md` (같은 폴더) |
> | 파일별 **진행 현황 / BLOCKED 사유** | 저장소 루트 `PROGRESS.md` |
> | 실행·진단·yaml 작성·스위트 **상세 절차** | 저장소 `.claude\skills\maestro-{run,debug,yaml,suite}\SKILL.md` |
> | 앱·셀렉터 함정 **전체 목록** | 저장소 `CLAUDE.md` |

---

## 1. 이게 무엇인가

- **소스 코드가 아니다.** Maestro 플로우(yaml) 모음이고, "테스트를 돌린다" = **USB로 연결된
  실기기에서 앱을 실제로 조작한다**는 뜻이다. 빌드·유닛테스트가 없다.
- **에뮬레이터는 쓸 수 없다.** 생체인증·실계좌 연동 때문이다.
- ⚠️ **실행이 실계좌·실계정에 닿는다.** 실제 송금·결제·충전이 발생하고, 되돌릴 수 없는 것이 있다.
  **§5를 읽기 전에는 아무것도 돌리지 말 것.**

### 폴더 구조

```
C:\GME\qa-automation\Maestro\   ← 편집·실행 폴더. CWD는 항상 여기다
├── Old\*.yaml            ★ 실행 대상 66개 — 구 UI(V2)용, `_old` 접미사
├── *.yaml                개편 UI(V3)용 사본 — 배포 전까지 손대지 않는다
├── env\ko.env, en.env    화면 문구 사전(${VAR}로 참조)
├── Test Files\           갤러리 업로드용 이미지 픽스처 4장
├── run_test.ps1          단일 플로우 실행기
├── run_suite.ps1         회귀 스위트 실행기
├── push_test_images.ps1  갤러리 픽스처 주입
├── lint_flows.ps1        정적 검사기(실행 전에 돌린다)
├── shots_runs\           실행별 스크린샷(자동 회수)
└── suite_logs\           스위트 실행 로그 + SUMMARY.md
```

**저장소에만 있는 것**(정본에 없다 → 동기화가 지우지 않도록 제외 목록에 들어 있다):

```
C:\GME\qa-automation\
├── gme_excel.py          체크리스트(SharePoint 엑셀) 셀 단위 기입 도구
├── docs\README_win.md    ★ 그 도구 안내 — **Windows 기준. 이 팀은 이걸 본다**
├── docs\README_mac.md    같은 도구의 macOS 원본
├── docs\PROGRESS.md · SUITE.md
└── .claude\skills\       작업별 상세 절차
```

### 정본은 한 곳뿐이다 — 저장소 사본을 고치지 말 것

| | 경로 | 성격 |
|---|---|---|
| **작업 폴더** | `C:\GME\qa-automation\` | **편집·실행·커밋이 전부 여기다** |
| 원격 | GitHub `basshul/YAML` (비공개) | `main` 만 푸시한다 |
| 증적 | OneDrive `개인용 - Automation\` | 스크린샷·실행 로그만. **작업 파일은 없다** |

**2026-09-22 에 폴더를 하나로 합쳤다.** 종전의 OneDrive 정본 + 미러 2벌 구조와
동기화 스크립트(`sync_from_source.ps1`)는 폐기했다 — 두 벌이 있으면 반드시 한쪽이 낡는다.
✅ **저장소만 받아도 실행에 필요한 파일은 다 있다**(2026-09-18 `secrets.env` 폐지).

---

## 2. 설치 (1회)

실제로 돌아가고 있는 조합이다. 더 높은 버전이 안 된다는 뜻은 아니지만, 문제가 생기면 여기를 의심한다.

| 도구 | 확인된 버전 | 비고 |
|---|---|---|
| JDK | 25.0.1 | Maestro가 JVM 위에서 돈다 |
| Maestro CLI | **2.5.1** | scoop 설치(`~\scoop\apps\maestro\2.5.1`) |
| Android platform-tools (adb) | 36.0.2 | `adb`가 PATH에 있어야 한다 |
| PowerShell | 7+ | 러너가 `.ps1`이다 |
| Python 3 | 3.14.2 | 체크리스트 기입 도구(`gme_excel.py`)용. **`python3` 가 아니라 `python`** |

기기 쪽:

- **실기기 1대**, USB 디버깅 ON, 연결 유지
- **기기 생체인증 OFF** — 켜져 있으면 지문 화면이 끼어들어 플로우가 갈라진다
  (⚠️ 수동 테스트 중 **앱** 지문 인증을 켜 두면 전 스위트가 진입 불가가 된다)
- 앱은 **stag 빌드** `com.gmeremit.online.gmeremittance_native.stag` 설치

설치 확인:

```powershell
maestro -v            # 2.5.1
adb devices -l        # 정확히 1대. 2대 이상이면 러너가 실행을 거부한다
```

### 설치 명령 — 새 PC 기준

이 PC에 실제로 깔려 있는 방식이다.

```powershell
# 1) scoop (패키지 매니저) — 이미 있으면 건너뛴다
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression

# 2) Maestro
scoop install maestro
```

| 도구 | 설치 방식 | 실제 경로 |
|---|---|---|
| Maestro | `scoop install maestro` | `~\scoop\shims\maestro.cmd` |
| JDK | Oracle 설치 프로그램 | `C:\Program Files\Common Files\Oracle\Java\javapath\java.exe` |
| adb | **Android SDK platform-tools** | `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` |
| Python | python.org 설치 프로그램 | `C:\Python314\python.exe` |
| Git | Git for Windows | 저장소 clone 용 |

⚠️ **adb 는 PATH 에 직접 걸어야 한다** — SDK 설치 프로그램이 걸어주지 않는다.

```powershell
setx PATH "$env:PATH;$env:LOCALAPPDATA\Android\Sdk\platform-tools"
```

### 파일 받기 — 저장소만으로 자동화 환경이 선다

```powershell
git clone https://github.com/basshul/YAML.git C:\GME\qa-automation
```

**저장소 사본만으로도 실행된다.** 러너에 절대경로가 없고 전부 **CWD 기준**으로 동작한다
(2026-09-17 실측: `run_test.ps1`·`run_suite.ps1`·`push_test_images.ps1`·`lint_flows.ps1` 에
정본 경로 하드코딩 **0건**, `$PSScriptRoot` 도 안 쓴다). CWD 를 clone 한 `Maestro\` 로 잡으면 된다.

⚠️ 단 **편집은 정본에서만** 한다(§1) — 저장소에서 고치면 다음 동기화가 지운다.
정본(OneDrive)이 붙어 있는 환경이라면 그쪽을 CWD 로 쓰는 것이 맞다.

#### 저장소에 없는 파일은 없다 (2026-09-18)

종전에는 `env\secrets.env` 를 정본에만 두었으나, **전부 테스트 전용 계정·이메일이라 공개돼도
무방하다는 판단**으로 폐지하고 값을 `ko.env`·`en.env` 로 옮겼다
(`PROFILE_EMAIL` · `PROFILE_EMAIL_TEST`). `.gitignore` · `sync_from_source.ps1` · `run_test.ps1` 의
관련 처리도 함께 제거했다. → **clone 한 것만으로 값이 다 갖춰진다.**

#### 실행할 때 `--env` 로 넘기는 파라미터 2개

이건 "없는 값"이 아니라 **호출 시 주는 인자**다. 각 파일 헤더에 사용법이 적혀 있다.

| 키 | 쓰는 곳 | 안 넘기면 |
|---|---|---|
| `MAIL_ACCOUNT` | `01_05_Login_Password_Reset` — 초기화 메일의 **수신 계정 확인** | `typeof` 가드가 있어 **그 단계만 건너뛴다**(메일 본문은 그대로 검사) |
| `STAG_ID` | `_stag_login_probe` — 수동 프로브 헬퍼 | 단독 실행 대상이 아니다. 쓸 때 `--env STAG_ID=test123` 처럼 준다 |

나머지 자격정보는 플로우 내부 `env:` 블록에 있다(`PW_CUR_LAST` · `PW_LAST` · `PW_NEW_LAST` · `LOCK_ID`).

#### 필수와 불필요 — 추적 185개 중 90개가 필수

⚠️ **골라 받지 마라.** 전체가 **5.1 MB**, 필수만 추려도 **4.2 MB** 다(차이 0.9 MB).
이 분류는 *받을 것*을 고르려는 게 아니라 **"고쳐도 되는 것과 아닌 것"** 을 가리는 용도다.

**필수 — 없으면 못 돌린다**

| 항목 | 수 |
|---|---|
| `Maestro\Old\*.yaml` — 실행 대상 50 + 헬퍼 17 | 67 |
| `Maestro\env\ko.env` · `en.env` — 각 418키, **키 집합이 같아야 한다** | 2 |
| `run_test.ps1` · `run_suite.ps1` · `push_test_images.ps1` | 3 |
| `Maestro\Test Files\` — 갤러리 픽스처 | 4 |
| `lint_flows.ps1` · `lint_labels.json` · `lint_whitelist.txt` | 3 |
| `CLAUDE.md` · `.claude\skills\` 4 · `docs\` 4 | 9 |

**없어도 돌아간다 — 지우지는 말 것(용도가 있다)**

| 항목 | 수 | 무엇인가 |
|---|---|---|
| `Maestro\*.yaml` (루트) | 44 | **개편 UI(V3) 사본.** 폐기가 아니라 **보류** — 개편 빌드를 못 받아서다. 재개하면 쓴다 |
| `Maestro\lint_selftest\` + `lint_selftest.ps1` | 23 | 린터 **자기검사 픽스처** |
| `Maestro\_archive\` · `Old\_archive\` | 18 | 보관본 |
| `lint_*.json` | 2 | 린터 **산출물**(돌리면 재생성) |
| `flows_index.json` | 1 | **낡았다**(2026-06-25, V3 기준). 쓰기 전에 재생성하거나 무시 |
| `k_*.yaml` · `_stag_login*.yaml` · `charge.yaml` | 7 | 실험·단편 |
| `Automation Report.bat/.txt` · 루트 `run_test.ps1` | 3 | 데일리 리포트 / `Maestro\` 쪽과 중복 |

### 체크리스트 기입 도구 — 결과를 적을 사람만

테스트 실행에는 필요 없다. **QA 체크리스트에 결과를 기입할 때만** 쓴다.
절차는 [README_win.md](README_win.md) 에 있고, 요점은 셋이다:

```powershell
setx GME_CLIENT_ID "0ba0c638-c539-4584-b803-8af3ae62ddd1"
setx GME_TENANT_ID "b19514d1-d63d-4dda-b580-d80917436738"
$env:PYTHONIOENCODING = "utf-8"        # ★ 빼면 성공해 놓고 cp949 오류로 죽는다
python gme_excel.py login              # 최초 1회, 브라우저 인증
```

- ⚠️ **`login` 은 Claude가 대신 못 한다** — 자동모드가 브라우저 인증을 막는다. `!` 로 직접 실행한다.
- ⚠️ 대상 파일의 **편집** 권한이 있어야 한다. 읽기만 되면 `set` 에서 `HTTP 403` 이다.

---

## 3. 첫 실행 — 이 3줄

```powershell
$PSNativeCommandArgumentPassing = 'Legacy'    # ★ 생략하면 env 값의 `|`가 cmd 파이프로 해석돼 즉사
cd "C:\GME\qa-automation\Maestro"
.\run_test.ps1 -lang ko -flow "Old\09_Home_old.yaml"
```

`09_Home`을 첫 실행으로 쓰는 이유: **부작용이 0**이다(홈 화면 확인만 한다).

- `-lang ko|en` — 문구 사전 선택
- `-device <시리얼>` — 기기가 2대 이상일 때만. **시리얼을 코드에 박지 말 것**(기기는 교체된다)
- `-Build live` — **운영 빌드. 요청이 있을 때만.** 기본은 stag이고 플로우가 서버를 LIVETEST로 강제한다

### 결과 읽는 법

| 신호 | 의미 |
|---|---|
| `EXIT=0` | 통과 |
| `shots_runs\<시각>_<플로우>\` | 그 실행의 스크린샷(자동 회수) |
| `suite_logs\<시각>\SUMMARY.md` | 스위트 실행 결과표 |

⚠️ **EXIT=0이 "검증됐다"는 뜻은 아니다.** Maestro는 텍스트가 전체 일치하지 않으면 **에러 없이
조용히 건너뛴다.** 조건부 처리만 있고 assert가 없으면 아무 일도 안 일어나도 통과한다
(실제로 `21_Card`의 7개 케이스가 토글을 하나도 안 움직인 채 통과하고 있었다).
→ 새로 만든 플로우는 **화면을 보면서 한 번은 돌려볼 것.**

### 서버가 맞는지는 코드가 아니라 접속 호스트로 본다

stag 빌드는 서버 기본값이 STAG라서, LIVETEST 강제가 한 곳이라도 빠지면 **조용히 gmeuat로 돈다.**

```powershell
adb logcat -d | Select-String -Pattern '(livetest|gmeuat)\.gmeremit\.com'
```

---

## 4. 파일과 케이스를 읽는 법

- **한 파일 = 한 실행 단위.** Maestro에 케이스 선택 옵션은 없다.
  일부만 보고 싶으면 **본 파일에서 구간을 잘라 임시 yaml로 추출**해 돌리고,
  ⛔ **수정은 항상 본 파일에 하고 임시본은 다시 뽑는다**(임시본을 고치면 반영이 유실된다).
- 케이스 헤더는 `# [NN] [Low|Medium|High] <화면> - <검증 내용>` 규약이고 **ClickUp 케이스와 1:1**이다.
- `_` 로 시작하는 파일은 **헬퍼**다(`runFlow:`로 불린다). 단독 실행 대상이 아니다.
  예: `_server_override_old.yaml`(서버 지정) · `_switch_test123_old.yaml`(계정 전환) ·
  `_dismiss_popups_stag_old.yaml`(홈 팝업 큐 처리).
- 반복 문구는 `${VAR}` → `env\ko.env` / `env\en.env`에 있다.
  ⚠️ 두 파일의 **키 집합이 같아야** 한다. 한쪽에만 있으면 그 언어 실행에서 치환되지 않고 조용히 SKIP된다.
- 헤더 `appId: ${APP_ID}` 는 러너의 `-Build`가 정한다. **파일에 패키지명을 박지 말 것.**

### 무엇을 테스트하는가 (실행 단위 기준)

| 영역 | 파일 |
|---|---|
| 진입·로그인·가입 | `05_InitialScreen` · `01_01`/`01_02`/`01_03` · `06_Registration_All` |
| 홈·환율·메뉴 | `09_Home` · `07_TodaysRate` · `26_Menu` |
| 해외송금 | `02_01`(실시간) · `02_02`(예약) |
| 국내송금·QR | `03_Domestic` · `08_MyQR` |
| 해외송금 받기(인바운드) | `13_01` ~ `13_07` (7분할) |
| 입금·충전 | `14_01`/`14_02`/`14_03`(계정별) · `10_DomesticTopup` · `11_IntlTopup` |
| 결제·상품 | `12_BillPayment` · `18_Telecom` · `20_Booking` · `21_Card` · `22_Event` |
| 지갑·내역 | `17_WalletStatement` · `04_Menu_History` · `16_ATMWithdraw` |
| 프로필·설정 | `25_Profile` · `25_Profile_Foreign` · `04_01`/`04_02`/`04_06` · `19_IssueCertificate` |
| 노출 확인 | `15_Loan` (개인금융 **미**노출 확인) |

케이스별 상태(완료/BLOCKED/보류)는 **`PROGRESS.md`** 에 있다. 이 표는 지도일 뿐이다.

---

## 5. ⛔ 돌리기 전에 반드시 아는 것 — 되돌릴 수 없는 실행

| 플로우 | 무슨 일이 일어나는가 |
|---|---|
| `11_IntlTopup` / `12_BillPayment` | **실제 결제. 취소 불가** — 돌릴 때마다 금액이 누적된다 |
| `02_01` / `03_Domestic` / `08_MyQR` | **실제 송금**이 나간다 |
| `20_Booking` | 실결제 후 자동취소. 날짜를 가까이 잡으면 **취소 수수료** |
| `21_Card` | GME Shop 잔액 부족 시 **실계좌 자동충전** |
| `06_Registration_*` | **비멱등** — 성공 1회당 계정·이메일·신분증번호를 소모한다(재실행 전 admin 삭제) |
| `01_04` / `01_05` (G9) | **계정 잠금 / 비밀번호 실제 초기화** — admin이 풀어줘야 한다 |
| `01_Login_screen`, `05_InitialScreen` | `clearState` → **로그아웃**된다. 뒤에 재로그인이 필요하다 |

그 밖에 반드시 지킬 것:

- 로그인 실패는 **5회 제한**, PIN 오입력은 **계정 잠금**이다. ⛔ 비밀번호를 추측으로 시도하지 말 것.
- **잔액 부족은 FAIL로 위장된다.** 앱은 PIN 입력 전까지 잔액을 검증하지 않아, 의도한 PIN 입력이
  실제로 소모된 뒤에 실패한다. 실행 전에 잔액을 확인한다(`ENVIRONMENT.md` §1.3).
- 신분증/ARC/여권 업로드·QR 케이스는 **실행 직전 `.\push_test_images.ps1`**.
  갤러리 최신 4장이 픽스처라는 전제라, 다른 사진이 쌓이면 앱이 "OCR이 유효하지 않습니다"로 거부한다
  — **앱 버그가 아니다.**
- **동시에 두 개를 돌리지 말 것.** 기기가 하나라 Maestro 실행이 충돌한다.
- **실행 중 기기를 만지지 말 것.** 알림 패널만 내려도 `Element not found`로 죽어 셀렉터 버그처럼 보인다.

---

## 6. 회귀 스위트

폴더 통째 실행(`maestro test Old\`)은 **하면 안 된다** — 순서가 곧 상태 의존성이고, 헬퍼와
다른 빌드 파일까지 딸려 들어가며, 계정을 소모하거나 실결제가 나가는 플로우가 섞인다.
그래서 `run_suite.ps1`이 있다.

```powershell
.\run_suite.ps1 -List                      # ★ 실행 계획·예상 소요만. 옵션 확인은 반드시 -List로
.\run_suite.ps1                            # 기본 = G1~G4 (G9 제외)
.\run_suite.ps1 -Group G1
.\run_suite.ps1 -Balance 12000             # 잔액을 사람이 알려준다(구 UI 홈은 잔액을 마스킹한다)
.\run_suite.ps1 -Resume                    # 못 끝낸 그룹부터
```

⚠️ **`-List`를 빼면 실기기에서 진짜로 돈다.** 옵션을 확인하려던 것이 5시간짜리 실행이 된다.

### 그룹의 축은 기능이 아니라 **계정**이다

구 UI 계정 전환은 드로어 로그아웃 → PIN 잠금화면 → 재로그인 → **PIN 재등록**까지 3~4분이 든다.
기능별로 섞으면 전환이 9회 반복되므로, 계정별로 묶어 **2회**로 줄였다.

| 그룹 | 계정 | 항목 | 예상 | 성격 |
|---|---|---|---|---|
| **G1** | 로그인 불필요 | 5 | 35분 | 진입·가입·로그인 |
| **G2** | `seungsoo818`(한국인) | 28 | 218분 | 본체. 실결제 포함 |
| **G3** | `test123` → `test251024`(외국인) | 3 | 21분 | 순서 고정 |
| **G4** | `seungsoo818` | 3 | 45분 | 설정 변경(자기 원복형) — **반드시 맨 뒤** |
| **G9** | — | 2 | 7분 | **파괴적. 기본 세트에서 제외**(admin 개입 필요) |

기본 세트(G1~G4) = **39항목 / 약 5.3시간**. 시작 전에 `-List`로 끝나는 시각을 확인할 것.

- **G4가 맨 뒤인 이유**: 중간에 실패하면 앱이 외국어·바뀐 PIN·바뀐 비밀번호 상태로 남고,
  그 상태는 **뒤따르는 모든 항목의 진입을 깨뜨린다.** 자동 복구도 이 셋은 되돌리지 못한다.
- **실패 시**: 계속 진행 + 자동 복구(`_suite_recover_old.yaml`).
  단 **복구가 2회 연속 실패하면 중단**한다(안 그러면 남은 항목이 전부 FAIL로 찍히고 몇 시간이 날아간다).
- **잔액 부족은 FAIL이 아니라 SKIP**으로 리포트된다(코드 결함과 갈라 보이게).
  ⛔ 자동 충전은 기본 꺼짐 — KFTC 인출은 OTP/생체인증이 필요해 자동화로 완주되지 않는다.
  **잔액은 사람이 미리 채운다.**
- **준비 상태는 검사하지 않는다.** 계정·픽스처가 준비된 상태를 전제한다 — 준비 안 된 실행은 휴먼 에러다.

순서 제약·제외 파일·서버 3중 검증 등 상세는 `maestro-suite` skill에 있다.

---

## 7. 실패했을 때 — 환경 문제부터 걷어낸다

코드를 고치기 전에 이 순서로 본다. **대부분은 코드 결함이 아니다.**

1. **세션 만료** — 하루가 지나면 만료된다. 진입부터 실패하면 이걸 먼저 의심하고
   `01_01_Login_First_old.yaml`로 재로그인한다. ⚠️ **PIN만으로는 복구되지 않는다.**
2. **기기** — `adb devices -l`(연결·1대) / 지문 인증이 켜지지 않았는지 / 실행 중 기기를 만지지 않았는지.
3. **서버** — `adb logcat`으로 gmeuat가 아닌지(§3).
4. **데이터** — 잔액 / 갤러리 픽스처 / 계정 소모(`test006`·`test007`) / 수취인·계좌 목록 변경.
   ⚠️ 연동 계좌 목록은 계정 상태에 따라 바뀐다(`케이뱅크`가 실제로 사라져 `08_MyQR`이 멈춘 적이 있다).
5. **정적 검사** — `.\lint_flows.ps1`. ERROR면 **돌리기 전에** 고친다.
6. 여기까지 다 통과하면 그때 코드를 본다 → `maestro-debug` skill.

⚠️ **해상도가 바뀌면 좌표만 깨지는 게 아니다.** 기기를 교체했다면 `index`(화면 맨 위 기준)·
`hideKeyboard`(키보드가 없으면 **뒤로가기로 동작한다**)·고정 퍼센트 스와이프가 함께 깨진다.

---

## 8. yaml을 고칠 때 — 가장 자주 터지는 함정

전체 목록은 `CLAUDE.md`와 `maestro-yaml` skill에 있다. 여기에는 처음 온 사람이 반드시 밟는 것만 적는다.

1. **텍스트는 전체 매칭이다.** 부분 문구를 쓰면 **에러 없이 조용히 SKIP**된다 — 가장 자주, 가장 늦게
   터지는 함정이다. `"간편 비밀번호"`(실제 문구는 `"간편 비밀번호를 입력하세요"`) 때문에 실송금
   케이스가 **PIN을 입력한 적 없이 통과**하고 있었다. → 되도록 **`id`로 판정**하고, 문구는 실기기
   덤프로 원문을 확인한다.
2. **id에 패키지명을 박지 말 것.** `com.…:id/xxx` 형태는 stag 빌드에서 절대 매칭되지 않는데,
   대개 조건부 블록 안이라 조용히 SKIP된다. `id: "balloonClose"` 처럼 짧게 쓴다(부분 매칭된다).
3. **assert 없는 조건부는 거짓 통과다.** `extendedWaitUntil`로 결과 도달을 먼저 강제한 뒤 갈래를 처리한다.
4. **YAML 이중인용 안에서는 백슬래시를 2겹**으로. 1겹이면 `Parsing Failed`로 **파일이 통째로 죽는다.**
   `\s`가 필요하면 단일인용(`'GMEPay[\s\S]*입금'`). 개행이 섞이면 `.*`로 부족하다 → `[\s\S]*`.
5. **`inputText`는 한글을 입력하지 못한다** → 검색어는 ASCII 부분문자열로.
6. **범용 `tapOn: "닫기"` 금지** — 엉뚱한 X를 눌러 앱이 런처로 빠져나간 사고가 있다.
7. ⛔ **파일 인코딩**: yaml은 UTF-8이고 한글 주석이 대량으로 들어 있다.
   **PowerShell `Get-Content`/`Set-Content`로 편집하면 파일 전체가 깨진다.** 에디터나 `sed`를 쓴다.
   ⚠️ **개행은 파일마다 다르다**(실측 LF 86 / CRLF 25 / 한 파일 안에 섞인 것 3) → 스크립트로 다시 쓸 때
   **읽은 그대로 보존**한다. 일괄 변환하면 내용은 그대로인데 전 줄이 변경으로 잡힌다. 자세한 건 §10.3.
8. **대형 파일(1000줄+)은 섹션을 나눠 검증**한다. 통짜로 반복 실행하면 한 번에 반나절이 날아간다.

고친 뒤:

```powershell
.\lint_flows.ps1                                       # ERROR 0 확인
.\run_test.ps1 -lang ko -flow "Old\<고친 파일>.yaml"    # 화면을 보면서 1회
```

정적 검사가 통과했다고 플로우가 맞다는 뜻은 아니다 — 좌표·타이밍·앱 결함은 **실행만이 잡는다.**

---

## 9. 결과 보고

- 작업 결과는 **ClickUp 태스크에 댓글로** 남긴다(태스크를 임의로 검색·생성하지 않는다).
- QA 체크리스트 결과는 **SharePoint 마스터**에 직접 적는다
  (GME-IT-Korea > Shared Documents > General > QA Report > Final Checklist > `GME QA Checklist V2.1.xlsx`).
  로컬 `_WORK` 사본에 적고 손으로 옮기던 구조는 **2026-09-16 폐기**했다.
  - 기입은 저장소 루트의 **`gme_excel.py`** 로 한다(Graph Excel API, 셀 단위 → 동시 편집·서식 안전).
    ⛔ **openpyxl·Excel COM 금지**(다른 시트 파트가 깨지거나 저장이 조용히 무시된다).
  - ⚠️ **`PYTHONIOENCODING=utf-8`** 을 붙인다 — 없으면 기입은 되고 마지막 출력에서 죽는다.
  - **결과 열은 라운드마다 이동한다** → 열을 고정하지 말고 헤더를 읽어 확인한다.
  - ★ 기입 전 `get` 으로 행을 대조한다. F열은 중복 문구가 많아 **D열(2Depth)까지** 봐야 한다.
  - ⚠️ **검증하지 않은 행은 비워 둔다.** 통과로 적으면 과대 보고다.

---

## 10. 환경을 옮길 때 — 어디를 고치는가

기기·계정·서버·담당자가 바뀌면 고칠 곳이 **세 층위**로 나뉜다.

| 층위 | 무엇 | 안 고치면 |
|---|---|---|
| ① **사전조건** | 사람이 준비하는 것(계정·잔액·픽스처·권한) | 코드는 멀쩡한데 **FAIL로 위장**된다 |
| ② **코드** | yaml의 값 + `.ps1`/`.json` 설정 | 즉시 실패하거나, 더 나쁘게는 **조용히 SKIP**된다 |
| ③ **skill·문서** | `.claude\skills\`, `CLAUDE.md` | 사람과 Claude가 **낡은 전제로 판단**한다 |

⚠️ **세 층위는 같이 움직인다.** 계정 하나를 바꾸면 ①의 준비 · ②의 yaml 27곳과 `run_suite.ps1`의
`acct` · ③의 그룹표가 전부 대상이다. 한 곳만 고치면 나머지가 낡아 사고가 난다.

### 10.1 ① 사전조건 — 코드로는 못 고치는 것

| 항목 | 옮길 때 할 일 | 빠뜨리면 |
|---|---|---|
| **기기** | 실기기 1대 / USB 디버깅 ON / **생체인증 OFF** | 지문 화면이 끼어들어 플로우가 갈라진다 |
| **해상도** | 바뀌었으면 좌표·`index`·스와이프 재점검(§7) | 2026-09-09 교체에서 **7개 파일이 한꺼번에** 깨졌다 |
| **앱 빌드** | stag 설치 + 서버 LIVETEST 확인(§3) | 에러 없이 **gmeuat 서버로 돈다** |
| **계정 5개** | 아래 표대로 새로 만들거나 값 교체 | 진입부터 막힌다 |
| **잔액** | 아래 임계 이상으로 **사람이 미리 채운다** | PIN이 실제로 소모된 뒤 실패한다 |
| **갤러리 픽스처** | `Test Files\` 4장을 `push_test_images.ps1`로 주입 | "OCR이 유효하지 않습니다" — 앱 버그가 아니다 |
| **admin 권한** | 계정 잠금 해제 · `test006`/`test007` 삭제 · 비밀번호 초기화 복구 | `06_Registration`·G9를 **아예 돌릴 수 없다** |
| **세션** | 하루 지나면 재로그인(`01_01`) | 진입 실패를 셀렉터 버그로 오진한다 |

**계정** — 플로우가 전제하는 5개:

| 계정 | 성격 | 쓰는 곳 |
|---|---|---|
| `seungsoo818` | 한국인·은행 연결됨. **기본** | G1·G2·G4 대부분 |
| `test123` | 외국인·은행 미연결 | `14_02` · `25_Profile_Foreign` · `_switch_test123` |
| `test251024` | 외국인·GMEPay 신청완료 | `14_03` |
| `test006` / `test007` | **회원가입이 생성·소모**한다 | `06_Registration_*` |

⚠️ `15_Loan [01]`은 `seungsoo818`이 **한국인일 때만** 통과한다(국적을 바꾸면 결과가 뒤집힌다).
⚠️ 계정별로 **비밀번호가 다르다.** 값은 `ENVIRONMENT.md`가 아니라 별도 보관처에 있다.

**잔액 임계** — `run_suite.ps1`의 `needs.balance` 실측값. 합산이 아니라 **항목별 최소**이고,
스위트 전체를 돌리려면 **최대 15,000원**이 필요하다.

| 15,000 | 13,000 | 3,000 | 2,000 | 1,000 |
|---|---|---|---|---|
| `02_01` 해외송금 | `16_ATMWithdraw` | `03_Domestic` · `21_Card` | `08_MyQR` | `10_DomesticTopup` |

### 10.2 ② 코드 — yaml에 박힌 값

`Old\` 코드줄 실측 집계다. **표만 옮겨 적었으니, 고칠 때는 `ENVIRONMENT.md` §3을 열 것**
(파일별 위치와 주의사항이 거기 있다).

| 값 | 곳 / 종류 | 대표 |
|---|---|---|
| 계정 ID | 27곳 / 5종 | `seungsoo818`(12) · `test007`(6) · `test006`(4) |
| 은행명 | 17곳 / 2종 | `카카오뱅크`(13) · `신한은행`(4) |
| 수취인명 | 21곳 / 3종 | `GME TEST`(스리랑카, 10) · `COMMERCIAL BANK`(7) |
| 계좌·신분증번호 | 37곳 / 20종 | 신분증번호는 **가입 성공 1회당 소모**된다 |
| 이메일 | 11곳 / 9종 | 가입용 `test006@`/`test007@` · 인바운드 `*@example.com` |
| 금액 | 41곳 / 26종 | 실송금 금액은 위 잔액 임계와 연동된다 |
| 휴대폰번호 | 3곳 / 3종 | ⚠️ `10_DomesticTopup [04]`는 **거부되는 것이 케이스 정의**다 |
| 기기 시리얼 | **0곳** ✅ | 이 상태를 유지할 것 — 러너가 자동 감지한다 |

- **고치는 원칙**: 어느 값이든 무관하면 **목록에서 골라 그 값으로 검증**(동적 선택),
  특정 값이 케이스의 일부면 **하드코딩 유지 + 전제 단언 추가**,
  ⛔ 실송금·실결제는 **동적 선택 금지**(어느 계좌로 돈이 갔는지 재현돼야 한다).
- **자격정보(PIN·로그인 비밀번호)는 일괄 치환이 안 된다.** PIN은 숫자 탭으로, 비밀번호는 보안
  키보드 탭 시퀀스로 흩어져 있다 → **바뀌면 시간이 걸린다는 것을 예상**할 것.
- 이메일(`PROFILE_EMAIL` · `PROFILE_EMAIL_TEST`)은 `ko/en.env` 에 있다. 새 환경에서는 값을 바꾼다.

### 10.3 ② 코드 — 스크립트·설정 파일

**`ENVIRONMENT.md`가 다루지 않는 부분이다.** 여기를 놓치면 첫 줄부터 안 돈다.

| 파일 | 고칠 것 | 안 고치면 |
|---|---|---|
| `~/qa_daily.sh` · `run_report_old.ps1` · `report_scenario_map_old.json` | 저장소 **절대경로**(`C:\GME\qa-automation`) | 데일리 집계·리포트가 빈 결과로 돈다 |
| `run_test.ps1` · `run_suite.ps1` | `$BuildMap` — stag/live **패키지명 2종** | 앱 패키지가 바뀌면 전 플로우가 launch 실패 |
| `run_suite.ps1`의 `$Suite` 블록 | `acct`(계정명) · `needs.balance`(임계) · `est`(소요) · `f`(파일 경로) · 그룹과 **순서** | 계정 전환이 어긋나 뒤 항목이 연쇄 실패 |
| `run_suite.ps1` `-MaxCharge` | 자동 충전 상한 기본 **30,000원**(실계좌에서 빠진다) | `-AutoCharge`를 쓸 때만 의미 있다 |
| `push_test_images.ps1` | `Test Files\` **4장의 파일명과 touch 순서**(= 갤러리 index 0~3), push 경로 `/sdcard/Pictures` | 인덱스가 밀려 업로드 케이스가 전부 깨진다 |
| `env\ko.env` · `en.env` | UI 문구 사전. 현재 **381키, 양쪽 동일** | 한쪽에만 있으면 그 언어에서 **조용히 SKIP** |
| `lint_labels.json` | 실측 라벨·id 사전(`wrongLabels`·`genericLabels`·`injectedEnvVars` 등) | 빌드가 올라가 문구가 바뀌면 검사기가 낡는다. ⛔ **추측으로 넣지 말 것** |
| `lint_whitelist.txt` | 검사 예외(`RULE 파일명:줄`) | "확인해서 의도된 것"만. 줄 번호는 파일이 밀리면 어긋난다 |
| `gme_excel.py` (저장소 루트) | `GME_CLIENT_ID`·`GME_TENANT_ID` 환경변수, 대상은 **SharePoint 공유 링크**(`-f`) | 링크가 바뀌면 `HTTP 404`. 토큰은 `~/.gme_excel_token.json` 에 계정별로 남는다 |

⚠️ **저장소 루트의 `run_test.ps1` 은 갤러리 픽스처 전용 래퍼**다 — 이미지를
`/sdcard/DCIM` 에 push 한 뒤 `Maestro\run_test.ps1` 로 그대로 넘긴다(인자 동일).
`21_Card [24]`·`06_Registration` 처럼 갤러리가 필요한 것만 이걸 쓰고, 나머지는 `Maestro\` 쪽을 쓴다.

### 10.4 ③ skill·문서

`.claude\skills\`는 **저장소에만 있고 정본(OneDrive)에는 없다.** Claude Code가 이 저장소에서
작업할 때 자동으로 읽고, 사람은 그냥 파일을 읽으면 된다.

| skill | 환경이 바뀌면 낡는 항목 |
|---|---|
| `maestro-run` | 빌드·패키지 2종 / CWD 경로 / **자동 로그아웃 ~10분** / 백그라운드 판단 기준(도구 10분 vs 긴 플로우 17~18분) / 산출물 경로(`shots_runs\`·`suite_logs\`) |
| `maestro-suite` | 그룹표의 **계정명** / 순서 제약(`13_04`의 **72시간 만료**, `02_01`→`02_02`, `14_01`→`02`→`03`, `25_Profile_Foreign`은 `14_02` 직후) / 제외 파일 / `est` 실측값 |
| `maestro-yaml` | 구 UI 전환 규칙(id) / **해상도 교체 사례**(1080x2220 → SM-S911N 1080x2340) / 시스템 사진 피커 **좌표 분기** |
| `maestro-debug` | 문구 대응표(빌드마다 바뀐다) / 환경 대 코드 분류 기준 / 로그 경로 |

- **`CLAUDE.md`**(저장소 루트)에도 환경 값이 있다: 정본 절대경로 · 빌드 정책 · 체크리스트 경로와
  **+1 오프셋** · ClickUp/Jira/SharePoint 식별자.
- 담당자가 바뀌면 **개인 전역 지침**(`~\.claude\CLAUDE.md`)에도 같은 값이 있다 → 넘겨받는 사람이
  자기 것으로 옮겨 적어야 한다.

### 10.5 옮기는 순서

1. **사전조건** 준비 — 계정 5개 · 잔액 · 픽스처 · admin 권한 (§10.1)
2. **스크립트** 경로·패키지 — 데일리 배치 3곳의 절대경로, `$BuildMap` (§10.3)
3. **env** — `ko/en.env` 문구·계정 이메일 (§10.2)
4. **yaml 값** — 계정·은행·수취인·계좌·이메일·금액 (§10.2, 상세는 `ENVIRONMENT.md` §3)
5. **검사기 사전** — `lint_labels.json` · `lint_whitelist.txt`
6. **skill·CLAUDE.md** 갱신 (§10.4)
7. **체크리스트 기입 도구** — `gme_excel.py` 환경변수·`login`([README_win.md](README_win.md)).
   결과를 적을 사람만 하면 된다
8. **검증** — 아래 순서로, 한 단계씩 통과시킨 뒤 다음으로 간다

```powershell
.\lint_flows.ps1                                       # ERROR 0
.\run_test.ps1 -lang ko -flow "Old\09_Home_old.yaml"   # 부작용 0 스모크
.\run_suite.ps1 -List                                  # 계획·소요만
.\run_suite.ps1 -Group G1                              # 진입·로그인 계열부터
```

⚠️ 정적 검사가 통과했다고 맞는 것은 아니다. **환경 이전 직후에는 반드시 화면을 보면서** 돌린다.

---

## 11. 한 장 요약 — 하지 말 것

| ⛔ | 왜 |
|---|---|
| 저장소(GitHub) 사본을 편집 | 다음 동기화가 지운다. 편집은 OneDrive 정본에서만 |
| `$PSNativeCommandArgumentPassing` 생략 | env 값의 `\|` 가 cmd 파이프로 해석돼 전 플로우 즉사 |
| `run_suite.ps1`을 `-List` 없이 옵션 확인 | 실기기에서 5시간짜리가 진짜로 돈다 |
| 동시에 두 개 실행 | 기기가 하나라 충돌한다 |
| 실행 중 기기 조작 | `Element not found`로 죽어 셀렉터 버그로 오진한다 |
| 비밀번호 추측 시도 | 5회 = 계정 잠금. admin 개입이 필요하다 |
| 기기 시리얼 하드코딩 | 기기는 교체된다. 러너가 자동 감지한다 |
| PowerShell `Set-Content`로 yaml 편집 | 파일 전체가 깨진다 |
| 실계정·실개인정보를 yaml에 적기 | 테스트 계정 값만 쓴다. 실제 사람에게 닿는 값은 애초에 넣지 않는다 |
| 검증 안 한 행을 체크리스트에 Pass로 | 과대 보고다. 비워 두는 것이 맞다 |

막히면 `ENVIRONMENT.md` → `PROGRESS.md` → skill 순서로 본다.
