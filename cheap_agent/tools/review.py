import re

from cheap_agent.tools._common import truncate
from cheap_agent.cache import get_cache, make_hash, set_cache
from cheap_agent.config import (
    ENABLE_LLM_REVIEW,
    ENABLE_REVIEW_CACHE,
    MASK_SECRET_VALUES,
    MAX_DIFF_CHARS,
    MAX_DIFF_FILES,
    MAX_IMPACT_SYMBOLS,
    MAX_OUTPUT_CHARS,
    MAX_REVIEW_CHANGED_FILES,
    REVIEW_CACHE_TTL_SEC,
)
from cheap_agent.workspace import resolve_safe_path



_SECRET_PATTERNS = [
    re.compile(r"(?i)(api_key|token|secret|password|private_key|access_key|openai_api_key)\s*[=:]\s*\S+"),
]


def mask_secrets_in_text(text: str) -> str:
    if not MASK_SECRET_VALUES:
        return text
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: m.group().split("=")[0].split(":")[0] + "=***MASKED***", text)
    return text


def parse_file_list(text: str) -> list[str]:
    files = []
    for part in text.replace(",", "\n").splitlines():
        part = part.strip()
        if part:
            files.append(part)
    return files[:MAX_REVIEW_CHANGED_FILES]


# ---------------------------------------------------------------------------
# diff parsing helpers
# ---------------------------------------------------------------------------

_DIFF_FILE_RE = re.compile(r'^diff --git a/(.+?) b/(.+?)$', re.MULTILINE)
_DIFF_HUNK_RE = re.compile(r'^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@', re.MULTILINE)
_DIFF_ADD_RE = re.compile(r'^\+[^+]', re.MULTILINE)
_DIFF_DEL_RE = re.compile(r'^^-[^-]', re.MULTILINE)
_DIFF_NEW_FILE_RE = re.compile(r'^new file mode', re.MULTILINE)
_DIFF_DELETED_FILE_RE = re.compile(r'^deleted file mode', re.MULTILINE)


def parse_changed_files_from_diff(diff_text: str) -> list[str]:
    files = []
    for m in _DIFF_FILE_RE.finditer(diff_text):
        f = m.group(2)
        if f not in files:
            files.append(f)
    return files[:MAX_DIFF_FILES]


def parse_diff_summary(diff_text: str) -> dict:
    if not diff_text or not diff_text.strip():
        return {"files": [], "total_added": 0, "total_removed": 0, "is_truncated": False}

    is_truncated = len(diff_text) > MAX_DIFF_CHARS
    if is_truncated:
        diff_text = diff_text[:MAX_DIFF_CHARS]

    files = []
    file_splits = re.split(r'^diff --git', diff_text, flags=re.MULTILINE)

    for chunk in file_splits[1:]:
        path_m = re.search(r'a/(.+?) b/(.+?)$', chunk, re.MULTILINE)
        if not path_m:
            continue
        path = path_m.group(2)
        added = len(_DIFF_ADD_RE.findall(chunk))
        removed = len(_DIFF_DEL_RE.findall(chunk))
        hunks = len(_DIFF_HUNK_RE.findall(chunk))
        is_new = bool(_DIFF_NEW_FILE_RE.search(chunk))
        is_deleted = bool(_DIFF_DELETED_FILE_RE.search(chunk))

        files.append({
            "path": path,
            "added_lines": added,
            "removed_lines": removed,
            "hunks": hunks,
            "is_new_file": is_new,
            "is_deleted_file": is_deleted,
        })

    total_added = sum(f["added_lines"] for f in files)
    total_removed = sum(f["removed_lines"] for f in files)

    return {
        "files": files[:MAX_DIFF_FILES],
        "total_added": total_added,
        "total_removed": total_removed,
        "is_truncated": is_truncated,
    }


def extract_symbols_from_diff(diff_text: str) -> list[str]:
    symbols = set()
    for line in diff_text.splitlines():
        if not line.startswith("+"):
            continue
        line = line[1:]
        m = re.match(r'^\s*def\s+(\w+)', line)
        if m:
            symbols.add(m.group(1))
            continue
        m = re.match(r'^\s*class\s+(\w+)', line)
        if m:
            symbols.add(m.group(1))
            continue
        m = re.match(r'^\s*(\w+)\s*[=:]', line)
        if m and m.group(1).isupper():
            symbols.add(m.group(1))

    return list(symbols)[:MAX_IMPACT_SYMBOLS]


