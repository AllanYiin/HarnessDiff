import { afterEach, describe, expect, it, vi } from "vitest";

import { createProject, createRun, getProjectTranscript, listProjects } from "./api";

function mockJsonResponse(body: unknown, ok = true, status = 200) {
  const response = {
    ok,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
    body: null
  } as Response;
  return {
    ...response,
    clone: () => response
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

  it("surfaces backend error detail when creating a run fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(mockJsonResponse({ detail: "ToolAnything import failed" }, false, 500))
    );

    await expect(
      createRun({
        projectId: "proj_mock",
        prompt: "hello",
        inputMode: "integrated",
        model: "fake-model",
        reasoningEffort: "medium",
        profiles: [{ id: "harness", label: "Harness", harness_modules: {} }]
      })
    ).rejects.toThrow("建立 run 失敗：HTTP 500 - ToolAnything import failed");
  });

  it("normalizes transcript profiles and drops malformed runs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockJsonResponse({
          project: { id: "proj_history", name: "History" },
          runs: [
            {
              id: "run_1",
              prompt: "hello",
              input_mode: "independent",
              status: "completed",
              profiles: [
                { id: "baseline", label: "NoHarness", harness_modules: {}, output_text: "baseline" },
                {
                  id: "controlled",
                  label: "Controlled",
                  harness_modules: { context_manifest: true, guardrails: true },
                  output_text: "controlled"
                }
              ]
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
          profiles: [
            { id: "baseline", label: "NoHarness", output_text: "baseline" },
            {
              id: "controlled",
              label: "Controlled",
              harness_modules: { context_summary: true, guardrails: true },
              output_text: "controlled"
            }
          ]
        }
      ]
    });
  });
});
