# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 이 저장소의 성격

소스 코드가 아니라 **GME Remittance 안드로이드 앱의 Maestro E2E 테스트 플로우(yaml) 모음**이다.
빌드·린트·유닛테스트가 없고, "테스트를 돌린다" = **USB로 연결된 실기기에서 앱을 조작한다**는 뜻이다.
에뮬레이터는 사용하지 않는다(생체인증·실계좌 연동 때문).

이 문서는 **지침만** 다룬다. 나머지는 따로 있다:

### 📁 `docs\` — 사람이 읽는 문서는 전부 여기 (2026-09-16 정리)

흩어져 있던 md 를 한곳에 모았다. **문서를 새로 쓰면 여기에 둔다.**

- [docs/PROGRESS.md](docs/PROGRESS.md) — 파일별 진행 현황(완료/잔여/BLOCKED/보류)
- [docs/GUIDE.md](docs/GUIDE.md) — 넘겨받은 사람이 처음 돌리기까지
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) — 사전조건(계정·잔액·픽스처·되돌릴 수 없는 실행)과 하드코딩 인벤토리
- [docs/SUITE.md](docs/SUITE.md) — 스위트 문서였으나 **내용은 `maestro-suite` skill로 옮겼다**(포인터만 남음)

⚠️ **`docs\` 로 옮기면 안 되는 md 가 있다** — 경로가 고정이라 옮기면 조용히 로드되지 않는다:
**이 파일(`CLAUDE.md`, 저장소 루트)** 과 **`.claude\skills\*\SKILL.md`**.
린터 산출물 `lint_*.md` 는 문서가 아니라 **돌릴 때마다 다시 만들어지는 산출물**이라
`.gitignore` 로 제외한다(`artifacts/` · `lint_*.md`).

### `.claude/skills/` — 작업별 상세 절차(skill)

해당 작업을 할 때 자동으로 불려 온다:
  - `maestro-run` — 플로우/스위트 실행, 실행 전 점검, 빌드 전환, 백그라운드 판단
  - `maestro-debug` — 실패 진단. **환경 문제(기기 끊김·자동 로그아웃·세션 만료)와 코드 결함을 구분**
  - `maestro-yaml` — yaml 작성. 셀렉터 함정, 거짓 통과를 막는 assert 구조, 임시본 재추출
  - `maestro-suite` — 회귀 스위트. 태그·순서 제약·제외 파일·재작성 계획

### 폴더는 하나다 — 2026-09-22 병합

종전에는 OneDrive 에 정본을 두고 이 저장소가 그 **사본**이었다. 두 벌이 있으면 반드시 한쪽이 낡아서
(2026-09-10 에 9일치가 벌어져 저장소 린터가 이미 고쳐진 결함 11건을 ERROR 로 리포트했다)
**이 저장소 하나로 합쳤다.** 미러 동기화 스크립트(`sync_from_source.ps1`)는 폐기했다.

```
C:\GME\qa-automation\            ★ 편집·실행·커밋이 전부 여기서 일어난다
├── Maestro\
│   ├── *.yaml            # 개편 UI(V3)용 사본 — 건드리지 않는다
│   ├── Old\*.yaml       # ★ 편집 대상: 구 UI(V2)용, `_old` 접미사
│   ├── env\{ko,en}.env  # i18n 문자열
│   ├── Test Files\      # 갤러리 업로드용 이미지 픽스처 4장
│   ├── run_test.ps1      # 실행 러너 (CWD 는 항상 `Maestro\`)
│   ├── run_suite.ps1 · lint_flows.ps1 · push_test_images.ps1
│   └── shots_runs\ · suite_logs\   # 실행 산출물(gitignore)
├── Checklist\          # SharePoint 마스터 바로가기(.url) + 참고 사본 xlsx
├── docs\ · gme_excel.py · CLAUDE.md · .claude\skills\
└── GME QA Checklist V2.1.xlsx   # 데일리 배치가 매일 읽고 덮어쓰는 작업본
```

**OneDrive 쪽에 남은 것 — 증적뿐이다. 작업 파일은 없다.**
`개인용 - Automation\` 에는 스크린샷(`Maestro\shots_*`, `Screenshot\`)·실행 로그(`suite_logs\`)·
오래된 백업 폴더만 남겨 클라우드 백업을 유지한다. 실행 로그에는 **계정 ID·잔액·거래내역·실 이메일**이
그대로 남아 git 에 올리지 않는다.
- 앞으로 생기는 증적은 `Maestro\shots_runs\` 에 쌓인다(gitignore) → 클라우드 보관이 필요하면
  주기적으로 OneDrive 로 옮긴다(수동).
- `_pre_merge_20260922\` 는 병합 전 원본을 담아둔 **롤백용**이다. 이상 없으면 지워도 된다.

⛔ **외부 스크립트 3곳이 이 경로를 박아 둔다** — 경로를 또 옮기면 같이 고쳐야 한다:
`~/qa_daily.sh`(`--yaml-dir`·`--xlsx`) · `C:\Users\GME\run_report_old.ps1` ·
`C:\Users\GME\report_scenario_map_old.json`(`yaml_dir`, 이게 리포트 스크립트의 기본값을 덮어쓴다).

### 저장소에 올라가는 값 — `secrets.env` 는 2026-09-18 폐지했다

⚠️ **이 저장소는 2026-09-11부터 GitHub(`basshul/YAML`, 비공개)에 푸시된다.**

종전에는 개인정보를 `Maestro\env\secrets.env` 에 분리해 두었으나, **전부 테스트 전용 계정·이메일이라
공개돼도 무방하다는 사용자 판단(2026-09-18)** 으로 파일을 없애고 값을 `env\ko.env`·`en.env` 로 옮겼다
(`PROFILE_EMAIL` · `PROFILE_EMAIL_TEST`). `.gitignore` · `sync_from_source.ps1` · `run_test.ps1` 의
관련 처리도 함께 제거했다.

→ 이제 **저장소만 받아도 실행에 필요한 파일이 전부 있다.**

⛔ 단 기준은 남는다: **실제 사람·실계정에 닿는 값은 애초에 넣지 않는다.** 그런 값이 필요해지면
그때 다시 분리 파일을 만든다.

- 실행 로그(`suite_logs\`)에는 **계정 ID·잔액·거래 내역·실 이메일**이 그대로 남는다 → 추적하지 않는다.
  증적은 정본(OneDrive)에 그대로 있다.
- 앱이 화면에 보여주는 값이면 **주입보다 런타임 판독이 낫다**: `21_Card [12]` 의 카드 CVC 는
  `[11]` 이 `copyTextFrom: cvcnumbertext` + `evalScript` 로 읽어 `output.cvc1~3` 으로 넘긴다.
  로그에는 치환 전 원문만 찍혀 값이 남지 않는다.
- **로그인 비밀번호·PIN 은 평문으로 둔다**(2026-09-18 결정). 테스트 계정이라 공개돼도 무방하고,
  로그인은 **보안 키패드를 글자별 접근성 라벨로 탭**하는 구조라 변수로 빼도 탭 시퀀스에 그대로 드러난다.
  오히려 디버깅만 어려워지고, 저장소 단독 실행이 깨진다. 공개 전환 시에는 **계정 자체를 교체**하는 쪽이 맞다.
- ⛔ 이전 히스토리(로그·실 이메일 포함)는 로컬 `backup-pre-squash-20260911` 브랜치에만 있다 →
  **`git push --all` / `--mirror` 금지.** `main` 만 명시해 푸시한다.

## 실행 명령

CWD는 항상 `Maestro\` 루트다. 플로우 경로는 그 기준의 상대경로로 넘긴다.

```powershell
$PSNativeCommandArgumentPassing = 'Legacy'   # ★ 생략하면 env 값의 `|`가 cmd 파이프로 해석돼 즉사
.\run_test.ps1 -lang ko -flow "Old\14_01_Deposit_seungsoo818_old.yaml"
.\run_test.ps1 -lang en -flow "Old\09_Home_old.yaml"
.\run_test.ps1 -lang ko -flow "Old\09_Home_old.yaml" -device 27dbf1ec440d7ece
.\run_test.ps1 -lang ko -flow "Old\09_Home_old.yaml" -Build live   # 운영(Live) 요청이 있을 때만
```

### ★ 어느 빌드로 도는가 (2026-09-03 사용자 선언)

| 상황 | 패키지 | 서버 | 러너 |
|---|---|---|---|
| **기본**(언급 없음) | `com.gmeremit...gmeremittance_native.stag` | **LIVETEST로 지정** | `-Build stag` (기본값) |
| **운영/Live 요청 시** | `com.gmeremit...gmeremittance_native` | 운영 | `-Build live` |

⛔ `.livetest` 빌드는 **더 이상 쓰지 않는다** — 기기에서 이미 삭제됐다(2026-09-03 adb 확인).
`env\*.env`의 `APP_ID` 기본값도 `.stag`로 바꿨고, 러너의 `-Build`가 그 값을 덮어쓴다.
`-AppId <pkg>`는 임의 패키지용으로 남겨뒀고 `-Build`보다 우선한다.

- `-device` 생략 시 `adb devices`로 자동 감지하고, **2대 이상이면 실행을 거부한다**(실계좌 플로우가
  엉뚱한 기기에서 도는 사고 방지). 시리얼을 하드코딩하지 말 것 — 기기는 교체된다.
- `run_test.ps1`은 `env\<lang>.env`를 파싱해 `--env KEY="VALUE"`로 넘긴다. 값의 인용은 필수다.
- 갤러리 의존 케이스(신분증/ARC/여권 업로드, QR 스캔)는 **실행 직전 `.\push_test_images.ps1`**을
  돌려야 한다. `icon_thumbnail`의 index가 "테스트 이미지 4장이 갤러리 최신 4개"라는 전제에 기대므로,
  다른 이미지가 쌓이면 앱이 "OCR이 유효하지 않습니다"로 거부한다(앱 버그가 아니다).
- 저장소 루트에도 `run_test.ps1` 이 있다 — **갤러리 픽스처가 필요한 케이스 전용 래퍼**다
  (`21_Card [24]` 글로벌 QR, `06_Registration` OCR). 이미지를 push 한 뒤 `Maestro\run_test.ps1` 로
  **그대로 넘긴다**(2026-09-23 재작성). 인자는 같고 `-flow` 는 `Maestro\` 기준이다.
  ⚠️ 종전엔 러너 전체를 **복사해 갖고 있어** `Maestro\` 쪽에만 들어간 개선(플로우가 쓰는 env 만 추리기)이
  여기엔 없었고, env 가 475개로 늘자 **"The command line is too long."** 로 죽었다.

### 단일 케이스만 돌리는 법

Maestro에는 케이스 선택 옵션이 없다. 한 파일이 곧 한 실행 단위다.
큰 파일을 부분 검증할 때는 **본 파일에서 필요한 구간을 잘라 임시 yaml로 추출**해 돌리고,
**수정은 항상 본 파일에 하고 임시본은 재추출**한다(임시본을 고치면 반영이 유실된다).
`Old\_tmp_*.yaml`이 그 흔적이다.

### 회귀 스위트

`Maestro\run_suite.ps1`이 `Old\` 플로우를 정해진 순서로 묶어 돌린다.
**태그·순서 제약·제외 파일·재작성 계획은 `maestro-suite` skill에 있다**
(`.claude/skills/maestro-suite/SKILL.md`) — 스위트를 건드리기 전에 읽을 것.

```powershell
.\run_suite.ps1 -List                     # 실행 계획만 출력
.\run_suite.ps1 -Names 08_MyQR,03_Domestic         # 기본 = .stag 빌드 + LIVETEST 서버
.\run_suite.ps1 -Group G2 -Build live               # 운영(Live) 요청이 있을 때만
```

- **동시에 두 개를 돌리지 말 것.** 기기가 하나라 Maestro 실행이 충돌한다.
- PowerShell 인자 전달은 **해시테이블 스플래팅**으로 한다. 배열 스플래팅은 `-AppId` 같은
  명명 파라미터에 바인딩되지 않는다(`$args`는 자동 변수라 이름으로 쓸 수 없다).

### stag 빌드에서 서버를 코드로 못박는다 — **이제 이게 기본 경로다**

플로우는 `appId: ${APP_ID}`이고 러너의 `-Build`가 그 값을 정한다. ⚠️ **`clearState`가 서버 선택을 빌드
기본값(stag=STAG)으로 초기화**하므로, 그대로 두면 **전 스위트가 STAG 서버로 조용히 돌아간다.**

```yaml
- runFlow: "_server_override_old.yaml"   # 매 launchApp 뒤에 (콜드 실행마다 스플래시가 뜬다)
```

헬퍼는 **항등 시퀀스**다 — LIVETEST를 찍고 `button1`을 누른 뒤 `launchApp`으로 되살려 한 번 더 누른다:
- 선택을 바꾸면 버튼이 `CONTINUE` → **`APPLY & QUIT`** 로 바뀌며 **앱이 종료된다**(둘 다 id `button1`).
- Maestro는 `checked:`를 무시해 "이미 LIVETEST인지" 판별이 **불가능하다** → 판별하지 않는다.
- 재실행에 `clearState`를 쓰면 선택이 또 초기화된다 → **`launchApp`만** 쓴다.

검증은 코드가 아니라 **접속 호스트**로 한다: `adb logcat -d | grep -oE '(livetest|gmeuat)\.gmeremit\.com'`.
`run_suite.ps1`은 이걸 **3중으로 본다**: P0에서 빌드 설치 확인 → **첫 항목 직후 조기 검사**
(gmeuat가 잡히면 즉시 중단) → 종료 시 전체 집계. 3시간 돌고 나서야 엉뚱한 서버였다는 걸 아는 게
최악이라 조기 검사를 넣었다. 강제 누락 자체는 린터 **`E08`**이 정적으로 잡는다.

7.20.0에서 인앱 배너 id가 `btnTwo` → **`btnClose`** 로 바뀌었고, 홈 팝업은 **큐**로 뜨므로
`_dismiss_popups_stag_old.yaml`을 쓴다(즉석 블록을 만들지 말 것).

## 플로우 파일 구조

```yaml
appId: ${APP_ID}      # 러너의 -Build 가 정한다(기본 .stag)
---
# 공통 진입: launchApp → Server Override 스플래시 → PIN 입력 → 홈
# [01] [High] <화면> - <검증 내용>
- tapOn: { id: "..." }
```

- **appId는 `${APP_ID}`가 원칙**이다(`Old\` 49개). `.stag`를 헤더에 박은 7개는 EasyCare i18n 전용이라 그대로 둔다.
  `.livetest`/`.sgt`를 헤더에 박은 파일은 **없어야 한다** — 있으면 린터 `W09`가 잡는다.
- 케이스 헤더는 `# [NN] [Low|Medium|High] <설명>` 규약이고 이게 ClickUp 케이스와 1:1로 대응한다.
- `_` 접두사 파일은 **헬퍼 플로우**다(`runFlow: file:`로 호출). 예: `_change_language_old.yaml`(env `LANG_LABEL`),
  `_server_override_old.yaml`, `_switch_test123_old.yaml`.
