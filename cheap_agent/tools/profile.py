import re
from collections import defaultdict
from pathlib import Path

from cheap_agent.tools._common import truncate
from cheap_agent.cache import make_hash
from cheap_agent.cache_manager import ensure_cache_dir, get_disk_cache, set_disk_cache, write_json_cache_atomic
from cheap_agent.config import (
    CACHE_SCHEMA_VERSION,
    ENABLE_CONVENTIONS_CACHE,
    ENABLE_LLM_CONVENTIONS,
    ENABLE_LLM_PROFILE,
    ENABLE_LLM_RUNBOOK,
    ENABLE_ONBOARDING_PACK_CACHE,
    ENABLE_PROJECT_PROFILE_V2_CACHE,
    ENABLE_RUNBOOK_CACHE,
    LLM_MODEL,
    MAX_ONBOARDING_ITEMS,
    MAX_OUTPUT_CHARS,
    MAX_PROFILE_EVIDENCE_ITEMS,
    CONVENTIONS_CACHE_TTL_SEC,
    ONBOARDING_PACK_CACHE_TTL_SEC,
    PROJECT_PROFILE_V2_CACHE_TTL_SEC,
    RUNBOOK_CACHE_TTL_SEC,
    WORKSPACE_ROOT,
)
from cheap_agent.workspace import get_file_index_cached, get_file_index_version



def _safe_read_file(path: str, max_chars: int = 3000) -> str:
    try:
        target = (WORKSPACE_ROOT / path).resolve()
        root = WORKSPACE_ROOT.resolve()
        if not (target == root or root in target.parents):
            return ""
        if not target.is_file():
            return ""
        return target.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# build_project_profile_v2
# ---------------------------------------------------------------------------

