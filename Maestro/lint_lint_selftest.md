# lint_flows 결과 — 2026-09-14 17:49

- 대상: `lint_selftest` / 22개 파일
- **ERROR 9** / **WARN 13**

> 실행으로는 원리적으로 안 잡히는 부류만 검사한다. 좌표·타이밍·앱 결함은 실행만이 잡는다.

## [ERROR] E01_PKG_ID — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E01_pkgid.yaml | 5 | id에 패키지명이 박혀 있다 → stag 빌드에서 절대 매칭되지 않고, 조건부 블록이면 에러 없이 SKIP된다. 짧은 id만 쓸 것 |

## [ERROR] E02_YAML_ESCAPE — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E02_escape.yaml | 5 | 이중인용 안의 \s 는 유효한 YAML 이스케이프가 아니다 → Parsing Failed로 파일이 통째로 죽는다. 백슬래시를 2겹으로 쓰거나 단일인용을 쓸 것 |

## [ERROR] E04_ENV_UNDEFINED — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E04_env.yaml | 4 | ${NOT_A_REAL_VAR_XYZ} 가 env\*.env 에도, 어떤 flow의 env: 블록에도 없다 → 치환되지 않은 리터럴로 남아 조용히 SKIP된다 |

## [ERROR] E05_WRONG_LABEL — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E05_label.yaml | 4 | 실측 문구와 다르다: "국내송금" → "국내 송금"  (구 UI 홈 그리드 실측 라벨(공백). 텍스트 전체매칭이라 조용히 SKIP된다) |

## [ERROR] E06_V3_SELECTOR — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E06_v3.yaml | 10 | 개편 UI 전용 셀렉터다. 구 UI 홈에는 Home 텍스트가 없다 → 도달 대기가 타임아웃하고, notVisible 가드는 항상 참이 된다. id: bottom_item_home 을 쓸 것 |

## [ERROR] E07_LAUNCH_APPID — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E07_launch.yaml | 4 | 플로우 도중 launchApp이 특정 빌드를 하드코딩한다 → -AppId로 stag를 지정해도 이 줄에서 다른 빌드가 실행된다. ${APP_ID} 를 쓸 것 |

## [ERROR] E08_NO_SERVER_OVERRIDE — 2건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E07_launch.yaml | 1 | launchApp을 하는데 Server Override(LIVETEST 강제) 처리가 없다 → stag 빌드에서 **조용히 gmeuat(STAG) 서버로 돈다**. - runFlow: "_server_override_old.yaml" 를 launchApp 뒤에 둘 것 |
| bad_E08_override.yaml | 1 | launchApp을 하는데 Server Override(LIVETEST 강제) 처리가 없다 → stag 빌드에서 **조용히 gmeuat(STAG) 서버로 돈다**. - runFlow: "_server_override_old.yaml" 를 launchApp 뒤에 둘 것 |

## [ERROR] E09_BAD_PRESSKEY — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_E09_presskey.yaml | 10 | pressKey 값 'backdhwjs' 은 Maestro가 아는 키가 아니다 → **파일 전체가 Parsing Failed로 거부되고 한 케이스도 실행되지 않는다.** back/enter/home/lock/backspace/tab/volume up\|down 등만 쓸 것 |

## [WARN] W01_GENERIC_LABEL — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W01_generic.yaml | 9 | `visible: "닫기" → tapOn: "닫기"` 맹목적 팝업 닫기다. 무엇이 떠 있는지 모른 채 아무 X나 누르므로 엉뚱한 X를 눌러 앱이 런처로 빠져나간 사고 이력이 있다 → id로 특정하거나(인앱 배너는 btnTwo\|btnClose), 최소한 `notVisible: <목적 화면 id>`로 가드를 좁힐 것 |

## [WARN] W02_NOTVISIBLE_UNPAIRED — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W02_notvisible.yaml | 4 | "존재하지않는문구ZZZ" 가 어떤 파일에서도 긍정 검증(assertVisible 등)된 적이 없다 → 오타여도 통과한다. 같은 화면에서 실제 라벨을 한 번은 assertVisible로 확인할 것 |