- 반복되는 문자열(비밀번호·언어·UI 라벨)은 `env:`/`${VAR}`로 변수화한다.
  단 **로그에는 치환 전 원문이 찍히므로** 실제 치환 여부는 화면 동작으로 확인해야 한다.

## 구 UI(V2) vs 개편 UI(V3)

같은 앱에 두 홈이 공존하고 실행마다 갈린다. `Old\`는 **구 UI(`HomeActivityV2`)** 기준이며,
루트의 개편 UI판을 그대로 가져오면 진입 경로부터 깨진다. 반복 적용되는 전환 규칙:

| 대상 | 개편 UI | 구 UI |
|---|---|---|
| 홈 도달 판정 | `text: "Home"` | **`id: bottom_item_home`** |
| 설정 진입 | 프로필 탭 / 기어 좌표탭 | **드로어 `iv_nav` → "설정"** |
| 로그아웃 | 프로필 탭 | **드로어에만 있다** |
| 입력 필드 | 퍼센트 좌표 | **컨테이너 id**(구 UI는 native라 id가 살아 있다) |

- ⚠️ **PIN(간편 비밀번호) 화면은 두 UI가 같다 — 전환 대상이 아니다.** 그래서 위 표에서 뺐다.
  구 UI `ActivityLockScreen` 실기기 덤프(2026-09-01)에도 `"4자리 숫자를 입력하세요"`·
  `"간편 비밀번호를 입력하세요"`·`input_dot_1`~`4`·`keypadContainer`가 그대로 있다.
  id를 권장하는 건 전환 때문이 아니라 **언어·문구 변경에 안 흔들려서**다.
  → 종전 표에 이 항목이 "개편 UI = 문구 / 구 UI = id"로 적혀 있어 **"문구는 V3 전용"으로 오독**했고,
    그 전제로 `Old\`에서 76곳을 걷어냈다가 되돌린 사고가 있었다(2026-08-31).
- **홈 복귀 판정에 `btnTransfer`를 쓰지 말 것.** 구 UI 홈은 스크롤 위치를 유지해서 상단 카드가
  화면 밖일 수 있다. 도달 판정은 `bottom_item_home`, 필요하면 `scrollUntilVisible direction: UP`.
- **`back` 1탭이 액티비티를 벗어난다고 가정하지 말 것.** 한 액티비티 안에서 뷰만 바꾸는 화면이 있고,
  입력 필드가 있으면 back이 키패드만 닫는다. `repeat { while: notVisible <다음 화면 id> }`로 반복한다.
- **범용 `tapOn: "닫기"` 금지** — 엉뚱한 X를 눌러 앱이 런처로 빠져나간 사고가 있다.
  인앱 배너는 `btnTwo`, **7.20.0부터는 `btnClose`** 다 → `btnTwo|btnClose`로 둘 다 받는다.
- **계정 전환 경로가 다르다**: `iv_nav` → 로그아웃 → **PIN 잠금화면** → `loginpwidhidpass` →
  `btn_diaog_ok`(앱 오타 `diaog`) → `usernameId` 폼. 이 경로는 **기존 PIN을 해지**하므로 로그인 직후
  "간편 비밀번호를 생성해 주세요"가 뜬다 → **기존과 같은 PIN으로 재등록**해야 한다. 중간에 끊기면 PIN 없는 상태로
  남아 다음 실행 진입 자체가 막히니, 진입 블록에도 이 분기를 넣어둔다.
- 재로그인 1회 비용이 크므로 **같은 계정이 필요한 케이스를 묶는다** → 케이스가 번호순으로
  실행되지 않게 되며, 그럴 때는 파일 헤더에 실행 순서를 반드시 명시한다.

## Maestro 셀렉터 함정

- **텍스트는 전체 매칭**이다. 부분 문구를 그대로 쓰면 **에러 없이 조용히 SKIP**된다 —
  가장 자주, 가장 늦게 터지는 함정이다. 2026-08-28 전수 점검에서 나온 실제 사례:

  | 쓰던 값 | 실제 화면 문구 | 여파 |
  |---|---|---|
  | `"간편 비밀번호"` | **"간편 비밀번호를 입력하세요"** | `02_01 [02]`가 **PIN을 입력한 적이 없었다** → 실송금 미성립인데 통과 |
  | `"로그인 세션이 만료"` | "…만료되었습니다.**⏎**서비스를…" | 세션 만료를 감지 못함 |
  | `"잔액"` | "잔액이 부족합니다" | 잔액부족 팝업을 못 닫음 |
  | `"국내송금"` / `"예약"` | **"국내 송금"**(공백) / **"예약하기"** | 홈 진입 실패 |

  → **문구 가드는 실기기 덤프로 원문을 확인**하고, 되도록 `id`로 판정한다.
  잠금화면은 `id: input_dot_1`, 홈은 `id: bottom_item_home`이 언어·문구에 흔들리지 않는다.
  개행이 섞이면 `.*`로 부족하다 → **`[\s\S]*`**(단일인용).
- **id에 패키지명을 박지 말 것.** `id: "com.…livetest:id/xxx"` 형태는 **stag 빌드에서 절대
  매칭되지 않는데**, 대개 조건부 블록 안이라 **에러 없이 SKIP**된다. Maestro는 짧은 id를 부분
  매칭하므로 `id: "balloonClose"` 로 쓴다. (2026-08-28 정리: `04_Menu_History` **145곳** 등 175곳)
- **다이얼로그·바텀시트가 뜨면 뒤 화면이 접근성 트리에서 사라진다.** 뒤 요소를 겨냥한 assert가
  `Element not found`로 죽는다 → **팝업을 먼저 닫고** 진행한다. 반대로 시트 안에서는 뒤 화면과
  텍스트가 겹쳐도 모호하지 않다(`02_02` "기존 수취인 추가" 시트에서 실측).
- YAML **이중인용 안에서는 백슬래시를 2겹**으로 쓴다(1겹이면 `Parsing Failed`로 파일이 통째로 죽는다).
  `\s`가 필요하면 단일인용(`'GMEPay[\s\S]*입금'`)을 쓴다.
- `text:` assert가 실패해도 `id:`는 즉시 성공하는 경우가 있다 → **가능하면 id 우선**.
- `rightOf`/`below` 상대 셀렉터는 스와이프 액션 아이콘에서 불안정하다 → index 기반으로.
- `inputText`는 **한글을 입력하지 못한다** → 검색어는 ASCII 부분문자열을 쓴다.
- PIN 키패드는 셔플되지만 **화면 진입 시에만이고 탭마다가 아니다**(2026-09-01 실측 정정).
  대기 없는 연타 3회가 3/3 정확히 입력됐다 → **탭 사이 대기는 불필요하다.**
  위험한 건 **첫 탭 전**이다: 화면 도달을 안 기다리고 누르면 **같은 글자를 가진 다른 요소**를 집는다
  (실례: 금액에 `"2"`를 넣은 직후 대기 없이 `tapOn: "2"`로 PIN 시작).
  → **숫자 탭 앞에 `id: input_dot_1`(또는 `keypadContainer`) 도달 대기를 둔다.**
- 접근성 트리에 안 잡히는 WebView 텍스트가 있다(예: "취소 수수료") → 그 경우만 좌표로 우회.
- **조건부 처리만 있고 assert가 없으면 거짓 통과가 된다.** 성공·실패 팝업을 둘 다
  `runFlow: when:`으로만 두면 **아무것도 안 떠도 EXIT=0**이다. `extendedWaitUntil`로
  **결과 도달을 먼저 강제**한 뒤 갈래를 처리한다(`02_01 [02]`가 이 구조로 통과하고 있었다).

## 편집 시 주의

- yaml은 **UTF-8**이고 한글 주석이 대량으로 들어 있다.
  **PowerShell `Get-Content`/`Set-Content`로 편집하지 말 것** — 파일 전체가 깨진다.
  Edit/Write 도구나 bash(`sed`, heredoc)를 쓴다.
- ⚠️ **개행은 파일마다 다르다 — "CRLF"로 단정하지 말 것**(2026-09-15 전수 실측으로 정정).
  `Maestro\` 전체 114개 중 **LF 86 / CRLF 25 / 한 파일 안에 섞인 것 3**
  (`13_01_Rate_Indonesia` · `13_04_Request` · `13_05_ExistingSender`).
  `env\ko.env`는 LF인데 `en.env`는 CRLF다. BOM도 `Old\`엔 없지만 루트 개편 UI 사본
  `04_01_Change_SimplePassword.yaml` · `04_06_Settings_Change languages.yaml` **2개에는 있다.**
  → 스크립트로 파일을 다시 쓸 때는 **읽은 바이트 그대로 보존**한다(`newline=""`로 읽고 감지한
  개행으로 join). 일괄 변환하면 내용은 그대로인데 **전 줄이 변경으로 잡히고**, `.gitattributes`가
  `* -text`라 저장소에도 그대로 올라간다. 쓴 뒤 `\r\n` 개수를 원본과 대조해 검산할 것.
- 대형 파일(1000줄+)은 처음부터 **섹션 분리 → 개별 검증 → 전체 1회 확인** 순서로 간다.
  통짜로 반복 실행하면 한 번에 반나절이 날아간다.
- 실행 중에는 **기기를 만지지 말 것.** 알림 패널을 내리면 "Element not found"로 실패해
  셀렉터 버그처럼 오진하기 쉽다.

## 실행이 실계좌·실계정에 닿는다

- 실기기 + 실서비스라 **실제 결제·충전·송금이 발생할 수 있다.**
  GME Shop은 잔액 부족 시 "구매하기" 탭만으로 **실계좌 자동충전**이 일어난다.
  예약(KTX) 케이스는 가까운 날짜를 잡으면 취소 수수료가 붙는다 → 최대한 먼 미래로.
- 로그인 실패는 **5회 제한**, PIN 오입력은 계정 잠금이다. 비밀번호를 추측으로 시도하지 말 것.
- ⛔ **자격정보(로그인 비밀번호·PIN)를 이 저장소의 문서에 적지 않는다.** 이 두 md는 커밋되는 파일이다.
  실제 값은 메모리(`project_01_login`)에만 두고, 문서에서는 "정상 PIN" / "정상 비밀번호"로 부른다.
  ⚠️ 값이 바뀌는데 문서가 안 따라오면 **폐기된 값으로 실계정에 시도하는 사고**가 난다(실제로 있었다).
- **유휴 ~10분이면 자동 로그아웃**된다. 그 잠금 화면(`autologout.AutoLogoutActivity`,
  "Enter password to unlock" + 보안 키패드)은 ★**접근성 트리에 노출되지 않고 덤프는 직전 화면을
  돌려준다** → 플로우가 엉뚱한 화면으로 오진해 **보안 키패드를 블라인드로 누른다**(2026-09-15 사고).
  판정은 `adb shell dumpsys activity activities | grep topResumedActivity` 뿐이고,
  `run_test.ps1` 이 실행 전에 보고 **exit 3 으로 끊는다**(`clearState` 플로우는 예외).
  복구는 `Old\01_01_Login_Success_old.yaml` 하나뿐이다 — 앱 언어가 한국어로 돌아가므로 en 검증
  중이면 `_set_lang_en_old.yaml` 을 다시 돌린다. **실행 사이에 공백을 두지 말 것.**
- 하루가 지나면 세션이 만료된다. 진입부터 실패하면 이걸 먼저 의심하고
  `01_01_Login_First_old.yaml`로 재로그인한다(PIN만으로는 복구되지 않는다).
  ⚠️ 만료 다이얼로그를 **닫고 진행하지 말 것** — 구 UI는 PIN으로 복구되지 않으므로 의미가 없다.
  `assertNotVisible: '로그인 세션이 만료[\s\S]*'` 로 **즉시 실패**시키고, 그 판정은
  **홈 대기보다 앞**에 둔다(뒤에 두면 홈 대기가 먼저 타임아웃 나서 원인이 가려진다).
- `clearState: true`가 걸린 플로우(`01_Login_screen_old`, `05_InitialScreen_old`)는 실행하면
  **로그아웃된다** → 이후 재로그인 플로우가 필요하다.

## 결과 보고

작업 결과는 ClickUp 태스크에 **댓글로** 남긴다(태스크를 임의로 검색·생성하지 않는다).
`Automation Report.bat`은 `qa_report.json`을 읽어 데일리 리포트를 ClickUp 문서로 올리는 별도 배치다.
⚠️ 배치 파일에 한글을 직접 넣으면 cmd 파서가 밀려 깨진다 → ASCII 런처 + `.ps1` 분리가 원칙이다.

### QA 체크리스트 결과 기입 (2026-09-16 **전면 교체**)

★ **기입 대상은 SharePoint 마스터다.** 로컬 `_WORK` 사본에 적고 사람이 손으로 옮기던 구조는 폐기했다.

```
GME-IT-Korea > Shared Documents > General > QA Report > Final Checklist
└── GME QA Checklist V2.1.xlsx      ★ 여기에 직접 쓴다
```

정본 `Checklist\` 에는 이 파일을 가리키는 **`.url` 바로가기**와 참고 사본만 둔다.

#### 도구 — `gme_excel.py` (저장소 루트)

Graph Excel API 의 `range(address=...)` **PATCH** 라 **셀 단위**로 쓴다. 파일을 통째로 교체하지
않으므로 **다른 시트·서식·수식이 보존되고, 다른 사람이 동시에 편집 중이어도 안전**하다.
설치·사용 안내는 **[docs/README_win.md](docs/README_win.md)**(Windows 기준, 이 팀 환경) —
macOS 원본은 [docs/README_mac.md](docs/README_mac.md).

```powershell
$env:GME_CLIENT_ID="0ba0c638-c539-4584-b803-8af3ae62ddd1"
$env:GME_TENANT_ID="b19514d1-d63d-4dda-b580-d80917436738"
$env:PYTHONIOENCODING="utf-8"      # ★ 없으면 셀은 써지고 마지막 print 에서 cp949 오류로 죽는다
$LINK='<SharePoint 공유 링크>'      # `&nav=...` 는 빼도 된다(실측 확인)
python gme_excel.py -f $LINK sheets
python gme_excel.py -f $LINK get '시트명' D39:I57
python gme_excel.py -f $LINK set '시트명' H39 'Pass'
```

- 로그인은 최초 1회 `python gme_excel.py login`(브라우저 인증). 토큰 `~/.gme_excel_token.json`,
  scope **`Files.ReadWrite.All`**, refresh 자동.
  ⚠️ **`login` 은 자동모드가 막는다** → 사용자가 `!` 를 붙여 직접 실행해야 한다.
  ⚠️ login 이 성공해도 `✅` 출력에서 UnicodeEncodeError 가 난다 — **토큰은 이미 저장됐으니 무시**.
- ⛔ 스크립트가 저장소 밖(`D:\다운로드\` 등)에 있으면 자동모드가 `Code from External` 로 막는다.

#### 기입 전에 — 행을 **매번** 대조한다

```powershell
python gme_excel.py -f $LINK get 'Checklist(Livetest) (Basshu)' D39:I57
```

- ★ **F열(Checklist)만 보고 행을 정하지 말 것.** 같은 문구가 여러 행에 있다 —
  "이용약관 동의 화면 노출 확인" 은 Initial Screen 과 로그인화면 `Register Here` 양쪽에 있다.
  **D열(2Depth)까지 봐야 귀속이 갈린다**(2026-09-16 실제로 이걸로 2건의 귀속이 바뀌었다).
- **결과 열은 라운드마다 이동한다.** 9행 = 라운드 라벨, 10행 = `iOS Result`/`Android Result` 쌍.
  열을 고정하지 말고 헤더를 읽어 확인한다.
- ⚠️ **검증하지 않은 행은 비워둔다.** 통과로 적으면 과대 보고다. 자주 비는 것:
  생체인식(기기 생체인증 OFF) / OTP 제출 / 영수증 **다운로드**(보기까지만) / 문자·이메일 **수신**.
- **행/열을 추가하지 않는다.** 값만 쓴다.

#### 폐기된 경로 (2026-09-16)

| 폐기된 것 | 이유 |
|---|---|
| `write_bb.py` · `fill_result.ps1` · `apply_*.ps1` · `_bb_mapping.json` | 전부 **"마스터에 직접 못 쓰니 작업본에 적고 손으로 옮긴다"는 우회 구조**였다. 정본에서 삭제됨 — 필요하면 **git 히스토리에서 복원**한다(`Checklist/` 8개 파일 모두 추적돼 있었다) |
| MCP 커넥터 직접 쓰기 | 부여 스코프가 **읽기 전용**(`Files.Read.All`·`Sites.Read.All`만) → 쓰기 도구가 전부 `This tool is not available` 로 잘린다. 문서 권한과 무관하다 |
| OneDrive 동기화 폴더 경유 | **UPLOAD FAILED**. 로컬만 바뀌고 OneDrive 가 타임스탬프를 서버값으로 되돌린다. ⚠️ **트레이 아이콘에는 오류가 안 뜬다** |

⛔ **openpyxl 금지**(스레드댓글·customXml·조건부서식 24파트 파괴 실측) /
⛔ **Excel COM 금지**(동기화 폴더 파일은 ReadOnly 로 열려 `Save()` 가 조용히 무시된다).