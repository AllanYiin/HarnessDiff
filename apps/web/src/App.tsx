import { useMemo, useRef, useState } from "react";

import { AnalysisSummary } from "./components/AnalysisSummary";
import { ChatPane } from "./components/ChatPane";
import { Composer } from "./components/Composer";
import { TopBar } from "./components/TopBar";
import {
  createProject,
  createRun,
  getRunAnalysis,
  streamRun,
  type AnalysisDocument,
  type RunStreamEvent
} from "./api";
import { nextInputModeAfterCompletedTurn } from "./domain/inputMode";
import type {
  AttachmentPreview,
  HarnessModuleId,
  HarnessModules,
  InputMode,
  Message,
  PaneId,
  PaneState
} from "./types";

const panes: PaneId[] = ["NoHarness", "Harness"];

const defaultHarnessModules: HarnessModules = {
  context_manifest: true,
  source_map: true,
  guardrails: true,
  output_contract: true,
  planning_preamble: false,
  tool_policy: true,
  memory_selection: true,
  post_answer_critique: true,
  token_budgeter: true
};

function createAssistantText(pane: PaneId, prompt: string) {
  if (pane === "Harness") {
    return `我會先保留任務目標、限制與可驗證點，再回答：「${prompt}」。這一側會在後續階段加入 Context Manifest、Guardrails 與 Output Contract。`;
  }
  return `收到：「${prompt}」。這一側保留直接對話路徑，不額外加入 Harness 控制。`;
}

function createMessage(role: Message["role"], text: string, status: Message["status"] = "done") {
  return {
    id: `${role}_${crypto.randomUUID()}`,
    role,
    text,
    status
  };
}

const initialPaneState: PaneState = {
  messages: [],
  draft: "",
  streaming: false
};

