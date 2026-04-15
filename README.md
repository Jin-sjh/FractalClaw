# FractalClaw

A powerful AI Agent framework with hierarchical agent architecture.

## Features

- Hierarchical Agent Tree Structure
- Plan-ReAct Execution Loop
- Configurable via YAML
- Tool Management
- Memory Management
- Planning System

## Installation

```bash
pip install -e .
```

## Quick Start

### Step 1: Configuration

Before first use, you need to configure your API key and model:

```bash
fractalclaw config
```

This will launch an interactive configuration wizard to set up:
- Model provider (OpenAI, Anthropic, Aliyun, Tencent, Ollama, etc.)
- Model name (gpt-4, qwen-max, glm-4, etc.)
- API Key
- Base URL (optional, for proxies or compatible services)

Alternatively, you can manually configure by copying the example file:

```bash
cp .env.example .env
# Then edit .env and fill in your API key and model settings
```

### Step 2: Start Interactive Session

```bash
fractalclaw run
```

This will launch the FractalClaw interactive terminal where you can input tasks.

### Step 3: Execute Tasks

After starting, simply type your task description and press Enter. The system will:
1. Analyze your intent
2. Confirm understanding with you
3. Generate appropriate agent configuration
4. Execute the task

Type `/exit` to quit, or `/new` to start a new session.

## CLI Commands

| Command | Description |
|---------|-------------|
| `fractalclaw config` | Interactive configuration wizard |
| `fractalclaw run` | Start interactive session |
| `fractalclaw task "your task"` | Execute a single task directly |
| `fractalclaw list` | List all available agents |
| `fractalclaw workspace` | Show workspace information |
| `fractalclaw monitor` | Launch monitoring dashboard |

## Programmatic Usage

```python
from pathlib import Path
from fractalclaw.agent import AgentFactory, AgentContext

# Create factory
factory = AgentFactory(config_dir=Path("configs"))

# Create agent from YAML config
coder = factory.create("coder")

# Run task
context = AgentContext(task="Implement a quick sort algorithm")
result = await coder.run(context)
```

## Configuration

### Global Settings (configs/settings.yaml)

```yaml
llm:
  model: "gpt-4"
  temperature: 0.7

behavior:
  max_iterations: 10
  enable_planning: true
```

### Agent Configuration (configs/agents/coder.yaml)

```yaml
name: "CodeAgent"
description: "Code Expert Agent"
role: specialist

llm:
  temperature: 0.3

system_prompt: |
  You are a professional code assistant...

tools:
  - name: "read_file"
    description: "Read file content"
    parameters:
      type: object
      properties:
        path:
          type: string
      required: ["path"]
```

## Roadmap

### Phase 1: Core Enhancement (1-2 weeks)

#### 1.1 Agent Intrinsic Properties Configuration
**Status**: Planned
**Priority**: P0

为 Agent 配置创建固有属性功能，支持：
- Agent 能力标签定义
- Agent 专长领域声明
- Agent 行为约束配置
- Agent 资源限制设置

```yaml
intrinsic_properties:
  capabilities: ["code_generation", "file_operations", "web_search"]
  expertise: ["python", "javascript", "data_analysis"]
  constraints:
    max_file_size: 10MB
    allowed_extensions: [".py", ".js", ".md"]
  resource_limits:
    max_memory: 512MB
    max_execution_time: 300s
```

#### 1.2 Test Coverage Enhancement
- [ ] Agent base class unit tests
- [ ] Plan module tests
- [ ] Memory system tests
- [ ] Tools manager tests
- [ ] Integration test cases

#### 1.3 CLI Enhancement
- [ ] Interactive task input
- [ ] Agent config hot reload
- [ ] Real-time execution log
- [ ] Result export

---

### Phase 2: Visualization & Monitoring (2-4 weeks)

#### 2.1 Fractal Progress Display Interface
**Status**: Planned
**Priority**: P1

