"""ThinkLess as an MCP server: any MCP-compatible agent (Claude Code, Claude Desktop…) can ask
which model and effort level a request needs, before spending compute on it.

The agent starts this program itself and talks to it over stdin/stdout ("stdio"),
so nothing must be printed to stdout here.

Run by an agent with: uv --directory <project> run thinkless-mcp
"""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from .llm import LLM, AnthropicLLM
from .pipeline import Router

ROOT = Path(__file__).resolve().parents[2]

INSTRUCTIONS = (
    "ThinkLess saves compute. Before working on a user request, call choose_model with the "
    "request text. It returns the smallest Claude model and effort level that should be enough. "
    "Use that model when you can delegate the work (for example to a subagent). If it returns "
    "questions, ask the user first instead of guessing."
)


def create_server(llm: LLM | None = None) -> MCPServer:
    load_dotenv(ROOT / ".env.local")
    router = Router(llm or AnthropicLLM())
    server = MCPServer(name="thinkless", title="ThinkLess", instructions=INSTRUCTIONS)

    @server.tool(structured_output=True)
    def choose_model(request: str) -> dict[str, Any]:
        """Recommend the cheapest Claude model and effort level that can handle this request.

        Call this before answering or delegating a task. Returns status "route" with a
        recommendation (model, effort, reason), or status "needs_answers" with clarifying
        questions to ask the user first. Costs about 0.02 cents (one Haiku call).
        """
        advice = router.route(request)
        advice.pop("triage_step", None)  # trace details are for the demo page, not the agent
        return advice

    return server


def main() -> None:
    create_server().run("stdio")
