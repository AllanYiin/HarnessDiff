import { Mic, Paperclip, Send, Square, X } from "lucide-react";
import type { ClipboardEvent, KeyboardEvent, PointerEvent } from "react";
import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";

import type { SkillSummary } from "../api";
import type { AttachmentPreview, InputMode, ProfileId, ProfileInstance } from "../types";

type ComposerProps = {
  inputMode: InputMode;
  integratedDraft: string;
  profiles: ProfileInstance[];
  profileDrafts: Record<ProfileId, string>;
  skills: SkillSummary[];
  attachments: AttachmentPreview[];
  disabled: boolean;
  profileDisabled: Record<ProfileId, boolean>;
  running: boolean;
  onModeChange: (mode: InputMode) => void;
  onIntegratedDraftChange: (value: string) => void;
  onProfileDraftChange: (profileId: ProfileId, value: string) => void;
  onAttach: (files: FileList | File[] | null) => void;
  onRemoveAttachment: (id: string) => void;
  onSubmitIntegrated: () => void;
  onSubmitProfile: (profileId: ProfileId) => void;
  onPause: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

type SpeechRecognitionEventLike = {
  results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }>;
};

type SlashState = {
  target: "integrated" | ProfileId;
  query: string;
  start: number;
  end: number;
};

type PromptEditorHandle = {
  focus: () => void;
  setSelectionRange: (start: number, end: number) => void;
};

