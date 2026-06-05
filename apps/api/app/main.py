from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.audio import router as audio_router
from app.routes.health import router as health_router
from app.routes.projects import router as projects_router
from app.routes.runs import router as runs_router
from app.routes.skills import router as skills_router
from app.routes.subagents import router as subagents_router
from app.routes.tools import router as tools_router
from app.providers.base import LLMProvider
from app.providers.openai_responses import OpenAIResponsesProvider
from app.services.audio_transcription import AudioTranscriber, OpenAIAudioTranscriber
from app.services.skill_store import SkillStore
from app.services.tool_runtime import ToolAnythingRuntime, create_default_tool_runtime
from app.storage.project_store import ProjectStore


_DEFAULT_TOOL_RUNTIME = object()


def create_app(
    data_dir: Path | None = None,
    harnessdiff_home: Path | None = None,
    llm_provider: LLMProvider | None = None,
    audio_transcriber: AudioTranscriber | None = None,
    tool_runtime: ToolAnythingRuntime | None | object = _DEFAULT_TOOL_RUNTIME,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.skill_store.ensure_dirs()
        yield

    app = FastAPI(title="HarnessDiff API", version="0.0.0-stage0", lifespan=lifespan)
    app.state.project_store = ProjectStore(data_dir=data_dir)
    app.state.skill_store = (
        SkillStore(home_dir=harnessdiff_home) if harnessdiff_home is not None else SkillStore()
    )
    app.state.llm_provider = llm_provider or OpenAIResponsesProvider()
    app.state.audio_transcriber = audio_transcriber or OpenAIAudioTranscriber()
    app.state.tool_runtime = (
        create_default_tool_runtime()
        if tool_runtime is _DEFAULT_TOOL_RUNTIME
        else tool_runtime
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(audio_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(skills_router, prefix="/api")
    app.include_router(subagents_router, prefix="/api")
    app.include_router(tools_router, prefix="/api")

    return app


app = create_app()
