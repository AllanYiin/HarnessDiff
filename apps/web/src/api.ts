import type {
  HarnessModules,
  InputMode,
  AgentStepTrace,
  MessageAttachment,
  ProfileId,
  ProfileInstance,
  SurfaceType,
  ToolCallTrace,
  VisionAttachmentInput
} from "./types";

type Project = {
  id: string;
  name: string;
  surface_type: SurfaceType;
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
  input_mode: InputMode;
  status: string;
  attachments: MessageAttachment[];
  profiles: Array<ProfileInstance & { output_text: string; steps: AgentStepTrace[] }>;
};

export type ProjectTranscript = {
  project: Project;
  runs: TranscriptRun[];
};

export type RunStreamEvent = {
  run_id: string;
  profile_id?: ProfileId;
  profile_label?: string;
  type:
    | "created"
    | "delta"
    | "completed"
    | "error"
    | "tool_call"
    | "agent_step_started"
    | "agent_step_completed"
    | "agent_step_error"
    | "skill_invocation"
    | "analysis_ready"
    | "run_completed"
    | "run_failed";
  text?: string | null;
  message?: string;
  tool_call?: Omit<ToolCallTrace, "id">;
  agent_step?: Omit<AgentStepTrace, "id">;
  skill_id?: string;
  status?: string;
  sequence?: number;
  token_usage?: ToolCallTrace["token_usage"];
  metadata?: Record<string, unknown>;
  usage?: unknown;
  analysis?: AnalysisDocument;
};

