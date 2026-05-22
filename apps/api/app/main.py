from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import router as health_router
from app.routes.projects import router as projects_router
from app.routes.runs import router as runs_router
from app.providers.base import LLMProvider
from app.providers.openai_responses import OpenAIResponsesProvider
from app.storage.project_store import ProjectStore


def create_app(data_dir: Path | None = None, llm_provider: LLMProvider | None = None) -> FastAPI:
    app = FastAPI(title="HarnessDiff API", version="0.0.0-stage0")
    app.state.project_store = ProjectStore(data_dir=data_dir)
    app.state.llm_provider = llm_provider or OpenAIResponsesProvider()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    return app


app = create_app()
