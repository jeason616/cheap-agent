import ast
import fnmatch
import re
import sys
from pathlib import Path

from config import MAX_CONTEXT_LINES, MAX_OUTPUT_CHARS, MAX_SEARCH_RESULTS, WORKSPACE_ROOT
from workspace import get_project_files_cached, get_relative_path, is_allowed_text_file, is_skipped_dir, resolve_safe_path, MAX_FILE_SIZE


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"


# ---------------------------------------------------------------------------
# read_file_around_line
# ---------------------------------------------------------------------------

def read_file_around_line_logic(
    file_path: str,
    line_number: int,
    context_lines: int = 80,
) -> str:
    """Read a snippet of code around a specific line number."""
    if line_number < 1:
        return "[Error] line_number must be >= 1"

    context_lines = min(context_lines, MAX_CONTEXT_LINES)

    target = resolve_safe_path(file_path)
    if not target.is_file():
        return f"[Error] File not found: {file_path}"
    if target.stat().st_size > MAX_FILE_SIZE:
        return f"[Error] File too large ({target.stat().st_size} bytes): {file_path}"

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"[Error] Cannot read file: {e}"

    total = len(lines)
    if line_number > total:
        return f"[Error] line_number {line_number} exceeds total lines ({total}) in {file_path}"

    half = context_lines // 2
    start = max(1, line_number - half)
    end = min(total, line_number + half)

    rel = get_relative_path(target)
    output_lines = [f"File: {rel}", f"Total lines: {total}", f"Showing lines {start}-{end} around line {line_number}", ""]

    width = len(str(end))
    for i in range(start - 1, end):
        lineno = i + 1
        prefix = ">> " if lineno == line_number else "   "
        output_lines.append(f"{prefix}{lineno:>{width}} | {lines[i]}")

    return _truncate("\n".join(output_lines), MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# extract_symbols
# ---------------------------------------------------------------------------

def _extract_python_symbols(target: Path) -> str:
    """Extract symbols from a Python file using ast."""
    file_size = target.stat().st_size
    if file_size > 2 * 1024 * 1024:
        return f"[Error] File too large for AST parsing ({file_size} bytes)"

    try:
        source = target.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(target))
    except SyntaxError as e:
        return f"[Error] Python syntax error: {e}"
    except Exception as e:
        return f"[Error] Cannot parse file: {e}"

    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []
    variables: list[str] = []
    main_entry: str | None = None

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(a.name for a in node.names)
            imports.append(f"from {module} import {names}")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = _format_args(node.args)
            doc = _get_docstring_first_line(node)
            suffix = f'  # "{doc}"' if doc else ""
            functions.append(f"- {node.name}(line {node.lineno}): args=({args}){suffix}")
        elif isinstance(node, ast.ClassDef):
            bases = [getattr(b, "id", getattr(b, "attr", "?")) for b in node.bases]
            classes.append(f"- {node.name}(line {node.lineno}), bases=[{', '.join(bases)}]")
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    margs = _format_args(item.args)
                    classes.append(f"  - {item.name}(line {item.lineno}): args=({margs})")
        elif isinstance(node, ast.Assign):
            for target_node in node.targets:
                if isinstance(target_node, ast.Name):
                    name = target_node.id
                    if name.isupper() or name.startswith("_"):
                        variables.append(f"- {name}")
        elif isinstance(node, ast.If):
            if _is_main_guard(node):
                main_entry = f"Found if __name__ == '__main__' at line {node.lineno}"

    rel = get_relative_path(target)
    parts = [f"File: {rel}", "Language: Python", ""]

    parts.append("Imports:")
    parts.extend(f"- {s}" for s in imports) if imports else parts.append("- (none)")
    parts.append("")

    parts.append("Top-level functions:")
    parts.extend(functions) if functions else parts.append("- (none)")
    parts.append("")

    parts.append("Classes:")
    parts.extend(classes) if classes else parts.append("- (none)")
    parts.append("")

    parts.append("Top-level variables:")
    parts.extend(variables) if variables else parts.append("- (none)")
    parts.append("")

    if main_entry:
        parts.append("Main entry:")
        parts.append(f"- {main_entry}")
    else:
        parts.append("Main entry: not found")

    return _truncate("\n".join(parts), MAX_OUTPUT_CHARS)


