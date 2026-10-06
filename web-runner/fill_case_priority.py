r"""yaml 케이스 주석의 **빠진 중요도**를 체크리스트 시트 값으로 채운다.

    python fill_case_priority.py            # 예행 — 바뀔 줄만 보여준다
    python fill_case_priority.py --apply    # 실제로 고친다

왜 시트에서 끌어오나:
  중요도는 **지어내면 안 된다.** 체크리스트의 Priority 열이 정본이고,
  매핑(`시나리오 [케이스]`)으로 yaml 케이스와 이어진다.

한 케이스가 중요도가 다른 체크리스트 행 **여럿**을 덮으면 **가장 높은 값**을 쓴다
— 덮는 것 중 제일 중요한 것보다 낮을 수 없다.

⚠️ 파일마다 줄바꿈이 다르다(LF/CRLF 혼재) → **감지한 eol 을 그대로** 쓴다.
   읽고 쓰는 건 전부 바이트다. 텍스트 모드로 쓰면 Windows 가 CRLF 로 바꿔
   파일 전체가 변경으로 잡힌다.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

WEB_RUNNER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_RUNNER_DIR))

import runner                                        # noqa: E402

CACHE = WEB_RUNNER_DIR / "checklist_cache.json"
RANK = {"Low": 1, "Medium": 2, "High": 3}
UNRANK = {v: k for k, v in RANK.items()}


def norm(name: str) -> str:
    n = re.sub(r"^.*[\\/]", "", str(name or ""))
    n = re.sub(r"\.ya?ml$", "", n, flags=re.I)
    n = re.sub(r"_old$", "", n, flags=re.I)
    return n.replace(" ", "").lower()


def sheet_priorities() -> dict:
    """(시나리오, 케이스) → 중요도. 여럿이면 가장 높은 것."""
    rows = json.loads(CACHE.read_text(encoding="utf-8"))["rows"]
    best: dict = {}
    for r in rows:
        pri = (r.get("priority") or "").strip()
        if pri not in RANK:
            continue
        for p in r.get("pairs") or []:
            for c in p["cases"]:
                key = (norm(p["file"]), c)
                if RANK[pri] > RANK.get(best.get(key, ""), 0):
                    best[key] = pri
    return best


def plan() -> tuple[dict, list]:
    """파일별로 (줄 번호 → 넣을 중요도) 와, 근거가 없어 못 채우는 목록."""
    best = sheet_priorities()
    edits: dict = collections.defaultdict(dict)
    missing = []

    for t in runner.list_tests():
        rel = t["file"]
        path = runner.MAESTRO_DIR / rel
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-8", errors="replace")
        eol = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(eol)

        # ★ 같은 케이스가 **머리의 색인 블록과 본문 양쪽**에 적힌 파일이 많다.
        #   색인은 사람용 목차이니 건드리지 않고 **본문(= 마지막에 나오는 줄)만** 고친다.
        parsed_lines = []
        last_for_id: dict = {}
        has_pri: set = set()
        for lineno, line in enumerate(lines):
            parsed = runner._parse_case_line(line)
            if not parsed:
                continue
            ids, pri, text = parsed
            keys = [runner.case_id(i) for i in ids if runner.case_id(i)]
            parsed_lines.append((lineno, keys, pri, text))
            for k in keys:
                last_for_id[k] = lineno
                if pri:
                    has_pri.add(k)

        for lineno, keys, pri, text in parsed_lines:
            if pri:
                continue
            # 이 줄이 **마지막 자리**인 케이스만 책임진다(색인 줄은 여기서 걸러진다)
            own = [k for k in keys if last_for_id.get(k) == lineno and k not in has_pri]
            if not own:
                continue
            found = [best[(norm(t["name"]), k)] for k in own
                     if (norm(t["name"]), k) in best]
            if not found:
                missing.append((t["name"], "/".join(own), text[:46]))
                continue
            edits[rel][lineno] = UNRANK[max(RANK[p] for p in found)]

    return edits, missing


def apply_edits(rel: str, line_edits: dict, dry: bool) -> list:
    """케이스 번호 묶음 **바로 뒤**에 ` [중요도]` 를 끼워 넣는다."""
    path = runner.MAESTRO_DIR / rel
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    shown = []

    for lineno, pri in sorted(line_edits.items()):
        old = lines[lineno]
        # `#` 뒤의 선 문자·공백을 건너뛰고, 대괄호 묶음이 끝나는 자리를 찾는다
        m = runner.COMMENT_HEAD_RE.match(old)
        i = m.end()
        while i < len(old) and old[i] in runner.DIVIDER_CHARS + " \t":
            i += 1
        while i < len(old) and old[i] == "[":
            close = old.find("]", i)
            if close < 0:
                break
            i = close + 1
            j = i
            while j < len(old) and old[j] in " \t":
                j += 1
            if j < len(old) and old[j] == "[":
                i = j                          # 묶음이 이어진다
            else:
                break
        new = old[:i] + " [" + pri + "]" + old[i:]
        lines[lineno] = new
        shown.append((lineno + 1, old.strip(), new.strip()))

    if not dry:
        path.write_bytes(eol.join(lines).encode("utf-8"))
    return shown


def main(argv: list[str]) -> int:
    dry = "--apply" not in argv
    edits, missing = plan()
    total = sum(len(v) for v in edits.values())
    print(("[예행] " if dry else "") + f"중요도를 채울 줄 {total}개 / 파일 {len(edits)}개")
    for rel, line_edits in sorted(edits.items()):
        shown = apply_edits(rel, line_edits, dry)
        print(f"{NL}  {rel}")
        for lineno, old, new in shown:
            print(f"    {lineno:>5}  - {old[:76]}")
            print(f"           + {new[:76]}")
    if missing:
        print(f"{NL}근거가 없어 못 채우는 것 {len(missing)}개 "
              "(시트에 케이스 번호가 없는 행들이다 — 시트를 고치면 풀린다)")
        for name, ids, text in missing:
            print(f"    {name:<34} [{ids}] {text}")
    if dry:
        print(f"{NL}(예행이라 쓰지 않았습니다. --apply 를 붙이면 고칩니다)")
    return 0


NL = chr(10)

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
