export type Vec3 = {
  x: number;
  y: number;
  z: number;
};

export type CameraPose = {
  position: Vec3;
  target: Vec3;
  roll: number;
  fov: number;
};

export type SampledCameraPose = CameraPose & {
  pan: number;
  tilt: number;
  distance: number;
};

export type CameraKeyframe = CameraPose & {
  t: number;
};

export type RigPreset = {
  id: string;
  label: string;
  intent: string;
  keyframes: CameraKeyframe[];
};

export const rigPresets: RigPreset[] = [
  {
    id: "orbit-reveal",
    label: "環繞揭示",
    intent: "先交代空間，再把主體推出來，適合產品展示或場景建立。",
    keyframes: [
      { t: 0, position: { x: -7, y: 4.4, z: 8 }, target: { x: 0, y: 1.2, z: 0 }, roll: -2, fov: 42 },
      { t: 0.5, position: { x: 0.5, y: 4.9, z: 6.3 }, target: { x: 0.2, y: 1.4, z: -0.4 }, roll: 0, fov: 36 },
      { t: 1, position: { x: 6.2, y: 4.1, z: 5.6 }, target: { x: 0.4, y: 1.5, z: -0.3 }, roll: 2, fov: 34 }
    ]
  },
  {
    id: "dolly-focus",
    label: "推軌聚焦",
    intent: "用平穩推近建立壓迫感，讓視線停在中央主體。",
    keyframes: [
      { t: 0, position: { x: 0, y: 2.6, z: 10 }, target: { x: 0, y: 1.4, z: 0 }, roll: 0, fov: 46 },
      { t: 0.62, position: { x: 0.2, y: 2.35, z: 6 }, target: { x: 0, y: 1.35, z: -0.1 }, roll: 0, fov: 38 },
      { t: 1, position: { x: 0.3, y: 2.2, z: 3.7 }, target: { x: 0.05, y: 1.3, z: -0.2 }, roll: 0, fov: 30 }
    ]
  },
  {
    id: "crane-down",
    label: "升降俯衝",
    intent: "從高處俯視進入地面視角，適合轉場或導覽大型空間。",
    keyframes: [
      { t: 0, position: { x: -2.4, y: 8.2, z: 7.4 }, target: { x: 0, y: 0.8, z: 0 }, roll: 0, fov: 48 },
      { t: 0.45, position: { x: -1.3, y: 5.4, z: 5.8 }, target: { x: 0.1, y: 1, z: -0.2 }, roll: 1, fov: 39 },
      { t: 1, position: { x: 1.8, y: 2.1, z: 4.4 }, target: { x: 0.15, y: 1.35, z: -0.4 }, roll: -1, fov: 35 }
    ]
  },
  {
    id: "dutch-pass",
    label: "斜角掠過",
    intent: "用 roll 與橫移營造速度感，適合音樂節奏或戲劇性片段。",
    keyframes: [
      { t: 0, position: { x: -6.6, y: 2.4, z: 4.4 }, target: { x: -0.3, y: 1.2, z: -0.1 }, roll: -9, fov: 35 },
      { t: 0.45, position: { x: -1.2, y: 2.1, z: 3.5 }, target: { x: 0, y: 1.25, z: -0.2 }, roll: -3, fov: 31 },
      { t: 1, position: { x: 5.8, y: 2.8, z: 4.9 }, target: { x: 0.5, y: 1.25, z: -0.2 }, roll: 8, fov: 37 }
    ]
  }
];

export function clamp01(value: number) {
  return Math.min(1, Math.max(0, value));
}

function easeInOutCubic(value: number) {
  const t = clamp01(value);
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function lerp(start: number, end: number, t: number) {
  return start + (end - start) * t;
}

function lerpVec(start: Vec3, end: Vec3, t: number): Vec3 {
  return {
    x: lerp(start.x, end.x, t),
    y: lerp(start.y, end.y, t),
    z: lerp(start.z, end.z, t)
  };
}

function deriveCameraAngles(position: Vec3, target: Vec3) {
  const dx = target.x - position.x;
  const dy = target.y - position.y;
  const dz = target.z - position.z;
  const horizontalDistance = Math.hypot(dx, dz);
  const distance = Math.hypot(horizontalDistance, dy);
  return {
    pan: (Math.atan2(dx, dz) * 180) / Math.PI,
    tilt: (Math.atan2(dy, horizontalDistance) * 180) / Math.PI,
    distance
  };
}

export function findRigPreset(id: string) {
  return rigPresets.find((preset) => preset.id === id) ?? rigPresets[0];
}

export function sampleCameraPose(presetId: string, progress: number): SampledCameraPose {
  const preset = findRigPreset(presetId);
  const t = clamp01(progress);
  const keyframes = preset.keyframes;
  const nextIndex = keyframes.findIndex((keyframe) => keyframe.t >= t);
  const end = keyframes[nextIndex === -1 ? keyframes.length - 1 : nextIndex];
  const start = keyframes[Math.max(0, keyframes.indexOf(end) - 1)] ?? end;
  const span = Math.max(0.0001, end.t - start.t);
  const localT = start === end ? 0 : easeInOutCubic((t - start.t) / span);
  const position = lerpVec(start.position, end.position, localT);
  const target = lerpVec(start.target, end.target, localT);
  const angles = deriveCameraAngles(position, target);

  return {
    position,
    target,
    roll: lerp(start.roll, end.roll, localT),
    fov: lerp(start.fov, end.fov, localT),
    ...angles
  };
}
