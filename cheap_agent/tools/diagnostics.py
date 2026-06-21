import re
import sys
from pathlib import Path

from cheap_agent.tools._common import truncate
from cheap_agent.cache import get_cache, make_hash, set_cache
from cheap_agent.config import (
    DIAGNOSTIC_CACHE_TTL_SEC,
    ENABLE_DIAGNOSTIC_CACHE,
    ENABLE_LLM_DIAGNOSTICS,
    MAX_CONTEXT_LINES,
    MAX_OUTPUT_CHARS,
    MAX_TRACEBACK_CONTEXT_FILES,
    MAX_TRACEBACK_FRAMES,
    WORKSPACE_ROOT,
)
from cheap_agent.workspace import get_relative_path, resolve_safe_path



def _is_in_workspace(filepath: str) -> bool:
    try:
        p = Path(filepath).resolve()
        root = WORKSPACE_ROOT.resolve()
        return p == root or root in p.parents
    except Exception:
        return False


def _is_stdlib_or_site(filepath: str) -> bool:
    lower = filepath.lower().replace("\\", "/")
    markers = ["site-packages", "lib/python", "conda", "/usr/lib", "/usr/local/lib", "anaconda", "miniconda"]
    return any(m in lower for m in markers)


# ---------------------------------------------------------------------------
# parse_python_traceback
# ---------------------------------------------------------------------------

_TB_FRAME_RE = re.compile(
    r'^\s*File\s+"([^"]+)",\s+line\s+(\d+),?\s+in\s+(\S+)',
    re.MULTILINE,
)
_TB_ERROR_RE = re.compile(
    r'^(\w+(?:\.\w+)*(?:Error|Exception|Warning|Exit))\s*:\s*(.*)',
    re.MULTILINE,
)
_TB_CODE_RE = re.compile(
    r'^\s{4}(.+)$',
    re.MULTILINE,
)


def parse_python_traceback(error_log: str) -> dict:
    frames = extract_traceback_frames(error_log)
    error_match = _TB_ERROR_RE.search(error_log)
    error_type = error_match.group(1) if error_match else "Unknown"
    error_message = error_match.group(2).strip() if error_match else ""
    classified = classify_traceback_frames(frames)

    return {
        "error_type": error_type,
        "error_message": error_message,
        "frames": frames,
        "classified": classified,
        "has_traceback": len(frames) > 0,
    }


def extract_traceback_frames(error_log: str) -> list[dict]:
    frames = []
    lines = error_log.splitlines()
    max_frames = MAX_TRACEBACK_FRAMES

    for i, line in enumerate(lines):
        if len(frames) >= max_frames:
            break
        m = _TB_FRAME_RE.match(line)
        if m:
            filepath = m.group(1)
            lineno = int(m.group(2))
            func = m.group(3)
            code = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                cm = re.match(r'^\s{4}(.+)$', next_line)
                if cm:
                    code = cm.group(1).strip()

            frames.append({
                "file": filepath,
                "line": lineno,
                "function": func,
                "code": code,
                "is_in_workspace": _is_in_workspace(filepath),
                "is_stdlib_or_site": _is_stdlib_or_site(filepath),
            })

    return frames


def classify_traceback_frames(frames: list[dict]) -> dict:
    project_frames = [f for f in frames if f["is_in_workspace"] and not f["is_stdlib_or_site"]]
    external_frames = [f for f in frames if f["is_stdlib_or_site"] or not f["is_in_workspace"]]
    last_project = project_frames[-1] if project_frames else None
    last_frame = frames[-1] if frames else None
    return {
        "project_frames": project_frames,
        "external_frames": external_frames,
        "last_project_frame": last_project,
        "last_frame": last_frame,
    }


# ---------------------------------------------------------------------------
# analyze_traceback_with_context
# ---------------------------------------------------------------------------

