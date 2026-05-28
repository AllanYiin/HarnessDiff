from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from app.models.project import ProjectCreate
from app.models.run import ProfileConfig, RunCreate
from app.providers.base import LLMProvider, LLMRequest, ProviderEvent
from app.services.analysis_builder import build_run_analysis
from app.services.chat_tool_runtime import (
    PARALLEL_OPENAI_NAME,
    PARALLEL_TOOL_NAME,
    ChatToolRuntime,
)
from app.services.subagent_definitions import SubagentDefinition
from app.services.subagent_runtime import (
    SUBAGENT_OPENAI_NAME,
    SUBAGENT_TOOL_NAME,
    SubagentToolRuntime,
)
from app.storage.project_store import ProjectStore


def test_chat_tool_runtime_exposes_subagent_tool_and_delegates_standard_tool() -> None:
    standard = FakeStandardRuntime()
    subagent = FakeSubagentRuntime()
    runtime = ChatToolRuntime(standard_runtime=standard, subagent_runtime=subagent)

    assert (
        "standard.shell.bash",
        "standard.fs.read",
        SUBAGENT_TOOL_NAME,
        PARALLEL_TOOL_NAME,
    ) == runtime.list_tool_names()
    openai_tool_names = [tool["name"] for tool in runtime.list_openai_tools()]
    assert openai_tool_names[0] == "standard_shell_bash"
    openai_names = set(openai_tool_names)
    assert SUBAGENT_OPENAI_NAME in openai_names
    assert PARALLEL_OPENAI_NAME in openai_names

    standard_result = asyncio.run(runtime.invoke_openai_tool("standard_fs_read", {}))
    subagent_result = asyncio.run(
        runtime.invoke_openai_tool(
            SUBAGENT_OPENAI_NAME,
            {"subagent_id": "researcher", "task": "check", "context": ""},
        )
    )

    assert standard.calls == [("standard_fs_read", {})]
    assert standard_result.output_payload()["tool_name"] == "standard.fs.read"
    assert subagent.calls[0][0] == SUBAGENT_OPENAI_NAME
    assert subagent_result.output_payload()["tool_name"] == SUBAGENT_TOOL_NAME


def test_chat_tool_runtime_can_expose_restricted_no_harness_tool_set() -> None:
    standard = FakeStandardRuntime()
    subagent = FakeSubagentRuntime()
    runtime = ChatToolRuntime(
        standard_runtime=standard,
        subagent_runtime=subagent,
        excluded_tool_names=("standard.shell.bash",),
        include_subagent=False,
        include_parallel=False,
    )

    assert runtime.list_tool_names() == ("standard.fs.read",)
    assert {tool["name"] for tool in runtime.list_openai_tools()} == {"standard_fs_read"}

    subagent_result = asyncio.run(runtime.invoke_openai_tool(SUBAGENT_OPENAI_NAME, {}))

    assert subagent.calls == []
    assert subagent_result.output_payload()["ok"] is False
    assert subagent_result.output_payload()["error"]["type"] == "tool_not_allowed"


def test_chat_tool_runtime_parallel_tool_invokes_allowed_tools_concurrently() -> None:
    standard = FakeStandardRuntime()
    subagent = FakeSubagentRuntime()
    runtime = ChatToolRuntime(standard_runtime=standard, subagent_runtime=subagent)

    result = asyncio.run(
        runtime.invoke_openai_tool(
            PARALLEL_OPENAI_NAME,
            {
                "tool_uses": [
                    {"recipient_name": "standard_fs_read", "parameters": {"path": "a"}},
                    {
                        "recipient_name": SUBAGENT_OPENAI_NAME,
                        "parameters": {
                            "subagent_id": "researcher",
                            "task": "check",
                            "context": "",
                        },
                    },
                ]
            },
        )
    )

    payload = result.output_payload()
    assert payload["ok"] is True
    assert payload["tool_name"] == PARALLEL_TOOL_NAME
    assert payload["results"][0]["tool_name"] == "standard.fs.read"
    assert payload["results"][1]["tool_name"] == SUBAGENT_TOOL_NAME


def test_subagent_runtime_writes_artifacts_and_analysis_usage_totals(tmp_path) -> None:
    store, run, profile = _create_harness_run(tmp_path)
    provider = ScriptedSubagentProvider()
    runtime = SubagentToolRuntime(
        provider=provider,
        store=store,
        run=run,
        profile=profile,
        definitions=(
            SubagentDefinition(
                id="researcher",
                label="Researcher",
                description="Research",
                instructions="Research instructions",
                model="fake-model",
                reasoning_effort="low",
            ),
        ),
    )

    result = asyncio.run(
        runtime.invoke(
            SUBAGENT_OPENAI_NAME,
            {"subagent_id": "researcher", "task": "Find evidence", "context": "URL A"},
        )
    )

    assert result.ok is True
    assert result.text == "subagent notes"
    assert provider.requests[0].tools_enabled is False
    assert provider.requests[0].tool_context is None
    assert provider.requests[0].subagent_id == "researcher"

    subagent_dir = (
        tmp_path
        / "projects"
        / run.project_id
        / "runs"
        / run.id
        / profile.id
        / "subagents"
        / "researcher"
    )
    assert json.loads((subagent_dir / "output.json").read_text(encoding="utf-8"))[
        "text"
    ] == "subagent notes"
    assert json.loads((subagent_dir / "usage.json").read_text(encoding="utf-8"))[
        "usage"
    ]["total_tokens"] == 15
    assert (subagent_dir / "events.jsonl").exists()

    analysis = build_run_analysis(
        run,
        store.get_run_dir(run.project_id, run.id),
        store.list_run_dirs(run.project_id),
    )
    profile_analysis = analysis.profiles[profile.id]
    assert profile_analysis.subagent_count == 1
    assert profile_analysis.subagent_usage_total.total_tokens == 15
    assert profile_analysis.caller_usage_total.total_tokens == 15
    assert profile_analysis.subagents["researcher"].current_turn_usage.total_tokens == 15