export function App() {
  const [model, setModel] = useState("gpt-5.4-mini");
  const [reasoningEffort, setReasoningEffort] = useState("medium");
  const [turnCount, setTurnCount] = useState(0);
  const [inputMode, setInputMode] = useState<InputMode>("integrated");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [harnessModules, setHarnessModules] = useState<HarnessModules>(defaultHarnessModules);
  const [analysis, setAnalysis] = useState<AnalysisDocument | null>(null);
  const [integratedDraft, setIntegratedDraft] = useState("");
  const [attachments, setAttachments] = useState<AttachmentPreview[]>([]);
  const [paneState, setPaneState] = useState<Record<PaneId, PaneState>>({
    NoHarness: { ...initialPaneState },
    Harness: { ...initialPaneState }
  });
  const timers = useRef<number[]>([]);

  const running = useMemo(
    () => panes.some((pane) => paneState[pane].streaming),
    [paneState]
  );

  function updatePane(pane: PaneId, next: (current: PaneState) => PaneState) {
    setPaneState((current) => ({
      ...current,
      [pane]: next(current[pane])
    }));
  }

  function streamMockResponse(pane: PaneId, prompt: string) {
    const response = createAssistantText(pane, prompt);
    const assistant = createMessage("assistant", "", "streaming");
    updatePane(pane, (current) => ({
      ...current,
      streaming: true,
      messages: [...current.messages, createMessage("user", prompt), assistant]
    }));

    const chunks = response.match(/.{1,12}/g) ?? [response];
    chunks.forEach((chunk, index) => {
      const timer = window.setTimeout(() => {
        updatePane(pane, (current) => ({
          ...current,
          messages: current.messages.map((message) =>
            message.id === assistant.id
              ? {
                  ...message,
                  text: `${message.text}${chunk}`,
                  status: index === chunks.length - 1 ? "done" : "streaming"
                }
              : message
          ),
          streaming: index === chunks.length - 1 ? false : current.streaming
        }));
      }, 80 * (index + 1));
      timers.current.push(timer);
    });
  }

  function prepareStreamingPane(pane: PaneId, prompt: string, assistantId: string) {
    updatePane(pane, (current) => ({
      ...current,
      streaming: true,
      messages: [
        ...current.messages,
        createMessage("user", prompt),
        { id: assistantId, role: "assistant", text: "", status: "streaming" }
      ]
    }));
  }

  function applyStreamEvent(event: RunStreamEvent, assistantIds: Record<PaneId, string>) {
    if (!event.pane) {
      return;
    }
    if (event.type === "delta" && event.text) {
      updatePane(event.pane, (current) => ({
        ...current,
        messages: current.messages.map((message) =>
          message.id === assistantIds[event.pane as PaneId]
            ? { ...message, text: `${message.text}${event.text}`, status: "streaming" }
            : message
        )
      }));
    }
    if (event.type === "completed" || event.type === "error") {
      updatePane(event.pane, (current) => ({
        ...current,
        streaming: false,
        messages: current.messages.map((message) =>
          message.id === assistantIds[event.pane as PaneId]
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

  async function ensureProject() {
    if (projectId) {
      return projectId;
    }
    const project = await createProject("HarnessDiff local session");
    setProjectId(project.id);
    return project.id;
  }

  async function submitWithApi(prompt: string, targetPanes: PaneId[], mode: InputMode) {
    const activeProjectId = await ensureProject();
    setAnalysis(null);
    const assistantIds = {
      NoHarness: `assistant_${crypto.randomUUID()}`,
      Harness: `assistant_${crypto.randomUUID()}`
    };
    const run = await createRun({
      projectId: activeProjectId,
      prompt,
      inputMode: mode,
      model,
      reasoningEffort,
      targetPanes,
      harnessModules
    });
    targetPanes.forEach((pane) => prepareStreamingPane(pane, prompt, assistantIds[pane]));
    await streamRun(run.id, (event) => {
      if (event.type === "analysis_ready" && event.analysis) {
        setAnalysis(event.analysis);
      }
      applyStreamEvent(event, assistantIds);
    });
    getRunAnalysis(run.id).then(setAnalysis).catch(() => undefined);
    setTurnCount((current) => {
      const next = current + 1;
      setInputMode((currentMode) => nextInputModeAfterCompletedTurn(current, currentMode));
      return next;
    });
  }

  function completeTurnAfterMock() {
    const timer = window.setTimeout(() => {
      setTurnCount((current) => {
        const next = current + 1;
        setInputMode((mode) => nextInputModeAfterCompletedTurn(current, mode));
        return next;
      });
    }, 1200);
    timers.current.push(timer);
  }

  function submitIntegrated() {
    const prompt = integratedDraft.trim();
    if (!prompt || running) {
      return;
    }
    setIntegratedDraft("");
    submitWithApi(prompt, panes, "integrated").catch(() => {
      setAnalysis(null);
      panes.forEach((pane) => streamMockResponse(pane, prompt));
      completeTurnAfterMock();
    });
  }

  function submitPane(pane: PaneId) {
    const prompt = paneState[pane].draft.trim();
    if (!prompt || running) {
      return;
    }
    updatePane(pane, (current) => ({ ...current, draft: "" }));
    submitWithApi(prompt, [pane], "independent").catch(() => {
      setAnalysis(null);
      streamMockResponse(pane, prompt);
      completeTurnAfterMock();
    });
  }

  function handleAttach(files: FileList | null) {
    if (!files) {
      return;
    }
    const previews = Array.from(files).map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      type: file.type,
      size: file.size,
      url: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined
    }));
    setAttachments((current) => [...current, ...previews]);
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
    setHarnessModules((current) => ({ ...current, [id]: enabled }));
  }

  return (
    <main className="shell">
      <TopBar
        model={model}
        reasoningEffort={reasoningEffort}
        harnessModules={harnessModules}
        onModelChange={setModel}
        onReasoningEffortChange={setReasoningEffort}
        onHarnessModuleChange={updateHarnessModule}
      />
      <section className="workspace" aria-label="HarnessDiff chat comparison">
        <ChatPane
          pane="NoHarness"
          messages={paneState.NoHarness.messages}
          streaming={paneState.NoHarness.streaming}
        />
        <ChatPane
          pane="Harness"
          messages={paneState.Harness.messages}
          streaming={paneState.Harness.streaming}
        />
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
        noHarnessDraft={paneState.NoHarness.draft}
        harnessDraft={paneState.Harness.draft}
        attachments={attachments}
        disabled={running}
        onModeChange={setInputMode}
        onIntegratedDraftChange={setIntegratedDraft}
        onPaneDraftChange={(pane, value) =>
          updatePane(pane, (current) => ({ ...current, draft: value }))
        }
        onAttach={handleAttach}
        onRemoveAttachment={removeAttachment}
        onSubmitIntegrated={submitIntegrated}
        onSubmitPane={submitPane}
      />
    </main>
  );
}
