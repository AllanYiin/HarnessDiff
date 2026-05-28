export type ProfileId = string;

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
  | "token_budgeter";

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
};

export type VisionAttachmentInput = {
  kind: "image";
  name: string;
  mime_type: string;
  size_bytes: number;
  image_url: string;
  detail?: "auto" | "low" | "high";
};

export type ProfileState = {
  messages: Message[];
  draft: string;
  streaming: boolean;
};
