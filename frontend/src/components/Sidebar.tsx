import { Bot, ChartNoAxesCombined, ClipboardCheck, LayoutDashboard, Settings2, TestTubeDiagonal, X } from 'lucide-react'

const navigation = [
  { label: 'Dashboard', icon: LayoutDashboard, href: '#dashboard', active: true },
  { label: 'New Test', icon: TestTubeDiagonal, href: '#new-test' },
  { label: 'Test History', icon: ClipboardCheck, href: '#recent-tests' },
  { label: 'Reports', icon: ChartNoAxesCombined, disabled: true },
  { label: 'Settings', icon: Settings2, disabled: true },
]

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

function Sidebar({ isOpen, onClose }: SidebarProps) {
  return (
    <>
      <button className={`sidebar-backdrop${isOpen ? ' is-visible' : ''}`} onClick={onClose} aria-label="Close navigation menu" tabIndex={isOpen ? 0 : -1} />
      <aside className={`sidebar${isOpen ? ' is-open' : ''}`} aria-label="Main navigation">
        <div className="sidebar-top">
          <a className="brand" href="#dashboard" onClick={onClose}>
            <span className="brand-mark"><TestTubeDiagonal size={19} strokeWidth={2.3} aria-hidden="true" /></span>
            <span className="brand-copy"><strong>TestPilot <i>AI</i></strong><small>AI-powered web testing, made simple.</small></span>
          </a>
          <button className="sidebar-close-button" type="button" onClick={onClose} aria-label="Close navigation menu">
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        <div className="nav-caption">WORKSPACE</div>
        <nav className="primary-nav">
          {navigation.map(({ label, icon: Icon, href, active, disabled }) => (
            disabled ? (
              <button className="nav-link is-disabled" type="button" key={label} disabled title={`${label} will be available in a later phase`}>
                <Icon size={18} aria-hidden="true" /><span>{label}</span><span className="nav-soon">SOON</span>
              </button>
            ) : (
              <a className={`nav-link${active ? ' is-active' : ''}`} href={href} key={label} onClick={onClose} aria-current={active ? 'page' : undefined}>
                <Icon size={18} aria-hidden="true" /><span>{label}</span>{active ? <span className="nav-active-dot" /> : null}
              </a>
            )
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="agent-avatar"><Bot size={19} aria-hidden="true" /></div>
          <div className="agent-copy"><strong>AI Testing Agent</strong><span><i className="agent-status-dot" /> v1.0</span></div>
          <span className="agent-ready">READY</span>
        </div>
      </aside>
    </>
  )
}

export default Sidebar