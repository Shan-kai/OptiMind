import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { IRConstraint, IRExpression, IRModel, IRVariable } from '../types/ir'
import type { AnalysisReport, SolverSolution } from '../types/session'
import LatexView from './LatexView'

interface ResultPanelProps {
  report: AnalysisReport
  executionGraph: string[]
  ir: IRModel | null
  solution: SolverSolution | null
}

type TabKey = 'summary' | 'ir' | 'solution'

/* ------------------------------------------------------------------
   Icons
   ------------------------------------------------------------------ */
function Icon({
  name,
  className = 'h-4 w-4',
}: {
  name: string
  className?: string
}) {
  const paths: Record<string, React.ReactNode> = {
    check: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M5 13l4 4L19 7"
      />
    ),
    x: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M6 18L18 6M6 6l12 12"
      />
    ),
    alert: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
      />
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="10" strokeWidth="2" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 16v-4M12 8h.01" />
      </>
    ),
    summary: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    ),
    ir: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
      />
    ),
    solution: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M13 10V3L4 14h7v7l9-11h-7z"
      />
    ),
    empty: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
      />
    ),
    target: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    ),
    arrow: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M17 8l4 4m0 0l-4 4m4-4H3"
      />
    ),
    lightbulb: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
      />
    ),
    sparkle: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
      />
    ),
  }

  const icon = paths[name] ?? paths.info
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      className={className}
      aria-hidden="true"
    >
      {icon}
    </svg>
  )
}

/* ------------------------------------------------------------------
   Status helpers
   ------------------------------------------------------------------ */
type StatusTone = 'success' | 'error' | 'warning' | 'info' | 'neutral'

interface StatusConfig {
  label: string
  tone: StatusTone
  icon: string
  badgeClass: string
  accentClass: string
}

function getStatusConfig(status?: string | null): StatusConfig {
  const s = (status ?? '').toLowerCase()

  if (['success', 'optimal', 'solved', 'completed'].includes(s)) {
    return {
      label: status || '成功',
      tone: 'success',
      icon: 'check',
      badgeClass: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
      accentClass: 'border-emerald-400',
    }
  }
  if (['error', 'no_solution', 'infeasible', 'unbounded', 'failed'].includes(s)) {
    return {
      label: status || '错误',
      tone: 'error',
      icon: 'x',
      badgeClass: 'bg-rose-50 text-rose-700 ring-rose-600/20',
      accentClass: 'border-rose-400',
    }
  }
  if (['partial', 'feasible', 'suboptimal', 'limited'].includes(s)) {
    return {
      label: status || '部分可行',
      tone: 'warning',
      icon: 'alert',
      badgeClass: 'bg-amber-50 text-amber-700 ring-amber-600/20',
      accentClass: 'border-amber-400',
    }
  }
  if (['awaiting_input', 'pending', 'running', 'created'].includes(s)) {
    return {
      label: status || '等待输入',
      tone: 'info',
      icon: 'info',
      badgeClass: 'bg-sky-50 text-sky-700 ring-sky-600/20',
      accentClass: 'border-sky-400',
    }
  }

  return {
    label: status || '未知',
    tone: 'neutral',
    icon: 'info',
    badgeClass: 'bg-slate-100 text-slate-700 ring-slate-500/20',
    accentClass: 'border-slate-300',
  }
}

function StatusBadge({ status, className = '' }: { status?: string | null; className?: string }) {
  const cfg = getStatusConfig(status)
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${cfg.badgeClass} ${className}`}
    >
      <Icon name={cfg.icon} className="h-3.5 w-3.5" />
      {cfg.label}
    </span>
  )
}

/* ------------------------------------------------------------------
   Shared primitives
   ------------------------------------------------------------------ */
function SectionCard({
  title,
  icon,
  children,
  className = '',
}: {
  title: string
  icon?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded-xl border border-slate-100 bg-white p-4 shadow-sm transition hover:shadow-md ${className}`}
    >
      <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-800">
        {icon && <Icon name={icon} className="h-4 w-4 text-indigo-500" />}
        {title}
      </h3>
      {children}
    </section>
  )
}

function EmptyState({ text = '暂无数据' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center text-slate-400">
      <div className="mb-3 rounded-2xl bg-slate-50 p-4 text-slate-300">
        <Icon name="empty" className="h-10 w-10" />
      </div>
      <p className="text-sm font-medium">{text}</p>
    </div>
  )
}

