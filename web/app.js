"use strict";

const $ = (sel) => document.querySelector(sel);
const TIER_NAMES = { simple: "Simple", medium: "Medium", complex: "Complex", expert: "Expert" };

const state = { request: "", questions: [], config: null };

/* ---------- formatting ---------- */

function usd(x) {
  if (x === null || x === undefined) return "–";
  if (x === 0) return "$0";
  if (x < 0.01) return `${(x * 100).toFixed(3)} ¢`;
  return "$" + x.toFixed(4);
}

function ms(x) {
  return x >= 1000 ? `${(x / 1000).toFixed(1)} s` : `${x} ms`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Minimal, safe Markdown: escape first, then add a few tags. */
function renderMarkdown(src) {
  const blocks = [];
  let text = src.replace(/```[\w-]*\n([\s\S]*?)```/g, (_, code) => {
    blocks.push(`<pre><code>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`);
    return `\u0000${blocks.length - 1}\u0000`;
  });
  text = escapeHtml(text);
  const inline = (s) =>
    s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");

  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };

  for (const line of text.split("\n")) {
    const block = line.match(/^\u0000(\d+)\u0000$/);
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (block) { closeList(); out.push(blocks[Number(block[1])]); }
    else if (heading) { closeList(); const level = Math.min(heading[1].length + 1, 4); out.push(`<h${level}>${inline(heading[2])}</h${level}>`); }
    else if (bullet || numbered) {
      const tag = bullet ? "ul" : "ol";
      if (list !== tag) { closeList(); out.push(`<${tag}>`); list = tag; }
      out.push(`<li>${inline((bullet || numbered)[1])}</li>`);
    }
    else if (line.trim() === "") { closeList(); }
    else { closeList(); out.push(`<p>${inline(line)}</p>`); }
  }
  closeList();
  return out.join("");
}

