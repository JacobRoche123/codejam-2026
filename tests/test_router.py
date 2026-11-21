import pytest
from conftest import FakeLLM, verdict

from thinkless.config import cost_usd
from thinkless.llm import LLMResult
from thinkless.pipeline import Router, clean_models, pick_from_list
from thinkless.triage import QA, parse_verdict


def test_cost_matches_published_prices():
    # 1M input + 1M output on Haiku 5.5 = $0.10 + $0.50
    assert cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)
    # Cache reads are billed at 10% of the input price.
    assert cost_usd("claude-opus-5-5", 0, 0, cache_read_tokens=1_000_000) == pytest.approx(0.40)


@pytest.mark.parametrize(
    ("complexity", "model", "effort"),
    [
        ("simple", "claude-haiku-5-5", "low"),
        ("medium", "claude-sonnet-5-5", "medium"),
        ("complex", "claude-opus-5-5", "high"),
    ],
)
def test_routes_each_tier_to_its_model(complexity, model, effort):
    llm = FakeLLM([verdict(complexity=complexity)])
    outcome = Router(llm).ask("question")
    assert outcome.status == "done"
    assert llm.calls[0]["model"] == "claude-haiku-5-5"  # triage is always the cheap model
    assert llm.calls[1]["model"] == model
    assert llm.calls[1]["effort"] == effort
    assert [s.kind for s in outcome.steps] == ["triage", "execute"]


def test_executor_receives_original_request_and_brief():
    llm = FakeLLM([verdict(brief="Brief précis en 3 points")])
    Router(llm).ask("positif ou négatif ?")
    prompt = llm.calls[1]["messages"][0]["content"]
    assert "<request>\npositif ou négatif ?\n</request>" in prompt  # the user's words are never lost
    assert "Brief précis en 3 points" in prompt


def test_ambiguous_request_asks_questions_without_executing():
    llm = FakeLLM([verdict(clarity="ambiguous", questions=["Quel langage ?", "Pour qui ?"])])
    outcome = Router(llm).ask("écris un script")
    assert outcome.status == "needs_answers"
    assert outcome.questions == ["Quel langage ?", "Pour qui ?"]
    assert len(llm.calls) == 1


def test_answers_are_sent_to_triage_and_force_execution():
    llm = FakeLLM([verdict(clarity="ambiguous", questions=["Encore une ?"], complexity="medium")])
    outcome = Router(llm).ask("écris un script", answers=[QA("Quel langage ?", "Python")])
    assert outcome.status == "done"  # never a second round of questions
    assert "Python" in llm.calls[0]["messages"][0]["content"]


def test_at_most_three_questions():
    raw = verdict(clarity="ambiguous", questions=["a", "b", "c", "d", "e"])
    call = LLMResult(__import__("json").dumps(raw), "claude-haiku-5-5", 1, 1, 0, 0, 1, "end_turn")
    assert parse_verdict(call, answered=False).questions == ["a", "b", "c"]


def test_unknown_complexity_falls_back_to_medium():
    call = LLMResult('{"clarity":"clear","questions":[],"complexity":"huge","reason":"","brief":"x"}',
                     "claude-haiku-5-5", 1, 1, 0, 0, 1, "end_turn")
    assert parse_verdict(call, answered=False).complexity == "medium"


def test_repeated_request_is_served_from_cache_for_free():
    llm = FakeLLM([verdict()])
    router = Router(llm)
    first = router.ask("Capitale de la France ?")
    second = router.ask("  capitale de la   FRANCE ? ")
    assert second.cached and second.total_cost == 0
    assert second.answer == first.answer
    assert len(llm.calls) == 2  # no new calls for the cached request


def test_baseline_comparison_reports_savings():
    llm = FakeLLM([verdict(complexity="simple")])
    outcome = Router(llm).ask("question", compare_baseline=True)
    assert outcome.steps[-1].kind == "baseline"
    assert sorted(c["model"] for c in llm.calls[1:]) == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert outcome.baseline_cost > outcome.total_cost
    assert 0 < outcome.savings_pct < 100


def test_fallback_model_is_shown_in_trace():
    llm = FakeLLM([verdict(complexity="complex")], fallback_to="claude-opus-4-8")
    outcome = Router(llm).ask("question")
    assert outcome.steps[1].model == "claude-opus-4-8"
    assert "fallback" in outcome.steps[1].detail


def test_advisor_mode_recommends_without_answering():
    llm = FakeLLM([verdict(complexity="medium", reason="du code à écrire")])
    advice = Router(llm).route("Écris une fonction de tri")
    assert advice["status"] == "route"
    assert advice["recommendation"] == {
        "tier": "medium",
        "size": "medium",
        "model": "claude-sonnet-5-5",
        "effort": "medium",
        "label": "Sonnet 5.5 · effort medium",
        "source": "default Claude models",
    }
    assert len(llm.calls) == 1  # only the triage ran: no answer was generated
    assert advice["triage_cost"] > 0


@pytest.mark.parametrize(
    ("complexity", "models", "expected"),
    [
        ("simple", ["s", "m", "l"], "s"),
        ("medium", ["s", "m", "l"], "m"),
        ("complex", ["s", "m", "l"], "l"),
        ("medium", ["s", "l"], "l"),            # two middles: prudence picks the larger
        ("medium", ["a", "b", "c", "d"], "c"),  # same with four models
        ("complex", ["only"], "only"),          # one model: always that one
    ],
)
def test_pick_from_list(complexity, models, expected):
    assert pick_from_list(complexity, models) == expected


def test_clean_models_trims_dedups_and_caps():
    assert clean_models(["  a ", "", "b", "a", "   "]) == ["a", "b"]
    assert len(clean_models([f"m{i}" for i in range(50)])) == 20
    assert clean_models(None) == []


def test_advisor_mode_uses_the_agents_own_models():
    llm = FakeLLM([verdict(complexity="complex")])
    advice = Router(llm).route(
        "Design a system", available_models=["tiny-model", "mid-model", "big-model"]
    )
    rec = advice["recommendation"]
    assert rec["model"] == "big-model"
    assert rec["size"] == "large"
    assert rec["source"] == "your list"
    assert "claude" not in rec["label"].lower()


def test_advisor_mode_passes_questions_through():
    llm = FakeLLM([verdict(clarity="ambiguous", questions=["Pour qui ?"])])
    advice = Router(llm).route("Écris un courriel")
    assert advice["status"] == "needs_answers"
    assert advice["questions"] == ["Pour qui ?"]
    assert "recommendation" not in advice


def test_empty_request_is_rejected():
    with pytest.raises(ValueError):
        Router(FakeLLM([])).ask("   ")
