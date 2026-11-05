# 스프린트 7.23.0 — 자동화 산출물

이 폴더는 **7.23.0 스프린트에서 자동화한 것**만 모은다. 체크리스트 기반 회귀 자산은
`YAML\Old\`(구 UI) · `YAML\New\`(개편 UI) 쪽이고, 여기 있는 건 그 스프린트의 신규 기능 검증이다.

| | |
|---|---|
| 티켓 | [S2-59](https://gmeremit-team.atlassian.net/browse/S2-59) *[QA] Coupon link generator: switch from Firebase to Airbridge* (에픽 S2-36) |
| 대상 | 쿠폰 링크 생성기의 Firebase → **Airbridge** 전환 |
| 작성 | 2026-11-04 |
| 상태 | **실기기 검증 0회** — 아래 "남은 일" 참고 |

## 산출물

| 파일 | 커버 | 상태 |
|---|---|---|
| `28_01_쿠폰딥링크_앱수신과쿠폰함_old.yaml` | TC-01 · 02 · 05 · 07 · 10 (앱 수신부) | 셀렉터 **실기기 실측**(2026-11-04) |
| `28_02_쿠폰딥링크_웹랜딩_old.yaml` | TC-02 · 03 · 04 · 08 · 09 · 10 (웹 구간) | ⛔ **보류 — 기능이 빌드에 없다**(머리말 참고) |

### ⛔ 2026-11-04 실기기 실측으로 뒤집힌 것

1. **미로그인 경로가 빌드에 없다.** 쿠폰 딥링크가 로그인 전에 들어오면 앱이 버린다
   (`SplashScreen: checkSessionAndHandle - deepLink: null`) — 랜딩도 Welcome Back 팝업도 뜨지
   않고 로그인 뒤로 이어지지도 않는다. **티켓 Step 1~4 는 현재 빌드에서 재현 불가**다.
   에픽 S2-36 이 "해야 할 일" 인 것과 맞는다 → **티켓에 확인 요청 필요.**
2. **딥링크에 `airbridge_referrer` 가 없으면 Airbridge SDK 가 버린다.** 화면상 아무 일도
   일어나지 않아 오진하기 쉽다. `airbridge_referrer=airbridge%3Dtrue` 하나면 통과한다.
3. **https 링크는 운영 앱으로 직행**한다(운영만 도메인 verified). 자동화는 커스텀 스킴만 쓴다.
4. ✅ **로그인 상태에서는 동작한다** — TC-10(잘못된 코드 → 오류 안내 → 쿠폰함) 전 구간 통과.

둘로 나눈 이유는 앱 쪽은 근거가 확실하고 웹 쪽은 아직 추정이라서다. 한 파일이면 웹에서 죽을 때
앱 검증까지 통째로 못 돌린다. 자세한 근거·함정은 **각 파일 머리말**에 있다.

🚫 **TC-06(앱 미설치 → 스토어 → 지연 딥링크)은 자동화 대상이 아니다** — 스토어 설치 단계를
`adb install` 로 바꾸면 설치 referrer 가 없어 deferred deeplink 가 애초에 성립하지 않는다. 수동 케이스.

## 헬퍼는 복제하지 않는다

공용 헬퍼 6개를 `..\..\Old\` 에서 **빌려 쓴다**(`runFlow: "../../Old/_xxx_old.yaml"`).
`runFlow` 상대경로가 **그 yaml 이 있는 폴더** 기준이라 이렇게 쓸 수 있다(2026-11-04 실측).

```
_server_override_old   _onboarding_gate_old   _enter_login_pw_old
_enter_pin_old         _dismiss_popups_stag_old   _pick_app_from_chooser_old
```

⚠️ `Old\` 의 헬퍼가 바뀌면 여기도 같이 영향을 받는다 — 그게 의도다(사본을 두면 반드시 어긋난다).

## 실행

⛔ CWD 는 **`C:\GME\qa-automation\Maestro\YAML`** 다(러너가 `env\` 를 CWD 기준으로 읽는다).

```powershell
cd C:\GME\qa-automation\Maestro\YAML
.\run_test.ps1 -lang ko -User Basshu `
  -flow "sprint\7.23.0\28_01_쿠폰딥링크_앱수신과쿠폰함_old.yaml" `
  -ExtraEnv COUPON_CODE_EXPIRED=<만료·소진된 쿠폰 코드>
```

정적 검사(구 UI 트랙이므로 `-Track v2` 를 명시한다 — 경로에 `Old` 가 없어 자동 판별이 안 된다):

```powershell
.\lint_flows.ps1 -Path "sprint\7.23.0" -Track v2
```

### 필요한 데이터

전부 `-ExtraEnv` 로 넘긴다(env 파일에 적으면 러너가 "한쪽만 두세요" 로 거부한다).
출처는 Core 어드민 `OTHER SERVICE > Coupon > Coupon Link Generator > Download Excel`.

| 키 | 용도 | 필수 |
|---|---|---|
| `COUPON_CODE_EXPIRED` | 28_01 전체 전제 | ✅ |
| `COUPON_CODE_CLAIMED` | TC-05 중복 수령 | 선택 |
| `COUPON_CODE_VALID` | TC-01 ⚠️ **1회용**(돌리면 소모된다) | 선택 |
| `COUPON_URL_EXPIRED` · `PHONE_REGISTERED` | 28_02 전제 | 28_02 필수 |
| `PHONE_UNREGISTERED` · `COUPON_URL_VALID` · `PHONE_OTHER_ACCOUNT` | TC-03/04/07-M | 선택 |

## 실측으로 확정한 것 (2026-11-04)

실제 링크 `https://abr.ge/h3ssc1s` 를 풀어 확인했다:

