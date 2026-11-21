"""ThinkLess as an MCP server: any MCP-compatible agent (Claude Code, Claude Desktop, Cursor…)
can ask which model and effort level a request needs, before spending compute on it.

The agent starts this program itself and talks to it over stdin/stdout ("stdio"),
so nothing must be printed to stdout here.

Install for any user, in one command (each user brings their own Anthropic API key):
    claude mcp add thinkless -e ANTHROPIC_API_KEY=sk-ant-... -- \
        uvx --from git+https://github.com/JacobRoche123/codejam-2026 thinkless-mcp
"""

from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .llm import LLM, AnthropicLLM
from .pipeline import Router

ROOT = Path(__file__).resolve().parents[2]

INSTRUCTIONS = (
    "ThinkLess is an advisor that saves compute, for any AI provider. Before working on a user "
    "request, call choose_model with the request text and, if you know them, the models you can "
    "use, ordered from smallest/cheapest to largest. It returns the smallest model and effort "
    "level that should be enough. Use that model when you can delegate the work (for example to "
    "a subagent). If it returns questions, ask the user first instead of guessing."
)

MISSING_KEY = (
    "ThinkLess needs an Anthropic API key to run its triage. Reinstall it with "
    "-e ANTHROPIC_API_KEY=<your key>, for example: claude mcp add thinkless "
    "-e ANTHROPIC_API_KEY=sk-ant-... -- uvx --from "
    "git+https://github.com/JacobRoche123/codejam-2026 thinkless-mcp"
)


def create_server(llm: LLM | None = None) -> MCPServer:
    # Local development: read the key from the project's .env.local if it exists.
    load_dotenv(ROOT / ".env.local")
    server = MCPServer(name="thinkless", title="ThinkLess advisor", instructions=INSTRUCTIONS)
    state: dict[str, Router] = {}

    def router() -> Router:
        """Creates the Claude client on first use."""
        if "router" not in state:
            state["router"] = Router(llm or AnthropicLLM())
        return state["router"]

    @server.tool(
        title="ThinkLess advisor: pick the cheapest sufficient model",
        annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True),
        structured_output=True,
    )
    def choose_model(request: str, available_models: list[str] | None = None) -> dict[str, Any]:
        """Recommend the cheapest model and effort level that can handle this request.

        Works with any provider: pass `available_models`, the models you can use, ordered
        from smallest/cheapest to largest (for example ["small-model", "medium-model",
        "large-model"]); the advice then names one of them, with a neutral size (small,
        medium, large). Without the list, it recommends Claude models (Haiku, Sonnet, Opus).

        Advice only: it never answers the request and changes nothing. Call it before
        answering or delegating a task. Returns status "route" with a recommendation
        (model, size, effort, reason), or status "needs_answers" with clarifying questions
        to ask the user first. Costs about 0.02 cents (one Claude Haiku call).
        """
        # ToolError is the one exception whose message the MCP library passes to the agent;
        # any other exception is reported as a generic crash.
        try:
            advice = router().route(request, available_models=available_models)
        except ValueError as exc:  # e.g. an empty request
            raise ToolError(str(exc)) from exc
        except anthropic.AuthenticationError as exc:  # a key was given but is wrong
            raise ToolError(MISSING_KEY) from exc
        except TypeError as exc:  # no key at all: the SDK cannot build the request
            if "authentication" not in str(exc):
                raise
            raise ToolError(MISSING_KEY) from exc
        advice.pop("triage_step", None)  # trace details are for the demo page, not the agent
        return advice

    return server


def main() -> None:
    create_server().run("stdio")
