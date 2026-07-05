# CODING_STANDARD — 编码规范

> 基于 Configuration over Hard Coding、Deterministic First、Interface-oriented Design。

---

# 1. Python

- 版本：3.11+
- 格式化：Black（line-length 100）
- Lint：Ruff
- 类型检查：mypy --strict（核心域）/ mypy（适配层）
- Import 排序：Ruff isort 规则

---

# 2. 命名

| 类型 | 约定 |
| ---- | ---- |
| 模块/文件 | snake_case |
| 类 | PascalCase |
| 函数/变量 | snake_case |
| 常量 | UPPER_SNAKE |
| 接口 | `I` 前缀（`IOntologyService`、`ILLMClient`） |

---

# 3. 配置优先

禁止硬编码：API Key、Model Name、Prompt、Solver Parameter、Magic Number 一律走 Config。
默认配置位于 `config/`，覆盖项通过环境变量。

---

# 4. 注释与文档

- 公共接口必须 docstring。
- 复杂逻辑前留简短 orienting 注释，避免空叙述。

---

# 5. 提交与质量门禁

- 提交前须通过：`ruff check`、`black --check`、`mypy`、`pytest`。
- CI 须全绿方可并入 main。
