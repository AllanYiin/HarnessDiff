export const BOARD_WIDTH = 10;
export const BOARD_HEIGHT = 20;

export type PieceKind = "I" | "O" | "T" | "S" | "Z" | "J" | "L";

export type Cell = {
  kind: PieceKind;
  hue: number;
  cracked?: boolean;
};

export type Board = Array<Array<Cell | null>>;

export type Piece = {
  kind: PieceKind;
  rotation: number;
  x: number;
  y: number;
  hue: number;
};

export type GameStatus = "ready" | "playing" | "paused" | "lost";

export type GameState = {
  board: Board;
  active: Piece;
  next: PieceKind[];
  bag: PieceKind[];
  hold: PieceKind | null;
  canHold: boolean;
  score: number;
  lines: number;
  chain: number;
  spectrum: number;
  status: GameStatus;
  lastEvent: string;
};

const kinds: PieceKind[] = ["I", "O", "T", "S", "Z", "J", "L"];

const hues: Record<PieceKind, number> = {
  I: 184,
  O: 43,
  T: 260,
  S: 154,
  Z: 352,
  J: 220,
  L: 28
};

const shapes: Record<PieceKind, Array<Array<[number, number]>>> = {
  I: [
    [[0, 1], [1, 1], [2, 1], [3, 1]],
    [[2, 0], [2, 1], [2, 2], [2, 3]],
    [[0, 2], [1, 2], [2, 2], [3, 2]],
    [[1, 0], [1, 1], [1, 2], [1, 3]]
  ],
  O: [
    [[1, 0], [2, 0], [1, 1], [2, 1]],
    [[1, 0], [2, 0], [1, 1], [2, 1]],
    [[1, 0], [2, 0], [1, 1], [2, 1]],
    [[1, 0], [2, 0], [1, 1], [2, 1]]
  ],
  T: [
    [[1, 0], [0, 1], [1, 1], [2, 1]],
    [[1, 0], [1, 1], [2, 1], [1, 2]],
    [[0, 1], [1, 1], [2, 1], [1, 2]],
    [[1, 0], [0, 1], [1, 1], [1, 2]]
  ],
  S: [
    [[1, 0], [2, 0], [0, 1], [1, 1]],
    [[1, 0], [1, 1], [2, 1], [2, 2]],
    [[1, 1], [2, 1], [0, 2], [1, 2]],
    [[0, 0], [0, 1], [1, 1], [1, 2]]
  ],
  Z: [
    [[0, 0], [1, 0], [1, 1], [2, 1]],
    [[2, 0], [1, 1], [2, 1], [1, 2]],
    [[0, 1], [1, 1], [1, 2], [2, 2]],
    [[1, 0], [0, 1], [1, 1], [0, 2]]
  ],
  J: [
    [[0, 0], [0, 1], [1, 1], [2, 1]],
    [[1, 0], [2, 0], [1, 1], [1, 2]],
    [[0, 1], [1, 1], [2, 1], [2, 2]],
    [[1, 0], [1, 1], [0, 2], [1, 2]]
  ],
  L: [
    [[2, 0], [0, 1], [1, 1], [2, 1]],
    [[1, 0], [1, 1], [1, 2], [2, 2]],
    [[0, 1], [1, 1], [2, 1], [0, 2]],
    [[0, 0], [1, 0], [1, 1], [1, 2]]
  ]
};

export function createEmptyBoard(): Board {
  return Array.from({ length: BOARD_HEIGHT }, () => Array<Cell | null>(BOARD_WIDTH).fill(null));
}

export function createPiece(kind: PieceKind): Piece {
  return { kind, rotation: 0, x: 3, y: 0, hue: hues[kind] };
}

export function pieceCells(piece: Piece) {
  return shapes[piece.kind][piece.rotation % 4].map(([x, y]) => ({
    x: piece.x + x,
    y: piece.y + y
  }));
}

function shuffleBag(seed = Math.random): PieceKind[] {
  const bag = [...kinds];
  for (let index = bag.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(seed() * (index + 1));
    [bag[index], bag[swapIndex]] = [bag[swapIndex], bag[index]];
  }
  return bag;
}

function drawKind(next: PieceKind[], bag: PieceKind[]) {
  const nextQueue = [...next];
  let nextBag = [...bag];
  if (nextQueue.length === 0) {
    nextBag = shuffleBag();
    nextQueue.push(...nextBag);
    nextBag = [];
  }
  const kind = nextQueue.shift() ?? "I";
  while (nextQueue.length < 5) {
    if (nextBag.length === 0) {
      nextBag = shuffleBag();
    }
    nextQueue.push(nextBag.shift() ?? "I");
  }
  return { kind, next: nextQueue, bag: nextBag };
}

export function createInitialState(seedKinds: PieceKind[] = ["I", "O", "T", "S", "Z", "J", "L"]): GameState {
  const [first = "I", ...rest] = seedKinds;
  const next = rest.length >= 5 ? rest.slice(0, 5) : [...rest, ...shuffleBag()].slice(0, 5);
  return {
    board: createEmptyBoard(),
    active: createPiece(first),
    next,
    bag: [],
    hold: null,
    canHold: true,
    score: 0,
    lines: 0,
    chain: 0,
    spectrum: 0,
    status: "ready",
    lastEvent: "Ready"
  };
}

export function canPlace(board: Board, piece: Piece): boolean {
  return pieceCells(piece).every(({ x, y }) => {
    if (x < 0 || x >= BOARD_WIDTH || y >= BOARD_HEIGHT) return false;
    if (y < 0) return true;
    return board[y][x] === null;
  });
}

