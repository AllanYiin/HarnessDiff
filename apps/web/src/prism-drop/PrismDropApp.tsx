import { useEffect, useMemo, useReducer } from "react";

import {
  BOARD_HEIGHT,
  BOARD_WIDTH,
  createInitialState,
  createPiece,
  freezeBend,
  ghostPiece,
  hardDrop,
  holdPiece,
  move,
  pieceCells,
  rotate,
  startOrPause,
  type Board,
  type Cell,
  type GameState,
  type PieceKind
} from "./engine";
import "./prism-drop.css";

type Action =
  | { type: "startPause" }
  | { type: "reset" }
  | { type: "left" }
  | { type: "right" }
  | { type: "softDrop" }
  | { type: "hardDrop" }
  | { type: "rotate" }
  | { type: "hold" }
  | { type: "freeze" }
  | { type: "tick" };

function reducer(state: GameState, action: Action): GameState {
  switch (action.type) {
    case "startPause":
      return startOrPause(state);
    case "reset":
      return createInitialState();
    case "left":
      return move(state, -1, 0);
    case "right":
      return move(state, 1, 0);
    case "softDrop":
    case "tick":
      return move(state, 0, 1);
    case "hardDrop":
      return hardDrop(state);
    case "rotate":
      return rotate(state);
    case "hold":
      return holdPiece(state);
    case "freeze":
      return freezeBend(state);
    default:
      return state;
  }
}

function cellStyle(cell: Cell | null) {
  if (!cell) return undefined;
  return {
    "--cell-hue": cell.hue,
    "--cell-alpha": cell.cracked ? 0.52 : 0.88
  } as React.CSSProperties;
}

function overlayBoard(state: GameState): Board {
  const board = state.board.map((row) => row.slice());
  const ghost = ghostPiece(state.board, state.active);
  for (const { x, y } of pieceCells(ghost)) {
    if (y >= 0 && y < BOARD_HEIGHT && x >= 0 && x < BOARD_WIDTH && !board[y][x]) {
      board[y][x] = { kind: state.active.kind, hue: state.active.hue, cracked: true };
    }
  }
  for (const { x, y } of pieceCells(state.active)) {
    if (y >= 0 && y < BOARD_HEIGHT && x >= 0 && x < BOARD_WIDTH) {
      board[y][x] = { kind: state.active.kind, hue: state.active.hue };
    }
  }
  return board;
}

function MiniPiece({ kind, label }: { kind: PieceKind | null; label: string }) {
  const piece = kind ? createPiece(kind) : null;
  const cells = piece ? pieceCells({ ...piece, x: 0, y: 0 }) : [];
  return (
    <div className="pdMiniPiece" aria-label={label}>
      {Array.from({ length: 16 }).map((_, index) => {
        const x = index % 4;
        const y = Math.floor(index / 4);
        const filled = piece && cells.some((cell) => cell.x === x && cell.y === y);
        return (
          <span
            className={filled ? "pdMiniCell filled" : "pdMiniCell"}
            key={`${label}-${index}`}
            style={filled && piece ? cellStyle({ kind: piece.kind, hue: piece.hue }) : undefined}
          />
        );
      })}
    </div>
  );
}

