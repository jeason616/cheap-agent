<div align="center">

# 🔍 cheap-agent

**Local MCP Read-Only Code Analysis & Paper Writing Assistant**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP Server](https://img.shields.io/badge/MCP-Server-green?logo=model-context-protocol)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tools: 74](https://img.shields.io/badge/Tools-74-purple)](#-tool-overview)

English · [中文](README_CN.md)

</div>

---

## ✨ What is this?

`cheap-agent` is a locally running **MCP Server** called by [Codex](https://openai.com/index/codex/), [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [MiMo Code](https://github.com), and other MCP Clients. It provides **code analysis** and **academic paper writing assistance**.

It **only analyzes and suggests** — it never modifies code or papers. Final changes are made by Codex.

```
┌─────────────┐     MCP (stdio)     ┌──────────────────┐
│  Codex /    │ ◄─────────────────► │  cheap-agent     │
│  Claude Code│                     │  MCP Server      │
│  MiMo Code  │                     │  (read-only)     │
└─────────────┘                     └──────────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │ Your project  │
                                    │ (unmodified)  │
                                    └──────────────┘
```

## 🛡️ Safety

| Feature | Description |
|:--------|:-----------|
| 🔒 **Read-only** | Never modifies, creates, or deletes files |
| 🚫 **No Shell** | Never executes commands (git, python, npm, etc.) |
| 📁 **Path sandbox** | All file access restricted to `WORKSPACE_ROOT` |
| 🔑 **Secret masking** | API_KEY, TOKEN auto-masked before caching |
| 🤖 **No fabrication** | Never invents results, citations, figures, or methods |
| 🌐 **No network** | Never accesses the internet to search references |

## 🚀 Quick Start

### 1️⃣ Install

```bash
cd cheap-agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2️⃣ Configure `.env`

```env
# OpenAI-compatible API
LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
LLM_API_KEY=your-key-here
LLM_MODEL=mimo-v2.5-pro

# Tool Profile (optional: minimal / code / paper / full / safe / debug)
MCP_PROFILE=full
```

### 3️⃣ Connect to MCP Client

**Codex** — edit `~/.codex/config.toml`:

```toml
[mcp_servers.cheap_agent]
command = "/path/to/cheap-agent/.venv/bin/python"
args = ["/path/to/cheap-agent/server.py"]
```

**Claude Code** — run:

```bash
claude mcp add cheap-agent -- /path/to/cheap-agent/.venv/bin/python /path/to/cheap-agent/server.py
```

### 4️⃣ Test

```bash
# Unit tests (integration tests are skipped by default)
python -m pytest tests/ -v

# Run the slow end-to-end stdio integration tests explicitly
python -m pytest tests/ -v -m integration
```

---

## 🧰 Tool Overview

> **74 tools** total, all read-only, all support `use_llm=False` rule-based mode

### 🔧 Code Assistance (35 tools)

<details>
<summary><b>📂 Code Reading</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `read_file_around_line` | Read code snippet around a line | ❌ |
| `extract_symbols` | Extract functions/classes/imports | ❌ |
| `search_code` | Keyword search across project | ❌ |
| `find_related_files` | Find files related to a task | ✅ |

</details>

<details>
<summary><b>🗺️ Project Understanding</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `build_project_map` | Project structure map | ❌ |
| `summarize_file` | Single file summary | ✅ |
| `summarize_directory` | Directory summary | ✅ |
| `detect_project_profile` | Project type detection | ❌ |
| `build_project_profile_v2` | Detailed project profile | ✅ |
| `get_codex_onboarding_pack` | Onboarding context pack | ❌ |
| `infer_project_runbook` | Runbook inference | ✅ |
| `recommend_workflow_for_task` | Tool recommendation | ❌ |
| `explain_project_conventions` | Project conventions | ✅ |

</details>

<details>
<summary><b>🐛 Error Diagnostics</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `analyze_traceback_with_context` | Traceback + code context | ✅ |
| `diagnose_import_error` | Import error diagnosis | ✅ |
| `diagnose_training_error` | CUDA OOM / shape mismatch | ✅ |
| `suggest_debug_steps` | Debug plan generation | ✅ |

</details>

<details>
<summary><b>🧪 Testing & Validation</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `suggest_minimal_repro` | Minimal reproduction plan | ✅ |
| `generate_unit_test_plan` | Unit test plan | ✅ |
| `check_config_consistency` | Config consistency check | ✅ |
| `suggest_validation_plan` | Validation plan | ✅ |

</details>

<details>
<summary><b>🔍 Code Review</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `review_file` | Code quality review | ✅ |
| `review_diff` | Diff review | ✅ |
| `risk_check_before_edit` | Pre-edit risk analysis | ✅ |
| `post_edit_review` | Post-edit review | ✅ |
| `analyze_change_impact` | Change impact analysis | ✅ |

</details>

### 📝 Paper Assistance (39 tools)

<details>
<summary><b>📄 Paper Structure</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `detect_paper_project` | Detect paper project | ❌ |
| `build_paper_map` | Paper project map | ❌ |
| `summarize_latex_structure` | LaTeX structure summary | ✅ |
| `find_paper_sections` | Section finder | ❌ |
| `review_paper_structure` | Structure completeness | ✅ |
| `check_claim_evidence` | Claim-evidence check | ✅ |

</details>

<details>
<summary><b>📊 Experiment Verification</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `parse_latex_tables` | LaTeX table parsing | ❌ |
| `extract_experiment_claims` | Experiment claim extraction | ✅ |
| `check_result_claim_consistency` | Text-table consistency | ✅ |
| `check_ablation_logic` | Ablation completeness | ✅ |
| `check_metric_consistency` | Metric notation consistency | ❌ |

</details>

<details>
<summary><b>✍️ Writing Review</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `review_academic_paragraph` | Paragraph quality | ✅ |
| `check_abstract_quality` | Abstract completeness | ✅ |
| `check_introduction_logic` | Introduction logic chain | ✅ |
| `check_contribution_clarity` | Contribution clarity | ✅ |
| `check_term_consistency` | Term consistency | ✅ |
| `check_ieee_style` | IEEE/TGRS style | ✅ |

</details>

<details>
<summary><b>🖼️ Figure & Reference</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `parse_figures_and_labels` | Figure/table/equation parsing | ❌ |
| `check_figure_reference_consistency` | Reference consistency | ❌ |
| `review_figure_caption` | Figure caption review | ✅ |
| `review_table_caption` | Table caption review | ✅ |
| `check_caption_text_consistency` | Caption-text consistency | ✅ |
| `check_equation_reference_consistency` | Equation reference check | ✅ |

</details>

<details>
<summary><b>📚 References & Related Work</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `parse_bib_file` | BibTeX parsing | ❌ |
| `check_citation_coverage` | Citation coverage check | ❌ |
| `group_references_by_topic` | Reference topic grouping | ✅ |
| `check_related_work_coverage` | Related Work coverage | ✅ |
| `check_reference_recency` | Reference recency check | ❌ |
| `check_bibtex_quality` | BibTeX quality check | ❌ |
| `suggest_citation_positions` | Citation position suggestions | ✅ |
| `build_related_work_outline` | Related Work outline | ✅ |

</details>

<details>
<summary><b>📬 Reviewer Response</b></summary>

| Tool | Description | LLM |
|:-----|:-----------|:----|
| `parse_reviewer_comments` | Reviewer comment parsing | ✅ |
| `group_reviewer_concerns` | Concern clustering | ✅ |
| `map_comments_to_revisions` | Comment-to-revision mapping | ✅ |
| `check_response_completeness` | Response completeness | ✅ |
| `review_response_tone` | Response tone review | ✅ |
| `draft_response_outline` | Response outline generation | ✅ |

</details>

---

## 🎛️ Tool Profile System

Control which tools are enabled via `MCP_PROFILE`:

| Profile | Tools | Use Case |
|:--------|:------|:---------|
| `minimal` | ~10 | ⚡ Fast startup, low overhead |
| `code` | ~35 | 💻 Code development & debugging |
| `paper` | ~44 | 📝 Paper writing & submission |
| `full` | 74 | 🔓 All tools (default) |
| `safe` | ~15 | 🛡️ Only rule-based, low-risk tools |
| `debug` | ~5 | 🔧 MCP self-diagnostics |

```env
# Example: only enable paper tools
MCP_PROFILE=paper
```

### 📊 Meta Tools

| Tool | Description |
|:-----|:-----------|
| `show_active_profile` | Show current profile and enabled groups |
| `list_available_tools` | List currently available tools |
| `explain_tool_routing` | Recommend tools for a task |

---

## ⚡ Performance

| Tool Type | Latency | Notes |
|:----------|:--------|:------|
| 🟢 Rule-based | < 1s | `search_code`, `parse_bib_file`, etc. |
| 🟡 LLM tools | 5-30s | Depends on model and input length |
| 🔵 Cache hit | < 0.5s | Repeated calls use cache automatically |

---

## 📁 Project Structure

```
cheap-agent/
├── server.py              # 🚀 MCP Server entry point (registers all tools)
├── requirements.txt       # 📦 Pinned dependencies
├── pyproject.toml         # ⚙️ Project metadata, ruff & pytest config
├── cheap_agent/           # 📦 Main package
│   ├── __init__.py        #   Package init (__version__)
│   ├── config.py          #   Configuration (env-driven)
│   ├── tool_registry.py   #   Tool metadata registry (single source of truth)
│   ├── profiles.py        #   Profile & feature-switch management
│   ├── workspace.py       #   Safe, sandboxed file reading
│   ├── llm_client.py      #   LLM client (with retry)
│   ├── cache.py           #   In-memory cache
│   ├── cache_manager.py   #   Disk cache
│   ├── parsers/           #   LaTeX/BibTeX parsers
│   ├── prompts/           #   Prompt templates
│   └── tools/             #   🧰 15 tool modules
│       ├── reading.py     #     File reading
│       ├── project.py     #     Project understanding
│       ├── diagnostics.py #     Error diagnostics
│       ├── testing.py     #     Testing & validation
│       ├── review.py      #     Code review
│       ├── code.py        #     Code analysis helpers
│       ├── profile.py     #     Project profiling
│       ├── cache_tools.py #     Cache management
│       ├── meta.py        #     Meta tools
│       ├── paper.py       #     Paper structure
│       ├── experiments.py #     Experiment verification
│       ├── writing.py     #     Writing review
│       ├── figures.py     #     Figure & reference
│       ├── related_work.py#     References & Related Work
│       └── rebuttal.py    #     Reviewer response
└── tests/                 # 🧪 Test suite
```

---

## 🤝 Contributing

PRs welcome! Please ensure:

- [ ] New tools are read-only
- [ ] No shell commands executed
- [ ] Paths restricted to `WORKSPACE_ROOT`
- [ ] Added to `tool_registry.py` with profile tags
- [ ] Tests added to `tests/`

---

<div align="center">

**Made with ❤️ for researchers and developers**

</div>
