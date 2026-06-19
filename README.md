# cheap-agent

本地运行的 **MCP 只读代码分析辅助智能体**。被 Codex、Cline 或其他 MCP Client 调用，通过 OpenAI-compatible API 调用便宜模型完成代码分析。

## 核心特性

- 只读文件，不修改、不删除、不执行 shell
- 所有文件访问限制在 `WORKSPACE_ROOT` 内
- 通过 OpenAI-compatible API 调用本地或远程便宜模型（Ollama / DeepSeek / OpenRouter / vLLM 等）
- 默认 `stdio` transport，Codex 本地直接调用
- 可选 `streamable-http` transport

## 提供的 MCP 工具

### LLM 分析工具（需要调用模型）

| 工具 | 作用 |
|------|------|
| `review_file` | 审查指定文件的代码质量 |
| `analyze_error_log` | 分析报错日志，定位原因 |
| `find_related_files` | 根据任务描述找相关文件 |
| `generate_test_ideas` | 为文件生成测试思路 |
| `summarize_project` | 分析项目结构并生成摘要 |

### 本地读取工具（不调用 LLM，快速响应）

| 工具 | 作用 |
|------|------|
| `read_file_around_line` | 读取指定行附近的代码片段，用于报错定位 |
| `extract_symbols` | 提取文件中的函数、类、import、入口等结构信息 |
| `search_code` | 在项目中搜索关键词，返回匹配位置 |

### 项目理解工具（增强项目认知）

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `build_project_map` | 生成项目结构地图 | 否 |
| `summarize_file` | 对单个文件生成摘要 | 是（可选） |
| `summarize_directory` | 对目录生成摘要 | 是（可选） |
| `detect_project_profile` | 自动判断项目画像 | 否（可选） |

### 错误诊断工具（增强报错定位）

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `analyze_traceback_with_context` | 解析 traceback，读取项目内代码上下文并分析 | 是（可选） |
| `diagnose_import_error` | 诊断 ModuleNotFoundError、ImportError 等导入问题 | 是（可选） |
| `diagnose_training_error` | 诊断 CUDA OOM、shape mismatch、数据加载等训练错误 | 是（可选） |
| `suggest_debug_steps` | 根据问题描述生成结构化调试计划 | 是（可选） |

### 测试和验证工具（增强测试能力）

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `suggest_minimal_repro` | 根据问题描述生成最小复现方案 | 是（可选） |
| `generate_unit_test_plan` | 为文件或符号生成单元测试计划 | 是（可选） |
| `check_config_consistency` | 检查配置文件与代码之间的不一致风险 | 是（可选） |
| `suggest_validation_plan` | 根据任务描述和修改文件生成验证计划 | 是（可选） |

### 代码审查工具（增强代码审查能力）

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `review_diff` | 审查 unified diff，指出潜在 bug 和遗漏同步修改 | 是（可选） |
| `risk_check_before_edit` | 修改前分析风险与影响范围 | 是（可选） |
| `post_edit_review` | 修改后做二次审查 | 是（可选） |
| `analyze_change_impact` | 分析修改的潜在影响范围和引用位置 | 是（可选） |

### 缓存和记忆工具（增强缓存层）

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `cache_status` | 查看缓存状态、大小和性能统计 | 否 |
| `clear_cache` | 清理过期缓存或指定缓存命名空间 | 否 |
| `rebuild_project_index` | 强制重建项目文件索引 | 否 |
| `get_cached_project_context` | 快速返回缓存中的项目画像和摘要 | 否 |
| `export_perf_report` | 输出工具耗时统计和优化建议 | 否 |

### 项目画像与启动上下文工具（增强项目画像）

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `build_project_profile_v2` | 构建完整项目画像，包含技术栈、入口、测试、运行方式 | 是（可选） |
| `get_codex_onboarding_pack` | 生成简短启动上下文包，帮助 Codex 快速进入项目 | 否 |
| `infer_project_runbook` | 推断安装、启动、测试、调试流程 | 是（可选） |
| `recommend_workflow_for_task` | 根据任务描述推荐 MCP 工具调用顺序 | 否 |
| `explain_project_conventions` | 总结项目开发约定 | 是（可选） |

