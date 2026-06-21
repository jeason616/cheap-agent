import re
import sys
import time
from collections import Counter
from pathlib import Path

from cheap_agent.tools._common import truncate
from cheap_agent.cache import make_hash
from cheap_agent.config import (
    CACHE_SCHEMA_VERSION,
    ENABLE_LLM_PAPER_REVIEW,
    ENABLE_PAPER_TOOLS,
    LLM_MODEL,
    MAX_CITATION_ITEMS,
    MAX_CLAIMS_TO_CHECK,
    MAX_EVIDENCE_ITEMS,
    MAX_OUTPUT_CHARS,
    PAPER_CACHE_TTL_SEC,
    PAPER_LLM_MAX_TOKENS,
    PAPER_LLM_TEMPERATURE,
    WORKSPACE_ROOT,
)
from cheap_agent.workspace import get_relative_path

from cheap_agent.parsers.latex_parser import (
    detect_main_tex_file,
    find_markdown_files,
    find_tex_files,
    parse_latex_abstract,
    parse_latex_citations,
    parse_latex_documentclass,
    parse_latex_figures,
    parse_latex_inputs,
    parse_latex_labels,
    parse_latex_refs,
    parse_latex_sections,
    parse_latex_tables,
    parse_latex_title,
    read_latex_file_safe,
    resolve_latex_project_files,
    strip_latex_comments,
)
from cheap_agent.parsers.bib_parser import (
    find_bib_files,
    parse_bib_entries,
    parse_bib_keys_from_text,
    read_bib_file_safe,
    summarize_bib_entries,
)


def _file_mtime(path: str) -> tuple[float, int]:
    try:
        p = (WORKSPACE_ROOT / path).resolve()
        st = p.stat()
        return st.st_mtime, st.st_size
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# detect_paper_project
# ---------------------------------------------------------------------------

def detect_paper_project_logic(use_llm: bool = False) -> str:
    tex_files = find_tex_files(max_files=100)
    bib_files = find_bib_files(max_files=10)
    md_files = find_markdown_files(max_files=50)

    root = WORKSPACE_ROOT.resolve()
    evidence = []
    detected = "no"
    project_type = "unknown"
    confidence = "low"
    main_files = []

    paper_dirs = ["sections", "figures", "figs", "tables", "supplementary", "paper", "manuscript"]
    found_dirs = [d for d in paper_dirs if (root / d).is_dir()]

    has_main_tex = False
    main_tex = detect_main_tex_file()
    if main_tex:
        has_main_tex = True
        main_files.append(main_tex)
        try:
            text = read_latex_file_safe(main_tex, max_chars=5000)
            if "\\documentclass" in text:
                evidence.append(f"{main_tex} contains \\documentclass")
            if "\\begin{document}" in text:
                evidence.append(f"{main_tex} contains \\begin{document}")
        except Exception:
            pass

    if tex_files:
        evidence.append(f"{len(tex_files)} .tex file(s) found")
    if bib_files:
        evidence.append(f"{len(bib_files)} .bib file(s) found")
        main_files.extend(bib_files[:3])
    if found_dirs:
        evidence.append(f"paper directories found: {', '.join(found_dirs)}")

    paper_md = [f for f in md_files if any(w in f.lower() for w in ["manuscript", "paper", "rebuttal", "response"])]
    if paper_md:
        evidence.append(f"paper-related markdown: {', '.join(paper_md[:3])}")

    if has_main_tex and bib_files:
        detected = "yes"
        project_type = "LaTeX paper project"
        confidence = "high"
    elif has_main_tex:
        detected = "yes"
        project_type = "LaTeX paper project (no bib found)"
        confidence = "medium"
    elif bib_files and tex_files:
        detected = "likely"
        project_type = "LaTeX paper project"
        confidence = "medium"
    elif paper_md:
        detected = "likely"
        project_type = "Markdown manuscript"
        confidence = "medium"
    elif tex_files:
        detected = "likely"
        project_type = "LaTeX project (paper unclear)"
        confidence = "low"

    parts = ["Paper Project Detection", ""]
    parts.append(f"Detected: {detected}")
    parts.append(f"Project type: {project_type}")
    parts.append(f"Confidence: {confidence}")
    parts.append("")
    parts.append("Evidence:")
    for e in evidence:
        parts.append(f"  - {e}")
    parts.append("")
    if main_files:
        parts.append(f"Main files: {', '.join(main_files[:5])}")
    parts.append("")
    parts.append("Suggested next tools:")
    parts.append("  - build_paper_map")
    parts.append("  - summarize_latex_structure")
    parts.append("  - parse_bib_file")
    parts.append("  - check_citation_coverage")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# build_paper_map
