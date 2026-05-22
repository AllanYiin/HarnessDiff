import type { InputMode } from "../types";

export function nextInputModeAfterCompletedTurn(
  completedTurnIndex: number,
  currentMode: InputMode
): InputMode {
  return completedTurnIndex === 0 ? "independent" : currentMode;
}

