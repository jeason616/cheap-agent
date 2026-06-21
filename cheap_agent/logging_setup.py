"""Centralized logging setup for cheap-agent.

Why this exists: cheap-agent is a stdio MCP server. MCP JSON-RPC travels
over stdout, so stdout must stay pristine. All diagnostics go to stderr.
Previously every module used `print(..., file=sys.stderr)`, which cannot
be filtered by level, formatted, or silenced. This module configures a
single stderr StreamHandler on the root logger and exposes `get_logger`.

Importing this module is idempotent: the handler is attached only once.
Log level is controlled by the `LOG_LEVEL` env var (default INFO).
"""

import logging
import os
import sys

_CONFIGURED = False
_DEFAULT_FORMAT = "[%(name)s] %(levelname)s: %(message)s"


def _configure_once() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    root = logging.getLogger()
    # Avoid duplicate handlers if something else already configured root.
    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "_cheap_agent", False)
        for h in root.handlers
    ):
        handler._cheap_agent = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Triggers root setup on first call."""
    _configure_once()
    return logging.getLogger(name)
