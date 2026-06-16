from config import MAX_FILE_CHARS
from llm_client import ask_llm
from prompts import (
    CODE_REVIEW_SYSTEM_PROMPT,
    ERROR_ANALYSIS_SYSTEM_PROMPT,
    RELATED_FILES_SYSTEM_PROMPT,
    TEST_IDEAS_SYSTEM_PROMPT,
    PROJECT_SUMMARY_SYSTEM_PROMPT,
)
from workspace import list_project_files, read_text_file

PROMPT_RESERVE = 2000


def _safe_content(content: str, limit: int | None = None) -> str:
    cap = limit or MAX_FILE_CHARS
    if len(content) <= cap:
        return content
    return content[:cap] + f"\n\n... [content truncated to {cap} chars for prompt safety]"


def review_file_logic(
    file_path: str,
    question: str = "请检查这个文件是否有明显问题，并给出修改建议。",
) -> str:
    """Read a file and ask the LLM to review it."""
    try:
        content = read_text_file(file_path)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        return f"[Error] {e}"

    content = _safe_content(content)
    user_prompt = f"文件路径: {file_path}\n\n文件内容:\n```\n{content}\n```\n\n审查要求: {question}"
    return ask_llm(CODE_REVIEW_SYSTEM_PROMPT, user_prompt)


def analyze_error_log_logic(
    error_log: str,
    project_hint: str = "",
) -> str:
    """Analyze an error log and suggest causes / next steps."""
    hint_section = f"\n项目上下文: {project_hint}" if project_hint else ""
    user_prompt = f"报错日志:\n```\n{error_log}\n```{hint_section}"
    return ask_llm(ERROR_ANALYSIS_SYSTEM_PROMPT, user_prompt)


def find_related_files_logic(
    task: str,
    keyword: str | None = None,
    max_files: int = 100,
) -> str:
    """List project files and ask the LLM which are most relevant to the task."""
    try:
        files = list_project_files(keyword=keyword, max_files=max_files)
    except Exception as e:
        return f"[Error] Failed to list project files: {e}"

    if not files:
        return "未找到匹配的文件。请检查 WORKSPACE_ROOT 或 keyword。"

    file_list = "\n".join(files)
    file_list = _safe_content(file_list, limit=30000)
    user_prompt = (
        f"任务描述: {task}\n\n"
        f"项目文件列表 ({len(files)} 个):\n{file_list}\n\n"
        "请分析哪些文件与该任务最相关。"
    )
    return ask_llm(RELATED_FILES_SYSTEM_PROMPT, user_prompt)


def generate_test_ideas_logic(
    file_path: str,
    test_goal: str = "",
) -> str:
    """Generate test ideas for a given file."""
    try:
        content = read_text_file(file_path)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        return f"[Error] {e}"

    content = _safe_content(content)
    goal_section = f"\n测试目标: {test_goal}" if test_goal else ""
    user_prompt = f"文件路径: {file_path}\n\n文件内容:\n```\n{content}\n```{goal_section}"
    return ask_llm(TEST_IDEAS_SYSTEM_PROMPT, user_prompt)


def summarize_project_logic(max_files: int = 150) -> str:
    """Summarize the project structure based on file listing."""
    try:
        files = list_project_files(max_files=max_files)
    except Exception as e:
        return f"[Error] Failed to list project files: {e}"

    if not files:
        return "未找到文件。请检查 WORKSPACE_ROOT 是否正确。"

    file_list = "\n".join(files)
    file_list = _safe_content(file_list, limit=30000)
    user_prompt = f"项目文件列表 ({len(files)} 个):\n{file_list}\n\n请分析项目结构。"
    return ask_llm(PROJECT_SUMMARY_SYSTEM_PROMPT, user_prompt)
