# Chapter 7. Decision Intelligence Layer（决策智能层设计）

---

# 7.1 Design Purpose（设计目标）

Decision Intelligence Layer 的核心目标是：

> 将优化求解结果（Solution）转化为可解释、可分析、可执行的业务决策建议。

该层解决一个关键问题：

> 数学最优解 ≠ 可执行决策

在真实工业场景中，优化结果必须经过：

- 可解释性分析
- 稳健性验证
- 情景对比分析
- 业务约束再审查

才能进入实际决策流程。

---

# 7.2 Layer Positioning（层定位）

该层位于系统末端：

```
Optimization Intelligence Layer
          ↓
Solver Layer
          ↓
Decision Intelligence Layer   ← 本层
          ↓
Presentation Layer
```

本层本质是：

> Optimization → Business Decision Translation Layer

---

# 7.3 Core Responsibilities（核心职责）

Decision Intelligence Layer 负责以下五类核心任务：

---

## 7.3.1 Solution Interpretation（解解释）

将 Solver 输出转化为业务可理解表达：

输入：

```
Solution
```

输出：

```
Business-readable Explanation
```

例如：

- 哪些设施被选中
- 哪些客户被分配到哪里
- 成本构成是什么
- 为什么是这个解

---

## 7.3.2 Sensitivity Analysis（敏感性分析）

分析关键参数变化对结果的影响：

例如：

- demand ↑ 10%
- cost ↑ 5%
- capacity ↓ 20%

输出：

- objective变化趋势
- 解结构变化
- 稳定性指标

---

## 7.3.3 Scenario Analysis（情景分析）

对比不同业务场景：

```
Baseline Scenario
Scenario A (High Demand)
Scenario B (Low Capacity)
Scenario C (Cost Shock)
```

输出：

- 最优解差异
- 成本变化
- 结构变化

---

## 7.3.4 Business Recommendation（决策建议）

将优化结果转为业务行动建议：

例如：

- 建议开设哪些仓库
- 建议关闭哪些设施
- 建议调整产能
- 建议调整供应链结构

输出必须：

> 可执行（Actionable）

---

## 7.3.5 Risk Assessment（风险评估）

评估解的风险：

- solution stability
- constraint tightness
- infeasibility sensitivity
- operational risk

---

# 7.4 Internal Submodules（内部模块）

---

## 7.4.1 SolutionInterpreter（解解释器）

职责：

将数值解转为语义解释：

```
x[i][j] = 1 → Customer i assigned to Facility j
```

---

## 7.4.2 SensitivityAnalyzer（敏感性分析器）

方法：

- parametric perturbation
- shadow price analysis
- dual variable analysis（CPLEX）

---

## 7.4.3 ScenarioEngine（情景引擎）

构建：

- 多场景参数输入
- batch solving
- comparative analysis

---

## 7.4.4 RecommendationEngine（推荐引擎）

将 optimization result 转换为：

```
Decision Actions
```

例如：

- Open Facility A
- Close Facility B
- Increase capacity of C

---

## 7.4.5 RiskEvaluator（风险评估器）

评估：

- solution robustness
- constraint binding strength
- sensitivity score

---

# 7.5 Data Flow（数据流）

```
Solution
   ↓
SolutionInterpreter
   ↓
ScenarioEngine
   ↓
SensitivityAnalyzer
   ↓
RiskEvaluator
   ↓
RecommendationEngine
   ↓
Business Report
   ↓
Presentation Layer
```

---

# 7.6 Design Principles（设计原则）

---

## Principle 1：No Re-optimization Logic

本层禁止：

- 修改模型
- 重新求解
- 改变量定义

只能：

分析已有解。

---

## Principle 2：Explainability First

所有输出必须：

- 可解释
- 可追溯
- 可复现

---

## Principle 3：Business First Language

禁止：

- 数学符号输出为主

必须：

- business action language

例如：

❌ x_ij = 1
✔ 客户 i 被分配至仓库 j

---

## Principle 4：Scenario-driven Thinking

所有分析必须：

围绕场景，而不是单点解。

---

## Principle 5：Solver Output is Immutable

本层不能修改：

- Solution
- Variable values
- Objective value

---

# 7.7 Key Outputs（核心输出）

Decision Intelligence Layer 输出：

---

## 1. Business Report

结构化报告：

- summary
- key decisions
- cost breakdown
- allocation plan

---

## 2. Scenario Comparison Table

| Scenario | Cost | Feasible | Change |
| -------- | ---- | -------- | ------ |

---

## 3. Sensitivity Report

- parameter elasticity
- stability range

---

## 4. Recommendation List

```
- Open Facility A
- Close Facility B
- Reallocate Demand C
```

---

## 5. Risk Score

- Low / Medium / High
- or numerical score

---

# 7.8 Advanced Techniques（高级技术）

---

## 7.8.1 Dual Analysis

使用 CPLEX dual variables：

- shadow price
- marginal cost

---

## 7.8.2 What-if Simulation

快速模拟：

- 参数扰动
- policy变化

---

## 7.8.3 Explainable Optimization (XOR)

结合：

- variable importance
- constraint binding strength

---

## 7.8.4 Counterfactual Analysis

如果：

- 不开 facility A，会怎样？

---

# 7.9 Failure Modes（典型失败模式）

---

## 1. Over-interpretation

错误：

把噪声当结论

---

## 2. False causality

错误：

把 correlation 当 causation

---

## 3. Overconfidence

错误：

认为最优解一定可执行

---

## 4. Ignoring constraints reality gap

忽略现实约束差异

---

## 5. Scenario explosion

情景过多导致不可分析

---

# 7.10 Engineering Insight（工程洞察）

这一层的本质是：

> Optimization → Decision Translation System

不是：

- 计算层
- 建模层

而是：

> 解释层 + 决策层 + 风险层

---

# 7.11 Summary（总结）

Decision Intelligence Layer 是 OptiMind 的：

> Business Value Extraction Engine（商业价值提取引擎）

它将：

- Solver 输出（数学解）
  转换为：
- Business decision（业务决策）

核心能力：

- Explain solution
- Analyze sensitivity
- Compare scenarios
- Recommend actions
- Assess risk

最终目标：让优化结果真正“可以被业务采用
