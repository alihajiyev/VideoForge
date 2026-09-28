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
import { Badge } from '@/components/ui/primitives'

export type PageKey = 'dashboard' | 'run' | 'library' | 'reports' | 'discover' | 'logs' | 'settings'

const NAV: { key: PageKey; label: string; icon: ReactNode; hint: string }[] = [
  { key: 'dashboard', label: 'Panel', icon: <LayoutDashboard className="size-4" />, hint: 'Genel durum' },
  { key: 'run', label: 'Calistir', icon: <Play className="size-4" />, hint: 'Canli islem' },
  { key: 'library', label: 'Kutuphane', icon: <Library className="size-4" />, hint: 'Islenen videolar' },
  { key: 'reports', label: 'Cikti & Rapor', icon: <FileText className="size-4" />, hint: 'SEO + videolar' },
  { key: 'discover', label: 'Kesif', icon: <Compass className="size-4" />, hint: 'Video onerisi' },
  { key: 'logs', label: 'Loglar', icon: <ScrollText className="size-4" />, hint: 'bot_log.txt' },
  { key: 'settings', label: 'Ayarlar', icon: <Settings className="size-4" />, hint: 'Motor + tema' },
]

export function Sidebar({ page, onNavigate }: { page: PageKey; onNavigate: (page: PageKey) => void }): ReactNode {
  const { job, info, env } = useApp()
  const problems = env.filter((e) => !e.ok).length

  return (
    <nav className="flex w-[212px] shrink-0 flex-col border-r border-border bg-[var(--canvas-2)] px-2.5 py-3">
      <div className="flex flex-col gap-0.5">
        {NAV.map((item) => {
          const active = page === item.key
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className={cn(
                'group relative flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left transition-colors',
                active
                  ? 'bg-[var(--surface-2)] text-fg shadow-[inset_0_0_0_1px_var(--border)]'
                  : 'text-fg-muted hover:bg-[var(--surface-2)] hover:text-fg',
              )}
            >
              {active ? <span className="absolute top-1/2 left-0 h-5 w-[3px] -translate-y-1/2 rounded-full bg-brand" /> : null}
              <span className={cn('transition-colors', active ? 'text-brand' : 'text-fg-subtle group-hover:text-fg-muted')}>
                {item.icon}
              </span>
              <span className="flex-1">
                <span className="block text-[12.5px] font-medium">{item.label}</span>
                <span className="block text-[10.5px] text-fg-subtle">{item.hint}</span>
              </span>
              {item.key === 'run' && job?.status === 'running' ? (
                <span className="size-1.5 animate-pulse rounded-full bg-brand" />
              ) : null}
              {item.key === 'settings' && problems > 0 ? <Badge tone="warn">{problems}</Badge> : null}
            </button>
          )
        })}
      </div>

      <div className="mt-auto flex flex-col gap-2 px-1">
        <div className="hairline" />
        <div className="space-y-1 text-[10.5px] text-fg-subtle">
          <div className="flex items-center justify-between">
            <span>surum</span>
            <span className="num text-fg-muted">{info?.version ?? '—'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>electron</span>
            <span className="num text-fg-muted">{info?.electron ?? '—'}</span>
          </div>
        </div>
      </div>
    </nav>
  )
}
