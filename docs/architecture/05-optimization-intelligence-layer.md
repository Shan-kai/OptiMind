# Chapter 5. Optimization Intelligence Layer（优化智能层设计）

---

# 5.1 Design Purpose（设计目标）

Optimization Intelligence Layer 是 OptiMind 的**核心决策与建模引擎层**。

其职责是：

> 将结构化的 Optimization Instance 转换为可执行的数学优化模型（IR），并完成模型验证、求解器映射与优化执行准备。

该层本质上是：

> Semantic Optimization Compiler（语义优化编译器）

输入：

```
Optimization Instance
```

输出：

```
Intermediate Representation (IR)
```

---

# 5.2 Layer Positioning（层定位）

该层位于系统中间核心位置：

```
Data Intelligence Layer
        ↓
Optimization Intelligence Layer   ← 本层
        ↓
Solver Layer
        ↓
Decision Intelligence Layer
```

该层是：

> Business Semantics → Mathematical Model 的转换层

---

# 5.3 Core Responsibilities（核心职责）

Optimization Intelligence Layer 负责以下五大核心任务：

---

## 5.3.1 Intent Understanding（意图理解）

将业务输入转化为标准优化问题定义。

输入：

- Optimization Instance
- 用户需求（自然语言或结构化描述）

输出：

```
Problem Specification
```

包含：

- Problem Type（如 Facility Location）
- Optimization Type（MILP / LP / CP）
- Objective Type
- Constraint Family

---

## 5.3.2 Problem Specification（问题规格化）

将模糊问题转化为严格结构定义：

```json
ProblemSpec {
  "problem_type": "Capacitated Facility Location",
  "objective": "Minimize Cost",
  "constraints": [
    "capacity",
    "assignment"
  ],
  "decision_scope": "facility selection + allocation"
}
```

---

## 5.3.3 Optimization Ontology Service（知识本体服务）

`OntologyService` 是 Optimization Intelligence Layer 访问本体的唯一入口。它封装了：

- 问题类型检测（`detect`）
- 字段语义匹配（`match_fields`）
- 知识包检索（`retrieve`）
- 参数别名查询（`aliases`）
- 实例/IR 验证（`validate`）
- 结构化补丁生成（`patch_for`）
- 补丁应用（`apply_patch`）

`config/ontology/*.yaml` 是 Ontology 的唯一来源，包含：

- `signature`：问题签名，用于检测与字段匹配
- `aliases`：参数别名
- `defaults`：默认值
- `logic_checks`：验证规则

上层模块禁止直接读取 ontology 文件或内置字典。

---

## 5.3.4 Model Generation（模型生成）

将：

```
Instance + Spec + Ontology
```

转换为：

```
Mathematical Model (IR)
```

包括：

- Sets
- Parameters
- Variables
- Constraints
- Objective

但注意：

👉 不是直接生成 CPLEX 代码
👉 而是生成 IR（中间表示）

**关键约束**：LLM 不再直接生成 IR。当确定性路径走不通时，LLM 只输出 `OntologyPatch`（结构化本体补丁），然后由同一个确定性 `IRGenerator` 重新生成 IR。

---

## 5.3.5 Model Verification（模型验证）

对 IR 进行严格验证：

### 结构验证

- 是否缺失变量
- 是否缺失约束
- 是否存在未引用参数

---

### 数学一致性验证

- index 是否匹配
- 维度是否一致
- 约束是否可计算

---

### 逻辑验证

- 是否满足业务规则
- 是否存在矛盾约束

---

### Solver 可行性验证

- 是否可转 CPLEX / DOcplex
- 是否可求解（feasible check）

---

## 5.3.6 Solver Routing（求解器路由）

根据模型类型自动选择求解器：

| Problem Type     | Solver                |
| ---------------- | --------------------- |
| LP / MILP        | IBM CPLEX             |
| CP               | CP Optimizer          |
| Network Flow     | CPLEX                 |
| Large-scale MILP | Decomposition + CPLEX |