/* ---------- tabs ---------- */

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t === tab);
      t.setAttribute("aria-selected", t === tab ? "true" : "false");
    });
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`));
    if (tab.dataset.tab === "bench") loadBenchmark();
  });
});

document.querySelectorAll("[data-example]").forEach((chip) => {
  chip.addEventListener("click", () => {
    $("#request").value = chip.dataset.example;
    $("#request").focus();
  });
});

/* ---------- live demo ---------- */

function setBusy(busy, label) {
  document.querySelectorAll("button.primary").forEach((b) => (b.disabled = busy));
  if (busy) {
    $("#trace").insertAdjacentHTML(
      "beforeend",
      `<li class="step pending" id="pending"><span class="spinner"></span>${escapeHtml(label)}</li>`
    );
  } else {
    $("#pending")?.remove();
  }
}

function stepHtml(step, complexity) {
  const tierClass = step.kind === "execute" ? complexity : "";
  const tokens = step.kind === "cache" ? "0 tokens" : `${step.input_tokens} → ${step.output_tokens} tokens`;
  return `
    <li class="step ${step.kind} ${tierClass}">
      <div class="step-head"><span>${escapeHtml(step.title)}</span><span>${usd(step.cost_usd)}</span></div>
      <div class="step-model">${escapeHtml(step.tier_label)}${step.model !== "cache" ? ` · <code>${escapeHtml(step.model)}</code>` : ""}</div>
      <div class="step-meta"><span>${tokens}</span>${step.latency_ms ? `<span>${ms(step.latency_ms)}</span>` : ""}${step.cache_read_tokens ? `<span>${step.cache_read_tokens} cached</span>` : ""}</div>
      ${step.detail ? `<div class="step-detail">${escapeHtml(step.detail)}</div>` : ""}
    </li>`;
}

function renderTotals(data) {
  const box = $("#totals");
  const routedCost = data.steps.filter((s) => s.kind !== "baseline").reduce((a, s) => a + s.cost_usd, 0) + (state.questionCost || 0);
  let html = `<div class="card-title">Summary</div>
    <div class="total-row"><span>Total cost with ThinkLess</span><strong>${usd(routedCost)}</strong></div>`;
  if (data.baseline_cost) {
    const savings = Math.round(100 * (1 - routedCost / data.baseline_cost));
    const max = Math.max(routedCost, data.baseline_cost);
    html += `
      <div class="total-row"><span>Same request, everything on Opus</span><strong>${usd(data.baseline_cost)}</strong></div>
      <div class="bars" style="margin:10px 0">
        <div class="bar routed" title="ThinkLess"><span style="width:${(100 * routedCost) / max}%"></span></div>
        <div class="bar base" title="Everything on Opus"><span style="width:${(100 * data.baseline_cost) / max}%"></span></div>
      </div>
      <div class="savings">${savings > 0 ? `−${savings} %` : `+${-savings} %`}</div>
      <div class="muted small">billed compute compared with "everything on Opus".</div>`;
  } else if (!data.cached) {
    html += `<p class="muted small">Tick "Compare with everything on Opus" to see the savings.</p>`;
  }
  box.innerHTML = html;
  box.hidden = false;
}

async function ask(answers) {
  $("#error").hidden = true;
  const compare = $("#compare").checked;
  setBusy(true, compare ? "The agent is working… (Opus runs in parallel for comparison)" : "The agent is working…");
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: state.request, answers, compare }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail?.[0]?.msg || data.detail || `Error ${res.status}`);
    setBusy(false);

    if (!answers) $("#trace").innerHTML = "";
    $("#trace").insertAdjacentHTML("beforeend", data.steps.map((s) => stepHtml(s, data.complexity)).join(""));

    if (data.status === "needs_answers") {
      state.questionCost = data.total_cost;
      showQuestions(data.questions);
      return;
    }

    $("#questions-card").hidden = true;
    const badge = $("#tier-badge");
    badge.className = `badge ${data.cached ? "cache" : data.complexity}`;
    badge.textContent = data.cached ? "Cache" : TIER_NAMES[data.complexity] || data.complexity;
    $("#reason").textContent = data.reason || "";
    $("#answer").innerHTML = renderMarkdown(data.answer || "");
    $("#answer-card").hidden = false;
    renderTotals(data);
    if (!answers) state.questionCost = 0;
  } catch (err) {
    setBusy(false);
    $("#error").textContent = err.message;
    $("#error").hidden = false;
  }
}

/* Advisor mode: ask ThinkLess which model to use, without generating an answer. */
async function advise(answers) {
  $("#error").hidden = true;
  setBusy(true, "ThinkLess is analysing the request…");
  try {
    const res = await fetch("/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: state.request, answers, available_models: readModels() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail?.[0]?.msg || data.detail || `Error ${res.status}`);
    setBusy(false);

    if (!answers) $("#trace").innerHTML = "";
    $("#trace").insertAdjacentHTML("beforeend", stepHtml(data.triage_step, null));

    if (data.status === "needs_answers") {
      showQuestions(data.questions);
      return;
    }
    $("#questions-card").hidden = true;
    const rec = data.recommendation;
    $("#advice-badge").className = `badge ${rec.tier}`;
    $("#advice-badge").textContent = TIER_NAMES[rec.tier] || rec.tier;
    $("#advice-model").textContent = rec.model;
    $("#advice-size").textContent = `${rec.size} · ${rec.source}`;
    $("#advice-effort").textContent = rec.effort;
    $("#advice-reason").textContent = data.reason || "";
    $("#advice-json").textContent = JSON.stringify(data, null, 2);
    $("#advice-card").hidden = false;
  } catch (err) {
    setBusy(false);
    $("#error").textContent = err.message;
    $("#error").hidden = false;
  }
}

function showQuestions(questions) {
  state.questions = questions;
  $("#questions").innerHTML = questions
    .map((q, i) => `<div class="question"><label for="q${i}">${escapeHtml(q)}</label><input type="text" id="q${i}" required></div>`)
    .join("");
  $("#questions-card").hidden = false;
  $("#q0")?.focus();
}

function hideResults() {
  ["#questions-card", "#answer-card", "#advice-card", "#totals"].forEach((id) => ($(id).hidden = true));
}

$("#ask-form").addEventListener("submit", (e) => {
  e.preventDefault();
  state.request = $("#request").value.trim();
  if (!state.request) return;
  state.questionCost = 0;
  hideResults();
  $("#advisor").checked ? advise(null) : ask(null);
});

$("#questions-card").addEventListener("submit", (e) => {
  e.preventDefault();
  const answers = state.questions.map((q, i) => ({ question: q, answer: $(`#q${i}`).value.trim() }));
  $("#advisor").checked ? advise(answers) : ask(answers);
});

