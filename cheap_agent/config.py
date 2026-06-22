import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from cheap_agent.logging_setup import get_logger

# `load_dotenv()` with no args searches upward from the CALLING file's
# directory (this file = cheap_agent/config.py). That works from source, but
# after a `uv tool` / pipx install config.py lives inside the tool's isolated
# venv (site-packages), so the search never reaches the user's project .env.
# usecwd=True searches upward from os.getcwd() instead — the project the MCP
# client launched us in — matching the documented cwd-based behavior.
load_dotenv(find_dotenv(usecwd=True))

logger = get_logger("cheap_agent.config")


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not a valid int, using default %s", key, raw, default)
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r is not a valid float, using default %s", key, raw, default)
        return default


# Truthy values accepted for bool env vars. Anything else (including "1",
# "yes", "on" historically treated as False) falls back to the default with
# a warning, so misconfigurations are visible instead of silently wrong.
_TRUTHY = {"true", "1", "yes", "on", "t", "y"}
_FALSY = {"false", "0", "no", "off", "f", "n", ""}


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in _TRUTHY:
        return True
    if val in _FALSY:
        return False
    logger.warning("%s=%r is not a valid bool, using default %s", key, raw, default)
    return default


WORKSPACE_ROOT: Path = Path(os.getenv("WORKSPACE_ROOT") or os.getcwd()).resolve()
logger.info("WORKSPACE_ROOT=%s", WORKSPACE_ROOT)

LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5-coder:7b")

MAX_FILE_CHARS: int = _env_int("MAX_FILE_CHARS", 8000)
MAX_OUTPUT_CHARS: int = _env_int("MAX_OUTPUT_CHARS", 6000)
MAX_SCAN_FILE_SIZE_BYTES: int = _env_int("MAX_SCAN_FILE_SIZE_BYTES", 2 * 1024 * 1024)
MAX_SEARCH_RESULTS: int = _env_int("MAX_SEARCH_RESULTS", 50)
MAX_CONTEXT_LINES: int = _env_int("MAX_CONTEXT_LINES", 200)

ENABLE_PROJECT_MAP_CACHE: bool = _env_bool("ENABLE_PROJECT_MAP_CACHE", True)
PROJECT_MAP_CACHE_TTL_SEC: int = _env_int("PROJECT_MAP_CACHE_TTL_SEC", 300)
MAX_PROJECT_MAP_FILES: int = _env_int("MAX_PROJECT_MAP_FILES", 500)
MAX_SUMMARY_FILES: int = _env_int("MAX_SUMMARY_FILES", 100)
MAX_SYMBOL_FILES_FOR_PROJECT_MAP: int = _env_int("MAX_SYMBOL_FILES_FOR_PROJECT_MAP", 20)
ENABLE_LLM_FILE_SUMMARY: bool = _env_bool("ENABLE_LLM_FILE_SUMMARY", True)

MAX_TRACEBACK_CONTEXT_FILES: int = _env_int("MAX_TRACEBACK_CONTEXT_FILES", 5)
MAX_TRACEBACK_FRAMES: int = _env_int("MAX_TRACEBACK_FRAMES", 20)
ENABLE_DIAGNOSTIC_CACHE: bool = _env_bool("ENABLE_DIAGNOSTIC_CACHE", True)
DIAGNOSTIC_CACHE_TTL_SEC: int = _env_int("DIAGNOSTIC_CACHE_TTL_SEC", 300)
ENABLE_LLM_DIAGNOSTICS: bool = _env_bool("ENABLE_LLM_DIAGNOSTICS", True)

ENABLE_TESTING_CACHE: bool = _env_bool("ENABLE_TESTING_CACHE", True)
TESTING_CACHE_TTL_SEC: int = _env_int("TESTING_CACHE_TTL_SEC", 300)
ENABLE_LLM_TESTING: bool = _env_bool("ENABLE_LLM_TESTING", True)
MAX_REPRO_CONTEXT_FILES: int = _env_int("MAX_REPRO_CONTEXT_FILES", 5)
MAX_CHANGED_FILES_FOR_VALIDATION: int = _env_int("MAX_CHANGED_FILES_FOR_VALIDATION", 20)
MAX_CONFIG_FILES_TO_CHECK: int = _env_int("MAX_CONFIG_FILES_TO_CHECK", 30)
MASK_SECRET_VALUES: bool = _env_bool("MASK_SECRET_VALUES", True)

