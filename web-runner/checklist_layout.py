r"""체크리스트 시트의 **열 배치를 머리글로 알아낸다.**

왜 위치를 박지 않나:
  종전엔 `B10:L600` 을 읽고 `COLS` 배열로 이름을 붙였다 — **위치 고정**이다.
  신규 문서(V2.2)는 앞에 `No`·`Case ID` 두 열이 생겨 전체가 두 칸 밀렸다.
  위치를 박아 두면 그 순간 **모든 열이 조용히 어긋난다**(Priority 자리에 1Depth 가 들어온다).
  → 머리글 글자로 찾으면 열이 늘든 줄든 따라간다.

두 판본을 **같은 코드로** 읽는다:

  V2.1 (현재 쓰는 문서)   머리글 8행 · 데이터 10행~
      B Priority · C 1Depth · D 2Depth · E 3Depth · F Checklist
      G 커버 상태 · H YAML 파일 · I YAML 케이스 · J 완료일 · K 커버상태(Old) · L 검토 필요
      → 매핑이 **시트 안에** 있다(H·I).

  V2.2 (신규 문서)        머리글 9행(+10행 2단) · 데이터 11행~
      B No · C Case ID · D Priority · E 1Depth · F 2Depth · G 3Depth · H Checklist
      I~ 버전별 `iOS Result`/`Android Result` 쌍이 계속 늘어난다 · 끝에 Comment
      → **매핑 열이 없다.** 대신 행마다 **고유한 Case ID** 가 있다(406행 전부, 중복 0).
        매핑은 저장소의 `checklist_mapping.json` 에 Case ID 로 둔다.

★ Case ID 가 생긴 것이 큰 이득이다. 종전엔 결과 기입을 **엑셀 행 번호**로 해야 해서,
  시트 중간에 행이 끼면 엉뚱한 행에 쓸 위험이 있었다. 고유 키가 있으면 그게 사라진다.
"""

from __future__ import annotations

import re

# 머리글 → 우리가 쓰는 이름. 공백·줄바꿈·대소문자를 무시하고 맞춘다.
HEADER_ALIASES = {
    "priority": "priority",
    "caseid": "case_id",
    "no": "no",
    "1depth": "d1",
    "2depth": "d2",
    "3depth": "d3",
    "checklist": "text",
    "커버상태": "cover",
    "yaml파일": "yaml_file",
    "yaml케이스": "yaml_case",
    "완료일": "done_date",
    "커버상태old": "cover_old",
    "검토필요": "review",
    "comment": "comment",
}


# 결과 열은 머리글 **아랫단**에 있다(9행 날짜·버전 / 10행 iOS·Android).
#   윗단 별칭과 섞으면 `text` 가 있는 행을 고르는 판단이 흐려진다 → 따로 둔다.
RESULT_ALIASES = {
    "iosresult": "ios",
    "androidresult": "android",
}


def _norm(s: str) -> str:
    return re.sub(r"[\s​()]+", "", str(s or "")).lower()


def col_letter(idx0: int) -> str:
    """0-based 열 번호 → 엑셀 문자(0→A)."""
    s, i = "", idx0 + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class Layout:
    """어느 열이 무엇인지. `idx[이름] = 0-based 열 번호`(시트 전체 기준)."""

    def __init__(self, sheet: str, header_row: int, first_row: int, idx: dict[str, int],
                 result_idx: dict[str, int] | None = None):
        self.sheet = sheet
        self.header_row = header_row
        self.first_row = first_row
        self.idx = idx
        # {"ios": 0-based 열, "android": …}. 2단 머리글이 아니면 비어 있다.
        self.result_idx = result_idx or {}

    def result_col(self, platform: str) -> str:
        """결과를 적을 열 문자. 못 찾으면 사유를 그대로 올린다 —
        ⛔ 열 문자를 **지어내지 않는다**(docs/CHECKLIST.md §9 가 막아 둔 사고다)."""
        i = self.result_idx.get((platform or "").strip().lower())
        if i is None:
            have = ", ".join(sorted(self.result_idx)) or "없음"
            raise RuntimeError(
                f"{self.sheet} 에서 '{platform}' 결과 열을 찾지 못했습니다(찾은 것: {have}). "
                "머리글 아랫단에 `iOS Result` · `Android Result` 가 있어야 합니다.")
        return col_letter(i)

    @property
    def has_sheet_mapping(self) -> bool:
        """매핑(yaml 파일·케이스)이 **시트 안에** 있는가. 없으면 저장소 파일에서 읽는다."""
        return "yaml_file" in self.idx and "yaml_case" in self.idx

    @property
    def has_case_id(self) -> bool:
        return "case_id" in self.idx

    def last_col(self) -> int:
        return max(self.idx.values())

    def range(self, last_row: int = 600) -> str:
        """데이터 범위. 필요한 열까지만 읽는다(버전 Result 열이 50개가 넘는다)."""
        return f"A{self.first_row}:{col_letter(self.last_col())}{last_row}"

    def get(self, raw: list, name: str) -> str:
        i = self.idx.get(name)
        if i is None or i >= len(raw) or raw[i] is None:
            return ""
        return str(raw[i]).strip()

    def describe(self) -> str:
        order = sorted(self.idx.items(), key=lambda kv: kv[1])
        cols = " · ".join(f"{col_letter(i)}={n}" for n, i in order)
        return (f"{self.sheet} — 머리글 {self.header_row}행 / 데이터 {self.first_row}행~\n"
                f"    {cols}\n"
                f"    매핑 위치: {'시트(H·I)' if self.has_sheet_mapping else '저장소 파일(Case ID 기준)'}\n"
                f"    결과 열: " + (" · ".join(
                    f"{col_letter(i)}={n}" for n, i in sorted(self.result_idx.items(),
                                                              key=lambda kv: kv[1])) or "못 찾음"))


def detect(fetch_range) -> Layout:
    """머리글 후보 행을 훑어 열 배치를 알아낸다.

    `fetch_range(a1)` 은 그 범위의 2차원 값을 돌려주는 함수다(호출자가 준다 —
    이 모듈이 Graph 에 직접 붙지 않게 해서 테스트가 쉬워진다).

    ⚠️ 머리글이 **2단**인 판본이 있다(9행 날짜 / 10행 iOS·Android). 우리가 쓰는 열은
       전부 윗단에 있으므로 윗단만 본다. 아래 단은 결과 기입 때 따로 다룬다.
    """
    rows = fetch_range("A7:BZ12")
    best = None
    for off, raw in enumerate(rows):
        hit = {}
        for i, cell in enumerate(raw):
            key = HEADER_ALIASES.get(_norm(cell))
            if key and key not in hit:
                hit[key] = i
        # 'Checklist'(확인 문구) 가 없으면 머리글 행이 아니다 — 가장 확실한 표지다
        if "text" in hit and (best is None or len(hit) > len(best[1])):
            best = (7 + off, hit)
    if not best:
        raise RuntimeError("머리글 행을 찾지 못했습니다 — 시트 구조가 예상과 다릅니다.")
    header_row, idx = best
    # 데이터는 머리글 **다음 행부터**. 2단 머리글이면 한 줄 더 건너뛴다.
    nxt = rows[header_row - 7 + 1] if header_row - 7 + 1 < len(rows) else []
    result_idx = {}
    for i, cell in enumerate(nxt):
        key = RESULT_ALIASES.get(_norm(cell))
        if key and key not in result_idx:
            result_idx[key] = i
    two_tier = bool(result_idx)
    return Layout("", header_row, header_row + (2 if two_tier else 1), idx, result_idx)
