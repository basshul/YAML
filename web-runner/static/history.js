"use strict";

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function when(stamp) {
  // 2026-09-23_142809 → 2026-09-23 14:28
  const m = /^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(stamp);
  return m ? `${m[1]} ${m[2]}:${m[3]}` : stamp;
}

async function boot() {
  let runs;
  try {
    const res = await fetch("/api/history?limit=100");
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "이력을 불러오지 못했습니다.");
    runs = data.runs;
  } catch (err) {
    $("stats").textContent = err.message;
    return;
  }

  if (runs.length === 0) {
    $("stats").innerHTML = '<p class="muted">아직 실행 기록이 없습니다.</p>';
    return;
  }

  renderStats(runs);
  renderRuns(runs);
}

function renderStats(runs) {
  const all = runs.flatMap((r) => r.items);
  const pass = all.filter((i) => i.status === "PASS").length;
  const fail = all.filter((i) => i.status === "FAIL").length;
  const skip = all.filter((i) => i.status === "SKIP").length;
  const rate = all.length ? Math.round((pass / all.length) * 100) : 0;
  const mixed = runs.filter((r) => r.server_mixed).length;
  const aborted = runs.filter((r) => r.aborted).length;

  $("statMeta").textContent = `최근 실행 ${when(runs[0].stamp)}`;
  $("stats").innerHTML =
    `<div class="stat"><b>${runs.length}</b><span>실행 횟수</span></div>` +
    `<div class="stat"><b>${all.length}</b><span>실행한 테스트</span></div>` +
    `<div class="stat pass"><b>${pass}</b><span>PASS</span></div>` +
    `<div class="stat fail"><b>${fail}</b><span>FAIL</span></div>` +
    `<div class="stat skip"><b>${skip}</b><span>SKIP</span></div>` +
    `<div class="stat"><b>${rate}%</b><span>통과율</span></div>` +
    (mixed ? `<div class="stat fail"><b>${mixed}</b><span>서버 혼입</span></div>` : "") +
    (aborted ? `<div class="stat fail"><b>${aborted}</b><span>중단됨</span></div>` : "");
}

function renderRuns(runs) {
  const box = $("runs");
  box.innerHTML =
    `<div class="run head"><span class="c-when">실행 일시</span><span class="c-dev">기기</span>` +
    `<span class="c-env">환경</span><span class="c-res">결과 (PASS / FAIL)</span></div>`;

  for (const r of runs) {
    const ok = r.counts.FAIL === 0 && !r.aborted;
    const wrap = document.createElement("details");
    wrap.className = "run " + (ok ? "ok" : "bad");

    const flags =
      (r.aborted ? '<span class="pill money">중단됨</span>' : "") +
      (r.server_mixed ? '<span class="pill money">서버 혼입</span>' : "");

    // 실행 일시 / 기기 / 환경 / 결과 네 축으로 보여준다
    const pkg = r.build ? r.build.split(".").pop() : "";
    const env =
      `${esc(r.server)}` +
      (pkg ? ` <span class="muted">· ${esc(pkg)}</span>` : "") +
      (r.lang ? ` <span class="muted">· ${esc(r.lang)}</span>` : "");

    wrap.innerHTML =
      `<summary>` +
      `<span class="c-when"><b>${when(r.stamp)}</b>` +
      `<span class="muted">소요 ${esc(r.elapsed) || "-"}</span></span>` +
      `<span class="c-dev">${esc(r.device) || '<span class="muted">미기록</span>'}` +
      `<span class="muted">${esc(r.resolution)}</span></span>` +
      `<span class="c-env">${env}</span>` +
      `<span class="c-res"><span class="st-${ok ? "PASS" : "FAIL"}">${ok ? "PASS" : "FAIL"}</span> ` +
      `<span class="muted">${r.total}개 중</span> ` +
      `<b class="st-PASS">${r.counts.PASS}</b> / <b class="st-FAIL">${r.counts.FAIL}</b>` +
      (r.counts.SKIP ? ` / <b class="st-SKIP">${r.counts.SKIP}</b>` : "") +
      `${flags}</span>` +
      `</summary>` +
      `<table class="grid"><tr><th>그룹</th><th>항목</th><th>결과</th><th>스텝</th><th>소요</th><th>사유</th><th></th></tr>` +
      r.items
        .map(
          (i) =>
            `<tr><td class="muted">${esc(i.group)}</td><td>${esc(i.name)}</td>` +
            `<td class="st-${i.status}">${i.status}</td><td>${esc(i.steps)}</td><td>${esc(i.elapsed)}</td>` +
            `<td class="muted">${esc(i.reason)}</td>` +
            `<td><button class="ghost small" data-stamp="${r.stamp}" data-item="${esc(i.name)}">로그</button></td></tr>`
        )
        .join("") +
      `</table>`;
    box.appendChild(wrap);
  }

  box.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-item]");
    if (btn) showLog(btn.dataset.stamp, btn.dataset.item);
  });
}

async function showLog(stamp, item) {
  $("logTitle").textContent = `${item} — ${when(stamp)}`;
  $("logBody").textContent = "불러오는 중…";
  $("logModal").classList.remove("hidden");
  try {
    const res = await fetch(`/api/history/${stamp}/log?item=${encodeURIComponent(item)}`);
    const data = await res.json();
    $("logBody").textContent = res.ok && !data.error ? data.text : data.error;
  } catch (err) {
    $("logBody").textContent = "로그를 불러오지 못했습니다: " + err.message;
  }
}

$("logClose").addEventListener("click", () => $("logModal").classList.add("hidden"));
$("logModal").addEventListener("click", (ev) => {
  if (ev.target.id === "logModal") $("logModal").classList.add("hidden");
});

boot();
