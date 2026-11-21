import asyncio

from conftest import FakeLLM, verdict

from thinkless.mcp_server import create_server


def test_choose_model_tool_is_listed():
    server = create_server(FakeLLM([]))
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["choose_model"]


def test_choose_model_returns_a_recommendation():
    server = create_server(FakeLLM([verdict(complexity="simple", reason="question factuelle")]))
    result = asyncio.run(server.call_tool("choose_model", {"request": "Capitale du Japon ?"}))
    advice = result.structured_content
    assert advice["status"] == "route"
    assert advice["recommendation"]["model"] == "claude-haiku-5-5"
    assert "triage_step" not in advice
