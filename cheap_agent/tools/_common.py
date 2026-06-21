"""Shared helpers for tool modules.

Extracted from per-module duplicates so there is a single source of truth.
"""

# This module must stay dependency-light (no cheap_agent.config import here)
# to avoid circular imports — tool modules import this alongside config.


def truncate(text: str, limit: int) -> str:
    """Truncate text to `limit` chars, appending a visible truncation marker."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"
