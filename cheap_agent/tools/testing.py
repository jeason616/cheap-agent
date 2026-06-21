import re
import sys
from pathlib import Path

from cheap_agent.tools._common import truncate
from cheap_agent.cache import get_cache, make_hash, set_cache
from cheap_agent.config import (
    ENABLE_LLM_TESTING,
    ENABLE_TESTING_CACHE,
    MASK_SECRET_VALUES,
    MAX_CHANGED_FILES_FOR_VALIDATION,
    MAX_CONFIG_FILES_TO_CHECK,
    MAX_FILE_CHARS,
    MAX_OUTPUT_CHARS,
    MAX_REPRO_CONTEXT_FILES,
    TESTING_CACHE_TTL_SEC,
    WORKSPACE_ROOT,
)
from cheap_agent.workspace import get_project_files_cached, get_relative_path, resolve_safe_path



_SECRET_PATTERNS = [
    re.compile(r"(?i)(api_key|token|secret|password|credential|auth)\s*[=:]\s*\S+"),
]


def _mask_secrets(text: str) -> str:
    if not MASK_SECRET_VALUES:
        return text
    for pat in _SECRET_PATTERNS:
        text = pat.sub(lambda m: m.group().split("=")[0].split(":")[0] + "=***MASKED***", text)
    return text


def _file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# suggest_minimal_repro
# ---------------------------------------------------------------------------

