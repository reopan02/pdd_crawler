import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/cookies', label: 'Cookie 管理', icon: '🍪' },
  { to: '/crawl', label: '批量采集', icon: '📡' },
  { to: '/data', label: '数据管理', icon: '🗃️' },
]

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-mark">
            <div className="logo-icon">⬡</div>
            <div>
              <div>PDD Crawler</div>
              <div className="logo-sub">v0.2.0 · 数据采集</div>
            </div>
          </div>
        </div>
        <nav className="nav-section">
          <div className="nav-label">功能模块</div>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <span style={{ fontSize: 16 }}>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="status-dot" />
          SYSTEM ONLINE
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  )
}
