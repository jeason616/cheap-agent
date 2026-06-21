"""Tests for the Phase 1 reading tools (no LLM calls)."""

import sys


def test_read_file_around_line():
    from cheap_agent.tools.reading import read_file_around_line_logic

    result = read_file_around_line_logic("cheap_agent/config.py", 1, context_lines=10)
    assert "File:" in result
    assert ">> " in result
    assert "Total lines:" in result
    print("[PASS] read_file_around_line normal")

    result = read_file_around_line_logic("cheap_agent/config.py", 99999)
    assert "Error" in result or "exceeds" in result
    print("[PASS] read_file_around_line line out of range")

    result = read_file_around_line_logic("cheap_agent/config.py", 0)
    assert "Error" in result
    print("[PASS] read_file_around_line line < 1")

    result = read_file_around_line_logic("cheap_agent/config.py", 1, context_lines=9999)
    assert ">> " in result
    print("[PASS] read_file_around_line context_lines capped")

    try:
        read_file_around_line_logic("../../etc/passwd", 1)
        print("[FAIL] path traversal NOT blocked!")
        sys.exit(1)
    except PermissionError:
        print("[PASS] read_file_around_line path traversal blocked")


def test_extract_symbols():
    from cheap_agent.tools.reading import extract_symbols_logic

    result = extract_symbols_logic("cheap_agent/workspace.py")
    assert "Imports:" in result
    assert "Top-level functions:" in result
    assert "resolve_safe_path" in result
    print("[PASS] extract_symbols Python file")

    result = extract_symbols_logic("README.md")
    assert "File:" in result
    print("[PASS] extract_symbols non-Python file")

    result = extract_symbols_logic("nonexistent.py")
    assert "Error" in result
    print("[PASS] extract_symbols file not found")

    try:
        extract_symbols_logic("../../etc/passwd")
        print("[FAIL] path traversal NOT blocked!")
        sys.exit(1)
    except PermissionError:
        print("[PASS] extract_symbols path traversal blocked")


def test_search_code():
    from cheap_agent.tools.reading import search_code_logic

    result = search_code_logic("resolve_safe_path")
    assert "Results:" in result
    assert "cheap_agent/workspace.py" in result
    print("[PASS] search_code normal")

    result = search_code_logic("def ", file_glob="*.py")
    assert "Results:" in result
    print("[PASS] search_code with file_glob")

    result = search_code_logic("", file_glob="*.py")
    assert "Error" in result
    print("[PASS] search_code empty query")

    result = search_code_logic("def", max_results=2)
    lines = result.split("\n")
    count = sum(1 for l in lines if l and not l.startswith(("Search", "Scanned", "Results")))
    print("[PASS] search_code max_results")


if __name__ == "__main__":
    print("=== reading tools tests ===\n")
    test_read_file_around_line()
    print()
    test_extract_symbols()
    print()
    test_search_code()
    print("\n=== all reading tools tests passed ===")
