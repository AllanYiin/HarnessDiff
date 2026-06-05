from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
from collections import deque
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from app.models.run import RunAttachment
from app.services.tool_runtime import (
    ToolInvocationRecord,
    _elapsed_ms,
)


PDF_FULL_TEXT_CHAR_THRESHOLD = 24_000
PDF_BLOCK_TARGET_CHARS = 1_800
PDF_BLOCK_OVERLAP_CHARS = 160
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")

PDF_GREP_TOOL_NAME = "attachment.pdf.grep"
PDF_GREP_OPENAI_NAME = "attachment_pdf_grep"
PDF_READ_LINES_TOOL_NAME = "attachment.pdf.read_lines"
PDF_READ_LINES_OPENAI_NAME = "attachment_pdf_read_lines"
PDF_SEARCH_BLOCKS_TOOL_NAME = "attachment.pdf.search_blocks"
PDF_SEARCH_BLOCKS_OPENAI_NAME = "attachment_pdf_search_blocks"
PDF_READ_BLOCK_TOOL_NAME = "attachment.pdf.read_block"
PDF_READ_BLOCK_OPENAI_NAME = "attachment_pdf_read_block"
PDF_READ_BLOCKS_TOOL_NAME = "attachment.pdf.read_blocks"
PDF_READ_BLOCKS_OPENAI_NAME = "attachment_pdf_read_blocks"

NO_HARNESS_PDF_TOOL_NAMES = (
    PDF_GREP_TOOL_NAME,
    PDF_READ_LINES_TOOL_NAME,
)
HARNESS_PDF_TOOL_NAMES = (
    PDF_SEARCH_BLOCKS_TOOL_NAME,
    PDF_READ_BLOCK_TOOL_NAME,
    PDF_READ_BLOCKS_TOOL_NAME,
)


@dataclass(frozen=True)
class ExtractedPdf:
    attachment_id: str
    text: str
    line_indexed_text: str
    pages: list[dict[str, Any]]
    blocks: list[dict[str, Any]]
    char_count: int
    line_count: int
    page_count: int
    parser: str


