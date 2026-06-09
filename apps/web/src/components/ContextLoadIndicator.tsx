import { useMemo, useState, type CSSProperties } from "react";
import type { ContextSection, ProfileAnalysis, SkillSummary, ToolSummary } from "../api";
import type { ProfileInstance } from "../types";

const waffleCellCount = 100;
const contextWindowByModel: Record<string, number | null> = {
  "gpt-5.4-mini": 400_000,
  "gpt-5.4": 1_000_000,
  "gpt-5.5": 1_000_000
};

const sectionColorByKey: Record<string, string> = {
  agent_instructions: "#2563eb",
  system_prompt: "#1e40af",
  tool_definitions: "#7c3aed",
  activated_skills: "#0e7490",
  behavior_preferences: "#c2410c",
  harness_control_plane: "#be123c",
  personal_memory: "#0369a1",
  current_user_turn: "#16a34a",
  current_agent_task: "#15803d",
  agent_steps: "#d97706",
  agent_step_trace: "#d97706",
  stored_conversation_history: "#334155",
  provider_unclassified: "#64748b"
};

type ContextLoadIndicatorProps = {
  analysis?: ProfileAnalysis;
  profile: ProfileInstance;
  skills: SkillSummary[];
  tools: ToolSummary[];
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

export function ContextLoadIndicator({ analysis, profile, skills, tools, model }: ContextLoadIndicatorProps) {
  const [open, setOpen] = useState(false);
  const contextWindowTokens = contextWindowForModel(model);
  const slices = useMemo(
    () => buildContextSlices(analysis, profile, skills, tools),
    [analysis, profile, skills, tools]
  );
  const sectionTokens = slices.reduce((sum, section) => sum + section.tokens, 0);
  const classifiedTokens = slices.reduce(
    (sum, section) => (section.key === "provider_unclassified" ? sum : sum + section.tokens),
    0
  );
  const providerInputTokens = safeNumber(analysis?.current_turn_usage.input_tokens);
  const loadedTokens = Math.max(providerInputTokens, sectionTokens);
  const loadRatio =
    contextWindowTokens !== null && contextWindowTokens > 0
      ? clamp(loadedTokens / contextWindowTokens, 0, 1)
      : null;
  const loadPercent = loadRatio === null ? null : Math.round(loadRatio * 100);
  const loadPercentLabel =
    loadRatio === null ? "?" : loadRatio > 0 && loadPercent === 0 ? "<1%" : `${loadPercent}%`;
  const ringDegrees = loadRatio === null ? 0 : Math.round(loadRatio * 360);
  const status =
    loadPercent !== null && loadPercent >= 75
      ? "compressSoon"
      : loadPercent !== null && loadPercent >= 60
        ? "watch"
        : "ok";
  const statusLabel =
    status === "compressSoon" ? "壓縮門檻" : status === "watch" ? "偏高" : "正常";
  const classifiedLabel =
    classifiedTokens > 0 ? `${formatTokens(classifiedTokens)} classified sections` : "尚無分類";

  return (
    <div className={`contextLoadIndicator ${open ? "isOpen" : ""}`}>
      <button
        type="button"
        className={`contextRingButton ${status}`}
        aria-expanded={open}
        aria-label={`上文負載 ${loadRatio === null ? "未知" : loadPercentLabel}，${statusLabel}`}
        onClick={() => setOpen((current) => !current)}
        onBlur={(event) => {
          if (!event.currentTarget.parentElement?.contains(event.relatedTarget as Node | null)) {
            setOpen(false);
          }
        }}
        style={{ "--context-ring-deg": `${ringDegrees}deg` } as CSSProperties}
      >
        <span className="contextRing" aria-hidden="true" />
        <span className="contextRingText">{loadPercentLabel}</span>
      </button>
      <div className="contextPopover" role="dialog" aria-label="上文明細">
        <div className="contextPopoverHeader">
          <strong>上文負載</strong>
          <span>
            {formatTokens(loadedTokens)} / {formatContextWindow(contextWindowTokens)}
          </span>
        </div>
        <ContextWaffle slices={slices} contextWindowTokens={contextWindowTokens} />
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

function ContextWaffle({
  slices,
  contextWindowTokens
}: {
  slices: ContextSlice[];
  contextWindowTokens: number | null;
}) {
  const cells = waffleCells(slices, contextWindowTokens);
  return (
    <div className="contextWaffle" aria-hidden="true">
      {cells.map((color, index) => (
        <span key={index} style={{ background: color }} />
      ))}
    </div>
  );
}

function buildContextSlices(
  analysis: ProfileAnalysis | undefined,
  profile: ProfileInstance,
  skills: SkillSummary[],
  tools: ToolSummary[]
): ContextSlice[] {
  const sections = analysis?.context_sections ?? [];
  const slices = sections.map((section) => contextSlice(section));
  const sectionTokens = slices.reduce((sum, section) => sum + section.tokens, 0);
  const providerInputTokens = safeNumber(analysis?.current_turn_usage.input_tokens);
  if (providerInputTokens > sectionTokens) {
    slices.push({
      key: "provider_unclassified",
      label: "Provider input reconciliation",
      status: "reported",
      tokens: providerInputTokens - sectionTokens,
      notes:
        "Provider-reported input tokens above saved context estimates; this may include provider-side serialization, cached prompt framing, or tokenizer differences.",
      color: sectionColorByKey.provider_unclassified
    });
  }
  return slices.length ? slices : pendingContextSlices(profile, skills, tools);
}

function pendingContextSlices(
  profile: ProfileInstance,
  skills: SkillSummary[],
  tools: ToolSummary[]
): ContextSlice[] {
  const enabledModules = Object.entries(profile.harness_modules)
    .filter(([, enabled]) => enabled)
    .map(([name]) => name);
  const enabledTools = tools.filter((tool) => tool.enabled);
  const enabledSkills = skills.filter((skill) => skill.enabled);
  const slices = [
    pendingSlice(
      "agent_instructions",
      "Agent instructions",
      "estimated",
      [
        "HarnessDiff Agent mode runtime instructions",
        profile.label,
        enabledModules.join(" ")
      ].join("\n"),
      "Estimated from the selected Agent profile before backend analysis is available."
    ),
    pendingSlice(
      "harness_control_plane",
      "Harness modules",
      enabledModules.length ? "configured" : "not_configured",
      enabledModules.join("\n"),
      "Enabled Harness module ids that affect instructions and control-plane context."
    ),
    pendingSlice(
      "tool_definitions",
      "Tool definitions",
      profile.harness_modules.tool_policy ? "configured" : "not_configured",
      enabledTools.length
        ? enabledTools.map((tool) => `${tool.name}: ${tool.description}`).join("\n")
        : profile.harness_modules.tool_policy
          ? "Runtime tool schemas are enabled and assembled by the backend."
          : "",
      "Estimated from enabled tool metadata; provider schema overhead is finalized by the backend."
    ),
    pendingSlice(
      "activated_skills",
      "Skill metadata",
      enabledSkills.length ? "configured" : "not_configured",
      enabledSkills.map((skill) => `${skill.name}: ${skill.description}`).join("\n"),
      "First-layer skill metadata available before task-specific skill activation."
    )
  ];
  return slices.filter((slice) => slice.tokens > 0);
}

function pendingSlice(
  key: string,
  label: string,
  status: string,
  text: string,
  notes: string
): ContextSlice {
  return {
    key,
    label,
    status,
    tokens: estimateTextTokens(text),
    notes,
    color: sectionColorByKey[key] ?? "#64748b"
  };
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

function waffleCells(slices: ContextSlice[], contextWindowTokens: number | null) {
  const positiveSlices = slices.filter((section) => section.tokens > 0);
  if (!positiveSlices.length || contextWindowTokens === null || contextWindowTokens <= 0) {
    return Array.from({ length: waffleCellCount }, () => "#e2e8f0");
  }
  const total = Math.max(contextWindowTokens, positiveSlices.reduce((sum, section) => sum + section.tokens, 0));
  const rawCounts = positiveSlices.map((section) => ({
    section,
    count: Math.floor((section.tokens / total) * waffleCellCount),
    remainder: ((section.tokens / total) * waffleCellCount) % 1
  }));
  let assigned = rawCounts.reduce((sum, item) => sum + item.count, 0);
  [...rawCounts]
    .sort((left, right) => right.remainder - left.remainder)
    .forEach((item) => {
      if (assigned < waffleCellCount && item.remainder > 0) {
        item.count += 1;
        assigned += 1;
      }
    });
  const usedCells = rawCounts.flatMap((item) => Array.from({ length: item.count }, () => item.section.color));
  return [
    ...usedCells,
    ...Array.from({ length: Math.max(0, waffleCellCount - usedCells.length) }, () => "#e2e8f0")
  ].slice(0, waffleCellCount);
}

function contextWindowForModel(model: string) {
  return contextWindowByModel[model] ?? null;
}

function safeNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;
}

function estimateTextTokens(text: string) {
  const characters = text.trim().length;
  return characters ? Math.max(1, Math.ceil(characters / 4)) : 0;
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

function formatContextWindow(value: number | null) {
  return value === null ? "window unknown" : formatTokens(value);
}
