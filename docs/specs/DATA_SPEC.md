# DATA_SPEC — 数据规范

> 规定原始业务数据的接入、画像、质量校验与映射到 Optimization Instance 的规则。

---

# 1. 支持格式

- 文件：CSV、Excel（.xlsx）
- 数据库（后续）：MySQL、PostgreSQL、Oracle
- API（后续）：REST

所有原始数据必须先进入 Data Intelligence Layer，禁止 LLM 直接读取原始数据。

---

# 2. Data Profile 字段

| 字段 | 说明 |
| ---- | ---- |
| missing_rate | 缺失率 |
| dtype | 推断类型 |
| value_range | 数值范围 |
| cardinality | 唯一值数 |
| quantiles | 分位数 |

---

# 3. 质量校验项

- Missing Value
- Outlier
- Duplicate
- Invalid Coordinate
- Unit Conflict
- Invalid Encoding

---

# 4. Feature Mapping 约定

业务列名 -> 优化符号：

| 业务列 | 优化符号 | 含义 |
| ------ | -------- | ---- |
| demand | d_i / d_{i,t} | 需求量 |
| supply | s_i | 供应量 |
| capacity | Q_j / C | 容量/背包容量 |
| fixed_cost | f_j | 固定成本 |
| cost / distance | c_ij / c_{i,j} | 距离/运输成本/弧成本 |
| value / profit | v_i | 物品价值 |
| weight | w_i | 物品重量 |
| processing_time | p_j | 加工时间 |
| due_date | d_j | 交货期 |
| holding_cost | h_i | 库存持有成本 |
| ordering_cost | s_i | 订货固定成本 |
| purchase_cost | c_i | 采购成本 |
| initial_inventory | I0_i | 期初库存 |

映射结果随 Optimization Instance 持久化，保证可追溯。

支持的问题类型：

| 问题类型 | 典型索引列 | 典型参数列 |
| -------- | ---------- | ---------- |
| facility_location | customer, facility | demand, capacity, fixed_cost, cost/distance |
| assignment | agent, task | cost |
| transportation | source, sink | supply, demand, cost |
| knapsack | item | value/profit, weight, capacity |
| scheduling | job | processing_time, due_date, weight |
| inventory | item, period | demand, holding_cost, ordering_cost, purchase_cost, initial_inventory |
| network_flow | node1, node2 | cost, capacity |

---

# 5. Optimization Instance 结构

    {
      "problem_type": "facility_location",
      "sets": { "I": [...], "J": [...] },
      "parameters": { "d": {...}, "Q": {...}, "f": {...}, "c": {...} },
      "meta": { "dataset_id": "...", "profile_id": "...", "feature_map_id": "..." }
    }
