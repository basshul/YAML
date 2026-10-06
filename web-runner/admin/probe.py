r"""admin 화면 정찰 — **조회만 한다. 아무것도 누르지 않는다.**

로그인 직후 화면의 메뉴 구조·링크·HTML·스크린샷을 떠서 admin/probe_out/ 에 남긴다.
여기서 뽑은 경로와 셀렉터로 실제 액션(계정 조회·잠금 해제·삭제)을 만든다.

실행:
    .venv\Scripts\python.exe admin\probe.py            # 창을 띄운 채(기본)
    .venv\Scripts\python.exe admin\probe.py --headless
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin.session import AdminSession, AdminError   # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "probe_out"


def dump(session: AdminSession, label: str) -> dict:
    """현재 화면을 통째로 남기고, 요약을 돌려준다."""
    page = session.page
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{label}.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(OUT_DIR / f"{label}.png"), full_page=True)

    links = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(e => ({text: (e.innerText||'').trim(), href: e.getAttribute('href')}))",
    )
    # WebForms admin 은 프레임을 쓰는 경우가 있다 — 있으면 같이 적어 둔다.
    frames = [{"name": f.name, "url": f.url} for f in page.frames if f is not page.main_frame]
    controls = page.eval_on_selector_all(
        "input, select, textarea, button",
        """els => els
            .filter(e => !['hidden'].includes(e.type))
            .map(e => ({
                tag: e.tagName.toLowerCase(),
                type: e.type || '',
                id: e.id || '',
                name: e.getAttribute('name') || '',
                text: (e.value || e.innerText || e.placeholder || '').trim().slice(0, 60),
            }))""",
    )
    summary = {
        "label": label,
        "url": page.url,
        "title": page.title(),
        "frames": frames,
        "controls": controls,
        "links": [l for l in links if l["href"] and not l["href"].startswith("#")],
    }
    (OUT_DIR / f"{label}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="admin 화면 정찰 — 조회만 한다")
    ap.add_argument("paths", nargs="*", help="추가로 떠 올 경로(사이트 루트 기준 /Remit/...)")
    ap.add_argument("--headless", action="store_true", help="창을 띄우지 않는다")
    args = ap.parse_args()

    try:
        with AdminSession(headless=args.headless, slow_mo=80) as s:
            report(dump(s, "01_after_login"), top_links=20)
            for i, path in enumerate(args.paths, start=2):
                label = f"{i:02d}_" + path.strip("/").replace("/", "_").replace(".aspx", "")
                s.goto(path)                       # ensure_alive() 가 안에서 돈다
                report(dump(s, label), top_links=0)
            print()
            print(f"덤프: {OUT_DIR}")
    except AdminError as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 1
    return 0


def report(summary: dict, *, top_links: int) -> None:
    print()
    print(f"── {summary['label']}  {summary['title']}")
    print(f"   {summary['url']}")
    if summary["frames"]:
        print("   프레임: " + ", ".join(f["url"] for f in summary["frames"]))
    controls = [c for c in summary["controls"] if c["id"] or c["name"]]
    if controls:
        print(f"   컨트롤 {len(controls)}개:")
        for c in controls[:50]:
            print(f"     {c['tag']:<8} {c['type']:<10} id={c['id']:<34} {c['text'][:34]}")
    if top_links:
        print(f"   링크 {len(summary['links'])}개 (상위 {top_links})")
        for link in summary["links"][:top_links]:
            print(f"     {link['text'][:34]:<34} {link['href']}")


if __name__ == "__main__":
    raise SystemExit(main())
