
# ROADMAP.md

> Project Name: OptiMind
>
> Subtitle: Optimization Copilot — AI-native Decision Intelligence Platform for Operations Research
>
> Version: v1.0
>
> Status: 核心阶段已完成（Core Phases Completed）

---

# 1. Development Philosophy（开发理念）

OptiMind 采用 **Documentation First、Architecture First、Iterative Development** 的开发模式。

整个项目并非一次性完成，而是按照工业软件研发流程逐步演进，每个阶段均具有明确目标、可交付成果（Deliverables）和验收标准（Acceptance Criteria）。

开发遵循：

```
需求分析
    ↓
系统设计
    ↓
接口设计
    ↓
模块开发
    ↓
单元测试
    ↓
集成测试
    ↓
系统测试
    ↓
部署发布
```

每完成一个阶段，都必须进行：

- Code Review
- Architecture Review
- Refactoring
- Documentation Update

之后才能进入下一阶段。

---

# 2. Development Roadmap

```
Phase 0
Project Foundation
        │
        ▼
Phase 1
System Infrastructure
        │
        ▼
Phase 2
Data Intelligence
        │
        ▼
Phase 3
Optimization Ontology
        │
        ▼
Phase 4
Knowledge Retrieval (RAM)
        │
        ▼
Phase 5
Optimization Modeling
        │
        ▼
Phase 6
Model Verification
        │
        ▼
Phase 7
Solver Integration
        │
        ▼
Phase 8
Decision Intelligence
        │
        ▼
Phase 9
Visualization
        │
        ▼
Phase 10
Deployment
```

---

# Phase 0：Project Foundation（项目基础建设）

## Goal

完成项目基础规范建设，为后续开发提供统一标准。

---

## Tasks

建立：

```
README.md
PROJECT.md
ROADMAP.md
SYSTEM_ARCHITECTURE.md           # 架构总览索引

docs/architecture/                # 架构各章拆分（详见 SYSTEM_ARCHITECTURE.md 目录）
docs/specs/
    IR_SPEC.md                    # 中间表示规范
    API_SPEC.md                   # API 接口规范
    DATA_SPEC.md                  # 数据规范
    ONTOLOGY_SPEC.md              # 优化知识本体规范
    TEST_SPEC.md                  # 测试规范
    CODING_STANDARD.md            # 编码规范
```

建立 Git 仓库。

建立基础目录结构。

建立 Python 项目。

建立 Docker 环境。

建立 Ruff、Black、MyPy、Pytest。

建立 CI（GitHub Actions）。

---

## Deliverables

✔ 文档规范

✔ 工程框架

✔ 开发环境

---

## Acceptance Criteria

所有开发文档完成。

能够运行：

```
pytest

ruff

black

mypy
```

全部通过。

---

# Phase 1：System Infrastructure（系统基础设施）

## Goal

搭建整个平台基础框架。

---

## Tasks

完成：

```
FastAPI

LangGraph

Configuration

Logging

Dependency Injection

Exception Handler

Configuration Manager

Workflow Skeleton
```

建立：

```
app/

core/

workflow/

config/

tests/
```

---

## Deliverables

整个项目可以正常启动。

FastAPI 正常运行。

LangGraph 可运行空流程。

---

## Acceptance Criteria

启动：

```
uvicorn
```

即可访问 API。

Workflow 可以正常执行。

---

# Phase 2：Data Intelligence

## Goal

完成数据智能层。

实现：

业务数据

↓

Optimization Instance

自动转换。

---

## Modules

### Data Connector

当前支持：

```
CSV

Excel (.xlsx / .xls)
```

后续支持：

```
SQL

JSON
```

---

### Data Profiling

自动统计：

- 缺失率
- 数据类型
- 数值范围
- 类别分布
- 唯一值

输出：

Data Profile Report。

---

### Data Quality Check

自动检测：

```
Missing Value

Outlier

Duplicate

Invalid Coordinate

Unit Conflict

Invalid Encoding
```

---

### Schema Understanding

LLM / 启发式规则自动理解字段含义。

例如：

```
Qty

↓

Demand
```

```
value / weight / capacity

↓

Knapsack
```

---

### Problem Type Detection

根据列名和语义自动推断问题类型：

```
facility_location
assignment
transportation
knapsack
scheduling
inventory
network_flow
```

---

### Feature Mapping

映射：

```
Demand

↓

d_i
```

```
Capacity

↓

Q_j
```

```
value / weight

↓

v_i / w_i
```

生成：

Optimization Instance。

---

## Deliverables

Optimization Instance。

---

## Acceptance Criteria

任意 Excel。

均可转换。

---

# Phase 3：Optimization Ontology（对应架构层：Optimization Intelligence Layer）

> 注：本阶段专注于构建优化知识本体体系，作为 Optimization Intelligence Layer 的知识基础。

## Goal

建立整个运筹优化知识体系。

---

## Modules

Problem

Variable

Constraint

Objective

Solver

Algorithm

Template

---

## Tasks

建立：

Facility Location。

Assignment。

Transportation。

Network Flow。

Knapsack。

Scheduling。

Inventory。

以后：

持续增加。

---

## Deliverables

Ontology Repository。

---

## Acceptance Criteria

能够：

根据 Problem Type。

自动：

检索变量。

约束。

目标函数。

---

# Phase 4：Retrieval-Augmented Modeling (RAM)

## Goal

建立：

Optimization Knowledge Retrieval。

而不是：

Document Retrieval。

---

## Tasks

根据：

