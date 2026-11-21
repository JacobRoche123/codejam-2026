import asyncio

import pytest
from conftest import FakeLLM, verdict
from mcp.server.mcpserver.exceptions import ToolError

from thinkless.mcp_server import create_server


def test_choose_model_tool_is_listed_as_read_only_advice():
    server = create_server(FakeLLM([]))
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["choose_model"]
    assert tools[0].annotations.read_only_hint is True
    assert "advisor" in tools[0].title.lower()


class NoKeyLLM(FakeLLM):
    """Behaves like the SDK when no API key is configured."""

    def complete(self, **kwargs):
        raise TypeError("Could not resolve authentication method. Expected one of api_key...")


def test_missing_key_gives_the_agent_install_instructions():
    server = create_server(NoKeyLLM([]))
    with pytest.raises(ToolError, match="ANTHROPIC_API_KEY"):
        asyncio.run(server.call_tool("choose_model", {"request": "hi"}))


def test_choose_model_returns_a_recommendation():
    server = create_server(FakeLLM([verdict(complexity="simple", reason="question factuelle")]))
    result = asyncio.run(server.call_tool("choose_model", {"request": "Capitale du Japon ?"}))
    advice = result.structured_content
    assert advice["status"] == "route"
    assert advice["recommendation"]["model"] == "claude-haiku-5-5"
    assert "triage_step" not in advice
