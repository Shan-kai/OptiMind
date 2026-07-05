# API_SPEC — API 接口规范

> OptiMind 对外通过 FastAPI 暴露 REST 接口。所有业务逻辑位于下层，API 层仅做路由、校验与编排触发。

---

# 1. 设计原则

- 统一资源命名：`/api/v1/...`。
- `/api/v1/optimize` 当前为同步端点，直接返回完整结果；未来长任务可扩展为异步 `task_id` 模式。
- 统一错误格式：`{ "code": "...", "message": "...", "trace_id": "..." }`。
- 鉴权：API Key（Header `X-API-Key`），未来扩展 RBAC。
- API 层不直接调用 LLM、Solver 或 Data 内部对象，一律走 Workflow / 服务接口。
- 大文件上传限制与超时由配置项控制，不硬编码。

---

# 2. 核心端点

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| POST | `/api/v1/optimize` | 触发完整 Pipeline，同步返回 `OptimizeResponse` |
| POST | `/api/v1/optimize/{thread_id}/resume` | 恢复被澄清请求中断的 Pipeline |
| GET  | `/api/v1/health` | 健康检查，返回版本与可用 solver 后端 |
| GET  | `/api/v1/problem-types` | 列出所有注册的问题类型（精简列表） |
| GET  | `/api/v1/problem-types/{value}` | 返回指定问题类型的完整自描述元数据 |
| POST | `/api/v1/uploads` | （future）上传 CSV/Excel 原始数据，返回 `dataset_id` |
| POST | `/api/v1/instances` | （future）由 dataset 生成 Optimization Instance |
| GET  | `/api/v1/tasks/{task_id}` | （future）查询任务状态（pending/running/ok/failed） |
| GET  | `/api/v1/tasks/{task_id}/result` | （future）获取优化结果与决策报告 |
| GET  | `/api/v1/models/{task_id}/ir` | （future）获取该任务的 IR（可追溯） |

---

# 3. `/api/v1/problem-types`

返回精简的问题类型列表，供前端下拉框使用。

**响应：**

```json
[
  {
    "value": "facility_location",
    "label": "Facility Location",
    "description": "Uncapacitated facility location: choose which facilities to open...",
    "tags": ["location", "assignment", "binary", "milp"]
  }
]
```

---

# 4. `/api/v1/problem-types/{value}`

返回指定问题类型的完整自描述元数据，供前端展示字段匹配提示。

**响应：**

```json
{
  "value": "facility_location",
  "label": "Facility Location",
  "description": "...",
  "sets": {
    "I": { "name": "I", "description": "set of customers", "index_roles": ["customer_key"] },
    "J": { "name": "J", "description": "set of facilities", "index_roles": ["facility_key"] }
  },
  "parameters": [
    {
      "symbol": "d_i",
      "base_name": "d",
      "description": "demand of customer i",
      "aliases": ["d_i"],
      "shape": "vector",
      "index_sets": ["I"],
      "required": true,
      "default_value": 1.0
    }
  ],
  "variables": [...],
  "constraints": [...],
  "objective": { "sense": "minimize", "expression": "...", "description": "..." },
  "tags": ["location", "assignment", "binary", "milp"]
}
```

---

# 5. 请求/响应示例

触发优化（同步返回）：

```
POST /api/v1/optimize
Content-Type: application/json
{ "source": "tests/fixtures/facility_location.csv", "problem_type": "facility_location" }
```

响应：

```json
{
  "status": "success",
  "thread_id": "...",
  "problem_type": "facility_location",
  "analysis_report": { ... },
  "ir": { ... },
  "solution": {
    "status": "optimal",
    "objective_value": 1234.5,
    "variables": { "x_ij": { "A_1": 0.0, ... }, "y_j": { "1": 1.0, ... } }
  },
  "execution_graph": ["data_intelligence", "knowledge_retrieval", "modeling", "verification", "solver", "decision"],
  "errors": [],
  "clarification_request": null
}
```

---

# 6. ClarificationRequest 扩展

`clarification_request.station` 现在支持三种值：

- `data_intelligence`：需要确认列语义
- `modeling`：需要补充缺失参数
- `ontology_patch`：需要审批 LLM 提出的 ontology 补丁

当 `station === "ontology_patch"` 时，`context` 中包含：

```json
{
  "patch": "{...}",
  "confidence": "0.85",
  "gap_kind": "required_parameters_missing",
  "trigger_station": "modeling"
}
```

---

# 7. OptimizeResponse 字段说明

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| `status` | `string` | `success` / `error` / `partial` / `awaiting_input` |
| `thread_id` | `string \| null` | 会话/线程 ID，用于中断后恢复 |
| `problem_type` | `string \| null` | 检测到或指定的问题类型 |
| `analysis_report` | `object \| null` | 决策智能分析报告 |
| `ir` | `object \| null` | 最终用于求解的 IR（优先 `verified_ir`，否则回退到 `ir`） |
| `solution` | `object \| null` | 求解器输出：`status`、`objective_value`、`variables` |
| `execution_graph` | `string[]` | 实际执行的 Pipeline 阶段列表 |
| `errors` | `string[]` | 非致命或致命错误信息 |
| `clarification_request` | `object \| null` | 当 `status` 为 `awaiting_input` 时返回 |

---

# 8. Health 端点

```
GET /api/v1/health
```

返回：

```json
{
  "status": "ok",
  "version": "0.1.0",
  "available_solver_backends": ["cplex", "highs", "mock"]
}
```

| 字段 | 类型 | 说明 |
| ---- | ---- | ---- |
| `status` | `string` | 服务状态 |
| `version` | `string` | API 版本 |
| `available_solver_backends` | `string[]` | 当前环境可用的 solver 后端列表 |

---

# 9. 任务状态机（异步扩展预留）

未来若 `/api/v1/optimize` 改为异步模式，任务状态机如下：

    pending -> running -> ok
                |
                +-------> failed

---
