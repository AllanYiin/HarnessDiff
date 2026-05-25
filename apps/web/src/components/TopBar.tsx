import { useState } from "react";
import { History, Plus, Settings, Sparkles, SplitSquareHorizontal } from "lucide-react";

import type { HarnessModuleId, HarnessModules } from "../types";

const harnessModuleOptions: { id: HarnessModuleId; label: string }[] = [
  { id: "context_summary", label: "Context Summary" },
  { id: "source_map", label: "Source Map" },
  { id: "guardrails", label: "Guardrails" },
  { id: "output_contract", label: "Output Contract" },
  { id: "planning_preamble", label: "Planning Preamble" },
  { id: "tool_policy", label: "Tool Policy" },
  { id: "memory_selection", label: "Memory Selection" },
  { id: "post_answer_critique", label: "Post-answer Critique" },
  { id: "token_budgeter", label: "Token Budgeter" }
];

type TopBarProps = {
  model: string;
  reasoningEffort: string;
  harnessModules: HarnessModules;
  historyOpen: boolean;
  skillsOpen: boolean;
  onModelChange: (value: string) => void;
  onReasoningEffortChange: (value: string) => void;
  onHarnessModuleChange: (id: HarnessModuleId, enabled: boolean) => void;
  onNewConversation: () => void;
  onToggleHistory: () => void;
  onToggleSkills: () => void;
};

export function TopBar({
  model,
  reasoningEffort,
  harnessModules,
  historyOpen,
  skillsOpen,
  onModelChange,
  onReasoningEffortChange,
  onHarnessModuleChange,
  onNewConversation,
  onToggleHistory,
  onToggleSkills
}: TopBarProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <header className="topBar">
      <div className="brand">
        <SplitSquareHorizontal aria-hidden="true" size={22} />
        <div>
          <strong>HarnessDiff</strong>
          <span>Chat comparison</span>
        </div>
      </div>
      <div className="topControls" aria-label="Model controls">
        <button className="textButton" type="button" onClick={onNewConversation}>
          <Plus aria-hidden="true" size={16} />
          新對話
        </button>
        <button
          className={`textButton ${historyOpen ? "selected" : ""}`}
          type="button"
          onClick={onToggleHistory}
          aria-expanded={historyOpen}
        >
          <History aria-hidden="true" size={16} />
          歷史
        </button>
        <button
          className={`textButton ${skillsOpen ? "selected" : ""}`}
          type="button"
          onClick={onToggleSkills}
          aria-expanded={skillsOpen}
        >
          <Sparkles aria-hidden="true" size={16} />
          技能
        </button>
        <label>
          <span>模型</span>
          <select value={model} onChange={(event) => onModelChange(event.target.value)}>
            <option value="gpt-5.4-mini">gpt-5.4-mini</option>
            <option value="gpt-5.4">gpt-5.4</option>
            <option value="gpt-5.5">gpt-5.5</option>
          </select>
        </label>
        <label>
          <span>思考強度</span>
          <select
            value={reasoningEffort}
            onChange={(event) => onReasoningEffortChange(event.target.value)}
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="xhigh">xhigh</option>
          </select>
        </label>
        <button
          className="iconButton"
          type="button"
          aria-label="Harness settings"
          aria-expanded={settingsOpen}
          onClick={() => setSettingsOpen((current) => !current)}
        >
          <Settings aria-hidden="true" size={18} />
        </button>
        {settingsOpen ? (
          <div className="settingsMenu" aria-label="Harness module toggles">
            <strong>Harness 技巧</strong>
            <div className="toggleGrid">
              {harnessModuleOptions.map((option) => (
                <label key={option.id} className="toggleRow">
                  <input
                    type="checkbox"
                    checked={harnessModules[option.id]}
                    onChange={(event) => onHarnessModuleChange(option.id, event.target.checked)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </header>
  );
}
