"""Tool metadata registry for cheap-agent MCP server."""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class ToolMeta:
    name: str
    group: str
    category: str
    profile_tags: frozenset[str]
    risk_level: str
    requires_llm: bool
    read_only: bool
    enabled_by_default: bool
    description: str
    function_ref: Optional[Callable] = None


VALID_PROFILES = {"minimal", "code", "paper", "full", "safe", "debug"}
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_GROUPS = {"code", "paper", "cache", "meta"}


def _t(
    name: str,
    group: str,
    category: str,
    profiles: set[str],
    risk: str,
    llm: bool,
    read_only: bool,
    desc: str,
    enabled: bool = True,
) -> ToolMeta:
    return ToolMeta(
        name=name,
        group=group,
        category=category,
        profile_tags=frozenset(profiles),
        risk_level=risk,
        requires_llm=llm,
        read_only=read_only,
        enabled_by_default=enabled,
        description=desc,
    )


TOOL_REGISTRY: dict[str, ToolMeta] = {
    # ── Meta tools ──────────────────────────────────────────────
    "list_available_tools": _t(
        "list_available_tools", "meta", "meta",
        {"minimal", "code", "paper", "full", "safe", "debug"},
        "low", False, True,
        "List currently available MCP tools.",
    ),
    "show_active_profile": _t(
        "show_active_profile", "meta", "meta",
        {"minimal", "code", "paper", "full", "safe", "debug"},
        "low", False, True,
        "Show current MCP profile and enabled groups.",
    ),
    "explain_tool_routing": _t(
        "explain_tool_routing", "meta", "meta",
        {"minimal", "code", "paper", "full", "safe", "debug"},
        "low", False, True,
        "Recommend tools for a given task description.",
    ),

    # ── Cache tools ─────────────────────────────────────────────
    "cache_status": _t(
        "cache_status", "cache", "cache",
        {"minimal", "code", "paper", "full", "safe", "debug"},
        "low", False, True,
        "View cache status, namespaces, and performance stats.",
    ),
    "clear_cache": _t(
        "clear_cache", "cache", "cache",
        {"code", "paper", "full", "debug"},
        "low", False, True,
        "Clean expired or specified cache namespaces.",
    ),
    "rebuild_project_index": _t(
        "rebuild_project_index", "cache", "cache",
        {"code", "full", "debug"},
        "low", False, True,
        "Force rebuild project file index.",
    ),
    "get_cached_project_context": _t(
        "get_cached_project_context", "cache", "cache",
        {"code", "paper", "full", "debug"},
        "low", False, True,
        "Return cached project context.",
    ),
    "export_perf_report": _t(
        "export_perf_report", "cache", "cache",
        {"code", "paper", "full", "debug"},
        "low", False, True,
        "Export tool performance report.",
    ),

    # ── Code: reading ───────────────────────────────────────────
    "read_file_around_line": _t(
        "read_file_around_line", "code", "code_reading",
        {"minimal", "code", "full", "safe"},
        "low", False, True,
        "Read code snippet around a specific line number.",
    ),
    "extract_symbols": _t(
        "extract_symbols", "code", "code_reading",
        {"code", "full", "safe"},
        "low", False, True,
        "Extract functions, classes, imports from a code file.",
    ),
    "search_code": _t(
        "search_code", "code", "code_reading",
        {"minimal", "code", "full", "safe"},
        "low", False, True,
        "Search keywords in project files.",
    ),
    "find_related_files": _t(
        "find_related_files", "code", "code_reading",
        {"minimal", "code", "full"},
        "low", True, True,
        "Find files related to a task description.",
    ),

    # ── Code: project ───────────────────────────────────────────
    "build_project_map": _t(
        "build_project_map", "code", "code_project",
        {"minimal", "code", "full"},
        "low", False, True,
        "Build project structure map.",
    ),
    "summarize_file": _t(
        "summarize_file", "code", "code_project",
        {"code", "full"},
        "medium", True, True,
        "Summarize a single file.",
    ),
    "summarize_directory": _t(
        "summarize_directory", "code", "code_project",
        {"code", "full"},
        "medium", True, True,
        "Summarize a directory.",
    ),
    "detect_project_profile": _t(
        "detect_project_profile", "code", "code_project",
        {"code", "full"},
        "low", False, True,
        "Detect project type, language, and stack.",
    ),
    "build_project_profile_v2": _t(
        "build_project_profile_v2", "code", "code_project",
        {"code", "full"},
        "medium", True, True,
        "Build detailed project profile with evidence and confidence.",
    ),
    "get_codex_onboarding_pack": _t(
        "get_codex_onboarding_pack", "code", "code_project",
        {"code", "full"},
        "low", False, True,
        "Generate short onboarding context for Codex.",
    ),
    "infer_project_runbook": _t(
        "infer_project_runbook", "code", "code_project",
        {"code", "full"},
        "medium", True, True,
        "Infer install, start, test, debug workflows.",
    ),
    "recommend_workflow_for_task": _t(
        "recommend_workflow_for_task", "code", "code_project",
        {"code", "full"},
        "low", False, True,
        "Recommend MCP tool sequence for a task.",
    ),
    "explain_project_conventions": _t(
        "explain_project_conventions", "code", "code_project",
        {"code", "full"},
        "medium", True, True,
        "Summarize project development conventions.",
    ),
    "review_file": _t(
        "review_file", "code", "code_project",
        {"code", "full"},
        "medium", True, True,
        "Review a code file for issues.",
    ),
    "summarize_project": _t(
        "summarize_project", "code", "code_project",
        {"code", "full"},
        "medium", True, True,
        "Summarize project structure.",
    ),

    # ── Code: diagnostics ───────────────────────────────────────
    "analyze_error_log": _t(
        "analyze_error_log", "code", "code_diagnostic",
        {"code", "full"},
        "medium", True, True,
        "Analyze error log for causes and next steps.",
    ),
    "analyze_traceback_with_context": _t(
        "analyze_traceback_with_context", "code", "code_diagnostic",
        {"code", "full"},
        "medium", True, True,
        "Parse Python traceback and read relevant code context.",
    ),
    "diagnose_import_error": _t(
        "diagnose_import_error", "code", "code_diagnostic",
        {"code", "full"},
        "medium", True, True,
        "Diagnose ModuleNotFoundError and ImportError.",
    ),
    "diagnose_training_error": _t(
        "diagnose_training_error", "code", "code_diagnostic",
        {"code", "full"},
        "medium", True, True,
        "Diagnose CUDA OOM, shape mismatch, dataloader errors.",
    ),
    "suggest_debug_steps": _t(
        "suggest_debug_steps", "code", "code_diagnostic",
        {"code", "full"},
        "medium", True, True,
        "Generate structured debug plan.",
    ),

    # ── Code: testing ───────────────────────────────────────────
    "generate_test_ideas": _t(
        "generate_test_ideas", "code", "code_testing",
        {"code", "full"},
        "medium", True, True,
        "Generate test ideas for a file.",
    ),
    "suggest_minimal_repro": _t(
        "suggest_minimal_repro", "code", "code_testing",
        {"code", "full"},
        "medium", True, True,
        "Generate minimal reproduction plan.",
    ),
    "generate_unit_test_plan": _t(
        "generate_unit_test_plan", "code", "code_testing",
        {"code", "full"},
        "medium", True, True,
        "Generate unit test plan for a file or symbol.",
    ),
    "check_config_consistency": _t(
        "check_config_consistency", "code", "code_testing",
        {"code", "full"},
        "medium", True, True,
        "Check config file vs code consistency.",
    ),
    "suggest_validation_plan": _t(
        "suggest_validation_plan", "code", "code_testing",
        {"code", "full"},
        "medium", True, True,
        "Generate validation plan for changed files.",
    ),

    # ── Code: review ────────────────────────────────────────────
    "review_diff": _t(
        "review_diff", "code", "code_review",
        {"code", "full"},
        "medium", True, True,
        "Review unified diff for bugs and missing syncs.",
    ),
    "risk_check_before_edit": _t(
        "risk_check_before_edit", "code", "code_review",
        {"code", "full"},
        "medium", True, True,
        "Analyze risk before code changes.",
    ),
    "post_edit_review": _t(
        "post_edit_review", "code", "code_review",
        {"code", "full"},
        "medium", True, True,
        "Post-edit review with task and changed files.",
    ),
    "analyze_change_impact": _t(
        "analyze_change_impact", "code", "code_review",
        {"code", "full"},
        "medium", True, True,
        "Analyze potential impact of code changes.",
    ),

    # ── Paper: structure ────────────────────────────────────────
    "detect_paper_project": _t(
        "detect_paper_project", "paper", "paper_structure",
        {"paper", "full"},
        "low", False, True,
        "Detect if project is a LaTeX/Markdown paper.",
    ),
    "build_paper_map": _t(
        "build_paper_map", "paper", "paper_structure",
        {"minimal", "paper", "full"},
        "low", False, True,
        "Build paper map with sections, bib, figures, labels.",
    ),
    "summarize_latex_structure": _t(
        "summarize_latex_structure", "paper", "paper_structure",
        {"paper", "full"},
        "medium", True, True,
        "Summarize LaTeX paper structure.",
    ),
    "find_paper_sections": _t(
        "find_paper_sections", "paper", "paper_structure",
        {"paper", "full"},
        "low", False, True,
        "Find paper sections by query.",
    ),
    "review_paper_structure": _t(
        "review_paper_structure", "paper", "paper_structure",
        {"paper", "full"},
        "medium", True, True,
        "Check paper structure completeness.",
    ),
    "check_claim_evidence": _t(
        "check_claim_evidence", "paper", "paper_structure",
        {"paper", "full"},
        "medium", True, True,
        "Check if claims have evidence support.",
    ),

    # ── Paper: citation ─────────────────────────────────────────
    "parse_bib_file": _t(
        "parse_bib_file", "paper", "paper_citation",
        {"paper", "full", "safe"},
        "low", False, True,
        "Parse BibTeX file and summarize entries.",
    ),
    "check_citation_coverage": _t(
        "check_citation_coverage", "paper", "paper_citation",
        {"paper", "full"},
        "low", False, True,
        "Check citation keys consistency between text and bib.",
    ),

    # ── Paper: experiment ───────────────────────────────────────
    "parse_latex_tables": _t(
        "parse_latex_tables", "paper", "paper_experiment",
        {"paper", "full", "safe"},
        "low", False, True,
        "Parse LaTeX tables with caption, label, columns, rows.",
    ),
    "extract_experiment_claims": _t(
        "extract_experiment_claims", "paper", "paper_experiment",
        {"paper", "full"},
        "medium", True, True,
        "Extract experiment claims from text.",
    ),
    "check_result_claim_consistency": _t(
        "check_result_claim_consistency", "paper", "paper_experiment",
        {"paper", "full"},
        "medium", True, True,
        "Check if claims are supported by table results.",
    ),
    "check_ablation_logic": _t(
        "check_ablation_logic", "paper", "paper_experiment",
        {"paper", "full"},
        "medium", True, True,
        "Check ablation study completeness.",
    ),
    "check_metric_consistency": _t(
        "check_metric_consistency", "paper", "paper_experiment",
        {"paper", "full", "safe"},
        "low", False, True,
        "Check metric notation consistency.",
    ),

    # ── Paper: writing ──────────────────────────────────────────
    "review_academic_paragraph": _t(
        "review_academic_paragraph", "paper", "paper_writing",
        {"paper", "full"},
        "medium", True, True,
        "Review paragraph for academic quality.",
    ),
    "check_abstract_quality": _t(
        "check_abstract_quality", "paper", "paper_writing",
        {"paper", "full"},
        "medium", True, True,
        "Check abstract coverage and quality.",
    ),
    "check_introduction_logic": _t(
        "check_introduction_logic", "paper", "paper_writing",
        {"paper", "full"},
        "medium", True, True,
        "Check Introduction logic chain.",
    ),
    "check_contribution_clarity": _t(
        "check_contribution_clarity", "paper", "paper_writing",
        {"paper", "full"},
        "medium", True, True,
        "Check contribution clarity and evidence.",
    ),
    "check_term_consistency": _t(
        "check_term_consistency", "paper", "paper_writing",
        {"paper", "full"},
        "low", True, True,
        "Check term and abbreviation consistency.",
    ),
    "check_ieee_style": _t(
        "check_ieee_style", "paper", "paper_writing",
        {"paper", "full"},
        "low", True, True,
        "Check IEEE/TGRS style issues.",
    ),

    # ── Paper: figures ──────────────────────────────────────────
    "parse_figures_and_labels": _t(
        "parse_figures_and_labels", "paper", "paper_figure",
        {"paper", "full", "safe"},
        "low", False, True,
        "Parse LaTeX figures, tables, equations, labels, refs.",
    ),
    "check_figure_reference_consistency": _t(
        "check_figure_reference_consistency", "paper", "paper_figure",
        {"paper", "full", "safe"},
        "low", False, True,
        "Check figure/table/equation label and ref consistency.",
    ),
    "review_figure_caption": _t(
        "review_figure_caption", "paper", "paper_figure",
        {"paper", "full"},
        "medium", True, True,
        "Review figure caption quality.",
    ),
    "review_table_caption": _t(
        "review_table_caption", "paper", "paper_figure",
        {"paper", "full"},
        "medium", True, True,
        "Review table caption quality.",
    ),
    "check_caption_text_consistency": _t(
        "check_caption_text_consistency", "paper", "paper_figure",
        {"paper", "full"},
        "medium", True, True,
        "Check caption vs referencing text consistency.",
    ),
    "check_equation_reference_consistency": _t(
        "check_equation_reference_consistency", "paper", "paper_figure",
        {"paper", "full"},
        "low", True, True,
        "Check equation label, ref, symbol consistency.",
    ),

    # ── Paper: related work ─────────────────────────────────────
    "group_references_by_topic": _t(
        "group_references_by_topic", "paper", "paper_related_work",
        {"paper", "full"},
        "medium", True, True,
        "Group bib entries by research topic.",
    ),
    "check_related_work_coverage": _t(
        "check_related_work_coverage", "paper", "paper_related_work",
        {"paper", "full"},
        "medium", True, True,
        "Check Related Work topic coverage.",
    ),
    "check_reference_recency": _t(
        "check_reference_recency", "paper", "paper_related_work",
        {"paper", "full", "safe"},
        "low", False, True,
        "Check reference year distribution.",
    ),
    "check_bibtex_quality": _t(
        "check_bibtex_quality", "paper", "paper_related_work",
        {"paper", "full", "safe"},
        "low", False, True,
        "Check BibTeX entry quality.",
    ),
    "suggest_citation_positions": _t(
        "suggest_citation_positions", "paper", "paper_related_work",
        {"paper", "full"},
        "medium", True, True,
        "Suggest where citations are needed in text.",
    ),
    "build_related_work_outline": _t(
        "build_related_work_outline", "paper", "paper_related_work",
        {"paper", "full"},
        "medium", True, True,
        "Generate Related Work organization outline.",
    ),

    # ── Paper: rebuttal ─────────────────────────────────────────
    "parse_reviewer_comments": _t(
        "parse_reviewer_comments", "paper", "paper_rebuttal",
        {"paper", "full"},
        "medium", True, True,
        "Parse reviewer comments with concern type and severity.",
    ),
    "group_reviewer_concerns": _t(
        "group_reviewer_concerns", "paper", "paper_rebuttal",
        {"paper", "full"},
        "medium", True, True,
        "Aggregate multi-reviewer concerns.",
    ),
    "map_comments_to_revisions": _t(
        "map_comments_to_revisions", "paper", "paper_rebuttal",
        {"paper", "full"},
        "medium", True, True,
        "Map reviewer comments to manuscript revision targets.",
    ),
    "check_response_completeness": _t(
        "check_response_completeness", "paper", "paper_rebuttal",
        {"paper", "full"},
        "medium", True, True,
        "Check if response letter addresses all comments.",
    ),
    "review_response_tone": _t(
        "review_response_tone", "paper", "paper_rebuttal",
        {"paper", "full"},
        "low", True, True,
        "Check response tone for professionalism.",
    ),
    "draft_response_outline": _t(
        "draft_response_outline", "paper", "paper_rebuttal",
        {"paper", "full"},
        "medium", True, True,
        "Generate response outline for reviewer comments.",
    ),
}

TOOL_COUNT = len(TOOL_REGISTRY)
