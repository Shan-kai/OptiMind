# Chapter 8. Workflow & Orchestration Layer（工作流与编排层设计）

---

# 8.1 Design Purpose（设计目标）

Workflow & Orchestration Layer 的核心目标是：

> 统一调度 OptiMind 全部模块，实现从“业务输入”到“优化决策输出”的端到端自动化执行流程。

该层本质上是：

> **Optimization AI System Orchestrator（优化智能系统调度器）**

它负责：

- 控制执行顺序
- 管理状态流转
- 调度各功能模块
- 处理失败重试
- 维护执行上下文
- 支持中断与恢复

---

# 8.2 Layer Positioning（层定位）

该层位于系统中枢：

```
Presentation Layer
        ↓
Workflow & Orchestration Layer   ← 本层
        ↓
Data / Optimization / Solver / Decision Layers
```

其本质是：

> System Brain（系统大脑）

但注意：

它不做计算，只做控制。

---

# 8.3 Core Responsibilities（核心职责）

---

## 8.3.1 Workflow Execution（流程执行）

定义完整执行路径：

```
Data → Instance → Model → IR → Solve → Analysis → Report
```

每一步都是一个 Node（节点）。

---

## 8.3.2 State Management（状态管理）

维护全局状态：

```text
WorkflowState {
  input_data,
  instance,
  problem_spec,
  ir_model,
  solution,
  analysis_report
}
```

所有模块必须读取/写入 State。

---

## 8.3.3 Task Routing（任务路由）

根据任务类型选择执行路径：

- Facility Location Workflow
- Scheduling Workflow
- Network Flow Workflow
- Generic MILP Workflow

---

## 8.3.4 Failure Recovery（失败恢复）

支持：

- retry
- fallback solver
- partial re-execution

例如：

```
Solver timeout → switch to heuristic solver
```

---

## 8.3.5 Tool Orchestration（工具编排）

统一管理：

- LLM calls
- Solver calls
- Data pipeline calls
- Knowledge retrieval calls

---

# 8.4 Workflow Engine Design（工作流引擎设计）

OptiMind 采用：

> LangGraph-style State Machine Architecture

---

## 8.4.1 Graph Structure（图结构）

```
                    ┌─────────────────┐
                    │  data_intelligence │
                    └────────┬────────┘
                             ↓
                    ┌─────────────────┐
                    │   gap_detection  │
                    └────────┬────────┘
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
    ┌─────────────────┐ ┌──────────────┐ ┌─────────────┐
    │ ontology_patch   │ │knowledge_retrieval│ │   __end__    │
    └────────┬────────┘ └──────┬───────┘ └─────────────┘
             │                 ↓
             └──────────┐  modeling
                        ↓      ↓
                    gap_detection
                        ↓
                   verification
                        ↓
                    gap_detection
                        ↓
                      solver
                        ↓
                     decision
                        ↓
                      __end__
```

实际节点包括：

- `data_intelligence`：数据加载、schema 理解、instance 构建
- `gap_detection`：四阶段组合闸门检测
- `ontology_patch`：确定性补全或 LLM 补丁
- `knowledge_retrieval`：调用 `OntologyService.retrieve`
- `modeling`：确定性 IR 生成
- `verification`：IR 验证
- `solver`：求解器调用
- `decision`：决策分析

---

## 8.4.2 Node Definition（节点定义）

每个 Node 必须实现：

```python
def node(state: WorkflowState, deps: WorkflowDependencies) -> dict[str, Any]:
    ...
```

返回一个 state 更新 dict，由 LangGraph 合并到全局 state。

---

## 8.4.3 Gap Detection Node（缺口检测节点）

`gap_detection` 节点根据 workflow state 判断确定性路径是否走不通。它调用 `src/opti_mind/workflow/gap_detection.py` 中的 `detect_gap`，按四阶段组合闸门输出 `GapReport`：

- A. `data_intelligence` 后：问题类型 confidence < 0.4
- B. `data_intelligence` 后：required roles 缺失且确定性补全失败
- C. `modeling` 后：required parameters 缺失且默认值/推导规则无法补全
- D. `verification` 后：IR 验证不通过且非 solver 类错误

若未检测到 gap，返回 `{"gap_report": None}`，允许流程继续。

---

## 8.4.4 Ontology Patch Node（本体补丁节点）

`ontology_patch` 节点消费 `GapReport`，按以下顺序处理：

1. 先尝试确定性补全（ontology defaults / aliases）。
2. 确定性补全失败则调用 `OntologyService.patch_for()`。
3. 根据补丁 confidence 分级处理：
   - `>= 0.9`：自动应用
   - `0.7 ~ 0.9`：自动应用并记录 summary
   - `< 0.7`：触发 `interrupt(ClarificationRequest(station="ontology_patch"))`
