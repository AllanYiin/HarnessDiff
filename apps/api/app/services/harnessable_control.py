from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.run import ProfileConfig, RunDocument


BLOCKING_EFFECTS = {"BLOCK", "ABORT", "FAIL_SAFE", "REQUIRE_APPROVAL"}


@dataclass(slots=True)
class HarnessableGateResult:
    allowed: bool = True
    decisions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def blocking_decision(self) -> dict[str, Any] | None:
        for decision in self.decisions:
            if decision.get("effect") in BLOCKING_EFFECTS:
                return decision
        return None


class HarnessableControlPlane:
    def __init__(self) -> None:
        self.available = False
        self.kernel = None
        self._imports: dict[str, Any] = {}
        self._load_harnessable()
        if self.available:
            self._register_rules()

    def applies_to(self, profile: ProfileConfig) -> bool:
        return any(profile.harness_modules.values())

    def evaluate_before_provider(
        self, run: RunDocument, profile: ProfileConfig, instructions: str
    ) -> HarnessableGateResult:
        if not self.applies_to(profile):
            return HarnessableGateResult()
        if not self.available:
            return HarnessableGateResult(
                decisions=[
                    {
                        "event_type": "HARNESSABLE_UNAVAILABLE",
                        "effect": "ALLOW",
                        "reason": {"code": "HARNESSABLE_IMPORT_UNAVAILABLE"},
                    }
                ]
            )

        decisions = [
            self._emit(
                event_type="USER_INPUT_RECEIVED",
                run=run,
                profile=profile,
                payload={"text": run.prompt},
                hook_point="before_input_accept",
            ),
        ]
        if decisions[-1]["effect"] not in BLOCKING_EFFECTS:
            decisions.append(
                self._emit(
                    event_type="MODEL_CALL_REQUESTED",
                    run=run,
                    profile=profile,
                    payload={"prompt": run.prompt, "instructions": instructions},
                    hook_point="before_model_call",
                    capability={"type": "MODEL", "id": "provider.openai_responses"},
                )
            )
        return HarnessableGateResult(
            allowed=all(decision["effect"] not in BLOCKING_EFFECTS for decision in decisions),
            decisions=decisions,
        )

    def _load_harnessable(self) -> None:
        _ensure_harnessable_import_path()
        try:
            from harnessable import HarnessKernel
            from harnessable.events import EventType, HarnessEvent
            from harnessable.rules import HarnessRule
        except ImportError:
            return
        self._imports = {
            "HarnessKernel": HarnessKernel,
            "EventType": EventType,
            "HarnessEvent": HarnessEvent,
            "HarnessRule": HarnessRule,
        }
        self.kernel = HarnessKernel()
        self.available = True

    def _register_rules(self) -> None:
        assert self.kernel is not None
        HarnessRule = self._imports["HarnessRule"]
        self.kernel.register_rule(
            HarnessRule(
                id="harnessdiff.guardrails.prompt_injection",
                name="HarnessDiff guardrails prompt injection gate",
                applies_to={"event_types": ["USER_INPUT_RECEIVED"], "runtimes": ["chat"]},
                condition={"field": "metadata.guardrails_enabled", "equals": True},
                detector={
                    "type": "regex",
                    "field": "payload.text",
                    "pattern": (
                        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules)"
                        r"|reveal\s+(the\s+)?(system|developer)\s+(prompt|message)"
                        r"|bypass\s+(safety|guardrails|policy)"
                        r"|jailbreak"
                    ),
                },
                action={"when_detected": {"type": "BLOCK"}, "when_clean": {"type": "ALLOW"}},
                severity="high",
                telemetry={"module": "guardrails"},
            )
        )

    def _emit(
        self,
        *,
        event_type: str,
        run: RunDocument,
        profile: ProfileConfig,
        payload: dict[str, Any],
        hook_point: str,
        capability: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert self.kernel is not None
        EventType = self._imports["EventType"]
        HarnessEvent = self._imports["HarnessEvent"]
        event = HarnessEvent(
            event_id=f"evt_{uuid4().hex}",
            run_id=run.id,
            event_type=EventType(event_type),
            runtime_type="chat",
            hook_point=hook_point,
            actor={"role": "user" if event_type == "USER_INPUT_RECEIVED" else "assistant"},
            capability=capability or {},
            payload=payload,
            metadata={
                "profile_id": profile.id,
                "profile_label": profile.label,
                "guardrails_enabled": bool(profile.harness_modules.get("guardrails")),
                "tool_policy_enabled": bool(profile.harness_modules.get("tool_policy")),
            },
        )
        decision = self.kernel.emit(event)
        decision_doc = decision.to_dict()
        return {
            "event_type": event_type,
            "event_id": event.event_id,
            "decision_id": decision_doc.get("decision_id"),
            "rule_id": decision_doc.get("rule_id"),
            "effect": decision_doc.get("effect"),
            "reason": decision_doc.get("reason", {}),
            "telemetry": decision_doc.get("telemetry", {}),
            "contributing_decisions": decision_doc.get("contributing_decisions", []),
        }


def _ensure_harnessable_import_path() -> None:
    candidates = []
    env_path = os.environ.get("HARNESSABLE_SRC")
    if env_path:
        candidates.append(Path(env_path))
    current = Path(__file__).resolve()
    try:
        candidates.append(current.parents[6] / "Harnessable" / "src")
    except IndexError:
        pass
    for candidate in candidates:
        if candidate.exists():
            candidate_text = str(candidate)
            if candidate_text not in sys.path:
                sys.path.insert(0, candidate_text)
