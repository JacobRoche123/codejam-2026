from conftest import FakeLLM, verdict
from fastapi.testclient import TestClient

from thinkless.llm import LLMResult
from thinkless.report import build_report, pct
from thinkless.server import create_app


class JudgeAwareLLM(FakeLLM):
    """FakeLLM that also answers the judge's schema (score_a / score_b)."""

    def complete(self, *, model, effort, system, messages, max_tokens=16000, json_schema=None):
        if json_schema and "score_a" in json_schema["properties"]:
            self.calls.append({"model": model, "judge": True})
            return LLMResult('{"score_a": 8, "score_b": 9, "comment": "both fine"}', model, 900, 60, 0, 0, 5, "end_turn")
        return super().complete(model=model, effort=effort, system=system, messages=messages,
                                max_tokens=max_tokens, json_schema=json_schema)


def test_pct():
    assert pct(1, 4) == 25.0
    assert pct(1, 0) is None


def test_report_compares_thinkless_with_opus_and_grades_both():
    llm = JudgeAwareLLM([verdict(complexity="simple")])
    report = build_report(llm, "Capital of Australia?")
    assert report["status"] == "done"
    assert report["choice"]["display"] == "Claude Haiku 5.5"
    assert report["baseline"]["display"] == "Claude Opus 5.5"
    # The FakeLLM returns the same token counts for both, so the saving comes from prices only.
    assert report["savings"]["usd"] > 0 and 0 < report["savings"]["pct"] < 100
    # Both judge passes ran, in both orders, and the scores are averaged.
    assert sum(1 for c in llm.calls if c.get("judge")) == 2
    assert report["quality"]["thinkless"] == 8.5 and report["quality"]["baseline"] == 8.5
    assert report["judge"]["cost"] > 0


def test_report_asks_questions_first_and_carries_their_cost():
    llm = JudgeAwareLLM([verdict(clarity="ambiguous", questions=["Which language?"])])
    first = build_report(llm, "Write a script")
    assert first["status"] == "needs_answers"
    assert first["question_cost"] > 0


def test_report_endpoint():
    client = TestClient(create_app(JudgeAwareLLM([verdict(complexity="medium")])))
    data = client.post("/api/report", json={"request": "Write a sort function", "question_cost": 0.001}).json()
    assert data["status"] == "done"
    assert data["choice"]["display"] == "Claude Sonnet 5.5"
    assert data["thinkless"]["question_cost"] == 0.001
