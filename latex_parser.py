import re
from pathlib import Path

from config import MAX_TEX_FILE_CHARS, MAX_MARKDOWN_FILE_CHARS, MAX_PAPER_FILES, WORKSPACE_ROOT
from workspace import resolve_safe_path, get_relative_path, SKIP_DIRS, MAX_FILE_SIZE


_TEX_EXTS = {".tex", ".sty", ".cls", ".bib"}
_MD_EXTS = {".md", ".markdown", ".txt", ".rst"}


def find_tex_files(max_files: int | None = None) -> list[str]:
    limit = max_files or MAX_PAPER_FILES
    root = WORKSPACE_ROOT.resolve()
    results = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if any(d in SKIP_DIRS for d in parts):
            continue
        if p.suffix.lower() in _TEX_EXTS and p.stat().st_size <= MAX_FILE_SIZE:
            results.append(str(rel).replace("\\", "/"))
        if len(results) >= limit:
            break
    return sorted(results)


def find_markdown_files(max_files: int | None = None) -> list[str]:
    limit = max_files or MAX_PAPER_FILES
    root = WORKSPACE_ROOT.resolve()
    results = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if any(d in SKIP_DIRS for d in parts):
            continue
        if p.suffix.lower() in _MD_EXTS and p.stat().st_size <= MAX_FILE_SIZE:
            results.append(str(rel).replace("\\", "/"))
        if len(results) >= limit:
            break
    return sorted(results)


def detect_main_tex_file() -> str | None:
    root = WORKSPACE_ROOT.resolve()
    candidates = ["main.tex", "paper.tex", "manuscript.tex", "article.tex"]
    for name in candidates:
        p = root / name
        if p.is_file():
            return name

    for tex in find_tex_files(max_files=50):
        try:
            text = _read_tex(tex, max_chars=5000)
            if "\\documentclass" in text and "\\begin{document}" in text:
                return tex
        except Exception:
            continue
    return None