/* "small-model, medium-model" → ["small-model", "medium-model"]; empty field → null (Claude defaults). */
function readModels() {
  const models = $("#models").value.split(",").map((m) => m.trim()).filter(Boolean);
  return models.length ? models : null;
}

// The comparison only makes sense when an answer is generated;
// the model list only matters in advisor mode.
$("#advisor").addEventListener("change", () => {
  const advisor = $("#advisor").checked;
  $("#compare").disabled = advisor;
  if (advisor) $("#compare").checked = false;
  $("#models-row").hidden = !advisor;
});

$("#request").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("#ask-form").requestSubmit();
});

/* ---------- benchmark ---------- */

let benchLoaded = false;

async function loadBenchmark() {
  if (benchLoaded) return;
  const data = await fetch("/api/benchmark").then((r) => r.json());
  if (!data.available) {
    $("#bench-empty").hidden = false;
    return;
  }
  benchLoaded = true;
  const s = data.summary;
  $("#kpis").innerHTML = `
    <div class="card kpi highlight"><div class="label">Less billed compute</div><div class="value">−${Math.round(s.savings_pct)} %</div><div class="sub">${usd(s.routed_cost)} instead of ${usd(s.baseline_cost)}</div></div>
    <div class="card kpi"><div class="label">Average quality</div><div class="value">${s.routed_quality}/10</div><div class="sub">Opus alone: ${s.baseline_quality}/10</div></div>
    <div class="card kpi"><div class="label">Expected tier found</div><div class="value">${s.tier_match}/${s.tasks}</div><div class="sub">tasks classified as expected</div></div>
    <div class="card kpi"><div class="label">Tasks tested</div><div class="value">${s.tasks}</div><div class="sub">graded blind by ${escapeHtml(s.judge_model)}</div></div>`;
  $("#bench-note").textContent = "Green: ThinkLess · Red: everything on Opus";

  const max = Math.max(...data.rows.map((r) => Math.max(r.routed_cost, r.baseline_cost)));
  $("#bench-rows").innerHTML = data.rows
    .map((r) => `
      <tr>
        <td class="task">${escapeHtml(r.request.split("\n")[0].slice(0, 90))}${r.questions.length ? `<small>${r.questions.length} question(s) asked first</small>` : ""}</td>
        <td><span class="badge ${r.chosen}">${TIER_NAMES[r.chosen] || r.chosen}</span></td>
        <td class="num">${usd(r.routed_cost)}</td>
        <td class="num">${usd(r.baseline_cost)}</td>
        <td><div class="bars">
          <div class="bar routed"><span style="width:${Math.max(1, (100 * r.routed_cost) / max)}%"></span></div>
          <div class="bar base"><span style="width:${Math.max(1, (100 * r.baseline_cost) / max)}%"></span></div>
        </div></td>
        <td class="num">${r.routed_score} vs ${r.baseline_score}</td>
      </tr>`)
    .join("");
  $("#bench").hidden = false;
  if (data.effort) renderEffort(data.effort);
}

function renderEffort(effort) {
  const comma = (x) => String(x);
  const high = effort.summary.find((s) => s.effort === "high");
  $("#effort-note").textContent = `${effort.model} · ${effort.tasks} tasks`;
  $("#effort-rows").innerHTML = effort.summary
    .map((s) => {
      const relative = high ? Math.round((100 * s.avg_output_tokens) / high.avg_output_tokens) : 100;
      const quality = s.avg_score === null ? "reference" : `${comma(s.avg_score)} vs ${comma(s.avg_reference_score)}`;
      return `
        <tr>
          <td><strong>${s.effort}</strong></td>
          <td class="num">${s.avg_output_tokens}</td>
          <td><div class="bars"><div class="bar routed"><span style="width:${Math.max(2, Math.min(100, relative))}%"></span></div><small class="muted">${relative} %</small></div></td>
          <td class="num">${usd(s.total_cost)}</td>
          <td class="num">${comma(s.avg_seconds)} s</td>
          <td class="num">${quality}</td>
        </tr>`;
    })
    .join("");
  $("#effort-card").hidden = false;
}

