import { useEffect, useRef, useState } from 'react'
import type { ChatMessage as ChatMessageType, ClarificationRequest, SessionEvent } from '../types/session'
import ChatMessage from './ChatMessage'
import QuickReplies from './QuickReplies'

interface ChatBoxProps {
  messages: ChatMessageType[]
  events: SessionEvent[]
  clarification: ClarificationRequest | null
  isLoading: boolean
  status: string
  uploadedFile: { name: string; size: number } | null
  onSend: (text: string) => void
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export default function ChatBox({
  messages,
  events,
  clarification,
  isLoading,
  status,
  uploadedFile,
  onSend,
}: ChatBoxProps) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !isLoading) {
      onSend(input.trim())
      setInput('')
    }
  }

  const handleQuickReply = (value: string) => {
    if (!isLoading) {
      onSend(value)
    }
  }

  const isAwaiting = status === 'awaiting_input'

  const lastToolCall = isLoading
    ? [...events]
        .reverse()
        .find((e) => e.event_type === 'tool_call')
    : null

  return (
    <div className="flex h-full flex-col rounded-xl bg-white shadow">
      {uploadedFile && (
        <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-2">
          <div className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-1.5 text-sm shadow-sm ring-1 ring-slate-200">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="h-4 w-4 text-indigo-500"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a3 3 0 00-3-3H10.5z"
              />
            </svg>
            <span className="font-medium text-slate-700">{uploadedFile.name}</span>
            <span className="text-xs text-slate-400">({formatFileSize(uploadedFile.size)})</span>
          </div>
        </div>
      )}
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && !uploadedFile && (
          <div className="text-center text-sm text-slate-400">
            上传文件后，这里会显示对话
          </div>
        )}
        {messages.map((msg, idx) => (
          <div key={idx}>
            <ChatMessage message={msg} />
            {msg.role === 'assistant' && idx === messages.length - 1 && clarification && (
              <QuickReplies
                options={clarification.options}
                onSelect={handleQuickReply}
                disabled={isLoading}
              />
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-none bg-white px-4 py-3 shadow">
              <div className="flex items-center gap-2">
                <div className="flex space-x-1">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400"></div>
                  <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400 delay-100"></div>
                  <div className="h-2 w-2 animate-bounce rounded-full bg-slate-400 delay-200"></div>
                </div>
                {lastToolCall && (
                  <span className="text-xs text-slate-500">
                    正在调用{' '}
                    <span className="font-medium text-indigo-600">
                      {(lastToolCall.payload.tool as string) || 'tool'}
                    </span>
                    ...
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="border-t border-slate-100 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              isAwaiting
                ? '请回答上面的问题，或点击快捷选项'
                : '输入消息，例如：跑一下 / 业务目标改成最小化成本'
            }
            disabled={isLoading}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none disabled:bg-slate-100"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            发送
          </button>
        </div>
      </form>
    </div>
  )
}
