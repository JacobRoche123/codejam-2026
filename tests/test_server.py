from conftest import FakeLLM, verdict
from fastapi.testclient import TestClient

from thinkless.server import create_app


def test_ask_then_answer_flow():
    llm = FakeLLM([
        verdict(clarity="ambiguous", questions=["Quel langage ?"]),
        verdict(complexity="medium", brief="Script Python"),
    ])
    client = TestClient(create_app(llm))

    first = client.post("/api/ask", json={"request": "écris un script"}).json()
    assert first["status"] == "needs_answers"
    assert first["questions"] == ["Quel langage ?"]

    second = client.post(
        "/api/ask",
        json={"request": "écris un script", "answers": [{"question": "Quel langage ?", "answer": "Python"}]},
    ).json()
    assert second["status"] == "done"
    assert second["complexity"] == "medium"
    assert second["total_cost"] > 0


def test_route_endpoint_returns_advice_only():
    client = TestClient(create_app(FakeLLM([verdict(complexity="complex")])))
    advice = client.post("/api/route", json={"request": "Démontre ce théorème"}).json()
    assert advice["status"] == "route"
    assert advice["recommendation"]["model"] == "claude-opus-5-5"
    assert "answer" not in advice


def test_route_endpoint_uses_the_callers_models():
    client = TestClient(create_app(FakeLLM([verdict(complexity="medium")])))
    advice = client.post(
        "/api/route",
        json={"request": "Write a sort function", "available_models": ["a", "b", "c"]},
    ).json()
    assert advice["recommendation"]["model"] == "b"
    assert advice["recommendation"]["source"] == "your list"


def test_route_endpoint_rejects_too_many_models():
    client = TestClient(create_app(FakeLLM([])))
    response = client.post(
        "/api/route", json={"request": "x", "available_models": [f"m{i}" for i in range(21)]}
    )
    assert response.status_code == 422


def test_empty_request_is_a_validation_error():
    client = TestClient(create_app(FakeLLM([])))
    assert client.post("/api/ask", json={"request": ""}).status_code == 422


def test_benchmark_endpoint_and_static_page():
    client = TestClient(create_app(FakeLLM([])))
    assert "available" in client.get("/api/benchmark").json()
    assert client.get("/").status_code == 200
