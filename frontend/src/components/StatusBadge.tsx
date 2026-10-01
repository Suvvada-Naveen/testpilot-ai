import { CircleCheck, CircleDashed, CircleX, LoaderCircle } from 'lucide-react'
import type { TestStatus } from '../types/test'

const statusIcons = {
  Completed: CircleCheck,
  Running: LoaderCircle,
  Failed: CircleX,
  Pending: CircleDashed,
}

interface StatusBadgeProps {
  status: TestStatus
}

function StatusBadge({ status }: StatusBadgeProps) {
  const Icon = statusIcons[status]

  return (
    <span className={`status-badge status-${status.toLowerCase().replace(' ', '-')}`}>
      <Icon size={14} aria-hidden="true" className={status === 'Running' ? 'spin' : undefined} />
      {status}
    </span>
  )
}

export default StatusBadge