def read_latex_file_safe(file_path: str, max_chars: int | None = None) -> str:
    target = resolve_safe_path(file_path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    if target.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({target.stat().st_size} bytes): {file_path}")
    limit = max_chars or MAX_TEX_FILE_CHARS
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + f"\n\n... [truncated at {limit} chars]"
    return text


def _read_tex(file_path: str, max_chars: int | None = None) -> str:
    return read_latex_file_safe(file_path, max_chars)


def strip_latex_comments(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("%"):
            continue
        idx = line.find(" %")
        if idx >= 0:
            result.append(line[:idx])
        else:
            result.append(line)
    return "\n".join(result)


_RE_INPUT = re.compile(r"\\(?:input|include)\{([^}]+)\}")
_RE_SECTION = re.compile(r"\\(chapter|section|subsection|subsubsection)\*?\{([^}]+)\}")
_RE_LABEL = re.compile(r"\\label\{([^}]+)\}")
_RE_REF = re.compile(r"\\(?:ref|autoref|eqref|pageref|nameref)\{([^}]+)\}")
_RE_CITE = re.compile(r"\\(?:cite|citep|citet|citeauthor|citeyear|citetext|parencite|textcite)\*?\{([^}]+)\}")
_RE_FIG_BEGIN = re.compile(r"\\begin\{figure\*?\}")
_RE_TAB_BEGIN = re.compile(r"\\begin\{table\*?\}")
_RE_CAPTION = re.compile(r"\\caption\{([^}]*)\}")
_RE_DOCCLASS = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}")
_RE_TITLE = re.compile(r"\\title\{([^}]+)\}")
_RE_ABSTRACT_BEGIN = re.compile(r"\\begin\{abstract\}")
_RE_ABSTRACT_END = re.compile(r"\\end\{abstract\}")


def parse_latex_inputs(tex_text: str) -> list[str]:
    return _RE_INPUT.findall(tex_text)


def parse_latex_sections(tex_text: str, file_path: str = "") -> list[dict]:
    sections = []
    for i, line in enumerate(tex_text.split("\n"), 1):
        m = _RE_SECTION.search(line)
        if m:
            level = m.group(1)
            title = m.group(2).strip()
            sections.append({"level": level, "title": title, "line": i, "file": file_path})
    return sections


def parse_latex_labels(tex_text: str, file_path: str = "") -> list[dict]:
    labels = []
    for i, line in enumerate(tex_text.split("\n"), 1):
        for m in _RE_LABEL.finditer(line):
            labels.append({"label": m.group(1), "line": i, "file": file_path})
    return labels


def parse_latex_refs(tex_text: str, file_path: str = "") -> list[dict]:
    refs = []
    for i, line in enumerate(tex_text.split("\n"), 1):
        for m in _RE_REF.finditer(line):
            cmd = line[m.start():m.end()].split("{")[0].lstrip("\\")
            refs.append({"ref": m.group(1), "command": cmd, "line": i, "file": file_path})
    return refs


def parse_latex_citations(tex_text: str, file_path: str = "") -> list[dict]:
    cites = []
    for i, line in enumerate(tex_text.split("\n"), 1):
        for m in _RE_CITE.finditer(line):
            cmd_match = re.match(r"\\(\w+)", line[m.start():])
            cmd = cmd_match.group(1) if cmd_match else "cite"
            keys = [k.strip() for k in m.group(1).split(",")]
            for key in keys:
                if key:
                    cites.append({"key": key, "command": cmd, "line": i, "file": file_path})
    return cites


def parse_latex_figures(tex_text: str, file_path: str = "") -> list[dict]:
    figures = []
    in_fig = False
    caption = ""
    label = ""
    start_line = 0
    for i, line in enumerate(tex_text.split("\n"), 1):
        if _RE_FIG_BEGIN.search(line):
            in_fig = True
            caption = ""
            label = ""
            start_line = i
        if in_fig:
            cm = _RE_CAPTION.search(line)
            if cm:
                caption = cm.group(1).strip()
            lm = _RE_LABEL.search(line)
            if lm:
                label = lm.group(1)
            if "\\end{figure" in line:
                figures.append({"caption": caption, "label": label, "line": start_line, "file": file_path})
                in_fig = False
    return figures


def parse_latex_tables(tex_text: str, file_path: str = "") -> list[dict]:
    tables = []
    in_tab = False
    caption = ""
    label = ""
    start_line = 0
    for i, line in enumerate(tex_text.split("\n"), 1):
        if _RE_TAB_BEGIN.search(line):
            in_tab = True
            caption = ""
            label = ""
            start_line = i
        if in_tab:
            cm = _RE_CAPTION.search(line)
            if cm:
                caption = cm.group(1).strip()
            lm = _RE_LABEL.search(line)
            if lm:
                label = lm.group(1)
            if "\\end{table" in line:
                tables.append({"caption": caption, "label": label, "line": start_line, "file": file_path})
                in_tab = False
    return tables


def parse_latex_abstract(tex_text: str) -> str:
    m_start = _RE_ABSTRACT_BEGIN.search(tex_text)
    if not m_start:
        return ""
    rest = tex_text[m_start.end():]
    m_end = _RE_ABSTRACT_END.search(rest)
    if m_end:
        return rest[:m_end.start()].strip()[:2000]
    return rest[:2000].strip()


def parse_latex_title(tex_text: str) -> str:
    m = _RE_TITLE.search(tex_text)
    return m.group(1).strip() if m else ""


def parse_latex_documentclass(tex_text: str) -> str:
    m = _RE_DOCCLASS.search(tex_text)
    return m.group(1).strip() if m else ""


def resolve_latex_project_files(main_tex: str) -> list[str]:
    try:
        text = read_latex_file_safe(main_tex)
    except Exception:
        return [main_tex]

    inputs = parse_latex_inputs(text)
    root = WORKSPACE_ROOT.resolve()
    main_dir = str(Path(main_tex).parent)
    files = [main_tex]

    for inp in inputs:
        candidate = inp if inp.endswith(".tex") else inp + ".tex"
        if main_dir and main_dir != ".":
            candidate = str(Path(main_dir) / candidate)
        candidate = candidate.replace("\\", "/")
        abs_path = (root / candidate).resolve()
        if abs_path.exists() and root in abs_path.parents:
            files.append(candidate)
        else:
            files.append(f"{candidate} [NOT FOUND]")

    return files


_MD_SECTION_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def parse_markdown_sections(md_text: str, file_path: str = "") -> list[dict]:
    sections = []
    for i, line in enumerate(md_text.split("\n"), 1):
        m = _MD_SECTION_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            level_name = {1: "h1", 2: "h2", 3: "h3", 4: "h4", 5: "h5", 6: "h6"}.get(level, "h?")
            sections.append({"level": level_name, "title": title, "line": i, "file": file_path})
    return sections
