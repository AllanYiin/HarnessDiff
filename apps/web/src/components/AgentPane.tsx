import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { MarkdownContent } from "./MarkdownContent";
import { AgentTraceTimeline } from "./AgentTraceTimeline";
import { ToolCallDisclosure } from "./ToolCallDisclosure";
import type { AgentStepTrace, Message, ProfileInstance } from "../types";

type AgentPaneProps = {
  profile: ProfileInstance;
  messages: Message[];
  steps: AgentStepTrace[];
  streaming: boolean;
};

export function AgentPane({ profile, messages, steps, streaming }: AgentPaneProps) {
  const hasControls = Object.values(profile.harness_modules).some(Boolean);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

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
        <span className={`profileStatus ${streaming ? "active" : ""}`}>
          {streaming ? "執行中" : "待命"}
        </span>
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

function formatBytes(size: number) {
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.round(size / 1024)} KB`;
  }
  return `${size} B`;
}
