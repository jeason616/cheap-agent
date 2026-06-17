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

MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "stdio")
MCP_HOST: str = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT: int = _env_int("MCP_PORT", 8000)
MCP_PATH: str = os.getenv("MCP_PATH", "/mcp")

if MCP_TRANSPORT not in ("stdio", "streamable-http"):
    print(f"[config] Warning: MCP_TRANSPORT={MCP_TRANSPORT!r} is unknown, falling back to stdio", file=sys.stderr)
    MCP_TRANSPORT = "stdio"

if not LLM_API_KEY:
    print("[config] Warning: LLM_API_KEY is not set", file=sys.stderr)
