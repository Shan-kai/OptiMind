export type ObjectiveSense = 'min' | 'max'
export type VariableDomain = 'binary' | 'integer' | 'continuous' | 'semi_continuous'
export type ConstraintSense = 'le' | 'ge' | 'eq' | 'range'
export type ExpressionKind = 'linear' | 'quadratic' | 'general'

export interface IRMeta {
  schema_version?: string
  source?: string
  generated_at?: string
  [key: string]: unknown
}

export interface IRSet {
  name: string
  description?: string
  index_domain?: string
  members: 'from_instance' | unknown[]
}

export interface IRParameter {
  name: string
  description?: string
  sets?: string[]
  dtype?: string
  source?: string
}

export interface IRVariable {
  name: string
  description?: string
  sets?: string[]
  domain: VariableDomain
  lower?: number | null
  upper?: number | null
}

export interface IRExpressionTerm {
  coef: string
  var: string
  sum_sets?: string[]
  where?: string
}

export interface IRExpression {
  kind: ExpressionKind
  terms?: IRExpressionTerm[]
  raw_expr?: string
  latex?: string
}

export interface IRConstraint {
  name: string
  expr: string
  scope?: string
  sense: ConstraintSense
  rhs?: string | null
  description?: string
  latex?: string
}

export interface IRModel {
  meta: IRMeta
  problem_type: string
  sense: ObjectiveSense
  sets: IRSet[]
  parameters: IRParameter[]
  variables: IRVariable[]
  objective: IRExpression | null
  constraints: IRConstraint[]
}
