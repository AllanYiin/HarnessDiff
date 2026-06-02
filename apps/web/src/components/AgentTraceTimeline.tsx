import { ChevronDown } from "lucide-react";

import type { AgentStepTrace } from "../types";

type AgentTraceTimelineProps = {
  steps: AgentStepTrace[];
};

export function AgentTraceTimeline({ steps }: AgentTraceTimelineProps) {
  if (!steps.length) {
    return null;
  }
  const visibleSteps = steps.slice(-8);
  return (
    <details className="agentTraceTimeline">
      <summary className="agentTraceTimelineSummary">
        <span>處理過程</span>
        <span className="agentTraceCount">{visibleSteps.length}</span>
        <ChevronDown aria-hidden="true" size={14} />
      </summary>
      <div className="agentTraceList" aria-label="Agent 處理過程">
        {visibleSteps.map((step) => (
          <details className="agentTraceItem" key={step.id}>
            <summary>
              <span className={`traceStatus ${step.status}`}>{statusLabel(step.status)}</span>
              <span className="traceLabel">{step.label}</span>
              {step.elapsed_ms ? <span className="traceTime">{step.elapsed_ms}ms</span> : null}
              <ChevronDown aria-hidden="true" size={14} />
            </summary>
            <dl>
              {step.tool_name ? (
                <>
                  <dt>工具</dt>
                  <dd>{step.tool_name}</dd>
                </>
              ) : null}
              {step.subagent_id ? (
                <>
                  <dt>子任務</dt>
                  <dd>{step.subagent_label || step.subagent_id}</dd>
                </>
              ) : null}
              {step.token_usage?.total_tokens ? (
                <>
                  <dt>用量</dt>
                  <dd>{step.token_usage.total_tokens}</dd>
                </>
              ) : null}
            </dl>
          </details>
        ))}
      </div>
    </details>
  );
}

function statusLabel(status: AgentStepTrace["status"]) {
  if (status === "completed") return "完成";
  if (status === "error") return "錯誤";
  if (status === "cancelled") return "取消";
  if (status === "skipped") return "略過";
  return "執行";
}