### 论文辅助工具（论文写作辅助）

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `detect_paper_project` | 判断当前项目是否为 LaTeX/Markdown 论文项目 | 否 |
| `build_paper_map` | 生成论文项目地图（章节、bib、图表、labels、citations） | 否 |
| `summarize_latex_structure` | 总结 LaTeX 论文结构，指出章节安排和潜在问题 | 是（可选） |
| `find_paper_sections` | 查找 Introduction、Method、Experiments 等章节位置 | 否 |
| `review_paper_structure` | 检查论文整体结构是否完整（适合 IEEE 风格） | 是（可选） |
| `check_claim_evidence` | 检查强 claim 是否有表格、图、引用等 evidence 支撑 | 是（可选） |
| `parse_bib_file` | 解析 BibTeX 文件，输出引用库摘要 | 否 |
| `check_citation_coverage` | 检查正文 citation keys 与 refs.bib 是否一致 | 否 |

### 论文实验结果与表格核对工具

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `parse_latex_tables` | 解析 LaTeX 表格，提取 caption、label、列名、行名、数值和最佳值标记 | 否 |
| `extract_experiment_claims` | 从正文中提取实验相关 claim（best/outperform/ablation gain 等） | 是（可选） |
| `check_result_claim_consistency` | 检查正文实验 claim 是否被表格结果支持 | 是（可选） |
| `check_ablation_logic` | 检查消融实验是否完整，模块贡献是否清楚 | 是（可选） |
| `check_metric_consistency` | 检查 mAP、AP50、FPS 等指标格式是否统一 | 否 |

### 论文语言与 IEEE 风格审查工具

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `review_academic_paragraph` | 审查单段学术表达质量（中式英语、过强 claim、逻辑跳跃等） | 是（可选） |
| `check_abstract_quality` | 检查摘要是否覆盖背景、挑战、方法、创新、实验、结论 | 是（可选） |
| `check_introduction_logic` | 检查 Introduction 逻辑链（背景→挑战→不足→动机→方法→贡献） | 是（可选） |
| `check_contribution_clarity` | 检查贡献点是否清楚、具体、有证据、不过度宣传 | 是（可选） |
| `check_term_consistency` | 检查全文术语、缩写、方法名、指标名是否一致 | 是（可选） |
| `check_ieee_style` | 检查 IEEE/TGRS 风格问题（引用格式、缩写定义、口语表达等） | 是（可选） |

### 图表、Caption 与正文引用一致性审查工具

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `parse_figures_and_labels` | 解析 LaTeX 中的 figure、table、equation、label、ref 和 graphics 文件 | 否 |
| `check_figure_reference_consistency` | 检查图表/公式 label 是否存在、是否重复、是否被引用、图文件是否缺失 | 否 |
| `review_figure_caption` | 审查 figure caption 是否具体、清楚、符合 IEEE/TGRS 风格 | 是（可选） |
| `review_table_caption` | 审查 table caption 是否说明数据集、指标、比较对象和最佳值标记 | 是（可选） |
| `check_caption_text_consistency` | 检查 caption 与正文引用该图表附近文字是否一致 | 是（可选） |
| `check_equation_reference_consistency` | 检查公式 label、公式引用、符号解释和引用格式是否一致 | 是（可选） |

### Related Work 与参考文献增强工具

| 工具 | 作用 | 默认调用 LLM |
|------|------|-------------|
| `group_references_by_topic` | 根据本地 refs.bib 将参考文献按主题分组 | 是（可选） |
| `check_related_work_coverage` | 检查 Related Work 是否覆盖必要研究方向 | 是（可选） |
| `check_reference_recency` | 检查参考文献年份分布和近期文献比例 | 否 |
| `check_bibtex_quality` | 检查 BibTeX 条目字段缺失、重复、格式问题 | 否 |
| `suggest_citation_positions` | 检查正文中可能需要引用的位置，推荐本地 refs.bib 候选 | 是（可选） |
| `build_related_work_outline` | 根据论文主题和本地参考文献生成 Related Work 组织提纲 | 是（可选） |

