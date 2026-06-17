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

## 安全说明

- **只读**：不提供写文件、删除文件功能
- **无 shell**：不暴露任意命令执行能力
- **路径限制**：所有文件访问限制在 `WORKSPACE_ROOT` 内，越界路径会被拒绝
- **无外部智能体**：不调用 opencode、mimo-code、codex CLI 等
- **HTTP 安全**：如果启用 HTTP transport，建议仅绑定 `127.0.0.1`，不要暴露到公网

## 项目结构

```
cheap-agent/
├── README.md          # 本文件
├── requirements.txt   # Python 依赖
├── .env.example       # 环境变量模板
├── server.py          # MCP Server 入口
├── config.py          # 配置加载
├── llm_client.py      # OpenAI-compatible LLM 调用
├── workspace.py       # 安全文件读取与路径工具
├── prompts.py         # 提示词模板
├── tools_code.py      # LLM 分析工具逻辑
├── tools_reading.py   # 本地读取工具逻辑（不调用 LLM）
└── test_stdio.py      # 冒烟测试
```
