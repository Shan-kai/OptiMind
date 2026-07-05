# IR_SPEC — Intermediate Representation 规范

> OptiMind 全系统模块之间唯一的数据交换格式。IR 是 Data / Modeling / Solver / Decision 各层之间的数据契约（Data Contract）。

---

# 1. 设计目标

- 解耦模块：模块间禁止直接传递自然语言或 Python 对象，仅通过 IR 通信。
- 可验证：IR 必须可被结构化校验（schema + 业务一致性检查）。
- 多求解器友好：同一份 IR 可编译为 CPLEX / Gurobi / HiGHS / SCIP 等不同求解器模型。
- 可序列化：IR 必须可无损序列化为 JSON / YAML，便于持久化、缓存与追踪。

---

# 2. 顶层结构

IR 以一个 Optimization Model 为根，包含：

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| `meta` | object | 元信息：版本、来源 Problem Spec、生成时间 |
| `problem_type` | string | 所属问题类型（来自 Ontology），如 `facility_location` / `assignment` |
| `sense` | enum | `min` / `max` |
| `sets` | array[Set] | 集合定义 |
| `parameters` | array[Parameter] | 已知参数（来自 Optimization Instance） |
| `variables` | array[Variable] | 决策变量 |
| `objective` | Expression | 目标函数表达式 |
| `constraints` | array[Constraint] | 约束条件 |

---

# 3. Sets（集合）

- `members` 取值 `from_instance`（运行时由 Instance 注入）或显式枚举列表。
- 禁止含未定义集合。

示例：

    {
      "name": "I",
      "description": "需求点集合",
      "index_domain": "int",
      "members": "from_instance"
    }

---

# 4. Parameters（参数）

- `source` 指向 Feature Mapping 产出，保证可追溯（Traceability）。

示例：

    {
      "name": "d_i",
      "description": "需求量",
      "sets": ["I"],
      "dtype": "float",
      "source": "feature_map:demand->d_i"
    }

---

# 5. Variables（决策变量）

`domain` 取值：`binary` / `integer` / `continuous` / `semi_continuous`。

示例：

    {
      "name": "x_ij",
      "description": "是否将需求点 i 分配给设施 j",
      "sets": ["I", "J"],
      "domain": "binary",
      "lower": 0,
      "upper": 1
    }

---

# 6. Objective（目标函数）

- 支持表达式 `kind`：`linear`、`quadratic`、`general`。
- 索引求和通过 `sum` + `where` 描述，避免隐式控制流。

示例：

    {
      "kind": "linear",
      "expr": [ {"coef": "f_j", "var": "x_ij", "sum": ["J"], "where": "i in I"} ]
    }

---

# 7. Constraints（约束）

`sense` 取值 `le` / `ge` / `eq` / `range`。

示例：

    {
      "name": "assign_once",
      "expr": "sum_{j in J} x_ij == 1",
      "scope": "forall i in I",
      "sense": "eq",
      "rhs": null
    }

---

# 8. 校验规则（Verification）

1. 结构验证：所有索引引用的集合已定义、变量已声明。
2. 数学一致性：目标函数与约束中出现的变量集合一致；参数 dtype 匹配。
3. 逻辑验证：业务不变量由 Ontology 规则注入（如每个需求点至少被分配一次）。
4. Solver 可行性：维度与求解器要求匹配（MILP 中无非线性连续等）。

IR 只有通过全部验证后才可进入 Solver Layer。

---

# 9. 序列化与版本

- 默认序列化格式：JSON（`meta.schema_version` = `1.0`）。
- 任何向后不兼容的变更必须提升 schema 主版本，并保留转换器。
- 各问题类型的 IR 示例可通过 `tests/unit/test_end_to_end.py` 中的回归测试查看。