开发分形进度显示界面，能够直观看到处理流程：
- 树状 Agent 结构可视化
- 实时任务执行状态
- 分形递归过程展示
- 节点间通信可视化
- 执行时间统计

```
┌─────────────────────────────────────────────────────────────┐
│                    Fractal Progress View                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Root Agent ────────────────────────────────────── [RUNNING] │
│    │                                                         │
│    ├── Coordinator 1 ──────────────────────────── [DONE]     │
│    │     │                                                    │
│    │     ├── Worker 1 ─────────────────────────── [DONE]     │
│    │     └── Worker 2 ─────────────────────────── [RUNNING]  │
│    │                                                          │
│    └── Coordinator 2 ──────────────────────────── [PENDING]  │
│          │                                                    │
│          └── Specialist ───────────────────────── [WAITING]  │
│                                                              │
│  Progress: ████████████░░░░░░░░ 60%  (6/10 tasks)           │
│  Time: 45.2s | Iterations: 23 | Tools: 15                    │
└─────────────────────────────────────────────────────────────┘
```

#### 2.2 ModelSelector Intelligence
- [ ] Dynamic weight calculator
- [ ] LLM task analyzer
- [ ] Selection history learning

#### 2.3 Built-in Tools Extension
- [ ] Code execution sandbox
- [ ] Web fetch tool
- [ ] Database operations
- [ ] Git operations

---

### Phase 3: Security & Sandbox (4-6 weeks)

#### 3.1 Agent Sandbox System
**Status**: Planned
**Priority**: P1

开发沙箱功能，限制各个 Agent 访问权限，保证安全：
- 文件系统隔离
- 网络访问控制
- 资源使用限制
- 危险操作拦截
- 权限继承机制

```yaml
sandbox:
  file_system:
    mode: "restricted"
    allowed_paths:
      - "${workspace}/src"
      - "${workspace}/output"
    denied_patterns:
      - "*.env"
      - "*.key"
      - ".git/**"
  
  network:
    enabled: true
    allowed_domains:
      - "api.openai.com"
      - "github.com"
    denied_ports: [22, 3306, 5432]
  
  execution:
    max_cpu_percent: 50
    max_memory_mb: 512
    max_processes: 5
    timeout_seconds: 300
  
  permissions:
    allow_shell: false
    allow_network: true
    allow_file_write: true
    allow_file_delete: false
```

#### 3.2 Memory System Enhancement
- [ ] Vector-based memory retrieval
- [ ] Memory importance evaluation
- [ ] Cross-session persistence

#### 3.3 Parallel Execution Optimization
- [ ] Task parallel scheduling
- [ ] Resource conflict handling
- [ ] Deadlock detection

---

### Phase 4: Ecosystem (6-8 weeks)

#### 4.1 Agent Template Library
- [ ] General agent templates
- [ ] Domain-specific templates
- [ ] Template marketplace

#### 4.2 Tool Ecosystem
- [ ] Tool development SDK
- [ ] Third-party integration guide
- [ ] Tool marketplace

#### 4.3 Documentation
- [ ] API reference
- [ ] Developer guide
- [ ] Best practices
- [ ] Example projects

---

## Priority Summary

| Priority | Feature | Description |
|----------|---------|-------------|
| P0 | Agent Intrinsic Properties | Agent 固有属性配置 |
| P0 | Test Coverage | 测试覆盖增强 |
| P1 | Fractal Progress Display | 分形进度显示界面 |
| P1 | Sandbox System | 沙箱安全系统 |
| P1 | ModelSelector Intelligence | 模型选择智能化 |
| P2 | Memory Enhancement | 记忆系统增强 |
| P3 | Ecosystem Building | 生态建设 |

---

## Milestones

```
v0.2.0 ─── Core Enhancement ─── Test coverage > 80%
   │
v0.3.0 ─── Visualization ─── Fractal progress display complete
   │
v0.4.0 ─── Security ─── Sandbox system complete
   │
v1.0.0 ─── Release ─── Documentation complete, ecosystem established
```

## License

MIT
