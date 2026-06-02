import type { AnalysisDocument, HarnessDecisionTrace, ProfileAnalysis } from "../api";

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
        <div className="analysisAside">
          <div className="analysisMetrics" aria-label="Token and context metrics">
            {profiles.map((profile) => (
              <Metric key={profile.profile_id} profile={profile} />
            ))}
            <span>Turn {analysis.turn_index + 1}</span>
          </div>
          <RiskSignals profiles={profiles} />
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

function RiskSignals({ profiles }: { profiles: ProfileAnalysis[] }) {
  const signals = profiles.flatMap((profile) =>
    extractRiskSignals(profile).map((signal) => ({
      ...signal,
      profileLabel: profile.profile_label
    }))
  );
  if (signals.length === 0) {
    return null;
  }
  return (
    <div className="riskSignals" aria-label="Harness risk preflight signals">
      {signals.slice(0, 4).map((signal) => (
        <span key={`${signal.profileLabel}-${signal.kind}`}>
          {signal.profileLabel} {signal.label} {signal.count}
        </span>
      ))}
    </div>
  );
}

function extractRiskSignals(profile: ProfileAnalysis) {
  const decisions = flattenDecisions(profile.harness_decisions ?? []);
  const counters = new Map<string, { label: string; count: number }>();
  decisions.forEach((decision) => {
    const reason = decision.reason ?? {};
    addSignal(counters, "missing_context", "missing", countItems(reason.missing_context));
    addSignal(counters, "scanner_coverage_gaps", "coverage", countItems(reason.scanner_coverage_gaps));
    addSignal(counters, "scanner_findings", "scanner", countItems(reason.scanner_findings));
    addSignal(counters, "similarity_matches", "similarity", countItems(reason.similarity_matches));
    addSignal(counters, "claim_gaps", "claims", countItems(reason.claim_gaps));
    addSignal(counters, "offer_disclosure_gaps", "offers", countItems(reason.offer_disclosure_gaps));
    addSignal(counters, "provenance_gaps", "provenance", countItems(reason.provenance_gaps));
    addSignal(counters, "provenance_findings", "prov findings", countItems(reason.provenance_findings));
    addSignal(counters, "rollback_constraints", "rollback", countItems(reason.rollback_constraints));
  });
  return Array.from(counters, ([kind, value]) => ({ kind, ...value })).filter(
    (signal) => signal.count > 0
  );
}

function flattenDecisions(decisions: HarnessDecisionTrace[]): HarnessDecisionTrace[] {
  return decisions.flatMap((decision) => [
    decision,
    ...flattenDecisions(decision.contributing_decisions ?? [])
  ]);
}

function addSignal(
  counters: Map<string, { label: string; count: number }>,
  key: string,
  label: string,
  count: number
) {
  if (count <= 0) {
    return;
  }
  const current = counters.get(key);
  counters.set(key, { label, count: (current?.count ?? 0) + count });
}

function countItems(value: unknown) {
  if (Array.isArray(value)) {
    return value.length;
  }
  return value ? 1 : 0;
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

