"""Tests for Phase 5 code review tools."""

import sys

SAMPLE_DIFF = """diff --git a/src/train.py b/src/train.py
--- a/src/train.py
+++ b/src/train.py
@@ -10,3 +10,5 @@
 import torch
+import os
+API_KEY=secret123
 
-def train(config):
+def train(config, batch_size=32):
+    print("starting training")
     pass
"""


def test_parse_changed_files_from_diff():
    from tools_review import parse_changed_files_from_diff

    files = parse_changed_files_from_diff(SAMPLE_DIFF)
    assert "src/train.py" in files
    print("[PASS] parse_changed_files_from_diff")

    files = parse_changed_files_from_diff("")
    assert len(files) == 0
    print("[PASS] parse_changed_files_from_diff empty")


def test_parse_diff_summary():
    from tools_review import parse_diff_summary

    summary = parse_diff_summary(SAMPLE_DIFF)
    assert len(summary["files"]) >= 1
    assert summary["total_added"] > 0
    assert summary["files"][0]["path"] == "src/train.py"
    print("[PASS] parse_diff_summary normal")

    summary = parse_diff_summary("")
    assert len(summary["files"]) == 0
    assert summary["total_added"] == 0
    print("[PASS] parse_diff_summary empty")


def test_extract_symbols_from_diff():
    from tools_review import extract_symbols_from_diff

    symbols = extract_symbols_from_diff(SAMPLE_DIFF)
    assert "train" in symbols
    print("[PASS] extract_symbols_from_diff")

    symbols = extract_symbols_from_diff("")
    assert len(symbols) == 0
    print("[PASS] extract_symbols_from_diff empty")


def test_mask_secrets_in_text():
    from tools_review import mask_secrets_in_text

    text = "API_KEY=secret123\nTOKEN=abc"
    masked = mask_secrets_in_text(text)
    assert "secret123" not in masked
    assert "MASKED" in masked
    print("[PASS] mask_secrets_in_text")


def test_parse_file_list():
    from tools_review import parse_file_list

    files = parse_file_list("a.py\nb.py\nc.py")
    assert len(files) == 3
    assert "a.py" in files
    print("[PASS] parse_file_list newline")

    files = parse_file_list("a.py, b.py, c.py")
    assert len(files) == 3
    print("[PASS] parse_file_list comma")

    files = parse_file_list("")
    assert len(files) == 0
    print("[PASS] parse_file_list empty")


def test_review_diff():
    from tools_review import review_diff_logic

    result = review_diff_logic(SAMPLE_DIFF, use_llm=False)
    assert "Diff Review" in result
    assert "Changed files" in result
    assert "src/train.py" in result
    print("[PASS] review_diff normal")

    result = review_diff_logic(SAMPLE_DIFF, use_llm=False)
    assert "MASKED" in result or "API_KEY" not in result or "Potential" in result
    print("[PASS] review_diff secret masking")

    result = review_diff_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] review_diff empty")


def test_risk_check_before_edit():
    from tools_review import risk_check_before_edit_logic

    result = risk_check_before_edit_logic("修改训练脚本", target_files="config.py", use_llm=False)
    assert "Pre-edit Risk Check" in result
    assert "Risk level" in result
    print("[PASS] risk_check_before_edit normal")

    result = risk_check_before_edit_logic("修改配置", use_llm=False)
    assert "Pre-edit Risk Check" in result
    print("[PASS] risk_check_before_edit no target files")

    result = risk_check_before_edit_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] risk_check_before_edit empty")


def test_post_edit_review():
    from tools_review import post_edit_review_logic

    result = post_edit_review_logic("修复 bug", "config.py", use_llm=False)
    assert "Post-edit Review" in result
    assert "config.py" in result
    print("[PASS] post_edit_review normal")

    result = post_edit_review_logic("修复 bug", "config.py", diff_text=SAMPLE_DIFF, use_llm=False)
    assert "Post-edit Review" in result
    print("[PASS] post_edit_review with diff")

    result = post_edit_review_logic("", "config.py", use_llm=False)
    assert "Error" in result
    print("[PASS] post_edit_review empty task")

    result = post_edit_review_logic("test", "", use_llm=False)
    assert "Error" in result
    print("[PASS] post_edit_review empty files")


def test_analyze_change_impact():
    from tools_review import analyze_change_impact_logic

    result = analyze_change_impact_logic("修改了函数", target_files="config.py", use_llm=False)
    assert "Change Impact Analysis" in result
    assert "Likely impacted areas" in result
    print("[PASS] analyze_change_impact normal")

    result = analyze_change_impact_logic("修改了函数", diff_text=SAMPLE_DIFF, use_llm=False)
    assert "Change Impact Analysis" in result
    print("[PASS] analyze_change_impact with diff")

    result = analyze_change_impact_logic("", use_llm=False)
    assert "Error" in result
    print("[PASS] analyze_change_impact empty")


if __name__ == "__main__":
    print("=== review tools tests ===\n")
    test_parse_changed_files_from_diff()
    test_parse_diff_summary()
    test_extract_symbols_from_diff()
    test_mask_secrets_in_text()
    test_parse_file_list()
    print()
    test_review_diff()
    print()
    test_risk_check_before_edit()
    print()
    test_post_edit_review()
    print()
    test_analyze_change_impact()
    print("\n=== all review tools tests passed ===")
