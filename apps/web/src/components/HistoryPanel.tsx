import type { ProjectSummary } from "../api";

type HistoryPanelProps = {
  projects: ProjectSummary[];
  activeProjectId: string | null;
  loading: boolean;
  onSelectProject: (projectId: string) => void;
};

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function HistoryPanel({
  projects,
  activeProjectId,
  loading,
  onSelectProject
}: HistoryPanelProps) {
  return (
    <aside className="historyPanel" aria-label="歷史對話紀錄">
      <div className="historyHeader">
        <strong>歷史對話</strong>
        <span>{loading ? "載入中" : `${projects.length} 筆`}</span>
      </div>
      <div className="historyList">
        {projects.length === 0 ? (
          <div className="historyEmpty">尚無歷史紀錄</div>
        ) : (
          projects.map((project) => (
            <button
              className={`historyItem ${project.id === activeProjectId ? "selected" : ""}`}
              key={project.id}
              onClick={() => onSelectProject(project.id)}
              type="button"
            >
              <span>{project.name}</span>
              <time dateTime={project.updated_at}>{formatTime(project.updated_at)}</time>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
