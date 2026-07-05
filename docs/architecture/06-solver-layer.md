# Chapter 6. Solver Layer（求解器层设计）

---

# 6.1 Design Purpose（设计目标）

Solver Layer 是 OptiMind 的**执行计算核心层（Execution Engine Layer）**。

其核心职责是：

> 将 IR（Intermediate Representation）转换为可由工业优化求解器执行的计算模型，并高效获得最优或近似最优解。

该层不参与：

- 建模
- 语义理解
- 数据处理
- 决策解释

只负责一件事：

> **Optimization Execution（优化求解执行）**

---

# 6.2 Layer Positioning（层定位）

Solver Layer 位于系统架构中的执行核心：

```
Optimization Intelligence Layer
          ↓
     Solver Layer        ← 本层
          ↓
Decision Intelligence Layer
```

其本质是：

> Mathematical Execution Engine

---

# 6.3 Core Responsibilities（核心职责）

Solver Layer 负责以下五大任务：

---

## 6.3.1 IR to Solver Model Translation（IR模型翻译）

将 IR 转换为具体求解器模型：

例如：

```
IR → DOcplex Model
IR → CPLEX Model
IR → (Future) Gurobi Model
```

---

转换内容包括：

- Sets → Index
- Variables → Decision Variables
- Constraints → Linear / Integer Constraints
- Objective → Linear Objective Function

---

## 6.3.2 Model Compilation（模型编译）

将抽象数学模型编译为：

> Solver-native representation

包括：

- Sparse matrix construction
- Constraint indexing
- Variable binding

---

## 6.3.3 Optimization Execution（优化执行）

调用已注册的 solver backend：

```
CplexBackend.solve(ir)
```

或：

```
HighsBackend.solve(ir)
```

或（测试时）：

```
MockBackend.solve(ir)
```

实际执行由 `SolverRouter` 根据配置选择后端，并统一包装 `SolverError`。

---

支持：

- MILP
- LP
- CP（扩展）
- Large-scale optimization

---

## 6.3.4 Solution Extraction（解提取）

将 solver output 转换为统一结构：

```
Solution {
  variable_values,
  objective_value,
  status,
  gap,
  runtime
}
```

---

## 6.3.5 Performance Optimization（性能优化）

包括：

- Presolve optimization
- Warm start
- Lazy constraint callback
- Cut generation
- Heuristic acceleration
- Parallel solving

---

# 6.4 Internal Submodules（内部模块）

---

## 6.4.1 SolverBackend 抽象基类

统一接口：

```text
available() → bool
solve(model: IR) → Solution
```

所有求解器后端必须实现：

- CplexBackend
- HighsBackend
- MockBackend
- GurobiBackend（future）

注册到 `SolverBackendRegistry` 后，`SolverRouter` 按配置名发现并实例化。

---

## 6.4.2 Backend Adapters（后端适配器）

当前实现：

- **CplexBackend**：IR → DOcplex model → CPLEX
- **HighsBackend**：IR → `highspy.HighsLp` → HiGHS
- **MockBackend**：返回全 0 的可行解，用于无许可证环境测试

职责：

- IR → solver-native model
- constraint mapping
- variable binding
- solution extraction

---

## 6.4.3 ModelCompiler（模型编译器）

负责：

将 IR 编译为 solver-native model

包含：

- expression builder
- constraint builder
- variable registry

---

## 6.4.4 ExecutionEngine（执行引擎）

调用求解器：

```
run_optimization()
```

支持：

- time limit
- gap tolerance
- thread configuration

---

## 6.4.5 SolutionParser（解解析器）

解析 solver 输出：

```
CPLEX solution → Solution object
```

---

## 6.4.6 PerformanceMonitor（性能监控）

监控：

- runtime
- node count
- memory usage
- gap convergence

---

# 6.5 Data Flow（数据流）

