---
name: maestro-run
description: GME Remittance 앱의 Maestro 플로우/스위트를 실기기에서 실행할 때. run_test.ps1·run_suite.ps1 호출 규약, 실행 전 필수 점검(기기 연결·로그인 상태·수정 반영), 빌드 전환(stag/운영), 백그라운드 실행 판단. "테스트 돌려줘", "플로우 실행", "스위트 실행" 요청에 사용.
---

# Maestro 플로우 실행

"테스트를 돌린다" = **USB로 연결된 실기기에서 앱을 조작한다.** 에뮬레이터는 쓰지 않는다.
실행이 **실계좌·실계정에 닿는다** — 실제 결제·충전·송금이 발생할 수 있다.

## CWD와 셸 전제

CWD는 항상 `Maestro\` 루트다. 플로우 경로는 그 기준 상대경로.

```powershell
$PSNativeCommandArgumentPassing = 'Legacy'   # ★ 생략하면 env 값의 `|`가 cmd 파이프로 해석돼 즉사
```

작업 파일은 이 저장소가 아니라 다음 경로에 있다:
`C:\Users\GME\Global Money Express Co., Ltd\개인용 - Automation\Maestro\`
편집 대상은 **`Old\`**(구 UI). 루트의 동일 사본은 개편 UI용이라 건드리지 않는다.

## 실행 명령

```powershell
.\run_test.ps1 -lang ko -flow "Old\09_Home_old.yaml"              # 기본 = stag + LIVETEST
.\run_test.ps1 -lang ko -flow "Old\09_Home_old.yaml" -Build live  # 운영 요청이 있을 때만
.\run_suite.ps1 -Names 04_Menu_History
```

- `-device` 생략 시 자동 감지하고 **2대 이상이면 실행을 거부**한다. 시리얼을 하드코딩하지 말 것.
- `run_test.ps1`이 `env\<lang>.env`를 파싱해 `--env KEY="VALUE"`로 넘긴다. 값의 인용은 필수.
- 상위 폴더에도 `run_test.ps1`이 있다. 헷갈리면 `Maestro\` 쪽을 쓴다.
- 스위트 상세는 `maestro-suite` 스킬 참고.

### 빌드 2종 (2026-09-03 사용자 선언)

| 상황 | appId | 서버 | 러너 |
|---|---|---|---|
| **기본**(언급 없음) | `...gmeremittance_native.stag` | **LIVETEST로 지정** | `-Build stag` (기본값) |
| **운영/Live 요청 시** | `...gmeremittance_native` | 운영 | `-Build live` |

- ⛔ **`.livetest` 빌드는 더 이상 쓰지 않는다** — 기기에서 이미 삭제됐다(2026-09-03 adb 확인).
  `env\*.env`의 `APP_ID` 기본값도 `.stag`이고, 러너의 `-Build`가 그 값을 덮어쓴다.
  `-AppId <pkg>`는 임의 패키지용으로 남아 있고 `-Build`보다 우선한다.
- 운영 빌드도 **구 UI(`HomeActivityV2`)** 라 `Old\` 플로우가 그대로 통한다.
- 운영에는 **Server Override 스플래시가 없다**(헬퍼는 조건부라 자동 SKIP).
- ⚠️ stag는 Server Override 기본값이 **STAG**이고 `clearState`가 그 선택을 되돌린다 →
  강제를 빠뜨리면 **에러 없이 gmeuat로 돈다.** 검증은 코드가 아니라 **접속 호스트**로:
  `adb logcat -d | grep -oE '(livetest|gmeuat)\.gmeremit\.com'`
  강제 누락 자체는 린터 **`E08`**이 정적으로 잡는다.

## 실행 전 점검 — 매번 한다

이 셋을 건너뛰면 코드 결함으로 오진한다. 실제로 9회 실행 중 4회가 이 문제였다.

```bash
adb devices -l                                                    # ① 기기 연결
adb shell dumpsys activity activities | grep -i mResumedActivity   # ② 앱 상태
```

1. **기기 연결** — 목록이 비면 USB 문제다. `adb kill-server`로 복구되지 않으면 사용자에게 알린다.
2. **앱 상태** —
   - `HomeActivityV2` → 정상, 바로 실행
   - `ActivityLockScreen` → PIN 잠금(플로우가 처리)
   - `AutoLogoutActivity` / 런처 → **자동 로그아웃**. 유휴 ~10분이면 걸린다 → 재로그인 필요
   - `LoginV2Activity` → 로그아웃 상태 → `Old\01_01_Login_Success_old.yaml` 먼저
3. **수정 반영 확인** — 파일을 고치고 돌릴 때는 실행 명령 앞에 카운트를 찍는다.
   편집한 수정이 파일에서 되돌아간 사고가 실제로 있었다(같은 실패를 두 번 겪음).

```powershell
$c = (Select-String -Path "Old\04_Menu_History_old.yaml" -Pattern 'timeout: 120000' -SimpleMatch).Count
Write-Host "실행직전 확인: $c"
```

### 기기가 바뀌었을 때 — 1회만 추가로 본다

기기 교체는 곧 **해상도 변경**이고, 그러면 "요소가 화면 밖으로 밀리거나 키패드에 가려지는" 실패가
**한꺼번에** 나온다(2026-09-09 실측: 7개 파일). 셀렉터 버그로 오진하기 딱 좋은 모양이다.

```bash
adb shell wm size && adb shell wm density     # 해상도·DPI 를 기록해 둔다
```

1. **해상도를 기록한다.** 리포트에 남겨 두면 다음 교체 때 원인 판정이 1분이면 끝난다.
2. **첫 실패를 코드 결함으로 단정하지 말 것.** 아래 셋이면 거의 해상도다:
   - `Element not found` 인데 화면에는 **보인다** → 키패드가 덮었다
   - 목록에서 **다른 행**이 눌렸다 → `index:` 가 행이 아니라 화면 위치를 가리킨다
   - 좌표 탭이 **아무 일도 안 했는데 통과**했다 → 좌표가 빗나갔다
   → 고치는 법은 `maestro-yaml` 스킬의 **"기기·해상도가 바뀌어도 버티게 쓰기"**.
3. **환경도 함께 본다** — 생체인증 OFF(켜져 있으면 전 플로우가 진입에서 막힌다), 화면 잠금 해제,
   앱 언어, 갤러리 픽스처 재푸시(`push_test_images.ps1`), 기기 변경 팝업(어드민 승인이 필요할 수 있다).
4. **`.\lint_flows.ps1` 을 한 번 돌린다.** `W11`·`W12`·`W13` 이 해상도에 약한 자리를 정적으로 짚어 준다.

### 세션 만료

하루 지나면 세션이 만료된다. 진입부터 실패하면 이걸 먼저 의심하고
`Old\01_01_Login_Success_old.yaml`로 재로그인한다. **PIN만으로는 복구되지 않는다.**
재로그인과 본 실행 사이에 유휴를 두지 말 것(자동 로그아웃이 다시 걸린다).

## 백그라운드 실행

도구 타임아웃은 최대 10분인데 긴 플로우는 **17~18분**이 걸린다.
→ `run_in_background: true`로 돌리고 완료 알림을 기다린다. **폴링하지 않는다.**

## 금지 사항

- **동시에 두 개를 돌리지 말 것.** 기기가 하나라 Maestro 실행이 충돌한다.
- **실행 중 기기를 만지지 말 것.** 알림 패널만 내려도 `Element not found`로 실패해 셀렉터 버그로 오진한다.
- **비밀번호를 추측하지 말 것.** 로그인 실패 5회 제한, PIN 오입력은 계정 잠금이다.
- 자격정보는 저장소 문서에 적지 않는다. 실제 값은 메모리에만 둔다.

## 갤러리 의존 케이스

신분증/ARC/여권 업로드·QR 스캔은 **실행 직전 `.\push_test_images.ps1`** 를 돌린다.
`icon_thumbnail`의 index가 "테스트 이미지 4장이 갤러리 최신 4개"라는 전제에 기대므로,
다른 이미지가 쌓이면 앱이 "OCR이 유효하지 않습니다"로 거부한다 — **앱 버그가 아니다.**

## 실행 후

- 결과는 `suite_logs\<타임스탬프>\`에 항목별 `.log` + `SUMMARY.md`로 남는다.
- **스크린샷은 러너가 회수한다** — `takeScreenshot` 은 CWD 에 떨어뜨리지만(경로 옵션이 없다)
  실행 직후 `shots_runs\<yyyyMMdd_HHmmss>_<플로우>\` 로 옮겨진다. 루트에 png 가 쌓이면 회수가 안 된 것이다.
  ⚠️ 폴더명이 `shots_` 로 시작해야 `.gitignore` 와 `sync_from_source.ps1` 이 함께 걸러낸다.
- 실패했으면 `maestro-debug` 스킬로 진단한다. **환경 문제와 코드 결함을 먼저 구분할 것.**
