import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from cheap_agent.tools._common import truncate
from cheap_agent.cache import make_hash
from cheap_agent.cache_manager import ensure_cache_dir, get_disk_cache, set_disk_cache, write_json_cache_atomic
from cheap_agent.config import (
    CACHE_SCHEMA_VERSION,
    ENABLE_FIGURE_CACHE,
    ENABLE_LLM_FIGURE_CHECK,
    FIGURE_CACHE_TTL_SEC,
    LLM_MODEL,
    MAX_CAPTION_CHARS,
    MAX_CAPTION_CONTEXT_CHARS,
    MAX_CAPTION_ITEMS,
    MAX_EQUATIONS_TO_CHECK,
    MAX_FIGURE_ITEMS,
    MAX_FIGURE_OUTPUT_CHARS,
    MAX_GRAPHICS_FILES,
    MAX_LABEL_REFS,
    MAX_OUTPUT_CHARS,
    PAPER_CACHE_DIR,
    PAPER_LLM_MAX_TOKENS,
    PAPER_LLM_TEMPERATURE,
    WORKSPACE_ROOT,
)
from cheap_agent.parsers.latex_parser import (
    detect_main_tex_file,
    read_latex_file_safe,
    resolve_latex_project_files,
    strip_latex_comments,
)
from cheap_agent.workspace import resolve_safe_path, get_relative_path



def _paper_cache_dir() -> Path:
    d = WORKSPACE_ROOT.resolve() / PAPER_CACHE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _call_llm(system_prompt: str, user_prompt: str, use_llm: bool) -> str | None:
    if not use_llm or not ENABLE_LLM_FIGURE_CHECK:
        return None
    try:
        from cheap_agent.llm_client import ask_llm
        return ask_llm(system_prompt, user_prompt, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
    except Exception as e:
        return f"[LLM Error] {e}"


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_RE_FIG_BEGIN = re.compile(r"\\begin\{(figure\*?)\}")
_RE_FIG_END = re.compile(r"\\end\{(figure\*?)\}")
_RE_TAB_BEGIN = re.compile(r"\\begin\{(table\*?)\}")
_RE_TAB_END = re.compile(r"\\end\{(table\*?)\}")
_RE_EQ_BEGIN = re.compile(r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}")
_RE_EQ_END = re.compile(r"\\end\{(equation\*?|align\*?|gather\*?|multline\*?)\}")
_RE_CAPTION = re.compile(r"\\caption\{([^}]*)\}")
_RE_LABEL = re.compile(r"\\label\{([^}]+)\}")
_RE_INCLUDEGRAPHICS = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_RE_INPUT = re.compile(r"\\(?:input|include)\{([^}]+)\}")
_RE_REF = re.compile(r"\\(?:ref|autoref|cref|Cref|eqref|nameref)\{([^}]+)\}")
_RE_FIG_REF_INLINE = re.compile(r"(?:Fig(?:ure)?\.?\s*~?\\ref|\\(?:autoref|cref|Cref))\{([^}]+)\}")
_RE_TAB_REF_INLINE = re.compile(r"(?:Table\.?\s*~?\\ref|\\(?:autoref|cref|Cref))\{([^}]+)\}")
_RE_EQ_REF_INLINE = re.compile(r"(?:Eq(?:uation)?\.?\s*~?\\(?:ref|eqref)|\\eqref)\{([^}]+)\}")


def _collect_tex_texts(tex_path: str = "") -> dict[str, str]:
    """Collect text from main tex and included files."""
    if tex_path:
        try:
            resolve_safe_path(tex_path)
            files = [tex_path]
        except (PermissionError, ValueError):
            return {}
    else:
        main_tex = detect_main_tex_file()
        if not main_tex:
            return {}
        files = resolve_latex_project_files(main_tex)

    result = {}
    for f in files:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f, max_chars=100000)
            result[f] = strip_latex_comments(text)
        except Exception:
            continue
    return result


def _file_exists_in_workspace(path: str) -> bool:
    try:
        full = (WORKSPACE_ROOT / path).resolve()
        return full.exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# parse_figures_and_labels
# ---------------------------------------------------------------------------

