import { Image, Mic, Paperclip, Send } from "lucide-react";

import type { AttachmentPreview, InputMode, PaneId } from "../types";

type ComposerProps = {
  inputMode: InputMode;
  integratedDraft: string;
  noHarnessDraft: string;
  harnessDraft: string;
  attachments: AttachmentPreview[];
  disabled: boolean;
  onModeChange: (mode: InputMode) => void;
  onIntegratedDraftChange: (value: string) => void;
  onPaneDraftChange: (pane: PaneId, value: string) => void;
  onAttach: (files: FileList | null) => void;
  onRemoveAttachment: (id: string) => void;
  onSubmitIntegrated: () => void;
  onSubmitPane: (pane: PaneId) => void;
};

export function Composer({
  inputMode,
  integratedDraft,
  noHarnessDraft,
  harnessDraft,
  attachments,
  disabled,
  onModeChange,
  onIntegratedDraftChange,
  onPaneDraftChange,
  onAttach,
  onRemoveAttachment,
  onSubmitIntegrated,
  onSubmitPane
}: ComposerProps) {
  return (
    <footer className="composer">
      <div className="composerHeader">
        <div className="segmented" role="tablist" aria-label="Input mode">
          <button
            type="button"
            className={inputMode === "integrated" ? "selected" : ""}
            onClick={() => onModeChange("integrated")}
            aria-selected={inputMode === "integrated"}
          >
            整合單一輸入
          </button>
          <button
            type="button"
            className={inputMode === "independent" ? "selected" : ""}
            onClick={() => onModeChange("independent")}
            aria-selected={inputMode === "independent"}
          >
            個別獨立輸入
          </button>
        </div>
        <div className="composerTools">
          <label className="iconButton fileButton" aria-label="Attach file">
            <Paperclip aria-hidden="true" size={18} />
            <input type="file" multiple onChange={(event) => onAttach(event.target.files)} />
          </label>
          <button className="iconButton" type="button" aria-label="Attach image">
            <Image aria-hidden="true" size={18} />
          </button>
          <button className="iconButton" type="button" aria-label="Voice input">
            <Mic aria-hidden="true" size={18} />
          </button>
        </div>
      </div>

      {attachments.length > 0 ? (
        <div className="attachmentStrip" aria-label="Attachment previews">
          {attachments.map((attachment) => (
            <button
              className="attachmentPreview"
              key={attachment.id}
              type="button"
              onClick={() => onRemoveAttachment(attachment.id)}
              title="移除附件"
            >
              {attachment.url ? <img src={attachment.url} alt="" /> : <Paperclip size={16} />}
              <span>{attachment.name}</span>
            </button>
          ))}
        </div>
      ) : null}

      {inputMode === "integrated" ? (
        <div className="inputRow">
          <textarea
            value={integratedDraft}
            onChange={(event) => onIntegratedDraftChange(event.target.value)}
            placeholder="輸入一個問題，同時送到左右兩邊。"
            disabled={disabled}
          />
          <button className="sendButton" type="button" onClick={onSubmitIntegrated} disabled={disabled}>
            <Send aria-hidden="true" size={18} />
            送出
          </button>
        </div>
      ) : (
        <div className="splitInputRow">
          <div className="inputRow">
            <textarea
              value={noHarnessDraft}
              onChange={(event) => onPaneDraftChange("NoHarness", event.target.value)}
              placeholder="只送到 NoHarness。"
              disabled={disabled}
            />
            <button
              className="sendButton secondarySend"
              type="button"
              onClick={() => onSubmitPane("NoHarness")}
              disabled={disabled}
            >
              <Send aria-hidden="true" size={18} />
              送左側
            </button>
          </div>
          <div className="inputRow">
            <textarea
              value={harnessDraft}
              onChange={(event) => onPaneDraftChange("Harness", event.target.value)}
              placeholder="只送到 Harness。"
              disabled={disabled}
            />
            <button
              className="sendButton harnessSend"
              type="button"
              onClick={() => onSubmitPane("Harness")}
              disabled={disabled}
            >
              <Send aria-hidden="true" size={18} />
              送右側
            </button>
          </div>
        </div>
      )}
    </footer>
  );
}

