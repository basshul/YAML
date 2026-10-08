"use strict";

/* v5 화면. 왼쪽 = 실행 조작, 오른쪽 = 체크리스트 표.
 *
 * ⚠️ 체크리스트 데이터(413행·결과·매핑·이력)는 아직 뒷단이 없다
 *    (docs/CHECKLIST.md 단계 0·1). 그래서 지금 표는 **시나리오 선택**만 한다 —
 *    /api/tests 의 39개를 시나리오 머리줄로 그린다.
 *    체크리스트에 기대는 조작(결과 필터·매핑 모드·엑셀 저장·상세 패널)은
 *    markOffline() 이 한곳에서 꺼 둔다. /api/checklist 가 생기면 그 호출만 지우면 된다.
 */

const state = {
  config: null,
  tests: [],
  selected: new Set(),
  server: "livetest",
  running: false,
  groupFilter: "all",
  expanded: new Set(),
  preflight: null,
  checklist: null,
  priFilter: "all",
  onlyBadMap: false,
  runUser: "",
};

const $ = (s) => document.getElementById(s);
const esc = (t) =>
  String(t == null ? "" : t).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------------------------------------------------------------- 불러오기 */

async function api(path) {
  const res = await fetch(path);
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || path + " 실패");
  return data;
}

async function boot() {
  initRunUser();
  markAdminReady();
  markOffline();
  try {
    state.config = await api("/api/config");
    state.server = state.config.servers[0].value;
    renderServers();

    const { tests } = await api("/api/tests");
    state.tests = tests;
    renderAreaFilter();
    renderTable();

    await loadDevices();
    await loadChecklist();
    $("connState").textContent = "서버 연결됨";
  } catch (err) {
    $("connState").textContent = "연결 실패: " + err.message;
    $("connState").classList.add("bad");
    $("tbody").innerHTML =
      '<tr><td colspan="7" class="muted">목록을 불러오지 못했습니다: ' + esc(err.message) + "</td></tr>";
  }
  attachIfRunning();
}

/* 실행자 선택. **브라우저에 기억한다** — 새로고침마다 다시 고르게 하면 금세 안 쓴다.
   ⚠️ localStorage 는 사생활 보호 창·저장 차단에서 **예외를 던진다** → 읽기·쓰기 모두 감싼다.
      기억이 없으면 그냥 첫 항목으로 둔다(없는 사람을 지어내지 않는다). */
const RUN_USER_KEY = "webrunner.runUser";

function initRunUser() {
  const sel = $("runUser");
  if (!sel) return;
  let saved = null;
  try { saved = localStorage.getItem(RUN_USER_KEY); } catch (e) { /* 막혀 있으면 기본값 */ }
  // ★ **첫 항목을 자동으로 고르지 않는다.** 기억해 둔 값이 있을 때만 되살린다 —
  //   고르지 않은 사람이 남의 계정으로 돌리는 것을 막는 것이 이 선택의 목적이다.
  const known = [...sel.options].map((o) => o.value).filter(Boolean);
  sel.value = known.includes(saved) ? saved : "";
  state.runUser = sel.value;
  sel.addEventListener("change", () => {
    state.runUser = sel.value;
    try { localStorage.setItem(RUN_USER_KEY, sel.value); } catch (e) { /* 저장만 안 될 뿐 */ }
    updateRunState();
    markAdminReady();
  });
}

/* 아직 데이터가 없어 못 쓰는 조작을 한곳에서 끈다.
   체크리스트가 붙으면 쓸 수 있게 된 것부터 하나씩 켠다. */
function markOffline() {
  const connected = clConnected();
  const NOTE = connected
    ? "결과 데이터가 아직 없습니다 — 실행 결과를 연결하면 열립니다."
    : "체크리스트 데이터가 아직 연결되지 않았습니다.";

  // 중요도는 체크리스트가 붙으면 바로 쓸 수 있다(시트의 Priority).
  // 결과·이번 실행·결과 보기·엑셀은 **실행 결과**가 있어야 하므로 아직 꺼 둔다.
  const always = ["f-run", "f-res", "basis", "mapmode", "btn-save", "btn-reload"];
  for (const id of always) {
    const el = $(id);
    if (!el) continue;
    el.disabled = true;
    el.title = NOTE;
  }
  const pri = $("f-pri");
  if (pri) {
    pri.disabled = !connected;
    pri.title = connected ? "" : NOTE;
  }

  renderMapWarn();

  const info = connected
    ? "체크리스트 " + state.checklist.data.summary.rows + "행 · 받아온 시각 " +
      esc(state.checklist.data.fetched_at)
    : NOTE;
  $("sv-pend").innerHTML = '<span class="muted">' + info + "</span>";
  $("sv-mine").innerHTML = '<span class="muted">결과 기입은 실행 결과가 붙은 뒤에 열립니다.</span>';

  const sub = document.querySelector(".col-right h2 .muted");
  if (sub) {
    sub.textContent = connected
      ? "시나리오별로 펼치면 체크리스트 확인 항목이 보입니다"
      : "체크리스트는 아직 연결 전 — 지금은 실행할 시나리오만 고릅니다";
  }
}

