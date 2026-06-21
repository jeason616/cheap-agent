import re
from collections import defaultdict

from cheap_agent.tools._common import truncate
from cheap_agent.config import (
    ENABLE_LLM_EXPERIMENT_CHECK,
    MAX_EXPERIMENT_OUTPUT_CHARS,
    MAX_TABLE_FILES,
    MAX_TABLE_RAW_CHARS,
    PAPER_LLM_MAX_TOKENS,
    PAPER_LLM_TEMPERATURE,
)
from cheap_agent.parsers.latex_parser import (
    detect_main_tex_file,
    read_latex_file_safe,
    resolve_latex_project_files,
    strip_latex_comments,
)
from cheap_agent.workspace import resolve_safe_path


# ---------------------------------------------------------------------------
# Enhanced table parsing
# ---------------------------------------------------------------------------

_RE_TAB_BEGIN = re.compile(r"\\begin\{(table\*?)\}")
_RE_TAB_END = re.compile(r"\\end\{(table\*?)\}")
_RE_TABULAR_BEGIN = re.compile(r"\\begin\{(tabular|tabularx|longtable)\*?\}(\{[^}]*\})?")
_RE_TABULAR_END = re.compile(r"\\end\{(tabular|tabularx|longtable)\*?\}")
_RE_CAPTION = re.compile(r"\\caption\{([^}]*)\}")
_RE_LABEL = re.compile(r"\\label\{([^}]*)\}")
_RE_TOPRULE = re.compile(r"\\toprule")
_RE_MIDRULE = re.compile(r"\\midrule")
_RE_BOTTOMRULE = re.compile(r"\\bottomrule")
_RE_HLINE = re.compile(r"\\hline")
_RE_TEXTBF = re.compile(r"\\textbf\{([^}]*)\}")
_RE_UNDERLINE = re.compile(r"\\underline\{([^}]*)\}")
_RE_EMPH = re.compile(r"\\emph\{([^}]*)\}")
_RE_MATH = re.compile(r"\$([^$]*)\$")
_RE_PERCENT = re.compile(r"\\%")
_RE_PM = re.compile(r"\\pm")
_RE_CMDS = re.compile(r"\\[a-zA-Z]+\{([^}]*)\}")
_RE_AMP = re.compile(r"(?<!\\)&")
_RE_NEWLINE = re.compile(r"\\\\")
_RE_NOTES = re.compile(r"\\note\{([^}]*)\}")


def _clean_cell(cell: str) -> str:
    cell = cell.strip()
    cell = _RE_PERCENT.sub("%", cell)
    cell = _RE_MATH.sub(r"\1", cell)
    cell = re.sub(r"\\[a-zA-Z]+", "", cell)
    cell = cell.strip(" {}")
    return cell


def _is_bold(cell: str) -> bool:
    return bool(_RE_TEXTBF.search(cell))


def _is_underline(cell: str) -> bool:
    return bool(_RE_UNDERLINE.search(cell))


def _extract_numeric(cell: str) -> str | None:
    cleaned = _clean_cell(cell)
    cleaned = cleaned.replace("%", "").replace("\\", "").strip()
    m = re.search(r"[-+]?\d*\.?\d+", cleaned)
    return m.group(0) if m else None


def _parse_tabular_rows(tabular_text: str) -> list[list[str]]:
    rows = []
    current_row = []
    for line in tabular_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("%"):
            continue
        if _RE_TOPRULE.match(line) or _RE_MIDRULE.match(line) or _RE_BOTTOMRULE.match(line) or _RE_HLINE.match(line):
            if current_row:
                rows.append(current_row)
                current_row = []
            continue
        if "\\multicolumn" in line or "\\multirow" in line:
            pass
        cells = _RE_AMP.split(line)
        for cell in cells:
            cell = cell.strip()
            if cell and cell != "\\\\":
                current_row.append(cell)
        if "\\\\" in line or "\\tabularnewline" in line:
            if current_row:
                rows.append(current_row)
                current_row = []
    if current_row:
        rows.append(current_row)
    return rows


