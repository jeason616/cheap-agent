"""Tests for cheap_agent.tools.code — the only tool module that previously
had no unit tests. All functions call ask_llm directly (no use_llm=False
path), so we monkeypatch ask_llm to capture the prompts and avoid real
LLM calls."""

import pytest


@pytest.fixture
def captured_llm(monkeypatch):
    """Replace ask_llm in tools.code with a recorder. Returns a list that
    collects (system_prompt, user_prompt) tuples."""
    calls = []

    def fake_ask_llm(system_prompt, user_prompt, temperature=0.2, max_tokens=1024):
        calls.append((system_prompt, user_prompt))
        return f"[stub] received {len(user_prompt)} chars"

    monkeypatch.setattr("cheap_agent.tools.code.ask_llm", fake_ask_llm)
    return calls


def test_review_file_logic(captured_llm):
    from cheap_agent.tools.code import review_file_logic
    from cheap_agent.prompts.base import CODE_REVIEW_SYSTEM_PROMPT

    result = review_file_logic("cheap_agent/config.py")
    assert "[stub]" in result
    assert len(captured_llm) == 1
    sys_p, user_p = captured_llm[0]
    assert sys_p == CODE_REVIEW_SYSTEM_PROMPT
    assert "cheap_agent/config.py" in user_p
    assert "文件内容" in user_p


def test_review_file_logic_custom_question(captured_llm):
    from cheap_agent.tools.code import review_file_logic

    review_file_logic("cheap_agent/config.py", question="检查安全问题")
    _, user_p = captured_llm[0]
    assert "检查安全问题" in user_p


def test_review_file_logic_not_found(captured_llm):
    from cheap_agent.tools.code import review_file_logic

    result = review_file_logic("does_not_exist_xyz.py")
    assert result.startswith("[Error]")
    assert captured_llm == []  # LLM must not be called on read failure


def test_review_file_logic_path_traversal(captured_llm):
    from cheap_agent.tools.code import review_file_logic

    result = review_file_logic("../../etc/passwd")
    assert result.startswith("[Error]")
    assert captured_llm == []


def test_analyze_error_log_logic(captured_llm):
    from cheap_agent.tools.code import analyze_error_log_logic
    from cheap_agent.prompts.base import ERROR_ANALYSIS_SYSTEM_PROMPT

    result = analyze_error_log_logic("Traceback: RuntimeError: boom")
    assert "[stub]" in result
    sys_p, user_p = captured_llm[0]
    assert sys_p == ERROR_ANALYSIS_SYSTEM_PROMPT
    assert "RuntimeError: boom" in user_p


def test_analyze_error_log_logic_with_hint(captured_llm):
    from cheap_agent.tools.code import analyze_error_log_logic

    analyze_error_log_logic("error here", project_hint="pytorch project")
    _, user_p = captured_llm[0]
    assert "pytorch project" in user_p


def test_find_related_files_logic(captured_llm):
    from cheap_agent.tools.code import find_related_files_logic
    from cheap_agent.prompts.base import RELATED_FILES_SYSTEM_PROMPT

    result = find_related_files_logic("fix the cache bug")
    assert "[stub]" in result
    sys_p, _ = captured_llm[0]
    assert sys_p == RELATED_FILES_SYSTEM_PROMPT


def test_find_related_files_logic_no_files(captured_llm, monkeypatch):
    from cheap_agent.tools.code import find_related_files_logic

    monkeypatch.setattr("cheap_agent.tools.code.list_project_files", lambda **kw: [])
    result = find_related_files_logic("anything")
    assert "未找到" in result
    assert captured_llm == []


def test_generate_test_ideas_logic(captured_llm):
    from cheap_agent.tools.code import generate_test_ideas_logic
    from cheap_agent.prompts.base import TEST_IDEAS_SYSTEM_PROMPT

    result = generate_test_ideas_logic("cheap_agent/cache.py")
    assert "[stub]" in result
    sys_p, user_p = captured_llm[0]
    assert sys_p == TEST_IDEAS_SYSTEM_PROMPT
    assert "cheap_agent/cache.py" in user_p


def test_generate_test_ideas_logic_not_found(captured_llm):
    from cheap_agent.tools.code import generate_test_ideas_logic

    result = generate_test_ideas_logic("nope.py")
    assert result.startswith("[Error]")
    assert captured_llm == []


def test_summarize_project_logic(captured_llm):
    from cheap_agent.tools.code import summarize_project_logic
    from cheap_agent.prompts.base import PROJECT_SUMMARY_SYSTEM_PROMPT

    result = summarize_project_logic(max_files=20)
    assert "[stub]" in result
    sys_p, _ = captured_llm[0]
    assert sys_p == PROJECT_SUMMARY_SYSTEM_PROMPT


def test_summarize_project_logic_no_files(captured_llm, monkeypatch):
    from cheap_agent.tools.code import summarize_project_logic

    monkeypatch.setattr("cheap_agent.tools.code.list_project_files", lambda **kw: [])
    result = summarize_project_logic()
    assert "未找到" in result
    assert captured_llm == []


def test_safe_content_truncation():
    """Long content should be truncated before being passed to the LLM."""
    from cheap_agent.tools.code import _safe_content

    big = "x" * 100000
    capped = _safe_content(big, limit=1000)
    assert len(capped) < len(big)
    assert "truncated" in capped
