import re
from collections import Counter
from pathlib import Path

from cheap_agent.tools._common import truncate
from cheap_agent.config import (
    ENABLE_LLM_WRITING_CHECK,
    MAX_ABSTRACT_CHARS,
    MAX_CONTRIBUTION_CHARS,
    MAX_INTRODUCTION_CHARS,
    MAX_PARAGRAPH_CHARS,
    MAX_TERMS_TO_CHECK,
    MAX_WRITING_OUTPUT_CHARS,
    PAPER_CACHE_DIR,
    PAPER_LLM_MAX_TOKENS,
    PAPER_LLM_TEMPERATURE,
    WORKSPACE_ROOT,
)
from cheap_agent.parsers.latex_parser import (
    detect_main_tex_file,
    parse_latex_abstract,
    parse_latex_sections,
    read_latex_file_safe,
    resolve_latex_project_files,
    strip_latex_comments,
)
from cheap_agent.workspace import resolve_safe_path



def _paper_cache_dir() -> Path:
    d = WORKSPACE_ROOT.resolve() / PAPER_CACHE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _call_llm(system_prompt: str, user_prompt: str, use_llm: bool) -> str | None:
    if not use_llm or not ENABLE_LLM_WRITING_CHECK:
        return None
    try:
        from cheap_agent.llm_client import ask_llm
        return ask_llm(system_prompt, user_prompt, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
    except Exception as e:
        return f"[LLM Error] {e}"


# ---------------------------------------------------------------------------
# Over-strong / informal word lists
# ---------------------------------------------------------------------------

_OVER_STRONG_WORDS = [
    (r"\bsignificantly\b", "high", "Use 'consistently' or provide statistical evidence"),
    (r"\bprove[sd]?\b", "high", "Use 'demonstrates' or 'suggests' unless formal proof is given"),
    (r"\bguarantee[sd]?\b", "high", "Use 'ensures' or remove"),
    (r"\bperfect\b", "high", "Use 'effective' or 'well-performing'"),
    (r"\bobviously\b", "medium", "Remove or rephrase"),
    (r"\bvery\b", "low", "Remove or use a stronger adjective"),
    (r"\bhuge\b", "medium", "Use 'substantial' or 'significant'"),
    (r"\bexcellent\b", "medium", "Use 'effective' or 'strong'"),
    (r"\bremarkable\b", "medium", "Use 'notable' or 'substantial'"),
    (r"\bdramatically\b", "medium", "Use 'substantially'"),
    (r"\balways\b", "medium", "Use 'consistently' or 'typically'"),
    (r"\ball cases\b", "medium", "Use 'most cases' or provide evidence"),
    (r"\bcompletely\b", "medium", "Use 'largely' or 'substantially'"),
    (r"\bstate-of-the-art\b", "medium", "Only use if clearly supported by experiments"),
    (r"\bprove\b", "high", "Use 'demonstrates'"),
    (r"\bguarantee\b", "high", "Remove or rephrase"),
]

_INFORMAL_PHRASES = [
    (r"\bwe can see that\b", "medium", "Use 'As shown in' or 'It can be observed that'"),
    (r"\bit is obvious that\b", "high", "Remove or provide evidence"),
    (r"\bjust\b", "low", "Remove informal 'just'"),
    (r"\ba lot of\b", "low", "Use 'numerous' or 'many'"),
    (r"\bkind of\b", "low", "Use 'approximately' or 'somewhat'"),
    (r"\bsort of\b", "low", "Remove or rephrase formally"),
    (r"\bget rid of\b", "low", "Use 'eliminate' or 'remove'"),
    (r"\bfind out\b", "low", "Use 'determine' or 'identify'"),
    (r"\bfigure out\b", "low", "Use 'determine' or 'resolve'"),
    (r"\bby the way\b", "low", "Remove"),
    (r"\bin a nutshell\b", "low", "Use 'In summary'"),
    (r"\bas we all know\b", "high", "Remove or provide citation"),
    (r"\bit goes without saying\b", "high", "Remove"),
]

_REF_STYLE_PATTERNS = [
    (re.compile(r"Figure\s+\\ref\{", re.IGNORECASE), "Figure \\ref{}"),
    (re.compile(r"Fig\.\s+\\ref\{", re.IGNORECASE), "Fig.~\\ref{}"),
    (re.compile(r"Table\s+\\ref\{", re.IGNORECASE), "Table \\ref{}"),
    (re.compile(r"Tab\.\s+\\ref\{", re.IGNORECASE), "Tab.~\\ref{}"),
    (re.compile(r"Section\s+\\ref\{", re.IGNORECASE), "Section \\ref{}"),
    (re.compile(r"Sec\.\s+\\ref\{", re.IGNORECASE), "Sec.~\\ref{}"),
]

_ABBREVIATION_RE = re.compile(r"\b([A-Z]{2,})\b")
_ABBR_DEFINITION_RE = re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(([A-Z]{2,})\)")


# ---------------------------------------------------------------------------
# review_academic_paragraph
# ---------------------------------------------------------------------------

def review_academic_paragraph_logic(
    paragraph: str,
    section_type: str = "",
    use_llm: bool = True,
) -> str:
    if not paragraph or not paragraph.strip():
        return "[Error] paragraph must not be empty"

    paragraph = paragraph[:MAX_PARAGRAPH_CHARS]
    issues = []

    for pattern, severity, suggestion in _OVER_STRONG_WORDS:
        for m in re.finditer(pattern, paragraph, re.IGNORECASE):
            word = m.group(0)
            context_start = max(0, m.start() - 30)
            context_end = min(len(paragraph), m.end() + 30)
            context = paragraph[context_start:context_end].strip()
            issues.append({
                "type": "over-strong claim",
                "text": word,
                "context": context,
                "severity": severity,
                "suggestion": suggestion,
            })

    for pattern, severity, suggestion in _INFORMAL_PHRASES:
        for m in re.finditer(pattern, paragraph, re.IGNORECASE):
            phrase = m.group(0)
            context_start = max(0, m.start() - 30)
            context_end = min(len(paragraph), m.end() + 30)
            context = paragraph[context_start:context_end].strip()
            issues.append({
                "type": "informal expression",
                "text": phrase,
                "context": context,
                "severity": severity,
                "suggestion": suggestion,
            })

    sentences = re.split(r"[.!?]+", paragraph)
    long_sentences = [s.strip() for s in sentences if len(s.strip()) > 250]
    for s in long_sentences[:3]:
        issues.append({
            "type": "long sentence",
            "text": s[:100] + "...",
            "context": "",
            "severity": "medium",
            "suggestion": "Consider splitting into shorter sentences",
        })

    abbreviations = set(_ABBREVIATION_RE.findall(paragraph))
    defined_abbreviations = set(m.group(2) for m in _ABBR_DEFINITION_RE.finditer(paragraph))
    undefined = abbreviations - defined_abbreviations
    for abbr in sorted(undefined):
        if len(abbr) >= 3 and abbr not in ("IEEE", "ACM", "CVPR", "ICCV", "ECCV", "AAAI", "TGRS", "GRSL"):
            issues.append({
                "type": "undefined abbreviation",
                "text": abbr,
                "context": "",
                "severity": "low",
                "suggestion": f"Define '{abbr}' on first use",
            })

    severity_count = Counter(i["severity"] for i in issues)
    if severity_count["high"] > 0:
        overall = "needs revision"
    elif severity_count["medium"] > 2:
        overall = "needs revision"
    elif issues:
        overall = "acceptable"
    else:
        overall = "clear"

    parts = ["Academic Paragraph Review", ""]
    parts.append(f"Section type: {section_type or 'unknown'}")
    parts.append(f"Overall assessment: {overall}")
    parts.append(f"Issues found: {len(issues)}")
    parts.append("")

    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues[:20], 1):
            parts.append(f"{i}. {issue['type']}")
            if issue["text"]:
                parts.append(f"   - Text: \"{issue['text']}\"")
            if issue["context"]:
                parts.append(f"   - Context: \"{issue['context']}\"")
            parts.append(f"   - Severity: {issue['severity']}")
            parts.append(f"   - Suggestion: {issue['suggestion']}")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Focus on high severity issues first")
    parts.append("  - Use suggested rewrites as guidance, not final text")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Review this academic paragraph for IEEE/TGRS style. Be concise.",
        f"Paragraph:\n{paragraph[:2000]}\n\nIssues found:\n{result[:1000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_WRITING_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_abstract_quality