function mergePiece(board: Board, piece: Piece): Board {
  const nextBoard = board.map((row) => row.slice());
  for (const { x, y } of pieceCells(piece)) {
    if (y >= 0 && y < BOARD_HEIGHT && x >= 0 && x < BOARD_WIDTH) {
      nextBoard[y][x] = { kind: piece.kind, hue: piece.hue };
    }
  }
  return nextBoard;
}

export function clearCompletedLines(board: Board) {
  const remaining = board.filter((row) => row.some((cell) => cell === null));
  const cleared = BOARD_HEIGHT - remaining.length;
  const emptyRows = Array.from({ length: cleared }, () => Array<Cell | null>(BOARD_WIDTH).fill(null));
  return { board: [...emptyRows, ...remaining], cleared };
}

function prismPulse(board: Board) {
  const colorCounts = new Map<PieceKind, number>();
  for (const row of board) {
    for (const cell of row) {
      if (cell) colorCounts.set(cell.kind, (colorCounts.get(cell.kind) ?? 0) + 1);
    }
  }
  const target = [...colorCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  if (!target) return { board, cleared: 0 };
  let cleared = 0;
  const pulsed = board.map((row) =>
    row.map((cell) => {
      if (cell?.kind === target) {
        cleared += 1;
        return null;
      }
      return cell;
    })
  );
  return { board: pulsed, cleared };
}

function settle(state: GameState): GameState {
  const merged = mergePiece(state.board, state.active);
  const lineResult = clearCompletedLines(merged);
  const gainedSpectrum = lineResult.cleared * 34 + (state.chain > 0 ? 12 : 0);
  const nextSpectrum = Math.min(132, state.spectrum + gainedSpectrum);
  const shouldPulse = nextSpectrum >= 100 && lineResult.cleared > 0;
  const pulseResult = shouldPulse ? prismPulse(lineResult.board) : { board: lineResult.board, cleared: 0 };
  const draw = drawKind(state.next, state.bag);
  const active = createPiece(draw.kind);
  const chain = lineResult.cleared > 0 ? state.chain + 1 : 0;
  const score =
    state.score +
    [0, 120, 320, 520, 820][lineResult.cleared] * Math.max(1, chain) +
    pulseResult.cleared * 18;
  const lost = !canPlace(pulseResult.board, active);

  return {
    ...state,
    board: pulseResult.board,
    active,
    next: draw.next,
    bag: draw.bag,
    canHold: true,
    score,
    lines: state.lines + lineResult.cleared,
    chain,
    spectrum: shouldPulse ? nextSpectrum - 100 : nextSpectrum,
    status: lost ? "lost" : "playing",
    lastEvent: shouldPulse
      ? `Prism pulse cleared ${pulseResult.cleared}`
      : lineResult.cleared > 0
        ? `Cleared ${lineResult.cleared}`
        : "Landed"
  };
}

export function move(state: GameState, dx: number, dy: number): GameState {
  if (state.status !== "playing") return state;
  const moved = { ...state.active, x: state.active.x + dx, y: state.active.y + dy };
  if (canPlace(state.board, moved)) return { ...state, active: moved, lastEvent: "Move" };
  if (dy > 0) return settle(state);
  return state;
}

export function rotate(state: GameState): GameState {
  if (state.status !== "playing") return state;
  const candidates = [0, -1, 1, -2, 2].map((kick) => ({
    ...state.active,
    rotation: (state.active.rotation + 1) % 4,
    x: state.active.x + kick
  }));
  const rotated = candidates.find((candidate) => canPlace(state.board, candidate));
  return rotated ? { ...state, active: rotated, lastEvent: "Rotate" } : state;
}

export function hardDrop(state: GameState): GameState {
  if (state.status !== "playing") return state;
  let dropped = state.active;
  while (canPlace(state.board, { ...dropped, y: dropped.y + 1 })) {
    dropped = { ...dropped, y: dropped.y + 1 };
  }
  return settle({ ...state, active: dropped, score: state.score + Math.max(0, dropped.y - state.active.y) * 2 });
}

export function holdPiece(state: GameState): GameState {
  if (state.status !== "playing" || !state.canHold) return state;
  if (state.hold) {
    return {
      ...state,
      active: createPiece(state.hold),
      hold: state.active.kind,
      canHold: false,
      lastEvent: "Hold swap"
    };
  }
  const draw = drawKind(state.next, state.bag);
  return {
    ...state,
    active: createPiece(draw.kind),
    next: draw.next,
    bag: draw.bag,
    hold: state.active.kind,
    canHold: false,
    lastEvent: "Hold"
  };
}

export function freezeBend(state: GameState): GameState {
  if (state.status !== "playing" || state.spectrum < 24) return state;
  const board = state.board.map((row) => row.map((cell) => (cell ? { ...cell } : cell)));
  const targetY = Math.min(BOARD_HEIGHT - 1, Math.max(0, state.active.y + 6));
  const targetX = Math.max(0, Math.min(BOARD_WIDTH - 1, state.active.x + 1));
  if (!board[targetY][targetX]) {
    board[targetY][targetX] = { kind: "T", hue: 260, cracked: true };
  }
  return {
    ...state,
    board,
    spectrum: state.spectrum - 24,
    lastEvent: "Freeze bend: time slowed, crack left behind"
  };
}

export function startOrPause(state: GameState): GameState {
  if (state.status === "ready") return { ...state, status: "playing", lastEvent: "Start" };
  if (state.status === "playing") return { ...state, status: "paused", lastEvent: "Paused" };
  if (state.status === "paused") return { ...state, status: "playing", lastEvent: "Resume" };
  return createInitialState();
}

export function ghostPiece(board: Board, active: Piece): Piece {
  let ghost = active;
  while (canPlace(board, { ...ghost, y: ghost.y + 1 })) {
    ghost = { ...ghost, y: ghost.y + 1 };
  }
  return ghost;
}
