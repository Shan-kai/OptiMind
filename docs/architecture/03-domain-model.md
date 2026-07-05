# Chapter 3. Domain Model（领域模型设计）

---

# 3.1 Design Philosophy（设计理念）

OptiMind 的领域模型不是传统 Web 系统中的业务对象建模，而是面向 **Optimization Modeling（优化建模）** 的语义建模体系。

其核心目标是：

> 将“业务问题”抽象为“可计算的数学优化问题”。

因此，本系统的 Domain Model 本质上是：

```
Business Problem
        ↓
Semantic Problem Representation
        ↓
Mathematical Optimization Problem
        ↓
Solver Executable Model
```

---

# 3.2 Core Domain Boundary（核心领域边界）

整个系统的核心领域（Core Domain）是：

> Optimization Intelligence Domain（优化智能领域）

该领域负责：

- 问题识别
- 问题建模
- 变量定义
- 约束构建
- 目标函数构建
- 求解器适配
- 解空间解释

---

系统辅助领域（Supporting Domains）包括：

- Data Intelligence Domain（数据智能）
- Knowledge Domain（知识体系）
- Decision Intelligence Domain（决策分析）

基础设施领域（Generic Domains）包括：

- Logging
- Config
- API
- Storage
- Cache

---

# 3.3 Ubiquitous Language（统一领域语言）

整个系统必须统一以下核心概念：

| Concept              | Meaning      |
| -------------------- | ------------ |
| Problem              | 业务问题抽象 |
| Optimization Problem | 数学优化问题 |
| Variable             | 决策变量     |
| Constraint           | 约束条件     |
| Objective            | 优化目标     |
| Instance             | 具体数据实例 |
| Model                | 数学模型     |
| IR                   | 中间表示     |
| Solution             | 求解结果     |
| Scenario             | 情景分析     |
| Policy               | 决策策略     |

所有模块必须使用统一术语，禁止同义词混用。

---

# 3.4 Core Domain Model（核心领域模型）

## 3.4.1 Problem（问题抽象）

```text
Problem
 ├── problem_id
 ├── problem_type
 ├── description
 ├── constraints_description
 ├── objective_description
 ├── raw_data_ref
 └── metadata
```

---

## 3.4.2 OptimizationProblem（优化问题）

Problem 的结构化表达：

```text
OptimizationProblem
 ├── sets
 ├── parameters
 ├── variables
 ├── constraints
 ├── objective
 ├── objective_sense (min/max)
 └── metadata
```

---

## 3.4.3 Sets（集合）

表示索引空间：

```text
Sets
 ├── customers
 ├── facilities
 ├── products
 └── time_periods
```

集合是所有变量索引的基础。

---

## 3.4.4 Parameters（参数）

表示输入数据：

```text
Parameters
 ├── demand[i]
 ├── capacity[j]
 ├── cost[i][j]
 └── fixed_cost[j]
```

参数完全由 Data Intelligence Layer 提供。

---

## 3.4.5 Variables（决策变量）

核心优化变量：

```text
Variables
 ├── x[i][j]   # assignment
 ├── y[j]      # facility open
 └── z[t]      # time decision
```

变量必须满足：

- 明确索引
- 明确取值域（binary / integer / continuous）
- 明确语义

---

## 3.4.6 Constraints（约束）

约束结构：

```text
Constraint
 ├── name
 ├── expression
 ├── type
 │     ├── equality
 │     ├── inequality
 │     └── logical
 └── metadata
```

典型约束：

- Capacity Constraint
- Demand Satisfaction
- Assignment Constraint
- Flow Conservation
- Budget Constraint

---

## 3.4.7 Objective（目标函数）

```text
Objective
 ├── sense (min / max)
 ├── expression
 └── components
```

例如：

```
Minimize:
    Transportation Cost
  + Fixed Opening Cost
  + Penalty Cost
```

---

## 3.4.8 Optimization Instance（实例）

来自 Data Intelligence Layer：

```text
OptimizationInstance
 ├── sets
 ├── parameters
 ├── raw_data
 └── metadata
```

Instance 是 Model 的输入。

---

## 3.4.9 Model（数学模型）

```text
Model
 ├── optimization_problem
 ├── instance
 ├── ir_representation
 ├── solver_mapping
 └── status
```

Model 是 IR 的封装。

---

## 3.4.10 IR（Intermediate Representation）

系统最关键的数据结构：

```json
{
  "sets": {},
  "parameters": {},
  "variables": {},
  "constraints": {},
  "objective": {}
}
```

IR 是：

> 唯一跨模块通信协议

---

## 3.4.11 Solution（求解结果）

```text
Solution
 ├── variable_values
 ├── objective_value
 ├── status
 ├── gap
 ├── runtime
 └── solver_info
```

---

# 3.5 Domain Relationships（领域关系）

核心关系如下：

```
Problem
   ↓
OptimizationProblem
   ↓
Instance (Data Layer)
   ↓
Model (IR)
   ↓
Solver Execution
   ↓
Solution
   ↓
Decision Insight
```

---

# 3.6 Domain Invariants（领域不变量）

系统必须保证以下不变量成立：

## 1. Variable Consistency

所有变量必须：

- 被定义
- 被索引
- 被约束引用

---

## 2. Constraint Completeness

所有业务约束必须：

- 被建模
- 被验证

---

## 3. Objective Validity

必须存在且仅存在一个主目标函数。

---

## 4. Instance Validity

Instance 必须：

- 完整
- 无缺失关键参数
- 可用于求解

---

## 5. Solver Compatibility

Model 必须：

- 可转换为 DOcplex / CPLEX 格式

---

# 3.7 Domain Layering（领域分层）

Domain 被划分为三层：

```
Level 1: Business Semantics
    Problem / Instance

Level 2: Mathematical Representation
    OptimizationProblem / Model / IR

Level 3: Execution Layer
    Solver / Solution
```

---

# 3.8 Design Implications（设计影响）

该领域模型带来以下系统设计约束：

## 1. 必须存在 IR 层

禁止模块之间直接交换 Python 对象或自然语言。

---

## 2. 所有建模必须基于 Ontology

不能 LLM 直接生成模型结构。

---

## 3. Solver 完全解耦

Solver 只能依赖 IR。

---

## 4. Data 与 Model 分离

数据不能直接参与建模逻辑。

---

## 5. Decision Layer 独立

分析不能影响模型结构。

---

# 3.9 Summary（总结）

本章定义了 OptiMind 的核心领域模型体系。

核心结论如下：

- Problem 是语义入口
- Instance 是数据入口
- Model 是数学表达
- IR 是系统核心协议
- Solver 是计算引擎
- Solution 是决策基础
