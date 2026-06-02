import { describe, expect, it } from "vitest";

import type { SkillDetail, SkillSummary } from "../api";
import { parseSkillCommandIds, skillDetailsPromptBlock } from "./skillCommands";

const skills: SkillSummary[] = [
  {
    id: "longdoc-evidence-reader",
    name: "longdoc-evidence-reader",
    description: "Read long docs",
    version: "",
    enabled: true,
    can_toggle: true,
    can_delete: false,
    path: ""
  },
  {
    id: "skill-creator",
    name: "Skill Creator",
    description: "Create skills",
    version: "",
    enabled: true,
    can_toggle: true,
    can_delete: false,
    path: ""
  }
];

describe("skill slash commands", () => {
  it("extracts installed skill ids from slash commands", () => {
    expect(
      parseSkillCommandIds(
        "/longdoc-evidence-reader summarize this with /Skill-Creator and /missing",
        skills
      )
    ).toEqual(["longdoc-evidence-reader", "skill-creator"]);
  });

  it("deduplicates repeated skill commands", () => {
    expect(parseSkillCommandIds("/skill-creator /Skill-Creator", skills)).toEqual([
      "skill-creator"
    ]);
  });

  it("ignores disabled skills in slash commands", () => {
    expect(
      parseSkillCommandIds("/skill-creator", [
        { ...skills[1], enabled: false }
      ])
    ).toEqual([]);
  });

  it("formats full skill content as deferred prompt context", () => {
    const details: SkillDetail[] = [
      { id: "skill-creator", path: "/tmp/SKILL.md", content: "# Skill\n```bad```" }
    ];

    const block = skillDetailsPromptBlock(details);

    expect(block).toContain("Requested skill details");
    expect(block).toContain("Requested skill 1: skill-creator");
    expect(block).toContain("`\u200b``bad`\u200b``");
  });
});
