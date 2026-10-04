import type { ReactNode } from 'react'
import { LayoutDashboard, Play, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useApp } from '@/app/AppContext'

/** Minimalist surum: yalnizca 3 ozellik (Ana Sayfa karti) + Calistir + Ayarlar. */
export type PageKey = 'dashboard' | 'run' | 'settings'

const NAV: { key: PageKey; label: string; icon: ReactNode }[] = [
  { key: 'dashboard', label: 'Ana Sayfa', icon: <LayoutDashboard className="size-[22px]" /> },
  { key: 'run', label: 'Çalıştır', icon: <Play className="size-[22px]" /> },
  { key: 'settings', label: 'Ayarlar', icon: <Settings className="size-[22px]" /> },
]

/**
 * YouTube tarzi sol menu: ayri kenarlik yok (zemin sayfayla ayni), satirlar
 * 40px yuksekliginde ve hover/aktif durumda #272727 dolgusu alir.
 */
export function Sidebar({ page, onNavigate }: { page: PageKey; onNavigate: (page: PageKey) => void }): ReactNode {
  const { job, info, env } = useApp()
  const problems = env.filter((e) => !e.ok).length

  return (
    <nav className="flex w-[236px] shrink-0 flex-col gap-0.5 overflow-y-auto bg-[var(--canvas)] px-3 py-3">
      {NAV.map((item) => {
        const active = page === item.key
        return (
          <button
            key={item.key}
            onClick={() => onNavigate(item.key)}
            title={item.label}
            className={cn(
              'flex h-10 items-center gap-5 rounded-[10px] px-3 text-left transition-colors',
              active
                ? 'bg-[var(--surface-3)] text-fg'
                : 'text-fg-muted hover:bg-[var(--surface-3)] hover:text-fg',
            )}
          >
            <span className={cn('shrink-0', active ? 'text-brand' : 'text-fg-muted')}>{item.icon}</span>
            <span className={cn('flex-1 truncate text-[14px]', active ? 'font-semibold' : 'font-normal')}>
              {item.label}
            </span>
            {item.key === 'run' && job?.status === 'running' ? (
              <span className="size-2 shrink-0 animate-pulse-soft rounded-full bg-brand" />
            ) : null}
            {item.key === 'settings' && problems > 0 ? (
              <span className="num shrink-0 rounded-full bg-warn-soft px-2 text-[11px] font-semibold text-warn">
                {problems}
              </span>
            ) : null}
          </button>
        )
      })}

      <div className="mt-auto px-3 pt-4 text-[11.5px] text-fg-subtle">VideoForge {info?.version ?? '—'}</div>
    </nav>
  )
}
