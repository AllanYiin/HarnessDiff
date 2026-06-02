from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.agent import AgentRunConfig
from app.models.harness_modules import normalize_harness_modules
from app.models.project import utc_now_iso

SUPPORTED_RUN_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
SUPPORTED_RUN_PDF_MIME_TYPES = {"application/pdf", "application/octet-stream"}


class InputMode(str, Enum):
    integrated = "integrated"
    independent = "independent"


class RunStatus(str, Enum):
    submitted = "submitted"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ProfileConfig(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    harness_modules: dict[str, bool] = Field(default_factory=dict)

    @field_validator("harness_modules", mode="before")
    @classmethod
    def normalize_module_names(cls, value):
        return normalize_harness_modules(value if isinstance(value, dict) else {})


def default_profiles() -> list[ProfileConfig]:
    return [
        ProfileConfig(id="baseline", label="NoHarness", harness_modules={}),
        ProfileConfig(
            id="harness",
            label="Harness",
            harness_modules={
                "context_summary": True,
                "source_map": True,
                "guardrails": True,
                "output_contract": True,
                "planning_preamble": False,
                "tool_policy": True,
                "memory_selection": True,
                "post_answer_critique": True,
                "token_budgeter": True,
                "consequence_gate": True,
            },
        ),
    ]


def default_agent_profiles() -> list[ProfileConfig]:
    return [
        ProfileConfig(id="baseline_agent", label="NoHarness Agent", harness_modules={}),
        ProfileConfig(
            id="harness_agent",
            label="Harness Agent",
            harness_modules={
                "context_summary": True,
                "source_map": True,
                "guardrails": True,
                "output_contract": True,
                "planning_preamble": True,
                "tool_policy": True,
                "memory_selection": True,
                "post_answer_critique": True,
                "token_budgeter": True,
                "consequence_gate": True,
            },
        ),
    ]


class RunAttachment(BaseModel):
    kind: Literal["image", "pdf"] = "image"
    id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=0)
    image_url: str | None = None
    detail: Literal["auto", "low", "high"] = "auto"
    data_base64: str | None = Field(default=None, exclude=True)
    page_count: int | None = Field(default=None, ge=0)
    char_count: int | None = Field(default=None, ge=0)
    line_count: int | None = Field(default=None, ge=0)
    parser: str | None = None
    text_path: str | None = None
    line_index_path: str | None = None
    block_index_path: str | None = None

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        if value == "image/jpg":
            return "image/jpeg"
        if value in SUPPORTED_RUN_IMAGE_MIME_TYPES or value in SUPPORTED_RUN_PDF_MIME_TYPES:
            return value
        raise ValueError("Attachments support image PNG, JPEG, WEBP, GIF, or PDF.")

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith(("data:image/", "https://", "http://")):
            return value
        raise ValueError("Image attachments must use a data URL or fully qualified URL.")

    @field_validator("data_base64")
    @classmethod
    def validate_data_base64(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("PDF data_base64 must not be empty.")
        return value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        return value

    @model_validator(mode="after")
    def validate_attachment_payload(self) -> "RunAttachment":
        if self.kind == "image":
            if self.mime_type not in SUPPORTED_RUN_IMAGE_MIME_TYPES:
                raise ValueError("Image attachments support PNG, JPEG, WEBP, or GIF.")
            if not self.image_url:
                raise ValueError("Image attachments require image_url.")
        if self.kind == "pdf":
            if self.mime_type not in SUPPORTED_RUN_PDF_MIME_TYPES:
                raise ValueError("PDF attachments require application/pdf mime_type.")
            if not self.data_base64 and not self.text_path:
                raise ValueError("PDF attachments require data_base64 before extraction.")
        return self


class RunCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    prompt: str = Field(min_length=1)
    input_mode: InputMode = InputMode.integrated
    model: str = Field(default="gpt-5.4-mini", min_length=1)
    reasoning_effort: str = Field(default="medium", min_length=1)
    profiles: list[ProfileConfig] = Field(default_factory=default_profiles, min_length=1)
    attachments: list[RunAttachment] = Field(default_factory=list)
    surface_payload: AgentRunConfig | None = None


class RunDocument(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    schema_version: str
    id: str
    project_id: str
    turn_index: int
    input_mode: InputMode
    model: str
    reasoning_effort: str
    profiles: list[ProfileConfig]
    attachments: list[RunAttachment] = Field(default_factory=list)
    surface_payload: AgentRunConfig | None = None
    status: RunStatus = RunStatus.submitted
    prompt: str
    created_at: str
    updated_at: str


def new_run_document(
    *,
    schema_version: str,
    run_id: str,
    project_id: str,
    turn_index: int,
    payload: RunCreate,
    profiles: list[ProfileConfig] | None = None,
) -> RunDocument:
    now = utc_now_iso()
    return RunDocument(
        schema_version=schema_version,
        id=run_id,
        project_id=project_id,
        turn_index=turn_index,
        input_mode=payload.input_mode,
        model=payload.model,
        reasoning_effort=payload.reasoning_effort,
        profiles=profiles or payload.profiles,
        attachments=payload.attachments,
        surface_payload=payload.surface_payload,
        prompt=payload.prompt,
        created_at=now,
        updated_at=now,
    )
