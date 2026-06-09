from __future__ import annotations

from typing import Any

from app.services.container_code_runtime import CONTAINER_CODE_TOOL_NAME

EXECUTION_POLICY_VERSION = 1

_EXECUTION_TERMS = (
    "run test",
    "run tests",
    "run pytest",
    "pytest",
    "unit test",
    "integration test",
    "e2e",
    "npm test",
    "npm run",
    "pnpm test",
    "pnpm run",
    "yarn test",
    "cargo test",
    "go test",
    "build",
    "compile",
    "execute",
    "執行",
    "跑測試",
    "執行測試",
    "測試",
    "建置",
    "編譯",
    "驗證",
)

_IMPLEMENTATION_TERMS = (
    "implement",
    "modify",
    "fix",
    "debug",
    "patch",
    "refactor",
    "write code",
    "add code",
    "update code",
    "修改",
    "實作",
    "修正",
    "除錯",
    "重構",
    "寫程式",
    "寫代碼",
    "加測試",
    "補測試",
    "請修改",
)

_CODE_CREATION_TERMS = (
    "create",
    "develop",
    "scaffold",
    "prototype",
    "新增",
    "建立",
    "撰寫",
    "開發",
    "製作",
    "打造",
    "建構",
)

_CODE_CONTEXT_TERMS = (
    "code",
    "repo",
    "repository",
    "runtime",
    "provider",
    "orchestrator",
    "api",
    "function",
    "class",
    "python",
    "typescript",
    "javascript",
    "node",
    "react",
    "vite",
    "pytest",
    "package.json",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    "程式",
    "代碼",
    "程式碼",
    "檔案",
    "測試",
    "錯誤",
    "報錯",
    "失敗",
    "後端",
    "前端",
)

_CODE_ARTIFACT_CONTEXT_TERMS = (
    "code",
    "app",
    "component",
    "frontend",
    "backend",
    "repo",
    "repository",
    "api",
    "function",
    "class",
    "python",
    "typescript",
    "javascript",
    "node",
    "react",
    "vite",
    "vitest",
    "pytest",
    "package.json",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    "程式",
    "代碼",
    "程式碼",
    "原型",
    "元件",
    "前端",
    "後端",
    "測試",
)

_EXPLANATION_STARTS = (
    "why ",
    "explain",
    "describe",
    "evaluate",
    "compare",
    "plan",
    "為何",
    "為什麼",
    "說明",
    "解釋",
    "評估",
    "比較",
    "規劃",
    "整理",
)

_EXPLANATION_ACTION_TERMS = (
    "please fix",
    "please implement",
    "please create",
    "please build",
    "fix ",
    "implement ",
    "請修改",
    "請修正",
    "請實作",
    "請建立",
    "請新增",
    "請開發",
    "請製作",
)

_PLANNING_ONLY_HINTS = (
    "重構方向",
    "重構建議",
    "refactor direction",
    "refactoring direction",
    "refactor plan",
)


def build_code_execution_policy(
    *,
    task_text: str,
    harness_modules: dict[str, bool],
    tool_names: tuple[str, ...],
    surface: str,
) -> dict[str, Any]:
    if not harness_modules.get("tool_policy", False):
        return {}
    if CONTAINER_CODE_TOOL_NAME not in tool_names:
        return {}
    if not requires_code_execution_evidence(task_text):
        return {}
    return {
        "schema_version": EXECUTION_POLICY_VERSION,
        "requires_execution_evidence": True,
        "required_tool_names": [CONTAINER_CODE_TOOL_NAME],
        "reason": "coding_task_requires_executable_evidence",
        "surface": surface,
    }


def requires_code_execution_evidence(task_text: str) -> bool:
    normalized = " ".join(task_text.lower().split())
    if not normalized:
        return False

    has_execution = _contains_any(normalized, _EXECUTION_TERMS)
    has_implementation = _contains_any(normalized, _IMPLEMENTATION_TERMS)
    has_code_context = _contains_any(normalized, _CODE_CONTEXT_TERMS)
    has_code_creation = _contains_any(normalized, _CODE_CREATION_TERMS)
    has_code_artifact_context = _contains_any(
        normalized, _CODE_ARTIFACT_CONTEXT_TERMS
    )
    has_code_creation_task = has_code_creation and has_code_artifact_context
    starts_as_explanation = normalized.startswith(_EXPLANATION_STARTS)
    has_explicit_action_after_explanation = _contains_any(
        normalized, _EXPLANATION_ACTION_TERMS
    )
    if starts_as_explanation and not has_explicit_action_after_explanation:
        return False
    if not has_execution and _contains_any(normalized, _PLANNING_ONLY_HINTS):
        return False
    if not has_execution and not has_implementation and not has_code_creation_task:
        return False
    if has_execution:
        return True
    if has_implementation and has_code_context:
        return True
    if has_code_creation_task:
        return True

    return has_implementation and not starts_as_explanation


def execution_policy_task_text(
    prompt: str,
    conversation_messages: tuple[dict[str, str], ...],
    *,
    max_messages: int = 6,
) -> str:
    parts: list[str] = []
    for message in conversation_messages[-max_messages:]:
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
    if prompt.strip():
        parts.append(prompt.strip())
    return "\n".join(parts)


def apply_execution_policy_instructions(
    instructions: str, execution_policy: dict[str, Any]
) -> str:
    if not execution_policy.get("requires_execution_evidence"):
        return instructions
    required_tools = execution_policy.get("required_tool_names") or ()
    required = ", ".join(str(tool) for tool in required_tools)
    return (
        f"{instructions}\n\n"
        "Execution evidence requirement:\n"
        f"- This task requires executable evidence from: {required}.\n"
        "- Before the final answer, call the required code execution tool at least once "
        "with a concrete command that validates the implementation, test, build, or runtime behavior.\n"
        "- If execution fails or the tool is unavailable, report that failure explicitly; "
        "do not present unexecuted code as verified."
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