def build_project_profile_v2_logic(
    use_llm: bool = True,
    force_refresh: bool = False,
) -> str:
    file_index = get_file_index_cached(force_rebuild=force_refresh)
    index_version = get_file_index_version(file_index)

    cache_key = make_cache_key(["profile_v2", index_version, str(use_llm), LLM_MODEL, str(CACHE_SCHEMA_VERSION)])
    if ENABLE_PROJECT_PROFILE_V2_CACHE and not force_refresh:
        cached = get_disk_cache("project_profile_v2", cache_key, ttl_sec=PROJECT_PROFILE_V2_CACHE_TTL_SEC)
        if cached and isinstance(cached, str):
            return cached

    parts = ["Project Profile v2", ""]

    lang_stats = defaultdict(int)
    ext_stats = defaultdict(int)
    categories = defaultdict(int)
    for f in file_index:
        suffix = f.get("suffix", "")
        ext_stats[suffix] += 1
        cat = f.get("category", "other")
        categories[cat] += 1

    main_lang = _detect_main_language(ext_stats)
    secondary = _detect_secondary_languages(ext_stats, main_lang)

    parts.append("Basic:")
    parts.append(f"  - project root: {WORKSPACE_ROOT}")
    parts.append(f"  - main language: {main_lang}")
    if secondary:
        parts.append(f"  - secondary languages: {', '.join(secondary)}")
    parts.append(f"  - total files: {len(file_index)}")
    parts.append("")

    stack = _detect_stack(file_index)
    parts.append("Detected stack:")
    for item in stack:
        parts.append(f"  - {item['name']}")
        parts.append(f"    Evidence: {item['evidence']}")
        parts.append(f"    Confidence: {item['confidence']}")
    parts.append("")

    entries = _detect_entry_points(file_index)
    parts.append("Entry points:")
    for item in entries:
        parts.append(f"  - {item['path']} ({item['role']})")
        parts.append(f"    Evidence: {item['evidence']}")
        parts.append(f"    Confidence: {item['confidence']}")
    parts.append("")

    configs = _detect_config_files(file_index)
    parts.append("Configuration:")
    for item in configs:
        parts.append(f"  - {item['path']}")
    parts.append("")

    test_info = _detect_test_info(file_index)
    parts.append("Testing:")
    parts.append(f"  - framework: {test_info['framework']}")
    parts.append(f"  - test dirs: {', '.join(test_info['dirs']) or '(none)'}")
    parts.append(f"  - test files: {test_info['count']}")
    parts.append(f"  - suggested command: {test_info['command']}")
    parts.append(f"  - Confidence: {test_info['confidence']}")
    parts.append("")

    runtime = _detect_runtime_info(file_index)
    parts.append("Runtime / operation:")
    parts.append(f"  - start command: {runtime['start_command']}")
    parts.append(f"  - dev workflow: {runtime['dev_workflow']}")
    parts.append(f"  - Confidence: {runtime['confidence']}")
    parts.append("")

    modules = _detect_important_modules(file_index)
    parts.append("Important modules:")
    for m in modules[:MAX_PROFILE_EVIDENCE_ITEMS]:
        parts.append(f"  - {m['path']}: {m['responsibility']}")
    parts.append("")

    read_order = _suggest_read_order(file_index, entries, configs)
    parts.append("Codex first-read order:")
    for i, f in enumerate(read_order[:10], 1):
        parts.append(f"  {i}. {f}")
    parts.append("")

    routing = _generate_task_routing(file_index)
    parts.append("Common task routing:")
    for task_type, info in routing.items():
        parts.append(f"  - {task_type}:")
        parts.append(f"    tools: {', '.join(info['tools'])}")
        parts.append(f"    files: {', '.join(info['files'][:3])}")
    parts.append("")

    parts.append("Uncertainty:")
    parts.append("  - Project type and stack are inferred from file names and extensions")
    parts.append("  - Test framework and run commands are guesses based on conventions")
    parts.append("  - User should confirm inferred commands before executing")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_PROFILE:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import PROJECT_PROFILE_V2_SYSTEM_PROMPT
            llm_input = f"Project profile:\n{result}\n\nFile categories: {dict(categories)}"
            llm_result = ask_llm(PROJECT_PROFILE_V2_SYSTEM_PROMPT, llm_input, max_tokens=1024)
            result = result + "\n\nLLM Notes:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_PROJECT_PROFILE_V2_CACHE:
        cache_dir = ensure_cache_dir()
        write_json_cache_atomic(cache_dir / "project_profile_v2.json", {"value": result, "cache_key": cache_key})
        set_disk_cache("project_profile_v2", cache_key, result, ttl_sec=PROJECT_PROFILE_V2_CACHE_TTL_SEC, tool="build_project_profile_v2")

    return truncate(result, MAX_OUTPUT_CHARS)


def _detect_main_language(ext_stats: dict) -> str:
    lang_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".java": "Java", ".go": "Go", ".rs": "Rust", ".cpp": "C++", ".c": "C"}
    scores = defaultdict(int)
    for ext, count in ext_stats.items():
        if ext in lang_map:
            scores[lang_map[ext]] += count
    if scores:
        return max(scores, key=scores.get)
    return "unknown"


def _detect_secondary_languages(ext_stats: dict, main: str) -> list[str]:
    lang_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".java": "Java", ".go": "Go", ".rs": "Rust"}
    secondary = []
    for ext, count in ext_stats.items():
        if ext in lang_map and lang_map[ext] != main and count > 2:
            secondary.append(lang_map[ext])
    return secondary[:3]


