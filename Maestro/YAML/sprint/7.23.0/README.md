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
| `28_01_쿠폰딥링크_앱수신과쿠폰함_old.yaml` | TC-01 · 02 · 05 · 07 · 10 (앱 수신부) | 셀렉터 **APK 실측** |
| `28_02_쿠폰딥링크_웹랜딩_old.yaml` | TC-02 · 03 · 04 · 08 · 09 · 10 (웹 구간) | ⛔ **전제 미확정 — 돌리지 말 것** |

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

## 남은 일

1. **미로그인 상태 랜딩 실측** — `pm clear` → 링크 투입 → `uiautomator dump`.
   앱 화면이면 `28_02` 를 `28_01` 로 접고, 웹이면 `WEB_*` 셀렉터를 실측값으로 바꾼다.
2. `28_02` 의 **화살표 CTA 셀렉터** — 지금은 `pressKey: enter`(폼 기본 제출)로 **가정**해 뒀다.
3. 실기기 1회 완주 후 `run_suite.ps1` 등록 여부 판단(지금은 미등록 — 외부 데이터 의존 + 미검증).