export type TokenUsage = {
  input_tokens: number;
  cached_tokens: number;
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

export type HarnessDecisionTrace = {
  event_type?: string;
  event_id?: string;
  decision_id?: string;
  rule_id?: string | null;
  effect?: string;
  reason?: Record<string, unknown>;
  telemetry?: Record<string, unknown>;
  contributing_decisions?: HarnessDecisionTrace[];
};

export type ProfileAnalysis = {
  profile_id: ProfileId;
  profile_label: string;
  current_turn_usage: TokenUsage;
  cumulative_usage: TokenUsage;
  context_sections: ContextSection[];
  output_characters: number;
  enabled_harness_modules: string[];
  harness_decisions: HarnessDecisionTrace[];
  provider_context_keys: string[];
};

export type AnalysisDocument = {
  schema_version: string;
  project_id: string;
  run_id: string;
  turn_index: number;
  generated_at: string;
  profiles: Record<ProfileId, ProfileAnalysis>;
  comparison: {
    total_token_delta: number;
    input_token_delta: number;
    output_token_delta: number;
    reasoning_token_delta: number;
    controlled_profile_extra_sections: string[];
  };
  notes: string[];
};

export type SkillSummary = {
  id: string;
  name: string;
  description: string;
  version: string;
  path: string;
};

export type SkillListResponse = {
  home_dir: string;
  skills_dir: string;
  skills: SkillSummary[];
};

export type SkillDetail = {
  id: string;
  path: string;
  content: string;
};

export type SubagentSummary = {
  id: string;
  label: string;
  description: string;
  model: string;
  reasoning_effort: string;
  max_output_chars: number;
  tools?: string[];
  enabled: boolean;
  path: string;
};

export type SubagentListResponse = {
  agents_dir: string;
  subagents: SubagentSummary[];
};

export type SubagentCreatePayload = {
  id: string;
  label: string;
  description: string;
  instructions: string;
  model: string;
  reasoning_effort: string;
  max_output_chars: number;
  tools?: string[];
  enabled: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function normalizeHarnessModules(value: unknown): Partial<HarnessModules> {
  if (!isRecord(value)) {
    return {};
  }
  const modules = { ...value };
  if (!("context_summary" in modules) && "context_manifest" in modules) {
    modules.context_summary = modules.context_manifest;
  }
  delete modules.context_manifest;
  return modules as Partial<HarnessModules>;
}

function normalizeProject(value: unknown, fallbackName: string): Project {
  if (!isRecord(value) || typeof value.id !== "string") {
    throw new Error("Project response is missing an id");
  }
  const now = new Date().toISOString();
  return {
    id: value.id,
    name: asString(value.name, fallbackName),
    surface_type: normalizeSurfaceType(value.surface_type),
    created_at: asString(value.created_at, now),
    updated_at: asString(value.updated_at, now)
  };
}

function normalizeSurfaceType(value: unknown): SurfaceType {
  if (value === "agent" || value === "workflow" || value === "multi_agents") {
    return value;
  }
  return "chat";
}

function normalizeTranscriptRun(value: unknown): TranscriptRun | null {
  if (!isRecord(value) || typeof value.id !== "string" || typeof value.prompt !== "string") {
    return null;
  }
  const profiles = Array.isArray(value.profiles)
    ? value.profiles.flatMap((profile) => {
        if (!isRecord(profile) || typeof profile.id !== "string") return [];
        return [{
          id: profile.id,
          label: asString(profile.label, profile.id),
          harness_modules: normalizeHarnessModules(profile.harness_modules),
          output_text: asString(profile.output_text),
          steps: normalizeAgentSteps(profile.steps)
        }];
      })
    : [];
  return {
    id: value.id,
    prompt: value.prompt,
    input_mode: value.input_mode === "independent" ? "independent" : "integrated",
    status: asString(value.status, "completed"),
    attachments: normalizeTranscriptAttachments(value.attachments),
    profiles
  };
}

function normalizeAgentSteps(value: unknown): AgentStepTrace[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((step, index) => {
    if (!isRecord(step) || typeof step.profile_id !== "string" || typeof step.step_id !== "string") {
      return [];
    }
    const sequence = typeof step.sequence === "number" ? step.sequence : index;
    const type = asString(step.type, "agent_step_completed");
    const status = normalizeAgentStepStatus(step.status);
    return [
      {
        id: `${step.step_id}_${type}_${sequence}`,
        profile_id: step.profile_id,
        profile_label: asString(step.profile_label),
        step_id: step.step_id,
        sequence,
        type,
        label: asString(step.label, step.step_id),
        status,
        tool_name: typeof step.tool_name === "string" ? step.tool_name : null,
        subagent_id: typeof step.subagent_id === "string" ? step.subagent_id : null,
        subagent_label: typeof step.subagent_label === "string" ? step.subagent_label : null,
        elapsed_ms: typeof step.elapsed_ms === "number" ? step.elapsed_ms : null,
        token_usage: isRecord(step.token_usage)
          ? (step.token_usage as AgentStepTrace["token_usage"])
          : undefined
      }
    ];
  });
}

function normalizeAgentStepStatus(value: unknown): AgentStepTrace["status"] {
  if (
    value === "running" ||
    value === "completed" ||
    value === "error" ||
    value === "cancelled" ||
    value === "skipped"
  ) {
    return value;
  }
  return "completed";
}

function normalizeTranscriptAttachments(value: unknown): MessageAttachment[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((attachment, index) => {
    if (!isRecord(attachment) || attachment.kind !== "image") {
      return [];
    }
    const name = asString(attachment.name, `image-${index + 1}`);
    const imageUrl = asString(attachment.image_url);
    if (!imageUrl) {
      return [];
    }
    return [
      {
        id: `attachment_${index}_${name}`,
        name,
        kind: "image",
        type: asString(attachment.mime_type, "image/*"),
        size: typeof attachment.size_bytes === "number" ? attachment.size_bytes : 0,
        status: "ready",
        url: imageUrl
      }
    ];
  });
}

export async function createProject(name: string, surfaceType: SurfaceType = "chat"): Promise<Project> {
  const response = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, surface_type: surfaceType })
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
  profiles: ProfileInstance[];
  attachments?: VisionAttachmentInput[];
  surfacePayload?: Record<string, unknown> | null;
}): Promise<Run> {
  const response = await fetch(`/api/projects/${params.projectId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt: params.prompt,
      input_mode: params.inputMode,
      model: params.model,
      reasoning_effort: params.reasoningEffort,
      profiles: params.profiles,
      attachments: params.attachments ?? [],
      surface_payload: params.surfacePayload ?? null
    })
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "建立 run 失敗"));
  }
  return response.json();
}

export async function getRunAnalysis(runId: string): Promise<AnalysisDocument> {
  const response = await fetch(`/api/runs/${runId}/analysis`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "載入分析失敗"));
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
    throw new Error(await responseErrorMessage(response, "串流 run 失敗"));
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

export async function listSkills(): Promise<SkillListResponse> {
  const response = await fetch("/api/skills");
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "載入技能清單失敗"));
  }
  return response.json();
}

export async function getSkill(skillId: string): Promise<SkillDetail> {
  const response = await fetch(`/api/skills/${encodeURIComponent(skillId)}`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "載入技能內容失敗"));
  }
  return response.json();
}

export async function importSkillFile(file: File): Promise<SkillSummary> {
  const mode = file.name.toLowerCase().endsWith(".zip") ? "zip" : "skill";
  const response = await fetch("/api/skills/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode,
      filename: file.name,
      data_base64: await fileToBase64(file)
    })
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "匯入技能失敗"));
  }
  return (await response.json()).skill;
}

export async function importSkillFolder(files: FileList): Promise<SkillSummary> {
  const fileItems = await Promise.all(
    Array.from(files).map(async (file) => ({
      relative_path: file.webkitRelativePath || file.name,
      data_base64: await fileToBase64(file)
    }))
  );
  const response = await fetch("/api/skills/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: "folder",
      filename: folderNameFromFiles(files),
      files: fileItems
    })
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "匯入技能資料夾失敗"));
  }
  return (await response.json()).skill;
}

export async function listSubagents(): Promise<SubagentListResponse> {
  const response = await fetch("/api/subagents");
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "載入 Subagents 失敗"));
  }
  return response.json();
}

export async function createSubagent(payload: SubagentCreatePayload): Promise<SubagentSummary> {
  const response = await fetch("/api/subagents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "新增 Subagent 失敗"));
  }
  return (await response.json()).subagent;
}

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function folderNameFromFiles(files: FileList) {
  const first = files[0];
  const relativePath = first?.webkitRelativePath ?? "";
  return relativePath.split("/")[0] || "skill-folder";
}

async function responseErrorMessage(response: Response, action: string): Promise<string> {
  const suffix = await responseErrorDetail(response);
  return suffix ? `${action}：HTTP ${response.status} - ${suffix}` : `${action}：HTTP ${response.status}`;
}

async function responseErrorDetail(response: Response): Promise<string> {
  try {
    const data = await response.clone().json();
    if (typeof data === "string") {
      return data;
    }
    if (data && typeof data === "object") {
      const record = data as Record<string, unknown>;
      const detail = record.detail ?? record.message ?? record.error;
      if (typeof detail === "string") {
        return detail;
      }
      if (detail !== undefined) {
        return JSON.stringify(detail);
      }
    }
  } catch {
    // Fall through to plain-text body.
  }
  try {
    return (await response.text()).trim();
  } catch {
    return "";
  }
}
