export type ProfileId = string;

export type SurfaceType = "chat" | "workflow" | "agent" | "multi_agents";

export type InputMode = "integrated" | "independent";

export type HarnessModuleId =
  | "context_summary"
  | "source_map"
  | "guardrails"
  | "output_contract"
  | "planning_preamble"
  | "tool_policy"
  | "memory_selection"
  | "post_answer_critique"
  | "token_budgeter"
  | "consequence_gate"
  | "artifact_review";

export type HarnessModules = Record<HarnessModuleId, boolean>;

export type ProfileInstance = {
  id: ProfileId;
  label: string;
  harness_modules: Partial<HarnessModules>;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: "streaming" | "done";
  toolCalls?: ToolCallTrace[];
  skillInvocations?: SkillInvocationTrace[];
  attachments?: MessageAttachment[];
};

export type MessageAttachment = {
  id: string;
  name: string;
  kind: AttachmentPreview["kind"];
  type: string;
  size: number;
  status: AttachmentPreview["status"];
  url?: string;
};

export type ToolCallTrace = {
  id: string;
  tool_name: string;
  openai_name?: string;
  ok?: boolean;
  arguments?: unknown;
  result_summary?: string;
  error?: unknown;
  elapsed_ms?: number;
  token_usage?: TokenUsageTrace;
  subagent_id?: string | null;
  subagent_label?: string | null;
};

export type TokenUsageTrace = {
  source?: string;
  basis?: string;
  input_tokens?: number;
  cached_tokens?: number;
  output_tokens?: number;
  reasoning_tokens?: number;
  total_tokens?: number;
};

export type SkillInvocationTrace = {
  id: string;
  skill_id: string;
  status?: string;
  sequence?: number;
  token_usage?: TokenUsageTrace;
  metadata?: Record<string, unknown>;
};

export type AttachmentPreview = {
  id: string;
  name: string;
  type: string;
  size: number;
  status: "ready" | "error";
  kind: "text" | "csv" | "document" | "spreadsheet" | "presentation" | "pdf" | "image" | "unsupported";
  summary: string;
  content?: string;
  error?: string;
  url?: string;
  dataUrl?: string;
  visionSupported?: boolean;
  runAttachment?: RunAttachmentInput;
};

export type VisionAttachmentInput = {
  kind: "image";
  name: string;
  mime_type: string;
  size_bytes: number;
  image_url: string;
  detail?: "auto" | "low" | "high";
};

export type PdfAttachmentInput = {
  kind: "pdf";
  id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  data_base64: string;
};

export type RunAttachmentInput = VisionAttachmentInput | PdfAttachmentInput;

export type ProfileState = {
  messages: Message[];
  draft: string;
  streaming: boolean;
};

export type AgentRunConfig = {
  type: "agent";
  objective: string;
  context?: string;
  max_steps?: number;
  allow_subagents?: boolean;
  allow_container_tools?: boolean;
};

export type ArtifactKind = "plain_text" | "markdown" | "single_page_html" | "svg";

export type ArtifactIncludeMode = "summary" | "full";

export type ArtifactDocument = {
  schema_version: string;
  id: string;
  project_id: string;
  profile_id: ProfileId;
  kind: ArtifactKind;
  title: string;
  content: string;
  version: number;
  source_run_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type ArtifactCreateInput = {
  profile_id: ProfileId;
  kind: ArtifactKind;
  title: string;
  content: string;
  source_run_id?: string | null;
};

export type ArtifactPatchInput = {
  base_version: number;
  title?: string;
  kind?: ArtifactKind;
  content?: string;
  source_run_id?: string | null;
};

export type RunArtifactRef = {
  artifact_id: string;
  version: number;
  profile_id: ProfileId;
  include_mode: ArtifactIncludeMode;
};

export type AgentStepTrace = {
  id: string;
  profile_id: ProfileId;
  profile_label?: string;
  step_id: string;
  sequence: number;
  type: string;
  label: string;
  status: "running" | "completed" | "error" | "cancelled" | "skipped";
  tool_name?: string | null;
  subagent_id?: string | null;
  subagent_label?: string | null;
  elapsed_ms?: number | null;
  token_usage?: TokenUsageTrace;
};
