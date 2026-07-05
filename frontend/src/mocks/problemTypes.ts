import type { ProblemTypeOption, ProblemTypeDetail } from '../types/session'

export const MOCK_PROBLEM_TYPES: ProblemTypeOption[] = [
  {
    value: 'facility_location',
    label: '设施选址',
    description: '在候选设施点中选择开设哪些设施，并将客户分配给已开设设施，最小化总成本。',
  },
  {
    value: 'transportation',
    label: '运输问题',
    description: '在多个供应点与需求点之间规划运输方案，最小化总运输成本。',
  },
  {
    value: 'assignment',
    label: '分配问题',
    description: '将任务或资源一对一/一对多分配给代理或机器，最小化总分配成本。',
  },
  {
    value: 'scheduling',
    label: '调度问题',
    description: '在机器或资源上安排作业顺序，满足加工时间约束并优化完成时间或成本。',
  },
  {
    value: 'inventory',
    label: '库存优化',
    description: '在多周期计划内决定订货量与库存水平，平衡订货、持有和采购成本。',
  },
  {
    value: 'network_flow',
    label: '网络流',
    description: '在网络节点与弧上规划流量，满足供需平衡与容量约束，最小化总流动成本。',
  },
  {
    value: 'knapsack',
    label: '背包问题',
    description: '在容量限制下选择物品子集，最大化总价值。',
  },
]

export const MOCK_PROBLEM_TYPE_DETAILS: Record<string, ProblemTypeDetail> = {
  facility_location: {
    value: 'facility_location',
    label: '设施选址',
    description: 'Uncapacitated facility location: choose which facilities to open and assign each customer to exactly one open facility.',
    sets: {
      I: 'set of customers / demand points',
      J: 'set of candidate facility locations',
    },
    parameters: {
      d_i: 'demand of customer i',
      f_j: 'fixed cost of opening facility j',
      c_ij: 'transportation cost from facility j to customer i',
    },
    variables: [
      { name: 'x_ij', kind: 'binary', description: '1 if customer i is served by facility j, else 0', indices: ['I', 'J'] },
      { name: 'y_j', kind: 'binary', description: '1 if facility j is opened, else 0', indices: ['J'] },
    ],
    constraints: [
      { name: 'assignment', expression: 'sum_{j in J} x_ij', sense: '==', rhs: '1', scope: 'for all i in I' },
      { name: 'linking', expression: 'x_ij', sense: '<=', rhs: 'y_j', scope: 'for all i in I, j in J' },
    ],
    objective: {
      sense: 'minimize',
      expression: 'sum_{j in J} f_j * y_j + sum_{i in I} sum_{j in J} c_ij * d_i * x_ij',
    },
    tags: ['location', 'assignment', 'binary', 'milp'],
  },
  transportation: {
    value: 'transportation',
    label: '运输问题',
    description: 'Classical transportation problem.',
    sets: {
      I: 'set of supply nodes',
      J: 'set of demand nodes',
    },
    parameters: {
      supply_i: 'supply amount at node i',
      demand_j: 'demand amount at node j',
      cost_ij: 'unit transportation cost from i to j',
    },
    variables: [
      { name: 'x_ij', kind: 'continuous', description: 'amount shipped from i to j', indices: ['I', 'J'] },
    ],
    constraints: [
      { name: 'supply', expression: 'sum_{j in J} x_ij', sense: '<=', rhs: 'supply_i', scope: 'for all i in I' },
      { name: 'demand', expression: 'sum_{i in I} x_ij', sense: '==', rhs: 'demand_j', scope: 'for all j in J' },
    ],
    objective: {
      sense: 'minimize',
      expression: 'sum_{i in I} sum_{j in J} cost_ij * x_ij',
    },
    tags: ['network', 'linear'],
  },
  knapsack: {
    value: 'knapsack',
    label: '背包问题',
    description: 'Select items to maximize total value without exceeding capacity.',
    sets: {
      I: 'set of items',
    },
    parameters: {
      value_i: 'value of item i',
      weight_i: 'weight of item i',
      C: 'knapsack capacity',
    },
    variables: [
      { name: 'x_i', kind: 'binary', description: '1 if item i is selected', indices: ['I'] },
    ],
    constraints: [
      { name: 'capacity', expression: 'sum_{i in I} weight_i * x_i', sense: '<=', rhs: 'C', scope: 'for all' },
    ],
    objective: {
      sense: 'maximize',
      expression: 'sum_{i in I} value_i * x_i',
    },
    tags: ['binary', 'combinatorial'],
  },
}
