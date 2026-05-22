import { Settings, SplitSquareHorizontal } from "lucide-react";

type TopBarProps = {
  model: string;
  reasoningEffort: string;
  onModelChange: (value: string) => void;
  onReasoningEffortChange: (value: string) => void;
};

export function TopBar({
  model,
  reasoningEffort,
  onModelChange,
  onReasoningEffortChange
}: TopBarProps) {
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
        <button className="iconButton" type="button" aria-label="Harness settings">
          <Settings aria-hidden="true" size={18} />
        </button>
      </div>
    </header>
  );
}

