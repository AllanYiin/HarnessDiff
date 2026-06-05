import { useMemo, useState, type CSSProperties } from "react";
import type { ContextSection, ProfileAnalysis } from "../api";

const waffleCellCount = 100;
const defaultContextWindowTokens = 1_000_000;

const sectionColorByKey: Record<string, string> = {
  system_prompt: "#2563eb",
  tool_definitions: "#7c3aed",
  activated_skills: "#0f766e",
  behavior_preferences: "#d97706",
  harness_control_plane: "#be123c",
  personal_memory: "#0891b2",
  current_user_turn: "#16a34a",
  stored_conversation_history: "#64748b",
  provider_unclassified: "#94a3b8"
};

type ContextLoadIndicatorProps = {
  analysis?: ProfileAnalysis;
  model: string;
};

type ContextSlice = {
  key: string;
  label: string;
  status: string;
  tokens: number;
  notes: string;
  color: string;
};

export function ContextLoadIndicator({ analysis, model }: ContextLoadIndicatorProps) {
  const [open, setOpen] = useState(false);
  const contextWindowTokens = contextWindowForModel(model);
  const slices = useMemo(() => buildContextSlices(analysis), [analysis]);
  const sectionTokens = slices.reduce((sum, section) => sum + section.tokens, 0);
  const providerInputTokens = safeNumber(analysis?.current_turn_usage.input_tokens);
  const loadedTokens = Math.max(providerInputTokens, sectionTokens);
  const loadRatio = contextWindowTokens > 0 ? clamp(loadedTokens / contextWindowTokens, 0, 1) : 0;
  const loadPercent = Math.round(loadRatio * 100);
  const ringDegrees = Math.round(loadRatio * 360);
  const status = loadPercent >= 75 ? "compressSoon" : loadPercent >= 60 ? "watch" : "ok";
  const statusLabel =
    status === "compressSoon" ? "壓縮門檻" : status === "watch" ? "偏高" : "正常";
  const classifiedLabel =
    sectionTokens > 0 ? `${formatTokens(sectionTokens)} classified` : "尚無分類";

  return (
    <div className={`contextLoadIndicator ${open ? "isOpen" : ""}`}>
      <button
        type="button"
        className={`contextRingButton ${status}`}
        aria-expanded={open}
        aria-label={`上文負載 ${loadPercent}%，${statusLabel}`}
        onClick={() => setOpen((current) => !current)}
        onBlur={(event) => {
          if (!event.currentTarget.parentElement?.contains(event.relatedTarget as Node | null)) {
            setOpen(false);
          }
        }}
        style={{ "--context-ring-deg": `${ringDegrees}deg` } as CSSProperties}
      >
        <span className="contextRing" aria-hidden="true" />
        <span className="contextRingText">{loadPercent}%</span>
      </button>
      <div className="contextPopover" role="dialog" aria-label="上文明細">
        <div className="contextPopoverHeader">
          <strong>上文負載</strong>
          <span>
            {formatTokens(loadedTokens)} / {formatTokens(contextWindowTokens)}
          </span>
        </div>
        <ContextWaffle slices={slices} />
        <div className="contextLegend" aria-label="上文分類">
          {slices.map((section) => (
            <div className="contextLegendRow" key={section.key}>
              <span className="contextLegendSwatch" style={{ background: section.color }} />
              <span className="contextLegendLabel">{section.label}</span>
              <span className="contextLegendMeta">
                {formatTokens(section.tokens)} · {section.status}
              </span>
            </div>
          ))}
        </div>
        <div className="contextPopoverFooter">
          <span>{statusLabel}</span>
          <span>{classifiedLabel}</span>
        </div>
      </div>
    </div>
  );
}

function ContextWaffle({ slices }: { slices: ContextSlice[] }) {
  const cells = waffleCells(slices);
  return (
    <div className="contextWaffle" aria-hidden="true">
      {cells.map((color, index) => (
        <span key={index} style={{ background: color }} />
      ))}
    </div>
  );
}

function buildContextSlices(analysis?: ProfileAnalysis): ContextSlice[] {
  const sections = analysis?.context_sections ?? [];
  const slices = sections.map((section) => contextSlice(section));
  const sectionTokens = slices.reduce((sum, section) => sum + section.tokens, 0);
  const providerInputTokens = safeNumber(analysis?.current_turn_usage.input_tokens);
  if (providerInputTokens > sectionTokens) {
    slices.push({
      key: "provider_unclassified",
      label: "Provider input overhead",
      status: "reported",
      tokens: providerInputTokens - sectionTokens,
      notes: "Provider-reported input tokens not classified by saved context sections.",
      color: sectionColorByKey.provider_unclassified
    });
  }
  return slices.length ? slices : [
    {
      key: "empty",
      label: "Analysis pending",
      status: "missing",
      tokens: 0,
      notes: "Run analysis has not been generated yet.",
      color: "#cbd5e1"
    }
  ];
}

function contextSlice(section: ContextSection): ContextSlice {
  return {
    key: section.key,
    label: section.label,
    status: section.status,
    tokens: safeNumber(section.estimated_tokens),
    notes: section.notes,
    color: sectionColorByKey[section.key] ?? "#64748b"
  };
}

function waffleCells(slices: ContextSlice[]) {
  const positiveSlices = slices.filter((section) => section.tokens > 0);
  if (!positiveSlices.length) {
    return Array.from({ length: waffleCellCount }, () => "#e2e8f0");
  }
  const total = positiveSlices.reduce((sum, section) => sum + section.tokens, 0);
  const rawCounts = positiveSlices.map((section) => ({
    section,
    count: Math.floor((section.tokens / total) * waffleCellCount),
    remainder: ((section.tokens / total) * waffleCellCount) % 1
  }));
  let assigned = rawCounts.reduce((sum, item) => sum + item.count, 0);
  [...rawCounts]
    .sort((left, right) => right.remainder - left.remainder)
    .forEach((item) => {
      if (assigned < waffleCellCount) {
        item.count += 1;
        assigned += 1;
      }
    });
  return rawCounts.flatMap((item) => Array.from({ length: item.count }, () => item.section.color));
}

function contextWindowForModel(_model: string) {
  return defaultContextWindowTokens;
}

function safeNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function formatTokens(value: number) {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M tok`;
  }
  if (value >= 1_000) {
    return `${Math.round(value / 1_000)}k tok`;
  }
  return `${value} tok`;
}
