"""Tests for Phase 6 memory and cache layer tools."""

import json
import sys
import tempfile
import time
from pathlib import Path


def test_get_cache_dir():
    from cheap_agent.cache_manager import get_cache_dir

    cache_dir = get_cache_dir()
    assert cache_dir is not None
    assert ".code_agent_cache" in str(cache_dir)
    print("[PASS] get_cache_dir normal")


def test_write_read_json_cache():
    from cheap_agent.cache_manager import read_json_cache, write_json_cache_atomic

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"
        data = {"key": "value", "number": 42}
        assert write_json_cache_atomic(path, data) is True
        assert path.exists()

        result = read_json_cache(path)
        assert result is not None
        assert result["key"] == "value"
        assert result["number"] == 42
        print("[PASS] write_json_cache_atomic / read_json_cache")

        result = read_json_cache(Path(tmpdir) / "nonexistent.json")
        assert result is None
        print("[PASS] read_json_cache nonexistent")

        bad_path = Path(tmpdir) / "bad.json"
        bad_path.write_text("not json", encoding="utf-8")
        result = read_json_cache(bad_path)
        assert result is None
        print("[PASS] read_json_cache corrupt JSON")


def test_mask_secrets():
    from cheap_agent.cache_manager import mask_secrets

    text = "API_KEY=secret123\nTOKEN=abc\nnormal=text"
    masked = mask_secrets(text)
    assert "secret123" not in masked
    assert "abc" not in masked
    assert "MASKED" in masked
    assert "normal=text" in masked
    print("[PASS] mask_secrets")


def test_set_get_disk_cache():
    from cheap_agent.cache_manager import ensure_cache_dir, get_disk_cache, set_disk_cache

    ensure_cache_dir()

    assert set_disk_cache("test_ns", "test_key", "test_value", ttl_sec=300) is True
    result = get_disk_cache("test_ns", "test_key", ttl_sec=300)
    assert result == "test_value"
    print("[PASS] set_disk_cache / get_disk_cache")

    result = get_disk_cache("test_ns", "nonexistent_key")
    assert result is None
    print("[PASS] get_disk_cache nonexistent")

    assert set_disk_cache("test_ns", "expired_key", "expired_value", ttl_sec=1) is True
    time.sleep(1.1)
    result = get_disk_cache("test_ns", "expired_key", ttl_sec=1)
    assert result is None
    print("[PASS] get_disk_cache TTL expired")


def test_clear_cache_namespace():
    from cheap_agent.cache_manager import ensure_cache_dir, set_disk_cache, clear_cache_namespace

    ensure_cache_dir()
    set_disk_cache("test_clear", "key1", "value1")
    set_disk_cache("test_clear", "key2", "value2")

    result = clear_cache_namespace("test_clear")
    assert result["cleared"] >= 0
    print("[PASS] clear_cache_namespace")


def test_get_cache_stats():
    from cheap_agent.cache_manager import get_cache_stats

    stats = get_cache_stats()
    assert "enabled" in stats
    assert "cache_dir" in stats
    assert "total_size_bytes" in stats
    assert "namespaces" in stats
    print("[PASS] get_cache_stats")


def test_cache_status():
    from cheap_agent.tools.cache_tools import cache_status_logic

    result = cache_status_logic()
    assert "Cache Status" in result
    assert "Disk cache enabled" in result
    assert "Cache dir" in result
    print("[PASS] cache_status")


def test_clear_cache():
    from cheap_agent.tools.cache_tools import clear_cache_logic

    result = clear_cache_logic("")
    assert "Cache Clear" in result
    print("[PASS] clear_cache empty (expired only)")

    result = clear_cache_logic("all")
    assert "Cache Clear" in result
    print("[PASS] clear_cache all")

    result = clear_cache_logic("invalid_namespace_xyz")
    assert "Error" in result
    print("[PASS] clear_cache invalid namespace")


def test_rebuild_project_index():
    from cheap_agent.tools.cache_tools import rebuild_project_index_logic

    result = rebuild_project_index_logic()
    assert "Project Index Rebuilt" in result
    assert "Files indexed" in result
    assert "Directories" in result
    assert "Time" in result
    print("[PASS] rebuild_project_index")


def test_get_cached_project_context():
    from cheap_agent.tools.cache_tools import get_cached_project_context_logic

    result = get_cached_project_context_logic()
    assert "Cached Project Context" in result
    print("[PASS] get_cached_project_context")


def test_export_perf_report():
    from cheap_agent.tools.cache_tools import export_perf_report_logic

    result = export_perf_report_logic()
    assert "Performance Report" in result
    print("[PASS] export_perf_report")


def test_record_tool_perf():
    from cheap_agent.cache_manager import ensure_cache_dir, record_tool_perf

    ensure_cache_dir()
    record_tool_perf("test_tool", 1.23, cache_hit=False, extra={"use_llm": True})
    record_tool_perf("test_tool", 0.45, cache_hit=True)

    from cheap_agent.cache_manager import get_cache_dir
    log_path = get_cache_dir() / "perf_logs" / "perf.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 2
    entry = json.loads(lines[-1])
    assert entry["tool"] == "test_tool"
    assert entry["cache_hit"] is True
    print("[PASS] record_tool_perf")


if __name__ == "__main__":
    print("=== cache tools tests ===\n")
    test_get_cache_dir()
    test_write_read_json_cache()
    test_mask_secrets()
    test_set_get_disk_cache()
    test_clear_cache_namespace()
    test_get_cache_stats()
    print()
    test_cache_status()
    test_clear_cache()
    test_rebuild_project_index()
    test_get_cached_project_context()
    test_export_perf_report()
    test_record_tool_perf()
    print("\n=== all cache tools tests passed ===")