ENABLE_REVIEW_CACHE: bool = _env_bool("ENABLE_REVIEW_CACHE", True)
REVIEW_CACHE_TTL_SEC: int = _env_int("REVIEW_CACHE_TTL_SEC", 300)
ENABLE_LLM_REVIEW: bool = _env_bool("ENABLE_LLM_REVIEW", True)
MAX_DIFF_CHARS: int = _env_int("MAX_DIFF_CHARS", 30000)
MAX_REVIEW_CHANGED_FILES: int = _env_int("MAX_REVIEW_CHANGED_FILES", 20)
MAX_IMPACT_SYMBOLS: int = _env_int("MAX_IMPACT_SYMBOLS", 20)
MAX_IMPACT_REFERENCES: int = _env_int("MAX_IMPACT_REFERENCES", 100)
MAX_DIFF_FILES: int = _env_int("MAX_DIFF_FILES", 50)

ENABLE_DISK_CACHE: bool = _env_bool("ENABLE_DISK_CACHE", True)
CACHE_DIR: str = os.getenv("CACHE_DIR", ".code_agent_cache")
CACHE_VERSION: int = _env_int("CACHE_VERSION", 1)

ENABLE_FILE_INDEX_CACHE: bool = _env_bool("ENABLE_FILE_INDEX_CACHE", True)
ENABLE_FILE_SUMMARY_CACHE: bool = _env_bool("ENABLE_FILE_SUMMARY_CACHE", True)
ENABLE_DIRECTORY_SUMMARY_CACHE: bool = _env_bool("ENABLE_DIRECTORY_SUMMARY_CACHE", True)
ENABLE_PROJECT_PROFILE_CACHE: bool = _env_bool("ENABLE_PROJECT_PROFILE_CACHE", True)
ENABLE_TOOL_RESULT_CACHE: bool = _env_bool("ENABLE_TOOL_RESULT_CACHE", True)
ENABLE_PERF_LOG_CACHE: bool = _env_bool("ENABLE_PERF_LOG_CACHE", True)

FILE_INDEX_CACHE_TTL_SEC: int = _env_int("FILE_INDEX_CACHE_TTL_SEC", 300)
FILE_SUMMARY_CACHE_TTL_SEC: int = _env_int("FILE_SUMMARY_CACHE_TTL_SEC", 86400)
DIRECTORY_SUMMARY_CACHE_TTL_SEC: int = _env_int("DIRECTORY_SUMMARY_CACHE_TTL_SEC", 3600)
PROJECT_PROFILE_CACHE_TTL_SEC: int = _env_int("PROJECT_PROFILE_CACHE_TTL_SEC", 3600)
TOOL_RESULT_CACHE_TTL_SEC: int = _env_int("TOOL_RESULT_CACHE_TTL_SEC", 300)
PERF_LOG_MAX_ENTRIES: int = _env_int("PERF_LOG_MAX_ENTRIES", 1000)

MAX_CACHE_SIZE_MB: int = _env_int("MAX_CACHE_SIZE_MB", 200)
MAX_CACHE_ENTRY_CHARS: int = _env_int("MAX_CACHE_ENTRY_CHARS", 50000)
CACHE_MASK_SECRETS: bool = _env_bool("CACHE_MASK_SECRETS", True)
CACHE_WRITE_ATOMIC: bool = _env_bool("CACHE_WRITE_ATOMIC", True)
CACHE_SCHEMA_VERSION: int = _env_int("CACHE_SCHEMA_VERSION", 1)

ENABLE_PROJECT_PROFILE_V2_CACHE: bool = _env_bool("ENABLE_PROJECT_PROFILE_V2_CACHE", True)
PROJECT_PROFILE_V2_CACHE_TTL_SEC: int = _env_int("PROJECT_PROFILE_V2_CACHE_TTL_SEC", 3600)
ENABLE_ONBOARDING_PACK_CACHE: bool = _env_bool("ENABLE_ONBOARDING_PACK_CACHE", True)
ONBOARDING_PACK_CACHE_TTL_SEC: int = _env_int("ONBOARDING_PACK_CACHE_TTL_SEC", 600)
ENABLE_RUNBOOK_CACHE: bool = _env_bool("ENABLE_RUNBOOK_CACHE", True)
RUNBOOK_CACHE_TTL_SEC: int = _env_int("RUNBOOK_CACHE_TTL_SEC", 3600)
ENABLE_CONVENTIONS_CACHE: bool = _env_bool("ENABLE_CONVENTIONS_CACHE", True)
CONVENTIONS_CACHE_TTL_SEC: int = _env_int("CONVENTIONS_CACHE_TTL_SEC", 3600)

