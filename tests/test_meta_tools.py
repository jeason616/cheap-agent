"""Tests for meta tools."""

import sys


def test_list_available_tools():
    from cheap_agent.tools.meta import list_available_tools_logic

    result = list_available_tools_logic()
    assert "Available MCP Tools" in result
    assert "Active profile" in result
    print("[PASS] list_available_tools")

    result = list_available_tools_logic(include_disabled=True)
    assert "Disabled" in result or "Available" in result
    print("[PASS] list_available_tools with disabled")


def test_show_active_profile():
    from cheap_agent.tools.meta import show_active_profile_logic

    result = show_active_profile_logic()
    assert "Active MCP Profile" in result
    assert "Profile:" in result
    assert "Safety:" in result
    print("[PASS] show_active_profile")


def test_explain_tool_routing():
    from cheap_agent.tools.meta import explain_tool_routing_logic

    result = explain_tool_routing_logic("检查论文实验表格")
    assert "Tool Routing Suggestion" in result
    assert "Recommended" in result
    print("[PASS] explain_tool_routing basic")

    result = explain_tool_routing_logic("")
    assert "Error" in result
    print("[PASS] explain_tool_routing empty input")


if __name__ == "__main__":
    print("=== meta tools tests ===\n")
    test_list_available_tools()
    test_show_active_profile()
    test_explain_tool_routing()
    print("\n=== all meta tools tests passed ===")
