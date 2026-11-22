"""Model tiers and prices used by the router.

Prices are Anthropic first-party API rates in USD per million tokens.
Cost is the compute proxy shown in the demo: a cheaper model doing the
same job uses less compute.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    name: str
    model: str
    effort: str
    label: str
    display: str  # human name of the model, e.g. "Claude Opus 5.5"


# Price per million tokens: (input, output).
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5-2": (8.00, 40.00),
}

# Published cache-read prices per million tokens, where known. Other models use
# CACHE_READ_FACTOR × input price.
CACHE_READ_PRICES: dict[str, float] = {
    "claude-sonnet-5-5": 0.10,
    "claude-opus-5-5": 0.20,
    "claude-fable-5-2": 0.20,
}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25

# One tier per difficulty, from cheapest to most capable.
TIERS: dict[str, Tier] = {
    "simple": Tier("simple", "claude-haiku-5-5", "low", "Haiku 5.5 · effort low", "Claude Haiku 5.5"),
    "medium": Tier("medium", "claude-sonnet-5-5", "medium", "Sonnet 5.5 · effort medium", "Claude Sonnet 5.5"),
    "complex": Tier("complex", "claude-opus-5-5", "high", "Opus 5.5 · effort high", "Claude Opus 5.5"),
    "expert": Tier("expert", "claude-fable-5-2", "high", "Fable 5.2 · effort high", "Claude Fable 5.2"),
}

# Provider-neutral size for each tier, used when an agent sends its own list of models.
SIZES: dict[str, str] = {"simple": "small", "medium": "medium", "complex": "large", "expert": "largest"}

# Limits on a model list sent by an agent.
MAX_MODELS = 20
MAX_MODEL_NAME = 100

TRIAGE = Tier("triage", "claude-haiku-5-5", "low", "Haiku 5.5 · effort low", "Claude Haiku 5.5")

# What a typical app does: send everything to its default strong model, Opus 5.5.
BASELINE = Tier("baseline", "claude-opus-5-5", "high", "Opus 5.5 · effort high", "Claude Opus 5.5")

# Models that accept server-side refusal fallbacks.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"}

MAX_QUESTIONS = 3

# Similarity cache: from this score on, Haiku checks whether two questions need the same answer.
# Text similarity alone is not enough: "capitale de la France" vs "de l'Allemagne" scores 0.87.
SIMILARITY_THRESHOLD = 0.75


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Dollar cost of one call. Unknown models are priced like Opus 5.5."""
    price_in, price_out = PRICES.get(model, PRICES["claude-opus-5-5"])
    cache_read = CACHE_READ_PRICES.get(model, price_in * CACHE_READ_FACTOR)
    return (
        input_tokens * price_in
        + cache_read_tokens * cache_read
        + cache_write_tokens * price_in * CACHE_WRITE_FACTOR
        + output_tokens * price_out
    ) / 1_000_000
