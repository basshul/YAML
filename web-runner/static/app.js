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
    $("connState").textContent = "서버 연결됨";
  } catch (err) {
    $("connState").textContent = "연결 실패: " + err.message;
    $("connState").classList.add("bad");
    $("tbody").innerHTML =
      '<tr><td colspan="7" class="muted">목록을 불러오지 못했습니다: ' + esc(err.message) + "</td></tr>";
  }
  attachIfRunning();
}

/* 체크리스트 뒷단이 없어서 꺼 두는 것들. 한곳에 모아 둔다. */
function markOffline() {
  const NOTE = "체크리스트 데이터가 아직 연결되지 않았습니다.";

  for (const id of ["f-run", "f-pri", "f-res", "basis", "mapmode", "btn-save", "btn-reload"]) {
    const el = $(id);
    if (!el) continue;
    el.disabled = true;
    el.title = NOTE;
  }
  const mt = document.querySelector(".modetog");
  if (mt) mt.title = NOTE;

  // 「확인할 것」 — 셀 수 있는 데이터가 없으니 전부 비활성
  for (const b of document.querySelectorAll("[data-todo]")) {
    const n = b.querySelector(".n");
    if (n) n.textContent = "–";
    b.disabled = true;
    b.title = NOTE;
  }
  $("sv-pend").innerHTML = '<span class="muted">' + NOTE + "</span>";
  $("sv-mine").innerHTML = '<span class="muted">결과 기입은 뒷단이 붙은 뒤에 열립니다.</span>';

  // 표 머리글 노출은 renderTable() 이 정한다(케이스를 펼쳤을 때만 뜻이 있다)
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

function visibleTests() {
  return state.tests.filter(
    (t) => state.groupFilter === "all" || t.group === state.groupFilter);
}

function renderTable() {
  const rows = visibleTests();
  const anyOpen = rows.some((t) => state.expanded.has(t.name));
  let html =
    '<tr><td colspan="7" class="muted" style="padding:10px 12px">' +
    "체크리스트 행은 아직 연결되지 않았습니다 — 아래 케이스는 <b>플로우 yaml 의 주석</b>에서 읽은 것입니다." +
    "</td></tr>";

  for (const t of rows) {
    const cases = t.cases || [];
    const open = state.expanded.has(t.name);
    const pills =
      (t.irreversible ? '<span class="tag man">실결제</span>' : "") +
      (t.needs_balance ? '<span class="tag pend">잔액 ' + t.needs_balance.toLocaleString() + "원</span>" : "") +
      (t.push ? '<span class="tag auto">픽스처</span>' : "");

    // 펼침 단추와 선택 체크박스는 **다른 일**을 한다 — 서로의 클릭을 먹지 않게 나눠 둔다
    const twisty = cases.length
      ? '<button class="twisty" type="button" data-expand="' + esc(t.name) + '"' +
        ' aria-expanded="' + open + '"' +
        ' aria-label="' + esc(t.name) + (open ? " 케이스 접기" : " 케이스 펼치기") + '">' +
        (open ? "▾" : "▸") + "</button>"
      : '<span class="twisty empty" aria-hidden="true">·</span>';

    html +=
      '<tr class="scenhead"><td colspan="7">' + twisty +
      '<label style="cursor:pointer"><input type="checkbox" data-test="' + esc(t.name) + '"' +
      (state.selected.has(t.name) ? " checked" : "") +
      ' aria-label="' + esc(t.name) + ' 시나리오 선택"> <span class="mono">' + esc(t.name) +
      "</span></label>" + (pills ? " " + pills : "") +
      '<span class="muted" style="font-weight:400"> · ' + esc(t.group) +
      " · 계정 " + esc(t.account) + "</span>" +
      '<span class="sum">' +
      (cases.length ? "케이스 " + cases.length : '<span class="muted">케이스 표기 없음</span>') +
      " · 약 " + t.est + "분</span></td></tr>";

    if (!open) continue;
    for (const c of cases) {
      html +=
        '<tr class="clrow">' +
        '<td><span class="id">[' + esc(c.id) + "]</span></td>" +
        "<td>" + esc(c.pri || "—") + "</td>" +
        '<td><span class="txt">' + esc(c.text) + "</span></td>" +
        '<td><span class="map">' + esc(t.name) + " [" + esc(c.id) + "]</span></td>" +
        '<td><span class="v none">—</span></td>' +
        '<td><span class="v none">—</span></td>' +
        '<td><span class="v none">—</span></td></tr>';
    }
  }
  $("tbody").innerHTML = html;
  $("empty").hidden = rows.length > 0;
  // 열이 뜻을 갖는 건 케이스 행이 보일 때뿐이다
  const thead = document.querySelector("table.cl thead");
  if (thead) thead.hidden = !anyOpen;
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
  if (picked.length) {
    text += "<br>" + picked.slice(0, 6).map((t) => "<code>" + esc(t.name) + "</code>").join(" ") +
      (picked.length > 6 ? ' <span class="muted">외 ' + (picked.length - 6) + "개</span>" : "");
  }
  $("selInfo").innerHTML = text;
  updateRunState();
}

function updateRunState() {
  const hasDevice = !!$("dev").value;
  $("runBtn").disabled = state.running || state.selected.size === 0 || !hasDevice;
  $("runAllBtn").disabled = state.running || !hasDevice || state.tests.length === 0;
}

/* -------------------------------------------------------------------- 실행 */

function onRunAll() {
  for (const t of state.tests) state.selected.add(t.name);
  renderTable();
  onRun();
}

async function onRun() {
  const picked = state.tests.filter((t) => state.selected.has(t.name));
  const srv = state.config.servers.find((s) => s.value === state.server);
  const isLive = !!(srv && srv.live);
  const money = picked.filter((t) => t.irreversible);
  const minutes = picked.reduce((sum, t) => sum + t.est, 0);

  let ask = picked.length + "개 시나리오를 실행합니다. (예상 " +
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
    const res = await fetch("/api/admin/preflight", { method: "POST" });
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
      body: JSON.stringify({ fix: fix, user_id: user, confirm: true }),
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
      body: JSON.stringify({ items: items, confirm: true }),
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