MAX_ONBOARDING_ITEMS: int = _env_int("MAX_ONBOARDING_ITEMS", 20)
MAX_PROFILE_EVIDENCE_ITEMS: int = _env_int("MAX_PROFILE_EVIDENCE_ITEMS", 50)
MAX_RUNBOOK_COMMANDS: int = _env_int("MAX_RUNBOOK_COMMANDS", 20)
MAX_CONVENTION_FILES: int = _env_int("MAX_CONVENTION_FILES", 30)

ENABLE_LLM_PROFILE: bool = _env_bool("ENABLE_LLM_PROFILE", True)
ENABLE_LLM_RUNBOOK: bool = _env_bool("ENABLE_LLM_RUNBOOK", True)
ENABLE_LLM_CONVENTIONS: bool = _env_bool("ENABLE_LLM_CONVENTIONS", True)

ENABLE_PAPER_CACHE: bool = _env_bool("ENABLE_PAPER_CACHE", True)
PAPER_CACHE_TTL_SEC: int = _env_int("PAPER_CACHE_TTL_SEC", 3600)

MAX_PAPER_FILES: int = _env_int("MAX_PAPER_FILES", 500)
MAX_TEX_FILE_CHARS: int = _env_int("MAX_TEX_FILE_CHARS", 50000)
MAX_MARKDOWN_FILE_CHARS: int = _env_int("MAX_MARKDOWN_FILE_CHARS", 50000)
MAX_BIB_ENTRIES: int = _env_int("MAX_BIB_ENTRIES", 2000)
MAX_CLAIMS_TO_CHECK: int = _env_int("MAX_CLAIMS_TO_CHECK", 50)
MAX_EVIDENCE_ITEMS: int = _env_int("MAX_EVIDENCE_ITEMS", 100)
MAX_CITATION_ITEMS: int = _env_int("MAX_CITATION_ITEMS", 2000)

ENABLE_LLM_PAPER_REVIEW: bool = _env_bool("ENABLE_LLM_PAPER_REVIEW", True)
PAPER_LLM_MAX_TOKENS: int = _env_int("PAPER_LLM_MAX_TOKENS", 1200)
PAPER_LLM_TEMPERATURE: float = _env_float("PAPER_LLM_TEMPERATURE", 0.1)

PAPER_CACHE_DIR: str = os.getenv("PAPER_CACHE_DIR", ".code_agent_cache/paper")

ENABLE_EXPERIMENT_CACHE: bool = _env_bool("ENABLE_EXPERIMENT_CACHE", True)
EXPERIMENT_CACHE_TTL_SEC: int = _env_int("EXPERIMENT_CACHE_TTL_SEC", 600)
ENABLE_LLM_EXPERIMENT_CHECK: bool = _env_bool("ENABLE_LLM_EXPERIMENT_CHECK", True)

MAX_TABLES_TO_PARSE: int = _env_int("MAX_TABLES_TO_PARSE", 20)
MAX_TABLE_FILES: int = _env_int("MAX_TABLE_FILES", 30)
MAX_EXPERIMENT_CLAIMS: int = _env_int("MAX_EXPERIMENT_CLAIMS", 50)
MAX_TABLE_RAW_CHARS: int = _env_int("MAX_TABLE_RAW_CHARS", 30000)
MAX_TABLE_CELL_CHARS: int = _env_int("MAX_TABLE_CELL_CHARS", 500)
MAX_METRIC_OCCURRENCES: int = _env_int("MAX_METRIC_OCCURRENCES", 200)
MAX_EXPERIMENT_OUTPUT_CHARS: int = _env_int("MAX_EXPERIMENT_OUTPUT_CHARS", 12000)

ENABLE_WRITING_CACHE: bool = _env_bool("ENABLE_WRITING_CACHE", True)
WRITING_CACHE_TTL_SEC: int = _env_int("WRITING_CACHE_TTL_SEC", 600)
ENABLE_LLM_WRITING_CHECK: bool = _env_bool("ENABLE_LLM_WRITING_CHECK", True)

