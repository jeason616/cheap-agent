"""Full integration test: spawn the MCP server over stdio and call all tools.

Marked `integration` — skipped by default (see pyproject.toml addopts).
Run explicitly with:  pytest -m integration
"""

import json
import subprocess
import sys
import time

import pytest


@pytest.mark.integration
def test_integration_all_tools():
    proc = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    def send(obj):
        proc.stdin.write((json.dumps(obj) + "\n").encode())
        proc.stdin.flush()

    def recv(timeout=60):
        buf = b""
        start = time.time()
        while time.time() - start < timeout:
            b = proc.stdout.read(1)
            if b:
                buf += b
                if buf.endswith(b"\n"):
                    line = buf.decode().strip()
                    if line:
                        try:
                            return json.loads(line)
                        except Exception:
                            pass
                    buf = b""
        return None

    try:
        # Initialize
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.1"},
        }})
        r = recv(10)
        assert r, "initialize timed out"
        print("Init: OK")

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        time.sleep(0.5)

        tests = [
            # Phase 1: Reading
            (10, "search_code", {"query": "def review_file", "max_results": 3}),
            (11, "read_file_around_line", {"file_path": "cheap_agent/config.py", "line_number": 21}),
            (12, "extract_symbols", {"file_path": "cheap_agent/config.py"}),
            # Phase 2: Project understanding
            (13, "build_project_map", {"max_files": 20, "include_symbols": False}),
            (14, "detect_project_profile", {"use_llm": False}),
            # Phase 3: Diagnostics
            (15, "analyze_traceback_with_context", {"error_log": 'Traceback:\n  File "cheap_agent/config.py", line 21\nRuntimeError: test', "use_llm": False}),
            (16, "diagnose_import_error", {"error_log": "ModuleNotFoundError: No module named 'torch'", "use_llm": False}),
            (17, "diagnose_training_error", {"error_log": "RuntimeError: CUDA out of memory", "use_llm": False}),
            (18, "suggest_debug_steps", {"problem_description": "training loss is NaN", "use_llm": False}),
            # Phase 4: Testing
            (19, "suggest_minimal_repro", {"problem_description": "forward error", "use_llm": False}),
            (20, "generate_unit_test_plan", {"file_path": "cheap_agent/config.py", "use_llm": False}),
            (21, "check_config_consistency", {"use_llm": False}),
            (22, "suggest_validation_plan", {"task_description": "fix bug", "changed_files": "cheap_agent/config.py", "use_llm": False}),
            # Phase 5: Review
            (23, "risk_check_before_edit", {"task_description": "change config", "use_llm": False}),
            (24, "review_diff", {"diff_text": "diff --git a/test.py b/test.py\n+def new_func():\n+    pass", "use_llm": False}),
            (25, "post_edit_review", {"task_description": "fix bug", "changed_files": "cheap_agent/config.py", "use_llm": False}),
            (26, "analyze_change_impact", {"task_description": "change function", "target_files": "cheap_agent/config.py", "use_llm": False}),
            # Phase 6: Cache
            (27, "cache_status", {}),
            (28, "rebuild_project_index", {}),
            (29, "get_cached_project_context", {}),
            (30, "export_perf_report", {}),
            # Phase 7: Profile
            (31, "build_project_profile_v2", {"use_llm": False}),
            (32, "get_codex_onboarding_pack", {}),
            (33, "infer_project_runbook", {"use_llm": False}),
            (34, "recommend_workflow_for_task", {"task_description": "traceback error"}),
            (35, "explain_project_conventions", {"use_llm": False}),
            # Base tools
            (36, "summarize_project", {"max_files": 20}),
        ]

        passed = 0
        failed = 0

        for req_id, tool_name, arguments in tests:
            send({"jsonrpc": "2.0", "id": req_id, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}})
            r = recv(timeout=60)

            if r and "result" in r:
                content = r["result"].get("content", [])
                text = content[0].get("text", "") if content else ""
                if "[Tool Error]" in text:
                    print(f"[FAIL] {tool_name} - tool error: {text[:100]}")
                    failed += 1
                elif len(text) > 5:
                    print(f"[PASS] {tool_name} ({len(text)} chars)")
                    passed += 1
                else:
                    print(f"[FAIL] {tool_name} - empty response")
                    failed += 1
            else:
                err = r.get("error", {}).get("message", "timeout") if r else "timeout"
                print(f"[FAIL] {tool_name} - {err}")
                failed += 1

        print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)}")
        assert failed == 0, f"{failed} integration tool calls failed"
    finally:
        proc.terminate()
