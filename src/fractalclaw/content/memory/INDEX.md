# Global Memory Index

Last Updated: 2026-04-13T20:44:00

## 目录结构

```
content/memory/
├── INDEX.md              # 本文件 - 全局记忆索引
├── daily/                # 全局日志目录（按日期记录）
├── procedural/           # 过程记忆 - 工作流程和最佳实践
│   └── best_practices.md
├── semantic/             # 语义记忆 - 项目知识和标准
│   └── project_standards.md
└── working_memory.md     # 工作记忆 - 当前状态
```

## SEMANTIC（语义记忆）

存储项目级别的知识和标准，所有 Agent 共享。

| 文件 | 描述 | 更新时间 |
|------|------|----------|
| project_standards.md | 项目标准规范 | 2026-04-12 |

## PROCEDURAL（过程记忆）

存储工作流程和最佳实践。

| 文件 | 描述 | 更新时间 |
|------|------|----------|
| best_practices.md | 最佳实践指南 | 2026-04-12 |

## WORKING MEMORY（工作记忆）

当前活跃的工作状态，定期心跳更新。

| 文件 | 描述 | 最后心跳 |
|------|------|----------|
| working_memory.md | 工作记忆状态 | 2026-04-13 |

## DAILY LOG（全局日志）

按日期记录的全局执行日志，存储在 `daily/` 目录下。