4. 维护 `upstream_attempts`，上限为 2，防止无限循环。

补丁应用成功后返回 `{"gap_report": None}`，并设置 `next_node` 回到上游节点重新执行。

---

## 8.4.5 Edge Definition（边定义）

Edge 表示：

- 条件转移
- 分支逻辑

例如：

```
if gap_report is not None → ontology_patch
if gap_report is None and knowledge_package exists → modeling
if verification_report exists → solver
```

---

# 8.5 Internal Submodules（内部模块）

---

## 8.5.1 WorkflowEngine（核心引擎）

职责：

- 执行 DAG / Graph
- 控制 state flow
- 管理 execution lifecycle

---

## 8.5.2 StateManager（状态管理器）

负责：

- state snapshot
- state persistence
- state recovery

---

## 8.5.3 TaskRouter（任务路由器）

根据：

- problem type
- data structure
- model size

选择 workflow。

---

## 8.5.4 RetryHandler（重试机制）

处理：

- solver failure
- LLM failure
- data inconsistency

策略：

- exponential backoff
- fallback strategy

---

## 8.5.5 ToolManager（工具管理器）

统一管理：

- LLM API
- Solver API
- Data APIs
- OntologyService API

---

# 8.6 Data Flow（数据流）

```
User Input
     ↓
WorkflowEngine
     ↓
StateManager
     ↓
TaskRouter
     ↓
Node Execution (Data → Gap Detection → Model → Verification → Solve → Analyze)
     ↓
RetryHandler (if needed)
     ↓
ToolManager (LLM / Solver / Data / OntologyService)
     ↓
Final State
     ↓
Output
```

---

# 8.7 Design Principles（设计原则）

---

## Principle 1：State is Single Source of Truth

所有信息必须写入：

```
WorkflowState
```

禁止模块间私有数据传递。

---

## Principle 2：No Direct Module Coupling

禁止：

- Data layer → Solver direct call
- LLM → Solver direct call
- Decision → Model modification

---

## Principle 3：Graph-driven Execution

所有流程必须显式：

- Node
- Edge

禁止 hidden control flow。

---

## Principle 4：Deterministic Workflow

同一输入：

→ 必须得到相同 workflow path（除非 stochastic solver）

---

## Principle 5：Tool Abstraction

所有外部能力：

必须通过 ToolManager 调用。

---

# 8.8 Advanced Capabilities（高级能力）

---

## 8.8.1 Dynamic Workflow Generation

根据问题动态生成 graph：

- MILP → standard pipeline
- VRP → extended pipeline
- stochastic → scenario branching

---

## 8.8.2 Parallel Execution

支持：

- scenario parallel solving
- batch optimization

---

## 8.8.3 Interrupt & Resume

支持：

- checkpoint
- resume from node

当前支持三种 clarification station：

- `data_intelligence`
- `modeling`
- `ontology_patch`

---

## 8.8.4 Multi-agent Extension (future)

Workflow 可扩展为：

- Planner Agent
- Modeling Agent
- Solver Agent
- Analyst Agent

但仍保持：

> state-driven architecture

---

# 8.9 Failure Modes（典型失败模式）

---

## 1. State corruption

state 更新错误

---

## 2. Infinite loop

workflow graph cycle error

**防护措施**：

- `gap_report` 只在检测到新 gap 时写入
- 成功节点返回时清除 `gap_report`
- `upstream_attempts` 上限为 2

---

## 3. Node failure cascade

一个 node failure 导致全流程失败

---

## 4. Tool timeout

LLM / solver API 超时

---

## 5. Inconsistent state updates

多个 node 写冲突 state

---

# 8.10 Engineering Insight（工程洞察）

这一层的本质是：

> **Control Plane（控制平面）**

而不是：

- Compute plane（计算平面）
- Data plane（数据平面）

对应关系：

| Layer          | Type          |
| -------------- | ------------- |
| Data Layer     | Data Plane    |
| Solver Layer   | Compute Plane |
| Workflow Layer | Control Plane |

---

# 8.11 Summary（总结）

Workflow & Orchestration Layer 是 OptiMind 的：

> System Execution Brain（系统执行大脑）

它负责：

- 编排所有模块
- 控制执行流程
- 管理状态一致性
- 处理失败恢复
- 调度所有工具

核心价值：

> **Without this layer, the system is just a set of disconnected modules.**

有了这一层：OptiMind becomes a real system, not a collection of components.
