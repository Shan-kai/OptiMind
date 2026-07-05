import { useEffect, useRef } from 'react'
import type { SessionEvent } from '../types/session'

interface EventStreamPanelProps {
  events: SessionEvent[]
  isLoading?: boolean
}

function eventIconPath(eventType: SessionEvent['event_type']): string {
  const paths: Record<string, string> = {
    user_message:
      'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z',
    assistant_message:
      'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
    tool_call: 'M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z',
    tool_result:
      'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
    state_update:
      'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
    pipeline_run:
      'M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z',
    error:
      'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  }
  return paths[eventType] || paths.tool_call
}

function EventIcon({ eventType }: { eventType: SessionEvent['event_type'] }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      strokeWidth={1.5}
      stroke="currentColor"
      className="h-4 w-4"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d={eventIconPath(eventType)} />
    </svg>
  )
}

function eventTone(eventType: SessionEvent['event_type']) {
  const toneMap: Record<string, { bg: string; text: string; ring: string }> = {
    user_message: { bg: 'bg-slate-100', text: 'text-slate-600', ring: 'ring-slate-200' },
    assistant_message: { bg: 'bg-indigo-50', text: 'text-indigo-600', ring: 'ring-indigo-200' },
    tool_call: { bg: 'bg-sky-50', text: 'text-sky-600', ring: 'ring-sky-200' },
    tool_result: { bg: 'bg-emerald-50', text: 'text-emerald-600', ring: 'ring-emerald-200' },
    state_update: { bg: 'bg-amber-50', text: 'text-amber-600', ring: 'ring-amber-200' },
    pipeline_run: { bg: 'bg-violet-50', text: 'text-violet-600', ring: 'ring-violet-200' },
    error: { bg: 'bg-rose-50', text: 'text-rose-600', ring: 'ring-rose-200' },
  }
  return toneMap[eventType] || toneMap.tool_call
}

function formatEventSummary(event: SessionEvent): string {
  const { event_type, payload } = event
  if (event_type === 'tool_call') {
    const tool = (payload.tool as string) || 'unknown'
    return `调用 ${tool}`
  }
  if (event_type === 'tool_result') {
    const tool = (payload.tool as string) || 'tool'
    const status = (payload.status as string) || 'ok'
    return `${tool} → ${status}`
  }
  if (event_type === 'assistant_message') {
    return (payload.message as string) || 'assistant'
  }
  if (event_type === 'user_message') {
    return (payload.message as string) || 'user'
  }
  if (event_type === 'state_update') {
    const keys = Object.keys(payload).slice(0, 3)
    return `更新状态: ${keys.join(', ')}${Object.keys(payload).length > 3 ? '...' : ''}`
  }
  if (event_type === 'pipeline_run') {
    return (payload.status as string) || 'pipeline run'
  }
  if (event_type === 'error') {
    return (payload.message as string) || 'error'
  }
  return event_type
}

function ToolResultDetail({ payload }: { payload: SessionEvent['payload'] }) {
  const status = payload.status as string | undefined
  const result = payload.result as Record<string, unknown> | undefined
  if (!status) return null

  return (
    <div className="mt-1.5 space-y-1 text-xs text-slate-500">
      <div className="flex items-center gap-1.5">
        <span className="font-medium">状态:</span>
        <span
          className={`rounded-full px-1.5 py-0.5 font-medium ${
            status === 'ok'
              ? 'bg-emerald-50 text-emerald-700'
              : status === 'awaiting_input'
                ? 'bg-amber-50 text-amber-700'
                : 'bg-rose-50 text-rose-700'
          }`}
        >
          {status}
        </span>
      </div>
      {result && Object.keys(result).length > 0 && (
        <pre className="max-h-24 overflow-auto rounded bg-slate-50 p-1.5 font-mono text-[10px]">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function EventStreamPanel({ events, isLoading }: EventStreamPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events, isLoading])

  const visibleEvents = events.filter((e) =>
    ['tool_call', 'tool_result', 'assistant_message', 'pipeline_run', 'error'].includes(
      e.event_type,
    ),
  )

  if (visibleEvents.length === 0 && !isLoading) {
    return (
      <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
        <h3 className="mb-2 text-sm font-bold text-slate-800">Agent 思考过程</h3>
        <p className="text-xs text-slate-400">暂无事件，发送消息后将显示工具调用记录。</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-bold text-slate-800">Agent 思考过程</h3>
      <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
        {visibleEvents.map((event) => {
          const tone = eventTone(event.event_type)
          return (
            <div key={event.sequence} className="flex items-start gap-2.5 text-sm">
              <div
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ring-1 ${tone.bg} ${tone.text} ${tone.ring}`}
              >
                <EventIcon eventType={event.event_type} />
              </div>
              <div className="flex-1">
                <div className="font-medium text-slate-700">{formatEventSummary(event)}</div>
                {event.event_type === 'tool_result' && <ToolResultDetail payload={event.payload} />}
                {event.event_type === 'assistant_message' &&
                  typeof event.payload.message === 'string' && (
                    <div className="mt-1 text-xs text-slate-500 line-clamp-2">
                      {event.payload.message}
                    </div>
                  )}
              </div>
            </div>
          )
        })}
        {isLoading && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400"></div>
            <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400 delay-100"></div>
            <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400 delay-200"></div>
            <span>等待 LLM 完成...</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
