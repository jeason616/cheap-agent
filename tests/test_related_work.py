"""Tests for Related Work and reference enhancement tools."""

import sys


def test_group_references_by_topic():
    from cheap_agent.tools.related_work import group_references_by_topic_logic

    result = group_references_by_topic_logic(bib_path="nonexistent.bib", use_llm=False)
    assert "Error" in result
    print("[PASS] group_references_by_topic nonexistent bib")


def test_check_related_work_coverage():
    from cheap_agent.tools.related_work import check_related_work_coverage_logic

    result = check_related_work_coverage_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Related Work Coverage" in result or "Error" in result
    print("[PASS] check_related_work_coverage")


def test_check_reference_recency():
    from cheap_agent.tools.related_work import check_reference_recency_logic

    result = check_reference_recency_logic(bib_path="nonexistent.bib", use_llm=False)
    assert "Error" in result
    print("[PASS] check_reference_recency nonexistent bib")


def test_check_bibtex_quality():
    from cheap_agent.tools.related_work import check_bibtex_quality_logic

    result = check_bibtex_quality_logic(bib_path="nonexistent.bib", use_llm=False)
    assert "Error" in result
    print("[PASS] check_bibtex_quality nonexistent bib")


def test_suggest_citation_positions():
    from cheap_agent.tools.related_work import suggest_citation_positions_logic

    result = suggest_citation_positions_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Error" in result or "Citation Position" in result
    print("[PASS] suggest_citation_positions")


def test_build_related_work_outline():
    from cheap_agent.tools.related_work import build_related_work_outline_logic

    result = build_related_work_outline_logic(tex_path="nonexistent.tex", use_llm=False)
    assert "Related Work Outline" in result or "Error" in result
    print("[PASS] build_related_work_outline")


def test_classify_entry():
    from cheap_agent.tools.related_work import _classify_entry

    entry = {"key": "zhang2021sarship", "title": "SAR ship detection with deep learning", "year": "2021"}
    topic, reason = _classify_entry(entry)
    assert "SAR" in topic or "ship" in topic.lower() or "detection" in topic.lower()
    print("[PASS] _classify_entry SAR detection")

    entry = {"key": "li2023dino", "title": "DINO: DETR with improved denoising anchor boxes", "year": "2023"}
    topic, reason = _classify_entry(entry)
    assert "DETR" in topic or "DINO" in topic or "transformer" in topic
    print("[PASS] _classify_entry DINO/DETR")

    entry = {"key": "unknown2020", "title": "Some unrelated paper", "year": "2020"}
    topic, reason = _classify_entry(entry)
    assert topic == "uncertain"
    print("[PASS] _classify_entry uncertain")


if __name__ == "__main__":
    print("=== related work tools tests ===\n")
    test_classify_entry()
    print()
    test_group_references_by_topic()
    test_check_related_work_coverage()
    test_check_reference_recency()
    test_check_bibtex_quality()
    test_suggest_citation_positions()
    test_build_related_work_outline()
    print("\n=== all related work tools tests passed ===")
