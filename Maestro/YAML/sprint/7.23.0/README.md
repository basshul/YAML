# 스프린트 7.23.0 — 자동화 산출물

이 폴더는 **7.23.0 스프린트에서 자동화한 것**만 모은다. 체크리스트 기반 회귀 자산은
`YAML\Old\`(구 UI) · `YAML\New\`(개편 UI) 쪽이고, 여기 있는 건 그 스프린트의 신규 기능 검증이다.

이 스프린트에는 **티켓이 둘**이다. 아래 1번(쿠폰)과 2번(네팔 QR Pay)은 서로 독립이다.

---

# 1. S2-59 — 쿠폰 딥링크 Airbridge 전환

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
   에픽 S2-36 이 "해야 할 일" 인 것과 맞는다.
   ★ **2026-11-05 사용자 확인: 7.22.0-stag 가 이 건이 해결된 빌드가 아니다.** 즉 제품 결함이 아니라
     **빌드가 낡은 것**이다 → 티켓에 결함으로 올리지 말 것. 해결된 빌드로 교체한 뒤 재확인한다.
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

## 케이스별 현황 (2026-11-06 / 7.23.0-stag 72300077 실기기)

**EXIT=0 완주** — `[02-1] [09] [08] [02-2] [02-3] [02-4] [07] [10-1] [10-2]`, 스크린샷 13장.

| TC | 위치 | 상태 |
|---|---|---|
| TC-02 만료 링크 (티켓 영상 케이스) | `[02-1]`~`[02-4]` | ✅ **Step 1~6 전 구간 완주** |
| TC-08 Sign in 직링크 | `[08]` | ✅ 완주 |
| TC-09 번호 밸리데이션 | `[09]` | ✅ 완주 (⚠️ 기대값 미정 — 아래 참고) |
| TC-07 기로그인 유입 | `[07]` | ✅ 완주 |
| TC-10 파라미터 변조 | `[10-1]` `[10-2]` | ✅ 완주 |
| TC-02 Contact Support | `[02-C]` | ⏸ 이번 실행은 `SKIP_OPTIONAL=true` 로 껐다(고객센터 채널을 연다) |
| TC-03 미가입 + 유효 링크 | `[03]` | ⏸ `PHONE_UNREGISTERED` + `COUPON_CODE_VALID` 필요 |
| TC-04 미가입 + 만료 링크 | `[04]` | ⏸ `PHONE_UNREGISTERED` 필요 |
| TC-05 중복 수령 | `[05]` | ⏸ `COUPON_CODE_CLAIMED` 필요 |
| TC-01 유효 쿠폰 (Happy Path) | `[01]` | ⏸ `COUPON_CODE_VALID` 필요 · **비멱등** |
| TC-06 앱 미설치 | 머리말 | 🚫 자동화 불가(스토어 설치 referrer) |

의도적으로 범위를 자른 것: TC-03/04 는 **가입을 진행하지 않고** 유도 팝업까지만 · TC-05 는 쿠폰
**건수를 세지 않고** 팝업으로 판정 · TC-07 의 번호 불일치는 **티켓에도 기대값이 미정**이라 미구현.

### ⚠️ TC-09 — 전화번호 밸리데이션이 없다 (확인 필요)

`iv_next`(화살표 CTA)는 **입력이 비어 있지 않기만 하면 활성화**된다. 자릿수·형식을 보지 않는다.
`0101230`(7자리)을 제출하니 에러 없이 **미가입 번호로 취급**되어 가입 유도 팝업이 떴다.
티켓 기대("CTA 비활성 유지 또는 에러 메시지")와 다르다.
→ 플로우는 **빈 입력일 때 CTA 가 비활성인 것만 단언**하고(확실한 사실), 자릿수 부족 쪽은
  **증적만 남긴다.** ⛔ 사양이 정해지기 전에 단언을 넣지 말 것 — 어느 쪽으로 정해지든 거짓이 된다.

### 실행에 필요한 데이터

| 키 | 값 / 출처 | 비고 |
|---|---|---|
| `COUPON_CODE_EXPIRED` | **`GME-FTEA5M`** (실측 확정: 만료/소진) | 필수. 소모되지 않는다 |
| `ACCT_MAIN_PHONE` | `01090381905` — **사용자 프로파일에 고정** | 넘기지 않아도 된다 |
| `COUPON_CODE_CLAIMED` · `COUPON_CODE_VALID` · `PHONE_UNREGISTERED` | 어드민에서 발급 | 없으면 그 케이스만 SKIP |

```powershell
cd C:\GME\qa-automation\Maestro\YAML
.\run_test.ps1 -lang ko -User Basshu `
  -flow "sprint\7.23.0\28_01_쿠폰딥링크_앱수신과쿠폰함_old.yaml" `
  -ExtraEnv COUPON_CODE_EXPIRED=GME-FTEA5M,SKIP_OPTIONAL=true
```


## 남은 일

1. **데이터 확보** — 어드민에서 `COUPON_CODE_VALID`(유효·미수령) · `COUPON_CODE_CLAIMED`(이미 받은)
   · `PHONE_UNREGISTERED`(미가입 번호) 를 받으면 TC-01·03·04·05 까지 완주한다.
   ⚠️ TC-01 은 **비멱등** — 한 번 돌면 그 코드가 소모되고, 그 뒤엔 TC-05 픽스처가 된다.
2. **TC-09 사양 확인** — 위 "전화번호 밸리데이션이 없다" 건. 정해지면 단언을 추가한다.
3. **TC-02 `[02-C]`** — 고객센터 연결은 실제 CS 채널을 열 수 있어 기본 실행에서 뺐다(`SKIP_OPTIONAL`).
   한 번은 사람이 지켜보며 확인할 것.
4. `run_suite.ps1` 등록 여부 판단 — 지금은 미등록(외부 데이터 의존 + `clearState` 로 로그아웃한다).
   넣는다면 `01_01_로그인_정상` 과 같은 G1 자리여야 한다.
