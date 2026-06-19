"""Profile management and feature switch logic."""

import sys

from cheap_agent.config import (
    DISABLE_ALL_WRITE_TOOLS,
    DISABLE_SHELL_TOOLS,
    ENABLE_CACHE_TOOLS,
    ENABLE_CODE_DIAGNOSTIC_TOOLS,
    ENABLE_CODE_PROJECT_TOOLS,
    ENABLE_CODE_READING_TOOLS,
    ENABLE_CODE_REVIEW_TOOLS,
    ENABLE_CODE_TESTING_TOOLS,
    ENABLE_CODE_TOOLS,
    ENABLE_LLM_CODE_TOOLS,
    ENABLE_LLM_PAPER_TOOLS,
    ENABLE_LLM_REBUTTAL_TOOLS,
    ENABLE_META_TOOLS,
    ENABLE_ONLY_READ_TOOLS,
    ENABLE_PAPER_CITATION_TOOLS,
    ENABLE_PAPER_EXPERIMENT_TOOLS,
    ENABLE_PAPER_FIGURE_TOOLS,
    ENABLE_PAPER_REBUTTAL_TOOLS,
    ENABLE_PAPER_RELATED_WORK_TOOLS,
    ENABLE_PAPER_STRUCTURE_TOOLS,
    ENABLE_PAPER_TOOLS,
    ENABLE_PAPER_WRITING_TOOLS,
    MCP_PROFILE,
    SHOW_DISABLED_TOOLS,
    SHOW_TOOL_LLM_REQUIREMENT,
    SHOW_TOOL_RISK_LEVEL,
)
from cheap_agent.tool_registry import TOOL_REGISTRY, ToolMeta, VALID_PROFILES


def get_active_profile() -> str:
    profile = MCP_PROFILE
    if profile not in VALID_PROFILES:
        print(f"[profiles] Warning: unknown profile '{profile}', falling back to 'safe'", file=sys.stderr)
        return "safe"
    return profile


_CATEGORY_TO_GROUP_SWITCH = {
    "code_reading": "ENABLE_CODE_READING_TOOLS",
    "code_project": "ENABLE_CODE_PROJECT_TOOLS",
    "code_diagnostic": "ENABLE_CODE_DIAGNOSTIC_TOOLS",
    "code_testing": "ENABLE_CODE_TESTING_TOOLS",
    "code_review": "ENABLE_CODE_REVIEW_TOOLS",
    "paper_structure": "ENABLE_PAPER_STRUCTURE_TOOLS",
    "paper_citation": "ENABLE_PAPER_CITATION_TOOLS",
    "paper_experiment": "ENABLE_PAPER_EXPERIMENT_TOOLS",
    "paper_writing": "ENABLE_PAPER_WRITING_TOOLS",
    "paper_figure": "ENABLE_PAPER_FIGURE_TOOLS",
    "paper_related_work": "ENABLE_PAPER_RELATED_WORK_TOOLS",
    "paper_rebuttal": "ENABLE_PAPER_REBUTTAL_TOOLS",
    "cache": None,
    "meta": None,
}

_GROUP_SWITCH_MAP = {
    "code": ENABLE_CODE_TOOLS,
    "paper": ENABLE_PAPER_TOOLS,
    "cache": ENABLE_CACHE_TOOLS,
    "meta": ENABLE_META_TOOLS,
}

_CATEGORY_SWITCH_VALUES = {
    "code_reading": ENABLE_CODE_READING_TOOLS,
    "code_project": ENABLE_CODE_PROJECT_TOOLS,
    "code_diagnostic": ENABLE_CODE_DIAGNOSTIC_TOOLS,
    "code_testing": ENABLE_CODE_TESTING_TOOLS,
    "code_review": ENABLE_CODE_REVIEW_TOOLS,
    "paper_structure": ENABLE_PAPER_STRUCTURE_TOOLS,
    "paper_citation": ENABLE_PAPER_CITATION_TOOLS,
    "paper_experiment": ENABLE_PAPER_EXPERIMENT_TOOLS,
    "paper_writing": ENABLE_PAPER_WRITING_TOOLS,
    "paper_figure": ENABLE_PAPER_FIGURE_TOOLS,
    "paper_related_work": ENABLE_PAPER_RELATED_WORK_TOOLS,
    "paper_rebuttal": ENABLE_PAPER_REBUTTAL_TOOLS,
}


