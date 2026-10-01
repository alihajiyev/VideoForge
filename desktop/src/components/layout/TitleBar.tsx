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
    <header className="drag-region relative z-50 flex h-10 shrink-0 items-center justify-between border-b border-border bg-[var(--canvas-2)] pl-3">
      <div className="flex items-center gap-2.5">
        <BrandMark />
        <span className="text-[12.5px] font-semibold tracking-[-0.01em] text-fg">VideoForge</span>
        <button
          onClick={() => onOpenPalette?.()}
          title="Komut paleti (Ctrl+K)"
          className="no-drag hidden items-center gap-1.5 rounded-[8px] border border-border bg-[var(--surface-2)] px-2 py-[3px] text-[11px] text-fg-subtle transition-colors hover:border-border-strong hover:text-fg sm:flex"
        >
          <Search className="size-3" />
          Ara
          <span className="rounded-[4px] border border-border px-1 text-[9.5px]">Ctrl K</span>
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

      <div className="no-drag flex h-full items-center">
        <IconButton onClick={() => void refreshEnv()} title="Ortamı yeniden kontrol et" className="h-full w-10 rounded-none">
          <RefreshCw className={cn('size-3.5', envLoading && 'animate-spin')} />
        </IconButton>
        <IconButton
          onClick={cycleMode}
          title={mode === 'dark' ? 'Aydınlık tema' : 'Karanlık tema'}
          className="h-full w-10 rounded-none"
        >
          {mode === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </IconButton>

        {isDesktop ? (
          <>
            <span className="mx-1 h-5 w-px bg-border" />
            <IconButton onClick={() => void api.winMinimize()} title="Küçült" className="h-full w-11 rounded-none">
              <Minus className="size-4" />
            </IconButton>
            <IconButton
              onClick={() => void api.winMaximize()}
              title={maximized ? 'Geri yükle' : 'Büyüt'}
              className="h-full w-11 rounded-none"
            >
              {maximized ? <Square className="size-3.5" /> : <Maximize2 className="size-4" />}
            </IconButton>
            <IconButton
              onClick={() => void api.winClose()}
              title="Kapat"
              className="h-full w-11 rounded-none hover:bg-[#e11d48] hover:text-white"
            >
              <X className="size-4" />
            </IconButton>
          </>
        ) : null}
      </div>
    </header>
  )
}