# ---------------------------------------------------------------------------

def build_paper_map_logic(
    main_file: str = "",
    include_bib: bool = True,
    include_figures: bool = True,
    use_llm: bool = False,
) -> str:
    if not main_file:
        main_file = detect_main_tex_file() or ""
    if not main_file:
        return "[Error] No main .tex file found. Set main_file explicitly."

    try:
        tex_text = read_latex_file_safe(main_file)
    except Exception as e:
        return f"[Error] Cannot read {main_file}: {e}"

    tex_text_clean = strip_latex_comments(tex_text)
    project_files = resolve_latex_project_files(main_file)

    doc_class = parse_latex_documentclass(tex_text)
    title = parse_latex_title(tex_text)
    abstract = parse_latex_abstract(tex_text)
    inputs = parse_latex_inputs(tex_text)

    all_sections = []
    all_labels = []
    all_citations = []
    all_figures = []
    all_tables = []
    all_refs = []

    for f in project_files:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f)
            text_clean = strip_latex_comments(text)
            all_sections.extend(parse_latex_sections(text_clean, f))
            all_labels.extend(parse_latex_labels(text_clean, f))
            all_citations.extend(parse_latex_citations(text_clean, f))
            all_figures.extend(parse_latex_figures(text_clean, f))
            all_tables.extend(parse_latex_tables(text_clean, f))
            all_refs.extend(parse_latex_refs(text_clean, f))
        except Exception:
            pass

    bib_files = find_bib_files() if include_bib else []

    parts = ["Paper Map", ""]
    parts.append(f"Main manuscript: {main_file}")
    parts.append(f"Document class: {doc_class or '(not found)'}")
    parts.append(f"Title: {title or '(not found)'}")
    parts.append(f"Abstract: {'Found' if abstract else 'Not found'}")
    parts.append("")

    parts.append("Section files:")
    for f in project_files:
        marker = " [MISSING]" if "[NOT FOUND]" in f else ""
        parts.append(f"  - {f}{marker}")
    parts.append("")

    parts.append("Sections:")
    for i, s in enumerate(all_sections[:50], 1):
        parts.append(f"  {i}. [{s['level']}] {s['title']} ({s['file']}:{s['line']})")
    parts.append("")

    if bib_files:
        parts.append("References:")
        for b in bib_files:
            parts.append(f"  - {b}")
        parts.append("")

    if include_figures and all_figures:
        parts.append(f"Figures ({len(all_figures)}):")
        for fig in all_figures[:20]:
            label_str = f" [{fig['label']}]" if fig["label"] else ""
            parts.append(f"  - {fig['caption'][:60]}{label_str} ({fig['file']}:{fig['line']})")
        parts.append("")

    if all_tables:
        parts.append(f"Tables ({len(all_tables)}):")
        for tab in all_tables[:20]:
            label_str = f" [{tab['label']}]" if tab["label"] else ""
            parts.append(f"  - {tab['caption'][:60]}{label_str} ({tab['file']}:{tab['line']})")
        parts.append("")

    unique_labels = list({l["label"] for l in all_labels})
    if unique_labels:
        parts.append(f"Labels ({len(unique_labels)}):")
        for lb in sorted(unique_labels)[:30]:
            parts.append(f"  - {lb}")
        parts.append("")

    unique_cite_keys = list({c["key"] for c in all_citations})
    parts.append(f"Citation count:")
    parts.append(f"  - {len(all_citations)} citation commands")
    parts.append(f"  - {len(unique_cite_keys)} unique citation keys")
    parts.append("")

    issues = []
    for f in project_files:
        if "[NOT FOUND]" in f:
            issues.append(f"- {f.replace(' [NOT FOUND]', '')} is included but file not found")
    if not abstract:
        issues.append("- Abstract not found")
    if not title:
        issues.append("- Title not found")
    if issues:
        parts.append("Potential issues:")
        for iss in issues:
            parts.append(f"  {iss}")
        parts.append("")

    parts.append("Suggested Codex first-read order:")
    parts.append(f"  1. {main_file}")
    if abstract:
        parts.append("  2. abstract / introduction")
    read_idx = 3
    for s in all_sections[:5]:
        parts.append(f"  {read_idx}. {s['file']}:{s['line']} ({s['title']})")
        read_idx += 1
    if bib_files:
        parts.append(f"  {read_idx}. {bib_files[0]}")

    result = "\n".join(parts)

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# summarize_latex_structure
# ---------------------------------------------------------------------------

