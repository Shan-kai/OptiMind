import axios from 'axios'
import type { ProblemTypeOption, ProblemTypeDetail } from '../types/session'
import { MOCK_PROBLEM_TYPE_DETAILS, MOCK_PROBLEM_TYPES } from '../mocks/problemTypes'
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

export async function getProblemTypes(): Promise<ProblemTypeOption[]> {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true') {
    return Promise.resolve(MOCK_PROBLEM_TYPES)
  }
  const { data } = await api.get<ProblemTypeOption[]>('/problem-types')
  return data
}

export async function getProblemTypeDetail(value: string): Promise<ProblemTypeDetail> {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true') {
    const detail = MOCK_PROBLEM_TYPE_DETAILS[value]
    if (!detail) {
      return Promise.reject(new Error(getErrorMessage(`未找到问题类型详情: ${value}`)))
    }
    return Promise.resolve(detail)
  }
  const { data } = await api.get<ProblemTypeDetail>(`/problem-types/${value}`)
  return data
}
