<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT License">
  <img src="https://img.shields.io/badge/Status-Alpha-orange?style=for-the-badge" alt="Alpha">
</p>

<h1 align="center">FractalClaw</h1>

<p align="center"><strong>A Tree-Structured Multi-Agent Framework with Recursive Delegation & Wave-Based Parallel Execution</strong></p>

<p align="center">
  <em>Fractals: infinitely complex, infinitely beautiful.<br>
  Agents creating agents, recursively.</em>
</p>

---

## What is FractalClaw?

FractalClaw is a Python framework for building **recursive, tree-structured multi-agent systems**. Inspired by fractal geometry — where self-similar patterns repeat at every scale — FractalClaw allows agents to dynamically spawn sub-agents, which can themselves spawn further sub-agents, forming a self-organizing execution tree.

Unlike flat agent orchestration frameworks, FractalClaw treats **delegation as a first-class concept**: every agent can plan, delegate subtasks to specialized child agents, evaluate results, and replan — all governed by deterministic safety rules that prevent infinite recursion, duplicate work, and budget exhaustion.

### Key Highlights

- **Recursive Agent Tree** — Agents dynamically create child agents at runtime, forming a fractal-like execution tree with configurable depth limits and delegation budgets.
- **Two-Phase Planning** — Phase 1 (LLM): lightweight decision on *whether* to delegate and *who* to delegate to. Phase 2 (Code): deterministic construction of the full plan — no LLM hallucination in structural fields.
- **Wave-Based Parallel Execution** — Independent subtasks run in parallel across execution waves, with write-scope conflict detection and fail-fast options.
- **Delegation Governance** — Deterministic rules enforce max depth, delegation budgets, fingerprint-based deduplication, and no-benefit-split detection to keep the tree healthy.
- **Smart Model Routing** — Different LLM models can be assigned to different task types (reasoning, coding, research, chat, writing) and automatically selected based on task profiles and depth decay.
- **Workspace Isolation** — Each agent gets an isolated workspace; child outputs are aggregated back to the parent with intelligent conflict resolution (e.g., merging `requirements.txt`, `package.json`).
- **Multi-Tier Memory** — Working memory, session memory, daily logs, procedural knowledge, and semantic memory with parent-child knowledge sharing.
- **Real-Time Monitoring** — WebSocket-based monitoring server and web visualization of the fractal agent tree.
- **MCP & Skills** — Built-in support for Model Context Protocol (MCP) tools and a skill system for reusable agent capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CLI / REPL                          │
│                  (fractal run / config)                  │
├─────────────────────────────────────────────────────────┤
│                   FractalClawApp                        │
│         Intent Recognition → Workspace Setup            │
│         → Config Generation → Execution                 │
├─────────────────────────────────────────────────────────┤
│                    Scheduler                            │
│          Task Projects · Agent Workspace                │
├─────────────────────────────────────────────────────────┤
│                  Agent Tree (Root)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Child A  │  │ Child B  │  │ Child C  │  ...        │
│  │ ┌──────┐ │  │          │  │ ┌──────┐ │             │
│  │ │Sub A'│ │  │          │  │ │Sub C'│ │             │
│  │ └──────┘ │  │          │  │ └──────┘ │             │
│  └──────────┘  └──────────┘  └──────────┘             │
├─────────────────────────────────────────────────────────┤
│  Plan-ReAct Loop: Plan → Execute → Evaluate → Reflect  │
│                    ↺ Replan (if needed)                 │
├─────────────────────────────────────────────────────────┤
│  LLM Engine │ Memory Manager │ Tool Manager │ Monitor  │
│  (Circuit   │ (Working/      │ (Builtin/    │ (Events/ │
│   Breaker)  │  Session/Log)  │  MCP/Skills) │  WS/Web)│
└─────────────────────────────────────────────────────────┘
```

## Core Concepts

### Agent Roles

| Role | Description | Default Tools |
|------|-------------|---------------|
| **Root** | Top-level orchestrator, full tool access | read, write, edit, search, find_files, bash, tavily_search, llm_generate |
| **Coordinator** | Manages sub-task delegation | Same as Root |
| **Worker** | Executes atomic tasks | read, write, edit, bash, search, find_files |
| **Specialist** | Domain-specific expert | Same as Worker |

### Execution Loop

Each `BaseAgent` follows a **Plan → Execute → Evaluate → Reflect → Replan** loop:

1. **Plan** — Two-phase planning decides delegation strategy
2. **Execute** — Wave-based parallel or serial execution of subtasks
3. **Evaluate** — LLM assesses whether the goal was achieved
4. **Reflect** — Optional self-reflection on the execution
5. **Replan** — If the goal is not met, replan with failure context (up to `max_replan_attempts`)

### Delegation Governance

The `DelegationGovernance` module enforces deterministic safety rules:

- **Max Depth** — Prevents infinite recursion (default: 5 levels)
- **Delegation Budget** — Caps total delegations per tree (default: 20)
- **Branch Budget** — Caps delegations per branch (default: 6)
- **Fingerprint Deduplication** — Prevents the same task from being delegated twice in the same branch
- **No-Benefit Split Detection** — Downgrades delegation when a single subagent would just duplicate the parent's work

### Wave-Based Execution

The `PlanExecutionEngine` organizes tasks into execution waves:

```
Wave 1: [Task A (parallel)] [Task B (parallel)] [Task C (serial)]
Wave 2: [Task D (parallel)] [Task E (serial)]
  ...
