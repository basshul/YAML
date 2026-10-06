"""GME admin(백오피스)에 붙는 **유일한** 창구.

⚠️ 설계 규칙 — 이 파일 밖에서는 admin 에 직접 붙지 않는다.
   runner.py 가 PowerShell 창구인 것과 같은 규칙이다. admin 화면이 바뀌었을 때
   고칠 곳이 여기 하나로 끝나게 하려는 것이다.

왜 HTTP 직접 호출이 아니라 브라우저인가 (2026-10-02 조사):
  admin 은 ASP.NET WebForms(IIS 8.5 / ASP.NET 4.0) 다.
  · 모든 동작이 __VIEWSTATE / __EVENTVALIDATION 을 실어 보내는 포스트백이다.
  · 로그인 버튼의 onclick 이 setDeviceIdAndPostback() 이고, 이 JS 가
    localStorage 의 deviceId 를 읽어 HiddenDeviceId 를 채운 뒤 폼을 보낸다.
  requests 로 흉내 내려면 매 요청마다 VIEWSTATE 를 파싱해 되보내야 하고,
  화면이 조금만 바뀌어도 조용히 깨진다. → 실제 브라우저를 쓴다.

왜 영구 프로필인가:
  deviceId 가 localStorage 에 산다. 임시 프로필로 띄우면 **매 실행이 새 기기로**
  잡힌다. admin 에 기기 승인 절차가 있으면 거기서 막힌다.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeoutError, sync_playwright

ADMIN_DIR = Path(__file__).resolve().parent
WEB_RUNNER_DIR = ADMIN_DIR.parent
CONFIG_FILE = WEB_RUNNER_DIR / "config.local.json"
PROFILE_DIR = ADMIN_DIR / ".browser_profile"   # ★ deviceId 가 사는 곳 — 지우면 새 기기가 된다
SHOT_DIR = ADMIN_DIR / "shots"                 # 실패 시점 화면

# 로그인 화면의 표식. 이게 보이면 "아직/다시 로그인 화면" 이다.
LOGIN_MARKER = "#txtPwd"

_REQUIRED_KEYS = ("url", "username", "password", "compcode")


class AdminError(RuntimeError):
    """admin 자동화 공통 예외."""


class AdminLoginError(AdminError):
    """로그인이 되지 않았다(자격증명·회사코드·기기 승인 등)."""


class AdminSessionExpired(AdminError):
    """작업 도중 세션이 끊겨 로그인 화면으로 튕겼다."""


def load_admin_config() -> dict:
    """config.local.json 의 admin 블록을 읽는다.

    비밀번호는 **이 저장소에 들어오지 않는다** — config.local.json 은 gitignore 다.
    """
    if not CONFIG_FILE.exists():
        raise AdminError(
            f"{CONFIG_FILE.name} 이 없습니다. config.example.json 을 복사해서 만드세요."
        )
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("admin")
    if not isinstance(cfg, dict):
        raise AdminError(f"{CONFIG_FILE.name} 에 admin 블록이 없습니다.")
    missing = [k for k in _REQUIRED_KEYS if not str(cfg.get(k, "")).strip()]
    if missing:
        raise AdminError(
            f"{CONFIG_FILE.name} 의 admin 블록에 비어 있는 값이 있습니다: {', '.join(missing)}"
        )
    return cfg


class AdminSession:
    """로그인 → 액션들 → 로그아웃 을 **한 세션**으로 처리한다.

    세션은 5~10분 유휴면 끊긴다(ASP.NET 세션 타임아웃). 액션 사이 간격이
    그보다 짧으면 한 세션으로 쭉 간다. 끊겼을 때 **모르고 다음 액션으로 넘어가는 것**만
    막으면 되므로, 액션마다 ensure_alive() 로 확인하고 끊겼으면 거기서 멈춘다.

        with AdminSession(headless=False) as s:
            s.goto("Account/Search.aspx")
            ...
    """

    def __init__(self, *, headless: bool = True, slow_mo: int = 0, timeout_ms: int = 20_000):
        self._cfg = load_admin_config()
        self._headless = headless
        self._slow_mo = slow_mo
        self._timeout_ms = timeout_ms
        self._pw = None
        self._ctx = None
        self._page: Page | None = None

    # ── 수명 ────────────────────────────────────────────────────────────
    def __enter__(self) -> "AdminSession":
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        # 영구 프로필: localStorage(=deviceId)를 실행 간에 유지한다.
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=self._headless,
            slow_mo=self._slow_mo,
        )
        self._ctx.set_default_timeout(self._timeout_ms)
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self.login()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # 예외로 빠져나갈 때도 로그아웃은 시도한다 — 세션을 서버에 남기지 않는다.
        try:
            self.logout()
        except Exception:
            pass
        for closer in (self._ctx, self._pw):
            try:
                if closer is not None:
                    closer.close() if closer is self._ctx else closer.stop()
            except Exception:
                pass

    @property
    def page(self) -> Page:
        if self._page is None:
            raise AdminError("세션이 열려 있지 않습니다 (with 문 안에서 쓰세요).")
        return self._page

    @property
    def base_url(self) -> str:
        """admin 로그인 경로. 예: http://host:5001/admin/"""
        return self._cfg["url"].rstrip("/") + "/"

    @property
    def site_url(self) -> str:
        """사이트 루트. 메뉴 링크가 /Remit/... 처럼 루트 기준이라 필요하다."""
        from urllib.parse import urlsplit
        parts = urlsplit(self.base_url)
        return f"{parts.scheme}://{parts.netloc}/"

    # ── 로그인·로그아웃 ──────────────────────────────────────────────────
    def login(self) -> None:
        """로그인 폼 3필드를 채우고 제출한다.

        ★ btnLogin 은 **실제로 클릭해야** 한다 — onclick 의 JS 가 HiddenDeviceId 를
          채운 뒤 포스트백한다. 폼을 직접 submit 하면 기기 정보가 빈 채로 간다.
        """
        page = self.page
        page.goto(self.base_url, wait_until="domcontentloaded")
        page.fill("#txtUsername", self._cfg["username"])
        page.fill("#txtPwd", self._cfg["password"])
        page.fill("#txtCompcode", str(self._cfg["compcode"]))
        page.click("#btnLogin")
        try:
            page.wait_for_load_state("networkidle")
        except PWTimeoutError:
            pass

        if page.locator(LOGIN_MARKER).count():
            # 로그인 화면에 그대로 있다 = 실패. 화면의 메시지를 그대로 올려준다.
            reason = self._visible_error(page) or "원인 메시지를 화면에서 찾지 못했다"
            shot = self.screenshot("login_failed")
            raise AdminLoginError(f"admin 로그인 실패: {reason} (화면: {shot})")

    def logout(self) -> None:
        """세션을 서버에서 끊는다.

        경로는 정찰(2026-10-02)에서 확인했다: 사이트 루트의 /LogOut.aspx.
        ★ CSS 속성 선택자는 대소문자를 가린다 — href*='ogout' 로는 'LogOut' 이
          안 잡힌다. 보조 선택자에는 i 플래그를 붙인다.
        """
        if self._page is None:
            return
        try:
            self._page.goto(self.site_url + "LogOut.aspx", wait_until="domcontentloaded")
            return
        except Exception:
            pass
        link = self._page.locator("a[href*='logout' i], a[href*='logoff' i]").first
        if link.count():
            link.click()
            try:
                self._page.wait_for_load_state("networkidle")
            except PWTimeoutError:
                pass

    # ── 이동·점검 ───────────────────────────────────────────────────────
    def goto(self, path: str) -> None:
        """admin 안의 경로로 이동한 뒤 세션이 살아 있는지 확인한다."""
        if path.startswith("http"):
            url = path
        elif path.startswith("/"):
            url = self.site_url + path.lstrip("/")      # 사이트 루트 기준
        else:
            url = self.base_url + path                  # admin/ 기준
        try:
            self.page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:
            # 직전 포스트백 이동과 겹치면 한 번은 이렇게 튕긴다 → 가라앉히고 다시
            if "interrupted by another navigation" not in str(exc):
                raise
            self.page.wait_for_load_state("load")
            self.page.goto(url, wait_until="domcontentloaded")
        self.ensure_alive()

    def ensure_alive(self) -> None:
        """세션이 끊겨 로그인 화면으로 튕겼으면 **거기서 멈춘다.**

        끊긴 줄 모르고 다음 액션으로 넘어가면 '사전 작업을 했다'고 믿은 채
        테스트가 돌아 FAIL 로 위장된다 — 그게 제일 나쁜 결과다.
        """
        if self.page.locator(LOGIN_MARKER).count():
            raise AdminSessionExpired(
                "admin 세션이 끊겼습니다(로그인 화면으로 튕김). 여기서 중단합니다."
            )

    def screenshot(self, name: str) -> Path:
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOT_DIR / f"{name}.png"
        try:
            self.page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass
        return path

    @staticmethod
    def _visible_error(page: Page) -> str:
        """로그인 화면에 떠 있는 오류 문구를 긁는다(있으면)."""
        for sel in (".alert", ".text-danger", "[id*='lblMsg']", "[id*='lblError']"):
            loc = page.locator(sel).first
            if loc.count():
                text = (loc.inner_text() or "").strip()
                if text:
                    return text
        return ""
