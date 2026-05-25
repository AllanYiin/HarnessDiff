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
              <MarkdownContent source={message.text} />
            </article>
          ))
        )}
      </div>
    </section>
  );
}
