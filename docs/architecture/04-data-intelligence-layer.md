# Chapter 4. Data Intelligence Layer（数据智能层设计）

---

# 4.1 Design Purpose（设计目标）

Data Intelligence Layer 的核心目标是：

> 将企业异构、脏乱、语义不一致的原始业务数据，转换为标准化、可用于优化建模的 Optimization Instance。

在真实工业场景中，数据通常来自：

- ERP 系统
- WMS 仓储系统
- MES 制造系统
- CRM 客户系统
- Excel / CSV 手工数据
- API 数据流

这些数据具有以下特点：

- 字段语义不统一
- 缺失值普遍存在
- 单位不一致
- 数据粒度不一致
- 命名混乱
- 存在异常值

因此，本层的核心任务不是建模，而是：

> Data → Semantic → Optimization-ready Structure

---

# 4.2 Layer Positioning（层定位）

Data Intelligence Layer 位于系统最底层：

```
Raw Business Data
        ↓
Data Intelligence Layer   ← 本层
        ↓
Optimization Instance
        ↓
Optimization Intelligence Layer
        ↓
Solver Layer
        ↓
Decision Intelligence Layer
```

该层是：

> Optimization Pipeline 的数据入口（Data Gateway）

---

# 4.3 Core Responsibilities（核心职责）

Data Intelligence Layer 负责：

## 1. Data Ingestion（数据接入）

当前已实现的数据源：

```
CSV
Excel (.xlsx / .xls)
```

规划中：

```
SQL (PostgreSQL / MySQL)
REST API
ERP / SAP / MES / WMS 连接器
```

---

## 2. Data Profiling（数据画像）

自动生成数据结构分析报告：

- 行数 / 列数
- 数据类型识别
- 缺失率分析
- 唯一值统计
- 分布分析
- 异常检测

输出：

```
DataProfileReport
```

---

## 3. Data Cleaning（数据清洗）

处理：

- Missing Values
- Outliers
- Duplicates
- Invalid Formats
- Unit Inconsistency

注意：

清洗必须是**可追溯（Traceable）**的，不允许黑盒操作。

---

## 4. Schema Understanding（字段语义理解）

这是本层最关键能力。

系统需要理解：

| 原始字段 | 语义                |
| -------- | ------------------- |
| qty      | demand              |
| wh_id    | facility            |
| dist     | distance            |
| cost     | transportation cost |

使用：

- LLM semantic mapping
- rule-based matching
- ontology alignment

---

## 5. Feature Mapping（优化参数映射）

将业务字段映射为优化模型参数：

```
Raw Field → Semantic Meaning → CanonicalRole → Optimization Parameter
```

例如：

```
Demand → d_i
Capacity → Q_j
Cost → c_ij
FixedCost → f_j
```

`FeatureMapper` 按 `canonical_role` 建立原始列到标准优化角色的映射，再由 `InstanceBuilder` 生成 `OptimizationInstance`。

---

## 6. Optimization Instance Construction（实例构建）

最终输出标准化结构：

```json
OptimizationInstance {
  "sets": {
    "customers": [...],
    "facilities": [...]
  },
  "parameters": {
    "demand": [...],
    "capacity": [...],
    "cost": [[...]],
    "fixed_cost": [...]
  }
}
```

---

# 4.4 Internal Submodules（内部子模块）

Data Intelligence Layer 由以下子模块组成：

---

## 4.4.1 DataConnector（数据连接器）

职责：

统一数据接入接口。

当前实现：

- File Loader（CSV / Excel）

规划中：

- Database Connector
- API Connector

设计原则：

```
Single Responsibility
```

禁止混合：

数据处理逻辑。

---

## 4.4.2 DataProfiler（数据画像模块）

功能：

自动分析数据结构。

输出：

```
Column Stats
Missing Rate
Distribution
Correlation
```

---

## 4.4.3 DataQualityChecker（数据质量检测）

检测规则：

- Missing threshold
- Outlier detection (IQR / Z-score)
- Duplicate detection
- Type mismatch
- Range violation

输出：

```
DataQualityReport
```

---

## 4.4.4 SchemaInterpreter（语义解释器）

核心模块之一。

输入：

```
Raw Column Names
```

输出：

```
Semantic Labels
```

方法：

- LLM-based interpretation
- Ontology matching
- Heuristic rules

---

## 4.4.5 FeatureMapper（特征映射器）

负责：

```
Semantic → CanonicalRole → Optimization Parameter
```

例如：

```
Customer Demand → DEMAND → d_i
Warehouse Capacity → CAPACITY → Q_j
Shipping Cost → COST → c_ij
```

`FeatureMapper.map(df, semantics)` 输出 `dict[CanonicalRole, pd.Series]`，
`InstanceBuilder` 基于该映射构造 `OptimizationInstance`。

---

## 4.4.6 InstanceBuilder（实例构建器）

负责：

生成 Optimization Instance。

输出必须符合：

```
DATA_SPEC.md
```

---

# 4.5 Data Flow（数据流）

完整流程如下：

```
Raw Data
   ↓
DataConnector
   ↓
DataProfiler
   ↓
DataQualityChecker
   ↓
SchemaInterpreter
   ↓
FeatureMapper
   ↓
InstanceBuilder
   ↓
OptimizationInstance
```

---

# 4.6 Design Constraints（设计约束）

## Constraint 1：LLM 限制

LLM 只能用于：

- 字段语义识别
- 模糊匹配辅助

禁止：

- 数据清洗
- 数值计算
- 数据填充逻辑决策

---

## Constraint 2：确定性优先

所有可以规则化的操作必须使用：

- Python
- Pandas
- Numpy

---

## Constraint 3：可追溯性（Traceability）

所有数据转换必须记录：

```
Before → After → Rule/Method
```

---

## Constraint 4：不可破坏原始数据

原始数据必须保留：

```
raw_data/
processed_data/
```

分离存储。

---

# 4.7 Output Specification（输出规范）

Data Intelligence Layer 输出唯一标准结构：

```
OptimizationInstance
```

必须满足：

- 可用于 IR 生成
- 可直接进入 Optimization Layer
- 不依赖原始数据
- 完全结构化

---

# 4.8 Design Pattern（设计模式）

本层推荐使用：

## 1. Pipeline Pattern

数据处理链：

```
Stage1 → Stage2 → Stage3 → Stage4
```

---

## 2. Factory Pattern

用于：

DataConnector 创建。

---

## 3. Strategy Pattern

用于：

不同清洗策略：

- mean imputation
- median imputation
- model-based imputation

---

## 4. Adapter Pattern

用于：

不同数据源统一接口。

---

# 4.9 Common Failure Cases（常见失败模式）

工业项目中 Data Layer 常见失败包括：

## 1. Schema mismatch

字段无法映射到 ontology。

---

## 2. Unit inconsistency

kg vs ton 混乱。

---

## 3. Sparse data

缺失值过多导致模型不可解。

---

## 4. Granularity mismatch

客户级 vs 仓库级数据不一致。

---

## 5. Dirty categorical data

类别命名不一致：

```
NYC / New York / NewYork
```

---

# 4.10 Summary（总结）

Data Intelligence Layer 是整个 OptiMind 的：

> Data Foundation Layer（数据基础层）

其核心价值是：

- 将“业务数据”转化为“优化数据”
- 将“混乱信息”转化为“结构化实例”
- 将“自然语言字段”转化为“数学符号”

最终输出：

> OptimizationInstance

该层决定整个系统的上限，因为：

> 如果数据错了，后面所有优化都是错的。
