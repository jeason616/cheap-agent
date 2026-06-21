import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from cheap_agent.cache_manager import (
    clear_cache_namespace,
    ensure_cache_dir,
    get_cache_dir,
    get_cache_stats,
    record_tool_perf,
)
from cheap_agent.config import ENABLE_DISK_CACHE, PERF_LOG_MAX_ENTRIES, WORKSPACE_ROOT
from cheap_agent.workspace import get_relative_path



# ---------------------------------------------------------------------------
# cache_status
# ---------------------------------------------------------------------------

def cache_status_logic() -> str:
    stats = get_cache_stats()

    parts = ["Cache Status", ""]
    parts.append(f"Disk cache enabled: {ENABLE_DISK_CACHE}")
    parts.append(f"Cache dir: {stats.get('cache_dir', 'N/A')}")
    parts.append(f"Total size: {stats.get('total_size_mb', 0)} MB")
    parts.append(f"Max size: {stats.get('max_size_mb', 200)} MB")
    parts.append("")

    parts.append("Namespaces:")
    for ns, info in stats.get("namespaces", {}).items():
        size_kb = info.get("size_bytes", 0) / 1024
        parts.append(f"  - {ns}: {info.get('files', 0)} files, {size_kb:.1f} KB")
    parts.append("")

    perf_summary = _get_perf_summary(limit=5)
    if perf_summary:
        parts.append("Recent performance (slowest tools):")
        for i, (tool, avg_time) in enumerate(perf_summary, 1):
            parts.append(f"  {i}. {tool}: {avg_time:.1f}s avg")
        parts.append("")

    parts.append("Notes:")
    parts.append("  - Cache is stored in .code_agent_cache/ inside WORKSPACE_ROOT")
    parts.append("  - File changes automatically invalidate related cache entries")
    parts.append("  - Use clear_cache to clean expired or all cache")

    return "\n".join(parts)


def _get_perf_summary(limit: int = 5) -> list[tuple[str, float]]:
    try:
        cache_dir = get_cache_dir()
        log_path = cache_dir / "perf_logs" / "perf.jsonl"
        if not log_path.exists():
            return []

        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tool_times: dict[str, list[float]] = defaultdict(list)
        for line in lines[-PERF_LOG_MAX_ENTRIES:]:
            try:
                entry = json.loads(line)
                tool = entry.get("tool", "")
                elapsed = entry.get("elapsed_sec", 0)
                if tool:
                    tool_times[tool].append(elapsed)
            except Exception:
                pass

        avg_times = [(tool, sum(times) / len(times)) for tool, times in tool_times.items()]
        avg_times.sort(key=lambda x: -x[1])
        return avg_times[:limit]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------

