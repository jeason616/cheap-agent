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
from tools_reading import (
    extract_symbols_logic,
    read_file_around_line_logic,
    search_code_logic,
)
from tools_project import (
    build_project_map_logic,
    detect_project_profile_logic,
    summarize_directory_logic,
    summarize_file_logic,
)
from tools_diagnostics import (
    analyze_traceback_with_context_logic,
    diagnose_import_error_logic,
    diagnose_training_error_logic,
    suggest_debug_steps_logic,
)
from tools_testing import (
    check_config_consistency_logic,
    generate_unit_test_plan_logic,
    suggest_minimal_repro_logic,
    suggest_validation_plan_logic,
)
from tools_review import (
    analyze_change_impact_logic,
    post_edit_review_logic,
    review_diff_logic,
    risk_check_before_edit_logic,
)
from tools_cache import (
    cache_status_logic,
    clear_cache_logic,
    export_perf_report_logic,
    get_cached_project_context_logic,
    rebuild_project_index_logic,
)
from tools_profile import (
    build_project_profile_v2_logic,
    explain_project_conventions_logic,
    get_codex_onboarding_pack_logic,
    infer_project_runbook_logic,
    recommend_workflow_for_task_logic,
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
    max_files: int = 100,
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
def summarize_project(max_files: int = 150) -> str:
    """分析项目文件结构，生成项目摘要。"""
    return _safe_call(summarize_project_logic, max_files)


@mcp.tool()
def read_file_around_line(
    file_path: str,
    line_number: int,
    context_lines: int = 80,
) -> str:
    """读取指定行附近的代码片段，用于报错定位。不调用 LLM。"""
    return _safe_call(read_file_around_line_logic, file_path, line_number, context_lines)


@mcp.tool()
def extract_symbols(file_path: str) -> str:
    """提取代码文件中的 imports、函数、类、入口等结构信息。不调用 LLM。"""
    return _safe_call(extract_symbols_logic, file_path)


@mcp.tool()
def search_code(
    query: str,
    file_glob: str = "",
    max_results: int = 50,
    case_sensitive: bool = False,
) -> str:
    """在项目中搜索关键词，返回匹配的文件、行号和内容。不调用 LLM。"""
    return _safe_call(search_code_logic, query, file_glob, max_results, case_sensitive)


@mcp.tool()
def build_project_map(
    max_files: int = 500,
    include_symbols: bool = True,
) -> str:
    """生成项目结构地图，包含目录、入口、配置、模型、数据等分类。"""
    return _safe_call(build_project_map_logic, max_files, include_symbols)


@mcp.tool()
def summarize_file(
    file_path: str,
    use_llm: bool = True,
) -> str:
    """对单个文件生成摘要，包含结构信息和可能用途。"""
    return _safe_call(summarize_file_logic, file_path, use_llm)


@mcp.tool()
def summarize_directory(
    dir_path: str = ".",
    max_files: int = 100,
    use_llm: bool = True,
) -> str:
    """对目录生成摘要，判断目录职责和重要文件。"""
    return _safe_call(summarize_directory_logic, dir_path, max_files, use_llm)


@mcp.tool()
def detect_project_profile(
    use_llm: bool = False,
) -> str:
    """自动判断项目画像：语言、类型、技术栈、入口、配置等。"""
    return _safe_call(detect_project_profile_logic, use_llm)


@mcp.tool()
def analyze_traceback_with_context(
    error_log: str,
    context_lines: int = 60,
    use_llm: bool = True,
) -> str:
    """解析 Python traceback，自动读取项目内相关代码上下文并分析错误原因。"""
    return _safe_call(analyze_traceback_with_context_logic, error_log, context_lines, use_llm)


@mcp.tool()
def diagnose_import_error(
    error_log: str,
    use_llm: bool = True,
) -> str:
    """专门诊断 ModuleNotFoundError、ImportError、相对导入错误等导入问题。"""
    return _safe_call(diagnose_import_error_logic, error_log, use_llm)


@mcp.tool()
def diagnose_training_error(
    error_log: str,
    project_hint: str = "",
    use_llm: bool = True,
) -> str:
    """诊断 PyTorch/YOLO 训练推理错误：CUDA OOM、shape mismatch、数据加载等。"""
    return _safe_call(diagnose_training_error_logic, error_log, project_hint, use_llm)


@mcp.tool()
def suggest_debug_steps(
    problem_description: str,
    error_log: str = "",
    use_project_profile: bool = True,
    use_llm: bool = True,
) -> str:
    """根据问题描述和错误日志，生成结构化调试计划和排查步骤。"""
    return _safe_call(suggest_debug_steps_logic, problem_description, error_log, use_project_profile, use_llm)


@mcp.tool()
def suggest_minimal_repro(
    problem_description: str,
    error_log: str = "",
    related_file: str = "",
    use_llm: bool = True,
) -> str:
    """根据问题描述、错误日志、相关文件生成最小复现方案。只生成方案，不创建文件。"""
    return _safe_call(suggest_minimal_repro_logic, problem_description, error_log, related_file, use_llm)


@mcp.tool()
def generate_unit_test_plan(
    file_path: str,
    target_symbol: str = "",
    test_goal: str = "",
    use_llm: bool = True,
) -> str:
    """针对指定文件或符号生成单元测试计划。只生成计划，不创建测试文件。"""
    return _safe_call(generate_unit_test_plan_logic, file_path, target_symbol, test_goal, use_llm)


@mcp.tool()
def check_config_consistency(
    config_path: str = "",
    code_hint: str = "",
    use_llm: bool = True,
) -> str:
    """检查配置文件与代码之间的不一致风险。只读检查，不修改文件。"""
    return _safe_call(check_config_consistency_logic, config_path, code_hint, use_llm)


@mcp.tool()
def suggest_validation_plan(
    task_description: str,
    changed_files: str = "",
    error_log: str = "",
    use_llm: bool = True,
) -> str:
    """根据任务描述和修改文件生成验证计划。只建议步骤，不执行命令。"""
    return _safe_call(suggest_validation_plan_logic, task_description, changed_files, error_log, use_llm)


@mcp.tool()
def review_diff(
    diff_text: str,
    task_description: str = "",
    use_llm: bool = True,
) -> str:
    """审查 unified diff，指出潜在 bug、遗漏同步修改和测试缺口。不执行 git diff。"""
    return _safe_call(review_diff_logic, diff_text, task_description, use_llm)


@mcp.tool()
def risk_check_before_edit(
    task_description: str,
    target_files: str = "",
    use_llm: bool = True,
) -> str:
    """修改前根据任务和目标文件分析风险与影响范围。只读分析，不修改文件。"""
    return _safe_call(risk_check_before_edit_logic, task_description, target_files, use_llm)


@mcp.tool()
def post_edit_review(
    task_description: str,
    changed_files: str,
    diff_text: str = "",
    use_llm: bool = True,
) -> str:
    """修改后根据任务、修改文件和可选 diff 做二次审查。只读审查，不执行命令。"""
    return _safe_call(post_edit_review_logic, task_description, changed_files, diff_text, use_llm)


@mcp.tool()
def analyze_change_impact(
    task_description: str,
    target_files: str = "",
    diff_text: str = "",
    use_llm: bool = True,
) -> str:
    """分析代码修改的潜在影响范围、引用位置和需要同步修改的内容。"""
    return _safe_call(analyze_change_impact_logic, task_description, target_files, diff_text, use_llm)


@mcp.tool()
def cache_status() -> str:
    """查看缓存状态、缓存大小、命名空间和近期性能统计。"""
    return _safe_call(cache_status_logic)


@mcp.tool()
def clear_cache(namespace: str = "") -> str:
    """清理过期缓存或指定缓存命名空间。只清理缓存目录，不修改项目文件。"""
    return _safe_call(clear_cache_logic, namespace)


@mcp.tool()
def rebuild_project_index() -> str:
    """强制重建项目文件索引。不调用 LLM，不读取文件全文。"""
    return _safe_call(rebuild_project_index_logic)


@mcp.tool()
def get_cached_project_context(
    include_profile: bool = True,
    include_map: bool = True,
    include_recent_summaries: bool = True,
    max_items: int = 20,
) -> str:
    """快速返回已有缓存中的项目画像、项目地图和近期摘要。"""
    return _safe_call(get_cached_project_context_logic, include_profile, include_map, include_recent_summaries, max_items)


@mcp.tool()
def export_perf_report(limit: int = 100) -> str:
    """输出 MCP 工具性能报告，包含耗时统计和优化建议。"""
    return _safe_call(export_perf_report_logic, limit)


@mcp.tool()
def build_project_profile_v2(
    use_llm: bool = True,
    force_refresh: bool = False,
) -> str:
    """构建完整项目画像 v2，包含技术栈、入口、配置、测试、运行方式和 Codex 阅读顺序。"""
    return _safe_call(build_project_profile_v2_logic, use_llm, force_refresh)


@mcp.tool()
def get_codex_onboarding_pack(
    task_description: str = "",
    max_items: int = 20,
    use_llm: bool = False,
) -> str:
    """生成简短启动上下文包，帮助 Codex 快速进入项目。默认不调用 LLM。"""
    return _safe_call(get_codex_onboarding_pack_logic, task_description, max_items, use_llm)


@mcp.tool()
def infer_project_runbook(
    use_llm: bool = True,
    include_commands: bool = True,
) -> str:
    """推断项目的安装、启动、测试、调试流程。不执行命令，只建议。"""
    return _safe_call(infer_project_runbook_logic, use_llm, include_commands)


@mcp.tool()
def recommend_workflow_for_task(
    task_description: str,
    use_llm: bool = False,
) -> str:
    """根据任务描述推荐 MCP 工具调用顺序和优先阅读文件。默认不调用 LLM。"""
    return _safe_call(recommend_workflow_for_task_logic, task_description, use_llm)


@mcp.tool()
def explain_project_conventions(
    use_llm: bool = True,
) -> str:
    """总结项目开发约定，帮助 Codex 避免破坏已有结构和安全边界。"""
    return _safe_call(explain_project_conventions_logic, use_llm)


if __name__ == "__main__":
    print(f"[cheap-agent] starting with transport={MCP_TRANSPORT}", file=sys.stderr)

    if MCP_TRANSPORT == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
