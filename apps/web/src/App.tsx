import { useEffect, useMemo, useRef, useState } from "react";

import { AnalysisSummary } from "./components/AnalysisSummary";
import { AgentComposer } from "./components/AgentComposer";
import { AgentWorkspace } from "./components/AgentWorkspace";
import { ChatPane } from "./components/ChatPane";
import { Composer } from "./components/Composer";
import { HistoryPanel } from "./components/HistoryPanel";
import { SkillPanel } from "./components/SkillPanel";
import { TopBar } from "./components/TopBar";
import {
  createProject,
  createRun,
  createSubagent,
  getProjectTranscript,
  getSkill,
  importSkillFile,
  importSkillFolder,
  listSkills,
  listProjects,
  listSubagents,
  streamRun,
  updateProjectName,
  type AnalysisDocument,
  type ProjectSummary,
  type RunStreamEvent,
  type SubagentCreatePayload,
  type SubagentSummary,
  type SkillSummary
} from "./api";
import { attachmentPromptBlock, attachmentVisionInputs, ingestFiles } from "./domain/fileIngestion";
import { nextInputModeAfterCompletedTurn } from "./domain/inputMode";
import { parseSkillCommandIds, skillDetailsPromptBlock } from "./domain/skillCommands";
import {
  readPreferredModel,
  readPreferredReasoningEffort,
  writePreferredModel,
  writePreferredReasoningEffort
} from "./domain/userPreferences";
import type {
  AgentStepTrace,
  AttachmentPreview,
  HarnessModuleId,
  HarnessModules,
  InputMode,
  Message,
  MessageAttachment,
  ProfileId,
  ProfileInstance,
  ProfileState,
  SurfaceType,
  VisionAttachmentInput
} from "./types";

const newConversationName = "新對話";
const activeProjectStorageKey = "harnessdiff.activeProjectId";
const preferredSurfaceStorageKey = "harnessdiff.preferredSurface";

const defaultHarnessModules: HarnessModules = {
  context_summary: true,
  source_map: true,
  guardrails: true,
  output_contract: true,
  planning_preamble: false,
  tool_policy: true,
  memory_selection: true,
  post_answer_critique: true,
  token_budgeter: true,
  consequence_gate: true
};

const defaultProfiles: ProfileInstance[] = [
  { id: "baseline", label: "NoHarness", harness_modules: {} },
  { id: "harness", label: "Harness", harness_modules: defaultHarnessModules }
];

const defaultAgentProfiles: ProfileInstance[] = [
  { id: "baseline_agent", label: "NoHarness Agent", harness_modules: {} },
  { id: "harness_agent", label: "Harness Agent", harness_modules: defaultHarnessModules }
];

function createMessage(
  role: Message["role"],
  text: string,
  status: Message["status"] = "done",
  attachments: MessageAttachment[] = []
) {
  return {
    id: `${role}_${crypto.randomUUID()}`,
    role,
    text,
    status,
    attachments
  };
}

const initialProfileState: ProfileState = {
  messages: [],
  draft: "",
  streaming: false
};

function createInitialProfileState(profiles: ProfileInstance[]): Record<ProfileId, ProfileState> {
  return Object.fromEntries(
    profiles.map((profile) => [profile.id, { ...initialProfileState, messages: [] }])
  );
}

function profilesForSurface(surfaceType: SurfaceType) {
  return surfaceType === "agent" ? defaultAgentProfiles : defaultProfiles;
}

function titleFromPrompt(prompt: string) {
  const compact = prompt.replace(/\s+/g, " ").trim();
  return compact.length > 32 ? `${compact.slice(0, 32)}...` : compact || newConversationName;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error || "未知錯誤");
}

