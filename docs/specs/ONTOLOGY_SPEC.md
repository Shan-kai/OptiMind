# ONTOLOGY_SPEC — 优化知识本体规范

> Optimization Ontology 是 Modeling 的知识基础。LLM 不允许从零生成模型，必须基于 Ontology 检索后生成。

---

## 1. 本体维度

| 维度 | 说明 |
| ---- | ---- |
| Problem | 问题类型（facility_location / assignment / transportation / network_flow / knapsack / scheduling / inventory） |
| Variable | 典型决策变量模板 |
| Constraint | 典型约束模板 |
| Objective | 典型目标模板 |
| Solver | 求解器适用性与参数 |
| Algorithm | 适用算法（含 Benders / Column Generation 等，后续） |
| Template | 可复用模型模板 |

---

## 2. 单一来源 Schema

`config/ontology/*.yaml` 是 Ontology 的唯一来源。每个 YAML 文件包含以下顶层键：

```yaml
problem_type: facility_location
description: "..."

# 问题签名：用于自动识别问题类型与必填字段
signature:
  index_roles: [customer_key, facility_key]
  required_roles: [customer_key, facility_key]
  optional_roles: [demand, capacity, fixed_cost, cost, distance]
  required_parameters: [d_i, f_j, c_ij]
  optional_parameters: [Q_j]
  required_sets: [I, J]

# 参数别名：base name -> canonical symbol 列表
aliases:
  d: [d_i]
  f: [f_j]
  c: [c_ij]
  Q: [Q_j]

# 标量默认值：base name -> default value
defaults:
  d: 1.0
  Q: 9999.0

# 逻辑检查规则
logic_checks:
  required_variables: [x_ij, y_j]
  required_constraint_patterns:
    - assign
    - once
    - one
    - each

# 集合、参数、变量、约束、目标
sets:
  I: set of customers / demand points
  J: set of candidate facility locations

parameters:
  d_i: demand of customer i
  f_j: fixed cost of opening facility j
  c_ij: transportation cost from facility j to customer i

variables:
  - name: x_ij
    kind: binary
    description: ...
    indices: [I, J]

constraints:
  - name: assignment
    expression: sum_{j in J} x_ij
    sense: ==
    rhs: "1"
    scope: for all i in I

objective:
  sense: minimize
  expression: ...

tags: [location, assignment, binary, milp]

metadata:
  keyword_aliases:
    d: [demand, customer_demand, requirement]
    f: [fixed_cost, opening_cost, setup_cost]
```

### 字段说明

- `signature`：问题类型检测与字段匹配的依据（长期目标为替代 `src/opti_mind/data/instance_builder.py` 中的 `_PROBLEM_SIGNATURES`）。
- `aliases`：描述参数 base name 到 canonical symbol 的映射（替代原硬编码别名表）。
- `defaults`：提供缺失参数的默认值（替代原硬编码默认标量）。
- `logic_checks`：声明 IR 必须满足的结构规则（长期目标为替代 `src/opti_mind/verification/validator.py` 中的硬编码 `_check_logic`）。
- `metadata.keyword_aliases`：为 schema interpreter 提供列名同义词提示，优先级低于 `aliases`。

---

## 3. OntologyService 接口

`src/opti_mind/ontology/service.py` 中的 `IOntologyService` 是上层访问 Ontology 的唯一入口。

```python
class IOntologyService(Protocol):
    def list_types(self) -> list[ProblemTypeInfo]: ...
    def get_entry(self, problem_type: str) -> OntologyEntry | None: ...
    def get_detail(self, problem_type: str) -> ProblemTypeDetail | None: ...
    def detect(
        self,
        columns: list[str],
        profile: DataProfileReport | None = None,
        semantics: list[FieldSemantics] | None = None,
        business_context: str = "",
        hint: str | None = None,
    ) -> DetectionResult: ...
    def match_fields(
        self,
        problem_type: str,
        columns: list[str],
        semantics: list[FieldSemantics] | None = None,
    ) -> FieldMatchResult: ...
    def retrieve(self, problem_spec: ProblemSpecification) -> KnowledgePackage: ...
    def validate(
        self,
        problem_type: str,
        instance: dict[str, Any] | None = None,
        ir: dict[str, Any] | None = None,
    ) -> ValidationResult: ...
    def aliases(
        self,
        symbol: str,
        problem_type: str | None = None,
    ) -> list[str]: ...
    def patch_for(
        self,
        gap: GapReport,
        instance: dict[str, Any] | None = None,
        field_semantics: list[FieldSemantics] | None = None,
        business_goal: str = "",
    ) -> OntologyPatch: ...
    def apply_patch(
        self,
        patch: OntologyPatch,
        instance: dict[str, Any],
    ) -> PatchApplicationResult: ...
```

