import { useCallback, useEffect, useState } from 'react'
import FileUploader from './components/FileUploader'
import ChatBox from './components/ChatBox'
import SessionStatus from './components/SessionStatus'
import ResultPanel from './components/ResultPanel'
import DataPanel from './components/DataPanel'
import EventStreamPanel from './components/EventStreamPanel'
import { useSessionStore } from './store/sessionStore'

const MIN_LEFT_WIDTH = 30
const MAX_LEFT_WIDTH = 70
const DEFAULT_LEFT_WIDTH = 66

function Logo({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="6" fill="url(#logo-gradient)" />
      <path
        d="M7 15.5C7 15.5 9 8.5 12 8.5C15 8.5 17 15.5 17 15.5"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="3" stroke="white" strokeWidth="2" />
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366f1" />
          <stop offset="1" stopColor="#7c3aed" />
        </linearGradient>
      </defs>
    </svg>
  )
}

function ErrorIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={2}
      stroke="currentColor"
      className={className}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  )
}

function EmptyResult() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center rounded-2xl bg-white p-6 text-center shadow-sm ring-1 ring-slate-100">
      <div className="mb-3 rounded-full bg-indigo-50 p-3 text-indigo-300">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="h-8 w-8"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5m.75-9l3-3 2.148 2.148A12.061 12.061 0 0116.5 7.605"
          />
        </svg>
      </div>
      <p className="text-sm font-medium text-slate-600">完成优化后，结果会显示在这里</p>
      <p className="mt-1 text-xs text-slate-400">你可以在左侧与助手继续交互</p>
    </div>
  )
}

export default function App() {
  const {
    sessionId,
    status,
    messages,
    events,
    clarificationRequest,
    ir,
    solution,
    analysisReport,
    instance,
    executionGraph,
    errors,
    isLoading,
    uploadedFile,
    uploadFile,
    sendMessage,
    reset,
  } = useSessionStore()

  const [leftWidth, setLeftWidth] = useState(DEFAULT_LEFT_WIDTH)
  const [isResizing, setIsResizing] = useState(false)

  const startResize = useCallback(() => setIsResizing(true), [])
  const stopResize = useCallback(() => setIsResizing(false), [])

  const handleResize = useCallback(
    (e: MouseEvent) => {
      const container = document.getElementById('main-content')
      if (!container) return
      const rect = container.getBoundingClientRect()
      const pct = ((e.clientX - rect.left) / rect.width) * 100
      setLeftWidth(Math.min(MAX_LEFT_WIDTH, Math.max(MIN_LEFT_WIDTH, pct)))
    },
    []
  )

  useEffect(() => {
    if (!isResizing) return
    window.addEventListener('mousemove', handleResize)
    window.addEventListener('mouseup', stopResize)
    return () => {
      window.removeEventListener('mousemove', handleResize)
      window.removeEventListener('mouseup', stopResize)
    }
  }, [isResizing, handleResize, stopResize])

  const hasStarted = sessionId !== null

  return (
    <div className="mx-auto flex h-screen max-w-6xl flex-col p-4">
      <header className="mb-5 flex items-center justify-between border-b border-slate-200/80 pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-md">
            <Logo className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">OptiMind</h1>
            <p className="text-xs text-slate-500">AI 驱动的运筹优化助手</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {hasStarted && <SessionStatus status={status} />}
          {hasStarted && (
            <button
              onClick={reset}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
            >
              新建会话
            </button>
          )}
        </div>
      </header>

      {errors.length > 0 && (
        <div className="mb-5 flex items-start gap-3 rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700 shadow-sm">
          <ErrorIcon className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="flex-1 space-y-1">
            {errors.map((err, idx) => (
              <p key={idx}>{err}</p>
            ))}
          </div>
        </div>
      )}

      {!hasStarted ? (
        <div className="flex flex-1 flex-col items-center justify-center">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-100">
            <div className="mb-6 text-center">
              <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="h-7 w-7"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
                  />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-slate-900">开始优化</h2>
              <p className="mt-1 text-sm text-slate-500">上传数据文件并描述你的业务目标</p>
            </div>
            <FileUploader
              onUpload={(file, goal, type) =>
                uploadFile(file, {
                  business_goal: goal,
                  problem_type: type || undefined,
                })
              }
              isLoading={isLoading}
            />
          </div>
        </div>
      ) : (
        <main
          id="main-content"
          className={`flex flex-1 min-h-0 gap-1 ${isResizing ? 'select-none' : ''}`}
        >
          <div
            className="flex min-h-0 flex-col"
            style={{ width: `${leftWidth}%` }}
          >
            <ChatBox
              messages={messages}
              events={events}
              clarification={clarificationRequest}
              isLoading={isLoading}
              status={status}
              uploadedFile={uploadedFile}
              onSend={sendMessage}
            />
          </div>

          <div
            onMouseDown={startResize}
            className="group relative w-1.5 shrink-0 cursor-col-resize rounded-full bg-slate-200 transition-colors hover:bg-indigo-400 active:bg-indigo-500"
            title="拖动调整左右宽度"
          >
            <div className="absolute left-1/2 top-1/2 hidden h-8 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-500/30 group-hover:block" />
          </div>

          <div
            className="flex min-h-0 flex-col gap-4 overflow-y-auto"
            style={{ width: `${100 - leftWidth}%` }}
          >
            <EventStreamPanel events={events} isLoading={isLoading} />
            {analysisReport ? (
              <>
                <ResultPanel
                  report={analysisReport}
                  executionGraph={executionGraph}
                  ir={ir}
                  solution={solution}
                />
                <DataPanel instance={instance} />
              </>
            ) : (
              <EmptyResult />
            )}
          </div>
        </main>
      )}
    </div>
  )
}