MAX_WRITING_INPUT_CHARS: int = _env_int("MAX_WRITING_INPUT_CHARS", 30000)
MAX_WRITING_OUTPUT_CHARS: int = _env_int("MAX_WRITING_OUTPUT_CHARS", 12000)
MAX_PARAGRAPH_CHARS: int = _env_int("MAX_PARAGRAPH_CHARS", 5000)
MAX_STYLE_ISSUES: int = _env_int("MAX_STYLE_ISSUES", 100)
MAX_TERMS_TO_CHECK: int = _env_int("MAX_TERMS_TO_CHECK", 200)
MAX_TERM_OCCURRENCES: int = _env_int("MAX_TERM_OCCURRENCES", 200)
MAX_ABSTRACT_CHARS: int = _env_int("MAX_ABSTRACT_CHARS", 5000)
MAX_INTRODUCTION_CHARS: int = _env_int("MAX_INTRODUCTION_CHARS", 30000)
MAX_CONTRIBUTION_CHARS: int = _env_int("MAX_CONTRIBUTION_CHARS", 10000)

ENABLE_FIGURE_CACHE: bool = _env_bool("ENABLE_FIGURE_CACHE", True)
FIGURE_CACHE_TTL_SEC: int = _env_int("FIGURE_CACHE_TTL_SEC", 600)
ENABLE_LLM_FIGURE_CHECK: bool = _env_bool("ENABLE_LLM_FIGURE_CHECK", True)

MAX_FIGURE_ITEMS: int = _env_int("MAX_FIGURE_ITEMS", 200)
MAX_CAPTION_ITEMS: int = _env_int("MAX_CAPTION_ITEMS", 100)
MAX_CAPTION_CHARS: int = _env_int("MAX_CAPTION_CHARS", 3000)
MAX_CAPTION_CONTEXT_CHARS: int = _env_int("MAX_CAPTION_CONTEXT_CHARS", 5000)
MAX_FIGURE_OUTPUT_CHARS: int = _env_int("MAX_FIGURE_OUTPUT_CHARS", 12000)
MAX_GRAPHICS_FILES: int = _env_int("MAX_GRAPHICS_FILES", 200)
MAX_EQUATIONS_TO_CHECK: int = _env_int("MAX_EQUATIONS_TO_CHECK", 100)
MAX_LABEL_REFS: int = _env_int("MAX_LABEL_REFS", 500)

ENABLE_RELATED_WORK_CACHE: bool = _env_bool("ENABLE_RELATED_WORK_CACHE", True)
RELATED_WORK_CACHE_TTL_SEC: int = _env_int("RELATED_WORK_CACHE_TTL_SEC", 600)
ENABLE_LLM_RELATED_WORK_CHECK: bool = _env_bool("ENABLE_LLM_RELATED_WORK_CHECK", True)

MAX_BIB_ENTRIES_TO_ANALYZE: int = _env_int("MAX_BIB_ENTRIES_TO_ANALYZE", 500)
MAX_RELATED_WORK_TEXT_CHARS: int = _env_int("MAX_RELATED_WORK_TEXT_CHARS", 40000)
MAX_REFERENCE_GROUPS: int = _env_int("MAX_REFERENCE_GROUPS", 30)
MAX_CITATION_SUGGESTIONS: int = _env_int("MAX_CITATION_SUGGESTIONS", 30)
MAX_REFERENCES_PER_TOPIC: int = _env_int("MAX_REFERENCES_PER_TOPIC", 50)
MAX_RELATED_WORK_OUTPUT_CHARS: int = _env_int("MAX_RELATED_WORK_OUTPUT_CHARS", 16000)
REFERENCE_RECENCY_YEARS: int = _env_int("REFERENCE_RECENCY_YEARS", 3)

ENABLE_REBUTTAL_CACHE: bool = _env_bool("ENABLE_REBUTTAL_CACHE", True)
REBUTTAL_CACHE_TTL_SEC: int = _env_int("REBUTTAL_CACHE_TTL_SEC", 600)
ENABLE_LLM_REBUTTAL_CHECK: bool = _env_bool("ENABLE_LLM_REBUTTAL_CHECK", True)

