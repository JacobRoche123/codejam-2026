"""Savings report: how much ThinkLess saves on one prompt, and at what quality.

The prompt is answered twice: through ThinkLess (triage, then the chosen model) and by Opus 5.5
alone, in parallel. A judge then grades both answers blind. Everything is measured on real calls:
token counts from the API, multiplied by published prices.
"""

from typing import Any

from .config import BASELINE, TIERS
from .judge import judge
from .llm import LLM
from .pipeline import Router
from .triage import QA


def pct(part: float, whole: float) -> float | None:
    """part / whole as a percentage, rounded to 0.1; None when whole is zero."""
    return round(100 * part / whole, 1) if whole else None


def build_report(
    llm: LLM,
    request: str,
    answers: list[QA] | None = None,
    question_cost: float = 0.0,
) -> dict[str, Any]:
    """Runs the comparison and returns everything the report page shows.

    `question_cost` is the cost of an earlier clarification round, so the ThinkLess total
    includes it. If ThinkLess needs clarifications first, returns status "needs_answers".
    """
    outcome = Router(llm).ask(request, answers, compare_baseline=True)
    if outcome.status == "needs_answers":
        return {
            "status": "needs_answers",
            "questions": outcome.questions,
            "question_cost": question_cost + outcome.total_cost,
            "steps": [s.__dict__ for s in outcome.steps],
        }

    execute = next(s for s in outcome.steps if s.kind == "execute")
    triage = next(s for s in outcome.steps if s.kind == "triage")
    base = next(s for s in outcome.steps if s.kind == "baseline")
    grades = judge(llm, Router._raw_prompt(request, answers), outcome.answer, outcome.baseline_answer or "")

    tier = TIERS[outcome.complexity]
    routed_cost = outcome.total_cost + question_cost
    routed_tokens = outcome.total_tokens
    base_tokens = base.input_tokens + base.output_tokens
    routed_ms = sum(s.latency_ms for s in outcome.routed_steps)

    return {
        "status": "done",
        "request": request,
        "choice": {
            "tier": tier.name,
            "model": execute.model,
            "display": tier.display,
            "effort": tier.effort,
            "reason": outcome.reason,
        },
        "thinkless": {
            "cost": routed_cost,
            "triage_cost": triage.cost_usd,
            "answer_cost": execute.cost_usd,
            "question_cost": question_cost,
            "tokens": routed_tokens,
            "latency_ms": routed_ms,
            "answer": outcome.answer,
            "score": grades["routed_score"],
        },
        "baseline": {
            "model": base.model,
            "display": BASELINE.display,
            "effort": BASELINE.effort,
            "cost": base.cost_usd,
            "tokens": base_tokens,
            "latency_ms": base.latency_ms,
            "answer": outcome.baseline_answer,
            "score": grades["baseline_score"],
        },
        "savings": {
            "usd": base.cost_usd - routed_cost,
            "pct": pct(base.cost_usd - routed_cost, base.cost_usd),
            "tokens": base_tokens - routed_tokens,
            "tokens_pct": pct(base_tokens - routed_tokens, base_tokens),
            "ms": base.latency_ms - routed_ms,
        },
        "quality": {
            "thinkless": grades["routed_score"],
            "baseline": grades["baseline_score"],
            "retained_pct": pct(grades["routed_score"], grades["baseline_score"]),
        },
        "judge": {
            "model": grades["judge_model"],
            "comments": grades["judge_comments"],
            "cost": grades["judge_cost"],
        },
        "steps": [s.__dict__ for s in outcome.steps],
    }