def test_subagent_runtime_enables_declared_web_tools(tmp_path) -> None:
    store, run, profile = _create_harness_run(tmp_path)
    provider = ScriptedSubagentProvider()
    runtime = SubagentToolRuntime(
        provider=provider,
        store=store,
        run=run,
        profile=profile,
        standard_runtime=FakeWebStandardRuntime(),
        definitions=(
            SubagentDefinition(
                id="web-researcher",
                label="Web Researcher",
                description="Research the web",
                instructions="Use web evidence only.",
                model="fake-model",
                reasoning_effort="low",
                tools=("standard.web.search", "standard.web.fetch"),
            ),
        ),
    )

    result = asyncio.run(
        runtime.invoke(
            SUBAGENT_OPENAI_NAME,
            {"subagent_id": "web-researcher", "task": "Find sources", "context": ""},
        )
    )

    assert result.ok is True
    request = provider.requests[0]
    assert request.tools_enabled is True
    assert request.tool_context is not None
    assert request.tool_context.list_tool_names() == (
        "standard.web.search",
        "standard.web.fetch",
    )
    assert {tool["name"] for tool in request.tool_context.list_openai_tools()} == {
        "standard_web_search",
        "standard_web_fetch",
    }
    assert "exactly 5 distinct search query principles" in request.prompt
    assert "Do not call tools." not in request.prompt

    disallowed = asyncio.run(request.tool_context.invoke_openai_tool("standard_fs_read", {}))
    assert disallowed.output_payload()["ok"] is False
    assert disallowed.output_payload()["error"]["type"] == "tool_not_allowed"


def test_subagent_runtime_returns_structured_error_for_unknown_subagent(tmp_path) -> None:
    store, run, profile = _create_harness_run(tmp_path)
    runtime = SubagentToolRuntime(
        provider=ScriptedSubagentProvider(),
        store=store,
        run=run,
        profile=profile,
        definitions=(),
    )

    result = asyncio.run(
        runtime.invoke(
            SUBAGENT_OPENAI_NAME,
            {"subagent_id": "missing", "task": "Find evidence", "context": ""},
        )
    )

    assert result.ok is False
    assert result.error["type"] == "subagent_not_allowed"
    assert result.output_payload()["error"]["type"] == "subagent_not_allowed"


def _create_harness_run(tmp_path):
    store = ProjectStore(data_dir=tmp_path)
    project = store.create_project(ProjectCreate(name="Subagent test"))
    profile = ProfileConfig(
        id="harness",
        label="Harness",
        harness_modules={"tool_policy": True},
    )
    run = store.create_run(
        project.id,
        RunCreate(
            prompt="delegate",
            model="fake-model",
            reasoning_effort="medium",
            profiles=[profile],
        ),
    )
    return store, run, profile


class ScriptedSubagentProvider(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def stream_text(self, request: LLMRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        yield ProviderEvent(
            type="delta",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=1,
            text="subagent notes",
            subagent_id=request.subagent_id,
            subagent_label=request.subagent_label,
            parent_profile_id=request.parent_profile_id,
        )
        yield ProviderEvent(
            type="completed",
            profile_id=request.profile_id,
            profile_label=request.profile_label,
            sequence=2,
            usage={
                "input_tokens": 8,
                "cached_tokens": 2,
                "output_tokens": 7,
                "reasoning_tokens": 1,
                "total_tokens": 15,
            },
            subagent_id=request.subagent_id,
            subagent_label=request.subagent_label,
            parent_profile_id=request.parent_profile_id,
        )


class FakeInvocation:
    def __init__(self, name: str) -> None:
        self.name = name

    def output_payload(self):
        return {"ok": True, "tool_name": self.name}

    def event_payload(self):
        return {"ok": True, "tool_name": self.name}


class FakeStandardRuntime:
    def __init__(self) -> None:
        self.calls = []

    def list_openai_tools(self):
        return [
            {"type": "function", "name": "standard_fs_read", "parameters": {}},
            {"type": "function", "name": "standard_shell_bash", "parameters": {}},
        ]

    def list_tool_names(self):
        return ("standard.fs.read", "standard.shell.bash")

    def from_openai_name(self, openai_name):
        return {
            "standard_fs_read": "standard.fs.read",
            "standard_shell_bash": "standard.shell.bash",
        }.get(openai_name, openai_name)

    async def invoke_openai_tool(self, openai_name, arguments):
        self.calls.append((openai_name, arguments))
        return FakeInvocation("standard.fs.read")


class FakeWebStandardRuntime:
    def list_openai_tools(self):
        return [
            {"type": "function", "name": "standard_web_search", "parameters": {}},
            {"type": "function", "name": "standard_web_fetch", "parameters": {}},
            {"type": "function", "name": "standard_fs_read", "parameters": {}},
        ]

    def list_tool_names(self):
        return ("standard.web.search", "standard.web.fetch", "standard.fs.read")

    def from_openai_name(self, openai_name):
        return {
            "standard_web_search": "standard.web.search",
            "standard_web_fetch": "standard.web.fetch",
            "standard_fs_read": "standard.fs.read",
        }.get(openai_name, openai_name)

    async def invoke_openai_tool(self, openai_name, arguments):
        return FakeInvocation(self.from_openai_name(openai_name))


class FakeSubagentRuntime:
    def __init__(self) -> None:
        self.calls = []

    async def invoke(self, openai_name, arguments):
        self.calls.append((openai_name, arguments))
        return FakeInvocation(SUBAGENT_TOOL_NAME)
