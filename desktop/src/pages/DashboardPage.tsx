import { useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Compass,
  ExternalLink,
  FolderOpen,
  Layers,
  Link2,
  Play,
  RefreshCw,
  Sparkles,
  Zap,
} from 'lucide-react'
import { CHANNELS } from '@shared/channels'
import { api, unwrap } from '@/lib/api'
import { useResource } from '@/lib/hooks'
import { useApp, useGunSayisi } from '@/app/AppContext'
import { cn, formatBytes, formatRelative, formatUsd } from '@/lib/utils'
import { Badge, Button, EmptyState, Input, Panel, SectionTitle, Spinner, StatCard, Switch } from '@/components/ui/primitives'
import { GunSayisiSecici } from '@/components/ui/GunSayisiSecici'
import { KurulumRehberi } from '@/components/dashboard/KurulumRehberi'
import { MaliyetKarti } from '@/components/dashboard/MaliyetKarti'
import { KotaKarti } from '@/components/dashboard/KotaKarti'
import { KrediKarti } from '@/components/dashboard/KrediKarti'
import type { PageKey } from '@/components/layout/Sidebar'
import type { Artifact, EnvCheck } from '@shared/types'

function EnvRow({ check }: { check: EnvCheck }): ReactNode {
  return (
    <div className="flex items-start gap-2.5 rounded-[9px] border border-border bg-[var(--surface-2)] px-3 py-2">
      {check.ok ? (
        <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />
      ) : (
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" />
      )}
      <div className="min-w-0">
        <p className="truncate text-[12px] font-medium text-fg">{check.label}</p>
        <p className="truncate text-[11px] text-fg-subtle" title={check.detail}>
          {check.detail}
        </p>
        {!check.ok && check.fix ? <p className="mt-0.5 text-[11px] text-warn">{check.fix}</p> : null}
      </div>
    </div>
  )
}

