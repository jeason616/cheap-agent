"""Tests for figure, caption, and reference consistency tools."""

import sys


def test_parse_figures_and_labels():
    from cheap_agent.tools.figures import parse_figures_and_labels_logic

    result = parse_figures_and_labels_logic(tex_path="nonexistent.tex")
    assert "Error" in result
    print("[PASS] parse_figures_and_labels nonexistent file")


def test_check_figure_reference_consistency():
    from cheap_agent.tools.figures import check_figure_reference_consistency_logic

    result = check_figure_reference_consistency_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Error" in result
    print("[PASS] check_figure_reference_consistency nonexistent file")


def test_review_figure_caption():
    from cheap_agent.tools.figures import review_figure_caption_logic

    result = review_figure_caption_logic(caption_text="Visualization results.", use_llm=False)
    assert "Figure Caption Review" in result
    assert "too short" in result.lower() or "vague" in result.lower() or "issue" in result.lower()
    print("[PASS] review_figure_caption vague caption")

    result = review_figure_caption_logic(caption_text="Overall framework of the proposed SCD-DINO method for oriented object detection in SAR images.", use_llm=False)
    assert "Figure Caption Review" in result
    print("[PASS] review_figure_caption good caption")

    result = review_figure_caption_logic(caption_text="", label="", tex_path="", use_llm=False)
    assert "Error" in result
    print("[PASS] review_figure_caption empty input")


def test_review_table_caption():
    from cheap_agent.tools.figures import review_table_caption_logic

    result = review_table_caption_logic(caption_text="Comparison with methods.", use_llm=False)
    assert "Table Caption Review" in result
    print("[PASS] review_table_caption basic")

    result = review_table_caption_logic(caption_text="", label="", tex_path="", use_llm=False)
    assert "Error" in result
    print("[PASS] review_table_caption empty input")


def test_check_caption_text_consistency():
    from cheap_agent.tools.figures import check_caption_text_consistency_logic

    result = check_caption_text_consistency_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Error" in result
    print("[PASS] check_caption_text_consistency nonexistent file")


def test_check_equation_reference_consistency():
    from cheap_agent.tools.figures import check_equation_reference_consistency_logic

    result = check_equation_reference_consistency_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Error" in result
    print("[PASS] check_equation_reference_consistency nonexistent file")


if __name__ == "__main__":
    print("=== figure tools tests ===\n")
    test_parse_figures_and_labels()
    test_check_figure_reference_consistency()
    print()
    test_review_figure_caption()
    print()
    test_review_table_caption()
    print()
    test_check_caption_text_consistency()
    test_check_equation_reference_consistency()
    print("\n=== all figure tools tests passed ===")
