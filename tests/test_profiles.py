"""Tests for profile management."""

import sys
import os


def test_profile_paper():
    os.environ["MCP_PROFILE"] = "paper"
    from cheap_agent import config, profiles
    import importlib
    importlib.reload(config)
    importlib.reload(profiles)

    enabled = profiles.get_enabled_tools()
    names = {t.name for t in enabled}
    assert "build_paper_map" in names
    assert "check_ieee_style" in names
    assert "parse_reviewer_comments" in names
    print("[PASS] profile=paper enables paper tools")


def test_profile_code():
    os.environ["MCP_PROFILE"] = "code"
    from cheap_agent import config, profiles
    import importlib
    importlib.reload(config)
    importlib.reload(profiles)

    enabled = profiles.get_enabled_tools()
    names = {t.name for t in enabled}
    assert "search_code" in names
    assert "analyze_traceback_with_context" in names
    assert "review_diff" in names
    print("[PASS] profile=code enables code tools")


def test_profile_minimal():
    os.environ["MCP_PROFILE"] = "minimal"
    from cheap_agent import config, profiles
    import importlib
    importlib.reload(config)
    importlib.reload(profiles)

    enabled = profiles.get_enabled_tools()
    names = {t.name for t in enabled}
    assert "search_code" in names
    assert "build_paper_map" in names
    assert len(enabled) <= 15
    print("[PASS] profile=minimal has few tools")


def test_profile_safe():
    os.environ["MCP_PROFILE"] = "safe"
    from cheap_agent import config, profiles
    import importlib
    importlib.reload(config)
    importlib.reload(profiles)

    enabled = profiles.get_enabled_tools()
    for t in enabled:
        assert t.risk_level == "low", f"{t.name} has risk_level={t.risk_level}"
        assert t.read_only, f"{t.name} is not read_only"
    print("[PASS] profile=safe only has low-risk read-only tools")


def test_unknown_profile_falls_back_to_safe():
    os.environ["MCP_PROFILE"] = "unknown_xyz"
    from cheap_agent import config, profiles
    import importlib
    importlib.reload(config)
    importlib.reload(profiles)

    profile = profiles.get_active_profile()
    assert profile == "safe", f"Expected 'safe', got '{profile}'"
    print("[PASS] unknown profile falls back to safe")


if __name__ == "__main__":
    print("=== profile tests ===\n")
    test_profile_paper()
    test_profile_code()
    test_profile_minimal()
    test_profile_safe()
    test_unknown_profile_falls_back_to_safe()
    print("\n=== all profile tests passed ===")