def get_profile_tool_names(profile: str) -> set[str]:
    names = set()
    for name, meta in TOOL_REGISTRY.items():
        if profile == "full" or profile in meta.profile_tags:
            names.add(name)
    return names


def is_tool_group_enabled(group: str, category: str) -> bool:
    if not _GROUP_SWITCH_MAP.get(group, True):
        return False
    if category in _CATEGORY_SWITCH_VALUES:
        return _CATEGORY_SWITCH_VALUES[category]
    return True


def is_tool_allowed(tool_name: str) -> bool:
    meta = TOOL_REGISTRY.get(tool_name)
    if meta is None:
        return False

    profile = get_active_profile()
    if profile != "full" and profile not in meta.profile_tags:
        return False

    if not is_tool_group_enabled(meta.group, meta.category):
        return False

    if ENABLE_ONLY_READ_TOOLS and not meta.read_only:
        print(f"[profiles] Blocked non-read-only tool: {tool_name}", file=sys.stderr)
        return False

    if DISABLE_ALL_WRITE_TOOLS and not meta.read_only:
        print(f"[profiles] Blocked write tool: {tool_name}", file=sys.stderr)
        return False

    if DISABLE_SHELL_TOOLS and "shell" in tool_name.lower():
        print(f"[profiles] Blocked shell tool: {tool_name}", file=sys.stderr)
        return False

    return True


def get_enabled_tools() -> list[ToolMeta]:
    return [meta for name, meta in TOOL_REGISTRY.items() if is_tool_allowed(name)]


def get_disabled_tools() -> list[ToolMeta]:
    return [meta for name, meta in TOOL_REGISTRY.items() if not is_tool_allowed(name)]


def _llm_status(meta: ToolMeta) -> str:
    if not meta.requires_llm:
        return "no"
    if meta.group == "code" and not ENABLE_LLM_CODE_TOOLS:
        return "disabled"
    if meta.group == "paper":
        if meta.category == "paper_rebuttal" and not ENABLE_LLM_REBUTTAL_TOOLS:
            return "disabled"
        if not ENABLE_LLM_PAPER_TOOLS:
            return "disabled"
    return "optional"


def format_active_profile_report() -> str:
    profile = get_active_profile()
    enabled = get_enabled_tools()
    disabled = get_disabled_tools()

    enabled_groups = sorted({t.category for t in enabled})
    disabled_groups = sorted({t.category for t in disabled})

    parts = ["Active MCP Profile", ""]
    parts.append(f"Profile: {profile}")
    parts.append("")

    purposes = {
        "minimal": "Minimal tool set for fast startup.",
        "code": "Code understanding, debugging, testing, and review.",
        "paper": "Paper writing, submission checking, and rebuttal assistance.",
        "full": "All tools enabled for personal full use.",
        "safe": "Only safe, rule-based, low-risk tools.",
        "debug": "MCP self-diagnostics, cache, and performance tools.",
    }
    parts.append(f"Purpose: {purposes.get(profile, 'Unknown')}")
    parts.append("")

    parts.append("Enabled tool groups:")
    for g in enabled_groups:
        parts.append(f"  - {g}")
    parts.append("")

    if disabled_groups:
        parts.append("Disabled tool groups:")
        for g in disabled_groups:
            parts.append(f"  - {g}")
        parts.append("")

    parts.append("Safety:")
    parts.append(f"  - Read-only tools only: {ENABLE_ONLY_READ_TOOLS}")
    parts.append(f"  - Shell tools disabled: {DISABLE_SHELL_TOOLS}")
    parts.append(f"  - Write tools disabled: {DISABLE_ALL_WRITE_TOOLS}")
    parts.append("")

    parts.append(f"Enabled tools: {len(enabled)}")
    parts.append(f"Disabled tools: {len(disabled)}")

    return "\n".join(parts)


