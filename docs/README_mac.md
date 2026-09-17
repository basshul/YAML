# SharePoint 엑셀 편집 도구 설치 안내 — macOS 판

> 🪟 **Windows 사용자는 [README_win.md](README_win.md) 를 보세요.**
> 이 문서는 macOS/zsh 기준이라 `~/.zshrc`·`export`·`python3` 가 Windows 에서는 통하지 않습니다.
> Windows 판에는 그 차이와 함께 **`PYTHONIOENCODING=utf-8` 누락 시 "성공해 놓고 죽는" 함정**도 적혀 있습니다.

QA 체크리스트 같은 SharePoint 엑셀 파일을 명령줄에서, 또는 Claude에게 시켜서
수정하기 위한 도구입니다.

**여러 명이 동시에 편집 중이어도 안전합니다.** 파일을 통째로 덮어쓰지 않고
지정한 셀만 바꾸기 때문에, 다른 사람이 같은 시간에 입력한 내용이 사라지지
않습니다. 차트·서식·수식도 그대로 보존됩니다.

---

## 1. 준비물

| 항목 | 확인 방법 |
|---|---|
| Python 3 | `python3 --version` — macOS는 기본 내장 |
| `gme_excel.py` | 이 문서와 같이 받은 파일 |
| 회사 계정 | 본인의 `@gmeremit.com` 계정 |
| 파일 접근 권한 | SharePoint에서 그 파일을 열 수 있으면 됨 |

별도로 설치할 라이브러리는 없습니다.

---

## 2. 환경변수 설정

터미널에서 아래를 실행합니다. `~/.zshrc` 에 넣어두면 매번 입력하지 않아도
됩니다.

```bash
echo '
export GME_CLIENT_ID="0ba0c638-c539-4584-b803-8af3ae62ddd1"
export GME_TENANT_ID="b19514d1-d63d-4dda-b580-d80917436738"
' >> ~/.zshrc
source ~/.zshrc
```

> 이 두 값은 비밀번호가 아닙니다. 앱을 식별하는 공개 값이며, 이것만으로는
> 아무 파일에도 접근할 수 없습니다. 실제 권한은 아래 3단계의 본인 로그인에서
> 생깁니다.

---

## 3. 로그인 (최초 1회)

```bash
python3 gme_excel.py login
```

브라우저가 열리면 **본인 회사 계정**으로 로그인합니다. 완료되면 터미널에
`✅ 로그인 완료` 가 표시됩니다.

이후에는 다시 로그인할 필요가 없습니다. 토큰이 `~/.gme_excel_token.json` 에
저장되고 자동으로 갱신됩니다.

확인:

```bash
python3 gme_excel.py whoami
```

---

## 4. 사용법

대상 파일은 SharePoint에서 **공유 링크를 복사**해서 지정합니다.

```bash
LINK='https://gmeremittance.sharepoint.com/:x:/s/GME-IT-Korea/IQC...'

# 시트 목록
python3 gme_excel.py -f "$LINK" sheets

# 범위 읽기
python3 gme_excel.py -f "$LINK" get 'Checklist(Live)' B9:I20

# 셀 쓰기
python3 gme_excel.py -f "$LINK" set 'Checklist(Live)' I11 'Pass'
```

자주 쓰는 파일이 정해져 있으면 환경변수로 등록해두고 `-f` 를 생략합니다.

```bash
export GME_FILE_URL='https://gmeremittance.sharepoint.com/:x:/s/...'
python3 gme_excel.py sheets
```

### Claude로 쓰는 경우

이 폴더에서 Claude를 열고 평소 말하듯 지시하면 됩니다.

> "Checklist(Live) 시트 11행 Comment에 'Pass' 넣어줘"

---

## 권한에 대해

이 도구는 **로그인한 본인의 권한으로만** 동작합니다.

- SharePoint에서 열 수 없는 파일은 이 도구로도 열리지 않습니다
- 다른 사람의 권한을 빌려오거나 권한이 확대되지 않습니다
- 발급되는 토큰에는 본인 계정이 기록되며, 본인 PC에만 저장됩니다

즉 SharePoint 웹에서 직접 편집하는 것과 권한 범위가 동일합니다.

---

## 문제 해결

| 증상 | 조치 |
|---|---|
| `환경변수가 설정되지 않았습니다` | 2단계를 다시 확인. 터미널을 새로 열었다면 `source ~/.zshrc` |
| `로그인이 필요합니다` | `python3 gme_excel.py login` |
| `요청 실패 (HTTP 403)` | 해당 파일 접근 권한이 없음. 파일 소유자에게 공유 요청 |
| `요청 실패 (HTTP 404)` | 공유 링크가 잘못됐거나 만료됨. SharePoint에서 다시 복사 |
| 브라우저가 안 열림 | 터미널에 출력된 주소를 직접 복사해서 여세요 |
| 로그인이 계속 실패 | `rm ~/.gme_excel_token.json` 후 다시 `login` |

### 시트 이름에 공백이나 괄호가 있는 경우

작은따옴표로 감싸면 됩니다.

```bash
python3 gme_excel.py -f "$LINK" get 'Checklist(Livetest) (Basshu)' B9:I20
```
