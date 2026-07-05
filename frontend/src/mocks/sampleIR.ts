import type { IRModel } from '../types/ir'

export const SAMPLE_IR_MODEL: IRModel = {
  meta: {
    schema_version: '1.0',
    source: 'facility_location_demo',
    generated_at: new Date().toISOString(),
  },
  problem_type: 'facility_location',
  sense: 'min',
  sets: [
    { name: 'I', description: '需求点集合', index_domain: 'int', members: 'from_instance' },
    { name: 'J', description: '候选设施集合', index_domain: 'int', members: 'from_instance' },
  ],
  parameters: [
    { name: 'd_i', description: '需求量', sets: ['I'], dtype: 'float', source: 'feature_map:demand->d_i' },
    { name: 'f_j', description: '开设固定成本', sets: ['J'], dtype: 'float', source: 'feature_map:fixed_cost->f_j' },
    { name: 'c_ij', description: '单位运输成本', sets: ['I', 'J'], dtype: 'float', source: 'feature_map:cost->c_ij' },
  ],
  variables: [
    { name: 'x_ij', description: '是否将需求点 i 分配给设施 j', sets: ['I', 'J'], domain: 'binary', lower: 0, upper: 1 },
    { name: 'y_j', description: '是否开设设施 j', sets: ['J'], domain: 'binary', lower: 0, upper: 1 },
  ],
  objective: {
    kind: 'linear',
    terms: [
      { coef: 'f_j', var: 'y_j', sum_sets: ['J'], where: '' },
      { coef: 'c_ij * d_i', var: 'x_ij', sum_sets: ['I', 'J'], where: '' },
    ],
    raw_expr: 'sum_{j in J} f_j * y_j + sum_{i in I} sum_{j in J} c_ij * d_i * x_ij',
    latex: '\\sum_{j \\in J} f_{j} \\cdot y_{j} + \\sum_{i \\in I} \\sum_{j \\in J} c_{ij} \\cdot d_{i} \\cdot x_{ij}',
  },
  constraints: [
    {
      name: 'assign_once',
      expr: 'sum_{j in J} x_ij',
      scope: 'forall i in I',
      sense: 'eq',
      rhs: '1',
      description: '每个需求点必须被分配给且仅被一个设施',
      latex: '\\forall i \\in I: \\sum_{j \\in J} x_{ij} = 1',
    },
    {
      name: 'linking',
      expr: 'x_ij',
      scope: 'forall i in I, j in J',
      sense: 'le',
      rhs: 'y_j',
      description: '需求点只能分配给已开设的设施',
      latex: '\\forall i \\in I, j \\in J: x_{ij} \\le y_{j}',
    },
  ],
}
