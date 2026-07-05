import type { IRModel } from './ir'

export interface ChatMessage {
  role: 'system' | 'assistant' | 'user'
  content: string
  created_at?: string
}

export interface ClarificationOption {
  label: string
  value: string
}

export type SessionEventType =
  | 'user_message'
  | 'assistant_message'
  | 'tool_call'
  | 'tool_result'
  | 'state_update'
  | 'pipeline_run'
  | 'error'

export interface SessionEvent {
  sequence: number
  timestamp: string
  event_type: SessionEventType
  handler: string
  payload: Record<string, unknown>
  errors: string[]
}

export interface ClarificationRequest {
  station: 'data_intelligence' | 'modeling' | 'ontology_patch'
  question: string
  options: ClarificationOption[]
  expected_field: string
  context: Record<string, string>
}

export interface AnalysisReport {
  status: string
  objective_value: number | null
  objective_sense: string
  executive_summary: string
  llm_summary: string
  llm_recommendations: string[]
  llm_assumptions: string[]
  recommendations: Array<{
    category: string
    priority: string
    title: string
    description: string
    expected_impact: string
    actionable: boolean
  }>
  variable_summaries: Array<{
    name: string
    value: number | Record<string, number>
    description: string
    is_indexed: boolean
  }>
  constraint_statuses: Array<{
    name: string
    is_binding: boolean
    is_violated: boolean
  }>
  raw_solution: Record<string, unknown>
}

export interface SolverSolution {
  status: string
  objective_value?: number | null
  variables?: Record<string, number | Record<string, number>>
  [key: string]: unknown
}

export interface OptimizationInstance {
  problem_type: string
  sets: Record<string, string[]>
  parameters: Record<string, number | Record<string, number> | Record<string, Record<string, number>>>
  meta?: Record<string, unknown>
}

export interface SessionResponse {
  session_id: string
  status: 'created' | 'awaiting_input' | 'success' | 'error'
  messages: ChatMessage[]
  clarification_request: ClarificationRequest | null
  ir: IRModel | null
  solution: SolverSolution | null
  analysis_report: AnalysisReport | null
  instance: OptimizationInstance | null
  execution_graph: string[]
  errors: string[]
}

export interface UploadParams {
  business_goal?: string
  problem_type?: string
}

export interface ProblemTypeOption {
  value: string
  label: string
  description: string
}

export interface ProblemTypeDetail {
  value: string
  label: string
  description: string
  sets: Record<string, string>
  parameters: Record<string, string>
  variables: Record<string, unknown>[]
  constraints: Record<string, unknown>[]
  objective: Record<string, unknown> | null
  tags: string[]
}
