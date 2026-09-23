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

function logLine(text) {
  const box = $("log");
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;

  const el = document.createElement("div");
  if (/\bPASS\b|정상|OK$/.test(text)) el.className = "l-pass";
  else if (/\bFAIL\b|⛔|실패|\[STOP\]/.test(text)) el.className = "l-fail";
  else if (/⚠️|SKIP/.test(text)) el.className = "l-warn";
  else if (/^===|^──|^▶|^\$ /.test(text)) el.className = "l-head";
  el.textContent = text;
  box.appendChild(el);

  if (atBottom) box.scrollTop = box.scrollHeight;
}

/* ---------------------------------------------------------------- 진행 표시 */

const prog = { items: [], timer: null };

function startProgress(names, finished) {
  prog.items = (names || []).map((name) => {
    const t = state.tests.find((x) => x.name === name);
    const r = finished ? (finished.items || []).find((x) => x.name === name) : null;
    return {
      name,
      est: t ? t.est : 0,
      status: r ? r.status : "대기",   // 대기 → 실행 중 → PASS/FAIL/SKIP
      steps: r ? parseInt(r.steps, 10) || 0 : 0,
      now: "",
      recover: false,
      startedAt: null,
      elapsed: r ? r.elapsed : null,
      reason: r ? r.reason : "",
    };
  });
  renderProgress();
  $("progBarWrap").classList.remove("hidden");
  clearInterval(prog.timer);
  if (finished) {
    $("progBar").className = "bar " + (finished.ok ? "done" : "fail");
    $("progBar").style.width = "100%";
    prog.timer = null;
  } else {
    $("progBar").className = "bar";
    prog.timer = setInterval(renderProgress, 1000);
  }
}

function stopProgress(ok) {
  clearInterval(prog.timer);
  prog.timer = null;
  $("progBar").className = "bar " + (ok ? "done" : "fail");
  $("progBar").style.width = "100%";
  renderProgress();
}

function item(name) {
  return prog.items.find((i) => i.name === name);
}

function mmss(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function renderProgress() {
  const list = $("progList");
  list.innerHTML = "";

  for (const i of prog.items) {
    const running = i.status === "실행 중";
    const row = document.createElement("div");
    row.className = "prog" + (running ? " running" : "");

    const over = ["PASS", "FAIL", "SKIP"].includes(i.status);
    const chipClass = over ? i.status : "";
    const elapsed = i.elapsed || (running && i.startedAt ? mmss(Date.now() - i.startedAt) : "");
    const detail =
      i.reason ||
      (over ? "" : running ? i.now || "시작하는 중…" : `약 ${i.est}분 예상`);

    row.innerHTML =
      `<span class="chip ${chipClass}">${i.status}</span>` +
      `<span class="body"><span class="name">${i.name}</span>` +
      `<span class="now${i.recover ? " recover" : ""}">${i.recover ? "복구 중 · " : ""}${detail}</span></span>` +
      `<span class="num">${i.steps ? i.steps + "스텝" : ""}${elapsed ? "<br>" + elapsed : ""}</span>`;
    list.appendChild(row);
  }

  // 진행률: 끝난 항목 수 + 현재 항목의 (경과/예상). 예상은 빗나가므로 95%에서 멈춘다.
  const total = prog.items.length || 1;
  let done = prog.items.filter((i) => i.status !== "대기" && i.status !== "실행 중").length;
  const cur = prog.items.find((i) => i.status === "실행 중");
  if (cur && cur.startedAt && cur.est > 0) {
    done += Math.min((Date.now() - cur.startedAt) / (cur.est * 60000), 0.95);
  }
  if (prog.timer) $("progBar").style.width = Math.min(99, (done / total) * 100) + "%";
}

function setRunning(on) {
  state.running = on;
  $("logMeta").textContent = on ? "실행 중…" : "";
  document.querySelectorAll("input, select, button").forEach((el) => {
    if (el.id !== "runBtn") el.disabled = on || el.dataset.alwaysDisabled === "1";
  });
  $("runBtn").textContent = on ? "실행 중…" : "실행";
  updateRunState();
}

async function onRun() {
  const picked = state.tests.filter((t) => state.selected.has(t.name));
  const isLive = state.config.servers.find((s) => s.value === state.server)?.live;
  const money = picked.filter((t) => t.irreversible);

  let ask = `${picked.length}개 테스트를 실행합니다.\n\n`;
  if (isLive) ask += "⚠️ 운영(Live) — 실서비스 계정과 실자금이 움직입니다.\n";
  if (money.length) ask += `⚠️ 실결제 포함: ${money.map((t) => t.name).join(", ")}\n`;
  ask += "\n계속할까요?";
  if (!confirm(ask)) return;

  $("log").innerHTML = "";
  $("summary").classList.add("hidden");
  startProgress(picked.map((t) => t.name));
  setRunning(true);

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tests: picked.map((t) => t.name),
        device: $("deviceSel").value,
        server: state.server,
        platform: "android",
        confirm_live: !!isLive,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "실행을 시작하지 못했습니다.");
    listen();
  } catch (err) {
    logLine("[오류] " + err.message);
    setRunning(false);
  }
}

