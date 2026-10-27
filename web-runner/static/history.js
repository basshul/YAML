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

/* 결과 칸에 적을 말. **일부만 깨졌으면 숫자로** 적는다 — 48케이스 중 1개가 깨진 것과
   전부 깨진 것이 똑같이 `FAIL` 로 보이면 어느 쪽인지 알 수 없다.
   전부 통과·전부 실패는 종전대로 `PASS`·`FAIL` 그대로 둔다(서버가 `cases` 를 안 주는
   경우 — 가르지 못했다 — 도 마찬가지다). */
function verdict(i) {
  const c = i.cases;
  if (!c || !c.pass || !c.fail) return i.status;
  return `성공 ${c.pass} · 실패 ${c.fail}`;
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
            `<td class="st-${i.status}">${esc(verdict(i))}</td><td>${esc(i.steps)}</td><td>${esc(i.elapsed)}</td>` +
            `<td class="muted">${esc(i.reason)}</td>` +
            `<td><button class="ghost small" data-kind="cases" data-stamp="${r.stamp}" data-item="${esc(i.name)}">케이스</button> ` +
            `<button class="ghost small" data-kind="log" data-stamp="${r.stamp}" data-item="${esc(i.name)}">로그</button></td></tr>`
        )
        .join("") +
      `</table>`;
    box.appendChild(wrap);
  }

  box.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-item]");
    if (!btn) return;
    if (btn.dataset.kind === "cases") toggleCases(btn);
    else showLog(btn.dataset.stamp, btn.dataset.item);
  });
}

/* 시나리오 **안의 케이스별 결과**.

   시나리오가 FAIL 이라고만 적히면 48케이스짜리 `04_02_메뉴_거래내역` 는 로그를 끝까지 읽어야
   어디서 깨졌는지 알 수 있다. 서버가 로그의 최상위 스텝 순서를 yaml 커맨드 순서에 맞춰
   끊긴 자리를 짚어 준다.
   ⚠️ **추정이다.** 케이스 경계 마커(docs/CHECKLIST.md §10 단계 4)가 들어오기 전까지의
     다리라서 화면에도 그렇게 적는다.
   ⛔ 가를 수 없으면 서버가 422 와 사유를 준다 → **그 사유를 그대로 보여준다.**
     엉뚱한 케이스를 지목하는 것이 모르는 것보다 나쁘다. */
const CASE_LABEL = { PASS: "Pass", FAIL: "Fail", NOTRUN: "미실행", BLOCKED: "BLOCKED", NA: "N/A" };
const CASE_CLASS = { PASS: "st-PASS", FAIL: "st-FAIL", NOTRUN: "muted", BLOCKED: "st-SKIP", NA: "st-SKIP" };

async function toggleCases(btn) {
  const row = btn.closest("tr");
  const next = row.nextElementSibling;
  if (next && next.classList.contains("caserow")) {   // 한 번 더 누르면 접는다
    next.remove();
    return;
  }
  const tr = document.createElement("tr");
  tr.className = "caserow";
  tr.innerHTML = '<td colspan="7" class="muted">케이스를 가르는 중…</td>';
  row.after(tr);

  const { stamp, item } = btn.dataset;
  let data;
  try {
    const res = await fetch(`/api/history/${stamp}/cases?item=${encodeURIComponent(item)}`);
    data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "케이스를 불러오지 못했습니다.");
  } catch (err) {
    tr.innerHTML = `<td colspan="7" class="muted">${esc(err.message)}</td>`;
    return;
  }

  const n = (s) => data.cases.filter((c) => c.status === s).length;
  const head =
    `<b>${esc(data.flow)}</b>` +
    // 이름이 바뀐 뒤의 이력이다 — 로그에 적힌 옛 이름을 같이 보여야 헷갈리지 않는다.
    (data.renamed_from ? ` <span class="muted">(로그: ${esc(data.renamed_from)})</span>` : "") +
    ` <span class="muted">· 케이스 ${data.cases.length}개 · ` +
    `Pass ${n("PASS")} / Fail ${n("FAIL")} / 미실행 ${n("NOTRUN")}` +
    (n("BLOCKED") ? ` / BLOCKED ${n("BLOCKED")}` : "") +
    (n("NA") ? ` / N/A ${n("NA")}` : "") +
    ` · 스텝 ${data.steps}/${data.commands}</span>`;
  // 공통 진입부(런치·Server Override·PIN)에서 깨지면 **케이스는 하나도 못 돌았다.**
  // 그걸 안 적으면 "전부 미실행"만 보이고 왜 그런지 알 수 없다.
  const note = data.entry_failed
    ? `<div class="muted">공통 진입부에서 끊겨 케이스가 하나도 실행되지 않았습니다 — ${esc(data.fail_step)}</div>`
    : "";

  tr.innerHTML =
    `<td colspan="7">${head}${note}` +
    '<table class="grid"><tr><th style="width:72px">케이스</th><th style="width:78px">결과</th>' +
    "<th>확인 항목</th><th>실패 스텝</th></tr>" +
    data.cases
      .map(
        (c) =>
          `<tr><td>[${esc(c.id)}]</td>` +
          `<td class="${CASE_CLASS[c.status] || "muted"}">${esc(CASE_LABEL[c.status] || c.status)}</td>` +
          `<td>${esc(c.title)}</td><td class="muted">${esc(c.step)}</td></tr>`
      )
      .join("") +
    '</table><div class="muted">※ 로그 스텝 순서로 <b>추정</b>한 결과입니다 — 케이스 경계 마커가 들어오면 정확해집니다.</div></td>';
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