```

Tasks marked `parallel_safe` with non-overlapping `write_scope` run concurrently. Conflicting tasks are automatically serialized.

## Quick Start

### Prerequisites

- Python 3.10+
- An OpenAI-compatible API key (OpenAI, DeepSeek, Qwen, GLM, etc.) or local Ollama

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/fractalclaw.git
cd fractalclaw

# Install the package
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### Configuration

```bash
# Interactive configuration wizard
fractal config
```

The wizard will guide you through:
1. Selecting a model provider (OpenAI, Anthropic, Aliyun, Tencent, DeepSeek, Ollama, etc.)
2. Entering your API key and base URL
3. Specifying the default model
4. (Optional) Configuring task-specific models for reasoning, coding, research, chat, and writing

Alternatively, copy `.env.example` to `.env` and fill in your values manually.

### Run

```bash
# Start the interactive REPL
fractal run

# Execute a single task directly
fractal task "Build a Flask REST API for a todo app"

# List available agents
fractal list

# View workspace info
fractal workspace

# Start the monitoring server
fractal monitor --server --port 8765

# Start the web visualization
fractal monitor --web --web-port 8080
```

## Project Structure

```
fractalclaw/
├── src/fractalclaw/
│   ├── agent/            # Core agent abstractions
│   │   ├── base.py       # Agent, BaseAgent, AgentConfig, Plan-ReAct loop
│   │   ├── tree.py       # AgentTree — parent-child relationships
│   │   ├── execution.py  # DelegationGovernance, PlanExecutionEngine
│   │   ├── factory.py    # AgentFactory — static & runtime agent creation
│   │   ├── loader.py     # ConfigLoader — YAML config parsing
│   │   ├── config_generator.py  # LLM-powered agent config generation
│   │   └── config_validator.py  # Config validation
│   ├── llm/              # LLM integration layer
│   │   ├── engine.py     # LLMEngine with circuit breaker
│   │   ├── model_selector.py    # Smart model selection
│   │   ├── model_router.py      # Task-type → model routing
│   │   ├── task_classifier.py   # Keyword-based task classification
│   │   └── provider_pool.py     # Multi-provider management
│   ├── memory/           # Multi-tier memory system
│   │   ├── manager.py    # MemoryManager — unified interface
│   │   ├── working_memory.py    # Short-term working memory
│   │   ├── session.py    # Session tracking
│   │   ├── sharing.py    # Parent-child knowledge sharing
│   │   ├── daily_log.py  # Daily activity logs
│   │   └── markdown_store.py    # Markdown-based persistence
│   ├── plan/             # Planning module
│   │   └── manager.py    # PlanManager, Plan, Task models
│   ├── tools/            # Tool system
│   │   ├── builtin/      # Built-in tools (read, write, bash, search, etc.)
│   │   ├── mcp/          # Model Context Protocol client
│   │   ├── skills/       # Skill loader & parser
│   │   └── definitions.py # Tool aliases & role defaults
│   ├── scheduler/        # Task scheduling & workspace management
│   │   ├── scheduler.py  # Scheduler, TaskProject
│   │   └── agent_workspace.py  # AgentWorkspaceManager
│   ├── monitor/          # Real-time monitoring
│   │   ├── events.py     # Event types & emission
│   │   ├── fractal_tree.py # Tree data for visualization
│   │   └── static/       # Web UI (HTML/JS/CSS)
│   └── entry/            # Application entry points
│       ├── main.py       # FractalClawApp — interactive REPL
│       ├── cli.py        # Typer CLI (fractal config/run/task/monitor)
│       ├── monitor_server.py  # WebSocket monitoring server
│       └── monitor_web.py     # Web monitoring interface
├── configs/              # Configuration files
│   ├── settings.yaml     # Global settings (LLM, behavior, memory, planning, tools)
│   ├── models.yaml       # Model registry
│   └── basic_agents/     # Predefined agent configs
│       ├── agent_intent_recognition.yaml
│       └── agent_search_tool.yaml
├── tests/                # Test suite
├── .env.example          # Environment variable template
├── pyproject.toml        # Project metadata & dependencies
└── LICENSE               # MIT License
```

## Configuration

### Global Settings (`configs/settings.yaml`)

```yaml
llm:
  temperature: 0.7
  max_tokens: 8192
  stream: true
  timeout: 60.0

