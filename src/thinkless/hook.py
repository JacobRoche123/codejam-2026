"""Claude Code hook: triage every prompt automatically, before Claude reads it.

Claude Code runs this program on each UserPromptSubmit event, sends the event as JSON on
stdin ({"prompt": "...", ...}), and adds whatever we print to stdout to Claude's context.
The advice tells Claude which ThinkLess subagent (small/medium/large) should do the work.

Rules of the hook contract we rely on:
- exit 0 → our stdout becomes context; any other non-2 exit is a non-blocking error;
- we never exit 2 (that would block the user's prompt);
- if we print nothing, Claude simply works as usual.
"""

import json
import os
import sys
from typing import Any

from .llm import LLM, AnthropicLLM
from .pipeline import Router

# The subagent that runs each size, as defined in plugin/agents/*.md. Claude Code prefixes
# plugin subagents with the plugin name: agents/small.md becomes "thinkless:small".
SUBAGENTS = {
    "small": ("thinkless:small", "Claude Haiku 5.5, effort low"),
    "medium": ("thinkless:medium", "Claude Sonnet 5.5, effort medium"),
    "large": ("thinkless:large", "Claude Opus 5.5, effort high"),
}

MIN_WORDS = 3  # "thanks", "ok go", "yes": not worth a triage call


def should_skip(prompt: str) -> bool:
    """Slash commands, very short replies, or THINKLESS_HOOK=off skip the triage (and its cost)."""
    text = prompt.strip()
    return (
        os.environ.get("THINKLESS_HOOK", "").lower() == "off"
        or not text
        or text.startswith("/")
        or len(text.split()) < MIN_WORDS
    )


def format_advice(advice: dict[str, Any]) -> str:
    """Turns Router.route() output into instructions Claude can act on."""
    cost = f"{advice['triage_cost'] * 100:.3f} ¢"
    header = f"[ThinkLess advice · triage by Claude Haiku · cost {cost}]"

    if advice["status"] == "needs_answers":
        questions = "\n".join(f"- {q}" for q in advice["questions"])
        return (
            f"{header}\n"
            "This request is missing details that would change the answer. Before doing any work, "
            f"ask the user these questions:\n{questions}"
        )

    rec = advice["recommendation"]
    agent, runs_on = SUBAGENTS[rec["size"]]
    lines = [
        header,
        f"Difficulty: {rec['tier']} → {rec['size']} model ({runs_on}).",
        f"Reason: {advice['reason']}",
    ]
    if rec["size"] == "small":
        lines.append(
            "Action: this task is simple. Answer it directly and briefly; no subagent is needed. "
            f'(If you are a large model and the answer is long, you may delegate it with the Agent tool (also called Task), subagent_type "{agent}".)'
        )
    else:
        lines.append(
            f'Required action: your first step must be an Agent tool call (also called Task) with subagent_type "{agent}", '
            "passing it the task brief below. Call it exactly once, in the foreground, and wait for "
            "its result: never start a second one. Do not write the answer yourself: this routing "
            "was decided by ThinkLess, the compute-saving router the user installed. When the "
            "subagent returns, relay its answer to the user without rewriting it."
        )
    if advice.get("brief"):
        lines.append(f"Task brief for the subagent: {advice['brief']}")
    return "\n".join(lines)


def run(event: dict[str, Any], llm: LLM | None = None) -> str:
    """Returns the context to add for one hook event ('' = add nothing)."""
    prompt = event.get("prompt", "")
    if should_skip(prompt):
        return ""
    advice = Router(llm or AnthropicLLM()).route(prompt)
    return format_advice(advice)


def main() -> None:
    try:
        event = json.load(sys.stdin)
        output = run(event)
    except Exception as exc:  # never break the user's prompt: report and let Claude continue
        print(f"ThinkLess hook skipped: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)  # non-blocking error: the prompt goes ahead without advice
    if output:
        print(output)
