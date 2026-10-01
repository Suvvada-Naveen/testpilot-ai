import { ArrowUpRight, ChevronRight } from 'lucide-react'
import type { RecentTest } from '../types/test'
import EmptyState from './EmptyState'
import StatusBadge from './StatusBadge'

interface RecentTestsProps {
  tests: RecentTest[]
  isLoading: boolean
  error: string | null
  onRetry: () => void
}

function RecentTests({ tests, isLoading, error, onRetry }: RecentTestsProps) {
  return (
    <section className="panel recent-panel" id="recent-tests" aria-labelledby="recent-tests-title">
      <div className="panel-heading recent-heading">
        <div>
          <span className="section-kicker">SESSION LOG</span>
          <h2 id="recent-tests-title">Recent Tests</h2>
        </div>
        <span className="test-count">{String(tests.length).padStart(2, '0')} sessions</span>
      </div>

      {isLoading ? (
        <div className="empty-state" role="status"><p>Loading recent sessions...</p></div>
      ) : error ? (
        <div className="empty-state" role="status">
          <p>{error}</p>
          <button className="history-link" type="button" onClick={onRetry}>Retry loading sessions</button>
        </div>
      ) : tests.length === 0 ? <EmptyState /> : (
        <>
          <div className="recent-columns" aria-hidden="true">
            <span>WEBSITE</span><span>TEST PLAN</span><span>MODE</span><span>STATUS</span><span>DATE</span>
          </div>
          <ul className="recent-list">
            {tests.map((test) => (
              <li className="recent-row" key={test.id}>
                <div className="test-website">
                  <span className="website-mark" aria-hidden="true">{test.domain.charAt(0).toUpperCase()}</span>
                  <span className="website-details"><strong>{test.domain}</strong><small>{test.id}</small></span>
                </div>
                <span className="test-plan" title={test.title}>{test.title}</span>
                <span className="test-mode-text">{test.mode}</span>
                <span className="test-status"><StatusBadge status={test.status} /></span>
                <span className="test-date">{test.dateLabel}</span>
                <ChevronRight className="row-chevron" size={16} aria-hidden="true" />
              </li>
            ))}
          </ul>
          <a className="history-link" href="#recent-tests">View all sessions <ArrowUpRight size={15} aria-hidden="true" /></a>
        </>
      )}
    </section>
  )
}

export default RecentTests