## 安装

### Linux / macOS

```bash
cd cheap-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 设置你的 WORKSPACE_ROOT 和 LLM 配置
```

### Windows PowerShell

```powershell
cd cheap-agent
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env 设置你的 WORKSPACE_ROOT 和 LLM 配置
```

## 配置 `.env`

```env
# 允许读取的项目根目录
WORKSPACE_ROOT=/path/to/your/project

# OpenAI-compatible API（Ollama / DeepSeek / OpenRouter / vLLM 等）
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5-coder:7b

# 截断限制
MAX_FILE_CHARS=8000
MAX_OUTPUT_CHARS=6000

# 本地搜索/扫描限制
MAX_SCAN_FILE_SIZE_BYTES=2097152
MAX_SEARCH_RESULTS=50
MAX_CONTEXT_LINES=200

# MCP transport: stdio 或 streamable-http
MCP_TRANSPORT=stdio
MCP_HOST=127.0.0.1
MCP_PORT=8000
MCP_PATH=/mcp
```

## 本地测试

```bash
python test_stdio.py
```

会依次检查：配置加载、WORKSPACE_ROOT 存在、LLM 调用、文件审查逻辑。

## 启动 MCP Server

### stdio 模式（默认）

```bash
python server.py
```

运行后没有输出是正常的——MCP Server 通过 stdin/stdout 与 Client 通信。

### HTTP 模式（可选）

修改 `.env`：

```env
MCP_TRANSPORT=streamable-http
MCP_PORT=8000
```

然后：

```bash
python server.py
```

> 注意：不要将 HTTP MCP 暴露到公网。建议仅绑定 `127.0.0.1`。

## Codex MCP 配置

### Linux / macOS

在 `~/.codex/config.toml` 中添加：

```toml
[mcp_servers.local_code_agent]
command = "/absolute/path/to/cheap-agent/.venv/bin/python"
args = ["/absolute/path/to/cheap-agent/server.py"]
startup_timeout_sec = 30
tool_timeout_sec = 600
default_tools_approval_mode = "prompt"
```

### Windows

```toml
[mcp_servers.local_code_agent]
command = "C:\\absolute\\path\\to\\cheap-agent\\.venv\\Scripts\\python.exe"
args = ["C:\\absolute\\path\\to\\cheap-agent\\server.py"]
startup_timeout_sec = 30
tool_timeout_sec = 600
default_tools_approval_mode = "prompt"
```

## Codex 自定义指令建议

将以下内容加入项目的 `AGENTS.md`：

```text
本项目配置了 local_code_agent MCP 工具。遇到报错分析、文件审查、相关文件定位、
测试思路生成、项目结构理解等任务时，可以优先调用该 MCP 工具获取初步分析。
但该工具只是辅助分析者，不是最终决策者。不要让它修改文件，不要完全相信它的结论。
最终判断和代码修改由 Codex 自己完成。
```

## 使用示例

在 Codex 中，你可以直接使用：

### LLM 分析工具

- `review_file(file_path="src/train.py")` — 审查训练脚本
- `analyze_error_log(error_log="...")` — 分析报错
- `find_related_files(task="找出数据加载相关代码", keyword="data")` — 定位相关文件
- `generate_test_ideas(file_path="src/model.py")` — 生成测试思路
- `summarize_project()` — 了解项目结构

### 本地读取工具（快速，不调用 LLM）

- `read_file_around_line(file_path="src/train.py", line_number=158)` — 读取报错行附近代码
- `extract_symbols(file_path="src/model.py")` — 提取函数、类、import 结构
- `search_code(query="calculate_param")` — 搜索关键词在项目中的位置
- `search_code(query="TODO", file_glob="*.py")` — 只在 Python 文件中搜索 TODO

### 项目理解工具

