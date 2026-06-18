import re
from collections import Counter
from pathlib import Path

from cheap_agent.config import MAX_BIB_ENTRIES, WORKSPACE_ROOT
from cheap_agent.workspace import resolve_safe_path, SKIP_DIRS, MAX_FILE_SIZE


def find_bib_files(max_files: int | None = None) -> list[str]:
    limit = max_files or 50
    root = WORKSPACE_ROOT.resolve()
    results = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if any(d in SKIP_DIRS for d in parts):
            continue
        if p.suffix.lower() == ".bib" and p.stat().st_size <= MAX_FILE_SIZE:
            results.append(str(rel).replace("\\", "/"))
        if len(results) >= limit:
            break
    return sorted(results)


def read_bib_file_safe(file_path: str, max_chars: int | None = None) -> str:
    target = resolve_safe_path(file_path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    if target.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({target.stat().st_size} bytes): {file_path}")
    limit = max_chars or 200000
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + f"\n\n... [truncated at {limit} chars]"
    return text


_RE_BIB_ENTRY = re.compile(
    r"@(\w+)\s*\{\s*([^,\s]+)\s*,",
    re.IGNORECASE,
)
_RE_BIB_FIELD = re.compile(
    r"(\w+)\s*=\s*\{([^}]*)\}",
    re.IGNORECASE,
)


def parse_bib_entries(bib_text: str, max_entries: int | None = None) -> list[dict]:
    limit = max_entries or MAX_BIB_ENTRIES
    entries = []
    seen_keys: set[str] = set()

    chunks = re.split(r"(?=@\w+\s*\{)", bib_text)

    for chunk in chunks:
        if len(entries) >= limit:
            break
        chunk = chunk.strip()
        if not chunk:
            continue

        m = _RE_BIB_ENTRY.match(chunk)
        if not m:
            continue

        entry_type = m.group(1).lower()
        key = m.group(2).strip()

        fields = {}
        for fm in _RE_BIB_FIELD.finditer(chunk):
            fname = fm.group(1).lower()
            fval = fm.group(2).strip()
            fields[fname] = fval

        is_duplicate = key in seen_keys
        seen_keys.add(key)

        preview = chunk[:200].replace("\n", " ")

        entries.append({
            "key": key,
            "type": entry_type,
            "title": fields.get("title", ""),
            "author": fields.get("author", ""),
            "year": fields.get("year", ""),
            "journal": fields.get("journal", ""),
            "booktitle": fields.get("booktitle", ""),
            "is_duplicate": is_duplicate,
            "raw_preview": preview,
        })

    return entries


def parse_bib_keys_from_text(bib_text: str) -> set[str]:
    keys = set()
    for m in _RE_BIB_ENTRY.finditer(bib_text):
        keys.add(m.group(2).strip())
    return keys


def summarize_bib_entries(entries: list[dict]) -> str:
    if not entries:
        return "No bib entries found."

    type_counts = Counter(e["type"] for e in entries)
    year_counts = Counter(e["year"] for e in entries if e["year"])
    missing_year = sum(1 for e in entries if not e["year"])
    missing_title = sum(1 for e in entries if not e["title"])
    duplicates = [e["key"] for e in entries if e["is_duplicate"]]

    parts = [f"Total entries: {len(entries)}", ""]

    parts.append("Entry types:")
    for t, c in type_counts.most_common():
        parts.append(f"  - {t}: {c}")
    parts.append("")

    parts.append("Year distribution:")
    for y, c in sorted(year_counts.items(), reverse=True)[:15]:
        parts.append(f"  - {y}: {c}")
    parts.append("")

    parts.append("Sample entries:")
    for i, e in enumerate(entries[:10], 1):
        title_short = e["title"][:80] + "..." if len(e["title"]) > 80 else e["title"]
        parts.append(f"  {i}. {e['key']}")
        parts.append(f"     Type: {e['type']}, Year: {e['year'] or '(none)'}")
        if title_short:
            parts.append(f"     Title: {title_short}")
    parts.append("")

    issues = []
    if missing_year:
        issues.append(f"- {missing_year} entries missing year")
    if missing_title:
        issues.append(f"- {missing_title} entries missing title")
    if duplicates:
        issues.append(f"- {len(duplicates)} duplicate key(s): {', '.join(duplicates[:5])}")
    if issues:
        parts.append("Potential issues:")
        parts.extend(issues)

    return "\n".join(parts)