def _detect_stack(file_index: list[dict]) -> list[dict]:
    stack = []
    paths = [f["path"] for f in file_index]
    contents = {}

    for p in paths[:30]:
        c = _safe_read_file(p, 1000)
        if c:
            contents[p] = c

    all_text = " ".join(contents.values())
    all_paths = " ".join(paths)

    checks = [
        ("FastMCP", "FastMCP", ["server.py"], "high"),
        ("MCP SDK", "mcp", ["requirements.txt", "pyproject.toml"], "high"),
        ("OpenAI API", "openai", ["requirements.txt", "llm_client.py"], "high"),
        ("PyTorch", "torch", ["requirements.txt", "train.py"], "medium"),
        ("Ultralytics/YOLO", "ultralytics", ["requirements.txt", "train.py"], "medium"),
        ("pytest", "pytest", ["requirements.txt", "pyproject.toml"], "medium"),
        ("python-dotenv", "dotenv", ["requirements.txt", "config.py"], "high"),
        ("FastAPI", "fastapi", ["requirements.txt"], "medium"),
        ("Flask", "flask", ["requirements.txt"], "medium"),
        ("React", "react", ["package.json"], "medium"),
        ("Vue", "vue", ["package.json"], "medium"),
    ]

    for name, keyword, evidence_files, default_conf in checks:
        found_evidence = []
        if keyword.lower() in all_text.lower():
            found_evidence.append(f"found '{keyword}' in source")
        for ef in evidence_files:
            if ef in all_paths:
                found_evidence.append(f"{ef} exists")
        if found_evidence:
            conf = default_conf if len(found_evidence) > 1 else "medium"
            stack.append({"name": name, "evidence": "; ".join(found_evidence), "confidence": conf})

    return stack


def _detect_entry_points(file_index: list[dict]) -> list[dict]:
    entries = []
    entry_patterns = [
        (r"server\.py$", "MCP server entry", "high"),
        (r"main\.py$", "main entry", "high"),
        (r"app\.py$", "application entry", "high"),
        (r"train\.py$", "training entry", "high"),
        (r"infer(?:ence)?\.py$", "inference entry", "medium"),
        (r"(?:eval|evaluate)\.py$", "evaluation entry", "medium"),
        (r"predict\.py$", "prediction entry", "medium"),
        (r"cli\.py$", "CLI entry", "medium"),
        (r"run\.py$", "run entry", "medium"),
    ]
    for f in file_index:
        path = f["path"]
        for pattern, role, conf in entry_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                entries.append({"path": path, "role": role, "evidence": f"filename matches {pattern}", "confidence": conf})
                break
    return entries[:10]


def _detect_config_files(file_index: list[dict]) -> list[dict]:
    configs = []
    for f in file_index:
        path = f["path"]
        suffix = f.get("suffix", "")
        if suffix in ("yaml", "yml", "json", "toml", "ini", "cfg"):
            configs.append({"path": path})
        elif path.endswith(".env.example"):
            configs.append({"path": path})
        elif path in ("config.py", "settings.py"):
            configs.append({"path": path})
    return configs[:20]


def _detect_test_info(file_index: list[dict]) -> dict:
    test_files = [f for f in file_index if f.get("is_test") or "test" in f["path"].lower()]
    test_dirs = set()
    for f in test_files:
        parent = str(Path(f["path"]).parent)
        if parent != ".":
            test_dirs.add(parent)

    has_pytest = any("pytest" in _safe_read_file(f["path"], 500).lower() for f in file_index[:20])
    has_unittest = any("unittest" in _safe_read_file(f["path"], 500).lower() for f in file_index[:20])

    framework = "unknown"
    command = "# needs confirmation"
    conf = "low"
    if has_pytest:
        framework = "pytest"
        command = "python -m pytest tests/ -x -v"
        conf = "medium"
    elif has_unittest:
        framework = "unittest"
        command = "python -m unittest discover"
        conf = "medium"
    elif test_files:
        framework = "test files found (framework unknown)"
        command = "python -m pytest"
        conf = "low"

    return {
        "framework": framework,
        "dirs": sorted(test_dirs),
        "count": len(test_files),
        "command": command,
        "confidence": conf,
    }


def _detect_runtime_info(file_index: list[dict]) -> dict:
    paths = [f["path"] for f in file_index]
    has_server = "server.py" in paths
    has_train = any("train" in p.lower() for p in paths)
    has_requirements = "requirements.txt" in paths
    has_pyproject = "pyproject.toml" in paths

    start_cmd = "# needs confirmation"
    dev_workflow = "unknown"
    conf = "low"

    if has_server:
        start_cmd = "python server.py"
        dev_workflow = "MCP server via stdio"
        conf = "medium"
    elif has_train:
        start_cmd = "python train.py"
        dev_workflow = "training pipeline"
        conf = "medium"

    return {
        "start_command": start_cmd,
        "dev_workflow": dev_workflow,
        "confidence": conf,
    }


