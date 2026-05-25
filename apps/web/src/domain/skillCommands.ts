import type { SkillDetail, SkillSummary } from "../api";

export function parseSkillCommandIds(text: string, skills: SkillSummary[]): string[] {
  const aliases = new Map<string, string>();
  skills.forEach((skill) => {
    aliases.set(skill.id.toLowerCase(), skill.id);
    aliases.set(skill.name.toLowerCase(), skill.id);
  });
  const found: string[] = [];
  const seen = new Set<string>();
  for (const match of text.matchAll(/(?:^|\s)\/([A-Za-z0-9_.-]+)/g)) {
    const skillId = aliases.get(match[1].toLowerCase());
    if (skillId && !seen.has(skillId)) {
      found.push(skillId);
      seen.add(skillId);
    }
  }
  return found;
}

export function skillDetailsPromptBlock(details: SkillDetail[]): string {
  if (!details.length) {
    return "";
  }
  const blocks = details.map((detail, index) =>
    [
      `### Requested skill ${index + 1}: ${detail.id}`,
      "```markdown",
      detail.content.replaceAll("```", "`\u200b``"),
      "```"
    ].join("\n")
  );
  return ["", "---", "Requested skill details:", ...blocks, "---"].join("\n");
}

