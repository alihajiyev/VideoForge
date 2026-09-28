import { useState, type ReactNode } from 'react'
import { AppProvider, useApp } from '@/app/AppContext'
import { Sidebar, type PageKey } from '@/components/layout/Sidebar'
import { TitleBar } from '@/components/layout/TitleBar'
import { ToastHost } from '@/components/ui/ToastHost'
import { Spinner } from '@/components/ui/primitives'
import { DashboardPage } from '@/pages/DashboardPage'
import { RunPage } from '@/pages/RunPage'
import { LibraryPage } from '@/pages/LibraryPage'
import { ReportsPage } from '@/pages/ReportsPage'
import { DiscoverPage } from '@/pages/DiscoverPage'
import { LogsPage } from '@/pages/LogsPage'
import { SettingsPage } from '@/pages/SettingsPage'

function Shell(): ReactNode {
  const { ready } = useApp()
  const [page, setPage] = useState<PageKey>('dashboard')

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-[12.5px] text-fg-subtle">
        <Spinner /> VideoForge hazirlaniyor...
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <TitleBar onNavigate={setPage} />
      <div className="flex min-h-0 flex-1">
        <Sidebar page={page} onNavigate={setPage} />
        <main className="app-bg min-w-0 flex-1 overflow-y-auto p-4">
          <div className="mx-auto max-w-[1400px]">
            {page === 'dashboard' ? <DashboardPage onNavigate={setPage} /> : null}
            {page === 'run' ? <RunPage onNavigate={setPage} /> : null}
            {page === 'library' ? <LibraryPage /> : null}
            {page === 'reports' ? <ReportsPage /> : null}
            {page === 'discover' ? <DiscoverPage onNavigate={setPage} /> : null}
            {page === 'logs' ? <LogsPage /> : null}
            {page === 'settings' ? <SettingsPage /> : null}
          </div>
        </main>
      </div>
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
