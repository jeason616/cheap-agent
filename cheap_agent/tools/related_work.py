import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from cheap_agent.cache import make_hash
from cheap_agent.cache_manager import ensure_cache_dir, get_disk_cache, set_disk_cache, write_json_cache_atomic
from cheap_agent.config import (
    CACHE_SCHEMA_VERSION,
    ENABLE_LLM_RELATED_WORK_CHECK,
    ENABLE_RELATED_WORK_CACHE,
    LLM_MODEL,
    MAX_BIB_ENTRIES_TO_ANALYZE,
    MAX_CITATION_SUGGESTIONS,
    MAX_OUTPUT_CHARS,
    MAX_REFERENCE_GROUPS,
    MAX_REFERENCES_PER_TOPIC,
    MAX_RELATED_WORK_OUTPUT_CHARS,
    MAX_RELATED_WORK_TEXT_CHARS,
    PAPER_CACHE_DIR,
    PAPER_LLM_MAX_TOKENS,
    PAPER_LLM_TEMPERATURE,
    REFERENCE_RECENCY_YEARS,
    RELATED_WORK_CACHE_TTL_SEC,
    WORKSPACE_ROOT,
)
from cheap_agent.parsers.bib_parser import (
    find_bib_files,
    parse_bib_entries,
    read_bib_file_safe,
)
from cheap_agent.parsers.latex_parser import (
    detect_main_tex_file,
    parse_latex_sections,
    read_latex_file_safe,
    resolve_latex_project_files,
    strip_latex_comments,
)
from cheap_agent.workspace import resolve_safe_path, get_relative_path


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"