# ---------------------------------------------------------------------------

def _extract_abstract_from_tex(tex_path: str) -> str:
    try:
        text = read_latex_file_safe(tex_path)
        return parse_latex_abstract(text)
    except Exception:
        return ""


def check_abstract_quality_logic(
    abstract_text: str = "",
    tex_path: str = "",
    use_llm: bool = True,
) -> str:
    if not abstract_text:
        if tex_path:
            try:
                resolve_safe_path(tex_path)
                abstract_text = _extract_abstract_from_tex(tex_path)
            except (PermissionError, ValueError) as e:
                return f"[Error] {e}"
        else:
            main_tex = detect_main_tex_file()
            if main_tex:
                abstract_text = _extract_abstract_from_tex(main_tex)

    if not abstract_text:
        return "[Error] No abstract found. Provide abstract_text or tex_path."

    abstract_text = abstract_text[:MAX_ABSTRACT_CHARS]
    lower = abstract_text.lower()

    coverage = {}
    coverage["background"] = "present" if any(w in lower for w in ["background", "recent", "existing", "traditional", "conventional", "prior"]) else "weak/missing"
    coverage["challenge"] = "present" if any(w in lower for w in ["challenge", "difficult", "however", "limitation", "issue", "problem", "gap"]) else "weak/missing"
    coverage["method"] = "present" if any(w in lower for w in ["propose", "present", "introduce", "design", "develop", "our method", "we propose"]) else "weak/missing"
    coverage["novelty"] = "present" if any(w in lower for w in ["novel", "new", "first", "unique", "innovative", "contribution"]) else "weak/missing"
    coverage["experiments"] = "present" if any(w in lower for w in ["experiment", "result", "evaluation", "dataset", "benchmark", "outperform", "achieve", "demonstrate"]) else "weak/missing"
    coverage["conclusion"] = "present" if any(w in lower for w in ["conclude", "show", "demonstrate", "verify", "validate", "significance"]) else "weak/missing"

    issues = []
    if len(abstract_text.split()) < 50:
        issues.append("Abstract may be too short (less than 50 words)")
    if len(abstract_text.split()) > 300:
        issues.append("Abstract may be too long (over 300 words)")
    for key, status in coverage.items():
        if "missing" in status:
            issues.append(f"Missing or weak: {key}")

    strong_words = ["significantly", "prove", "guarantee", "perfect", "state-of-the-art"]
    for w in strong_words:
        if w in lower:
            issues.append(f"Over-strong claim: '{w}'")

    parts = ["Abstract Quality Check", ""]
    parts.append("Coverage:")
    for key, status in coverage.items():
        parts.append(f"  - {key}: {status}")
    parts.append("")
    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues, 1):
            parts.append(f"  {i}. {issue}")
        parts.append("")
    parts.append("Suggested improvement direction:")
    parts.append("  - Ensure all 6 dimensions are covered")
    parts.append("  - Use specific metrics and datasets")
    parts.append("  - Avoid over-strong claims without evidence")
    parts.append("")
    parts.append("Notes for Codex:")
    parts.append("  - Supplement missing dimensions with concrete information")
    parts.append("  - Soften claims without direct evidence")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check this abstract for IEEE/TGRS quality. Be concise.",
        f"Abstract:\n{abstract_text[:2000]}\n\nIssues:\n{result[:1000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_WRITING_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_introduction_logic
