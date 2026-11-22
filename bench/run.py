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

from thinkless.judge import JUDGE_MODEL, judge  # shared with the savings report (effort.py imports judge from here)
from thinkless.llm import AnthropicLLM
from thinkless.pipeline import Router
from thinkless.triage import QA

ROOT = Path(__file__).resolve().parents[1]


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