/* 매핑 오류 경고(상단 전폭). **오류가 있을 때만** 보인다 — 늘 떠 있으면 경고가 아니다.
   ⚠️ 경고가 사라질 때 `오류만 보기` 가 켜진 채로 남으면 **빈 표**가 되고 끌 수단도
      함께 사라진다 → 숨길 때 반드시 토글도 같이 끈다. */
/* admin 점검도 사용자를 고른 뒤에만 — 점검 대상 계정이 사람마다 다르다. */
function markAdminReady() {
  const b = $("btn-pf");
  if (!b) return;
  b.disabled = !state.runUser;
  b.title = state.runUser ? "" : "먼저 사용자를 선택하세요.";
}

function renderMapWarn() {
  const bar = $("mapwarn");
  if (!bar) return;
  const n = clConnected() ? countMapErrors() : 0;
  if (!n) {
    bar.hidden = true;
    if (state.onlyBadMap) {
      state.onlyBadMap = false;
      const b = $("btn-mapwarn-only");
      if (b) b.setAttribute("aria-pressed", "false");
    }
    return;
  }
  bar.hidden = false;
  $("mapwarn-n").textContent = String(n);
}

function countMapErrors() {
  let n = 0;
  for (const rows of state.checklist.byFile.values()) {
    n += rows.filter((r) => r.mapError).length;
  }
  return n;
}

async function loadDevices() {
  const sel = $("dev");
  sel.innerHTML = "";
  try {
    const { devices } = await api("/api/devices");
    if (devices.length === 0) sel.appendChild(new Option("연결된 기기 없음", ""));
    for (const d of devices) {
      const label = d.ready
        ? (d.model || d.serial) + " (" + d.serial + ")"
        : d.serial + " — " + d.state + " (사용 불가)";
      const opt = new Option(label, d.serial);
      opt.disabled = !d.ready;
      sel.appendChild(opt);
    }
    const preferred = state.config && state.config.default_device;
    if (preferred && devices.some((d) => d.serial === preferred && d.ready)) sel.value = preferred;
  } catch (err) {
    sel.appendChild(new Option("기기 목록 실패: " + err.message, ""));
  }
  updateRunState();
}

function renderServers() {
  const box = $("serverChoices");
  box.innerHTML = "";
  for (const s of state.config.servers) {
    const label = document.createElement("label");
    label.className = "choice" + (s.live ? " live" : "");
    label.innerHTML =
      '<input type="radio" name="srv" value="' + esc(s.value) + '"' +
      (s.value === state.server ? " checked" : "") + "> " + esc(s.label);
    label.querySelector("input").addEventListener("change", () => {
      state.server = s.value;
      $("liveWarn").classList.toggle("hidden", !s.live);
    });
    box.appendChild(label);
  }
}

/* ------------------------------------------------------------ 체크리스트 표 */

/* 체크리스트 — 캐시가 없으면 화면은 시나리오 선택만 하던 때로 돌아간다(죽지 않는다). */
async function loadChecklist() {
  try {
    const data = await api("/api/checklist");
    indexChecklist(data);
  } catch (err) {
    state.checklist = { error: err.message, byFile: new Map(), orphan: [] };
  }
  markOffline();
  renderTable();
}

/* 행을 시나리오별로 묶고, 매핑이 실제 케이스를 가리키는지 그 자리에서 검증한다.
   ★ 검증 기준은 /api/tests 의 케이스 목록이다 — 시트가 혼자 맞다고 할 수 없다. */
function normFile(name) {
  // 시트는 'Old\13_01_Rate_Indonesia_old.yaml' 처럼 **파일명**으로 적기도 하고
  // '02_01_Overseas_Send now' 처럼 **띄어쓰기·대소문자**가 다르기도 하다.
  // 경로·확장자·_old 를 떼고, 공백을 없애고, 소문자로 맞춘다 — 여기까지는 안전하다.
  return String(name || "")
    .replace(/^.*[\\/]/, "")
    .replace(/\.ya?ml$/i, "")
    .replace(/_old$/i, "")
    .replace(/\s+/g, "")
    .toLowerCase()
    .trim();
}

/* 그래도 안 맞으면 **접두사가 유일하게 일치할 때만** 붙인다.
   시트 '14_01_Deposit_seungsoo818' ↔ 스위트 '14_01_Deposit' 같은 경우다.
   ★ 후보가 둘 이상이면 붙이지 않는다 — 잘못 붙은 매핑은 커버리지를 통째로 속인다. */
function matchScenario(key, byName) {
  const exact = byName.get(key);
  if (exact) return { test: exact, how: "exact" };
  const cands = [...byName.entries()].filter(([k]) => k.length > 3 && key.startsWith(k));
  if (cands.length === 1) return { test: cands[0][1], how: "prefix" };
  return { test: null, how: cands.length > 1 ? "ambiguous" : "none" };
}

