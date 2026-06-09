import { useEffect, useRef, useState } from "react";
import { basicSetup, EditorView } from "codemirror";
import { EditorState } from "@codemirror/state";
import { html } from "@codemirror/lang-html";
import { markdown } from "@codemirror/lang-markdown";
import { Check, Code2, Columns2, CopyPlus, Eye, FileText, Save } from "lucide-react";

import { MarkdownContent } from "./MarkdownContent";
import type { ArtifactDocument, ArtifactKind, ProfileId, ProfileInstance } from "../types";

type ArtifactWorkbenchProps = {
  profile: ProfileInstance;
  artifact: ArtifactDocument | null;
  draft: string;
  title: string;
  kind: ArtifactKind;
  saving: boolean;
  error: string;
  inputMode: "integrated" | "independent";
  onDraftChange: (profileId: ProfileId, value: string) => void;
  onSave: (profileId: ProfileId) => void;
  onInitializeAll: (profileId: ProfileId) => void;
};

type WorkbenchView = "edit" | "preview" | "diff";

export function ArtifactWorkbench({
  profile,
  artifact,
  draft,
  title,
  kind,
  saving,
  error,
  inputMode,
  onDraftChange,
  onSave,
  onInitializeAll
}: ArtifactWorkbenchProps) {
  const [view, setView] = useState<WorkbenchView>("edit");
  const [scriptsEnabled, setScriptsEnabled] = useState(false);
  const dirty =
    !artifact ||
    artifact.content !== draft ||
    artifact.title !== title ||
    artifact.kind !== kind;

  return (
    <section className="artifactWorkbench" aria-label="Artifact canvas workbench">
      <div className="artifactIdentity" aria-hidden="true">
        {Object.keys(profile.harness_modules).length > 0 ? (
          <Code2 size={14} />
        ) : (
          <FileText size={14} />
        )}
        <span>{title}</span>
      </div>
      <header className="artifactToolbar">
        <div className="artifactIconToolbar" role="toolbar" aria-label={`${profile.label} canvas actions`}>
          <button
            type="button"
            aria-label="Edit canvas"
            className={view === "edit" ? "selected" : ""}
            onClick={() => setView("edit")}
            title="Edit"
          >
            <FileText aria-hidden="true" size={16} />
          </button>
          <button
            type="button"
            aria-label="Preview canvas"
            className={view === "preview" ? "selected" : ""}
            onClick={() => setView("preview")}
            title="Preview"
          >
            <Eye aria-hidden="true" size={16} />
          </button>
          <button
            type="button"
            aria-label="Show canvas diff"
            className={view === "diff" ? "selected" : ""}
            onClick={() => setView("diff")}
            title="Diff"
          >
            <Columns2 aria-hidden="true" size={16} />
          </button>
          <button
            type="button"
            aria-label="Copy initial canvas"
            onClick={() => onInitializeAll(profile.id)}
            disabled={inputMode !== "integrated"}
            title="Copy initial"
          >
            <CopyPlus aria-hidden="true" size={16} />
          </button>
          <button
            type="button"
            aria-label="Save canvas"
            className="primaryArtifactAction"
            onClick={() => onSave(profile.id)}
            disabled={saving || (!dirty && Boolean(artifact))}
            title={saving ? "Saving" : dirty ? "Save" : "Saved"}
          >
            {saving ? <Save aria-hidden="true" size={16} /> : dirty ? <Save aria-hidden="true" size={16} /> : <Check aria-hidden="true" size={16} />}
          </button>
        </div>
      </header>

      {error ? <div className="artifactError">{error}</div> : null}

      <div className="artifactSurface" data-view={view}>
        {view === "edit" ? (
          <ArtifactCodeEditor
            key={`${profile.id}-${kind}`}
            kind={kind}
            value={draft}
            onChange={(value) => onDraftChange(profile.id, value)}
          />
        ) : null}
        {view === "preview" ? (
          <ArtifactPreview
            kind={kind}
            content={draft}
            scriptsEnabled={scriptsEnabled}
            onScriptsEnabledChange={setScriptsEnabled}
          />
        ) : null}
        {view === "diff" ? (
          <ArtifactDiff saved={artifact?.content ?? ""} draft={draft} />
        ) : null}
      </div>
    </section>
  );
}

