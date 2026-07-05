# 1. Architecture Overview（系统总体架构）

## 1.1 Introduction（简介）

OptiMind 是一个面向运筹优化（Operations Research，OR）的 AI 原生智能决策平台（AI-native Decision Intelligence Platform）。

系统通过融合大语言模型（LLM）、运筹优化知识体系（Optimization Ontology）、数学规划建模技术以及工业级求解器（IBM CPLEX），构建一条完整的智能优化 Pipeline，实现从业务需求理解到优化建模、求解分析以及决策支持的自动化流程。

与传统 AI Agent 不同，OptiMind 并不依赖 LLM 独立完成优化问题求解，而是采用"LLM + Knowledge + Optimization + Software Engineering"四位一体的架构思想。

整个系统强调：

- 模块解耦（Loose Coupling）
- 高内聚（High Cohesion）
- 可扩展（Scalability）
- 可测试（Testability）
- 可维护（Maintainability）
- Solver-Centric（求解器中心）
- Knowledge-Driven（知识驱动）

系统采用分层架构（Layered Architecture），各模块通过统一的数据契约（Intermediate Representation, IR）进行通信，避免模块间直接耦合。

---

# 1.2 Design Goals（设计目标）

OptiMind 的设计目标包括：

## （1）工业级架构

整个系统遵循工业软件设计规范，而非实验性 Agent Demo。

系统中的每一个模块均具有清晰职责，可以独立开发、独立测试、独立部署。

---

## （2）AI 与运筹优化深度融合

充分发挥：

LLM

负责：

- 理解
- 推理
- 规划
- 解释

Optimization Engine

负责：

- 建模
- 优化
- 求解

形成 AI + OR 的完整闭环。

---

## （3）统一的数据流

整个系统所有模块共享统一的数据结构。

任何模块之间禁止直接交换自然语言。

统一采用：

Intermediate Representation（IR）

作为唯一的数据交换格式。

这样能够：

- 保证一致性
- 提高可测试性
- 降低耦合
- 支持多求解器

---

## （4）知识驱动建模

系统不允许 LLM 从零生成数学模型。

所有模型必须建立在：

Optimization Ontology

Optimization Templates

Knowledge Retrieval

基础之上。

这样能够有效降低：

- Hallucination
- Constraint Missing
- Variable Missing

等问题。

---

## （5）Solver First

OptiMind 永远相信：

Solver

而不是：

LLM。

所有数学优化结果必须来自：

IBM CPLEX

任何分析都建立在 Solver 输出基础之上。

---

## （6）持续可扩展

平台未来支持：

- Gurobi
- HiGHS
- SCIP
- OR-Tools
- GraphRAG
- Multi-Agent
- MCP
- Digital Twin
- Reinforcement Learning

因此架构必须支持：

Plug-in Extension。

---

# 1.3 Architecture Principles（架构原则）

整个系统遵循以下原则：

---

## Principle 1

Single Responsibility Principle（SRP）

每一个模块只负责一项工作。

例如：

Data Profiling

只负责：

数据画像。

不负责：

数据清洗。

---

## Principle 2

Open-Closed Principle（OCP）

系统允许：

新增：

Solver

Algorithm

Knowledge

Problem

而无需修改已有代码。

---

## Principle 3

Interface-Oriented Design

模块之间仅依赖：

接口。

例如：

```
SolverBackend  (src/opti_mind/solver/backends/base.py)

IOntologyService  (src/opti_mind/ontology/service.py)

ILLMClient  (src/opti_mind/core/llm_client.py)

ISchemaInterpreter  (src/opti_mind/data/schema.py)
```

任何实现均可替换。

---

## Principle 4

Configuration over Hard Coding

禁止：

```
API Key

Model Name

Prompt

Solver Parameter

Magic Number
```

出现在源码。

统一：

Config。

---

## Principle 5

Deterministic Before AI

如果能够使用：

Python

规则

算法

完成。

则：

绝不调用：

LLM。

LLM：

仅用于：

语义理解。

推理。

解释。

---

## Principle 6

Knowledge Before Generation

生成之前必须：

Retrieve。

不允许：

直接：

Generate。

---

## Principle 7

Validation Before Solving

任何数学模型：

必须：

Validation。

之后：

才能：

Solver。

---

## Principle 8

Analysis After Optimization

求解结束不是结束。

必须：

Sensitivity

Scenario

Business Recommendation

形成：

Decision Intelligence。

---

# 1.4 Layered Architecture（系统分层）

整个系统划分为六层：

```
┌────────────────────────────────────────────┐
│               Presentation Layer           │
└────────────────────────────────────────────┘
                     │
┌────────────────────────────────────────────┐
│              Workflow Layer                │
└────────────────────────────────────────────┘
                     │
┌────────────────────────────────────────────┐
│        Data Intelligence Layer             │
└────────────────────────────────────────────┘
                     │
┌────────────────────────────────────────────┐
│   Optimization Intelligence Layer          │
└────────────────────────────────────────────┘
                     │
┌────────────────────────────────────────────┐
│      Decision Intelligence Layer           │
└────────────────────────────────────────────┘
                     │
┌────────────────────────────────────────────┐
│ Infrastructure & External Services Layer   │
└────────────────────────────────────────────┘
```

每一层均通过统一接口通信。

禁止跨层直接调用。

---

# 1.5 Layer Responsibilities（各层职责）

## ① Presentation Layer

负责：

用户交互。

包括：

- Web UI
- Dashboard
- REST API
- 文件上传
- 结果展示

推荐技术：

- Streamlit
- FastAPI

该层不包含任何业务逻辑。

---

## ② Workflow Layer

整个系统的大脑。

负责：

调度所有模块。

推荐：

LangGraph。

Workflow 负责：

```
State

Task

Memory

Node

Retry

Interrupt
```

但：

Workflow 不负责：

优化算法。

---

## ③ Data Intelligence Layer

负责：

业务数据理解。

包括：

- Data Connector
- Data Profiling
- Data Quality Check
- Schema Understanding
- Feature Mapping
- Optimization Instance

输出：

标准化 Optimization Instance。

---

## ④ Optimization Intelligence Layer

整个系统：

核心。

包括：

- Intent Understanding
- Problem Specification
- Ontology
- Knowledge Retrieval
- Model Generator
- IR
- Verification
- Solver Router
- Solver

这一层：

真正完成：

数学建模。

---

## ⑤ Decision Intelligence Layer

负责：

结果分析。

包括：

- Sensitivity Analysis
- Scenario Analysis
- Resource Utilization
- Constraint Analysis
- Business Recommendation

输出：

Business Report。

---

## ⑥ Infrastructure Layer

负责：

所有：

公共能力。

包括：

- Config
- Logging
- Cache
- Database
- Docker
- Monitoring
- Authentication（未来）

所有业务模块均不得直接依赖底层实现，而应通过统一接口访问基础设施。

---

# 1.6 High-Level Workflow（高层工作流）

整个系统遵循以下工作流程：

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
IBM CPLEX
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

该流程是 OptiMind 的唯一官方 Pipeline。

任何新增功能必须围绕该 Pipeline 扩展，而不得绕过核心流程。