/* ---------- config ---------- */

fetch("/api/config")
  .then((r) => r.json())
  .then((cfg) => {
    state.config = cfg;
    $("#tiers-list").textContent =
      `Simple → ${cfg.tiers.simple} · Medium → ${cfg.tiers.medium} · Complex → ${cfg.tiers.complex} · Expert (rare) → ${cfg.tiers.expert}.`;
  })
  .catch(() => {});

/* ---------- savings report ---------- */

/* Report amounts in one unit: cents below one dollar, dollars above. */
function cents(x) {
  if (x === null || x === undefined) return "–";
  return Math.abs(x) < 1 ? `${(x * 100).toFixed(2)} ¢` : "$" + x.toFixed(2);
}

const report = { request: "", questions: [], questionCost: 0 };

document.querySelectorAll("[data-report-example]").forEach((chip) => {
  chip.addEventListener("click", () => {
    $("#report-request").value = chip.dataset.reportExample;
    $("#report-request").focus();
  });
});

function reportProgress(step) {
  // step: 0 = hidden, 1..3 = current step, 4 = all done
  $("#report-progress").hidden = step === 0;
  document.querySelectorAll("#report-progress li").forEach((li) => {
    const n = Number(li.dataset.step);
    li.className = n < step ? "done" : n === step ? "active" : "";
  });
}

function pctText(x) {
  return x === null || x === undefined ? "–" : `${x > 0 ? "−" : "+"}${Math.abs(Math.round(x))} %`;
}

async function generateReport(answers) {
  $("#report-error").hidden = true;
  $("#report").hidden = true;
  $("#report-questions").hidden = true;
  document.querySelectorAll("#report-form button, #report-questions button").forEach((b) => (b.disabled = true));

  // The server does all three steps in one call; the steps advance on a timer so the user sees progress.
  reportProgress(1);
  const timers = [setTimeout(() => reportProgress(2), 2500), setTimeout(() => reportProgress(3), 12000)];
  try {
    const res = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: report.request, answers, question_cost: report.questionCost }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail?.[0]?.msg || data.detail || `Error ${res.status}`);

    if (data.status === "needs_answers") {
      report.questions = data.questions;
      report.questionCost = data.question_cost;
      $("#report-question-list").innerHTML = data.questions
        .map((q, i) => `<div class="question"><label for="rq${i}">${escapeHtml(q)}</label><input type="text" id="rq${i}" required></div>`)
        .join("");
      reportProgress(0);
      $("#report-questions").hidden = false;
      $("#rq0")?.focus();
      return;
    }
    reportProgress(4);
    renderReport(data);
  } catch (err) {
    reportProgress(0);
    $("#report-error").textContent = err.message;
    $("#report-error").hidden = false;
  } finally {
    timers.forEach(clearTimeout);
    document.querySelectorAll("#report-form button, #report-questions button").forEach((b) => (b.disabled = false));
  }
}