## [WARN] W03_SHOT_IN_SECURE — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W03_shot.yaml | 6 | 캡처 차단 화면 마커(5행) 근처의 takeScreenshot이다. FLAG_SECURE 화면에서 이 패턴이 플로우를 4회 죽였다 → assert로 대체 |

## [WARN] W04_CREDENTIAL — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W04_cred.yaml | 4 | 비밀번호로 보이는 리터럴이 플로우에 박혀 있다. 값이 바뀌면 전 파일을 손으로 훑어야 한다 → flow 레벨 env: 로 뺄 것 (값은 리포트에 출력하지 않는다) |

## [WARN] W05_HARDCODED_SERIAL — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W05_serial.yaml | 4 | 기기 시리얼로 보이는 값이 있다(주석 포함). 기기는 교체된다 → adb devices 자동 감지에 맡길 것 |

## [WARN] W06_DUP_FIXTURE — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W06_dupfixture.yaml | 6 | 신원 픽스처가 4행과 중복된다. 서버가 소모하는 값이면 두 번째가 반드시 실패한다(여권/ARC 동일번호·S1/S2 동일 이메일이 실제 사고였다) |

## [WARN] W07_RESULT_NO_WAIT — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W07_result.yaml | 6 | 결과 문구("송금이 완료") 갈래인데 앞 20줄에 extendedWaitUntil이 없다 → 아무것도 안 떠도 EXIT=0이 된다. 결과 도달을 먼저 강제할 것 |

## [WARN] W08_PIN_NO_SCREEN_WAIT — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W08_pin.yaml | 7 | PIN 숫자 4연타(7행~파일 끝) 앞에 **PIN 화면 도달 판정이 없다**. 화면이 아직 안 떴는데 누르면 같은 글자를 가진 다른 요소를 집는다 → 런 앞에 input_dot_1(또는 keypadContainer) 대기를 둘 것 |

## [WARN] W09_HEADER_APPID — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W09_appid.yaml | 1 | 헤더 appId가 하드코딩돼 있어 -AppId 로 빌드를 바꿀 수 없다. 전용 빌드 파일이면 의도된 것일 수 있다 → 그렇다면 화이트리스트에 넣을 것 |

## [WARN] W10_ACCT_HARDCODED — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W10_acct.yaml | 6 | 연동 계좌 목록(5행)에서 "신한은행"을 전제 단언 없이 탭한다. 목록은 계정 상태에 따라 바뀐다 → 앞에 assertVisible을 두거나(특정 계좌가 케이스의 일부일 때), 목록에서 골라 쓸 것(어느 계좌든 무관할 때) |

## [WARN] W11_COORD_NO_ASSERT — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W11_coord.yaml | 6 | 좌표 탭인데 같은 케이스 안에 결과 단언이 없다. 해상도가 바뀌면 조용히 빗나가고 그대로 통과한다 → id로 바꾸거나(가능하면), 최소한 탭의 결과를 assert할 것 |

## [WARN] W12_HIDEKEYBOARD_AS_BACK — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W12_hidekb.yaml | 7 | 앞 8스텝에 입력이 없는 hideKeyboard다. 키보드가 없으면 **뒤로가기로 동작해** 화면을 벗어난다 → 입력 직후에만 두거나 when: visible: <입력 필드> 로 가드할 것 |

## [WARN] W13_INDEX_AFTER_SCROLL — 1건

| 파일 | 줄 | 내용 |
|---|---|---|
| bad_W13_index.yaml | 10 | 스크롤/스와이프 직후의 index 셀렉터다. index는 행이 아니라 **그 순간 화면 맨 위**를 가리키므로 스크롤 위치가 조금만 달라져도 다른 행을 집는다 → 이름으로 앵커하거나(childOf: containsDescendants) centerElement: true로 위치를 고정할 것 |