def parse_figures_and_labels_logic(
    tex_path: str = "",
    include_tables: bool = True,
    include_equations: bool = True,
    max_items: int = 200,
) -> str:
    file_texts = _collect_tex_texts(tex_path)
    if not file_texts:
        return "[Error] No LaTeX files found."

    figures = []
    tables = []
    equations = []
    all_labels = []
    all_refs = []
    graphics_files = []

    for fpath, text in file_texts.items():
        lines = text.split("\n")

        for m in _RE_FIG_BEGIN.finditer(text):
            start = m.start()
            end_m = _RE_FIG_END.search(text, start)
            if not end_m:
                continue
            env_text = text[start:end_m.end()]
            start_line = text[:start].count("\n") + 1

            caption_m = _RE_CAPTION.search(env_text)
            label_m = _RE_LABEL.search(env_text)
            graphics = _RE_INCLUDEGRAPHICS.findall(env_text)

            caption = caption_m.group(1).strip() if caption_m else ""
            label = label_m.group(1).strip() if label_m else ""

            for g in graphics:
                graphics_files.append({"file": g, "source": fpath, "exists": _file_exists_in_workspace(g)})

            figures.append({
                "type": m.group(1),
                "source_file": fpath,
                "line": start_line,
                "caption": caption[:MAX_CAPTION_CHARS],
                "label": label,
                "graphics": graphics,
                "has_caption": bool(caption_m),
                "has_label": bool(label_m),
            })

        if include_tables:
            for m in _RE_TAB_BEGIN.finditer(text):
                start = m.start()
                end_m = _RE_TAB_END.search(text, start)
                if not end_m:
                    continue
                env_text = text[start:end_m.end()]
                start_line = text[:start].count("\n") + 1

                caption_m = _RE_CAPTION.search(env_text)
                label_m = _RE_LABEL.search(env_text)

                tables.append({
                    "type": m.group(1),
                    "source_file": fpath,
                    "line": start_line,
                    "caption": caption_m.group(1).strip()[:MAX_CAPTION_CHARS] if caption_m else "",
                    "label": label_m.group(1).strip() if label_m else "",
                    "has_caption": bool(caption_m),
                    "has_label": bool(label_m),
                })

        if include_equations:
            for m in _RE_EQ_BEGIN.finditer(text):
                start = m.start()
                end_m = _RE_EQ_END.search(text, start)
                if not end_m:
                    continue
                env_text = text[start:end_m.end()]
                start_line = text[:start].count("\n") + 1

                label_m = _RE_LABEL.search(env_text)
                preview = env_text[:200].replace("\n", " ")

                equations.append({
                    "type": m.group(1),
                    "source_file": fpath,
                    "line": start_line,
                    "label": label_m.group(1).strip() if label_m else "",
                    "has_label": bool(label_m),
                    "preview": preview,
                })

        for m in _RE_LABEL.finditer(text):
            all_labels.append({"label": m.group(1), "file": fpath, "line": text[:m.start()].count("\n") + 1})
        for m in _RE_REF.finditer(text):
            all_refs.append({"ref": m.group(1), "file": fpath, "line": text[:m.start()].count("\n") + 1})

    label_names = [l["label"] for l in all_labels]
    ref_names = [r["ref"] for r in all_refs]
    label_set = set(label_names)
    ref_set = set(ref_names)

    undefined_refs = ref_set - label_set
    unreferenced = label_set - ref_set
    duplicate_labels = [l for l, c in Counter(label_names).items() if c > 1]
    missing_graphics = [g["file"] for g in graphics_files if not g["exists"]]

    referenced_by = defaultdict(list)
    for r in all_refs:
        referenced_by[r["ref"]].append(f"{r['file']}:{r['line']}")

    parts = ["Parsed Figures, Tables, and Labels", ""]

    parts.append(f"Figures: {len(figures)}")
    parts.append(f"Tables: {len(tables)}")
    parts.append(f"Equations: {len(equations)}")
    parts.append(f"Labels: {len(label_set)}")
    parts.append(f"References: {len(ref_set)}")
    parts.append(f"Undefined refs: {len(undefined_refs)}")
    parts.append(f"Unreferenced labels: {len(unreferenced)}")
    parts.append(f"Duplicate labels: {len(duplicate_labels)}")
    parts.append(f"Missing graphics: {len(missing_graphics)}")
    parts.append("")

    if figures:
        parts.append("Figures:")
        for i, fig in enumerate(figures[:max_items], 1):
            parts.append(f"  {i}. {fig['label'] or '(no label)'}")
            parts.append(f"     Source: {fig['source_file']}:{fig['line']}")
            parts.append(f"     Caption: {fig['caption'][:100] or '(none)'}")
            if fig["graphics"]:
                for g in fig["graphics"]:
                    exists = "[exists]" if _file_exists_in_workspace(g) else "[MISSING]"
                    parts.append(f"     Graphics: {g} {exists}")
            refs = referenced_by.get(fig["label"], [])
            if refs:
                parts.append(f"     Referenced by: {', '.join(refs[:3])}")
            else:
                parts.append("     Referenced by: none")
            if not fig["has_caption"]:
                parts.append("     Issue: missing \\caption{}")
            if not fig["has_label"]:
                parts.append("     Issue: missing \\label{}")
        parts.append("")

    if tables:
        parts.append("Tables:")
        for i, tab in enumerate(tables[:max_items], 1):
            parts.append(f"  {i}. {tab['label'] or '(no label)'}")
            parts.append(f"     Source: {tab['source_file']}:{tab['line']}")
            parts.append(f"     Caption: {tab['caption'][:100] or '(none)'}")
            refs = referenced_by.get(tab["label"], [])
            if refs:
                parts.append(f"     Referenced by: {', '.join(refs[:3])}")
            else:
                parts.append("     Referenced by: none")
        parts.append("")

    if equations:
        parts.append("Equations:")
        for i, eq in enumerate(equations[:max_items], 1):
            parts.append(f"  {i}. {eq['label'] or '(no label)'}")
            parts.append(f"     Source: {eq['source_file']}:{eq['line']}")
            refs = referenced_by.get(eq["label"], [])
            if refs:
                parts.append(f"     Referenced by: {', '.join(refs[:3])}")
            else:
                parts.append("     Referenced by: none")
        parts.append("")

    if undefined_refs:
        parts.append("Undefined references:")
        for ref in sorted(undefined_refs)[:20]:
            locations = [r for r in all_refs if r["ref"] == ref]
            loc_str = ", ".join(f"{r['file']}:{r['line']}" for r in locations[:3])
            parts.append(f"  - {ref} (used in {loc_str})")
        parts.append("")

    if missing_graphics:
        parts.append("Missing graphics files:")
        for g in sorted(set(missing_graphics))[:10]:
            parts.append(f"  - {g}")
        parts.append("")

    result = "\n".join(parts)

    if ENABLE_FIGURE_CACHE:
        cache_dir = _paper_cache_dir()
        write_json_cache_atomic(cache_dir / "latex_figures.json", {"value": result})

    return truncate(result, MAX_FIGURE_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_figure_reference_consistency
# ---------------------------------------------------------------------------

def check_figure_reference_consistency_logic(
    tex_path: str = "",
    include_equations: bool = True,
    use_llm: bool = False,
) -> str:
    parsed = parse_figures_and_labels_logic(tex_path=tex_path, include_equations=include_equations)
    if parsed.startswith("[Error]"):
        return parsed

    file_texts = _collect_tex_texts(tex_path)
    all_text = "\n".join(file_texts.values())

    labels = set(re.findall(r"\\label\{([^}]+)\}", all_text))
    refs = set(re.findall(r"\\ref\{([^}]+)\}", all_text))
    refs.update(re.findall(r"\\autoref\{([^}]+)\}", all_text))
    refs.update(re.findall(r"\\cref\{([^}]+)\}", all_text))
    refs.update(re.findall(r"\\Cref\{([^}]+)\}", all_text))
    refs.update(re.findall(r"\\eqref\{([^}]+)\}", all_text))

    undefined_refs = refs - labels
    unreferenced = labels - refs

    label_list = re.findall(r"\\label\{([^}]+)\}", all_text)
    duplicate_labels = [l for l, c in Counter(label_list).items() if c > 1]

    graphics = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", all_text)
    missing_graphics = [g for g in graphics if not _file_exists_in_workspace(g)]

    fig_refs = re.findall(r"Figure\s+\\ref\{", all_text, re.IGNORECASE)
    fig_dot_refs = re.findall(r"Fig\.\s*~?\\ref\{", all_text, re.IGNORECASE)
    tab_refs = re.findall(r"Table\s+\\ref\{", all_text, re.IGNORECASE)
    tab_dot_refs = re.findall(r"Tab\.\s*~?\\ref\{", all_text, re.IGNORECASE)

    issues = []

    for ref in sorted(undefined_refs):
        locations = []
        for fpath, text in file_texts.items():
            for m in re.finditer(re.escape(ref), text):
                line = text[:m.start()].count("\n") + 1
                locations.append(f"{fpath}:{line}")
        issues.append({
            "type": "undefined reference",
            "text": ref,
            "source": ", ".join(locations[:3]),
            "severity": "high",
            "suggestion": f"Add \\label{{{ref}}} or fix the reference",
        })

    for label in sorted(unreferenced):
        for fpath, text in file_texts.items():
            m = re.search(re.escape(label), text)
            if m:
                line = text[:m.start()].count("\n") + 1
                issues.append({
                    "type": "unreferenced label",
                    "text": label,
                    "source": f"{fpath}:{line}",
                    "severity": "medium",
                    "suggestion": "Add a reference in text or remove the label",
                })
                break

    for label in duplicate_labels:
        issues.append({
            "type": "duplicate label",
            "text": label,
            "source": "multiple locations",
            "severity": "high",
            "suggestion": "Remove duplicate \\label{} definitions",
        })

    for g in sorted(set(missing_graphics)):
        issues.append({
            "type": "missing graphics file",
            "text": g,
            "source": "includegraphics",
            "severity": "high",
            "suggestion": "Check file path or add the missing file",
        })

    if fig_refs and fig_dot_refs:
        issues.append({
            "type": "reference style inconsistency",
            "text": f"Figure \\ref{{}} ({len(fig_refs)}x) and Fig.~\\ref{{}} ({len(fig_dot_refs)}x) both used",
            "source": "throughout",
            "severity": "low",
            "suggestion": "Choose one style, e.g., Fig.~\\ref{}",
        })
    if tab_refs and tab_dot_refs:
        issues.append({
            "type": "reference style inconsistency",
            "text": f"Table \\ref{{}} ({len(tab_refs)}x) and Tab.~\\ref{{}} ({len(tab_dot_refs)}x) both used",
            "source": "throughout",
            "severity": "low",
            "suggestion": "Choose one style, e.g., Table~\\ref{}",
        })

    parts = ["Figure/Table Reference Consistency Check", ""]
    parts.append(f"Summary:")
    parts.append(f"  - Labels: {len(labels)}")
    parts.append(f"  - References: {len(refs)}")
    parts.append(f"  - Undefined references: {len(undefined_refs)}")
    parts.append(f"  - Unreferenced labels: {len(unreferenced)}")
    parts.append(f"  - Duplicate labels: {len(duplicate_labels)}")
    parts.append(f"  - Missing graphics: {len(set(missing_graphics))}")
    parts.append("")

    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues[:50], 1):
            parts.append(f"{i}. {issue['type']}")
            parts.append(f"   Text: {issue['text']}")
            if issue.get("source"):
                parts.append(f"   Source: {issue['source']}")
            parts.append(f"   Severity: {issue['severity']}")
            parts.append(f"   Suggestion: {issue['suggestion']}")
    else:
        parts.append("No significant reference consistency issues found.")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Review figure/table reference consistency. Be concise.",
        f"Issues:\n{result[:2000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_FIGURE_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# review_figure_caption
