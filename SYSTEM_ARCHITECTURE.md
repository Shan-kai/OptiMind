# SYSTEM_ARCHITECTURE.md

> Project Name: OptiMind
>
> Subtitle: Optimization Copilot — AI-native Decision Intelligence Platform for Operations Research
>
> Version: v1.0
>
> Status: 核心架构已完成（Core Architecture Completed）

---

> 本文档是 OptiMind 系统架构的**总览索引**。完整章节内容按层拆分至 [docs/architecture/](docs/architecture/) 目录下，便于独立维护与检索。

---

# 1. Architecture Overview（系统总体架构）

OptiMind 是一个面向运筹优化（Operations Research，OR）的 AI 原生智能决策平台（AI-native Decision Intelligence Platform）。系统通过复合大语言模型（LLM）、运筹优化知识本体（Optimization Ontology）、数学规划建模技术以及工业级求解器（IBM CPLEX），构建一条完整的智能优化 Pipeline，实现从业务需求理解到优化建模、求解分析以及决策支持的自动化流程。

与传统 AI Agent 不同，OptiMind 并不依赖 LLM 独立完成优化问题求解，而是采用“LLM + Knowledge + Optimization + Software Engineering”四位一体的架构思想。

整个系统主张：

- 模块解耦（Loose Coupling）
- 高内聚（High Cohesion）
- 可扩展（Scalability）
- 可测试（Testability）
- 可维护（Maintainability）
- Solver-Centric（求解器中心）
- Knowledge-Driven（知识驱动）

系统采用分层架构（Layered Architecture），各模块通过统一的数据契约（Intermediate Representation, IR）进行通信，避免模块间直接耦合。

详见：[01-architecture-overview.md](docs/architecture/01-architecture-overview.md)

---

# 2. 系统分层一览（六层架构）

```
┌──────────────────────────────────────────┐
│            Presentation Layer            │  ← React frontend + Streamlit dashboard
├──────────────────────────────────────────┤
│            Workflow Layer                │
├──────────────────────────────────────────┤
│        Data Intelligence Layer           │
├──────────────────────────────────────────┤
│     Optimization Intelligence Layer      │
├──────────────────────────────────────────┤
│       Decision Intelligence Layer        │
├──────────────────────────────────────────┤
│   Infrastructure & External Services     │
└──────────────────────────────────────────┘
```

每一层均通过统一接口通信，禁止跨层直接调用。

---

# 3. 高层工作流（End-to-End Pipeline）

```
业务数据
    │
    ▼
Data Intelligence
    │
    ▼
Optimization Instance
    │
    ▼
Intent Understanding
    │
    ▼
Problem Specification
    │
    ▼
Optimization Ontology
    │
    ▼
Knowledge Retrieval (RAM)
    │
    ▼
Model Generator
    │
    ▼
Intermediate Representation (IR)
    │
    ▼
Model Verification
    │
    ▼
Solver Router
    │
    ▼
Solver Backend (CPLEX / HiGHS / Mock)
    │
    ▼
Solution Validation
    │
    ▼
Post-Optimal Analysis
    │
    ▼
Business Recommendation
    │
    ▼
Visualization Dashboard
```

该流程是 OptiMind 的唯一官方 Pipeline。任何新增功能必须围绕该 Pipeline 扩展，不得绕过核心流程。

---

# 4. 章节目录（Chapter Index）

| 章节 | 内容 | 文档 |
| ---- | ---- | ---- |
| Chapter 1 | Architecture Overview（系统总体架构） | [01-architecture-overview.md](docs/architecture/01-architecture-overview.md) |
| Chapter 2 | System Context & Container Architecture | [02-system-context-container.md](docs/architecture/02-system-context-container.md) |
| Chapter 3 | Domain Model（领域模型设计） | [03-domain-model.md](docs/architecture/03-domain-model.md) |
| Chapter 4 | Data Intelligence Layer（数据智能层设计） | [04-data-intelligence-layer.md](docs/architecture/04-data-intelligence-layer.md) |
| Chapter 5 | Optimization Intelligence Layer（优化智能层设计） | [05-optimization-intelligence-layer.md](docs/architecture/05-optimization-intelligence-layer.md) |
| Chapter 6 | Solver Layer（求解器层设计） | [06-solver-layer.md](docs/architecture/06-solver-layer.md) |
| Chapter 7 | Decision Intelligence Layer（决策智能层设计） | [07-decision-intelligence-layer.md](docs/architecture/07-decision-intelligence-layer.md) |
| Chapter 8 | Workflow & Orchestration Layer（工作流与编排层设计） | [08-workflow-orchestration-layer.md](docs/architecture/08-workflow-orchestration-layer.md) |
| Chapter 9 | Infrastructure & Deployment Architecture（基础设施与部署架构） | [09-infrastructure-deployment.md](docs/architecture/09-infrastructure-deployment.md) |
| Chapter 10 | System Summary & Architecture Conclusion（系统总结） | [10-system-summary.md](docs/architecture/10-system-summary.md) |

---

# 5. 配套规范（Companion Specs）

| 规范 | 文档 |
| ---- | ---- |
| Intermediate Representation | [docs/specs/IR_SPEC.md](docs/specs/IR_SPEC.md) |
| API 接口规范 | [docs/specs/API_SPEC.md](docs/specs/API_SPEC.md) |
| 数据规范 | [docs/specs/DATA_SPEC.md](docs/specs/DATA_SPEC.md) |
| 优化知识本体规范 | [docs/specs/ONTOLOGY_SPEC.md](docs/specs/ONTOLOGY_SPEC.md) |
| 测试规范 | [docs/specs/TEST_SPEC.md](docs/specs/TEST_SPEC.md) |
| 编码规范 | [docs/specs/CODING_STANDARD.md](docs/specs/CODING_STANDARD.md) |

---

# 6. 规范引用（Related Documents）

- [PROJECT.md](PROJECT.md) — 项目愿景与定位
- [ROADMAP.md](ROADMAP.md) — 开发路线图与里程碑
- [README.md](README.md) — 工程入口说明
