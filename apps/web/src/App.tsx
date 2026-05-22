import { useMemo, useRef, useState } from "react";

import { AnalysisSummary } from "./components/AnalysisSummary";
import { ChatPane } from "./components/ChatPane";
import { Composer } from "./components/Composer";
import { TopBar } from "./components/TopBar";
import { nextInputModeAfterCompletedTurn } from "./domain/inputMode";
import type { AttachmentPreview, InputMode, Message, PaneId, PaneState } from "./types";

const panes: PaneId[] = ["NoHarness", "Harness"];

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
    panes.forEach((pane) => streamMockResponse(pane, prompt));
    completeTurnAfterMock();
  }

  function submitPane(pane: PaneId) {
    const prompt = paneState[pane].draft.trim();
    if (!prompt || running) {
      return;
    }
    updatePane(pane, (current) => ({ ...current, draft: "" }));
    streamMockResponse(pane, prompt);
    completeTurnAfterMock();
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

  return (
    <main className="shell">
      <TopBar
        model={model}
        reasoningEffort={reasoningEffort}
        onModelChange={setModel}
        onReasoningEffortChange={setReasoningEffort}
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
      <AnalysisSummary turnCount={turnCount} inputMode={inputMode} running={running} />
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
