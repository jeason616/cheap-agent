from mcp.server.fastmcp import FastMCP

from cheap_agent.config import MCP_HOST, MCP_PATH, MCP_PORT, MCP_TRANSPORT
from cheap_agent.logging_setup import get_logger
from cheap_agent.profiles import get_active_profile, is_tool_allowed
from cheap_agent.tool_registry import TOOL_REGISTRY

logger = get_logger("cheap-agent")

# ── Logic function imports ───────────────────────────────────────
from cheap_agent.tools.code import (
    analyze_error_log_logic,
    find_related_files_logic,
    generate_test_ideas_logic,
    review_file_logic,
    summarize_project_logic,
)
from cheap_agent.tools.reading import (
    extract_symbols_logic,
    read_file_around_line_logic,
    search_code_logic,
)
from cheap_agent.tools.project import (
    build_project_map_logic,
    detect_project_profile_logic,
    summarize_directory_logic,
    summarize_file_logic,
)
from cheap_agent.tools.diagnostics import (
    analyze_traceback_with_context_logic,
    diagnose_import_error_logic,
    diagnose_training_error_logic,
    suggest_debug_steps_logic,
)
from cheap_agent.tools.testing import (
    check_config_consistency_logic,
    generate_unit_test_plan_logic,
    suggest_minimal_repro_logic,
    suggest_validation_plan_logic,
)
from cheap_agent.tools.review import (
    analyze_change_impact_logic,
    post_edit_review_logic,
    review_diff_logic,
    risk_check_before_edit_logic,
)
from cheap_agent.tools.cache_tools import (
    cache_status_logic,
    clear_cache_logic,
    export_perf_report_logic,
    get_cached_project_context_logic,
    rebuild_project_index_logic,
)
from cheap_agent.tools.profile import (
    build_project_profile_v2_logic,
    explain_project_conventions_logic,
    get_codex_onboarding_pack_logic,
    infer_project_runbook_logic,
    recommend_workflow_for_task_logic,
)
from cheap_agent.tools.paper import (
    build_paper_map_logic,
    check_citation_coverage_logic,
    check_claim_evidence_logic,
    detect_paper_project_logic,
    find_paper_sections_logic,
    parse_bib_file_logic,
    review_paper_structure_logic,
    summarize_latex_structure_logic,
)
from cheap_agent.tools.experiments import (
    check_ablation_logic_logic,
    check_metric_consistency_logic,
    check_result_claim_consistency_logic,
    extract_experiment_claims_logic,
    parse_latex_tables_detailed,
)
from cheap_agent.tools.writing import (
    check_abstract_quality_logic,
    check_contribution_clarity_logic,
    check_ieee_style_logic,
    check_introduction_logic_logic,
    check_term_consistency_logic,
    review_academic_paragraph_logic,
)
from cheap_agent.tools.figures import (
    check_caption_text_consistency_logic,
    check_equation_reference_consistency_logic,
    check_figure_reference_consistency_logic,
    parse_figures_and_labels_logic,
    review_figure_caption_logic,
    review_table_caption_logic,
)
from cheap_agent.tools.related_work import (
    build_related_work_outline_logic,
    check_bibtex_quality_logic,
    check_reference_recency_logic,
    check_related_work_coverage_logic,
    group_references_by_topic_logic,
    suggest_citation_positions_logic,
)
from cheap_agent.tools.rebuttal import (
    check_response_completeness_logic,
    draft_response_outline_logic,
    group_reviewer_concerns_logic,
    map_comments_to_revisions_logic,
    parse_reviewer_comments_logic,
    review_response_tone_logic,
)
from cheap_agent.tools.meta import (
    explain_tool_routing_logic,
    list_available_tools_logic,
    show_active_profile_logic,
)

# ── MCP Server ──────────────────────────────────────────────────
mcp = FastMCP(
    "local-code-agent",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
)

_profile = get_active_profile()
_registered_tools: list[str] = []


def _safe_call(fn, *args, **kwargs) -> str:
    """Run a tool logic function, translating exceptions to error strings.

    Business errors (missing file, path violation, bad input) are expected and
    logged at WARNING without a traceback. Anything else is unexpected and
    logged with a full traceback via logger.exception so failures are
    diagnosable in production.
    """
    try:
        return fn(*args, **kwargs)
    except (FileNotFoundError, PermissionError, ValueError, IsADirectoryError) as e:
        logger.warning("tool %s raised %s: %s", fn.__name__, type(e).__name__, e)
        return f"[Tool Error] {type(e).__name__}: {e}"
    except Exception as e:
        logger.exception("tool %s failed unexpectedly", fn.__name__)
        return f"[Tool Error] {type(e).__name__}: {e}"


def _register(tool_name: str, fn):
    """Register a tool only if allowed by the current profile.

    Description is pulled from TOOL_REGISTRY so it has a single source of
    truth (no duplicated strings between server.py and tool_registry.py).
    """
    meta = TOOL_REGISTRY.get(tool_name)
    if meta is None or not is_tool_allowed(tool_name):
        return

    @mcp.tool(name=tool_name, description=meta.description)
    def _wrapper(**kwargs):
        return _safe_call(fn, **kwargs)

    _registered_tools.append(tool_name)


# ── Meta tools (always registered) ─────────────────────────────

@mcp.tool()
def list_available_tools(
    include_disabled: bool = False,
    group: str = "",
) -> str:
    """List currently available MCP tools."""
    return list_available_tools_logic(include_disabled, group)


@mcp.tool()
def show_active_profile() -> str:
    """Show current MCP profile and enabled groups."""
    return show_active_profile_logic()


