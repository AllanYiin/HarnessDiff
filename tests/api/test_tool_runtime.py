from __future__ import annotations

import asyncio
import base64

from app.models.run import RunAttachment
from app.services.pdf_attachments import (
    PdfAttachmentToolRuntime,
    build_pdf_context_prompt,
    prepare_pdf_attachments,
)
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


def test_pdf_attachment_tools_support_grep_and_progressive_blocks(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    attachments = prepare_pdf_attachments(
        [
            RunAttachment(
                kind="pdf",
                id="pdf_test",
                name="paper.pdf",
                mime_type="application/pdf",
                size_bytes=len(_minimal_pdf_bytes()),
                data_base64=base64.b64encode(_minimal_pdf_bytes()).decode("ascii"),
            )
        ],
        run_dir=run_dir,
    )
    attachment = attachments[0]

    no_harness_prompt = build_pdf_context_prompt(
        attachments=tuple(attachments),
        run_dir=run_dir,
        harness_mode=False,
    )
    assert "reading_mode: full_text_below_threshold" in no_harness_prompt
    assert "HarnessDiff PDF needle" in no_harness_prompt

    grep_runtime = PdfAttachmentToolRuntime(
        run_dir=run_dir,
        attachments=tuple(attachments),
        mode="grep",
    )
    grep_result = asyncio.run(
        grep_runtime.invoke_openai_tool(
            "attachment_pdf_grep",
            {"pattern": "needle", "regex": False, "attachment_id": "pdf_test"},
        )
    )
    assert grep_result.ok is True
    assert grep_result.result["matches"][0]["page_number"] == 1
    assert "HarnessDiff PDF needle" in grep_result.result["matches"][0]["line"]

    harness_prompt = build_pdf_context_prompt(
        attachments=tuple(attachments),
        run_dir=run_dir,
        harness_mode=True,
    )
    assert "reading_mode: progressive_blocks" in harness_prompt
    assert "attachment_pdf_search_blocks" in harness_prompt

    block_runtime = PdfAttachmentToolRuntime(
        run_dir=run_dir,
        attachments=tuple(attachments),
        mode="harness",
    )
    search_result = asyncio.run(
        block_runtime.invoke_openai_tool(
            "attachment_pdf_search_blocks",
            {"query": "needle", "attachment_id": attachment.id},
        )
    )
    assert search_result.ok is True
    block_id = search_result.result["results"][0]["id"]
    read_result = asyncio.run(
        block_runtime.invoke_openai_tool(
            "attachment_pdf_read_block",
            {"block_id": block_id, "attachment_id": attachment.id},
        )
    )
    assert read_result.ok is True
    assert read_result.result["page_refs"] == [1]
    assert "HarnessDiff PDF needle" in read_result.result["content"]


def _minimal_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"5 0 obj << /Length 53 >> stream\n"
        b"BT /F1 12 Tf 72 720 Td (HarnessDiff PDF needle) Tj ET\n"
        b"endstream endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000241 00000 n \n"
        b"0000000311 00000 n \n"
        b"trailer << /Root 1 0 R /Size 6 >>\n"
        b"startxref\n"
        b"405\n"
        b"%%EOF"
    )
