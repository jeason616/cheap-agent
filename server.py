import sys

from mcp.server.fastmcp import FastMCP

from config import MCP_HOST, MCP_PATH, MCP_PORT, MCP_TRANSPORT
from tools_code import (
    analyze_error_log_logic,
    find_related_files_logic,
    generate_test_ideas_logic,
    review_file_logic,
    summarize_project_logic,
)

mcp = FastMCP(
    "local-code-agent",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
)


def _safe_call(fn, *args, **kwargs) -> str:
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[cheap-agent] tool error in {fn.__name__}: {e}", file=sys.stderr)
        return f"[Tool Error] {e}"


@mcp.tool()
def review_file(
    file_path: str,
    question: str = "请检查这个文件是否有明显问题，并给出修改建议。",
) -> str:
    """审查指定文件的代码质量，返回问题和建议。只读，不修改文件。"""
    return _safe_call(review_file_logic, file_path, question)


@mcp.tool()
def analyze_error_log(
    error_log: str,
    project_hint: str = "",
) -> str:
    """分析报错日志，返回可能原因和排查建议。"""
    return _safe_call(analyze_error_log_logic, error_log, project_hint)


@mcp.tool()
def find_related_files(
    task: str,
    keyword: str | None = None,
    max_files: int = 200,
) -> str:
    """根据任务描述，在项目中找出最相关的文件。"""
    return _safe_call(find_related_files_logic, task, keyword, max_files)


@mcp.tool()
def generate_test_ideas(
    file_path: str,
    test_goal: str = "",
) -> str:
    """为指定文件生成测试思路，不创建实际测试文件。"""
    return _safe_call(generate_test_ideas_logic, file_path, test_goal)


@mcp.tool()
def summarize_project(max_files: int = 300) -> str:
    """分析项目文件结构，生成项目摘要。"""
    return _safe_call(summarize_project_logic, max_files)


if __name__ == "__main__":
    print(f"[cheap-agent] starting with transport={MCP_TRANSPORT}", file=sys.stderr)

    if MCP_TRANSPORT == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
