from pathlib import Path

from config import MAX_FILE_CHARS, WORKSPACE_ROOT

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


def resolve_safe_path(path: str) -> Path:
    """Resolve a path and ensure it stays inside WORKSPACE_ROOT."""
    root = WORKSPACE_ROOT.resolve()
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if not (candidate == root or root in candidate.parents):
        raise PermissionError(
            f"Path '{path}' resolves outside workspace root: {root}"
        )
    return candidate


def _is_allowed_file(p: Path) -> bool:
    if p.suffix.lower() in ALLOWED_EXTENSIONS:
        return True
    if p.name in {"Makefile", "Dockerfile", "CMakeLists.txt", ".gitignore", ".dockerignore"}:
        return True
    return False


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS


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
        # skip hidden / ignored dirs
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
