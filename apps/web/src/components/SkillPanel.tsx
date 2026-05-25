import { FileArchive, FolderUp, Upload } from "lucide-react";
import { useRef } from "react";

import type { SkillSummary } from "../api";

type SkillPanelProps = {
  homeDir: string;
  skillsDir: string;
  skills: SkillSummary[];
  loading: boolean;
  importing: boolean;
  selectedSkillId: string;
  selectedSkillContent: string;
  error: string;
  onImportFile: (file: File | null) => void;
  onImportFolder: (files: FileList | null) => void;
  onSelectSkill: (skillId: string) => void;
};

export function SkillPanel({
  homeDir,
  skillsDir,
  skills,
  loading,
  importing,
  selectedSkillId,
  selectedSkillContent,
  error,
  onImportFile,
  onImportFolder,
  onSelectSkill
}: SkillPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  return (
    <aside className="skillPanel" aria-label="技能管理">
      <header className="skillPanelHeader">
        <div>
          <strong>技能</strong>
          <span>{skillsDir || homeDir}</span>
        </div>
        <div className="skillActions">
          <button
            className="textButton"
            type="button"
            disabled={importing}
            onClick={() => fileInputRef.current?.click()}
          >
            <FileArchive aria-hidden="true" size={16} />
            匯入檔案
          </button>
          <button
            className="textButton"
            type="button"
            disabled={importing}
            onClick={() => folderInputRef.current?.click()}
          >
            <FolderUp aria-hidden="true" size={16} />
            匯入資料夾
          </button>
          <input
            ref={fileInputRef}
            hidden
            type="file"
            accept=".zip,.skill,.md"
            onChange={(event) => {
              onImportFile(event.target.files?.[0] ?? null);
              event.target.value = "";
            }}
          />
          <input
            ref={folderInputRef}
            hidden
            type="file"
            multiple
            webkitdirectory=""
            directory=""
            onChange={(event) => {
              onImportFolder(event.target.files);
              event.target.value = "";
            }}
          />
        </div>
      </header>
      {error ? <p className="panelError">{error}</p> : null}
      {loading ? <p className="panelMuted">載入中</p> : null}
      {skills.length ? (
        <div className="skillList">
          {skills.map((skill) => (
            <button
              className={`skillItem ${selectedSkillId === skill.id ? "selected" : ""}`}
              key={skill.id}
              type="button"
              onClick={() => onSelectSkill(skill.id)}
            >
              <strong>{skill.name}</strong>
              <span>{skill.description || "沒有描述"}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="emptySkillState">
          <Upload aria-hidden="true" size={18} />
          <span>尚未匯入技能</span>
        </div>
      )}
      {selectedSkillContent ? (
        <section className="skillDetail" aria-label="完整 SKILL.md">
          <strong>SKILL.md</strong>
          <pre>{selectedSkillContent}</pre>
        </section>
      ) : null}
    </aside>
  );
}

