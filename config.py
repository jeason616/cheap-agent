import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[config] Warning: {key}={raw!r} is not a valid int, using default {default}", file=sys.stderr)
        return default


WORKSPACE_ROOT: Path = Path(os.getenv("WORKSPACE_ROOT") or os.getcwd()).resolve()
print(f"[config] WORKSPACE_ROOT={WORKSPACE_ROOT}", file=sys.stderr)

LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5-coder:7b")

MAX_FILE_CHARS: int = _env_int("MAX_FILE_CHARS", 8000)
MAX_OUTPUT_CHARS: int = _env_int("MAX_OUTPUT_CHARS", 6000)
MAX_SCAN_FILE_SIZE_BYTES: int = _env_int("MAX_SCAN_FILE_SIZE_BYTES", 2 * 1024 * 1024)
MAX_SEARCH_RESULTS: int = _env_int("MAX_SEARCH_RESULTS", 50)
MAX_CONTEXT_LINES: int = _env_int("MAX_CONTEXT_LINES", 200)

ENABLE_PROJECT_MAP_CACHE: bool = os.getenv("ENABLE_PROJECT_MAP_CACHE", "true").lower() == "true"
PROJECT_MAP_CACHE_TTL_SEC: int = _env_int("PROJECT_MAP_CACHE_TTL_SEC", 300)
MAX_PROJECT_MAP_FILES: int = _env_int("MAX_PROJECT_MAP_FILES", 500)
MAX_SUMMARY_FILES: int = _env_int("MAX_SUMMARY_FILES", 100)
MAX_SYMBOL_FILES_FOR_PROJECT_MAP: int = _env_int("MAX_SYMBOL_FILES_FOR_PROJECT_MAP", 20)
ENABLE_LLM_FILE_SUMMARY: bool = os.getenv("ENABLE_LLM_FILE_SUMMARY", "true").lower() == "true"

MAX_TRACEBACK_CONTEXT_FILES: int = _env_int("MAX_TRACEBACK_CONTEXT_FILES", 5)
MAX_TRACEBACK_FRAMES: int = _env_int("MAX_TRACEBACK_FRAMES", 20)
ENABLE_DIAGNOSTIC_CACHE: bool = os.getenv("ENABLE_DIAGNOSTIC_CACHE", "true").lower() == "true"
DIAGNOSTIC_CACHE_TTL_SEC: int = _env_int("DIAGNOSTIC_CACHE_TTL_SEC", 300)
ENABLE_LLM_DIAGNOSTICS: bool = os.getenv("ENABLE_LLM_DIAGNOSTICS", "true").lower() == "true"

ENABLE_TESTING_CACHE: bool = os.getenv("ENABLE_TESTING_CACHE", "true").lower() == "true"
TESTING_CACHE_TTL_SEC: int = _env_int("TESTING_CACHE_TTL_SEC", 300)
ENABLE_LLM_TESTING: bool = os.getenv("ENABLE_LLM_TESTING", "true").lower() == "true"
MAX_REPRO_CONTEXT_FILES: int = _env_int("MAX_REPRO_CONTEXT_FILES", 5)
MAX_CHANGED_FILES_FOR_VALIDATION: int = _env_int("MAX_CHANGED_FILES_FOR_VALIDATION", 20)
MAX_CONFIG_FILES_TO_CHECK: int = _env_int("MAX_CONFIG_FILES_TO_CHECK", 30)
MASK_SECRET_VALUES: bool = os.getenv("MASK_SECRET_VALUES", "true").lower() == "true"

