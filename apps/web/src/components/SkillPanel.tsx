import { Bot, FileArchive, FolderUp, Plus, Trash2, Upload, Wrench } from "lucide-react";
import type { FormEvent, KeyboardEvent } from "react";
import { useRef, useState } from "react";

import type { SubagentCreatePayload, SubagentSummary, SkillSummary, ToolSummary } from "../api";

type SkillPanelProps = {
  homeDir: string;
  skillsDir: string;
  skills: SkillSummary[];
  loading: boolean;
  importing: boolean;
  selectedSkillId: string;
  selectedSkillContent: string;
  agentsDir: string;
  subagents: SubagentSummary[];
  subagentsLoading: boolean;
  creatingSubagent: boolean;
  tools: ToolSummary[];
  toolsLoading: boolean;
  error: string;
  onImportFile: (file: File | null) => void;
  onImportFolder: (files: FileList | null) => void;
  onSelectSkill: (skillId: string) => void;
  onToggleSkill: (skillId: string, enabled: boolean) => void;
  onDeleteSkill: (skillId: string) => void;
  onToggleSubagent: (subagentId: string, enabled: boolean) => void;
  onDeleteSubagent: (subagentId: string) => void;
  onToggleTool: (toolId: string, enabled: boolean) => void;
  onDeleteTool: (toolId: string) => void;
  onCreateSubagent: (payload: SubagentCreatePayload) => Promise<void>;
};

type SkillPanelTab = "skills" | "subagents" | "tools";

const panelTabs: Array<{ id: SkillPanelTab; label: string }> = [
  { id: "skills", label: "技能" },
  { id: "subagents", label: "Subagents" },
  { id: "tools", label: "工具" }
];