function indexChecklist(data) {
  const byName = new Map(state.tests.map((t) => [normFile(t.name), t]));
  const byFile = new Map();
  const orphan = [];

  for (const row of data.rows || []) {
    // ★ 한 행이 **파일 여럿**을 덮을 수 있다(13_01·13_02·13_03 를 한 셀에 적은 행).
    //   짝마다 따로 붙여야 각 시나리오에서 보인다.
    const pairs = (row.pairs && row.pairs.length)
      ? row.pairs
      : [{ file: row.yaml_file, cases: row.cases || [] }];

    for (const pair of pairs) {
      const r = Object.assign({}, row, {
        cases: pair.cases || [],
        pairFile: pair.file,
      });
      r.mapError = null;
      r.notInSuite = false;

      if (!pair.file) {
        orphan.push(r);
        continue;
      }
      const key = normFile(pair.file);
      const m = matchScenario(key, byName);
      const t = m.test;
      r.matchedBy = m.how;
      r.mapKey = key;
      r.maps = r.cases.map((c) => key + " [" + c + "]");

      if (!t) {
        // 매핑이 틀린 게 아니다 — G9 처럼 **스위트 목록에서 빠진** 시나리오다.
        r.notInSuite = true;
      } else if (!r.cases.length) {
        r.mapError = "케이스 번호가 적혀 있지 않습니다";
      } else {
        const have = new Set((t.cases || []).map((c) => c.id));
        const missing = r.cases.filter((c) => !have.has(c));
        if (missing.length) {
          r.mapError = key + " 에 케이스 " +
            missing.map((c) => "[" + c + "]").join(", ") + " 가 없습니다";
        }
      }
      const bucket = t ? t.name : "__notinsuite";
      if (!byFile.has(bucket)) byFile.set(bucket, []);
      byFile.get(bucket).push(r);
    }
  }
  for (const rows of byFile.values()) {
    rows.sort((a, b) => (a.cases[0] || "99").localeCompare(b.cases[0] || "99") || a.row - b.row);
  }
  state.checklist = { data: data, byFile: byFile, orphan: orphan,
                      notInSuite: byFile.get("__notinsuite") || [], error: null };
}

function clRowsOf(name) {
  const cl = state.checklist;
  return (cl && !cl.error && cl.byFile.get(name)) || [];
}

function clConnected() {
  return !!(state.checklist && !state.checklist.error && state.checklist.data);
}

function renderAreaFilter() {
  const sel = $("f-area");
  const labels = (state.config && state.config.group_labels) || {};
  const groups = [...new Set(state.tests.map((t) => t.group))].sort();
  sel.innerHTML =
    '<option value="all">전체 (' + state.tests.length + "개 시나리오)</option>" +
    groups.map((g) => {
      const n = state.tests.filter((t) => t.group === g).length;
      return '<option value="' + esc(g) + '">' + esc(g) + " · " +
        esc(labels[g] || "") + " (" + n + ")</option>";
    }).join("");
  // 지금 거르는 기준은 체크리스트의 '영역'이 아니라 스위트의 '그룹'이다
  const field = sel.closest(".f");
  const lab = field && field.querySelector("span");
  if (lab) lab.textContent = "그룹";
  sel.setAttribute("aria-label", "그룹 필터");
}

function priOf(r) { return (r.priority || "").trim(); }

/* 이 시나리오가 그 중요도를 **하나라도** 품고 있는가.
   체크리스트가 붙었으면 시트의 중요도가 정본이고, 덮이지 않은 yaml 케이스도
   화면에 나오므로 **둘 다** 본다 — 한쪽만 보면 gap 행만 남는 시나리오가 사라진다. */
function hasPri(t, pri) {
  const yamlHit = (t.cases || []).some((c) => (c.pri || "").trim() === pri);
  if (!clConnected()) return yamlHit;
  const rows = clRowsOf(t.name);
  if (rows.some((r) => priOf(r) === pri)) return true;
  const covered = new Set();
  for (const r of rows) for (const c of r.cases) covered.add(c);
  return (t.cases || []).some(
    (c) => !covered.has(c.id) && (c.pri || "").trim() === pri);
}

function visibleTests() {
  let list = state.tests.filter(
    (t) => state.groupFilter === "all" || t.group === state.groupFilter);
  // 「오류만 보기」가 켜지면 **오류가 있는 시나리오만** 남긴다.
  //   종전엔 펼친 뒤의 케이스 행만 걸러서, 접힌 상태로 누르면 아무 변화가 없었다.
  if (state.onlyBadMap && clConnected()) {
    list = list.filter((t) => clRowsOf(t.name).some((r) => r.mapError));
  }
  // 중요도 필터도 **시나리오 단위**로 건다 — 그 중요도가 하나도 없는 시나리오는 감춘다.
  if (state.priFilter !== "all") {
    list = list.filter((t) => hasPri(t, state.priFilter));
  }
  return list;
}

function caseCell(idText, pri, text, mapText, mapErr, coverTag) {
  const map = mapText
    ? '<span class="map' + (mapErr ? " bad" : "") + '"' +
      (mapErr ? ' title="' + esc(mapErr) + '"' : "") + ">" + esc(mapText) + "</span>"
    : '<span class="map none">매핑 안 됨</span>';
  return '<td><span class="id">' + esc(idText) + "</span></td>" +
    "<td>" + esc(pri || "—") + "</td>" +
    '<td><span class="txt">' + esc(text) + "</span></td>" +
    "<td>" + map + (coverTag || "") + "</td>" +
    '<td><span class="v none">—</span></td>' +
    '<td><span class="v none">—</span></td>' +
    '<td><span class="v none">—</span></td>';
}

function coverTagOf(cover) {
  if (!cover || cover === "완전") return "";
  const cls = cover === "자동화 불가능" ? "pend" : "wait";
  return ' <span class="tag ' + cls + '">' + esc(cover) + "</span>";
}

