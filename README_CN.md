<div align="center">

# 🔍 cheap-agent

**本地运行的 MCP 只读代码分析与论文写作辅助智能体**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP Server](https://img.shields.io/badge/MCP-Server-green?logo=model-context-protocol)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tools: 74](https://img.shields.io/badge/Tools-74-purple)](#-工具总览)

[English](README.md) · 中文

</div>

---

## ✨ 这是什么？

`cheap-agent` 是一个本地运行的 **MCP Server**，被 [Codex](https://openai.com/index/codex/)、[Claude Code](https://docs.anthropic.com/en/docs/claude-code)、[MiMo Code](https://github.com) 等 MCP Client 调用，提供 **代码分析** 和 **论文写作辅助** 能力。

它**只负责分析和建议**，不负责修改代码或论文。最终修改由 Codex 完成。

```
┌─────────────┐     MCP (stdio)     ┌──────────────────┐
│  Codex /    │ ◄─────────────────► │  cheap-agent     │
│  Claude Code│                     │  MCP Server      │
│  MiMo Code  │                     │  (只读分析)       │
└─────────────┘                     └──────────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │ 你的项目文件  │
                                    │ (不修改)      │
                                    └──────────────┘
```

## 🛡️ 安全边界

| 特性 | 说明 |
|:-----|:-----|
| 🔒 **只读** | 不修改、不创建、不删除任何文件 |
| 🚫 **无 Shell** | 不执行任何命令（git、python、npm 等） |
| 📁 **路径沙箱** | 所有文件访问限制在 `WORKSPACE_ROOT` 内 |
| 🔑 **密钥脱敏** | 缓存写入前自动脱敏 API_KEY、TOKEN 等 |
| 🤖 **不编造** | 不编造实验结果、引用、图表或方法 |
| 🌐 **不联网** | 不访问网络查询参考文献 |

## 🚀 快速开始

### 1️⃣ 安装

```bash
cd cheap-agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 2️⃣ 配置 `.env`

```env
# OpenAI-compatible API
LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
LLM_API_KEY=your-key-here
LLM_MODEL=mimo-v2.5-pro

# 工具 Profile（可选：minimal / code / paper / full / safe / debug）
MCP_PROFILE=full
```

### 3️⃣ 接入 MCP Client

**Codex** — 编辑 `~/.codex/config.toml`：

```toml
[mcp_servers.cheap_agent]
command = "/path/to/cheap-agent/.venv/bin/python"
args = ["/path/to/cheap-agent/server.py"]
```

**Claude Code** — 运行：

```bash
claude mcp add cheap-agent -- /path/to/cheap-agent/.venv/bin/python /path/to/cheap-agent/server.py
```

### 4️⃣ 测试

```bash
python -m pytest tests/ -v --ignore=tests/test_integration.py
```

---

## 🧰 工具总览

> 共 **74 个工具**，全部只读，支持 `use_llm=False` 纯规则模式

### 🔧 代码辅助（35 个）

<details>
<summary><b>📂 代码读取</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `read_file_around_line` | 读取指定行附近代码 | ❌ |
| `extract_symbols` | 提取函数/类/import 结构 | ❌ |
| `search_code` | 关键词搜索项目文件 | ❌ |
| `find_related_files` | 根据任务找相关文件 | ✅ |

</details>

<details>
<summary><b>🗺️ 项目理解</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `build_project_map` | 项目结构地图 | ❌ |
| `summarize_file` | 单文件摘要 | ✅ |
| `summarize_directory` | 目录摘要 | ✅ |
| `detect_project_profile` | 项目类型检测 | ❌ |
| `build_project_profile_v2` | 完整项目画像 | ✅ |
| `get_codex_onboarding_pack` | 启动上下文包 | ❌ |
| `infer_project_runbook` | 运行手册推断 | ✅ |
| `recommend_workflow_for_task` | 任务工具推荐 | ❌ |
| `explain_project_conventions` | 项目约定总结 | ✅ |

</details>

<details>
<summary><b>🐛 错误诊断</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `analyze_traceback_with_context` | Traceback + 代码上下文分析 | ✅ |
| `diagnose_import_error` | 导入错误诊断 | ✅ |
| `diagnose_training_error` | CUDA OOM / shape mismatch 等 | ✅ |
| `suggest_debug_steps` | 调试计划生成 | ✅ |

</details>

<details>
<summary><b>🧪 测试验证</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `suggest_minimal_repro` | 最小复现方案 | ✅ |
| `generate_unit_test_plan` | 单元测试计划 | ✅ |
| `check_config_consistency` | 配置一致性检查 | ✅ |
| `suggest_validation_plan` | 验证计划 | ✅ |

</details>

<details>
<summary><b>🔍 代码审查</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `review_file` | 代码质量审查 | ✅ |
| `review_diff` | Diff 审查 | ✅ |
| `risk_check_before_edit` | 修改前风险分析 | ✅ |
| `post_edit_review` | 修改后审查 | ✅ |
| `analyze_change_impact` | 影响范围分析 | ✅ |

</details>

### 📝 论文辅助（39 个）

<details>
<summary><b>📄 论文结构</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `detect_paper_project` | 检测论文项目 | ❌ |
| `build_paper_map` | 论文项目地图 | ❌ |
| `summarize_latex_structure` | LaTeX 结构总结 | ✅ |
| `find_paper_sections` | 章节查找 | ❌ |
| `review_paper_structure` | 结构完整性检查 | ✅ |
| `check_claim_evidence` | Claim-Evidence 检查 | ✅ |

</details>

<details>
<summary><b>📊 实验核对</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `parse_latex_tables` | LaTeX 表格解析 | ❌ |
| `extract_experiment_claims` | 实验 Claim 提取 | ✅ |
| `check_result_claim_consistency` | 正文-表格一致性 | ✅ |
| `check_ablation_logic` | 消融实验完整性 | ✅ |
| `check_metric_consistency` | 指标格式统一性 | ❌ |

</details>

<details>
<summary><b>✍️ 写作审查</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `review_academic_paragraph` | 段落表达质量 | ✅ |
| `check_abstract_quality` | 摘要完整性 | ✅ |
| `check_introduction_logic` | Introduction 逻辑链 | ✅ |
| `check_contribution_clarity` | 贡献点清晰度 | ✅ |
| `check_term_consistency` | 术语一致性 | ✅ |
| `check_ieee_style` | IEEE/TGRS 风格 | ✅ |

</details>

<details>
<summary><b>🖼️ 图表引用</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `parse_figures_and_labels` | 图表/公式/Label 解析 | ❌ |
| `check_figure_reference_consistency` | 引用一致性检查 | ❌ |
| `review_figure_caption` | Figure Caption 审查 | ✅ |
| `review_table_caption` | Table Caption 审查 | ✅ |
| `check_caption_text_consistency` | Caption-正文一致性 | ✅ |
| `check_equation_reference_consistency` | 公式引用一致性 | ✅ |

</details>

<details>
<summary><b>📚 参考文献</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `parse_bib_file` | BibTeX 解析 | ❌ |
| `check_citation_coverage` | 引用覆盖检查 | ❌ |
| `group_references_by_topic` | 参考文献主题分组 | ✅ |
| `check_related_work_coverage` | Related Work 覆盖度 | ✅ |
| `check_reference_recency` | 文献年份检查 | ❌ |
| `check_bibtex_quality` | BibTeX 质量检查 | ❌ |
| `suggest_citation_positions` | 补引用位置建议 | ✅ |
| `build_related_work_outline` | Related Work 提纲 | ✅ |

</details>

<details>
<summary><b>📬 审稿回复</b></summary>

| 工具 | 说明 | LLM |
|:-----|:-----|:----|
| `parse_reviewer_comments` | 审稿意见解析 | ✅ |
| `group_reviewer_concerns` | 问题聚类 | ✅ |
| `map_comments_to_revisions` | 意见→修改位置映射 | ✅ |
| `check_response_completeness` | Response 完整性 | ✅ |
| `review_response_tone` | Response 语气审查 | ✅ |
| `draft_response_outline` | Response 提纲生成 | ✅ |

</details>

---

## 🎛️ 工具 Profile 系统

通过 `MCP_PROFILE` 控制启用哪些工具，避免工具列表过长：

| Profile | 工具数 | 适用场景 |
|:--------|:------|:---------|
| `minimal` | ~10 | ⚡ 快速启动、低开销 |
| `code` | ~35 | 💻 代码开发和调试 |
| `paper` | ~44 | 📝 论文写作和投稿 |
| `full` | 74 | 🔓 全部工具（默认） |
| `safe` | ~15 | 🛡️ 只有纯规则、低风险工具 |
| `debug` | ~5 | 🔧 MCP 自检和性能调试 |

```env
# 示例：只启用论文相关工具
MCP_PROFILE=paper
```

### 📊 元工具

| 工具 | 说明 |
|:-----|:-----|
| `show_active_profile` | 查看当前 Profile 和启用的工具组 |
| `list_available_tools` | 列出当前可用工具 |
| `explain_tool_routing` | 根据任务推荐工具调用顺序 |

---

## ⚡ 性能

| 工具类型 | 典型延迟 | 说明 |
|:---------|:---------|:-----|
| 🟢 纯规则工具 | < 1s | `search_code`、`parse_bib_file` 等 |
| 🟡 LLM 工具 | 5-30s | 取决于模型和输入长度 |
| 🔵 缓存命中 | < 0.5s | 重复调用自动走缓存 |

---

## 📁 项目结构

```
cheap-agent/
├── server.py              # 🚀 MCP Server 入口
├── config.py              # ⚙️ 配置加载
├── tool_registry.py       # 📋 工具元信息注册表
├── profiles.py            # 🎛️ Profile 管理
├── workspace.py           # 📁 安全文件读取
├── llm_client.py          # 🤖 LLM 调用
├── cache.py               # 💾 内存缓存
├── cache_manager.py       # 💿 磁盘缓存
├── parsers/               # 📖 LaTeX/BibTeX 解析
├── prompts/               # 📝 提示词模板
└── tools/                 # 🧰 20 个工具模块
    ├── code.py            #   代码分析
    ├── reading.py         #   文件读取
    ├── project.py         #   项目理解
    ├── diagnostics.py     #   错误诊断
    ├── testing.py         #   测试验证
    ├── review.py          #   代码审查
    ├── cache_tools.py     #   缓存管理
    ├── profile.py         #   项目画像
    ├── meta.py            #   元工具
    ├── paper.py           #   论文结构
    ├── experiments.py     #   实验核对
    ├── writing.py         #   写作审查
    ├── figures.py         #   图表引用
    ├── related_work.py    #   参考文献
    └── rebuttal.py        #   审稿回复
```

---

## 🤝 贡献

欢迎 PR！请确保：

- [ ] 新工具是只读的
- [ ] 不执行 shell 命令
- [ ] 路径限制在 `WORKSPACE_ROOT` 内
- [ ] 添加到 `tool_registry.py` 并标注 profile
- [ ] 添加测试到 `tests/`

---

<div align="center">

**Made with ❤️ for researchers and developers**

</div>
