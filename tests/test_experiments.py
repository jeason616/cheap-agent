"""Tests for experiment results and table verification tools."""

import sys


def test_parse_latex_tables_detailed():
    from cheap_agent.tools.experiments import parse_latex_tables_detailed

    result = parse_latex_tables_detailed(tex_path="nonexistent.tex")
    assert "Error" in result
    print("[PASS] parse_latex_tables nonexistent file")


def test_extract_experiment_claims():
    from cheap_agent.tools.experiments import extract_experiment_claims_logic

    result = extract_experiment_claims_logic(tex_path="nonexistent.tex")
    assert "Error" in result
    print("[PASS] extract_experiment_claims nonexistent file")


def test_check_result_claim_consistency():
    from cheap_agent.tools.experiments import check_result_claim_consistency_logic

    result = check_result_claim_consistency_logic(tex_path="nonexistent.tex")
    assert "Error" in result or "No" in result
    print("[PASS] check_result_claim_consistency")


def test_check_ablation_logic():
    from cheap_agent.tools.experiments import check_ablation_logic_logic

    result = check_ablation_logic_logic(tex_path="nonexistent.tex")
    assert "Error" in result
    print("[PASS] check_ablation_logic nonexistent file")


def test_check_metric_consistency():
    from cheap_agent.tools.experiments import check_metric_consistency_logic

    result = check_metric_consistency_logic(tex_path="nonexistent.tex")
    assert "Error" in result
    print("[PASS] check_metric_consistency nonexistent file")


def test_clean_cell():
    from cheap_agent.tools.experiments import _clean_cell

    assert _clean_cell("\\textbf{82.4}") == "82.4"
    assert _clean_cell("$82.4$") == "82.4"
    assert _clean_cell("82.4\\%") == "82.4%"
    print("[PASS] _clean_cell")


def test_is_bold():
    from cheap_agent.tools.experiments import _is_bold

    assert _is_bold("\\textbf{82.4}") is True
    assert _is_bold("82.4") is False
    print("[PASS] _is_bold")


def test_extract_numeric():
    from cheap_agent.tools.experiments import _extract_numeric

    assert _extract_numeric("82.4") == "82.4"
    assert _extract_numeric("\\textbf{82.4}") == "82.4"
    assert _extract_numeric("N/A") is None
    print("[PASS] _extract_numeric")


def test_parse_tabular_rows():
    from cheap_agent.tools.experiments import _parse_tabular_rows

    tabular = """\\toprule
Method & mAP & AP50 \\\\
\\midrule
Baseline & 78.3 & 85.1 \\\\
Ours & \\textbf{82.4} & \\textbf{88.9} \\\\
\\bottomrule"""

    rows = _parse_tabular_rows(tabular)
    assert len(rows) >= 2
    print("[PASS] _parse_tabular_rows")


if __name__ == "__main__":
    print("=== experiment tools tests ===\n")
    test_clean_cell()
    test_is_bold()
    test_extract_numeric()
    test_parse_tabular_rows()
    print()
    test_parse_latex_tables_detailed()
    test_extract_experiment_claims()
    test_check_result_claim_consistency()
    test_check_ablation_logic()
    test_check_metric_consistency()
    print("\n=== all experiment tools tests passed ===")