/* 시트가 「완전」이라고 해놓고 매핑 칸이 비어 있는 행이 있다(2026-10-06 실측 15건).
   화면이 그냥 '매핑 안 됨' 으로만 그리면 시트와 어긋나 보인다 → 사유를 적는다. */
function coverMismatch(r) {
  return r.cover === "완전" && !r.yaml_file;
}

function mapCellOf(r) {
  if (r.notInSuite) {
    // 시트에는 매핑이 있다. 단지 **스위트 목록에 없는 시나리오**일 뿐이다.
    const label = r.maps.length ? r.maps.join(", ") : (r.mapKey || r.yaml_file);
    return '<span class="map">' + esc(label) + "</span>" +
           ' <span class="tag wait">스위트에 없음</span>';
  }
  if (!r.yaml_file) {
    return '<span class="map none">매핑 안 됨</span>' +
      (coverMismatch(r)
        ? ' <span class="tag pend" title="시트의 커버 상태는 «완전» 인데 매핑 칸이 비어 있습니다">시트 불일치</span>'
        : "");
  }
  const label = r.maps.length ? r.maps.join(", ") : (r.mapKey || r.yaml_file);
  return '<span class="map' + (r.mapError ? " bad" : "") + '"' +
    (r.mapError ? ' title="' + esc(r.mapError) + '"' : "") + ">" + esc(label) + "</span>";
}

function renderTable() {
  const rows = visibleTests();
  const connected = clConnected();
  let html = "";

  if (!connected) {
    const why = state.checklist && state.checklist.error
      ? "체크리스트를 불러오지 못했습니다: " + esc(state.checklist.error)
      : "체크리스트 행은 아직 연결되지 않았습니다 — 아래 케이스는 <b>플로우 yaml 의 주석</b>에서 읽은 것입니다.";
    html += '<tr><td colspan="7" class="muted" style="padding:10px 12px">' + why + "</td></tr>";
  }

  for (const t of rows) {
    const yamlCases = t.cases || [];
    const clRows = connected ? clRowsOf(t.name) : [];
    // 오류만 보는 중에는 **펼친 채로** 보여 준다 — 무엇이 잘못됐는지가 케이스 행에 있다
    const open = state.onlyBadMap || state.expanded.has(t.name);
    const hasChildren = connected ? (clRows.length || yamlCases.length) : yamlCases.length;

    const pills =
      (t.irreversible ? '<span class="tag man">실결제</span>' : "") +
      (t.needs_balance ? '<span class="tag pend">잔액 ' + t.needs_balance.toLocaleString() + "원</span>" : "") +
      (t.push ? '<span class="tag auto">픽스처</span>' : "");
    const twisty = hasChildren
      ? '<button class="twisty" type="button" data-expand="' + esc(t.name) + '"' +
        ' aria-expanded="' + open + '"' +
        ' aria-label="' + esc(t.name) + (open ? " 케이스 접기" : " 케이스 펼치기") + '">' +
        '<i class="chev"></i></button>'
      : '<span class="twisty empty" aria-hidden="true">·</span>';

    // 머리줄 요약 — 연결되면 '덮인 케이스 / 전체' 가 바로 보인다
    let sum;
    if (connected) {
      const covered = new Set();
      for (const r of clRows) for (const c of r.cases) covered.add(c);
      const bad = clRows.filter((r) => r.mapError).length;
      sum = "체크리스트 " + clRows.length + "행 · 케이스 " + covered.size + "/" + yamlCases.length +
        (bad ? ' · <b style="color:var(--red)">매핑 오류 ' + bad + "</b>" : "");
    } else {
      sum = yamlCases.length ? "케이스 " + yamlCases.length
                             : '<span class="muted">케이스 표기 없음</span>';
    }

    html +=
      '<tr class="scenhead"><td colspan="7">' + twisty +
      '<label style="cursor:pointer"><input type="checkbox" data-test="' + esc(t.name) + '"' +
      (state.selected.has(t.name) ? " checked" : "") +
      ' aria-label="' + esc(t.name) + ' 시나리오 선택"> <span class="mono">' + esc(t.name) +
      "</span></label>" + (pills ? " " + pills : "") +
      '<span class="muted" style="font-weight:400"> · ' + esc(t.group) +
      " · 계정 " + esc(t.account) + "</span>" +
      '<span class="sum">' + sum + " · 약 " + t.est + "분</span></td></tr>";

    if (!open) continue;

    if (!connected) {
      for (const c of yamlCases) {
        if (state.priFilter !== "all" && (c.pri || "").trim() !== state.priFilter) continue;
        html += '<tr class="clrow">' +
          caseCell("[" + c.id + "]", c.pri, c.text, t.name + " [" + c.id + "]", null, "") +
          "</tr>";
      }
      continue;
    }

    // 체크리스트 행이 정본이다 — 확인 문구·중요도를 시트에서 가져온다
    const covered = new Set();
    for (const r of clRows) {
      for (const c of r.cases) covered.add(c);
      if (state.onlyBadMap && !r.mapError) continue;
      if (state.priFilter !== "all" && priOf(r) !== state.priFilter) continue;
      const ids = r.cases.length ? r.cases.map((c) => "[" + c + "]").join(" ") : "—";
      html += '<tr class="clrow">' +
        '<td><span class="id">' + esc(ids) + "</span></td>" +
        "<td>" + esc(r.priority || "—") + "</td>" +
        '<td><span class="txt">' + esc(r.text) + "</span></td>" +
        "<td>" + mapCellOf(r) + coverTagOf(r.cover) + "</td>" +
        '<td><span class="v none">—</span></td><td><span class="v none">—</span></td>' +
        '<td><span class="v none">—</span></td>' +
        "</tr>";
    }
    // 덮이지 않은 yaml 케이스 — 커버리지 구멍이 여기서 드러난다
    for (const c of yamlCases) {
      if (covered.has(c.id)) continue;
      if (state.priFilter !== "all" && (c.pri || "").trim() !== state.priFilter) continue;
      html += '<tr class="clrow gap">' +
        '<td><span class="id">[' + esc(c.id) + "]</span></td>" +
        "<td>" + esc(c.pri || "—") + "</td>" +
        '<td><span class="txt muted">' + esc(c.text) + "</span>" +
        '<span class="sub">체크리스트에 매핑된 행이 없습니다</span></td>' +
        '<td><span class="map none">매핑 안 됨</span></td>' +
        '<td><span class="v none">—</span></td><td><span class="v none">—</span></td>' +
        '<td><span class="v none">—</span></td></tr>';
    }
  }

  // 어느 시나리오에도 속하지 않는 행 — 언제나 맨 뒤
  if (connected && state.groupFilter === "all") {
    // 이 묶음도 **같은 필터를 탄다** — 중요도를 걸었는데 여기만 그대로 남으면 앞뒤가 안 맞는다
    let orphan = state.checklist.orphan.concat(state.checklist.notInSuite);
    if (state.priFilter !== "all") orphan = orphan.filter((r) => priOf(r) === state.priFilter);
    if (orphan.length) {
      const open = state.expanded.has("__none");
      html += '<tr class="scenhead"><td colspan="7">' +
        '<button class="twisty" type="button" data-expand="__none" aria-expanded="' + open + '">' +
        '<i class="chev"></i></button>' +
        '<span class="noscen">시나리오 없음 · 스위트에 없는 시나리오 — 실행 대상 아님</span>' +
        '<span class="sum">체크리스트 ' + orphan.length + "행</span></td></tr>";
      if (open) {
        for (const r of orphan) {
          const ids = r.cases.length ? r.cases.map((c) => "[" + c + "]").join(" ") : "—";
          html += '<tr class="clrow">' +
            '<td><span class="id">' + esc(ids) + "</span></td>" +
            "<td>" + esc(r.priority || "—") + "</td>" +
            '<td><span class="txt">' + esc(r.text) + "</span></td>" +
            "<td>" + mapCellOf(r) + coverTagOf(r.cover) + "</td>" +
            '<td><span class="v none">—</span></td><td><span class="v none">—</span></td>' +
            '<td><span class="v none">—</span></td></tr>';
        }
      }
    }
  }

  $("tbody").innerHTML = html;
  $("empty").hidden = rows.length > 0;
  renderSelection();
}