type SkillTokenRange = {
  start: number;
  tokenEnd: number;
  end: number;
  id: string;
};

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export function Composer({
  inputMode,
  integratedDraft,
  profiles,
  profileDrafts,
  skills,
  attachments,
  disabled,
  profileDisabled,
  running,
  onModeChange,
  onIntegratedDraftChange,
  onProfileDraftChange,
  onAttach,
  onRemoveAttachment,
  onSubmitIntegrated,
  onSubmitProfile,
  onPause
}: ComposerProps) {
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const listeningRef = useRef(false);
  const activeTargetRef = useRef<"integrated" | ProfileId>("integrated");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const integratedEditorRef = useRef<PromptEditorHandle | null>(null);
  const profileEditorRefs = useRef<Record<ProfileId, PromptEditorHandle | null>>({});
  const [slashState, setSlashState] = useState<SlashState | null>(null);
  const [activeSlashIndex, setActiveSlashIndex] = useState(0);

  const slashMatches = slashState
    ? skills
        .filter((skill) => {
          const query = slashState.query.toLowerCase();
          return (
            skill.id.toLowerCase().includes(query) ||
            skill.name.toLowerCase().includes(query) ||
            skill.description.toLowerCase().includes(query)
          );
        })
        .slice(0, 8)
    : [];

  function appendToActiveDraft(text: string) {
    const value = text.trim();
    if (!value) {
      return;
    }
    if (activeTargetRef.current === "integrated") {
      onIntegratedDraftChange(joinDraft(integratedDraft, value));
      return;
    }
    const profileId = activeTargetRef.current;
    onProfileDraftChange(profileId, joinDraft(profileDrafts[profileId] ?? "", value));
  }

  function updateSlashState(target: "integrated" | ProfileId, value: string, cursor: number) {
    const next = slashQueryAtCursor(value, cursor);
    if (!next || !skills.length) {
      setSlashState(null);
      setActiveSlashIndex(0);
      return;
    }
    setSlashState({ target, ...next });
    setActiveSlashIndex(0);
  }

  function handleEditorChange(target: "integrated" | ProfileId, value: string, cursor: number) {
    if (target === "integrated") {
      onIntegratedDraftChange(value);
    } else {
      onProfileDraftChange(target, value);
    }
    updateSlashState(target, value, cursor);
  }

  function handleEditorFocus(target: "integrated" | ProfileId, value: string, cursor: number) {
    activeTargetRef.current = target;
    updateSlashState(target, value, cursor);
  }

  function handleTextKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (!slashState || !slashMatches.length) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSlashIndex((current) => (current + 1) % slashMatches.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSlashIndex((current) => (current - 1 + slashMatches.length) % slashMatches.length);
    } else if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      insertSkillCommand(slashMatches[activeSlashIndex] ?? slashMatches[0]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setSlashState(null);
    }
  }

  function insertSkillCommand(skill: SkillSummary) {
    if (!slashState) {
      return;
    }
    const current =
      slashState.target === "integrated"
        ? integratedDraft
        : profileDrafts[slashState.target] ?? "";
    const replacement = `/${skill.id} `;
    const next = `${current.slice(0, slashState.start)}${replacement}${current.slice(slashState.end)}`;
    const cursor = slashState.start + replacement.length;
    if (slashState.target === "integrated") {
      onIntegratedDraftChange(next);
    } else {
      onProfileDraftChange(slashState.target, next);
    }
    setSlashState(null);
    requestAnimationFrame(() => {
      const editor =
        slashState.target === "integrated"
          ? integratedEditorRef.current
          : profileEditorRefs.current[slashState.target];
      editor?.focus();
      editor?.setSelectionRange(cursor, cursor);
    });
  }

  function handlePaste(event: ClipboardEvent<HTMLElement>) {
    const files = Array.from(event.clipboardData.files);
    if (!files.length) {
      return;
    }
    event.preventDefault();
    onAttach(files);
  }

  function setVoiceListening(value: boolean) {
    listeningRef.current = value;
    setListening(value);
  }

  function stopVoiceInput() {
    const recognition = recognitionRef.current;
    if (!recognition && !listeningRef.current) {
      setListening(false);
      return;
    }
    try {
      recognition?.stop();
    } finally {
      setVoiceListening(false);
    }
  }

  function startVoiceInput() {
    if (listeningRef.current) {
      return;
    }
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      setVoiceError("此瀏覽器不支援語音輸入");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "zh-TW";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const text = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      appendToActiveDraft(text);
    };
    recognition.onerror = () => {
      setVoiceError("語音輸入失敗，請確認麥克風權限");
      setVoiceListening(false);
    };
    recognition.onend = () => {
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
      setVoiceListening(false);
    };
    recognitionRef.current = recognition;
    setVoiceError("");
    setVoiceListening(true);
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setVoiceError("語音輸入失敗，請確認麥克風權限");
      setVoiceListening(false);
    }
  }

  function handleVoicePointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) {
      return;
    }
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture is best-effort; start/stop still works for the active target.
    }
    startVoiceInput();
  }

  function handleVoicePointerEnd(event: PointerEvent<HTMLButtonElement>) {
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      // Ignore stale pointer ids from cancelled pointer sequences.
    }
    stopVoiceInput();
  }

  function handleVoiceKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.repeat || (event.key !== " " && event.key !== "Enter")) {
      return;
    }
    event.preventDefault();
    startVoiceInput();
  }

  function handleVoiceKeyUp(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== " " && event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    stopVoiceInput();
  }

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
          {running ? (
            <button className="stopButton" type="button" onClick={onPause}>
              <Square aria-hidden="true" size={14} />
              暫停執行
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
          <button
            className={`iconButton ${listening ? "activeIconButton" : ""}`}
            type="button"
            aria-label={listening ? "Release to stop voice input" : "Hold to voice input"}
            aria-pressed={listening}
            onPointerDown={handleVoicePointerDown}
            onPointerUp={handleVoicePointerEnd}
            onPointerCancel={handleVoicePointerEnd}
            onKeyDown={handleVoiceKeyDown}
            onKeyUp={handleVoiceKeyUp}
            onBlur={stopVoiceInput}
          >
            <Mic aria-hidden="true" size={18} />
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
      {voiceError ? <div className="composerStatus">{voiceError}</div> : null}
      {slashState && slashMatches.length > 0 ? (
        <div className="skillCommandMenu" role="listbox" id="skill-command-menu">
          {slashMatches.map((skill, index) => (
            <button
              className={index === activeSlashIndex ? "selected" : ""}
              key={skill.id}
              type="button"
              role="option"
              aria-selected={index === activeSlashIndex}
              onMouseDown={(event) => {
                event.preventDefault();
                insertSkillCommand(skill);
              }}
            >
              <strong>/{skill.id}</strong>
              <span>{skill.description || skill.name}</span>
            </button>
          ))}
        </div>
      ) : null}

      {inputMode === "integrated" ? (
        <div className="inputRow">
          <PromptEditor
            ref={integratedEditorRef}
            value={integratedDraft}
            skills={skills}
            onValueChange={(value, cursor) => handleEditorChange("integrated", value, cursor)}
            onFocus={(cursor) => handleEditorFocus("integrated", integratedDraft, cursor)}
            onPaste={handlePaste}
            onKeyDown={handleTextKeyDown}
            onSelectionChange={(cursor) => updateSlashState("integrated", integratedDraft, cursor)}
            placeholder="輸入一個問題，同時送到左右兩邊。"
            disabled={disabled}
            aria-controls={slashState?.target === "integrated" ? "skill-command-menu" : undefined}
            aria-expanded={slashState?.target === "integrated" && slashMatches.length > 0}
            aria-autocomplete="list"
          />
          <button className="sendButton" type="button" onClick={onSubmitIntegrated} disabled={disabled}>
            <Send aria-hidden="true" size={18} />
            送出
          </button>
        </div>
      ) : (
        <div className="splitInputRow">
          {profiles.map((profile) => {
            const hasControls = Object.values(profile.harness_modules).some(Boolean);
            const paneDisabled = profileDisabled[profile.id] ?? false;
            return (
              <div className="inputRow" key={profile.id}>
                <PromptEditor
                  ref={(element) => {
                    profileEditorRefs.current[profile.id] = element;
                  }}
                  value={profileDrafts[profile.id] ?? ""}
                  skills={skills}
                  onValueChange={(value, cursor) => handleEditorChange(profile.id, value, cursor)}
                  onFocus={(cursor) => handleEditorFocus(profile.id, profileDrafts[profile.id] ?? "", cursor)}
                  onPaste={handlePaste}
                  onKeyDown={handleTextKeyDown}
                  onSelectionChange={(cursor) =>
                    updateSlashState(profile.id, profileDrafts[profile.id] ?? "", cursor)
                  }
                  placeholder={`只送到 ${profile.label}。`}
                  disabled={paneDisabled}
                  aria-controls={slashState?.target === profile.id ? "skill-command-menu" : undefined}
                  aria-expanded={slashState?.target === profile.id && slashMatches.length > 0}
                  aria-autocomplete="list"
                />
                <button
                  className={`sendButton ${hasControls ? "harnessSend" : "secondarySend"}`}
                  type="button"
                  onClick={() => onSubmitProfile(profile.id)}
                  disabled={paneDisabled}
                >
                  <Send aria-hidden="true" size={18} />
                  送 {profile.label}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </footer>
  );
}

const PromptEditor = forwardRef<
  PromptEditorHandle,
  {
    value: string;
    skills: SkillSummary[];
    placeholder: string;
    disabled: boolean;
    "aria-controls"?: string;
    "aria-expanded"?: boolean;
    "aria-autocomplete"?: "list";
    onValueChange: (value: string, cursor: number) => void;
    onFocus: (cursor: number) => void;
    onSelectionChange: (cursor: number) => void;
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
    onPaste: (event: ClipboardEvent<HTMLElement>) => void;
  }
>(function PromptEditor(
  {
    value,
    skills,
    placeholder,
    disabled,
    onValueChange,
    onFocus,
    onSelectionChange,
    onKeyDown,
    onPaste,
    ...ariaProps
  },
  ref
) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const pendingSelectionRef = useRef<number | null>(null);

  useImperativeHandle(ref, () => ({
    focus: () => rootRef.current?.focus(),
    setSelectionRange: (start: number, end: number) => {
      const root = rootRef.current;
      if (!root) {
        return;
      }
      setEditorSelection(root, start, end);
    }
  }));

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    const shouldRestoreSelection = pendingSelectionRef.current !== null || document.activeElement === root;
    const cursor = pendingSelectionRef.current ?? editorSelectionOffset(root) ?? value.length;
    renderPromptEditor(root, value, skills);
    if (shouldRestoreSelection) {
      setEditorSelection(root, cursor, cursor);
    }
    pendingSelectionRef.current = null;
  }, [value, skills]);

  function handleInput() {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    const next = editorPlainText(root);
    const cursor = editorSelectionOffset(root) ?? next.length;
    pendingSelectionRef.current = cursor;
    onValueChange(next, cursor);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (deleteAdjacentSkillToken(event, value, skills)) {
      return;
    }
    onKeyDown(event);
    if (event.key === "Enter" && !event.defaultPrevented) {
      event.preventDefault();
      insertPlainTextAtSelection("\n");
    }
  }

  function handleSelectionChange() {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    onSelectionChange(editorSelectionOffset(root) ?? value.length);
  }

  return (
    <div
      ref={rootRef}
      className="promptEditor"
      role="textbox"
      aria-multiline="true"
      aria-disabled={disabled}
      data-placeholder={placeholder}
      contentEditable={disabled ? "false" : "plaintext-only"}
      suppressContentEditableWarning
      spellCheck
      tabIndex={disabled ? -1 : 0}
      onInput={handleInput}
      onFocus={() => onFocus(editorSelectionOffset(rootRef.current) ?? value.length)}
      onKeyDown={handleKeyDown}
      onKeyUp={handleSelectionChange}
      onMouseUp={handleSelectionChange}
      onSelect={handleSelectionChange}
      onPaste={onPaste}
      {...ariaProps}
    />
  );

  function insertPlainTextAtSelection(text: string) {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    const selection = editorSelectionRange(root);
    const start = selection?.start ?? value.length;
    const end = selection?.end ?? start;
    const next = `${value.slice(0, start)}${text}${value.slice(end)}`;
    const cursor = start + text.length;
    pendingSelectionRef.current = cursor;
    onValueChange(next, cursor);
  }
});

function joinDraft(current: string, addition: string) {
  const trimmed = current.trimEnd();
  return trimmed ? `${trimmed} ${addition}` : addition;
}

function slashQueryAtCursor(value: string, cursor: number) {
  const prefix = value.slice(0, cursor);
  const tokenStart = Math.max(prefix.lastIndexOf(" "), prefix.lastIndexOf("\n"), prefix.lastIndexOf("\t")) + 1;
  const token = prefix.slice(tokenStart);
  if (!token.startsWith("/") || token.includes("/ ")) {
    return null;
  }
  const query = token.slice(1);
  if (!/^[A-Za-z0-9_.-]*$/.test(query)) {
    return null;
  }
  return { query, start: tokenStart, end: cursor };
}

function renderPromptEditor(root: HTMLDivElement, value: string, skills: SkillSummary[]) {
  const ranges = skillTokenRanges(value, skills);
  root.replaceChildren();
  let cursor = 0;
  ranges.forEach((range) => {
    if (range.start > cursor) {
      root.append(document.createTextNode(value.slice(cursor, range.start)));
    }
    const token = value.slice(range.start, range.tokenEnd);
    const chip = document.createElement("span");
    chip.className = "skillCommandToken";
    chip.contentEditable = "false";
    chip.dataset.skillId = range.id;
    chip.dataset.token = token;
    chip.textContent = token;
    root.append(chip);
    if (range.end > range.tokenEnd) {
      root.append(document.createTextNode(value.slice(range.tokenEnd, range.end)));
    }
    cursor = range.end;
  });
  if (cursor < value.length) {
    root.append(document.createTextNode(value.slice(cursor)));
  }
}

function skillTokenRanges(value: string, skills: SkillSummary[]): SkillTokenRange[] {
  if (!skills.length || !value.includes("/")) {
    return [];
  }
  const skillIds = new Set(skills.map((skill) => skill.id));
  const ranges: SkillTokenRange[] = [];
  const pattern = /(^|[\s])\/([A-Za-z0-9_.-]+)(?=$|[\s])/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(value)) !== null) {
    const id = match[2];
    if (!skillIds.has(id)) {
      continue;
    }
    const start = match.index + match[1].length;
    const tokenEnd = start + id.length + 1;
    const end = value[tokenEnd] === " " ? tokenEnd + 1 : tokenEnd;
    ranges.push({ start, tokenEnd, end, id });
  }
  return ranges;
}

function editorPlainText(root: HTMLElement) {
  return Array.from(root.childNodes).map((node) => nodePlainText(node)).join("");
}

function nodePlainText(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent ?? "";
  }
  if (node instanceof HTMLBRElement) {
    return "\n";
  }
  if (node instanceof HTMLElement && node.classList.contains("skillCommandToken")) {
    return node.dataset.token ?? node.textContent ?? "";
  }
  if (node instanceof HTMLDivElement || node instanceof HTMLParagraphElement) {
    return Array.from(node.childNodes).map((child) => nodePlainText(child)).join("") + "\n";
  }
  return Array.from(node.childNodes).map((child) => nodePlainText(child)).join("");
}

