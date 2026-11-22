"""Answer cache for the Claude Code plugin: reuse an earlier answer to the same question.

How it works, with no API key and no model call:
  1. Before each new prompt, the hook reads the session transcript and stores the previous
     question and its final answer in ~/.config/thinkless/cache.json.
  2. It then looks for a stored question that is very similar to the new one, in the same project
     and from the last 24 hours (free text similarity, the same difflib measure as the demo app).
  3. On a match, it hands the old answer to the lead agent, which reuses it only if the question
     is really the same and cannot depend on files or conversation that changed.

The lead agent is the safety check: "capital of France" and "capital of Germany" look alike.
"""

import json
import time
from pathlib import Path
from typing import Any

from .cache import normalize, similarity

CACHE_FILE = Path.home() / ".config" / "thinkless" / "cache.json"
THRESHOLD = 0.85  # higher than the demo app's 0.75: here no extra model double-checks the match
TTL_SECONDS = 24 * 3600
MAX_ENTRIES = 200
MAX_ANSWER_CHARS = 8000


# ---------- reading Claude Code transcripts ----------

def _human_prompt(entry: dict[str, Any]) -> str | None:
    """The text of a prompt the user typed, or None for tool results, notifications, slash commands."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return None
    # Interactive sessions log typed prompts as origin.kind "human" / promptSource "typed";
    # non-interactive runs (claude -p) as promptSource "sdk". "system" marks notifications.
    origin = entry.get("origin") or {}
    if origin.get("kind") != "human" and entry.get("promptSource") not in ("typed", "sdk"):
        return None
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip() or content.lstrip().startswith("/"):
        return None
    return content.strip()


def _assistant_text(entry: dict[str, Any]) -> str:
    """Visible text of a main-session assistant entry (thinking and tool calls are ignored)."""
    if entry.get("type") != "assistant" or entry.get("isSidechain"):
        return ""
    blocks = (entry.get("message") or {}).get("content") or []
    return "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()


def last_exchange(transcript_path: str | Path) -> tuple[str, str] | None:
    """The last human prompt that already has an answer, with its final answer text."""
    path = Path(transcript_path)
    if not path.is_file():
        return None
    exchanges: list[list[str]] = []  # [prompt, last answer text so far]
    for line in path.read_text(errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        prompt = _human_prompt(entry)
        if prompt is not None:
            exchanges.append([prompt, ""])
            continue
        text = _assistant_text(entry)
        if text and exchanges:
            exchanges[-1][1] = text  # keep the last text: the final answer of that turn
    for prompt, answer in reversed(exchanges):
        if answer:
            return prompt, answer
    return None


# ---------- the cache file ----------

def load(now: float | None = None) -> list[dict[str, Any]]:
    """Entries younger than the TTL. A missing or broken file is an empty cache."""
    now = time.time() if now is None else now
    try:
        entries = json.loads(CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [e for e in entries if isinstance(e, dict) and now - e.get("time", 0) < TTL_SECONDS]


def save(entries: list[dict[str, Any]]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(entries[-MAX_ENTRIES:], ensure_ascii=False))
    CACHE_FILE.chmod(0o600)


def remember(prompt: str, answer: str, cwd: str, now: float | None = None) -> None:
    """Stores (or refreshes) one question and its answer for this project."""
    now = time.time() if now is None else now
    key = normalize(prompt)
    entries = [e for e in load(now) if not (e["cwd"] == cwd and normalize(e["prompt"]) == key)]
    entries.append({"prompt": prompt, "answer": answer[:MAX_ANSWER_CHARS], "cwd": cwd, "time": now})
    save(entries)


def lookup(prompt: str, cwd: str, now: float | None = None) -> tuple[dict[str, Any], float] | None:
    """The most similar stored question in this project, if it reaches the threshold."""
    best, best_score = None, 0.0
    for entry in load(now):
        if entry["cwd"] != cwd:
            continue
        score = similarity(prompt, entry["prompt"])
        if score > best_score:
            best, best_score = entry, score
    if best is None or best_score < THRESHOLD:
        return None
    return best, best_score


def format_hit(entry: dict[str, Any], score: float, now: float | None = None) -> str:
    now = time.time() if now is None else now
    minutes = max(1, round((now - entry["time"]) / 60))
    age = f"{minutes} min" if minutes < 120 else f"{round(minutes / 60)} h"
    return (
        f"[ThinkLess cache · {round(score * 100)} % similar · answered {age} ago · no model call needed]\n"
        f"Previous question: {entry['prompt']}\n"
        "Reuse the answer below only if the new request asks exactly the same thing and cannot depend "
        "on files, code or conversation that changed since. Otherwise ignore this block.\n"
        f"<previous_answer>\n{entry['answer']}\n</previous_answer>"
    )