# ---------------------------------------------------------------------------

def _extract_introduction_from_tex(tex_path: str) -> str:
    try:
        text = read_latex_file_safe(tex_path, max_chars=MAX_INTRODUCTION_CHARS)
        text = strip_latex_comments(text)
        sections = parse_latex_sections(text, tex_path)
        intro_start = None
        intro_end = None
        for i, sec in enumerate(sections):
            if "intro" in sec["title"].lower():
                intro_start = sec["line"]
                if i + 1 < len(sections):
                    intro_end = sections[i + 1]["line"]
                break
        if intro_start is None:
            return ""
        lines = text.split("\n")
        start_idx = intro_start - 1
        end_idx = intro_end - 1 if intro_end else min(start_idx + 200, len(lines))
        return "\n".join(lines[start_idx:end_idx])
    except Exception:
        return ""


def check_introduction_logic_logic(
    tex_path: str = "",
    introduction_text: str = "",
    use_llm: bool = True,
) -> str:
    if not introduction_text:
        if tex_path:
            try:
                resolve_safe_path(tex_path)
                introduction_text = _extract_introduction_from_tex(tex_path)
            except (PermissionError, ValueError) as e:
                return f"[Error] {e}"
        else:
            main_tex = detect_main_tex_file()
            if main_tex:
                introduction_text = _extract_introduction_from_tex(main_tex)

    if not introduction_text:
        return "[Error] No Introduction found. Provide introduction_text or tex_path."

    introduction_text = introduction_text[:MAX_INTRODUCTION_CHARS]
    lower = introduction_text.lower()

    logic_chain = {}
    logic_chain["background"] = "present" if any(w in lower for w in ["background", "recent years", "widely used", "growing interest", "increasing attention"]) else "weak/missing"
    logic_chain["challenge"] = "present" if any(w in lower for w in ["challenge", "difficult", "however", "limitation", "issue", "problem", "gap", "difficulty"]) else "weak/missing"
    logic_chain["prior_limitations"] = "present" if any(w in lower for w in ["existing", "previous", "prior", "traditional", "conventional", "current methods", "drawback"]) else "weak/missing"
    logic_chain["motivation"] = "present" if any(w in lower for w in ["motivation", "to address", "to solve", "to overcome", "inspired by", "we aim", "our goal"]) else "weak/missing"
    logic_chain["proposed_idea"] = "present" if any(w in lower for w in ["propose", "present", "introduce", "design", "develop", "we propose", "our method"]) else "weak/missing"
    logic_chain["contributions"] = "present" if any(w in lower for w in ["contribution", "our main", "the main contributions", "we make the following", "key contributions"]) else "weak/missing"

    issues = []
    for key, status in logic_chain.items():
        if "missing" in status:
            issues.append(f"Missing or weak logic element: {key}")

    if "background" in lower and "challenge" not in lower and "however" not in lower:
        issues.append("Background present but no clear challenge transition")
    if "propose" in lower and "motivation" not in lower and "to address" not in lower:
        issues.append("Method proposed but motivation unclear")

    parts = ["Introduction Logic Check", ""]
    parts.append("Detected logic chain:")
    for i, (key, status) in enumerate(logic_chain.items(), 1):
        parts.append(f"  {i}. {key}: {status}")
    parts.append("")
    if issues:
        parts.append("Missing or weak parts:")
        for issue in issues:
            parts.append(f"  - {issue}")
        parts.append("")
    parts.append("Suggested restructuring:")
    parts.append("  1. First paragraph: background and task importance")
    parts.append("  2. Second paragraph: specific challenges in the field")
    parts.append("  3. Third paragraph: prior method limitations")
    parts.append("  4. Fourth paragraph: motivation and proposed idea")
    parts.append("  5. Final paragraph: contribution list")
    parts.append("")
    parts.append("Notes for Codex:")
    parts.append("  - Focus on paragraphs with weak logic transitions")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check Introduction logic chain for IEEE/TGRS paper. Be concise.",
        f"Introduction:\n{introduction_text[:3000]}\n\nIssues:\n{result[:1500]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_WRITING_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_contribution_clarity
