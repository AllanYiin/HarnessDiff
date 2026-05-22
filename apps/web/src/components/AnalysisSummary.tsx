type AnalysisSummaryProps = {
  turnCount: number;
  inputMode: string;
  running: boolean;
};

export function AnalysisSummary({ turnCount, inputMode, running }: AnalysisSummaryProps) {
  return (
    <aside className="analysisSummary" aria-label="Current comparison summary">
      <strong>{running ? "正在比較左右輸出" : turnCount === 0 ? "準備開始第一回合" : "本回合已收斂"}</strong>
      <span>
        {turnCount === 0
          ? "第一回合預設一鍵雙送；完成後會切換為個別輸入。"
          : `目前是 ${inputMode === "integrated" ? "整合輸入" : "個別輸入"}。詳細分析會在後續階段展開。`}
      </span>
    </aside>
  );
}