export function DashboardPage({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
  const { env, envLoading, refreshEnv, engine, startJob, job, info, spend } = useApp()
  const [channelId, setChannelId] = useState<string>('1')
  const [link, setLink] = useState('')
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)

  const reports = useResource(() => unwrap(api.reportsList()), [job?.endedAt], { intervalMs: 15000 })
  const library = useResource(() => unwrap(api.libraryList()), [job?.endedAt])

  const recent: Artifact[] = (reports.data ?? []).flatMap((g) => g.items).slice(0, 6)
  const selected = CHANNELS.find((c) => c.id === channelId)
  const running = job?.status === 'running'

  const launch = async (): Promise<void> => {
    setBusy(true)
    const ok = await startJob({ kind: 'channel', channelId: channelId as '1' | '2' | '3', link: link.trim(), force })
    setBusy(false)
    if (ok) onNavigate('run')
  }

  // Gün sayısı ayarlarda saklanır: Panel ve Keşif aynı değeri paylaşır.
  const [gunSayisi, setGunSayisi] = useGunSayisi()
  const quick = async (kind: 'discover' | 'weekly'): Promise<void> => {
    const ok = await startJob({
      kind,
      channelId: channelId as '1' | '2' | '3',
      haftalik: kind === 'weekly',
      gunSayisi,
    })
    if (ok) onNavigate('run')
  }

  return (
    <div className="space-y-3.5">
      {/* İşlem başlatma */}
      <Panel className="p-5">
        <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
          <div className="space-y-4">
            <div>
              <h1 className="text-[19px] leading-tight font-semibold tracking-[-0.02em] text-fg">İşlem başlat</h1>
              <p className="mt-1 text-[12.5px] text-fg-muted">
                Linki yapıştır: indirme, transkript, seslendirme, GPU temizliği ve SEO raporu sırayla çalışır.
              </p>
            </div>

            <div className="grid gap-2 sm:grid-cols-3">
              {CHANNELS.map((ch) => {
                const active = ch.id === channelId
                return (
                  <button
                    key={ch.id}
                    onClick={() => setChannelId(ch.id)}
                    className={cn(
                      'rounded-[10px] border p-3 text-left transition-colors',
                      active
                        ? 'border-brand bg-brand-soft'
                        : 'border-border bg-[var(--surface-2)] hover:border-border-strong',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="num text-[11px] text-fg-subtle">{ch.id}</span>
                      {active ? <Badge tone="brand">seçili</Badge> : null}
                    </div>
                    <p className="mt-1.5 truncate text-[13px] font-semibold text-fg">{ch.name}</p>
                    <p className="truncate text-[11.5px] text-fg-muted">{ch.niche}</p>
                    <p className="mt-1 text-[10.5px] leading-snug text-fg-subtle">{ch.note}</p>
                  </button>
                )
              })}
            </div>

            <div className="flex flex-col gap-2.5 sm:flex-row">
              <div className="relative flex-1">
                <Link2 className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-fg-subtle" />
                <Input
                  value={link}
                  onChange={(e) => setLink(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && link.trim()) void launch()
                  }}
                  placeholder="TikTok veya YouTube linkini yapıştır"
                  className="pl-9"
                />
              </div>
              <div className="flex flex-col items-stretch gap-1">
                <Button
                  variant="primary"
                  icon={<Play className="size-3.5" />}
                  loading={busy}
                  disabled={!link.trim() || running}
                  onClick={() => void launch()}
                >
                  İşlemi başlat
                </Button>
                {spend?.ortalama?.channel ? (
                  <span className="text-center text-[10.5px] text-fg-subtle">
                    Tahmini maliyet: ~{formatUsd(spend.ortalama.channel)}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
              <GunSayisiSecici value={gunSayisi} onChange={setGunSayisi} disabled={running} />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" icon={<Compass className="size-3.5" />} onClick={() => void quick('discover')} disabled={running}>
                  {gunSayisi} günlük plan oluştur
                </Button>
                <Button size="sm" icon={<Layers className="size-3.5" />} onClick={() => void quick('weekly')} disabled={running}>
                  {gunSayisi} günlük zincir
                </Button>
              </div>
              <Switch checked={force} onChange={setForce} label="Konu puanını atla" hint="--force" />
            </div>
          </div>

          {/* Ortam durumu */}
          <div className="border-t border-border pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-5">
            <SectionTitle
              title="Ortam durumu"
              subtitle={`${env.filter((e) => e.ok).length}/${env.length} kontrol başarılı`}
              right={
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<RefreshCw className={cn('size-3.5', envLoading && 'animate-spin')} />}
                  onClick={() => void refreshEnv()}
                >
                  Yenile
                </Button>
              }
            />
            <div className="mt-3 grid gap-2">
              {envLoading && !env.length ? (
                <div className="flex items-center gap-2 py-6 text-[12px] text-fg-subtle">
                  <Spinner /> Kontrol ediliyor...
                </div>
              ) : (
                env.slice(0, 6).map((check) => <EnvRow key={check.id} check={check} />)
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge tone="neutral">{engine ? `${engine.procW}x${engine.procH}` : 'çözünürlük ?'}</Badge>
              <Badge tone="neutral">{engine?.gpu ?? 'GPU ?'}</Badge>
              <Badge tone="neutral">{engine ? `${engine.models.length} Gemini modeli` : 'modeller ?'}</Badge>
              <Badge tone={engine?.elevenlabs ? 'success' : 'warn'}>
                ElevenLabs {engine?.elevenlabs ? 'açık' : 'kapalı'}
              </Badge>
            </div>
          </div>
        </div>
      </Panel>

      <KurulumRehberi onNavigate={onNavigate} />

      {/* İstatistikler */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="İşlenen video"
          value={library.data?.counts.videos ?? '—'}
          hint="bot.db kayıtlı · tekrar indirme koruması"
          icon={<Layers className="size-3.5" />}
        />
        <StatCard
          label="Keşif önerisi"
          value={library.data?.counts.oneriler ?? '—'}
          hint="puanlanmış video havuzu"
          icon={<Sparkles className="size-3.5" />}
        />
        <StatCard
          label="Üretilen çıktı"
          value={reports.data?.length ?? '—'}
          hint="masaüstünde gruplanmış iş"
          icon={<FolderOpen className="size-3.5" />}
        />
        <StatCard
          label="Aktif model"
          value={library.data?.settings?.working_model ? library.data.settings.working_model.replace('gemini-', '') : '—'}
          hint="bot.db > working_model"
          icon={<Zap className="size-3.5" />}
        />
      </div>

      {/* Maliyet + kota */}
      <div className="grid gap-3 lg:grid-cols-2">
        <MaliyetKarti />
        <KotaKarti />
      </div>

      {/* Servis kredileri (ElevenLabs, ZapCap, Gemini...) */}
      <KrediKarti />

      {/* Son çıktılar */}
      <Panel className="p-4">
        <SectionTitle
          title="Son üretilen dosyalar"
          subtitle="Masaüstü ve gün klasörleri taranır"
          icon={<FolderOpen className="size-4" />}
          right={
            <Button size="sm" variant="ghost" onClick={() => onNavigate('reports')}>
              Tümünü gör
            </Button>
          }
        />
        {recent.length === 0 ? (
          <EmptyState
            icon={<FolderOpen className="size-6" />}
            title="Henüz çıktı dosyası yok"
            message="Bir video işledikten sonra temiz video, seslendirme, kapak ve SEO raporu burada listelenir."
          />
        ) : (
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {recent.map((file) => (
              <div
                key={file.path}
                className="group flex items-center gap-3 rounded-[9px] border border-border bg-[var(--surface-2)] px-3 py-2"
              >
                <Badge tone="neutral">
                  {file.kind === 'video' ? 'mp4' : file.kind === 'audio' ? 'mp3' : file.kind === 'thumb' ? 'png' : 'html'}
                </Badge>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] text-fg" title={file.path}>
                    {file.name}
                  </p>
                  <p className="text-[10.5px] text-fg-subtle">
                    {formatBytes(file.size)} · {formatRelative(file.mtime)}
                  </p>
                </div>
                <button
                  onClick={() => void api.shellReveal(file.path)}
                  title="Klasörde göster"
                  className="text-fg-subtle opacity-0 transition-opacity group-hover:opacity-100 hover:text-fg"
                >
                  <ExternalLink className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Alt bilgi */}
      <Panel className="flex flex-wrap items-center gap-x-6 gap-y-1.5 px-4 py-2.5 text-[11.5px] text-fg-subtle">
        <span>
          Bot klasörü: <span className="font-mono text-fg-muted">{info?.videoForgePath ?? '—'}</span>
        </span>
        <span>
          Çıktı klasörü: <span className="font-mono text-fg-muted">{info?.desktop ?? '—'}</span>
        </span>
        <span className="ml-auto">{selected ? `seslendirme sesi: ${selected.voiceId}` : null}</span>
      </Panel>
    </div>
  )
}
