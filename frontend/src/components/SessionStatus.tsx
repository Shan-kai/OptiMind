import { STATUS_CONFIG } from '../lib/statusConfig'

interface SessionStatusProps {
  status: string
}

export default function SessionStatus({ status }: SessionStatusProps) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.idle

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={`h-2 w-2 rounded-full ${config.color}`}></span>
      <span className="font-medium text-slate-600">{config.label}</span>
    </div>
  )
}
