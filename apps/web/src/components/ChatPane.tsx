import type { Message, PaneId } from "../types";

type ChatPaneProps = {
  pane: PaneId;
  messages: Message[];
  streaming: boolean;
};

export function ChatPane({ pane, messages, streaming }: ChatPaneProps) {
  const isHarness = pane === "Harness";
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
              <span className="messageRole">{message.role === "user" ? "你" : pane}</span>
              <p>{message.text}</p>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

