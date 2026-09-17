# SharePoint 엑셀 편집 도구 설치 안내 — **Windows 판**

QA 체크리스트 같은 SharePoint 엑셀 파일을 명령줄에서, 또는 Claude에게 시켜서
수정하기 위한 도구입니다.

**여러 명이 동시에 편집 중이어도 안전합니다.** 파일을 통째로 덮어쓰지 않고
지정한 셀만 바꾸기 때문에, 다른 사람이 같은 시간에 입력한 내용이 사라지지
않습니다. 차트·서식·수식도 그대로 보존됩니다.

> 원본 [README_mac.md](README_mac.md) 는 macOS/zsh 기준입니다. 이 문서는 Windows(PowerShell)용으로
> 바꾸고, **Windows에서만 나타나는 함정 2가지**(§6)를 추가한 것입니다.
> 2026-09-16 실제로 이 순서대로 마스터 파일에 기입까지 확인했습니다.

---

## 1. 준비물

| 항목 | 확인 방법 |
|---|---|
| Python 3 | `python --version` — **`python3` 가 아닙니다**(아래 주의) |
| `gme_excel.py` | 이 저장소 루트 (`C:\GME\qa-automation\gme_excel.py`) |
| 회사 계정 | 본인의 `@gmeremit.com` 계정 |
| 파일 접근 권한 | SharePoint에서 그 파일을 **편집**할 수 있으면 됨 |

별도로 설치할 라이브러리는 없습니다(표준 라이브러리만 씁니다).

⚠️ **`python3` 를 쓰지 마세요.** Windows에는 `python3.exe` 라는 Microsoft Store 스텁이
`WindowsApps\` 에 있어서, 실제 파이썬 대신 스토어 설치 안내가 열릴 수 있습니다.
확인은 이렇게 합니다:

```powershell
(Get-Command python).Source     # 예: C:\Python314\python.exe
python --version                # 예: Python 3.14.2
```

⚠️ **읽기 권한만으로는 쓰지 못합니다.** 열리기는 해도 `set` 에서 `HTTP 403` 이 납니다.
그 파일의 편집 권한을 먼저 받아 두세요.

---

## 2. 환경변수 설정

PowerShell에서 아래를 **한 번만** 실행하면 이후 새로 여는 터미널에 계속 적용됩니다.

```powershell
setx GME_CLIENT_ID "0ba0c638-c539-4584-b803-8af3ae62ddd1"
setx GME_TENANT_ID "b19514d1-d63d-4dda-b580-d80917436738"
```

⚠️ `setx` 는 **새 프로세스부터** 적용됩니다. 지금 쓰던 창에서 바로 이어서 하려면
그 창에도 한 번 넣어 주세요:

```powershell
$env:GME_CLIENT_ID = "0ba0c638-c539-4584-b803-8af3ae62ddd1"
$env:GME_TENANT_ID = "b19514d1-d63d-4dda-b580-d80917436738"
```

> 이 두 값은 비밀번호가 아닙니다. 앱을 식별하는 공개 값이며, 이것만으로는
> 아무 파일에도 접근할 수 없습니다. 실제 권한은 아래 3단계의 본인 로그인에서
> 생깁니다.

---

## 3. 로그인 (최초 1회)

```powershell
$env:PYTHONIOENCODING = "utf-8"
python gme_excel.py login
```

브라우저가 열리면 **본인 회사 계정**으로 로그인합니다.

이후에는 다시 로그인할 필요가 없습니다. 토큰이 `C:\Users\<사용자>\.gme_excel_token.json` 에
저장되고 자동으로 갱신됩니다(refresh token).

확인:

```powershell
python gme_excel.py whoami
```

---

## 4. 사용법

대상 파일은 SharePoint에서 **공유 링크를 복사**해서 지정합니다.

```powershell
$LINK = 'https://gmeremittance.sharepoint.com/:x:/s/GME-IT-Korea/IQC...'

# 시트 목록
python gme_excel.py -f $LINK sheets

# 범위 읽기
python gme_excel.py -f $LINK get 'Checklist(Live)' B9:I20

