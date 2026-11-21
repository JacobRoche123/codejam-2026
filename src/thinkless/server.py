"""FastAPI server: JSON API for the router plus the static demo page."""

import json
from collections.abc import Callable
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import BASELINE, TIERS, TRIAGE
from .llm import LLM, AnthropicLLM
from .pipeline import Router
from .triage import QA

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
RESULTS_FILE = ROOT / "bench" / "results.json"
EFFORT_FILE = ROOT / "bench" / "effort.json"


class AnswerIn(BaseModel):
    question: str
    answer: str


class AskIn(BaseModel):
    request: str = Field(min_length=1, max_length=8000)
    answers: list[AnswerIn] | None = None
    compare: bool = False


def create_app(llm: LLM | None = None) -> FastAPI:
    load_dotenv(ROOT / ".env.local")
    app = FastAPI(title="ThinkLess")
    state: dict[str, Router] = {}

    def router() -> Router:
        if "router" not in state:
            state["router"] = Router(llm or AnthropicLLM())
        return state["router"]

    @app.get("/api/config")
    def config() -> dict:
        return {
            "triage": TRIAGE.label,
            "tiers": {name: tier.label for name, tier in TIERS.items()},
            "baseline": BASELINE.label,
        }

    @app.post("/api/ask")
    def ask(body: AskIn) -> dict:
        answers = [QA(a.question, a.answer) for a in body.answers] if body.answers else None
        return run_safely(
            lambda: router().ask(body.request, answers, compare_baseline=body.compare).to_dict()
        )

    @app.post("/api/route")
    def route(body: AskIn) -> dict:
        """Advisor mode: returns which model and effort to use, without answering."""
        answers = [QA(a.question, a.answer) for a in body.answers] if body.answers else None
        return run_safely(lambda: router().route(body.request, answers))

    def run_safely(action: Callable[[], dict]) -> dict:
        """Runs a router call and turns API errors into clear messages."""
        try:
            return action()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise HTTPException(502, "API key rejected: check .env.local.") from exc
        except anthropic.RateLimitError as exc:
            raise HTTPException(429, "Rate limit reached, try again in a moment.") from exc
        except anthropic.APIStatusError as exc:
            raise HTTPException(502, f"Claude API error ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise HTTPException(503, "Cannot reach the Claude API.") from exc

    @app.get("/api/benchmark")
    def benchmark() -> dict:
        if not RESULTS_FILE.exists():
            return {"available": False}
        data = {"available": True, **json.loads(RESULTS_FILE.read_text())}
        if EFFORT_FILE.exists():
            data["effort"] = json.loads(EFFORT_FILE.read_text())
        return data

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
