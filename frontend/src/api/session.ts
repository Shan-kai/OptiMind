import axios from 'axios'
import type { SessionEvent, SessionResponse, UploadParams } from '../types/session'
import { getErrorMessage } from '../lib/messages'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 300000,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = axios.isAxiosError(error)
      ? error.response?.data?.detail || error.message
      : error instanceof Error
        ? error.message
        : 'UNKNOWN'
    return Promise.reject(new Error(getErrorMessage(message)))
  },
)

export async function createSession(
  file: File,
  params: UploadParams = {},
): Promise<SessionResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (params.business_goal) {
    formData.append('business_goal', params.business_goal)
  }
  if (params.problem_type) {
    formData.append('problem_type', params.problem_type)
  }

  const { data } = await api.post<SessionResponse>('/sessions', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function sendChatMessage(
  sessionId: string,
  message: string,
): Promise<SessionResponse> {
  const { data } = await api.post<SessionResponse>(`/sessions/${sessionId}/chat`, {
    message,
  })
  return data
}

export async function getSession(sessionId: string): Promise<SessionResponse> {
  const { data } = await api.get<SessionResponse>(`/sessions/${sessionId}`)
  return data
}

export async function getSessionEvents(sessionId: string): Promise<SessionEvent[]> {
  const { data } = await api.get<SessionEvent[]>(`/sessions/${sessionId}/events`)
  return data
}

export { getProblemTypes, getProblemTypeDetail } from './problemTypes'
