import { afterEach, describe, expect, it, vi } from "vitest";

import { createProject, getProjectTranscript, listProjects } from "./api";

function mockJsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: () => Promise.resolve(body),
    body: null
  } as Response;
}

describe("api response normalization", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("falls back to an empty project list for unexpected list responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockJsonResponse({ id: "proj_mock" })));

    await expect(listProjects()).resolves.toEqual([]);
  });

  it("fills missing project metadata from the caller context", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockJsonResponse({ id: "proj_mock" }, true, 201)));

    await expect(createProject("First prompt")).resolves.toMatchObject({
      id: "proj_mock",
      name: "First prompt"
    });
  });

  it("normalizes transcript panes and drops malformed runs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockJsonResponse({
          project: { id: "proj_history", name: "History" },
          runs: [
            {
              id: "run_1",
              prompt: "hello",
              target_panes: ["NoHarness", "BadPane", "Harness"],
              input_mode: "independent",
              status: "completed",
              panes: {
                NoHarness: { output_text: "baseline" },
                Harness: { output_text: "controlled" }
              }
            },
            { id: "run_bad" }
          ]
        })
      )
    );

    await expect(getProjectTranscript("proj_history")).resolves.toMatchObject({
      project: { id: "proj_history", name: "History" },
      runs: [
        {
          id: "run_1",
          target_panes: ["NoHarness", "Harness"],
          panes: {
            NoHarness: { output_text: "baseline" },
            Harness: { output_text: "controlled" }
          }
        }
      ]
    });
  });
});
