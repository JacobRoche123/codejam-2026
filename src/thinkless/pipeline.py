"""Router pipeline: cache -> triage -> (questions) -> execute, with a trace of every step."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

from .cache import confirm_same, find_similar
from .config import BASELINE, SIMILARITY_THRESHOLD, TIERS, TRIAGE, Tier, cost_usd
from .llm import LLM, LLMResult
from .triage import QA, triage

EXECUTOR_SYSTEM = (
    "You are a helpful assistant. Answer the user's request. The brief holds notes from a triage "
    "step (clarifications, format, length); follow them, but the original request wins on any "
    "conflict. Answer in the user's language and do not pad the answer."
)


def executor_prompt(request: str, brief: str) -> str:
    if not brief or brief == request:
        return request
    return f"<request>\n{request}\n</request>\n\n<brief>\n{brief}\n</brief>"

BASELINE_SYSTEM = "You are a helpful assistant. Answer in the user's language."


@dataclass
class Step:
    kind: str  # "cache" | "triage" | "execute" | "baseline"
    title: str
    model: str
    tier_label: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    detail: str = ""

    @classmethod
    def from_call(cls, kind: str, title: str, tier: Tier, call: LLMResult, detail: str = "") -> "Step":
        return cls(
            kind=kind,
            title=title,
            model=call.model,
            tier_label=tier.label,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            cache_read_tokens=call.cache_read_tokens,
            cost_usd=cost_usd(
                call.model,
                call.input_tokens,
                call.output_tokens,
                call.cache_read_tokens,
                call.cache_write_tokens,
            ),
            latency_ms=call.latency_ms,
            detail=detail,
        )


@dataclass
class Outcome:
    status: str  # "needs_answers" | "done"
    steps: list[Step]
    questions: list[str] = field(default_factory=list)
    complexity: str | None = None
    reason: str = ""
    brief: str = ""
    answer: str = ""
    cached: bool = False
    baseline_answer: str | None = None

    @property
    def routed_steps(self) -> list[Step]:
        return [s for s in self.steps if s.kind != "baseline"]

    @property
    def total_cost(self) -> float:
        return sum(s.cost_usd for s in self.routed_steps)

    @property
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.routed_steps)

    @property
    def baseline_cost(self) -> float | None:
        costs = [s.cost_usd for s in self.steps if s.kind == "baseline"]
        return costs[0] if costs else None

    @property
    def savings_pct(self) -> float | None:
        base = self.baseline_cost
        if not base:
            return None
        return round(100 * (1 - self.total_cost / base), 1)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            total_cost=self.total_cost,
            total_tokens=self.total_tokens,
            baseline_cost=self.baseline_cost,
            savings_pct=self.savings_pct,
        )
        return data


def cache_key(request: str, answers: list[QA] | None) -> str:
    norm = " ".join(request.lower().split())
    if answers:
        norm += "||" + "||".join(" ".join(qa.answer.lower().split()) for qa in answers)
    return norm


class Router:
    def __init__(self, llm: LLM):
        self.llm = llm
        self.cache: dict[str, Outcome] = {}

    def route(self, request: str, answers: list[QA] | None = None) -> dict[str, Any]:
        """Advisor mode: triage only. Says which model and effort to use, never answers."""
        request = request.strip()
        if not request:
            raise ValueError("The request is empty.")

        verdict = triage(self.llm, request, answers)
        detail = (
            f"{len(verdict.questions)} question(s) to ask first."
            if verdict.needs_answers
            else "Advice only: no answer generated."
        )
        step = Step.from_call("triage", "Triage", TRIAGE, verdict.call, detail)
        result: dict[str, Any] = {
            "status": "needs_answers" if verdict.needs_answers else "route",
            "questions": verdict.questions,
            "reason": verdict.reason,
            "triage_cost": step.cost_usd,
            "triage_step": asdict(step),
        }
        if not verdict.needs_answers:
            tier = TIERS[verdict.complexity]
            result["recommendation"] = {
                "tier": tier.name,
                "model": tier.model,
                "effort": tier.effort,
                "label": tier.label,
            }
            result["brief"] = verdict.brief
        return result

    def ask(
        self,
        request: str,
        answers: list[QA] | None = None,
        compare_baseline: bool = False,
    ) -> Outcome:
        request = request.strip()
        if not request:
            raise ValueError("The request is empty.")

        # Filter 0: the exact same question (ignoring case and spaces) is free.
        key = cache_key(request, answers)
        hit = self.cache.get(key)
        if hit is not None:
            step = Step(
                kind="cache",
                title="Answer already computed",
                model="cache",
                tier_label="Local cache",
                detail="Same request already handled: no model call.",
            )
            return self._from_cache(hit, [step])

        steps: list[Step] = []

        # Filters 1 and 2: a similar question, confirmed by Haiku, reuses the earlier answer.
        # Questions answered after a clarification round are left out to keep things simple.
        if not answers:
            known = [k for k in self.cache if "||" not in k]
            match, score = find_similar(request, known)
            if match is not None and score >= SIMILARITY_THRESHOLD:
                same, why, call = confirm_same(self.llm, request, match)
                percent = round(score * 100)
                step = Step.from_call(
                    "cache_check",
                    f"Similar question ({percent} %)",
                    TRIAGE,
                    call,
                    f"Close to \"{match}\". "
                    + ("Haiku confirms: same answer. " if same else "Haiku rejects: different answer. ")
                    + why,
                )
                if same:
                    return self._from_cache(self.cache[match], [step])
                steps.append(step)

        verdict = triage(self.llm, request, answers)
        tier = TIERS[verdict.complexity]
        triage_detail = (
            f"{len(verdict.questions)} question(s) to ask before answering."
            if verdict.needs_answers
            else f"\"{verdict.complexity}\" task → {tier.label}. {verdict.reason}"
        )
        steps.append(Step.from_call("triage", "Triage", TRIAGE, verdict.call, triage_detail))

        if verdict.needs_answers:
            return Outcome(
                status="needs_answers",
                steps=steps,
                questions=verdict.questions,
                complexity=verdict.complexity,
                reason=verdict.reason,
            )

        brief = verdict.brief or request
        # The baseline is only for the demo comparison: run it alongside so it adds no wait.
        pool = ThreadPoolExecutor(max_workers=1) if compare_baseline else None
        base_future = (
            pool.submit(
                self.llm.complete,
                model=BASELINE.model,
                effort=BASELINE.effort,
                system=BASELINE_SYSTEM,
                messages=[{"role": "user", "content": self._raw_prompt(request, answers)}],
            )
            if pool
            else None
        )
        call = self.llm.complete(
            model=tier.model,
            effort=tier.effort,
            system=EXECUTOR_SYSTEM,
            messages=[{"role": "user", "content": executor_prompt(request, brief)}],
        )
        detail = "" if call.model == tier.model else f"Automatic fallback to {call.model}."
        steps.append(Step.from_call("execute", "Answer", tier, call, detail))

        outcome = Outcome(
            status="done",
            steps=steps,
            complexity=verdict.complexity,
            reason=verdict.reason,
            brief=brief,
            answer=call.text,
        )

        if base_future is not None:
            base_call = base_future.result()
            pool.shutdown()
            outcome.steps.append(
                Step.from_call(
                    "baseline",
                    "Comparison: everything on Opus",
                    BASELINE,
                    base_call,
                    "What the same request would cost without routing.",
                )
            )
            outcome.baseline_answer = base_call.text

        self.cache[key] = outcome
        return outcome

    @staticmethod
    def _from_cache(hit: Outcome, steps: list[Step]) -> Outcome:
        """Builds the outcome for a cache hit: the earlier answer, with this request's own steps."""
        return Outcome(
            status="done",
            steps=steps,
            complexity=hit.complexity,
            reason=hit.reason,
            brief=hit.brief,
            answer=hit.answer,
            cached=True,
        )

    @staticmethod
    def _raw_prompt(request: str, answers: list[QA] | None) -> str:
        if not answers:
            return request
        extra = "\n".join(f"- {qa.question} {qa.answer}" for qa in answers)
        return f"{request}\n\nDetails:\n{extra}"
