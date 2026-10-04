import { useEffect, useState, type ReactNode } from 'react'
import { Maximize2, Minus, Moon, RefreshCw, Search, Square, Sun, X } from 'lucide-react'
import type { PageKey } from './Sidebar'
import { api, isDesktop } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useApp } from '@/app/AppContext'
import { Badge, IconButton } from '@/components/ui/primitives'
import { BrandMark } from './BrandMark'

export function TitleBar({
  onNavigate,
  onOpenPalette,
}: {
  onNavigate: (page: PageKey) => void
  onOpenPalette?: () => void
}): ReactNode {
  const { settings, setMode, env, envLoading, refreshEnv, job, update } = useApp()
  const [maximized, setMaximized] = useState(false)
  const mode = settings?.mode ?? 'dark'

  useEffect(() => {
    if (!isDesktop) return
    // Handler eksik olabilir (orn. onizleme/otomasyon) - arayuzu kilitlemeyelim.
    void api
      .winState()
      .then((s) => setMaximized(s.maximized))
      .catch(() => undefined)
    return api.onWindowState((s) => setMaximized(s.maximized))
  }, [])

  const issues = env.filter((e) => !e.ok && e.id !== 'log' && e.id !== 'db')
  const cycleMode = (): void => {
    void setMode(mode === 'dark' ? 'light' : 'dark')
  }

  // Durum: ayni anda tek bir rozet gosterilir (eskiden ust uste binen rozetler vardi).
  const status = job?.status === 'running'
    ? { tone: 'brand' as const, text: 'işlem sürüyor', pulse: true }
    : issues.length
      ? { tone: 'warn' as const, text: `${issues.length} eksik kurulum`, pulse: false }
      : env.length
        ? { tone: 'success' as const, text: 'ortam hazır', pulse: false }
        : null

  return (
    <header className="drag-region relative z-50 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-[var(--canvas-2)] px-4">
      <div className="flex min-w-0 items-center gap-3">
        <BrandMark size={28} />
        <span className="text-[16px] leading-none font-bold tracking-[-0.045em] text-fg">VideoForge</span>
        <button
          onClick={() => onOpenPalette?.()}
          title="Komut paleti (Ctrl+K)"
          className="no-drag ml-2 hidden h-9 w-[280px] items-center gap-2.5 rounded-full border border-border bg-[var(--canvas)] px-4 text-[13px] text-fg-subtle transition-colors hover:border-border-strong hover:text-fg-muted sm:flex"
        >
          <Search className="size-4 shrink-0" />
          <span className="flex-1 truncate text-left">Kanal, işlem veya ayar ara</span>
          <span className="rounded-[6px] bg-[var(--surface-3)] px-1.5 py-0.5 text-[10px] text-fg-muted">Ctrl K</span>
        </button>
        {update?.available ? (
          <button
            onClick={() => onNavigate('settings')}
            title={`Yeni sürüm hazır: ${update.latest}`}
            className="no-drag"
          >
            <Badge tone="brand" dot className="cursor-pointer">
              güncelleme: {update.latest}
            </Badge>
          </button>
        ) : status ? (
          <Badge tone={status.tone} dot={status.pulse} className={cn(status.pulse && 'animate-pulse-soft')}>
            {status.text}
          </Badge>
        ) : null}
      </div>

      <div className="no-drag flex h-full shrink-0 items-center">
        <IconButton onClick={() => void refreshEnv()} title="Ortamı yeniden kontrol et" className="h-full w-11 rounded-none">
          <RefreshCw className={cn('size-3.5', envLoading && 'animate-spin')} />
        </IconButton>
        <IconButton
          onClick={cycleMode}
          title={mode === 'dark' ? 'Aydınlık tema' : 'Karanlık tema'}
          className="h-full w-11 rounded-none"
        >
          {mode === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </IconButton>

        {isDesktop ? (
          <>
            <span className="mx-1 h-5 w-px bg-border" />
            <IconButton onClick={() => void api.winMinimize()} title="Küçült" className="h-full w-12 rounded-none">
              <Minus className="size-4" />
            </IconButton>
            <IconButton
              onClick={() => void api.winMaximize()}
              title={maximized ? 'Geri yükle' : 'Büyüt'}
              className="h-full w-12 rounded-none"
            >
              {maximized ? <Square className="size-3.5" /> : <Maximize2 className="size-4" />}
            </IconButton>
            <IconButton
              onClick={() => void api.winClose()}
              title="Kapat"
              className="h-full w-12 rounded-none hover:bg-brand hover:text-white"
            >
              <X className="size-4" />
            </IconButton>
          </>
        ) : null}
      </div>
    </header>
  )
}