---

# 5.4 Internal Submodules（内部模块）

---

## 5.4.1 IntentParser（意图解析器）

职责：

将：

- 用户需求
- Instance结构

映射为：

ProblemSpec

---

## 5.4.2 OntologyService（本体服务）

职责：

从 Optimization Ontology 获取：

- Variable definitions
- Constraint templates
- Objective templates
- Problem signatures
- Parameter aliases and defaults

并负责：

- 问题类型检测
- 字段匹配
- 验证
- 结构化补丁

---

## 5.4.3 ModelBuilder（模型构建器）

核心模块。

负责：

```
Instance + Spec + Templates → IR
```

---

## 5.4.4 IRGenerator（中间表示生成器）

输出标准 IR：

```json
{
  "sets": [],
  "parameters": [],
  "variables": [],
  "constraints": [],
  "objective": {}
}
```

IR 结构严格遵循 `docs/specs/IR_SPEC.md`。

---

## 5.4.5 ModelValidator（模型验证器）

执行：

- Static check
- Semantic check
- Structural check

---

## 5.4.6 SolverRouter（求解器路由器）

策略选择：

- rule-based routing
- model-size-aware routing
- constraint-type-aware routing

---

# 5.5 Data Flow（数据流）

```
OptimizationInstance
        ↓
IntentParser
        ↓
ProblemSpecification
        ↓
OntologyService
        ↓
IRGenerator
        ↓
ModelValidator
        ↓
SolverRouter
        ↓
Solver Layer
```

当确定性路径走不通时：

```
IRGenerator
    ↓
GapReport
    ↓
OntologyService.patch_for (LLM 只补 ontology)
    ↓
OntologyPatch
    ↓
apply_patch
    ↓
IRGenerator (重新走确定性路径)
```

---

# 5.6 Design Principles（设计原则）

---

## Principle 1：LLM Only for Semantic Layer

LLM 只能用于：

- 意图理解
- 模糊语义补全
- 解释生成
- Ontology 补丁建议（不是 IR 生成）

禁止：

- 数学建模
- 约束生成逻辑
- 求解逻辑
- 直接生成 IR

---

## Principle 2：Ontology First

所有建模必须基于：

Optimization Ontology

不能从零生成模型结构。

---

## Principle 3：IR as Contract

IR 是唯一跨模块协议：

- Solver 不认识 LLM
- LLM 不直接接触 Solver
- ModelBuilder 不直接调用 Solver

---

## Principle 4：Verification First

任何模型必须经过：

ModelValidator

否则禁止进入 Solver。

---

## Principle 5：Deterministic Routing

Solver 选择必须：

- 可解释
- 可复现
- 可追踪

---

# 5.7 Failure Modes（典型失败模式）

---

## 1. Missing Constraint Problem

LLM 遗漏关键约束（最常见）

---

## 2. Wrong Indexing

变量维度错误：

x[i][j] vs x[j][i]

---

## 3. Inconsistent Objective

目标函数未对齐 ProblemSpec

---

## 4. Solver Mismatch

MILP 使用 CP Solver

---

## 5. Over-generated Model

模型冗余约束导致：

- infeasible
- slow solving

---

# 5.8 Architecture Insight（架构洞察）

这一层的本质不是：

> AI 建模

而是：

> Optimization Compiler System

类似于：

```
Python → Bytecode Compiler
```

这里是：

```
Business → Optimization Model Compiler
```

因此：

Optimization Intelligence Layer = 编译器前端（Front-end Compiler）

---

# 5.9 Summary（总结）

Optimization Intelligence Layer 是 OptiMind 的：

> Core Intelligence Engine

它负责：

- 理解问题（Intent）
- 定义问题（Spec）
- 获取知识（OntologyService）
- 构建模型（IR）
- 验证模型（Validation）
- 选择求解器（Routing）

最终输出：

> 可执行优化模型（Solver-ready IR）

这一层的质量，直接决定整个系统的上限