/* ------------------------------------------------------------------
   Formatting helpers (preserved logic)
   ------------------------------------------------------------------ */
function formatScalar(value: unknown): React.ReactNode {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))
  }
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.length > 0 ? value.join(', ') : '-'
  return JSON.stringify(value)
}

function renderVariableValue(value: unknown): React.ReactNode {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'number') {
    return (
      <span className="font-mono text-slate-800">
        {Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))}
      </span>
    )
  }
  if (typeof value === 'string') return <span className="font-mono text-slate-800">{value}</span>
  if (typeof value === 'object' && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return '-'
    return (
      <table className="mt-1 w-full text-left text-[11px]">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="border-b border-slate-100 last:border-0">
              <td className="py-0.5 pr-3 font-medium text-slate-500">{k}</td>
              <td className="py-0.5 font-mono text-slate-800">{renderVariableValue(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
  return formatScalar(value)
}

/* ------------------------------------------------------------------
   IR view
   ------------------------------------------------------------------ */
function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-lg bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-600/10">
      {children}
    </span>
  )
}

function VariableCard({ variable }: { variable: IRVariable }) {
  const domainLabels: Record<string, string> = {
    binary: '二元',
    integer: '整数',
    continuous: '连续',
    semi_continuous: '半连续',
  }

  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3 transition hover:bg-slate-50">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-bold text-indigo-700">{variable.name}</span>
        <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600">
          {domainLabels[variable.domain] ?? variable.domain}
        </span>
        {variable.sets && variable.sets.length > 0 && (
          <span className="text-[11px] text-slate-500">
            索引：{variable.sets.join(' × ')}
          </span>
        )}
      </div>
      {variable.description && (
        <div className="mt-1 text-[11px] text-slate-500">{variable.description}</div>
      )}
      {(variable.lower !== undefined && variable.lower !== null) ||
      (variable.upper !== undefined && variable.upper !== null) ? (
        <div className="mt-1.5 text-xs text-slate-600">
          {variable.lower ?? '-∞'} ≤ {variable.name} ≤ {variable.upper ?? '+∞'}
        </div>
      ) : null}
    </div>
  )
}

