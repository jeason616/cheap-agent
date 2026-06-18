"""Quick smoke tests for cheap-agent components (no MCP client needed)."""

import sys


def test_config():
    from cheap_agent.config import (
        LLM_BASE_URL, LLM_MODEL, MAX_FILE_CHARS, MAX_OUTPUT_CHARS,
        MCP_TRANSPORT, WORKSPACE_ROOT,
    )
    print(f"WORKSPACE_ROOT : {WORKSPACE_ROOT}")
    print(f"LLM_BASE_URL   : {LLM_BASE_URL}")
    print(f"LLM_MODEL      : {LLM_MODEL}")
    print(f"MAX_FILE_CHARS  : {MAX_FILE_CHARS}")
    print(f"MAX_OUTPUT_CHARS: {MAX_OUTPUT_CHARS}")
    print(f"MCP_TRANSPORT   : {MCP_TRANSPORT}")
    assert WORKSPACE_ROOT.exists(), f"WORKSPACE_ROOT does not exist: {WORKSPACE_ROOT}"
    print("[PASS] config loaded\n")


def test_workspace():
    from cheap_agent.workspace import list_project_files, read_text_file, resolve_safe_path
    safe = resolve_safe_path(".")
    print(f"resolve_safe_path('.') = {safe}")

    files = list_project_files(max_files=10)
    print(f"list_project_files(max_files=10) -> {len(files)} files")
    for f in files:
        print(f"  {f}")

    try:
        resolve_safe_path("../../etc/passwd")
        print("[FAIL] path traversal NOT blocked!")
        sys.exit(1)
    except PermissionError:
        print("[PASS] path traversal blocked")
    print("[PASS] workspace\n")


def test_llm():
    from cheap_agent.llm_client import ask_llm
    result = ask_llm("You are a test assistant.", "Say 'hello' in one word.", max_tokens=16)
    print(f"LLM response: {result[:200]}")
    assert result and "[LLM Error]" not in result, f"LLM call failed: {result}"
    print("[PASS] llm\n")


def test_review():
    from cheap_agent.tools.code import review_file_logic
    result = review_file_logic("config.py")
    print(f"review_file_logic('config.py') -> {len(result)} chars")
    print(result[:500])
    assert len(result) > 50, "Review output too short"
    print("[PASS] review_file_logic\n")


if __name__ == "__main__":
    print("=== cheap-agent smoke tests ===\n")
    test_config()
    test_workspace()
    test_llm()
    test_review()
    print("=== all tests passed ===")
