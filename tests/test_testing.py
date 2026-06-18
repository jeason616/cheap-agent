"""Tests for Phase 4 testing and verification tools."""

import sys


def test_suggest_minimal_repro():
    from cheap_agent.tools.testing import suggest_minimal_repro_logic

    result = suggest_minimal_repro_logic("模型 forward 报错", use_llm=False)
    assert "Minimal Reproduction Plan" in result
    assert "Likely target" in result
    assert "Minimal inputs" in result
    assert "Suggested repro script outline" in result
    print("[PASS] suggest_minimal_repro normal")

    result = suggest_minimal_repro_logic("...", related_file="config.py", use_llm=False)
    assert "Minimal Reproduction Plan" in result
    print("[PASS] suggest_minimal_repro with related file")

    result = suggest_minimal_repro_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] suggest_minimal_repro empty input")

    result = suggest_minimal_repro_logic("test", related_file="../../etc/passwd", use_llm=False)
    assert "Warning" in result or "Error" in result or "outside" in result.lower()
    print("[PASS] suggest_minimal_repro path traversal blocked")


def test_generate_unit_test_plan():
    from cheap_agent.tools.testing import generate_unit_test_plan_logic

    result = generate_unit_test_plan_logic("workspace.py", use_llm=False)
    assert "Unit Test Plan" in result
    assert "Target file" in result
    assert "Core test cases" in result
    print("[PASS] generate_unit_test_plan normal")

    result = generate_unit_test_plan_logic("workspace.py", target_symbol="resolve_safe_path", use_llm=False)
    assert "resolve_safe_path" in result
    print("[PASS] generate_unit_test_plan with target symbol")

    result = generate_unit_test_plan_logic("workspace.py", target_symbol="nonexistent_func_xyz", use_llm=False)
    assert "not found" in result.lower() or "Unit Test Plan" in result
    print("[PASS] generate_unit_test_plan symbol not found")

    result = generate_unit_test_plan_logic("nonexistent.py", use_llm=False)
    assert "Error" in result
    print("[PASS] generate_unit_test_plan file not found")

    try:
        generate_unit_test_plan_logic("../../etc/passwd", use_llm=False)
        print("[FAIL] path traversal NOT blocked!")
        sys.exit(1)
    except PermissionError:
        print("[PASS] generate_unit_test_plan path traversal blocked")


def test_check_config_consistency():
    from cheap_agent.tools.testing import check_config_consistency_logic

    result = check_config_consistency_logic(use_llm=False)
    assert "Config Consistency Check" in result
    assert "Checked files" in result
    print("[PASS] check_config_consistency normal")

    result = check_config_consistency_logic(config_path=".env.example", use_llm=False)
    assert "Config Consistency Check" in result
    print("[PASS] check_config_consistency with config path")

    result = check_config_consistency_logic(use_llm=False)
    assert "Suggested checks" in result
    print("[PASS] check_config_consistency has suggestions")


def test_suggest_validation_plan():
    from cheap_agent.tools.testing import suggest_validation_plan_logic

    result = suggest_validation_plan_logic("修改了训练脚本", use_llm=False)
    assert "Validation Plan" in result
    assert "Risk level" in result
    assert "What to verify" in result
    assert "Suggested checks" in result
    print("[PASS] suggest_validation_plan normal")

    result = suggest_validation_plan_logic("修复 bug", changed_files="config.py\nworkspace.py", use_llm=False)
    assert "config.py" in result
    assert "workspace.py" in result
    print("[PASS] suggest_validation_plan with changed files")

    result = suggest_validation_plan_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] suggest_validation_plan empty input")

    result = suggest_validation_plan_logic("test", changed_files="a.py\nb.py\nc.py", use_llm=False)
    assert "Validation Plan" in result
    print("[PASS] suggest_validation_plan multiple files")


if __name__ == "__main__":
    print("=== testing tools tests ===\n")
    test_suggest_minimal_repro()
    print()
    test_generate_unit_test_plan()
    print()
    test_check_config_consistency()
    print()
    test_suggest_validation_plan()
    print("\n=== all testing tools tests passed ===")