# ---------------------------------------------------------------------------

def _find_caption_for_label(file_texts: dict[str, str], label: str) -> tuple[str, str, int]:
    """Find caption and source for a given label."""
    for fpath, text in file_texts.items():
        label_m = re.search(re.escape(label), text)
        if not label_m:
            continue
        pos = label_m.start()
        env_start = text.rfind("\\begin{figure", max(0, pos - 5000), pos)
        if env_start < 0:
            continue
        env_end = text.find("\\end{figure", pos)
        if env_end < 0:
            continue
        env_text = text[env_start:env_end]
        caption_m = _RE_CAPTION.search(env_text)
        if caption_m:
            line = text[:env_start].count("\n") + 1
            return caption_m.group(1).strip(), fpath, line
    return "", "", 0


def _find_ref_context(file_texts: dict[str, str], label: str, context_chars: int = 500) -> list[str]:
    """Find sentences that reference a label."""
    contexts = []
    for fpath, text in file_texts.items():
        for m in re.finditer(re.escape(label), text):
            start = max(0, m.start() - context_chars)
            end = min(len(text), m.end() + context_chars)
            snippet = text[start:end].strip()
            contexts.append(f"[{fpath}] ...{snippet}...")
    return contexts[:5]


def review_figure_caption_logic(
    label: str = "",
    caption_text: str = "",
    tex_path: str = "",
    use_llm: bool = True,
) -> str:
    file_texts = _collect_tex_texts(tex_path)

    if caption_text:
        caption = caption_text[:MAX_CAPTION_CHARS]
        source = "provided text"
        ref_contexts = []
    elif label:
        if not file_texts:
            return "[Error] No LaTeX files found."
        caption, source, line = _find_caption_for_label(file_texts, label)
        if not caption:
            return f"[Error] No caption found for label '{label}'."
        caption = caption[:MAX_CAPTION_CHARS]
        ref_contexts = _find_ref_context(file_texts, label)
    elif tex_path or file_texts:
        if not file_texts:
            return "[Error] No LaTeX files found."
        results = []
        for fpath, text in file_texts.items():
            for m in _RE_FIG_BEGIN.finditer(text):
                start = m.start()
                end_m = _RE_FIG_END.search(text, start)
                if not end_m:
                    continue
                env_text = text[start:end_m.end()]
                caption_m = _RE_CAPTION.search(env_text)
                label_m = _RE_LABEL.search(env_text)
                if caption_m:
                    cap = caption_m.group(1).strip()[:MAX_CAPTION_CHARS]
                    lbl = label_m.group(1).strip() if label_m else ""
                    results.append({"caption": cap, "label": lbl, "source": fpath})
        if not results:
            return "No figure captions found."
        parts = ["Figure Caption Review (all figures)", ""]
        for i, r in enumerate(results[:MAX_CAPTION_ITEMS], 1):
            parts.append(f"Figure {i}: {r['label'] or '(no label)'}")
            parts.append(f"  Source: {r['source']}")
            parts.append(f"  Caption: {r['caption'][:150]}")
            parts.append("")
        return truncate("\n".join(parts), MAX_FIGURE_OUTPUT_CHARS)
    else:
        return "[Error] Provide caption_text, label, or tex_path."

    issues = []
    words = caption.split()
    if len(words) < 5:
        issues.append({"type": "too short", "severity": "medium", "suggestion": "Caption is very short. Add more detail about what the figure shows."})

    vague_phrases = ["visualization", "results", "examples", "comparison", "overview", "illustration"]
    if len(words) < 15 and any(p in caption.lower() for p in vague_phrases):
        issues.append({"type": "too vague", "severity": "medium", "suggestion": "Caption is vague. Specify what methods, datasets, or metrics are shown."})

    if "baseline" not in caption.lower() and "proposed" not in caption.lower() and "method" not in caption.lower():
        if len(words) < 20:
            issues.append({"type": "missing context", "severity": "low", "suggestion": "Consider mentioning which methods or settings are compared."})

    strong_words = ["significantly", "prove", "guarantee", "perfect", "state-of-the-art"]
    for w in strong_words:
        if w in caption.lower():
            issues.append({"type": "over-strong claim", "severity": "medium", "suggestion": f"'{w}' may be too strong for a caption."})

    parts = ["Figure Caption Review", ""]
    parts.append(f"Label: {label or '(not specified)'}")
    parts.append(f"Caption: {caption[:200]}")
    parts.append("")

    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues, 1):
            parts.append(f"  {i}. {issue['type']} (severity: {issue['severity']})")
            parts.append(f"     {issue['suggestion']}")
        parts.append("")
    else:
        parts.append("Assessment: Acceptable")
        parts.append("")

    if ref_contexts:
        parts.append("Referencing context:")
        for ctx in ref_contexts[:2]:
            parts.append(f"  {ctx[:200]}")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Verify suggested caption changes match actual figure content")
    parts.append("  - Do not invent elements not present in the figure")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Review this figure caption for IEEE/TGRS quality. Be concise.",
        f"Caption: {caption}\n\nIssues:\n{result[:1500]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_FIGURE_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# review_table_caption
