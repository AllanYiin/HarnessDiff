import type { AnalysisDocument, PaneAnalysis } from "../api";

type AnalysisSummaryProps = {
  turnCount: number;
  inputMode: string;
  running: boolean;
  analysis: AnalysisDocument | null;
};

export function AnalysisSummary({ turnCount, inputMode, running, analysis }: AnalysisSummaryProps) {
  const noHarness = analysis?.panes.NoHarness;
  const harness = analysis?.panes.Harness;
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
      : "若後端未啟動，畫面會使用 mock streaming，不會產生 token 分析。";

  return (
    <aside className="analysisSummary" aria-label="Current comparison summary">
      <div className="analysisLead">
        <strong>{headline}</strong>
        <span>{summary}</span>
      </div>
      {analysis ? (
        <div className="analysisMetrics" aria-label="Token and context metrics">
          <Metric label="NoHarness" pane={noHarness} />
          <Metric label="Harness" pane={harness} />
          <span>
            Context {contextCount(harness)}/{contextCount(noHarness)}
          </span>
          <span>Turn {analysis.turn_index + 1}</span>
        </div>
      ) : null}
    </aside>
  );
}

function Metric({ label, pane }: { label: string; pane?: PaneAnalysis }) {
  return (
    <span>
      {label} {pane ? pane.current_turn_usage.total_tokens : 0} /{" "}
      {pane ? pane.cumulative_usage.total_tokens : 0}
    </span>
  );
}

function contextCount(pane?: PaneAnalysis) {
  return pane?.context_sections.filter((section) => section.status === "sent").length ?? 0;
}

function formatSigned(value: number) {
  if (value > 0) {
    return `+${value}`;
  }
  return `${value}`;
}
