import { AgentPane } from "./AgentPane";
import type { AgentStepTrace, ProfileId, ProfileInstance, ProfileState } from "../types";

type AgentWorkspaceProps = {
  profiles: ProfileInstance[];
  profileState: Record<ProfileId, ProfileState>;
  steps: Record<ProfileId, AgentStepTrace[]>;
};

export function AgentWorkspace({ profiles, profileState, steps }: AgentWorkspaceProps) {
  return (
    <section className="workspace agentWorkspace" aria-label="HarnessDiff agent comparison">
      {profiles.map((profile) => (
        <AgentPane
          key={profile.id}
          profile={profile}
          messages={profileState[profile.id]?.messages ?? []}
          steps={steps[profile.id] ?? []}
          streaming={profileState[profile.id]?.streaming ?? false}
        />
      ))}
    </section>
  );
}
