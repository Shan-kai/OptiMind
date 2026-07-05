# OptiMind

> Optimization Copilot - AI-native Decision Intelligence Platform for Operations Research

An AI-native decision intelligence platform for Operations Research. The system automatically transforms business data into mathematical optimization models, solves them using industrial-grade solvers (CPLEX / HiGHS / Mock), and outputs actionable business recommendations.

---

## Project Status

Current status: **核心阶段已完成（Core phases completed）**

All core development phases are functional:
- Phase 0: Project Foundation
- Phase 1: System Infrastructure (FastAPI + LangGraph)
- Phase 2: Data Intelligence
- Phase 3: Optimization Ontology
- Phase 4: Knowledge Retrieval
- Phase 5: Optimization Modeling (IR generation)
- Phase 6: Model Verification
- Phase 7: Solver Integration (CPLEX + HiGHS + Mock)
- Phase 8: Decision Intelligence (Sensitivity, Scenario, Risk, Recommendation)
- Phase 9: Visualization (React Frontend + Streamlit Dashboard)
- Phase 10: Deployment (Docker + CI/CD)

---

## Documentation

| Document | Description |
| -------- | ----------- |
| [PROJECT.md](PROJECT.md) | Project vision, positioning, core design philosophy |
| [ROADMAP.md](ROADMAP.md) | Development roadmap and milestones |
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | System architecture overview index |
| [docs/architecture/](docs/architecture/) | Architecture chapters |
| [docs/specs/](docs/specs/) | Specs (IR / API / Data / Ontology / Test / Coding) |

---

## Quick Start

### Prerequisites

- Python >= 3.11
- Node.js >= 18 (for the React frontend)
- IBM CPLEX (optional, for real solving with the CPLEX backend)

### Install Backend

```bash
pip install -e ".[dev]"
```

### Install Frontend

```bash
cd frontend
npm install
```

### Run Tests

```bash
pytest -q --no-cov -m "not solver"
```

### Run API

```bash
uvicorn opti_mind.main:app --reload
```

### Run React Frontend

```bash
cd frontend
npm run dev
```

The frontend is available at `http://localhost:5173` and expects the API at `http://localhost:8000`.

### Switch Solver Backend

Set the `OPTI_MIND_SOLVER_BACKEND` environment variable to choose the solver:

```bash
# Use IBM CPLEX (default if available)
OPTI_MIND_SOLVER_BACKEND=cplex uvicorn opti_mind.main:app --reload

# Use HiGHS open-source MILP solver
OPTI_MIND_SOLVER_BACKEND=highs uvicorn opti_mind.main:app --reload

# Use the mock backend for testing without a solver license
OPTI_MIND_SOLVER_BACKEND=mock uvicorn opti_mind.main:app --reload
```

Supported backends: `cplex`, `highs`, `mock`.

If CPLEX is not available, the API will return a friendly prompt in the response; you can switch to the mock backend with `OPTI_MIND_SOLVER_BACKEND=mock`.

### Run Dashboard

```bash
streamlit run dashboard/app.py
```

### Run with Docker

```bash
cd docker
docker-compose up --build
```

---

## Supported Problem Types

OptiMind ships with ontology templates for the following problem families:

| Problem Type | Typical Columns |
|--------------|-----------------|
| `facility_location` | `customer`, `facility`, `demand`, `capacity`, `fixed_cost`, `transport_cost` |
| `knapsack` | `item`, `value`/`profit`, `weight`, `capacity` |
| `assignment` | `agent`, `task`, `cost` |
| `transportation` | `source`, `sink`, `supply`, `demand`, `cost` |
| `scheduling` | `job`, `processing_time`, `due_date`, `weight` |
| `inventory` | `item`, `period`, `demand`, `holding_cost`, `ordering_cost`, `purchase_cost`, `initial_inventory` |
| `network_flow` | `node1`, `node2`, `cost`, `capacity` |

Select a type explicitly in the frontend dropdown, or choose **auto** to let the Data Intelligence layer detect the problem type from column names.

## Sample Data

Sample datasets are included under `tests/fixtures/`:

- `tests/fixtures/facility_location.csv` — 8 customers × 8 facilities
- `tests/fixtures/knapsack.csv` — 8 items, capacity 30
- `tests/fixtures/assignment.csv` — 8 agents × 8 tasks
- `tests/fixtures/transportation.csv` — 8 sources × 8 sinks

### Knapsack Example

**Columns:**
| Column | Description |
|--------|-------------|
| item | Item identifier |
| value | Item value |
| weight | Item weight |
| capacity | Knapsack capacity (scalar) |

**Usage via API:**
```bash
curl -X POST http://localhost:8000/api/v1/sessions \
  -F "file=@tests/fixtures/knapsack.csv" \
  -F "business_goal=最大化背包价值"
```

**Usage via Frontend:**
1. Start the API: `uvicorn opti_mind.main:app --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173`
4. Upload `tests/fixtures/knapsack.csv`
5. Select problem type `auto` or `knapsack`
6. Click **开始优化**

The response includes the full optimization result:
- `ir`: final Intermediate Representation used for solving
- `solution`: solver output (`status`, `objective_value`, `variables`)
- `analysis_report`: decision intelligence report with recommendations
- `execution_graph`: ordered list of pipeline stages executed
- `errors`: any non-fatal pipeline errors

## LLM Switches

By default the deterministic heuristic path is used. To enable LLM augmentation, set the corresponding environment variables:

```bash
OPTI_MIND_LLM_SCHEMA_INTERPRETER=true   # Use LLM to interpret column semantics
OPTI_MIND_LLM_MODEL_GENERATOR=true      # Use LLM for direct model generation
OPTI_MIND_LLM_DECISION_ANALYZER=true    # Use LLM to enhance the analysis report
```

When an LLM call fails or times out, the pipeline falls back to the deterministic implementation automatically.

---

## Project Structure

```
OptiMind/
  README.md
  PROJECT.md
  ROADMAP.md
  SYSTEM_ARCHITECTURE.md
  docs/
    architecture/        # Architecture chapters
    specs/               # Specification documents
  src/opti_mind/
    core/                # Exceptions and LLM client
    data/                # Data Intelligence layer
    knowledge/           # Knowledge Retrieval (RAM)
    ontology/            # Optimization Ontology (YAML + built-in fallback)
    modeling/            # IR generation
    verification/        # Model Verification
    solver/              # Solver Integration (CPLEX / HiGHS / Mock backends)
    decision/            # Decision Intelligence
    workflow/            # LangGraph pipeline
    api/                 # FastAPI routes
  frontend/              # React + Vite frontend
  dashboard/             # Streamlit visualization
  tests/
  docker/
    Dockerfile
    docker-compose.yml
```

---

## License

MIT