# ---------------------------------------------------------------------------
# risk patterns
# ---------------------------------------------------------------------------

_RISK_PATTERNS = [
    (re.compile(r'^\+.*def\s+\w+\s*\(', re.MULTILINE), "New function added — check callers and tests"),
    (re.compile(r'^-.*def\s+\w+\s*\(', re.MULTILINE), "Function removed — check if callers still reference it"),
    (re.compile(r'^\+.*class\s+\w+', re.MULTILINE), "New class added — check imports and usage"),
    (re.compile(r'^-.*class\s+\w+', re.MULTILINE), "Class removed — check if imports still reference it"),
    (re.compile(r'^[+-].*(?:num_classes|nc|names)\s*[=:]'), "Class count or names changed — verify dataset/model consistency"),
    (re.compile(r'^[+-].*(?:batch_size|img_size|image_size)\s*[=:]'), "Training parameter changed — verify training pipeline"),
    (re.compile(r'^[+-].*(?:API_KEY|TOKEN|SECRET|PASSWORD)', re.IGNORECASE), "Secret/sensitive value modified — verify not exposed"),
    (re.compile(r'^\+.*(?:/home/|/Users/|C:\\\\|D:\\\\)'), "Hardcoded absolute path added — may break portability"),
    (re.compile(r'^\+.*print\s*\(', re.MULTILINE), "print() added — may pollute MCP stdio if in server.py"),
    (re.compile(r'^[+-].*WORKSPACE_ROOT'), "WORKSPACE_ROOT modified — verify security boundary"),
    (re.compile(r'^[+-].*(?:resolve_safe_path|is_in_workspace)'), "Path safety check modified — verify security"),
    (re.compile(r'^[+-].*(?:_cache|set_cache|get_cache|invalidate)'), "Cache logic modified — verify invalidation"),
    (re.compile(r'^-.*(?:try|except|raise)'), "Exception handling removed — may hide errors"),
    (re.compile(r'^[+-].*(?:stdout|stderr|logging|MCP_TRANSPORT)'), "I/O or transport config changed — verify MCP compatibility"),
]


def _detect_risk_patterns(diff_text: str) -> list[str]:
    risks = []
    for pat, msg in _RISK_PATTERNS:
        if pat.search(diff_text):
            risks.append(msg)
    return risks


# ---------------------------------------------------------------------------
# review_diff
# ---------------------------------------------------------------------------