def _extract_generic_symbols(target: Path) -> str:
    """Simple regex-based symbol extraction for non-Python files."""
    if target.stat().st_size > MAX_FILE_SIZE:
        return f"[Error] File too large ({target.stat().st_size} bytes)"

    try:
        source = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[Error] Cannot read file: {e}"

    lines = source.splitlines()
    ext = target.suffix.lower()

    patterns: list[tuple[str, re.Pattern]] = []
    if ext in (".js", ".ts", ".tsx", ".jsx"):
        patterns = [
            ("Function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)")),
            ("ArrowFunc", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(")),
            ("Class", re.compile(r"^\s*(?:export\s+)?class\s+(\w+)")),
            ("Import", re.compile(r"^\s*import\s+")),
            ("Export", re.compile(r"^\s*export\s+")),
        ]
    elif ext in (".java",):
        patterns = [
            ("Class", re.compile(r"^\s*(?:public\s+)?(?:abstract\s+)?(?:class|interface)\s+(\w+)")),
            ("Method", re.compile(r"^\s*(?:public|private|protected)?\s*\w+\s+(\w+)\s*\(")),
        ]
    elif ext in (".cpp", ".c", ".h", ".hpp"):
        patterns = [
            ("Function", re.compile(r"^\s*\w[\w\s\*]+?\s+(\w+)\s*\([^)]*\)\s*\{")),
            ("Include", re.compile(r"^\s*#include\s+")),
        ]
    else:
        patterns = [
            ("Function", re.compile(r"^\s*(?:function|def|fn)\s+(\w+)")),
            ("Class", re.compile(r"^\s*(?:class|struct)\s+(\w+)")),
        ]

    findings: dict[str, list[str]] = {name: [] for name, _ in patterns}
    for i, line in enumerate(lines, 1):
        for label, pat in patterns:
            m = pat.search(line)
            if m:
                name = m.group(1) if m.lastindex else line.strip()[:60]
                findings[label].append(f"- {name} (line {i})")

    rel = get_relative_path(target)
    parts = [f"File: {rel}", f"Language: {ext.lstrip('.') or 'unknown'}", "", "Note: non-Python file, using simplified regex extraction.", ""]

    for label, _ in patterns:
        items = findings[label]
        parts.append(f"{label}:")
        parts.extend(items[:50]) if items else parts.append("- (none)")
        parts.append("")

    return _truncate("\n".join(parts), MAX_OUTPUT_CHARS)


def extract_symbols_logic(file_path: str) -> str:
    """Extract structural symbols from a code file."""
    target = resolve_safe_path(file_path)
    if not target.is_file():
        return f"[Error] File not found: {file_path}"

    if target.suffix.lower() == ".py":
        return _extract_python_symbols(target)
    return _extract_generic_symbols(target)


def _format_args(args: ast.arguments) -> str:
    parts: list[str] = []
    for a in args.args:
        parts.append(a.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    return ", ".join(parts)


def _get_docstring_first_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        doc = ast.get_docstring(node)
        if doc:
            return doc.strip().split("\n")[0][:80]
    except Exception:
        pass
    return ""


def _is_main_guard(node: ast.If) -> bool:
    try:
        test = node.test
        if isinstance(test, ast.Compare):
            left = test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                for comp in test.comparators:
                    if isinstance(comp, ast.Constant) and comp.value == "__main__":
                        return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# search_code
# ---------------------------------------------------------------------------

def search_code_logic(
    query: str,
    file_glob: str = "",
    max_results: int = 50,
    case_sensitive: bool = False,
) -> str:
    """Search for a keyword in project files using Python stdlib only."""
    if not query or not query.strip():
        return "[Error] query must not be empty"

    max_results = min(max_results, MAX_SEARCH_RESULTS)
    root = WORKSPACE_ROOT.resolve()

    files = get_project_files_cached(max_files=5000, file_glob=file_glob)

    pattern = re.compile(re.escape(query), 0 if case_sensitive else re.IGNORECASE)
    results: list[str] = []
    scanned = 0

    for rel_path in files:
        if len(results) >= max_results:
            break

        abs_path = root / rel_path
        if not abs_path.is_file():
            continue
        if abs_path.stat().st_size > MAX_FILE_SIZE:
            continue

        try:
            lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        scanned += 1
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                results.append(f"{rel_path}:{i}\n  {line.rstrip()}")
                if len(results) >= max_results:
                    break

    header = f"Search query: {query}\nScanned files: {scanned}\nResults: {len(results)}\n"
    if not results:
        return header + "\n(no matches found)"
    return _truncate(header + "\n" + "\n\n".join(results), MAX_OUTPUT_CHARS)
