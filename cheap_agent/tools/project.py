import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from cheap_agent.cache import get_cache, make_hash, set_cache
from cheap_agent.config import (
    ENABLE_LLM_FILE_SUMMARY,
    ENABLE_PROJECT_MAP_CACHE,
    MAX_FILE_CHARS,
    MAX_OUTPUT_CHARS,
    MAX_PROJECT_MAP_FILES,
    MAX_SUMMARY_FILES,
    MAX_SYMBOL_FILES_FOR_PROJECT_MAP,
    PROJECT_MAP_CACHE_TTL_SEC,
    WORKSPACE_ROOT,
)
from cheap_agent.workspace import (
    get_project_files_cached,
    get_relative_path,
    resolve_safe_path,
    MAX_FILE_SIZE,
)

ENTRY_PATTERNS = {
    "train": ["train", "run_train", "training"],
    "infer": ["infer", "inference", "predict", "demo", "serve"],
    "eval": ["eval", "evaluate", "test", "metrics", "benchmark"],
    "main": ["main", "app", "run", "cli", "__main__"],
}

MODEL_PATTERNS = ["model", "models", "network", "backbone", "head", "neck", "detector", "encoder", "decoder", "loss"]
DATA_PATTERNS = ["data", "dataset", "datasets", "dataloader", "transforms", "augment", "preprocess"]
CONFIG_PATTERNS = ["config", "configs", "conf", "cfg", "settings"]
TEST_PATTERNS = ["test", "tests", "spec", "specs"]
DOC_PATTERNS = ["doc", "docs", "documentation"]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"


def _file_mtime_size(path: Path) -> tuple[float, int]:
    try:
        st = path.stat()
        return st.st_mtime, st.st_size
    except Exception:
        return 0, 0


