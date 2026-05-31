import { Paperclip, Send, Square, X } from "lucide-react";
import { useRef } from "react";

import type { AttachmentPreview } from "../types";

type AgentComposerProps = {
  draft: string;
  attachments: AttachmentPreview[];
  disabled: boolean;
  running: boolean;
  onDraftChange: (value: string) => void;
  onAttach: (files: FileList | File[] | null) => void;
  onRemoveAttachment: (id: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
};

export function AgentComposer({
  draft,
  attachments,
  disabled,
  running,
  onDraftChange,
  onAttach,
  onRemoveAttachment,
  onSubmit,
  onCancel
}: AgentComposerProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const canSubmit = draft.trim().length > 0 || attachments.length > 0;

  return (
    <footer className="composer agentComposer">
      <div className="agentComposerMain">
        <textarea
          value={draft}
          disabled={disabled}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="輸入一個任務，同時交給 NoHarness Agent 與 Harness Agent。"
          aria-label="Agent task"
        />
        <div className="agentComposerActions">
          {running ? (
            <button className="stopButton" type="button" onClick={onCancel}>
              <Square aria-hidden="true" size={14} />
              取消
            </button>
          ) : null}
          <label className="iconButton fileButton" aria-label="Attach file">
            <Paperclip aria-hidden="true" size={18} />
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".txt,.csv,.docx,.xlsx,.pptx,.md,.pdf,image/*"
              onChange={(event) => {
                onAttach(event.target.files);
                event.target.value = "";
              }}
            />
          </label>
          <button className="sendButton" type="button" onClick={onSubmit} disabled={disabled || !canSubmit}>
            <Send aria-hidden="true" size={18} />
            執行 Agent 對照
          </button>
        </div>
      </div>
      {attachments.length > 0 ? (
        <div className="attachmentStrip" aria-label="Attachment previews">
          {attachments.map((attachment) => (
            <button
              className={`attachmentPreview ${attachment.status === "error" ? "attachmentError" : ""}`}
              key={attachment.id}
              type="button"
              onClick={() => onRemoveAttachment(attachment.id)}
              title={attachment.error ?? "移除附件"}
            >
              {attachment.url ? <img src={attachment.url} alt="" /> : <Paperclip size={16} />}
              <span>{attachment.name}</span>
              <small>{attachment.kind}</small>
              <X aria-hidden="true" size={14} />
            </button>
          ))}
        </div>
      ) : null}
    </footer>
  );
}