- `build_project_map()` — 生成项目结构地图，包含目录、入口、配置分类
- `summarize_file(file_path="src/train.py")` — 总结文件作用和关键符号
- `summarize_directory(dir_path="models/")` — 总结目录职责和重要文件
- `detect_project_profile()` — 判断项目类型、技术栈、建议阅读顺序
- `summarize_file(file_path="src/train.py", use_llm=False)` — 只用规则摘要，不调用 LLM

### 错误诊断工具

- `analyze_traceback_with_context(error_log="Traceback...")` — 解析 traceback 并读取相关代码上下文
- `analyze_traceback_with_context(error_log="...", use_llm=False)` — 只用规则分析，不调用 LLM
- `diagnose_import_error(error_log="ModuleNotFoundError...")` — 诊断导入错误
- `diagnose_training_error(error_log="CUDA out of memory...")` — 诊断训练错误
- `diagnose_training_error(error_log="...", project_hint="YOLO project using ultralytics")` — 带项目上下文诊断
- `suggest_debug_steps(problem_description="训练时 loss 为 NaN")` — 生成调试计划

### 测试和验证工具

- `suggest_minimal_repro(problem_description="forward 报错")` — 生成最小复现方案
- `suggest_minimal_repro(problem_description="...", related_file="src/model.py")` — 带相关文件的复现方案
- `generate_unit_test_plan(file_path="src/utils.py")` — 为文件生成测试计划
- `generate_unit_test_plan(file_path="src/utils.py", target_symbol="calculate_param")` — 为特定函数生成测试计划
- `check_config_consistency()` — 检查配置文件一致性
- `check_config_consistency(config_path=".env.example")` — 检查特定配置文件
- `suggest_validation_plan(task_description="修改了训练脚本")` — 生成验证计划
- `suggest_validation_plan(task_description="...", changed_files="src/train.py\nconfig.py")` — 带修改文件的验证计划

### 代码审查工具

- `risk_check_before_edit(task_description="修改训练脚本", target_files="src/train.py")` — 修改前风险分析
- `review_diff(diff_text="diff --git a/...")` — 审查 diff
- `post_edit_review(task_description="修复 bug", changed_files="src/model.py")` — 修改后审查
- `post_edit_review(task_description="...", changed_files="src/model.py", diff_text="...")` — 带 diff 的修改后审查
- `analyze_change_impact(task_description="修改了函数签名", target_files="src/utils.py")` — 分析影响范围

### 缓存和记忆工具

- `cache_status()` — 查看当前 MCP 缓存状态
- `rebuild_project_index()` — 强制重建项目文件索引
- `get_cached_project_context()` — 快速获取缓存中的项目上下文
- `export_perf_report()` — 分析哪些 MCP 工具最慢
- `clear_cache()` — 只清理过期缓存
- `clear_cache(namespace="all")` — 清理全部缓存
- `clear_cache(namespace="tool_results")` — 清理指定命名空间

### 项目画像与启动上下文工具

- `get_codex_onboarding_pack()` — 快速获取当前项目启动上下文
- `get_codex_onboarding_pack(task_description="修复训练报错")` — 带任务的启动上下文
- `build_project_profile_v2()` — 生成完整项目画像
- `infer_project_runbook()` — 推断项目安装、启动和测试流程
- `recommend_workflow_for_task(task_description="修复训练报错")` — 推荐工具调用顺序
- `explain_project_conventions()` — 总结项目开发约定

### 论文辅助工具

- `detect_paper_project()` — 判断当前项目是否是论文项目
- `build_paper_map()` — 生成论文项目地图
- `summarize_latex_structure()` — 总结论文结构
- `find_paper_sections(query="method")` — 查找 Method 章节位置
- `review_paper_structure()` — 检查论文结构是否完整
- `check_claim_evidence()` — 检查强 claim 是否有 evidence 支撑
- `parse_bib_file()` — 解析 refs.bib
- `check_citation_coverage()` — 检查正文引用和 bib 是否一致

### 论文实验结果与表格核对工具

