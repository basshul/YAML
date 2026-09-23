# web-runner — 브라우저에서 Maestro 테스트 실행 (데모)

브라우저에서 테스트를 골라 실행하고, 로그와 pass/fail 결과를 보는 로컬 데모입니다.
실행은 기존 `Maestro\run_test.ps1` / `run_suite.ps1` 이 그대로 합니다 — 이 폴더는 그걸 부르는 껍데기입니다.

## 처음 한 번만

```powershell
cd C:\GME\qa-automation\web-runner
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.local.json
```

## 실행

```powershell
.\start.ps1
```

그다음 브라우저에서 <http://localhost:8765> 를 엽니다. 끄려면 터미널에서 `Ctrl+C`.

## 파일 구성

| 파일 | 하는 일 |
|---|---|
| `runner.py` | **PowerShell 스크립트를 부르는 유일한 창구.** 다른 파일에서 직접 부르지 않는다 |
| `server.py` | 웹서버 + API. 화면이 쓰는 데이터만 내보낸다 |
| `static/` | 브라우저 화면(HTML/JS) |
| `config.local.json` | 이 PC 전용 설정 + 비밀정보. **git 에 올라가지 않는다** |
| `config.example.json` | 위 파일의 템플릿(공유용) |
| `run_logs/` | 실행 로그 보관. git 에 올라가지 않는다 |

## 알아둘 것

- **서버 선택**은 빌드 이름이 아니라 **어느 서버에 붙는가**로 고릅니다.
  `LiveTest` → stag 빌드(플로우가 서버를 LIVETEST 로 강제) / `운영(Live)` → 실서비스.
- **테스트 목록의 정본은 `Maestro\run_suite.ps1` 의 `$Suite` 표**입니다.
  여기에 목록을 따로 적지 않습니다 — 표가 바뀌면 화면도 자동으로 바뀝니다.
- **G9(파괴적) 항목은 목록에 뜨지 않습니다.** 계정 잠금·비밀번호 초기화처럼 admin 개입이
  있어야 복구되는 것들이라 데모 범위에서 뺐습니다.
- 이번 데모에 **없는 것**: 대기열, iOS 실행, 로그인 기능, 외부 연동.
