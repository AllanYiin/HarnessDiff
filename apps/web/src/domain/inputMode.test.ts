import { describe, expect, it } from "vitest";

import { nextInputModeAfterCompletedTurn } from "./inputMode";

describe("nextInputModeAfterCompletedTurn", () => {
  it("switches to independent input after the first completed turn", () => {
    expect(nextInputModeAfterCompletedTurn(0, "integrated")).toBe("independent");
  });

  it("keeps the selected mode after later turns", () => {
    expect(nextInputModeAfterCompletedTurn(2, "integrated")).toBe("integrated");
    expect(nextInputModeAfterCompletedTurn(2, "independent")).toBe("independent");
  });
});

