"""Blind quality judge, shared by the benchmark and the savings report.

A judge model grades two answers to the same request without knowing which one came from
ThinkLess. It grades twice, with the answers in both orders, and the scores are averaged: this
cancels position bias (models tend to favour the first answer) and smooths out noise.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .config import cost_usd
from .llm import LLM

JUDGE_MODEL, JUDGE_EFFORT = "claude-sonnet-5-5", "medium"

JUDGE_SYSTEM = """You grade two answers to the same request. Judge only correctness, completeness
and whether the answer does what was asked. Length is not a virtue: a short correct answer to a
short question deserves full marks. Score each answer from 1 to 10."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score_a": {"type": "integer"},
        "score_b": {"type": "integer"},
        "comment": {"type": "string"},
    },
    "required": ["score_a", "score_b", "comment"],
    "additionalProperties": False,
}


def judge_once(llm: LLM, request: str, a: str, b: str) -> tuple[int, int, str, float]:
    """One grading pass. Returns (score_a, score_b, comment, cost_usd)."""
    call = llm.complete(
        model=JUDGE_MODEL,
        effort=JUDGE_EFFORT,
        system=JUDGE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"<request>\n{request}\n</request>\n\n<answer_a>\n{a}\n</answer_a>\n\n<answer_b>\n{b}\n</answer_b>",
        }],
        max_tokens=4000,
        json_schema=JUDGE_SCHEMA,
    )
    data = json.loads(call.text)
    cost = cost_usd(call.model, call.input_tokens, call.output_tokens,
                    call.cache_read_tokens, call.cache_write_tokens)
    return int(data["score_a"]), int(data["score_b"]), data["comment"], cost


def judge(llm: LLM, request: str, routed: str, baseline: str) -> dict[str, Any]:
    """Grades in both orders (in parallel) and averages the scores."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(judge_once, llm, request, routed, baseline)
        second = pool.submit(judge_once, llm, request, baseline, routed)
        r1, b1, c1, cost1 = first.result()
        b2, r2, c2, cost2 = second.result()
    return {
        "routed_score": (r1 + r2) / 2,
        "baseline_score": (b1 + b2) / 2,
        "judge_comments": [c1, c2],
        "judge_cost": cost1 + cost2,
        "judge_model": JUDGE_MODEL,
    }
