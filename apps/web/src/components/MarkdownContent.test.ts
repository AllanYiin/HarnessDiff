// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import mermaid from "mermaid";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarkdownContent, splitRequestedSkillDetails } from "./MarkdownContent";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({
      svg: '<svg role="img" aria-label="Rendered test diagram"><text>diagram</text></svg>'
    }))
  }
}));

describe("MarkdownContent skill disclosure parsing", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

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

  it("renders mermaid code fences as diagram previews", async () => {
    render(
      createElement(MarkdownContent, {
        source: [
          "```mermaid",
          "flowchart LR",
          "  A[Start] --> B[Done]",
          "```"
        ].join("\n")
      })
    );

    await screen.findByLabelText("Mermaid diagram preview");
    expect(mermaid.initialize).toHaveBeenCalledWith({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "default"
    });
    await waitFor(() => {
      expect(mermaid.render).toHaveBeenCalledWith(
        expect.stringMatching(/^mermaid-/),
        "flowchart LR\n  A[Start] --> B[Done]"
      );
    });
  });

  it("renders svg code fences as sandboxed previews", () => {
    render(
      createElement(MarkdownContent, {
        source: [
          "```svg",
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">',
          '<circle cx="5" cy="5" r="4" />',
          "</svg>",
          "```"
        ].join("\n")
      })
    );

    const frame = screen.getByTitle("SVG code preview");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("srcdoc")).toContain("<svg");
  });

  it("renders unlabeled svg fences as sandboxed previews", () => {
    render(
      createElement(MarkdownContent, {
        source: [
          "```",
          '<?xml version="1.0" encoding="UTF-8"?>',
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>',
          "```"
        ].join("\n")
      })
    );

    const frame = screen.getByTitle("SVG code preview");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("srcdoc")).toContain("<svg");
    expect(frame.getAttribute("srcdoc")).not.toContain("<?xml");
  });

  it("previews streaming svg fences after the svg root tag closes", () => {
    const { rerender } = render(
      createElement(MarkdownContent, {
        source: ["```svg", '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"'].join(
          "\n"
        )
      })
    );

    expect(screen.queryByTitle("SVG code preview")).toBeNull();
    expect(screen.getByText(/<svg xmlns=/)).toBeTruthy();

    rerender(
      createElement(MarkdownContent, {
        source: [
          "```svg",
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">',
          '<circle cx="5" cy="5" r="4" />'
        ].join("\n")
      })
    );

    const frame = screen.getByTitle("SVG code preview");
    expect(frame.getAttribute("srcdoc")).toContain("<circle");
    expect(frame.getAttribute("srcdoc")).toContain("</svg>");
  });

  it("remounts the svg preview frame when streaming updates the svg body", () => {
    const { rerender } = render(
      createElement(MarkdownContent, {
        source: [
          "```svg",
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">',
          '<circle cx="5" cy="5" r="4" />',
          "</svg>"
        ].join("\n")
      })
    );
    const firstFrame = screen.getByTitle("SVG code preview");

    rerender(
      createElement(MarkdownContent, {
        source: [
          "```svg",
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">',
          '<rect width="10" height="10" />',
          "</svg>"
        ].join("\n")
      })
    );

    const updatedFrame = screen.getByTitle("SVG code preview");
    expect(updatedFrame).not.toBe(firstFrame);
    expect(updatedFrame.getAttribute("srcdoc")).toContain("<rect");
  });

  it("keeps completed streaming shapes visible while the next svg tag is incomplete", () => {
    render(
      createElement(MarkdownContent, {
        source: [
          "```svg",
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">',
          '<circle cx="5" cy="5" r="4" />',
          '<rect width="'
        ].join("\n")
      })
    );

    const frame = screen.getByTitle("SVG code preview");
    expect(frame.getAttribute("srcdoc")).toContain("<circle");
    expect(frame.getAttribute("srcdoc")).not.toContain("<rect");
    expect(frame.getAttribute("srcdoc")).toContain("</svg>");
  });
});
