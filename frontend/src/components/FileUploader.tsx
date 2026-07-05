import { useEffect, useState, useRef } from 'react'
import { getProblemTypeDetail, getProblemTypes } from '../api/session'
import type { ProblemTypeDetail, ProblemTypeOption } from '../types/session'
import { PROBLEM_TYPE_LABEL_OVERRIDES } from '../config/problemTypeLabels'

interface FileUploaderProps {
  onUpload: (file: File, businessGoal: string, problemType: string) => void
  isLoading: boolean
}

function getDisplayLabel(pt: ProblemTypeOption): string {
  return PROBLEM_TYPE_LABEL_OVERRIDES[pt.value] ?? pt.label
}

export default function FileUploader({ onUpload, isLoading }: FileUploaderProps) {
  const [file, setFile] = useState<File | null>(null)
  const [businessGoal, setBusinessGoal] = useState('')
  const [problemType, setProblemType] = useState('')
  const [problemTypes, setProblemTypes] = useState<ProblemTypeOption[]>([])
  const [isLoadingTypes, setIsLoadingTypes] = useState(false)
  const [typeHint, setTypeHint] = useState<ProblemTypeDetail | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setIsLoadingTypes(true)
    getProblemTypes()
      .then((types) => setProblemTypes(types))
      .catch(() => setProblemTypes([]))
      .finally(() => setIsLoadingTypes(false))
  }, [])

  useEffect(() => {
    if (!problemType) {
      setTypeHint(null)
      return
    }
    setTypeHint(null)
    getProblemTypeDetail(problemType)
      .then((detail) => setTypeHint(detail))
      .catch(() => setTypeHint(null))
  }, [problemType])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected) setFile(selected)
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (file) {
      onUpload(file, businessGoal, problemType)
    }
  }

  const hintText = problemTypes.length > 0
    ? `支持 ${problemTypes.map(getDisplayLabel).join('、')} 等优化模型数据`
    : '上传 CSV 数据，系统会自动识别问题类型'

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        className="cursor-pointer rounded-xl border-2 border-dashed border-indigo-300 bg-indigo-50 p-8 text-center transition hover:border-indigo-500 hover:bg-indigo-100"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileChange}
        />
        <p className="text-lg font-medium text-indigo-700">
          {file ? file.name : '点击或拖拽上传 CSV 文件'}
        </p>
        <p className="mt-2 text-sm text-indigo-500">{hintText}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">业务目标</label>
          <input
            type="text"
            value={businessGoal}
            onChange={(e) => setBusinessGoal(e.target.value)}
            placeholder="例如：最小化总成本"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">问题类型</label>
          <select
            value={problemType}
            onChange={(e) => setProblemType(e.target.value)}
            disabled={isLoadingTypes}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">自动识别</option>
            {problemTypes.map((pt) => (
              <option key={pt.value} value={pt.value}>
                {getDisplayLabel(pt)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {typeHint && (
        <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-800">
          <p className="font-medium">{typeHint.label}</p>
          <p className="mt-1 text-indigo-600">{typeHint.description}</p>
          {Object.keys(typeHint.parameters).length > 0 && (
            <p className="mt-2 text-xs text-indigo-500">
              需要字段：{Object.keys(typeHint.parameters).join('、')}
            </p>
          )}
        </div>
      )}

      <button
        type="submit"
        disabled={!file || isLoading}
        className="w-full rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        {isLoading ? '上传中...' : '开始优化'}
      </button>
    </form>
  )
}
