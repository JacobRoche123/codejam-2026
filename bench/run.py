"""Benchmark: the router vs. sending everything to Opus 5.5.

For each task in bench/tasks.json:
  1. run the router (answering its questions from the task's "context"),
  2. run the baseline (Opus 5.5, effort high, raw request),
  3. ask a judge model to grade both answers blind.

Writes bench/results.json, which the demo page reads.
Usage: uv run python bench/run.py [--limit N]
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

from thinkless.config import cost_usd
from thinkless.llm import AnthropicLLM
from thinkless.pipeline import Router
from thinkless.triage import QA

ROOT = Path(__file__).resolve().parents[1]
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


def judge_once(llm: AnthropicLLM, request: str, a: str, b: str) -> tuple[int, int, str, float]:
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
    cost = cost_usd(call.model, call.input_tokens, call.output_tokens)
    return int(data["score_a"]), int(data["score_b"]), data["comment"], cost


def judge(llm: AnthropicLLM, request: str, routed: str, baseline: str) -> dict:
    """Grades twice with the answers in both orders and averages, to cancel position bias and noise."""
    r1, b1, c1, cost1 = judge_once(llm, request, routed, baseline)
    b2, r2, c2, cost2 = judge_once(llm, request, baseline, routed)
    return {
        "routed_score": (r1 + r2) / 2,
        "baseline_score": (b1 + b2) / 2,
        "judge_comments": [c1, c2],
        "judge_cost": cost1 + cost2,
    }


def run_task(llm: AnthropicLLM, task: dict) -> dict:
    router = Router(llm)
    # The baseline only runs once the router actually answers, so a question round costs no Opus call.
    outcome = router.ask(task["request"], compare_baseline=True)
    asked = list(outcome.questions)
    routed_cost = outcome.total_cost
    if outcome.status == "needs_answers":
        # The baseline gets the same context for free; the router pays for its question round.
        context = task.get("context", "Choisis une option raisonnable.")
        answers = [QA(q, context) for q in outcome.questions]
        outcome = router.ask(task["request"], answers, compare_baseline=True)
        routed_cost += outcome.total_cost

    baseline = next(s for s in outcome.steps if s.kind == "baseline")
    grades = judge(llm, task["request"], outcome.answer, outcome.baseline_answer or "")
    execute = next(s for s in outcome.steps if s.kind == "execute")
    return {
        "id": task["id"],
        "request": task["request"],
        "expected": task["expected"],
        "chosen": outcome.complexity,
        "model": execute.model,
        "questions": asked,
        "routed_cost": routed_cost,
        "baseline_cost": baseline.cost_usd,
        "routed_tokens": outcome.total_tokens,
        "baseline_tokens": baseline.input_tokens + baseline.output_tokens,
        "routed_ms": sum(s.latency_ms for s in outcome.routed_steps),
        "baseline_ms": baseline.latency_ms,
        **grades,
        "brief": outcome.brief,
        "routed_answer": outcome.answer,
        "baseline_answer": outcome.baseline_answer,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env.local")
    tasks = json.loads((ROOT / "bench" / "tasks.json").read_text())[: args.limit]
    llm = AnthropicLLM()

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda t: run_task(llm, t), tasks))

    for r in rows:
        print(f"{r['id']:<16} {r['chosen']:<8} ${r['routed_cost']:.4f} vs ${r['baseline_cost']:.4f}"
              f"  qualité {r['routed_score']}/10 vs {r['baseline_score']}/10")

    routed = sum(r["routed_cost"] for r in rows)
    baseline = sum(r["baseline_cost"] for r in rows)
    summary = {
        "tasks": len(rows),
        "routed_cost": routed,
        "baseline_cost": baseline,
        "savings_pct": round(100 * (1 - routed / baseline), 1) if baseline else 0,
        "routed_tokens": sum(r["routed_tokens"] for r in rows),
        "baseline_tokens": sum(r["baseline_tokens"] for r in rows),
        "routed_quality": round(sum(r["routed_score"] for r in rows) / len(rows), 2),
        "baseline_quality": round(sum(r["baseline_score"] for r in rows) / len(rows), 2),
        "tier_match": sum(r["chosen"] == r["expected"] for r in rows),
        "judge_model": JUDGE_MODEL,
        "judge_cost": sum(r["judge_cost"] for r in rows),
    }
    print(json.dumps(summary, indent=2))
    (ROOT / "bench" / "results.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