function renderSelection() {
  for (const el of document.querySelectorAll("[data-test]")) {
    el.checked = state.selected.has(el.dataset.test);
  }
  const picked = state.tests.filter((t) => state.selected.has(t.name));
  const minutes = picked.reduce((sum, t) => sum + t.est, 0);
  const money = picked.filter((t) => t.irreversible).length;

  let text = picked.length === 0
    ? "선택된 시나리오 없음"
    : "선택 <b>시나리오 " + picked.length + "개</b> · 예상 <b>" +
      Math.floor(minutes / 60) + "시간 " + (minutes % 60) + "분</b>";
  if (money > 0) text += ' · <b style="color:var(--red)">실결제 ' + money + "건</b>";
  // 필터를 바꿔도 선택은 남는다 → **지금 화면에 없는 선택**을 알린다.
  //   실행 직전 확인창에서야 알면 늦다(개수만 보고 눌러 버린다).
  const visNames = new Set(visibleTests().map((t) => t.name));
  const hidden = picked.filter((t) => !visNames.has(t.name)).length;
  if (hidden > 0) {
    text += ' · <b style="color:var(--amber)">화면에 없는 선택 ' + hidden + "개</b>";
  }
  if (picked.length) {
    text += "<br>" + picked.slice(0, 6).map((t) => "<code>" + esc(t.name) + "</code>").join(" ") +
      (picked.length > 6 ? ' <span class="muted">외 ' + (picked.length - 6) + "개</span>" : "");
  }
  $("selInfo").innerHTML = text;
  updateRunState();
}

function updateRunState() {
  const hasDevice = !!$("dev").value;
  const vis = visibleTests();
  // 사용자를 고르기 전에는 아무것도 돌리지 않는다 — 계정이 사람마다 다르다.
  const hasUser = !!state.runUser;
  const why = !hasUser ? "먼저 사용자를 선택하세요." : "";
  const runBtn = $("runBtn");
  runBtn.disabled = state.running || state.selected.size === 0 || !hasDevice || !hasUser;
  runBtn.title = why;
  const all = $("runAllBtn");
  all.disabled = state.running || !hasDevice || vis.length === 0 || !hasUser;
  all.title = why;
  // 필터가 걸렸는데 '전체 실행'이라고 적혀 있으면 거짓말이다 → 이름도 바꾼다
  all.textContent = (filterOn() ? "보이는 것 실행" : "전체 실행") + " (" + vis.length + ")";
}

