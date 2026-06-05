from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.services.skill_store import SkillStore
from app.services.tool_runtime import _elapsed_ms, _estimated_tool_token_usage, _json_summary


SKILL_ROUTING_REVIEW_TOOL_NAME = "skill_routing_review"
SKILL_ROUTING_REVIEW_OPENAI_NAME = "skill_routing_review"

RISK_TERMS = (
    "publish",
    "post",
    "campaign",
    "marketing",
    "persuade",
    "objection",
    "humanize",
    "ai voice",
    "social",
    "copywriting",
    "發布",
    "貼文",
    "社群",
    "行銷",
    "說服",
    "買單",
    "反對點",
    "潤稿",
    "AI 味",
    "ai 味",
    "翻譯腔",
    "敏感日期",
    "228",
)


@dataclass(frozen=True)
class SkillRoutingReviewInvocationRecord:
    ok: bool
    name: str
    openai_name: str
    arguments: dict[str, Any]
    elapsed_ms: int
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def output_payload(self) -> dict[str, Any]:
        if self.ok:
            return {
                "ok": True,
                "tool_name": self.name,
                "result": self.result or {},
            }
        return {
            "ok": False,
            "tool_name": self.name,
            "error": self.error or {},
        }

    def event_payload(self) -> dict[str, Any]:
        output_payload = self.output_payload()
        payload = {
            "ok": self.ok,
            "tool_name": self.name,
            "openai_name": self.openai_name,
            "arguments": self.arguments,
            "elapsed_ms": self.elapsed_ms,
            "token_usage": _estimated_tool_token_usage(self.arguments, output_payload),
        }
        if self.ok:
            payload["result_summary"] = _json_summary(self.result or {})
        else:
            payload["error"] = self.error or {}
        return payload


class SkillRoutingReviewRuntime:
    def __init__(
        self,
        *,
        skill_store: SkillStore,
        task_text: str,
        selected_skill_ids: tuple[str, ...] = (),
    ) -> None:
        self.skill_store = skill_store
        self.task_text = task_text
        self.selected_skill_ids = selected_skill_ids

    def list_tool_names(self) -> tuple[str, ...]:
        return (SKILL_ROUTING_REVIEW_TOOL_NAME,)

    def list_openai_tools(self) -> list[dict[str, Any]]:
        return [skill_routing_review_openai_tool()]

    def from_openai_name(self, openai_name: str) -> str:
        if openai_name == SKILL_ROUTING_REVIEW_OPENAI_NAME:
            return SKILL_ROUTING_REVIEW_TOOL_NAME
        return openai_name

    async def invoke_openai_tool(
        self, openai_name: str, arguments: dict[str, Any]
    ) -> SkillRoutingReviewInvocationRecord:
        started = time.perf_counter()
        tool_name = self.from_openai_name(openai_name)
        if tool_name != SKILL_ROUTING_REVIEW_TOOL_NAME:
            return SkillRoutingReviewInvocationRecord(
                ok=False,
                name=tool_name,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={
                    "type": "tool_not_allowed",
                    "message": f"Tool is not enabled for HarnessDiff: {tool_name}",
                },
            )
        try:
            result = self.review(arguments)
        except Exception as exc:
            return SkillRoutingReviewInvocationRecord(
                ok=False,
                name=SKILL_ROUTING_REVIEW_TOOL_NAME,
                openai_name=openai_name,
                arguments=arguments,
                elapsed_ms=_elapsed_ms(started),
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )
        return SkillRoutingReviewInvocationRecord(
            ok=True,
            name=SKILL_ROUTING_REVIEW_TOOL_NAME,
            openai_name=openai_name,
            arguments=arguments,
            elapsed_ms=_elapsed_ms(started),
            result=result,
        )

    def review(self, arguments: dict[str, Any]) -> dict[str, Any]:
        task_text = str(arguments.get("task_text") or self.task_text)
        trigger = str(arguments.get("trigger") or "manual")
        selected_skill_ids = _string_list(arguments.get("selected_skill_ids")) or list(
            self.selected_skill_ids
        )
        audit_reasons = _string_list(arguments.get("audit_reasons"))
        candidates = _candidate_rows(arguments.get("candidates"))
        if not candidates:
            candidates = [
                {
                    "id": activation.id,
                    "score": activation.score,
                    "reasons": [activation.reason] if activation.reason else [],
                }
                for activation in self.skill_store.select_skills_for_prompt(task_text, limit=4)
            ]
        candidates.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("id") or "")))

        if trigger == "close_score" and len(candidates) >= 2:
            selected = [str(item["id"]) for item in candidates[:2] if item.get("id")]
            return _review_result(
                decision="add" if selected else "none",
                selected_skill_ids=selected,
                confidence=0.75 if selected else 0.2,
                reasons=["trigger:close_score", "close candidate scores require joint hydration"],
                should_hydrate=bool(selected),
            )

        if selected_skill_ids and trigger not in {"undertrigger", "manual"}:
            return _review_result(
                decision="keep",
                selected_skill_ids=selected_skill_ids,
                confidence=0.7,
                reasons=[f"trigger:{trigger}", *audit_reasons],
                should_hydrate=True,
            )

        selected = [str(item["id"]) for item in candidates[:4] if item.get("id")]
        risky = _looks_risky(task_text) or bool(audit_reasons)
        if selected:
            return _review_result(
                decision="add" if not selected_skill_ids else "replace",
                selected_skill_ids=selected,
                confidence=0.7,
                reasons=[f"trigger:{trigger}", *audit_reasons],
                should_hydrate=True,
            )
        return _review_result(
            decision="none",
            selected_skill_ids=[],
            confidence=0.3 if risky else 0.1,
            reasons=[f"trigger:{trigger}", *audit_reasons],
            should_hydrate=False,
        )


def skill_routing_review_openai_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": SKILL_ROUTING_REVIEW_OPENAI_NAME,
        "description": (
            "Review HarnessDiff skill routing when no skill was selected for a risky "
            "task, or when top skill candidates are close. Returns fixed JSON with "
            "decision, selected_skill_ids, confidence, reasons, and should_hydrate."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_text": {
                    "type": "string",
                    "description": "Current user task. Defaults to the active run prompt.",
                },
                "trigger": {
                    "type": "string",
                    "enum": ["undertrigger", "close_score", "manual"],
                    "description": "Why the review is requested.",
                },
                "selected_skill_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Skill ids already selected before review.",
                },
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "description": "Optional candidate metadata with score fields.",
                },
                "audit_reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Short audit reasons to preserve in output.",
                },
            },
            "required": ["trigger"],
            "additionalProperties": False,
        },
    }


def _review_result(
    *,
    decision: str,
    selected_skill_ids: list[str],
    confidence: float,
    reasons: list[str],
    should_hydrate: bool,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "selected_skill_ids": selected_skill_ids,
        "confidence": max(0.0, min(1.0, confidence)),
        "reasons": [str(reason) for reason in reasons if str(reason).strip()],
        "should_hydrate": should_hydrate,
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _candidate_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        manifest = item.get("manifest") if isinstance(item.get("manifest"), dict) else {}
        skill_id = str(item.get("id") or manifest.get("id") or "").strip()
        if not skill_id:
            continue
        rows.append(
            {
                "id": skill_id,
                "score": item.get("score") if isinstance(item.get("score"), (int, float)) else 0,
                "reasons": _string_list(item.get("reasons")),
            }
        )
    return rows


def _looks_risky(task_text: str) -> bool:
    lowered = task_text.lower()
    return any(term.lower() in lowered for term in RISK_TERMS)
