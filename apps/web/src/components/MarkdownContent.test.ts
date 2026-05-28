import { describe, expect, it } from "vitest";

import { splitRequestedSkillDetails } from "./MarkdownContent";

describe("MarkdownContent skill disclosure parsing", () => {
  it("splits requested skill details into a dedicated disclosure part", () => {
    const parts = splitRequestedSkillDetails(
      [
        "Use this skill.",
        "---",
        "Requested skill details:",
        "### Requested skill 1: skill-creator",
        "```markdown",
        "# Skill",
        "`\u200b``escaped`\u200b``",
        "```",
        "---"
      ].join("\n")
    );

    expect(parts).toEqual([
      { type: "markdown", source: "Use this skill." },
      {
        type: "skillDetails",
        details: [
          {
            id: "skill-creator",
            content: "# Skill\n`\u200b``escaped`\u200b``"
          }
        ]
      }
    ]);
  });
});