def _classify_file(rel_path: str) -> list[str]:
    lower = rel_path.lower()
    parts = lower.replace("\\", "/").split("/")
    fname = Path(rel_path).stem.lower()
    tags: list[str] = []

    for cat, patterns in ENTRY_PATTERNS.items():
        if fname in patterns:
            tags.append(f"entry:{cat}")
    for p in MODEL_PATTERNS:
        if p in parts or p == fname:
            tags.append("model")
            break
    for p in DATA_PATTERNS:
        if p in parts or p == fname:
            tags.append("data")
            break
    for p in CONFIG_PATTERNS:
        if p in parts or p == fname:
            tags.append("config")
            break
    for p in TEST_PATTERNS:
        if p in parts or fname.startswith("test_") or fname.endswith("_test"):
            tags.append("test")
            break
    for p in DOC_PATTERNS:
        if p in parts:
            tags.append("docs")
            break

    ext = Path(rel_path).suffix.lower()
    if ext in (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"):
        tags.append("config_file")
    if ext in (".md", ".rst", ".txt"):
        tags.append("doc_file")

    return tags


# ---------------------------------------------------------------------------
# build_project_map
# ---------------------------------------------------------------------------

def build_project_map_logic(
    max_files: int = 500,
    include_symbols: bool = True,
) -> str:
    cache_key = f"project_map:{WORKSPACE_ROOT}:{max_files}:{include_symbols}"
    if ENABLE_PROJECT_MAP_CACHE:
        cached = get_cache(cache_key)
        if cached:
            return cached

    files = get_project_files_cached(max_files=min(max_files, MAX_PROJECT_MAP_FILES))
    root = WORKSPACE_ROOT.resolve()

    dirs: dict[str, int] = defaultdict(int)
    entries: dict[str, list[str]] = defaultdict(list)
    config_files: list[str] = []
    model_files: list[str] = []
    data_files: list[str] = []
    test_files: list[str] = []
    doc_files: list[str] = []

    for rel in files:
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent != ".":
            dirs[parent] += 1

        tags = _classify_file(rel)
        if "entry:train" in tags:
            entries["train"].append(rel)
        if "entry:infer" in tags:
            entries["infer"].append(rel)
        if "entry:eval" in tags:
            entries["eval"].append(rel)
        if "entry:main" in tags:
            entries["main"].append(rel)
        if "model" in tags:
            model_files.append(rel)
        if "data" in tags:
            data_files.append(rel)
        if "config" in tags or "config_file" in tags:
            config_files.append(rel)
        if "test" in tags:
            test_files.append(rel)
        if "docs" in tags or "doc_file" in tags:
            doc_files.append(rel)

    top_dirs = sorted(dirs.items(), key=lambda x: -x[1])[:15]

    parts = [f"Project root: {WORKSPACE_ROOT}", f"Total files: {len(files)}", ""]

    parts.append("Main directories:")
    for d, count in top_dirs:
        parts.append(f"  {d}/ ({count} files)")
    parts.append("")

    for label, key in [("Training entry", "train"), ("Inference entry", "infer"), ("Evaluation entry", "eval"), ("Main entry", "main")]:
        if entries[key]:
            parts.append(f"{label}:")
            for f in entries[key][:5]:
                parts.append(f"  - {f}")
            parts.append("")

    if config_files:
        parts.append(f"Config files ({len(config_files)}):")
        for f in config_files[:10]:
            parts.append(f"  - {f}")
        parts.append("")

    if model_files:
        parts.append(f"Model-related ({len(model_files)}):")
        for f in model_files[:10]:
            parts.append(f"  - {f}")
        parts.append("")

    if data_files:
        parts.append(f"Data-related ({len(data_files)}):")
        for f in data_files[:10]:
            parts.append(f"  - {f}")
        parts.append("")

    if test_files:
        parts.append(f"Test files ({len(test_files)}):")
        for f in test_files[:10]:
            parts.append(f"  - {f}")
        parts.append("")

    if doc_files:
        parts.append(f"Documentation ({len(doc_files)}):")
        for f in doc_files[:5]:
            parts.append(f"  - {f}")
        parts.append("")

    if include_symbols:
        py_files = [f for f in files if f.endswith(".py")]
        key_files = []
        for f in py_files:
            tags = _classify_file(f)
            if any(t.startswith("entry:") or t == "model" for t in tags):
                key_files.append(f)
            if len(key_files) >= MAX_SYMBOL_FILES_FOR_PROJECT_MAP:
                break

        if key_files:
            from cheap_agent.tools.reading import extract_symbols_logic
            parts.append(f"Key file symbols ({len(key_files)} files):")
            for f in key_files:
                symbols = extract_symbols_logic(f)
                brief = []
                for line in symbols.split("\n"):
                    if line.startswith("- ") and ("line" in line or "import" in line.lower()):
                        brief.append(f"  {line}")
                if brief:
                    parts.append(f"\n  {f}:")
                    parts.extend(brief[:8])
            parts.append("")

    suggested = []
    for key in ["main", "train", "infer", "eval"]:
        suggested.extend(entries[key][:2])
    for f in config_files[:3]:
        if f not in suggested:
            suggested.append(f)
    if not suggested:
        suggested = files[:5]

    parts.append("Suggested reading order for Codex:")
    for i, f in enumerate(suggested[:10], 1):
        parts.append(f"  {i}. {f}")

    result = _truncate("\n".join(parts), MAX_OUTPUT_CHARS)

    if ENABLE_PROJECT_MAP_CACHE:
        set_cache(cache_key, result, PROJECT_MAP_CACHE_TTL_SEC)

    return result


# ---------------------------------------------------------------------------
# summarize_file
# ---------------------------------------------------------------------------

def summarize_file_logic(
    file_path: str,
    use_llm: bool = True,
) -> str:
    target = resolve_safe_path(file_path)
    if not target.is_file():
        return f"[Error] File not found: {file_path}"

    mtime, fsize = _file_mtime_size(target)
    cache_key = f"summarize_file:{file_path}:{mtime}:{fsize}:{use_llm}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    rel = get_relative_path(target)
    ext = target.suffix.lower()
    lang = "Python" if ext == ".py" else ext.lstrip(".") or "unknown"

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return f"[Error] Cannot read file: {e}"

    total_lines = len(lines)
    size_kb = fsize / 1024

    symbols_section = ""
    if ext == ".py":
        from cheap_agent.tools.reading import extract_symbols_logic
        symbols_section = extract_symbols_logic(file_path)

    rule_parts = [
        f"File: {rel}",
        f"Type: {lang}",
        f"Lines: {total_lines}",
        f"Size: {size_kb:.1f} KB",
        "",
    ]

    if symbols_section and not symbols_section.startswith("[Error]"):
        rule_parts.append("Key symbols:")
        for line in symbols_section.split("\n"):
            if line.startswith("- ") and "line" in line:
                rule_parts.append(f"  {line}")
        rule_parts.append("")

        for label in ["Imports:", "Main entry:"]:
            for line in symbols_section.split("\n"):
                if line.startswith(label):
                    rule_parts.append(line)
                    idx = symbols_section.split("\n").index(line)
                    for follow in symbols_section.split("\n")[idx + 1:]:
                        if follow.startswith("- "):
                            rule_parts.append(f"  {follow}")
                        else:
                            break
        rule_parts.append("")

    tags = _classify_file(file_path)
    if tags:
        rule_parts.append(f"Likely role: {', '.join(tags)}")
        rule_parts.append("")

    rule_parts.append(f"Notes for Codex: review {rel} to understand its purpose")
    rule_result = "\n".join(rule_parts)

    if not use_llm or not ENABLE_LLM_FILE_SUMMARY:
        set_cache(cache_key, rule_result)
        return _truncate(rule_result, MAX_OUTPUT_CHARS)

    try:
        from cheap_agent.llm_client import ask_llm
        from cheap_agent.prompts.base import FILE_SUMMARY_SYSTEM_PROMPT
        content = "\n".join(lines[:200])
        user_prompt = f"文件路径: {rel}\n\n文件结构:\n{rule_result}\n\n文件内容(前200行):\n```\n{content}\n```"
        llm_result = ask_llm(FILE_SUMMARY_SYSTEM_PROMPT, user_prompt, max_tokens=512)
        final = rule_result + "\n\nLLM Summary:\n" + llm_result
    except Exception as e:
        final = rule_result + f"\n\n[LLM Error] {e}"

    set_cache(cache_key, final)
    return _truncate(final, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# summarize_directory
# ---------------------------------------------------------------------------

def summarize_directory_logic(
    dir_path: str = ".",
    max_files: int = 100,
    use_llm: bool = True,
) -> str:
    target = resolve_safe_path(dir_path)
    if not target.is_dir():
        return f"[Error] Directory not found: {dir_path}"

    rel_dir = get_relative_path(target)
    cache_key = f"summarize_dir:{rel_dir}:{max_files}:{use_llm}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    root = WORKSPACE_ROOT.resolve()
    files: list[str] = []
    subdirs: set[str] = set()

    for p in target.rglob("*"):
        if not p.is_file():
            if p.is_dir():
                rel = str(p.relative_to(root)).replace("\\", "/")
                parts = rel.split("/")
                if not any(d in (".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build") for d in parts):
                    subdirs.add(rel)
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        parts = rel.split("/")
        if any(d in (".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build") for d in parts):
            continue
        if p.stat().st_size > MAX_FILE_SIZE:
            continue
        ext = p.suffix.lower()
        if ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".yaml", ".yml", ".json", ".toml", ".md"):
            files.append(rel)
        if len(files) >= max_files:
            break

    files = sorted(files)

    file_summaries: dict[str, str] = {}
    key_files = [f for f in files if f.endswith(".py")][:10]
    for f in key_files:
        try:
            summary = summarize_file_logic(f, use_llm=False)
            brief_lines = [l for l in summary.split("\n") if l.startswith(("Likely role:", "- "))][:3]
            if brief_lines:
                file_summaries[f] = " | ".join(l.strip() for l in brief_lines)
        except Exception:
            pass

    parts = [
        f"Directory: {rel_dir}",
        f"Files scanned: {len(files)}",
        "",
    ]

    tags_count: dict[str, int] = defaultdict(int)
    for f in files:
        for tag in _classify_file(f):
            tags_count[tag] += 1

    if tags_count:
        likely = []
        if tags_count.get("model", 0) > 0:
            likely.append("model definitions")
        if tags_count.get("data", 0) > 0:
            likely.append("data processing")
        if tags_count.get("config", 0) > 0 or tags_count.get("config_file", 0) > 0:
            likely.append("configuration")
        if tags_count.get("test", 0) > 0:
            likely.append("testing")
        if tags_count.get("entry:train", 0) > 0:
            likely.append("training")
        if likely:
            parts.append(f"Likely responsibility: {', '.join(likely)}")
            parts.append("")

    if file_summaries:
        parts.append("Important files:")
        for f, summary in file_summaries.items():
            parts.append(f"  {f}: {summary}")
        parts.append("")

    if subdirs:
        sorted_subdirs = sorted(subdirs)[:10]
        parts.append("Subdirectories:")
        for d in sorted_subdirs:
            parts.append(f"  {d}/")
        parts.append("")

    suggested = []
    for f in files:
        tags = _classify_file(f)
        if any(t.startswith("entry:") for t in tags):
            suggested.append(f)
    for f in files:
        if f.endswith(".py") and f not in suggested:
            suggested.append(f)
        if len(suggested) >= 5:
            break

    if suggested:
        parts.append("Suggested reading order:")
        for i, f in enumerate(suggested[:5], 1):
            parts.append(f"  {i}. {f}")
        parts.append("")

    parts.append(f"Notes for Codex: explore {rel_dir}/ to understand its structure")

    result = _truncate("\n".join(parts), MAX_OUTPUT_CHARS)

    if use_llm and ENABLE_LLM_FILE_SUMMARY:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import DIRECTORY_SUMMARY_SYSTEM_PROMPT
            user_prompt = f"目录: {rel_dir}\n\n分析结果:\n{result}"
            llm_result = ask_llm(DIRECTORY_SUMMARY_SYSTEM_PROMPT, user_prompt, max_tokens=512)
            result = result + "\n\nLLM Summary:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    set_cache(cache_key, result)
    return _truncate(result, MAX_OUTPUT_CHARS)


# ---------------------------------------------------------------------------
# detect_project_profile
# ---------------------------------------------------------------------------

_DEP_MAP = {
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "keras": "Keras",
    "sklearn": "scikit-learn",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "mcp": "MCP",
    "fastmcp": "FastMCP",
    "openai": "OpenAI",
    "transformers": "HuggingFace Transformers",
    "ultralytics": "Ultralytics/YOLO",
    "opencv": "OpenCV",
    "pytest": "pytest",
    "react": "React",
    "vue": "Vue",
    "next": "Next.js",
    "vite": "Vite",
    "express": "Express",
}


def detect_project_profile_logic(
    use_llm: bool = False,
) -> str:
    cache_key = f"project_profile:{WORKSPACE_ROOT}:{use_llm}"
    cached = get_cache(cache_key)
    if cached:
        return cached

    files = get_project_files_cached(max_files=MAX_PROJECT_MAP_FILES)
    root = WORKSPACE_ROOT.resolve()

    ext_count: dict[str, int] = defaultdict(int)
    dep_hits: set[str] = set()
    has_requirements = False
    has_pyproject = False
    has_setup_py = False
    has_package_json = False
    has_dockerfile = False
    has_makefile = False
    readme_files: list[str] = []
    config_files: list[str] = []
    entry_files: list[str] = []

    for rel in files:
        ext = Path(rel).suffix.lower()
        ext_count[ext] += 1
        fname = Path(rel).name.lower()
        stem = Path(rel).stem.lower()

        if fname == "requirements.txt":
            has_requirements = True
            try:
                content = (root / rel).read_text(encoding="utf-8", errors="replace").lower()
                for dep, name in _DEP_MAP.items():
                    if dep in content:
                        dep_hits.add(name)
            except Exception:
                pass
        if fname == "pyproject.toml":
            has_pyproject = True
        if fname == "setup.py":
            has_setup_py = True
        if fname == "package.json":
            has_package_json = True
        if fname == "dockerfile":
            has_dockerfile = True
        if fname == "makefile":
            has_makefile = True
        if fname in ("readme.md", "readme.rst", "readme.txt"):
            readme_files.append(rel)
        if ext in (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg") or stem in ("config", "settings"):
            config_files.append(rel)
        if stem in ("main", "app", "run", "train", "infer", "eval", "server", "cli"):
            entry_files.append(rel)

    main_lang = "unknown"
    if ext_count[".py"] > ext_count.get(".js", 0) and ext_count[".py"] > ext_count.get(".ts", 0):
        main_lang = "Python"
    elif ext_count[".js"] + ext_count[".ts"] > ext_count.get(".py", 0):
        main_lang = "JavaScript/TypeScript"
    elif ext_count[".java"] > 0:
        main_lang = "Java"
    elif ext_count[".go"] > 0:
        main_lang = "Go"
    elif ext_count[".rs"] > 0:
        main_lang = "Rust"
    elif ext_count[".cpp"] + ext_count[".c"] > 0:
        main_lang = "C/C++"

    project_types: list[str] = []
    if "FastMCP" in dep_hits or "MCP" in dep_hits:
        project_types.append("MCP Server")
    if "Ultralytics/YOLO" in dep_hits:
        project_types.append("YOLO/Ultralytics project")
    if "PyTorch" in dep_hits or "TensorFlow" in dep_hits:
        project_types.append("Deep Learning project")
    if "FastAPI" in dep_hits or "Flask" in dep_hits or "Django" in dep_hits:
        project_types.append("Web API project")
    if has_package_json:
        project_types.append("Node.js project")
    if not project_types:
        if main_lang == "Python":
            project_types.append("Python project")
        elif main_lang != "unknown":
            project_types.append(f"{main_lang} project")

    parts = [
        "Project Profile",
        "",
        f"Root: {WORKSPACE_ROOT}",
        f"Total files: {len(files)}",
        "",
        f"Main language: {main_lang}",
        "",
        "Likely project type:",
    ]
    for t in project_types:
        parts.append(f"  - {t}")
    parts.append("")

    if dep_hits:
        parts.append("Detected stack:")
        for d in sorted(dep_hits):
            parts.append(f"  - {d}")
        parts.append("")

    dep_mgmt = []
    if has_requirements:
        dep_mgmt.append("requirements.txt")
    if has_pyproject:
        dep_mgmt.append("pyproject.toml")
    if has_setup_py:
        dep_mgmt.append("setup.py")
    if has_package_json:
        dep_mgmt.append("package.json")
    if dep_mgmt:
        parts.append(f"Dependency management: {', '.join(dep_mgmt)}")
        parts.append("")

    if entry_files:
        parts.append("Entry points:")
        for f in sorted(entry_files)[:8]:
            parts.append(f"  - {f}")
        parts.append("")

    if config_files:
        parts.append("Configuration:")
        for f in sorted(config_files)[:8]:
            parts.append(f"  - {f}")
        parts.append("")

    if readme_files:
        parts.append("Documentation:")
        for f in readme_files:
            parts.append(f"  - {f}")
        parts.append("")

    suggested = []
    for f in readme_files[:1]:
        suggested.append(f)
    for f in entry_files[:3]:
        if f not in suggested:
            suggested.append(f)
    for f in config_files[:2]:
        if f not in suggested:
            suggested.append(f)
    if not suggested:
        suggested = files[:5]

    parts.append("Suggested first-read order for Codex:")
    for i, f in enumerate(suggested[:8], 1):
        parts.append(f"  {i}. {f}")

    result = "\n".join(parts)

    if use_llm:
        try:
            from cheap_agent.llm_client import ask_llm
            from cheap_agent.prompts.base import PROJECT_PROFILE_SYSTEM_PROMPT
            llm_result = ask_llm(PROJECT_PROFILE_SYSTEM_PROMPT, f"项目画像:\n{result}", max_tokens=512)
            result = result + "\n\nLLM Notes:\n" + llm_result
        except Exception as e:
            result = result + f"\n\n[LLM Error] {e}"

    set_cache(cache_key, result)
    return _truncate(result, MAX_OUTPUT_CHARS)
