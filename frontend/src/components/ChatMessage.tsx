import ReactMarkdown from 'react-markdown'
import type { ChatMessage as ChatMessageType } from '../types/session'

interface ChatMessageProps {
  message: ChatMessageType
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'rounded-br-none bg-indigo-600 text-white'
            : 'rounded-bl-none bg-white text-slate-800 shadow'
        }`}
      >
        <div className="mb-1 text-xs opacity-70">
          {isUser ? '你' : isAssistant ? 'OptiMind' : '系统'}
        </div>
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
      </div>
    </div>
  )
}
