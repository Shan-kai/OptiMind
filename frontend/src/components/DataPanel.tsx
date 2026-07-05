import { useState } from 'react'
import type { OptimizationInstance } from '../types/session'

interface DataPanelProps {
  instance: OptimizationInstance | null
}

function isScalar(value: unknown): value is number {
  return typeof value === 'number'
}

function isVector(value: unknown): value is Record<string, number> {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((v) => typeof v === 'number')
  )
}

function isMatrix(value: unknown): value is Record<string, Record<string, number>> {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((v) => isVector(v))
  )
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))
}

function ScalarParam({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-0.5 text-lg font-bold text-slate-900">{formatNumber(value)}</div>
    </div>
  )
}

function VectorParam({ label, value }: { label: string; value: Record<string, number> }) {
  const entries = Object.entries(value)
  return (
    <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-1.5 grid grid-cols-3 gap-1 sm:grid-cols-4 md:grid-cols-5">
        {entries.map(([key, v]) => (
          <div key={key} className="rounded bg-slate-50 px-2 py-1">
            <div className="text-[10px] font-semibold text-slate-500">{key}</div>
            <div className="text-xs font-medium text-slate-900">{formatNumber(v)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function MatrixParam({ label, value }: { label: string; value: Record<string, Record<string, number>> }) {
  const rows = Object.keys(value)
  const cols = rows.length > 0 ? Object.keys(value[rows[0]]) : []
  return (
    <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
      <div className="mt-1.5 overflow-hidden rounded border border-slate-100">
        <table className="w-full text-[11px]">
          <thead className="bg-slate-50 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-2 py-1 text-left"></th>
              {cols.map((col) => (
                <th key={col} className="px-2 py-1 text-right">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row) => (
              <tr key={row} className="hover:bg-slate-50/60">
                <td className="px-2 py-1 font-medium text-slate-700">{row}</td>
                {cols.map((col) => (
                  <td key={col} className="px-2 py-1 text-right font-mono text-slate-800">
                    {formatNumber(value[row][col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ParameterCard({ symbol, value }: { symbol: string; value: unknown }) {
  if (isScalar(value)) {
    return <ScalarParam label={symbol} value={value} />
  }
  if (isMatrix(value)) {
    return <MatrixParam label={symbol} value={value} />
  }
  if (isVector(value)) {
    return <VectorParam label={symbol} value={value} />
  }
  return (
    <div className="rounded-lg border border-slate-100 bg-white p-3 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{symbol}</div>
      <pre className="mt-1 overflow-auto rounded bg-slate-50 p-1.5 text-[10px] text-slate-700">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

export default function DataPanel({ instance }: DataPanelProps) {
  const [expanded, setExpanded] = useState(true)

  if (!instance) {
    return (
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
        <h2 className="text-sm font-bold text-slate-900">输入数据</h2>
        <p className="mt-1 text-xs text-slate-400">暂无数据</p>
      </div>
    )
  }

  const parameters = Object.entries(instance.parameters)
  const sets = Object.entries(instance.sets)

  return (
    <div className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between p-4 text-left"
      >
        <div>
          <h2 className="text-base font-bold tracking-tight text-slate-900">输入数据</h2>
          <p className="text-[11px] text-slate-500">优化模型使用的参数与集合</p>
        </div>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={2}
          stroke="currentColor"
          className={`h-5 w-5 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 p-4">
          {sets.length > 0 && (
            <div className="mb-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">集合</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {sets.map(([name, members]) => (
                  <div
                    key={name}
                    className="rounded bg-indigo-50 px-2 py-1 text-[11px] font-medium text-indigo-700"
                  >
                    {name} = {'{'}{members.join(', ')}{'}'}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-2">
            {parameters.map(([symbol, value]) => (
              <ParameterCard key={symbol} symbol={symbol} value={value} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