def _detect_important_modules(file_index: list[dict]) -> list[dict]:
    modules = []
    for f in file_index:
        path = f["path"]
        cat = f.get("category", "other")
        if cat in ("code", "training", "model", "dataset") and path.endswith(".py"):
            responsibility = _guess_responsibility(path)
            modules.append({"path": path, "responsibility": responsibility})
    return modules[:MAX_PROFILE_EVIDENCE_ITEMS]


def _guess_responsibility(path: str) -> str:
    name = Path(path).stem.lower()
    if "model" in name:
        return "model definition"
    if "train" in name:
        return "training logic"
    if "data" in name or "dataset" in name:
        return "data loading"
    if "config" in name:
        return "configuration"
    if "util" in name or "helper" in name:
        return "utility functions"
    if "test" in name:
        return "tests"
    if "server" in name:
        return "server entry"
    return "module"


def _suggest_read_order(file_index: list[dict], entries: list[dict], configs: list[dict]) -> list[str]:
    order = []
    for e in entries[:3]:
        if e["path"] not in order:
            order.append(e["path"])
    for c in configs[:3]:
        if c["path"] not in order:
            order.append(c["path"])
    for f in file_index:
        if f["path"] not in order and f.get("is_code"):
            order.append(f["path"])
        if len(order) >= 10:
            break
    return order


def _generate_task_routing(file_index: list[dict]) -> dict:
    return {
        "bug_fix": {
            "tools": ["search_code", "read_file_around_line", "extract_symbols", "suggest_debug_steps"],
            "files": ["README.md", "server.py", "config.py"],
        },
        "training_error": {
            "tools": ["diagnose_training_error", "analyze_traceback_with_context", "suggest_minimal_repro"],
            "files": ["train.py", "config.py", "dataset.py"],
        },
        "config_change": {
            "tools": ["check_config_consistency", "search_code", "risk_check_before_edit"],
            "files": ["config.py", ".env.example", "configs/"],
        },
        "code_review": {
            "tools": ["review_diff", "analyze_change_impact", "post_edit_review"],
            "files": ["server.py", "tools_*.py"],
        },
        "test_generation": {
            "tools": ["generate_unit_test_plan", "suggest_minimal_repro", "suggest_validation_plan"],
            "files": ["test_*.py", "tests/"],
        },
        "project_understanding": {
            "tools": ["get_codex_onboarding_pack", "build_project_map", "summarize_directory"],
            "files": ["README.md", "server.py", "config.py"],
        },
    }


