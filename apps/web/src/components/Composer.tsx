import { Mic, Paperclip, Send, Square, X } from "lucide-react";
import type { ChangeEvent, ClipboardEvent, FocusEvent, KeyboardEvent } from "react";
import { useRef, useState } from "react";

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
  const activeTargetRef = useRef<"integrated" | ProfileId>("integrated");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const integratedTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const profileTextareaRefs = useRef<Record<ProfileId, HTMLTextAreaElement | null>>({});
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

  function handleTextChange(
    target: "integrated" | ProfileId,
    event: ChangeEvent<HTMLTextAreaElement>
  ) {
    const value = event.target.value;
    if (target === "integrated") {
      onIntegratedDraftChange(value);
    } else {
      onProfileDraftChange(target, value);
    }
    updateSlashState(target, value, event.target.selectionStart);
  }

  function handleTextFocus(target: "integrated" | ProfileId, event: FocusEvent<HTMLTextAreaElement>) {
    activeTargetRef.current = target;
    updateSlashState(target, event.currentTarget.value, event.currentTarget.selectionStart);
  }

  function handleTextKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
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
      const textarea =
        slashState.target === "integrated"
          ? integratedTextareaRef.current
          : profileTextareaRefs.current[slashState.target];
      textarea?.focus();
      textarea?.setSelectionRange(cursor, cursor);
    });
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(event.clipboardData.files);
    if (!files.length) {
      return;
    }
    event.preventDefault();
    onAttach(files);
  }

  function toggleVoiceInput() {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
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
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setVoiceError("");
    setListening(true);
    recognition.start();
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
            aria-label={listening ? "Stop voice input" : "Voice input"}
            aria-pressed={listening}
            onClick={toggleVoiceInput}
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
          <textarea
            ref={integratedTextareaRef}
            value={integratedDraft}
            onFocus={(event) => handleTextFocus("integrated", event)}
            onPaste={handlePaste}
            onKeyDown={handleTextKeyDown}
            onSelect={(event) =>
              updateSlashState("integrated", event.currentTarget.value, event.currentTarget.selectionStart)
            }
            onChange={(event) => handleTextChange("integrated", event)}
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
                <textarea
                  ref={(element) => {
                    profileTextareaRefs.current[profile.id] = element;
                  }}
                  value={profileDrafts[profile.id] ?? ""}
                  onFocus={(event) => handleTextFocus(profile.id, event)}
                  onPaste={handlePaste}
                  onKeyDown={handleTextKeyDown}
                  onSelect={(event) =>
                    updateSlashState(profile.id, event.currentTarget.value, event.currentTarget.selectionStart)
                  }
                  onChange={(event) => handleTextChange(profile.id, event)}
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
