import crypto from "node:crypto";
import { readFile } from "node:fs/promises";

function writeJson(payload) {
  process.stdout.write(JSON.stringify(payload));
}

async function loadSdk() {
  try {
    return { sdk: await import("@microsoft/mxc-sdk") };
  } catch (error) {
    return {
      error: {
        ok: false,
        available: false,
        error_type: "mxc_sdk_missing",
        message: `Unable to import @microsoft/mxc-sdk: ${error?.message ?? String(error)}`,
        mxc_sdk_present: false,
      },
    };
  }
}

function stableHash(value) {
  return crypto.createHash("sha256").update(stableStringify(value)).digest("hex");
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function mergeUnique(left, right) {
  return Array.from(new Set([...(left ?? []), ...(right ?? [])]));
}

function buildConfig(sdk, request) {
  const policy = structuredClone(request.policy ?? {});
  const tools = typeof sdk.getAvailableToolsPolicy === "function" ? sdk.getAvailableToolsPolicy(process.env) : null;
  if (tools?.readonlyPaths) {
    policy.filesystem ??= {};
    policy.filesystem.readonlyPaths = mergeUnique(policy.filesystem.readonlyPaths, tools.readonlyPaths);
  }
  let config =
    typeof sdk.createConfigFromPolicy === "function" ? sdk.createConfigFromPolicy(policy) : structuredClone(policy);
  config.process ??= {};
  config.process.commandLine = policy.process?.commandLine;
  config.process.cwd = policy.process?.cwd;
  config.process.env = policy.process?.env ?? [];
  config.process.timeout = policy.process?.timeout;
  return { config, policy };
}

async function status() {
  const loaded = await loadSdk();
  if (loaded.error) {
    return loaded.error;
  }
  const { sdk } = loaded;
  let support = { isSupported: true };
  if (typeof sdk.getPlatformSupport === "function") {
    support = sdk.getPlatformSupport();
  }
  return {
    ok: true,
    available: Boolean(support?.isSupported),
    mxc_sdk_present: true,
    platform: process.platform,
    arch: process.arch,
    support,
    message: support?.isSupported ? "" : support?.message || "MXC is not supported on this host.",
  };
}

async function run(request) {
  const loaded = await loadSdk();
  if (loaded.error) {
    return loaded.error;
  }
  const { sdk } = loaded;
  if (typeof sdk.spawnSandboxFromConfig !== "function") {
    return {
      ok: false,
      error_type: "mxc_sdk_missing_spawn",
      message: "@microsoft/mxc-sdk does not expose spawnSandboxFromConfig.",
    };
  }
  const { config, policy } = buildConfig(sdk, request);
  const policyHash = stableHash(policy);
  let child;
  try {
    child = sdk.spawnSandboxFromConfig(config, { usePty: false, experimental: request.experimental === true });
  } catch (error) {
    return {
      ok: false,
      error_type: "mxc_spawn_failed",
      message: error?.message ?? String(error),
      policy_hash: policyHash,
    };
  }

  let stdout = "";
  let stderr = "";
  child.stdout?.on("data", (chunk) => {
    stdout += chunk.toString("utf8");
  });
  child.stderr?.on("data", (chunk) => {
    stderr += chunk.toString("utf8");
  });

  const exitCode = await new Promise((resolve) => {
    const timeoutMs = Math.max(1000, Number(request.timeout_seconds || 120) * 1000 + 5000);
    const timer = setTimeout(() => {
      stderr += "\nMXC runner timed out";
      try {
        child.kill?.();
      } catch {
        // Best-effort cleanup only.
      }
      resolve(124);
    }, timeoutMs);
    child.on("error", (error) => {
      clearTimeout(timer);
      stderr += `\n${error?.message ?? String(error)}`;
      resolve(127);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve(typeof code === "number" ? code : 0);
    });
  });

  return {
    ok: true,
    exit_code: exitCode,
    stdout,
    stderr,
    containment: config.containment ?? policy.containment,
    policy_hash: policyHash,
    enforcement_gaps: request.enforcement_gaps ?? [],
  };
}

async function main() {
  const requestPath = process.argv[2];
  if (!requestPath) {
    writeJson({ ok: false, error_type: "missing_request", message: "request path is required" });
    return;
  }
  const request = JSON.parse(await readFile(requestPath, "utf8"));
  if (request.mode === "status") {
    writeJson(await status());
    return;
  }
  if (request.mode === "run") {
    writeJson(await run(request));
    return;
  }
  writeJson({ ok: false, error_type: "invalid_mode", message: `Unsupported MXC runner mode: ${request.mode}` });
}

main().catch((error) => {
  writeJson({ ok: false, error_type: error?.name ?? "Error", message: error?.message ?? String(error) });
});