- `parse_latex_tables()` — 解析当前论文中的实验表格
- `parse_latex_tables(tex_path="sections/experiments.tex")` — 解析指定文件中的表格
- `extract_experiment_claims()` — 提取实验章节中的性能 claim
- `check_result_claim_consistency()` — 检查正文和表格结果是否一致
- `check_ablation_logic()` — 检查消融实验是否支撑方法模块
- `check_metric_consistency()` — 检查 mAP、AP50、FPS 等指标格式是否统一

### 论文语言与 IEEE 风格审查工具

- `review_academic_paragraph(paragraph="...")` — 审查单段学术表达质量
- `check_abstract_quality()` — 检查当前论文摘要是否完整
- `check_introduction_logic()` — 检查 Introduction 逻辑链是否自然
- `check_contribution_clarity()` — 检查贡献点是否具体且有实验支撑
- `check_term_consistency(terms_hint="SCD-DINO, Soft Top-K, scatter descriptor")` — 检查术语是否统一
- `check_ieee_style()` — 检查全文 IEEE/TGRS 风格问题

### 图表、Caption 与正文引用一致性审查工具

- `parse_figures_and_labels()` — 解析当前论文中的图表、公式和 label
- `check_figure_reference_consistency()` — 检查是否有未定义引用、未引用图表或缺失图文件
- `review_figure_caption(label="fig:query_refinement")` — 审查指定图注是否清楚
- `review_table_caption(label="tab:main_results")` — 审查指定表注是否完整
- `check_caption_text_consistency()` — 检查正文对图表的描述是否和 caption 一致
- `check_equation_reference_consistency()` — 检查公式引用和符号解释是否一致

### Related Work 与参考文献增强工具

- `group_references_by_topic()` — 将 refs.bib 按主题分组
- `check_related_work_coverage()` — 检查 Related Work 是否覆盖所需研究方向
- `check_reference_recency()` — 检查参考文献是否过旧
- `check_bibtex_quality()` — 检查 refs.bib 是否有字段缺失或格式问题
- `suggest_citation_positions()` — 检查 Introduction 和 Related Work 中哪些句子可能需要引用
- `build_related_work_outline()` — 生成 Related Work 的扩写提纲

## 安全说明

- **只读**：不提供写文件、删除文件功能
- **无 shell**：不暴露任意命令执行能力
- **路径限制**：所有文件访问限制在 `WORKSPACE_ROOT` 内，越界路径会被拒绝
- **无外部智能体**：不调用 opencode、mimo-code、codex CLI 等
- **HTTP 安全**：如果启用 HTTP transport，建议仅绑定 `127.0.0.1`，不要暴露到公网

## 项目结构

```
cheap-agent/
├── README.md              # 项目文档
├── requirements.txt       # Python 依赖
├── .env.example           # 环境变量模板
├── server.py              # MCP Server 入口
├── cheap_agent/           # 主包
│   ├── __init__.py
│   ├── config.py          # 配置加载
│   ├── llm_client.py      # OpenAI-compatible LLM 调用
│   ├── workspace.py       # 安全文件读取与路径工具
│   ├── cache.py           # 内存缓存系统
│   ├── cache_manager.py   # 磁盘缓存管理
│   ├── parsers/           # 文档解析器
│   │   ├── latex_parser.py
│   │   └── bib_parser.py
│   ├── prompts/           # 提示词模板
│   │   ├── base.py        # 基础编码提示词
│   │   └── paper.py       # 论文分析提示词
│   └── tools/             # MCP 工具业务逻辑
│       ├── code.py        # LLM 分析工具
│       ├── reading.py     # 本地读取工具
│       ├── project.py     # 项目理解工具
│       ├── diagnostics.py # 错误诊断工具
│       ├── testing.py     # 测试验证工具
│       ├── review.py      # 代码审查工具
│       ├── cache_tools.py # 缓存管理工具
│       ├── profile.py     # 项目画像工具
│       └── paper.py       # 论文辅助工具
└── tests/                 # 测试文件
    ├── test_stdio.py
    ├── test_reading.py
    ├── test_project.py
    ├── test_diagnostics.py
    ├── test_testing.py
    ├── test_review.py
    ├── test_cache.py
    ├── test_profile.py
    └── test_paper.py
```
