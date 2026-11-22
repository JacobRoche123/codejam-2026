"""Claude Code hook: runs before Claude reads each prompt.

Claude Code runs this program on each UserPromptSubmit event, sends the event as JSON on
stdin ({"prompt": "...", "transcript_path": "...", "cwd": "...", ...}), and adds whatever we
print to stdout to Claude's context. It offers a cached answer when the same question was
already answered, and, with an API key, names the Claude model and subagent to use.

Rules of the hook contract we rely on:
- exit 0 → our stdout becomes context; any other non-2 exit is a non-blocking error;
- we never exit 2 (that would block the user's prompt);
- if we print nothing, Claude simply works as usual.
"""

import json
import os
import sys
from typing import Any

from . import memory, savings
from .config import TIERS
from .llm import LLM, AnthropicLLM, resolve_api_key
from .pipeline import Router

# The subagent that runs each tier, as defined in plugin/agents/*.md. Claude Code prefixes
# plugin subagents with the plugin name: agents/opus.md becomes "thinkless:opus".
SUBAGENTS = {
    "simple": "thinkless:haiku",
    "medium": "thinkless:sonnet",
    "complex": "thinkless:opus",
    "expert": "thinkless:fable",
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
    tier = TIERS[rec["tier"]]
    agent = SUBAGENTS[rec["tier"]]
    lines = [
        header,
        f"Model: {tier.display} · effort {tier.effort} (difficulty: {rec['tier']}).",
        f"Reason: {advice['reason']}",
    ]
    if rec["tier"] == "simple":
        lines.append(
            f"Action: this task is simple enough for {tier.display}. Answer it directly and briefly; "
            "no subagent is needed. "
            f'(If you are a larger model and the answer is long, you may delegate it with the Agent tool (also called Task), subagent_type "{agent}".)'
        )
    else:
        lines.append(
            f'Required action: use {tier.display}. Your first step must be an Agent tool call (also called Task) with subagent_type "{agent}", '
            "passing it the task brief below. Call it exactly once, in the foreground, and wait for "
            "its result: never start a second one. Do not write the answer yourself: this routing "
            "was decided by ThinkLess, the compute-saving router the user installed. When the "
            "subagent returns, relay its answer to the user without rewriting it."
        )
    if advice.get("brief"):
        lines.append(f"Task brief for the subagent: {advice['brief']}")
    return "\n".join(lines)


def update_cache(event: dict[str, Any]) -> None:
    """Stores the previous question and its answer from this session's transcript."""
    transcript = event.get("transcript_path")
    if not transcript:
        return
    exchange = memory.last_exchange(transcript)
    if exchange and not should_skip(exchange[0]):
        memory.remember(exchange[0], exchange[1], event.get("cwd", ""))


def run(event: dict[str, Any], llm: LLM | None = None) -> str:
    """Returns the context to add for one hook event ('' = add nothing).

    1. Cache: free, no key needed. A similar earlier question goes to the lead agent.
    2. Triage: only with an API key (precise mode). Without one, the ThinkLess Router
       agent triages the request itself, inside the Claude subscription.
    """
    prompt = event.get("prompt", "")
    if should_skip(prompt):
        return ""
    counter = counter_block()
    try:
        update_cache(event)
        hit = memory.lookup(prompt, event.get("cwd", ""))
    except OSError:  # an unreadable transcript or cache file must never block the prompt
        hit = None
    if hit:
        return join(memory.format_hit(*hit), counter)
    if llm is None and resolve_api_key() is None:
        return counter  # no key: the router agent does the triage itself
    advice = Router(llm or AnthropicLLM()).route(prompt)
    return join(format_advice(advice), counter)


def join(*blocks: str) -> str:
    return "\n\n".join(b for b in blocks if b)


def counter_block() -> str:
    """The live savings counter the router shows in its opening line ('' when unavailable)."""
    if os.environ.get("THINKLESS_COUNTER", "").lower() == "off":
        return ""
    try:
        text = savings.counter_text(savings.running_total())
    except Exception:  # a counter problem must never block or slow down the prompt
        return ""
    return (
        f"[ThinkLess counter] {text}\n"
        "Add this to your opening line, for example: "
        f'"(ThinkLess: Claude Sonnet 5.5 · {text})". It covers the prompts before this one.'
    )


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if event.get("hook_event_name") == "Stop":
            # Claude just finished answering: store this exchange now, so even the last
            # question of a session can be reused later. Prints nothing.
            update_cache(event)
            return
        output = run(event)
    except Exception as exc:  # never break the user's prompt: report and let Claude continue
        print(f"ThinkLess hook skipped: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)  # non-blocking error: the prompt goes ahead without advice
    if output:
        print(output)
