import { describe, expect, it } from "vitest";

import {
  defaultModel,
  defaultReasoningEffort,
  readPreferredModel,
  readPreferredReasoningEffort,
  writePreferredModel,
  writePreferredReasoningEffort
} from "./userPreferences";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

describe("user preference persistence", () => {
  it("persists and reads the last selected model and reasoning effort", () => {
    const storage = new MemoryStorage();

    writePreferredModel("gpt-5.5", storage);
    writePreferredReasoningEffort("xhigh", storage);

    expect(readPreferredModel(storage)).toBe("gpt-5.5");
    expect(readPreferredReasoningEffort(storage)).toBe("xhigh");
  });

  it("falls back when stored values are invalid", () => {
    const storage = new MemoryStorage();
    storage.setItem("harnessdiff.model", "not-a-model");
    storage.setItem("harnessdiff.reasoningEffort", "maximum");

    expect(readPreferredModel(storage)).toBe(defaultModel);
    expect(readPreferredReasoningEffort(storage)).toBe(defaultReasoningEffort);
  });
});
