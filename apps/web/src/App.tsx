import { useEffect, useMemo, useRef, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";

import { CameraRigSimulator } from "./camera-rig/CameraRigSimulator";
import { PrismDropApp } from "./prism-drop/PrismDropApp";
import { AnalysisSummary } from "./components/AnalysisSummary";
import { AgentWorkspace } from "./components/AgentWorkspace";
import { ArtifactWorkbench } from "./components/ArtifactWorkbench";
import { ChatPane } from "./components/ChatPane";
import { Composer } from "./components/Composer";
import { HistoryPanel } from "./components/HistoryPanel";
import { SkillPanel } from "./components/SkillPanel";
import { TopBar } from "./components/TopBar";
import {
  createProject,
  createArtifact,
  createRun,
  createSubagent,
  deleteSubagent,
  deleteSkill,
  deleteTool,
  getProjectTranscript,
  getRunAnalysis,
  getSkill,
  importSkillFile,
  importSkillFolder,
  listSkills,
  listProjects,
  listSubagents,
  listTools,
  listArtifacts,
  patchArtifact,
  streamRun,
  transcribeAudio,
  updateSubagentEnabled,
  updateSkillEnabled,
  updateToolEnabled,
  updateProjectName,
  type AnalysisDocument,
  type ProjectSummary,
  type RunStreamEvent,
  type SubagentCreatePayload,
  type SubagentSummary,
  type SkillSummary,
  type ToolSummary
} from "./api";
import { attachmentPromptBlock, attachmentRunInputs, ingestFiles } from "./domain/fileIngestion";
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
  ArtifactDocument,
  ArtifactKind,
  AttachmentPreview,
  HarnessModuleId,
  HarnessModules,
  InputMode,
  Message,
  MessageAttachment,
  ProfileId,
  ProfileInstance,
  ProfileState,
  RunArtifactRef,
  SurfaceType,
  RunAttachmentInput
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
  consequence_gate: true,
  artifact_review: true
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

function createInitialProfileAttachments(
  profiles: ProfileInstance[]
): Record<ProfileId, AttachmentPreview[]> {
  return Object.fromEntries(profiles.map((profile) => [profile.id, []]));
}

function createInitialArtifacts(profiles: ProfileInstance[]): Record<ProfileId, ArtifactDocument | null> {
  return Object.fromEntries(profiles.map((profile) => [profile.id, null]));
}

function createInitialArtifactDrafts(profiles: ProfileInstance[]): Record<ProfileId, string> {
  return Object.fromEntries(profiles.map((profile) => [profile.id, ""]));
}

function createInitialArtifactTitles(profiles: ProfileInstance[]): Record<ProfileId, string> {
  return Object.fromEntries(profiles.map((profile) => [profile.id, `${profile.label} canvas`]));
}

function createInitialArtifactKinds(profiles: ProfileInstance[]): Record<ProfileId, ArtifactKind> {
  return Object.fromEntries(profiles.map((profile) => [profile.id, "markdown"]));
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
  const demoMode = new URLSearchParams(window.location.search).get("demo");
  if (demoMode === "camera-rig" || window.location.hash === "#camera-rig") {
    return <CameraRigSimulator />;
  }
  if (demoMode === "prism-drop" || window.location.hash === "#prism-drop") {
    return <PrismDropApp />;
  }
  return <HarnessDiffApp />;
}

function HarnessDiffApp() {
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
  const [managementErrors, setManagementErrors] = useState<{
    skills: string;
    subagents: string;
    tools: string;
  }>({ skills: "", subagents: "", tools: "" });
  const [selectedSkillId, setSelectedSkillId] = useState("");
  const [selectedSkillContent, setSelectedSkillContent] = useState("");
  const [agentsDir, setAgentsDir] = useState("");
  const [subagents, setSubagents] = useState<SubagentSummary[]>([]);
  const [subagentsLoading, setSubagentsLoading] = useState(false);
  const [creatingSubagent, setCreatingSubagent] = useState(false);
  const [tools, setTools] = useState<ToolSummary[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [profiles, setProfiles] = useState<ProfileInstance[]>(() => profilesForSurface(readPreferredSurface()));
  const [analysis, setAnalysis] = useState<AnalysisDocument | null>(null);
  const [integratedDraft, setIntegratedDraft] = useState("");
  const [integratedAttachments, setIntegratedAttachments] = useState<AttachmentPreview[]>([]);
  const [profileAttachments, setProfileAttachments] = useState<Record<ProfileId, AttachmentPreview[]>>(
    () => createInitialProfileAttachments(profilesForSurface(readPreferredSurface()))
  );
  const [artifactsByProfile, setArtifactsByProfile] = useState<Record<ProfileId, ArtifactDocument | null>>(
    () => createInitialArtifacts(profilesForSurface(readPreferredSurface()))
  );
  const [artifactDrafts, setArtifactDrafts] = useState<Record<ProfileId, string>>(
    () => createInitialArtifactDrafts(profilesForSurface(readPreferredSurface()))
  );
  const [artifactTitles, setArtifactTitles] = useState<Record<ProfileId, string>>(
    () => createInitialArtifactTitles(profilesForSurface(readPreferredSurface()))
  );
  const [artifactKinds, setArtifactKinds] = useState<Record<ProfileId, ArtifactKind>>(
    () => createInitialArtifactKinds(profilesForSurface(readPreferredSurface()))
  );
  const [savingArtifacts, setSavingArtifacts] = useState<Record<ProfileId, boolean>>({});
  const [artifactError, setArtifactError] = useState("");
  const [canvasOpenByProfile, setCanvasOpenByProfile] = useState<Record<ProfileId, boolean>>({});
  const [agentSteps, setAgentSteps] = useState<Record<ProfileId, AgentStepTrace[]>>({});
  const [profileState, setProfileState] = useState<Record<ProfileId, ProfileState>>(
    () => createInitialProfileState(profilesForSurface(readPreferredSurface()))
  );
  const activeStreamControllers = useRef<Map<ProfileId, AbortController>>(new Map());
  const assistantTextBuffers = useRef<Record<ProfileId, string>>({});
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
  const enabledSkills = useMemo(
    () => skills.filter((skill) => skill.enabled),
    [skills]
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
      setManagementErrors((current) => ({ ...current, skills: "" }));
      return response.skills;
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
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
      setManagementErrors((current) => ({ ...current, subagents: "" }));
      return response.subagents;
    } catch (error) {
      setManagementErrors((current) => ({ ...current, subagents: errorMessage(error) }));
      return [];
    } finally {
      setSubagentsLoading(false);
    }
  }

  async function refreshTools() {
    setToolsLoading(true);
    try {
      const response = await listTools();
      setTools(response.tools);
      setManagementErrors((current) => ({ ...current, tools: "" }));
      return response.tools;
    } catch (error) {
      setManagementErrors((current) => ({ ...current, tools: errorMessage(error) }));
      return [];
    } finally {
      setToolsLoading(false);
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
    refreshTools();

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
    clearAttachmentList(integratedAttachments);
    Object.values(profileAttachments).forEach(clearAttachmentList);
    setIntegratedAttachments([]);
    setSurfaceType(nextSurfaceType);
    const nextProfiles = profilesForSurface(nextSurfaceType);
    setProfiles(nextProfiles);
    setProfileState(createInitialProfileState(nextProfiles));
    setProfileAttachments(createInitialProfileAttachments(nextProfiles));
    setArtifactsByProfile(createInitialArtifacts(nextProfiles));
    setArtifactDrafts(createInitialArtifactDrafts(nextProfiles));
    setArtifactTitles(createInitialArtifactTitles(nextProfiles));
    setArtifactKinds(createInitialArtifactKinds(nextProfiles));
    setSavingArtifacts({});
    setArtifactError("");
    setCanvasOpenByProfile({});
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
    refreshTools();
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
    setManagementErrors((current) => ({ ...current, skills: "" }));
    try {
      const skill = await importSkillFile(file);
      await refreshSkills();
      await selectSkill(skill.id);
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
    } finally {
      setSkillImporting(false);
    }
  }

  async function handleImportSkillFolder(files: FileList | null) {
    if (!files || files.length === 0) {
      return;
    }
    setSkillImporting(true);
    setManagementErrors((current) => ({ ...current, skills: "" }));
    try {
      const skill = await importSkillFolder(files);
      await refreshSkills();
      await selectSkill(skill.id);
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
    } finally {
      setSkillImporting(false);
    }
  }

  async function selectSkill(skillId: string) {
    setSelectedSkillId(skillId);
    setManagementErrors((current) => ({ ...current, skills: "" }));
    try {
      const detail = await getSkill(skillId);
      setSelectedSkillContent(detail.content);
    } catch (error) {
      setSelectedSkillContent("");
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
    }
  }

  async function handleCreateSubagent(payload: SubagentCreatePayload) {
    setCreatingSubagent(true);
    setManagementErrors((current) => ({ ...current, subagents: "" }));
    try {
      await createSubagent(payload);
      await refreshSubagents();
    } catch (error) {
      setManagementErrors((current) => ({ ...current, subagents: errorMessage(error) }));
      throw error;
    } finally {
      setCreatingSubagent(false);
    }
  }

  async function handleToggleSubagent(subagentId: string, enabled: boolean) {
    setManagementErrors((current) => ({ ...current, subagents: "" }));
    try {
      const updated = await updateSubagentEnabled(subagentId, enabled);
      setSubagents((current) =>
        current.map((subagent) =>
          subagent.id === updated.id ? { ...subagent, ...updated } : subagent
        )
      );
    } catch (error) {
      setManagementErrors((current) => ({ ...current, subagents: errorMessage(error) }));
    }
  }

  async function handleDeleteSubagent(subagentId: string) {
    setManagementErrors((current) => ({ ...current, subagents: "" }));
    try {
      await deleteSubagent(subagentId);
      setSubagents((current) => current.filter((subagent) => subagent.id !== subagentId));
    } catch (error) {
      setManagementErrors((current) => ({ ...current, subagents: errorMessage(error) }));
    }
  }

  async function handleToggleSkill(skillId: string, enabled: boolean) {
    setManagementErrors((current) => ({ ...current, skills: "" }));
    try {
      const updated = await updateSkillEnabled(skillId, enabled);
      setSkills((current) =>
        current.map((skill) => (skill.id === updated.id ? { ...skill, ...updated } : skill))
      );
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
    }
  }

  async function handleDeleteSkill(skillId: string) {
    setManagementErrors((current) => ({ ...current, skills: "" }));
    try {
      await deleteSkill(skillId);
      setSkills((current) => current.filter((skill) => skill.id !== skillId));
      if (selectedSkillId === skillId) {
        setSelectedSkillId("");
        setSelectedSkillContent("");
      }
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
    }
  }

  async function handleToggleTool(toolId: string, enabled: boolean) {
    setManagementErrors((current) => ({ ...current, tools: "" }));
    try {
      const updated = await updateToolEnabled(toolId, enabled);
      setTools((current) =>
        current.map((tool) => (tool.id === updated.id ? { ...tool, ...updated } : tool))
      );
    } catch (error) {
      setManagementErrors((current) => ({ ...current, tools: errorMessage(error) }));
    }
  }

  async function handleDeleteTool(toolId: string) {
    setManagementErrors((current) => ({ ...current, tools: "" }));
    try {
      await deleteTool(toolId);
      setTools((current) => current.filter((tool) => tool.id !== toolId));
    } catch (error) {
      setManagementErrors((current) => ({ ...current, tools: errorMessage(error) }));
    }
  }

  async function loadConversation(nextProjectId: string) {
    if (running) {
      pauseExecution();
    }
    setHistoryLoading(true);
    try {
      const transcript = await getProjectTranscript(nextProjectId);
      const latestCompletedRun = [...transcript.runs]
        .reverse()
        .find((run) => run.status === "completed");
      const restoredAnalysis = latestCompletedRun
        ? await getRunAnalysis(latestCompletedRun.id).catch(() => null)
        : null;
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
            status: "done",
            toolCalls: profile.tool_calls,
            skillInvocations: profile.skill_invocations
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
      setIntegratedAttachments([]);
      setProfileAttachments(createInitialProfileAttachments(nextProfiles));
      await loadProjectArtifacts(transcript.project.id, nextProfiles);
      setAgentSteps(nextAgentSteps);
      setTurnCount(transcript.runs.length);
      setInputMode(transcript.runs.length > 0 ? "independent" : "integrated");
      setAnalysis(restoredAnalysis);
      window.localStorage.setItem(activeProjectStorageKey, transcript.project.id);
      setHistoryOpen(false);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadProjectArtifacts(activeProjectId: string, nextProfiles: ProfileInstance[]) {
    try {
      const artifacts = await listArtifacts(activeProjectId);
      const latestByProfile = createInitialArtifacts(nextProfiles);
      for (const artifact of artifacts) {
        if (!latestByProfile[artifact.profile_id]) {
          latestByProfile[artifact.profile_id] = artifact;
        }
      }
      setArtifactsByProfile(latestByProfile);
      setArtifactDrafts(
        Object.fromEntries(
          nextProfiles.map((profile) => [
            profile.id,
            latestByProfile[profile.id]?.content ?? ""
          ])
        )
      );
      setArtifactTitles(
        Object.fromEntries(
          nextProfiles.map((profile) => [
            profile.id,
            latestByProfile[profile.id]?.title ?? `${profile.label} canvas`
          ])
        )
      );
      setArtifactKinds(
        Object.fromEntries(
          nextProfiles.map((profile) => [
            profile.id,
            latestByProfile[profile.id]?.kind ?? "markdown"
          ])
        )
      );
      setArtifactError("");
      setCanvasOpenByProfile({});
    } catch (error) {
      setArtifactError(errorMessage(error));
      setArtifactsByProfile(createInitialArtifacts(nextProfiles));
      setArtifactDrafts(createInitialArtifactDrafts(nextProfiles));
      setArtifactTitles(createInitialArtifactTitles(nextProfiles));
      setArtifactKinds(createInitialArtifactKinds(nextProfiles));
      setCanvasOpenByProfile({});
    }
  }

  async function saveArtifactForProfile(
    profileId: ProfileId,
    projectIdOverride?: string
  ): Promise<ArtifactDocument | null> {
    const profile = profiles.find((candidate) => candidate.id === profileId);
    const activeProjectId = projectIdOverride ?? (await ensureProject(projectName));
    if (!profile || !activeProjectId) {
      return null;
    }
    const existing = artifactsByProfile[profileId] ?? null;
    const content = artifactDrafts[profileId] ?? existing?.content ?? "";
    const title = (artifactTitles[profileId] ?? existing?.title ?? `${profile.label} canvas`).trim();
    const kind = existing?.kind ?? artifactKinds[profileId] ?? inferArtifactKindFromContent(content);
    if (!existing && !content.trim()) {
      return null;
    }
    setSavingArtifacts((current) => ({ ...current, [profileId]: true }));
    setArtifactError("");
    try {
      const saved = existing
        ? await patchArtifact(activeProjectId, existing.id, {
            base_version: existing.version,
            title,
            kind,
            content
          })
        : await createArtifact(activeProjectId, {
            profile_id: profileId,
            title,
            kind,
            content
          });
      setArtifactsByProfile((current) => ({ ...current, [profileId]: saved }));
      setArtifactDrafts((current) => ({ ...current, [profileId]: saved.content }));
      setArtifactTitles((current) => ({ ...current, [profileId]: saved.title }));
      setArtifactKinds((current) => ({ ...current, [profileId]: saved.kind }));
      return saved;
    } catch (error) {
      setArtifactError(errorMessage(error));
      return null;
    } finally {
      setSavingArtifacts((current) => ({ ...current, [profileId]: false }));
    }
  }

  async function ensureArtifactsForRun(
    activeProjectId: string,
    targetProfileIds: ProfileId[],
    mode: InputMode
  ): Promise<RunArtifactRef[]> {
    const nextDrafts = { ...artifactDrafts };
    const nextTitles = { ...artifactTitles };
    const nextKinds = { ...artifactKinds };
    if (mode === "integrated" && targetProfileIds.length > 1) {
      const seedProfileId =
        targetProfileIds.find((profileId) => (nextDrafts[profileId] ?? "").trim()) ??
        targetProfileIds[0];
      const seedDraft = nextDrafts[seedProfileId] ?? "";
      const seedTitle = nextTitles[seedProfileId] ?? "Shared canvas";
      const seedKind = nextKinds[seedProfileId] ?? inferArtifactKindFromContent(seedDraft);
      if (seedDraft.trim()) {
        for (const profileId of targetProfileIds) {
          if (!artifactsByProfile[profileId] && !(nextDrafts[profileId] ?? "").trim()) {
            nextDrafts[profileId] = seedDraft;
            nextTitles[profileId] = seedTitle;
            nextKinds[profileId] = seedKind;
          }
        }
        setArtifactDrafts(nextDrafts);
        setArtifactTitles(nextTitles);
        setArtifactKinds(nextKinds);
      }
    }

    const refs: RunArtifactRef[] = [];
    for (const profileId of targetProfileIds) {
      const expectedContent = nextDrafts[profileId] ?? artifactsByProfile[profileId]?.content ?? "";
      const artifact = await saveArtifactForProfileWithState(
        profileId,
        activeProjectId,
        nextDrafts,
        nextTitles,
        nextKinds
      );
      if (!artifact && (artifactsByProfile[profileId] || expectedContent.trim())) {
        throw new Error("Could not save artifact canvas before creating the run.");
      }
      if (artifact) {
        refs.push({
          artifact_id: artifact.id,
          version: artifact.version,
          profile_id: profileId,
          include_mode: "full"
        });
      }
    }
    return refs;
  }

  async function saveArtifactForProfileWithState(
    profileId: ProfileId,
    activeProjectId: string,
    drafts: Record<ProfileId, string>,
    titles: Record<ProfileId, string>,
    kinds: Record<ProfileId, ArtifactKind>
  ): Promise<ArtifactDocument | null> {
    const profile = profiles.find((candidate) => candidate.id === profileId);
    if (!profile) {
      return null;
    }
    const existing = artifactsByProfile[profileId] ?? null;
    const content = drafts[profileId] ?? existing?.content ?? "";
    const title = (titles[profileId] ?? existing?.title ?? `${profile.label} canvas`).trim();
    const kind = existing?.kind ?? kinds[profileId] ?? inferArtifactKindFromContent(content);
    if (!existing && !content.trim()) {
      return null;
    }
    if (
      existing &&
      existing.content === content &&
      existing.title === title &&
      existing.kind === kind
    ) {
      return existing;
    }
    setSavingArtifacts((current) => ({ ...current, [profileId]: true }));
    try {
      const saved = existing
        ? await patchArtifact(activeProjectId, existing.id, {
            base_version: existing.version,
            title,
            kind,
            content
          })
        : await createArtifact(activeProjectId, {
            profile_id: profileId,
            title,
            kind,
            content
          });
      setArtifactsByProfile((current) => ({ ...current, [profileId]: saved }));
      setArtifactDrafts((current) => ({ ...current, [profileId]: saved.content }));
      setArtifactTitles((current) => ({ ...current, [profileId]: saved.title }));
      setArtifactKinds((current) => ({ ...current, [profileId]: saved.kind }));
      return saved;
    } catch (error) {
      setArtifactError(errorMessage(error));
      return null;
    } finally {
      setSavingArtifacts((current) => ({ ...current, [profileId]: false }));
    }
  }

  function initializeIntegratedCanvases(profileId: ProfileId) {
    const seedDraft = artifactDrafts[profileId] ?? "";
    const seedTitle = artifactTitles[profileId] ?? "Shared canvas";
    const seedKind = artifactKinds[profileId] ?? inferArtifactKindFromContent(seedDraft);
    if (!seedDraft.trim()) {
      return;
    }
    setArtifactDrafts((current) => ({
      ...current,
      ...Object.fromEntries(
        profiles
          .filter((profile) => !artifactsByProfile[profile.id] && !(current[profile.id] ?? "").trim())
          .map((profile) => [profile.id, seedDraft])
      )
    }));
    setArtifactTitles((current) => ({
      ...current,
      ...Object.fromEntries(
        profiles
          .filter((profile) => !artifactsByProfile[profile.id])
          .map((profile) => [profile.id, seedTitle])
      )
    }));
    setArtifactKinds((current) => ({
      ...current,
      ...Object.fromEntries(
        profiles
          .filter((profile) => !artifactsByProfile[profile.id])
          .map((profile) => [profile.id, seedKind])
      )
    }));
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
      assistantTextBuffers.current[event.profile_id] = `${
        assistantTextBuffers.current[event.profile_id] ?? ""
      }${event.text}`;
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
      if (event.type === "completed") {
        void applyArtifactUpdatesFromText(
          event.profile_id,
          assistantTextBuffers.current[event.profile_id] ?? ""
        );
      }
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

  async function applyArtifactUpdatesFromText(profileId: ProfileId, text: string) {
    const activeProjectId = projectIdRef.current;
    if (!activeProjectId || !text.includes("harnessdiff-artifact-update")) {
      return;
    }
    const updates = parseArtifactUpdateBlocks(text).filter((update) => update.profile_id === profileId);
    for (const update of updates) {
      const currentArtifact = artifactsByProfile[profileId];
      if (currentArtifact && update.artifact_id !== currentArtifact.id) {
        setArtifactError("Artifact update ignored because it targeted a different canvas.");
        continue;
      }
      try {
        const saved = await patchArtifact(activeProjectId, update.artifact_id, {
          base_version: update.base_version,
          title: update.title,
          kind: update.kind,
          content: update.content
        });
        setArtifactsByProfile((current) => ({ ...current, [profileId]: saved }));
        setArtifactDrafts((current) => ({ ...current, [profileId]: saved.content }));
        setArtifactTitles((current) => ({ ...current, [profileId]: saved.title }));
        setArtifactKinds((current) => ({ ...current, [profileId]: saved.kind }));
        setArtifactError("");
      } catch (error) {
        setArtifactError(errorMessage(error));
      }
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
    runAttachments: RunAttachmentInput[],
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
    activeProfiles.forEach((profile) => {
      assistantTextBuffers.current[profile.id] = "";
    });
    activeProfiles.forEach((profile) =>
      prepareStreamingProfile(profile.id, displayPrompt, assistantIds[profile.id], messageAttachments)
    );
    try {
      const activeProjectId = await ensureProject(prompt);
      const artifactRefs = await ensureArtifactsForRun(activeProjectId, targetProfileIds, mode);
      const run = await createRun({
        projectId: activeProjectId,
        prompt,
        inputMode: mode,
        model,
        reasoningEffort,
        profiles: activeProfiles,
        attachments: runAttachments,
        artifactRefs,
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
    if (
      (!draft && integratedAttachments.length === 0) ||
      running ||
      submittingProfilesRef.current.size > 0
    ) {
      return;
    }
    try {
      const prompt = await buildPromptWithContext(draft, integratedAttachments);
      const runAttachments = attachmentRunInputs(integratedAttachments);
      const messageAttachments = messageAttachmentPreviews(integratedAttachments);
      setIntegratedDraft("");
      clearAttachments("integrated");
      void submitWithApi(
        prompt,
        draft,
        profiles.map((profile) => profile.id),
        "integrated",
        runAttachments,
        messageAttachments
      );
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
      setSkillsOpen(true);
    }
  }

  async function submitProfile(profileId: ProfileId) {
    const profile = profiles.find((candidate) => candidate.id === profileId);
    const draft = profileState[profileId]?.draft.trim() ?? "";
    const attachments = profileAttachments[profileId] ?? [];
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
      const prompt = await buildPromptWithContext(draft, attachments);
      const runAttachments = attachmentRunInputs(attachments);
      const messageAttachments = messageAttachmentPreviews(attachments);
      updateProfileState(profileId, (current) => ({ ...current, draft: "" }));
      clearAttachments(profileId);
      void submitWithApi(prompt, draft, [profileId], "independent", runAttachments, messageAttachments);
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
      setSkillsOpen(true);
    }
  }

  function agentSurfacePayload(objective: string) {
    return {
      type: "agent",
      objective: objective || "Inspect attached files",
      context: "",
      max_steps: 16,
      allow_subagents: true,
      allow_container_tools: true
    };
  }

  function clearAgentStepsForProfiles(profileIds: ProfileId[]) {
    const targets = new Set(profileIds);
    setAgentSteps((current) =>
      Object.fromEntries(Object.entries(current).filter(([profileId]) => !targets.has(profileId)))
    );
  }

  async function submitAgentIntegrated() {
    const draft = integratedDraft.trim();
    if (
      (!draft && integratedAttachments.length === 0) ||
      running ||
      submittingProfilesRef.current.size > 0
    ) {
      return;
    }
    try {
      const prompt = await buildPromptWithContext(draft, integratedAttachments);
      const runAttachments = attachmentRunInputs(integratedAttachments);
      const messageAttachments = messageAttachmentPreviews(integratedAttachments);
      setIntegratedDraft("");
      clearAttachments("integrated");
      const targetProfileIds = profiles.map((profile) => profile.id);
      clearAgentStepsForProfiles(targetProfileIds);
      void submitWithApi(
        prompt,
        draft,
        targetProfileIds,
        "integrated",
        runAttachments,
        messageAttachments,
        agentSurfacePayload(draft)
      );
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
      setSkillsOpen(true);
    }
  }

  async function submitAgentProfile(profileId: ProfileId) {
    const profile = profiles.find((candidate) => candidate.id === profileId);
    const draft = profileState[profileId]?.draft.trim() ?? "";
    const attachments = profileAttachments[profileId] ?? [];
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
      const prompt = await buildPromptWithContext(draft, attachments);
      const runAttachments = attachmentRunInputs(attachments);
      const messageAttachments = messageAttachmentPreviews(attachments);
      updateProfileState(profileId, (current) => ({ ...current, draft: "" }));
      clearAttachments(profileId);
      clearAgentStepsForProfiles([profileId]);
      void submitWithApi(
        prompt,
        draft,
        [profileId],
        "independent",
        runAttachments,
        messageAttachments,
        agentSurfacePayload(draft)
      );
    } catch (error) {
      setManagementErrors((current) => ({ ...current, skills: errorMessage(error) }));
      setSkillsOpen(true);
    }
  }

  async function handleAttach(target: "integrated" | ProfileId, files: FileList | File[] | null) {
    if (!files || files.length === 0) {
      return;
    }
    const previews = await ingestFiles(files);
    if (target === "integrated") {
      setIntegratedAttachments((current) => [...current, ...previews]);
      return;
    }
    setProfileAttachments((current) => ({
      ...current,
      [target]: [...(current[target] ?? []), ...previews]
    }));
  }

  function buildPromptWithAttachments(text: string, attachments: AttachmentPreview[]) {
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

  async function buildPromptWithContext(text: string, attachments: AttachmentPreview[]) {
    const withAttachments = buildPromptWithAttachments(text, attachments);
    const skillIds = parseSkillCommandIds(text, enabledSkills);
    if (!skillIds.length) {
      return withAttachments;
    }
    const details = await Promise.all(skillIds.map((skillId) => getSkill(skillId)));
    return `${withAttachments}${skillDetailsPromptBlock(details)}`.trim();
  }

  function clearAttachments(target: "integrated" | ProfileId) {
    if (target === "integrated") {
      setIntegratedAttachments((current) => {
        clearAttachmentList(current);
        return [];
      });
      return;
    }
    setProfileAttachments((current) => {
      clearAttachmentList(current[target] ?? []);
      return { ...current, [target]: [] };
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

  function removeAttachment(target: "integrated" | ProfileId, id: string) {
    if (target === "integrated") {
      setIntegratedAttachments((current) => {
        const targetAttachment = current.find((attachment) => attachment.id === id);
        if (targetAttachment?.url) {
          URL.revokeObjectURL(targetAttachment.url);
        }
        return current.filter((attachment) => attachment.id !== id);
      });
      return;
    }
    setProfileAttachments((current) => {
      const attachments = current[target] ?? [];
      const targetAttachment = attachments.find((attachment) => attachment.id === id);
      if (targetAttachment?.url) {
        URL.revokeObjectURL(targetAttachment.url);
      }
      return {
        ...current,
        [target]: attachments.filter((attachment) => attachment.id !== id)
      };
    });
  }

  async function handleTranscribeAudio(_target: "integrated" | ProfileId, audio: Blob) {
    return transcribeAudio(audio);
  }

  function clearAttachmentList(attachments: AttachmentPreview[]) {
    attachments.forEach((attachment) => {
      if (attachment.url) {
        URL.revokeObjectURL(attachment.url);
      }
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

  function handleArtifactDraftChange(profileId: ProfileId, value: string) {
    setArtifactDrafts((current) => ({ ...current, [profileId]: value }));
    if (!artifactsByProfile[profileId]) {
      setArtifactKinds((current) => ({ ...current, [profileId]: inferArtifactKindFromContent(value) }));
    }
  }

  function renderProfileArtifactLayer(profile: ProfileInstance) {
    const artifact = artifactsByProfile[profile.id] ?? null;
    const open = Boolean(canvasOpenByProfile[profile.id]);
    return (
      <div className={`profileCanvasLayer ${open ? "open" : ""}`}>
        <button
          className="profileCanvasToggle"
          type="button"
          aria-label={open ? `Hide ${profile.label} canvas` : `Show ${profile.label} canvas`}
          aria-expanded={open}
          onClick={() =>
            setCanvasOpenByProfile((current) => ({ ...current, [profile.id]: !open }))
          }
          title={open ? "Hide canvas" : "Show canvas"}
        >
          {open ? <PanelRightClose aria-hidden="true" size={16} /> : <PanelRightOpen aria-hidden="true" size={16} />}
        </button>
        {open ? (
          <div className="profileCanvasDrawer">
            <ArtifactWorkbench
              profile={profile}
              artifact={artifact}
              draft={artifactDrafts[profile.id] ?? artifact?.content ?? ""}
              title={artifactTitles[profile.id] ?? artifact?.title ?? `${profile.label} canvas`}
              kind={artifact?.kind ?? artifactKinds[profile.id] ?? "markdown"}
              saving={Boolean(savingArtifacts[profile.id])}
              error={artifactError}
              inputMode={inputMode}
              onDraftChange={handleArtifactDraftChange}
              onSave={(profileId) => {
                void saveArtifactForProfile(profileId);
              }}
              onInitializeAll={initializeIntegratedCanvases}
            />
          </div>
        ) : null}
      </div>
    );
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
          refreshTools();
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
          tools={tools}
          toolsLoading={toolsLoading}
          errors={managementErrors}
          onImportFile={handleImportSkillFile}
          onImportFolder={handleImportSkillFolder}
          onSelectSkill={selectSkill}
          onToggleSkill={handleToggleSkill}
          onDeleteSkill={handleDeleteSkill}
          onToggleSubagent={handleToggleSubagent}
          onDeleteSubagent={handleDeleteSubagent}
          onToggleTool={handleToggleTool}
          onDeleteTool={handleDeleteTool}
          onCreateSubagent={handleCreateSubagent}
        />
      ) : null}
      {surfaceType === "agent" ? (
        <AgentWorkspace
          profiles={profiles}
          profileState={profileState}
          steps={agentSteps}
          analysis={analysis}
          skills={enabledSkills}
          tools={tools}
          model={model}
          renderArtifactLayer={renderProfileArtifactLayer}
        />
      ) : (
        <section className="workspace comparisonWorkspace" aria-label="HarnessDiff comparison and canvas">
          <div className="paneComparisonGrid" aria-label="HarnessDiff chat comparison">
            {profiles.map((profile) => (
              <div className="profileWorkColumn" key={profile.id}>
                <ChatPane
                  profile={profile}
                  messages={profileState[profile.id]?.messages ?? []}
                  streaming={profileState[profile.id]?.streaming ?? false}
                />
                {renderProfileArtifactLayer(profile)}
              </div>
            ))}
          </div>
        </section>
      )}
      <AnalysisSummary
        turnCount={turnCount}
        inputMode={inputMode}
        running={running}
        analysis={analysis}
      />
      {surfaceType === "agent" ? (
        <Composer
          inputMode={inputMode}
          integratedDraft={integratedDraft}
          profiles={profiles}
          profileDrafts={Object.fromEntries(
            profiles.map((profile) => [profile.id, profileState[profile.id]?.draft ?? ""])
          )}
          skills={enabledSkills}
          attachments={integratedAttachments}
          profileAttachments={profileAttachments}
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
          onTranscribeAudio={handleTranscribeAudio}
          onSubmitIntegrated={submitAgentIntegrated}
          onSubmitProfile={submitAgentProfile}
          onPause={pauseExecution}
        />
      ) : (
        <Composer
          inputMode={inputMode}
          integratedDraft={integratedDraft}
          profiles={profiles}
          profileDrafts={Object.fromEntries(
            profiles.map((profile) => [profile.id, profileState[profile.id]?.draft ?? ""])
          )}
          skills={enabledSkills}
          attachments={integratedAttachments}
          profileAttachments={profileAttachments}
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
          onTranscribeAudio={handleTranscribeAudio}
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

function parseArtifactUpdateBlocks(text: string) {
  const updates: Array<{
    artifact_id: string;
    profile_id: ProfileId;
    base_version: number;
    kind: ArtifactKind;
    title: string;
    content: string;
  }> = [];
  const blockPattern = /```harnessdiff-artifact-update\s*([\s\S]*?)```/g;
  let match: RegExpExecArray | null;
  while ((match = blockPattern.exec(text))) {
    try {
      const parsed = JSON.parse(match[1].trim()) as Record<string, unknown>;
      if (
        typeof parsed.artifact_id === "string" &&
        typeof parsed.profile_id === "string" &&
        typeof parsed.base_version === "number" &&
        isArtifactKind(parsed.kind) &&
        typeof parsed.title === "string" &&
        typeof parsed.content === "string"
      ) {
        updates.push({
          artifact_id: parsed.artifact_id,
          profile_id: parsed.profile_id,
          base_version: parsed.base_version,
          kind: parsed.kind,
          title: parsed.title,
          content: parsed.content
        });
      }
    } catch {
      continue;
    }
  }
  return updates;
}

function isArtifactKind(value: unknown): value is ArtifactKind {
  return value === "plain_text" || value === "markdown" || value === "single_page_html" || value === "svg";
}

function inferArtifactKindFromContent(content: string): ArtifactKind {
  const trimmed = content.trimStart().toLowerCase();
  if (trimmed.startsWith("<svg") || /<svg[\s>]/.test(trimmed.slice(0, 256))) {
    return "svg";
  }
  if (
    trimmed.startsWith("<!doctype html") ||
    trimmed.startsWith("<html") ||
    /<html[\s>]/.test(trimmed.slice(0, 256))
  ) {
    return "single_page_html";
  }
  return "markdown";
}