# ---------------------------------------------------------------------------

_CONTRIBUTION_PATTERNS = [
    re.compile(r"(?:the\s+)?main\s+contributions?\s+(?:are|is|of\s+this\s+paper)", re.IGNORECASE),
    re.compile(r"(?:we\s+)?make\s+the\s+following\s+contributions?", re.IGNORECASE),
    re.compile(r"(?:our|the)\s+contributions?\s+(?:are|can\s+be\s+summarized)", re.IGNORECASE),
    re.compile(r"contributions?\s+of\s+this\s+(?:paper|work)", re.IGNORECASE),
    re.compile(r"(?:we\s+)?(?:propose|introduce|present)\s+(?:a|the|our)", re.IGNORECASE),
]

_VAGUE_WORDS = [
    r"\b(?:novel|new|effective|efficient|robust|superior)\b",
    r"\b(?:significantly|substantially|greatly)\b",
    r"\b(?:first|state-of-the-art)\b",
]


def _extract_contributions(text: str) -> list[str]:
    contributions = []
    lines = text.split("\n")
    in_contribution = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for pat in _CONTRIBUTION_PATTERNS:
            if pat.search(stripped):
                in_contribution = True
                break
        if in_contribution:
            if stripped.startswith(("\\item", "•", "-", "*")):
                contributions.append(stripped)
            elif re.match(r"^\d+[\.\)]\s+", stripped):
                contributions.append(stripped)
            elif contributions and not stripped.startswith(("\\section", "\\subsection")):
                contributions[-1] += " " + stripped
            elif len(contributions) > 0 and not any(pat.search(stripped) for pat in _CONTRIBUTION_PATTERNS):
                in_contribution = False
    return contributions[:10]


