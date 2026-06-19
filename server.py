import sys

from mcp.server.fastmcp import FastMCP

from cheap_agent.config import MCP_HOST, MCP_PATH, MCP_PORT, MCP_TRANSPORT
from cheap_agent.profiles import get_active_profile, is_tool_allowed

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
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[cheap-agent] tool error in {fn.__name__}: {e}", file=sys.stderr)
        return f"[Tool Error] {e}"


def _register(tool_name: str, fn, description: str, **params):
    """Register a tool only if it's allowed by the current profile."""
    if not is_tool_allowed(tool_name):
        return

    @mcp.tool(name=tool_name, description=description)
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

_register("cache_status", cache_status_logic, "View cache status, namespaces, and performance stats.")
_register("clear_cache", clear_cache_logic, "Clean expired or specified cache namespaces.")
_register("rebuild_project_index", rebuild_project_index_logic, "Force rebuild project file index.")
_register("get_cached_project_context", get_cached_project_context_logic, "Return cached project context.")
_register("export_perf_report", export_perf_report_logic, "Export tool performance report.")

# ── Code: reading ───────────────────────────────────────────────

_register("read_file_around_line", read_file_around_line_logic,
          "Read code snippet around a specific line number.")
_register("extract_symbols", extract_symbols_logic,
          "Extract functions, classes, imports from a code file.")
_register("search_code", search_code_logic,
          "Search keywords in project files.")
_register("find_related_files", find_related_files_logic,
          "Find files related to a task description.")

# ── Code: project ───────────────────────────────────────────────

_register("build_project_map", build_project_map_logic,
          "Build project structure map.")
_register("summarize_file", summarize_file_logic,
          "Summarize a single file.")
_register("summarize_directory", summarize_directory_logic,
          "Summarize a directory.")
_register("detect_project_profile", detect_project_profile_logic,
          "Detect project type, language, and stack.")
_register("build_project_profile_v2", build_project_profile_v2_logic,
          "Build detailed project profile with evidence and confidence.")
_register("get_codex_onboarding_pack", get_codex_onboarding_pack_logic,
          "Generate short onboarding context for Codex.")
_register("infer_project_runbook", infer_project_runbook_logic,
          "Infer install, start, test, debug workflows.")
_register("recommend_workflow_for_task", recommend_workflow_for_task_logic,
          "Recommend MCP tool sequence for a task.")
_register("explain_project_conventions", explain_project_conventions_logic,
          "Summarize project development conventions.")
_register("review_file", review_file_logic,
          "Review a code file for issues.")
_register("summarize_project", summarize_project_logic,
          "Summarize project structure.")

# ── Code: diagnostics ───────────────────────────────────────────

_register("analyze_error_log", analyze_error_log_logic,
          "Analyze error log for causes and next steps.")
_register("analyze_traceback_with_context", analyze_traceback_with_context_logic,
          "Parse Python traceback and read relevant code context.")
_register("diagnose_import_error", diagnose_import_error_logic,
          "Diagnose ModuleNotFoundError and ImportError.")
_register("diagnose_training_error", diagnose_training_error_logic,
          "Diagnose CUDA OOM, shape mismatch, dataloader errors.")
_register("suggest_debug_steps", suggest_debug_steps_logic,
          "Generate structured debug plan.")

# ── Code: testing ───────────────────────────────────────────────

_register("generate_test_ideas", generate_test_ideas_logic,
          "Generate test ideas for a file.")
_register("suggest_minimal_repro", suggest_minimal_repro_logic,
          "Generate minimal reproduction plan.")
_register("generate_unit_test_plan", generate_unit_test_plan_logic,
          "Generate unit test plan for a file or symbol.")
_register("check_config_consistency", check_config_consistency_logic,
          "Check config file vs code consistency.")
_register("suggest_validation_plan", suggest_validation_plan_logic,
          "Generate validation plan for changed files.")

# ── Code: review ────────────────────────────────────────────────

_register("review_diff", review_diff_logic,
          "Review unified diff for bugs and missing syncs.")
_register("risk_check_before_edit", risk_check_before_edit_logic,
          "Analyze risk before code changes.")
_register("post_edit_review", post_edit_review_logic,
          "Post-edit review with task and changed files.")
_register("analyze_change_impact", analyze_change_impact_logic,
          "Analyze potential impact of code changes.")

# ── Paper: structure ────────────────────────────────────────────

_register("detect_paper_project", detect_paper_project_logic,
          "Detect if project is a LaTeX/Markdown paper.")
