# TEST_SPEC — 测试规范

> 遵循 Testability First。每个模块可在无其他模块在场的情况下独立测试。

---

# 1. 测试分层

| 层 | 工具 | 范围 |
| ---- | ---- | ---- |
| 单元测试 | pytest | 单模块纯函数/类 |
| 集成测试 | pytest + fixtures | 跨模块契约（IR 校验、Solver 接口） |
| 系统测试 | pytest + API client | 端到端 Pipeline |
| 回归测试 | pytest | Ontology / Template 检索一致性 |

---

# 2. 覆盖目标

- 核心域（IR 生成与校验）：>= 90%
- Data / Solver / Decision 接口适配层：>= 80%
- Workflow 编排：>= 70%

覆盖率工具：coverage / pytest-cov。

---

# 3. 命名与组织

    tests/
      unit/
        test_ir_validator.py
        test_feature_mapper.py
      integration/
        test_solver_adapter.py
      system/
        test_optimize_pipeline.py

测试函数命名：`test_<行为>_<期望>`。

---

# 4. 数据与用例

- 固定测试数据集置于 `tests/fixtures/`。
- 求解器相关测试在无 CPLEX 许可时通过 mock `SolverBackend` 跳过真实求解，并在 CI 标记 `@pytest.mark.solver`。
