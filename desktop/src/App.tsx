import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { AppProvider, useApp } from '@/app/AppContext'
import { Sidebar, type PageKey } from '@/components/layout/Sidebar'
import { TitleBar } from '@/components/layout/TitleBar'
import { ToastHost } from '@/components/ui/ToastHost'
import { CommandPalette } from '@/components/ui/CommandPalette'
import { Spinner } from '@/components/ui/primitives'
import { DashboardPage } from '@/pages/DashboardPage'
import { RunPage } from '@/pages/RunPage'
import { LibraryPage } from '@/pages/LibraryPage'
import { ReportsPage } from '@/pages/ReportsPage'
import { DiscoverPage } from '@/pages/DiscoverPage'
import { LogsPage } from '@/pages/LogsPage'
import { SettingsPage } from '@/pages/SettingsPage'

/** Ctrl+1..7 kisayollari icin sayfa sirasi. */
const KISAYOL_SAYFALARI: PageKey[] = ['dashboard', 'run', 'discover', 'library', 'reports', 'logs', 'settings']

function Shell(): ReactNode {
  const { ready } = useApp()
  const [page, setPage] = useState<PageKey>('dashboard')
  const [palet, setPalet] = useState(false)

  const navigate = useCallback((next: PageKey) => setPage(next), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const ctrl = e.ctrlKey || e.metaKey
      if (ctrl && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalet((v) => !v)
        return
      }
      if (ctrl && /^[1-7]$/.test(e.key)) {
        const hedef = KISAYOL_SAYFALARI[Number(e.key) - 1]
        if (hedef) {
          e.preventDefault()
          setPage(hedef)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-[12.5px] text-fg-subtle">
        <Spinner /> VideoForge hazırlanıyor...
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <TitleBar onNavigate={navigate} onOpenPalette={() => setPalet(true)} />
      <div className="flex min-h-0 flex-1">
        <Sidebar page={page} onNavigate={navigate} />
        <main className="app-bg min-w-0 flex-1 overflow-y-auto p-4">
          <div className="mx-auto max-w-[1400px]">
            {page === 'dashboard' ? <DashboardPage onNavigate={navigate} /> : null}
            {page === 'run' ? <RunPage onNavigate={navigate} /> : null}
            {page === 'library' ? <LibraryPage /> : null}
            {page === 'reports' ? <ReportsPage /> : null}
            {page === 'discover' ? <DiscoverPage onNavigate={navigate} /> : null}
            {page === 'logs' ? <LogsPage /> : null}
            {page === 'settings' ? <SettingsPage /> : null}
          </div>
        </main>
      </div>
      <CommandPalette open={palet} onClose={() => setPalet(false)} onNavigate={navigate} />
      <ToastHost />
    </div>
  )
}

export default function App(): ReactNode {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
