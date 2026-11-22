"""ThinkLess savings dashboard: what ThinkLess saved in your real Claude Code sessions.

No API key and no model call: it only reads the session logs Claude Code already keeps in
~/.claude/projects. For every prompt handled by ThinkLess it computes:

  - the actual cost: every token each model really used (lead agent + worker subagents),
    at Anthropic's published API prices, plus ThinkLess's own triage when it ran;
  - an Opus 5.5 estimate: the tokens of the model that did the work (the worker subagent, or
    the lead when it answered itself), priced as if Opus 5.5 had used the same tokens.

The estimate is labeled as such: a real Opus run would have produced a somewhat different
number of tokens. Costs are API-equivalent: on a Claude subscription you are not billed per
token, so savings mean less of your plan's usage rather than dollars.

Usage: thinkless-savings [--days 30] [--no-open] [--out FILE]
"""

import argparse
import html
import json
import re
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import CACHE_READ_FACTOR, CACHE_READ_PRICES, PRICES
from .memory import _human_prompt

PROJECTS_DIR = Path.home() / ".claude" / "projects"
REPORT_FILE = Path.home() / ".config" / "thinkless" / "savings.html"
OPUS = "claude-opus-5-5"
WRITE_5M, WRITE_1H = 1.25, 2.0  # cache-write multipliers of the input price
ADVICE_COST = re.compile(r"\[ThinkLess advice · triage by Claude Haiku · cost ([0-9.]+) ¢\]")
DISPLAY = {
    "claude-haiku-5-5": "Claude Haiku 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-fable-5-2": "Claude Fable 5.2",
}


# ---------- pricing ----------

def usage_cost(model: str, usage: dict[str, Any], price_as: str | None = None) -> float:
    """API-equivalent cost of one usage record, optionally priced as another model."""
    priced = price_as or model
    price_in, price_out = PRICES.get(priced, PRICES[OPUS])
    cache_read = CACHE_READ_PRICES.get(priced, price_in * CACHE_READ_FACTOR)
    created = usage.get("cache_creation") or {}
    w5 = created.get("ephemeral_5m_input_tokens")
    w1 = created.get("ephemeral_1h_input_tokens")
    if w5 is None and w1 is None:  # no breakdown: assume the 5-minute rate
        w5, w1 = usage.get("cache_creation_input_tokens", 0), 0
    return (
        usage.get("input_tokens", 0) * price_in
        + (w5 or 0) * price_in * WRITE_5M
        + (w1 or 0) * price_in * WRITE_1H
        + usage.get("cache_read_input_tokens", 0) * cache_read
        + usage.get("output_tokens", 0) * price_out
    ) / 1_000_000


