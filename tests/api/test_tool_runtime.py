from __future__ import annotations

import asyncio

from app.services.tool_runtime import ALLOWED_TOOL_NAMES, ToolAnythingRuntime


def test_tool_runtime_exposes_only_allowed_readonly_tools(tmp_path) -> None:
    runtime = ToolAnythingRuntime(tmp_path)

    assert set(runtime.list_tool_names()) == set(ALLOWED_TOOL_NAMES)
    assert "standard.fs.write" not in runtime.list_tool_names()
    assert "standard.fs.patch_text" not in runtime.list_tool_names()
    assert "standard.fs.read" not in runtime.list_tool_names()

    openai_names = {tool["name"] for tool in runtime.list_openai_tools()}
    assert "standard_fs_read" not in openai_names
    assert "standard_fs_grep" in openai_names
    assert "standard_web_fetch" in openai_names
    assert "standard_shell_bash" in openai_names
    assert "standard_code_container_exec" in openai_names


def test_tool_runtime_invokes_filesystem_and_data_tools(tmp_path) -> None:
    (tmp_path / "sample.txt").write_text('{"name": "HarnessDiff"}\n', encoding="utf-8")
    (tmp_path / "notes.txt").write_text("before\nneedle\n after\n", encoding="utf-8")
    runtime = ToolAnythingRuntime(tmp_path)

    grep_result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_fs_grep",
            {
                "root_id": "workspace",
                "relative_path": "sample.txt",
                "pattern": "HarnessDiff",
                "glob": "*",
                "case_sensitive": True,
                "regex": False,
                "context_lines": 0,
                "max_matches": 10,
            },
        )
    )
    assert grep_result.ok is True
    assert grep_result.result["matches"][0]["line"] == '{"name": "HarnessDiff"}'
    assert "content" not in grep_result.result
    event_payload = grep_result.event_payload()
    assert event_payload["token_usage"]["source"] == "estimated"
    assert event_payload["token_usage"]["total_tokens"] > 0

    context_result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_fs_grep",
            {
                "root_id": "workspace",
                "relative_path": "notes.txt",
                "pattern": "needle",
                "glob": "*",
                "case_sensitive": True,
                "regex": False,
                "context_lines": 1,
                "max_matches": 10,
            },
        )
    )
    assert context_result.ok is True
    assert context_result.result["matches"][0]["before"] == [
        {"line_number": 1, "line": "before"}
    ]
    assert context_result.result["matches"][0]["after"] == [
        {"line_number": 3, "line": " after"}
    ]

    parse_result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_data_json_parse",
            {"text": '{"ok": true}'},
        )
    )
    assert parse_result.ok is True
    assert parse_result.result["value"] == {"ok": True}


def test_tool_runtime_blocks_filesystem_escape(tmp_path) -> None:
    runtime = ToolAnythingRuntime(tmp_path)

    result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_fs_grep",
            {
                "root_id": "workspace",
                "relative_path": "../outside.txt",
                "pattern": "outside",
                "glob": "*",
                "case_sensitive": False,
                "regex": False,
                "context_lines": 0,
                "max_matches": 10,
            },
        )
    )

    assert result.ok is False
    assert "path escapes configured workspace root" in result.error["message"]


def test_tool_runtime_invokes_readonly_bash_tool(tmp_path) -> None:
    (tmp_path / "sample.txt").write_text(
        "alpha\nHarnessDiff beta\ngamma\n", encoding="utf-8"
    )
    (tmp_path / "sample.py").write_text("print('ok')\n", encoding="utf-8")
    runtime = ToolAnythingRuntime(tmp_path)

    result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_shell_bash",
            {"command": "grep -n HarnessDiff sample.txt | sed -n '1,1p'"},
        )
    )

    assert result.ok is True
    assert result.result["exit_code"] == 0
    assert "2:HarnessDiff beta" in result.result["stdout"]
    assert result.result["fallback"] == "python-readonly-bash"

    find_result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_shell_bash",
            {"command": "find . -maxdepth 1 -name '*.py'"},
        )
    )
    assert find_result.ok is True
    assert "sample.py" in find_result.result["stdout"]


def test_tool_runtime_invokes_container_code_tool_validation(tmp_path) -> None:
    runtime = ToolAnythingRuntime(tmp_path)

    result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_code_container_exec",
            {"command": "python3 --version", "workdir": "../outside"},
        )
    )

    assert result.ok is True
    assert result.result["exit_code"] == 127
    assert result.result["error"]["type"] == "invalid_workdir"


def test_tool_runtime_readonly_bash_rejects_mutation_and_escape(tmp_path) -> None:
    runtime = ToolAnythingRuntime(tmp_path)

    mutation = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_shell_bash",
            {"command": "rm -rf sample.txt"},
        )
    )
    assert mutation.ok is True
    assert mutation.result["exit_code"] == 2
    assert "read-only guard" in mutation.result["stderr"]

    escape = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_shell_bash",
            {"command": "cat ../outside.txt"},
        )
    )
    assert escape.ok is True
    assert escape.result["exit_code"] == 2
    assert "path escapes configured workspace root" in escape.result["stderr"]


def test_tool_runtime_web_search_without_provider_returns_structured_error(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    runtime = ToolAnythingRuntime(tmp_path)

    result = asyncio.run(
        runtime.invoke_openai_tool(
            "standard_web_search",
            {"query": "HarnessDiff", "limit": 1},
        )
    )

    assert result.ok is False
    assert "SERPAPI_KEY" in result.error["message"]
