"""Tests for tool registry."""

import sys

from cheap_agent.tool_registry import TOOL_REGISTRY, VALID_PROFILES, VALID_RISK_LEVELS


def test_all_tools_have_required_fields():
    for name, meta in TOOL_REGISTRY.items():
        assert meta.name, f"{name}: missing name"
        assert meta.group, f"{name}: missing group"
        assert meta.category, f"{name}: missing category"
        assert meta.profile_tags, f"{name}: missing profile_tags"
        assert meta.risk_level, f"{name}: missing risk_level"
        assert meta.description, f"{name}: missing description"
    print(f"[PASS] All {len(TOOL_REGISTRY)} tools have required fields")


def test_tool_names_unique():
    names = [m.name for m in TOOL_REGISTRY.values()]
    assert len(names) == len(set(names)), "Duplicate tool names found"
    print("[PASS] Tool names are unique")


def test_risk_levels_valid():
    for name, meta in TOOL_REGISTRY.items():
        assert meta.risk_level in VALID_RISK_LEVELS, f"{name}: invalid risk_level '{meta.risk_level}'"
    print("[PASS] All risk levels are valid")


def test_profile_tags_valid():
    for name, meta in TOOL_REGISTRY.items():
        for tag in meta.profile_tags:
            assert tag in VALID_PROFILES, f"{name}: invalid profile tag '{tag}'"
    print("[PASS] All profile tags are valid")


def test_all_tools_read_only():
    for name, meta in TOOL_REGISTRY.items():
        assert meta.read_only, f"{name}: not marked as read_only"
    print("[PASS] All tools are read_only")


if __name__ == "__main__":
    print("=== tool registry tests ===\n")
    test_all_tools_have_required_fields()
    test_tool_names_unique()
    test_risk_levels_valid()
    test_profile_tags_valid()
    test_all_tools_read_only()
    print("\n=== all tool registry tests passed ===")
