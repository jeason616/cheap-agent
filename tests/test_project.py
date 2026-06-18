"""Tests for Phase 2 project understanding tools."""

import sys


def test_build_project_map():
    from cheap_agent.tools.project import build_project_map_logic

    result = build_project_map_logic(max_files=50)
    assert "Project root:" in result
    assert "Total files:" in result
    print("[PASS] build_project_map normal")

    result = build_project_map_logic(max_files=5, include_symbols=False)
    assert "Project root:" in result
    print("[PASS] build_project_map without symbols")

    result = build_project_map_logic(max_files=10, include_symbols=True)
    assert "Project root:" in result
    print("[PASS] build_project_map with symbols")


def test_summarize_file():
    from cheap_agent.tools.project import summarize_file_logic

    result = summarize_file_logic("config.py", use_llm=False)
    assert "File:" in result
    assert "Type:" in result
    assert "Lines:" in result
    print("[PASS] summarize_file without LLM")

    result = summarize_file_logic("workspace.py", use_llm=False)
    assert "Python" in result
    print("[PASS] summarize_file Python file")

    result = summarize_file_logic("nonexistent.py", use_llm=False)
    assert "Error" in result
    print("[PASS] summarize_file file not found")

    try:
        summarize_file_logic("../../etc/passwd", use_llm=False)
        print("[FAIL] path traversal NOT blocked!")
        sys.exit(1)
    except PermissionError:
        print("[PASS] summarize_file path traversal blocked")


def test_summarize_directory():
    from cheap_agent.tools.project import summarize_directory_logic

    result = summarize_directory_logic(".", max_files=50, use_llm=False)
    assert "Directory:" in result
    assert "Files scanned:" in result
    print("[PASS] summarize_directory normal")

    result = summarize_directory_logic(".", max_files=5, use_llm=False)
    assert "Directory:" in result
    print("[PASS] summarize_directory max_files")

    result = summarize_directory_logic("nonexistent_dir", use_llm=False)
    assert "Error" in result
    print("[PASS] summarize_directory dir not found")

    try:
        summarize_directory_logic("../../etc", use_llm=False)
        print("[FAIL] path traversal NOT blocked!")
        sys.exit(1)
    except PermissionError:
        print("[PASS] summarize_directory path traversal blocked")


def test_detect_project_profile():
    from cheap_agent.tools.project import detect_project_profile_logic

    result = detect_project_profile_logic(use_llm=False)
    assert "Project Profile" in result
    assert "Main language:" in result
    assert "Suggested first-read" in result
    print("[PASS] detect_project_profile normal")

    assert "Python" in result
    print("[PASS] detect_project_profile detected Python")


if __name__ == "__main__":
    print("=== project tools tests ===\n")
    test_build_project_map()
    print()
    test_summarize_file()
    print()
    test_summarize_directory()
    print()
    test_detect_project_profile()
    print("\n=== all project tools tests passed ===")