def _parse_single_table(table_text: str, file_path: str, table_index: int) -> dict | None:
    caption_m = _RE_CAPTION.search(table_text)
    label_m = _RE_LABEL.search(table_text)
    env_m = _RE_TAB_BEGIN.search(table_text)

    caption = caption_m.group(1).strip() if caption_m else ""
    label = label_m.group(1).strip() if label_m else ""
    env_type = env_m.group(1) if env_m else "table"

    tabular_m = _RE_TABULAR_BEGIN.search(table_text)
    tabular_type = "unknown"
    if tabular_m:
        tabular_type = tabular_m.group(1)

    tabular_text = ""
    if tabular_m:
        start = tabular_m.end()
        end_m = _RE_TABULAR_END.search(table_text[start:])
        if end_m:
            tabular_text = table_text[start:start + end_m.start()]
        else:
            tabular_text = table_text[start:]

    rows = _parse_tabular_rows(tabular_text)

    column_headers = []
    row_entries = []
    bold_values = []
    underline_values = []
    numeric_values = []

    if rows:
        column_headers = [_clean_cell(c) for c in rows[0]]
        for row in rows[1:]:
            row_name = _clean_cell(row[0]) if row else ""
            row_data = {}
            for j, cell in enumerate(row[1:], 1):
                col_name = column_headers[j] if j < len(column_headers) else f"col{j}"
                row_data[col_name] = _clean_cell(cell)
                if _is_bold(cell):
                    bold_values.append({"row": row_name, "col": col_name, "value": _clean_cell(cell)})
                if _is_underline(cell):
                    underline_values.append({"row": row_name, "col": col_name, "value": _clean_cell(cell)})
                num = _extract_numeric(cell)
                if num:
                    numeric_values.append({"row": row_name, "col": col_name, "value": num})
            row_entries.append({"row_name": row_name, "data": row_data})

    notes = _RE_NOTES.findall(table_text)

    return {
        "table_index": table_index,
        "source_file": file_path,
        "caption": caption,
        "label": label,
        "environment": env_type,
        "tabular_type": tabular_type,
        "column_headers": column_headers,
        "row_entries": row_entries,
        "bold_values": bold_values,
        "underline_values": underline_values,
        "numeric_values": numeric_values,
        "notes": notes,
        "raw_latex": table_text[:MAX_TABLE_RAW_CHARS],
    }