function editorSelectionRange(root: HTMLElement) {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return null;
  }
  const range = selection.getRangeAt(0);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) {
    return null;
  }
  return {
    start: editorOffsetForPoint(root, range.startContainer, range.startOffset),
    end: editorOffsetForPoint(root, range.endContainer, range.endOffset),
  };
}

function editorSelectionOffset(root: HTMLElement | null) {
  if (!root) {
    return null;
  }
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return null;
  }
  const range = selection.getRangeAt(0);
  if (!root.contains(range.startContainer)) {
    return null;
  }
  return editorOffsetForPoint(root, range.startContainer, range.startOffset);
}

function editorOffsetForPoint(root: HTMLElement, container: Node, offset: number) {
  const range = document.createRange();
  range.selectNodeContents(root);
  range.setEnd(container, offset);
  return range.toString().length;
}

function setEditorSelection(root: HTMLElement, start: number, end: number) {
  const selection = window.getSelection();
  if (!selection) {
    return;
  }
  const range = document.createRange();
  const startPoint = editorPointAtOffset(root, start);
  const endPoint = editorPointAtOffset(root, end);
  range.setStart(startPoint.node, startPoint.offset);
  range.setEnd(endPoint.node, endPoint.offset);
  selection.removeAllRanges();
  selection.addRange(range);
}