behavior:
  max_iterations: 5
  enable_planning: true
  enable_reflection: true
  max_replan_attempts: 5

memory:
  max_working_entries: 10
  enable_persistence: true
  enable_session_save: true
  enable_daily_log: true
  enable_working_memory: true
  heartbeat_interval_hours: 24

planning:
  max_depth: 5
  max_subtasks: 10
  enable_parallel: true

tools:
  max_concurrent_calls: 5
  default_timeout: 30.0
  enable_approval: false
```

### Task-Specific Model Routing

Configure different models for different task types in `.env`:

```env
MODEL_REASONING=deepseek/deepseek-chat
MODEL_CODE=deepseek/deepseek-coder
MODEL_RESEARCH=openai/gpt-4
MODEL_CHAT=openai/gpt-3.5-turbo
MODEL_WRITING=anthropic/claude-3-sonnet
```

### Supported Providers

| Provider | Environment Variable | Base URL |
|----------|---------------------|----------|
| OpenAI | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| Anthropic | `ANTHROPIC_API_KEY` | `https://api.anthropic.com` |
| DeepSeek | `OPENAI_API_KEY` | `https://api.deepseek.com/v1` |
| Aliyun (Qwen) | `OPENAI_API_KEY` | `https://dashscope.aliyuncs.com/api/v1` |
| Zhipu (GLM) | `OPENAI_API_KEY` | `https://open.bigmodel.cn/api/paas/v4` |
| Tencent | `OPENAI_API_KEY` | Provider-specific |
| Ollama | — | `http://localhost:11434` |
| Custom | `OPENAI_API_KEY` | Your endpoint |

All providers except Anthropic and Ollama use the OpenAI-compatible API interface.

## Built-in Tools

| Tool | Description |
|------|-------------|
| `read` | Read file contents |
| `write` | Write content to a file |
| `write_chunked` | Write large files in chunks |
| `edit` | Edit file contents |
| `bash` | Execute shell commands |
| `search` | Search for patterns in files |
| `find_files` | Find files by name pattern |
| `tavily_search` | Web search via Tavily API |
| `llm_generate` | Generate text using LLM |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy src/fractalclaw
```

