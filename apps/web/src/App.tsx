import { useEffect, useMemo, useRef, useState } from "react";

import { AnalysisSummary } from "./components/AnalysisSummary";
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
import { attachmentPromptBlock, ingestFiles } from "./domain/fileIngestion";
import { nextInputModeAfterCompletedTurn } from "./domain/inputMode";
import { parseSkillCommandIds, skillDetailsPromptBlock } from "./domain/skillCommands";
import type {
  AttachmentPreview,
  HarnessModuleId,
  HarnessModules,
  InputMode,
  Message,
  ProfileId,
  ProfileInstance,
  ProfileState
} from "./types";

const newConversationName = "新對話";
const activeProjectStorageKey = "harnessdiff.activeProjectId";

const defaultHarnessModules: HarnessModules = {
  context_summary: true,
  source_map: true,
  guardrails: true,
  output_contract: true,
  planning_preamble: false,
  tool_policy: true,
  memory_selection: true,
  post_answer_critique: true,
  token_budgeter: true
};

const defaultProfiles: ProfileInstance[] = [
  { id: "baseline", label: "NoHarness", harness_modules: {} },
  { id: "harness", label: "Harness", harness_modules: defaultHarnessModules }
];

function createMessage(role: Message["role"], text: string, status: Message["status"] = "done") {
  return {
    id: `${role}_${crypto.randomUUID()}`,
    role,
    text,
    status
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
  const [model, setModel] = useState("gpt-5.4-mini");
  const [reasoningEffort, setReasoningEffort] = useState("medium");
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
  const [profiles, setProfiles] = useState<ProfileInstance[]>(defaultProfiles);
  const [analysis, setAnalysis] = useState<AnalysisDocument | null>(null);
  const [integratedDraft, setIntegratedDraft] = useState("");
  const [attachments, setAttachments] = useState<AttachmentPreview[]>([]);
  const [profileState, setProfileState] = useState<Record<ProfileId, ProfileState>>(
    createInitialProfileState(defaultProfiles)
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

  function resetConversationState(nextProjectId: string | null, nextProjectName = newConversationName) {
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
    setProfiles(defaultProfiles);
    setProfileState(createInitialProfileState(defaultProfiles));
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
      const project = await createProject(newConversationName);
      setProjectId(project.id);
      setProjectName(project.name);
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
      const nextProfiles = transcript.runs[0]?.profiles.map(({ output_text, ...profile }) => profile) ?? defaultProfiles;
      const nextProfileState = createInitialProfileState(nextProfiles);
      for (const run of transcript.runs) {
        for (const profile of run.profiles) {
          const state = nextProfileState[profile.id] ?? { ...initialProfileState, messages: [] };
          state.messages.push({
            id: `${run.id}_${profile.id}_user`,
            role: "user",
            text: run.prompt,
            status: "done"
          });
          state.messages.push({
            id: `${run.id}_${profile.id}_assistant`,
            role: "assistant",
            text: profile.output_text || (run.status === "cancelled" ? "已暫停。" : ""),
            status: "done"
          });
          nextProfileState[profile.id] = state;
        }
      }
      setProjectId(transcript.project.id);
      setProjectName(transcript.project.name);
      setProfiles(nextProfiles);
      setProfileState(nextProfileState);
      setTurnCount(transcript.runs.length);
      setInputMode(transcript.runs.length > 0 ? "independent" : "integrated");
      setAnalysis(null);
      window.localStorage.setItem(activeProjectStorageKey, transcript.project.id);
      setHistoryOpen(false);
    } finally {
      setHistoryLoading(false);
    }
  }

  function prepareStreamingProfile(profileId: ProfileId, prompt: string, assistantId: string) {
    updateProfileState(profileId, (current) => ({
      ...current,
      streaming: true,
      messages: [
        ...current.messages,
        createMessage("user", prompt),
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
    projectCreationRef.current = createProject(autoName)
      .then((project) => {
        projectIdRef.current = project.id;
        projectNameRef.current = project.name;
        setProjectId(project.id);
        setProjectName(project.name);
        window.localStorage.setItem(activeProjectStorageKey, project.id);
        refreshProjects();
        return project.id;
      })
      .finally(() => {
        projectCreationRef.current = null;
      });
    return projectCreationRef.current;
  }

  async function submitWithApi(prompt: string, targetProfileIds: ProfileId[], mode: InputMode) {
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
      prepareStreamingProfile(profile.id, prompt, assistantIds[profile.id])
    );
    try {
      const activeProjectId = await ensureProject(prompt);
      const run = await createRun({
        projectId: activeProjectId,
        prompt,
        inputMode: mode,
        model,
        reasoningEffort,
        profiles: activeProfiles
      });
      await streamRun(
        run.id,
        (event) => {
          if (event.type === "analysis_ready" && event.analysis) {
            setAnalysis(event.analysis);
          }
          applyStreamEvent(event, assistantIds);
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
      setIntegratedDraft("");
      clearAttachments();
      void submitWithApi(prompt, profiles.map((profile) => profile.id), "integrated");
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
      updateProfileState(profileId, (current) => ({ ...current, draft: "" }));
      clearAttachments();
      void submitWithApi(prompt, [profileId], "independent");
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
        historyOpen={historyOpen}
        skillsOpen={skillsOpen}
        onModelChange={setModel}
        onReasoningEffortChange={setReasoningEffort}
        onHarnessModuleChange={updateHarnessModule}
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
      <AnalysisSummary
        turnCount={turnCount}
        inputMode={inputMode}
        running={running}
        analysis={analysis}
      />
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
    </main>
  );
}