function editorPointAtOffset(root: HTMLElement, targetOffset: number) {
  let current = 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let node = walker.nextNode();
  while (node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent ?? "";
      const next = current + text.length;
      if (targetOffset <= next) {
        return { node, offset: Math.max(0, targetOffset - current) };
      }
      current = next;
    } else if (node instanceof HTMLBRElement) {
      const next = current + 1;
      if (targetOffset <= next) {
        return { node: root, offset: childIndex(root, node) + 1 };
      }
      current = next;
    } else if (node instanceof HTMLElement && node.classList.contains("skillCommandToken")) {
      const token = node.dataset.token ?? node.textContent ?? "";
      const next = current + token.length;
      if (targetOffset <= next) {
        const offset = targetOffset - current < token.length / 2 ? childIndex(root, node) : childIndex(root, node) + 1;
        return { node: root, offset };
      }
      current = next;
    }
    node = walker.nextNode();
  }
  return { node: root, offset: root.childNodes.length };
}

function childIndex(parent: HTMLElement, child: Node) {
  return Array.prototype.indexOf.call(parent.childNodes, child);
}

function deleteAdjacentSkillToken(event: KeyboardEvent<HTMLElement>, value: string, skills: SkillSummary[]) {
  if (event.key !== "Backspace" && event.key !== "Delete") {
    return false;
  }
  const root = event.currentTarget;
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || !selection.getRangeAt(0).collapsed) {
    return false;
  }
  const cursor = editorSelectionOffset(root);
  if (cursor === null) {
    return false;
  }
  const ranges = skillTokenRanges(value, skills);
  const target =
    event.key === "Backspace"
      ? ranges.find((range) => cursor > range.start && cursor <= range.end)
      : ranges.find((range) => cursor >= range.start && cursor < range.end);
  if (!target) {
    return false;
  }
  event.preventDefault();
  const next = `${value.slice(0, target.start)}${value.slice(target.end)}`;
  root.replaceChildren();
  root.append(document.createTextNode(next));
  root.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward" }));
  requestAnimationFrame(() => setEditorSelection(root, target.start, target.start));
  return true;
}
