import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from cheap_agent.cache import make_hash
from cheap_agent.cache_manager import ensure_cache_dir, get_disk_cache, set_disk_cache, write_json_cache_atomic
from cheap_agent.config import (
    CACHE_SCHEMA_VERSION,
    ENABLE_LLM_REBUTTAL_CHECK,
    ENABLE_REBUTTAL_CACHE,
    LLM_MODEL,
    MAX_COMMENT_CONTEXT_CHARS,
    MAX_OUTPUT_CHARS,
    MAX_REBUTTAL_OUTPUT_CHARS,
    MAX_RESPONSE_OUTLINES,
    MAX_RESPONSE_TEXT_CHARS,
    MAX_REVIEWER_COMMENTS,
    MAX_REVIEWER_COMMENTS_CHARS,
    PAPER_CACHE_DIR,
    PAPER_LLM_MAX_TOKENS,
    PAPER_LLM_TEMPERATURE,
    REBUTTAL_CACHE_TTL_SEC,
    WORKSPACE_ROOT,
)
from cheap_agent.parsers.latex_parser import (
    detect_main_tex_file,
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
    if not use_llm or not ENABLE_LLM_REBUTTAL_CHECK:
        return None
    try:
        from cheap_agent.llm_client import ask_llm
        return ask_llm(system_prompt, user_prompt, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
    except Exception as e:
        return f"[LLM Error] {e}"


def _read_text_safe(path: str, max_chars: int) -> str:
    try:
        resolve_safe_path(path)
        return read_latex_file_safe(path, max_chars=max_chars)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Concern type patterns
# ---------------------------------------------------------------------------

_CONCERN_PATTERNS = [
    ("novelty", re.compile(r"\b(novelty|novel|contribution|differentiat|prior work|existing work|newness)\b", re.IGNORECASE)),
    ("method_clarity", re.compile(r"\b(method|approach|framework|mechanism|unclear|confus|explain|description|formulation)\b", re.IGNORECASE)),
    ("experiment", re.compile(r"\b(experiment|result|evaluation|benchmark|comparison|performance|quantitative)\b", re.IGNORECASE)),
    ("ablation", re.compile(r"\b(ablation|ablat|component|module|contribution of|effect of|study)\b", re.IGNORECASE)),
    ("comparison", re.compile(r"\b(comparison|compare|baseline|state.of.the.art|sota|competitor|versus)\b", re.IGNORECASE)),
    ("metric", re.compile(r"\b(metric|measure|accuracy|precision|recall|map|ap50|fps|latency|parameter)\b", re.IGNORECASE)),
    ("citation", re.compile(r"\b(citation|cite|reference|bibliography|prior work|missing ref)\b", re.IGNORECASE)),
    ("related_work", re.compile(r"\b(related work|literature|survey|prior|previous work|reference)\b", re.IGNORECASE)),
    ("writing", re.compile(r"\b(writing|grammar|typo|english|language|clarity|readable|expression)\b", re.IGNORECASE)),
    ("figure_table", re.compile(r"\b(figure|fig|table|caption|visualization|illustration|plot|chart)\b", re.IGNORECASE)),
    ("equation", re.compile(r"\b(equation|eq|formula|notation|symbol|mathematical)\b", re.IGNORECASE)),
    ("runtime_efficiency", re.compile(r"\b(runtime|speed|efficiency|complexity|scalab|inference time|faster|slower)\b", re.IGNORECASE)),
    ("reproducibility", re.compile(r"\b(reproduc|replicate|code|implementation|detail|setting|hyperparameter)\b", re.IGNORECASE)),
    ("limitation", re.compile(r"\b(limitation|limit|weakness|failure|shortcoming|drawback|case.*fail)\b", re.IGNORECASE)),
    ("dataset", re.compile(r"\b(dataset|data set|benchmark|data quality|annotation|label)\b", re.IGNORECASE)),
    ("baseline", re.compile(r"\b(baseline|comparison method|competitor|existing method|fair comparison)\b", re.IGNORECASE)),
    ("theory", re.compile(r"\b(theory|theoretical|proof|convergence|complexity|bound|guarantee)\b", re.IGNORECASE)),
    ("response_tone", re.compile(r"\b(tone|polite|courtesy|response.*style|rebuttal)\b", re.IGNORECASE)),
    ("minor_typo", re.compile(r"\b(minor|typo|spelling|formatting|punctuation|layout)\b", re.IGNORECASE)),
]

_CONCERN_PATTERNS_ZH = [
    ("novelty", re.compile(r"(创新|新颖|贡献|区别|现有工作)")),
    ("method_clarity", re.compile(r"(方法|框架|机制|不清楚|描述|公式)")),
    ("experiment", re.compile(r"(实验|结果|评估|对比|性能)")),
    ("ablation", re.compile(r"(消融|模块|贡献|影响|分析)")),
    ("writing", re.compile(r"(写作|语法|语言|表述|清晰)")),
    ("figure_table", re.compile(r"(图|表|可视化|标注)")),
    ("limitation", re.compile(r"(局限|不足|缺点|问题)")),
]

_SEVERITY_HIGH = re.compile(r"\b(major|significant|critical|fundamental|serious|must|essential|important concern|weakness)\b", re.IGNORECASE)
_SEVERITY_LOW = re.compile(r"\b(minor|small|typo|formatting|cosmetic|suggestion|optional)\b", re.IGNORECASE)

_ACTION_PATTERNS = [
    ("clarify_text", re.compile(r"\b(clarify|explain|unclear|confus|elaborate|describe better)\b", re.IGNORECASE)),
    ("add_experiment", re.compile(r"\b(add.*experiment|more.*result|additional.*evaluat|conduct.*experiment)\b", re.IGNORECASE)),
    ("add_ablation", re.compile(r"\b(ablation|component.*study|module.*analysis|add.*study)\b", re.IGNORECASE)),
    ("add_comparison", re.compile(r"\b(compare|comparison|baseline|more.*method|include.*sota)\b", re.IGNORECASE)),
    ("add_citation", re.compile(r"\b(cite|citation|reference|add.*ref|missing.*ref)\b", re.IGNORECASE)),
    ("revise_figure", re.compile(r"\b(figure|fig|visualization|illustration|revise.*fig)\b", re.IGNORECASE)),
    ("revise_table", re.compile(r"\b(table|revise.*table|add.*table)\b", re.IGNORECASE)),
    ("revise_caption", re.compile(r"\b(caption|figure.*title|table.*title)\b", re.IGNORECASE)),
    ("revise_method", re.compile(r"\b(method|approach|framework|revise.*method)\b", re.IGNORECASE)),
    ("revise_introduction", re.compile(r"\b(introduction|intro|motivation|contribution)\b", re.IGNORECASE)),
    ("revise_related_work", re.compile(r"\b(related work|literature|prior work)\b", re.IGNORECASE)),
    ("revise_experiments", re.compile(r"\b(experiment|result|evaluation|revise.*experiment)\b", re.IGNORECASE)),
    ("add_limitation", re.compile(r"\b(limitation|limit|shortcoming|add.*limitation)\b", re.IGNORECASE)),
    ("fix_typo", re.compile(r"\b(typo|spelling|formatting|punctuation|minor.*fix)\b", re.IGNORECASE)),
    ("explain_no_change", re.compile(r"\b(no change|already|existing|we believe|disagree|not necessary)\b", re.IGNORECASE)),
]

_DEFENSIVE_PHRASES = [
    (r"\bthe reviewer (is|was) wrong\b", "high", "Avoid directly stating the reviewer is wrong"),
    (r"\bthe reviewer misunderstood\b", "high", "Use 'We apologize for the unclear description' instead"),
    (r"\bwe disagree\b", "medium", "Use 'We respectfully note that...' instead"),
    (r"\bobviously\b", "medium", "Remove; what is obvious to authors may not be to reviewers"),
    (r"\bclearly\b", "low", "Consider removing; may sound dismissive"),
    (r"\bas (we|everyone) know\b", "medium", "Remove; sounds dismissive of reviewer concern"),
    (r"\bit is (well|widely) known\b", "low", "Consider removing"),
    (r"\bthis (completely|totally|entirely) (solves|fixes|addresses)\b", "medium", "Soften: 'This helps address' or 'This partially addresses'"),
    (r"\bwe have already\b", "low", "Consider: 'We have revised' to sound more responsive"),
    (r"\bthis is not (a|our) (problem|issue|concern)\b", "high", "Avoid deflecting; acknowledge the concern"),
    (r"\bthanks.*but\b", "medium", "Avoid 'thanks but' pattern; sound more receptive"),
]


# ---------------------------------------------------------------------------
# parse_reviewer_comments
# ---------------------------------------------------------------------------

def _extract_reviewer_blocks(text: str) -> list[dict]:
    """Split text into reviewer blocks."""
    blocks = []
    current_reviewer = ""
    current_lines = []

    for line in text.split("\n"):
        reviewer_m = re.match(r"^(?:Reviewer\s*#?\s*(\d+)|审稿人\s*(\d+)|R(\d+))[:\s]", line, re.IGNORECASE)
        if reviewer_m:
            if current_reviewer or current_lines:
                blocks.append({"reviewer": current_reviewer or "Unknown", "text": "\n".join(current_lines)})
            num = reviewer_m.group(1) or reviewer_m.group(2) or reviewer_m.group(3)
            current_reviewer = f"Reviewer {num}"
            current_lines = []
        else:
            current_lines.append(line)

    if current_reviewer or current_lines:
        blocks.append({"reviewer": current_reviewer or "Unknown", "text": "\n".join(current_lines)})

    if not blocks:
        blocks.append({"reviewer": "Reviewer 1", "text": text})

    return blocks


def _extract_comments_from_block(block: dict) -> list[dict]:
    """Extract individual comments from a reviewer block."""
    text = block["text"]
    reviewer = block["reviewer"]
    comments = []

    patterns = [
        re.compile(r"^(?:Comment|意见|Comments?)\s*#?\s*(\d+)[:\s]", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^(?:Major|Minor|主要|次要)\s*(?:Comment|意见)s?\s*#?\s*(\d+)?[:\s]", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^(\d+)[\.\)]\s+", re.MULTILINE),
        re.compile(r"^R\d+[.-]C(\d+)[:\s]", re.IGNORECASE | re.MULTILINE),
    ]

    found = []
    for pat in patterns:
        for m in pat.finditer(text):
            pos = m.start()
            num = m.group(1) if m.lastindex else str(len(found) + 1)
            found.append((pos, num))

    if not found:
        comments.append({
            "reviewer": reviewer,
            "comment_id": f"{reviewer.replace(' ', '')}-C1",
            "text": text.strip()[:MAX_COMMENT_CONTEXT_CHARS],
        })
        return comments

    found.sort(key=lambda x: x[0])

    for i, (pos, num) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        comment_text = text[pos:end].strip()
        comment_text = re.sub(r"^(?:Comment|意见|Comments?)\s*#?\s*\d+[:\s]*", "", comment_text, flags=re.IGNORECASE).strip()
        comment_text = re.sub(r"^(?:Major|Minor|主要|次要)\s*(?:Comment|意见)s?\s*#?\s*\d*[:\s]*", "", comment_text, flags=re.IGNORECASE).strip()
        comment_text = re.sub(r"^\d+[\.\)]\s*", "", comment_text).strip()

        reviewer_num = re.search(r"\d+", reviewer)
        rid = reviewer_num.group(0) if reviewer_num else "X"
        comments.append({
            "reviewer": reviewer,
            "comment_id": f"R{rid}-C{num}",
            "text": comment_text[:MAX_COMMENT_CONTEXT_CHARS],
        })

    return comments[:MAX_REVIEWER_COMMENTS]


def _classify_comment(comment: dict) -> dict:
    """Add concern type, severity, and required action to a comment."""
    text = comment["text"]

    concern_types = []
    for ctype, pat in _CONCERN_PATTERNS + _CONCERN_PATTERNS_ZH:
        if pat.search(text):
            concern_types.append(ctype)
    if not concern_types:
        concern_types = ["other"]

    severity = "medium"
    if _SEVERITY_HIGH.search(text):
        severity = "high"
    elif _SEVERITY_LOW.search(text):
        severity = "low"

    actions = []
    for action, pat in _ACTION_PATTERNS:
        if pat.search(text):
            actions.append(action)
    if not actions:
        actions = ["clarify_text"]

    return {
        **comment,
        "concern_types": concern_types,
        "severity": severity,
        "required_actions": actions,
    }


def parse_reviewer_comments_logic(
    comments_text: str = "",
    comments_path: str = "",
    use_llm: bool = True,
) -> str:
    if comments_path:
        comments_text = _read_text_safe(comments_path, MAX_REVIEWER_COMMENTS_CHARS)
    if not comments_text:
        return "[Error] No reviewer comments provided. Set comments_text or comments_path."

    comments_text = comments_text[:MAX_REVIEWER_COMMENTS_CHARS]
    blocks = _extract_reviewer_blocks(comments_text)

    all_comments = []
    for block in blocks:
        all_comments.extend(_extract_comments_from_block(block))

    classified = [_classify_comment(c) for c in all_comments]

    parts = ["Parsed Reviewer Comments", ""]
    parts.append(f"Reviewers: {len(blocks)}")
    parts.append(f"Total comments: {len(classified)}")
    parts.append("")

    by_reviewer = defaultdict(list)
    for c in classified:
        by_reviewer[c["reviewer"]].append(c)

    for reviewer, comments in by_reviewer.items():
        parts.append(f"{reviewer}")
        for c in comments:
            parts.append(f"  Comment {c['comment_id']}")
            text_preview = c['text'][:150].replace('\n', ' ')
            parts.append(f"    Text: {text_preview}")
            parts.append(f"    Concern types: {', '.join(c['concern_types'])}")
            parts.append(f"    Severity: {c['severity']}")
            parts.append(f"    Required actions: {', '.join(c['required_actions'])}")
            parts.append("")
        parts.append("")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Refine reviewer comment parsing. Be concise.",
        f"Parsed comments:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Refinement:\n{llm_result}"

    return _truncate(result, MAX_REBUTTAL_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# group_reviewer_concerns
# ---------------------------------------------------------------------------

def group_reviewer_concerns_logic(
    comments_text: str = "",
    comments_path: str = "",
    use_llm: bool = True,
) -> str:
    if comments_path:
        comments_text = _read_text_safe(comments_path, MAX_REVIEWER_COMMENTS_CHARS)
    if not comments_text:
        return "[Error] No reviewer comments provided."

    comments_text = comments_text[:MAX_REVIEWER_COMMENTS_CHARS]
    blocks = _extract_reviewer_blocks(comments_text)
    all_comments = []
    for block in blocks:
        all_comments.extend(_extract_comments_from_block(block))
    classified = [_classify_comment(c) for c in all_comments]

    by_type = defaultdict(list)
    for c in classified:
        for ct in c["concern_types"]:
            by_type[ct].append(c)

    high_priority = [c for c in classified if c["severity"] == "high"]
    multi_reviewer = {}
    for ct, comments in by_type.items():
        reviewers = set(c["reviewer"] for c in comments)
        if len(reviewers) > 1:
            multi_reviewer[ct] = {"count": len(comments), "reviewers": list(reviewers), "comments": comments}

    parts = ["Reviewer Concern Groups", ""]
    parts.append(f"Total comments: {len(classified)}")
    parts.append(f"High severity: {len(high_priority)}")
    parts.append(f"Multi-reviewer concerns: {len(multi_reviewer)}")
    parts.append("")

    if high_priority:
        parts.append("High-priority concerns:")
        for i, c in enumerate(high_priority[:10], 1):
            parts.append(f"  {i}. {c['comment_id']}: {', '.join(c['concern_types'])}")
            parts.append(f"     Text: {c['text'][:100]}")
            parts.append(f"     Actions: {', '.join(c['required_actions'])}")
        parts.append("")

    if multi_reviewer:
        parts.append("Multi-reviewer concerns (likely most important):")
        for ct, info in multi_reviewer.items():
            parts.append(f"  - {ct}")
            parts.append(f"    Mentioned by: {', '.join(info['reviewers'])}")
            parts.append(f"    Comments: {', '.join(c['comment_id'] for c in info['comments'][:5])}")
        parts.append("")

    parts.append("Concern summary by type:")
    type_counts = Counter()
    for c in classified:
        for ct in c["concern_types"]:
            type_counts[ct] += 1
    for ct, count in type_counts.most_common():
        parts.append(f"  - {ct}: {count} comments")
    parts.append("")

    parts.append("Suggested response order:")
    priority_order = ["novelty", "method_clarity", "experiment", "ablation", "comparison",
                       "related_work", "citation", "dataset", "baseline", "runtime_efficiency",
                       "reproducibility", "figure_table", "writing", "minor_typo"]
    idx = 1
    for ct in priority_order:
        if ct in type_counts:
            parts.append(f"  {idx}. {ct} ({type_counts[ct]} comments)")
            idx += 1
    for ct, count in type_counts.most_common():
        if ct not in priority_order:
            parts.append(f"  {idx}. {ct} ({count} comments)")
            idx += 1

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Refine reviewer concern grouping. Be concise.",
        f"Groups:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Refinement:\n{llm_result}"

    return _truncate(result, MAX_REBUTTAL_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# map_comments_to_revisions
# ---------------------------------------------------------------------------

_SECTION_MAP = {
    "novelty": ["Introduction", "Method"],
    "method_clarity": ["Method"],
    "experiment": ["Experiments"],
    "ablation": ["Experiments / Ablation Study"],
    "comparison": ["Experiments / Comparison"],
    "metric": ["Experiments / Metrics"],
    "citation": ["References", "Related Work"],
    "related_work": ["Related Work"],
    "writing": ["Throughout manuscript"],
    "figure_table": ["Figures / Tables"],
    "equation": ["Equations"],
    "runtime_efficiency": ["Experiments / Efficiency"],
    "reproducibility": ["Experiments / Implementation Details"],
    "limitation": ["Conclusion / Limitations"],
    "dataset": ["Experiments / Dataset"],
    "baseline": ["Experiments / Baselines"],
    "theory": ["Method / Theory"],
    "minor_typo": ["Throughout manuscript"],
}


def map_comments_to_revisions_logic(
    comments_text: str = "",
    comments_path: str = "",
    tex_path: str = "",
    use_llm: bool = True,
) -> str:
    if comments_path:
        comments_text = _read_text_safe(comments_path, MAX_REVIEWER_COMMENTS_CHARS)
    if not comments_text:
        return "[Error] No reviewer comments provided."

    comments_text = comments_text[:MAX_REVIEWER_COMMENTS_CHARS]
    blocks = _extract_reviewer_blocks(comments_text)
    all_comments = []
    for block in blocks:
        all_comments.extend(_extract_comments_from_block(block))
    classified = [_classify_comment(c) for c in all_comments]

    parts = ["Comment-to-Revision Map", ""]
    parts.append(f"Comments mapped: {len(classified)}")
    parts.append("")

    for c in classified[:MAX_RESPONSE_OUTLINES]:
        parts.append(f"{c['comment_id']}")
        parts.append(f"  Reviewer concern: {c['text'][:150]}")

        sections = set()
        for ct in c["concern_types"]:
            sections.update(_SECTION_MAP.get(ct, ["Other"]))

        parts.append(f"  Suggested revision targets:")
        for s in sorted(sections):
            parts.append(f"    - {s}")

        evidence = []
        if "experiment" in c["concern_types"] or "ablation" in c["concern_types"]:
            evidence.append("Main comparison table")
            evidence.append("Ablation table")
        if "figure_table" in c["concern_types"]:
            evidence.append("Relevant figure/table")
        if "citation" in c["concern_types"] or "related_work" in c["concern_types"]:
            evidence.append("Updated references")
        if evidence:
            parts.append(f"  Suggested evidence to cite:")
            for e in evidence:
                parts.append(f"    - {e}")

        parts.append(f"  Response should mention:")
        parts.append(f"    - What was clarified or revised")
        parts.append(f"    - Where it was revised (section/table/figure)")
        parts.append(f"    - Why the revision addresses the concern")

        status = "needs revision" if c["severity"] in ("high", "medium") else "minor fix"
        parts.append(f"  Status: {status}")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Do not claim modifications that are not actually made")
    parts.append("  - Always point to specific manuscript locations")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Refine comment-to-revision mapping. Be concise.",
        f"Mappings:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Refinement:\n{llm_result}"

    return _truncate(result, MAX_REBUTTAL_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_response_completeness
# ---------------------------------------------------------------------------

def check_response_completeness_logic(
    comments_text: str = "",
    response_text: str = "",
    comments_path: str = "",
    response_path: str = "",
    tex_path: str = "",
    use_llm: bool = True,
) -> str:
    if comments_path:
        comments_text = _read_text_safe(comments_path, MAX_REVIEWER_COMMENTS_CHARS)
    if response_path:
        response_text = _read_text_safe(response_path, MAX_RESPONSE_TEXT_CHARS)

    if not comments_text:
        return "[Error] No reviewer comments provided."
    if not response_text:
        return "[Error] No response text provided."

    comments_text = comments_text[:MAX_REVIEWER_COMMENTS_CHARS]
    response_text = response_text[:MAX_RESPONSE_TEXT_CHARS]

    blocks = _extract_reviewer_blocks(comments_text)
    all_comments = []
    for block in blocks:
        all_comments.extend(_extract_comments_from_block(block))
    classified = [_classify_comment(c) for c in all_comments]

    response_lower = response_text.lower()

    results = []
    for c in classified:
        cid = c["comment_id"]
        cid_lower = cid.lower()
        cid_num = re.search(r"C(\d+)", cid)
        cid_short = f"c{cid_num.group(1)}" if cid_num else ""

        has_response = (
            cid_lower in response_lower
            or cid_short in response_lower
            or c["text"][:30].lower() in response_lower
        )

        has_location = bool(re.search(r"(section|table|figure|fig|tab|eq|appendix|page)", response_lower))
        has_evidence = bool(re.search(r"(table|figure|fig|tab|ablation|experiment|result|visualization)", response_lower))
        has_thanks = bool(re.search(r"(thank|appreciate|grateful|we agree|good point|valuable)", response_lower))

        if not has_response:
            status = "missing"
        elif not has_location and not has_evidence:
            status = "partial"
        else:
            status = "addressed"

        results.append({
            "comment": c,
            "has_response": has_response,
            "has_location": has_location,
            "has_evidence": has_evidence,
            "has_thanks": has_thanks,
            "status": status,
        })

    addressed = sum(1 for r in results if r["status"] == "addressed")
    partial = sum(1 for r in results if r["status"] == "partial")
    missing = sum(1 for r in results if r["status"] == "missing")

    parts = ["Response Completeness Check", ""]
    parts.append(f"Summary:")
    parts.append(f"  - Reviewer comments parsed: {len(classified)}")
    parts.append(f"  - Fully addressed: {addressed}")
    parts.append(f"  - Partially addressed: {partial}")
    parts.append(f"  - Missing responses: {missing}")
    parts.append("")

    if missing > 0:
        parts.append("Missing responses:")
        for r in results:
            if r["status"] == "missing":
                parts.append(f"  {r['comment']['comment_id']}: {r['comment']['text'][:100]}")
                parts.append(f"    Severity: {r['comment']['severity']}")
        parts.append("")

    if partial > 0:
        parts.append("Partial responses:")
        for r in results:
            if r["status"] == "partial":
                parts.append(f"  {r['comment']['comment_id']}")
                parts.append(f"    Problem: Response found but missing specific location or evidence")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Add specific section/table/figure references to each response")
    parts.append("  - Do not claim modifications that are not verified in the manuscript")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Check response completeness. Be concise.",
        f"Completeness check:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Analysis:\n{llm_result}"

    return _truncate(result, MAX_REBUTTAL_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# review_response_tone
# ---------------------------------------------------------------------------

def review_response_tone_logic(
    response_text: str = "",
    response_path: str = "",
    use_llm: bool = True,
) -> str:
    if response_path:
        response_text = _read_text_safe(response_path, MAX_RESPONSE_TEXT_CHARS)
    if not response_text:
        return "[Error] No response text provided."

    response_text = response_text[:MAX_RESPONSE_TEXT_CHARS]
    issues = []

    for pattern, severity, suggestion in _DEFENSIVE_PHRASES:
        for m in re.finditer(pattern, response_text, re.IGNORECASE):
            start = max(0, m.start() - 30)
            end = min(len(response_text), m.end() + 30)
            context = response_text[start:end].strip()
            issues.append({
                "type": "defensive/inappropriate phrasing",
                "text": m.group(0),
                "context": context,
                "severity": severity,
                "suggestion": suggestion,
            })

    thanks_count = len(re.findall(r"\b(thank|appreciate|grateful)\b", response_text, re.IGNORECASE))
    if thanks_count == 0:
        issues.append({
            "type": "missing courtesy",
            "text": "",
            "context": "",
            "severity": "low",
            "suggestion": "Consider thanking the reviewer at the beginning of each response",
        })

    very_short = [s for s in response_text.split("\n\n") if 0 < len(s.strip()) < 50 and not s.strip().startswith("#")]
    for s in very_short[:3]:
        issues.append({
            "type": "possibly too brief",
            "text": s.strip()[:80],
            "context": "",
            "severity": "low",
            "suggestion": "Consider expanding with specific revision details",
        })

    severity_count = Counter(i["severity"] for i in issues)
    if severity_count.get("high", 0) > 0:
        overall = "needs revision"
    elif severity_count.get("medium", 0) > 2:
        overall = "needs revision"
    elif issues:
        overall = "acceptable"
    else:
        overall = "professional"

    parts = ["Response Tone Review", ""]
    parts.append(f"Overall tone: {overall}")
    parts.append(f"Issues found: {len(issues)}")
    parts.append("")

    if issues:
        parts.append("Issues:")
        for i, issue in enumerate(issues[:20], 1):
            parts.append(f"{i}. {issue['type']}")
            if issue["text"]:
                parts.append(f"   Text: \"{issue['text']}\"")
            if issue["context"]:
                parts.append(f"   Context: \"{issue['context']}\"")
            parts.append(f"   Severity: {issue['severity']}")
            parts.append(f"   Suggestion: {issue['suggestion']}")
        parts.append("")

    parts.append("Suggested response style:")
    parts.append("  - Thank the reviewer for each comment")
    parts.append("  - Acknowledge the concern before explaining changes")
    parts.append("  - State what was revised with specific locations")
    parts.append("  - Provide evidence (table/figure/section) when possible")
    parts.append("  - Use moderate language; avoid overclaiming")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Review response tone. Be concise.",
        f"Tone review:\n{result[:2000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Review:\n{llm_result}"

    return _truncate(result, MAX_REBUTTAL_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# draft_response_outline
# ---------------------------------------------------------------------------

def draft_response_outline_logic(
    comments_text: str = "",
    comments_path: str = "",
    tex_path: str = "",
    use_llm: bool = True,
) -> str:
    if comments_path:
        comments_text = _read_text_safe(comments_path, MAX_REVIEWER_COMMENTS_CHARS)
    if not comments_text:
        return "[Error] No reviewer comments provided."

    comments_text = comments_text[:MAX_REVIEWER_COMMENTS_CHARS]
    blocks = _extract_reviewer_blocks(comments_text)
    all_comments = []
    for block in blocks:
        all_comments.extend(_extract_comments_from_block(block))
    classified = [_classify_comment(c) for c in all_comments]

    parts = ["Response Outline", ""]
    parts.append(f"Comments to address: {len(classified)}")
    parts.append("")

    for c in classified[:MAX_RESPONSE_OUTLINES]:
        sections = set()
        for ct in c["concern_types"]:
            sections.update(_SECTION_MAP.get(ct, ["Other"]))

        evidence = []
        if "experiment" in c["concern_types"] or "ablation" in c["concern_types"]:
            evidence.append("comparison table")
            evidence.append("ablation table")
        if "figure_table" in c["concern_types"]:
            evidence.append("relevant figure/table")
        if "citation" in c["concern_types"]:
            evidence.append("updated references")

        parts.append(f"Response Outline for {c['comment_id']}")
        parts.append(f"  Reviewer concern: {c['text'][:150]}")
        parts.append(f"  Concern type: {', '.join(c['concern_types'])}")
        parts.append(f"  Severity: {c['severity']}")
        parts.append("")
        parts.append("  Suggested response structure:")
        parts.append("    1. Thank the reviewer for the comment")
        parts.append("    2. Acknowledge the concern")
        parts.append("    3. State planned or completed revision (do not claim completed unless verified)")
        parts.append("    4. Point to target manuscript location")
        if evidence:
            parts.append(f"    5. Mention supporting evidence: {', '.join(evidence)}")
        parts.append("    6. Close with how the revision addresses the concern")
        parts.append("")
        parts.append("  Needed manuscript changes:")
        for s in sorted(sections):
            parts.append(f"    - {s}")
        if evidence:
            parts.append("  Evidence to cite in response:")
            for e in evidence:
                parts.append(f"    - {e}")
        parts.append("")

        risk = "high" if c["severity"] == "high" else ("medium" if c["severity"] == "medium" else "low")
        parts.append(f"  Risk: {risk}")
        parts.append("")

    parts.append("General cautions:")
    parts.append("  - Do not claim new experiments unless they are actually present")
    parts.append("  - Do not cite papers not in refs.bib")
    parts.append("  - Always point to specific manuscript locations")
    parts.append("  - Use moderate language")

    result = "\n".join(parts)

    llm_result = _call_llm(
        "Refine response outlines. Be concise.",
        f"Outlines:\n{result[:3000]}",
        use_llm,
    )
    if llm_result:
        result += f"\n\nLLM Refinement:\n{llm_result}"

    return _truncate(result, MAX_REBUTTAL_OUTPUT_CHARS)
