import { useEffect, useMemo, useRef } from "react";

import { rigPresets, sampleCameraPose, type SampledCameraPose, type Vec3 } from "./cameraRig";

export type StageObject = {
  id: string;
  label: string;
  x: number;
  z: number;
  h: number;
  tone: "amber" | "teal" | "blue" | "slate";
};

type ScreenPoint = {
  x: number;
  y: number;
  depth: number;
};

const tonePalette: Record<StageObject["tone"], { fill: string; stroke: string; glow: string }> = {
  amber: { fill: "#f7c36a", stroke: "#fff2c7", glow: "rgba(247, 195, 106, 0.42)" },
  teal: { fill: "#53d7c2", stroke: "#c7fff6", glow: "rgba(83, 215, 194, 0.36)" },
  blue: { fill: "#77a7ff", stroke: "#d8e5ff", glow: "rgba(119, 167, 255, 0.36)" },
  slate: { fill: "#9ca7bb", stroke: "#eef2ff", glow: "rgba(156, 167, 187, 0.3)" }
};

function normalize(value: Vec3): Vec3 {
  const length = Math.hypot(value.x, value.y, value.z) || 1;
  return { x: value.x / length, y: value.y / length, z: value.z / length };
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x
  };
}

function dot(a: Vec3, b: Vec3) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

function rotate2d(x: number, y: number, degrees: number) {
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return { x: x * cos - y * sin, y: x * sin + y * cos };
}

export function projectWorldPoint(point: Vec3, pose: SampledCameraPose, width: number, height: number): ScreenPoint | null {
  const forward = normalize({
    x: pose.target.x - pose.position.x,
    y: pose.target.y - pose.position.y,
    z: pose.target.z - pose.position.z
  });
  const worldUp = { x: 0, y: 1, z: 0 };
  const right = normalize(cross(forward, worldUp));
  const up = normalize(cross(right, forward));
  const relative = {
    x: point.x - pose.position.x,
    y: point.y - pose.position.y,
    z: point.z - pose.position.z
  };
  const cameraX = dot(relative, right);
  const cameraY = dot(relative, up);
  const cameraZ = dot(relative, forward);

  if (cameraZ <= 0.08) {
    return null;
  }

  const rolled = rotate2d(cameraX, cameraY, pose.roll);
  const focal = (height * 0.78) / Math.tan((Math.max(18, Math.min(70, pose.fov)) * Math.PI) / 360);

  return {
    x: width / 2 + (rolled.x / cameraZ) * focal,
    y: height / 2 - (rolled.y / cameraZ) * focal,
    depth: cameraZ
  };
}