def _paper_cache_dir() -> Path:
    d = WORKSPACE_ROOT.resolve() / PAPER_CACHE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _call_llm(system_prompt: str, user_prompt: str, use_llm: bool) -> str | None:
    if not use_llm or not ENABLE_LLM_RELATED_WORK_CHECK:
        return None
    try:
        from cheap_agent.llm_client import ask_llm
        return ask_llm(system_prompt, user_prompt, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
    except Exception as e:
        return f"[LLM Error] {e}"


def _get_bib_path(bib_path: str) -> str:
    if bib_path:
        try:
            resolve_safe_path(bib_path)
            return bib_path
        except (PermissionError, ValueError):
            return ""
    bibs = find_bib_files()
    return bibs[0] if bibs else ""


def _load_bib_entries(bib_path: str) -> list[dict]:
    if not bib_path:
        return []
    try:
        text = read_bib_file_safe(bib_path)
        return parse_bib_entries(text, max_entries=MAX_BIB_ENTRIES_TO_ANALYZE)
    except Exception:
        return []


def _get_related_work_text(tex_path: str) -> str:
    if tex_path:
        try:
            resolve_safe_path(tex_path)
            text = read_latex_file_safe(tex_path, max_chars=MAX_RELATED_WORK_TEXT_CHARS)
            return strip_latex_comments(text)
        except Exception:
            return ""
    main_tex = detect_main_tex_file()
    if not main_tex:
        return ""
    try:
        files = resolve_latex_project_files(main_tex)
        all_text = ""
        for f in files:
            if "[NOT FOUND]" in f:
                continue
            try:
                text = read_latex_file_safe(f, max_chars=MAX_RELATED_WORK_TEXT_CHARS)
                text = strip_latex_comments(text)
                sections = parse_latex_sections(text, f)
                for i, sec in enumerate(sections):
                    if "related" in sec["title"].lower() or "literature" in sec["title"].lower():
                        lines = text.split("\n")
                        start = sec["line"] - 1
                        end = sections[i + 1]["line"] - 1 if i + 1 < len(sections) else min(start + 300, len(lines))
                        all_text += "\n".join(lines[start:end]) + "\n"
            except Exception:
                continue
        return all_text[:MAX_RELATED_WORK_TEXT_CHARS]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Topic classification patterns
# ---------------------------------------------------------------------------

_TOPIC_PATTERNS = [
    ("SAR object detection", [r"\bsar\b.*\bdetect", r"\bdetect.*\bsar\b", r"\bsar\b.*\btarget"], "high"),
    ("SAR ship/aircraft/vehicle detection", [r"\bsar\b.*\bship\b", r"\bsar\b.*\baircraft\b", r"\bsar\b.*\bvehicle\b", r"\bship\b.*\bdetect\b"], "high"),
    ("Oriented/rotated object detection", [r"\boriented\b.*\bdetect", r"\brotated\b.*\bbox", r"\boriented\b.*\bbox", r"\bobb\b"], "high"),
    ("DETR/DINO/transformer detector", [r"\bdetr\b", r"\bdino\b", r"\btransformer\b.*\bdetect", r"\bquery.based\b"], "high"),
    ("Scattering center / ASC", [r"\bscatter\w*\b.*\bcenter\b", r"\basc\b", r"\battributed\b.*\bscatter"], "high"),
    ("Small object detection", [r"\bsmall\b.*\bobject\b", r"\bsmall\b.*\btarget\b", r"\bdense\b.*\btarget\b"], "medium"),
    ("Remote sensing object detection", [r"\bremote\b.*\bsens\w*\b.*\bdetect", r"\baerial\b.*\bdetect", r"\bsatellite\b.*\bdetect"], "medium"),
    ("SAR image interpretation", [r"\bsar\b.*\binterpret", r"\bsar\b.*\bimage\b.*\bunderstand", r"\bsar\b.*\brecognition\b"], "medium"),
    ("Multi-modal SAR/optical fusion", [r"\bmulti.modal\b.*\bsar\b", r"\bsar\b.*\boptical\b.*\bfusion\b"], "medium"),
    ("YOLO-based detection", [r"\byolo\b", r"\bultralytics\b"], "medium"),
    ("CNN-based detection", [r"\bcnn\b.*\bdetect", r"\bconvolutional\b.*\bdetect", r"\bbackbone\b"], "low"),
    ("Anchor-based detection", [r"\banchor.based\b", r"\bfaster\s*rcnn\b", r"\bssd\b", r"\byolo\b.*\banchor\b"], "low"),
]


def _classify_entry(entry: dict, topics_hint: str = "") -> tuple[str, str]:
    """Classify a bib entry into a topic. Returns (topic, reason)."""
    title = entry.get("title", "").lower()
    venue = (entry.get("journal", "") or entry.get("booktitle", "")).lower()
    key = entry.get("key", "").lower()
    combined = f"{title} {venue} {key}"

    for topic, patterns, conf in _TOPIC_PATTERNS:
        for pat in patterns:
            if re.search(pat, combined, re.IGNORECASE):
                return topic, f"title/venue matches pattern '{pat}'"

    if topics_hint:
        for hint in topics_hint.split(","):
            hint = hint.strip().lower()
            if hint and hint in combined:
                return hint, f"matches topics_hint '{hint}'"

    return "uncertain", "insufficient information to classify"


# ---------------------------------------------------------------------------
# group_references_by_topic
# ---------------------------------------------------------------------------

def group_references_by_topic_logic(
    bib_path: str = "",
    topics_hint: str = "",
    use_llm: bool = True,
) -> str:
    bib_path = _get_bib_path(bib_path)
    if not bib_path:
        return "[Error] No .bib file found."

    entries = _load_bib_entries(bib_path)
    if not entries:
        return "[Error] No bib entries found."

    groups = defaultdict(list)
    for entry in entries:
        topic, reason = _classify_entry(entry, topics_hint)
        groups[topic].append({"entry": entry, "reason": reason})

    parts = ["Reference Topic Groups", ""]
    parts.append(f"Bib file: {bib_path}")
    parts.append(f"Total entries: {len(entries)}")
    parts.append(f"Groups: {len(groups)}")
    parts.append("")

    priority_topics = []
    for topic in groups:
        if topic != "uncertain":
            priority_topics.append(topic)
    priority_topics.sort(key=lambda t: -len(groups[t]))

    for topic in priority_topics[:MAX_REFERENCE_GROUPS]:
        items = groups[topic]
        parts.append(f"Topic: {topic} ({len(items)} refs)")
        for item in items[:MAX_REFERENCES_PER_TOPIC]:
            e = item["entry"]
            title_short = e.get("title", "")[:80]
            year = e.get("year", "?")
            venue = e.get("journal", "") or e.get("booktitle", "") or ""
            parts.append(f"  - {e['key']}")
            parts.append(f"    Title: {title_short}")
            parts.append(f"    Year: {year}, Venue: {venue}")
            parts.append(f"    Reason: {item['reason']}")
        parts.append("")

    if "uncertain" in groups:
        items = groups["uncertain"]
        parts.append(f"Uncertain ({len(items)} refs):")
        for item in items[:10]:
            e = item["entry"]
            parts.append(f"  - {e['key']}: {e.get('title', '')[:60]}")
        if len(items) > 10:
            parts.append(f"  ... and {len(items) - 10} more")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Use these groups to organize Related Work paragraphs")
    parts.append("  - Uncertain entries may need manual classification")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Refine reference topic grouping. Be concise.",
        f"Groups:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Refinement:\n{llm_result}"

    return _truncate(result, MAX_RELATED_WORK_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_related_work_coverage
# ---------------------------------------------------------------------------

_EXPECTED_TOPICS = [
    "SAR object detection",
    "Oriented/rotated object detection",
    "DETR/DINO/transformer detector",
    "Scattering center / ASC",
    "Small object detection",
    "Remote sensing object detection",
]


def check_related_work_coverage_logic(
    tex_path: str = "",
    bib_path: str = "",
    topics_hint: str = "",
    use_llm: bool = True,
) -> str:
    rw_text = _get_related_work_text(tex_path)
    bib_path_resolved = _get_bib_path(bib_path)
    entries = _load_bib_entries(bib_path_resolved)

    groups = defaultdict(list)
    for entry in entries:
        topic, _ = _classify_entry(entry, topics_hint)
        groups[topic].append(entry)

    topics_to_check = _EXPECTED_TOPICS[:]
    if topics_hint:
        for t in topics_hint.split(","):
            t = t.strip()
            if t and t not in topics_to_check:
                topics_to_check.append(t)

    parts = ["Related Work Coverage Check", ""]
    parts.append(f"Related Work text: {'found (' + str(len(rw_text)) + ' chars)' if rw_text else 'not found'}")
    parts.append(f"Bib entries: {len(entries)}")
    parts.append("")

    coverage = {}
    for topic in topics_to_check:
        topic_lower = topic.lower()
        in_text = bool(re.search(re.escape(topic_lower.split("/")[0].split("(")[0].strip()), rw_text, re.IGNORECASE)) if rw_text else False
        in_bib = topic in groups
        if in_text and in_bib:
            coverage[topic] = "covered"
        elif in_text:
            coverage[topic] = "text present but few bib refs"
        elif in_bib:
            coverage[topic] = "bib refs present but text weak"
        else:
            coverage[topic] = "missing"

    parts.append("Coverage summary:")
    for topic, status in coverage.items():
        parts.append(f"  - {topic}: {status}")
    parts.append("")

    gaps = []
    for topic, status in coverage.items():
        if status in ("missing", "bib refs present but text weak"):
            refs = groups.get(topic, [])
            gaps.append({"topic": topic, "status": status, "refs": refs})

    if gaps:
        parts.append("Potential gaps:")
        for i, gap in enumerate(gaps[:10], 1):
            severity = "high" if gap["status"] == "missing" else "medium"
            parts.append(f"{i}. {gap['topic']}")
            parts.append(f"   Status: {gap['status']}")
            parts.append(f"   Severity: {severity}")
            if gap["refs"]:
                parts.append(f"   Available local refs: {', '.join(r['key'] for r in gap['refs'][:5])}")
            else:
                parts.append("   No local refs available — consider adding references.")
            parts.append("")
    else:
        parts.append("No significant coverage gaps found.")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Only local refs.bib is checked; no online search")
    parts.append("  - If a topic has no local refs, user must add them manually")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check Related Work coverage gaps. Be concise.",
        f"Coverage:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Analysis:\n{llm_result}"

    return _truncate(result, MAX_RELATED_WORK_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_reference_recency
# ---------------------------------------------------------------------------

def check_reference_recency_logic(
    bib_path: str = "",
    recent_year_threshold: int = 3,
    use_llm: bool = False,
) -> str:
    bib_path = _get_bib_path(bib_path)
    if not bib_path:
        return "[Error] No .bib file found."

    entries = _load_bib_entries(bib_path)
    if not entries:
        return "[Error] No bib entries found."

    current_year = datetime.now().year
    years = []
    missing_year = []
    year_counter = Counter()

    for entry in entries:
        year_str = entry.get("year", "").strip()
        if year_str and year_str.isdigit():
            y = int(year_str)
            years.append(y)
            year_counter[y] += 1
        else:
            missing_year.append(entry["key"])

    if not years:
        return "No valid year fields found in bib entries."

    median_year = sorted(years)[len(years) // 2]
    recent_n = sum(1 for y in years if y >= current_year - recent_year_threshold)
    recent_5 = sum(1 for y in years if y >= current_year - 5)

    parts = ["Reference Recency Check", ""]
    parts.append(f"Summary:")
    parts.append(f"  - Total references: {len(entries)}")
    parts.append(f"  - References with year: {len(years)}")
    parts.append(f"  - Missing year: {len(missing_year)}")
    parts.append(f"  - Recent refs within {recent_year_threshold} years: {recent_n}")
    parts.append(f"  - References within 5 years: {recent_5}")
    parts.append(f"  - Oldest: {min(years)}")
    parts.append(f"  - Newest: {max(years)}")
    parts.append(f"  - Median year: {median_year}")
    parts.append("")

    parts.append("Year distribution:")
    for y, c in sorted(year_counter.items(), reverse=True)[:15]:
        bar = "#" * min(c, 20)
        parts.append(f"  {y}: {bar} ({c})")
    parts.append("")

    issues = []
    if recent_n < len(years) * 0.2:
        issues.append(f"Only {recent_n}/{len(years)} references are within {recent_year_threshold} years. Consider adding recent work.")
    if missing_year:
        issues.append(f"{len(missing_year)} entries lack year field: {', '.join(missing_year[:5])}")

    if issues:
        parts.append("Potential issues:")
        for i, issue in enumerate(issues, 1):
            parts.append(f"  {i}. {issue}")
        parts.append("")

    parts.append("Notes:")
    parts.append("  - This tool does not search online; it only checks local refs.bib")
    parts.append("  - If recent references are insufficient, user must add them manually")

    return _truncate("\n".join(parts), MAX_RELATED_WORK_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_bibtex_quality
# ---------------------------------------------------------------------------

_TITLE_ACRONYMS = re.compile(r"\b(SAR|DINO|YOLO|CNN|DETR|GRSL|TGRS|IEEE|ASC|OBB|FPN|IoU)\b")
_DUPLICATE_TITLE_SIMILARITY = re.compile(r"(.{20,})")


def check_bibtex_quality_logic(
    bib_path: str = "",
    use_llm: bool = False,
) -> str:
    bib_path = _get_bib_path(bib_path)
    if not bib_path:
        return "[Error] No .bib file found."

    entries = _load_bib_entries(bib_path)
    if not entries:
        return "[Error] No bib entries found."

    issues = []
    seen_keys = set()

    for entry in entries:
        key = entry["key"]
        etype = entry.get("type", "").lower()
        title = entry.get("title", "")
        author = entry.get("author", "")
        year = entry.get("year", "")
        journal = entry.get("journal", "")
        booktitle = entry.get("booktitle", "")

        if key in seen_keys:
            issues.append({"type": "duplicate key", "entry": key, "severity": "high", "suggestion": f"Duplicate cite key: {key}"})
        seen_keys.add(key)

        if not title:
            issues.append({"type": "missing title", "entry": key, "severity": "high", "suggestion": f"Entry '{key}' lacks title"})
        if not author:
            issues.append({"type": "missing author", "entry": key, "severity": "high", "suggestion": f"Entry '{key}' lacks author"})
        if not year:
            issues.append({"type": "missing year", "entry": key, "severity": "medium", "suggestion": f"Entry '{key}' lacks year"})

        if etype == "article" and not journal:
            issues.append({"type": "missing journal", "entry": key, "severity": "high", "suggestion": f"Article '{key}' lacks journal"})
        if etype == "inproceedings" and not booktitle:
            issues.append({"type": "missing booktitle", "entry": key, "severity": "high", "suggestion": f"Inproceedings '{key}' lacks booktitle"})

        if title:
            acronyms = _TITLE_ACRONYMS.findall(title)
            for acr in acronyms:
                if f"{{{acr}}}" not in title and f"${acr}$" not in title:
                    issues.append({
                        "type": "title capitalization risk",
                        "entry": key,
                        "severity": "low",
                        "suggestion": f"'{acr}' in title may need braces: '{{{acr}}}'",
                    })

    titles = [(e.get("title", "").lower(), e["key"]) for e in entries if e.get("title")]
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            t1, k1 = titles[i]
            t2, k2 = titles[j]
            if len(t1) > 20 and len(t2) > 20:
                common = len(set(t1.split()) & set(t2.split()))
                total = len(set(t1.split()) | set(t2.split()))
                if total > 0 and common / total > 0.6:
                    issues.append({
                        "type": "possible duplicate",
                        "entry": f"{k1} / {k2}",
                        "severity": "medium",
                        "suggestion": f"Similar titles — may be duplicate",
                    })

    parts = ["BibTeX Quality Check", ""]
    parts.append(f"Summary:")
    parts.append(f"  - Total entries: {len(entries)}")
    high = sum(1 for i in issues if i["severity"] == "high")
    med = sum(1 for i in issues if i["severity"] == "medium")
    low = sum(1 for i in issues if i["severity"] == "low")
    parts.append(f"  - High severity: {high}")
    parts.append(f"  - Medium severity: {med}")
    parts.append(f"  - Low severity: {low}")
    parts.append("")

    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues[:30], 1):
            parts.append(f"{i}. {issue['type']}")
            parts.append(f"   Entry: {issue['entry']}")
            parts.append(f"   Severity: {issue['severity']}")
            parts.append(f"   Suggestion: {issue['suggestion']}")
    else:
        parts.append("No significant quality issues found.")

    return _truncate("\n".join(parts), MAX_RELATED_WORK_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# suggest_citation_positions
# ---------------------------------------------------------------------------

_CITATION_NEED_PATTERNS = [
    (r"\bsar\b.*\bimage\b.*\b(?:affect|character|noise|scatter)", "SAR imaging characteristics"),
    (r"\boriented\b.*\bdetect\b.*\b(?:widely|attract|popular|stud)", "oriented detection trend"),
    (r"\bdetr\b.*\b(?:show|achieve|attract|popular|attention)", "DETR trend"),
    (r"\bdino\b.*\b(?:show|achieve|strong|perform)", "DINO performance"),
    (r"\bscatter\w*\b.*\bcenter\b.*\b(?:provide|offer|interpret)", "scattering center interpretation"),
    (r"\bexist\w*\b.*\bmethod\b.*\b(?:struggle|limit|fail|issue|challenge)", "existing method limitations"),
    (r"\btradition\w*\b.*\bmethod\b.*\b(?:suffer|limit|weak)", "traditional method limitations"),
    (r"\bdeep\b.*\blearn\w*\b.*\b(?:achieve|show|dominat)", "deep learning trend"),
    (r"\bremote\b.*\bsens\w*\b.*\b(?:applicat|task|challeng)", "remote sensing domain"),
    (r"\bsmall\b.*\bobject\b.*\b(?:difficult|challenge|hard|miss)", "small object challenge"),
]

_CITATION_NEED_PATTERNS_ZH = [
    (r"sar.*图像.*(?:受到|影响|特性)", "SAR imaging characteristics"),
    (r"旋转.*检测.*(?:广泛|关注|研究)", "oriented detection trend"),
    (r"现有.*方法.*(?:不足|局限|问题)", "existing method limitations"),
    (r"散射.*中心.*(?:提供|解释|可解释)", "scattering center interpretation"),
]


def suggest_citation_positions_logic(
    tex_path: str = "",
    section_name: str = "",
    use_llm: bool = True,
    max_suggestions: int = 30,
) -> str:
    rw_text = _get_related_work_text(tex_path)
    if not rw_text:
        main_tex = detect_main_tex_file()
        if main_tex:
            try:
                files = resolve_latex_project_files(main_tex)
                all_text = ""
                for f in files:
                    if "[NOT FOUND]" in f:
                        continue
                    try:
                        text = read_latex_file_safe(f, max_chars=MAX_RELATED_WORK_TEXT_CHARS)
                        all_text += strip_latex_comments(text) + "\n"
                    except Exception:
                        continue
                rw_text = all_text[:MAX_RELATED_WORK_TEXT_CHARS]
            except Exception:
                pass

    if not rw_text:
        return "[Error] No text found to analyze."

    bib_path = _get_bib_path("")
    entries = _load_bib_entries(bib_path)

    suggestions = []
    lines = rw_text.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("%") or stripped.startswith("\\"):
            continue
        if len(stripped) < 20:
            continue

        for pattern, topic in _CITATION_NEED_PATTERNS + _CITATION_NEED_PATTERNS_ZH:
            if re.search(pattern, stripped, re.IGNORECASE):
                candidates = []
                for entry in entries:
                    title_lower = entry.get("title", "").lower()
                    if any(kw in title_lower for kw in topic.lower().split()):
                        candidates.append(entry["key"])
                if len(candidates) > 3:
                    candidates = candidates[:3]

                suggestions.append({
                    "line": i,
                    "text": stripped[:150],
                    "topic": topic,
                    "candidates": candidates,
                    "confidence": "medium" if candidates else "low",
                })
                break

    suggestions = suggestions[:max_suggestions]

    parts = ["Citation Position Suggestions", ""]
    parts.append(f"Text analyzed: {len(rw_text)} chars")
    parts.append(f"Bib entries available: {len(entries)}")
    parts.append(f"Suggestions: {len(suggestions)}")
    parts.append("")

    no_candidate_topics = []
    for i, s in enumerate(suggestions, 1):
        parts.append(f"Suggestion {i}")
        parts.append(f"  Line: ~{s['line']}")
        parts.append(f"  Text: \"{s['text']}\"")
        parts.append(f"  Topic: {s['topic']}")
        parts.append(f"  Confidence: {s['confidence']}")
        if s["candidates"]:
            parts.append(f"  Candidate refs: {', '.join(s['candidates'])}")
        else:
            parts.append("  No local candidate found")
            no_candidate_topics.append(s["topic"])
        parts.append("")

    if no_candidate_topics:
        parts.append("Topics needing additional references:")
        for t in sorted(set(no_candidate_topics)):
            parts.append(f"  - {t}")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Only recommend cite keys from local refs.bib")
    parts.append("  - If no candidate found, user must add references manually")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Refine citation position suggestions. Be concise.",
        f"Suggestions:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Refinement:\n{llm_result}"

    return _truncate(result, MAX_RELATED_WORK_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# build_related_work_outline
# ---------------------------------------------------------------------------

def build_related_work_outline_logic(
    tex_path: str = "",
    bib_path: str = "",
    topics_hint: str = "",
    use_llm: bool = True,
) -> str:
    bib_path_resolved = _get_bib_path(bib_path)
    entries = _load_bib_entries(bib_path_resolved)

    groups = defaultdict(list)
    for entry in entries:
        topic, _ = _classify_entry(entry, topics_hint)
        groups[topic].append(entry)

    main_topics = [t for t in groups if t != "uncertain"]
    main_topics.sort(key=lambda t: -len(groups[t]))

    rw_text = _get_related_work_text(tex_path)
    main_tex = detect_main_tex_file()
    paper_context = ""
    if main_tex:
        try:
            text = read_latex_file_safe(main_tex, max_chars=5000)
            paper_context = strip_latex_comments(text)[:2000]
        except Exception:
            pass

    parts = ["Related Work Outline", ""]
    parts.append(f"Bib entries: {len(entries)}")
    parts.append(f"Detected topics: {len(main_topics)}")
    parts.append("")

    parts.append("Suggested structure:")
    section_num = 1

    sar_topics = [t for t in main_topics if "sar" in t.lower()]
    obb_topics = [t for t in main_topics if "oriented" in t.lower() or "rotated" in t.lower()]
    detr_topics = [t for t in main_topics if "detr" in t.lower() or "dino" in t.lower() or "transformer" in t.lower()]
    scatter_topics = [t for t in main_topics if "scatter" in t.lower() or "asc" in t.lower()]
    other_topics = [t for t in main_topics if t not in sar_topics + obb_topics + detr_topics + scatter_topics]

    def _write_section(title: str, topic_list: list[str], purpose: str):
        nonlocal section_num
        if not topic_list:
            return
        refs = []
        for t in topic_list:
            refs.extend(groups[t])
        ref_keys = list({r["key"] for r in refs})[:10]

        parts.append(f"{section_num}. {title}")
        parts.append(f"   Purpose: {purpose}")
        if ref_keys:
            parts.append(f"   Candidate local citations: {', '.join(ref_keys[:8])}")
        else:
            parts.append("   Candidate local citations: (none found — may need to add)")
        parts.append("")
        section_num += 1

    _write_section(
        "SAR object detection and interpretation",
        sar_topics,
        "Introduce SAR detection challenges, speckle noise, and existing SAR target detection methods.",
    )
    _write_section(
        "Oriented object detection in remote sensing",
        obb_topics,
        "Explain why rotated bounding boxes are important for aircraft/ship/vehicle targets.",
    )
    _write_section(
        "Query-based detectors and DINO-style methods",
        detr_topics,
        "Discuss DETR/DINO and query refinement mechanisms.",
    )
    _write_section(
        "Scattering center priors for SAR interpretation",
        scatter_topics,
        "Introduce physical scattering priors and how they motivate the proposed method.",
    )
    _write_section(
        "Other related work",
        other_topics,
        "Cover additional relevant topics such as small object detection, remote sensing, etc.",
    )

    parts.append("Suggested transition to proposed method:")
    parts.append("  - Existing OBB detectors focus on geometric localization, while SAR scattering")
    parts.append("    responses provide complementary physical cues. This motivates the proposed")
    parts.append("    scatter-aware query refinement mechanism.")
    parts.append("")
    parts.append("Cautions:")
    parts.append("  - Do not cite papers not present in refs.bib")
    parts.append("  - Confirm whether each candidate citation truly supports the sentence")
    parts.append("  - If a topic has no local refs, user must add them before writing")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Refine Related Work outline. Be concise.",
        f"Outline:\n{result[:3000]}\n\nPaper context:\n{paper_context[:1000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Refinement:\n{llm_result}"

    return _truncate(result, MAX_RELATED_WORK_OUTPUT_CHARS)