function listen() {
  const es = new EventSource("/api/run/stream");
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);

    if (msg.type === "line") {
      logLine(msg.text);
      return;
    }
    if (msg.type === "test_start") {
      const i = item(msg.name);
      if (i) {
        i.status = "실행 중";
        i.startedAt = Date.now();
      }
    } else if (msg.type === "step") {
      const i = item(msg.name);
      if (i) {
        i.now = msg.text;
        i.recover = !!msg.recover;
        if (msg.status === "COMPLETED") i.steps += 1;
      }
    } else if (msg.type === "test_done") {
      const i = item(msg.name);
      if (i) {
        i.status = msg.status;
        i.recover = false;
        i.now = "";
        i.reason = msg.reason || "";
        if (msg.steps != null) i.steps = msg.steps;
        if (msg.elapsed) i.elapsed = msg.elapsed;
      }
    } else if (msg.type === "done") {
      es.close();
      // 요약이 정본이다 — 실패 사유처럼 스트림에 안 실린 것도 여기서 채운다
      for (const r of (msg.summary && msg.summary.items) || []) {
        const i = item(r.name);
        if (!i) continue;
        i.status = r.status;
        i.steps = parseInt(r.steps, 10) || i.steps;
        i.elapsed = r.elapsed || i.elapsed;
        i.reason = r.reason || "";
        i.now = "";
      }
      showSummary(msg.summary);
      stopProgress(msg.summary ? msg.summary.ok : false);
      setRunning(false);
      return;
    }
    renderProgress();
  };
  es.onerror = () => {
    es.close();
    logLine("[연결 끊김] 서버와의 로그 연결이 끊겼습니다.");
    stopProgress(false);
    setRunning(false);
  };
}

function showSummary(s) {
  const box = $("summary");
  if (!s) {
    box.classList.add("hidden");
    return;
  }
  const rows = s.items
    .map(
      (i) =>
        `<tr><td>${i.group}</td><td>${i.name}</td>` +
        `<td class="st-${i.status}">${i.status}</td>` +
        `<td>${i.steps}</td><td>${i.elapsed}</td><td>${i.reason || ""}</td></tr>`
    )
    .join("");

  box.className = "panel summary " + (s.ok ? "pass" : "fail");
  box.innerHTML =
    `<div class="headline">${s.ok ? "PASS — 전부 통과" : "FAIL — 실패한 항목이 있습니다"}</div>` +
    `<div>PASS ${s.counts.PASS} · FAIL ${s.counts.FAIL} · SKIP ${s.counts.SKIP} · 소요 ${s.elapsed}` +
    ` <span class="muted">(종료코드 ${s.returncode})</span></div>` +
    (rows
      ? `<table><tr><th>그룹</th><th>항목</th><th>결과</th><th>스텝</th><th>소요</th><th>사유</th></tr>${rows}</table>`
      : "") +
    `<div class="muted" style="margin-top:8px">로그 파일: ${s.log_file}</div>`;
}

/* 새로고침해도 이어지게: 실행 중이면 로그에 다시 붙고, 끝난 실행이면 결과를 되살린다 */
async function attachIfRunning() {
  try {
    const st = await api("/api/run/status");
    if (st.running) {
      startProgress(st.names);   // 이벤트 backlog 를 다시 받아 상태를 복원한다
      setRunning(true);
      listen();
    } else if (st.summary) {
      startProgress(st.names, st.summary);
      showSummary(st.summary);
      $("logMeta").textContent = "직전 실행 결과";
    }
  } catch (_) {
    /* 서버가 기억하는 실행이 없으면 그만 */
  }
}

/* -------------------------------------------------------------------- 시작 */

$("refreshDevices").addEventListener("click", loadDevices);
$("deviceSel").addEventListener("change", updateRunState);
$("clearSel").addEventListener("click", () => {
  state.selected.clear();
  renderSelection();
});
$("runBtn").addEventListener("click", onRun);

boot().then(attachIfRunning);