def analyze_traceback_with_context_logic(
    error_log: str,
    context_lines: int = 60,
    use_llm: bool = True,
) -> str:
    if not error_log or not error_log.strip():
        return "[Error] error_log must not be empty"

    cache_key = f"traceback:{make_hash(error_log)}:{context_lines}:{use_llm}"
    if ENABLE_DIAGNOSTIC_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    parsed = parse_python_traceback(error_log)
    classified = parsed["classified"]
    project_frames = classified["project_frames"]

    parts = ["Traceback Summary", ""]
    parts.append(f"- Error type: {parsed['error_type']}")
    parts.append(f"- Error message: {parsed['error_message'][:200]}")
    parts.append(f"- Total frames: {len(parsed['frames'])}")
    parts.append(f"- Project frames: {len(project_frames)}")
    parts.append(f"- External frames: {len(classified['external_frames'])}")
    parts.append("")

    if classified["last_project_frame"]:
        f = classified["last_project_frame"]
        parts.append(f"- Last project frame: {f['file']}:{f['line']} in {f['function']}()")
        parts.append(f"  Code: {f['code']}")
    parts.append("")

    if project_frames:
        parts.append("Project frames:")
        for f in project_frames:
            parts.append(f"  - {f['file']}:{f['line']} in {f['function']}() -> {f['code']}")
        parts.append("")

    if classified["external_frames"]:
        parts.append("External frames (not read):")
        for f in classified["external_frames"][:5]:
            parts.append(f"  - {f['file']}:{f['line']} in {f['function']}()")
        parts.append("")

    context_lines = min(context_lines, MAX_CONTEXT_LINES)
    code_contexts: list[str] = []
    read_count = 0

    for f in project_frames:
        if read_count >= MAX_TRACEBACK_CONTEXT_FILES:
            break
        try:
            from cheap_agent.tools.reading import read_file_around_line_logic
            ctx = read_file_around_line_logic(f["file"], f["line"], context_lines)
            if not ctx.startswith("[Error]"):
                code_contexts.append(ctx)
                read_count += 1
        except Exception:
            pass

    if code_contexts:
        parts.append("Code Context:")
        for ctx in code_contexts:
            parts.append(ctx)
            parts.append("")
    else:
        parts.append("Code Context: (no project files could be read)")
        parts.append("")

    rule_diagnosis = _rule_diagnose_traceback(parsed)
    parts.append("Initial Diagnosis:")
    parts.append(rule_diagnosis)

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_DIAGNOSTICS:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import TRACEBACK_ANALYSIS_SYSTEM_PROMPT
            llm_input = f"Traceback analysis:\n{result}\n\nOriginal error log:\n{error_log[:2000]}"
            llm_result = ask_llm(TRACEBACK_ANALYSIS_SYSTEM_PROMPT, llm_input, max_tokens=1024)
            result = result + "\n\nLLM Diagnosis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_DIAGNOSTIC_CACHE:
        set_cache(cache_key, result, DIAGNOSTIC_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _rule_diagnose_traceback(parsed: dict) -> str:
    etype = parsed["error_type"]
    emsg = parsed["error_message"].lower()
    frames = parsed["classified"]["project_frames"]

    lines = []

    if "cuda" in emsg and "out of memory" in emsg:
        lines.append("- Likely cause: CUDA out of memory")
        lines.append("- Try reducing batch_size, image_size, or enabling AMP/mixed precision")
    elif "shape" in emsg or "size mismatch" in emsg or "mat1 and mat2" in emsg:
        lines.append("- Likely cause: tensor shape mismatch")
        lines.append("- Check model output dimensions vs loss/label dimensions")
    elif "module" in emsg and ("not found" in emsg or "no module" in emsg):
        lines.append("- Likely cause: missing module or wrong Python environment")
        lines.append("- Check requirements.txt and current Python environment")
    elif "import" in emsg:
        lines.append("- Likely cause: import error")
        lines.append("- Check module names, relative imports, and PYTHONPATH")
    elif "keyerror" in etype.lower():
        lines.append("- Likely cause: missing key in config or data dict")
        lines.append("- Check config files and data format")
    elif "indexerror" in etype.lower():
        lines.append("- Likely cause: index out of range")
        lines.append("- Check array/list bounds, dataset labels, class indices")
    elif "filenotfound" in etype.lower() or "no such file" in emsg:
        lines.append("- Likely cause: file path error")
        lines.append("- Check dataset paths, config paths, working directory")
    elif "typeerror" in etype.lower():
        lines.append("- Likely cause: wrong type or arguments")
        lines.append("- Check function signatures and data types")
    elif "valueerror" in etype.lower():
        lines.append("- Likely cause: invalid value")
        lines.append("- Check input data ranges, num_classes, config values")
    elif "runtimeerror" in etype.lower():
        lines.append("- Likely cause: runtime issue")
        lines.append("- Check device, tensor shapes, data format")
    else:
        lines.append(f"- Error type: {etype}")
        lines.append("- Check the traceback frames and code context above")

    if frames:
        lines.append(f"\n- Suggested first read: {frames[-1]['file']}:{frames[-1]['line']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# diagnose_import_error
# ---------------------------------------------------------------------------

_IMPORT_ERROR_PATTERNS = [
    (re.compile(r"No module named '?(\w+(?:\.\w+)*)'?", re.IGNORECASE), "module_not_found"),
    (re.compile(r"cannot import name '?(\w+)'? from '?([^'\"]+)'?", re.IGNORECASE), "import_name_error"),
    (re.compile(r"attempted relative import with no known parent package", re.IGNORECASE), "relative_import_error"),
    (re.compile(r"ModuleNotFoundError.*?(\w+)", re.IGNORECASE), "module_not_found"),
    (re.compile(r"ImportError.*?(\w+)", re.IGNORECASE), "import_error"),
    (re.compile(r"DLL load failed", re.IGNORECASE), "dll_error"),
    (re.compile(r"undefined symbol", re.IGNORECASE), "undefined_symbol"),
]


def _extract_missing_module(error_log: str) -> tuple[str, str]:
    for pat, kind in _IMPORT_ERROR_PATTERNS:
        m = pat.search(error_log)
        if m:
            groups = m.groups()
            module = groups[0] if groups else "unknown"
            return module, kind
    return "unknown", "unknown"


def _check_dep_files() -> list[str]:
    root = WORKSPACE_ROOT.resolve()
    found = []
    for name in ["requirements.txt", "pyproject.toml", "setup.py", "environment.yml", "Pipfile"]:
        if (root / name).exists():
            found.append(name)
    return found


def _search_module_in_project(module_name: str) -> list[str]:
    root = WORKSPACE_ROOT.resolve()
    matches = []
    parts = module_name.split(".")
    top = parts[0]

    for p in root.rglob(f"{top}.py"):
        try:
            rel = str(p.relative_to(root)).replace("\\", "/")
            if not any(d in rel for d in [".git", ".venv", "venv", "__pycache__", "node_modules"]):
                matches.append(rel)
        except ValueError:
            pass

    for p in root.rglob(f"{top}/__init__.py"):
        try:
            rel = str(p.relative_to(root)).replace("\\", "/")
            if not any(d in rel for d in [".git", ".venv", "venv", "__pycache__", "node_modules"]):
                matches.append(rel.replace("/__init__.py", "/"))
        except ValueError:
            pass

    return matches[:5]


def diagnose_import_error_logic(
    error_log: str,
    use_llm: bool = True,
) -> str:
    if not error_log or not error_log.strip():
        return "[Error] error_log must not be empty"

    cache_key = f"import_err:{make_hash(error_log)}:{use_llm}"
    if ENABLE_DIAGNOSTIC_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    parsed = parse_python_traceback(error_log)
    module_name, kind = _extract_missing_module(error_log)
    dep_files = _check_dep_files()
    project_matches = _search_module_in_project(module_name)

    parts = ["Import Error Diagnosis", ""]
    parts.append(f"- Error type: {parsed['error_type']}")
    parts.append(f"- Missing/conflicting module: {module_name}")
    parts.append(f"- Error kind: {kind}")
    parts.append("")

    parts.append("Likely Causes:")
    causes = _rule_diagnose_import(kind, module_name, project_matches, dep_files)
    for i, cause in enumerate(causes, 1):
        parts.append(f"  {i}. {cause}")
    parts.append("")

    parts.append("Evidence:")
    parts.append(f"  - Error message: {parsed['error_message'][:200]}")
    if project_matches:
        parts.append(f"  - Found in project: {', '.join(project_matches)}")
    else:
        parts.append(f"  - Module '{module_name}' NOT found in project")
    parts.append(f"  - Dependency files: {', '.join(dep_files) if dep_files else '(none found)'}")
    parts.append("")

    parts.append("Suggested Checks:")
    parts.append("  1. Check current Python environment (which python, pip list)")
    parts.append("  2. Check requirements.txt / pyproject.toml for the module")
    parts.append("  3. Check working directory (os.getcwd())")
    parts.append("  4. Check PYTHONPATH")
    parts.append("  5. Check for filename conflicts (module name vs local file)")
    parts.append("")

    if parsed["classified"]["project_frames"]:
        f = parsed["classified"]["project_frames"][-1]
        parts.append(f"Notes for Codex: first check {f['file']}:{f['line']} in {f['function']}()")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_DIAGNOSTICS:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import IMPORT_ERROR_SYSTEM_PROMPT
            llm_input = f"Import error analysis:\n{result}\n\nOriginal error log:\n{error_log[:2000]}"
            llm_result = ask_llm(IMPORT_ERROR_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Diagnosis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_DIAGNOSTIC_CACHE:
        set_cache(cache_key, result, DIAGNOSTIC_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _rule_diagnose_import(kind: str, module: str, project_matches: list[str], dep_files: list[str]) -> list[str]:
    causes = []

    if kind == "relative_import_error":
        causes.append("Relative import used but package structure is wrong or script run directly")
        causes.append("Try running as module: python -m package.module")
    elif kind == "dll_error":
        causes.append("Binary library load failed — check if the correct version is installed")
        causes.append("May need to reinstall the package or check system dependencies")
    elif kind == "undefined_symbol":
        causes.append("Compiled extension has ABI mismatch — reinstall with matching Python/CUDA version")
    else:
        if not dep_files:
            causes.append("No requirements.txt or pyproject.toml found — dependencies may not be tracked")
        if project_matches:
            causes.append(f"Module '{module}' exists in project — may be a path/PYTHONPATH issue")
            causes.append("Check if the working directory or PYTHONPATH includes the module location")
        else:
            causes.append(f"Module '{module}' not found in project — likely needs pip install")
            if dep_files:
                causes.append(f"Check if '{module}' is listed in {dep_files[0]}")
        causes.append("Check if the correct Python environment/virtualenv is activated")
        causes.append("Check if there's a local file named the same as the module (shadowing)")

    return causes


# ---------------------------------------------------------------------------
# diagnose_training_error
# ---------------------------------------------------------------------------

_TRAINING_ERROR_CATEGORIES = [
    ("cuda_oom", re.compile(r"cuda.*out of memory|OOM|CUDA error.*no memory", re.IGNORECASE)),
    ("shape_mismatch", re.compile(r"shape mismatch|size mismatch|mat1 and mat2|cannot be multiplied|dimension|shapes .* not aligned", re.IGNORECASE)),
    ("device_error", re.compile(r"expected all tensors.*same device|tensor.*device.*cpu.*cuda|cuda.*cpu", re.IGNORECASE)),
    ("dtype_error", re.compile(r"dtype.*mismatch|expected.*float.*got.*int|expected.*int.*got.*float", re.IGNORECASE)),
    ("dataloader_error", re.compile(r"RuntimeError.*stack expects.*equal size|IndexError.*dataloader|num_workers|pin_memory", re.IGNORECASE)),
    ("dataset_path_error", re.compile(r"FileNotFoundError.*dataset|No such file.*images|dataset.*not found|path.*not exist", re.IGNORECASE)),
    ("label_format_error", re.compile(r"label.*format|annotation.*error|class.*index.*out of|num_classes|classes.*mismatch", re.IGNORECASE)),
    ("nan_loss", re.compile(r"loss.*nan|loss.*inf|nan.*loss|gradient.*nan", re.IGNORECASE)),
    ("num_classes_error", re.compile(r"num_classes.*mismatch|classes.*must be|out_channels.*mismatch", re.IGNORECASE)),
    ("config_error", re.compile(r"KeyError.*config|yaml.*error|config.*missing|attribute.*not found", re.IGNORECASE)),
    ("dependency_error", re.compile(r"module.*not found|import.*error|no module named", re.IGNORECASE)),
]


def _classify_training_error(error_log: str) -> str:
    for category, pattern in _TRAINING_ERROR_CATEGORIES:
        if pattern.search(error_log):
            return category
    return "unknown_training_error"


def _training_error_suggestions(category: str) -> list[str]:
    suggestions = {
        "cuda_oom": [
            "Reduce batch_size",
            "Reduce image_size / input dimensions",
            "Enable AMP / mixed precision (amp=True)",
            "Reduce num_workers",
            "Use gradient accumulation",
            "Check for memory leaks (tensors not freed)",
        ],
        "shape_mismatch": [
            "Check model output shape vs loss input shape",
            "Check num_classes in config vs model head",
            "Check label format and dimensions",
            "Check data transforms (resize, crop) consistency",
        ],
        "device_error": [
            "Ensure all tensors are on the same device (CPU or CUDA)",
            "Check model.to(device) and data.to(device)",
            "Check loss function device",
        ],
        "dtype_error": [
            "Check input data dtype (float32 vs float16 vs int64)",
            "Check model weight dtype",
            "Check label dtype (long for classification, float for regression)",
        ],
        "dataloader_error": [
            "Check dataset __getitem__ return shapes are consistent",
            "Check collate_fn if using custom batching",
            "Check num_workers (try 0 for debugging)",
            "Check if all samples have the same shape",
        ],
        "dataset_path_error": [
            "Check dataset root path in config",
            "Check relative vs absolute paths",
            "Check working directory",
            "Check if dataset files exist at the specified location",
        ],
        "label_format_error": [
            "Check label class indices (should be 0-indexed)",
            "Check num_classes matches actual classes",
            "Check annotation format (COCO, YOLO, VOC)",
            "Check label file encoding and format",
        ],
        "nan_loss": [
            "Check learning rate (too high can cause NaN)",
            "Check input data for NaN/Inf values",
            "Check label values (invalid indices)",
            "Check loss function (log of 0, division by 0)",
            "Enable gradient clipping",
        ],
        "num_classes_error": [
            "Check num_classes in config yaml",
            "Check model head output channels",
            "Check dataset class count",
            "Ensure background class is included/excluded correctly",
        ],
        "config_error": [
            "Check config yaml keys match what code expects",
            "Check for typos in config keys",
            "Check if all required config fields are present",
        ],
        "dependency_error": [
            "Check requirements.txt / pyproject.toml",
            "Check Python environment",
            "Check CUDA and PyTorch version compatibility",
        ],
    }
    return suggestions.get(category, ["Check the traceback and code context above"])


def diagnose_training_error_logic(
    error_log: str,
    project_hint: str = "",
    use_llm: bool = True,
) -> str:
    if not error_log or not error_log.strip():
        return "[Error] error_log must not be empty"

    cache_key = f"train_err:{make_hash(error_log)}:{use_llm}"
    if ENABLE_DIAGNOSTIC_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    parsed = parse_python_traceback(error_log)
    category = _classify_training_error(error_log)
    suggestions = _training_error_suggestions(category)

    parts = ["Training Error Diagnosis", ""]
    parts.append(f"Error category: {category}")
    parts.append(f"Error type: {parsed['error_type']}")
    parts.append(f"Error message: {parsed['error_message'][:200]}")
    parts.append("")

    if parsed["classified"]["last_project_frame"]:
        f = parsed["classified"]["last_project_frame"]
        parts.append(f"Last project frame: {f['file']}:{f['line']} in {f['function']}()")
        parts.append(f"  Code: {f['code']}")
        parts.append("")

    parts.append("Suggested quick checks:")
    for s in suggestions:
        parts.append(f"  - {s}")
    parts.append("")

    if parsed["classified"]["project_frames"]:
        parts.append("Likely related files:")
        seen = set()
        for f in parsed["classified"]["project_frames"]:
            rel = f["file"]
            if rel not in seen:
                parts.append(f"  - {rel}:{f['line']} in {f['function']}()")
                seen.add(rel)
        parts.append("")

    if project_hint:
        parts.append(f"Project hint: {project_hint}")
        parts.append("")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_DIAGNOSTICS:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import TRAINING_ERROR_SYSTEM_PROMPT
            llm_input = f"Training error analysis:\n{result}\n\nOriginal error log:\n{error_log[:2000]}"
            if project_hint:
                llm_input += f"\n\nProject context: {project_hint[:500]}"
            llm_result = ask_llm(TRAINING_ERROR_SYSTEM_PROMPT, llm_input, max_tokens=1024)
            result = result + "\n\nLLM Diagnosis:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_DIAGNOSTIC_CACHE:
        set_cache(cache_key, result, DIAGNOSTIC_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# suggest_debug_steps
# ---------------------------------------------------------------------------

def _classify_problem_area(problem: str, error_log: str) -> str:
    combined = (problem + " " + error_log).lower()

    if any(w in combined for w in ["cuda", "gpu", "memory", "oom", "device"]):
        return "device/gpu"
    if any(w in combined for w in ["shape", "dimension", "size mismatch", "tensor"]):
        return "model/dimensions"
    if any(w in combined for w in ["import", "module", "install", "dependency", "package"]):
        return "dependency/environment"
    if any(w in combined for w in ["config", "yaml", "toml", "setting", "parameter"]):
        return "configuration"
    if any(w in combined for w in ["data", "dataset", "label", "image", "path", "file not found"]):
        return "data/dataset"
    if any(w in combined for w in ["loss", "nan", "inf", "gradient", "train", "epoch"]):
        return "training/runtime"
    if any(w in combined for w in ["model", "network", "forward", "backward", "layer"]):
        return "model/architecture"
    return "unknown"


def suggest_debug_steps_logic(
    problem_description: str,
    error_log: str = "",
    use_project_profile: bool = True,
    use_llm: bool = True,
) -> str:
    if not problem_description or not problem_description.strip():
        return "[Error] problem_description must not be empty"

    cache_key = f"debug_steps:{make_hash(problem_description + error_log)}:{use_llm}"
    if ENABLE_DIAGNOSTIC_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    area = _classify_problem_area(problem_description, error_log)

    parts = ["Debug Plan", ""]
    parts.append(f"Problem: {problem_description[:200]}")
    parts.append(f"Likely area: {area}")
    parts.append("")

    steps = _generate_debug_steps(area, problem_description, error_log)
    parts.append("Recommended steps:")
    for i, step in enumerate(steps, 1):
        parts.append(f"  {i}. {step}")
    parts.append("")

    tools = _suggest_tools(area)
    parts.append("Suggested MCP tools to call next:")
    for t in tools:
        parts.append(f"  - {t}")
    parts.append("")

    if error_log:
        parsed = parse_python_traceback(error_log)
        if parsed["classified"]["project_frames"]:
            parts.append("Files likely worth reading:")
            seen = set()
            for f in parsed["classified"]["project_frames"][-5:]:
                if f["file"] not in seen:
                    parts.append(f"  - {f['file']}:{f['line']}")
                    seen.add(f["file"])
            parts.append("")

    donts = _generate_donts(area)
    parts.append("What not to do first:")
    for d in donts:
        parts.append(f"  - {d}")

    result = "\n".join(parts)

    if use_llm and ENABLE_LLM_DIAGNOSTICS:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import DEBUG_STEPS_SYSTEM_PROMPT
            llm_input = f"Debug plan:\n{result}"
            if error_log:
                llm_input += f"\n\nError log:\n{error_log[:1500]}"
            llm_result = ask_llm(DEBUG_STEPS_SYSTEM_PROMPT, llm_input, max_tokens=512)
            result = result + "\n\nLLM Suggestions:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    if ENABLE_DIAGNOSTIC_CACHE:
        set_cache(cache_key, result, DIAGNOSTIC_CACHE_TTL_SEC)

    return truncate(result, MAX_OUTPUT_CHARS)


def _generate_debug_steps(area: str, problem: str, error_log: str) -> list[str]:
    base_steps = {
        "device/gpu": [
            "Confirm which device (CPU/CUDA) is being used",
            "Check GPU memory usage (nvidia-smi)",
            "Check batch_size and image_size in config",
            "Try reducing batch_size or enabling AMP",
            "Check model.to(device) and data.to(device) consistency",
        ],
        "model/dimensions": [
            "Read the model definition file to check input/output shapes",
            "Check num_classes in config vs model head",
            "Check data transforms (resize, crop) dimensions",
            "Run with a single sample to check shapes",
        ],
        "dependency/environment": [
            "Check which Python environment is active (which python)",
            "Check installed packages (pip list | grep <module>)",
            "Check requirements.txt / pyproject.toml",
            "Check Python version compatibility",
        ],
        "configuration": [
            "Read the config file being used",
            "Check for missing or extra keys",
            "Compare config with code expectations",
            "Check default values in code",
        ],
        "data/dataset": [
            "Check dataset paths in config",
            "Verify dataset files exist at specified paths",
            "Check label format and class indices",
            "Check data transforms pipeline",
            "Run with a small subset to isolate the issue",
        ],
        "training/runtime": [
            "Check learning rate and optimizer settings",
            "Check loss function implementation",
            "Check for NaN/Inf in input data",
            "Check gradient clipping settings",
            "Try running with fewer epochs or smaller dataset",
        ],
        "model/architecture": [
            "Read the model forward() method",
            "Check layer dimensions match",
            "Check for missing layers or wrong connections",
            "Test with a simple input shape",
        ],
        "unknown": [
            "Read the error traceback carefully",
            "Identify the last project file in the traceback",
            "Read the relevant code around the error line",
            "Check recent changes to the codebase",
        ],
    }
    return base_steps.get(area, base_steps["unknown"])


def _suggest_tools(area: str) -> list[str]:
    base = ["read_file_around_line", "search_code"]
    extra = {
        "device/gpu": ["search_code (search for .to(device) or .cuda())"],
        "model/dimensions": ["extract_symbols", "build_project_map"],
        "dependency/environment": ["diagnose_import_error", "detect_project_profile"],
        "configuration": ["summarize_file", "search_code (search config keys)"],
        "data/dataset": ["summarize_directory", "search_code (search dataset paths)"],
        "training/runtime": ["analyze_traceback_with_context", "extract_symbols"],
        "model/architecture": ["extract_symbols", "summarize_file"],
    }
    return base + extra.get(area, [])


def _generate_donts(area: str) -> list[str]:
    donts = {
        "device/gpu": [
            "Don't blindly increase batch_size",
            "Don't change model architecture before confirming it's a device issue",
        ],
        "model/dimensions": [
            "Don't change model layers without checking the full shape chain",
            "Don't modify loss function without checking model output shape",
        ],
        "dependency/environment": [
            "Don't install packages without checking version compatibility",
            "Don't change Python version without checking all dependencies",
        ],
        "configuration": [
            "Don't add random config keys without understanding what code expects",
        ],
        "data/dataset": [
            "Don't modify dataset files before understanding the expected format",
            "Don't change paths without checking relative vs absolute",
        ],
        "training/runtime": [
            "Don't change learning rate dramatically without understanding the issue",
            "Don't remove loss terms without understanding their purpose",
        ],
        "model/architecture": [
            "Don't remove layers without understanding the data flow",
        ],
    }
    return donts.get(area, ["Don't make changes without understanding the root cause first"])
