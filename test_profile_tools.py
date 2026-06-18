"""Tests for Phase 7 project profile and onboarding tools."""

import sys


def test_build_project_profile_v2():
    from tools_profile import build_project_profile_v2_logic

    result = build_project_profile_v2_logic(use_llm=False, force_refresh=True)
    assert "Project Profile v2" in result
    assert "main language" in result.lower() or "Basic:" in result
    assert "Entry points" in result
    assert "Configuration" in result
    assert "Testing" in result
    assert "Codex first-read order" in result
    print("[PASS] build_project_profile_v2 normal")

    result = build_project_profile_v2_logic(use_llm=False, force_refresh=False)
    assert "Project Profile v2" in result
    print("[PASS] build_project_profile_v2 cached")


def test_get_codex_onboarding_pack():
    from tools_profile import get_codex_onboarding_pack_logic

    result = get_codex_onboarding_pack_logic()
    assert "Codex Onboarding Pack" in result
    assert "Start here" in result
    assert "Key conventions" in result
    assert "Do not forget" in result
    print("[PASS] get_codex_onboarding_pack normal")

    result = get_codex_onboarding_pack_logic(task_description="修复训练报错")
    assert "Codex Onboarding Pack" in result
    assert "Recommended tools" in result
    print("[PASS] get_codex_onboarding_pack with task")

    result = get_codex_onboarding_pack_logic(max_items=5)
    assert "Codex Onboarding Pack" in result
    print("[PASS] get_codex_onboarding_pack max_items")


def test_infer_project_runbook():
    from tools_profile import infer_project_runbook_logic

    result = infer_project_runbook_logic(use_llm=False)
    assert "Project Runbook" in result
    assert "Install" in result
    assert "Start" in result
    assert "Test" in result
    assert "do not execute" in result.lower() or "not execute" in result.lower()
    print("[PASS] infer_project_runbook normal")

    result = infer_project_runbook_logic(use_llm=False, include_commands=True)
    assert "Project Runbook" in result
    print("[PASS] infer_project_runbook with commands")


def test_recommend_workflow_for_task():
    from tools_profile import recommend_workflow_for_task_logic

    result = recommend_workflow_for_task_logic("traceback error in train.py")
    assert "Recommended Workflow" in result
    assert "traceback_error" in result
    assert "analyze_traceback_with_context" in result
    print("[PASS] recommend_workflow traceback_error")

    result = recommend_workflow_for_task_logic("CUDA out of memory")
    assert "training_error" in result
    assert "diagnose_training_error" in result
    print("[PASS] recommend_workflow training_error")

    result = recommend_workflow_for_task_logic("change config file settings")
    assert "config" in result.lower()
    print("[PASS] recommend_workflow config_change")

    result = recommend_workflow_for_task_logic("review this diff")
    assert "code_review" in result or "diff" in result.lower()
    print("[PASS] recommend_workflow code_review")

    result = recommend_workflow_for_task_logic("")
    assert "Error" in result
    print("[PASS] recommend_workflow empty input")


def test_explain_project_conventions():
    from tools_profile import explain_project_conventions_logic

    result = explain_project_conventions_logic(use_llm=False)
    assert "Project Conventions" in result
    assert "MCP tools" in result
    assert "server.py" in result
    assert "stdout" in result.lower() or "stdio" in result.lower()
    assert "WORKSPACE_ROOT" in result
    assert "tools_" in result
    print("[PASS] explain_project_conventions normal")


if __name__ == "__main__":
    print("=== profile tools tests ===\n")
    test_build_project_profile_v2()
    print()
    test_get_codex_onboarding_pack()
    print()
    test_infer_project_runbook()
    print()
    test_recommend_workflow_for_task()
    print()
    test_explain_project_conventions()
    print("\n=== all profile tools tests passed ===")
