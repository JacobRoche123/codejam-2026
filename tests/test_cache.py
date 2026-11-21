from conftest import FakeLLM, verdict

from thinkless.cache import find_similar, similarity
from thinkless.pipeline import Router


def test_similarity_scores():
    assert similarity("Bonjour  ?", "bonjour ?") == 1.0  # case and spaces are ignored
    assert similarity("capitale de l'Australie", "écris un poème") < 0.5


def test_find_similar_picks_the_closest_question():
    known = ["quelle est la capitale de la france ?", "écris un poème sur la mer"]
    match, score = find_similar("Quelle est la capitale française ?", known)
    assert match == "quelle est la capitale de la france ?"
    assert score > 0.75


def test_similar_question_confirmed_by_haiku_reuses_the_answer():
    llm = FakeLLM([
        verdict(),                                   # triage of the first question
        {"same": True, "reason": "même question"},   # Haiku confirms the second one
    ])
    router = Router(llm)
    first = router.ask("Quelle est la capitale de l'Australie ?")
    second = router.ask("Quelle est la capitale australienne ?")

    assert second.cached
    assert second.answer == first.answer
    assert [s.kind for s in second.steps] == ["cache_check"]
    assert "%" in second.steps[0].title
    assert 0 < second.total_cost < first.total_cost  # only the cheap check was paid
    assert len(llm.calls) == 3  # triage + answer for the first, one check for the second


def test_similar_but_different_question_is_answered_normally():
    llm = FakeLLM([
        verdict(),                                        # first question
        {"same": False, "reason": "pays différent"},      # France ≠ Allemagne
        verdict(),                                        # triage of the second question
    ])
    router = Router(llm)
    router.ask("Quelle est la capitale de la France ?")
    second = router.ask("Quelle est la capitale de l'Allemagne ?")

    assert not second.cached
    assert [s.kind for s in second.steps] == ["cache_check", "triage", "execute"]
    assert "refuse" in second.steps[0].detail


def test_unrelated_question_skips_the_check():
    llm = FakeLLM([verdict(), verdict()])
    router = Router(llm)
    router.ask("Quelle est la capitale de la France ?")
    second = router.ask("Écris un poème sur la mer")

    assert [s.kind for s in second.steps] == ["triage", "execute"]  # no Haiku check was paid
