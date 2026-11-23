import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import clsx from 'clsx'
import { ChevronDown, TrendingUp } from 'lucide-react'
import { NAVIGATION } from './navigation'
import { useAuthStore } from '../../store/auth'
import { Badge } from '../ui'

function hasAccess(item, user, permissions) {
  if (!item.permission) return true
  if (user?.is_superuser) return true
  return permissions.includes(item.permission)
}

export function Sidebar({ open, onNavigate }) {
  const { pathname } = useLocation()
  const user = useAuthStore((s) => s.user)
  const permissions = useAuthStore((s) => s.permissions)

  const [expanded, setExpanded] = useState(() => {
    const initial = {}
    NAVIGATION.forEach((item) => {
      if (item.children?.some((c) => pathname.startsWith(c.to))) initial[item.label] = true
    })
    return initial
  })

  const visible = NAVIGATION.filter((item) => hasAccess(item, user, permissions))

  return (
    <aside
      className={clsx(
        'fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-base-700 bg-base-850',
        'flex flex-col transition-transform lg:translate-x-0 lg:static',
        open ? 'translate-x-0' : '-translate-x-full',
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-base-700 px-4 shrink-0">
        <div className="flex h-7 w-7 items-center justify-center rounded bg-accent/15">
          <TrendingUp size={15} className="text-accent" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-tight truncate">Prajwal</p>
          <p className="text-2xs text-ink-faint leading-tight">Trading Platform</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Main navigation">
        {visible.map((item) => {
          const Icon = item.icon
          if (item.children) {
            const isOpen = expanded[item.label]
            const active = item.children.some((c) => pathname.startsWith(c.to))
            return (
              <div key={item.label} className="mb-0.5">
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((prev) => ({ ...prev, [item.label]: !prev[item.label] }))
                  }
                  aria-expanded={!!isOpen}
                  className={clsx(
                    'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors',
                    active ? 'text-ink' : 'text-ink-muted hover:text-ink hover:bg-base-800',
                  )}
                >
                  <Icon size={15} className="shrink-0" />
                  <span className="flex-1 text-left truncate">{item.label}</span>
                  {item.blocked && (
                    <Badge tone="warn" className="px-1 py-0">
                      {item.blocked}
                    </Badge>
                  )}
                  <ChevronDown
                    size={13}
                    className={clsx('shrink-0 transition-transform', isOpen && 'rotate-180')}
                  />
                </button>
                {isOpen && (
                  <div className="ml-[21px] border-l border-base-700 pl-2.5 mt-0.5 space-y-0.5">
                    {item.children.map((child) => (
                      <NavLink
                        key={child.to}
                        to={child.to}
                        end
                        onClick={onNavigate}
                        className={({ isActive }) =>
                          clsx(
                            'block rounded-md px-2.5 py-1.5 text-[13px] transition-colors',
                            isActive
                              ? 'bg-accent-soft text-accent font-medium'
                              : 'text-ink-muted hover:text-ink hover:bg-base-800',
                          )
                        }
                      >
                        {child.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            )
          }
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                clsx(
                  'mb-0.5 flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-accent-soft text-accent font-medium'
                    : 'text-ink-muted hover:text-ink hover:bg-base-800',
                )
              }
            >
              <Icon size={15} className="shrink-0" />
              <span className="truncate">{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      <div className="border-t border-base-700 px-3 py-2.5 shrink-0">
        <Badge tone="warn" className="w-full justify-center py-1">
          Paper trading · live orders off
        </Badge>
      </div>
    </aside>
  )
}
