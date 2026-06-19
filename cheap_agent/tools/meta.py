"""Meta tools for MCP self-diagnostics and tool routing."""

from cheap_agent.profiles import (
    classify_task_for_routing,
    format_active_profile_report,
    format_available_tools_report,
    get_active_profile,
    get_tools_for_routing,
    is_tool_allowed,
)


def list_available_tools_logic(
    include_disabled: bool = False,
    group: str = "",
) -> str:
    report = format_available_tools_report(include_disabled=include_disabled)

    if group:
        lines = report.split("\n")
        filtered = []
        in_target = False
        for line in lines:
            if line.startswith(f"[{group}]"):
                in_target = True
                filtered.append(line)
            elif line.startswith("[") and line.endswith("]"):
                in_target = False
            elif in_target:
                filtered.append(line)
        if filtered:
            return "\n".join(filtered)
        return f"No tools found for group '{group}'."

    return report


def show_active_profile_logic() -> str:
    return format_active_profile_report()


def explain_tool_routing_logic(task_description: str = "") -> str:
    if not task_description or not task_description.strip():
        return "[Error] task_description must not be empty."

    task_type = classify_task_for_routing(task_description)
    recommended = get_tools_for_routing(task_type)
    profile = get_active_profile()

    enabled_recs = [t for t in recommended if is_tool_allowed(t)]
    disabled_recs = [t for t in recommended if not is_tool_allowed(t)]

    parts = ["Tool Routing Suggestion", ""]
    parts.append(f"Task: {task_description[:200]}")
    parts.append(f"Detected task type: {task_type}")
    parts.append(f"Current profile: {profile}")
    parts.append("")

    if enabled_recs:
        parts.append("Recommended enabled tools:")
        for i, t in enumerate(enabled_recs, 1):
            parts.append(f"  {i}. {t}")
    else:
        parts.append("No recommended tools are currently enabled.")
        parts.append("Consider switching profile to 'full' or the appropriate profile.")

    if disabled_recs:
        parts.append("")
        parts.append("Disabled tools (need profile change to enable):")
        for t in disabled_recs:
            parts.append(f"  - {t}")

    parts.append("")
    parts.append("Notes:")
    parts.append("  - Only currently enabled tools are recommended")
    parts.append("  - Switch profile via MCP_PROFILE in .env if needed")

    return "\n".join(parts)
