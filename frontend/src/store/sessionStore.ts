import { create } from 'zustand'
import type { ChatMessage, ClarificationRequest, SessionEvent, SessionResponse, UploadParams } from '../types/session'
import { createSession, getSessionEvents, sendChatMessage } from '../api/session'
import { getErrorMessage } from '../lib/messages'

interface SessionState {
  sessionId: string | null
  status: 'idle' | 'created' | 'awaiting_input' | 'success' | 'error'
  messages: ChatMessage[]
  events: SessionEvent[]
  clarificationRequest: ClarificationRequest | null
  ir: SessionResponse['ir']
  solution: SessionResponse['solution']
  analysisReport: SessionResponse['analysis_report']
  instance: SessionResponse['instance']
  executionGraph: string[]
  errors: string[]
  isLoading: boolean
  uploadedFile: { name: string; size: number } | null

  uploadFile: (file: File, params: UploadParams) => Promise<void>
  sendMessage: (text: string) => Promise<void>
  refreshEvents: () => Promise<void>
  reset: () => void
}

const initialState = {
  sessionId: null,
  status: 'idle' as const,
  messages: [],
  events: [],
  clarificationRequest: null,
  ir: null,
  solution: null,
  analysisReport: null,
  instance: null,
  executionGraph: [],
  errors: [],
  isLoading: false,
  uploadedFile: null,
}

function responseToState(response: SessionResponse): Partial<SessionState> {
  return {
    sessionId: response.session_id,
    status: response.status,
    messages: response.messages,
    clarificationRequest: response.clarification_request,
    ir: response.ir,
    solution: response.solution,
    analysisReport: response.analysis_report,
    instance: response.instance,
    executionGraph: response.execution_graph,
    errors: response.errors,
  }
}

export const useSessionStore = create<SessionState>((set, get) => ({
  ...initialState,

  uploadFile: async (file, params) => {
    set({ isLoading: true, errors: [] })
    try {
      const response = await createSession(file, params)
      const events = await getSessionEvents(response.session_id)
      set({
        ...responseToState(response),
        events,
        isLoading: false,
        uploadedFile: { name: file.name, size: file.size },
      })
    } catch (error) {
      set({
        ...initialState,
        isLoading: false,
        status: 'error',
        errors: [error instanceof Error ? error.message : getErrorMessage('UPLOAD_FAILED')],
      })
    }
  },

  sendMessage: async (text) => {
    const sessionId = get().sessionId
    if (!sessionId || text.trim() === '') return

    set((state) => ({
      messages: [...state.messages, { role: 'user', content: text }],
      isLoading: true,
    }))

    try {
      const response = await sendChatMessage(sessionId, text)
      const events = await getSessionEvents(sessionId)
      set({ ...responseToState(response), events, isLoading: false })
    } catch (error) {
      set((_state) => ({
        isLoading: false,
        status: 'error',
        errors: [error instanceof Error ? error.message : getErrorMessage('SEND_FAILED')],
      }))
    }
  },

  refreshEvents: async () => {
    const sessionId = get().sessionId
    if (!sessionId) return
    try {
      const events = await getSessionEvents(sessionId)
      set({ events })
    } catch (error) {
      // Non-fatal: event refresh failures should not block the UI.
      console.warn('Failed to refresh events:', error)
    }
  },

  reset: () => set(initialState),
}))