_register("build_paper_map", build_paper_map_logic,
          "Build paper map with sections, bib, figures, labels.")
_register("summarize_latex_structure", summarize_latex_structure_logic,
          "Summarize LaTeX paper structure.")
_register("find_paper_sections", find_paper_sections_logic,
          "Find paper sections by query.")
_register("review_paper_structure", review_paper_structure_logic,
          "Check paper structure completeness.")
_register("check_claim_evidence", check_claim_evidence_logic,
          "Check if claims have evidence support.")

# ── Paper: citation ─────────────────────────────────────────────

_register("parse_bib_file", parse_bib_file_logic,
          "Parse BibTeX file and summarize entries.")
_register("check_citation_coverage", check_citation_coverage_logic,
          "Check citation keys consistency between text and bib.")

# ── Paper: experiment ───────────────────────────────────────────

_register("parse_latex_tables", parse_latex_tables_detailed,
          "Parse LaTeX tables with caption, label, columns, rows.")
_register("extract_experiment_claims", extract_experiment_claims_logic,
          "Extract experiment claims from text.")
_register("check_result_claim_consistency", check_result_claim_consistency_logic,
          "Check if claims are supported by table results.")
_register("check_ablation_logic", check_ablation_logic_logic,
          "Check ablation study completeness.")
_register("check_metric_consistency", check_metric_consistency_logic,
          "Check metric notation consistency.")

# ── Paper: writing ──────────────────────────────────────────────

_register("review_academic_paragraph", review_academic_paragraph_logic,
          "Review paragraph for academic quality.")
_register("check_abstract_quality", check_abstract_quality_logic,
          "Check abstract coverage and quality.")
_register("check_introduction_logic", check_introduction_logic_logic,
          "Check Introduction logic chain.")
_register("check_contribution_clarity", check_contribution_clarity_logic,
          "Check contribution clarity and evidence.")
_register("check_term_consistency", check_term_consistency_logic,
          "Check term and abbreviation consistency.")
_register("check_ieee_style", check_ieee_style_logic,
          "Check IEEE/TGRS style issues.")

# ── Paper: figures ──────────────────────────────────────────────

_register("parse_figures_and_labels", parse_figures_and_labels_logic,
          "Parse LaTeX figures, tables, equations, labels, refs.")
_register("check_figure_reference_consistency", check_figure_reference_consistency_logic,
          "Check figure/table/equation label and ref consistency.")
_register("review_figure_caption", review_figure_caption_logic,
          "Review figure caption quality.")
_register("review_table_caption", review_table_caption_logic,
          "Review table caption quality.")
_register("check_caption_text_consistency", check_caption_text_consistency_logic,
          "Check caption vs referencing text consistency.")
_register("check_equation_reference_consistency", check_equation_reference_consistency_logic,
          "Check equation label, ref, symbol consistency.")

# ── Paper: related work ─────────────────────────────────────────

_register("group_references_by_topic", group_references_by_topic_logic,
          "Group bib entries by research topic.")
_register("check_related_work_coverage", check_related_work_coverage_logic,
          "Check Related Work topic coverage.")
_register("check_reference_recency", check_reference_recency_logic,
          "Check reference year distribution.")
_register("check_bibtex_quality", check_bibtex_quality_logic,
          "Check BibTeX entry quality.")
_register("suggest_citation_positions", suggest_citation_positions_logic,
          "Suggest where citations are needed in text.")
_register("build_related_work_outline", build_related_work_outline_logic,
          "Generate Related Work organization outline.")

# ── Paper: rebuttal ─────────────────────────────────────────────

_register("parse_reviewer_comments", parse_reviewer_comments_logic,
          "Parse reviewer comments with concern type and severity.")
_register("group_reviewer_concerns", group_reviewer_concerns_logic,
          "Aggregate multi-reviewer concerns.")
_register("map_comments_to_revisions", map_comments_to_revisions_logic,
          "Map reviewer comments to manuscript revision targets.")
_register("check_response_completeness", check_response_completeness_logic,
          "Check if response letter addresses all comments.")
_register("review_response_tone", review_response_tone_logic,
          "Check response tone for professionalism.")
_register("draft_response_outline", draft_response_outline_logic,
          "Generate response outline for reviewer comments.")

# ── Entry point ─────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[cheap-agent] profile={_profile}, registered={len(_registered_tools)} tools", file=sys.stderr)
    print(f"[cheap-agent] tools: {', '.join(_registered_tools)}", file=sys.stderr)

    if MCP_TRANSPORT == "streamable-http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
