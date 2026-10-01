import { useState, type ReactNode } from 'react'
import { Compass, ExternalLink, Layers, RefreshCw, Sparkles, Target } from 'lucide-react'
import { CHANNELS } from '@shared/channels'
import { api, unwrap } from '@/lib/api'
import { useResource, useTicker } from '@/lib/hooks'
import { useApp, useGunSayisi } from '@/app/AppContext'
import { cn, formatBytes, formatRelative } from '@/lib/utils'
import { Badge, Button, EmptyState, Panel, SectionTitle, Spinner, StatCard, Switch } from '@/components/ui/primitives'
import { GunSayisiSecici } from '@/components/ui/GunSayisiSecici'
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
  // Plan modu acikken secilen gun sayisi kadar video bulunur (7 sabit degil).
  const [planModu, setPlanModu] = useState(true)
  // Gun sayisi ayarlarda saklanir: Panel'de yazilan sayi burada da gorunur.
  const [gunSayisi, setGunSayisi] = useGunSayisi()
  const [busy, setBusy] = useState(false)
  useTicker(job?.status === 'running')

  const weekly = useResource(() => unwrap(api.weeklyPlan()) as Promise<WeeklyData>, [job?.endedAt])
  const reports = useResource(() => unwrap(api.reportsList()), [job?.endedAt])

  const kesifReports = (reports.data ?? [])
    .flatMap((g) => g.items)
    .filter((i) => i.kind === 'report')
    .slice(0, 6)

  const gun = gunSayisi

  const run = async (kind: 'discover' | 'weekly'): Promise<void> => {
    setBusy(true)
    const ok = await startJob({
      kind,
      channelId: channelId as '1' | '2' | '3',
      haftalik: kind === 'weekly' || planModu,
      gunSayisi: gun,
    })
    setBusy(false)
    if (ok) onNavigate('run')
  }

  return (
    <div className="space-y-3.5">
      <Panel className="app-bg p-5">
        <SectionTitle
          title="Keşif modülü"
          subtitle="Kaynak kanalları tarar, transkript çıkarır, Gemini ile stile göre puanlar ve seçtiğiniz gün sayısı kadar plan üretir"
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
            <div className="flex flex-wrap items-start gap-4">
              <Switch checked={planModu} onChange={setPlanModu} label="Çok günlü plan modu" hint="Kapalıysa yalnızca tek seferlik öneri listesi üretilir." />
              <div className={cn('transition-opacity', !planModu && 'pointer-events-none opacity-40')}>
                <GunSayisiSecici
                  value={gunSayisi}
                  onChange={setGunSayisi}
                  disabled={job?.status === 'running' || !planModu}
                />
              </div>
              <div className="ml-auto flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  icon={<Sparkles className="size-3.5" />}
                  loading={busy}
                  disabled={job?.status === 'running'}
                  onClick={() => void run('discover')}
                >
                  {planModu ? `${gun} günlük plan oluştur` : 'Keşif çalıştır'}
                </Button>
                <Button
                  variant="secondary"
                  icon={<Layers className="size-3.5" />}
                  disabled={job?.status === 'running' || !planModu}
                  title={planModu ? undefined : 'Zincir için önce plan modunu açın'}
                  onClick={() => void run('weekly')}
                >
                  {gun} günlük zinciri başlat
                </Button>
              </div>
            </div>
            <p className="text-[11.5px] text-fg-subtle">
              Not: Keşif, kaynak kanal listesini <span className="font-mono">kesif_config.json</span> dosyasından okur. Terminal
              sorusu çıkmaması için <span className="font-mono">--evet</span> ile çalıştırılır; kaynak kanallar config'de kayıtlı olmalıdır.
            </p>
          </div>

          <div className="space-y-2">
            <StatCard
              label="Plandaki gün"
              value={weekly.data?.plan?.length ?? '—'}
              hint={`${gun} günlük plan · haftalik_plan.json`}
              icon={<Target className="size-3.5" />}
            />
            <StatCard label="Gemini puanlama" value={engine ? `${engine.models.length} model` : '—'} hint="kota doluysa sıradaki modele geçer" icon={<Sparkles className="size-3.5" />} />
          </div>
        </div>
      </Panel>

      <div className="grid gap-3.5 xl:grid-cols-[1fr_360px]">
        <Panel className="overflow-hidden">
          <div className="border-b border-border p-4">
            <SectionTitle
              title="Günlük plan"
              subtitle="Skor sırasına göre gün gün öneriler"
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
              title="Plan yok"
              message="Çok günlü keşif çalıştığında haftalik_plan.json oluşur ve burada listelenir."
            />
          ) : (
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border text-[11px] tracking-wide text-fg-subtle uppercase">
                  <th className="px-4 py-2 font-medium">Gün</th>
                  <th className="px-4 py-2 font-medium">Video</th>
                  <th className="px-4 py-2 font-medium">Puan</th>
                </tr>
              </thead>
              <tbody>
                {weekly.data?.plan?.map((item, idx) => {
                  const score = planScore(item)
                  return (
                    <tr key={`${planTitle(item)}-${idx}`} className="border-b border-border/60 last:border-0 hover:bg-[var(--surface-2)]">
                      <td className="px-4 py-2 text-[12px] text-fg-muted">Gün {item.gun ?? idx + 1}</td>
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
          <SectionTitle title="Keşif raporları" subtitle="HTML çıktıları (Masaüstü)" icon={<Target className="size-4" />} />
          <div className="mt-3 space-y-2">
            {kesifReports.length === 0 ? (
              <p className="py-6 text-center text-[11.5px] text-fg-subtle">Henüz keşif raporu üretilmedi.</p>
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
                      Aç
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
          {weekly.data?.results?.length ? (
            <div className="mt-4 border-t border-border pt-3">
              <p className="text-[11.5px] font-medium text-fg-muted">Sonuç dosyaları</p>
              <div className="mt-2 space-y-1.5">
                {weekly.data.results.map((r) => (
                  <div key={r.channel} className="flex items-center justify-between text-[11.5px] text-fg-subtle">
                    <span>haftalik_sonuc_ch{r.channel}.json</span>
                    <Badge tone="neutral">{r.items.length} kayıt</Badge>
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
