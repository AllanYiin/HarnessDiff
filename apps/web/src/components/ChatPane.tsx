import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { MarkdownContent } from "./MarkdownContent";
import { ToolCallDisclosure } from "./ToolCallDisclosure";
import type { Message, ProfileInstance } from "../types";

type ChatPaneProps = {
  profile: ProfileInstance;
  messages: Message[];
  streaming: boolean;
};

export function ChatPane({ profile, messages, streaming }: ChatPaneProps) {
  const hasControls = Object.values(profile.harness_modules).some(Boolean);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  async function copyMarkdown(message: Message) {
    if (!message.text) return;
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(message.text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = message.text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopiedMessageId(message.id);
    window.setTimeout(() => setCopiedMessageId((current) => (current === message.id ? null : current)), 1200);
  }

  return (
    <section className={`chatProfile ${hasControls ? "controlledProfile" : "neutralProfile"}`}>
      <header className="profileHeader">
        <div>
          <h2>{profile.label}</h2>
          <p>{hasControls ? "使用 profile-level Harness 控制" : "直接 profile path"}</p>
        </div>
        <span className={`profileStatus ${streaming ? "active" : ""}`}>
          {streaming ? "產生中" : "待命"}
        </span>
      </header>
      <div className="messageList" aria-label={`${profile.label} 對話內容`} aria-live="polite" tabIndex={0}>
        {messages.length === 0 ? (
          <div className="emptyState">
            <strong>尚無對話</strong>
            <span>送出後會顯示此 profile 的回答。</span>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <header className="messageHeader">
                <span className="messageRole">{message.role === "user" ? "你" : profile.label}</span>
                {message.text ? (
                  <button
                    aria-label="複製 Markdown 原始碼"
                    className="messageCopyButton"
                    onClick={() => void copyMarkdown(message)}
                    title="複製 Markdown 原始碼"
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
                      <p>
                        SKILL.md body 已加入本回合 provider instructions。耗用為依 SKILL.md
                        字元數估算，實際值會混入本回合 provider input tokens。
                      </p>
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