# ---------------------------------------------------------------------------

def _find_table_caption_for_label(file_texts: dict[str, str], label: str) -> tuple[str, str, int]:
    for fpath, text in file_texts.items():
        label_m = re.search(re.escape(label), text)
        if not label_m:
            continue
        pos = label_m.start()
        env_start = text.rfind("\\begin{table", max(0, pos - 5000), pos)
        if env_start < 0:
            continue
        env_end = text.find("\\end{table", pos)
        if env_end < 0:
            continue
        env_text = text[env_start:env_end]
        caption_m = _RE_CAPTION.search(env_text)
        if caption_m:
            line = text[:env_start].count("\n") + 1
            return caption_m.group(1).strip(), fpath, line
    return "", "", 0


def review_table_caption_logic(
    label: str = "",
    caption_text: str = "",
    tex_path: str = "",
    use_llm: bool = True,
) -> str:
    file_texts = _collect_tex_texts(tex_path)

    if caption_text:
        caption = caption_text[:MAX_CAPTION_CHARS]
        source = "provided text"
    elif label:
        if not file_texts:
            return "[Error] No LaTeX files found."
        caption, source, line = _find_table_caption_for_label(file_texts, label)
        if not caption:
            return f"[Error] No caption found for table label '{label}'."
        caption = caption[:MAX_CAPTION_CHARS]
    elif tex_path or file_texts:
        if not file_texts:
            return "[Error] No LaTeX files found."
        results = []
        for fpath, text in file_texts.items():
            for m in _RE_TAB_BEGIN.finditer(text):
                start = m.start()
                end_m = _RE_TAB_END.search(text, start)
                if not end_m:
                    continue
                env_text = text[start:end_m.end()]
                caption_m = _RE_CAPTION.search(env_text)
                label_m = _RE_LABEL.search(env_text)
                if caption_m:
                    cap = caption_m.group(1).strip()[:MAX_CAPTION_CHARS]
                    lbl = label_m.group(1).strip() if label_m else ""
                    results.append({"caption": cap, "label": lbl, "source": fpath})
        if not results:
            return "No table captions found."
        parts = ["Table Caption Review (all tables)", ""]
        for i, r in enumerate(results[:MAX_CAPTION_ITEMS], 1):
            parts.append(f"Table {i}: {r['label'] or '(no label)'}")
            parts.append(f"  Source: {r['source']}")
            parts.append(f"  Caption: {r['caption'][:150]}")
            parts.append("")
        return truncate("\n".join(parts), MAX_FIGURE_OUTPUT_CHARS)
    else:
        return "[Error] Provide caption_text, label, or tex_path."

    issues = []
    lower = caption.lower()

    if "dataset" not in lower and "benchmark" not in lower and "on " not in lower:
        issues.append({"type": "missing dataset", "severity": "medium", "suggestion": "Consider specifying which dataset or benchmark is used."})

    metric_words = ["map", "ap", "precision", "recall", "f1", "fps", "latency", "params", "gflops"]
    if not any(m in lower for m in metric_words):
        issues.append({"type": "missing metrics", "severity": "medium", "suggestion": "Consider mentioning which metrics are reported."})

    if "bold" not in lower and "best" not in lower and "highest" not in lower:
        issues.append({"type": "missing best-value explanation", "severity": "low", "suggestion": "Consider explaining bold values or best-result markers."})

    if len(caption.split()) < 8:
        issues.append({"type": "too short", "severity": "medium", "suggestion": "Caption is very short. Add more context about what the table compares."})

    parts = ["Table Caption Review", ""]
    parts.append(f"Label: {label or '(not specified)'}")
    parts.append(f"Caption: {caption[:200]}")
    parts.append("")

    if issues:
        parts.append("Assessment: Needs revision")
        parts.append("")
        parts.append("Issues:")
        for i, issue in enumerate(issues, 1):
            parts.append(f"  {i}. {issue['type']} (severity: {issue['severity']})")
            parts.append(f"     {issue['suggestion']}")
    else:
        parts.append("Assessment: Acceptable")

    parts.append("")
    parts.append("Notes for Codex:")
    parts.append("  - Confirm dataset name before applying suggested changes")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Review this table caption for IEEE/TGRS quality. Be concise.",
        f"Caption: {caption}\n\nIssues:\n{result[:1500]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_FIGURE_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_caption_text_consistency
