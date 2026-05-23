import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { MarkdownContent } from "./MarkdownContent";
import type { Message, PaneId } from "../types";

type ChatPaneProps = {
  pane: PaneId;
  messages: Message[];
  streaming: boolean;
};

export function ChatPane({ pane, messages, streaming }: ChatPaneProps) {
  const isHarness = pane === "Harness";
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
    <section className={`chatPane ${isHarness ? "harnessPane" : "neutralPane"}`}>
      <header className="paneHeader">
        <div>
          <h2>{pane}</h2>
          <p>{isHarness ? "加入可開關的 Harness 控制" : "保留原始對話路徑"}</p>
        </div>
        <span className={`paneStatus ${streaming ? "active" : ""}`}>
          {streaming ? "產生中" : "待命"}
        </span>
      </header>
      <div className="messageList" aria-live="polite">
        {messages.length === 0 ? (
          <div className="emptyState">
            <strong>{isHarness ? "等待同題比較" : "尚無對話"}</strong>
            <span>{isHarness ? "送出後會顯示加上控制後的回答。" : "第一回合會與右側同時開始。"}</span>
          </div>
        ) : (
          messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <header className="messageHeader">
                <span className="messageRole">{message.role === "user" ? "你" : pane}</span>
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
              <MarkdownContent source={message.text} />
            </article>
          ))
        )}
      </div>
    </section>
  );
}