export function App() {
  const [model, setModel] = useState(readPreferredModel);
  const [reasoningEffort, setReasoningEffort] = useState(readPreferredReasoningEffort);
  const [surfaceType, setSurfaceType] = useState<SurfaceType>(() => readPreferredSurface());
  const [turnCount, setTurnCount] = useState(0);
  const [inputMode, setInputMode] = useState<InputMode>("integrated");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState(newConversationName);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [skillsHomeDir, setSkillsHomeDir] = useState("");
  const [skillsDir, setSkillsDir] = useState("");
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillImporting, setSkillImporting] = useState(false);
  const [skillError, setSkillError] = useState("");
  const [selectedSkillId, setSelectedSkillId] = useState("");
  const [selectedSkillContent, setSelectedSkillContent] = useState("");
  const [agentsDir, setAgentsDir] = useState("");
  const [subagents, setSubagents] = useState<SubagentSummary[]>([]);
  const [subagentsLoading, setSubagentsLoading] = useState(false);
  const [creatingSubagent, setCreatingSubagent] = useState(false);
  const [profiles, setProfiles] = useState<ProfileInstance[]>(() => profilesForSurface(readPreferredSurface()));
  const [analysis, setAnalysis] = useState<AnalysisDocument | null>(null);
  const [integratedDraft, setIntegratedDraft] = useState("");
  const [attachments, setAttachments] = useState<AttachmentPreview[]>([]);
  const [agentSteps, setAgentSteps] = useState<Record<ProfileId, AgentStepTrace[]>>({});
  const [profileState, setProfileState] = useState<Record<ProfileId, ProfileState>>(
    () => createInitialProfileState(profilesForSurface(readPreferredSurface()))
  );
  const activeStreamControllers = useRef<Map<ProfileId, AbortController>>(new Map());
  const submittingProfilesRef = useRef<Set<ProfileId>>(new Set());
  const projectIdRef = useRef<string | null>(null);
  const projectNameRef = useRef(newConversationName);
  const projectCreationRef = useRef<Promise<string> | null>(null);

  const running = useMemo(
    () => profiles.some((profile) => profileState[profile.id]?.streaming),
    [profiles, profileState]
  );
  const profileDisabled = useMemo(
    () =>
      Object.fromEntries(
        profiles.map((profile) => [profile.id, Boolean(profileState[profile.id]?.streaming)])
      ),
    [profiles, profileState]
  );
  const configurableHarnessProfileId = useMemo(
    () =>
      profiles.find((profile) => Object.keys(profile.harness_modules).length > 0)?.id ??
      profiles[profiles.length - 1]?.id,
    [profiles]
  );
  const configurableHarnessModules = useMemo(
    () =>
      (profiles.find((profile) => profile.id === configurableHarnessProfileId)?.harness_modules ??
        {}) as HarnessModules,
    [configurableHarnessProfileId, profiles]
  );

  function updateProfileState(profileId: ProfileId, next: (current: ProfileState) => ProfileState) {
    setProfileState((current) => ({
      ...current,
      [profileId]: next(current[profileId] ?? { ...initialProfileState, messages: [] })
    }));
  }

  async function refreshProjects() {
    setHistoryLoading(true);
    try {
      const nextProjects = await listProjects();
      setProjects(nextProjects);
      return nextProjects;
    } catch {
      return [];
    } finally {
      setHistoryLoading(false);
    }
  }

  async function refreshSkills() {
    setSkillsLoading(true);
    try {
      const response = await listSkills();
      setSkillsHomeDir(response.home_dir);
      setSkillsDir(response.skills_dir);
      setSkills(response.skills);
      return response.skills;
    } catch (error) {
      setSkillError(errorMessage(error));
      return [];
    } finally {
      setSkillsLoading(false);
    }
  }

  async function refreshSubagents() {
    setSubagentsLoading(true);
    try {
      const response = await listSubagents();
      setAgentsDir(response.agents_dir);
      setSubagents(response.subagents);
      return response.subagents;
    } catch (error) {
      setSkillError(errorMessage(error));
      return [];
    } finally {
      setSubagentsLoading(false);
    }
  }

  useEffect(() => {
    let ignore = false;
    refreshProjects().then((loadedProjects) => {
      if (ignore) {
        return;
      }
      const savedProjectId = window.localStorage.getItem(activeProjectStorageKey);
      const savedProject = loadedProjects.find((project) => project.id === savedProjectId);
      if (savedProject) {
        loadConversation(savedProject.id);
      }
    });
    refreshSkills();
    refreshSubagents();

    return () => {
      ignore = true;
      abortActiveStreams();
    };
  }, []);

  useEffect(() => {
    projectIdRef.current = projectId;
  }, [projectId]);

  useEffect(() => {
    projectNameRef.current = projectName;
  }, [projectName]);

  function abortActiveStreams() {
    activeStreamControllers.current.forEach((controller) => controller.abort());
    activeStreamControllers.current.clear();
    submittingProfilesRef.current.clear();
  }

  function resetConversationState(
    nextProjectId: string | null,
    nextProjectName = newConversationName,
    nextSurfaceType = surfaceType
  ) {
    abortActiveStreams();
    projectCreationRef.current = null;
    projectIdRef.current = nextProjectId;
    projectNameRef.current = nextProjectName;
    setProjectId(nextProjectId);
    setProjectName(nextProjectName);
    setTurnCount(0);
    setInputMode("integrated");
    setAnalysis(null);
    setIntegratedDraft("");
    setAttachments([]);
    setSurfaceType(nextSurfaceType);
    const nextProfiles = profilesForSurface(nextSurfaceType);
    setProfiles(nextProfiles);
    setProfileState(createInitialProfileState(nextProfiles));
    setAgentSteps({});
    if (nextProjectId) {
      window.localStorage.setItem(activeProjectStorageKey, nextProjectId);
    } else {
      window.localStorage.removeItem(activeProjectStorageKey);
    }
  }

  async function startNewConversation() {
    resetConversationState(null);
    refreshSkills();
    refreshSubagents();
    try {
      const project = await createProject(newConversationName, surfaceType);
      setProjectId(project.id);
      setProjectName(project.name);
      setSurfaceType(project.surface_type);
      writePreferredSurface(project.surface_type);
      window.localStorage.setItem(activeProjectStorageKey, project.id);
      await refreshProjects();
    } catch {
      setHistoryOpen(false);
    }
  }

  async function handleImportSkillFile(file: File | null) {
    if (!file) {
      return;
    }
    setSkillImporting(true);
    setSkillError("");
    try {
      const skill = await importSkillFile(file);
      await refreshSkills();
      await selectSkill(skill.id);
    } catch (error) {
      setSkillError(errorMessage(error));
    } finally {
      setSkillImporting(false);
    }
  }

  async function handleImportSkillFolder(files: FileList | null) {
    if (!files || files.length === 0) {
      return;
    }
    setSkillImporting(true);
    setSkillError("");
    try {
      const skill = await importSkillFolder(files);
      await refreshSkills();
      await selectSkill(skill.id);
    } catch (error) {
      setSkillError(errorMessage(error));
    } finally {
      setSkillImporting(false);
    }
  }

  async function selectSkill(skillId: string) {
    setSelectedSkillId(skillId);
    setSkillError("");
    try {
      const detail = await getSkill(skillId);
      setSelectedSkillContent(detail.content);
    } catch (error) {
      setSelectedSkillContent("");
      setSkillError(errorMessage(error));
    }
  }

  async function handleCreateSubagent(payload: SubagentCreatePayload) {
    setCreatingSubagent(true);
    setSkillError("");
    try {
      await createSubagent(payload);
      await refreshSubagents();
    } catch (error) {
      setSkillError(errorMessage(error));
      throw error;
    } finally {
      setCreatingSubagent(false);
    }
  }

  async function loadConversation(nextProjectId: string) {
    if (running) {
      pauseExecution();
    }
    setHistoryLoading(true);
    try {
      const transcript = await getProjectTranscript(nextProjectId);
      const nextProfiles =
        transcript.runs[0]?.profiles.map(({ output_text, steps, ...profile }) => profile) ??
        profilesForSurface(transcript.project.surface_type);
      const nextProfileState = createInitialProfileState(nextProfiles);
      const nextAgentSteps: Record<ProfileId, AgentStepTrace[]> = {};
      for (const run of transcript.runs) {
        for (const profile of run.profiles) {
          const state = nextProfileState[profile.id] ?? { ...initialProfileState, messages: [] };
          state.messages.push({
            id: `${run.id}_${profile.id}_user`,
            role: "user",
            text: displayPromptFromProviderPrompt(run.prompt),
            status: "done",
            attachments: run.attachments
          });
          state.messages.push({
            id: `${run.id}_${profile.id}_assistant`,
            role: "assistant",
            text: profile.output_text || (run.status === "cancelled" ? "已暫停。" : ""),
            status: "done"
          });
          nextProfileState[profile.id] = state;
          if (profile.steps.length > 0) {
            nextAgentSteps[profile.id] = [
              ...(nextAgentSteps[profile.id] ?? []),
              ...profile.steps
            ];
          }
        }
      }
      setProjectId(transcript.project.id);
      setProjectName(transcript.project.name);
      setSurfaceType(transcript.project.surface_type);
      writePreferredSurface(transcript.project.surface_type);
      setProfiles(nextProfiles);
      setProfileState(nextProfileState);
      setAgentSteps(nextAgentSteps);
      setTurnCount(transcript.runs.length);
      setInputMode(transcript.runs.length > 0 ? "independent" : "integrated");
      setAnalysis(null);
      window.localStorage.setItem(activeProjectStorageKey, transcript.project.id);
      setHistoryOpen(false);
    } finally {
      setHistoryLoading(false);
    }
  }

  function prepareStreamingProfile(
    profileId: ProfileId,
    displayPrompt: string,
    assistantId: string,
    messageAttachments: MessageAttachment[]
  ) {
    updateProfileState(profileId, (current) => ({
      ...current,
      streaming: true,
      messages: [
        ...current.messages,
        createMessage("user", displayPrompt, "done", messageAttachments),
        { id: assistantId, role: "assistant", text: "", status: "streaming" }
      ]
    }));
  }

  function applyStreamEvent(event: RunStreamEvent, assistantIds: Record<ProfileId, string>) {
    if (!event.profile_id) {
      return;
    }
    if (event.type === "delta" && event.text) {
      updateProfileState(event.profile_id, (current) => ({
        ...current,
        messages: current.messages.map((message) =>
          message.id === assistantIds[event.profile_id as ProfileId]
            ? { ...message, text: `${message.text}${event.text}`, status: "streaming" }
            : message
        )
      }));
    }
    if (event.type === "tool_call" && event.tool_call) {
      const toolCall = event.tool_call;
      updateProfileState(event.profile_id, (current) => ({
        ...current,
        messages: current.messages.map((message) =>
          message.id === assistantIds[event.profile_id as ProfileId]
            ? {
                ...message,
                toolCalls: [
                  ...(message.toolCalls ?? []),
                  {
                    id: `tool_${crypto.randomUUID()}`,
                    ...toolCall,
                    tool_name: toolCall.tool_name || toolCall.openai_name || "unknown_tool"
                  }
                ]
              }
            : message
        )
      }));
    }
    if (event.type === "skill_invocation" && event.skill_id) {
      updateProfileState(event.profile_id, (current) => ({
        ...current,
        messages: current.messages.map((message) =>
          message.id === assistantIds[event.profile_id as ProfileId]
            ? {
                ...message,
                skillInvocations: [
                  ...(message.skillInvocations ?? []),
                  {
                    id: `skill_${crypto.randomUUID()}`,
                    skill_id: event.skill_id ?? "",
                    status: event.status,
                    sequence: event.sequence,
                    token_usage: event.token_usage,
                    metadata: event.metadata
                  }
                ]
              }
            : message
        )
      }));
    }
    if (event.type === "completed" || event.type === "error") {
      updateProfileState(event.profile_id, (current) => ({
        ...current,
        streaming: false,
        messages: current.messages.map((message) =>
          message.id === assistantIds[event.profile_id as ProfileId]
            ? {
                ...message,
                text:
                  event.type === "error" && !message.text
                    ? `串流失敗：${event.message ?? "請稍後重試"}`
                    : message.text,
                status: "done"
              }
            : message
        )
      }));
    }
  }

  function applyAgentStreamEvent(event: RunStreamEvent, assistantIds: Record<ProfileId, string>) {
    applyStreamEvent(event, assistantIds);
    if (
      event.agent_step &&
      (event.type === "agent_step_started" ||
        event.type === "agent_step_completed" ||
        event.type === "agent_step_error")
    ) {
      const step = event.agent_step;
      setAgentSteps((current) => ({
        ...current,
        [step.profile_id]: [
          ...(current[step.profile_id] ?? []).filter(
            (candidate) => !(candidate.step_id === step.step_id && candidate.type === step.type)
          ),
          {
            id: `${step.step_id}_${step.type}_${step.sequence}`,
            ...step
          }
        ]
      }));
    }
  }

  function markProfilesFailed(
    activeProfiles: ProfileInstance[],
    assistantIds: Record<ProfileId, string>,
    error: unknown
  ) {
    const text = `後端請求失敗：${errorMessage(error)}`;
    activeProfiles.forEach((profile) => {
      updateProfileState(profile.id, (current) => ({
        ...current,
        streaming: false,
        messages: current.messages.map((message) =>
          message.id === assistantIds[profile.id]
            ? {
                ...message,
                text,
                status: "done"
              }
            : message
        )
      }));
    });
  }

  async function ensureProject(prompt: string) {
    const autoName = titleFromPrompt(prompt);
    const currentProjectId = projectIdRef.current;
    if (currentProjectId) {
      if (turnCount === 0 && projectNameRef.current === newConversationName) {
        updateProjectName(currentProjectId, autoName)
          .then((project) => {
            projectNameRef.current = project.name;
            setProjectName(project.name);
            refreshProjects();
          })
          .catch(() => undefined);
      }
      return currentProjectId;
    }
    if (projectCreationRef.current) {
      return projectCreationRef.current;
    }
    projectCreationRef.current = createProject(autoName, surfaceType)
      .then((project) => {
        projectIdRef.current = project.id;
        projectNameRef.current = project.name;
        setProjectId(project.id);
        setProjectName(project.name);
        setSurfaceType(project.surface_type);
        writePreferredSurface(project.surface_type);
        window.localStorage.setItem(activeProjectStorageKey, project.id);
        refreshProjects();
        return project.id;
      })
      .finally(() => {
        projectCreationRef.current = null;
      });
    return projectCreationRef.current;
  }

  async function submitWithApi(
    prompt: string,
    displayPrompt: string,
    targetProfileIds: ProfileId[],
    mode: InputMode,
    visionAttachments: VisionAttachmentInput[],
    messageAttachments: MessageAttachment[],
    surfacePayload?: Record<string, unknown> | null
  ) {
    setAnalysis(null);
    const controller = new AbortController();
    const activeProfiles = profiles.filter((profile) => targetProfileIds.includes(profile.id));
    activeProfiles.forEach((profile) => {
      activeStreamControllers.current.set(profile.id, controller);
      submittingProfilesRef.current.add(profile.id);
    });
    const assistantIds = Object.fromEntries(
      activeProfiles.map((profile) => [profile.id, `assistant_${crypto.randomUUID()}`])
    );
    activeProfiles.forEach((profile) =>
      prepareStreamingProfile(profile.id, displayPrompt, assistantIds[profile.id], messageAttachments)
    );
    try {
      const activeProjectId = await ensureProject(prompt);
      const run = await createRun({
        projectId: activeProjectId,
        prompt,
        inputMode: mode,
        model,
        reasoningEffort,
        profiles: activeProfiles,
        attachments: visionAttachments,
        surfacePayload
      });
      await streamRun(
        run.id,
        (event) => {
          if (event.type === "analysis_ready" && event.analysis) {
            setAnalysis(event.analysis);
          }
          if (surfaceType === "agent") {
            applyAgentStreamEvent(event, assistantIds);
          } else {
            applyStreamEvent(event, assistantIds);
          }
        },
        controller.signal
      );
      refreshProjects();
      setTurnCount((current) => {
        const next = current + 1;
        setInputMode((currentMode) => nextInputModeAfterCompletedTurn(current, currentMode));
        return next;
      });
    } catch (error) {
      if (!isAbortError(error)) {
        setAnalysis(null);
        markProfilesFailed(activeProfiles, assistantIds, error);
      }
    } finally {
      activeProfiles.forEach((profile) => {
        if (activeStreamControllers.current.get(profile.id) === controller) {
          activeStreamControllers.current.delete(profile.id);
        }
        submittingProfilesRef.current.delete(profile.id);
      });
    }
  }

  async function submitIntegrated() {
    const draft = integratedDraft.trim();
    if ((!draft && attachments.length === 0) || running || submittingProfilesRef.current.size > 0) {
      return;
    }
    try {
      const prompt = await buildPromptWithContext(draft);
      const visionAttachments = attachmentVisionInputs(attachments);
      const messageAttachments = messageAttachmentPreviews(attachments);
      setIntegratedDraft("");
      clearAttachments();
      void submitWithApi(
        prompt,
        draft,
        profiles.map((profile) => profile.id),
        "integrated",
        visionAttachments,
        messageAttachments
      );
    } catch (error) {
      setSkillError(errorMessage(error));
      setSkillsOpen(true);
    }
  }

  async function submitProfile(profileId: ProfileId) {
    const profile = profiles.find((candidate) => candidate.id === profileId);
    const draft = profileState[profileId]?.draft.trim() ?? "";
    if (!profile) {
      return;
    }
    if (
      (!draft && attachments.length === 0) ||
      Boolean(profileState[profileId]?.streaming) ||
      submittingProfilesRef.current.has(profileId)
    ) {
      return;
    }
    try {
      const prompt = await buildPromptWithContext(draft);
      const visionAttachments = attachmentVisionInputs(attachments);
      const messageAttachments = messageAttachmentPreviews(attachments);
      updateProfileState(profileId, (current) => ({ ...current, draft: "" }));
      clearAttachments();
      void submitWithApi(prompt, draft, [profileId], "independent", visionAttachments, messageAttachments);
    } catch (error) {
      setSkillError(errorMessage(error));
      setSkillsOpen(true);
    }
  }

  async function submitAgentTask() {
    const draft = integratedDraft.trim();
    if ((!draft && attachments.length === 0) || running || submittingProfilesRef.current.size > 0) {
      return;
    }
    try {
      const prompt = await buildPromptWithContext(draft);
      const visionAttachments = attachmentVisionInputs(attachments);
      const messageAttachments = messageAttachmentPreviews(attachments);
      setIntegratedDraft("");
      clearAttachments();
      setAgentSteps({});
      void submitWithApi(
        prompt,
        draft,
        profiles.map((profile) => profile.id),
        "integrated",
        visionAttachments,
        messageAttachments,
        {
          type: "agent",
          objective: draft || "Inspect attached files",
          context: "",
          max_steps: 16,
          allow_subagents: true,
          allow_container_tools: true
        }
      );
    } catch (error) {
      setSkillError(errorMessage(error));
      setSkillsOpen(true);
    }
  }

  async function handleAttach(files: FileList | File[] | null) {
    if (!files || files.length === 0) {
      return;
    }
    const previews = await ingestFiles(files);
    setAttachments((current) => [...current, ...previews]);
  }

  function buildPromptWithAttachments(text: string) {
    return `${text}${attachmentPromptBlock(attachments)}`.trim();
  }

  function messageAttachmentPreviews(source: AttachmentPreview[]): MessageAttachment[] {
    return source.flatMap((attachment) => {
      if (attachment.status !== "ready") {
        return [];
      }
      return [
        {
          id: attachment.id,
          name: attachment.name,
          kind: attachment.kind,
          type: attachment.type,
          size: attachment.size,
          status: attachment.status,
          url: attachment.kind === "image" ? attachment.dataUrl ?? attachment.url : attachment.url
        }
      ];
    });
  }

  async function buildPromptWithContext(text: string) {
    const withAttachments = buildPromptWithAttachments(text);
    const skillIds = parseSkillCommandIds(text, skills);
    if (!skillIds.length) {
      return withAttachments;
    }
    const details = await Promise.all(skillIds.map((skillId) => getSkill(skillId)));
    return `${withAttachments}${skillDetailsPromptBlock(details)}`.trim();
  }

  function clearAttachments() {
    setAttachments((current) => {
      current.forEach((attachment) => {
        if (attachment.url) {
          URL.revokeObjectURL(attachment.url);
        }
      });
      return [];
    });
  }

  function displayPromptFromProviderPrompt(prompt: string) {
    const marker = "\n---\nUser-provided attachments:";
    const index = prompt.indexOf(marker);
    if (index >= 0) {
      return prompt.slice(0, index).trim();
    }
    return prompt;
  }

  function removeAttachment(id: string) {
    setAttachments((current) => {
      const target = current.find((attachment) => attachment.id === id);
      if (target?.url) {
        URL.revokeObjectURL(target.url);
      }
      return current.filter((attachment) => attachment.id !== id);
    });
  }

  function updateHarnessModule(id: HarnessModuleId, enabled: boolean) {
    if (!configurableHarnessProfileId) {
      return;
    }
    setProfiles((current) =>
      current.map((profile) =>
        profile.id === configurableHarnessProfileId
          ? {
              ...profile,
              harness_modules: { ...profile.harness_modules, [id]: enabled }
            }
          : profile
      )
    );
  }

  function updateModel(value: string) {
    setModel(value);
    writePreferredModel(value);
  }

  function updateReasoningEffort(value: string) {
    setReasoningEffort(value);
    writePreferredReasoningEffort(value);
  }

  function handleSurfaceChange(nextSurfaceType: SurfaceType) {
    if (running || nextSurfaceType === surfaceType) {
      return;
    }
    writePreferredSurface(nextSurfaceType);
    resetConversationState(null, newConversationName, nextSurfaceType);
    setHistoryOpen(false);
    setSkillsOpen(false);
  }

  function pauseExecution() {
    abortActiveStreams();
    setProfileState((current) => {
      const next = { ...current };
      for (const profile of profiles) {
        const state = next[profile.id] ?? { ...initialProfileState, messages: [] };
        next[profile.id] = {
          ...state,
          streaming: false,
          messages: state.messages.map((message) =>
            message.status === "streaming"
              ? {
                  ...message,
                  status: "done",
                  text: message.text || "已暫停。"
                }
              : message
          )
        };
      }
      return next;
    });
  }

  return (
    <main className="shell">
      <TopBar
        model={model}
        reasoningEffort={reasoningEffort}
        harnessModules={configurableHarnessModules}
        surfaceType={surfaceType}
        historyOpen={historyOpen}
        skillsOpen={skillsOpen}
        surfaceSwitchDisabled={running}
        onModelChange={updateModel}
        onReasoningEffortChange={updateReasoningEffort}
        onHarnessModuleChange={updateHarnessModule}
        onSurfaceChange={handleSurfaceChange}
        onNewConversation={startNewConversation}
        onToggleHistory={() => {
          setHistoryOpen((current) => !current);
          setSkillsOpen(false);
          refreshProjects();
        }}
        onToggleSkills={() => {
          setSkillsOpen((current) => !current);
          setHistoryOpen(false);
          refreshSkills();
          refreshSubagents();
        }}
      />
      {historyOpen ? (
        <HistoryPanel
          projects={projects}
          activeProjectId={projectId}
          loading={historyLoading}
          onSelectProject={loadConversation}
        />
      ) : null}
      {skillsOpen ? (
        <SkillPanel
          homeDir={skillsHomeDir}
          skillsDir={skillsDir}
          skills={skills}
          loading={skillsLoading}
          importing={skillImporting}
          selectedSkillId={selectedSkillId}
          selectedSkillContent={selectedSkillContent}
          agentsDir={agentsDir}
          subagents={subagents}
          subagentsLoading={subagentsLoading}
          creatingSubagent={creatingSubagent}
          error={skillError}
          onImportFile={handleImportSkillFile}
          onImportFolder={handleImportSkillFolder}
          onSelectSkill={selectSkill}
          onCreateSubagent={handleCreateSubagent}
        />
      ) : null}
      {surfaceType === "agent" ? (
        <AgentWorkspace profiles={profiles} profileState={profileState} steps={agentSteps} />
      ) : (
        <section className="workspace" aria-label="HarnessDiff chat comparison">
          {profiles.map((profile) => (
            <ChatPane
              key={profile.id}
              profile={profile}
              messages={profileState[profile.id]?.messages ?? []}
              streaming={profileState[profile.id]?.streaming ?? false}
            />
          ))}
        </section>
      )}
      <AnalysisSummary
        turnCount={turnCount}
        inputMode={inputMode}
        running={running}
        analysis={analysis}
      />
      {surfaceType === "agent" ? (
        <AgentComposer
          draft={integratedDraft}
          attachments={attachments}
          disabled={running}
          running={running}
          onDraftChange={setIntegratedDraft}
          onAttach={handleAttach}
          onRemoveAttachment={removeAttachment}
          onSubmit={submitAgentTask}
          onCancel={pauseExecution}
        />
      ) : (
        <Composer
          inputMode={inputMode}
          integratedDraft={integratedDraft}
          profiles={profiles}
          profileDrafts={Object.fromEntries(
            profiles.map((profile) => [profile.id, profileState[profile.id]?.draft ?? ""])
          )}
          skills={skills}
          attachments={attachments}
          disabled={running}
          profileDisabled={profileDisabled}
          running={running}
          onModeChange={setInputMode}
          onIntegratedDraftChange={setIntegratedDraft}
          onProfileDraftChange={(profileId, value) =>
            updateProfileState(profileId, (current) => ({ ...current, draft: value }))
          }
          onAttach={handleAttach}
          onRemoveAttachment={removeAttachment}
          onSubmitIntegrated={submitIntegrated}
          onSubmitProfile={submitProfile}
          onPause={pauseExecution}
        />
      )}
    </main>
  );
}

function readPreferredSurface(): SurfaceType {
  const value = window.localStorage.getItem(preferredSurfaceStorageKey);
  return value === "agent" ? "agent" : "chat";
}

function writePreferredSurface(surfaceType: SurfaceType) {
  if (surfaceType === "chat" || surfaceType === "agent") {
    window.localStorage.setItem(preferredSurfaceStorageKey, surfaceType);
  }
}
