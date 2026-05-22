from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.models.project import utc_now_iso
from app.models.run import RunDocument, RunStatus
from app.providers.base import LLMProvider, LLMRequest, ProviderEvent
from app.services.analysis_builder import build_run_analysis
from app.services.context_builder import build_instructions
from app.storage.json_io import write_json_atomic
from app.storage.project_store import ProjectStore


class RunOrchestrator:
    def __init__(self, store: ProjectStore, provider: LLMProvider) -> None:
        self.store = store
        self.provider = provider

    async def stream_run(self, run: RunDocument) -> AsyncIterator[dict[str, Any]]:
        self.store.update_run_status(run.project_id, run.id, RunStatus.running)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        pane_errors: list[dict[str, Any]] = []

        async def run_pane(pane: str) -> None:
            try:
                instructions = build_instructions(pane, run.harness_modules)
                self.store.prepare_pane_run(
                    run.project_id,
                    run.id,
                    pane,
                    run.prompt,
                    instructions,
                    run.harness_modules,
                )
                request = LLMRequest(
                    pane=pane,
                    model=run.model,
                    reasoning_effort=run.reasoning_effort,
                    instructions=instructions,
                    prompt=run.prompt,
                )
                async for event in self.provider.stream_text(request):
                    self.store.append_pane_event(run.project_id, run.id, pane, event)
                    if event.type == "delta":
                        self.store.append_pane_output_delta(run.project_id, run.id, pane, event.text or "")
                    elif event.type == "completed" and event.usage is not None:
                        self.store.write_pane_usage(run.project_id, run.id, pane, event.usage)
                    await queue.put(_event_to_payload(run.id, event))
            except Exception as exc:  # Provider errors must not kill the other pane.
                error_payload = {
                    "run_id": run.id,
                    "pane": pane,
                    "type": "error",
                    "message": str(exc),
                    "retryable": True,
                    "sequence": 0,
                }
                pane_errors.append(error_payload)
                self.store.append_error_event(run.project_id, run.id, pane, error_payload)
                await queue.put(error_payload)
            finally:
                await queue.put({"run_id": run.id, "pane": pane, "type": "pane_done"})

        tasks = [asyncio.create_task(run_pane(str(pane))) for pane in run.target_panes]
        remaining = len(tasks)
        try:
            while remaining:
                payload = await queue.get()
                if payload["type"] == "pane_done":
                    remaining -= 1
                    continue
                yield payload
            await asyncio.gather(*tasks)
            if pane_errors:
                self.store.update_run_status(run.project_id, run.id, RunStatus.failed)
                yield {"run_id": run.id, "type": "run_failed", "errors": pane_errors}
                return
            self.store.update_run_status(run.project_id, run.id, RunStatus.completed)
            analysis = build_run_analysis(
                run,
                self.store.get_run_dir(run.project_id, run.id),
                self.store.list_run_dirs(run.project_id),
            )
            self.store.write_run_analysis(
                run.project_id, run.id, analysis.model_dump(mode="json")
            )
            yield {
                "run_id": run.id,
                "type": "analysis_ready",
                "analysis": analysis.model_dump(mode="json"),
            }
            yield {"run_id": run.id, "type": "run_completed"}
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            self.store.update_run_status(run.project_id, run.id, RunStatus.cancelled)
            raise


def sse_encode(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_to_payload(run_id: str, event: ProviderEvent) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "pane": event.pane,
        "type": event.type,
        "text": event.text,
        "sequence": event.sequence,
        "response_id": event.response_id,
        "usage": event.usage,
    }