def clear_cache_logic(namespace: str = "") -> str:
    if namespace and namespace not in ("all", "file_index", "file_summaries", "directory_summaries", "project_profile", "project_map", "tool_results", "perf_logs"):
        return f"[Error] Unknown namespace: {namespace}. Allowed: all, file_index, file_summaries, directory_summaries, project_profile, project_map, tool_results, perf_logs"

    result = clear_cache_namespace(namespace or None)

    parts = ["Cache Clear", ""]
    parts.append(f"Namespace: {namespace or '(expired only)'}")
    parts.append(f"Cleared entries: {result.get('cleared', 0)}")
    bytes_freed = result.get("bytes_freed", 0)
    parts.append(f"Space freed: {bytes_freed / 1024:.1f} KB")
    parts.append("")
    parts.append("Note: Only cache files were removed. Project source files were not modified.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# rebuild_project_index
# ---------------------------------------------------------------------------

def rebuild_project_index_logic() -> str:
    from cheap_agent.workspace import SKIP_DIRS, ALLOWED_EXTENSIONS, MAX_FILE_SIZE

    start = time.time()
    root = WORKSPACE_ROOT.resolve()
    cache_dir = ensure_cache_dir()

    files = []
    dirs_seen = set()
    skipped_dirs = 0
    ext_count: dict[str, int] = defaultdict(int)

    for p in root.rglob("*"):
        if not p.is_file():
            if p.is_dir():
                rel = str(p.relative_to(root)).replace("\\", "/")
                parts = rel.split("/")
                if any(d in SKIP_DIRS for d in parts):
                    skipped_dirs += 1
                else:
                    dirs_seen.add(rel)
            continue

        rel = p.relative_to(root)
        parts = rel.parts
        if any(d in SKIP_DIRS for d in parts):
            continue

        ext = p.suffix.lower()
        fname = p.name.lower()
        if ext not in ALLOWED_EXTENSIONS and fname not in {"Makefile", "Dockerfile", "CMakeLists.txt", ".gitignore", ".dockerignore"}:
            continue

        try:
            st = p.stat()
        except Exception:
            continue

        if st.st_size > MAX_FILE_SIZE:
            continue

        rel_str = str(rel).replace("\\", "/")
        suffix = ext.lstrip(".") if ext else fname

        category = _classify_file(rel_str, ext, fname)
        is_code = ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".c", ".h", ".hpp", ".rs", ".go")
        is_config = ext in (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".env") or fname in ("config.py", "settings.py")
        is_test = "test" in rel_str.lower() or fname.startswith("test_") or fname.endswith("_test.py")

        files.append({
            "path": rel_str,
            "suffix": suffix,
            "size": st.st_size,
            "mtime": st.st_mtime,
            "is_code": is_code,
            "is_config": is_config,
            "is_test": is_test,
            "category": category,
        })

    files.sort(key=lambda x: x["path"])

    index_data = {
        "schema_version": 1,
        "created_at": time.time(),
        "workspace_root": str(WORKSPACE_ROOT),
        "total_files": len(files),
        "total_dirs": len(dirs_seen),
        "skipped_dirs": skipped_dirs,
        "files": files,
    }

    index_path = cache_dir / "file_index.json"
    from cheap_agent.cache_manager import write_json_cache_atomic
    write_json_cache_atomic(index_path, index_data)

    elapsed = time.time() - start

    parts = ["Project Index Rebuilt", ""]
    parts.append(f"Files indexed: {len(files)}")
    parts.append(f"Directories: {len(dirs_seen)}")
    parts.append(f"Skipped dirs: {skipped_dirs}")
    parts.append(f"Time: {elapsed:.2f}s")
    parts.append("")

    for ext, count in sorted(ext_count.items(), key=lambda x: -x[1])[:10]:
        parts.append(f"  .{ext}: {count}")

    top_cats = defaultdict(int)
    for f in files:
        top_cats[f["category"]] += 1
    parts.append("\nBy category:")
    for cat, count in sorted(top_cats.items(), key=lambda x: -x[1]):
        parts.append(f"  {cat}: {count}")

    return "\n".join(parts)


def _classify_file(rel_path: str, ext: str, fname: str) -> str:
    lower = rel_path.lower()
    parts = lower.split("/")

    if fname.startswith("test_") or fname.endswith("_test.py") or "test" in parts:
        return "test"
    if ext in (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg") or "config" in parts or "setting" in parts:
        return "config"
    if ext in (".md", ".rst", ".txt") or "doc" in parts or "readme" in fname:
        return "doc"
    if ext in (".sh", ".bat", ".ps1"):
        return "script"
    if any(w in parts for w in ["model", "models", "network", "backbone"]):
        return "model"
    if any(w in parts for w in ["data", "dataset", "datasets", "dataloader"]):
        return "dataset"
    if any(w in parts for w in ["train", "training"]):
        return "training"
    if any(w in parts for w in ["infer", "inference", "predict", "deploy"]):
        return "inference"
    if any(w in parts for w in ["eval", "evaluate", "benchmark"]):
        return "evaluation"
    if ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".c", ".h", ".hpp", ".rs", ".go"):
        return "code"
    return "other"


# ---------------------------------------------------------------------------
# get_cached_project_context
# ---------------------------------------------------------------------------