def prepare_pdf_attachments(
    attachments: list[RunAttachment],
    *,
    run_dir: Path,
) -> list[RunAttachment]:
    prepared: list[RunAttachment] = []
    for index, attachment in enumerate(attachments):
        if attachment.kind != "pdf":
            prepared.append(attachment)
            continue
        if not attachment.data_base64:
            prepared.append(attachment)
            continue
        attachment_id = attachment.id or _attachment_id(attachment.name, index)
        extracted = extract_pdf_base64(
            attachment.data_base64,
            filename=attachment.name,
            attachment_id=attachment_id,
        )
        attachments_dir = run_dir / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)
        text_path = attachments_dir / f"{attachment_id}.txt"
        lines_path = attachments_dir / f"{attachment_id}.lines.txt"
        blocks_path = attachments_dir / f"{attachment_id}.blocks.json"
        text_path.write_text(extracted.text, encoding="utf-8", newline="\n")
        lines_path.write_text(extracted.line_indexed_text, encoding="utf-8", newline="\n")
        blocks_path.write_text(
            json.dumps(extracted.blocks, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        prepared.append(
            attachment.model_copy(
                update={
                    "id": attachment_id,
                    "mime_type": attachment.mime_type or "application/pdf",
                    "page_count": extracted.page_count,
                    "char_count": extracted.char_count,
                    "line_count": extracted.line_count,
                    "parser": extracted.parser,
                    "text_path": _run_relative(text_path, run_dir),
                    "line_index_path": _run_relative(lines_path, run_dir),
                    "block_index_path": _run_relative(blocks_path, run_dir),
                    "data_base64": None,
                }
            )
        )
    return prepared


def extract_pdf_base64(data_base64: str, *, filename: str, attachment_id: str) -> ExtractedPdf:
    try:
        data = base64.b64decode(data_base64, validate=True)
    except ValueError as exc:
        raise ValueError(f"Invalid base64 PDF attachment: {filename}") from exc
    return extract_pdf_bytes(data, filename=filename, attachment_id=attachment_id)


def extract_pdf_bytes(data: bytes, *, filename: str, attachment_id: str) -> ExtractedPdf:
    pages, parser = _extract_pages_with_pypdf(data)
    if not any(page["text"].strip() for page in pages):
        fallback_pages, fallback_parser = _extract_pages_with_pymupdf(data)
        if any(page["text"].strip() for page in fallback_pages):
            pages, parser = fallback_pages, fallback_parser
    pages = _normalize_pages(pages)
    text = _document_text(filename, pages)
    line_rows = _line_rows(pages)
    line_indexed_text = "\n".join(
        f"L{row['line_number']:06d} [p{row['page_number']:03d}] {row['text']}"
        for row in line_rows
    )
    blocks = _build_blocks(attachment_id, filename, pages)
    return ExtractedPdf(
        attachment_id=attachment_id,
        text=text,
        line_indexed_text=line_indexed_text,
        pages=pages,
        blocks=blocks,
        char_count=len(text),
        line_count=len(line_rows),
        page_count=len(pages),
        parser=parser,
    )


class PdfAttachmentToolRuntime:
    def __init__(
        self,
        *,
        run_dir: Path,
        attachments: tuple[RunAttachment, ...],
        mode: str,
    ) -> None:
        self.run_dir = run_dir
        self.attachments = tuple(
            attachment
            for attachment in attachments
            if attachment.kind == "pdf" and attachment.id
        )
        self.mode = mode
        self._blocks_cache: dict[str, list[dict[str, Any]]] = {}
        self._lines_cache: dict[str, list[dict[str, Any]]] = {}

    def has_pdf_attachments(self) -> bool:
        return bool(self.attachments)

    def list_tool_names(self) -> tuple[str, ...]:
        if not self.has_pdf_attachments():
            return ()
        if self.mode == "harness":
            return HARNESS_PDF_TOOL_NAMES
        return NO_HARNESS_PDF_TOOL_NAMES

    def list_openai_tools(self) -> list[dict[str, Any]]:
        if not self.has_pdf_attachments():
            return []
        if self.mode == "harness":
            return [
                _pdf_search_blocks_tool(),
                _pdf_read_block_tool(),
                _pdf_read_blocks_tool(),
            ]
        return [_pdf_grep_tool(), _pdf_read_lines_tool()]

    async def invoke_openai_tool(
        self,
        openai_name: str,
        arguments: dict[str, Any],
    ) -> ToolInvocationRecord:
        started = time.perf_counter()
        tool_name = self.from_openai_name(openai_name)
        if tool_name not in self.list_tool_names():
            return ToolInvocationRecord(
                ok=False,
                name=tool_name or openai_name,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={
                    "type": "tool_not_allowed",
                    "message": f"Tool is not enabled for this profile: {openai_name}",
                },
            )
        try:
            if tool_name == PDF_GREP_TOOL_NAME:
                result = self.grep(**arguments)
            elif tool_name == PDF_READ_LINES_TOOL_NAME:
                result = self.read_lines(**arguments)
            elif tool_name == PDF_SEARCH_BLOCKS_TOOL_NAME:
                result = self.search_blocks(**arguments)
            elif tool_name == PDF_READ_BLOCK_TOOL_NAME:
                result = self.read_block(**arguments)
            elif tool_name == PDF_READ_BLOCKS_TOOL_NAME:
                result = self.read_blocks(**arguments)
            else:
                raise ValueError(f"Unknown PDF attachment tool: {openai_name}")
        except Exception as exc:
            return ToolInvocationRecord(
                ok=False,
                name=tool_name or openai_name,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )
        return ToolInvocationRecord(
            ok=True,
            name=tool_name,
            openai_name=openai_name,
            arguments=arguments,
            elapsed_ms=_elapsed_ms(started),
            result=result,
        )

    def from_openai_name(self, openai_name: str) -> str:
        return {
            PDF_GREP_OPENAI_NAME: PDF_GREP_TOOL_NAME,
            PDF_GREP_TOOL_NAME: PDF_GREP_TOOL_NAME,
            PDF_READ_LINES_OPENAI_NAME: PDF_READ_LINES_TOOL_NAME,
            PDF_READ_LINES_TOOL_NAME: PDF_READ_LINES_TOOL_NAME,
            PDF_SEARCH_BLOCKS_OPENAI_NAME: PDF_SEARCH_BLOCKS_TOOL_NAME,
            PDF_SEARCH_BLOCKS_TOOL_NAME: PDF_SEARCH_BLOCKS_TOOL_NAME,
            PDF_READ_BLOCK_OPENAI_NAME: PDF_READ_BLOCK_TOOL_NAME,
            PDF_READ_BLOCK_TOOL_NAME: PDF_READ_BLOCK_TOOL_NAME,
            PDF_READ_BLOCKS_OPENAI_NAME: PDF_READ_BLOCKS_TOOL_NAME,
            PDF_READ_BLOCKS_TOOL_NAME: PDF_READ_BLOCKS_TOOL_NAME,
        }.get(openai_name, "")

    def grep(
        self,
        pattern: str,
        attachment_id: str | None = None,
        case_sensitive: bool = False,
        regex: bool = True,
        context_lines: int = 2,
        max_matches: int = 40,
    ) -> dict[str, Any]:
        if not pattern:
            raise ValueError("pattern is required.")
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(pattern if regex else re.escape(pattern), flags)
        context = max(0, min(int(context_lines), 10))
        limit = max(1, min(int(max_matches), 200))
        matches: list[dict[str, Any]] = []
        scanned_attachments = 0
        for attachment in self._select_attachments(attachment_id):
            scanned_attachments += 1
            rows = self._line_rows_for_attachment(attachment)
            before = deque(maxlen=context)
            pending_after: list[dict[str, Any]] = []
            for row in rows:
                line_payload = _line_payload(attachment, row)
                still_pending: list[dict[str, Any]] = []
                for pending in pending_after:
                    pending["match"]["after"].append(line_payload)
                    pending["remaining"] -= 1
                    if pending["remaining"] > 0:
                        still_pending.append(pending)
                pending_after = still_pending
                if len(matches) < limit and compiled.search(str(row["text"])):
                    match = {
                        **line_payload,
                        "before": list(before),
                        "after": [],
                    }
                    matches.append(match)
                    if context:
                        pending_after.append({"match": match, "remaining": context})
                before.append(line_payload)
                if len(matches) >= limit and not pending_after:
                    break
            if len(matches) >= limit:
                break
        return {
            "pattern": pattern,
            "attachment_id": attachment_id,
            "matches": matches,
            "match_count": len(matches),
            "scanned_attachments": scanned_attachments,
            "truncated": len(matches) >= limit,
        }

    def read_lines(
        self,
        attachment_id: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        attachment = self._attachment_by_id(attachment_id)
        start = max(1, int(start_line))
        end = max(start, min(int(end_line), start + 220))
        rows = [
            _line_payload(attachment, row)
            for row in self._line_rows_for_attachment(attachment)
            if start <= int(row["line_number"]) <= end
        ]
        return {
            "attachment_id": attachment.id,
            "name": attachment.name,
            "start_line": start,
            "end_line": end,
            "lines": rows,
            "truncated": int(end_line) > end,
        }

    def search_blocks(
        self,
        query: str,
        attachment_id: str | None = None,
        limit: int = 5,
        terms: list[str] | None = None,
        search_body: bool = True,
        include_snippets: bool = True,
        max_snippets_per_block: int = 4,
    ) -> dict[str, Any]:
        query_terms = _query_terms(query, terms=terms)
        if not query_terms:
            raise ValueError("query or terms must contain searchable text.")
        max_results = max(1, min(int(limit), 12))
        rows: list[dict[str, Any]] = []
        for attachment in self._select_attachments(attachment_id):
            for block in self._blocks_for_attachment(attachment):
                fields = {
                    "title": str(block.get("title") or ""),
                    "text_preview": str(block.get("text_preview") or ""),
                }
                if search_body:
                    fields["content"] = str(block.get("content") or "")
                score = 0.0
                matched: list[str] = []
                snippets: list[dict[str, str]] = []
                for field_name, text in fields.items():
                    folded = text.casefold()
                    for term in query_terms:
                        count = folded.count(term.casefold())
                        if count <= 0:
                            continue
                        if term not in matched:
                            matched.append(term)
                        score += count * (3.0 if field_name == "title" else 1.0)
                        if include_snippets and len(snippets) < max_snippets_per_block:
                            start = folded.find(term.casefold())
                            if start >= 0:
                                snippets.append(
                                    {
                                        "field": field_name,
                                        "keyword": term,
                                        "snippet": _snippet(text, start, start + len(term)),
                                    }
                                )
                if score <= 0:
                    continue
                rows.append(
                    {
                        "attachment_id": attachment.id,
                        "attachment_name": attachment.name,
                        "id": block["id"],
                        "title": block["title"],
                        "score": round(score, 4),
                        "page_refs": block["page_refs"],
                        "line_start": block["line_start"],
                        "line_end": block["line_end"],
                        "matched": matched,
                        "snippets": snippets,
                        "text_preview": block["text_preview"],
                    }
                )
        rows.sort(key=lambda item: item["score"], reverse=True)
        return {
            "query": query,
            "terms": query_terms,
            "results": rows[:max_results],
            "result_count": min(len(rows), max_results),
            "truncated": len(rows) > max_results,
            "retrieval_policy": {
                "next_recommended_tool": PDF_READ_BLOCKS_TOOL_NAME,
                "recommended_args": {
                    "block_ids": [row["id"] for row in rows[:max_results]],
                    "max_chars_per_block": 2200,
                },
                "reason": (
                    "search_blocks is for landing-point discovery only; read block "
                    "content before making evidence claims."
                ),
            },
        }

    def read_block(
        self,
        block_id: str,
        attachment_id: str | None = None,
        max_chars: int = 2_200,
    ) -> dict[str, Any]:
        attachment, block = self._find_block(block_id, attachment_id)
        content = str(block.get("content") or "")
        max_len = max(200, min(int(max_chars), 8_000))
        return {
            "attachment_id": attachment.id,
            "attachment_name": attachment.name,
            "id": block["id"],
            "title": block["title"],
            "page_refs": block["page_refs"],
            "line_start": block["line_start"],
            "line_end": block["line_end"],
            "content": content[:max_len],
            "truncated": len(content) > max_len,
        }

    def read_blocks(
        self,
        block_ids: list[str],
        attachment_id: str | None = None,
        max_chars_per_block: int = 2_200,
        max_blocks: int = 5,
    ) -> dict[str, Any]:
        if not isinstance(block_ids, list) or not block_ids:
            raise ValueError("block_ids must be a non-empty list.")
        selected = []
        unknown = []
        for block_id in [str(item) for item in block_ids[: max(1, min(int(max_blocks), 12))]]:
            try:
                selected.append(
                    self.read_block(
                        block_id,
                        attachment_id=attachment_id,
                        max_chars=max_chars_per_block,
                    )
                )
            except ValueError:
                unknown.append(block_id)
        return {
            "status": "ok" if selected else "error",
            "blocks": selected,
            "unknown_block_ids": unknown,
            "max_chars_per_block": max_chars_per_block,
        }

    def _select_attachments(self, attachment_id: str | None) -> tuple[RunAttachment, ...]:
        if attachment_id:
            return (self._attachment_by_id(attachment_id),)
        return self.attachments

    def _attachment_by_id(self, attachment_id: str) -> RunAttachment:
        for attachment in self.attachments:
            if attachment.id == attachment_id:
                return attachment
        raise ValueError(f"Unknown PDF attachment_id: {attachment_id}")

    def _line_rows_for_attachment(self, attachment: RunAttachment) -> list[dict[str, Any]]:
        assert attachment.id is not None
        if attachment.id in self._lines_cache:
            return self._lines_cache[attachment.id]
        path = self._attachment_path(attachment.line_index_path)
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                match = re.match(r"^L(\d{6}) \[p(\d{3})\] ?(.*)$", raw.rstrip("\n"))
                if not match:
                    continue
                rows.append(
                    {
                        "line_number": int(match.group(1)),
                        "page_number": int(match.group(2)),
                        "text": match.group(3),
                    }
                )
        self._lines_cache[attachment.id] = rows
        return rows

    def _blocks_for_attachment(self, attachment: RunAttachment) -> list[dict[str, Any]]:
        assert attachment.id is not None
        if attachment.id in self._blocks_cache:
            return self._blocks_cache[attachment.id]
        path = self._attachment_path(attachment.block_index_path)
        blocks = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(blocks, list):
            raise ValueError("PDF block index is corrupt.")
        self._blocks_cache[attachment.id] = blocks
        return blocks

    def _find_block(
        self,
        block_id: str,
        attachment_id: str | None,
    ) -> tuple[RunAttachment, dict[str, Any]]:
        for attachment in self._select_attachments(attachment_id):
            for block in self._blocks_for_attachment(attachment):
                if block.get("id") == block_id:
                    return attachment, block
        raise ValueError(f"Unknown PDF block_id: {block_id}")

    def _attachment_path(self, relative_path: str | None) -> Path:
        if not relative_path:
            raise ValueError("PDF attachment index path is missing.")
        path = (self.run_dir / relative_path).resolve()
        path.relative_to(self.run_dir.resolve())
        if not path.exists():
            raise ValueError(f"PDF attachment index does not exist: {relative_path}")
        return path


def build_pdf_context_prompt(
    *,
    attachments: tuple[RunAttachment, ...],
    run_dir: Path,
    harness_mode: bool,
) -> str:
    pdfs = [attachment for attachment in attachments if attachment.kind == "pdf"]
    if not pdfs:
        return ""
    sections = ["", "---", "PDF attachments:"]
    for attachment in pdfs:
        sections.extend(_pdf_attachment_context(attachment, run_dir, harness_mode=harness_mode))
    sections.append("---")
    return "\n".join(sections)


def _pdf_attachment_context(
    attachment: RunAttachment,
    run_dir: Path,
    *,
    harness_mode: bool,
) -> list[str]:
    metadata = [
        f"### PDF: {attachment.name}",
        f"- attachment_id: {attachment.id}",
        f"- pages: {attachment.page_count}",
        f"- extracted_characters: {attachment.char_count}",
        f"- extracted_lines: {attachment.line_count}",
        f"- parser: {attachment.parser or 'unknown'}",
    ]
    if harness_mode:
        metadata.extend(
            [
                "- reading_mode: progressive_blocks",
                (
                    "- instructions: Use attachment_pdf_search_blocks to find candidate "
                    "blocks, then attachment_pdf_read_blocks or attachment_pdf_read_block "
                    "to read full evidence before answering. Search snippets are only "
                    "navigation hints; cite page_refs and block ids from read results."
                ),
            ]
        )
        return metadata
    if (attachment.char_count or 0) <= PDF_FULL_TEXT_CHAR_THRESHOLD:
        text = _read_attachment_text(run_dir, attachment.text_path)
        metadata.extend(
            [
                "- reading_mode: full_text_below_threshold",
                "",
                "```text",
                text.replace("```", "`\u200b``"),
                "```",
            ]
        )
        return metadata
    metadata.extend(
        [
            "- reading_mode: grep_lines_above_threshold",
            (
                "- instructions: The extracted PDF text is line-indexed. Use "
                "attachment_pdf_grep first with precise keywords, then "
                "attachment_pdf_read_lines around matching line numbers before answering. "
                "Do not claim the PDF lacks information until grep/read_lines have been tried."
            ),
        ]
    )
    return metadata


def _extract_pages_with_pypdf(data: bytes) -> tuple[list[dict[str, Any]], str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF text extraction.") from exc
    reader = PdfReader(BytesIO(data))
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append({"page_number": index, "text": _normalize_text(text)})
    return pages, "pypdf"


def _extract_pages_with_pymupdf(data: bytes) -> tuple[list[dict[str, Any]], str]:
    try:
        import fitz
    except ImportError:
        return [], "pypdf"
    pages: list[dict[str, Any]] = []
    with fitz.open(stream=data, filetype="pdf") as document:
        for index, page in enumerate(document, start=1):
            pages.append({"page_number": index, "text": _normalize_text(page.get_text("text"))})
    return pages, "pymupdf"


def _document_text(filename: str, pages: list[dict[str, Any]]) -> str:
    parts = [f"# Extracted PDF text: {filename}"]
    for page in pages:
        parts.append(f"\n--- Page {page['page_number']} ---\n{page['text'].strip()}")
    return "\n".join(parts).strip()


def _line_rows(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in pages:
        for raw_line in str(page["text"]).splitlines():
            text = raw_line.strip()
            if not text:
                continue
            rows.append(
                {
                    "line_number": len(rows) + 1,
                    "page_number": int(page["page_number"]),
                    "text": text,
                }
            )
    return rows


def _build_blocks(
    attachment_id: str,
    filename: str,
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    global_line = 0
    for page in pages:
        page_number = int(page["page_number"])
        paragraphs = _paragraphs(str(page["text"]))
        for paragraph in paragraphs:
            line_count = len([line for line in paragraph.splitlines() if line.strip()])
            start_line = global_line + 1
            global_line += max(1, line_count)
            for chunk in _chunk_text(paragraph, PDF_BLOCK_TARGET_CHARS, PDF_BLOCK_OVERLAP_CHARS):
                block_number = len(blocks) + 1
                block_id = f"{attachment_id}_p{page_number:03d}_b{block_number:04d}"
                title = f"{filename} p.{page_number} block {block_number}"
                blocks.append(
                    {
                        "id": block_id,
                        "attachment_id": attachment_id,
                        "title": title,
                        "page_refs": [page_number],
                        "line_start": start_line,
                        "line_end": global_line,
                        "text_preview": _preview(chunk),
                        "content": chunk,
                    }
                )
    return blocks


def _paragraphs(text: str) -> list[str]:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    if paragraphs:
        return paragraphs
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def _chunk_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    compact = text.strip()
    if len(compact) <= target_chars:
        return [compact] if compact else []
    chunks = []
    start = 0
    while start < len(compact):
        end = min(start + target_chars, len(compact))
        if end < len(compact):
            boundary = max(compact.rfind("\n", start, end), compact.rfind(". ", start, end))
            if boundary > start + math.floor(target_chars * 0.55):
                end = boundary + 1
        chunks.append(compact[start:end].strip())
        if end >= len(compact):
            break
        start = max(end - overlap_chars, start + 1)
    return [chunk for chunk in chunks if chunk]


def _query_terms(query: str, *, terms: list[str] | None) -> list[str]:
    raw_terms = terms if terms is not None else []
    selected = [str(term).strip() for term in raw_terms if str(term).strip()]
    if not selected:
        selected.extend(re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,}", query))
        cjk = re.findall(r"[\u4e00-\u9fff]{2,}", query)
        selected.extend(cjk)
    deduped: list[str] = []
    for term in selected:
        if len(term) < 2 or term.casefold() in {item.casefold() for item in deduped}:
            continue
        deduped.append(term[:80])
        if len(deduped) >= 12:
            break
    return deduped


def _snippet(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return f"{prefix}{text[left:right].strip()}{suffix}"


def _preview(text: str, max_chars: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= max_chars else compact[: max_chars - 3] + "..."


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return SURROGATE_RE.sub("\uFFFD", normalized)


def _normalize_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **page,
            "text": _normalize_text(str(page.get("text") or "")),
        }
        for page in pages
    ]


def _attachment_id(name: str, index: int) -> str:
    digest = hashlib.sha256(f"{index}:{name}".encode("utf-8")).hexdigest()[:12]
    return f"pdf_{digest}"


def _run_relative(path: Path, run_dir: Path) -> str:
    return path.resolve().relative_to(run_dir.resolve()).as_posix()


def _read_attachment_text(run_dir: Path, relative_path: str | None) -> str:
    if not relative_path:
        return ""
    path = (run_dir / relative_path).resolve()
    path.relative_to(run_dir.resolve())
    return path.read_text(encoding="utf-8")


def _line_payload(attachment: RunAttachment, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "attachment_id": attachment.id,
        "attachment_name": attachment.name,
        "line_number": row["line_number"],
        "page_number": row["page_number"],
        "line": row["text"],
    }


def _attachment_id_parameter(required: bool = False) -> dict[str, Any]:
    schema = {
        "type": "string",
        "description": "PDF attachment_id. Omit only when there is one relevant PDF.",
    }
    return schema if required else schema


def _pdf_grep_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": PDF_GREP_OPENAI_NAME,
        "description": (
            "Grep line-indexed extracted PDF text. Use this for long PDF attachments "
            "before reading nearby lines."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "attachment_id": _attachment_id_parameter(),
                "case_sensitive": {"type": "boolean", "default": False},
                "regex": {"type": "boolean", "default": True},
                "context_lines": {"type": "integer", "default": 2},
                "max_matches": {"type": "integer", "default": 40},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    }


def _pdf_read_lines_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": PDF_READ_LINES_OPENAI_NAME,
        "description": "Read an inclusive line range from extracted PDF text.",
        "parameters": {
            "type": "object",
            "properties": {
                "attachment_id": _attachment_id_parameter(required=True),
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["attachment_id", "start_line", "end_line"],
            "additionalProperties": False,
        },
    }


def _pdf_search_blocks_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": PDF_SEARCH_BLOCKS_OPENAI_NAME,
        "description": (
            "Search progressive PDF blocks for candidate evidence. Snippets are only "
            "navigation hints; use read_block or read_blocks before answering."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "attachment_id": _attachment_id_parameter(),
                "limit": {"type": "integer", "default": 5},
                "terms": {"type": "array", "items": {"type": "string"}},
                "search_body": {"type": "boolean", "default": True},
                "include_snippets": {"type": "boolean", "default": True},
                "max_snippets_per_block": {"type": "integer", "default": 4},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }


def _pdf_read_block_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": PDF_READ_BLOCK_OPENAI_NAME,
        "description": "Read full content for one PDF block returned by search_blocks.",
        "parameters": {
            "type": "object",
            "properties": {
                "block_id": {"type": "string"},
                "attachment_id": _attachment_id_parameter(),
                "max_chars": {"type": "integer", "default": 2200},
            },
            "required": ["block_id"],
            "additionalProperties": False,
        },
    }


def _pdf_read_blocks_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": PDF_READ_BLOCKS_OPENAI_NAME,
        "description": "Read full content for several PDF blocks returned by search_blocks.",
        "parameters": {
            "type": "object",
            "properties": {
                "block_ids": {"type": "array", "items": {"type": "string"}},
                "attachment_id": _attachment_id_parameter(),
                "max_chars_per_block": {"type": "integer", "default": 2200},
                "max_blocks": {"type": "integer", "default": 5},
            },
            "required": ["block_ids"],
            "additionalProperties": False,
        },
    }
