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
  type: "created" | "delta" | "completed" | "error" | "run_completed";
  text?: string | null;
  message?: string;
  usage?: unknown;
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