function drawLine(ctx: CanvasRenderingContext2D, points: Array<ScreenPoint | null>) {
  const visible = points.filter(Boolean) as ScreenPoint[];
  if (visible.length < 2) return;
  ctx.beginPath();
  visible.forEach((point, index) => {
    if (index === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();
}

function drawGuides(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.save();
  ctx.strokeStyle = "rgba(234, 242, 255, 0.28)";
  ctx.lineWidth = 1;
  ctx.strokeRect(width * 0.09, height * 0.1, width * 0.82, height * 0.8);
  ctx.beginPath();
  ctx.moveTo(width / 3, height * 0.1);
  ctx.lineTo(width / 3, height * 0.9);
  ctx.moveTo((width * 2) / 3, height * 0.1);
  ctx.lineTo((width * 2) / 3, height * 0.9);
  ctx.moveTo(width * 0.09, height / 3);
  ctx.lineTo(width * 0.91, height / 3);
  ctx.moveTo(width * 0.09, (height * 2) / 3);
  ctx.lineTo(width * 0.91, (height * 2) / 3);
  ctx.stroke();
  ctx.restore();
}

function drawScene(
  canvas: HTMLCanvasElement,
  pose: SampledCameraPose,
  objects: StageObject[],
  showGuides: boolean,
  presetId: string,
  progress: number
) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round(rect.height * dpr));

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.save();
  ctx.scale(dpr, dpr);
  const cssWidth = width / dpr;
  const cssHeight = height / dpr;

  const sky = ctx.createLinearGradient(0, 0, 0, cssHeight);
  sky.addColorStop(0, "#091326");
  sky.addColorStop(0.55, "#111d32");
  sky.addColorStop(1, "#08101c");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  ctx.strokeStyle = "rgba(119, 167, 255, 0.16)";
  ctx.lineWidth = 1;
  for (let i = -6; i <= 6; i += 1) {
    drawLine(ctx, [
      projectWorldPoint({ x: i, y: 0, z: -7 }, pose, cssWidth, cssHeight),
      projectWorldPoint({ x: i, y: 0, z: 8 }, pose, cssWidth, cssHeight)
    ]);
    drawLine(ctx, [
      projectWorldPoint({ x: -6, y: 0, z: i }, pose, cssWidth, cssHeight),
      projectWorldPoint({ x: 6, y: 0, z: i }, pose, cssWidth, cssHeight)
    ]);
  }

  const pathPoints = Array.from({ length: 46 }, (_, index) => {
    const pathPose = sampleCameraPose(presetId, index / 45);
    return projectWorldPoint(pathPose.position, pose, cssWidth, cssHeight);
  });
  ctx.strokeStyle = "rgba(247, 195, 106, 0.54)";
  ctx.lineWidth = 2;
  drawLine(ctx, pathPoints);

  const target = projectWorldPoint(pose.target, pose, cssWidth, cssHeight);
  if (target) {
    ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
    ctx.beginPath();
    ctx.arc(target.x, target.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = "12px ui-sans-serif, system-ui";
    ctx.fillText("Target", target.x + 8, target.y - 8);
  }

  const drawableObjects = objects
    .map((object) => ({
      object,
      base: projectWorldPoint({ x: object.x, y: 0, z: object.z }, pose, cssWidth, cssHeight),
      top: projectWorldPoint({ x: object.x, y: object.h / 70, z: object.z }, pose, cssWidth, cssHeight)
    }))
    .filter((item) => item.base && item.top)
    .sort((a, b) => (b.base?.depth ?? 0) - (a.base?.depth ?? 0));

  drawableObjects.forEach(({ object, base, top }) => {
    if (!base || !top) return;
    const palette = tonePalette[object.tone];
    const objectHeight = Math.max(24, Math.abs(base.y - top.y));
    const objectWidth = Math.max(18, objectHeight * 0.28);
    const left = top.x - objectWidth / 2;
    const topY = top.y;

    ctx.shadowColor = palette.glow;
    ctx.shadowBlur = 18;
    ctx.fillStyle = palette.fill;
    ctx.strokeStyle = palette.stroke;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(left, topY, objectWidth, objectHeight, 7);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;

    ctx.fillStyle = "rgba(255, 255, 255, 0.84)";
    ctx.font = "12px ui-sans-serif, system-ui";
    ctx.fillText(object.label, left - 4, topY - 8);
  });

  const currentPathPose = sampleCameraPose(presetId, progress / 100);
  const currentPathPoint = projectWorldPoint(currentPathPose.position, pose, cssWidth, cssHeight);
  if (currentPathPoint) {
    ctx.fillStyle = "#f7c36a";
    ctx.beginPath();
    ctx.arc(currentPathPoint.x, currentPathPoint.y, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  if (showGuides) {
    drawGuides(ctx, cssWidth, cssHeight);
  }

  ctx.restore();
}

export function CameraCanvasViewport({
  pose,
  objects,
  showGuides,
  presetId,
  progress
}: {
  pose: SampledCameraPose;
  objects: StageObject[];
  showGuides: boolean;
  presetId: string;
  progress: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const renderKey = useMemo(
    () => `${presetId}:${Math.round(progress)}:${showGuides}:${pose.position.x.toFixed(2)}:${pose.position.y.toFixed(2)}:${pose.position.z.toFixed(2)}`,
    [pose, presetId, progress, showGuides]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    const render = () => drawScene(canvas, pose, objects, showGuides, presetId, progress);
    render();

    const observer = new ResizeObserver(render);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [renderKey, pose, objects, showGuides, presetId, progress]);

  return <canvas ref={canvasRef} className="crCanvasViewport" aria-label="Canvas rendered camera simulation" />;
}