export function SkillPanel({
  homeDir,
  skillsDir,
  skills,
  loading,
  importing,
  selectedSkillId,
  selectedSkillContent,
  agentsDir,
  subagents,
  subagentsLoading,
  creatingSubagent,
  tools,
  toolsLoading,
  error,
  onImportFile,
  onImportFolder,
  onSelectSkill,
  onToggleSkill,
  onDeleteSkill,
  onToggleSubagent,
  onDeleteSubagent,
  onToggleTool,
  onDeleteTool,
  onCreateSubagent
}: SkillPanelProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [activeTab, setActiveTab] = useState<SkillPanelTab>("skills");
  const [formOpen, setFormOpen] = useState(false);
  const [subagentForm, setSubagentForm] = useState({
    id: "",
    label: "",
    description: "",
    instructions: "",
    model: "gpt-5.4-mini",
    reasoning_effort: "low",
    max_output_chars: "4000"
  });

  async function submitSubagentForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = subagentForm.id.trim();
    const label = subagentForm.label.trim();
    const instructions = subagentForm.instructions.trim();
    if (!id || !label || !instructions) {
      return;
    }
    try {
      await onCreateSubagent({
        id,
        label,
        description: subagentForm.description.trim(),
        instructions,
        model: subagentForm.model.trim() || "gpt-5.4-mini",
        reasoning_effort: subagentForm.reasoning_effort,
        max_output_chars: Number(subagentForm.max_output_chars) || 4000,
        enabled: true
      });
    } catch {
      return;
    }
    setSubagentForm({
      id: "",
      label: "",
      description: "",
      instructions: "",
      model: "gpt-5.4-mini",
      reasoning_effort: "low",
      max_output_chars: "4000"
    });
    setFormOpen(false);
  }

  function moveTabFocus(event: KeyboardEvent<HTMLButtonElement>, tabId: SkillPanelTab) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const currentIndex = panelTabs.findIndex((tab) => tab.id === tabId);
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? panelTabs.length - 1
          : event.key === "ArrowRight"
            ? (currentIndex + 1) % panelTabs.length
            : (currentIndex - 1 + panelTabs.length) % panelTabs.length;
    setActiveTab(panelTabs[nextIndex].id);
  }

  const activePath =
    activeTab === "skills"
      ? skillsDir || homeDir
      : activeTab === "subagents"
        ? agentsDir || "agents"
        : "HarnessDiff runtime tools";
  const activeTitle =
    activeTab === "skills" ? "技能" : activeTab === "subagents" ? "Subagents" : "工具";

  return (
    <aside className="skillPanel" aria-label="技能管理">
      <header className="skillPanelHeader">
        <div>
          <strong>{activeTitle}</strong>
          <span>{activePath}</span>
        </div>
        {activeTab === "skills" ? (
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
        ) : activeTab === "subagents" ? (
          <button
            className="iconButton"
            type="button"
            aria-label="新增 Subagent"
            aria-expanded={formOpen}
            onClick={() => setFormOpen((current) => !current)}
          >
            <Plus aria-hidden="true" size={16} />
          </button>
        ) : null}
      </header>
      {error ? <p className="panelError">{error}</p> : null}
      <div className="skillTabs" role="tablist" aria-label="技能與 Subagents">
        {panelTabs.map((tab) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`skill-panel-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`skill-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              className="skillTab"
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => moveTabFocus(event, tab.id)}
            >
              <span>{tab.label}</span>
              <strong>
                {tab.id === "skills"
                  ? skills.length
                  : tab.id === "subagents"
                    ? subagents.length
                    : tools.length}
              </strong>
            </button>
          );
        })}
      </div>
      <div className="skillPanelBody">
        <section
          id="skill-panel-skills"
          className="skillTabPanel"
          role="tabpanel"
          aria-labelledby="skill-panel-tab-skills"
          hidden={activeTab !== "skills"}
        >
          {loading ? <p className="panelMuted">載入中</p> : null}
          {skills.length ? (
            <div className="skillList">
              {skills.map((skill) => (
                <div
                  className={`skillItem ${selectedSkillId === skill.id ? "selected" : ""} ${
                    skill.enabled ? "" : "disabledSkill"
                  }`}
                  key={skill.id}
                >
                  <button
                    className="skillSelectButton"
                    type="button"
                    onClick={() => onSelectSkill(skill.id)}
                  >
                    <span className="skillItemTitle">
                      <strong>{skill.name}</strong>
                      <small>{skill.enabled ? "啟用中" : "已停用"}</small>
                    </span>
                    <span>{skill.description || "沒有描述"}</span>
                  </button>
                  <div className="skillRowActions">
                    <button
                      className="skillSwitch"
                      type="button"
                      role="switch"
                      aria-checked={skill.enabled ? "true" : "false"}
                      aria-label={`${skill.enabled ? "停用" : "啟用"} ${skill.name}`}
                      disabled={!skill.can_toggle}
                      onClick={() => onToggleSkill(skill.id, !skill.enabled)}
                    >
                      <span aria-hidden="true" />
                    </button>
                    <button
                      className="iconButton dangerIconButton"
                      type="button"
                      aria-label={`刪除 ${skill.name}`}
                      title={skill.can_delete ? "刪除技能" : "只能刪除匯入到 HarnessDiff skills 目錄的技能"}
                      disabled={!skill.can_delete}
                      onClick={() => {
                        if (window.confirm(`確定要刪除「${skill.name}」嗎？`)) {
                          onDeleteSkill(skill.id);
                        }
                      }}
                    >
                      <Trash2 aria-hidden="true" size={15} />
                    </button>
                  </div>
                </div>
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
        </section>
        <section
          id="skill-panel-subagents"
          className="skillTabPanel"
          role="tabpanel"
          aria-labelledby="skill-panel-tab-subagents"
          hidden={activeTab !== "subagents"}
        >
          {subagentsLoading ? <p className="panelMuted">載入中</p> : null}
          {subagents.length ? (
            <div className="subagentList">
              {subagents.map((subagent) => (
                <div
                  className={`subagentItem ${subagent.enabled ? "" : "disabledSkill"}`}
                  key={subagent.id}
                >
                  <Wrench aria-hidden="true" size={16} />
                  <div className="managedItemBody">
                    <span className="skillItemTitle">
                      <strong>{subagent.label}</strong>
                      <small>{subagent.enabled ? "啟用中" : "已停用"}</small>
                    </span>
                    <span>{subagent.id}</span>
                    {subagent.description ? <p>{subagent.description}</p> : null}
                  </div>
                  <div className="skillRowActions">
                    <button
                      className="skillSwitch"
                      type="button"
                      role="switch"
                      aria-checked={subagent.enabled ? "true" : "false"}
                      aria-label={`${subagent.enabled ? "停用" : "啟用"} ${subagent.label}`}
                      disabled={!subagent.can_toggle}
                      onClick={() => onToggleSubagent(subagent.id, !subagent.enabled)}
                    >
                      <span aria-hidden="true" />
                    </button>
                    <button
                      className="iconButton dangerIconButton"
                      type="button"
                      aria-label={`刪除 ${subagent.label}`}
                      disabled={!subagent.can_delete}
                      onClick={() => {
                        if (window.confirm(`確定要刪除「${subagent.label}」嗎？`)) {
                          onDeleteSubagent(subagent.id);
                        }
                      }}
                    >
                      <Trash2 aria-hidden="true" size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="emptySkillState">
              <Wrench aria-hidden="true" size={18} />
              <span>尚未建立 Subagent</span>
            </div>
          )}
          {formOpen ? (
            <form className="subagentForm" onSubmit={(event) => void submitSubagentForm(event)}>
              <div className="subagentFormGrid">
                <label>
                  <span>ID</span>
                  <input
                    value={subagentForm.id}
                    onChange={(event) =>
                      setSubagentForm((current) => ({ ...current, id: event.target.value }))
                    }
                    placeholder="fact_checker"
                    required
                  />
                </label>
                <label>
                  <span>名稱</span>
                  <input
                    value={subagentForm.label}
                    onChange={(event) =>
                      setSubagentForm((current) => ({ ...current, label: event.target.value }))
                    }
                    placeholder="Fact Checker"
                    required
                  />
                </label>
                <label>
                  <span>模型</span>
                  <input
                    value={subagentForm.model}
                    onChange={(event) =>
                      setSubagentForm((current) => ({ ...current, model: event.target.value }))
                    }
                  />
                </label>
                <label>
                  <span>思考強度</span>
                  <select
                    value={subagentForm.reasoning_effort}
                    onChange={(event) =>
                      setSubagentForm((current) => ({
                        ...current,
                        reasoning_effort: event.target.value
                      }))
                    }
                  >
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                    <option value="xhigh">xhigh</option>
                  </select>
                </label>
              </div>
              <label>
                <span>描述</span>
                <input
                  value={subagentForm.description}
                  onChange={(event) =>
                    setSubagentForm((current) => ({
                      ...current,
                      description: event.target.value
                    }))
                  }
                  placeholder="Check claims against provided evidence."
                />
              </label>
              <label>
                <span>Instructions</span>
                <textarea
                  value={subagentForm.instructions}
                  onChange={(event) =>
                    setSubagentForm((current) => ({
                      ...current,
                      instructions: event.target.value
                    }))
                  }
                  rows={5}
                  required
                />
              </label>
              <label>
                <span>最大輸出字元</span>
                <input
                  type="number"
                  min={256}
                  max={20000}
                  value={subagentForm.max_output_chars}
                  onChange={(event) =>
                    setSubagentForm((current) => ({
                      ...current,
                      max_output_chars: event.target.value
                    }))
                  }
                />
              </label>
              <button className="textButton" type="submit" disabled={creatingSubagent}>
                <Plus aria-hidden="true" size={16} />
                建立 Subagent
              </button>
            </form>
          ) : null}
        </section>
        <section
          id="skill-panel-tools"
          className="skillTabPanel"
          role="tabpanel"
          aria-labelledby="skill-panel-tab-tools"
          hidden={activeTab !== "tools"}
        >
          {toolsLoading ? <p className="panelMuted">載入中</p> : null}
          {tools.length ? (
            <div className="subagentList">
              {tools.map((tool) => (
                <div
                  className={`subagentItem ${tool.enabled ? "" : "disabledSkill"}`}
                  key={tool.id}
                >
                  <Bot aria-hidden="true" size={16} />
                  <div className="managedItemBody">
                    <span className="skillItemTitle">
                      <strong>{tool.name}</strong>
                      <small>{tool.enabled ? "啟用中" : "已停用"}</small>
                    </span>
                    <span>{tool.id}</span>
                    {tool.description ? <p>{tool.description}</p> : null}
                  </div>
                  <div className="skillRowActions">
                    <button
                      className="skillSwitch"
                      type="button"
                      role="switch"
                      aria-checked={tool.enabled ? "true" : "false"}
                      aria-label={`${tool.enabled ? "停用" : "啟用"} ${tool.name}`}
                      disabled={!tool.can_toggle}
                      onClick={() => onToggleTool(tool.id, !tool.enabled)}
                    >
                      <span aria-hidden="true" />
                    </button>
                    <button
                      className="iconButton dangerIconButton"
                      type="button"
                      aria-label={`刪除 ${tool.name}`}
                      disabled={!tool.can_delete}
                      onClick={() => {
                        if (window.confirm(`確定要刪除「${tool.name}」嗎？`)) {
                          onDeleteTool(tool.id);
                        }
                      }}
                    >
                      <Trash2 aria-hidden="true" size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="emptySkillState">
              <Bot aria-hidden="true" size={18} />
              <span>尚無工具</span>
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}
