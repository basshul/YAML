#!/usr/bin/env python3
"""
SharePoint 엑셀 셀 단위 편집 (Microsoft Graph Excel API)

파일을 통째로 교체하지 않고 셀 단위로 조작하므로, 다른 사람이 동시에
편집 중이어도 그 변경이 유실되지 않는다. 차트/서식/매크로도 보존된다.

인증은 Authorization Code + PKCE. 로그인한 본인 권한으로만 동작하며,
SharePoint에서 접근 권한이 없는 파일은 이 도구로도 열리지 않는다.

── 설정 ──────────────────────────────────────────────
    export GME_CLIENT_ID="0ba0c638-c539-4584-b803-8af3ae62ddd1"
    export GME_TENANT_ID="b19514d1-d63d-4dda-b580-d80917436738"
    export GME_FILE_URL="<자주 쓰는 파일의 공유 링크>"   # 선택

── 사용 ──────────────────────────────────────────────
    python3 gme_excel.py login                        # 최초 1회
    python3 gme_excel.py whoami                       # 로그인 확인

    python3 gme_excel.py sheets                       # 시트 목록
    python3 gme_excel.py get '시트명' A1:H20           # 범위 읽기
    python3 gme_excel.py set '시트명' I11 '값'         # 셀 쓰기

    파일을 매번 지정하려면 -f 옵션을 쓴다.
    python3 gme_excel.py -f '<공유링크>' sheets
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

CLIENT_ID = os.environ.get("GME_CLIENT_ID", "")
TENANT    = os.environ.get("GME_TENANT_ID", "")
SCOPES    = "Files.ReadWrite.All offline_access User.Read"

GRAPH     = "https://graph.microsoft.com/v1.0"
CACHE     = os.path.expanduser("~/.gme_excel_token.json")


def auth_base():
    return f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0"


# ---------------------------------------------------------------- HTTP

def _req(url, method="GET", body=None, headers=None, form=False):
    headers = dict(headers or {})
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw[:600]
        raise SystemExit(f"\n요청 실패 (HTTP {e.code})\n{detail}\n")


# ---------------------------------------------------------------- 인증

def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _save(tok):
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 120
    with open(CACHE, "w") as f:
        json.dump(tok, f)
    os.chmod(CACHE, 0o600)
    return tok


class _Catch(http.server.BaseHTTPRequestHandler):
    """리디렉션으로 돌아온 ?code= 를 한 번만 받아낸다."""
    result = {}

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Catch.result = {k: v[0] for k, v in q.items()}
        ok = "code" in _Catch.result
        msg = ("로그인 완료. 터미널로 돌아가세요." if ok else
               f"실패: {_Catch.result.get('error_description', '알 수 없는 오류')}")
        body = ("<html><meta charset='utf-8'><body "
                f"style='font:16px sans-serif;padding:3em'>{msg}</body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


def login():
    _need_config()

    # 'http://localhost' 로 등록된 리디렉션 URI는 임의 포트를 허용한다.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    redirect = f"http://localhost:{port}"

    verifier  = _b64(secrets.token_bytes(48))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    state     = _b64(secrets.token_bytes(16))

    url = f"{auth_base()}/authorize?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect,
        "response_mode": "query",
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    print("\n  브라우저에서 본인 회사 계정으로 로그인해주세요.")
    print(f"  창이 안 열리면 아래 주소를 직접 여세요:\n\n  {url}\n")
    webbrowser.open(url)

    srv = http.server.HTTPServer(("127.0.0.1", port), _Catch)
    srv.timeout = 300
    srv.handle_request()
    srv.server_close()

    res = _Catch.result
    if "code" not in res:
        raise SystemExit(f"인증 실패: {res.get('error_description', res)}")
    if res.get("state") != state:
        raise SystemExit("state 불일치 — 중단합니다.")

    _save(_req(f"{auth_base()}/token", "POST", {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": res["code"],
        "redirect_uri": redirect,
        "code_verifier": verifier,
    }, form=True))
    print("✅ 로그인 완료\n")


def _need_config():
    missing = [n for n, v in (("GME_CLIENT_ID", CLIENT_ID),
                              ("GME_TENANT_ID", TENANT)) if not v]
    if missing:
        raise SystemExit(
            "환경변수가 설정되지 않았습니다: " + ", ".join(missing) +
            "\n설치 안내(README)의 '2. 환경변수 설정' 을 참고하세요.")


def token():
    _need_config()
    if not os.path.exists(CACHE):
        raise SystemExit("로그인이 필요합니다:  python3 gme_excel.py login")
    tok = json.load(open(CACHE))
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    tok = _save(_req(f"{auth_base()}/token", "POST", {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": tok["refresh_token"],
        "scope": SCOPES,
    }, form=True))
    return tok["access_token"]


def H():
    return {"Authorization": f"Bearer {token()}"}


# ---------------------------------------------------------------- 대상 파일

def workbook_url(link):
    """SharePoint 공유 링크 → 해당 통합 문서의 Graph workbook 엔드포인트."""
    if not link:
        raise SystemExit(
            "대상 파일이 지정되지 않았습니다.\n"
            "  -f '<공유링크>' 로 지정하거나, GME_FILE_URL 환경변수를 설정하세요.")
    sid = "u!" + base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
    item = _req(f"{GRAPH}/shares/{sid}/driveItem", headers=H())
    drive = item["parentReference"]["driveId"]
    return f"{GRAPH}/drives/{drive}/items/{item['id']}/workbook", item["name"]


def _range(wb, sheet, addr):
    return (f"{wb}/worksheets('{urllib.parse.quote(sheet)}')"
            f"/range(address='{addr}')")


# ---------------------------------------------------------------- 명령

def cmd_whoami(a):
    me = _req(f"{GRAPH}/me", headers=H())
    print(f"  {me.get('displayName')}  <{me.get('userPrincipalName')}>")


def cmd_sheets(a):
    wb, name = workbook_url(a.file)
    print(f"  [{name}]")
    for w in _req(f"{wb}/worksheets", headers=H())["value"]:
        print(f"  {w['position']:>2}  {w['name']}")


def cmd_get(a):
    wb, _ = workbook_url(a.file)
    for row in _req(_range(wb, a.sheet, a.range), headers=H())["values"]:
        print("\t".join("" if c is None else str(c) for c in row))


def cmd_set(a):
    wb, _ = workbook_url(a.file)
    r = _req(_range(wb, a.sheet, a.cell), "PATCH",
             {"values": [[a.value]]}, headers=H())
    print(f"✅ {a.sheet}!{a.cell} = {r['values'][0][0]!r}")


# ---------------------------------------------------------------- CLI

def main():
    p = argparse.ArgumentParser(
        description="SharePoint 엑셀 셀 단위 편집",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("-f", "--file", default=os.environ.get("GME_FILE_URL", ""),
                   help="대상 파일의 SharePoint 공유 링크 "
                        "(기본값: GME_FILE_URL 환경변수)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login",  help="본인 계정으로 로그인 (최초 1회)")
    sub.add_parser("whoami", help="현재 로그인 계정 확인")
    sub.add_parser("sheets", help="시트 목록")

    g = sub.add_parser("get", help="범위 읽기")
    g.add_argument("sheet")
    g.add_argument("range", help="예: A1:H20")

    s = sub.add_parser("set", help="셀 쓰기")
    s.add_argument("sheet")
    s.add_argument("cell", help="예: I11")
    s.add_argument("value")

    a = p.parse_args()
    {"login": lambda _: login(), "whoami": cmd_whoami, "sheets": cmd_sheets,
     "get": cmd_get, "set": cmd_set}[a.cmd](a)


if __name__ == "__main__":
    main()