def check_contribution_clarity_logic(
    tex_path: str = "",
    contribution_text: str = "",
    use_llm: bool = True,
) -> str:
    if not contribution_text:
        if tex_path:
            try:
                resolve_safe_path(tex_path)
                contribution_text = read_latex_file_safe(tex_path, max_chars=MAX_CONTRIBUTION_CHARS)
            except (PermissionError, ValueError) as e:
                return f"[Error] {e}"
        else:
            main_tex = detect_main_tex_file()
            if main_tex:
                try:
                    contribution_text = read_latex_file_safe(main_tex, max_chars=MAX_CONTRIBUTION_CHARS)
                except Exception:
                    pass

    if not contribution_text:
        return "[Error] No contribution text found."

    contribution_text = contribution_text[:MAX_CONTRIBUTION_CHARS]
    contributions = _extract_contributions(contribution_text)

    if not contributions:
        return "No explicit contribution list found. Consider adding a contribution section in Introduction."

    parts = ["Contribution Clarity Check", ""]
    parts.append(f"Detected contributions: {len(contributions)}")
    parts.append("")

    all_issues = []
    for i, contrib in enumerate(contributions, 1):
        parts.append(f"Contribution {i}:")
        parts.append(f"  Text: {contrib[:150]}")

        clarity = "high"
        issues = []

        for vague_pat in _VAGUE_WORDS:
            if re.search(vague_pat, contrib, re.IGNORECASE):
                issues.append("Contains vague or over-strong words")
                clarity = "medium"
                break

        if len(contrib.split()) < 10:
            issues.append("Too short, lacks specificity")
            clarity = "low"

        if "novel" in contrib.lower() and "propose" not in contrib.lower() and "design" not in contrib.lower():
            issues.append("'novel' without clear method description")

        parts.append(f"  Clarity: {clarity}")
        if issues:
            parts.append(f"  Issues: {'; '.join(issues)}")
            all_issues.extend(issues)
        parts.append("")

    if len(contributions) > 4:
        all_issues.append("Too many contributions (more than 4). Consider consolidating.")
    if len(contributions) < 2:
        all_issues.append("Too few contributions (less than 2). Consider adding more.")

    if all_issues:
        parts.append("Overall issues:")
        for issue in all_issues[:10]:
            parts.append(f"  - {issue}")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Ensure each contribution has corresponding method section")
    parts.append("  - Ensure each contribution has experimental support")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check contribution clarity for IEEE/TGRS paper. Be concise.",
        f"Contributions:\n{chr(10).join(contributions[:5])}\n\nIssues:\n{result[:1500]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_WRITING_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_term_consistency
# ---------------------------------------------------------------------------

_TERM_VARIANTS = [
    ("Soft Top-K", ["soft top-k", "SoftTopK", "soft top-k selector", "Soft-TopK"]),
    ("scatter descriptor", ["scattering descriptor", "Scatter Descriptor", "scatter descriptors"]),
    ("AP50", ["AP_{50}", "AP@0.5", "AP$_{50}$", "AP 50"]),
    ("oriented object detection", ["rotated object detection", "Oriented Object Detection"]),
    ("false alarm", ["false positive", "FP", "False Alarm"]),
    ("mAP", ["mean Average Precision", "Mean Average Precision"]),
]


def _find_abbreviations(text: str) -> list[dict]:
    abbreviations = []
    defined = set()
    for m in _ABBR_DEFINITION_RE.finditer(text):
        full = m.group(1)
        abbr = m.group(2)
        defined.add(abbr)
        abbreviations.append({"abbr": abbr, "full": full, "line": text[:m.start()].count("\n") + 1, "defined": True})

    for m in _ABBREVIATION_RE.finditer(text):
        abbr = m.group(1)
        if abbr not in defined and len(abbr) >= 3 and abbr not in ("IEEE", "ACM", "CVPR", "ICCV", "ECCV", "AAAI", "TGRS", "GRSL", "SAR", "OBB"):
            abbreviations.append({"abbr": abbr, "full": "", "line": text[:m.start()].count("\n") + 1, "defined": False})

    return abbreviations[:MAX_TERMS_TO_CHECK]


