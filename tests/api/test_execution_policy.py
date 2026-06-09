from __future__ import annotations

from app.services.container_code_runtime import CONTAINER_CODE_TOOL_NAME
from app.services.execution_policy import (
    build_code_execution_policy,
    execution_policy_task_text,
    requires_code_execution_evidence,
)


def test_requires_code_execution_evidence_for_coding_and_test_tasks() -> None:
    assert requires_code_execution_evidence("請修改 Python 程式並跑測試")
    assert requires_code_execution_evidence("Implement the provider fix and run pytest")
    assert requires_code_execution_evidence("請修改")
    assert requires_code_execution_evidence("請撰寫代碼並產出可執行結果")
    assert requires_code_execution_evidence("請建立 React 原型，新增 UI 與測試")
    assert requires_code_execution_evidence("Create a Vite app prototype")


def test_does_not_require_execution_for_explanation_only_task() -> None:
    assert not requires_code_execution_evidence("為何目前只會寫出代碼而不會執行?")
    assert not requires_code_execution_evidence("為何撰寫代碼的結果沒有自動執行?")
    assert not requires_code_execution_evidence("Evaluate the MXC adoption plan")
    assert not requires_code_execution_evidence("請整理這段 Python 函式的重構方向。")
    assert not requires_code_execution_evidence("請撰寫 README 文件")


def test_build_code_execution_policy_requires_harness_tool_policy_and_code_tool() -> None:
    policy = build_code_execution_policy(
        task_text="請修改 provider 並跑測試",
        harness_modules={"tool_policy": True},
        tool_names=("standard.web.search", CONTAINER_CODE_TOOL_NAME),
        surface="chat",
    )

    assert policy["requires_execution_evidence"] is True
    assert policy["required_tool_names"] == [CONTAINER_CODE_TOOL_NAME]
    assert policy["surface"] == "chat"

    assert (
        build_code_execution_policy(
            task_text="請修改 provider 並跑測試",
            harness_modules={},
            tool_names=("standard.web.search", CONTAINER_CODE_TOOL_NAME),
            surface="chat",
        )
        == {}
    )
    assert (
        build_code_execution_policy(
            task_text="請修改 provider 並跑測試",
            harness_modules={"tool_policy": True},
            tool_names=("standard.web.search",),
            surface="chat",
        )
        == {}
    )


def test_execution_policy_task_text_includes_recent_profile_history() -> None:
    task_text = execution_policy_task_text(
        "請修改",
        (
            {"role": "user", "content": "請找出 provider 為何沒有執行程式"},
            {"role": "assistant", "content": "需要加 tool_choice"},
        ),
    )

    assert "provider" in task_text
    assert task_text.endswith("請修改")
