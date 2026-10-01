import { Menu, Radio } from 'lucide-react'

interface HeaderProps {
  onMenuClick: () => void
}

function Header({ onMenuClick }: HeaderProps) {
  return (
    <header className="topbar">
      <button className="mobile-menu-button" type="button" onClick={onMenuClick} aria-label="Open navigation menu">
        <Menu size={20} aria-hidden="true" />
      </button>
      <div className="breadcrumbs"><span>WORKSPACE</span><span className="breadcrumb-slash">/</span><strong>OVERVIEW</strong></div>
      <div className="environment-chip"><Radio size={14} aria-hidden="true" /><span>LOCAL MOCK ENVIRONMENT</span></div>
    </header>
  )
}

export default Header