def summarize_latex_structure_logic(
    main_file: str = "",
    use_llm: bool = True,
) -> str:
    map_result = build_paper_map_logic(main_file=main_file, use_llm=False)
    if map_result.startswith("[Error]"):
        return map_result

    parts = ["LaTeX Structure Summary", ""]

    sections = []
    for line in map_result.split("\n"):
        m = re.match(r"^\s*\d+\.\s+\[(\w+)\]\s+(.+?)\s+\((.+?):(\d+)\)", line)
        if m:
            sections.append({"level": m.group(1), "title": m.group(2), "file": m.group(3), "line": int(m.group(4))})

    if not sections:
        parts.append("No sections found.")
        return "\n".join(parts)

    parts.append("Overall structure:")
    if any("IEEE" in line or "ieee" in line.lower() for line in map_result.split("\n")):
        parts.append("  - This manuscript appears to follow an IEEE-style structure.")
    else:
        parts.append("  - Standard paper structure detected.")
    parts.append("")

    parts.append("Sections:")
    role_map = {
        "introduction": "motivation, challenge, contribution",
        "related": "prior methods and literature",
        "method": "proposed framework",
        "experiment": "datasets, metrics, comparison, ablation",
        "result": "findings and analysis",
        "conclusion": "summary and future work",
        "abstract": "overview",
    }
    for i, s in enumerate(sections[:30], 1):
        role = "unknown"
        for kw, r in role_map.items():
            if kw in s["title"].lower():
                role = r
                break
        parts.append(f"  {i}. {s['title']}")
        parts.append(f"     Role: {role}")
    parts.append("")

    issues = []
    has_intro = any("intro" in s["title"].lower() for s in sections)
    has_method = any("method" in s["title"].lower() or "approach" in s["title"].lower() for s in sections)
    has_exp = any("experiment" in s["title"].lower() or "result" in s["title"].lower() for s in sections)
    has_conclusion = any("conclusion" in s["title"].lower() for s in sections)
    has_related = any("related" in s["title"].lower() for s in sections)
    has_ablation = any("ablation" in s["title"].lower() for s in sections)

    if not has_intro:
        issues.append("- Introduction section not clearly identified")
    if not has_method:
        issues.append("- Method/Methodology section not clearly identified")
    if not has_exp:
        issues.append("- Experiments/Results section not clearly identified")
    if not has_conclusion:
        issues.append("- Conclusion section not clearly identified")
    if not has_related:
        issues.append("- Related Work section may be missing or merged")
    if not has_ablation:
        issues.append("- Ablation study section not explicitly visible")

    if issues:
        parts.append("Potential structure issues:")
        parts.extend(issues)
        parts.append("")

    parts.append("Suggested Codex actions:")
    parts.append("  - Read method and experiments together to verify consistency")
    parts.append("  - Check whether contributions in Introduction are supported by experiments")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_PAPER_REVIEW:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.paper import LATEX_STRUCTURE_SYSTEM_PROMPT
            llm_input = f"LaTeX structure:\n{map_result[:3000]}"
            llm_result = ask_llm(LATEX_STRUCTURE_SYSTEM_PROMPT, llm_input, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# find_paper_sections
# ---------------------------------------------------------------------------

def find_paper_sections_logic(
    query: str = "",
    main_file: str = "",
) -> str:
    if not main_file:
        main_file = detect_main_tex_file() or ""
    if not main_file:
        return "[Error] No main .tex file found."

    try:
        tex_text = read_latex_file_safe(main_file)
    except Exception as e:
        return f"[Error] Cannot read {main_file}: {e}"

    project_files = resolve_latex_project_files(main_file)
    all_sections = []
    for f in project_files:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f)
            all_sections.extend(parse_latex_sections(strip_latex_comments(text), f))
        except Exception:
            pass

    parts = ["Paper Sections", ""]
    if query:
        parts.append(f"Query: {query}")
    parts.append("")

    if not query:
        parts.append("All sections:")
        for i, s in enumerate(all_sections[:50], 1):
            parts.append(f"  {i}. [{s['level']}] {s['title']} ({s['file']}:{s['line']})")
        return "\n".join(parts)

    query_lower = query.lower()
    matches = [s for s in all_sections if query_lower in s["title"].lower() or query_lower in s["level"].lower()]

    if not matches:
        parts.append(f"No sections matching '{query}' found.")
        parts.append("Available sections:")
        for s in all_sections[:20]:
            parts.append(f"  - [{s['level']}] {s['title']}")
        return "\n".join(parts)

    parts.append("Matches:")
    for i, s in enumerate(matches, 1):
        parts.append(f"  {i}. {s['file']}:{s['line']}")
        parts.append(f"     Level: {s['level']}")
        parts.append(f"     Title: {s['title']}")
    parts.append("")

    if matches:
        first_match = matches[0]
        match_idx = next((i for i, s in enumerate(all_sections) if s == first_match), -1)
        if match_idx >= 0:
            nearby = all_sections[max(0, match_idx - 1):match_idx + 5]
            parts.append("All nearby sections:")
            for s in nearby:
                parts.append(f"  - [{s['level']}] {s['title']}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# review_paper_structure
# ---------------------------------------------------------------------------

def review_paper_structure_logic(
    main_file: str = "",
    paper_type: str = "ieee",
    use_llm: bool = True,
) -> str:
    if not main_file:
        main_file = detect_main_tex_file() or ""
    if not main_file:
        return "[Error] No main .tex file found."

    try:
        tex_text = read_latex_file_safe(main_file)
    except Exception as e:
        return f"[Error] Cannot read {main_file}: {e}"

    tex_text_clean = strip_latex_comments(tex_text)
    project_files = resolve_latex_project_files(main_file)

    all_sections = []
    all_figures = []
    all_tables = []
    all_citations = []
    for f in project_files:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = strip_latex_comments(read_latex_file_safe(f))
            all_sections.extend(parse_latex_sections(text, f))
            all_figures.extend(parse_latex_figures(text, f))
            all_tables.extend(parse_latex_tables(text, f))
            all_citations.extend(parse_latex_citations(text, f))
        except Exception:
            pass

    abstract = parse_latex_abstract(tex_text)
    title = parse_latex_title(tex_text)
    bib_files = find_bib_files()

    section_titles = [s["title"].lower() for s in all_sections]
    has_title = bool(title)
    has_abstract = bool(abstract)
    has_intro = any("intro" in t for t in section_titles)
    has_related = any("related" in t for t in section_titles)
    has_method = any("method" in t or "approach" in t for t in section_titles)
    has_exp = any("experiment" in t or "result" in t for t in section_titles)
    has_conclusion = any("conclusion" in t for t in section_titles)
    has_refs = bool(bib_files) or any("reference" in t for t in section_titles)
    has_ablation = any("ablation" in t or "analysis" in t for t in section_titles)

    parts = ["Paper Structure Review", ""]
    parts.append("Detected structure:")
    parts.append(f"  - Title: {'found' if has_title else 'missing'}")
    parts.append(f"  - Abstract: {'found' if has_abstract else 'missing'}")
    parts.append(f"  - Introduction: {'found' if has_intro else 'missing'}")
    parts.append(f"  - Related Work: {'found' if has_related else 'missing / merged'}")
    parts.append(f"  - Method: {'found' if has_method else 'missing'}")
    parts.append(f"  - Experiments: {'found' if has_exp else 'missing'}")
    parts.append(f"  - Conclusion: {'found' if has_conclusion else 'missing'}")
    parts.append(f"  - References: {'found' if has_refs else 'missing'}")
    parts.append(f"  - Figures: {len(all_figures)}")
    parts.append(f"  - Tables: {len(all_tables)}")
    parts.append(f"  - Citations: {len(all_citations)}")
    parts.append("")

    strengths = []
    if has_title and has_abstract and has_intro and has_method and has_exp and has_conclusion:
        strengths.append("- The manuscript has a standard complete structure.")
    if all_figures:
        strengths.append(f"- Contains {len(all_figures)} figure(s).")
    if all_tables:
        strengths.append(f"- Contains {len(all_tables)} table(s).")
    if all_citations:
        strengths.append(f"- Contains {len(all_citations)} citation(s).")
    if strengths:
        parts.append("Strengths:")
        parts.extend(strengths)
        parts.append("")

    issues = []
    if not has_title:
        issues.append("1. Title is missing.")
    if not has_abstract:
        issues.append("2. Abstract is missing.")
    if not has_intro:
        issues.append("3. Introduction section is missing.")
    if not has_method:
        issues.append("4. Method/Methodology section is missing.")
    if not has_exp:
        issues.append("5. Experiments/Results section is missing.")
    if not has_conclusion:
        issues.append("6. Conclusion section is missing.")
    if not has_ablation and has_exp:
        issues.append("7. Ablation study section is not explicitly visible.")
    if not has_related:
        issues.append("8. Related Work section may be missing or merged into Introduction.")
    if issues:
        parts.append("Potential issues:")
        parts.extend(issues)
        parts.append("")

    parts.append("Suggested improvements:")
    if not has_ablation:
        parts.append("  - Add a subsection for ablation study if experiments contain module analysis.")
    parts.append("  - Ensure each claimed contribution has corresponding evidence in experiments.")
    parts.append("  - Read Introduction and Experiments together to verify consistency.")
    parts.append("")
    parts.append("Notes for Codex:")
    parts.append("  - Read Introduction contribution claims against Experiments tables.")
    parts.append("  - Check whether method modules are reflected in ablation tables.")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_PAPER_REVIEW:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.paper import PAPER_STRUCTURE_REVIEW_SYSTEM_PROMPT
            llm_input = f"Structure review:\n{result}"
            llm_result = ask_llm(PAPER_STRUCTURE_REVIEW_SYSTEM_PROMPT, llm_input, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_claim_evidence
# ---------------------------------------------------------------------------

_CLAIM_KEYWORDS = re.compile(
    r"\b(significantly|substantially|outperforms|state-of-the-art|superior|robust|effective|efficient|accurate|"
    r"improves|reduces|achieves|best|novel|first|consistently|remarkably|dramatically|substantially|"
    r"显著|明显|大幅|优于|最佳|首次|有效|鲁棒|提升|降低)\b",
    re.IGNORECASE,
)


def check_claim_evidence_logic(
    main_file: str = "",
    section_query: str = "",
    use_llm: bool = True,
) -> str:
    if not main_file:
        main_file = detect_main_tex_file() or ""
    if not main_file:
        return "[Error] No main .tex file found."

    project_files = resolve_latex_project_files(main_file)

    all_sections = []
    all_citations = []
    all_figures = []
    all_tables = []
    all_refs = []

    for f in project_files:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = strip_latex_comments(read_latex_file_safe(f))
            all_sections.extend(parse_latex_sections(text, f))
            all_citations.extend(parse_latex_citations(text, f))
            all_figures.extend(parse_latex_figures(text, f))
            all_tables.extend(parse_latex_tables(text, f))
            all_refs.extend(parse_latex_refs(text, f))
        except Exception:
            pass

    claims = []
    for f in project_files:
        if "[NOT FOUND]" in f:
            continue
        try:
            lines = read_latex_file_safe(f).split("\n")
            for i, line in enumerate(lines, 1):
                if _CLAIM_KEYWORDS.search(line):
                    stripped = line.strip()
                    if len(stripped) > 10:
                        keyword_m = _CLAIM_KEYWORDS.search(line)
                        keyword = keyword_m.group(0) if keyword_m else ""
                        claims.append({
                            "text": stripped[:200],
                            "file": f,
                            "line": i,
                            "keyword": keyword,
                        })
        except Exception:
            pass

    claims = claims[:MAX_CLAIMS_TO_CHECK]

    table_refs = [r for r in all_refs if "tab" in r["ref"].lower()]
    fig_refs = [r for r in all_refs if "fig" in r["ref"].lower()]
    cite_keys = {c["key"] for c in all_citations}

    parts = ["Claim-Evidence Check", ""]
    parts.append(f"Claims checked: {len(claims)}")
    parts.append("")

    if not claims:
        parts.append("No strong claims detected with keyword matching.")
        return "\n".join(parts)

    issues_count = 0
    for i, claim in enumerate(claims[:MAX_CLAIMS_TO_CHECK], 1):
        parts.append(f"{i}. \"{claim['text'][:100]}\"")
        parts.append(f"   Location: {claim['file']}:{claim['line']}")
        parts.append(f"   Strength: strong (keyword: '{claim['keyword']}')")

        evidence_found = []
        if table_refs:
            evidence_found.append(f"- {len(table_refs)} table reference(s) in project")
        if fig_refs:
            evidence_found.append(f"- {len(fig_refs)} figure reference(s) in project")
        if cite_keys:
            evidence_found.append(f"- {len(cite_keys)} unique citation(s)")

        if evidence_found:
            parts.append("   Possible evidence found:")
            for e in evidence_found[:3]:
                parts.append(f"     {e}")
        else:
            parts.append("   Possible evidence found: (none)")
            issues_count += 1

        if "significantly" in claim["keyword"].lower() or "显著" in claim["keyword"]:
            parts.append("   Issue: 'significantly' may be too strong unless statistical evidence is provided.")
            parts.append("   Suggestion: Use 'consistently improves' or add statistical evidence.")
        parts.append("")

    parts.append(f"Overall issues:")
    parts.append(f"  - {issues_count} claims lack direct evidence references.")
    parts.append("")
    parts.append("Notes for Codex:")
    parts.append("  - Check Introduction contribution claims against Experiments tables.")
    parts.append("  - Consider softening claims without direct evidence.")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_PAPER_REVIEW:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.paper import CLAIM_EVIDENCE_SYSTEM_PROMPT
            llm_input = f"Claim-evidence check:\n{result[:3000]}"
            llm_result = ask_llm(CLAIM_EVIDENCE_SYSTEM_PROMPT, llm_input, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# parse_bib_file
# ---------------------------------------------------------------------------

def parse_bib_file_logic(
    bib_file: str = "",
    max_entries: int = 200,
) -> str:
    if not bib_file:
        bibs = find_bib_files()
        if not bibs:
            return "[Error] No .bib files found in project."
        bib_file = bibs[0]

    try:
        bib_text = read_bib_file_safe(bib_file)
    except Exception as e:
        return f"[Error] Cannot read {bib_file}: {e}"

    entries = parse_bib_entries(bib_text, max_entries=max_entries)
    summary = summarize_bib_entries(entries)

    parts = ["BibTeX Summary", ""]
    parts.append(f"Bib file: {bib_file}")
    parts.append("")
    parts.append(summary)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# check_citation_coverage
# ---------------------------------------------------------------------------

def check_citation_coverage_logic(
    main_file: str = "",
    bib_file: str = "",
) -> str:
    if not main_file:
        main_file = detect_main_tex_file() or ""
    if not main_file:
        return "[Error] No main .tex file found."

    if not bib_file:
        bibs = find_bib_files()
        if not bibs:
            return "[Error] No .bib files found."
        bib_file = bibs[0]

    project_files = resolve_latex_project_files(main_file)
    all_citations = []
    for f in project_files:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = strip_latex_comments(read_latex_file_safe(f))
            all_citations.extend(parse_latex_citations(text, f))
        except Exception:
            pass

    try:
        bib_text = read_bib_file_safe(bib_file)
        bib_entries = parse_bib_entries(bib_text)
        bib_keys = {e["key"] for e in bib_entries}
    except Exception as e:
        return f"[Error] Cannot read bib file: {e}"

    cited_keys = {c["key"] for c in all_citations}
    missing_bib = cited_keys - bib_keys
    uncited = bib_keys - cited_keys
    duplicate_keys = [e["key"] for e in bib_entries if e["is_duplicate"]]

    parts = ["Citation Coverage Check", ""]
    parts.append(f"Main file: {main_file}")
    parts.append(f"Bib file: {bib_file}")
    parts.append("")
    parts.append(f"Citation commands: {len(all_citations)}")
    parts.append(f"Unique citation keys used: {len(cited_keys)}")
    parts.append(f"Bib entries: {len(bib_entries)}")
    parts.append("")

    if missing_bib:
        parts.append("Missing bib entries (cited but not in .bib):")
        for k in sorted(missing_bib)[:20]:
            parts.append(f"  - {k}")
        parts.append("")

    if uncited:
        parts.append(f"Uncited bib entries ({len(uncited)}):")
        for k in sorted(uncited)[:20]:
            parts.append(f"  - {k}")
        if len(uncited) > 20:
            parts.append(f"  ... showing first 20 of {len(uncited)}")
        parts.append("")

    if duplicate_keys:
        parts.append("Duplicate bib keys:")
        for k in duplicate_keys[:10]:
            parts.append(f"  - {k}")
        parts.append("")

    issues = []
    if missing_bib:
        issues.append(f"{len(missing_bib)} citation key(s) are used in text but missing from {bib_file}.")
    if uncied:
        issues.append(f"{len(uncited)} bib entries are not cited.")
    if duplicate_keys:
        issues.append(f"{len(duplicate_keys)} duplicate bib key(s) found.")

    if issues:
        parts.append("Potential issues:")
        for i, iss in enumerate(issues, 1):
            parts.append(f"  {i}. {iss}")
        parts.append("")

    parts.append("Suggested Codex actions:")
    if missing_bib:
        parts.append("  1. Verify missing bib keys.")
    if uncied:
        parts.append("  2. Remove unused references only after confirming they are not needed.")
    parts.append("  3. Do not invent references.")

    return "\n".join(parts)
