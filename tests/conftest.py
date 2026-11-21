import json
from typing import Any

import pytest

from thinkless.llm import LLMResult


class FakeLLM:
    """Offline stand-in for the Claude API. Triage calls return `verdicts` in order."""

    def __init__(self, verdicts: list[dict[str, Any]], fallback_to: str | None = None):
        self.verdicts = list(verdicts)
        self.fallback_to = fallback_to
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, model, effort, system, messages, max_tokens=16000, json_schema=None):
        self.calls.append({"model": model, "effort": effort, "messages": messages, "schema": json_schema})
        if json_schema is not None:
            return LLMResult(json.dumps(self.verdicts.pop(0)), model, 400, 120, 0, 0, 5, "end_turn")
        served = self.fallback_to or model
        return LLMResult(f"réponse de {model}", served, 200, 800, 0, 0, 20, "end_turn")


def verdict(clarity="clear", questions=None, complexity="simple", reason="ok", brief="tâche"):
    return {
        "clarity": clarity,
        "questions": questions or [],
        "complexity": complexity,
        "reason": reason,
        "brief": brief,
    }


@pytest.fixture
def make_llm():
    return FakeLLM