# ---------------------------------------------------------------------------

def check_caption_text_consistency_logic(
    tex_path: str = "",
    use_llm: bool = True,
    max_items: int = 50,
) -> str:
    file_texts = _collect_tex_texts(tex_path)
    if not file_texts:
        return "[Error] No LaTeX files found."

    all_text = "\n".join(file_texts.values())
    all_labels = set(re.findall(r"\\label\{([^}]+)\}", all_text))

    items = []
    for label in sorted(all_labels):
        if len(items) >= max_items:
            break
        if label.startswith("fig:") or label.startswith("tab:"):
            is_fig = label.startswith("fig:")
            if is_fig:
                caption, cap_source, _ = _find_caption_for_label(file_texts, label)
            else:
                caption, cap_source, _ = _find_table_caption_for_label(file_texts, label)

            if not caption:
                continue

            ref_contexts = _find_ref_context(file_texts, label, context_chars=MAX_CAPTION_CONTEXT_CHARS)
            if not ref_contexts:
                continue

            items.append({
                "label": label,
                "is_figure": is_fig,
                "caption": caption[:MAX_CAPTION_CHARS],
                "cap_source": cap_source,
                "ref_contexts": ref_contexts,
            })

    if not items:
        return "No figure/table labels with both caption and reference found."

    issues = []
    for item in items:
        label = item["label"]
        caption_lower = item["caption"].lower()
        for ctx in item["ref_contexts"]:
            ctx_lower = ctx.lower()
            if label in ctx_lower:
                ctx_words = set(re.findall(r"\b[a-z]{3,}\b", ctx_lower))
                cap_words = set(re.findall(r"\b[a-z]{3,}\b", caption_lower))
                overlap = ctx_words & cap_words
                if len(overlap) < 2 and len(cap_words) > 3:
                    issues.append({
                        "label": label,
                        "caption": item["caption"][:100],
                        "context": ctx[:200],
                        "severity": "medium",
                        "suggestion": "Caption and referencing text may describe different things. Verify consistency.",
                    })

    parts = ["Caption-Text Consistency Check", ""]
    parts.append(f"Checked items: {len(items)}")
    parts.append(f"Potential mismatches: {len(issues)}")
    parts.append("")

    if issues:
        for i, issue in enumerate(issues[:10], 1):
            parts.append(f"Issue {i}")
            parts.append(f"  Label: {issue['label']}")
            parts.append(f"  Caption: {issue['caption']}")
            parts.append(f"  Context: {issue['context']}")
            parts.append(f"  Severity: {issue['severity']}")
            parts.append(f"  Suggestion: {issue['suggestion']}")
            parts.append("")
    else:
        parts.append("No significant caption-text mismatches found.")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Verify that figure/table labels match the content described in text")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check caption-text consistency. Be concise.",
        f"Consistency check:\n{result[:2000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_FIGURE_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_equation_reference_consistency
