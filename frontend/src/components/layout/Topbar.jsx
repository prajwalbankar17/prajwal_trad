import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { Bell, LogOut, Menu, User } from 'lucide-react'
import { api } from '../../api/client'
import { useAuthStore } from '../../store/auth'
import { Badge } from '../ui'
import { timeIST } from '../../lib/format'

const STATUS_TONE = {
  OPEN: 'profit',
  PRE_OPEN: 'warn',
  POST_CLOSE: 'warn',
  CLOSED: 'neutral',
  HOLIDAY: 'neutral',
}

export function Topbar({ onMenuClick }) {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await api.get('/health')).data,
    refetchInterval: 30_000,
  })

  const { data: notifications } = useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: async () =>
      (await api.get('/notifications', { params: { unread_only: true, page_size: 1 } })).data,
    refetchInterval: 60_000,
  })

  const status = health?.market_status ?? 'CLOSED'
  const unread = notifications?.total ?? 0

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-base-700 bg-base-850/95 px-4 backdrop-blur">
      <button
        type="button"
        onClick={onMenuClick}
        className="btn-ghost p-1.5 lg:hidden"
        aria-label="Open navigation"
      >
        <Menu size={16} />
      </button>

      <div className="flex items-center gap-2">
        <Badge tone={STATUS_TONE[status] ?? 'neutral'}>
          <span
            className={clsx(
              'h-1.5 w-1.5 rounded-full',
              status === 'OPEN' ? 'bg-profit animate-pulse' : 'bg-current',
            )}
          />
          {status.replace('_', ' ')}
        </Badge>
        <span className="hidden text-2xs text-ink-faint tnum sm:inline">
          {timeIST(health?.time_ist)} IST
        </span>
      </div>

      {/* Feed state is never implied - if it is not connected, it says so. */}
      <Badge tone="neutral" className="hidden md:inline-flex">
        Historical data · no live feed
      </Badge>

      <div className="ml-auto flex items-center gap-2">
        <Link to="/notifications" className="relative btn-ghost p-1.5" aria-label="Notifications">
          <Bell size={15} />
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[9px] font-bold text-white">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </Link>

        <div className="hidden items-center gap-2 rounded-md border border-base-700 bg-base-800 px-2.5 py-1 sm:flex">
          <User size={13} className="text-ink-faint" />
          <div className="leading-tight">
            <p className="text-xs font-medium">{user?.username ?? '—'}</p>
            <p className="text-[10px] text-ink-faint">
              {user?.roles?.map((r) => r.name).join(', ') || 'No role'}
            </p>
          </div>
        </div>

        <button type="button" onClick={logout} className="btn-ghost p-1.5" aria-label="Sign out">
          <LogOut size={15} />
        </button>
      </div>
    </header>
  )
}