/* -------------------------------------------------------------------- 실행 */

/* 필터가 걸려 있는가 — 버튼 이름과 경고 문구가 이 값으로 갈린다 */
function filterOn() {
  return state.groupFilter !== "all" || state.priFilter !== "all" || state.onlyBadMap;
}

function onRunAll() {
  // ★ **보이는 것만** 고른다. 종전엔 state.tests 전부를 골라 필터가 무의미했다.
  for (const t of visibleTests()) state.selected.add(t.name);
  renderTable();
  onRun();
}

async function onRun() {
  const picked = state.tests.filter((t) => state.selected.has(t.name));
  const srv = state.config.servers.find((s) => s.value === state.server);
  const isLive = !!(srv && srv.live);
  const money = picked.filter((t) => t.irreversible);
  const minutes = picked.reduce((sum, t) => sum + t.est, 0);

  let ask = "실행자: " + (state.runUser || "-") + "\n" +
    picked.length + "개 시나리오를 실행합니다. (예상 " +
    Math.floor(minutes / 60) + "시간 " + (minutes % 60) + "분)\n\n";
  if (isLive) ask += "⚠️ 운영(Live) — 실서비스 계정과 실자금이 움직입니다.\n";
  if (money.length) ask += "⚠️ 실결제 포함: " + money.map((t) => t.name).join(", ") + "\n";
  ask += "\n계속할까요?";
  if (!confirm(ask)) return;

  startProgress(picked.map((t) => t.name));
  setRunning(true);
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tests: picked.map((t) => t.name),
        user: state.runUser,
        device: $("dev").value,
        server: state.server,
        platform: "android",
        confirm_live: isLive,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "실행을 시작하지 못했습니다.");
    listen();
  } catch (err) {
    setRunNow('<b style="color:var(--red)">시작 실패</b> · ' + esc(err.message));
    stopProgress();
    setRunning(false);
  }
}

async function onStop() {
  if (!confirm("실행을 중단합니다.\n\n앱은 중단 시점 화면에 남습니다. 계속할까요?")) return;
  try {
    const res = await fetch("/api/run/stop", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "중단하지 못했습니다.");
    setRunNow("중단 요청됨 — 정리 중입니다…");
  } catch (err) {
    setRunNow('<b style="color:var(--red)">중단 실패</b> · ' + esc(err.message));
  }
}

/* 진행은 한 줄로만 보여준다 — 스텝 로그와 결과 상세는 「실행 이력」이 맡는다. */
const prog = { names: [], done: 0, now: "", startedAt: 0, timer: null, finished: false };

function startProgress(names) {
  prog.names = names.slice();
  prog.done = 0;
  prog.now = "";
  prog.finished = false;
  prog.startedAt = Date.now();
  $("runProg").classList.remove("hidden");
  clearInterval(prog.timer);
  prog.timer = setInterval(renderProgress, 1000);
  renderProgress();
}

function stopProgress() {
  clearInterval(prog.timer);
  prog.timer = null;
}

function mmss(ms) {
  const s = Math.floor(ms / 1000);
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

function setRunNow(html) {
  $("runProg").classList.remove("hidden");
  $("runNow").innerHTML = html;
}

function renderProgress() {
  if (prog.finished) return;
  const total = prog.names.length || 1;
  $("progBar").style.width = Math.round((prog.done / total) * 100) + "%";
  setRunNow(
    "<b>" + Math.min(prog.done + 1, total) + " / " + total + "</b>" +
    (prog.now ? " · <code>" + esc(prog.now) + "</code> 진행 중" : "") +
    " · " + mmss(Date.now() - prog.startedAt) + " 경과");
}

function listen() {
  const es = new EventSource("/api/run/stream");
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "test_start") {
      prog.now = msg.name;
    } else if (msg.type === "test_done") {
      prog.done += 1;
      prog.now = "";
    } else if (msg.type === "done") {
      es.close();
      finish(msg.summary);
      return;
    }
    if (msg.type !== "line") renderProgress();
  };
  es.onerror = () => {
    es.close();
    prog.finished = true;
    setRunNow('<b style="color:var(--red)">연결 끊김</b> — 서버와의 로그 연결이 끊겼습니다.');
    stopProgress();
    setRunning(false);
  };
}

function finish(summary) {
  stopProgress();
  setRunning(false);
  prog.finished = true;
  const c = (summary && summary.counts) || {};
  $("progBar").style.width = "100%";
  const head = summary && summary.stopped
    ? '<b style="color:#96631a">중단됨</b>'
    : summary && summary.ok
      ? '<b style="color:#137333">완료</b>'
      : '<b style="color:var(--red)">실패 있음</b>';
  setRunNow(
    head + " · PASS " + (c.PASS || 0) + " · FAIL " + (c.FAIL || 0) + " · SKIP " + (c.SKIP || 0) +
    ' · <a href="/history.html">실행 이력에서 상세 보기</a>');
}

