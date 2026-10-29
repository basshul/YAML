r"""yaml 케이스 주석의 중요도를 체크리스트 시트 값에 맞춘다.

    python fill_case_priority.py            # 예행 — 빠진 것만
    python fill_case_priority.py --apply    # 빠진 것을 채운다
    python fill_case_priority.py --fix      # 예행 — **틀린 것**까지 본다
    python fill_case_priority.py --fix --apply

어느 모드든 마지막에 **머리말 색인을 본문에 맞춘다**(`sync_index`, 2026-10-29 신설).
색인은 본문에서 끌어낸 사람용 목차라 어긋나 있으면 그냥 틀린 것이다.

★ `--fix` 는 **이미 적혀 있는데 시트와 다른** 값을 고친다(2026-10-28 신설).
  그동안 이 스크립트는 빈 칸만 채웠고, 손으로 적힌 값은 그대로 남았다. 그 결과
  192개 중 **39개가 시트와 어긋나** 있었다 — `09_홈화면` 은 yaml 에 High 16개였지만
  시트 기준은 2개뿐이었다. 어느 케이스를 지워도 되는지 판단할 때 이 값을 보므로,
  틀린 채 두면 **지우면 안 될 것을 지우게 된다.**
  ⚠️ 양방향이다. yaml 이 과대평가한 쪽(High→Medium)이 다수지만
    `21_카드 [05]`(Medium→High)처럼 **올려야 하는 것**도 있다.

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
FIX = "--fix" in sys.argv          # 틀린 값까지 고칠 것인가
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
    fixes: dict = collections.defaultdict(dict)   # --fix: 틀린 값 교정

    for t in runner.list_tests():
        rel = t["file"]
        path = runner.MAESTRO_DIR / rel
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-8", errors="replace")
        real = runner.real_cases(rel)          # 이 파일이 실제로 가진 케이스 id (접미사 포함)
        eol = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(eol)

        # ★ 같은 케이스가 **머리의 색인 블록과 본문 양쪽**에 적힌 파일이 많다.
        #   색인은 사람용 목차이니 건드리지 않고 **본문(= 마지막에 나오는 줄)만** 고친다.
        parsed_lines = []
        last_for_id: dict = {}
        last_pri_for_id: dict = {}
        has_pri: set = set()
        for lineno, line in enumerate(lines):
            parsed = runner._parse_case_line(line)
            if not parsed:
                continue
            ids, pri, text = parsed
            # ★ 키 규칙은 `checklist_sync` 와 같아야 한다 — 접미사를 살릴지는 **yaml 이 정한다**
            #   (`[16a] [High] …` 은 별개 케이스, `[27-1] 지문인증…` 은 `[27]` 의 본문 단계).
            #   그냥 접으면 `[01-2]` 가 `[01]` 의 중요도를 받아 **엉뚱한 값**이 박힌다.
            keys = []
            for i in ids:
                kept = runner.case_id(i, keep_suffix=True)
                k = kept if kept in real else runner.case_id(i)
                if k:
                    keys.append(k)
            parsed_lines.append((lineno, keys, pri, text))
            for k in keys:
                last_for_id[k] = lineno
                if pri:
                    has_pri.add(k)
                    # ★ --fix 는 **중요도가 적힌 줄 중 마지막**을 고친다.
                    #   `last_for_id`(그냥 마지막 줄)로는 안 된다 — 색인·요약 블록이
                    #   본문보다 **뒤**에 있는 파일이 있다(04_01 의 447·465행).
                    #   그러면 본문이 "마지막"이 아니게 되어 조용히 안 고쳐진다.
                    last_pri_for_id[k] = lineno

        for lineno, keys, pri, text in parsed_lines:
            if pri:
                if not FIX:
                    continue
                # 이 줄이 **마지막 자리**인 케이스만 책임진다(색인 줄은 걸러진다)
                own = [k for k in keys if last_pri_for_id.get(k) == lineno]
                found = [best[(norm(t["name"]), k)] for k in own
                         if (norm(t["name"]), k) in best]
                if not found:
                    continue
                want = UNRANK[max(RANK[p] for p in found)]
                if want != pri:
                    fixes[rel][lineno] = (pri, want)
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

    return edits, missing, fixes


def apply_fixes(rel: str, line_fixes: dict, dry: bool) -> list:
    """이미 적힌 `[중요도]` 를 시트 값으로 **갈아 끼운다**.

    ⚠️ 줄 전체를 다시 쓰지 않고 **그 대괄호만** 바꾼다 — 제목·ClickUp 표기를 건드리지 않는다.
    """
    path = runner.MAESTRO_DIR / rel
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    shown = []
    for lineno, (cur, want) in sorted(line_fixes.items()):
        old = lines[lineno]
        new = old.replace("[" + cur + "]", "[" + want + "]", 1)
        assert new != old, (rel, lineno, old)
        lines[lineno] = new
        shown.append((lineno + 1, old.strip(), new.strip()))
    if not dry:
        path.write_bytes(eol.join(lines).encode("utf-8"))
    return shown


PRI_TOKEN = re.compile(r"\[(High|Medium|Low)\]")


def sync_index(dry: bool) -> dict:
    r"""머리말 **색인**의 중요도를 **본문**에 맞춘다.

    같은 케이스가 머리의 색인 블록과 본문 양쪽에 적힌 파일이 많다. 위의 `--fix` 는
    본문(= 중요도가 적힌 마지막 줄)만 고치므로 **색인은 낡은 채 남는다.**
    2026-10-29 에 그 상태가 실제로 사고를 냈다 — `runner.read_cases` 가 색인을 읽고
    있어서 화면의 High 필터가 시나리오 4개를 잘못 끌어들였다(파서는 그때 고쳤다).
    파서를 고쳐도 **사람이 파일을 열면 여전히 틀린 목차**를 보므로 여기서 같이 맞춘다.

    ⚠️ 방향은 늘 **본문 → 색인**이다. 색인은 사람용 목차일 뿐 파생물이고,
      시트와 대조해 고친 것은 본문이기 때문이다.
    ⚠️ 바꾸는 건 **색인 줄의 대괄호 하나**다. 토큰 길이가 달라져 제목 열이 틀어지므로
      바뀐 줄이 속한 색인 블록만 다시 정렬한다(여기까지 전부 주석 전용 변경이다).
    ⚠️ `--fix` 전용이 아니라 **늘 돈다.** 색인은 본문에서 끌어낸 값이라 어긋나 있으면
      그냥 틀린 것이고, 남겨 둘 이유가 없다.
    """
    out: dict[str, list] = {}
    for path in sorted((runner.MAESTRO_DIR / "Old").glob("*.yaml")):
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        eol = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(eol)

        # 각 케이스 id 의 **중요도가 적힌 마지막 줄** = 본문 (runner.read_cases 와 같은 규칙)
        parsed, last_pri_line, body = [], {}, {}
        for i, line in enumerate(lines):
            got = runner._parse_case_line(line)
            if not got:
                continue
            ids, pri, _ = got
            parsed.append((i, ids, pri))
            if pri:
                for raw_id in ids:
                    last_pri_line[raw_id] = i
                    body[raw_id] = pri

        fixes = []
        for i, ids, pri in parsed:
            if not pri:
                continue
            # 이 줄이 **마지막 자리가 아닌** = 색인 줄인 id 들이 뭐라고 하는지 본다
            want = {body[r] for r in ids if last_pri_line.get(r) != i and r in body}
            # ⚠️ 한 색인 줄이 여러 케이스를 묶어 적었는데 그 본문들의 중요도가 **서로 다르면**
            #   어느 값으로 고쳐야 할지 알 수 없다 → 건드리지 않고 넘어간다.
            if len(want) == 1 and want != {pri}:
                fixes.append((i, pri, want.pop()))
        if not fixes:
            continue

        shown, touched = [], set()
        for i, cur, want in fixes:
            old = lines[i]
            lines[i] = PRI_TOKEN.sub("[" + want + "]", old, count=1)
            touched.add(i)
            shown.append((i + 1, old.strip(), lines[i].strip()))

        # 바뀐 줄이 속한 **연속 색인 블록**의 제목 열을 다시 맞춘다
        blocks: list[list[int]] = []
        for i in sorted(touched):
            a = b = i
            while a - 1 >= 0 and runner._parse_case_line(lines[a - 1]):
                a -= 1
            while b + 1 < len(lines) and runner._parse_case_line(lines[b + 1]):
                b += 1
            if blocks and blocks[-1][1] >= a:
                blocks[-1][1] = max(blocks[-1][1], b)
            else:
                blocks.append([a, b])
        for a, b in blocks:
            parts = []
            for i in range(a, b + 1):
                m = PRI_TOKEN.search(lines[i])
                parts.append((i, lines[i][:m.end()], lines[i][m.end():].lstrip()) if m else None)
            width = max((len(h) for x in parts if x for _, h, _ in [x]), default=0)
            for x in parts:
                if not x:
                    continue
                i, head, tail = x
                lines[i] = head + " " * (width - len(head) + 1) + tail

        if not dry:
            path.write_bytes(eol.join(lines).encode("utf-8"))
        out[path.name] = shown
    return out


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
    edits, missing, fixes = plan()
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
    if FIX:
        n = sum(len(v) for v in fixes.values())
        print(f"{NL}{'[예행] ' if dry else ''}시트와 **다른** 중요도 {n}개 / 파일 {len(fixes)}개")
        for rel, line_fixes in sorted(fixes.items()):
            shown = apply_fixes(rel, line_fixes, dry)
            print(f"{NL}  {rel}")
            for lineno, old, new in shown:
                print(f"    {lineno:>5}  - {old[:76]}")
                print(f"           + {new[:76]}")
    # ★ 색인 맞추기는 **맨 뒤**다 — 위에서 본문을 고쳤으면 그 결과를 다시 읽어야 한다.
    #   파일을 새로 읽으므로 위 단계가 쓴 값이 그대로 반영된다(예행이면 옛 값 기준).
    idx = sync_index(dry)
    n = sum(len(v) for v in idx.values())
    print(f"{NL}{'[예행] ' if dry else ''}본문과 **다른 머리말 색인** {n}개 / 파일 {len(idx)}개")
    for rel, shown in sorted(idx.items()):
        print(f"{NL}  {rel}")
        for lineno, old, new in shown:
            print(f"    {lineno:>5}  - {old[:76]}")
            print(f"           + {new[:76]}")
    if dry:
        print(f"{NL}(예행이라 쓰지 않았습니다. --apply 를 붙이면 고칩니다)")
    return 0


NL = chr(10)

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