```
IR
 ↓
SolverRouter
 ↓
SolverBackendRegistry
 ↓
ModelCompiler
 ↓
CplexBackend | HighsBackend | MockBackend
 ↓
CPLEX Solver | HiGHS Solver | Mock
 ↓
Solution
```

`SolverRouter` 根据配置（如 `OPTI_MIND_SOLVER_BACKEND`）从 registry 中选择可用后端；不同后端共享同一套 IR 编译逻辑，但生成各自的 solver-native model。

---

# 6.6 Solver Architecture（求解器架构）

```
                    +---------------------+
                    |    SolverRouter     |
                    +---------------------+
                              ↓
                    +---------------------+
                    | SolverBackendRegistry|
                    +---------------------+
                              ↓
              +-------------------------------+
              |     SolverBackend 抽象基类    |
              +-------------------------------+
                    ↓              ↓              ↓
            CplexBackend   HighsBackend   MockBackend
                    ↓              ↓              ↓
            +----------------+  +----------------+
            | IRToModelCompiler|  | IRToHighsCompiler|
            +----------------+  +----------------+
                    ↓              ↓
            +----------------+  +----------------+
            | DOcplex Model  |  | HighsLp        |
            +----------------+  +----------------+
                    ↓              ↓
            +----------------+  +----------------+
            | CPLEX Solver   |  | HiGHS Solver   |
            +----------------+  +----------------+
                    ↓              ↓
            +----------------+  +----------------+
            |   Solution     |  |   Solution     |
            +----------------+  +----------------+
```

---

# 6.7 Design Principles（设计原则）

---

## Principle 1：Solver is Ground Truth

所有结果必须来自 solver：

- LLM 不可修改结果
- IR 不可“假解”

---

## Principle 2：No Semantic Logic in Solver Layer

Solver Layer 不理解：

- business meaning
- customer semantics
- ontology

只理解：

> mathematical structure

---

## Principle 3：IR Strict Contract

Solver Layer 只能消费 IR：

- 不允许访问 raw data
- 不允许访问 ontology
- 不允许访问 LLM

---

## Principle 4：Performance Awareness

必须考虑：

- O(n³) constraint explosion
- memory usage
- solver node explosion

---

## Principle 5：Deterministic Execution

同一 IR：

→ 必须得到一致结果（given same solver config）

---

# 6.8 Advanced Solver Techniques（高级求解技术）

---

## 6.8.1 Warm Start

利用历史解：

```
previous_solution → initial solution
```

---

## 6.8.2 Lazy Constraints

动态添加约束：

- VRP
- scheduling problems

---

## 6.8.3 Cut Generation

减少搜索空间：

- Gomory cuts
- cover cuts

---

## 6.8.4 Decomposition

处理大规模问题：

- Benders decomposition
- Dantzig-Wolfe decomposition

---

## 6.8.5 Heuristics

快速可行解：

- greedy initialization
- local search

---

# 6.9 Failure Modes（典型失败模式）

---

## 1. Infeasible Model

IR 生成错误导致无解

---

## 2. Over-constrained Model

约束过多导致 infeasible

---

## 3. Solver Timeout

大规模 MILP 无法收敛

---

## 4. Memory Explosion

变量规模过大

---

## 5. Numerical Instability

浮点误差导致求解失败

---

# 6.10 Engineering Implications（工程影响）

Solver Layer 强制整个系统：

## 1. IR must be minimal but complete

不能冗余

---

## 2. Model must be solver-friendly

不能“学术化建模”

---

## 3. Constraint design matters

比算法更重要

---

## 4. Performance is a first-class concern

不是后期优化

---

# 6.11 Summary（总结）

Solver Layer 是 OptiMind 的：

> **Execution Core Engine（执行核心引擎）**

它的本质是：

> A Mathematical Optimization Runtime System

职责非常清晰：

- 接收 IR
- 通过 registry 选择后端
- 编译模型
- 调用 CPLEX / HiGHS / Mock
- 输出 Solution

这一层决定：

> 系统是否“真的能用”，而不是“看起来能用”