function setRunning(on) {
  state.running = on;
  $("stopBtn").classList.toggle("hidden", !on);
  $("runAllBtn").disabled = on;
  updateRunState();
}

async function attachIfRunning() {
  try {
    const st = await api("/api/run/status");
    if (!st.running) return;
    startProgress(st.names || []);
    setRunning(true);
    setRunNow("실행 중인 작업에 다시 붙었습니다…");
    listen();
  } catch (err) {
    /* 붙을 게 없으면 조용히 넘어간다 */
  }
}

/* ------------------------------------------------------------ 사전 조건 점검 */

async function onPreflight() {
  const btn = $("btn-pf");
  const out = $("pf-out");
  const started = Date.now();
  setAdminBusy(true);
  btn.textContent = "점검 중… 0초";
  // 30초쯤 걸린다 — 아무 변화가 없으면 죽은 버튼으로 보인다
  const tick = setInterval(() => {
    btn.textContent = "점검 중… " + Math.round((Date.now() - started) / 1000) + "초";
  }, 1000);
  out.textContent = "admin 에 로그인해 계정을 확인하는 중입니다… (30초쯤 걸립니다)";
  try {
    const res = await fetch("/api/admin/preflight", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user: state.runUser }),
  });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "점검 실패");
    renderPreflight(data);
  } catch (err) {
    out.innerHTML = '<span class="warn">점검 실패: ' + esc(err.message) + "</span>";
  } finally {
    clearInterval(tick);
    setAdminBusy(false);
    btn.textContent = "admin 점검";
  }
}

function renderPreflight(data) {
  state.preflight = data;
  const head = data.ok
    ? '<p class="pf-head ok">사전 조건을 모두 만족합니다.</p>'
    : '<p class="pf-head warn">사전 조건이 충족되지 않았습니다 — NG 항목을 해결해야 합니다.</p>';
  $("pf-out").innerHTML = head + data.checks.map(pfRow).join("");
  updateFixAll();
}

function pfRow(c) {
  const want = c.want === "exists" ? "있어야 함" : "없어야 함";
  const got = c.found ? "있음" : "없음";
  const kind = c.kind === "documents" ? "문서" : "계정";
  // 처리할 수 있는 NG 에만 단추를 단다. '있어야 하는데 없는' 계정은 사람이 만들어야 해서 없다.
  const fix = !c.ok && c.fix
    ? '<button class="small pf-fix" type="button" data-fix="' + esc(c.fix) +
      '" data-user="' + esc(c.user_id) + '">' + esc(c.fix_label || "처리") + "</button>"
    : "";
  return '<div class="pf-row" data-row="' + esc(c.kind + ":" + c.user_id) + '">' +
    '<span class="pf-mark ' + (c.ok ? "ok" : "warn") + '">' + (c.ok ? "OK" : "NG") + "</span>" +
    '<span class="pf-name"><span class="pf-kind">' + kind + "</span> <code>" +
    esc(c.user_id) + "</code></span>" +
    '<span class="muted">' + want + " / " + got +
    (c.detail ? " · " + esc(c.detail) : "") + "</span>" +
    '<span class="pf-why muted">' + esc(c.why) + "</span>" + fix + "</div>";
}