def format_available_tools_report(include_disabled: bool = False) -> str:
    profile = get_active_profile()
    enabled = get_enabled_tools()
    disabled = get_disabled_tools()

    by_category: dict[str, list[ToolMeta]] = {}
    for t in enabled:
        by_category.setdefault(t.category, []).append(t)

    parts = ["Available MCP Tools", ""]
    parts.append(f"Active profile: {profile}")
    parts.append("")

    parts.append("Enabled groups:")
    for cat in sorted(by_category.keys()):
        parts.append(f"  - {cat}")
    parts.append("")

    parts.append("Tools:")
    for cat in sorted(by_category.keys()):
        parts.append(f"\n[{cat}]")
        for t in by_category[cat]:
            line = f"  - {t.name}"
            if SHOW_TOOL_RISK_LEVEL:
                line += f"  [{t.risk_level}]"
            if SHOW_TOOL_LLM_REQUIREMENT:
                llm = _llm_status(t)
                line += f"  [LLM: {llm}]"
            parts.append(line)
            parts.append(f"    {t.description}")

    if include_disabled and disabled:
        parts.append(f"\nDisabled tools ({len(disabled)}):")
        for t in disabled:
            parts.append(f"  - {t.name} [{t.category}]")

    return "\n".join(parts)


def get_tools_for_routing(task_type: str) -> list[str]:
    routing = {
        "code_error": ["analyze_traceback_with_context", "read_file_around_line", "search_code", "suggest_debug_steps"],
        "code_review": ["review_diff", "analyze_change_impact", "post_edit_review", "suggest_validation_plan"],
        "paper_experiment": ["parse_latex_tables", "extract_experiment_claims", "check_result_claim_consistency", "check_ablation_logic", "check_metric_consistency"],
        "paper_submission": ["check_ieee_style", "check_figure_reference_consistency", "check_citation_coverage", "check_bibtex_quality"],
        "paper_rebuttal": ["parse_reviewer_comments", "group_reviewer_concerns", "draft_response_outline", "check_response_completeness"],
        "paper_writing": ["review_academic_paragraph", "check_abstract_quality", "check_introduction_logic", "check_contribution_clarity"],
        "paper_structure": ["build_paper_map", "summarize_latex_structure", "find_paper_sections", "review_paper_structure"],
        "project_understanding": ["build_project_map", "detect_project_profile", "get_codex_onboarding_pack", "summarize_project"],
        "debug": ["cache_status", "export_perf_report", "rebuild_project_index", "get_cached_project_context"],
    }
    return routing.get(task_type, ["search_code", "build_project_map"])


def classify_task_for_routing(task: str) -> str:
    task_lower = task.lower()

    if any(w in task_lower for w in ["rebuttal", "reviewer", "response letter", "审稿", "回复"]):
        return "paper_rebuttal"
    if any(w in task_lower for w in ["abstract", "introduction", "contribution", "写作", "语言"]):
        return "paper_writing"
    if any(w in task_lower for w in ["experiment", "table", "ablation", "claim", "实验", "表格"]):
        return "paper_experiment"
    if any(w in task_lower for w in ["submission", "ieee", "style", "投稿", "格式"]):
        return "paper_submission"
    if any(w in task_lower for w in ["related work", "bib", "citation", "reference", "引用", "参考文献"]):
        return "paper_structure"
    if any(w in task_lower for w in ["figure", "caption", "label", "图表", "公式"]):
        return "paper_structure"
    if any(w in task_lower for w in ["traceback", "error", "exception", "报错", "bug"]):
        return "code_error"
    if any(w in task_lower for w in ["review diff", "code review", "pr", "diff", "代码审查"]):
        return "code_review"
    if any(w in task_lower for w in ["paper", "latex", "论文", "tex"]):
        return "paper_structure"
    if any(w in task_lower for w in ["cache", "performance", "缓存", "性能"]):
        return "debug"
    return "project_understanding"
