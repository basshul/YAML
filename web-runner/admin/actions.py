r"""admin 사전 작업 액션들.

각 액션은 AdminSession 을 받아 **한 가지 일만** 한다. 세션을 직접 열지 않는다 —
"로그인 → 액션 여러 개 → 로그아웃"을 한 세션으로 묶는 건 부르는 쪽(서버/버튼)의 몫이다.

⚠️ 비가역 액션(삭제·초기화)은 confirm=True 를 명시적으로 받기 전에는 실행하지 않는다.

실행(단독 확인용):
    .venv\Scripts\python.exe admin\actions.py find test006
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin.session import AdminSession, AdminError, AdminSessionExpired  # noqa: E402
import user_profile                              # noqa: E402
from admin import documents                  # noqa: E402

# 고객을 찾을 수 있는 화면들. (경로, 그리드 접두어, 설명)
# ★ 화면마다 **담는 모집단이 다르다**:
#   OnlineCustomer/List 는 '승인 대기' 목록이라 이미 승인된 계정은 안 나온다
#   (2026-10-02 확인 — seungsoo818 이 안 나와서 검색이 깨진 줄 알았다).
CUSTOMER_SCREENS = {
    "setup":    ("/Remit/Administration/CustomerSetup/List.aspx", "grid_list", "고객 설정"),
    "kjbank":   ("/KJBank/CustomerSetup/ModifyCustomer.aspx", "grid_kjcustomer", "KJ뱅크 고객"),
    "approval": ("/Remit/Administration/OnlineCustomer/List.aspx", "grid_list", "승인 대기"),
}


def find_customer(session: AdminSession, user_id: str, screen: str = "setup") -> dict:
    """User ID 로 고객을 찾는다. **조회만 한다.**

    ⚠️ 그리드의 검색 상태는 **세션에 남는다** — 같은 grid_list 이름을 여러 화면이
       공유해서, 다른 화면에서 쓴 검색어가 그대로 들어 있는 걸 봤다.
       그래서 조건·검색어·날짜를 **매번 전부 명시한다.** 비워 두면 직전 값이 쓰인다.
    """
    path, grid, _label = CUSTOMER_SCREENS[screen]
    page = session.page
    session.goto(path)

    page.select_option(f"#{grid}_searchCriteria", "emailId")
    page.fill(f"#{grid}_searchValue", user_id)
    # 날짜 범위가 남아 있으면 오래된 계정이 걸러진다 → 비운다.
    # ★ 이 칸들은 데이트피커라 readonly 다. fill() 은 못 쓰고 DOM 으로 지워야 한다.
    for date_field in (f"#{grid}_fromDate", f"#{grid}_toDate"):
        loc = page.locator(date_field)
        if loc.count() and loc.input_value():
            loc.evaluate("el => { el.value = ''; }")

    # ★ 검색은 페이지 자신의 함수로 돌린다.
    #   Swift_grid.js 의 SubmitForm(gridName) 은 숨은 제출버튼의 .click() 을 부른다.
    #   · Playwright 의 click() 은 'display:none' 이라 막힌다.
    #   · 검색창 Enter 는 더 나쁘다 — WebForms 포스트에 **버튼 이름이 안 실려**
    #     서버가 검색 핸들러를 타지 않는다(빈 표가 돌아온다).
    page.evaluate(f"SubmitForm('{grid}')")
    page.wait_for_load_state("networkidle")
    session.ensure_alive()

    rows = page.eval_on_selector_all(
        f"#{grid}_body tr",
        """trs => trs.map(tr => ({
            cells: [...tr.children].map(td => (td.innerText || '').trim()),
            links: [...tr.querySelectorAll('a, button')].map(a => ({
                text: (a.innerText || a.title || '').trim(),
                href: a.getAttribute('href') || a.getAttribute('onclick') || '',
            })),
        })).filter(r => r.cells.length > 1)""",
    )
    hits = [r for r in rows if any(user_id.lower() == c.lower() for c in r["cells"])]
    return {
        "user_id": user_id,
        "screen": screen,
        "found": bool(hits),
        "rows": hits,
        "row_count": len(rows),
    }


# 스위트 전 사람이 admin 에 들어가 눈으로 확인하던 것 — GUIDE.md §10.1 의 '계정 5개'.
# want:
#   exists — 있어야 한다. 없으면 플로우가 진입부터 막힌다
#   absent — **없어야** 한다. 06_Registration 이 생성·소모하는 계정이라
#            남아 있으면 같은 ID 로 다시 가입할 수 없어 재실행이 불가능하다
# 점검의 **모양**만 여기 둔다 — 실제 계정 ID 는 사용자 프로파일에서 온다.
#   (`Maestro\env\user.<이름>.env`. maestro 플로우도 같은 파일을 읽는다 →
#    계정을 두 군데에 적어 어긋나는 일이 없다.)
# 키 → (원하는 상태, 왜 그래야 하는가)
PREFLIGHT_SHAPE = [
    ("ACCT_MAIN",     "exists", "G1·G2·G4 기본 계정 (한국인·은행 연결)"),
    ("ACCT_FOREIGN",  "exists", "외국인·은행 미연결 (14_02 · 25_Profile_Foreign)"),
    ("ACCT_GMEPAY",   "exists", "외국인·GMEPay 신청완료 (14_03)"),
    ("ACCT_SIGNUP_1", "absent", "06_Registration 이 소모 — 남아 있으면 재실행 불가"),
    ("ACCT_SIGNUP_2", "absent", "06_Registration 이 소모 — 남아 있으면 재실행 불가"),
]

# 업로드 문서가 **승인 대기로 남아 있으면 안 되는** 계정의 키.
# 남아 있으면 신분증 업로드를 다루는 플로우가 기존 대기 건에 걸려 갈라진다.
PREFLIGHT_DOC_KEYS = ["ACCT_MAIN", "ACCT_FOREIGN", "ACCT_GMEPAY"]


def preflight_plan(user: str) -> tuple[list[dict], list[str]]:
    """프로파일을 읽어 (계정 점검 목록, 문서 점검 대상) 을 만든다.

    ★ **값이 빈 키는 통째로 뺀다.** 아직 그 역할 계정이 없는 사람에게
      없는 계정을 찾게 하면 고칠 수도 없는 NG 만 쌓인다.
    """
    acct = user_profile.accounts(user)
    accounts = [
        {"user_id": acct[key], "want": want, "why": why}
        for key, want, why in PREFLIGHT_SHAPE if acct.get(key)
    ]
    docs = [acct[key] for key in PREFLIGHT_DOC_KEYS if acct.get(key)]
    return accounts, docs


def check_account(session: AdminSession, spec: dict) -> dict:
    """계정 한 건을 점검한다. 고칠 수 있으면 fix 에 그 방법을 적는다."""
    found = find_customer(session, spec["user_id"], "setup")
    customer_id = customer_id_of(found)
    ok = found["found"] if spec["want"] == "exists" else not found["found"]
    # ★ 고칠 수 있는 건 '없어야 하는데 있는' 경우뿐이다.
    #   '있어야 하는데 없는' 계정은 사람이 만들어야 한다(06_Registration 이 만드는 계정이고,
    #   그건 테스트지 사전 작업이 아니다) → fix 를 주지 않는다.
    fix = None if ok or spec["want"] == "exists" else "remove_customer"
    return {
        "kind": "account", "user_id": spec["user_id"],
        "want": spec["want"], "why": spec["why"],
        "found": found["found"], "ok": ok,
        "detail": ("#" + customer_id) if customer_id else "",
        "customer_id": customer_id,
        "fix": fix,
        "fix_label": "계정 삭제" if fix else "",
    }


def check_documents(session: AdminSession, user_id: str) -> dict:
    """업로드 문서(승인 대기) 한 계정을 점검한다."""
    pending = [d for d in documents.list_documents(session, user_id)
               if d["status"].upper() == documents.PENDING]
    return {
        "kind": "documents", "user_id": user_id,
        "want": "absent",
        "why": "승인 대기 문서가 남아 있으면 신분증 업로드 플로우가 기존 건에 걸린다",
        "found": bool(pending), "ok": not pending,
        "detail": ", ".join(d["doc_type"] for d in pending),
        "customer_id": "",
        "fix": "clear_documents" if pending else None,
        "fix_label": "대기 문서 삭제" if pending else "",
    }


def preflight(session: AdminSession, user: str, accounts: list[dict] | None = None,
              docs: list[str] | None = None) -> dict:
    """스위트 사전 조건을 **조회만으로** 점검한다.

    한 세션 안에서 차례로 확인한다. 세션이 끊기면 find_customer 안의
    ensure_alive() 가 거기서 멈춘다 — 못 본 항목을 '정상'으로 보고하지 않는다.
    """
    if accounts is None or docs is None:
        plan_accounts, plan_docs = preflight_plan(user)
        accounts = plan_accounts if accounts is None else accounts
        docs = plan_docs if docs is None else docs
    checks = [check_account(session, spec) for spec in accounts]
    checks += [check_documents(session, u) for u in docs]
    return {"checks": checks, "ok": all(c["ok"] for c in checks), "user": user}


FIXES = {
    # 고칠 수 있는 NG 는 둘뿐이다. 둘 다 **비가역**이라 confirm 을 명시해야 돈다.
    "remove_customer": "계정 삭제",
    "clear_documents": "승인 대기 문서 삭제",
}


def fix_check(session: AdminSession, fix: str, user_id: str, user: str, *,
              confirm: bool = False) -> dict:
    """NG 항목 하나를 처리하고, **그 항목만 다시 점검해서** 돌려준다.

    ⚠️ 둘 다 되돌릴 수 없다. confirm=False 면 무엇을 할지만 알려주고 멈춘다.
    """
    if fix not in FIXES:
        raise AdminError("모르는 처리 방법입니다: " + str(fix))

    if fix == "remove_customer":
        found = find_customer(session, user_id, "setup")
        if not found["found"]:
            return {"done": False, "why": "이미 없습니다",
                    "check": check_account(session, _spec_of(user_id))}
        cid = customer_id_of(found)
        r = remove_customer(session, user_id, cid, confirm=confirm)
        if not confirm:
            return {"done": False, "dry_run": True,
                    "target": r["picked"], "selected": r["selected_value"]}
        return {"done": True, "check": check_account(session, _spec_of(user, user_id))}

    # clear_documents
    r = documents.clear_pending(session, user_id, confirm=confirm)
    if not confirm:
        return {"done": False, "dry_run": True,
                "targets": [t["doc_type"] for t in r["targets"]]}
    return {"done": True, "cleared": [d["doc_type"] for d in r["done"]],
            "check": check_documents(session, user_id)}


def _spec_of(user: str, user_id: str) -> dict:
    """처리 뒤 **그 항목만** 다시 점검할 때 쓸 기준. 프로파일에서 찾는다.

    못 찾으면 absent 로 둔다 — 고칠 수 있는 NG 는 '없어야 하는데 있는' 경우뿐이라
    (remove_customer) 처리 직후의 기대 상태가 absent 다.
    """
    accounts, _ = preflight_plan(user)
    for spec in accounts:
        if spec["user_id"] == user_id:
            return spec
    return {"user_id": user_id, "want": "absent", "why": ""}


def fix_all(session: AdminSession, items: list[dict], user: str, *,
              confirm: bool = False) -> dict:
    """여러 NG 를 **한 세션에서** 처리한다.

    건별로 세션을 새로 열면 로그인만 N 번이다(한 번에 15~25초).
    "로그인 → 전체 액션 → 로그아웃" 이라는 원래 방침이 여기에도 적용된다.

    한 건이 실패해도 **멈추지 않고 나머지를 계속한다** — 대신 그 건의 사유를 남긴다.
    단, 세션이 끊긴 것(AdminSessionExpired)이라면 이어가 봐야 전부 실패하므로 거기서 멈춘다.
    """
    results = []
    for item in items:
        fix, user_id = item.get("fix"), item.get("user_id")
        try:
            r = fix_check(session, fix, user_id, user, confirm=confirm)
        except AdminSessionExpired:
            results.append({"user_id": user_id, "fix": fix, "done": False,
                            "error": "세션이 끊겨 여기서 멈췄습니다"})
            break
        except AdminError as exc:
            results.append({"user_id": user_id, "fix": fix, "done": False,
                            "error": str(exc)})
            continue
        r["user_id"], r["fix"] = user_id, fix
        results.append(r)
    return {"results": results,
            "ok": all(r.get("done") for r in results) if results else True}


def guard_target(user: str, user_id: str) -> None:
    """그 사용자의 프로파일에 없는 계정은 건드리지 않는다."""
    mine = set(user_profile.accounts(user).values())
    if user_id not in mine:
        raise AdminError(
            user_id + " 는 " + user + " 의 프로파일에 없는 계정이다 — 처리하지 않는다."
            " (화면이 오래됐거나 사용자를 잘못 고른 것이다)")


def run_fix_all(items: list[dict], user: str, *,
                confirm: bool = False, headless: bool = True) -> dict:
    """로그인 → 전부 처리 → 로그아웃. 서버(「NG 전부 처리」)가 부르는 진입점."""
    for it in items:
        guard_target(user, it.get("user_id", ""))
    with AdminSession(headless=headless) as session:
        return fix_all(session, items, user, confirm=confirm)


def run_fix(fix: str, user_id: str, user: str, *,
            confirm: bool = False, headless: bool = True) -> dict:
    """로그인 → 처리 → 재점검 → 로그아웃. 서버(버튼)가 부르는 진입점.

    ⛔ **대상이 그 사용자의 프로파일에 있는 계정인지 먼저 확인한다.** 계정 삭제는
      되돌릴 수 없는데, 낡은 화면이 남의 계정을 지우라고 보낼 수 있다.
    """
    guard_target(user, user_id)
    with AdminSession(headless=headless) as session:
        return fix_check(session, fix, user_id, user, confirm=confirm)


def run_preflight(user: str, *, headless: bool = True) -> dict:
    """로그인 → 점검 → 로그아웃 을 한 세션으로. 서버(버튼)가 부르는 진입점."""
    with AdminSession(headless=headless) as session:
        return preflight(session, user)


REMOVE_CUSTOMER_PAGE = "/AgentPanel/OnlineAgent/DeleteCustomer/DeleteCustomer.aspx"


def customer_id_of(found: dict) -> str:
    """find_customer 결과에서 customerId 를 꺼낸다(행의 Manage.aspx 링크에 들어 있다)."""
    if not found["found"]:
        return ""
    for link in found["rows"][0]["links"]:
        m = re.search(r"customerId=(\d+)", link["href"])
        if m:
            return m.group(1)
    return ""


def remove_customer(session: AdminSession, user_id: str, customer_id: str = "",
                    *, confirm: bool = False) -> dict:
    """회원가입이 소모한 테스트 계정을 admin 에서 제거한다. **되돌릴 수 없다.**

    confirm=False(기본)면 **제출 직전까지만** 하고 멈춘다 — 자동완성이 어떤 계정을
    집었는지 확인하는 용도다. 실제 제출은 confirm=True 를 명시해야 한다.

    ★ 이 화면은 자동완성이다(swift_autocomplete.js). 글자만 타이핑하면 숨은
      txtEmail_aValue 가 **비거나 직전 값이 남는다** — 그 상태로 제출하면 엉뚱한
      계정이 대상이 될 수 있다. 목록에서 항목을 **실제로 골라야** 거기에
      값이 들어간다. 그래서 고른 뒤 기대값과 대조하고, 다르면 제출하지 않는다.

    ★ 이 화면의 숨은 값은 **customerId 가 아니라 사용자 ID** 다
      (자동완성 소스 category=remit-CustomerEmailV2 의 Id 가 사용자 ID).
      2026-10-02 에 customerId 로 대조했다가 막혔다 — 안전장치가 제 일을 한 것이다.
      customer_id 는 기록용으로만 받는다(무엇을 지웠는지 로그에 남기려고).
    """
    page = session.page
    session.goto(REMOVE_CUSTOMER_PAGE)

    # 1) 자동완성 깨우기 — _aText 에 포커스하면 _aSearch 가 드러난다
    page.click("#txtEmail_aText")
    page.fill("#txtEmail_aSearch", "")
    page.type("#txtEmail_aSearch", user_id, delay=60)

    # 2) 제안 목록에서 **정확히 일치하는** 항목만 고른다.
    #    항목 표기는 "test006 | 01090380808 | anfrhrl001@gmail.com" 처럼 합성돼 있다.
    #    첫 칸(사용자 ID)으로 **완전일치** 비교한다 — 부분일치를 허용하면
    #    test006 이 test0061 같은 계정을 집을 수 있다.
    page.wait_for_selector("ul.ui-autocomplete li", state="visible")
    items = page.locator("ul.ui-autocomplete li")
    picked = None
    for i in range(items.count()):
        label = (items.nth(i).inner_text() or "").strip()
        if label.split("|")[0].strip().lower() == user_id.lower():
            items.nth(i).click()
            picked = label
            break
    if picked is None:
        offered = [items.nth(i).inner_text().strip() for i in range(min(items.count(), 5))]
        raise AdminError(f"자동완성에 '{user_id}' 와 정확히 같은 항목이 없다. 후보: {offered}")

    # 3) 숨은 값 대조 — 어긋나면 여기서 끝난다(아무 일도 일어나지 않는다)
    got = (page.input_value("#txtEmail_aValue") or "").strip()
    result = {
        "user_id": user_id, "picked": picked, "customer_id": str(customer_id),
        "selected_value": got, "submitted": False, "page_message": "",
    }
    if got.lower() != user_id.lower():
        raise AdminError(
            f"고른 항목의 값이 다르다: 기대 '{user_id}' / 실제 '{got}' → 제출하지 않는다")
    if not confirm:
        return result          # 예행 — 제출하지 않는다

    # 4) 제출. 확인 대화상자가 뜨면 수락한다.
    #    ★ Playwright 는 대화상자를 **기본으로 취소**한다 — 핸들러가 없으면
    #      아무 일도 일어나지 않은 채 성공처럼 보인다.
    page.on("dialog", lambda d: d.accept())
    page.click("#changePass")
    page.wait_for_load_state("networkidle")
    session.ensure_alive()
    result["submitted"] = True
    result["page_message"] = _page_message(page)
    return result


def _page_message(page) -> str:
    """화면에 뜬 결과 문구를 긁는다(있으면)."""
    for sel in (".alert", "[id*='lblMsg']", "[id*='lblError']", "[id*='Message']"):
        loc = page.locator(sel).first
        if loc.count():
            text = (loc.inner_text() or "").strip()
            if text:
                return text
    return ""


def _main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "preflight":
        # 두 번째 인자로 사용자를 받는다. 없으면 Basshu — 종전 동작 그대로.
        who = sys.argv[2] if len(sys.argv) >= 3 else "Basshu"
        print("사용자: " + who)
        result = run_preflight(who)
        KIND = {"account": "계정", "documents": "문서"}
        for c in result["checks"]:
            want = "있어야 함" if c["want"] == "exists" else "없어야 함"
            got = "있음" if c["found"] else "없음"
            print(f"  {'OK ' if c['ok'] else '★NG'}  {KIND.get(c.get('kind'), ''):<4} "
                  f"{c['user_id']:<14} {want:<8} / {got:<4} {c.get('detail', ''):<22} {c['why']}")
        print(("사전 조건 충족" if result["ok"] else "★ 사전 조건 미충족 — 위 ★NG 를 해결해야 한다"))
        return 0 if result["ok"] else 1

    if len(sys.argv) >= 3 and sys.argv[1] == "remove":
        return _main_remove(sys.argv[2:])

    if len(sys.argv) < 3 or sys.argv[1] != "find":
        print(__doc__)
        return 2
    try:
        with AdminSession(headless=True) as s:
            for user_id in sys.argv[2:]:
                for screen, (_p, _g, label) in CUSTOMER_SCREENS.items():
                    r = find_customer(s, user_id, screen)
                    mark = "찾음" if r["found"] else "없음"
                    print(f"{user_id:<16} {label:<10} {mark}  (표의 행 {r['row_count']}개)")
                    for row in r["rows"]:
                        print("    " + " | ".join(row["cells"][:6]))
                        for link in row["links"]:
                            if link["text"] or link["href"]:
                                print(f"      동작: {(link['text'] or '-')[:20]:<20} {link['href'][:90]}")
    except AdminError as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 1
    return 0


def _main_remove(argv: list[str]) -> int:
    """remove <user_id>... [--confirm]   — --confirm 이 없으면 예행이다."""
    confirm = "--confirm" in argv
    user_ids = [a for a in argv if not a.startswith("--")]
    try:
        with AdminSession(headless=True) as s:
            for user_id in user_ids:
                before = find_customer(s, user_id, "setup")
                cid = customer_id_of(before)
                if not cid:
                    print(f"{user_id}: 조회되지 않는다 — 건너뛴다")
                    continue
                print(f"{user_id}: 조회됨 customerId={cid}")

                r = remove_customer(s, user_id, cid, confirm=confirm)
                print(f"  자동완성이 고른 항목 = '{r['picked']}'")
                print(f"  숨은 값 '{r['selected_value']}' == 기대 '{user_id}' → 일치")
                if not confirm:
                    print("  [예행] 제출하지 않았다")
                    continue
                after = find_customer(s, user_id, "setup")
                print(f"  제출함 → 재조회: "
                      + ("사라졌다 ✅" if not after["found"] else "아직 보인다 ⚠️")
                      + (f" | 화면: {r['page_message']}" if r["page_message"] else ""))
    except AdminError as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
