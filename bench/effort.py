"""Thinking-mode comparison: the same model at effort low, medium and high.

Effort controls how much the model reasons before answering. Reasoning produces
"thinking" tokens, billed as output tokens: fewer tokens means less compute.
For each task we measure tokens, cost and time per effort level, and have the
judge grade low and medium against high (the reference).

Writes bench/effort.json, which the demo page reads.
Usage: uv run python bench/effort.py
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from run import judge

from thinkless.config import cost_usd
from thinkless.llm import AnthropicLLM

ROOT = Path(__file__).resolve().parents[1]
MODEL = "claude-sonnet-5-5"
EFFORTS = ["low", "medium", "high"]
TASK_IDS = ["regex", "resume", "python-csv", "explication", "preuve", "algo"]
SYSTEM = "You are a helpful assistant. Answer in the user's language and do not pad the answer."


def run_task(llm: AnthropicLLM, task: dict) -> list[dict]:
    answers = {}
    rows = []
    for effort in EFFORTS:
        call = llm.complete(
            model=MODEL,
            effort=effort,
            system=SYSTEM,
            messages=[{"role": "user", "content": task["request"]}],
        )
        answers[effort] = call.text
        rows.append({
            "id": task["id"],
            "effort": effort,
            "output_tokens": call.output_tokens,
            "cost": cost_usd(call.model, call.input_tokens, call.output_tokens,
                             call.cache_read_tokens, call.cache_write_tokens),
            "ms": call.latency_ms,
        })
    # Grade each lighter mode against "high", the reference.
    for row in rows:
        if row["effort"] == "high":
            row["score"], row["reference_score"] = None, None
            continue
        grades = judge(llm, task["request"], answers[row["effort"]], answers["high"])
        row["score"], row["reference_score"] = grades["routed_score"], grades["baseline_score"]
        row["judge_cost"] = grades["judge_cost"]
    return rows


def main() -> None:
    load_dotenv(ROOT / ".env.local")
    tasks = [t for t in json.loads((ROOT / "bench" / "tasks.json").read_text()) if t["id"] in TASK_IDS]
    llm = AnthropicLLM()

    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = [row for task_rows in pool.map(lambda t: run_task(llm, t), tasks) for row in task_rows]

    summary = []
    for effort in EFFORTS:
        mine = [r for r in rows if r["effort"] == effort]
        graded = [r for r in mine if r["score"] is not None]
        summary.append({
            "effort": effort,
            "avg_output_tokens": round(sum(r["output_tokens"] for r in mine) / len(mine)),
            "total_cost": sum(r["cost"] for r in mine),
            "avg_seconds": round(sum(r["ms"] for r in mine) / len(mine) / 1000, 1),
            "avg_score": round(sum(r["score"] for r in graded) / len(graded), 2) if graded else None,
            "avg_reference_score": round(sum(r["reference_score"] for r in graded) / len(graded), 2) if graded else None,
        })

    for s in summary:
        print(f"{s['effort']:<7} {s['avg_output_tokens']:>5} jetons  ${s['total_cost']:.4f}  {s['avg_seconds']} s"
              f"  qualité {s['avg_score']} vs high {s['avg_reference_score']}")
    (ROOT / "bench" / "effort.json").write_text(
        json.dumps({"model": MODEL, "tasks": len(tasks), "summary": summary, "rows": rows},
                   indent=2, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
