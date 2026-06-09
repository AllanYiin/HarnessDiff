import { Check, Copy } from "lucide-react";
import { useMemo, useState } from "react";

import { MarkdownContent } from "./MarkdownContent";
import { AgentTraceTimeline } from "./AgentTraceTimeline";
import { ToolCallDisclosure } from "./ToolCallDisclosure";
import { ContextLoadIndicator } from "./ContextLoadIndicator";
import type { ContextSection, ProfileAnalysis, SkillSummary, ToolSummary } from "../api";
import type { AgentStepTrace, Message, ProfileInstance } from "../types";

type AgentPaneProps = {
  profile: ProfileInstance;
  messages: Message[];
  steps: AgentStepTrace[];
  streaming: boolean;
  analysis?: ProfileAnalysis;
  skills: SkillSummary[];
  tools: ToolSummary[];
  model: string;
};

export function AgentPane({
  profile,
  messages,
  steps,
  streaming,
  analysis,
  skills,
  tools,
  model
}: AgentPaneProps) {
  const hasControls = Object.values(profile.harness_modules).some(Boolean);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const pendingContextSections = useMemo(
    () => buildPendingAgentContextSections(messages, steps),
    [messages, steps]
  );

  async function copyMessage(message: Message) {
    if (!message.text) return;
    await navigator.clipboard?.writeText(message.text);
    setCopiedMessageId(message.id);
    window.setTimeout(() => {
      setCopiedMessageId((current) => (current === message.id ? null : current));
    }, 1200);
  }

  return (
    <section className={`agentPane ${hasControls ? "controlledProfile" : "neutralProfile"}`}>
      <header className="profileHeader">
        <div>
          <h2>{profile.label}</h2>
          <p>{hasControls ? "Harness 控制與工具軌跡" : "直接 Agent 對照組"}</p>
        </div>
        <div className="profileHeaderActions">
          <ContextLoadIndicator
            analysis={analysis}
            profile={profile}
            skills={skills}
            tools={tools}
            model={model}
            pendingContextSections={pendingContextSections}
          />
          <span className={`profileStatus ${streaming ? "active" : ""}`}>
            {streaming ? "執行中" : "待命"}
          </span>
        </div>
      </header>
      <div className="agentAnswer" aria-live="polite" tabIndex={0}>
        {messages.length === 0 ? (
          <div className="emptyState">
            <strong>尚未執行</strong>
            <span>送出任務後會逐段顯示 Agent 結果。</span>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <header className="messageHeader">
                <span className="messageRole">{message.role === "user" ? "任務" : profile.label}</span>
                {message.text ? (
                  <button
                    aria-label={message.role === "user" ? "複製任務內容" : "複製 Agent 回答"}
                    className="messageCopyButton"
                    onClick={() => void copyMessage(message)}
                    type="button"
                  >
                    {copiedMessageId === message.id ? <Check size={14} /> : <Copy size={14} />}
                  </button>
                ) : null}
              </header>
              {message.toolCalls?.length ? (
                <div className="toolCallStack" aria-label="工具呼叫紀錄">
                  {message.toolCalls.map((toolCall, index) => (
                    <ToolCallDisclosure index={index} key={toolCall.id} toolCall={toolCall} />
                  ))}
                </div>
              ) : null}
              {message.skillInvocations?.length ? (
                <div className="skillInvocationStack" aria-label="技能載入紀錄">
                  {message.skillInvocations.map((skill) => (
                    <details className="skillInvocationDisclosure" key={skill.id}>
                      <summary>
                        <span className="skillInvocationBadge">Skill</span>
                        <span className="skillInvocationName">{skill.skill_id}</span>
                        {skill.token_usage?.total_tokens ? (
                          <span className="skillInvocationTokens">
                            估 {skill.token_usage.total_tokens} tok
                          </span>
                        ) : null}
                        <span className="skillInvocationStatus">
                          {skill.status === "loaded" ? "已載入" : "已選上"}
                        </span>
                      </summary>
                      <p>SKILL.md body 已加入本回合 provider instructions。</p>
                    </details>
                  ))}
                </div>
              ) : null}
              {message.attachments?.length ? (
                <div className="messageAttachmentGrid" aria-label="使用者附件">
                  {message.attachments.map((attachment) => (
                    <figure className="messageAttachment" key={attachment.id}>
                      {attachment.kind === "image" && attachment.url ? (
                        <img src={attachment.url} alt={attachment.name} />
                      ) : (
                        <div className="messageAttachmentFile">{attachment.kind}</div>
                      )}
                      <figcaption>
                        <span>{attachment.name}</span>
                        <small>{formatBytes(attachment.size)}</small>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              ) : null}
              <MarkdownContent source={message.text} />
            </article>
          ))
        )}
        <AgentTraceTimeline steps={steps} />
      </div>
    </section>
  );
}

function buildPendingAgentContextSections(
  messages: Message[],
  steps: AgentStepTrace[]
): ContextSection[] {
  const currentTaskIndex = latestUserMessageIndex(messages);
  const currentTask = currentTaskIndex >= 0 ? messages[currentTaskIndex]?.text ?? "" : "";
  const historyText =
    currentTaskIndex > 0
      ? messages
          .slice(0, currentTaskIndex)
          .map((message) => `${message.role}: ${message.text}`)
          .join("\n")
      : "";
  const stepText = steps
    .map((step) => {
      const toolName = step.tool_name ? ` · ${step.tool_name}` : "";
      return `${step.sequence}: ${step.label}${toolName} [${step.status}]`;
    })
    .join("\n");

  return [
    pendingContextSection(
      "stored_conversation_history",
      "Stored conversation history",
      historyText,
      "local",
      "Visible profile-local transcript while backend analysis is pending."
    ),
    pendingContextSection(
      "current_agent_task",
      "Current agent task",
      currentTask,
      "local",
      "Latest submitted agent task visible in this pane while backend analysis is pending."
    ),
    pendingContextSection(
      "agent_steps",
      "Agent step trace",
      stepText,
      "recorded",
      "Agent steps received from the run stream while backend analysis is pending."
    )
  ].filter((section) => section.estimated_tokens > 0);
}

function latestUserMessageIndex(messages: Message[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user" && messages[index]?.text.trim()) {
      return index;
    }
  }
  return -1;
}

function pendingContextSection(
  key: string,
  label: string,
  text: string,
  status: string,
  notes: string
): ContextSection {
  const characters = text.trim().length;
  return {
    key,
    label,
    status,
    characters,
    estimated_tokens: characters ? Math.max(1, Math.ceil(characters / 4)) : 0,
    notes
  };
}

function formatBytes(size: number) {
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.round(size / 1024)} KB`;
  }
  return `${size} B`;
}
