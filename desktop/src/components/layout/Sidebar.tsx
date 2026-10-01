import type { ReactNode } from 'react'
import {
  Compass,
  FileText,
  LayoutDashboard,
  Library,
  Play,
  ScrollText,
  Settings,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useApp } from '@/app/AppContext'

export type PageKey = 'dashboard' | 'run' | 'library' | 'reports' | 'discover' | 'logs' | 'settings'

/** Yan menu: tek satir, sade. (Eski surumde her ogede ikinci bir aciklama satiri
 *  vardi; menu kalabalik ve yorucu gorunuyordu.) */
const NAV: { key: PageKey; label: string; icon: ReactNode }[] = [
  { key: 'dashboard', label: 'Panel', icon: <LayoutDashboard className="size-4" /> },
  { key: 'run', label: 'Çalıştır', icon: <Play className="size-4" /> },
  { key: 'discover', label: 'Keşif', icon: <Compass className="size-4" /> },
  { key: 'library', label: 'Kütüphane', icon: <Library className="size-4" /> },
  { key: 'reports', label: 'Çıktılar', icon: <FileText className="size-4" /> },
  { key: 'logs', label: 'Günlük', icon: <ScrollText className="size-4" /> },
  { key: 'settings', label: 'Ayarlar', icon: <Settings className="size-4" /> },
]

export function Sidebar({ page, onNavigate }: { page: PageKey; onNavigate: (page: PageKey) => void }): ReactNode {
  const { job, info, env } = useApp()
  const problems = env.filter((e) => !e.ok).length

  return (
    <nav className="flex w-[188px] shrink-0 flex-col border-r border-border bg-[var(--canvas-2)] px-2 py-2.5">
      <div className="flex flex-col gap-0.5">
        {NAV.map((item) => {
          const active = page === item.key
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              title={item.label}
              className={cn(
                'flex items-center gap-2.5 rounded-[9px] px-2.5 py-[7px] text-left transition-colors',
                active
                  ? 'bg-[var(--surface-2)] text-fg'
                  : 'text-fg-muted hover:bg-[var(--surface-2)] hover:text-fg',
              )}
            >
              <span className={cn('shrink-0 transition-colors', active ? 'text-brand' : 'text-fg-subtle')}>
                {item.icon}
              </span>
              <span className="flex-1 truncate text-[12.5px] font-medium">{item.label}</span>
              {item.key === 'run' && job?.status === 'running' ? (
                <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-brand" />
              ) : null}
              {item.key === 'settings' && problems > 0 ? (
                <span className="num shrink-0 rounded-full bg-warn-soft px-1.5 text-[10.5px] font-semibold text-warn">
                  {problems}
                </span>
              ) : null}
            </button>
          )
        })}
      </div>

      <div className="mt-auto px-2 pt-3 text-[10.5px] text-fg-subtle">
        VideoForge {info?.version ?? '—'}
      </div>
    </nav>
  )
}
