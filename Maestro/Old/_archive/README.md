# Old\_archive\ — 보관용 조각 yaml

여기 있는 파일은 **실행 대상이 아니다.** 회귀 스위트에도, 다른 flow의 `runFlow:`에도 없다.
지우지 않고 남긴 이유와 되살릴 조건만 적어둔다.

## `k_reg_setup_old.yaml` / `k_step_*_old.yaml` (5개) — 2026-09-01 이관

`06_Registration`의 **카메라·OCR 구간을 손으로 디버깅**하려고 본 파일에서 잘라둔 조각이다.
`launchApp`이 없고 "직전 화면 상태를 이어받아" 동작하도록 만들어져,
검증 스텝 사이에 끼워 실행하는 용도였다(CLAUDE.md의 "구간을 잘라 임시 yaml로 추출" 방식).

| 파일 | 담당 구간 |
|---|---|
| `k_reg_setup_old.yaml` | 가입 폼 입력(ID·비밀번호·휴대폰·국적) → 신분증 타입 선택 화면까지 |
| `k_step_pick_old.yaml` | 신분증 타입 선택 → [다음] → 카메라 진입 (+ 권한 팝업) |
| `k_step_shoot_old.yaml` | 셔터(`captureBtnImageView`) 탭 → 크롭 화면 |
| `k_step_done_old.yaml` | 크롭 [완료] → OCR 정보 입력 화면 |
| `k_step_passportno_old.yaml` | 여권번호 보안 키패드 입력 → 입력완료 |

### ⚠️ 되살리기 전에 알아야 할 것

- **낡았다.** 2026-08-04 판이라 그 뒤 `06_Registration`에서 잡힌 **결함 11건이 반영돼 있지 않다**
  (셔터 좌표 → `captureBtnImageView`, 캡처 불가 화면의 `takeScreenshot` 44곳, 중복 픽스처 등).
- 원칙은 **본 파일에서 다시 잘라내는 것**이다. 임시본을 고치면 본 파일에 반영이 유실된다.
  → 이 조각들은 "그때 어떻게 쪼갰는지"의 참고 자료로만 볼 것.
- `KB_ID` / `KB_PHONE` / `KB_NAT` / `KB_IDTYPE` 는 **CLI `--env`로 주입**하던 변수다.
  어떤 `.env`에도 없다(그래서 정적 검사 `E04`가 잡았고, 이관으로 해소됐다).
- `appId`가 `.stag`로 하드코딩돼 있다.

**관련:** `06_Registration_All_old.yaml`, PROGRESS.md의 `06_Registration` 절