def review_diff_logic(
    diff_text: str,
    task_description: str = "",
    use_llm: bool = True,
) -> str:
    if not diff_text or not diff_text.strip():
        return "[Error] diff_text must not be empty"

    cache_key = f"review_diff:{make_hash(diff_text + task_description)}:{use_llm}"
    if ENABLE_REVIEW_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    diff_text = mask_secrets_in_text(diff_text)
    summary = parse_diff_summary(diff_text)
    changed_files = parse_changed_files_from_diff(diff_text)
    risk_patterns = _detect_risk_patterns(diff_text)

    parts = ["Diff Review", ""]
    if task_description:
        parts.append(f"Task: {task_description[:200]}")
        parts.append("")

    parts.append("Changed files:")
    for f in summary["files"]:
        status = " (NEW)" if f["is_new_file"] else (" (DELETED)" if f["is_deleted_file"] else "")
        parts.append(f"  - {f['path']}: +{f['added_lines']} -{f['removed_lines']}{status}")
    parts.append(f"\nTotal: +{summary['total_added']} -{summary['total_removed']}")
    if summary["is_truncated"]:
        parts.append("(diff was truncated)")
    parts.append("")

    risk_level = "low"
    if len(changed_files) > 5 or len(risk_patterns) > 3:
        risk_level = "high"
    elif len(changed_files) > 2 or len(risk_patterns) > 0:
        risk_level = "medium"
    parts.append(f"Risk level: {risk_level}")
    parts.append("")

    if risk_patterns:
        parts.append("Potential issues:")
        for i, r in enumerate(risk_patterns, 1):
            parts.append(f"  {i}. {r}")
        parts.append("")

    missing = []
    if any(f["path"].endswith(".py") for f in summary["files"]):
        if not any(f["path"].startswith("test") or "test_" in f["path"] for f in summary["files"]):
            missing.append("No test files modified — consider updating tests")
    if any(f["path"].endswith((".yaml", ".yml", ".toml", ".json")) for f in summary["files"]):
        missing.append("Config file changed — verify .env.example and config.py are consistent")
    if any("readme" in f["path"].lower() for f in summary["files"]):
        pass
    elif any(f["path"].endswith(".py") for f in summary["files"]):
        missing.append("Python files changed — consider if README needs updating")

    if missing:
        parts.append("Missing checks:")
        for m in missing:
            parts.append(f"  - {m}")
        parts.append("")

    parts.append("Suggested validation:")
    parts.append("  - Call suggest_validation_plan with changed files")
    parts.append("  - Call generate_unit_test_plan for modified functions")
    parts.append("  - Manually review high-risk patterns above")
    parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Review the diff for the issues listed above")
    parts.append("  - Check if callers of modified functions need updates")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_REVIEW:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import DIFF_REVIEW_SYSTEM_PROMPT
            diff_excerpt = diff_text[:5000]
            llm_input = f"Diff review:\n{result}\n\nDiff excerpt:\n{diff_excerpt}"
            if task_description:
                llm_input += f"\n\nTask: {task_description}"
            llm_result = ask_llm(DIFF_REVIEW_SYSTEM_PROMPT, llm_input, max_tokens=1024)
            result = result + "\n\nLLM Review:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_REVIEW_CACHE:
        set_cache(cache_key, result, REVIEW_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# risk_check_before_edit
# ---------------------------------------------------------------------------

def risk_check_before_edit_logic(
    task_description: str,
    target_files: str = "",
    use_llm: bool = True,
) -> str:
    if not task_description or not task_description.strip():
        return "[Error] task_description must not be empty"

    cache_key = f"pre_risk:{make_hash(task_description + target_files)}:{use_llm}"
    if ENABLE_REVIEW_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    files = parse_file_list(target_files) if target_files else []
    file_infos = []
    for f in files:
        try:
            target = resolve_safe_path(f)
            if target.is_file():
                from cheap_agent.tools.reading import extract_symbols_logic
                symbols = extract_symbols_logic(f)
                file_infos.append({"path": f, "exists": True, "symbols": symbols[:500]})
            else:
                file_infos.append({"path": f, "exists": False, "symbols": ""})
        except (PermissionError, ValueError):
            file_infos.append({"path": f, "exists": False, "symbols": ""})

    areas = _detect_affected_areas(task_description, files)
    risk_level = _assess_edit_risk(task_description, files)

    parts = ["Pre-edit Risk Check", ""]
    parts.append(f"Task: {task_description[:200]}")
    parts.append("")

    if file_infos:
        parts.append("Target files:")
        for fi in file_infos:
            status = "exists" if fi["exists"] else "NOT FOUND"
            parts.append(f"  - {fi['path']} ({status})")
        parts.append("")

    parts.append(f"Likely affected areas: {', '.join(areas)}")
    parts.append(f"Risk level: {risk_level}")
    parts.append("")

    risks = _generate_edit_risks(task_description, files, areas)
    parts.append("Risks:")
    for i, r in enumerate(risks, 1):
        parts.append(f"  {i}. {r}")
    parts.append("")

    sync_files = _suggest_sync_files(task_description, files)
    if sync_files:
        parts.append("Files likely needing synchronized changes:")
        for sf in sync_files:
            parts.append(f"  - {sf}")
        parts.append("")

    parts.append("Recommended reading before edit:")
    for f in files[:5]:
        parts.append(f"  - Read {f} to understand current implementation")
    parts.append("")

    parts.append("What not to change blindly:")
    parts.append("  - Don't modify path safety checks (resolve_safe_path)")
    parts.append("  - Don't modify MCP stdout behavior")
    parts.append("  - Don't modify cache invalidation logic without understanding impact")
    parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Read target files before editing")
    parts.append("  - Preserve security boundaries")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_REVIEW:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import PRE_EDIT_RISK_SYSTEM_PROMPT
            llm_input = f"Pre-edit risk check:\n{result}"
            llm_result = ask_llm(PRE_EDIT_RISK_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_REVIEW_CACHE:
        set_cache(cache_key, result, REVIEW_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _detect_affected_areas(task: str, files: list[str]) -> list[str]:
    combined = (task + " " + " ".join(files)).lower()
    areas = []
    if any(w in combined for w in ["config", "setting", "env", ".yaml", ".toml"]):
        areas.append("config")
    if any(w in combined for w in ["dataset", "data", "label", "dataloader"]):
        areas.append("dataset")
    if any(w in combined for w in ["model", "network", "layer", "backbone"]):
        areas.append("model")
    if any(w in combined for w in ["train", "loss", "optimizer", "epoch"]):
        areas.append("training")
    if any(w in combined for w in ["test", "pytest", "unittest"]):
        areas.append("tests")
    if any(w in combined for w in ["readme", "doc", "md"]):
        areas.append("docs")
    if any(w in combined for w in ["mcp", "server", "tool", "stdio"]):
        areas.append("MCP communication")
    if any(w in combined for w in ["cache", "ttl", "invalidat"]):
        areas.append("cache")
    if any(w in combined for w in ["path", "workspace", "safe", "permission"]):
        areas.append("security boundary")
    if not areas:
        areas.append("general code")
    return areas


def _assess_edit_risk(task: str, files: list[str]) -> str:
    combined = (task + " " + " ".join(files)).lower()
    if any(w in combined for w in ["mcp", "server", "stdio", "workspace", "safe_path", "cache"]):
        return "high"
    if any(w in combined for w in ["model", "loss", "train", "config", "num_classes"]):
        return "high"
    if len(files) > 5:
        return "high"
    if any(w in combined for w in ["test", "doc", "readme", "comment"]):
        return "low"
    return "medium"


def _generate_edit_risks(task: str, files: list[str], areas: list[str]) -> list[str]:
    risks = []
    if "config" in areas:
        risks.append("Config changes may break existing setups — check .env.example and config.py")
    if "dataset" in areas:
        risks.append("Dataset format changes may break training — check label format and num_classes")
    if "model" in areas:
        risks.append("Model changes may affect output shape — check loss function and downstream layers")
    if "training" in areas:
        risks.append("Training changes may affect convergence — check learning rate and optimizer")
    if "MCP communication" in areas:
        risks.append("MCP changes may break stdio communication — don't add print() to stdout")
    if "cache" in areas:
        risks.append("Cache changes may cause stale data — verify invalidation logic")
    if "security boundary" in areas:
        risks.append("Security boundary changes may allow path traversal — verify all checks preserved")
    if not risks:
        risks.append("Low risk — but still review the changes carefully")
    return risks


def _suggest_sync_files(task: str, files: list[str]) -> list[str]:
    sync = []
    if any(f.endswith((".yaml", ".yml", ".toml")) for f in files):
        sync.append("config.py (may need to read new config keys)")
        sync.append(".env.example (may need to document new env vars)")
    if any("model" in f.lower() for f in files):
        sync.append("loss function or training script")
    if any("train" in f.lower() for f in files):
        sync.append("config files and dataset paths")
    if any("test" in f.lower() for f in files):
        sync.append("the code being tested")
    return sync


# ---------------------------------------------------------------------------
# post_edit_review
# ---------------------------------------------------------------------------

def post_edit_review_logic(
    task_description: str,
    changed_files: str,
    diff_text: str = "",
    use_llm: bool = True,
) -> str:
    if not task_description or not task_description.strip():
        return "[Error] task_description must not be empty"
    if not changed_files or not changed_files.strip():
        return "[Error] changed_files must not be empty"

    cache_key = f"post_edit:{make_hash(task_description + changed_files + diff_text)}:{use_llm}"
    if ENABLE_REVIEW_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    files = parse_file_list(changed_files)[:MAX_REVIEW_CHANGED_FILES]
    file_infos = []
    for f in files:
        try:
            target = resolve_safe_path(f)
            if target.is_file():
                from cheap_agent.tools.reading import extract_symbols_logic
                symbols = extract_symbols_logic(f)
                file_infos.append({"path": f, "exists": True, "symbols": symbols[:300]})
            else:
                file_infos.append({"path": f, "exists": False, "symbols": ""})
        except (PermissionError, ValueError):
            file_infos.append({"path": f, "exists": False, "symbols": ""})

    diff_review = ""
    if diff_text:
        try:
            diff_review = review_diff_logic(diff_text, task_description, use_llm=False)
        except Exception:
            pass

    parts = ["Post-edit Review", ""]
    parts.append(f"Task: {task_description[:200]}")
    parts.append("")

    parts.append("Changed files:")
    for fi in file_infos:
        status = "exists" if fi["exists"] else "NOT FOUND (may be deleted)"
        parts.append(f"  - {fi['path']} ({status})")
    parts.append("")

    coverage = _assess_task_coverage(task_description, files)
    parts.append("Review summary:")
    parts.append(f"  - Task coverage: {coverage}")
    parts.append(f"  - Changed {len(files)} file(s)")
    parts.append("")

    if diff_review and not diff_review.startswith("[Error]"):
        parts.append("Diff review highlights:")
        for line in diff_review.split("\n"):
            if line.strip().startswith(("Potential", "Risk", "Missing")):
                parts.append(f"  {line}")
        parts.append("")

    problems = _detect_post_edit_problems(task_description, files, file_infos)
    if problems:
        parts.append("Potential problems:")
        for i, p in enumerate(problems, 1):
            parts.append(f"  {i}. {p}")
        parts.append("")

    parts.append("Suggested follow-up checks:")
    parts.append("  1. Verify the change matches the task goal")
    parts.append("  2. Check for unintended side effects")
    parts.append("  3. Run tests if available")
    parts.append("  4. Check config consistency")
    parts.append("")

    parts.append("Suggested validation commands (do NOT execute automatically):")
    parts.append("  - python -m pytest tests/ -x -v")
    parts.append("  - Call suggest_validation_plan for detailed validation steps")
    parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Review if all files in the task scope were modified")
    parts.append("  - Check if tests or docs need updates")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_REVIEW:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import POST_EDIT_REVIEW_SYSTEM_PROMPT
            llm_input = f"Post-edit review:\n{result}"
            if diff_text:
                llm_input += f"\n\nDiff excerpt:\n{diff_text[:3000]}"
            llm_result = ask_llm(POST_EDIT_REVIEW_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Review:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_REVIEW_CACHE:
        set_cache(cache_key, result, REVIEW_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _assess_task_coverage(task: str, files: list[str]) -> str:
    task_lower = task.lower()
    files_lower = " ".join(files).lower()
    if any(w in task_lower for w in ["fix", "bug", "error", "issue"]):
        return "partial — verify the specific bug is addressed"
    if any(w in task_lower for w in ["add", "feature", "implement"]):
        return "check if all new components are included"
    if any(w in task_lower for w in ["refactor", "rename", "move"]):
        return "check if all references are updated"
    return "review if the changes match the task goal"


def _detect_post_edit_problems(task: str, files: list[str], file_infos: list[dict]) -> list[str]:
    problems = []
    not_found = [fi["path"] for fi in file_infos if not fi["exists"]]
    if not_found:
        problems.append(f"Files not found (may be deleted): {', '.join(not_found)}")
    if len(files) > 5:
        problems.append("Many files changed — higher risk of missing something")
    if any("test" in f.lower() for f in files) and not any("test" not in f.lower() for f in files):
        problems.append("Only test files changed — verify if source code also needs changes")
    return problems


# ---------------------------------------------------------------------------
# analyze_change_impact
# ---------------------------------------------------------------------------

def analyze_change_impact_logic(
    task_description: str,
    target_files: str = "",
    diff_text: str = "",
    use_llm: bool = True,
) -> str:
    if not task_description or not task_description.strip():
        return "[Error] task_description must not be empty"

    cache_key = f"impact:{make_hash(task_description + target_files + diff_text)}:{use_llm}"
    if ENABLE_REVIEW_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    files = parse_file_list(target_files) if target_files else []
    symbols = []
    if diff_text:
        symbols = extract_symbols_from_diff(diff_text)

    references: dict[str, list[str]] = {}
    if symbols:
        for sym in symbols[:MAX_IMPACT_SYMBOLS]:
            try:
                from cheap_agent.tools.reading import search_code_logic
                result = search_code_logic(sym, max_results=5)
                if result and "no matches" not in result.lower():
                    refs = []
                    for line in result.split("\n"):
                        if ":" in line and not line.startswith(("Search", "Scanned", "Results")):
                            refs.append(line.strip())
                    if refs:
                        references[sym] = refs[:5]
            except Exception:
                pass

    parts = ["Change Impact Analysis", ""]
    parts.append(f"Task: {task_description[:200]}")
    parts.append("")

    if files:
        parts.append("Changed / target files:")
        for f in files:
            parts.append(f"  - {f}")
        parts.append("")

    if symbols:
        parts.append("Potentially changed symbols:")
        for s in symbols:
            parts.append(f"  - {s}")
        parts.append("")

    areas = _detect_impact_areas(task_description, files, symbols)
    parts.append("Likely impacted areas:")
    for a in areas:
        parts.append(f"  - {a}")
    parts.append("")

    if references:
        parts.append("References found:")
        for sym, refs in references.items():
            parts.append(f"  {sym}:")
            for r in refs[:3]:
                parts.append(f"    {r}")
        parts.append("")

    sync = _suggest_impact_sync(task_description, files, symbols)
    if sync:
        parts.append("Potential synchronized changes:")
        for s in sync:
            parts.append(f"  - {s}")
        parts.append("")

    parts.append("Suggested reading order:")
    for f in files[:5]:
        parts.append(f"  - Read {f}")
    parts.append("")

    parts.append("Suggested validation:")
    parts.append("  - Call suggest_validation_plan with changed files")
    parts.append("  - Check references found above for breaking changes")
    parts.append("")

    parts.append("Uncertainty:")
    parts.append("  - Dynamic references (eval, getattr, string-based imports) cannot be detected statically")
    parts.append("  - External API consumers are not covered")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_REVIEW:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import CHANGE_IMPACT_SYSTEM_PROMPT
            llm_input = f"Change impact analysis:\n{result}"
            if diff_text:
                llm_input += f"\n\nDiff excerpt:\n{diff_text[:3000]}"
            llm_result = ask_llm(CHANGE_IMPACT_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Analysis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_REVIEW_CACHE:
        set_cache(cache_key, result, REVIEW_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _detect_impact_areas(task: str, files: list[str], symbols: list[str]) -> list[str]:
    combined = (task + " " + " ".join(files) + " " + " ".join(symbols)).lower()
    areas = []
    if any(w in combined for w in ["def ", "class ", "function", "method"]):
        areas.append("callers of modified functions/classes")
    if any(w in combined for w in ["test", "pytest"]):
        areas.append("tests")
    if any(w in combined for w in ["config", "env", "yaml", "setting"]):
        areas.append("configs")
    if any(w in combined for w in ["readme", "doc", "md"]):
        areas.append("docs")
    if any(w in combined for w in ["dataset", "data", "label"]):
        areas.append("dataset")
    if any(w in combined for w in ["model", "network", "layer"]):
        areas.append("model")
    if any(w in combined for w in ["train", "loss", "optimizer"]):
        areas.append("training pipeline")
    if any(w in combined for w in ["mcp", "tool", "server"]):
        areas.append("MCP tools")
    if not areas:
        areas.append("general code — check callers and tests")
    return areas


def _suggest_impact_sync(task: str, files: list[str], symbols: list[str]) -> list[str]:
    sync = []
    if any(w in " ".join(symbols).lower() for w in ["num_classes", "nc", "names"]):
        sync.append("Verify model output channels match num_classes")
        sync.append("Verify dataset class count matches config")
    if any("config" in f.lower() for f in files):
        sync.append("Check .env.example and config.py for consistency")
    if any("model" in f.lower() for f in files):
        sync.append("Check loss function for shape compatibility")
    if any("test" in f.lower() for f in files):
        sync.append("Update corresponding source code tests")
    return sync