def check_term_consistency_logic(
    tex_path: str = "",
    terms_hint: str = "",
    use_llm: bool = True,
) -> str:
    if tex_path:
        try:
            resolve_safe_path(tex_path)
            files_to_scan = [tex_path]
        except (PermissionError, ValueError) as e:
            return f"[Error] {e}"
    else:
        main_tex = detect_main_tex_file()
        if not main_tex:
            return "[Error] No main .tex file found."
        files_to_scan = resolve_latex_project_files(main_tex)

    all_text = ""
    file_texts = {}
    for f in files_to_scan:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f, max_chars=50000)
            text = strip_latex_comments(text)
            all_text += text + "\n"
            file_texts[f] = text
        except Exception:
            continue

    if not all_text:
        return "[Error] No text found to check."

    issues = []

    for canonical, variants in _TERM_VARIANTS:
        found_variants = []
        for v in [canonical] + variants:
            count = len(re.findall(re.escape(v), all_text, re.IGNORECASE))
            if count > 0:
                found_variants.append((v, count))
        if len(found_variants) > 1:
            variant_names = [f"{v} ({c}x)" for v, c in found_variants]
            issues.append({
                "type": "term variant",
                "canonical": canonical,
                "found": variant_names,
                "suggestion": f"Use '{canonical}' consistently",
            })

    abbreviations = _find_abbreviations(all_text)
    undefined_abbrs = [a for a in abbreviations if not a["defined"]]
    if undefined_abbrs:
        for a in undefined_abbrs[:10]:
            issues.append({
                "type": "undefined abbreviation",
                "canonical": a["abbr"],
                "found": [f"line ~{a['line']}"],
                "suggestion": f"Define '{a['abbr']}' on first use",
            })

    if terms_hint:
        hint_terms = [t.strip() for t in terms_hint.split(",") if t.strip()]
        for term in hint_terms:
            lower_term = term.lower()
            variants_found = set()
            for f, text in file_texts.items():
                for m in re.finditer(re.escape(term), text, re.IGNORECASE):
                    variants_found.add(m.group(0))
            if len(variants_found) > 1:
                issues.append({
                    "type": "hint term variant",
                    "canonical": term,
                    "found": list(variants_found),
                    "suggestion": f"Unify '{term}' spelling",
                })

    parts = ["Term Consistency Check", ""]
    parts.append(f"Files scanned: {len(file_texts)}")
    parts.append(f"Issues found: {len(issues)}")
    parts.append("")

    if issues:
        parts.append("Potential inconsistencies:")
        for i, issue in enumerate(issues[:15], 1):
            parts.append(f"{i}. {issue['type']}")
            parts.append(f"   Canonical: {issue['canonical']}")
            parts.append(f"   Found: {', '.join(issue['found'][:5])}")
            parts.append(f"   Suggestion: {issue['suggestion']}")
        parts.append("")
    else:
        parts.append("No significant term inconsistencies found.")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Unify terms to a single canonical form")
    parts.append("  - Define abbreviations on first use")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check term consistency. Be concise.",
        f"Issues:\n{result[:2000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_WRITING_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_ieee_style
# ---------------------------------------------------------------------------

