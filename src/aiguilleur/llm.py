"""Thin wrapper around the Anthropic SDK so the router can be tested offline."""

import time
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from .config import FALLBACK_MODELS


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int
    stop_reason: str | None


class LLM(Protocol):
    def complete(
        self,
        *,
        model: str,
        effort: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 16000,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResult: ...


class AnthropicLLM:
    """Calls the Claude API. Reads ANTHROPIC_API_KEY from the environment."""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()

    def complete(
        self,
        *,
        model: str,
        effort: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 16000,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        output_config: dict[str, Any] = {"effort": effort}
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            # Stable system prompt first so repeated calls can hit the prompt cache.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": output_config,
        }

        start = time.perf_counter()
        if model in FALLBACK_MODELS:
            # If a safety classifier declines, the API retries on a fallback model
            # inside the same call instead of returning an empty refusal.
            response = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **kwargs,
            )
        else:
            response = self.client.messages.create(**kwargs)
        latency_ms = int((time.perf_counter() - start) * 1000)

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        return LLMResult(
            text=text,
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            latency_ms=latency_ms,
            stop_reason=response.stop_reason,
        )
