"""Tests for reviewer comments and rebuttal/response tools."""

import sys


def test_parse_reviewer_comments():
    from cheap_agent.tools.rebuttal import parse_reviewer_comments_logic

    result = parse_reviewer_comments_logic(
        comments_text="Reviewer 1:\nComment 1: The novelty is unclear.\nComment 2: Missing ablation study.",
        use_llm=False,
    )
    assert "Parsed Reviewer Comments" in result
    assert "Reviewer" in result
    assert "novelty" in result.lower() or "ablation" in result.lower()
    print("[PASS] parse_reviewer_comments basic")

    result = parse_reviewer_comments_logic(comments_text="", use_llm=False)
    assert "Error" in result
    print("[PASS] parse_reviewer_comments empty input")


def test_group_reviewer_concerns():
    from cheap_agent.tools.rebuttal import group_reviewer_concerns_logic

    result = group_reviewer_concerns_logic(
        comments_text="Reviewer 1:\nComment 1: Novelty unclear.\nReviewer 2:\nComment 1: Novelty needs clarification.",
        use_llm=False,
    )
    assert "Reviewer Concern Groups" in result
    assert "novelty" in result.lower()
    print("[PASS] group_reviewer_concerns basic")

    result = group_reviewer_concerns_logic(comments_text="", use_llm=False)
    assert "Error" in result
    print("[PASS] group_reviewer_concerns empty input")


def test_map_comments_to_revisions():
    from cheap_agent.tools.rebuttal import map_comments_to_revisions_logic

    result = map_comments_to_revisions_logic(
        comments_text="Reviewer 1:\nComment 1: Missing ablation for Soft Top-K.",
        use_llm=False,
    )
    assert "Comment-to-Revision Map" in result
    assert "Experiments" in result or "Ablation" in result
    print("[PASS] map_comments_to_revisions basic")

    result = map_comments_to_revisions_logic(comments_text="", use_llm=False)
    assert "Error" in result
    print("[PASS] map_comments_to_revisions empty input")


def test_check_response_completeness():
    from cheap_agent.tools.rebuttal import check_response_completeness_logic

    result = check_response_completeness_logic(
        comments_text="Reviewer 1:\nComment 1: Novelty unclear.\nComment 2: Missing ablation.",
        response_text="R1-C1: We thank the reviewer. We have revised the Introduction.\nR1-C2: We added ablation in Section 4.",
        use_llm=False,
    )
    assert "Response Completeness Check" in result
    print("[PASS] check_response_completeness basic")

    result = check_response_completeness_logic(
        comments_text="Reviewer 1:\nComment 1: Novelty unclear.",
        response_text="",
        use_llm=False,
    )
    assert "Error" in result
    print("[PASS] check_response_completeness empty response")

    result = check_response_completeness_logic(
        comments_text="",
        response_text="We thank the reviewer.",
        use_llm=False,
    )
    assert "Error" in result
    print("[PASS] check_response_completeness empty comments")


def test_review_response_tone():
    from cheap_agent.tools.rebuttal import review_response_tone_logic

    result = review_response_tone_logic(
        response_text="The reviewer misunderstood our method. We disagree with this comment.",
        use_llm=False,
    )
    assert "Response Tone Review" in result
    assert "defensive" in result.lower() or "misunderstood" in result.lower()
    print("[PASS] review_response_tone defensive")

    result = review_response_tone_logic(
        response_text="We thank the reviewer for this insightful comment. We have revised the manuscript to clarify.",
        use_llm=False,
    )
    assert "Response Tone Review" in result
    print("[PASS] review_response_tone professional")

    result = review_response_tone_logic(response_text="", use_llm=False)
    assert "Error" in result
    print("[PASS] review_response_tone empty input")


def test_draft_response_outline():
    from cheap_agent.tools.rebuttal import draft_response_outline_logic

    result = draft_response_outline_logic(
        comments_text="Reviewer 1:\nComment 1: Novelty unclear compared with DINO.",
        use_llm=False,
    )
    assert "Response Outline" in result
    assert "R1" in result
    print("[PASS] draft_response_outline basic")

    result = draft_response_outline_logic(comments_text="", use_llm=False)
    assert "Error" in result
    print("[PASS] draft_response_outline empty input")


if __name__ == "__main__":
    print("=== rebuttal tools tests ===\n")
    test_parse_reviewer_comments()
    print()
    test_group_reviewer_concerns()
    print()
    test_map_comments_to_revisions()
    print()
    test_check_response_completeness()
    print()
    test_review_response_tone()
    print()
    test_draft_response_outline()
    print("\n=== all rebuttal tools tests passed ===")
