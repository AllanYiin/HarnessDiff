import type { HarnessModules, InputMode, PaneId } from "./types";

type Project = {
  id: string;
};

type Run = {
  id: string;
};

export type RunStreamEvent = {
  run_id: string;
  pane?: PaneId;
  type:
    | "created"
    | "delta"
    | "completed"
    | "error"
    | "analysis_ready"
    | "run_completed"
    | "run_failed";
  text?: string | null;
  message?: string;
  usage?: unknown;
  analysis?: AnalysisDocument;
};

export type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  source: string;
};

export type ContextSection = {
  key: string;
  label: string;
  status: string;
  characters: number;
  estimated_tokens: number;
  notes: string;
};

export type PaneAnalysis = {
  pane: PaneId;
  current_turn_usage: TokenUsage;
  cumulative_usage: TokenUsage;
  context_sections: ContextSection[];
  output_characters: number;
  enabled_harness_modules: string[];
  provider_context_keys: string[];
};

export type AnalysisDocument = {
  schema_version: string;
  project_id: string;
  run_id: string;
  turn_index: number;
  generated_at: string;
  panes: Partial<Record<PaneId, PaneAnalysis>>;
  comparison: {
    total_token_delta: number;
    input_token_delta: number;
    output_token_delta: number;
    reasoning_token_delta: number;
    harness_extra_sections: string[];
  };
  notes: string[];
};

export async function createProject(name: string): Promise<Project> {
  const response = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(`Failed to create project: ${response.status}`);
  }
  return response.json();
}

export async function createRun(params: {
  projectId: string;
  prompt: string;
  inputMode: InputMode;
  model: string;
  reasoningEffort: string;
  targetPanes: PaneId[];
  harnessModules: HarnessModules;
}): Promise<Run> {
  const response = await fetch(`/api/projects/${params.projectId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt: params.prompt,
      input_mode: params.inputMode,
      model: params.model,
      reasoning_effort: params.reasoningEffort,
      target_panes: params.targetPanes,
      harness_modules: params.harnessModules
    })
  });
  if (!response.ok) {
    throw new Error(`Failed to create run: ${response.status}`);
  }
  return response.json();
}

export async function getRunAnalysis(runId: string): Promise<AnalysisDocument> {
  const response = await fetch(`/api/runs/${runId}/analysis`);
  if (!response.ok) {
    throw new Error(`Failed to load analysis: ${response.status}`);
  }
  return response.json();
}

export async function streamRun(
  runId: string,
  onEvent: (event: RunStreamEvent) => void
): Promise<void> {
  const response = await fetch(`/api/runs/${runId}/stream`, {
    headers: { Accept: "text/event-stream" }
  });
  if (!response.ok || !response.body) {
    throw new Error(`Failed to stream run: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk
        .split("\n")
        .find((candidate) => candidate.startsWith("data: "));
      if (!line) {
        continue;
      }
      onEvent(JSON.parse(line.slice("data: ".length)));
    }
  }
}
