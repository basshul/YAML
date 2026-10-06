r"""admin — 업로드 문서(Document Upload List) 조회·정리.

경로: ADMINISTRATION > Online Customers > Online Remit > **Document Upload List** 탭
      = /Remit/Administration/OnlineCustomer/DocumentUploadList.aspx  (그리드 grid_listReUp)

★ 이 화면에 **「삭제」는 없다.** 행이 가진 동작은 `approve` / `reject` 둘뿐이고,
  승인 대기(PENDING) 문서를 치우는 수단은 **reject** 다. 그래서 여기서 말하는
  "문서 삭제" 는 reject 를 뜻한다.

동작 방식(2026-10-06 조사):
  행의 버튼이 `ApproveReject(rowId, customerId, type, docType, docNumber, idType)` 를 부른다.
  그 함수는 숨은 필드 `hdnType`/`hdnRowId`/`hdnCustomerId` 를 채우고 confirm() 을 띄운 뒤
  숨은 제출버튼 `#buttonApproveReject` 를 click() 한다.
  → 우리는 **같은 필드를 채우고 같은 버튼을 click()** 한다. 앱이 하는 일과 동일하고,
    confirm() 대화상자에 의존하지 않아 결과가 결정적이다(우리 쪽 확인 단계가 따로 있다).

실행:
    .venv\Scripts\python.exe admin\documents.py list seungsoo818
    .venv\Scripts\python.exe admin\documents.py clear seungsoo818            # 예행
    .venv\Scripts\python.exe admin\documents.py clear test123 --types ARC,Passport --confirm
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin.session import AdminSession, AdminError   # noqa: E402

PAGE = "/Remit/Administration/OnlineCustomer/DocumentUploadList.aspx"
GRID = "grid_listReUp"
PENDING = "PENDING"

# ApproveReject('6563','527451','reject','National Id','8808181229522','Neither')
ACTION_RE = re.compile(
    r"ApproveReject\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'",
)


def list_documents(session: AdminSession, user_id: str) -> list[dict]:
    """Username 으로 업로드 문서를 찾는다. **조회만 한다.**

    ⚠️ 그리드 검색 상태는 세션에 남는다 → 조건·검색어를 매번 명시한다.
    ⚠️ 검색 제출은 페이지 자신의 SubmitForm() 으로 한다. 검색창 Enter 는
       WebForms 포스트에 버튼 이름이 안 실려 **빈 표가 돌아온다.**
    """
    page = session.page
    session.goto(PAGE)
    page.select_option("#" + GRID + "_searchCriteria", "username")
    page.fill("#" + GRID + "_searchValue", user_id)
    page.evaluate("SubmitForm('" + GRID + "')")
    page.wait_for_load_state("networkidle")
    session.ensure_alive()

    raw = page.eval_on_selector_all(
        "#" + GRID + "_body tbody tr",
        """trs => trs.map(tr => ({
             cells: [...tr.children].map(td => (td.innerText || '').trim()),
             acts: [...tr.querySelectorAll('[onclick]')]
                     .map(e => e.getAttribute('onclick') || '')
           }))""",
    )

    docs = []
    for r in raw:
        cells = r["cells"]
        if len(cells) < 7:
            continue
        actions = {}
        row_id = customer_id = ""
        doc_type_js = ""
        for onclick in r["acts"]:
            m = ACTION_RE.search(onclick or "")
            if not m:
                continue
            row_id, customer_id, kind, doc_type_js = m.groups()
            actions[kind] = onclick
        if not row_id:
            continue
        docs.append({
            "user_id": cells[0], "name": cells[1], "wallet": cells[2],
            "country": cells[3], "status": cells[4], "doc_type": cells[5],
            "created": cells[6],
            "row_id": row_id, "customer_id": customer_id,
            "doc_type_js": doc_type_js, "actions": sorted(actions),
        })
    return docs


def reject_document(session: AdminSession, doc: dict, *, confirm: bool = False) -> dict:
    """문서 한 건을 reject 한다(= 승인 대기에서 치운다). **되돌릴 수 없다.**

    confirm=False(기본)면 **제출하지 않고** 무엇을 대상으로 잡았는지만 돌려준다.
    """
    result = {
        "user_id": doc["user_id"], "doc_type": doc["doc_type"], "status": doc["status"],
        "row_id": doc["row_id"], "customer_id": doc["customer_id"],
        "submitted": False,
    }
    if doc["status"].upper() != PENDING:
        raise AdminError(
            "승인 대기(PENDING) 가 아닌 문서다: "
            + doc["doc_type"] + " / " + doc["status"] + " → 건드리지 않는다")
    if "reject" not in doc["actions"]:
        raise AdminError(
            "이 행에 reject 동작이 없다: " + doc["doc_type"]
            + " (가능한 동작: " + ", ".join(doc["actions"] or ["없음"]) + ")")
    if not confirm:
        return result

    page = session.page
    # 앱의 ApproveReject() 가 하는 일을 그대로 한다 — 숨은 필드 3개 + 숨은 제출버튼 click()
    # ★ 이 click 은 **포스트백 이동**을 일으킨다. 그 이동이 커밋되기 전에 다음 goto 를
    #   하면 "interrupted by another navigation" 으로 죽는다(2026-10-06 두 번 겪었다 —
    #   제출 자체는 이미 나간 뒤라 더 헷갈린다). 이동을 명시적으로 기다린다.
    with page.expect_navigation(wait_until="load"):
        page.evaluate(
            """([rowId, customerId]) => {
                 document.getElementById('hdnType').value = 'reject';
                 document.getElementById('hdnRowId').value = rowId;
                 document.getElementById('hdnCustomerId').value = customerId;
                 document.getElementById('buttonApproveReject').click();
               }""",
            [doc["row_id"], doc["customer_id"]],
        )
    page.wait_for_load_state("networkidle")
    session.ensure_alive()
    result["submitted"] = True
    return result


def clear_pending(session: AdminSession, user_id: str, doc_types: list[str] | None = None,
                  *, confirm: bool = False) -> dict:
    """한 계정의 **승인 대기** 문서를 치운다.

    doc_types 를 주면 그 종류만(대소문자 무시). 안 주면 PENDING 전부.
    한 건 처리할 때마다 표가 다시 그려지므로 **매번 다시 조회해서 집는다** —
    들고 있던 행 참조를 재사용하면 엉뚱한 행을 건드릴 수 있다.
    """
    wanted = {t.strip().lower() for t in (doc_types or []) if t.strip()}
    done, skipped = [], []

    docs = list_documents(session, user_id)
    targets = [d for d in docs
               if d["status"].upper() == PENDING
               and (not wanted or d["doc_type"].strip().lower() in wanted)]
    for d in docs:
        if d not in targets:
            skipped.append({"doc_type": d["doc_type"], "status": d["status"],
                            "why": "대상 아님"})

    if not confirm:
        return {"user_id": user_id, "targets": targets, "skipped": skipped,
                "done": [], "dry_run": True}

    for want in list(targets):
        # ★ 매번 다시 조회한다. row_id 로 같은 행을 다시 찾아 상태까지 확인한 뒤 누른다.
        fresh = [d for d in list_documents(session, user_id) if d["row_id"] == want["row_id"]]
        if not fresh:
            skipped.append({"doc_type": want["doc_type"], "status": "-",
                            "why": "다시 조회하니 없다 — 이미 처리됨"})
            continue
        done.append(reject_document(session, fresh[0], confirm=True))

    left = [d for d in list_documents(session, user_id) if d["status"].upper() == PENDING]
    return {"user_id": user_id, "targets": targets, "skipped": skipped,
            "done": done, "left_pending": left, "dry_run": False}


# ── CLI ────────────────────────────────────────────────────────────────────

def _print_docs(user_id: str, docs: list[dict]) -> None:
    print(user_id + " — 문서 " + str(len(docs)) + "건")
    for d in docs:
        print("   " + d["status"].ljust(9) + d["doc_type"].ljust(14)
              + "row=" + d["row_id"].ljust(7) + "cust=" + d["customer_id"].ljust(9)
              + d["created"] + "  [" + ", ".join(d["actions"]) + "]")


def _main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("list", "clear"):
        print(__doc__)
        return 2
    cmd = argv[0]
    confirm = "--confirm" in argv
    types: list[str] = []
    users: list[str] = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--types" and i + 1 < len(argv):
            types = argv[i + 1].split(",")      # ★ 뒤따르는 값은 계정명이 아니다
            i += 2
            continue
        if a.startswith("--types="):
            types = a.split("=", 1)[1].split(",")
        elif not a.startswith("--"):
            users.append(a)
        i += 1
    if not users:
        print("계정을 지정하세요.", file=sys.stderr)
        return 2

    try:
        with AdminSession(headless=True) as s:
            for user in users:
                if cmd == "list":
                    _print_docs(user, list_documents(s, user))
                    continue

                r = clear_pending(s, user, types, confirm=confirm)
                if r["dry_run"]:
                    print(user + " — [예행] 대상 " + str(len(r["targets"])) + "건"
                          + (" (종류: " + ", ".join(types) + ")" if types else ""))
                    for t in r["targets"]:
                        print("   치울 것: " + t["doc_type"].ljust(14)
                              + t["status"] + "  row=" + t["row_id"])
                    for sk in r["skipped"]:
                        print("   건너뜀 : " + sk["doc_type"].ljust(14)
                              + sk["status"] + "  " + sk["why"])
                    print("   제출하지 않았습니다. 실제로 치우려면 --confirm 을 붙이세요.")
                    continue

                print(user + " — 처리 " + str(len(r["done"])) + "건")
                for d in r["done"]:
                    print("   reject 제출: " + d["doc_type"].ljust(14) + "row=" + d["row_id"])
                left = r["left_pending"]
                print("   남은 승인 대기: "
                      + ("없음 ✅" if not left else
                         str(len(left)) + "건 ⚠️ " + ", ".join(x["doc_type"] for x in left)))
    except AdminError as exc:
        print("[실패] " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
