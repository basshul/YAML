# -*- coding: utf-8 -*-
"""자동화 실행 결과를 체크리스트에 기입한다.

행을 '행 번호' 가 아니라 'ID' 로, 열을 '열 문자' 가 아니라 '머리글 문구' 로 찾는다.
그래서 행을 넣고 빼거나 열 순서를 바꿔도 스크립트를 고칠 필요가 없다.

하는 일 두 가지
  1) 자동화결과 시트 맨 아래에 실행 기록을 한 줄씩 덧붙인다 (이력이 남는다)
  2) Checklist 시트의 해당 릴리스·플랫폼 결과 칸에 값을 찍는다 (한눈에 보인다)

저장 방식: xlsx(zip) 안에서 건드리는 시트 XML 만 교체하고 나머지 파트는
원본 바이트 그대로 복사한다. 조건부서식·메모·스레드댓글·차트가 보존된다.
(openpyxl 로 통째로 저장하면 스레드댓글 등이 사라진다.)

사용법
  python write_result.py <xlsx> --release "<릴리스>" --platform Android \
      --env "Livetest New app" --build 7.21.0-stag --device SM-S928N \
      --results results.json [--sheet "Checklist(Basshu)"] [--dry-run]

results.json:  {"REG-001": "Pass", "REG-002": {"result": "Fail", "note": "..."}}
"""
import argparse, datetime, io, json, os, re, shutil, sys, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

LOG_SHEET = "자동화결과"
LOG_COLS = ["실행일시", "릴리스", "환경", "플랫폼", "빌드", "기기", "ID", "결과", "yaml 파일", "비고"]


# ── xlsx 내부 구조 읽기 ─────────────────────────────────────
def sheet_parts(z):
    """시트 이름 -> zip 안의 XML 경로"""
    wbx = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    tgt = {}
    for rel in re.findall(r"<Relationship\b[^>]*/?>", rels):
        i = re.search(r'\bId="([^"]+)"', rel)
        t = re.search(r'\bTarget="([^"]+)"', rel)
        if i and t:
            tgt[i.group(1)] = t.group(1)
    out = {}
    for sm in re.findall(r"<sheet\b[^>]*/?>", wbx):
        nm = re.search(r'\bname="([^"]+)"', sm)
        rid = re.search(r'\br:id="([^"]+)"', sm)
        if not (nm and rid and rid.group(1) in tgt):
            continue
        t = tgt[rid.group(1)]
        out[unescape(nm.group(1))] = t.lstrip("/") if t.startswith("/") else "xl/" + t
    return out


def shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    x = z.read("xl/sharedStrings.xml").decode("utf-8")
    out = []
    for si in re.findall(r"<si>(.*?)</si>", x, re.S):
        out.append(unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))
    return out


def unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&apos;", "'").replace("&#10;", "\n").replace("&amp;", "&"))


def escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("\n", "&#10;"))


def cell_text(c, sst):
    """<c ...>...</c> 한 개의 표시 문자열"""
    t = re.search(r'\st="([^"]+)"', c)
    t = t.group(1) if t else "n"
    if t == "s":
        v = re.search(r"<v>(\d+)</v>", c)
        return sst[int(v.group(1))] if v else ""
    if t == "inlineStr":
        return unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", c, re.S)))
    v = re.search(r"<v>(.*?)</v>", c, re.S)
    return unescape(v.group(1)) if v else ""


def read_grid(xml, sst):
    """{행번호: {열문자: 문자열}}"""
    grid = {}
    for rm in re.finditer(r'<row[^>]*\sr="(\d+)"[^>]*>(.*?)</row>', xml, re.S):
        r = int(rm.group(1))
        cells = {}
        for cm in re.finditer(r'<c\s[^>]*r="([A-Z]+)\d+"[^>]*(?:/>|>.*?</c>)', rm.group(2), re.S):
            cells[cm.group(1)] = cell_text(cm.group(0), sst)
        grid[r] = cells
    return grid


