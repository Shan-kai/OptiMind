# Chapter 9. Infrastructure & Deployment Architecture（基础设施与部署架构）

---

# 9.1 Design Purpose（设计目标）

Infrastructure & Deployment Layer 的核心目标是：

> 为 OptiMind 提供可运行、可扩展、可监控、可部署的工业级运行环境。

该层不涉及任何：

- 建模逻辑
- 优化逻辑
- 决策逻辑

只负责：

> **系统运行能力（System Operational Capability）**

---

# 9.2 Layer Positioning（层定位）

该层位于整个系统最底层：

```
Presentation Layer
Workflow Layer
Data / Optimization / Solver / Decision Layers
        ↓
Infrastructure Layer   ← 本层
```

本质是：

> **Execution Foundation Layer（执行基础设施层）**

---

# 9.3 Core Responsibilities（核心职责）

---

## 9.3.1 Service Hosting（服务托管）

提供统一服务运行环境：

- FastAPI Service
- Workflow Engine Service
- Solver Service
- LLM Gateway Service
- Data Service

---

## 9.3.2 API Gateway（API 网关）

统一入口：

```
/optimize
/analyze
/upload
/solve
/report
```

功能：

- routing
- authentication
- rate limiting

---

## 9.3.3 Data Storage（数据存储）

支持多层数据存储：

### Raw Data Storage

- CSV / Excel files
- object storage

### Structured Storage

- PostgreSQL
- MySQL

### Cache Layer

- Redis

---

## 9.3.4 Task Queue System（任务队列系统）

用于异步优化任务：

- long MILP solving
- scenario simulation
- batch optimization

推荐：

- Celery + Redis
- or RabbitMQ

---

## 9.3.5 Observability（可观测性）

系统运行监控：

### Logging

- structured logging
- workflow tracing

### Metrics

- solver runtime
- queue latency
- API latency

### Tracing

- request trace ID
- workflow trace graph

---

## 9.3.6 Containerization（容器化）

系统必须支持：

```
Docker
Docker Compose
```

未来扩展：

```
Kubernetes
```

---

# 9.4 System Deployment Architecture（系统部署架构）

```
                        ┌────────────────────┐
                        │     User / UI      │
                        └─────────┬──────────┘
                                  │
                        ┌─────────▼──────────┐
                        │    API Gateway     │
                        │   (FastAPI)        │
                        └─────────┬──────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ Workflow Service│    │ Data Service   │    │ LLM Gateway    │
│ (LangGraph)    │    │ (ETL + IR)     │    │ (OpenAI/Qwen)  │
└──────┬──────────┘    └──────┬─────────┘    └──────┬─────────┘
       │                     │                     │
       ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│                 Optimization Core Engine                 │
│  (Modeling + IR + Ontology + Validation + Routing)      │
└─────────────────────────┬───────────────────────────────┘
                          ▼
               ┌──────────────────────┐
               │   Solver Service     │
               │   (CPLEX Engine)     │
               └─────────┬────────────┘
                          ▼
               ┌──────────────────────┐
               │ Decision Engine      │
               │ (Analysis Layer)     │
               └─────────┬────────────┘
                          ▼
               ┌──────────────────────┐
               │ Reporting Service    │
               └──────────────────────┘
```

---

# 9.5 Infrastructure Components（基础设施组件）

---

## 9.5.1 FastAPI Service Layer

职责：

- API 入口
- request validation
- workflow trigger

---

## 9.5.2 Workflow Service (LangGraph Runtime)

职责：

- graph execution
- state management
- retry logic

---

## 9.5.3 Data Service

职责：

- ETL pipeline
- instance generation
- schema mapping

---

## 9.5.4 Solver Service

职责：

- CPLEX execution
- model compilation
- solution extraction

---

## 9.5.5 LLM Gateway

职责：

- prompt management
- model routing
- caching

支持：

- OpenAI
- DeepSeek
- Qwen
- Claude

---

## 9.5.6 Decision Service

职责：

- scenario analysis
- sensitivity analysis
- recommendation generation

---

# 9.6 Data Infrastructure（数据基础设施）

---

## Storage Layers

### 1. Object Storage

- raw datasets
- logs
- reports

---

### 2. Relational DB

- optimization instances
- workflow states
- results

---

### 3. Cache Layer

Redis:

- workflow state cache
- solver cache
- LLM response cache

---

# 9.7 Deployment Modes（部署模式）

---

## 9.7.1 Local Development

```
docker-compose up
```

包含：

- API
- Redis
- PostgreSQL

---

## 9.7.2 Single Node Production

适用于：

- small enterprise

---

## 9.7.3 Distributed Deployment (future)

包含：

- Kubernetes
- microservices scaling
- solver cluster

---

# 9.8 CI/CD Pipeline（持续集成）

---

流程：

```
Code Push
   ↓
Lint (Ruff / Black)
   ↓
Type Check (MyPy)
   ↓
Unit Tests (Pytest)
   ↓
Build Docker Image
   ↓
Deploy
```

---

# 9.9 Monitoring & Logging（监控与日志）

---

## Logging Strategy

structured logs:

```
workflow_id
node_id
solver_runtime
error_trace
```

---

## Metrics

- API latency
- solver runtime
- queue size
- memory usage

---

## Tracing

full workflow trace:

```
Input → Data → Model → Solver → Decision
```

---

# 9.10 Security Design（安全设计）

---

## 9.10.1 API Security

- API key authentication
- rate limiting

---

## 9.10.2 Data Security

- encrypted storage
- access control

---

## 9.10.3 LLM Safety

- prompt injection protection
- output validation

---

# 9.11 Scalability Design（扩展性设计）

---

## Horizontal Scaling

- stateless API layer
- workflow worker scaling
- solver worker scaling

---

## Bottleneck Identification

- solver computation
- LLM latency
- data preprocessing

---

# 9.12 Failure Handling（失败处理）

---

## Retry Strategy

- API retry
- solver retry
- workflow retry

---

## Fallback Strategy

- fallback solver
- heuristic approximation
- partial result return

---

## Circuit Breaker

- LLM failure protection
- solver timeout protection

---

# 9.13 Summary（总结）

Infrastructure Layer 是 OptiMind 的：

> **System Execution Foundation（系统执行基础层）**

它提供：

- 运行环境
- 服务调度
- 数据存储
- 任务队列
- 可观测性
- 部署能力

核心价值：

> **Without infrastructure, architecture cannot run.**

这一层让 OptiMind 从：

> “设计系统”

变成：“可部署的工业系统”
