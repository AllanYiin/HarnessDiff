import { describe, expect, it } from "vitest";

import {
  BOARD_HEIGHT,
  BOARD_WIDTH,
  clearCompletedLines,
  createEmptyBoard,
  createInitialState,
  freezeBend,
  hardDrop,
  holdPiece,
  move,
  startOrPause,
  type Board,
  type Cell
} from "./engine";

function filledCell(): Cell {
  return { kind: "I", hue: 184 };
}

function playingState() {
  return startOrPause(createInitialState(["I", "O", "T", "S", "Z", "J"]));
}

describe("Prism Drop engine", () => {
  it("clears completed lines and preserves board height", () => {
    const board = createEmptyBoard();
    board[BOARD_HEIGHT - 1] = Array.from({ length: BOARD_WIDTH }, filledCell);

    const result = clearCompletedLines(board);

    expect(result.cleared).toBe(1);
    expect(result.board).toHaveLength(BOARD_HEIGHT);
    expect(result.board[0].every((cell) => cell === null)).toBe(true);
  });

  it("hard drops the active piece and advances to the next piece", () => {
    const state = playingState();

    const dropped = hardDrop(state);

    expect(dropped.active.kind).toBe("O");
    expect(dropped.score).toBeGreaterThan(0);
    expect(dropped.board.some((row) => row.some(Boolean))).toBe(true);
  });

  it("allows hold once per falling piece", () => {
    const state = playingState();
    const held = holdPiece(state);
    const secondHold = holdPiece(held);

    expect(held.hold).toBe("I");
    expect(held.active.kind).toBe("O");
    expect(held.canHold).toBe(false);
    expect(secondHold).toBe(held);
  });

  it("triggers a prism pulse when spectrum reaches the threshold after clearing", () => {
    const state = playingState();
    const board: Board = createEmptyBoard();
    board[BOARD_HEIGHT - 1] = Array.from({ length: BOARD_WIDTH }, (_, index) =>
      index >= 4 && index <= 7 ? null : filledCell()
    );
    const primed = { ...state, board, active: { ...state.active, x: 4, y: BOARD_HEIGHT - 2 }, spectrum: 90 };

    const resolved = move(primed, 0, 1);

    expect(resolved.lines).toBe(1);
    expect(resolved.spectrum).toBeLessThan(100);
    expect(resolved.lastEvent).toContain("Prism pulse");
  });

  it("freeze bend spends spectrum and leaves a cracked risk cell", () => {
    const state = { ...playingState(), spectrum: 40 };

    const frozen = freezeBend(state);

    expect(frozen.spectrum).toBe(16);
    expect(frozen.board.flat().some((cell) => cell?.cracked)).toBe(true);
  });
});