def suggest_minimal_repro_logic(
    problem_description: str,
    error_log: str = "",
    related_file: str = "",
    use_llm: bool = True,
) -> str:
    if not problem_description or not problem_description.strip():
        return "[Error] problem_description must not be empty"

    cache_key = f"repro:{make_hash(problem_description + error_log + related_file)}:{use_llm}"
    if ENABLE_TESTING_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    file_info = ""
    if related_file:
        try:
            target = resolve_safe_path(related_file)
            if target.is_file():
                from cheap_agent.tools.reading import extract_symbols_logic
                from cheap_agent.tools.project import summarize_file_logic
                symbols = extract_symbols_logic(related_file)
                summary = summarize_file_logic(related_file, use_llm=False)
                file_info = f"Related file: {related_file}\n\n{summary}\n\n{symbols}"
            else:
                file_info = f"[Warning] File not found: {related_file}"
        except (PermissionError, FileNotFoundError, ValueError) as e:
            file_info = f"[Warning] {e}"

    error_analysis = ""
    if error_log:
        try:
            from cheap_agent.tools.diagnostics import parse_python_traceback
            parsed = parse_python_traceback(error_log)
            if parsed["has_traceback"]:
                frames = parsed["classified"]["project_frames"]
                if frames:
                    error_analysis = f"Error: {parsed['error_type']}: {parsed['error_message']}\n"
                    error_analysis += f"Last project frame: {frames[-1]['file']}:{frames[-1]['line']} in {frames[-1]['function']}()"
        except Exception:
            pass

    parts = ["Minimal Reproduction Plan", ""]
    parts.append(f"Problem: {problem_description[:300]}")
    parts.append("")

    area = _classify_repro_area(problem_description, error_log)
    parts.append(f"Likely target: {area}")
    parts.append("")

    inputs = _suggest_minimal_inputs(area, problem_description, error_log)
    parts.append("Minimal inputs:")
    for inp in inputs:
        parts.append(f"  - {inp}")
    parts.append("")

    outline = _generate_repro_outline(area, related_file, problem_description)
    parts.append("Suggested repro script outline:")
    for i, step in enumerate(outline, 1):
        parts.append(f"  {i}. {step}")
    parts.append("")

    fname = _suggest_repro_filename(area, related_file)
    parts.append(f"Suggested filename: {fname}")
    parts.append("")

    parts.append("What to avoid:")
    parts.append("  - Don't load full datasets")
    parts.append("  - Don't start full training pipeline")
    parts.append("  - Don't depend on large weight files")
    parts.append("  - Don't modify original project code")
    parts.append("")

    if file_info:
        parts.append(f"File info:\n{file_info[:1000]}")
        parts.append("")

    if error_analysis:
        parts.append(f"Error analysis:\n{error_analysis}")
        parts.append("")

    parts.append("Notes for Codex:")
    if related_file:
        parts.append(f"  - Read {related_file} to understand the target function/class")
    parts.append("  - Create the repro script at the suggested filename")
    parts.append("  - Run the script to observe the error behavior")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_TESTING:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import MINIMAL_REPRO_SYSTEM_PROMPT
            llm_input = f"Repro analysis:\n{result}"
            if error_log:
                llm_input += f"\n\nError log:\n{error_log[:1500]}"
            llm_result = ask_llm(MINIMAL_REPRO_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Suggestions:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_TESTING_CACHE:
        set_cache(cache_key, result, TESTING_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _classify_repro_area(problem: str, error_log: str) -> str:
    combined = (problem + " " + error_log).lower()
    if any(w in combined for w in ["forward", "model", "layer", "network"]):
        return "model forward / network layer"
    if any(w in combined for w in ["dataloader", "dataset", "batch", "data"]):
        return "data loading / dataset"
    if any(w in combined for w in ["config", "yaml", "setting", "parameter"]):
        return "configuration"
    if any(w in combined for w in ["loss", "nan", "gradient"]):
        return "loss / training loop"
    if any(w in combined for w in ["transform", "augment", "preprocess"]):
        return "data transforms"
    if any(w in combined for w in ["import", "module"]):
        return "import / module"
    return "unknown function / script"


def _suggest_minimal_inputs(area: str, problem: str, error_log: str) -> list[str]:
    inputs = {
        "model forward / network layer": [
            "Dummy input tensor: torch.randn(batch_size, channels, height, width)",
            "Minimal model config (just enough to instantiate)",
            "No pretrained weights needed",
        ],
        "data loading / dataset": [
            "2-5 sample files (images/annotations)",
            "Minimal data.yaml or config with correct paths",
            "Small batch_size=2",
        ],
        "configuration": [
            "Minimal config dict with only required fields",
            "Test with missing/extra keys",
        ],
        "loss / training loop": [
            "Dummy predictions: torch.randn(batch_size, num_classes)",
            "Dummy targets: torch.randint(0, num_classes, (batch_size,))",
            "Minimal model that outputs correct shape",
        ],
        "data transforms": [
            "Single sample image (PIL or numpy)",
            "Minimal transform pipeline",
        ],
        "import / module": [
            "Just the import statement",
            "Check if module is installed",
        ],
    }
    return inputs.get(area, ["Minimal input that triggers the target code path"])


def _generate_repro_outline(area: str, related_file: str, problem: str) -> list[str]:
    outlines = {
        "model forward / network layer": [
            "Import the model class",
            "Instantiate with minimal config (no weights)",
            "Create dummy input tensor",
            "Call model.forward(dummy_input)",
            "Print output shape and values",
            "Assert expected shape",
        ],
        "data loading / dataset": [
            "Import dataset class",
            "Create minimal dataset with 2-5 samples",
            "Create DataLoader with batch_size=2",
            "Iterate one batch",
            "Print batch shapes and types",
            "Assert expected shapes",
        ],
        "configuration": [
            "Import config loading function",
            "Create minimal config dict",
            "Call config loading",
            "Print loaded config",
            "Assert required keys exist",
        ],
        "loss / training loop": [
            "Import loss function",
            "Create dummy predictions and targets",
            "Compute loss",
            "Print loss value",
            "Assert loss is finite (not NaN/Inf)",
        ],
        "data transforms": [
            "Import transform",
            "Create single sample",
            "Apply transform",
            "Print output shape and dtype",
            "Assert expected output",
        ],
        "import / module": [
            "Try importing the module",
            "Print module version if available",
            "Check if key classes/functions exist",
        ],
    }
    return outlines.get(area, [
        "Import target function/class",
        "Construct minimal input",
        "Call target logic",
        "Print key intermediate results",
        "Observe expected behavior",
    ])


def _suggest_repro_filename(area: str, related_file: str) -> str:
    if related_file:
        stem = Path(related_file).stem
        return f"scripts/repro_{stem}.py"
    return "scripts/repro_issue.py"


# ---------------------------------------------------------------------------
# generate_unit_test_plan
# ---------------------------------------------------------------------------

def generate_unit_test_plan_logic(
    file_path: str,
    target_symbol: str = "",
    test_goal: str = "",
    use_llm: bool = True,
) -> str:
    target = resolve_safe_path(file_path)
    if not target.is_file():
        return f"[Error] File not found: {file_path}"

    cache_key = f"test_plan:{file_path}:{target_symbol}:{use_llm}"
    if ENABLE_TESTING_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    from cheap_agent.tools.reading import extract_symbols_logic
    symbols = extract_symbols_logic(file_path)

    symbol_info = ""
    if target_symbol:
        found = False
        for line in symbols.split("\n"):
            if target_symbol in line and "line" in line.lower():
                symbol_info = line.strip()
                found = True
                break
        if not found:
            symbol_info = f"Symbol '{target_symbol}' not found in extracted symbols"

    rel = get_relative_path(target)
    test_file = f"tests/test_{target.stem}.py"

    parts = ["Unit Test Plan", ""]
    parts.append(f"Target file: {rel}")
    if target_symbol:
        parts.append(f"Target symbol: {target_symbol}")
    if symbol_info:
        parts.append(f"Symbol info: {symbol_info}")
    if test_goal:
        parts.append(f"Test goal: {test_goal}")
    parts.append(f"Recommended test file: {test_file}")
    parts.append("")

    if target_symbol:
        cases = _generate_symbol_test_cases(target_symbol, test_goal)
    else:
        cases = _generate_file_test_cases(symbols, test_goal)

    parts.append("Core test cases:")
    for i, case in enumerate(cases, 1):
        parts.append(f"  {i}. {case}")
    parts.append("")

    parts.append("Expected checks:")
    parts.append("  - Output type and value range")
    parts.append("  - Expected exceptions for invalid inputs")
    parts.append("  - Side effects (file writes, state changes)")
    parts.append("  - Edge cases (empty, None, zero, negative, overflow)")
    parts.append("")

    parts.append("Mocking / fixtures:")
    if any(w in symbols.lower() for w in ["open(", "pathlib", "file", "read", "write"]):
        parts.append("  - May need to mock file I/O")
    if any(w in symbols.lower() for w in ["requests", "urllib", "http", "api"]):
        parts.append("  - May need to mock network calls")
    if any(w in symbols.lower() for w in ["torch", "cuda", "gpu", "device"]):
        parts.append("  - May need to mock CUDA/device")
    parts.append("  - Use pytest fixtures for common test data")
    parts.append("")

    parts.append(f"Notes for Codex:")
    parts.append(f"  - Read {rel} to understand function signatures")
    if target_symbol:
        parts.append(f"  - Focus on testing {target_symbol} behavior")
    parts.append(f"  - Create {test_file} with the test cases above")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_TESTING:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import UNIT_TEST_PLAN_SYSTEM_PROMPT
            llm_input = f"Test plan:\n{result}\n\nFile symbols:\n{symbols[:2000]}"
            if test_goal:
                llm_input += f"\n\nTest goal: {test_goal}"
            llm_result = ask_llm(UNIT_TEST_PLAN_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Suggestions:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_TESTING_CACHE:
        set_cache(cache_key, result, TESTING_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _generate_symbol_test_cases(symbol: str, goal: str) -> list[str]:
    return [
        f"Normal input: valid arguments that {symbol} should handle",
        f"Empty/None input: test {symbol} with empty or None arguments",
        f"Boundary values: min/max valid values for numeric arguments",
        f"Invalid input: wrong types, out-of-range values",
        f"Return value: check type, range, and correctness",
        f"Exceptions: verify expected exceptions are raised",
    ]


def _generate_file_test_cases(symbols: str, goal: str) -> list[str]:
    cases = [
        "Test each public function with normal inputs",
        "Test each public function with empty/None inputs",
        "Test boundary values for numeric parameters",
        "Test invalid inputs (wrong types, out-of-range)",
        "Test return values and types",
        "Test expected exceptions",
    ]
    if "class" in symbols.lower():
        cases.append("Test class instantiation and methods")
    if "main" in symbols.lower():
        cases.append("Test main entry point behavior")
    return cases


# ---------------------------------------------------------------------------
# check_config_consistency
# ---------------------------------------------------------------------------

def check_config_consistency_logic(
    config_path: str = "",
    code_hint: str = "",
    use_llm: bool = True,
) -> str:
    cache_key = f"config_check:{make_hash(config_path + code_hint)}:{use_llm}"
    if ENABLE_TESTING_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    config_files = _find_config_files()
    if config_path:
        try:
            target = resolve_safe_path(config_path)
            if target.is_file():
                rel = get_relative_path(target)
                if rel not in config_files:
                    config_files = [rel] + config_files
        except (PermissionError, FileNotFoundError, ValueError) as e:
            return f"[Error] {e}"

    config_files = config_files[:MAX_CONFIG_FILES_TO_CHECK]

    env_keys: set[str] = set()
    config_py_keys: set[str] = set()
    yaml_keys: set[str] = set()
    issues: list[str] = []

    for cf in config_files:
        if cf == ".env.example":
            env_keys = _extract_env_keys(cf)
        elif cf == "config.py":
            config_py_keys = _extract_config_py_keys(cf)
        elif cf.endswith((".yaml", ".yml")):
            yaml_keys.update(_extract_yaml_keys(cf))

    if env_keys and config_py_keys:
        in_env_not_config = env_keys - config_py_keys
        in_config_not_env = config_py_keys - env_keys
        if in_env_not_config:
            issues.append(f".env.example has keys not read by config.py: {', '.join(sorted(in_env_not_config)[:10])}")
        if in_config_not_env:
            issues.append(f"config.py reads keys not in .env.example: {', '.join(sorted(in_config_not_env)[:10])}")

    if yaml_keys and "names" in yaml_keys and "nc" in yaml_keys:
        issues.append("data.yaml has both 'names' and 'nc' — verify they are consistent")

    parts = ["Config Consistency Check", ""]
    parts.append("Checked files:")
    for cf in config_files:
        parts.append(f"  - {cf}")
    parts.append("")

    if env_keys:
        parts.append(f"Detected .env.example keys ({len(env_keys)}):")
        for k in sorted(env_keys)[:15]:
            parts.append(f"  - {k}")
        parts.append("")

    if config_py_keys:
        parts.append(f"Detected config.py keys ({len(config_py_keys)}):")
        for k in sorted(config_py_keys)[:15]:
            parts.append(f"  - {k}")
        parts.append("")

    if issues:
        parts.append("Potential inconsistencies:")
        for i, issue in enumerate(issues, 1):
            parts.append(f"  {i}. {issue}")
        parts.append("")
    else:
        parts.append("No obvious inconsistencies found.")
        parts.append("")

    parts.append("Suggested checks:")
    parts.append("  1. Verify all .env.example keys are read in config.py")
    parts.append("  2. Verify all config.py keys have defaults or are in .env.example")
    parts.append("  3. Check YAML config fields match code expectations")
    parts.append("  4. Check requirements.txt has all imported packages")
    parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Config keys may be environment-specific, don't blindly change")
    parts.append("  - Check if missing keys have defaults in config.py")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_TESTING:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import CONFIG_CONSISTENCY_SYSTEM_PROMPT
            llm_input = f"Config consistency check:\n{result}"
            if code_hint:
                llm_input += f"\n\nCode hint: {code_hint}"
            llm_result = ask_llm(CONFIG_CONSISTENCY_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Suggestions:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_TESTING_CACHE:
        set_cache(cache_key, result, TESTING_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _find_config_files() -> list[str]:
    files = get_project_files_cached(max_files=500)
    config_files = []
    for f in files:
        fname = Path(f).name.lower()
        ext = Path(f).suffix.lower()
        if fname in (".env.example", "config.py", "pyproject.toml", "requirements.txt", "data.yaml"):
            config_files.append(f)
        elif ext in (".yaml", ".yml", ".json", ".toml", ".ini"):
            if any(d in f.lower() for d in ["config", "setting", "conf"]):
                config_files.append(f)
    return config_files[:MAX_CONFIG_FILES_TO_CHECK]


def _extract_env_keys(file_path: str) -> set[str]:
    keys = set()
    try:
        target = resolve_safe_path(file_path)
        content = target.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=")[0].strip()
                if key:
                    keys.add(key)
    except Exception:
        pass
    return keys


def _extract_config_py_keys(file_path: str) -> set[str]:
    keys = set()
    try:
        target = resolve_safe_path(file_path)
        content = target.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            m = re.match(r'^(\w+)\s*[:=]', line.strip())
            if m and m.group(1).isupper():
                keys.add(m.group(1))
    except Exception:
        pass
    return keys


def _extract_yaml_keys(file_path: str) -> set[str]:
    keys = set()
    try:
        target = resolve_safe_path(file_path)
        content = target.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            m = re.match(r'^(\w+)\s*:', line.strip())
            if m:
                keys.add(m.group(1))
    except Exception:
        pass
    return keys


# ---------------------------------------------------------------------------
# suggest_validation_plan
# ---------------------------------------------------------------------------

def suggest_validation_plan_logic(
    task_description: str,
    changed_files: str = "",
    error_log: str = "",
    use_llm: bool = True,
) -> str:
    if not task_description or not task_description.strip():
        return "[Error] task_description must not be empty"

    cache_key = f"validation:{make_hash(task_description + changed_files + error_log)}:{use_llm}"
    if ENABLE_TESTING_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    parsed_files = [f.strip() for f in changed_files.splitlines() if f.strip()]
    parsed_files = parsed_files[:MAX_CHANGED_FILES_FOR_VALIDATION]

    file_infos: list[dict] = []
    for f in parsed_files:
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

    risk = _assess_risk(task_description, parsed_files, error_log)

    parts = ["Validation Plan", ""]
    parts.append(f"Task: {task_description[:200]}")
    parts.append("")

    if parsed_files:
        parts.append("Changed files:")
        for fi in file_infos:
            status = "exists" if fi["exists"] else "NOT FOUND"
            parts.append(f"  - {fi['path']} ({status})")
        parts.append("")

    parts.append(f"Risk level: {risk}")
    parts.append("")

    verify_items = _generate_verify_items(task_description, parsed_files, risk)
    parts.append("What to verify:")
    for i, item in enumerate(verify_items, 1):
        parts.append(f"  {i}. {item}")
    parts.append("")

    checks = _generate_suggested_checks(task_description, parsed_files, risk)
    parts.append("Suggested checks:")
    for i, check in enumerate(checks, 1):
        parts.append(f"  {i}. {check}")
    parts.append("")

    commands = _suggest_commands(task_description, parsed_files)
    parts.append("Suggested commands (do NOT execute automatically):")
    for cmd in commands:
        parts.append(f"  - {cmd}")
    parts.append("")

    parts.append("Manual review points:")
    parts.append("  - Verify the change matches the task goal")
    parts.append("  - Check for unintended side effects")
    parts.append("  - Confirm no existing tests are broken")
    parts.append("")

    parts.append("Notes for Codex:")
    parts.append("  - Static checks can be done by reading files")
    parts.append("  - Commands should be confirmed by user before running")
    if parsed_files:
        parts.append(f"  - Read changed files to understand the modifications")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_TESTING:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import VALIDATION_PLAN_SYSTEM_PROMPT
            llm_input = f"Validation plan:\n{result}"
            if error_log:
                llm_input += f"\n\nError log:\n{error_log[:1000]}"
            llm_result = ask_llm(VALIDATION_PLAN_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Suggestions:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_TESTING_CACHE:
        set_cache(cache_key, result, TESTING_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _assess_risk(task: str, files: list[str], error_log: str) -> str:
    combined = (task + " " + " ".join(files)).lower()
    if any(w in combined for w in ["config", "setting", "env", "model", "loss", "train"]):
        return "high"
    if len(files) > 5:
        return "high"
    if any(w in combined for w in ["test", "doc", "readme", "comment"]):
        return "low"
    if len(files) <= 2:
        return "low"
    return "medium"


def _generate_verify_items(task: str, files: list[str], risk: str) -> list[str]:
    items = [
        "Target functionality is complete",
        "Configuration is consistent",
        "No import errors introduced",
    ]
    if risk in ("medium", "high"):
        items.append("No training/inference flow broken")
        items.append("Tests or documentation may need updates")
    if risk == "high":
        items.append("Check for side effects on other modules")
        items.append("Verify data pipeline integrity")
    return items


def _generate_suggested_checks(task: str, files: list[str], risk: str) -> list[str]:
    checks = [
        "Static: read changed files, verify fields/functions exist",
        "Unit: test modified functions with normal and edge inputs",
    ]
    if risk in ("medium", "high"):
        checks.append("Minimal repro: construct small input to verify behavior")
        checks.append("Integration: run entry script with small config")
    return checks


def _suggest_commands(task: str, files: list[str]) -> list[str]:
    commands = []
    if any(f.endswith(".py") for f in files):
        commands.append("python -m pytest tests/ -x -v  # run tests, stop on first failure")
    if any(f.endswith((".yaml", ".yml", ".json", ".toml")) for f in files):
        commands.append("python -c \"import config; print('config OK')\"  # verify config loads")
    if any("train" in f.lower() for f in files):
        commands.append("python train.py --help  # verify train script loads")
    if any("server" in f.lower() for f in files):
        commands.append("python server.py  # verify MCP server starts")
    if not commands:
        commands.append("python -m pytest tests/ -x -v")
    return commands