ENABLE_REVIEW_CACHE: bool = os.getenv("ENABLE_REVIEW_CACHE", "true").lower() == "true"
REVIEW_CACHE_TTL_SEC: int = _env_int("REVIEW_CACHE_TTL_SEC", 300)
ENABLE_LLM_REVIEW: bool = os.getenv("ENABLE_LLM_REVIEW", "true").lower() == "true"
MAX_DIFF_CHARS: int = _env_int("MAX_DIFF_CHARS", 30000)
MAX_REVIEW_CHANGED_FILES: int = _env_int("MAX_REVIEW_CHANGED_FILES", 20)
MAX_IMPACT_SYMBOLS: int = _env_int("MAX_IMPACT_SYMBOLS", 20)
MAX_IMPACT_REFERENCES: int = _env_int("MAX_IMPACT_REFERENCES", 100)
MAX_DIFF_FILES: int = _env_int("MAX_DIFF_FILES", 50)

ENABLE_DISK_CACHE: bool = os.getenv("ENABLE_DISK_CACHE", "true").lower() == "true"
CACHE_DIR: str = os.getenv("CACHE_DIR", ".code_agent_cache")
CACHE_VERSION: int = _env_int("CACHE_VERSION", 1)

ENABLE_FILE_INDEX_CACHE: bool = os.getenv("ENABLE_FILE_INDEX_CACHE", "true").lower() == "true"
ENABLE_FILE_SUMMARY_CACHE: bool = os.getenv("ENABLE_FILE_SUMMARY_CACHE", "true").lower() == "true"
ENABLE_DIRECTORY_SUMMARY_CACHE: bool = os.getenv("ENABLE_DIRECTORY_SUMMARY_CACHE", "true").lower() == "true"
ENABLE_PROJECT_PROFILE_CACHE: bool = os.getenv("ENABLE_PROJECT_PROFILE_CACHE", "true").lower() == "true"
ENABLE_TOOL_RESULT_CACHE: bool = os.getenv("ENABLE_TOOL_RESULT_CACHE", "true").lower() == "true"
ENABLE_PERF_LOG_CACHE: bool = os.getenv("ENABLE_PERF_LOG_CACHE", "true").lower() == "true"

FILE_INDEX_CACHE_TTL_SEC: int = _env_int("FILE_INDEX_CACHE_TTL_SEC", 300)
FILE_SUMMARY_CACHE_TTL_SEC: int = _env_int("FILE_SUMMARY_CACHE_TTL_SEC", 86400)
DIRECTORY_SUMMARY_CACHE_TTL_SEC: int = _env_int("DIRECTORY_SUMMARY_CACHE_TTL_SEC", 3600)
PROJECT_PROFILE_CACHE_TTL_SEC: int = _env_int("PROJECT_PROFILE_CACHE_TTL_SEC", 3600)
TOOL_RESULT_CACHE_TTL_SEC: int = _env_int("TOOL_RESULT_CACHE_TTL_SEC", 300)
PERF_LOG_MAX_ENTRIES: int = _env_int("PERF_LOG_MAX_ENTRIES", 1000)

MAX_CACHE_SIZE_MB: int = _env_int("MAX_CACHE_SIZE_MB", 200)
MAX_CACHE_ENTRY_CHARS: int = _env_int("MAX_CACHE_ENTRY_CHARS", 50000)
CACHE_MASK_SECRETS: bool = os.getenv("CACHE_MASK_SECRETS", "true").lower() == "true"
CACHE_WRITE_ATOMIC: bool = os.getenv("CACHE_WRITE_ATOMIC", "true").lower() == "true"
CACHE_SCHEMA_VERSION: int = _env_int("CACHE_SCHEMA_VERSION", 1)

MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "stdio")
MCP_HOST: str = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT: int = _env_int("MCP_PORT", 8000)
MCP_PATH: str = os.getenv("MCP_PATH", "/mcp")

if MCP_TRANSPORT not in ("stdio", "streamable-http"):
    print(f"[config] Warning: MCP_TRANSPORT={MCP_TRANSPORT!r} is unknown, falling back to stdio", file=sys.stderr)
    MCP_TRANSPORT = "stdio"

if not LLM_API_KEY:
    print("[config] Warning: LLM_API_KEY is not set", file=sys.stderr)
