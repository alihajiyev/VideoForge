import { useState, type ReactNode } from 'react'
import { Compass, ExternalLink, Layers, RefreshCw, Sparkles, Target } from 'lucide-react'
import { CHANNELS } from '@shared/channels'
import { api, unwrap } from '@/lib/api'
import { useResource, useTicker } from '@/lib/hooks'
import { useApp } from '@/app/AppContext'
import { cn, formatBytes, formatRelative } from '@/lib/utils'
import { Badge, Button, EmptyState, Panel, SectionTitle, Spinner, StatCard, Switch } from '@/components/ui/primitives'
import type { PageKey } from '@/components/layout/Sidebar'
import type { WeeklyData } from '@electron/data/logs'

function planScore(item: Record<string, unknown>): number {
  const raw = item.skor ?? item.puan ?? item.score
  return typeof raw === 'number' ? raw : Number(raw) || 0
}

function planTitle(item: Record<string, unknown>): string {
  return String(item.baslik ?? item.title ?? item.link ?? item.video_id ?? '—')
}

export function DiscoverPage({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
  const { startJob, job, engine } = useApp()
  const [channelId, setChannelId] = useState('1')
  const [haftalik, setHaftalik] = useState(false)
  const [busy, setBusy] = useState(false)
  useTicker(job?.status === 'running')

  const weekly = useResource(() => unwrap(api.weeklyPlan()) as Promise<WeeklyData>, [job?.endedAt])
  const reports = useResource(() => unwrap(api.reportsList()), [job?.endedAt])

  const kesifReports = (reports.data ?? [])
    .flatMap((g) => g.items)
    .filter((i) => i.kind === 'report')
    .slice(0, 6)

  const run = async (kind: 'discover' | 'weekly'): Promise<void> => {
    setBusy(true)
    const ok = await startJob({ kind, channelId: channelId as '1' | '2' | '3', haftalik: kind === 'weekly' || haftalik })
    setBusy(false)
    if (ok) onNavigate('run')
  }

  return (
    <div className="space-y-3.5">
      <Panel className="app-bg p-5">
        <SectionTitle
          title="Kesif modulu"
          subtitle="Kaynak kanallari tarar, transkript cikarir, Gemini ile stile gore puanlar ve haftalik plan uretir"
          icon={<Compass className="size-4" />}
        />
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-3">
              {CHANNELS.map((ch) => (
                <button
                  key={ch.id}
                  onClick={() => setChannelId(ch.id)}
                  className={cn(
                    'rounded-[11px] border px-3 py-2.5 text-left transition-colors',
                    ch.id === channelId ? 'border-brand bg-brand-soft' : 'border-border bg-[var(--surface-2)] hover:border-border-strong',
                  )}
                >
                  <span className="num text-[10.5px] text-fg-subtle">kanal {ch.id}</span>
                  <p className="text-[12.5px] font-medium text-fg">{ch.name}</p>
                  <p className="text-[10.5px] text-fg-subtle">{ch.niche}</p>
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Switch
                checked={haftalik}
                onChange={setHaftalik}
                label="Haftalik mod"
                hint="7 video bulunur, skor sirasi = paylasim sirasi (1-7. gun)"
              />
              <div className="ml-auto flex gap-2">
                <Button
                  variant="primary"
                  icon={<Sparkles className="size-3.5" />}
                  loading={busy}
                  disabled={job?.status === 'running'}
                  onClick={() => void run('discover')}
                >
                  Kesif calistir
                </Button>
                <Button
                  variant="secondary"
                  icon={<Layers className="size-3.5" />}
                  disabled={job?.status === 'running'}
                  onClick={() => void run('weekly')}
                >
                  Haftalik zinciri baslat
                </Button>
              </div>
            </div>
            <p className="text-[11.5px] text-fg-subtle">
              Not: Kesif, kaynak kanal listesini <span className="font-mono">kesif_config.json</span> dosyasindan okur. Terminal
              sorusu cikmamasi icin <span className="font-mono">--evet</span> ile calistirilir; kaynak kanallar config'de kayitli olmalidir.
            </p>
          </div>

          <div className="space-y-2">
            <StatCard label="Planlanan gun" value={weekly.data?.plan?.length ?? '—'} hint="haftalik_plan.json" icon={<Target className="size-3" />} tone="brand" />
            <StatCard label="Gemini puanlama" value={engine ? `${engine.models.length} model` : '—'} hint="kota dolu ise siradaki modele gecer" icon={<Sparkles className="size-3" />} tone="cyan" />
          </div>
        </div>
      </Panel>

      <div className="grid gap-3.5 xl:grid-cols-[1fr_360px]">
        <Panel className="overflow-hidden">
          <div className="border-b border-border p-4">
            <SectionTitle
              title="Haftalik plan"
              subtitle="Skor sirasina gore gun gun oneriler"
              right={
                <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', weekly.loading && 'animate-spin')} />} onClick={() => weekly.reload()} />
              }
            />
          </div>
          {weekly.loading && !weekly.data ? (
            <div className="flex items-center justify-center gap-2 py-14 text-[12px] text-fg-subtle">
              <Spinner /> Plan okunuyor...
            </div>
          ) : (weekly.data?.plan?.length ?? 0) === 0 ? (
            <EmptyState
              icon={<Compass className="size-6" />}
              title="Haftalik plan yok"
              message="Haftalik kesif calistiginda haftalik_plan.json olusur ve burada listelenir."
            />
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border text-[11px] tracking-wide text-fg-subtle uppercase">
                  <th className="px-4 py-2 font-medium">Gun</th>
                  <th className="px-4 py-2 font-medium">Video</th>
                  <th className="px-4 py-2 font-medium">Puan</th>
                </tr>
              </thead>
              <tbody>
                {weekly.data?.plan?.map((item, idx) => {
                  const score = planScore(item)
                  return (
                    <tr key={`${planTitle(item)}-${idx}`} className="border-b border-border/60 last:border-0 hover:bg-[var(--surface-2)]">
                      <td className="px-4 py-2 text-[12px] text-fg-muted">Gun {item.gun ?? idx + 1}</td>
                      <td className="max-w-[380px] px-4 py-2">
                        <p className="truncate text-[12px] text-fg" title={planTitle(item)}>
                          {planTitle(item)}
                        </p>
                        {typeof item.link === 'string' ? (
                          <button
                            onClick={() => void api.shellOpenExternal(String(item.link))}
                            className="mt-0.5 inline-flex items-center gap-1 font-mono text-[10.5px] text-cyan hover:underline"
                          >
                            {String(item.link).slice(0, 48)} <ExternalLink className="size-2.5" />
                          </button>
                        ) : null}
                      </td>
                      <td className="px-4 py-2">
                        <Badge tone={score >= 6 ? 'success' : score >= 4 ? 'warn' : 'danger'}>{score ? score.toFixed(1) : '—'}</Badge>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel className="p-4">
          <SectionTitle title="Kesif raporlari" subtitle="HTML ciktilari (Masaustu)" icon={<Target className="size-4" />} />
          <div className="mt-3 space-y-2">
            {kesifReports.length === 0 ? (
              <p className="py-6 text-center text-[11.5px] text-fg-subtle">Henuz kesif raporu uretilmedi.</p>
            ) : (
              kesifReports.map((r) => (
                <div key={r.path} className="rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2">
                  <p className="truncate text-[11.5px] text-fg" title={r.path}>
                    {r.name}
                  </p>
                  <div className="mt-1 flex items-center gap-2 text-[10.5px] text-fg-subtle">
                    <span>{formatBytes(r.size)}</span>
                    <span>·</span>
                    <span>{formatRelative(r.mtime)}</span>
                    <Button size="sm" variant="ghost" className="ml-auto" onClick={() => void api.shellOpen(r.path)}>
                      Ac
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
          {weekly.data?.results?.length ? (
            <div className="mt-4 border-t border-border pt-3">
              <p className="text-[11.5px] font-medium text-fg-muted">Sonuc dosyalari</p>
              <div className="mt-2 space-y-1.5">
                {weekly.data.results.map((r) => (
                  <div key={r.channel} className="flex items-center justify-between text-[11.5px] text-fg-subtle">
                    <span>haftalik_sonuc_ch{r.channel}.json</span>
                    <Badge tone="neutral">{r.items.length} kayit</Badge>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </Panel>
      </div>
    </div>
  )
}