export function PrismDropApp() {
  const [state, dispatch] = useReducer(reducer, undefined, () => createInitialState());
  const board = useMemo(() => overlayBoard(state), [state]);
  const mainAction = state.status === "playing" ? "Pause" : state.status === "paused" ? "Resume" : state.status === "lost" ? "New run" : "Start";

  useEffect(() => {
    if (state.status !== "playing") return undefined;
    const interval = window.setInterval(() => dispatch({ type: "tick" }), 620);
    return () => window.clearInterval(interval);
  }, [state.status]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const keyMap: Record<string, Action["type"] | undefined> = {
        ArrowLeft: "left",
        ArrowRight: "right",
        ArrowDown: "softDrop",
        ArrowUp: "rotate",
        " ": "hardDrop",
        c: "hold",
        C: "hold",
        Shift: "hold",
        f: "freeze",
        F: "freeze",
        p: "startPause",
        P: "startPause",
        Enter: "startPause"
      };
      const mapped = keyMap[event.key];
      if (!mapped) return;
      event.preventDefault();
      dispatch({ type: mapped });
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <main className="pdShell">
      <section className="pdHero" aria-labelledby="pd-title">
        <div className="pdBrand">
          <p>Falling-block puzzle prototype</p>
          <h1 id="pd-title">Prism Drop</h1>
        </div>
        <p className="pdThesis">落塊、消行、光譜脈衝。保留熟悉手感，但把高分壓力放在節奏與風險選擇。</p>
      </section>

      <section className="pdStage" aria-label="Prism Drop game prototype">
        <div className="pdBoardWrap">
          <div className="pdBoard" role="grid" aria-label="10 by 20 game board">
            {board.flatMap((row, y) =>
              row.map((cell, x) => (
                <span
                  className={cell ? `pdCell filled ${cell.cracked ? "ghost" : ""}` : "pdCell"}
                  key={`${x}-${y}`}
                  style={cellStyle(cell)}
                  role="gridcell"
                />
              ))
            )}
          </div>
          {state.status !== "playing" && (
            <div className="pdOverlay">
              <strong>{state.status === "lost" ? "Run collapsed" : "Ready to bend gravity"}</strong>
              <span>{state.status === "lost" ? "用更乾淨的井道與光譜脈衝再挑戰。" : "Enter 開始，方向鍵移動，空白鍵硬降。"}</span>
            </div>
          )}
        </div>

        <aside className="pdStatus" aria-label="Game status">
          <div className="pdScoreRail">
            <span>Score</span>
            <strong>{state.score.toLocaleString()}</strong>
          </div>
          <div className="pdMeters">
            <label>
              Spectrum
              <span>{state.spectrum}%</span>
            </label>
            <meter min={0} max={100} value={Math.min(100, state.spectrum)} />
            <label>
              Chain
              <span>x{Math.max(1, state.chain)}</span>
            </label>
            <meter min={0} max={5} value={Math.min(5, state.chain)} />
          </div>

          <div className="pdPieceRow">
            <div>
              <span className="pdKicker">Hold</span>
              <MiniPiece kind={state.hold} label="hold piece" />
            </div>
            <div>
              <span className="pdKicker">Next</span>
              <div className="pdNextQueue">
                {state.next.slice(0, 3).map((kind, index) => (
                  <MiniPiece kind={kind} label={`next piece ${index + 1}`} key={`${kind}-${index}`} />
                ))}
              </div>
            </div>
          </div>

          <div className="pdActions">
            <button className="pdPrimary" type="button" onClick={() => dispatch({ type: "startPause" })}>
              {mainAction}
            </button>
            <button type="button" onClick={() => dispatch({ type: "freeze" })} disabled={state.spectrum < 24 || state.status !== "playing"}>
              Freeze Bend
            </button>
            <button type="button" onClick={() => dispatch({ type: "reset" })}>
              Reset
            </button>
          </div>
          <p className="pdEvent">{state.lastEvent}</p>
          <dl className="pdControls">
            <div><dt>Move</dt><dd>← →</dd></div>
            <div><dt>Rotate</dt><dd>↑</dd></div>
            <div><dt>Drop</dt><dd>↓ / Space</dd></div>
            <div><dt>Hold</dt><dd>C / Shift</dd></div>
            <div><dt>Pause</dt><dd>P / Enter</dd></div>
          </dl>
        </aside>
      </section>

      <section className="pdSpec" aria-label="Lightweight specification">
        <h2>Lightweight B spec</h2>
        <ul>
          <li><strong>MVP 主循環：</strong>10x20 盤面、7-bag-like 佇列、hold、ghost、消行、連鎖計分。</li>
          <li><strong>創新機制：</strong>Spectrum 滿 100 會觸發 Prism Pulse，清除盤面最多的色相；Freeze Bend 可短暫換取時間但留下裂紋風險。</li>
          <li><strong>美術原則：</strong>單一主舞台、暖白玻璃、柔和光譜、狀態資訊收在右側，不做卡片農場。</li>
          <li><strong>下一步：</strong>補 lock delay、音樂節拍事件、mobile touch controls、Playwright smoke test。</li>
        </ul>
      </section>
    </main>
  );
}
