import { useEffect, useMemo, useRef, useState } from "react";

import { CameraCanvasViewport, type StageObject } from "./CameraCanvasViewport";
import { rigPresets, sampleCameraPose } from "./cameraRig";
import "./camera-rig.css";

const stageObjects: StageObject[] = [
  { id: "hero", label: "主體", x: 0, z: 0, h: 112, tone: "amber" },
  { id: "left", label: "前景", x: -2.4, z: 1.8, h: 62, tone: "teal" },
  { id: "right", label: "背景", x: 2.7, z: -1.8, h: 78, tone: "blue" },
  { id: "marker", label: "路徑點", x: -1.5, z: -2.8, h: 38, tone: "slate" }
];

function formatNumber(value: number, digits = 1) {
  return value.toFixed(digits).replace(/\.0$/, "");
}

function CameraPathMap({ presetId, progress }: { presetId: string; progress: number }) {
  const points = useMemo(
    () => Array.from({ length: 36 }, (_, index) => sampleCameraPose(presetId, index / 35)),
    [presetId]
  );
  const current = sampleCameraPose(presetId, progress / 100);
  const path = points
    .map((pose, index) => {
      const x = 70 + pose.position.x * 12;
      const y = 72 - pose.position.z * 8;
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
  const cx = 70 + current.position.x * 12;
  const cy = 72 - current.position.z * 8;

  return (
    <svg className="crPathMap" viewBox="0 0 140 112" role="img" aria-label="Camera path top view">
      <path className="crPathGrid" d="M10 56H130M70 10V102" />
      <path className="crPathLine" d={path} />
      <circle className="crPathTarget" cx="70" cy="72" r="5" />
      <circle className="crPathDot" cx={cx} cy={cy} r="6" />
    </svg>
  );
}

export function CameraRigSimulator() {
  const [presetId, setPresetId] = useState(rigPresets[0].id);
  const [progress, setProgress] = useState(18);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [orbitBias, setOrbitBias] = useState(0);
  const [showGuides, setShowGuides] = useState(true);
  const lastFrameRef = useRef<number | null>(null);
  const selectedPreset = rigPresets.find((preset) => preset.id === presetId) ?? rigPresets[0];
  const pose = sampleCameraPose(presetId, progress / 100);
  const stageStyle = {
    "--cr-pan": `${pose.pan + orbitBias}deg`,
    "--cr-tilt": `${pose.tilt}deg`,
    "--cr-roll": `${pose.roll}deg`,
    "--cr-fov": `${pose.fov}`,
    "--cr-dolly": `${pose.distance}`,
    "--cr-camera-x": `${pose.position.x}`,
    "--cr-camera-y": `${pose.position.y}`,
    "--cr-camera-z": `${pose.position.z}`
  } as React.CSSProperties;

  useEffect(() => {
    if (!playing) {
      lastFrameRef.current = null;
      return undefined;
    }

    let frameId = 0;
    function tick(timestamp: number) {
      const last = lastFrameRef.current ?? timestamp;
      const delta = timestamp - last;
      lastFrameRef.current = timestamp;
      setProgress((current) => (current + delta * 0.008 * speed) % 100);
      frameId = window.requestAnimationFrame(tick);
    }

    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [playing, speed]);

  return (
    <main className="crShell" style={stageStyle}>
      <header className="crHeader">
        <div>
          <p>3D camera blocking prototype</p>
          <h1>3D 運鏡模擬器</h1>
        </div>
        <div className="crHeaderStatus" aria-live="polite">
          <span>{playing ? "播放中" : "已暫停"}</span>
          <strong>{Math.round(progress)}%</strong>
        </div>
      </header>

      <section className="crWorkspace" aria-label="3D camera simulator workspace">
        <div className="crViewportPanel">
          <div className="crViewport" aria-label="Simulated camera viewport">
            <div className="crScene" aria-hidden="true">
              <div className="crFloor">
                {Array.from({ length: 10 }).map((_, index) => (
                  <span
                    className="crFloorLine x"
                    key={`x-${index}`}
                    style={{ "--i": index } as React.CSSProperties}
                  />
                ))}
                {Array.from({ length: 10 }).map((_, index) => (
                  <span
                    className="crFloorLine z"
                    key={`z-${index}`}
                    style={{ "--i": index } as React.CSSProperties}
                  />
                ))}
              </div>
              {stageObjects.map((object) => (
                <div
                  className={`crObject ${object.tone}`}
                  key={object.id}
                  style={
                    {
                      "--obj-x": object.x,
                      "--obj-z": object.z,
                      "--obj-h": `${object.h}px`
                    } as React.CSSProperties
                  }
                >
                  <span>{object.label}</span>
                </div>
              ))}
              <div className="crTargetBeacon">Target</div>
            </div>
            {showGuides ? (
              <div className="crFrameGuides" aria-hidden="true">
                <span />
                <span />
                <span />
                <span />
              </div>
            ) : null}
            <div className="crLensReadout">
              <span>Lens {formatNumber(pose.fov, 0)}mm</span>
              <span>Pan {formatNumber(pose.pan)}°</span>
              <span>Tilt {formatNumber(pose.tilt)}°</span>
              <span>Roll {formatNumber(pose.roll)}°</span>
            </div>
          </div>
        </div>

        <aside className="crControls" aria-label="Camera controls">
          <div className="crPrimaryControls">
            <button className="crPrimaryButton" type="button" onClick={() => setPlaying((current) => !current)}>
              {playing ? "暫停運鏡" : "播放運鏡"}
            </button>
            <button type="button" onClick={() => setProgress(0)}>
              回到起點
            </button>
          </div>

          <label className="crField">
            <span>運鏡腳本</span>
            <select value={presetId} onChange={(event) => setPresetId(event.target.value)}>
              {rigPresets.map((preset) => (
                <option value={preset.id} key={preset.id}>
                  {preset.label}
                </option>
              ))}
            </select>
          </label>

          <label className="crField crTimeline">
            <span>時間軸</span>
            <input
              type="range"
              min="0"
              max="100"
              step="1"
              value={progress}
              onChange={(event) => setProgress(Number(event.target.value))}
            />
          </label>

          <div className="crTwoColumnControls">
            <label className="crField">
              <span>速度 {formatNumber(speed, 1)}x</span>
              <input
                type="range"
                min="0.25"
                max="2"
                step="0.25"
                value={speed}
                onChange={(event) => setSpeed(Number(event.target.value))}
              />
            </label>
            <label className="crField">
              <span>觀察角偏移 {formatNumber(orbitBias, 0)}°</span>
              <input
                type="range"
                min="-28"
                max="28"
                step="1"
                value={orbitBias}
                onChange={(event) => setOrbitBias(Number(event.target.value))}
              />
            </label>
          </div>

          <label className="crToggle">
            <input
              type="checkbox"
              checked={showGuides}
              onChange={(event) => setShowGuides(event.target.checked)}
            />
            <span>顯示安全框與三分線</span>
          </label>

          <div className="crStatusStrip">
            <CameraPathMap presetId={presetId} progress={progress} />
            <dl>
              <div>
                <dt>Camera</dt>
                <dd>
                  X {formatNumber(pose.position.x)} · Y {formatNumber(pose.position.y)} · Z {formatNumber(pose.position.z)}
                </dd>
              </div>
              <div>
                <dt>Distance</dt>
                <dd>{formatNumber(pose.distance)}m</dd>
              </div>
            </dl>
          </div>

          <details className="crReference">
            <summary>腳本意圖與下一步</summary>
            <p>{selectedPreset.intent}</p>
            <p>下一步可加入匯出 keyframes、手動新增鏡位、以及接 Three.js / Blender camera path。</p>
          </details>
        </aside>
      </section>
    </main>
  );
}