def get_cached_project_context_logic(
    include_profile: bool = True,
    include_map: bool = True,
    include_recent_summaries: bool = True,
    max_items: int = 20,
) -> str:
    from cheap_agent.cache_manager import get_disk_cache, read_json_cache, get_cache_dir

    parts = ["Cached Project Context", ""]

    if include_profile:
        profile = get_disk_cache("project_profile", "project_profile")
        if profile:
            parts.append("Project profile:")
            if isinstance(profile, str):
                parts.append(profile[:1000])
            else:
                parts.append(json.dumps(profile, ensure_ascii=False)[:1000])
            parts.append("")
        else:
            parts.append("Project profile: (not cached)")
            parts.append("  Suggest: call detect_project_profile(use_llm=False)")
            parts.append("")

    if include_map:
        project_map = get_disk_cache("project_map", "project_map")
        if project_map:
            parts.append("Project map:")
            if isinstance(project_map, str):
                parts.append(project_map[:1500])
            else:
                parts.append(json.dumps(project_map, ensure_ascii=False)[:1500])
            parts.append("")
        else:
            parts.append("Project map: (not cached)")
            parts.append("  Suggest: call build_project_map()")
            parts.append("")

    if include_recent_summaries:
        try:
            cache_dir = get_cache_dir()
            fs_dir = cache_dir / "file_summaries"
            if fs_dir.exists():
                summaries = []
                for f in sorted(fs_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:max_items]:
                    entry = read_json_cache(f)
                    if entry and "value" in entry:
                        tool = entry.get("tool", "")
                        value = entry["value"]
                        if isinstance(value, str):
                            first_line = value.split("\n")[0][:100]
                            summaries.append(f"  - [{tool}] {first_line}")

                if summaries:
                    parts.append(f"Recent file summaries ({len(summaries)}):")
                    parts.extend(summaries)
                    parts.append("")
        except Exception:
            pass

        try:
            cache_dir = get_cache_dir()
            ds_dir = cache_dir / "directory_summaries"
            if ds_dir.exists():
                summaries = []
                for f in sorted(ds_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:max_items]:
                    entry = read_json_cache(f)
                    if entry and "value" in entry:
                        value = entry["value"]
                        if isinstance(value, str):
                            first_line = value.split("\n")[0][:100]
                            summaries.append(f"  - {first_line}")

                if summaries:
                    parts.append(f"Recent directory summaries ({len(summaries)}):")
                    parts.extend(summaries)
                    parts.append("")
        except Exception:
            pass

    parts.append("Suggested first-read files:")
    parts.append("  1. README.md")
    parts.append("  2. server.py")
    parts.append("  3. config.py")
    parts.append("  4. workspace.py")
    parts.append("")

    stats = get_cache_stats()
    parts.append("Cache freshness:")
    parts.append(f"  - Total cache size: {stats.get('total_size_mb', 0)} MB")
    for ns, info in stats.get("namespaces", {}).items():
        parts.append(f"  - {ns}: {info.get('files', 0)} entries")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# export_perf_report
# ---------------------------------------------------------------------------

def export_perf_report_logic(limit: int = 100) -> str:
    try:
        cache_dir = get_cache_dir()
        log_path = cache_dir / "perf_logs" / "perf.jsonl"
        if not log_path.exists():
            return "Performance Report\n\nNo performance data recorded yet."
    except PermissionError:
        return "Performance Report\n\nCache dir not accessible."

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass

    if not entries:
        return "Performance Report\n\nNo performance data recorded yet."

    tool_times: dict[str, list[float]] = defaultdict(list)
    tool_cache_hits: dict[str, int] = defaultdict(int)
    tool_total: dict[str, int] = defaultdict(int)

    for entry in entries:
        tool = entry.get("tool", "")
        elapsed = entry.get("elapsed_sec", 0)
        cache_hit = entry.get("cache_hit", False)
        if tool:
            tool_times[tool].append(elapsed)
            tool_total[tool] += 1
            if cache_hit:
                tool_cache_hits[tool] += 1

    parts = ["Performance Report", ""]
    parts.append(f"Total recorded calls: {len(entries)}")
    parts.append("")

    avg_times = [(tool, sum(times) / len(times)) for tool, times in tool_times.items()]
    avg_times.sort(key=lambda x: -x[1])

    parts.append("Average latency by tool:")
    for tool, avg in avg_times:
        total = tool_total[tool]
        hits = tool_cache_hits[tool]
        hit_rate = (hits / total * 100) if total > 0 else 0
        parts.append(f"  - {tool}: {avg:.2f}s avg ({total} calls, {hit_rate:.0f}% cache hit)")
    parts.append("")

    slowest = sorted(entries, key=lambda x: -x.get("elapsed_sec", 0))[:10]
    parts.append("Slowest recent calls:")
    for i, entry in enumerate(slowest, 1):
        tool = entry.get("tool", "?")
        elapsed = entry.get("elapsed_sec", 0)
        hit = "[cache hit]" if entry.get("cache_hit") else ""
        parts.append(f"  {i}. {tool}: {elapsed:.2f}s {hit}")
    parts.append("")

    parts.append("Optimization suggestions:")
    for tool, avg in avg_times[:3]:
        if avg > 5:
            parts.append(f"  - {tool} is slow ({avg:.1f}s avg), consider use_llm=False or reduce input size")
        elif avg > 2:
            parts.append(f"  - {tool} is moderate ({avg:.1f}s avg), cache may help on repeated calls")

    return "\n".join(parts)