function ArtifactCodeEditor({
  kind,
  value,
  onChange
}: {
  kind: ArtifactKind;
  value: string;
  onChange: (value: string) => void;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const latestValueRef = useRef(value);

  useEffect(() => {
    latestValueRef.current = value;
    const host = hostRef.current;
    if (!host) {
      return;
    }
    const extensions = [
      basicSetup,
      kind === "single_page_html" || kind === "svg" ? html() : kind === "markdown" ? markdown() : [],
      EditorView.lineWrapping,
      EditorView.updateListener.of((update) => {
        if (!update.docChanged) {
          return;
        }
        const next = update.state.doc.toString();
        latestValueRef.current = next;
        onChange(next);
      })
    ];
    const view = new EditorView({
      parent: host,
      state: EditorState.create({ doc: value, extensions })
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [kind]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || latestValueRef.current === value) {
      return;
    }
    latestValueRef.current = value;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value }
    });
  }, [value]);

  return <div ref={hostRef} className="artifactEditor" />;
}

function ArtifactPreview({
  kind,
  content,
  scriptsEnabled,
  onScriptsEnabledChange
}: {
  kind: ArtifactKind;
  content: string;
  scriptsEnabled: boolean;
  onScriptsEnabledChange: (value: boolean) => void;
}) {
  if (kind === "svg") {
    if (!content.trim()) {
      return <pre className="artifactTextPreview">No canvas content.</pre>;
    }
    return (
      <iframe
        title="SVG preview"
        className="artifactHtmlPreview artifactSvgPreview"
        sandbox=""
        srcDoc={content}
      />
    );
  }
  if (kind === "markdown") {
    return (
      <div className="artifactMarkdownPreview">
        <MarkdownContent source={content || "No canvas content."} />
      </div>
    );
  }
  if (kind !== "single_page_html") {
    return <pre className="artifactTextPreview">{content || "No canvas content."}</pre>;
  }
  return (
    <div className="artifactPreviewStack">
      <label className="artifactScriptToggle">
        <input
          type="checkbox"
          checked={scriptsEnabled}
          onChange={(event) => onScriptsEnabledChange(event.target.checked)}
        />
        Enable scripts
      </label>
      <iframe
        title="single-page HTML preview"
        className="artifactHtmlPreview"
        sandbox={scriptsEnabled ? "allow-scripts" : ""}
        srcDoc={content}
      />
    </div>
  );
}

function ArtifactDiff({ saved, draft }: { saved: string; draft: string }) {
  const rows = lineDiff(saved, draft);
  return (
    <div className="artifactDiff" role="table" aria-label="Saved and draft diff">
      {rows.length === 0 ? <div className="artifactDiffEmpty">No saved content yet.</div> : null}
      {rows.map((row, index) => (
        <div className={`artifactDiffRow ${row.kind}`} role="row" key={`${row.kind}-${index}`}>
          <span>{row.kind === "same" ? " " : row.kind === "removed" ? "-" : "+"}</span>
          <code>{row.text || " "}</code>
        </div>
      ))}
    </div>
  );
}

function lineDiff(saved: string, draft: string) {
  const savedLines = saved.split(/\r?\n/);
  const draftLines = draft.split(/\r?\n/);
  const max = Math.max(savedLines.length, draftLines.length);
  const rows: Array<{ kind: "same" | "removed" | "added"; text: string }> = [];
  for (let index = 0; index < max; index += 1) {
    const left = savedLines[index];
    const right = draftLines[index];
    if (left === right) {
      rows.push({ kind: "same", text: left ?? "" });
      continue;
    }
    if (left !== undefined) {
      rows.push({ kind: "removed", text: left });
    }
    if (right !== undefined) {
      rows.push({ kind: "added", text: right });
    }
  }
  return rows;
}