@mcp.tool()
def explain_tool_routing(
    task_description: str = "",
) -> str:
    """Recommend tools for a given task description."""
    return _safe_call(explain_tool_routing_logic, task_description)


_registered_tools.extend(["list_available_tools", "show_active_profile", "explain_tool_routing"])

# ── Cache tools ─────────────────────────────────────────────────

_register("cache_status", cache_status_logic)
_register("clear_cache", clear_cache_logic)
_register("rebuild_project_index", rebuild_project_index_logic)
_register("get_cached_project_context", get_cached_project_context_logic)
_register("export_perf_report", export_perf_report_logic)

# ── Code: reading ───────────────────────────────────────────────

_register("read_file_around_line", read_file_around_line_logic)
_register("extract_symbols", extract_symbols_logic)
_register("search_code", search_code_logic)
_register("find_related_files", find_related_files_logic)

# ── Code: project ───────────────────────────────────────────────

_register("build_project_map", build_project_map_logic)
_register("summarize_file", summarize_file_logic)
_register("summarize_directory", summarize_directory_logic)
_register("detect_project_profile", detect_project_profile_logic)
_register("build_project_profile_v2", build_project_profile_v2_logic)
_register("get_codex_onboarding_pack", get_codex_onboarding_pack_logic)
_register("infer_project_runbook", infer_project_runbook_logic)
_register("recommend_workflow_for_task", recommend_workflow_for_task_logic)
_register("explain_project_conventions", explain_project_conventions_logic)
_register("review_file", review_file_logic)
_register("summarize_project", summarize_project_logic)

# ── Code: diagnostics ───────────────────────────────────────────

_register("analyze_error_log", analyze_error_log_logic)
_register("analyze_traceback_with_context", analyze_traceback_with_context_logic)
_register("diagnose_import_error", diagnose_import_error_logic)
_register("diagnose_training_error", diagnose_training_error_logic)
_register("suggest_debug_steps", suggest_debug_steps_logic)

# ── Code: testing ───────────────────────────────────────────────

_register("generate_test_ideas", generate_test_ideas_logic)
_register("suggest_minimal_repro", suggest_minimal_repro_logic)
_register("generate_unit_test_plan", generate_unit_test_plan_logic)
_register("check_config_consistency", check_config_consistency_logic)
_register("suggest_validation_plan", suggest_validation_plan_logic)

# ── Code: review ────────────────────────────────────────────────

_register("review_diff", review_diff_logic)
_register("risk_check_before_edit", risk_check_before_edit_logic)
_register("post_edit_review", post_edit_review_logic)
_register("analyze_change_impact", analyze_change_impact_logic)

# ── Paper: structure ────────────────────────────────────────────

_register("detect_paper_project", detect_paper_project_logic)
_register("build_paper_map", build_paper_map_logic)
_register("summarize_latex_structure", summarize_latex_structure_logic)
_register("find_paper_sections", find_paper_sections_logic)
_register("review_paper_structure", review_paper_structure_logic)
_register("check_claim_evidence", check_claim_evidence_logic)

# ── Paper: citation ─────────────────────────────────────────────

_register("parse_bib_file", parse_bib_file_logic)
_register("check_citation_coverage", check_citation_coverage_logic)

# ── Paper: experiment ───────────────────────────────────────────

_register("parse_latex_tables", parse_latex_tables_detailed)
_register("extract_experiment_claims", extract_experiment_claims_logic)
_register("check_result_claim_consistency", check_result_claim_consistency_logic)
_register("check_ablation_logic", check_ablation_logic_logic)
_register("check_metric_consistency", check_metric_consistency_logic)

# ── Paper: writing ──────────────────────────────────────────────

_register("review_academic_paragraph", review_academic_paragraph_logic)
_register("check_abstract_quality", check_abstract_quality_logic)
_register("check_introduction_logic", check_introduction_logic_logic)
_register("check_contribution_clarity", check_contribution_clarity_logic)
_register("check_term_consistency", check_term_consistency_logic)
_register("check_ieee_style", check_ieee_style_logic)

# ── Paper: figures ──────────────────────────────────────────────

_register("parse_figures_and_labels", parse_figures_and_labels_logic)
_register("check_figure_reference_consistency", check_figure_reference_consistency_logic)
_register("review_figure_caption", review_figure_caption_logic)
_register("review_table_caption", review_table_caption_logic)
_register("check_caption_text_consistency", check_caption_text_consistency_logic)
_register("check_equation_reference_consistency", check_equation_reference_consistency_logic)

# ── Paper: related work ─────────────────────────────────────────

_register("group_references_by_topic", group_references_by_topic_logic)
_register("check_related_work_coverage", check_related_work_coverage_logic)
_register("check_reference_recency", check_reference_recency_logic)
_register("check_bibtex_quality", check_bibtex_quality_logic)
_register("suggest_citation_positions", suggest_citation_positions_logic)
_register("build_related_work_outline", build_related_work_outline_logic)

# ── Paper: rebuttal ─────────────────────────────────────────────

_register("parse_reviewer_comments", parse_reviewer_comments_logic)
_register("group_reviewer_concerns", group_reviewer_concerns_logic)
_register("map_comments_to_revisions", map_comments_to_revisions_logic)
_register("check_response_completeness", check_response_completeness_logic)
_register("review_response_tone", review_response_tone_logic)
_register("draft_response_outline", draft_response_outline_logic)

# ── Entry point ─────────────────────────────────────────────────


def main() -> None:
    """Run the MCP server. Entry point for `cheap-agent` and `python -m cheap_agent`."""
    logger.info("profile=%s, registered=%d tools", _profile, len(_registered_tools))
    logger.info("tools: %s", ", ".join(_registered_tools))

    if MCP_TRANSPORT == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