/* NG 처리 — **되돌릴 수 없다.** 무엇을 지우는지 적어서 한 번 더 묻는다. */
async function onFix(btn) {
  const fix = btn.dataset.fix;
  const user = btn.dataset.user;
  const row = btn.closest(".pf-row");
  const what = fix === "remove_customer"
    ? "계정 " + user + " 을(를) admin 에서 삭제합니다."
    : user + " 의 승인 대기 문서를 전부 삭제(reject)합니다.";
  const BR = String.fromCharCode(10, 10);
  if (!confirm(what + BR + "되돌릴 수 없습니다. 계속할까요?")) return;

  const label = btn.textContent;
  setAdminBusy(true);
  btn.textContent = "처리 중…";
  try {
    const res = await fetch("/api/admin/fix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // user_id = 대상 계정, user = 사용자 프로파일. 서버가 '내 프로파일의 계정인지' 대조한다.
      body: JSON.stringify({ fix: fix, user_id: user, confirm: true, user: state.runUser }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "처리 실패");
    if (data.check) {
      applyCheck(data.check);   // 그 줄만 갈아끼운다 — 전체 재점검은 1분 걸린다
      refreshPfHead();
    }
  } catch (err) {
    alert("처리 실패: " + err.message);
  } finally {
    setAdminBusy(false);
    btn.textContent = label;
    updateFixAll();
  }
}

/* admin 작업은 **한 번에 하나만** 돈다(서버 _admin_lock). 그러니 도는 동안
   관련 단추를 전부 잠근다 — 안 그러면 다른 단추가 409 를 알림으로 되돌려준다. */
function setAdminBusy(on) {
  $("btn-pf").disabled = on;
  const all = $("btn-fixall");
  if (all) all.disabled = on || all.classList.contains("hidden");
  for (const b of document.querySelectorAll("#pf-out [data-fix]")) b.disabled = on;
}

/* 처리할 수 있는 NG 가 둘 이상일 때만 「전부 처리」를 보여준다 —
   한 건이면 그 행의 단추로 충분하다. */
function updateFixAll() {
  const btn = $("btn-fixall");
  if (!btn) return;
  const items = fixableItems();
  btn.classList.toggle("hidden", items.length < 2);
  btn.disabled = items.length < 2;
  btn.textContent = "NG " + items.length + "건 전부 처리";
}

function fixableItems() {
  const checks = (state.preflight && state.preflight.checks) || [];
  return checks.filter((c) => !c.ok && c.fix)
               .map((c) => ({ fix: c.fix, user_id: c.user_id, label: c.fix_label }));
}

function applyCheck(check) {
  const row = $("pf-out").querySelector('[data-row="' + check.kind + ":" + check.user_id + '"]');
  if (row) row.outerHTML = pfRow(check);
  const i = state.preflight.checks.findIndex(
    (c) => c.kind === check.kind && c.user_id === check.user_id);
  if (i >= 0) state.preflight.checks[i] = check;
}

function refreshPfHead() {
  const h = $("pf-out").querySelector(".pf-head");
  if (!h || !state.preflight) return;
  const allOk = state.preflight.checks.every((c) => c.ok);
  h.className = "pf-head " + (allOk ? "ok" : "warn");
  h.textContent = allOk
    ? "사전 조건을 모두 만족합니다."
    : "사전 조건이 충족되지 않았습니다 — NG 항목을 해결해야 합니다.";
}

/* NG 전부 처리 — **한 세션에서** 돈다. 건별 처리는 로그인만 N 번이다. */
async function onFixAll() {
  const items = fixableItems();
  if (!items.length) return;
  const BRK = String.fromCharCode(10);
  const list = items.map((it) => " · " + it.label + ": " + it.user_id).join(BRK);
  if (!confirm("아래 " + items.length + "건을 처리합니다." + BRK + BRK + list + BRK + BRK +
               "되돌릴 수 없습니다. 계속할까요?")) return;

  const btn = $("btn-fixall");
  const label = btn.textContent;
  setAdminBusy(true);
  btn.textContent = "처리 중…";
  try {
    const res = await fetch("/api/admin/fix-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: items, confirm: true, user: state.runUser }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "처리 실패");
    const failed = [];
    for (const r of data.results || []) {
      if (r.check) applyCheck(r.check);
      if (!r.done) failed.push(r.user_id + ": " + (r.error || "처리되지 않음"));
    }
    refreshPfHead();
    if (failed.length) alert("일부가 처리되지 않았습니다." + BRK + BRK + failed.join(BRK));
  } catch (err) {
    alert("처리 실패: " + err.message);
  } finally {
    setAdminBusy(false);
    btn.textContent = label;
    updateFixAll();
  }
}

/* ------------------------------------------------------------------ 도움말 */

let modalBack = null;
function openModal(id) {
  modalBack = document.activeElement;
  const m = $(id);
  m.setAttribute("aria-hidden", "false");
  (m.querySelector(".x") || m).focus();
}
function closeModal(id) {
  $(id).setAttribute("aria-hidden", "true");
  if (modalBack && modalBack.focus) modalBack.focus();
}

/* -------------------------------------------------------------------- 연결 */

$("refreshDevices").addEventListener("click", loadDevices);
$("dev").addEventListener("change", updateRunState);
$("runBtn").addEventListener("click", onRun);
$("runAllBtn").addEventListener("click", onRunAll);
$("stopBtn").addEventListener("click", onStop);
$("btn-pf").addEventListener("click", onPreflight);
$("btn-fixall").addEventListener("click", onFixAll);
$("pf-out").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-fix]");
  if (b) onFix(b);
});
$("f-area").addEventListener("change", (ev) => {
  state.groupFilter = ev.target.value;
  renderTable();
});
$("f-pri").addEventListener("change", (ev) => {
  state.priFilter = ev.target.value;
  renderTable();
});
$("btn-selvis").addEventListener("click", () => {
  for (const t of visibleTests()) state.selected.add(t.name);
  renderTable();
});
$("btn-selnone").addEventListener("click", () => {
  state.selected.clear();
  renderTable();
});
$("btn-mapwarn-only").addEventListener("click", (ev) => {
  state.onlyBadMap = !state.onlyBadMap;
  ev.currentTarget.setAttribute("aria-pressed", String(state.onlyBadMap));
  ev.currentTarget.textContent = state.onlyBadMap ? "전체 보기" : "오류만 보기";
  renderTable();
});
$("tbody").addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-expand]");
  if (!btn) return;
  const name = btn.dataset.expand;
  if (state.expanded.has(name)) state.expanded.delete(name);
  else state.expanded.add(name);
  renderTable();
});
$("tbody").addEventListener("change", (ev) => {
  const cb = ev.target.closest("[data-test]");
  if (!cb) return;
  if (cb.checked) state.selected.add(cb.dataset.test);
  else state.selected.delete(cb.dataset.test);
  renderSelection();
});
$("btn-help").addEventListener("click", () => openModal("helpm"));
for (const b of document.querySelectorAll("[data-close]")) {
  b.addEventListener("click", () => closeModal(b.dataset.close));
}
for (const m of document.querySelectorAll(".modal")) {
  m.addEventListener("click", (ev) => { if (ev.target === m) closeModal(m.id); });
}
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Escape") return;
  const open = [...document.querySelectorAll('.modal[aria-hidden="false"]')];
  if (open.length) closeModal(open[open.length - 1].id);
});

boot();
