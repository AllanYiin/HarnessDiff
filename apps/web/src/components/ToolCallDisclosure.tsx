import type { TokenUsageTrace, ToolCallTrace } from "../types";

type ToolCallDisclosureProps = {
  toolCall: ToolCallTrace;
  index: number;
};

function formatJson(value: unknown) {
  if (value === undefined || value === null || value === "") {
    return "(empty)";
  }
  if (typeof value === "string") {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  return JSON.stringify(value, null, 2);
}

function outputFor(toolCall: ToolCallTrace) {
  if (toolCall.ok === false) {
    return formatJson(toolCall.error ?? { message: "Tool call failed." });
  }
  return formatJson(toolCall.result_summary ?? "(no result summary)");
}

export function ToolCallDisclosure({ toolCall, index }: ToolCallDisclosureProps) {
  const isSubagent = Boolean(toolCall.subagent_id) || toolCall.tool_name === "harness.subagent.run";
  const statusLabel = toolCall.ok === false ? "失敗" : "完成";
  const name = toolCall.tool_name || toolCall.openai_name || "unknown_tool";
  const tokenLabel = tokenUsageLabel(toolCall.token_usage);

  return (
    <details className={`toolCallDisclosure ${isSubagent ? "subagentToolCall" : ""}`}>
      <summary>
        <span className="toolCallIndex">#{index + 1}</span>
        <span className="toolCallName">{name}</span>
        {isSubagent ? (
          <span className="toolCallBadge">{toolCall.subagent_label || toolCall.subagent_id || "Subagent"}</span>
        ) : null}
        <span className={`toolCallStatus ${toolCall.ok === false ? "failed" : ""}`}>{statusLabel}</span>
        {tokenLabel ? <span className="toolCallTokens">{tokenLabel}</span> : null}
        {typeof toolCall.elapsed_ms === "number" ? (
          <span className="toolCallLatency">{toolCall.elapsed_ms} ms</span>
        ) : null}
      </summary>
      <div className="toolCallBody">
        {toolCall.token_usage ? (
          <section>
            <h3>耗用</h3>
            <pre>{formatTokenUsage(toolCall.token_usage)}</pre>
          </section>
        ) : null}
        <section>
          <h3>輸入引數</h3>
          <pre>{formatJson(toolCall.arguments)}</pre>
        </section>
        <section>
          <h3>輸出結果</h3>
          <pre>{outputFor(toolCall)}</pre>
        </section>
      </div>
    </details>
  );
}

function tokenUsageLabel(usage?: TokenUsageTrace) {
  const total = tokenValue(usage?.total_tokens);
  if (!total) {
    return "";
  }
  return `${usage?.source === "provider_reported" ? "實" : "估"} ${total} tok`;
}

function formatTokenUsage(usage: TokenUsageTrace) {
  const lines = [
    `${usage.source === "provider_reported" ? "provider reported" : "estimated"} total: ${tokenValue(usage.total_tokens)}`,
    `input: ${tokenValue(usage.input_tokens)}`,
    `output: ${tokenValue(usage.output_tokens)}`,
  ];
  if (usage.cached_tokens !== undefined) {
    lines.push(`cached input: ${tokenValue(usage.cached_tokens)}`);
  }
  if (usage.reasoning_tokens !== undefined) {
    lines.push(`reasoning: ${tokenValue(usage.reasoning_tokens)}`);
  }
  if (usage.basis) {
    lines.push(`basis: ${usage.basis}`);
  }
  return lines.join("\n");
}

function tokenValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