def make_cache_key(parts: list[str] | tuple[str, ...]) -> str:
    combined = "|".join(str(p) for p in parts)
    import hashlib
    return hashlib.md5(combined.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# get_codex_onboarding_pack
# ---------------------------------------------------------------------------

def get_codex_onboarding_pack_logic(
    task_description: str = "",
    max_items: int = 20,
    use_llm: bool = False,
) -> str:
    max_items = min(max_items, MAX_ONBOARDING_ITEMS)
    task_hash = make_hash(task_description) if task_description else "default"
    cache_key = make_cache_key(["onboarding", task_hash, str(use_llm), LLM_MODEL])

    if ENABLE_ONBOARDING_PACK_CACHE:
        cached = get_disk_cache("onboarding_packs", cache_key, ttl_sec=ONBOARDING_PACK_CACHE_TTL_SEC)
        if cached and isinstance(cached, str):
            return cached

    file_index = get_file_index_cached()
    index_version = get_file_index_version(file_index)

    parts = ["Codex Onboarding Pack", ""]

    main_lang = "unknown"
    ext_stats = defaultdict(int)
    for f in file_index:
        ext_stats[f.get("suffix", "")] += 1
    if ext_stats.get("py", 0) > ext_stats.get("js", 0):
        main_lang = "Python"
    elif ext_stats.get("js", 0) + ext_stats.get("ts", 0) > 0:
        main_lang = "JavaScript/TypeScript"

    parts.append("Project:")
    parts.append(f"  - main language: {main_lang}")
    parts.append(f"  - total files: {len(file_index)}")
    parts.append("")

    start_files = ["README.md", "server.py", "config.py", "workspace.py"]
    start_files = [f for f in start_files if any(fi["path"] == f for fi in file_index)]
    if not start_files:
        start_files = [f["path"] for f in file_index[:4]]

    parts.append("Start here:")
    for i, f in enumerate(start_files[:max_items], 1):
        parts.append(f"  {i}. {f}")
    parts.append("")

    parts.append("Key conventions:")
    parts.append("  - config via .env / config.py")
    parts.append("  - MCP tools registered in server.py")
    parts.append("  - business logic split into tools_*.py")
    parts.append("  - cache under .code_agent_cache/")
    parts.append("  - logs to stderr only (stdio MCP)")
    parts.append("  - all paths restricted to WORKSPACE_ROOT")
    parts.append("")

    if task_description:
        routing = _classify_task_for_recommendation(task_description)
        tools = _get_tools_for_task_type(routing)
        parts.append(f"Recommended tools for this task ({routing}):")
        for t in tools[:5]:
            parts.append(f"  - {t}")
        parts.append("")

    parts.append("Do not forget:")
    parts.append("  - keep stdout clean for stdio MCP")
    parts.append("  - preserve WORKSPACE_ROOT safety boundary")
    parts.append("  - do not add shell execution tools")
    parts.append("  - cache writes only under .code_agent_cache/")

    result = "\n".join(parts)

    if ENABLE_ONBOARDING_PACK_CACHE:
        set_disk_cache("onboarding_packs", cache_key, result, ttl_sec=ONBOARDING_PACK_CACHE_TTL_SEC, tool="get_codex_onboarding_pack")

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# infer_project_runbook
# ---------------------------------------------------------------------------

def infer_project_runbook_logic(
    use_llm: bool = True,
    include_commands: bool = True,
) -> str:
    cache_key = make_cache_key(["runbook", str(use_llm), LLM_MODEL, str(CACHE_SCHEMA_VERSION)])
    if ENABLE_RUNBOOK_CACHE:
        cached = get_disk_cache("runbook", cache_key, ttl_sec=RUNBOOK_CACHE_TTL_SEC)
        if cached and isinstance(cached, str):
            return cached

    file_index = get_file_index_cached()
    paths = [f["path"] for f in file_index]

    readme_content = _safe_read_file("README.md", 3000)
    req_content = _safe_read_file("requirements.txt", 1000)

    parts = ["Project Runbook", ""]

    has_req = "requirements.txt" in paths
    has_pyproject = "pyproject.toml" in paths
    has_server = "server.py" in paths

    parts.append("Install:")
    if has_req:
        parts.append("  Suggested command, do not execute automatically:")
        parts.append("    pip install -r requirements.txt")
        parts.append("  Evidence: requirements.txt exists")
    elif has_pyproject:
        parts.append("  Suggested command, do not execute automatically:")
        parts.append("    pip install -e .")
        parts.append("  Evidence: pyproject.toml exists")
    else:
        parts.append("  (no dependency file found)")
    parts.append("")

    parts.append("Start:")
    if has_server:
        parts.append("  Suggested command, do not execute automatically:")
        parts.append("    python server.py")
        parts.append("  Evidence: server.py exists (MCP server)")
    parts.append("")

    test_files = [p for p in paths if "test" in p.lower()]
    parts.append("Test:")
    if test_files:
        parts.append("  Suggested command, do not execute automatically:")
        parts.append("    python -m pytest tests/ -x -v")
        parts.append(f"  Evidence: {len(test_files)} test file(s) found")
    else:
        parts.append("  (no test files found)")
    parts.append("")

    parts.append("Debug:")
    parts.append("  - Use analyze_traceback_with_context for Python errors")
    parts.append("  - Use diagnose_training_error for training issues")
    parts.append("  - Use search_code to locate functions and variables")
    parts.append("")

    parts.append("Cache / index:")
    parts.append("  - cache_status: view cache state")
    parts.append("  - rebuild_project_index: rebuild file index")
    parts.append("  - clear_cache: clean expired cache")
    parts.append("")

    parts.append("Common failure modes:")
    parts.append("  - stdout pollution in stdio MCP (never print to stdout)")
    parts.append("  - missing LLM config (check LLM_BASE_URL, LLM_API_KEY)")
    parts.append("  - wrong WORKSPACE_ROOT (must match project dir)")
    parts.append("  - stale cache (use clear_cache or rebuild_project_index)")
    parts.append("")

    parts.append("Uncertainty:")
    parts.append("  - Test framework and commands are inferred from conventions")
    parts.append("  - Install commands assume pip/Python environment")
    parts.append("  - User should confirm before executing any command")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_RUNBOOK:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import PROJECT_RUNBOOK_SYSTEM_PROMPT
            llm_result = ask_llm(PROJECT_RUNBOOK_SYSTEM_PROMPT, f"Runbook:\n{result}", max_tokens=512)
            result = result + "\n\nLLM Notes:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_RUNBOOK_CACHE:
        set_disk_cache("runbook", cache_key, result, ttl_sec=RUNBOOK_CACHE_TTL_SEC, tool="infer_project_runbook")

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# recommend_workflow_for_task
# ---------------------------------------------------------------------------

_TASK_CLASSIFICATION_PATTERNS = [
    ("traceback_error", re.compile(r"traceback|stack\s*trace|exception|error.*line\s+\d+", re.IGNORECASE)),
    ("import_error", re.compile(r"import.*error|module.*not.*found|cannot.*import|no module named", re.IGNORECASE)),
    ("training_error", re.compile(r"cuda.*(?:oom|out of memory)|shape.*mismatch|loss.*nan|training.*error|dataloader|num_classes", re.IGNORECASE)),
    ("config_change", re.compile(r"config|setting|env.*file|yaml|toml|parameter", re.IGNORECASE)),
    ("test_generation", re.compile(r"test|pytest|unittest|coverage|assert", re.IGNORECASE)),
    ("code_review", re.compile(r"review|diff|pr|pull.*request|merge", re.IGNORECASE)),
    ("refactor", re.compile(r"refactor|rename|reorganize|restructure|move.*file", re.IGNORECASE)),
    ("bug_fix", re.compile(r"bug|fix|error|issue|broken|wrong|incorrect", re.IGNORECASE)),
    ("project_understanding", re.compile(r"understand|explore|overview|structure|what.*is|how.*does", re.IGNORECASE)),
    ("performance_issue", re.compile(r"slow|performance|optimize|speed|latency|memory.*leak", re.IGNORECASE)),
    ("mcp_tool_development", re.compile(r"mcp.*tool|add.*tool|new.*tool|register.*tool|tool.*function", re.IGNORECASE)),
    ("cache_issue", re.compile(r"cache|stale|invalidat|clear.*cache|rebuild", re.IGNORECASE)),
]


def _classify_task_for_recommendation(task: str) -> str:
    for task_type, pattern in _TASK_CLASSIFICATION_PATTERNS:
        if pattern.search(task):
            return task_type
    return "unknown"


def _get_tools_for_task_type(task_type: str) -> list[str]:
    routing = {
        "traceback_error": ["analyze_traceback_with_context", "read_file_around_line", "search_code", "suggest_debug_steps", "suggest_validation_plan"],
        "import_error": ["diagnose_import_error", "search_code", "detect_project_profile", "suggest_debug_steps"],
        "training_error": ["diagnose_training_error", "analyze_traceback_with_context", "search_code", "summarize_file", "suggest_minimal_repro"],
        "config_change": ["check_config_consistency", "search_code", "risk_check_before_edit", "suggest_validation_plan"],
        "test_generation": ["generate_unit_test_plan", "suggest_minimal_repro", "extract_symbols", "suggest_validation_plan"],
        "code_review": ["review_diff", "analyze_change_impact", "post_edit_review", "suggest_validation_plan"],
        "refactor": ["risk_check_before_edit", "analyze_change_impact", "search_code", "post_edit_review"],
        "bug_fix": ["search_code", "read_file_around_line", "extract_symbols", "suggest_debug_steps", "suggest_validation_plan"],
        "project_understanding": ["get_codex_onboarding_pack", "build_project_map", "build_project_profile_v2", "summarize_directory", "summarize_file"],
        "performance_issue": ["search_code", "extract_symbols", "summarize_file", "suggest_debug_steps"],
        "mcp_tool_development": ["explain_project_conventions", "build_project_map", "extract_symbols", "review_diff"],
        "cache_issue": ["cache_status", "clear_cache", "rebuild_project_index", "export_perf_report"],
        "unknown": ["get_codex_onboarding_pack", "search_code", "build_project_map"],
    }
    return routing.get(task_type, routing["unknown"])


def recommend_workflow_for_task_logic(
    task_description: str,
    use_llm: bool = False,
) -> str:
    if not task_description or not task_description.strip():
        return "[Error] task_description must not be empty"

    task_type = _classify_task_for_recommendation(task_description)
    tools = _get_tools_for_task_type(task_type)

    confidence = "medium"
    if task_type != "unknown":
        confidence = "high"

    parts = ["Recommended Workflow", ""]
    parts.append(f"Task: {task_description[:200]}")
    parts.append(f"Task type: {task_type}")
    parts.append(f"Confidence: {confidence}")
    parts.append("")

    parts.append("Suggested MCP tool sequence:")
    for i, tool in enumerate(tools, 1):
        parts.append(f"  {i}. {tool}")
    parts.append("")

    files = _get_relevant_files_for_task(task_type)
    if files:
        parts.append("Suggested files to inspect first:")
        for f in files:
            parts.append(f"  - {f}")
        parts.append("")

    parts.append(f"Why: task classified as '{task_type}' based on keyword matching")
    parts.append("")

    donts = _get_donts_for_task(task_type)
    if donts:
        parts.append("What not to do first:")
        for d in donts:
            parts.append(f"  - {d}")
        parts.append("")

    parts.append("Need user confirmation:")
    parts.append("  - Confirm task classification is correct")
    parts.append("  - Confirm suggested tool sequence fits the actual problem")

    result = "\n".join(parts)

    if use_llm:
        try:
            from cheap_agent.llm_client import ask_llm
            llm_result = ask_llm("Review and refine this workflow recommendation. Keep it concise.", f"Workflow:\n{result}", max_tokens=256)
            result = result + "\n\nLLM Refinement:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    return truncate(result, MAX_OUTPUT_CHARS)


def _get_relevant_files_for_task(task_type: str) -> list[str]:
    files = {
        "traceback_error": ["the file mentioned in the traceback"],
        "import_error": ["requirements.txt", "pyproject.toml", "the file with the import"],
        "training_error": ["train.py", "config.py", "dataset.py", "model.py"],
        "config_change": ["config.py", ".env.example", "configs/"],
        "test_generation": ["the file to test", "test_*.py"],
        "code_review": ["the changed files"],
        "refactor": ["the files to refactor"],
        "bug_fix": ["the file with the bug"],
        "project_understanding": ["README.md", "server.py", "config.py"],
        "performance_issue": ["the slow code path"],
        "mcp_tool_development": ["server.py", "tools_*.py", "prompts.py"],
        "cache_issue": [".code_agent_cache/", "cache_manager.py"],
    }
    return files.get(task_type, [])


def _get_donts_for_task(task_type: str) -> list[str]:
    donts = {
        "traceback_error": ["Don't modify code before understanding the root cause"],
        "import_error": ["Don't install packages without checking version compatibility"],
        "training_error": ["Don't blindly change model architecture", "Don't change config without checking data"],
        "config_change": ["Don't modify .env without updating .env.example"],
        "test_generation": ["Don't create tests without understanding the target function"],
        "code_review": ["Don't approve without checking for missing syncs"],
        "bug_fix": ["Don't fix symptoms without finding root cause"],
        "project_understanding": ["Don't start coding without understanding the structure"],
    }
    return donts.get(task_type, [])


# ---------------------------------------------------------------------------
# explain_project_conventions
# ---------------------------------------------------------------------------

def explain_project_conventions_logic(
    use_llm: bool = True,
) -> str:
    cache_key = make_cache_key(["conventions", str(use_llm), LLM_MODEL, str(CACHE_SCHEMA_VERSION)])
    if ENABLE_CONVENTIONS_CACHE:
        cached = get_disk_cache("conventions", cache_key, ttl_sec=CONVENTIONS_CACHE_TTL_SEC)
        if cached and isinstance(cached, str):
            return cached

    file_index = get_file_index_cached()
    paths = [f["path"] for f in file_index]

    server_content = _safe_read_file("server.py", 2000)
    config_content = _safe_read_file("config.py", 2000)

    parts = ["Project Conventions", ""]

    tool_files = [p for p in paths if p.startswith("tools_") and p.endswith(".py")]
    parts.append("MCP tools:")
    parts.append("  - Tools are registered in server.py")
    parts.append(f"  - Logic functions live in {', '.join(tool_files) if tool_files else 'tools_*.py'}")
    parts.append("  - Tool functions should return strings")
    parts.append("  - Do not print to stdout (stdio MCP)")
    parts.append("")

    parts.append("Workspace safety:")
    parts.append("  - All paths must pass resolve_safe_path()")
    parts.append("  - No file access outside WORKSPACE_ROOT")
    parts.append("  - No shell execution allowed")
    parts.append("")

    parts.append("Logging:")
    parts.append("  - Use stderr or logging module")
    parts.append("  - Do not pollute stdout")
    parts.append("")

    parts.append("Cache:")
    parts.append("  - Only write under .code_agent_cache/")
    parts.append("  - Mask secrets before caching")
    parts.append("  - Use cache_manager.py for disk cache")
    parts.append("")

    test_files = [p for p in paths if p.startswith("test_") and p.endswith(".py")]
    parts.append("Testing:")
    parts.append(f"  - Test files: {', '.join(test_files) if test_files else 'test_*.py'}")
    parts.append("  - Logic functions are tested directly")
    parts.append("  - Use pytest conventions")
    parts.append("")

    parts.append("Configuration:")
    parts.append("  - Read via config.py using os.getenv()")
    parts.append("  - Defaults defined in config.py")
    parts.append("  - Document in .env.example")
    parts.append("")

    parts.append("LLM prompts:")
    parts.append("  - Stored in prompts.py")
    parts.append("  - Use BASE_RULES as foundation")
    parts.append("  - Each tool category has its own prompt")
    parts.append("")

    parts.append("When adding new tools:")
    parts.append("  1. Add logic in tools_xxx.py")
    parts.append("  2. Register MCP tool in server.py")
    parts.append("  3. Add prompt in prompts.py if LLM is used")
    parts.append("  4. Add config items if needed")
    parts.append("  5. Add tests in test_xxx.py")
    parts.append("  6. Update README.md")
    parts.append("")

    parts.append("Error handling:")
    parts.append("  - Use _safe_call() wrapper in server.py")
    parts.append("  - Return error strings, don't raise exceptions to MCP")
    parts.append("  - Log errors to stderr")
    parts.append("")

    parts.append("Output format:")
    parts.append("  - Structured text with headers and bullet points")
    parts.append("  - Truncate at MAX_OUTPUT_CHARS")
    parts.append("  - Include evidence and confidence when possible")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_CONVENTIONS:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import PROJECT_CONVENTIONS_SYSTEM_PROMPT
            llm_result = ask_llm(PROJECT_CONVENTIONS_SYSTEM_PROMPT, f"Conventions:\n{result}", max_tokens=512)
            result = result + "\n\nLLM Notes:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_CONVENTIONS_CACHE:
        set_disk_cache("conventions", cache_key, result, ttl_sec=CONVENTIONS_CACHE_TTL_SEC, tool="explain_project_conventions")

    return truncate(result, MAX_OUTPUT_CHARS)
