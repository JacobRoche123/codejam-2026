"""The triage agent: decides whether to ask questions and which model to use."""

import json
from dataclasses import dataclass, field

from .config import MAX_QUESTIONS, TRIAGE, TIERS
from .llm import LLM, LLMResult

TRIAGE_SYSTEM = """You are the triage step that runs before an assistant answers a request.
Your goal: make sure the final answer is right while spending as little compute as possible.
Two things waste compute: answering the wrong question, and using a bigger model than the task needs.

Read the request, plus any answers the user already gave to your earlier questions, then decide:

clarity
- "ambiguous" only when a missing detail would change the answer a lot and no sensible default exists
  (for example: which programming language, who the audience is, a hard constraint like length or budget).
- "clear" otherwise. Prefer a sensible default over a question.
- If the user already answered earlier questions, always return "clear".

questions
- When ambiguous: 1 to 3 short questions, each answerable in a few words. Otherwise an empty list.

complexity (pick the lowest tier that will still produce an answer as good as the strongest model's)
- "simple": facts, definitions, short rewrites, translations, classification, small arithmetic.
  The full answer fits in about 150 words and contains at most one line of code.
  Simple also requires that the facts are widely known: niche, local or recent facts (a small
  organization, a campus club, a local rule) need a model with broader knowledge, so pick medium.
  The same goes when one small detail decides correctness (regular expressions, formulas, dates).
- "medium": anything that writes more than one line of code, multi-step explanations, summaries
  of several points, comparisons, plans, emails or letters with specific requirements.
- "complex": hard reasoning, proofs, non-trivial algorithms, system design with trade-offs,
  subtle debugging, long multi-part deliverables.
- When torn between two tiers, pick the higher one: a wrong cheap answer wastes the whole call.

reason
- One short sentence explaining the tier choice, in the user's language.

brief
- Short notes for the assistant that will answer: the user's answers, the expected format and a
  target length. The assistant also sees the original request, which wins on any conflict.
- Never change what the user asked: keep their exact options, constraints and wording.
  If they ask "positive or negative", do not add a third option. Write in the user's language."""

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "clarity": {"type": "string", "enum": ["clear", "ambiguous"]},
        "questions": {"type": "array", "items": {"type": "string"}},
        "complexity": {"type": "string", "enum": ["simple", "medium", "complex"]},
        "reason": {"type": "string"},
        "brief": {"type": "string"},
    },
    "required": ["clarity", "questions", "complexity", "reason", "brief"],
    "additionalProperties": False,
}


@dataclass
class QA:
    question: str
    answer: str


@dataclass
class Verdict:
    clarity: str
    questions: list[str]
    complexity: str
    reason: str
    brief: str
    call: LLMResult = field(repr=False)

    @property
    def needs_answers(self) -> bool:
        return self.clarity == "ambiguous" and bool(self.questions)


def build_prompt(request: str, answers: list[QA] | None) -> str:
    parts = [f"<request>\n{request}\n</request>"]
    if answers:
        lines = "\n".join(f"Q: {qa.question}\nA: {qa.answer}" for qa in answers)
        parts.append(f"<answers_from_user>\n{lines}\n</answers_from_user>")
    return "\n\n".join(parts)


def parse_verdict(call: LLMResult, answered: bool) -> Verdict:
    data = json.loads(call.text)
    complexity = data.get("complexity", "medium")
    if complexity not in TIERS:
        complexity = "medium"
    questions = [q.strip() for q in data.get("questions", []) if q.strip()][:MAX_QUESTIONS]
    clarity = data.get("clarity", "clear")
    # One round of questions at most: once the user answered, we execute.
    if answered or not questions:
        clarity = "clear"
        questions = []
    return Verdict(
        clarity=clarity,
        questions=questions,
        complexity=complexity,
        reason=data.get("reason", "").strip(),
        brief=data.get("brief", "").strip(),
        call=call,
    )


def triage(llm: LLM, request: str, answers: list[QA] | None = None) -> Verdict:
    call = llm.complete(
        model=TRIAGE.model,
        effort=TRIAGE.effort,
        system=TRIAGE_SYSTEM,
        messages=[{"role": "user", "content": build_prompt(request, answers)}],
        max_tokens=4000,
        json_schema=TRIAGE_SCHEMA,
    )
    return parse_verdict(call, answered=bool(answers))