def total_tokens(usage: dict[str, Any]) -> int:
    return sum(usage.get(k, 0) or 0 for k in (
        "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


# ---------- reading sessions ----------

@dataclass
class Turn:
    prompt: str
    time: str
    cwd: str
    lead: list[tuple[str, dict]] = field(default_factory=list)      # (model, usage) of the lead
    workers: list[tuple[str, dict, str]] = field(default_factory=list)  # (model, usage, agentType)
    triage_cost: float = 0.0
    cache_offered: bool = False
    thinkless: bool = False

    @property
    def actual(self) -> float:
        return (sum(usage_cost(m, u) for m, u in self.lead)
                + sum(usage_cost(m, u) for m, u, _ in self.workers) + self.triage_cost)

    @property
    def opus_estimate(self) -> float:
        """The work's tokens priced as Opus 5.5: the workers' if any, otherwise the lead's."""
        work = [(m, u) for m, u, _ in self.workers] or self.lead
        return sum(usage_cost(m, u, price_as=OPUS) for m, u in work)

    @property
    def models(self) -> list[str]:
        seen: list[str] = []
        for m in [m for m, _ in self.lead] + [m for m, _, _ in self.workers]:
            if m not in seen:
                seen.append(m)
        return seen

    @property
    def tokens(self) -> int:
        return sum(total_tokens(u) for _, u in self.lead) + sum(total_tokens(u) for _, u, _ in self.workers)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    entries = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _usage_by_request(entries: list[dict[str, Any]], sidechain: bool):
    """Yields (entry, model, usage) once per API request: Claude Code splits one response
    into several log lines (thinking, text, tool call) that repeat the same usage."""
    seen: set[str] = set()
    for e in entries:
        if e.get("type") != "assistant" or bool(e.get("isSidechain")) != sidechain:
            continue
        msg = e.get("message") or {}
        key = e.get("requestId") or msg.get("id")
        if not msg.get("usage") or not msg.get("model") or key in seen:
            yield e, None, None
            continue
        seen.add(key)
        yield e, msg["model"], msg["usage"]


def read_session(path: Path) -> list[Turn]:
    """Splits one session log into turns (one per typed prompt) and attributes every cost."""
    entries = _read_jsonl(path)
    router_session = any(e.get("agentSetting", "").startswith("thinkless:") for e in entries
                         if e.get("type") == "agent-setting")
    turns: list[Turn] = []
    tool_turn: dict[str, Turn] = {}
    usage_iter = {id(e): (m, u) for e, m, u in _usage_by_request(entries, sidechain=False)}

    for e in entries:
        prompt = _human_prompt(e)
        if prompt is not None:
            turns.append(Turn(prompt=prompt, time=e.get("timestamp", ""), cwd=e.get("cwd", ""),
                              thinkless=router_session))
            continue
        if not turns:
            continue
        turn = turns[-1]
        if e.get("type") == "attachment":
            content = str((e.get("attachment") or {}).get("content") or "")
            # Advice or a cache offer alone does not make a turn "routed": a session that ignores
            # it (a plain Opus session, say) did not save anything. Routed = the ThinkLess Router
            # lead, or a ThinkLess worker subagent that actually ran (see below).
            match = ADVICE_COST.search(content)
            if match:
                turn.triage_cost += float(match.group(1)) / 100
            if content.startswith("[ThinkLess cache"):
                turn.cache_offered = True
        elif e.get("type") == "assistant" and not e.get("isSidechain"):
            model, usage = usage_iter.get(id(e), (None, None))
            if model:
                turn.lead.append((model, usage))
            for block in (e.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_turn[block.get("id", "")] = turn

    # Worker subagents live in <session>/subagents/agent-*.jsonl with a .meta.json beside them.
    for meta_path in (path.parent / path.stem / "subagents").glob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        turn = tool_turn.get(meta.get("toolUseId", ""))
        log = meta_path.with_name(meta_path.name.replace(".meta.json", ".jsonl"))
        if turn is None or not log.is_file():
            continue
        agent_type = meta.get("agentType", "")
        if agent_type.startswith("thinkless:"):
            turn.thinkless = True
        for _, model, usage in _usage_by_request(_read_jsonl(log), sidechain=True):
            if model:
                turn.workers.append((model, usage, agent_type))
    return turns


def collect(projects_dir: Path = PROJECTS_DIR, days: float | None = 30, now: float | None = None) -> list[Turn]:
    """ThinkLess turns from every Claude Code session modified in the last `days`."""
    now = time.time() if now is None else now
    turns: list[Turn] = []
    for path in sorted(projects_dir.glob("*/*.jsonl")):
        if days is not None and now - path.stat().st_mtime > days * 86400:
            continue
        turns += [t for t in read_session(path) if t.thinkless and (t.lead or t.workers)]
    return sorted(turns, key=lambda t: t.time, reverse=True)


# ---------- summary and report ----------

def summarize(turns: list[Turn]) -> dict[str, Any]:
    actual = sum(t.actual for t in turns)
    opus = sum(t.opus_estimate for t in turns)
    by_model: dict[str, dict[str, float]] = {}
    for t in turns:
        for m, u in t.lead + [(m, u) for m, u, _ in t.workers]:
            row = by_model.setdefault(m, {"cost": 0.0, "tokens": 0})
            row["cost"] += usage_cost(m, u)
            row["tokens"] += total_tokens(u)
    return {
        "prompts": len(turns),
        "actual": actual,
        "opus": opus,
        "saved": opus - actual,
        "saved_pct": round(100 * (opus - actual) / opus, 1) if opus else None,
        "triage": sum(t.triage_cost for t in turns),
        "cache_offered": sum(t.cache_offered for t in turns),
        "by_model": by_model,
    }


def local_time(timestamp: str) -> str:
    """'2026-11-22T02:11:05.123Z' (UTC in the logs) → '2026-11-21 21:11' in local time."""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return timestamp[:16].replace("T", " ")


def money(x: float) -> str:
    return f"{x * 100:.2f} ¢" if abs(x) < 1 else f"${x:.2f}"


def render_html(turns: list[Turn], summary: dict[str, Any], days: float | None) -> str:
    esc = html.escape
    pct = "–" if summary["saved_pct"] is None else f"{summary['saved_pct']:.0f} %"
    rows = []
    for t in turns:
        saved = t.opus_estimate - t.actual
        share = f"{100 * saved / t.opus_estimate:.0f} %" if t.opus_estimate else "–"
        when = local_time(t.time)
        models = " + ".join(DISPLAY.get(m, m) for m in t.models)
        tag = ' <span class="tag">cache offered</span>' if t.cache_offered else ""
        rows.append(
            f"<tr><td class='when'>{esc(when)}</td><td class='prompt'>{esc(t.prompt[:140])}"
            f"<small>{esc(Path(t.cwd).name or t.cwd)}</small></td><td>{esc(models)}{tag}</td>"
            f"<td class='num'>{money(t.actual)}</td><td class='num'>{money(t.opus_estimate)}</td>"
            f"<td class='num {'good' if saved >= 0 else 'bad'}'>{share}</td></tr>"
        )
    model_rows = "".join(
        f"<tr><td>{esc(DISPLAY.get(m, m))}</td><td class='num'>{int(v['tokens']):,}</td>"
        f"<td class='num'>{money(v['cost'])}</td></tr>"
        for m, v in sorted(summary["by_model"].items(), key=lambda kv: -kv[1]["cost"])
    )
    period = "all time" if days is None else f"last {days:g} days"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    empty = "" if turns else (
        "<div class='card'><strong>No ThinkLess prompts found yet.</strong> Start Claude Code with "
        "<code>claude --agent thinkless:router</code>, ask a few things, then run "
        "<code>thinkless-savings</code> again.</div>"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ThinkLess savings</title>
<style>
:root {{ --bg:#f6f7f9; --surface:#fff; --text:#15181d; --muted:#5d6573; --border:#e1e4ea; --accent:#0b7a5c; --bad:#b23a3a; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --surface:#171a20; --text:#e8eaee; --muted:#9aa3b2; --border:#2a2f39; --accent:#3cc497; --bad:#f07a7a; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px; }}
h1 {{ margin:0; font-size:24px; }} .sub {{ color:var(--muted); margin:4px 0 20px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:16px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:16px 18px; margin-bottom:16px; }}
.kpis .card {{ margin:0; }} .label {{ color:var(--muted); font-size:13px; }} .value {{ font-size:28px; font-weight:700; font-variant-numeric:tabular-nums; }}
.hi .value {{ color:var(--accent); }} .small {{ color:var(--muted); font-size:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.03em; padding:8px; border-bottom:1px solid var(--border); }}
td {{ padding:9px 8px; border-bottom:1px solid var(--border); vertical-align:top; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.good {{ color:var(--accent); font-weight:600; }} .bad {{ color:var(--bad); font-weight:600; }}
.prompt small {{ display:block; color:var(--muted); }} .when {{ white-space:nowrap; color:var(--muted); }}
.tag {{ font-size:11px; border:1px solid var(--border); border-radius:999px; padding:0 6px; color:var(--muted); }}
.wrap {{ overflow-x:auto; }} ul {{ margin:0; padding-left:18px; color:var(--muted); font-size:13px; }}
@media (max-width:760px) {{ .kpis {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
</style></head><body><main>
<h1>ThinkLess savings</h1>
<p class="sub">Read from your Claude Code session logs · {esc(period)} · generated {generated} · no API call made</p>
<div class="kpis">
  <div class="card hi"><div class="label">Saved vs Opus 5.5</div><div class="value">{pct}</div><div class="small">{money(summary['saved'])} saved (estimate)</div></div>
  <div class="card"><div class="label">Actual cost</div><div class="value">{money(summary['actual'])}</div><div class="small">API-equivalent, incl. triage {money(summary['triage'])}</div></div>
  <div class="card"><div class="label">Same work on Opus 5.5</div><div class="value">{money(summary['opus'])}</div><div class="small">estimate, same tokens</div></div>
  <div class="card"><div class="label">Prompts routed</div><div class="value">{summary['prompts']}</div><div class="small">{summary['cache_offered']} with a cached answer offered</div></div>
</div>
{empty}
<div class="card"><strong>By model</strong><div class="wrap"><table><thead><tr><th>Model</th><th class="num">Tokens</th><th class="num">Cost</th></tr></thead><tbody>{model_rows}</tbody></table></div></div>
<div class="card"><strong>Prompt by prompt</strong><div class="wrap"><table><thead><tr><th>When</th><th>Prompt · project</th><th>Models used</th><th class="num">Actual</th><th class="num">Opus est.</th><th class="num">Saved</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>
<div class="card"><strong>How this is computed</strong><ul>
<li><strong>Actual:</strong> every token each model used in the turn (the ThinkLess Router lead and any worker subagent), from Claude Code's own logs, at Anthropic's published API prices, plus ThinkLess's triage when an API key is set.</li>
<li><strong>Opus estimate:</strong> the tokens of the model that did the work, priced as Claude Opus 5.5. A real Opus run would use a somewhat different number of tokens, so this is an estimate.</li>
<li><strong>Subscription:</strong> on a Claude plan you are not billed per token. These are API-equivalent amounts: savings mean less of your plan's usage.</li>
<li><strong>Quality</strong> is not measured here (no model is called). Energy is not shown: Anthropic does not publish it per request.</li>
</ul></div>
</main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="ThinkLess savings from your Claude Code logs (no API call).")
    parser.add_argument("--days", type=float, default=30, help="look back this many days (0 = all time)")
    parser.add_argument("--no-open", action="store_true", help="do not open the report in a browser")
    parser.add_argument("--out", type=Path, default=REPORT_FILE, help="where to write the HTML report")
    args = parser.parse_args()
    days = None if args.days == 0 else args.days

    turns = collect(days=days)
    summary = summarize(turns)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(turns, summary, days))

    pct = "–" if summary["saved_pct"] is None else f"{summary['saved_pct']:.0f} %"
    print(f"ThinkLess savings · {summary['prompts']} prompts routed")
    print(f"  Actual cost:          {money(summary['actual'])}  (API-equivalent)")
    print(f"  Same work on Opus 5.5: {money(summary['opus'])}  (estimate)")
    print(f"  Saved:                {money(summary['saved'])}  ({pct})")
    print(f"Report: {args.out}")
    if not args.no_open:
        webbrowser.open(args.out.as_uri())
