import { ClipboardList } from 'lucide-react'

function EmptyState() {
  return (
    <div className="empty-state">
      <span className="empty-state-icon"><ClipboardList size={20} aria-hidden="true" /></span>
      <p>No test sessions yet</p>
      <span>Your sessions will appear here once created.</span>
    </div>
  )
}

export default EmptyState