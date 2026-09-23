"use strict";

const state = {
  config: null,
  tests: [],
  selected: new Set(),
  server: "livetest",
  running: false,
};

const $ = (id) => document.getElementById(id);

/* ---------------------------------------------------------------- 불러오기 */

async function api(path) {
  const res = await fetch(path);
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || `${path} 실패`);
  return data;
}

async function boot() {
  try {
    state.config = await api("/api/config");
    state.server = state.config.servers[0].value;
    renderServers();

    const { tests } = await api("/api/tests");
    state.tests = tests;
    renderTests();

    await loadDevices();
    $("connState").textContent = "서버 연결됨";
  } catch (err) {
    $("connState").textContent = "연결 실패: " + err.message;
    $("connState").classList.add("bad");
    $("testList").textContent = "목록을 불러오지 못했습니다: " + err.message;
  }
}

async function loadDevices() {
  const sel = $("deviceSel");
  sel.innerHTML = "";
  try {
    const { devices } = await api("/api/devices");
    if (devices.length === 0) {
      sel.appendChild(new Option("연결된 기기 없음", ""));
    }
    for (const d of devices) {
      const label = d.ready
        ? `${d.model || d.serial} (${d.serial})`
        : `${d.serial} — ${d.state} (사용 불가)`;
      const opt = new Option(label, d.serial);
      opt.disabled = !d.ready;
      sel.appendChild(opt);
    }
    const preferred = state.config?.default_device;
    if (preferred && devices.some((d) => d.serial === preferred && d.ready)) {
      sel.value = preferred;
    }
  } catch (err) {
    sel.appendChild(new Option("기기 조회 실패: " + err.message, ""));
  }
  updateRunState();
}

/* ------------------------------------------------------------------ 그리기 */

function renderServers() {
  const box = $("serverChoices");
  box.innerHTML = "";
  for (const s of state.config.servers) {
    const label = document.createElement("label");
    label.className = "choice" + (s.live ? " live" : "");
    label.innerHTML =
      `<input type="radio" name="server" value="${s.value}"` +
      `${s.value === state.server ? " checked" : ""}> ${s.label}`;
    label.querySelector("input").addEventListener("change", () => {
      state.server = s.value;
      $("liveWarn").classList.toggle("hidden", !s.live);
      $("runBtn").classList.toggle("live", s.live);
    });
    box.appendChild(label);
  }
}

function renderTests() {
  const list = $("testList");
  list.innerHTML = "";
  const labels = state.config.group_labels || {};

  const groups = [];
  for (const t of state.tests) {
    let g = groups.find((x) => x.name === t.group);
    if (!g) groups.push((g = { name: t.group, items: [] }));
    g.items.push(t);
  }

  for (const g of groups) {
    const box = document.createElement("div");
    box.className = "group";

    const head = document.createElement("div");
    head.className = "group-head";
    head.innerHTML =
      `<label class="g"><input type="checkbox" data-group="${g.name}"> ${g.name}</label>` +
      `<span class="desc">${labels[g.name] || ""}</span>`;
    head.querySelector("input").addEventListener("change", (ev) => {
      for (const t of g.items) toggle(t.name, ev.target.checked);
      renderSelection();
    });
    box.appendChild(head);

    for (const t of g.items) {
      const row = document.createElement("label");
      row.className = "test";

      const pills = [];
      if (t.irreversible) pills.push('<span class="pill money">실결제</span>');
      if (t.needs_balance)
        pills.push(`<span class="pill balance">잔액 ${t.needs_balance.toLocaleString()}원</span>`);
      if (t.push) pills.push('<span class="pill fixture">픽스처</span>');

      row.innerHTML =
        `<input type="checkbox" data-test="${t.name}">` +
        `<span class="body">` +
        `<span class="name">${t.name}${pills.join("")}</span>` +
        `<span class="meta">계정 ${t.account} · 약 ${t.est}분</span>` +
        `</span>`;
      if (t.note) row.title = t.note;
      row.querySelector("input").addEventListener("change", (ev) => {
        toggle(t.name, ev.target.checked);
        renderSelection();
      });
      box.appendChild(row);
    }
    list.appendChild(box);
  }
  renderSelection();
}

function toggle(name, on) {
  if (on) state.selected.add(name);
  else state.selected.delete(name);
}

function renderSelection() {
  // 체크 상태를 화면에 반영 (그룹 일괄 선택 때문에 다시 칠한다)
  for (const el of document.querySelectorAll("[data-test]")) {
    el.checked = state.selected.has(el.dataset.test);
  }
  for (const el of document.querySelectorAll("[data-group]")) {
    const items = state.tests.filter((t) => t.group === el.dataset.group);
    el.checked = items.length > 0 && items.every((t) => state.selected.has(t.name));
  }

  const picked = state.tests.filter((t) => state.selected.has(t.name));
  const minutes = picked.reduce((sum, t) => sum + t.est, 0);
  const money = picked.filter((t) => t.irreversible).length;

  let text =
    picked.length === 0
      ? "선택된 테스트 없음"
      : `${picked.length}개 선택 · 예상 ${Math.floor(minutes / 60)}시간 ${minutes % 60}분`;
  if (money > 0) text += ` · 실결제 ${money}건 포함`;
  $("selInfo").textContent = text;

  updateRunState();
}

function updateRunState() {
  const hasDevice = !!$("deviceSel").value;
  $("runBtn").disabled = state.running || state.selected.size === 0 || !hasDevice;
}

/* -------------------------------------------------------------------- 실행 */

function onRun() {
  alert("실행 연결은 4단계에서 붙입니다.");
}

/* -------------------------------------------------------------------- 시작 */

$("refreshDevices").addEventListener("click", loadDevices);
$("deviceSel").addEventListener("change", updateRunState);
$("clearSel").addEventListener("click", () => {
  state.selected.clear();
  renderSelection();
});
$("runBtn").addEventListener("click", onRun);

boot();
