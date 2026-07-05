# Chapter 2. System Context & Container Architecture

---

# 2.1 System Context（系统上下文）

## Purpose

OptiMind 是企业决策支持系统中的一个核心智能组件。

它并不是一个独立存在的软件，而是位于企业业务系统、数据平台与优化求解器之间的 AI 决策中枢。

系统主要负责：

- 理解业务问题；
- 理解企业数据；
- 自动建立优化模型；
- 调用专业求解器；
- 解释求解结果；
- 生成业务决策建议。

因此，OptiMind 在整个企业 IT 架构中的定位如下：

```
                         Enterprise Information System

      ERP          WMS         MES         CRM        Excel / CSV
       │             │           │           │             │
       └─────────────┴───────────┴───────────┴─────────────┘
                               │
                               ▼
                     Data Intelligence Layer
                               │
                               ▼
                        Optimization Instance
                               │
                               ▼
                           OptiMind Core
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
      Knowledge          Optimization         Decision
        Engine              Engine             Engine
          │                    │                    │
          └────────────────────┼────────────────────┘
                               ▼
                        IBM CPLEX Solver
                               │
                               ▼
                    Optimization Result
                               │
                               ▼
                  Dashboard / REST API / Report
```

整个系统位于：

Business Data

↓

Optimization Computing

之间。

因此：

OptiMind 可以看作：

Enterprise Optimization Middleware。

---

# 2.2 External Systems（外部系统）

目前系统需要与以下外部系统进行交互。

---

## Business Data Sources

负责提供业务数据。

当前已实现：

```
CSV

Excel (.xlsx / .xls)
```

规划中：

```
MySQL

PostgreSQL

Oracle

REST API

ERP

SAP

MES

WMS

CRM
```

所有业务数据均首先进入：

Data Intelligence Layer。

禁止：

LLM

直接读取：

原始数据。

---

## Large Language Model

职责：

语义理解。

业务推理。

Prompt Planning。

Constraint Explanation。

Result Interpretation。

LLM：

永远不参与：

数值优化。

支持：

```
OpenAI

Qwen

DeepSeek

Claude

Gemini
```

采用统一：

LLM Interface。

后续：

无需修改：

业务代码。

---

## Optimization Solver

当前：

IBM CPLEX。

未来支持：

```
Gurobi

HiGHS

SCIP

OR-Tools
```

所有 Solver：

实现统一：

`SolverBackend` 抽象基类。

Workflow：

无需知道：

底层 Solver。

---

## Visualization Platform

负责：

展示：

```
Optimization Result

Dashboard

Scenario Analysis

Sensitivity Analysis

Network Graph

Map

Cost Breakdown
```

推荐：

```
Plotly

Streamlit
```

未来：

React。

---

# 2.3 Container Architecture（容器架构）

OptiMind 采用模块化容器架构。

整个系统划分为多个相互独立的 Container。

```
                    +--------------------------------+
                    |        Presentation Layer      |
                    |--------------------------------|
                    |  Streamlit / REST API / UI     |
                    +--------------------------------+
                                   │
                                   ▼
                    +--------------------------------+
                    |       Workflow Container       |
                    |--------------------------------|
                    |  LangGraph Orchestrator        |
                    +--------------------------------+
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
+------------------+      +------------------+      +------------------+
| Data Container   |      | Knowledge        |      | Optimization     |
|                  |      | Container        |      | Container        |
+------------------+      +------------------+      +------------------+
        │                          │                          │
        └───────────────┬──────────┴───────────────┬──────────┘
                        ▼                          ▼
                +-----------------------------------------+
                |          Solver Container               |
                |-----------------------------------------|
                |     IBM CPLEX / DOcplex / Future Solver |
                +-----------------------------------------+
                                   │
                                   ▼
                +-----------------------------------------+
                |      Decision Intelligence Container    |
                +-----------------------------------------+
```

Container 之间：

只能通过接口通信。

不得直接访问彼此内部对象。

---

# 2.4 Container Responsibilities（容器职责）

## Presentation Container

负责：

所有用户交互。

包括：

- 上传数据；
- 查看结果；
- 下载报告；
- API 调用。

禁止：

出现：

业务逻辑。

---

## Workflow Container

整个系统：

唯一调度中心。

负责：

Workflow。

State。

Task。

Retry。

Memory。

Node Routing。

Workflow：

永远：

不知道：

Solver。

只负责：

调度。

---

## Data Container

负责：

数据生命周期。

包括：

- Connector；
- Profiling；
- Cleaning；
- Validation；
- Schema Understanding；
- Feature Mapping；
- Optimization Instance。

输出：

标准化：

Optimization Instance。

---

## Knowledge Container

维护：

Optimization Ontology。

负责：

Knowledge Retrieval。

Template Management。

Constraint Library。

Variable Library。

未来：

GraphRAG。

全部：

放：

这里。

---

## Optimization Container

整个系统：

核心。

负责：

Problem Specification。

Intent Understanding。

Model Generation。

IR。

Verification。

Solver Routing。

这一层：

不负责：

业务展示。

---

## Solver Container

负责：

统一管理：

所有：

Solver。

包括：

CPLEX。

未来：

Gurobi。

HiGHS。

SCIP。

所有 Solver：

实现统一接口。

---

## Decision Intelligence Container

负责：

所有：

Business Intelligence。

包括：

Sensitivity Analysis。

Scenario Analysis。

Business Recommendation。

Visualization Data。

Report Generation。

这一层：

完全独立。

以后：

甚至：

可以：

脱离：

LLM。

---

# 2.5 Inter-Container Communication（容器通信）

所有 Container 必须遵循以下原则：

① 不共享内部状态；

② 不直接引用彼此实现类；

③ 不允许跨 Container 调用私有方法；

④ 所有通信通过 Interface 或统一数据模型完成；

⑤ 统一采用 Pydantic 数据模型作为数据交换协议。

典型的数据流如下：

```
Business Data
      │
      ▼
Data Container
      │
Optimization Instance
      │
      ▼
Optimization Container
      │
Intermediate Representation (IR)
      │
      ▼
Solver Container
      │
Solution
      │
      ▼
Decision Intelligence Container
      │
Business Report
      │
      ▼
Presentation Layer
```

任何模块新增功能时，都必须遵循上述通信规范，不允许绕过 Workflow 或直接访问其他 Container 内部实现。
