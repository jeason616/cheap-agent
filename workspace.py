import fnmatch
import time
from pathlib import Path

from config import MAX_FILE_CHARS, MAX_SCAN_FILE_SIZE_BYTES, WORKSPACE_ROOT

SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    "dist", "build", ".cache", ".idea", ".vscode",
}

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java",
    ".cpp", ".c", ".h", ".hpp", ".rs", ".go",
    ".md", ".txt", ".rst",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".sh", ".bat", ".ps1",
    ".html", ".css", ".scss",
    ".sql", ".graphql",
    ".env.example", ".gitignore", ".dockerignore",
    "Makefile", "Dockerfile", "CMakeLists.txt",
}

MAX_FILE_SIZE = 512 * 1024  # 512 KB

_file_cache: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL = 10.0


def resolve_safe_path(path: str) -> Path:
    """Resolve a path and ensure it stays inside WORKSPACE_ROOT."""
    root = WORKSPACE_ROOT.resolve()
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if not (candidate == root or root in candidate.parents):
        raise PermissionError(
            f"Path '{path}' resolves outside workspace root: {root}"
        )
    return candidate


def get_relative_path(path: Path) -> str:
    """Return a forward-slash relative path from WORKSPACE_ROOT."""
    try:
        rel = path.resolve().relative_to(WORKSPACE_ROOT.resolve())
    except ValueError:
        return str(path)
    return str(rel).replace("\\", "/")


def is_allowed_text_file(p: Path) -> bool:
    """Check if a file has an allowed text extension."""
    if p.suffix.lower() in ALLOWED_EXTENSIONS:
        return True
    if p.name in {"Makefile", "Dockerfile", "CMakeLists.txt", ".gitignore", ".dockerignore"}:
        return True
    return False


def is_skipped_dir(name: str) -> bool:
    """Check if a directory name should be skipped."""
    return name in SKIP_DIRS


def _is_allowed_file(p: Path) -> bool:
    return is_allowed_text_file(p)


def _should_skip_dir(name: str) -> bool:
    return is_skipped_dir(name)


def read_text_file(path: str, max_chars: int | None = None) -> str:
    """Read a text file safely within the workspace."""
    target = resolve_safe_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {target}")
    file_size = target.stat().st_size
    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({file_size} bytes): {target}")

    limit = max_chars or MAX_FILE_CHARS
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + f"\n\n... [truncated at {limit} chars]"
    return text


def list_project_files(
    keyword: str | None = None,
    max_files: int = 200,
) -> list[str]:
    """List code/text files in the workspace, optionally filtered by keyword."""
    root = WORKSPACE_ROOT.resolve()
    results: list[str] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if any(_should_skip_dir(part) for part in parts):
            continue
        if not _is_allowed_file(p):
            continue
        if p.stat().st_size > MAX_FILE_SIZE:
            continue

        rel_str = str(rel).replace("\\", "/")
        if keyword and keyword.lower() not in rel_str.lower():
            continue

        results.append(rel_str)
        if len(results) >= max_files:
            break

    return sorted(results)


def get_project_files_cached(
    keyword: str | None = None,
    max_files: int = 200,
    file_glob: str = "",
) -> list[str]:
    """List project files with a short-lived cache to avoid repeated fs scans."""
    cache_key = f"{keyword}:{max_files}:{file_glob}"
    now = time.monotonic()

    if cache_key in _file_cache:
        ts, cached = _file_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return cached

    files = list_project_files(keyword=keyword, max_files=max_files)

    if file_glob:
        files = [f for f in files if fnmatch.fnmatch(f, file_glob)]

    _file_cache[cache_key] = (now, files)
    return files


def build_file_index(max_files: int | None = None) -> list[dict]:
    """Build a detailed file index with metadata."""
    from config import MAX_FILE_CHARS as _max
    limit = max_files or 500
    root = WORKSPACE_ROOT.resolve()
    results: list[dict] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if any(_should_skip_dir(part) for part in parts):
            continue
        if not _is_allowed_file(p):
            continue

        try:
            st = p.stat()
        except Exception:
            continue

        if st.st_size > MAX_FILE_SIZE:
            continue

        rel_str = str(rel).replace("\\", "/")
        suffix = p.suffix.lstrip(".") if p.suffix else p.name.lower()

        results.append({
            "path": rel_str,
            "suffix": suffix,
            "size": st.st_size,
            "mtime": st.st_mtime,
        })

        if len(results) >= limit:
            break

    results.sort(key=lambda x: x["path"])
    return results


def get_file_index_cached(force_rebuild: bool = False) -> list[dict]:
    """Get file index with disk cache support."""
    from cache_manager import get_disk_cache, set_disk_cache, ensure_cache_dir, write_json_cache_atomic
    from config import FILE_INDEX_CACHE_TTL_SEC, ENABLE_FILE_INDEX_CACHE

    if not force_rebuild and ENABLE_FILE_INDEX_CACHE:
        cached = get_disk_cache("file_index", "file_index", ttl_sec=FILE_INDEX_CACHE_TTL_SEC)
        if cached and isinstance(cached, dict) and "files" in cached:
            return cached["files"]

    index = build_file_index()

    if ENABLE_FILE_INDEX_CACHE:
        cache_dir = ensure_cache_dir()
        index_data = {
            "files": index,
            "total": len(index),
            "created_at": time.time(),
        }
        write_json_cache_atomic(cache_dir / "file_index.json", index_data)
        set_disk_cache("file_index", "file_index", index_data, ttl_sec=FILE_INDEX_CACHE_TTL_SEC, tool="build_file_index")

    return index


def get_file_index_version(file_index: list[dict]) -> str:
    """Generate a version hash from file index."""
    import hashlib
    parts = [f"{f['path']}:{f['mtime']}:{f['size']}" for f in file_index[:200]]
    combined = "|".join(parts)
    return hashlib.md5(combined.encode()).hexdigest()[:12]