# ---------------------------------------------------------------------------

def check_equation_reference_consistency_logic(
    tex_path: str = "",
    use_llm: bool = True,
    max_equations: int = 100,
) -> str:
    file_texts = _collect_tex_texts(tex_path)
    if not file_texts:
        return "[Error] No LaTeX files found."

    all_text = "\n".join(file_texts.values())

    equations = []
    for fpath, text in file_texts.items():
        for m in _RE_EQ_BEGIN.finditer(text):
            start = m.start()
            end_m = _RE_EQ_END.search(text, start)
            if not end_m:
                continue
            env_text = text[start:end_m.end()]
            start_line = text[:start].count("\n") + 1
            label_m = _RE_LABEL.search(env_text)
            preview = env_text[:300].replace("\n", " ")
            equations.append({
                "type": m.group(1),
                "source_file": fpath,
                "line": start_line,
                "label": label_m.group(1).strip() if label_m else "",
                "has_label": bool(label_m),
                "preview": preview,
            })
            if len(equations) >= max_equations:
                break

    eq_labels = {e["label"] for e in equations if e["label"]}
    eq_refs = set(re.findall(r"\\eqref\{([^}]+)\}", all_text))
    eq_refs.update(m.group(1) for m in re.finditer(r"(?:Eq(?:uation)?\.?\s*~?\\ref)\{([^}]+)\}", all_text))
    eq_refs.update(m.group(1) for m in re.finditer(r"\\ref\{((?:eq|equation)[^}]*)\}", all_text, re.IGNORECASE))

    undefined_refs = eq_refs - eq_labels
    unreferenced = eq_labels - eq_refs

    eq_ref_style_1 = len(re.findall(r"Eq\.\s*~?\\ref\{", all_text))
    eq_ref_style_2 = len(re.findall(r"Equation\s+\\ref\{", all_text, re.IGNORECASE))
    eq_ref_style_3 = len(re.findall(r"\\eqref\{", all_text))

    issues = []

    for ref in sorted(undefined_refs):
        locations = []
        for fpath, text in file_texts.items():
            for m in re.finditer(re.escape(ref), text):
                line = text[:m.start()].count("\n") + 1
                locations.append(f"{fpath}:{line}")
        issues.append({
            "type": "undefined equation reference",
            "text": ref,
            "source": ", ".join(locations[:3]),
            "severity": "high",
            "suggestion": f"Add \\label{{{ref}}} or fix the reference",
        })

    for label in sorted(unreferenced):
        for eq in equations:
            if eq["label"] == label:
                issues.append({
                    "type": "unreferenced equation",
                    "text": label,
                    "source": f"{eq['source_file']}:{eq['line']}",
                    "severity": "medium",
                    "suggestion": "Add a reference in text or remove the label",
                })
                break

    styles_used = sum([bool(eq_ref_style_1), bool(eq_ref_style_2), bool(eq_ref_style_3)])
    if styles_used > 1:
        issues.append({
            "type": "reference style inconsistency",
            "text": f"Eq.~\\ref{{}} ({eq_ref_style_1}x), Equation~\\ref{{}} ({eq_ref_style_2}x), \\eqref{{}} ({eq_ref_style_3}x) all used",
            "source": "throughout",
            "severity": "low",
            "suggestion": "Choose one style, e.g., Eq.~\\ref{}",
        })

    parts = ["Equation Reference Consistency Check", ""]
    parts.append(f"Summary:")
    parts.append(f"  - Equations found: {len(equations)}")
    parts.append(f"  - Equation labels: {len(eq_labels)}")
    parts.append(f"  - Equation refs: {len(eq_refs)}")
    parts.append(f"  - Undefined refs: {len(undefined_refs)}")
    parts.append(f"  - Unreferenced equations: {len(unreferenced)}")
    parts.append("")

    if equations:
        parts.append("Equations:")
        for i, eq in enumerate(equations[:20], 1):
            parts.append(f"  {i}. {eq['label'] or '(no label)'}")
            parts.append(f"     Source: {eq['source_file']}:{eq['line']}")
            refs = [r for r in eq_refs if r == eq["label"]]
            parts.append(f"     Referenced: {'yes' if refs else 'no'}")
        parts.append("")

    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues[:20], 1):
            parts.append(f"{i}. {issue['type']}")
            parts.append(f"   Text: {issue['text']}")
            if issue.get("source"):
                parts.append(f"   Source: {issue['source']}")
            parts.append(f"   Severity: {issue['severity']}")
            parts.append(f"   Suggestion: {issue['suggestion']}")
    else:
        parts.append("No significant equation reference issues found.")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check equation reference consistency. Be concise.",
        f"Issues:\n{result[:2000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_FIGURE_OUTPUT_CHARS)
