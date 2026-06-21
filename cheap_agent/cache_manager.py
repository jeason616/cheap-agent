import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

from cheap_agent.config import (
    CACHE_DIR,
    CACHE_MASK_SECRETS,
    CACHE_SCHEMA_VERSION,
    CACHE_VERSION,
    CACHE_WRITE_ATOMIC,
    ENABLE_DISK_CACHE,
    MAX_CACHE_ENTRY_CHARS,
    MAX_CACHE_SIZE_MB,
    PERF_LOG_MAX_ENTRIES,
    WORKSPACE_ROOT,
)
from cheap_agent.logging_setup import get_logger

logger = get_logger("cheap_agent.cache_manager")

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api_key|token|secret|password|private_key|access_key|openai_api_key|llm_api_key|authorization|bearer)\s*[=:]\s*\S+"),
]


def make_cache_key(parts: list[str] | tuple[str, ...]) -> str:
    combined = "|".join(str(p) for p in parts)
    return hashlib.md5(combined.encode()).hexdigest()[:16]


def mask_secrets(text: str) -> str:
    if not CACHE_MASK_SECRETS:
        return text
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: m.group().split("=")[0].split(":")[0].strip() + "=***MASKED***", text)
    return text


def get_cache_dir() -> Path:
    raw = CACHE_DIR
    if os.path.isabs(raw):
        candidate = Path(raw).resolve()
    else:
        candidate = (WORKSPACE_ROOT / raw).resolve()

    root = WORKSPACE_ROOT.resolve()
    if not (candidate == root or root in candidate.parents):
        raise PermissionError(f"Cache dir '{raw}' resolves outside workspace root: {root}")
    return candidate


def ensure_cache_dir() -> Path:
    cache_dir = get_cache_dir()
    for sub in ["file_summaries", "directory_summaries", "tool_results", "perf_logs", "locks"]:
        (cache_dir / sub).mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_file_signature(path: Path) -> dict:
    try:
        st = path.stat()
        return {"path": str(path), "mtime": st.st_mtime, "size": st.st_size}
    except Exception:
        return {"path": str(path), "mtime": 0, "size": 0}


def get_dependency_signatures(paths: list[Path]) -> list[dict]:
    return [get_file_signature(p) for p in paths if p.exists()]


def is_cache_entry_valid(entry: dict, ttl_sec: int | None = None) -> bool:
    if not entry:
        return False

    if entry.get("schema_version") != CACHE_SCHEMA_VERSION:
        return False
    if entry.get("cache_version") != str(CACHE_VERSION):
        return False

    created = entry.get("created_at", 0)
    ttl = ttl_sec or entry.get("ttl_sec", 300)
    if time.time() - created > ttl:
        return False

    workspace = entry.get("workspace_root", "")
    if workspace and workspace != str(WORKSPACE_ROOT):
        return False

    for dep in entry.get("dependencies", []):
        dep_path = Path(dep["path"])
        if dep_path.exists():
            try:
                st = dep_path.stat()
                if abs(st.st_mtime - dep.get("mtime", 0)) > 0.01:
                    return False
                if st.st_size != dep.get("size", 0):
                    return False
            except Exception:
                pass

    return True


def read_json_cache(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        return json.loads(text)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to read cache %s: %s", path, e)
        return None


def write_json_cache_atomic(path: Path, data: dict) -> bool:
    if not CACHE_WRITE_ATOMIC:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.warning("Failed to write cache %s: %s", path, e)
            return False

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(path))
            return True
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            return False
    except Exception as e:
        logger.warning("Failed to write cache %s: %s", path, e)
        return False


def get_disk_cache(namespace: str, key: str, ttl_sec: int | None = None) -> str | dict | None:
    if not ENABLE_DISK_CACHE:
        return None

    try:
        cache_dir = get_cache_dir()
    except PermissionError:
        return None

    path = cache_dir / namespace / f"{key}.json"
    entry = read_json_cache(path)
    if entry is None:
        return None

    if not is_cache_entry_valid(entry, ttl_sec):
        try:
            path.unlink()
        except Exception:
            pass
        return None

    return entry.get("value")


