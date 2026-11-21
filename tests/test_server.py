from conftest import FakeLLM, verdict
from fastapi.testclient import TestClient

from aiguilleur.server import create_app


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


def test_empty_request_is_a_validation_error():
    client = TestClient(create_app(FakeLLM([])))
    assert client.post("/api/ask", json={"request": ""}).status_code == 422


def test_benchmark_endpoint_and_static_page():
    client = TestClient(create_app(FakeLLM([])))
    assert "available" in client.get("/api/benchmark").json()
    assert client.get("/").status_code == 200
