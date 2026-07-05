
# PROJECT.md

> Project Name: OptiMind
>
> Subtitle: Optimization Copilot — AI-native Decision Intelligence Platform for Operations Research
>
> Version: v1.0
>
> Author: KK
>
> Status: 核心功能已完成（Core Features Completed）

---

# 1. Project Vision（项目愿景）

OptiMind 是一个面向 **Operations Research（运筹优化）** 的 AI 原生智能决策平台（AI-native Decision Intelligence Platform）。

本项目旨在利用大语言模型（LLM）的语义理解与推理能力，结合成熟的数学规划求解器（IBM CPLEX）和现代软件工程架构，实现从**业务数据**到**数学建模**、**优化求解**、**结果分析**和**决策建议**的完整自动化流程。

项目最终目标不是构建一个聊天机器人，也不是实现一个简单的 Agent，而是打造一个具备工业级可扩展性的智能优化平台。

---

# 2. Project Background（项目背景）

近年来，大语言模型在代码生成、自然语言理解和知识推理方面取得了显著进展。

与此同时，运筹优化（Operations Research）仍然是工业界解决资源配置、生产计划、物流配送、设施选址、库存管理、排程等复杂决策问题的核心技术。

然而，两者之间仍存在明显鸿沟：

- LLM 擅长理解业务需求，但缺乏严格的数学建模能力；
- 求解器能够获得高质量最优解，但无法理解自然语言业务需求；
- 企业优化项目往往需要大量人工完成数据整理、模型建立、求解和分析。

OptiMind 的目标正是打通这一链路，使 AI 成为运筹优化工程师的智能助手，而不是替代求解器。

---

# 3. Project Positioning（项目定位）

OptiMind 是一个 **Decision Intelligence Platform**，而不是：

- ❌ ChatBot
- ❌ Prompt Engineering Demo
- ❌ Code Generator
- ❌ LangGraph Demo
- ❌ Solver Wrapper

OptiMind 是：

- ✅ AI + Operations Research Platform
- ✅ Optimization Modeling Assistant
- ✅ Decision Intelligence Platform
- ✅ Optimization Engineering Framework
- ✅ AI-native Optimization Workflow

---

# 4. Core Design Philosophy（核心设计理念）

项目遵循以下设计原则：

## 4.1 LLM 不负责优化

LLM 负责：

- 理解业务需求
- 推理问题类型
- 辅助数学建模
- 检查模型合理性
- 解释优化结果

LLM 不负责：

- 数学优化计算
- 数值求解
- 替代求解器

所有优化计算均交由专业求解器完成。

---

## 4.2 Solver is the Source of Truth

IBM CPLEX 是优化结果的唯一可信来源。

任何数学规划问题都必须由求解器完成最终计算。

LLM 仅负责辅助。

---

## 4.3 Deterministic First

对于能够通过确定性算法完成的工作，不使用 LLM。

例如：

- CSV 读取
- Excel 解析
- 数据清洗
- 缺失值检测
- 数据验证
- 参数计算

均采用传统 Python 工程实现。

LLM 仅用于语义推理。

---

## 4.4 Separation of Responsibilities

每一个模块只负责一件事情。

例如：

Data Layer：

负责数据。

Model Layer：

负责建模。

Solver Layer：

负责求解。

Analysis Layer：

负责分析。

Visualization：

负责展示。

任何模块不得承担多个职责。

---

## 4.5 Intermediate Representation（IR）

整个系统所有模块之间只能通过统一 IR 通信。

禁止：

- 模块之间直接传递自然语言；
- 模块之间直接传递 Python 对象；
- 模块之间直接调用 Prompt。

IR 是整个系统的数据契约（Data Contract）。

---

# 5. Overall Objectives（总体目标）

OptiMind 应支持以下完整流程：

```
业务数据

↓

数据理解

↓

业务需求理解

↓

数学建模

↓

模型验证

↓

实例构建

↓

优化求解

↓

结果验证

↓

敏感性分析

↓

业务建议

↓

可视化
```

最终形成完整的数据—模型—优化—决策闭环。

---

# 6. Scope（项目范围）

## 当前版本（v1）

支持：

- 数据读取（CSV / Excel）
- 数据画像（Profiling）
- 数据质量检查
- Schema 理解
- Optimization Instance 构建
- Facility Location 建模
- Assignment 建模
- Transportation 建模
- Knapsack 建模
- Network Flow 建模
- Scheduling 建模
- Inventory 建模
- IBM CPLEX 求解
- HiGHS 开源求解器
- Mock 后端（无许可证测试）
- SolverBackend 抽象层与统一调度
- Ontology YAML 外部化配置
- 自动结果分析
- React 前端可视化
- Dashboard（Streamlit）可视化
- 结构化日志与请求 trace 可观测性

---

## 后续版本

计划支持：

- Vehicle Routing Problem（VRP）
- Network Flow
- Scheduling
- Inventory Optimization
- Robust Optimization
- Stochastic Programming
- Bilevel Programming
- Multi-objective Optimization

---

# 7. Non-goals（非目标）

当前项目不考虑：

- 自研求解器
- 自研 LLM
- 深度学习模型训练
- 大规模分布式优化
- GPU 并行求解
- 数字孪生平台
- 多用户权限系统

这些功能将在未来版本中评估。

---

# 8. Technical Principles（技术原则）

项目必须遵循：

- Clean Architecture
- Domain Driven Design（DDD）
- SOLID Principles
- Low Coupling
- High Cohesion
- Interface-oriented Design
- Configuration over Hard Coding
- Testability First

---

# 9. Development Principles（开发原则）

开发过程中必须坚持：

1. Documentation First（文档优先）
2. Architecture First（架构优先）
3. Interface First（接口优先）
4. Implementation Last（实现最后）

任何代码开发之前，应先完成对应模块设计文档。

---

# 10. AI Collaboration Rules（AI 协作规则）

任何 AI 参与开发时必须遵守：

1. 优先保证架构正确，而非快速完成任务；
2. 不允许为了简化实现而破坏模块边界；
3. 所有新增模块必须遵循统一接口规范；
4. 所有建议应优先考虑可维护性和可扩展性；
5. 如发现设计冲突，应主动提出并给出替代方案。

AI 的角色是项目技术负责人（Tech Lead），而非代码补全工具。

---

# 11. Success Criteria（成功标准）

项目成功的标准不是：

- 代码量；
- Prompt 数量；
- Agent 数量。

而是：

- 是否形成完整优化工作流；
- 是否能够自动完成建模与求解；
- 是否具备工业级可扩展架构；
- 是否能够支持不同优化问题扩展；
- 是否能够作为 AI + OR 智能决策平台持续演进。

---

# 12. Future Vision（未来愿景）

OptiMind 将逐步发展为一个开放的 AI + OR 平台。

未来可扩展方向包括：

- ✅ 多求解器统一调度；
- ✅ Optimization Ontology；
- GraphRAG；
- 自动算法推荐；
- 自动分解算法选择（Benders、Column Generation 等）；
- Agentic Optimization Workflow；
- 企业级部署（Docker / Kubernetes）；
- MCP Tool Ecosystem；
- 面向企业决策的 AI Copilot。

---

# 13. Motto（项目理念）

> **Understand the Business.**
>
> **Model the Optimization.**
>
> **Trust the Solver.**
>
> **Empower the Decision.**

OptiMind 的目标不是替代运筹优化工程师，而是帮助他们更快、更可靠地完成建模、求解和决策分析。