def check_ieee_style_logic(
    tex_path: str = "",
    use_llm: bool = True,
    max_issues: int = 100,
) -> str:
    if tex_path:
        try:
            resolve_safe_path(tex_path)
            files_to_scan = [tex_path]
        except (PermissionError, ValueError) as e:
            return f"[Error] {e}"
    else:
        main_tex = detect_main_tex_file()
        if not main_tex:
            return "[Error] No main .tex file found."
        files_to_scan = resolve_latex_project_files(main_tex)

    all_text = ""
    for f in files_to_scan:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f, max_chars=50000)
            all_text += strip_latex_comments(text) + "\n"
        except Exception:
            continue

    if not all_text:
        return "[Error] No text found."

    issues = []

    for pattern, severity, suggestion in _OVER_STRONG_WORDS:
        for m in re.finditer(pattern, all_text, re.IGNORECASE):
            if len(issues) >= max_issues:
                break
            line_num = all_text[:m.start()].count("\n") + 1
            word = m.group(0)
            issues.append({
                "type": "over-strong claim",
                "source": f"line {line_num}",
                "text": word,
                "severity": severity,
                "suggestion": suggestion,
            })

    for pattern, severity, suggestion in _INFORMAL_PHRASES:
        for m in re.finditer(pattern, all_text, re.IGNORECASE):
            if len(issues) >= max_issues:
                break
            line_num = all_text[:m.start()].count("\n") + 1
            phrase = m.group(0)
            issues.append({
                "type": "informal expression",
                "source": f"line {line_num}",
                "text": phrase,
                "severity": severity,
                "suggestion": suggestion,
            })

    fig_ref = re.findall(r"Figure\s+\\ref\{", all_text, re.IGNORECASE)
    fig_dot_ref = re.findall(r"Fig\.\s*~?\\ref\{", all_text, re.IGNORECASE)
    if fig_ref and fig_dot_ref:
        issues.append({
            "type": "reference style inconsistency",
            "source": "throughout",
            "text": f"Figure \\ref{{}} ({len(fig_ref)}x) and Fig.~\\ref{{}} ({len(fig_dot_ref)}x) both used",
            "severity": "medium",
            "suggestion": "Choose one style, e.g., Fig.~\\ref{}",
        })

    tab_ref = re.findall(r"Table\s+\\ref\{", all_text, re.IGNORECASE)
    tab_dot_ref = re.findall(r"Tab\.\s*~?\\ref\{", all_text, re.IGNORECASE)
    if tab_ref and tab_dot_ref:
        issues.append({
            "type": "reference style inconsistency",
            "source": "throughout",
            "text": f"Table \\ref{{}} ({len(tab_ref)}x) and Tab.~\\ref{{}} ({len(tab_dot_ref)}x) both used",
            "severity": "medium",
            "suggestion": "Choose one style, e.g., Table~\\ref{}",
        })

    labels = set(re.findall(r"\\label\{([^}]+)\}", all_text))
    refs = set(re.findall(r"\\ref\{([^}]+)\}", all_text))
    refs.update(re.findall(r"\\autoref\{([^}]+)\}", all_text))
    unreferenced = labels - refs
    if unreferenced:
        issues.append({
            "type": "unreferenced label",
            "source": "throughout",
            "text": f"Labels defined but never referenced: {', '.join(sorted(unreferenced)[:5])}",
            "severity": "low",
            "suggestion": "Remove unused labels or add references",
        })
    undefined_ref = refs - labels
    if undefined_ref:
        issues.append({
            "type": "undefined reference",
            "source": "throughout",
            "text": f"References to undefined labels: {', '.join(sorted(undefined_ref)[:5])}",
            "severity": "high",
            "suggestion": "Add missing \\label{} definitions",
        })

    parts = ["IEEE Style Check", ""]
    parts.append(f"Files scanned: {len(files_to_scan)}")
    parts.append(f"Issues found: {len(issues)}")

    severity_count = Counter(i["severity"] for i in issues)
    parts.append(f"  - High severity: {severity_count.get('high', 0)}")
    parts.append(f"  - Medium severity: {severity_count.get('medium', 0)}")
    parts.append(f"  - Low severity: {severity_count.get('low', 0)}")
    parts.append("")

    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues[:max_issues], 1):
            parts.append(f"{i}. {issue['type']}")
            if issue.get("source"):
                parts.append(f"   Source: {issue['source']}")
            parts.append(f"   Text: \"{issue['text'][:80]}\"")
            parts.append(f"   Severity: {issue['severity']}")
            parts.append(f"   Suggestion: {issue['suggestion']}")
    else:
        parts.append("No significant style issues found.")

    parts.append("")
    parts.append("Notes for Codex:")
    parts.append("  - Focus on high severity issues first")
    parts.append("  - Use suggested rewrites as guidance")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Review IEEE/TGRS style issues. Be concise.",
        f"Style issues:\n{result[:2000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return truncate(result, MAX_WRITING_OUTPUT_CHARS)
