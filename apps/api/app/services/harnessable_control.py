from __future__ import annotations

import os
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.run import ProfileConfig, RunDocument


BLOCKING_EFFECTS = {"BLOCK", "ABORT", "FAIL_SAFE", "REQUIRE_APPROVAL"}
PUBLIC_IMPACT_TERMS = (
    "publish",
    "post",
    "launch",
    "campaign",
    "advert",
    "marketing",
    "press release",
    "customer",
    "social",
    "email",
    "send",
    "public",
    "發布",
    "上架",
    "貼文",
    "社群",
    "廣告",
    "行銷",
    "客戶",
    "對外",
    "寄送",
    "公告",
)
CLAIM_TERMS = (
    "health",
    "nutrition",
    "safety",
    "performance",
    "price comparison",
    "compare",
    "claim",
    "健康",
    "營養",
    "安全",
    "效能",
    "比較",
    "宣稱",
    "功效",
)
FREE_OFFER_TERMS = ("free", "gift", "giveaway", "bogo", "免費", "贈品", "買一送一", "送")
SUBSCRIPTION_TERMS = ("subscription", "auto-renew", "renewal", "續訂", "自動續訂", "訂閱", "月租")
RIGHTS_TERMS = (
    "traditional",
    "cultural",
    "craft",
    "heritage",
    "source",
    "attribution",
    "licensed",
    "傳統",
    "文化",
    "圖樣",
    "來源",
    "授權",
    "出處",
)
SCANNER_HINT_TERMS = (
    ("map_or_geopolitical_visual", ("map", "territory", "border", "地圖", "疆界", "主權")),
    ("calendar_or_memorial_window", ("calendar", "memorial", "anniversary", "紀念日", "追思", "國殤", "日期")),
    ("visual_symbol_review", ("poster", "image", "gesture", "uniform", "visual", "海報", "圖片", "手勢", "制服", "視覺")),
)
SIMILARITY_TERMS = (
    "plagiarism",
    "copy",
    "copied",
    "knockoff",
    "similar",
    "inspired by",
    "reference image",
    "抄襲",
    "挪用",
    "仿作",
    "致敬",
    "相似",
    "參考圖",
    "素材",
)
PROVENANCE_TERMS = (
    "provenance",
    "attribution",
    "rights",
    "license",
    "licensed",
    "source",
    "cultural",
    "heritage",
    "來源",
    "出處",
    "授權",
    "權利",
    "文化",
    "傳統",
    "圖樣",
)
SCANNER_COVERAGE_BY_ASSET_KIND = {
    "ad_creative": ["ocr", "cv", "similarity", "provenance"],
    "image": ["ocr", "cv", "similarity", "provenance"],
    "map": ["cv", "localization", "provenance"],
    "poster": ["ocr", "cv", "similarity", "provenance"],
    "product_design": ["similarity", "provenance", "rights"],
    "social_post": ["ocr", "cv", "similarity", "provenance"],
    "slogan": ["similarity", "provenance"],
    "video": ["ocr", "cv", "asr", "similarity", "provenance"],
}


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
        if (
            decisions[-1]["effect"] not in BLOCKING_EFFECTS
            and profile.harness_modules.get("consequence_gate")
            and _looks_externally_visible(run.prompt)
        ):
            decisions.append(
                self._emit(
                    event_type="FINAL_OUTPUT_PROPOSED",
                    run=run,
                    profile=profile,
                    payload={
                        "content": run.prompt,
                        "risk_context": _risk_context_for_prompt(run, profile),
                    },
                    hook_point="before_consequence_preflight",
                )
            )
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

    def evaluate_skill_context_assembly(
        self,
        run: RunDocument,
        profile: ProfileConfig,
        *,
        selection_policy: str,
        candidate_count: int,
        selected_skills: tuple[Any, ...],
        metadata_budget_chars: int,
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
        if not self._event_type_supported("CONTEXT_ASSEMBLY_REQUESTED") or not self._event_type_supported(
            "CONTEXT_ASSEMBLED"
        ):
            return HarnessableGateResult(
                decisions=[
                    {
                        "event_type": "CONTEXT_ASSEMBLY_UNSUPPORTED",
                        "effect": "ALLOW",
                        "reason": {"code": "HARNESSABLE_CONTEXT_ASSEMBLY_EVENT_UNAVAILABLE"},
                    }
                ]
            )

        capability = {
            "type": "RESOURCE",
            "id": "context.skill_assembly",
            "compatibility_class": "skill",
            "supports": ["metadata_selection", "progressive_hydration", "budget_events"],
        }
        selected_payload = [
            {
                "id": skill.skill_id,
                "source": skill.source,
                "reason": skill.reason,
                "score": skill.score,
                "load_policy": skill.load_policy,
                "required_tools": list(skill.required_tools),
                "allowed_tools": list(skill.allowed_tools),
                "priority": skill.priority,
            }
            for skill in selected_skills
        ]
        request_payload = {
            "selection_policy": selection_policy,
            "candidate_count": candidate_count,
            "max_selected": 3,
            "metadata_budget_chars": metadata_budget_chars,
            "metadata_only_selector": True,
            "full_skill_hydration": "after_selection",
        }
        decisions = [
            self._emit(
                event_type="CONTEXT_ASSEMBLY_REQUESTED",
                run=run,
                profile=profile,
                payload=request_payload,
                hook_point="before_context_assembly",
                capability=capability,
                include_event_payload=True,
            ),
            self._emit(
                event_type="CONTEXT_ASSEMBLED",
                run=run,
                profile=profile,
                payload={
                    **request_payload,
                    "selected_skill_ids": [skill["id"] for skill in selected_payload],
                    "selected_skills": selected_payload,
                    "hydrated_skill_count": len(selected_payload),
                },
                hook_point="after_context_assembly",
                capability=capability,
                include_event_payload=True,
            ),
        ]
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
        try:
            from harnessable import ConsequenceGate
        except ImportError:
            ConsequenceGate = None
        self._imports = {
            "ConsequenceGate": ConsequenceGate,
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
        ConsequenceGate = self._imports.get("ConsequenceGate")
        if ConsequenceGate is not None:
            ConsequenceGate.install(self.kernel)
        self._register_consequence_preview_rules()
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

    def _register_consequence_preview_rules(self) -> None:
        assert self.kernel is not None
        HarnessRule = self._imports["HarnessRule"]
        preview_events = ["FINAL_OUTPUT_PROPOSED"]
        rules = [
            HarnessRule(
                id="harnessdiff.consequence.context_gap.preview.v1",
                name="HarnessDiff publishing context preview",
                applies_to={"event_types": preview_events, "runtimes": ["chat"]},
                condition={"field": "metadata.consequence_gate_enabled", "equals": True},
                detector={
                    "type": "context_gap_detector",
                    "required_fields": [
                        "jurisdiction",
                        "market",
                        "locale",
                        "release_at",
                        "publish_window",
                        "audience",
                        "channel",
                        "intent",
                        "asset_hash",
                        "artifact_refs",
                        "ai_generated",
                    ],
                },
                action={"when_detected": {"type": "WARN"}, "when_clean": {"type": "ALLOW"}},
                severity="medium",
                telemetry={"module": "consequence_gate", "preview": True},
            ),
            HarnessRule(
                id="harnessdiff.consequence.claim_evidence.preview.v1",
                name="HarnessDiff claim evidence preview",
                applies_to={"event_types": preview_events, "runtimes": ["chat"]},
                condition={"field": "metadata.consequence_gate_enabled", "equals": True},
                detector={"type": "claim_evidence_detector"},
                action={"when_detected": {"type": "WARN"}, "when_clean": {"type": "ALLOW"}},
                severity="medium",
                telemetry={"module": "consequence_gate", "preview": True},
            ),
            HarnessRule(
                id="harnessdiff.consequence.offer_disclosure.preview.v1",
                name="HarnessDiff offer disclosure preview",
                applies_to={"event_types": preview_events, "runtimes": ["chat"]},
                condition={"field": "metadata.consequence_gate_enabled", "equals": True},
                detector={"type": "offer_disclosure_detector"},
                action={"when_detected": {"type": "WARN"}, "when_clean": {"type": "ALLOW"}},
                severity="medium",
                telemetry={"module": "consequence_gate", "preview": True},
            ),
            HarnessRule(
                id="harnessdiff.consequence.provenance.preview.v1",
                name="HarnessDiff provenance preview",
                applies_to={"event_types": preview_events, "runtimes": ["chat"]},
                condition={"field": "metadata.consequence_gate_enabled", "equals": True},
                detector={"type": "provenance_metadata_detector"},
                action={"when_detected": {"type": "WARN"}, "when_clean": {"type": "ALLOW"}},
                severity="medium",
                telemetry={"module": "consequence_gate", "preview": True},
            ),
            HarnessRule(
                id="harnessdiff.consequence.scanner_coverage.preview.v1",
                name="HarnessDiff scanner coverage preview",
                applies_to={"event_types": preview_events, "runtimes": ["chat"]},
                condition={"field": "metadata.consequence_gate_enabled", "equals": True},
                detector={"type": "scanner_coverage_detector"},
                action={"when_detected": {"type": "WARN"}, "when_clean": {"type": "ALLOW"}},
                severity="medium",
                telemetry={"module": "consequence_gate", "preview": True},
            ),
            HarnessRule(
                id="harnessdiff.consequence.scanner_result.preview.v1",
                name="HarnessDiff scanner result preview",
                applies_to={"event_types": preview_events, "runtimes": ["chat"]},
                condition={"field": "metadata.consequence_gate_enabled", "equals": True},
                detector={"type": "scanner_result_detector"},
                action={"when_detected": {"type": "WARN"}, "when_clean": {"type": "ALLOW"}},
                severity="medium",
                telemetry={"module": "consequence_gate", "preview": True},
            ),
            HarnessRule(
                id="harnessdiff.consequence.rollback.preview.v1",
                name="HarnessDiff rollback readiness preview",
                applies_to={"event_types": preview_events, "runtimes": ["chat"]},
                condition={"field": "metadata.consequence_gate_enabled", "equals": True},
                detector={"type": "rollback_readiness_detector"},
                action={"when_detected": {"type": "WARN"}, "when_clean": {"type": "ALLOW"}},
                severity="medium",
                telemetry={"module": "consequence_gate", "preview": True},
            ),
        ]
        for rule in rules:
            self.kernel.register_rule(rule)

    def _emit(
        self,
        *,
        event_type: str,
        run: RunDocument,
        profile: ProfileConfig,
        payload: dict[str, Any],
        hook_point: str,
        capability: dict[str, Any] | None = None,
        include_event_payload: bool = False,
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
                "consequence_gate_enabled": bool(profile.harness_modules.get("consequence_gate")),
            },
        )
        decision = self.kernel.emit(event)
        decision_doc = decision.to_dict()
        result = {
            "event_type": event_type,
            "event_id": event.event_id,
            "decision_id": decision_doc.get("decision_id"),
            "rule_id": decision_doc.get("rule_id") or "",
            "effect": decision_doc.get("effect"),
            "reason": decision_doc.get("reason", {}),
            "telemetry": decision_doc.get("telemetry", {}),
            "contributing_decisions": decision_doc.get("contributing_decisions", []),
        }
        if include_event_payload:
            result["event_payload"] = payload
            result["capability"] = capability or {}
        return result

    def _event_type_supported(self, event_type: str) -> bool:
        EventType = self._imports.get("EventType")
        if EventType is None:
            return False
        try:
            EventType(event_type)
        except ValueError:
            return False
        return True


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


def _looks_externally_visible(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(term in lowered for term in PUBLIC_IMPACT_TERMS)


def _risk_context_for_prompt(run: RunDocument, profile: ProfileConfig) -> dict[str, Any]:
    prompt = run.prompt
    artifact_ref = f"harnessdiff://projects/{run.project_id}/runs/{run.id}/profiles/{profile.id}"
    high_exposure = _looks_externally_visible(prompt)
    return {
        "jurisdiction": None,
        "market": None,
        "locale": _infer_locale(run.prompt),
        "release_at": None,
        "publish_window": None,
        "audience": None,
        "channel": _infer_channel(run.prompt),
        "intent": "external artifact preflight",
        "campaign_id": f"harnessdiff:{run.project_id}:{run.id}",
        "asset_kind": _asset_kind_for_prompt(prompt),
        "asset_hash": None,
        "genai_trace_id": None,
        "artifact_refs": [artifact_ref],
        "ai_generated": True,
        "claims": _claims_for_prompt(prompt),
        "offers": _offers_for_prompt(prompt),
        "rights": _rights_for_prompt(prompt),
        "scanner_results": _scanner_results_for_prompt(prompt, artifact_ref),
        "scanner_coverage": _scanner_coverage_for_prompt(prompt),
        "rollback_plan": {},
        "precedent_refs": [],
        "known_constraints": {"high_exposure": high_exposure},
        "review_route": {},
    }


def _infer_locale(text: str) -> str:
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return "zh-Hant"
    return "en"


def _infer_channel(text: str) -> str | None:
    lowered = text.lower()
    if any(term in lowered for term in ("social", "社群", "貼文")):
        return "social"
    if any(term in lowered for term in ("email", "寄送")):
        return "email"
    if any(term in lowered for term in ("press release", "公告")):
        return "public_announcement"
    if any(term in lowered for term in ("push", "推播")):
        return "app_push"
    if any(term in lowered for term in ("ad", "advert", "廣告")):
        return "ad"
    return None


def _claims_for_prompt(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    if not any(term in lowered for term in CLAIM_TERMS):
        return []
    claim_type = "health" if any(term in lowered for term in ("health", "nutrition", "健康", "營養", "功效")) else "comparative"
    return [
        {
            "id": "prompt_claim_1",
            "type": claim_type,
            "text": _short_hash_label(text, "claim"),
            "requires_evidence": True,
        }
    ]


def _offers_for_prompt(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    has_free = any(term in lowered for term in FREE_OFFER_TERMS)
    has_subscription = any(term in lowered for term in SUBSCRIPTION_TERMS)
    if not (has_free and has_subscription):
        return []
    return [
        {
            "id": "prompt_offer_1",
            "contains_freebie": True,
            "subscription": {"auto_renew": True},
            "disclosure": {},
        }
    ]


def _rights_for_prompt(text: str) -> dict[str, Any]:
    lowered = text.lower()
    if not any(term in lowered for term in RIGHTS_TERMS):
        return {}
    return {
        "uses_cultural_source": True,
        "uses_third_party_assets": True,
    }


def _scanner_results_for_prompt(text: str, artifact_ref: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    findings = []
    for finding_type, terms in SCANNER_HINT_TERMS:
        if any(term in lowered for term in terms):
            findings.append(
                {
                    "type": finding_type,
                    "severity": "high",
                    "message": f"{finding_type} needs structured review before publish-ready output",
                    "evidence_ref": artifact_ref,
                    "confidence": 0.75,
                }
            )
    if any(term in lowered for term in SIMILARITY_TERMS):
        findings.append(
            {
                "type": "similarity.match",
                "severity": "high",
                "message": "Prompt indicates possible copied, adapted, or near-duplicate asset risk.",
                "evidence_ref": artifact_ref,
                "confidence": 0.72,
                "metadata": {
                    "matched_asset_ref": "prompt://possible-reference-asset",
                    "similarity_score": None,
                    "license_status": "unknown",
                    "transform_type": "unknown_prompt_hint",
                },
            }
        )
    if any(term in lowered for term in PROVENANCE_TERMS):
        findings.append(
            {
                "type": "provenance.review",
                "severity": "high",
                "message": "Prompt indicates source, attribution, cultural, or rights provenance must be reviewed.",
                "evidence_ref": artifact_ref,
                "confidence": 0.78,
                "metadata": {
                    "source_type": "prompt_indicated_asset_source",
                    "rights_status": "unknown",
                    "required_rights": ["attribution", "rights_review"],
                    "source_ref": "prompt://source-or-cultural-reference",
                },
            }
        )
    if not findings:
        return []
    return [
        {
            "scanner_id": "harnessdiff_prompt_metadata_scanner",
            "status": "completed",
            "findings": findings,
            "metadata": {"capabilities": ["prompt_metadata"]},
        }
    ]


def _asset_kind_for_prompt(text: str) -> str | None:
    lowered = text.lower()
    if any(term in lowered for term in ("video", "影片", "短影音")):
        return "video"
    if any(term in lowered for term in ("map", "地圖")):
        return "map"
    if any(term in lowered for term in ("poster", "海報")):
        return "poster"
    if any(term in lowered for term in ("ad", "advert", "advertising", "廣告")):
        return "ad_creative"
    if any(term in lowered for term in ("image", "visual", "圖片", "視覺")):
        return "image"
    if any(term in lowered for term in ("slogan", "標語", "文案")):
        return "slogan"
    if any(term in lowered for term in ("product design", "產品設計")):
        return "product_design"
    if any(term in lowered for term in ("social", "社群", "貼文")):
        return "social_post"
    return None


def _scanner_coverage_for_prompt(text: str) -> dict[str, Any]:
    asset_kind = _asset_kind_for_prompt(text)
    required = list(SCANNER_COVERAGE_BY_ASSET_KIND.get(asset_kind or "", []))
    if any(term in text.lower() for term in SIMILARITY_TERMS):
        required.append("similarity")
    if any(term in text.lower() for term in PROVENANCE_TERMS):
        required.extend(["provenance", "rights"])
    return {"required_scanners": sorted(set(required))} if required else {}


def _short_hash_label(text: str, prefix: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"

