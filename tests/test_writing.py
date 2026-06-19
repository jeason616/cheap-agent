"""Tests for paper language and IEEE style review tools."""

import sys


def test_review_academic_paragraph():
    from cheap_agent.tools.writing import review_academic_paragraph_logic

    result = review_academic_paragraph_logic("Our method significantly outperforms all baselines.", use_llm=False)
    assert "Academic Paragraph Review" in result
    assert "over-strong" in result.lower() or "issue" in result.lower()
    print("[PASS] review_academic_paragraph over-strong claim")

    result = review_academic_paragraph_logic("We can see that the results are good.", use_llm=False)
    assert "informal" in result.lower() or "issue" in result.lower()
    print("[PASS] review_academic_paragraph informal expression")

    result = review_academic_paragraph_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] review_academic_paragraph empty input")


def test_check_abstract_quality():
    from cheap_agent.tools.writing import check_abstract_quality_logic

    result = check_abstract_quality_logic(
        abstract_text="We propose a novel method for object detection. Experiments show our method achieves state-of-the-art performance.",
        use_llm=False,
    )
    assert "Abstract Quality Check" in result
    assert "Coverage" in result
    print("[PASS] check_abstract_quality basic")

    result = check_abstract_quality_logic(abstract_text="", tex_path="", use_llm=False)
    assert "Error" in result
    print("[PASS] check_abstract_quality empty input")


def test_check_introduction_logic():
    from cheap_agent.tools.writing import check_introduction_logic_logic

    result = check_introduction_logic_logic(
        introduction_text="Recently, object detection has attracted much attention. We propose a new method.",
        use_llm=False,
    )
    assert "Introduction Logic Check" in result
    assert "logic chain" in result.lower() or "logic" in result.lower()
    print("[PASS] check_introduction_logic basic")

    result = check_introduction_logic_logic(introduction_text="", tex_path="", use_llm=False)
    assert "Error" in result
    print("[PASS] check_introduction_logic empty input")


def test_check_contribution_clarity():
    from cheap_agent.tools.writing import check_contribution_clarity_logic

    result = check_contribution_clarity_logic(
        contribution_text="The main contributions are as follows:\n- We propose a novel scatter descriptor.\n- We design a soft top-k selector.",
        use_llm=False,
    )
    assert "Contribution Clarity Check" in result
    print("[PASS] check_contribution_clarity basic")

    result = check_contribution_clarity_logic(contribution_text="", tex_path="", use_llm=False)
    assert "Error" in result
    print("[PASS] check_contribution_clarity empty input")


def test_check_term_consistency():
    from cheap_agent.tools.writing import check_term_consistency_logic

    result = check_term_consistency_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Error" in result
    print("[PASS] check_term_consistency nonexistent file")


def test_check_ieee_style():
    from cheap_agent.tools.writing import check_ieee_style_logic

    result = check_ieee_style_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Error" in result
    print("[PASS] check_ieee_style nonexistent file")


if __name__ == "__main__":
    print("=== writing tools tests ===\n")
    test_review_academic_paragraph()
    print()
    test_check_abstract_quality()
    print()
    test_check_introduction_logic()
    print()
    test_check_contribution_clarity()
    print()
    test_check_term_consistency()
    print()
    test_check_ieee_style()
    print("\n=== all writing tools tests passed ===")