function ObjectiveView({ objective }: { objective: IRExpression }) {
  if (objective.latex) {
    return (
      <div className="overflow-x-auto rounded-lg bg-slate-50 px-3 py-2">
        <LatexView latex={objective.latex} displayMode />
      </div>
    )
  }
  if (objective.raw_expr) {
    return <div className="font-mono text-sm text-slate-800">{objective.raw_expr}</div>
  }
  if (!objective.terms || objective.terms.length === 0) {
    return <EmptyState text="目标函数为空" />
  }
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        {objective.kind} 表达式
      </p>
      {objective.terms.map((term, idx) => (
        <div key={idx} className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-sm text-slate-800">
          {term.coef} · {term.var}
          {term.sum_sets && term.sum_sets.length > 0 && (
            <span className="ml-2 text-xs text-slate-500">
              求和：{term.sum_sets.join(', ')}
              {term.where && ` （${term.where}）`}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function ConstraintCard({ constraint }: { constraint: IRConstraint }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3 transition hover:bg-slate-50">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-bold text-indigo-700">{constraint.name}</div>
        {constraint.description && (
          <div className="text-[11px] text-slate-500">{constraint.description}</div>
        )}
      </div>
      <div className="mt-2 overflow-x-auto rounded bg-white px-2 py-1.5">
        {constraint.latex ? (
          <LatexView latex={constraint.latex} displayMode />
        ) : (
          <code className="text-xs text-slate-700">
            {constraint.scope ? `${constraint.scope}: ` : ''}
            {constraint.expr} {constraint.sense} {constraint.rhs ?? ''}
          </code>
        )}
      </div>
    </div>
  )
}

function IRView({ ir }: { ir: IRModel | null }) {
  if (!ir) return <EmptyState />

  const senseLabels: Record<string, string> = {
    min: '最小化',
    max: '最大化',
    minimize: '最小化',
    maximize: '最大化',
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Tag>问题类型：{ir.problem_type}</Tag>
        <Tag>优化方向：{senseLabels[ir.sense] ?? ir.sense}</Tag>
      </div>

      {ir.sets.length > 0 && (
        <SectionCard title="集合" icon="ir">
          <div className="flex flex-wrap gap-2">
            {ir.sets.map((s) => (
              <div
                key={s.name}
                className="rounded bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700"
              >
                {s.name}
                {Array.isArray(s.members) && s.members.length > 0 && (
                  <span className="ml-1 text-indigo-500">
                    = {'{'}{s.members.join(', ')}{'}'}
                  </span>
                )}
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {ir.variables.length > 0 && (
        <SectionCard title="决策变量" icon="ir">
          <div className="grid grid-cols-1 gap-2">
            {ir.variables.map((v) => (
              <VariableCard key={v.name} variable={v} />
            ))}
          </div>
        </SectionCard>
      )}

      {ir.objective && (
        <SectionCard title="目标函数" icon="target">
          <ObjectiveView objective={ir.objective} />
        </SectionCard>
      )}

      {ir.constraints.length > 0 && (
        <SectionCard title="约束条件" icon="ir">
          <div className="grid grid-cols-1 gap-2">
            {ir.constraints.map((c) => (
              <ConstraintCard key={c.name} constraint={c} />
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------
   Solution view
   ------------------------------------------------------------------ */
function SolutionView({ solution }: { solution: SolverSolution | null }) {
  if (!solution) return <EmptyState />

  const variables = solution.variables

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">求解状态</div>
          <div className="mt-1.5">
            <StatusBadge status={solution.status} />
          </div>
        </div>
        <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">目标值</div>
          <div className="mt-1 text-xl font-bold text-slate-900">
            {formatScalar(solution.objective_value)}
          </div>
        </div>
      </div>

      {variables && (
        <SectionCard title="变量取值" icon="solution">
          <div className="overflow-hidden rounded-lg border border-slate-100">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-3 py-1.5 text-left">变量</th>
                  <th className="px-3 py-1.5 text-right">取值</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {Object.entries(variables).map(([name, value]) => (
                  <tr key={name} className="transition hover:bg-slate-50/60">
                    <td className="px-3 py-2 font-medium text-indigo-700">{name}</td>
                    <td className="px-3 py-2 text-right">{renderVariableValue(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------
   Summary tab
   ------------------------------------------------------------------ */
function SummaryTab({
  report,
  executionGraph,
}: {
  report: AnalysisReport
  executionGraph: string[]
}) {
  const statusCfg = getStatusConfig(report.status)

  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div
          className={`relative overflow-hidden rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100 transition hover:shadow-md border-l-4 ${statusCfg.accentClass}`}
        >
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">状态</div>
          <div className="mt-2">
            <StatusBadge status={report.status} />
          </div>
          <Icon name={statusCfg.icon} className="absolute right-4 top-4 h-8 w-8 text-slate-100" />
        </div>

        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 p-5 text-white shadow-md transition hover:shadow-lg">
          <div className="text-xs font-semibold uppercase tracking-wider text-indigo-100">目标值</div>
          <div className="mt-1 text-2xl font-bold">
            {report.objective_value?.toFixed(2) ?? '-'}
          </div>
          <Icon name="target" className="absolute right-4 top-4 h-8 w-8 text-white/20" />
        </div>

        <div className="relative overflow-hidden rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100 transition hover:shadow-md">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">优化方向</div>
          <div className="mt-1 text-xl font-bold text-slate-900">{report.objective_sense}</div>
          <Icon name="arrow" className="absolute right-4 top-4 h-8 w-8 text-slate-100" />
        </div>
      </div>

      {/* Execution graph */}
      {executionGraph.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {executionGraph.map((stage, idx) => (
            <div key={`${stage}-${idx}`} className="flex items-center gap-2">
              <span className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
                {stage}
              </span>
              {idx < executionGraph.length - 1 && (
                <Icon name="arrow" className="h-3.5 w-3.5 text-slate-300" />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Executive summary */}
      {(report.executive_summary || report.llm_summary) && (
        <SectionCard title="执行摘要" icon="summary">
          <div className="prose prose-sm max-w-none text-slate-700">
            <ReactMarkdown>{report.llm_summary || report.executive_summary}</ReactMarkdown>
          </div>
        </SectionCard>
      )}

      {/* LLM recommendations */}
      {report.llm_recommendations.length > 0 && (
        <SectionCard title="AI 建议" icon="sparkle">
          <ul className="space-y-2">
            {report.llm_recommendations.map((rec, idx) => (
              <li key={idx} className="flex gap-3 text-sm text-slate-700">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-bold text-indigo-600">
                  {idx + 1}
                </span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {/* Assumptions */}
      {report.llm_assumptions.length > 0 && (
        <SectionCard title="建模假设" icon="info">
          <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
            {report.llm_assumptions.map((ass, idx) => (
              <li key={idx}>{ass}</li>
            ))}
          </ul>
        </SectionCard>
      )}

      {/* Recommendations */}
      {report.recommendations.length > 0 && report.llm_recommendations.length === 0 && (
        <SectionCard title="优化建议" icon="lightbulb">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {report.recommendations.map((rec, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-slate-100 bg-slate-50/60 p-4 transition hover:bg-slate-50"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-semibold text-indigo-700">{rec.title}</div>
                  <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-500 ring-1 ring-slate-200">
                    {rec.priority}
                  </span>
                </div>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">{rec.description}</p>
                {rec.expected_impact && (
                  <div className="mt-3 text-xs text-slate-400">
                    预期影响：{rec.expected_impact}
                  </div>
                )}
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------
   Ontology patch notice
   ------------------------------------------------------------------ */
function OntologyPatchNotice() {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
      <div className="flex items-start gap-3">
        <Icon name="alert" className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div>
          <p className="font-medium">系统需要对建模规则进行补丁</p>
          <p className="mt-1 text-amber-700">
            当前问题缺少必要的参数或字段映射，系统已生成 ontology 补丁建议。请在对话中选择“同意并应用”或“拒绝并手动输入”。
          </p>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------
   Tabs
   ------------------------------------------------------------------ */
function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: string
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
        active
          ? 'bg-white text-indigo-700 shadow-sm ring-1 ring-slate-200'
          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
      }`}
      aria-selected={active}
      role="tab"
    >
      <Icon name={icon} className={active ? 'h-4 w-4 text-indigo-500' : 'h-4 w-4 text-slate-400'} />
      {label}
    </button>
  )
}

/* ------------------------------------------------------------------
   Main component
   ------------------------------------------------------------------ */
export default function ResultPanel({ report, executionGraph, ir, solution }: ResultPanelProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('summary')
  const [showPatchNotice, setShowPatchNotice] = useState(true)

  useEffect(() => {
    setShowPatchNotice(true)
  }, [ir])

  const needsPatchNotice = ir?.problem_type === 'ontology_patch' && showPatchNotice

  return (
    <div className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
      {/* Header */}
      <div className="border-b border-slate-100 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold tracking-tight text-slate-900">优化结果</h2>
            <p className="mt-0.5 text-xs text-slate-500">基于求解器与 LLM 的联合分析</p>
          </div>
          <StatusBadge status={report.status} />
        </div>

        {executionGraph.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {executionGraph.map((stage, idx) => (
              <div key={`${stage}-${idx}`} className="flex items-center gap-2">
                <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-600/10">
                  {stage}
                </span>
                {idx < executionGraph.length - 1 && (
                  <Icon name="arrow" className="h-3.5 w-3.5 text-slate-300" />
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {needsPatchNotice && (
        <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <OntologyPatchNotice />
            </div>
            <button
              type="button"
              onClick={() => setShowPatchNotice(false)}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              关闭
            </button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-2">
        <div className="flex gap-1">
          <TabButton
            active={activeTab === 'summary'}
            onClick={() => setActiveTab('summary')}
            icon="summary"
            label="摘要"
          />
          <TabButton
            active={activeTab === 'ir'}
            onClick={() => setActiveTab('ir')}
            icon="ir"
            label="建模结果"
          />
          <TabButton
            active={activeTab === 'solution'}
            onClick={() => setActiveTab('solution')}
            icon="solution"
            label="最优解"
          />
        </div>
      </div>

      {/* Tab panels */}
      <div className="p-5">
        {activeTab === 'summary' && <SummaryTab report={report} executionGraph={executionGraph} />}
        {activeTab === 'ir' && <IRView ir={ir} />}
        {activeTab === 'solution' && <SolutionView solution={solution} />}
      </div>
    </div>
  )
}
