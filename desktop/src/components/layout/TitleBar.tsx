import { useEffect, useState, type ReactNode } from 'react'
import { Maximize2, Minus, Moon, RefreshCw, Square, Sun, X } from 'lucide-react'
import type { PageKey } from './Sidebar'
import { api, isDesktop } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useApp } from '@/app/AppContext'
import { Badge, IconButton } from '@/components/ui/primitives'
import { BrandMark } from './BrandMark'

export function TitleBar({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
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

  return (
    <header className="drag-region relative z-50 flex h-11 shrink-0 items-center justify-between border-b border-border bg-[var(--canvas-2)] pr-0 pl-3">
      <div className="flex items-center gap-2.5">
        <BrandMark />
        <span className="text-[12.5px] font-semibold tracking-[-0.01em] text-fg">
          Video<span className="gradient-text">Forge</span>
        </span>
        <Badge tone="neutral" className="ml-1">
          YouTube Temizleyici &amp; Seslendirici
        </Badge>
        {update?.available ? (
          <button
            onClick={() => onNavigate('settings')}
            title={`Yeni surum hazir: ${update.latest}`}
            className="no-drag ml-1"
          >
            <Badge tone="brand" dot className="animate-pulse-soft cursor-pointer">
              guncelleme: {update.latest}
            </Badge>
          </button>
        ) : null}
        {job?.status === 'running' ? (
          <Badge tone="brand" dot className="animate-pulse-soft ml-1">
            islem suruyor
          </Badge>
        ) : issues.length ? (
          <Badge tone="warn" className="ml-1">
            {issues.length} ortam uyarisi
          </Badge>
        ) : env.length ? (
          <Badge tone="success" className="ml-1">
            ortam hazir
          </Badge>
        ) : null}
      </div>

      <div className="no-drag flex h-full items-center">
        <IconButton onClick={() => void refreshEnv()} title="Ortami yeniden kontrol et" className="h-full w-10 rounded-none">
          <RefreshCw className={cn('size-3.5', envLoading && 'animate-spin')} />
        </IconButton>
        <IconButton onClick={cycleMode} title={mode === 'dark' ? 'Aydinlik tema' : 'Karanlik tema'} className="h-full w-10 rounded-none">
          {mode === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </IconButton>

        {isDesktop ? (
          <>
            <span className="mx-1 h-5 w-px bg-border" />
            <IconButton onClick={() => void api.winMinimize()} title="Kucult" className="h-full w-11 rounded-none">
              <Minus className="size-4" />
            </IconButton>
            <IconButton onClick={() => void api.winMaximize()} title={maximized ? 'Geri yukle' : 'Buyut'} className="h-full w-11 rounded-none">
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
