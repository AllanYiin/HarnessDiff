import type { HarnessModules, InputMode, PaneId } from "./types";

type Project = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

type Run = {
  id: string;
};

export type ProjectSummary = Project;

export type TranscriptRun = {
  id: string;
  prompt: string;
  target_panes: PaneId[];
  input_mode: InputMode;
  status: string;
  panes: Partial<Record<PaneId, { output_text: string }>>;
};

export type ProjectTranscript = {
  project: Project;
  runs: TranscriptRun[];
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function isPaneId(value: unknown): value is PaneId {
  return value === "NoHarness" || value === "Harness";
}

function normalizeProject(value: unknown, fallbackName: string): Project {
  if (!isRecord(value) || typeof value.id !== "string") {
    throw new Error("Project response is missing an id");
  }
  const now = new Date().toISOString();
  return {
    id: value.id,
    name: asString(value.name, fallbackName),
    created_at: asString(value.created_at, now),
    updated_at: asString(value.updated_at, now)
  };
}

function normalizeTranscriptRun(value: unknown): TranscriptRun | null {
  if (!isRecord(value) || typeof value.id !== "string" || typeof value.prompt !== "string") {
    return null;
  }
  const targetPanes = Array.isArray(value.target_panes)
    ? value.target_panes.filter(isPaneId)
    : [];
  const panes: TranscriptRun["panes"] = {};
  if (isRecord(value.panes)) {
    for (const pane of targetPanes) {
      const panePayload = value.panes[pane];
      panes[pane] = {
        output_text: isRecord(panePayload) ? asString(panePayload.output_text) : ""
      };
    }
  }
  return {
    id: value.id,
    prompt: value.prompt,
    target_panes: targetPanes,
    input_mode: value.input_mode === "independent" ? "independent" : "integrated",
    status: asString(value.status, "completed"),
    panes
  };
}

export async function createProject(name: string): Promise<Project> {
  const response = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(`Failed to create project: ${response.status}`);
  }
  return normalizeProject(await response.json(), name);
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const response = await fetch("/api/projects");
  if (!response.ok) {
    throw new Error(`Failed to list projects: ${response.status}`);
  }
  const data = await response.json();
  if (!isRecord(data) || !Array.isArray(data.projects)) {
    return [];
  }
  return data.projects.flatMap((project) => {
    try {
      return [normalizeProject(project, "未命名對話")];
    } catch {
      return [];
    }
  });
}

export async function updateProjectName(projectId: string, name: string): Promise<Project> {
  const response = await fetch(`/api/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(`Failed to rename project: ${response.status}`);
  }
  return normalizeProject(await response.json(), name);
}

export async function getProjectTranscript(projectId: string): Promise<ProjectTranscript> {
  const response = await fetch(`/api/projects/${projectId}/transcript`);
  if (!response.ok) {
    throw new Error(`Failed to load transcript: ${response.status}`);
  }
  const data = await response.json();
  if (!isRecord(data)) {
    throw new Error("Transcript response is not an object");
  }
  const project = normalizeProject(data.project, "未命名對話");
  const runs = Array.isArray(data.runs)
    ? data.runs.flatMap((run) => {
        const normalized = normalizeTranscriptRun(run);
        return normalized ? [normalized] : [];
      })
    : [];
  return { project, runs };
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
  onEvent: (event: RunStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`/api/runs/${runId}/stream`, {
    headers: { Accept: "text/event-stream" },
    signal
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
