import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { MarkdownContent } from "./MarkdownContent";
import { AgentTraceTimeline } from "./AgentTraceTimeline";
import type { AgentStepTrace, Message, ProfileInstance } from "../types";

type AgentPaneProps = {
  profile: ProfileInstance;
  messages: Message[];
  steps: AgentStepTrace[];
  streaming: boolean;
};

export function AgentPane({ profile, messages, steps, streaming }: AgentPaneProps) {
  const hasControls = Object.values(profile.harness_modules).some(Boolean);
  const [copied, setCopied] = useState(false);
  const answer = [...messages].reverse().find((message) => message.role === "assistant");

  async function copyAnswer() {
    if (!answer?.text) return;
    await navigator.clipboard?.writeText(answer.text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <section className={`agentPane ${hasControls ? "controlledProfile" : "neutralProfile"}`}>
      <header className="profileHeader">
        <div>
          <h2>{profile.label}</h2>
          <p>{hasControls ? "Harness 控制與工具軌跡" : "直接 Agent 對照組"}</p>
        </div>
        <span className={`profileStatus ${streaming ? "active" : ""}`}>
          {streaming ? "執行中" : "待命"}
        </span>
      </header>
      <div className="agentAnswer" aria-live="polite" tabIndex={0}>
        {answer ? (
          <article className="message assistant">
            <header className="messageHeader">
              <span className="messageRole">{profile.label}</span>
              {answer.text ? (
                <button
                  aria-label="複製 Agent 回答"
                  className="messageCopyButton"
                  onClick={() => void copyAnswer()}
                  type="button"
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                </button>
              ) : null}
            </header>
            <MarkdownContent source={answer.text} />
          </article>
        ) : (
          <div className="emptyState">
            <strong>尚未執行</strong>
            <span>送出任務後會逐段顯示 Agent 結果。</span>
          </div>
        )}
      </div>
      <AgentTraceTimeline steps={steps} />
    </section>
  );
}
