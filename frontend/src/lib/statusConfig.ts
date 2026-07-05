export const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  idle: { label: '等待上传', color: 'bg-slate-400' },
  created: { label: '已创建', color: 'bg-blue-500' },
  awaiting_input: { label: '等待输入', color: 'bg-amber-500' },
  success: { label: '已完成', color: 'bg-green-500' },
  error: { label: '出错', color: 'bg-red-500' },
}
