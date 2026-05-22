export type PaneId = "NoHarness" | "Harness";

export type InputMode = "integrated" | "independent";

export type HarnessModuleId =
  | "context_manifest"
  | "source_map"
  | "guardrails"
  | "output_contract"
  | "planning_preamble"
  | "tool_policy"
  | "memory_selection"
  | "post_answer_critique"
  | "token_budgeter";

export type HarnessModules = Record<HarnessModuleId, boolean>;

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: "streaming" | "done";
};

export type AttachmentPreview = {
  id: string;
  name: string;
  type: string;
  size: number;
  url?: string;
};

export type PaneState = {
  messages: Message[];
  draft: string;
  streaming: boolean;
};
