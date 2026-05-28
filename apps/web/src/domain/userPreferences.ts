const modelStorageKey = "harnessdiff.model";
const reasoningEffortStorageKey = "harnessdiff.reasoningEffort";

export const modelOptions = ["gpt-5.4-mini", "gpt-5.4", "gpt-5.5"] as const;
export const reasoningEffortOptions = ["low", "medium", "high", "xhigh"] as const;

export type ModelOption = (typeof modelOptions)[number];
export type ReasoningEffortOption = (typeof reasoningEffortOptions)[number];

export const defaultModel: ModelOption = "gpt-5.4-mini";
export const defaultReasoningEffort: ReasoningEffortOption = "medium";

export function readPreferredModel(storage: Storage | undefined = safeLocalStorage()): string {
  return readOption(storage, modelStorageKey, modelOptions, defaultModel);
}

export function writePreferredModel(value: string, storage: Storage | undefined = safeLocalStorage()) {
  writeOption(storage, modelStorageKey, value, modelOptions);
}

export function readPreferredReasoningEffort(
  storage: Storage | undefined = safeLocalStorage()
): string {
  return readOption(
    storage,
    reasoningEffortStorageKey,
    reasoningEffortOptions,
    defaultReasoningEffort
  );
}

export function writePreferredReasoningEffort(
  value: string,
  storage: Storage | undefined = safeLocalStorage()
) {
  writeOption(storage, reasoningEffortStorageKey, value, reasoningEffortOptions);
}

function readOption<T extends readonly string[]>(
  storage: Storage | undefined,
  key: string,
  allowed: T,
  fallback: T[number]
) {
  if (!storage) {
    return fallback;
  }
  try {
    const value = storage.getItem(key);
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

function writeOption<T extends readonly string[]>(
  storage: Storage | undefined,
  key: string,
  value: string,
  allowed: T
) {
  if (!storage || !allowed.includes(value)) {
    return;
  }
  try {
    storage.setItem(key, value);
  } catch {
    // Storage can be blocked by browser policy; the UI state should still update.
  }
}

function safeLocalStorage() {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}
