import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  LayoutDashboard,
  Moon,
  Play,
  RefreshCw,
  Search,
  Settings,
  Square,
  Sun,
  Trash2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useApp } from '@/app/AppContext'
import type { PageKey } from '@/components/layout/Sidebar'

interface Komut {
  id: string
  etiket: string
  ipucu?: string
  ikon: ReactNode
  calistir: () => void
}

const SAYFALAR: { key: PageKey; etiket: string; ikon: ReactNode }[] = [
  { key: 'dashboard', etiket: 'Ana Sayfa', ikon: <LayoutDashboard className="size-4" /> },
  { key: 'run', etiket: 'Çalıştır', ikon: <Play className="size-4" /> },
  { key: 'settings', etiket: 'Ayarlar', ikon: <Settings className="size-4" /> },
]

/**
 * Komut paleti (Ctrl+K): sayfa gecisi ve sik kullanilan eylemler icin hizli
 * arama. Klavyeyle tamamen kullanilabilir (ok tuslari + Enter + Esc).
 */
export function CommandPalette({
  open,
  onClose,
  onNavigate,
}: {
  open: boolean
  onClose: () => void
  onNavigate: (page: PageKey) => void
}): ReactNode {
  const { job, cancelJob, setMode, settings, checkUpdate, queueClear, pushToast } = useApp()
  const [query, setQuery] = useState('')
  const [aktif, setAktif] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const komutlar = useMemo<Komut[]>(() => {
    const liste: Komut[] = SAYFALAR.map((s) => ({
      id: `git-${s.key}`,
      etiket: `${s.etiket} sayfasına git`,
      ipucu: 'Gezinme',
      ikon: s.ikon,
      calistir: () => onNavigate(s.key),
    }))
    const karanlik = (settings?.mode ?? 'dark') !== 'light'
    liste.push({
      id: 'tema',
      etiket: karanlik ? 'Aydınlık temaya geç' : 'Karanlık temaya geç',
      ipucu: 'Görünüm',
      ikon: karanlik ? <Sun className="size-4" /> : <Moon className="size-4" />,
      calistir: () => void setMode(karanlik ? 'light' : 'dark'),
    })
    liste.push({
      id: 'guncelleme',
      etiket: 'Güncellemeleri kontrol et',
      ipucu: 'Sürüm',
      ikon: <RefreshCw className="size-4" />,
      calistir: () => {
        void checkUpdate()
        pushToast({ tone: 'info', title: 'Güncelleme kontrol ediliyor', message: 'Son sürüm sorgulanıyor...' })
      },
    })
    if (job?.status === 'running') {
      liste.push({
        id: 'durdur',
        etiket: 'Çalışan işlemi durdur',
        ipucu: 'İşlem',
        ikon: <Square className="size-4" />,
        calistir: () => void cancelJob(),
      })
    }
    liste.push({
      id: 'kuyruk-temizle',
      etiket: 'Kuyruğu temizle',
      ipucu: 'İşlem',
      ikon: <Trash2 className="size-4" />,
      calistir: () => void queueClear(),
    })
    return liste
  }, [job?.status, settings?.mode, onNavigate, setMode, checkUpdate, cancelJob, queueClear, pushToast])

  const filtreli = useMemo(() => {
    const q = query.trim().toLocaleLowerCase('tr')
    if (!q) return komutlar
    return komutlar.filter((k) => `${k.etiket} ${k.ipucu ?? ''}`.toLocaleLowerCase('tr').includes(q))
  }, [komutlar, query])

  useEffect(() => {
    if (!open) return
    setQuery('')
    setAktif(0)
    const t = window.setTimeout(() => inputRef.current?.focus(), 20)
    return () => window.clearTimeout(t)
  }, [open])

  useEffect(() => {
    setAktif(0)
  }, [query])

  if (!open) return null

  const calistir = (k: Komut | undefined): void => {
    if (!k) return
    k.calistir()
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-[var(--overlay)] px-4 pt-[12vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Komut paleti"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[560px] overflow-hidden rounded-[12px] border border-border bg-[var(--surface)] shadow-[var(--shadow-pop)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-border px-3.5 py-2.5">
          <Search className="size-4 shrink-0 text-fg-subtle" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setAktif((a) => Math.min(filtreli.length - 1, a + 1))
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                setAktif((a) => Math.max(0, a - 1))
              } else if (e.key === 'Enter') {
                e.preventDefault()
                calistir(filtreli[aktif])
              } else if (e.key === 'Escape') {
                e.preventDefault()
                onClose()
              }
            }}
            placeholder="Komut ara... (sayfa, tema, güncelleme)"
            className="h-7 w-full bg-transparent text-[13px] text-fg placeholder:text-fg-subtle focus:outline-none"
            aria-label="Komut ara"
          />
        </div>
        <div className="max-h-[46vh] overflow-y-auto py-1.5">
          {filtreli.length === 0 ? (
            <p className="px-3.5 py-6 text-center text-[12px] text-fg-subtle">Sonuç yok</p>
          ) : (
            filtreli.map((k, i) => (
              <button
                key={k.id}
                onMouseEnter={() => setAktif(i)}
                onClick={() => calistir(k)}
                className={cn(
                  'flex w-full items-center gap-3 px-3.5 py-2 text-left transition-colors',
                  // YouTube onerisi gibi: secili satir notr gri dolgu + kirmizi ikon.
                  i === aktif ? 'bg-[var(--surface-2)]' : 'hover:bg-[var(--surface-2)]',
                )}
              >
                <span className={cn('shrink-0', i === aktif ? 'text-brand' : 'text-fg-subtle')}>{k.ikon}</span>
                <span className="flex-1 truncate text-[12.5px] text-fg">{k.etiket}</span>
                {k.ipucu ? <span className="shrink-0 text-[10.5px] text-fg-subtle">{k.ipucu}</span> : null}
              </button>
            ))
          )}
        </div>
        <div className="flex items-center gap-3 border-t border-border px-3.5 py-2 text-[10.5px] text-fg-subtle">
          <span>↑↓ gez</span>
          <span>Enter çalıştır</span>
          <span>Esc kapat</span>
        </div>
      </div>
    </div>
  )
}
