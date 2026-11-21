"""Similarity cache helpers: reuse an earlier answer when a new question asks the same thing.

Two filters, cheapest first:
  1. find_similar: free text similarity in Python (difflib). Fast, but blind to meaning:
     "capitale de la France" and "capitale de l'Allemagne" look 87 % alike.
  2. confirm_same: Haiku reads both questions and says whether they need the same answer.
     It only runs when filter 1 found a close candidate, so it costs a fraction of a cent.
"""

import json
from difflib import SequenceMatcher

from .config import TRIAGE
from .llm import LLM, LLMResult

CONFIRM_SYSTEM = """You compare two user requests sent to an assistant.
Answer same=true only if one correct answer would fully and correctly answer both requests.
Any difference in the subject, the language, a number, a name or a constraint means same=false.
Give a short reason in English, in one sentence."""

CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {
        "same": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["same", "reason"],
    "additionalProperties": False,
}


def normalize(text: str) -> str:
    """Lowercase and collapse spaces, so 'Bonjour  ?' and 'bonjour ?' compare equal."""
    return " ".join(text.lower().split())


def similarity(a: str, b: str) -> float:
    """Share of matching characters between two texts, from 0.0 (nothing) to 1.0 (identical)."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def find_similar(request: str, known: list[str]) -> tuple[str | None, float]:
    """Returns the known question closest to `request`, and its similarity score."""
    best, best_score = None, 0.0
    for candidate in known:
        score = similarity(request, candidate)
        if score > best_score:
            best, best_score = candidate, score
    return best, best_score


def confirm_same(llm: LLM, new_request: str, cached_request: str) -> tuple[bool, str, LLMResult]:
    """Asks Haiku whether both requests expect the same answer. Returns (same, reason, call)."""
    call = llm.complete(
        model=TRIAGE.model,
        effort=TRIAGE.effort,
        system=CONFIRM_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"<request_1>\n{cached_request}\n</request_1>\n<request_2>\n{new_request}\n</request_2>",
        }],
        max_tokens=2000,
        json_schema=CONFIRM_SCHEMA,
    )
    data = json.loads(call.text)
    return bool(data.get("same")), data.get("reason", "").strip(), call