```
https://gmeremit.airbridge.io/gmeremit.coupon.redeem/?couponCode=<코드>&discountValue=10&...
→ gmeremit://gmeremit.coupon.redeem/?couponCode=<코드>&discountValue=10
```

- `.redeem` 뒤에 **슬래시가 있다**. 앱이 읽는 쿼리 키는 `couponCode`.
- ⚠️ 이 Airbridge 페이지에는 **전화번호 입력칸이 없다** — `redirect()` 만 있는 바운스 페이지다.
  티켓이 말하는 "웹 쿠폰 랜딩 페이지" 는 **앱 화면일 가능성이 크다**(APK 에 `FREE SERVICE FEE COUPON`
  과 `dialog_cupon_message.xml` 이 다 있다). 확정 전까지 `28_02` 는 돌리지 않는다.
- ⛔ 기기에 GME 빌드가 3개(운영/livetest/stag) 깔려 있어 **`openLink` 마다 "연결 앱" 다이얼로그**가
  뜬다 → 모든 `openLink` 뒤에 `_pick_app_from_chooser_old.yaml` 을 붙였다.

## 케이스별 현황 (2026-11-05 감사)

| TC | 위치 | 상태 |
|---|---|---|
| TC-10 변조 파라미터 | `28_01 [10-1][10-2]` | ✅ **실기기 완주(EXIT=0)** · 외부 데이터 불필요 |
| TC-01 유효 쿠폰 | `28_01 [01]` | ⚠️ 코드 필요 · 미검증 · **비멱등** |
| TC-05 중복 수령 | `28_01 [05]` | ⚠️ 코드 필요 · 미검증 |
| TC-07 기로그인 유입 | `28_01 [07]` | ⚠️ 미검증 (불일치 절반은 `28_02 [07-M]` 보류) |
| TC-02 만료 링크 | `28_01 [02]` + `28_02 [02]` | ⛔ **미로그인 경로가 빌드에 없어 실행 불가** |
| TC-03 · 04 · 08 · 09 | `28_02` | ⛔ 보류 (같은 원인) |
| TC-06 앱 미설치 | `28_01` 머리말 | 🚫 자동화 불가(스토어 설치 referrer) |

의도적으로 범위를 자른 것: TC-03/04 는 **가입을 진행하지 않고** 유도 팝업까지만 · TC-05 는 쿠폰
**건수를 세지 않고** 팝업으로 판정 · TC-07 의 번호 불일치는 **티켓에도 기대값이 미정**이라 증적만 ·
TC-09 는 CTA 색을 읽을 수 없어 동작(진행 불가)으로 대신한다.

### ⛔ 딥링크 뒤에는 PIN 을 먼저 푼다

딥링크는 앱이 포그라운드에 떠 있어도 `SplashScreen` 을 거쳐 **잠금화면으로 떨어진다**.
그래서 `openLink` 8곳 뒤에 전부 `../../Old/_unlock_if_locked_old.yaml` 이 붙어 있다.
빼면 `extendedWaitUntil` 이 잠금화면 앞에서 타임아웃하고 **"쿠폰 팝업이 안 보인다"** 로 죽는다.

### ⚠️ 바텀시트 id 는 공용이다 — 반드시 문구를 같이 건다

쿠폰 결과 팝업과 홈의 "Easy Wallet 갱신" 안내가 **똑같이** `design_bottom_sheet` /
`txvCaption` / `btnOne` / `btnTwo` 다. 버튼 성격은 반대다(Easy Wallet 은 `btnOne` 이 **지금 갱신하기**).
→ id 만으로 집지 말고 `text:` 를 함께 걸 것. 홈 복귀 단언 앞에는 팝업 큐 정리를 둔다.

## 남은 일

1. **티켓 확인 요청** — 미로그인 랜딩(Step 1~4)이 7.22.0-stag 에 없다. 아직 배포 전인지,
   서버 플래그가 필요한지, 랜딩이 웹인지 앱 화면인지 확인해야 `28_02` 의 방향이 정해진다.
2. **쿠폰 코드 확보** → `28_01` 완주. 지금 돌릴 수 있는 건 `[10]`(코드 불필요)뿐이고,
   `[02]`·`[05]`·`[01]` 은 어드민에서 만료/수령/유효 코드를 받아야 한다.
   ⚠️ `[02]` 는 "미로그인 → 로그인 후 팝업" 전제라 위 1번이 풀려야 성립한다.
3. 실기기 1회 완주 후 `run_suite.ps1` 등록 여부 판단(지금은 미등록 — 외부 데이터 의존).
