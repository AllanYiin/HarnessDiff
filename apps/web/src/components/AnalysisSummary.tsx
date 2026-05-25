import type { AnalysisDocument, ProfileAnalysis } from "../api";

type AnalysisSummaryProps = {
  turnCount: number;
  inputMode: string;
  running: boolean;
  analysis: AnalysisDocument | null;
};

export function AnalysisSummary({ turnCount, inputMode, running, analysis }: AnalysisSummaryProps) {
  const profiles = analysis ? Object.values(analysis.profiles) : [];
  const headline = running
    ? "正在比較左右輸出"
    : analysis
      ? "本回合分析已產生"
      : turnCount === 0
        ? "準備開始第一回合"
        : "等待分析資料";
  const summary = analysis
    ? `Delta ${formatSigned(analysis.comparison.total_token_delta)} tokens；目前是 ${inputMode === "integrated" ? "整合輸入" : "個別輸入"}。`
    : turnCount === 0
      ? "第一回合預設一鍵雙送；完成後會切換為個別輸入。"
      : "尚未收到後端分析資料；請檢查本回合 stream 是否送出 analysis_ready。";

  return (
    <aside className="analysisSummary" aria-label="Current comparison summary">
      <div className="analysisLead">
        <strong>{headline}</strong>
        <span>{summary}</span>
      </div>
      {analysis ? (
        <div className="analysisMetrics" aria-label="Token and context metrics">
          {profiles.map((profile) => (
            <Metric key={profile.profile_id} profile={profile} />
          ))}
          <span>Turn {analysis.turn_index + 1}</span>
        </div>
      ) : null}
    </aside>
  );
}

function Metric({ profile }: { profile: ProfileAnalysis }) {
  const usage = profile.current_turn_usage;
  const cumulative = profile.cumulative_usage;
  const inputTokens = asNumber(usage.input_tokens);
  const cachedTokens = asNumber(usage.cached_tokens);
  const outputTokens = asNumber(usage.output_tokens);
  const reasoningTokens = asNumber(usage.reasoning_tokens);
  const totalTokens = asNumber(usage.total_tokens);
  const cumulativeTotalTokens = asNumber(cumulative.total_tokens);
  return (
    <span
      title={`Current turn: input ${inputTokens}, cached input ${cachedTokens}, output ${outputTokens}, reasoning ${reasoningTokens}, total ${totalTokens}; cumulative total ${cumulativeTotalTokens}`}
    >
      {profile.profile_label} input tokens {inputTokens} (cached input {cachedTokens}) · output tokens{" "}
      {outputTokens} · reasoning {reasoningTokens} · total {totalTokens} · Σ{" "}
      {cumulativeTotalTokens}
    </span>
  );
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatSigned(value: number) {
  if (value > 0) {
    return `+${value}`;
  }
  return `${value}`;
}
