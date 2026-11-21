"use strict";

const $ = (sel) => document.querySelector(sel);
const TIER_NAMES = { simple: "Simple", medium: "Moyenne", complex: "Complexe" };

const state = { request: "", questions: [], config: null };

/* ---------- formatting ---------- */

function usd(x) {
  if (x === null || x === undefined) return "–";
  if (x === 0) return "0 $";
  if (x < 0.01) return `${(x * 100).toFixed(3).replace(".", ",")} ¢`;
  return `${x.toFixed(4).replace(".", ",")} $`;
}

function ms(x) {
  return x >= 1000 ? `${(x / 1000).toFixed(1).replace(".", ",")} s` : `${x} ms`;
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
  const tokens = step.kind === "cache" ? "0 jeton" : `${step.input_tokens} → ${step.output_tokens} jetons`;
  return `
    <li class="step ${step.kind} ${tierClass}">
      <div class="step-head"><span>${escapeHtml(step.title)}</span><span>${usd(step.cost_usd)}</span></div>
      <div class="step-model">${escapeHtml(step.tier_label)}${step.model !== "cache" ? ` · <code>${escapeHtml(step.model)}</code>` : ""}</div>
      <div class="step-meta"><span>${tokens}</span>${step.latency_ms ? `<span>${ms(step.latency_ms)}</span>` : ""}${step.cache_read_tokens ? `<span>${step.cache_read_tokens} en cache</span>` : ""}</div>
      ${step.detail ? `<div class="step-detail">${escapeHtml(step.detail)}</div>` : ""}
    </li>`;
}

function renderTotals(data) {
  const box = $("#totals");
  const routedCost = data.steps.filter((s) => s.kind !== "baseline").reduce((a, s) => a + s.cost_usd, 0) + (state.questionCost || 0);
  let html = `<div class="card-title">Bilan</div>
    <div class="total-row"><span>Coût total avec ThinkLess</span><strong>${usd(routedCost)}</strong></div>`;
  if (data.baseline_cost) {
    const savings = Math.round(100 * (1 - routedCost / data.baseline_cost));
    const max = Math.max(routedCost, data.baseline_cost);
    html += `
      <div class="total-row"><span>Même demande, tout sur Opus</span><strong>${usd(data.baseline_cost)}</strong></div>
      <div class="bars" style="margin:10px 0">
        <div class="bar routed" title="ThinkLess"><span style="width:${(100 * routedCost) / max}%"></span></div>
        <div class="bar base" title="Tout sur Opus"><span style="width:${(100 * data.baseline_cost) / max}%"></span></div>
      </div>
      <div class="savings">${savings > 0 ? `−${savings} %` : `+${-savings} %`}</div>
      <div class="muted small">de calcul facturé par rapport à « tout sur Opus ».</div>`;
  } else if (!data.cached) {
    html += `<p class="muted small">Coche « Comparer avec tout sur Opus » pour voir l'économie.</p>`;
  }
  box.innerHTML = html;
  box.hidden = false;
}

async function ask(answers) {
  $("#error").hidden = true;
  const compare = $("#compare").checked;
  setBusy(true, compare ? "L'agent travaille… (Opus tourne en parallèle pour comparer)" : "L'agent travaille…");
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: state.request, answers, compare }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail?.[0]?.msg || data.detail || `Erreur ${res.status}`);
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
  setBusy(true, "ThinkLess analyse la demande…");
  try {
    const res = await fetch("/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: state.request, answers }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail?.[0]?.msg || data.detail || `Erreur ${res.status}`);
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

// The comparison only makes sense when an answer is generated.
$("#advisor").addEventListener("change", () => {
  $("#compare").disabled = $("#advisor").checked;
  if ($("#advisor").checked) $("#compare").checked = false;
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
    <div class="card kpi highlight"><div class="label">Calcul facturé en moins</div><div class="value">−${Math.round(s.savings_pct)} %</div><div class="sub">${usd(s.routed_cost)} au lieu de ${usd(s.baseline_cost)}</div></div>
    <div class="card kpi"><div class="label">Qualité moyenne</div><div class="value">${String(s.routed_quality).replace(".", ",")}/10</div><div class="sub">Opus seul : ${String(s.baseline_quality).replace(".", ",")}/10</div></div>
    <div class="card kpi"><div class="label">Niveau attendu trouvé</div><div class="value">${s.tier_match}/${s.tasks}</div><div class="sub">tâches classées comme prévu</div></div>
    <div class="card kpi"><div class="label">Tâches testées</div><div class="value">${s.tasks}</div><div class="sub">notées à l'aveugle par ${escapeHtml(s.judge_model)}</div></div>`;
  $("#bench-note").textContent = "Vert : ThinkLess · Rouge : tout sur Opus";

  const max = Math.max(...data.rows.map((r) => Math.max(r.routed_cost, r.baseline_cost)));
  $("#bench-rows").innerHTML = data.rows
    .map((r) => `
      <tr>
        <td class="task">${escapeHtml(r.request.split("\n")[0].slice(0, 90))}${r.questions.length ? `<small>${r.questions.length} question(s) posée(s) d'abord</small>` : ""}</td>
        <td><span class="badge ${r.chosen}">${TIER_NAMES[r.chosen] || r.chosen}</span></td>
        <td class="num">${usd(r.routed_cost)}</td>
        <td class="num">${usd(r.baseline_cost)}</td>
        <td><div class="bars">
          <div class="bar routed"><span style="width:${Math.max(1, (100 * r.routed_cost) / max)}%"></span></div>
          <div class="bar base"><span style="width:${Math.max(1, (100 * r.baseline_cost) / max)}%"></span></div>
        </div></td>
        <td class="num">${String(r.routed_score).replace(".", ",")} vs ${String(r.baseline_score).replace(".", ",")}</td>
      </tr>`)
    .join("");
  $("#bench").hidden = false;
  if (data.effort) renderEffort(data.effort);
}

function renderEffort(effort) {
  const comma = (x) => String(x).replace(".", ",");
  const high = effort.summary.find((s) => s.effort === "high");
  $("#effort-note").textContent = `${effort.model} · ${effort.tasks} tâches`;
  $("#effort-rows").innerHTML = effort.summary
    .map((s) => {
      const relative = high ? Math.round((100 * s.avg_output_tokens) / high.avg_output_tokens) : 100;
      const quality = s.avg_score === null ? "référence" : `${comma(s.avg_score)} vs ${comma(s.avg_reference_score)}`;
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
      `Simple → ${cfg.tiers.simple} · Moyenne → ${cfg.tiers.medium} · Complexe → ${cfg.tiers.complex}.`;
  })
  .catch(() => {});
