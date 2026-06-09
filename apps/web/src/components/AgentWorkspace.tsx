import { AgentPane } from "./AgentPane";
import type { AnalysisDocument, SkillSummary, ToolSummary } from "../api";
import type { AgentStepTrace, ProfileId, ProfileInstance, ProfileState } from "../types";
import type { ReactNode } from "react";

type AgentWorkspaceProps = {
  profiles: ProfileInstance[];
  profileState: Record<ProfileId, ProfileState>;
  steps: Record<ProfileId, AgentStepTrace[]>;
  analysis: AnalysisDocument | null;
  skills: SkillSummary[];
  tools: ToolSummary[];
  model: string;
  renderArtifactLayer?: (profile: ProfileInstance) => ReactNode;
};

export function AgentWorkspace({
  profiles,
  profileState,
  steps,
  analysis,
  skills,
  tools,
  model,
  renderArtifactLayer
}: AgentWorkspaceProps) {
  return (
    <section className="workspace agentWorkspace" aria-label="HarnessDiff agent comparison">
      {profiles.map((profile) => (
        <div className="profileWorkColumn" key={profile.id}>
          <AgentPane
            profile={profile}
            messages={profileState[profile.id]?.messages ?? []}
            steps={steps[profile.id] ?? []}
            streaming={profileState[profile.id]?.streaming ?? false}
            analysis={analysis?.profiles[profile.id]}
            skills={skills}
            tools={tools}
            model={model}
          />
          {renderArtifactLayer?.(profile)}
        </div>
      ))}
    </section>
  );
}
