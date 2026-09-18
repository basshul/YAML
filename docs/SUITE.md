# SUITE.md

구 UI(V2) 회귀 스위트 문서. 실행기는 `Maestro\run_suite.ps1`이다.

> **⚠️ 상세 내용은 skill로 옮겼다 — [`.claude/skills/maestro-suite/SKILL.md`](.claude/skills/maestro-suite/SKILL.md)**
>
> 그룹 체계(축은 **계정/로그인 상태**) / 실행 옵션 / 순서 제약 / 제외 파일 / 갤러리 픽스처 /
> 실행 전 게이트 / 서버 LIVETEST 3중 검증 / 잔액 취급이
> 전부 그쪽에 있다. Claude Code는 스위트를 건드릴 때 그 skill을 자동으로 불러 쓰고,
> 사람은 위 경로의 파일을 그냥 읽으면 된다.
>
> **이 문서에 내용을 다시 늘리지 말 것** — 두 곳에 같은 규칙이 있으면 반드시 한쪽이 낡는다.

## 왜 스위트가 따로 있는가

`maestro test Old\` 로 폴더를 통째 돌리면 안 되는 이유 셋. 이것만 여기 남긴다.

1. **순서가 보장되지 않는다.** 이 스위트는 로그인 상태가 앞뒤로 이어진다 —
   `clearState` 플로우가 로그아웃시키면 그 뒤에 재로그인을 끼워야 한다.
2. **딸려 들어간다.** `_*.yaml` 헬퍼와 appId가 다른 `stag`/`sgt` 파일까지 실행 대상이 된다.
3. **계정을 소모하거나 실결제가 나가는 플로우**를 기본에서 빼야 한다.

## 빠른 참조

```powershell
$PSNativeCommandArgumentPassing = 'Legacy'   # 생략 시 env 값의 `|`가 cmd 파이프로 해석돼 즉사
.\run_suite.ps1 -List                        # 실행 계획만 출력
.\run_suite.ps1                              # 기본 = G1,G2,G3,G4 (G9 파괴적 제외)
.\run_suite.ps1 -Names 08_MyQR,03_Domestic   # 적은 순서 그대로
```

- **동시에 두 개를 돌리지 말 것.** 기기가 하나라 Maestro 실행이 충돌한다.
- ⚠️ **옵션을 확인할 때는 반드시 `-List`를 붙인다.** 빼면 실기기에서 진짜로 돈다.
- ⚠️ **기본 세트에 들어 있다고 "부작용 없음"이 아니다.** `11_IntlTopup`·`12_BillPayment`는
  **실제 결제가 나가고 취소가 안 된다**(계획 출력에 `🔴비가역`으로 표시된다).
  각 항목의 `note`를 반드시 확인할 것.

## 관련 문서

- 지침 일반 — [CLAUDE.md](CLAUDE.md)
- 파일별 진행 현황 — [PROGRESS.md](PROGRESS.md)
- 실행/진단/작성 skill — `.claude/skills/maestro-{run,debug,yaml,suite}/SKILL.md`