def colnum(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def colname(n):
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


# ── 셀 쓰기 (스타일 유지) ────────────────────────────────────
def set_cell(xml, ref, value):
    m = re.search(r'<c\s[^>]*r="%s"((?:(?!/>|>).)*)(/>|>.*?</c>)' % ref, xml, re.S)
    new = '<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
    if m:
        st = re.search(r'\ss="(\d+)"', m.group(1))
        st = ' s="%s"' % st.group(1) if st else ""
        return xml[:m.start()] + new % (ref, st, escape(value)) + xml[m.end():]
    col, row = re.match(r"([A-Z]+)(\d+)", ref).groups()
    rm = re.search(r'<row[^>]*\sr="%s"[^>]*>(.*?)</row>' % row, xml, re.S)
    if not rm:
        raise KeyError("행 %s 없음" % row)
    body, pos = rm.group(1), len(rm.group(1))
    for cm in re.finditer(r'<c\s[^>]*r="([A-Z]+)\d+"', body):
        if colnum(cm.group(1)) > colnum(col):
            pos = cm.start()
            break
    return xml[:rm.start(1)] + body[:pos] + new % (ref, "", escape(value)) + body[pos:] + xml[rm.end(1):]


def append_rows(xml, rows_values, first_row):
    """[[v1, v2, ...], ...] 를 sheetData 끝에 덧붙인다"""
    chunks = []
    for i, vals in enumerate(rows_values):
        r = first_row + i
        cs = "".join('<c r="%s%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                     % (colname(j + 1), r, escape(v)) for j, v in enumerate(vals) if v != "")
        chunks.append('<row r="%d">%s</row>' % (r, cs))
    add = "".join(chunks)
    if "</sheetData>" in xml:
        xml = xml.replace("</sheetData>", add + "</sheetData>", 1)
    else:
        xml = xml.replace("<sheetData/>", "<sheetData>" + add + "</sheetData>", 1)
    last = first_row + len(rows_values) - 1
    xml = re.sub(r'(<dimension ref="[A-Z]+\d+:[A-Z]+)(\d+)(")',
                 lambda m: m.group(1) + str(max(int(m.group(2)), last)) + m.group(3), xml, count=1)
    return xml


# ── 본체 ────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("xlsx")
    p.add_argument("--sheet", default="Checklist(Basshu)")
    p.add_argument("--release", required=True)
    p.add_argument("--platform", required=True, choices=["iOS", "Android"])
    p.add_argument("--env", required=True)
    p.add_argument("--build", default="")
    p.add_argument("--device", default="")
    p.add_argument("--results", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    raw = json.load(open(a.results, encoding="utf-8"))
    results = {k: (v if isinstance(v, dict) else {"result": v}) for k, v in raw.items()}

    z = zipfile.ZipFile(a.xlsx)
    sst = shared_strings(z)
    parts = sheet_parts(z)
    for need in (a.sheet, LOG_SHEET):
        if need not in parts:
            sys.exit("시트를 찾을 수 없습니다: %s (있는 시트: %s)" % (need, ", ".join(parts)))

    cx = z.read(parts[a.sheet]).decode("utf-8")
    grid = read_grid(cx, sst)

    # 머리글 -> 열문자
    hdr = {v.strip(): k for k, v in grid.get(1, {}).items() if v.strip()}
    want = "%s | %s" % (a.release, a.platform)
    if want not in hdr:
        sys.exit("결과 열을 찾을 수 없습니다: %r\n1행 머리글: %s"
                 % (want, ", ".join(sorted(hdr))))
    rescol = hdr[want]
    idcol = hdr.get("ID")
    yamlcol = hdr.get("yaml 파일")
    if not idcol:
        sys.exit("ID 열이 없습니다. 이 시트는 ID 기반 기입을 쓸 수 없습니다.")

    # ID -> 행
    id2row, dups = {}, []
    for r, cells in grid.items():
        if r == 1:
            continue
        v = (cells.get(idcol) or "").strip()
        if not v:
            continue
        if v in id2row:
            dups.append(v)
        id2row[v] = r
    if dups:
        sys.exit("ID 가 중복입니다: %s" % ", ".join(sorted(set(dups))))

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hit, miss, log = [], [], []
    for tid in sorted(results):
        if tid not in id2row:
            miss.append(tid)
            continue
        row = id2row[tid]
        info = results[tid]
        y = info.get("yaml") or re.sub(r"^\(제안\)\s*", "", grid[row].get(yamlcol, "") if yamlcol else "")
        cx = set_cell(cx, "%s%d" % (rescol, row), info["result"])
        hit.append((tid, row, info["result"]))
        log.append([stamp, a.release, a.env, a.platform, a.build, a.device,
                    tid, info["result"], y, info.get("note", "")])

    lx = z.read(parts[LOG_SHEET]).decode("utf-8")
    lgrid = read_grid(lx, sst)
    lhdr = {v.strip(): k for k, v in lgrid.get(1, {}).items() if v.strip()}
    for c in LOG_COLS:
        if c not in lhdr:
            sys.exit("자동화결과 시트에 '%s' 열이 없습니다." % c)
    order = [lhdr[c] for c in LOG_COLS]
    if order != [colname(i + 1) for i in range(len(LOG_COLS))]:
        sys.exit("자동화결과 열 순서가 예상과 다릅니다: %s" % order)
    nextrow = max([r for r in lgrid if any(v.strip() for v in lgrid[r].values())] or [1]) + 1
    lx = append_rows(lx, log, nextrow)

    print("기입 %d건 / 이력 %d줄 (자동화결과 %d행부터)" % (len(hit), len(log), nextrow))
    for tid, row, res in hit[:8]:
        print("   %-9s -> %s%-4d  %s" % (tid, rescol, row, res))
    if len(hit) > 8:
        print("   ... 외 %d건" % (len(hit) - 8))
    if miss:
        print("⚠ 시트에 없는 ID %d개: %s" % (len(miss), ", ".join(miss[:10])))
    if a.dry_run:
        print("(dry-run — 저장하지 않음)")
        return

    bak = "%s.bak_%s" % (a.xlsx, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(a.xlsx, bak)
    tmp = a.xlsx + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for it in z.infolist():
            if it.filename == parts[a.sheet]:
                zo.writestr(it, cx.encode("utf-8"))
            elif it.filename == parts[LOG_SHEET]:
                zo.writestr(it, lx.encode("utf-8"))
            else:
                zo.writestr(it, z.read(it.filename))
    z.close()
    os.replace(tmp, a.xlsx)
    print("저장 완료 (백업: %s)" % os.path.basename(bak))


if __name__ == "__main__":
    main()
