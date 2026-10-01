import { useMemo, useState, type ReactNode } from 'react'
import { Database, RefreshCw, Search, Sparkles, Trash2 } from 'lucide-react'
import { api, unwrap } from '@/lib/api'
import { useResource } from '@/lib/hooks'
import { useApp } from '@/app/AppContext'
import { cn, formatDateTime } from '@/lib/utils'
import { Badge, Button, EmptyState, Input, Panel, SectionTitle, Spinner } from '@/components/ui/primitives'

export function LibraryPage(): ReactNode {
  const { pushToast, job } = useApp()
  const [tab, setTab] = useState<'videos' | 'oneriler'>('videos')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const library = useResource(() => unwrap(api.libraryList()), [job?.endedAt])

  const videos = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = library.data?.videos ?? []
    return q ? list.filter((v) => v.link.toLowerCase().includes(q)) : list
  }, [library.data, query])

  const oneriler = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = library.data?.oneriler ?? []
    const filtered = q ? list.filter((o) => `${o.video_id} ${o.tip} ${o.kanal}`.toLowerCase().includes(q)) : list
    return [...filtered].sort((a, b) => b.skor - a.skor)
  }, [library.data, query])

  const forget = async (link: string): Promise<void> => {
    setBusy(link)
    try {
      const res = await unwrap(api.libraryForget(link))
      if (res.ok) {
        pushToast({ tone: 'success', title: 'Kayıt silindi', message: `${res.deleted ?? 0} kayıt kaldırıldı` })
        library.reload()
      } else {
        pushToast({ tone: 'error', title: 'Silinemedi', message: res.error })
      }
    } catch (err) {
      pushToast({ tone: 'error', title: 'Silinemedi', message: String(err) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-3.5">
      <Panel className="p-4">
        <SectionTitle
          title="Kütüphane"
          subtitle="bot.db içeriği: işlenen linkler ve keşif puanları"
          icon={<Database className="size-4" />}
          right={
            <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', library.loading && 'animate-spin')} />} onClick={() => library.reload()}>
              Yenile
            </Button>
          }
        />
        {library.data && !library.data.ok ? (
          <p className="mt-3 rounded-[10px] border border-[color-mix(in_oklab,var(--warn)_30%,transparent)] bg-warn-soft px-3 py-2 text-[12px] text-warn">
            {library.data.error ?? 'bot.db okunamadı'}
          </p>
        ) : null}

        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            {(['videos', 'oneriler'] as const).map((key) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={cn(
                  'rounded-[8px] px-2.5 py-1.5 text-[12px] font-medium transition-colors',
                  tab === key ? 'bg-brand-soft text-brand' : 'text-fg-subtle hover:bg-[var(--surface-2)] hover:text-fg-muted',
                )}
              >
                {key === 'videos' ? `İşlenen videolar (${library.data?.counts.videos ?? 0})` : `Keşif önerileri (${library.data?.counts.oneriler ?? 0})`}
              </button>
            ))}
          </div>
          <div className="relative ml-auto w-64">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-fg-subtle" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ara..." className="h-8 pl-8 text-[12px]" />
          </div>
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        {library.loading && !library.data ? (
          <div className="flex items-center justify-center gap-2 py-14 text-[12px] text-fg-subtle">
            <Spinner /> bot.db okunuyor...
          </div>
        ) : tab === 'videos' ? (
          videos.length === 0 ? (
            <EmptyState icon={<Database className="size-6" />} title="Kayıtlı video yok" message="İşlenen her link bot.db'ye yazılır; aynı link tekrar işlenmez." />
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border text-[11px] tracking-wide text-fg-subtle uppercase">
                  <th className="px-4 py-2 font-medium">Video ID / link</th>
                  <th className="px-4 py-2 font-medium">Kayıt zamanı</th>
                  <th className="px-4 py-2 font-medium">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {videos.slice(0, 300).map((v) => (
                  <tr key={v.id} className="border-b border-border/60 last:border-0 hover:bg-[var(--surface-2)]">
                    <td className="px-4 py-2 font-mono text-[11.5px] text-fg">{v.link}</td>
                    <td className="num px-4 py-2 text-[11.5px] text-fg-muted">{formatDateTime(v.created_at)}</td>
                    <td className="px-4 py-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy === v.link}
                        icon={<Trash2 className="size-3.5" />}
                        onClick={() => void forget(v.link)}
                      >
                        Kaydı sil
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : oneriler.length === 0 ? (
          <EmptyState
            icon={<Sparkles className="size-6" />}
            title="Keşif önerisi yok"
            message="Keşif modülü çalıştığında bulunan videolar burada puanlarıyla listelenir."
          />
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border text-[11px] tracking-wide text-fg-subtle uppercase">
                <th className="px-4 py-2 font-medium">Video ID</th>
                <th className="px-4 py-2 font-medium">Puan</th>
                <th className="px-4 py-2 font-medium">Sınıf</th>
                <th className="px-4 py-2 font-medium">Kanal</th>
                <th className="px-4 py-2 font-medium">Tarih</th>
              </tr>
            </thead>
            <tbody>
              {oneriler.slice(0, 300).map((o) => (
                <tr key={`${o.video_id}-${o.kanal}`} className="border-b border-border/60 last:border-0 hover:bg-[var(--surface-2)]">
                  <td className="px-4 py-2 font-mono text-[11.5px] text-fg">{o.video_id}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <span className="num text-[12px] font-semibold text-fg">{o.skor.toFixed(1)}</span>
                      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--surface-3)]">
                        <span
                          className={cn('block h-full rounded-full', o.skor >= 6 ? 'bg-success' : o.skor >= 4 ? 'bg-warn' : 'bg-danger')}
                          style={{ width: `${Math.min(100, (o.skor / 10) * 100)}%` }}
                        />
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2">                      <Badge tone={o.skor >= 6 ? 'success' : o.skor >= 4 ? 'warn' : 'danger'}>{o.tip || (o.skor >= 6 ? 'KAZANAN' : o.skor >= 4 ? 'ORTA' : 'ÇÖP')}</Badge>
                  </td>
                  <td className="px-4 py-2 text-[11.5px] text-fg-muted">kanal {o.kanal}</td>
                  <td className="num px-4 py-2 text-[11.5px] text-fg-muted">{formatDateTime(o.tarih)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  )
}
