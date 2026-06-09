import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createProject,
  createArtifact,
  createRun,
  createSubagent,
  getProjectTranscript,
  listArtifacts,
  listProjects,
  listSubagents,
  patchArtifact,
  transcribeAudio
} from "./api";

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
      name: "First prompt",
      surface_type: "chat"
    });
  });

  it("sends surface type when creating an agent project", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockJsonResponse({ id: "proj_agent", name: "Agent", surface_type: "agent" }, true, 201)
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(createProject("Agent", "agent")).resolves.toMatchObject({
      id: "proj_agent",
      surface_type: "agent"
    });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      name: "Agent",
      surface_type: "agent"
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

  it("sends image attachments when creating a run", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ id: "run_mock" }, true, 201));
    vi.stubGlobal("fetch", fetchMock);

    await createRun({
      projectId: "proj_mock",
      prompt: "describe",
      inputMode: "integrated",
      model: "fake-model",
      reasoningEffort: "medium",
      profiles: [{ id: "harness", label: "Harness", harness_modules: {} }],
      attachments: [
        {
          kind: "image",
          name: "screen.png",
          mime_type: "image/png",
          size_bytes: 12,
          image_url: "data:image/png;base64,abc",
          detail: "auto"
        }
      ]
    });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.attachments).toEqual([
      {
        kind: "image",
        name: "screen.png",
        mime_type: "image/png",
        size_bytes: 12,
        image_url: "data:image/png;base64,abc",
        detail: "auto"
      }
    ]);
  });

  it("sends artifact refs when creating a run", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ id: "run_mock" }, true, 201));
    vi.stubGlobal("fetch", fetchMock);

    await createRun({
      projectId: "proj_mock",
      prompt: "revise canvas",
      inputMode: "independent",
      model: "fake-model",
      reasoningEffort: "medium",
      profiles: [{ id: "baseline", label: "NoHarness", harness_modules: {} }],
      artifactRefs: [
        {
          artifact_id: "art_1",
          profile_id: "baseline",
          version: 2,
          include_mode: "full"
        }
      ]
    });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.artifact_refs).toEqual([
      {
        artifact_id: "art_1",
        profile_id: "baseline",
        version: 2,
        include_mode: "full"
      }
    ]);
  });

  it("uses project-local artifact endpoints", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockJsonResponse({ artifacts: [{ id: "art_1" }] }))
      .mockResolvedValueOnce(mockJsonResponse({ id: "art_2" }, true, 201))
      .mockResolvedValueOnce(mockJsonResponse({ id: "art_2", version: 2 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listArtifacts("proj_mock", "baseline")).resolves.toEqual([{ id: "art_1" }]);
    await expect(
      createArtifact("proj_mock", {
        profile_id: "baseline",
        kind: "plain_text",
        title: "Note",
        content: "hello"
      })
    ).resolves.toMatchObject({ id: "art_2" });
    await expect(
      patchArtifact("proj_mock", "art_2", {
        base_version: 1,
        content: "updated"
      })
    ).resolves.toMatchObject({ version: 2 });

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/proj_mock/artifacts?profile_id=baseline");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/projects/proj_mock/artifacts",
      expect.objectContaining({ method: "POST" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/projects/proj_mock/artifacts/art_2",
      expect.objectContaining({ method: "PATCH" })
    );
  });

  it("posts recorded audio to the transcription endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ text: "語音內容" }));
    vi.stubGlobal("fetch", fetchMock);
    const audio = new Blob(["audio"], { type: "audio/webm" });

    await expect(transcribeAudio(audio)).resolves.toBe("語音內容");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/audio/transcriptions",
      expect.objectContaining({
        method: "POST",
        body: audio,
        headers: {
          "Content-Type": "audio/webm",
          "X-Audio-Filename": "voice-input.webm"
        }
      })
    );
  });

  it("normalizes transcript profiles and drops malformed runs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockJsonResponse({
          project: { id: "proj_history", name: "History", surface_type: "agent" },
          runs: [
            {
              id: "run_1",
              prompt: "hello",
              input_mode: "independent",
              status: "completed",
              attachments: [
                {
                  kind: "image",
                  name: "screen.png",
                  mime_type: "image/png",
                  size_bytes: 12,
                  image_url: "data:image/png;base64,abc",
                  detail: "auto"
                }
              ],
              profiles: [
                {
                  id: "baseline",
                  label: "NoHarness",
                  harness_modules: {},
                  output_text: "baseline",
                  steps: [
                    {
                      profile_id: "baseline",
                      profile_label: "NoHarness",
                      step_id: "step_0001",
                      sequence: 1,
                      type: "agent_step_completed",
                      label: "Run task",
                      status: "completed"
                    }
                  ]
                },
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
      project: { id: "proj_history", name: "History", surface_type: "agent" },
      runs: [
        {
          id: "run_1",
          attachments: [
            {
              id: "attachment_0_screen.png",
              name: "screen.png",
              kind: "image",
              type: "image/png",
              size: 12,
              status: "ready",
              url: "data:image/png;base64,abc"
            }
          ],
          profiles: [
            {
              id: "baseline",
              label: "NoHarness",
              output_text: "baseline",
              steps: [
                {
                  id: "step_0001_agent_step_completed_1",
                  profile_id: "baseline",
                  profile_label: "NoHarness",
                  step_id: "step_0001",
                  sequence: 1,
                  type: "agent_step_completed",
                  label: "Run task",
                  status: "completed"
                }
              ]
            },
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

  it("lists and creates subagent definitions through the subagents API", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        mockJsonResponse({
          agents_dir: "C:/home/.harnessdiff/agents",
          subagents: [
            {
              id: "researcher",
              label: "Researcher",
              description: "Research",
              model: "gpt-5.4-mini",
              reasoning_effort: "medium",
              max_output_chars: 4000,
              enabled: true,
              path: "researcher.md"
            }
          ]
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse(
          {
            subagent: {
              id: "fact_checker",
              label: "Fact Checker",
              description: "",
              model: "gpt-5.4-mini",
              reasoning_effort: "low",
              max_output_chars: 4000,
              enabled: true,
              path: "fact_checker.md"
            }
          },
          true,
          201
        )
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(listSubagents()).resolves.toMatchObject({
      agents_dir: "C:/home/.harnessdiff/agents",
      subagents: [{ id: "researcher" }]
    });
    await expect(
      createSubagent({
        id: "fact_checker",
        label: "Fact Checker",
        description: "",
        instructions: "Check claims.",
        model: "gpt-5.4-mini",
        reasoning_effort: "low",
        max_output_chars: 4000,
        enabled: true
      })
    ).resolves.toMatchObject({ id: "fact_checker" });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/subagents");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/subagents",
      expect.objectContaining({ method: "POST" })
    );
  });
});
