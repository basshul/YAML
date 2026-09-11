# write_bb.py — 체크리스트 결과 열에 값만 기입한다(zip 파트 교체 방식).
#
# ⚠️ Excel COM을 쓰지 않는다. 동기화 폴더의 통합문서를 Excel로 열면 ReadOnly로 잡혀
#    Save()가 조용히 무시되기 때문이다. 대신 xlsx(zip)의 해당 시트 XML만 바꾸고
#    **나머지 파트는 원본 바이트 그대로 복사**한다(조건부서식·vmlDrawing·스레드댓글 보존).
# ⚠️ 셀 스타일(s=)은 기존 값을 그대로 유지한다. 값은 마스터 기존 기입과 동일하게 inlineStr로 쓴다.
# ⚠️ 행/열을 추가하지 않는다. 대상 행이 시트에 없으면 건너뛰고 보고한다.
#
# 사용법: python write_bb.py <xlsx> <sheet_part> <col> <json: {"39":"Pass", ...}>
import sys, json, re, zipfile, shutil, os, datetime

book, part, col, payload = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
bak = f"{book}.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}"
shutil.copy2(book, bak)

zin = zipfile.ZipFile(book)
xml = zin.read(part).decode('utf-8')

written, missing = [], []
for row, val in payload.items():
    cref = f"{col}{row}"
    # 기존 셀(자체닫힘 포함)을 찾아 스타일을 유지한 채 교체
    m = re.search(r'<c r="%s"((?:(?!/>|>).)*)(/>|>.*?</c>)' % cref, xml, re.S)
    if m:
        style = re.search(r'\ss="(\d+)"', m.group(1))
        s = f' s="{style.group(1)}"' if style else ''
        xml = xml[:m.start()] + f'<c r="{cref}"{s} t="inlineStr"><is><t>{val}</t></is></c>' + xml[m.end():]
        written.append(cref); continue
    # 셀이 없으면 같은 행 안에서 열 순서에 맞춰 삽입
    rm = re.search(r'<row r="%s"[^>]*>(.*?)</row>' % row, xml, re.S)
    if not rm:
        missing.append(cref); continue
    body = rm.group(1)
    def key(ref):
        c = re.match(r'([A-Z]+)', ref).group(1)
        return (len(c), c)
    pos = len(body)
    for cm in re.finditer(r'<c r="([A-Z]+\d+)"', body):
        if key(cm.group(1)) > key(cref):
            pos = cm.start(); break
    new = body[:pos] + f'<c r="{cref}" t="inlineStr"><is><t>{val}</t></is></c>' + body[pos:]
    xml = xml[:rm.start(1)] + new + xml[rm.end(1):]
    written.append(cref)

tmp = book + '.tmp'
with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        zout.writestr(item, xml.encode('utf-8') if item.filename == part else zin.read(item.filename))
zin.close()
os.replace(tmp, book)
print(f"기입 {len(written)}: {' '.join(written)}")
if missing: print("행 없음:", ' '.join(missing))