# 셀 쓰기
python gme_excel.py -f $LINK set 'Checklist(Live)' I11 'Pass'
```

공유 링크 끝의 `?e=...` 는 그대로 두면 되고, **`&nav=...` 는 빼도 동작합니다**(실측 확인).

자주 쓰는 파일이 정해져 있으면 환경변수로 등록해두고 `-f` 를 생략합니다.

```powershell
setx GME_FILE_URL "https://gmeremittance.sharepoint.com/:x:/s/..."
python gme_excel.py sheets
```

### 여러 칸을 한 번에

```powershell
$cells = @('H39','H40','H41','H42','H43','H44','H45')
foreach ($c in $cells) {
  python gme_excel.py -f $LINK set 'Checklist(Livetest) (Basshu)' $c 'Pass'
}
```

### 시트 이름에 공백이나 괄호가 있는 경우

작은따옴표로 감싸면 됩니다.

```powershell
python gme_excel.py -f $LINK get 'Checklist(Livetest) (Basshu)' B9:I20
```

### Claude로 쓰는 경우

이 저장소에서 Claude를 열고 평소 말하듯 지시하면 됩니다.

> "Checklist(Live) 시트 11행 Comment에 'Pass' 넣어줘"

⚠️ **`login` 만은 Claude가 대신 못 합니다.** 브라우저 인증이라 자동모드가 차단합니다.
프롬프트에 **`!` 를 붙여 직접** 실행해 주세요. 로그인만 끝나면 나머지는 Claude가 처리합니다.

---

## 5. 기입 전에 — 행을 반드시 대조한다

체크리스트는 **F열(Checklist) 문구가 같은 행이 여럿**입니다. 예를 들어
"이용약관 동의 화면 노출 확인" 은 Initial Screen 과 로그인화면 `Register Here` 양쪽에 있습니다.

→ **`get` 으로 D열(2Depth)까지 같이 읽어** 귀속을 확인한 뒤 씁니다.

```powershell
python gme_excel.py -f $LINK get 'Checklist(Livetest) (Basshu)' D39:I57
```

- **결과 열은 라운드마다 이동합니다.** 9행=라운드 라벨, 10행=`iOS Result`/`Android Result` 쌍.
  열을 고정하지 말고 헤더를 읽어 확인하세요.
- ⚠️ **검증하지 않은 행은 비워 둡니다.** 통과로 적으면 과대 보고입니다.

---

## 6. ⚠️ Windows 특유의 함정 2가지

### ① `PYTHONIOENCODING=utf-8` 을 빼면 "성공해 놓고 죽습니다"

`login` 과 `set` 은 끝에 `✅` 를 출력합니다. Windows 콘솔 기본 인코딩이 **cp949** 라
이 이모지를 못 찍고 `UnicodeEncodeError` 로 죽습니다.

**중요한 건 이때 작업은 이미 끝나 있다는 점입니다** — 토큰은 저장됐고 셀도 써졌습니다.
종료 코드만 비정상이라 실패로 오해하고 재시도하기 쉽습니다.

```powershell
$env:PYTHONIOENCODING = "utf-8"      # 매 세션 1회. 또는 setx 로 영구 설정
```

### ② 스크립트를 저장소 안에 두세요

`D:\다운로드\` 같은 곳에 두면 Claude Code 자동모드가 `Code from External` 로
**실행 자체를 막습니다.** `C:\GME\qa-automation\` 로 옮기면 바로 통과합니다.

---

## 권한에 대해

이 도구는 **로그인한 본인의 권한으로만** 동작합니다.

- SharePoint에서 열 수 없는 파일은 이 도구로도 열리지 않습니다
- 다른 사람의 권한을 빌려오거나 권한이 확대되지 않습니다
- 발급되는 토큰에는 본인 계정이 기록되며, 본인 PC에만 저장됩니다

즉 SharePoint 웹에서 직접 편집하는 것과 권한 범위가 동일합니다.

참고로 **Claude의 Microsoft 365 커넥터로는 이 작업을 할 수 없습니다.** 그쪽에 부여된
스코프가 읽기 전용(`Files.Read.All`·`Sites.Read.All`)이라 쓰기 도구가 전부 차단됩니다.
이 도구가 필요한 이유가 그것입니다.

---

## 문제 해결

| 증상 | 조치 |
|---|---|
| `UnicodeEncodeError: 'cp949'` | **작업은 이미 성공했습니다.** §6①대로 `PYTHONIOENCODING=utf-8` 을 넣으세요 |
| `환경변수가 설정되지 않았습니다` | 2단계 확인. `setx` 는 **새 터미널부터** 적용됩니다 |
| `로그인이 필요합니다` | `python gme_excel.py login` |
| `요청 실패 (HTTP 403)` | 그 파일의 **편집** 권한이 없음. 파일 소유자에게 요청 |
| `요청 실패 (HTTP 404)` | 공유 링크가 잘못됐거나 만료됨. SharePoint에서 다시 복사 |
| 파이썬이 스토어 안내를 염 | `python3` 대신 **`python`** 을 쓰세요(§1) |
| 브라우저가 안 열림 | 터미널에 출력된 주소를 직접 복사해서 여세요 |
| Claude가 `Code from External` 로 거부 | 스크립트를 저장소 안으로 옮기세요(§6②) |
| 로그인이 계속 실패 | `Remove-Item "$env:USERPROFILE\.gme_excel_token.json"` 후 다시 `login` |
