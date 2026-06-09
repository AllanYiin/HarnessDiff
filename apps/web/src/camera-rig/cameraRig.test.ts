import { describe, expect, it } from "vitest";

import { findRigPreset, rigPresets, sampleCameraPose } from "./cameraRig";

describe("camera rig sampling", () => {
  it("returns a stable preset fallback", () => {
    expect(findRigPreset("missing").id).toBe(rigPresets[0].id);
  });

  it("samples the first and last keyframe at progress bounds", () => {
    const preset = rigPresets[0];
    const start = sampleCameraPose(preset.id, -0.5);
    const end = sampleCameraPose(preset.id, 1.5);

    expect(start.position.x).toBeCloseTo(preset.keyframes[0].position.x);
    expect(start.fov).toBeCloseTo(preset.keyframes[0].fov);
    expect(end.position.x).toBeCloseTo(preset.keyframes[preset.keyframes.length - 1].position.x);
    expect(end.roll).toBeCloseTo(preset.keyframes[preset.keyframes.length - 1].roll);
  });

  it("derives readable camera metadata for the UI", () => {
    const pose = sampleCameraPose("dolly-focus", 0.5);

    expect(Number.isFinite(pose.pan)).toBe(true);
    expect(Number.isFinite(pose.tilt)).toBe(true);
    expect(pose.distance).toBeGreaterThan(0);
    expect(pose.fov).toBeGreaterThanOrEqual(30);
  });
});