**关键约束**：`patch_for` 必须返回 `OntologyPatch`，禁止直接返回 `IRModel`。LLM 只补 ontology，不编 IR。

---

## 4. GapReport 与补丁契约

`src/opti_mind/ontology/gap_report.py` 定义了确定性路径与补丁层之间的数据契约。

```python
class GapKind(str, Enum):
    PROBLEM_TYPE_UNCERTAIN = "problem_type_uncertain"
    REQUIRED_ROLES_MISSING = "required_roles_missing"
    REQUIRED_PARAMETERS_MISSING = "required_parameters_missing"
    IR_VALIDATION_FAILED = "ir_validation_failed"
    COMBINED = "combined"

class GapReport(BaseModel):
    trigger_station: Literal["data_intelligence", "modeling", "verification"]
    gap_kind: GapKind
    confidence: float
    detected_problem_type: str | None = None
    problem_type_candidates: list[str] = []
    missing_roles: list[str] = []
    present_roles: list[str] = []
    column_aliases_tried: list[str] = []
    missing_parameters: list[str] = []
    inferred_parameters: list[str] = []
    validation_failures: list[str] = []
    recommended_patch_kind: Literal[
        "ontology_extension",
        "schema_remap",
        "parameter_completion",
        "problem_type_clarify",
    ] | None = None
    upstream_attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 5. 三层建模路径

```
数据 → ① 确定性路径 → 走得通？→ IR → 求解 → 出结果
                    ↓ 走不通？
                  ② Ontology 补全 → LLM 分析数据，输出结构化补丁（新增参数/约束）
                    ↓
                  ③ 确定性路径用补全后的 ontology 重新走
```

- **第①层**：确定性代码，不碰 LLM。优先走安全启发式（列名别名、默认值、索引集推断）。
- **第②层**：LLM 唯一该出现的地方。输出是可审计的 `OntologyPatch`。
- **第①层（回退）**：同一个 `IRGenerator`，只是 ontology 变大了。

触发条件（组合闸门）：
- A. 问题类型检测后：confidence < 0.4
- B. 字段匹配后：required roles 缺失且确定性补全失败
- C. IR 生成后：required parameters 缺失且默认值/推导规则无法补全
- D. 验证后：确定性 IR 验证不通过且非 solver 类错误

---

## 6. 补丁审批策略

| confidence | 处理方式 |
|------------|----------|
| `>= 0.9` | 自动应用，记录审计日志 |
| `0.7 ~ 0.9` | 自动应用，向用户展示摘要 |
| `< 0.7` | 必须人工审批，workflow 发出 `ClarificationRequest(station="ontology_patch")` |

高风险补丁（涉及问题类型变更、目标函数结构、约束语义、新增 required 参数无默认值）也必须人工审批。

---

## 7. 一致性约束

- 每个 Problem 至少绑定一组 Variable 定义与一组 Constraint 模板。
- Template 必须标注适用 Problem Type 与不适用的显式排除。
- Ontology 变更需经 Code Review，并回归 Knowledge Retrieval 测试。
- 禁止在 `src/opti_mind/data/instance_builder.py` 等处硬编码问题签名或别名；所有规则必须来自 `config/ontology/*.yaml`。

---

## 8. v1 范围

- facility_location
- assignment
- transportation
- knapsack
- scheduling
- inventory
- network_flow

后续版本持续增加，遵循 Open-Closed Principle：新增不改旧。
