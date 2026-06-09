import { AgentPane } from "./AgentPane";
import type { AnalysisDocument, SkillSummary, ToolSummary } from "../api";
import type { AgentStepTrace, ProfileId, ProfileInstance, ProfileState } from "../types";

type AgentWorkspaceProps = {
  profiles: ProfileInstance[];
  profileState: Record<ProfileId, ProfileState>;
  steps: Record<ProfileId, AgentStepTrace[]>;
  analysis: AnalysisDocument | null;
  skills: SkillSummary[];
  tools: ToolSummary[];
  model: string;
};

export function AgentWorkspace({
  profiles,
  profileState,
  steps,
  analysis,
  skills,
  tools,
  model
}: AgentWorkspaceProps) {
  return (
    <section className="workspace agentWorkspace" aria-label="HarnessDiff agent comparison">
      {profiles.map((profile) => (
        <AgentPane
          key={profile.id}
          profile={profile}
          messages={profileState[profile.id]?.messages ?? []}
          steps={steps[profile.id] ?? []}
          streaming={profileState[profile.id]?.streaming ?? false}
          analysis={analysis?.profiles[profile.id]}
          skills={skills}
          tools={tools}
          model={model}
        />
      ))}
    </section>
  );
}
