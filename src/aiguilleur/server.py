"""FastAPI server: JSON API for the router plus the static demo page."""

import json
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


class AnswerIn(BaseModel):
    question: str
    answer: str


class AskIn(BaseModel):
    request: str = Field(min_length=1, max_length=8000)
    answers: list[AnswerIn] | None = None
    compare: bool = False


def create_app(llm: LLM | None = None) -> FastAPI:
    load_dotenv(ROOT / ".env.local")
    app = FastAPI(title="Aiguilleur")
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
        try:
            outcome = router().ask(body.request, answers, compare_baseline=body.compare)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise HTTPException(502, "Clé API refusée : vérifie .env.local.") from exc
        except anthropic.RateLimitError as exc:
            raise HTTPException(429, "Limite de requêtes atteinte, réessaie dans un instant.") from exc
        except anthropic.APIStatusError as exc:
            raise HTTPException(502, f"Erreur de l'API Claude ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise HTTPException(503, "Impossible de joindre l'API Claude.") from exc
        return outcome.to_dict()

    @app.get("/api/benchmark")
    def benchmark() -> dict:
        if not RESULTS_FILE.exists():
            return {"available": False}
        return {"available": True, **json.loads(RESULTS_FILE.read_text())}

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