def parse_latex_tables_detailed(
    tex_path: str = "",
    include_raw: bool = False,
    max_tables: int = 20,
) -> str:
    if tex_path:
        try:
            target = resolve_safe_path(tex_path)
            if not target.is_file():
                return f"[Error] File not found: {tex_path}"
            files_to_scan = [tex_path]
        except (PermissionError, ValueError) as e:
            return f"[Error] {e}"
    else:
        main_tex = detect_main_tex_file()
        if not main_tex:
            return "[Error] No main .tex file found. Set tex_path explicitly."
        files_to_scan = resolve_latex_project_files(main_tex)

    files_to_scan = files_to_scan[:MAX_TABLE_FILES]
    all_tables = []
    table_index = 0

    for f in files_to_scan:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f)
            text = strip_latex_comments(text)

            pos = 0
            while pos < len(text) and table_index < max_tables:
                m = _RE_TAB_BEGIN.search(text, pos)
                if not m:
                    break
                start = m.start()
                end_m = _RE_TAB_END.search(text, m.end())
                if not end_m:
                    break
                table_text = text[start:end_m.end()]
                table = _parse_single_table(table_text, f, table_index + 1)
                if table:
                    all_tables.append(table)
                    table_index += 1
                pos = end_m.end()
        except Exception:
            continue

    if not all_tables:
        return "No LaTeX tables found in the project."

    parts = ["Parsed LaTeX Tables", ""]

    for table in all_tables:
        parts.append(f"Table {table['table_index']}")
        parts.append(f"  Source: {table['source_file']}")
        parts.append(f"  Label: {table['label'] or '(none)'}")
        parts.append(f"  Caption: {table['caption'] or '(none)'}")
        parts.append(f"  Columns: {', '.join(table['column_headers']) if table['column_headers'] else '(none)'}")

        if table["row_entries"]:
            parts.append("  Rows:")
            for entry in table["row_entries"][:15]:
                row_str = f"    - {entry['row_name']}: "
                cell_parts = []
                for col, val in entry["data"].items():
                    marker = ""
                    for bv in table["bold_values"]:
                        if bv["row"] == entry["row_name"] and bv["col"] == col:
                            marker = " [bold]"
                            break
                    cell_parts.append(f"{col}={val}{marker}")
                row_str += ", ".join(cell_parts[:6])
                parts.append(row_str)

        if table["bold_values"]:
            parts.append(f"  Bold values: {len(table['bold_values'])} (likely best results)")

        if table["notes"]:
            parts.append(f"  Notes: {'; '.join(table['notes'][:3])}")

        if include_raw:
            parts.append(f"  Raw LaTeX: {table['raw_latex'][:500]}...")

        parts.append("")

    result = "\n".join(parts)

    return truncate(result, MAX_EXPERIMENT_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# extract_experiment_claims
# ---------------------------------------------------------------------------

_CLAIM_PATTERNS_EN = [
    (r"\bbest\b", "best_performance", "strong"),
    (r"\bstate[- ]of[- ]the[- ]art\b", "best_performance", "strong"),
    (r"\boutperform\b", "outperform_baseline", "strong"),
    (r"\bsuperior\b", "outperform_baseline", "strong"),
    (r"\bimprove\b", "ablation_gain", "moderate"),
    (r"\bimprovement\b", "ablation_gain", "moderate"),
    (r"\bgain\b", "ablation_gain", "moderate"),
    (r"\bhigher\b", "ablation_gain", "weak"),
    (r"\blower\b", "ablation_gain", "weak"),
    (r"\breduce\b", "efficiency_claim", "moderate"),
    (r"\breduction\b", "efficiency_claim", "moderate"),
    (r"\bsignificant\b", "statistical_significance_claim", "moderate"),
    (r"\bconsistently\b", "robustness_claim", "moderate"),
    (r"\brobust\b", "robustness_claim", "moderate"),
    (r"\beffective\b", "robustness_claim", "moderate"),
    (r"\befficient\b", "efficiency_claim", "moderate"),
    (r"\breal[- ]time\b", "real_time_claim", "moderate"),
    (r"\bcompetitive\b", "best_performance", "weak"),
    (r"\bablation\b", "ablation_gain", "moderate"),
    (r"\bdemonstrates\b", "robustness_claim", "weak"),
    (r"\bvalidates\b", "robustness_claim", "weak"),
]

_CLAIM_PATTERNS_ZH = [
    (r"最优", "best_performance", "strong"),
    (r"优于", "outperform_baseline", "strong"),
    (r"提升", "ablation_gain", "moderate"),
    (r"降低", "efficiency_claim", "moderate"),
    (r"有效", "robustness_claim", "moderate"),
    (r"鲁棒", "robustness_claim", "moderate"),
    (r"实时", "real_time_claim", "moderate"),
    (r"消融实验", "ablation_gain", "moderate"),
    (r"验证了", "robustness_claim", "weak"),
    (r"证明了", "robustness_claim", "weak"),
    (r"明显", "ablation_gain", "moderate"),
    (r"显著", "statistical_significance_claim", "moderate"),
]

_ALL_CLAIM_PATTERNS = [(re.compile(p, re.IGNORECASE), t, s) for p, t, s in _CLAIM_PATTERNS_EN + _CLAIM_PATTERNS_ZH]

_RE_TABLE_REF = re.compile(r"(?:Table|Tab\.?)\s*\\ref\{([^}]+)\}", re.IGNORECASE)
_RE_FIG_REF = re.compile(r"(?:Fig(?:ure)?\.?)\s*\\ref\{([^}]+)\}", re.IGNORECASE)
_RE_METRIC = re.compile(r"\b(mAP|AP50|AP75|AP[_{@]50|Precision|Recall|F1|Pd|Pr|FAR|FP|FPS|Latency|Params|GFLOPs|IoU|Accuracy|OA|AA|Kappa)\b", re.IGNORECASE)
_RE_METHOD = re.compile(r"\b(Ours|Baseline|Proposed|Our method|The proposed)\b", re.IGNORECASE)


def extract_experiment_claims_logic(
    tex_path: str = "",
    use_llm: bool = True,
    max_claims: int = 50,
) -> str:
    if tex_path:
        try:
            target = resolve_safe_path(tex_path)
            if not target.is_file():
                return f"[Error] File not found: {tex_path}"
            files_to_scan = [tex_path]
        except (PermissionError, ValueError) as e:
            return f"[Error] {e}"
    else:
        main_tex = detect_main_tex_file()
        if not main_tex:
            return "[Error] No main .tex file found."
        files_to_scan = resolve_latex_project_files(main_tex)

    claims = []
    claim_id = 0

    for f in files_to_scan:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f)
            lines = text.split("\n")
            for i, line in enumerate(lines, 1):
                if len(claims) >= max_claims:
                    break
                stripped = line.strip()
                if not stripped or stripped.startswith("%"):
                    continue
                for pattern, claim_type, strength in _ALL_CLAIM_PATTERNS:
                    if pattern.search(stripped):
                        claim_id += 1
                        table_refs = _RE_TABLE_REF.findall(line)
                        fig_refs = _RE_FIG_REF.findall(line)
                        metrics = _RE_METRIC.findall(line)
                        methods = _RE_METHOD.findall(line)

                        evidence_parts = []
                        if table_refs:
                            evidence_parts.append(f"Table \\ref{{{table_refs[0]}}}")
                        if fig_refs:
                            evidence_parts.append(f"Fig \\ref{{{fig_refs[0]}}}")

                        needs_evidence = strength == "strong" and not evidence_parts

                        claims.append({
                            "claim_id": claim_id,
                            "source_file": f,
                            "line": i,
                            "claim_text": stripped[:200],
                            "claim_type": claim_type,
                            "strength": strength,
                            "mentioned_metric": metrics[0] if metrics else "not specified",
                            "mentioned_method": methods[0] if methods else "not specified",
                            "mentioned_table_or_figure": "; ".join(evidence_parts) if evidence_parts else "not explicitly referenced",
                            "needs_evidence": needs_evidence,
                        })
                        break
        except Exception:
            continue

    if not claims:
        return "No experiment claims detected."

    parts = ["Experiment Claims", ""]
    parts.append(f"Claims extracted: {len(claims)}")
    parts.append("")

    for claim in claims[:max_claims]:
        parts.append(f"Claim {claim['claim_id']}")
        parts.append(f"  Source: {claim['source_file']}:{claim['line']}")
        parts.append(f"  Type: {claim['claim_type']}")
        parts.append(f"  Strength: {claim['strength']}")
        parts.append(f"  Text: \"{claim['claim_text'][:100]}\"")
        parts.append(f"  Mentioned metric: {claim['mentioned_metric']}")
        parts.append(f"  Mentioned evidence: {claim['mentioned_table_or_figure']}")
        parts.append(f"  Needs evidence: {claim['needs_evidence']}")
        parts.append("")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_EXPERIMENT_CHECK:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.paper import EXPERIMENT_CLAIM_EXTRACTION_SYSTEM_PROMPT
            llm_input = f"Experiment claims:\n{result[:3000]}"
            llm_result = ask_llm(EXPERIMENT_CLAIM_EXTRACTION_SYSTEM_PROMPT, llm_input, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_EXPERIMENT_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_result_claim_consistency
# ---------------------------------------------------------------------------

def check_result_claim_consistency_logic(
    tex_path: str = "",
    use_llm: bool = True,
    max_claims: int = 50,
) -> str:
    tables_result = parse_latex_tables_detailed(tex_path=tex_path)
    claims_result = extract_experiment_claims_logic(tex_path=tex_path, use_llm=False, max_claims=max_claims)

    if claims_result.startswith("No experiment claims"):
        return "No experiment claims found to check."

    tables_data = _extract_table_data_from_result(tables_result)
    claims_data = _extract_claims_from_result(claims_result)

    issues = []
    claims_checked = len(claims_data)
    claims_lacking = 0

    for claim in claims_data:
        claim_text = claim.get("text", "")
        claim_strength = claim.get("strength", "weak")
        claim_metric = claim.get("metric", "")
        claim_evidence = claim.get("evidence", "")

        if claim_strength == "strong" and "not explicitly referenced" in claim_evidence:
            claims_lacking += 1
            issues.append({
                "claim": claim_text[:100],
                "source": claim.get("source", ""),
                "problem": "Strong claim without explicit table/figure reference",
                "severity": "medium",
                "suggestion": "Add explicit table/figure reference or soften the claim",
            })

        if "best" in claim_text.lower() and claim_metric:
            for table in tables_data:
                if table.get("bold_values"):
                    for bv in table["bold_values"]:
                        if claim_metric.lower() in bv.get("col", "").lower():
                            if bv.get("row", "").lower() not in ["ours", "proposed", "baseline"]:
                                issues.append({
                                    "claim": claim_text[:100],
                                    "source": claim.get("source", ""),
                                    "problem": f"Claim says 'best' on {claim_metric}, but another method may also be bold",
                                    "severity": "medium",
                                    "suggestion": "Verify the best-value marker is correct",
                                })

        if "significant" in claim_text.lower() or "显著" in claim_text:
            if "statistical" not in claim_text.lower() and "p-value" not in claim_text.lower():
                issues.append({
                    "claim": claim_text[:100],
                    "source": claim.get("source", ""),
                    "problem": "Claim uses 'significant' without statistical evidence",
                    "severity": "low",
                    "suggestion": "Use 'consistent' or provide statistical evidence (p-value, variance)",
                })

    parts = ["Result-Claim Consistency Check", ""]
    parts.append("Summary:")
    parts.append(f"  - Claims checked: {claims_checked}")
    parts.append(f"  - Potential inconsistencies: {len(issues)}")
    parts.append(f"  - Claims lacking explicit evidence: {claims_lacking}")
    parts.append("")

    if issues:
        for i, issue in enumerate(issues[:10], 1):
            parts.append(f"Issue {i}")
            parts.append(f"  Claim: \"{issue['claim']}\"")
            parts.append(f"  Source: {issue['source']}")
            parts.append(f"  Problem: {issue['problem']}")
            parts.append(f"  Severity: {issue['severity']}")
            parts.append(f"  Suggestion: {issue['suggestion']}")
            parts.append("")
    else:
        parts.append("No significant inconsistencies found.")
        parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Check Introduction contribution claims against Experiments tables")
    parts.append("  - Consider softening claims without direct evidence")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_EXPERIMENT_CHECK:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.paper import RESULT_CLAIM_CONSISTENCY_SYSTEM_PROMPT
            llm_input = f"Consistency check:\n{result[:3000]}"
            llm_result = ask_llm(RESULT_CLAIM_CONSISTENCY_SYSTEM_PROMPT, llm_input, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_EXPERIMENT_OUTPUT_CHARS)


def _extract_table_data_from_result(result: str) -> list[dict]:
    tables = []
    current_table = {}
    for line in result.split("\n"):
        if line.startswith("Table "):
            if current_table:
                tables.append(current_table)
            current_table = {"bold_values": []}
        if "bold" in line.lower():
            current_table.setdefault("bold_values", []).append({"row": "", "col": "", "value": ""})
    if current_table:
        tables.append(current_table)
    return tables


def _extract_claims_from_result(result: str) -> list[dict]:
    claims = []
    current_claim = {}
    for line in result.split("\n"):
        if line.startswith("Claim "):
            if current_claim:
                claims.append(current_claim)
            current_claim = {}
        if "Text:" in line:
            current_claim["text"] = line.split("Text:")[1].strip().strip('"')
        if "Strength:" in line:
            current_claim["strength"] = line.split("Strength:")[1].strip()
        if "Mentioned metric:" in line:
            current_claim["metric"] = line.split("Mentioned metric:")[1].strip()
        if "Mentioned evidence:" in line:
            current_claim["evidence"] = line.split("Mentioned evidence:")[1].strip()
        if "Source:" in line:
            current_claim["source"] = line.split("Source:")[1].strip()
    if current_claim:
        claims.append(current_claim)
    return claims


# ---------------------------------------------------------------------------
# check_ablation_logic
# ---------------------------------------------------------------------------

_ABLATION_KEYWORDS = [
    "ablation", "消融", "component analysis", "module analysis",
    "effectiveness", "contribution",
]

_MODULE_KEYWORDS_EN = [
    "SCD", "scatter descriptor", "soft top-k", "query refinement",
    "attention", "fusion", "loss", "backbone", "decoder", "encoder",
    "ASC", "DINO", "FPN", "neck", "head",
]

_MODULE_KEYWORDS_ZH = [
    "散射描述符", "软 Top-K", "查询优化", "注意力", "融合模块",
    "损失函数", "主干网络", "解码器", "编码器",
]


def check_ablation_logic_logic(
    tex_path: str = "",
    use_llm: bool = True,
) -> str:
    if tex_path:
        try:
            target = resolve_safe_path(tex_path)
            if not target.is_file():
                return f"[Error] File not found: {tex_path}"
            files_to_scan = [tex_path]
        except (PermissionError, ValueError) as e:
            return f"[Error] {e}"
    else:
        main_tex = detect_main_tex_file()
        if not main_tex:
            return "[Error] No main .tex file found."
        files_to_scan = resolve_latex_project_files(main_tex)

    all_sections = []
    ablation_tables = []
    mentioned_modules = set()
    ablation_claims = []

    for f in files_to_scan:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f)
            text_clean = strip_latex_comments(text)

            for kw in _ABLATION_KEYWORDS:
                if kw.lower() in text_clean.lower():
                    ablation_tables.append({"file": f, "keyword": kw})

            for kw in _MODULE_KEYWORDS_EN + _MODULE_KEYWORDS_ZH:
                if kw.lower() in text_clean.lower():
                    mentioned_modules.add(kw)

            lines = text_clean.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                for kw in ["improve", "gain", "improvement", "提升", "增益", "效果"]:
                    if kw in stripped.lower():
                        ablation_claims.append({"file": f, "line": i, "text": stripped[:150]})
                        break
        except Exception:
            continue

    ablation_sections = [t for t in ablation_tables if "ablation" in t["keyword"].lower() or "消融" in t["keyword"].lower()]

    parts = ["Ablation Logic Check", ""]

    parts.append("Detected proposed modules:")
    for m in sorted(mentioned_modules):
        parts.append(f"  - {m}")
    parts.append("")

    parts.append(f"Detected ablation-related content: {len(ablation_sections)} location(s)")
    for s in ablation_sections[:5]:
        parts.append(f"  - {s['file']}: contains '{s['keyword']}'")
    parts.append("")

    issues = []
    if not ablation_sections:
        issues.append("No explicit ablation section or table detected.")
        issues.append("Consider adding an ablation study to validate each module's contribution.")

    if ablation_claims:
        parts.append(f"Ablation-related claims: {len(ablation_claims)}")
        for c in ablation_claims[:5]:
            parts.append(f"  - {c['file']}:{c['line']}: \"{c['text'][:80]}\"")
        parts.append("")

    if issues:
        parts.append("Potential issues:")
        for i, issue in enumerate(issues, 1):
            parts.append(f"  {i}. {issue}")
        parts.append("")

    parts.append("Suggested improvements:")
    parts.append("  - Ensure each proposed module has a corresponding ablation row")
    parts.append("  - Explain any performance drops caused by individual modules")
    parts.append("  - Use consistent metrics between ablation and main experiments")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_EXPERIMENT_CHECK:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.paper import ABLATION_LOGIC_SYSTEM_PROMPT
            llm_input = f"Ablation check:\n{result[:3000]}"
            llm_result = ask_llm(ABLATION_LOGIC_SYSTEM_PROMPT, llm_input, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_EXPERIMENT_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# check_metric_consistency
# ---------------------------------------------------------------------------

_METRIC_PATTERNS = [
    (re.compile(r"\bmAP\b", re.IGNORECASE), "mAP"),
    (re.compile(r"\bAP[_{@]?50\b", re.IGNORECASE), "AP50"),
    (re.compile(r"\bAP[_{@]?75\b", re.IGNORECASE), "AP75"),
    (re.compile(r"\bPrecision\b", re.IGNORECASE), "Precision"),
    (re.compile(r"\bRecall\b", re.IGNORECASE), "Recall"),
    (re.compile(r"\bF1[- ]?score\b", re.IGNORECASE), "F1"),
    (re.compile(r"\bPd\b"), "Pd"),
    (re.compile(r"\bPr\b"), "Pr"),
    (re.compile(r"\bFAR\b"), "FAR"),
    (re.compile(r"\bFP\b"), "FP"),
    (re.compile(r"\bFPS\b"), "FPS"),
    (re.compile(r"\bLatency\b", re.IGNORECASE), "Latency"),
    (re.compile(r"\bParams\b", re.IGNORECASE), "Params"),
    (re.compile(r"\bGFLOPs\b", re.IGNORECASE), "GFLOPs"),
    (re.compile(r"\bIoU\b"), "IoU"),
    (re.compile(r"\bAccuracy\b", re.IGNORECASE), "Accuracy"),
    (re.compile(r"\bOA\b"), "OA"),
    (re.compile(r"\bAA\b"), "AA"),
    (re.compile(r"\bKappa\b", re.IGNORECASE), "Kappa"),
]


def check_metric_consistency_logic(
    tex_path: str = "",
    use_llm: bool = False,
) -> str:
    if tex_path:
        try:
            target = resolve_safe_path(tex_path)
            if not target.is_file():
                return f"[Error] File not found: {tex_path}"
            files_to_scan = [tex_path]
        except (PermissionError, ValueError) as e:
            return f"[Error] {e}"
    else:
        main_tex = detect_main_tex_file()
        if not main_tex:
            return "[Error] No main .tex file found."
        files_to_scan = resolve_latex_project_files(main_tex)

    metric_occurrences = defaultdict(list)
    notation_variants = defaultdict(set)

    for f in files_to_scan:
        if "[NOT FOUND]" in f:
            continue
        try:
            text = read_latex_file_safe(f)
            lines = text.split("\n")
            for i, line in enumerate(lines, 1):
                for pattern, canonical in _METRIC_PATTERNS:
                    for m in pattern.finditer(line):
                        actual = m.group(0)
                        metric_occurrences[canonical].append({"file": f, "line": i, "text": actual})
                        notation_variants[canonical].add(actual)
        except Exception:
            continue

    parts = ["Metric Consistency Check", ""]
    parts.append("Detected metrics:")
    for metric, occurrences in sorted(metric_occurrences.items()):
        variants = notation_variants[metric]
        variant_str = " / ".join(sorted(variants))
        parts.append(f"  - {metric}: {len(occurrences)} occurrences, notation: {variant_str}")
    parts.append("")

    issues = []
    for metric, variants in notation_variants.items():
        if len(variants) > 1:
            issues.append({
                "metric": metric,
                "problem": f"Multiple notations used: {', '.join(sorted(variants))}",
                "suggestion": f"Choose one style consistently, preferably {sorted(variants)[0]}",
                "severity": "medium",
            })

    for metric, occurrences in metric_occurrences.items():
        values_found = set()
        for occ in occurrences:
            try:
                text = read_latex_file_safe(occ["file"])
                lines = text.split("\n")
                if occ["line"] <= len(lines):
                    line = lines[occ["line"] - 1]
                    nums = re.findall(r"\d+\.?\d*", line)
                    for n in nums:
                        values_found.add(n)
            except Exception:
                pass
        if values_found:
            has_decimal = any("." in v for v in values_found)
            has_percentage = any(float(v) > 1 for v in values_found if re.match(r"^\d+\.?\d*$", v))
            if has_decimal and has_percentage:
                mixed = [v for v in values_found if "." in v and float(v) < 1]
                if mixed:
                    issues.append({
                        "metric": metric,
                        "problem": f"Values appear in both decimal ({mixed[0]}) and percentage format",
                        "suggestion": "Use one format consistently (e.g., 82.4% or 0.824)",
                        "severity": "medium",
                    })

    fps_occurrences = metric_occurrences.get("FPS", [])
    if fps_occurrences:
        has_hardware = False
        for f in files_to_scan:
            if "[NOT FOUND]" in f:
                continue
            try:
                text = read_latex_file_safe(f).lower()
                if any(w in text for w in ["gpu", "cpu", "rtx", "a100", "v100", "titan", "inference time", "batch size"]):
                    has_hardware = True
                    break
            except Exception:
                pass
        if not has_hardware:
            issues.append({
                "metric": "FPS",
                "problem": "FPS reported but no hardware/test environment description found",
                "suggestion": "Add inference hardware, batch size, and input resolution description",
                "severity": "low",
            })

    parts.append(f"Potential issues: {len(issues)}")
    for i, issue in enumerate(issues[:10], 1):
        parts.append(f"\n{i}. {issue['metric']}")
        parts.append(f"   Problem: {issue['problem']}")
        parts.append(f"   Suggestion: {issue['suggestion']}")
        parts.append(f"   Severity: {issue['severity']}")

    if not issues:
        parts.append("\nNo significant metric inconsistencies found.")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_EXPERIMENT_CHECK:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.paper import METRIC_CONSISTENCY_SYSTEM_PROMPT
            llm_input = f"Metric consistency check:\n{result[:3000]}"
            llm_result = ask_llm(METRIC_CONSISTENCY_SYSTEM_PROMPT, llm_input, max_tokens=PAPER_LLM_MAX_TOKENS, temperature=PAPER_LLM_TEMPERATURE)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_EXPERIMENT_OUTPUT_CHARS)