def set_disk_cache(
    namespace: str,
    key: str,
    value: str | dict,
    ttl_sec: int | None = None,
    dependencies: list[Path] | None = None,
    tool: str = "",
) -> bool:
    if not ENABLE_DISK_CACHE:
        return False

    try:
        cache_dir = ensure_cache_dir()
    except PermissionError:
        return False

    if isinstance(value, str) and len(value) > MAX_CACHE_ENTRY_CHARS:
        value = value[:MAX_CACHE_ENTRY_CHARS] + f"\n\n... [truncated at {MAX_CACHE_ENTRY_CHARS} chars]"

    if CACHE_MASK_SECRETS and isinstance(value, str):
        value = mask_secrets(value)

    entry = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "cache_version": str(CACHE_VERSION),
        "created_at": time.time(),
        "updated_at": time.time(),
        "ttl_sec": ttl_sec or 300,
        "key": key,
        "tool": tool,
        "workspace_root": str(WORKSPACE_ROOT),
        "dependencies": get_dependency_signatures(dependencies) if dependencies else [],
        "value": value,
    }

    path = cache_dir / namespace / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_json_cache_atomic(path, entry)


def clear_cache_namespace(namespace: str | None = None) -> dict:
    try:
        cache_dir = get_cache_dir()
    except PermissionError:
        return {"cleared": 0, "bytes_freed": 0}

    cleared = 0
    bytes_freed = 0

    if namespace is None or namespace == "" or namespace == "all":
        targets = [cache_dir / d for d in ["file_summaries", "directory_summaries", "tool_results", "file_index.json", "project_profile.json", "project_map.json"]]
    else:
        targets = [cache_dir / namespace]

    for target in targets:
        if target.is_dir():
            for f in target.rglob("*.json"):
                try:
                    size = f.stat().st_size
                    f.unlink()
                    cleared += 1
                    bytes_freed += size
                except Exception:
                    pass
        elif target.is_file():
            try:
                size = target.stat().st_size
                target.unlink()
                cleared += 1
                bytes_freed += size
            except Exception:
                pass

    return {"cleared": cleared, "bytes_freed": bytes_freed}


def get_cache_stats() -> dict:
    try:
        cache_dir = get_cache_dir()
    except PermissionError:
        return {"enabled": False, "error": "cache dir not accessible"}

    if not cache_dir.exists():
        return {"enabled": True, "cache_dir": str(cache_dir), "total_size_bytes": 0, "namespaces": {}}

    total_size = 0
    namespaces = {}

    for ns_dir in cache_dir.iterdir():
        if not ns_dir.is_dir():
            continue
        ns_size = 0
        ns_count = 0
        for f in ns_dir.rglob("*.json"):
            try:
                ns_size += f.stat().st_size
                ns_count += 1
            except Exception:
                pass
        namespaces[ns_dir.name] = {"files": ns_count, "size_bytes": ns_size}
        total_size += ns_size

    for f in cache_dir.glob("*.json"):
        try:
            total_size += f.stat().st_size
        except Exception:
            pass

    return {
        "enabled": True,
        "cache_dir": str(cache_dir),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "max_size_mb": MAX_CACHE_SIZE_MB,
        "namespaces": namespaces,
    }


def enforce_cache_size_limit() -> dict:
    stats = get_cache_stats()
    total = stats.get("total_size_bytes", 0)
    limit = MAX_CACHE_SIZE_MB * 1024 * 1024

    if total <= limit:
        return {"trimmed": False, "total_bytes": total}

    try:
        cache_dir = get_cache_dir()
    except PermissionError:
        return {"trimmed": False, "error": "cache dir not accessible"}

    entries = []
    for f in cache_dir.rglob("*.json"):
        try:
            entries.append((f, f.stat().st_mtime, f.stat().st_size))
        except Exception:
            pass

    entries.sort(key=lambda x: x[1])

    removed = 0
    freed = 0
    for path, _mtime, size in entries:
        if total - freed <= limit:
            break
        try:
            path.unlink()
            freed += size
            removed += 1
        except Exception:
            pass

    return {"trimmed": True, "removed": removed, "bytes_freed": freed, "remaining_bytes": total - freed}


def record_tool_perf(tool_name: str, elapsed_sec: float, cache_hit: bool = False, extra: dict | None = None) -> None:
    try:
        cache_dir = ensure_cache_dir()
    except PermissionError:
        return

    log_path = cache_dir / "perf_logs" / "perf.jsonl"

    entry = {
        "time": time.time(),
        "tool": tool_name,
        "elapsed_sec": round(elapsed_sec, 3),
        "cache_hit": cache_hit,
    }
    if extra:
        safe_extra = {k: v for k, v in extra.items() if k not in ("error_log", "diff_text", "user_prompt", "system_prompt")}
        entry["extra"] = safe_extra

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) > PERF_LOG_MAX_ENTRIES:
                log_path.write_text("\n".join(lines[-PERF_LOG_MAX_ENTRIES:]) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write perf log: %s", e)