Problem Specification。

自动：

Retrieve：

```
Variables

Constraints

Objective

Templates

Algorithms

Solver
```

---

## Deliverables

Knowledge Package。

---

## Acceptance Criteria

LLM 不需要：

从零建立模型。

---

# Phase 5：Optimization Modeling

## Goal

生成数学模型。

不是：

Python。

而是：

IR。

---

## Tasks

生成：

```
Sets

Parameters

Variables

Objective

Constraints
```

输出：

IR。

---

## Deliverables

IR。

---

## Acceptance Criteria

IR 满足：

IR_SPEC。

---

# Phase 6：Model Verification

## Goal

验证：

IR。

---

## Verification

结构。

变量。

索引。

逻辑。

数学。

一致性。

---

## LLM Review

增加：

Reviewer。

自动：

Review。

自动：

修复。

---

## Deliverables

Verified IR。

---

## Acceptance Criteria

通过：

全部验证。

---

# Phase 7：Solver Integration

## Goal

完成多求解器后端抽象与集成。

---

## Tasks

实现：

```
SolverBackend 抽象基类
```

实现：

```
CplexBackend
```

实现：

```
HighsBackend
```

实现：

```
MockBackend
```

实现：

```
SolverBackendRegistry
```

改造：

```
SolverRouter 使用 registry 选择后端
```

约束编译器支持：

```
空 scope 的整体求和约束（如 knapsack capacity）
多因子乘积系数（如 c_ij * d_i * x_ij）
```

支持：

未来：

Gurobi。

SCIP。

OR-Tools。

---

## Deliverables

Solver Layer。

---

## Acceptance Criteria

能够：

自动：

通过配置切换后端并 Solve。

---

# Phase 8：Decision Intelligence

## Goal

自动分析：

结果。

---

## Modules

Sensitivity。

Scenario。

Resource Utilization。

Constraint Analysis。

Business Recommendation。

---

## Deliverables

Business Report。

---

## Acceptance Criteria

能够：

自动：

生成：

分析报告。

---

# Phase 9：Visualization

## Goal

可视化。

---

## Dashboard

支持：

Network。

Map。

Cost。

Scenario。

Capacity。

Runtime。

Solver Statistics。

---

## Frontend

实现：

React + Vite 前端。

支持：

文件上传。

会话状态展示。

澄清交互。

结果面板（摘要 / IR / 最优解）。

---

## Deliverables

Web Dashboard。

React Frontend。

---

## Acceptance Criteria

交互正常。

---

# Phase 10：Deployment

## Goal

部署。

---

## Tasks

Docker。

Compose。

CI/CD。

Cloud。

Monitoring。

---

## Deliverables

可部署版本。

---

## Acceptance Criteria

Docker 一键启动。

---

# 3. Milestones（里程碑）

| Version | Milestone         | Description         |
| ------- | ----------------- | ------------------- |
| v0.1    | Framework         | 基础框架完成        |
| v0.2    | Data Intelligence | 数据智能完成        |
| v0.3    | Ontology          | 知识本体完成        |
| v0.4    | Modeling          | 自动建模完成        |
| v0.5    | Verification      | 自动验证完成        |
| v0.6    | Solver            | CPLEX + HiGHS 集成完成 |
| v0.7    | Decision          | 决策分析完成        |
| v0.8    | Dashboard         | Streamlit + React 前端完成 |
| v1.0    | MVP               | 最小可用产品        |
| v2.0    | Enterprise        | 企业级版本          |

---

# 4. MVP（Minimum Viable Product）

MVP 必须支持：

- CSV / Excel 导入
- Data Profiling
- Data Quality Check
- Schema Understanding
- Facility Location
- Assignment
- Transportation
- Knapsack
- Network Flow
- Scheduling
- Inventory
- Optimization Instance
- IR
- Model Verification
- IBM CPLEX
- HiGHS
- Mock Backend
- React 前端
- Dashboard
- 结构化日志 / 可观测性

---

# 5. Long-term Vision（长期规划）

未来逐步支持：

### Optimization

- Vehicle Routing
- Scheduling
- Network Flow
- Inventory
- Robust Optimization
- Stochastic Programming
- Bilevel Programming

---

### AI

- Multi-Agent
- MCP
- GraphRAG
- Tool Calling
- Memory
- Auto Prompt Optimization

---

### Solver

- ✅ IBM CPLEX
- Gurobi
- ✅ HiGHS
- SCIP
- OR-Tools

---

### Enterprise

- Docker
- Kubernetes
- Redis
- PostgreSQL
- RabbitMQ
- Multi-user
- Authentication
- RBAC

---

# 6. Development Principles

整个开发过程中始终坚持：

> 小步迭代（Small Iteration）

> 快速验证（Fast Validation）

> 模块解耦（Loose Coupling）

> 文档优先（Documentation First）

> 架构优先（Architecture First）

> 可维护优于可运行（Maintainability over Hack）

任何新功能开发之前，都必须先完成：

1. 接口设计
2. 数据结构设计
3. 文档更新
4. 测试方案设计

随后才能开始编码。

---

# 7. Definition of Done（完成标准）

每个阶段完成必须满足以下条件：

- 功能开发完成；
- 单元测试通过；
- 集成测试通过；
- 文档同步更新；
- Code Review 完成；
- Architecture Review 完成；
- 无严重静态检查问题（Ruff / MyPy）；
- 可纳入主分支（Main Branch）。

只有满足以上条件，阶段才视为完成，并进入下一阶段开发。