function renderReport(d) {
  const t = d.thinkless, b = d.baseline, s = d.savings, q = d.quality;
  report.last = d;

  $("#r-model").textContent = `${d.choice.display} · effort ${d.choice.effort}`;
  $("#r-badge").className = `badge ${d.choice.tier}`;
  $("#r-badge").textContent = TIER_NAMES[d.choice.tier] || d.choice.tier;
  $("#r-reason").textContent = d.choice.reason;

  const saved = s.usd >= 0;
  $("#r-kpis").innerHTML = `
    <div class="card kpi ${saved ? "highlight" : "warn"}"><div class="label">${saved ? "Money saved" : "Extra cost"}</div>
      <div class="value">${pctText(s.pct)}</div><div class="sub">${cents(t.cost)} instead of ${cents(b.cost)}</div></div>
    <div class="card kpi"><div class="label">Tokens</div>
      <div class="value">${pctText(s.tokens_pct)}</div><div class="sub">${t.tokens.toLocaleString("en")} vs ${b.tokens.toLocaleString("en")}</div></div>
    <div class="card kpi"><div class="label">Quality kept</div>
      <div class="value">${q.retained_pct === null ? "–" : Math.round(q.retained_pct) + " %"}</div><div class="sub">${q.thinkless}/10 vs ${q.baseline}/10 (Opus)</div></div>
    <div class="card kpi"><div class="label">Time</div>
      <div class="value">${ms(t.latency_ms)}</div><div class="sub">Opus alone: ${ms(b.latency_ms)}</div></div>`;

  const max = Math.max(t.cost, b.cost) || 1;
  const parts = [
    ["Triage · Claude Haiku 5.5", t.triage_cost],
    [`Answer · ${d.choice.display}`, t.answer_cost],
  ];
  if (t.question_cost) parts.unshift(["Clarifying round", t.question_cost]);
  $("#r-costs").innerHTML = `
    <div class="cost-row"><span>ThinkLess</span><div class="bar routed"><span style="width:${Math.max(1, (100 * t.cost) / max)}%"></span></div><strong>${cents(t.cost)}</strong></div>
    <div class="cost-row"><span>Claude Opus 5.5 alone</span><div class="bar base"><span style="width:${Math.max(1, (100 * b.cost) / max)}%"></span></div><strong>${cents(b.cost)}</strong></div>
    <ul class="cost-parts muted small">${parts.map(([k, v]) => `<li><span>${escapeHtml(k)}</span><span>${cents(v)}</span></li>`).join("")}</ul>`;

  $("#r-left-model").textContent = d.choice.display;
  $("#r-left-score").textContent = `${q.thinkless}/10`;
  $("#r-right-score").textContent = `${q.baseline}/10`;
  $("#r-left").innerHTML = renderMarkdown(t.answer || "");
  $("#r-right").innerHTML = renderMarkdown(b.answer || "");

  $("#r-judge").innerHTML = d.judge.comments
    .map((c, i) => `<p class="small"><strong>Pass ${i + 1}${i ? " (order swapped)" : ""}:</strong> ${escapeHtml(c)}</p>`)
    .join("");
  $("#r-judge-model").textContent = d.judge.model;
  $("#r-overhead").textContent = `Report overhead, not part of the savings: judging cost ${cents(d.judge.cost)}.`;
  $("#report").hidden = false;
  $("#report").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("#report-form").addEventListener("submit", (e) => {
  e.preventDefault();
  report.request = $("#report-request").value.trim();
  if (!report.request) return;
  report.questionCost = 0;
  generateReport(null);
});

$("#report-questions").addEventListener("submit", (e) => {
  e.preventDefault();
  const answers = report.questions.map((q, i) => ({ question: q, answer: $(`#rq${i}`).value.trim() }));
  generateReport(answers);
});

$("#r-copy").addEventListener("click", async () => {
  const d = report.last;
  if (!d) return;
  const text =
    `ThinkLess savings report\n` +
    `Prompt: ${d.request}\n` +
    `Model chosen: ${d.choice.display} (effort ${d.choice.effort}) instead of Claude Opus 5.5\n` +
    `Cost: ${cents(d.thinkless.cost)} vs ${cents(d.baseline.cost)} (${pctText(d.savings.pct)})\n` +
    `Tokens: ${d.thinkless.tokens} vs ${d.baseline.tokens} (${pctText(d.savings.tokens_pct)})\n` +
    `Quality (blind judge): ${d.quality.thinkless}/10 vs ${d.quality.baseline}/10\n`;
  try {
    await navigator.clipboard.writeText(text);
    $("#r-copy").textContent = "Copied ✓";
    setTimeout(() => ($("#r-copy").textContent = "Copy summary"), 1500);
  } catch {
    $("#r-copy").textContent = "Copy failed";
  }
});