MAX_REVIEWER_COMMENTS_CHARS: int = _env_int("MAX_REVIEWER_COMMENTS_CHARS", 50000)
MAX_RESPONSE_TEXT_CHARS: int = _env_int("MAX_RESPONSE_TEXT_CHARS", 50000)
MAX_REVIEWER_COMMENTS: int = _env_int("MAX_REVIEWER_COMMENTS", 100)
MAX_RESPONSE_OUTLINES: int = _env_int("MAX_RESPONSE_OUTLINES", 100)
MAX_REBUTTAL_OUTPUT_CHARS: int = _env_int("MAX_REBUTTAL_OUTPUT_CHARS", 16000)
MAX_COMMENT_CONTEXT_CHARS: int = _env_int("MAX_COMMENT_CONTEXT_CHARS", 8000)

MCP_PROFILE: str = os.getenv("MCP_PROFILE", "full").lower()

ENABLE_CODE_TOOLS: bool = _env_bool("ENABLE_CODE_TOOLS", True)
ENABLE_PAPER_TOOLS: bool = _env_bool("ENABLE_PAPER_TOOLS", True)
ENABLE_CACHE_TOOLS: bool = _env_bool("ENABLE_CACHE_TOOLS", True)
ENABLE_META_TOOLS: bool = _env_bool("ENABLE_META_TOOLS", True)

ENABLE_CODE_READING_TOOLS: bool = _env_bool("ENABLE_CODE_READING_TOOLS", True)
ENABLE_CODE_PROJECT_TOOLS: bool = _env_bool("ENABLE_CODE_PROJECT_TOOLS", True)
ENABLE_CODE_DIAGNOSTIC_TOOLS: bool = _env_bool("ENABLE_CODE_DIAGNOSTIC_TOOLS", True)
ENABLE_CODE_TESTING_TOOLS: bool = _env_bool("ENABLE_CODE_TESTING_TOOLS", True)
ENABLE_CODE_REVIEW_TOOLS: bool = _env_bool("ENABLE_CODE_REVIEW_TOOLS", True)

ENABLE_PAPER_STRUCTURE_TOOLS: bool = _env_bool("ENABLE_PAPER_STRUCTURE_TOOLS", True)
ENABLE_PAPER_CITATION_TOOLS: bool = _env_bool("ENABLE_PAPER_CITATION_TOOLS", True)
ENABLE_PAPER_EXPERIMENT_TOOLS: bool = _env_bool("ENABLE_PAPER_EXPERIMENT_TOOLS", True)
ENABLE_PAPER_WRITING_TOOLS: bool = _env_bool("ENABLE_PAPER_WRITING_TOOLS", True)
ENABLE_PAPER_FIGURE_TOOLS: bool = _env_bool("ENABLE_PAPER_FIGURE_TOOLS", True)
ENABLE_PAPER_RELATED_WORK_TOOLS: bool = _env_bool("ENABLE_PAPER_RELATED_WORK_TOOLS", True)
ENABLE_PAPER_REBUTTAL_TOOLS: bool = _env_bool("ENABLE_PAPER_REBUTTAL_TOOLS", True)

ENABLE_LLM_CODE_TOOLS: bool = _env_bool("ENABLE_LLM_CODE_TOOLS", True)
ENABLE_LLM_PAPER_TOOLS: bool = _env_bool("ENABLE_LLM_PAPER_TOOLS", True)
ENABLE_LLM_REBUTTAL_TOOLS: bool = _env_bool("ENABLE_LLM_REBUTTAL_TOOLS", True)

ENABLE_ONLY_READ_TOOLS: bool = _env_bool("ENABLE_ONLY_READ_TOOLS", True)
DISABLE_ALL_WRITE_TOOLS: bool = _env_bool("DISABLE_ALL_WRITE_TOOLS", True)
DISABLE_SHELL_TOOLS: bool = _env_bool("DISABLE_SHELL_TOOLS", True)

SHOW_DISABLED_TOOLS: bool = _env_bool("SHOW_DISABLED_TOOLS", False)
SHOW_TOOL_RISK_LEVEL: bool = _env_bool("SHOW_TOOL_RISK_LEVEL", True)
SHOW_TOOL_LLM_REQUIREMENT: bool = _env_bool("SHOW_TOOL_LLM_REQUIREMENT", True)

MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "stdio")
MCP_HOST: str = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT: int = _env_int("MCP_PORT", 8000)
MCP_PATH: str = os.getenv("MCP_PATH", "/mcp")

if MCP_TRANSPORT not in ("stdio", "streamable-http"):
    logger.warning("MCP_TRANSPORT=%r is unknown, falling back to stdio", MCP_TRANSPORT)
    MCP_TRANSPORT = "stdio"

if not LLM_API_KEY:
    logger.warning("LLM_API_KEY is not set")
