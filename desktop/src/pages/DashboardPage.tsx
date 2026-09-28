import { useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Compass,
  ExternalLink,
  Flame,
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
import { useApp } from '@/app/AppContext'
import { cn, formatBytes, formatRelative } from '@/lib/utils'
import { Badge, Button, EmptyState, Input, Panel, SectionTitle, Spinner, StatCard, Switch } from '@/components/ui/primitives'
import type { PageKey } from '@/components/layout/Sidebar'
import type { Artifact, EnvCheck } from '@shared/types'

function EnvRow({ check }: { check: EnvCheck }): ReactNode {
  return (
    <div className="flex items-start gap-2.5 rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2">
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
  const { env, envLoading, refreshEnv, engine, startJob, job, info } = useApp()
  const [channelId, setChannelId] = useState<string>('1')
  const [link, setLink] = useState('')
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)

  const reports = useResource(() => unwrap(api.reportsList()), [job?.endedAt], { intervalMs: 15000 })
  const library = useResource(() => unwrap(api.libraryList()), [job?.endedAt])

  const recent: Artifact[] = (reports.data ?? []).flatMap((g) => g.items).slice(0, 6)
  const selected = CHANNELS.find((c) => c.id === channelId)

  const launch = async (): Promise<void> => {
    setBusy(true)
    const ok = await startJob({ kind: 'channel', channelId: channelId as '1' | '2' | '3', link: link.trim(), force })
    setBusy(false)
    if (ok) onNavigate('run')
  }

  const quick = async (kind: 'discover' | 'weekly'): Promise<void> => {
    const ok = await startJob({ kind, channelId: channelId as '1' | '2' | '3', haftalik: kind === 'weekly' })
    if (ok) onNavigate('run')
  }

  return (
    <div className="space-y-4">
      {/* Baslatma karti */}
      <Panel className="app-bg overflow-hidden p-0">
        <div className="grid gap-0 lg:grid-cols-[1.35fr_1fr]">
          <div className="space-y-4 p-5">
            <div>
              <div className="flex items-center gap-2">
                <Flame className="size-4 text-brand" />
                <span className="text-[11.5px] font-semibold tracking-[0.08em] text-fg-subtle uppercase">Islem baslat</span>
              </div>
              <h1 className="mt-2 text-[22px] leading-tight font-semibold tracking-[-0.02em] text-fg">
                Videoyu indir, <span className="gradient-text">temizle</span>, seslendir ve SEO raporunu al
              </h1>
              <p className="mt-1.5 max-w-xl text-[12.5px] text-fg-muted">
                Bot mantigi aynen korunur: yt-dlp indirme, transkript, Gemini metin uretimi, ElevenLabs seslendirme,
                ProPainter GPU temizligi ve masaustune cikti yazimi.
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
                      'group relative overflow-hidden rounded-[12px] border p-3 text-left transition-all',
                      'bg-gradient-to-br',
                      ch.accent,
                      active ? 'border-brand shadow-[0_10px_30px_-16px_rgb(245_158_11/0.7)]' : 'border-border hover:border-border-strong',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="num text-[11px] text-fg-subtle">{ch.id}</span>
                      {active ? <Badge tone="brand">secili</Badge> : null}
                    </div>
                    <p className="mt-2 text-[13px] font-semibold text-fg">{ch.name}</p>
                    <p className="text-[11.5px] text-fg-muted">{ch.niche}</p>
                    <p className="mt-1.5 text-[10.5px] leading-snug text-fg-subtle">{ch.note}</p>
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
                  placeholder="TikTok / YouTube linkini yapistir..."
                  className="pl-9"
                />
              </div>
              <Button
                variant="primary"
                size="md"
                icon={<Play className="size-3.5" />}
                loading={busy}
                disabled={!link.trim() || job?.status === 'running'}
                onClick={() => void launch()}
              >
                Islemi baslat
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <Switch checked={force} onChange={setForce} label="Konu puanini atla" hint="--force (1. kanal)" />
              <div className="ml-auto flex gap-2">
                <Button size="sm" icon={<Compass className="size-3.5" />} onClick={() => void quick('discover')} disabled={job?.status === 'running'}>
                  Kesif calistir
                </Button>
                <Button size="sm" icon={<Layers className="size-3.5" />} onClick={() => void quick('weekly')} disabled={job?.status === 'running'}>
                  Haftalik zincir
                </Button>
              </div>
            </div>

            <div className="rounded-[11px] border border-border bg-[var(--surface-2)]/70 px-3.5 py-2.5">
              <p className="text-[11.5px] font-medium text-fg-muted">Kanal secimi neyi degistirir?</p>
              <ul className="mt-1.5 space-y-1 text-[11px] text-fg-subtle">
                <li>
                  <span className="text-fg-muted">1-2. kanal:</span> konu puani kapisi acik, karakter limiti 500-600 araligina kelepcelenir,
                  hook sorusu serbest.
                </li>
                <li>
                  <span className="text-fg-muted">3. kanal (PopkornFakty):</span> sinematik anlatici, tum sorular yasak, limit transcript'in %80'i
                  ve ses orijinal videodan uzun olamaz.
                </li>
              </ul>
            </div>
          </div>

          {/* Sag taraf: hizli durum */}
          <div className="border-t border-border bg-[var(--surface-2)]/60 p-5 lg:border-t-0 lg:border-l">
            <SectionTitle
              title="Ortam durumu"
              subtitle={`${env.filter((e) => e.ok).length}/${env.length} kontrol basarili`}
              right={
                <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', envLoading && 'animate-spin')} />} onClick={() => void refreshEnv()}>
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
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge tone={engine?.hdMode ? 'violet' : 'neutral'}>
                {engine ? `${engine.procW}x${engine.procH}` : 'cozunurluk ?'}
              </Badge>
              <Badge tone="cyan">{engine?.gpu ?? 'GPU ?'}</Badge>
              <Badge tone="brand">{engine ? `${engine.models.length} Gemini modeli` : 'modeller ?'}</Badge>
              <Badge tone={engine?.elevenlabs ? 'success' : 'warn'}>
                ElevenLabs {engine?.elevenlabs ? 'acik' : 'kapali'}
              </Badge>
            </div>
          </div>
        </div>
      </Panel>

      {/* Istatistikler */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Islenen video"
          value={library.data?.counts.videos ?? '—'}
          hint="bot.db kayitli (tekrar indirme korumasi)"
          icon={<Layers className="size-3" />}
          tone="brand"
        />
        <StatCard
          label="Kesif onerisi"
          value={library.data?.counts.oneriler ?? '—'}
          hint="puanlanmis video havuzu"
          icon={<Sparkles className="size-3" />}
          tone="cyan"
        />
        <StatCard
          label="Uretilen cikti"
          value={reports.data?.length ?? '—'}
          hint="masaustunde gruplanmis is"
          icon={<FolderOpen className="size-3" />}
          tone="violet"
        />
        <StatCard
          label="Aktif model"
          value={library.data?.settings?.working_model ? library.data.settings.working_model.replace('gemini-', '') : '—'}
          hint="bot.db > working_model"
          icon={<Zap className="size-3" />}
          tone="success"
        />
      </div>

      {/* Son ciktilar */}
      <Panel className="p-4">
        <SectionTitle
          title="Son uretilen dosyalar"
          subtitle="Masaustu ve Gun klasorleri taranir"
          icon={<FolderOpen className="size-4" />}
          right={
            <Button size="sm" variant="ghost" onClick={() => onNavigate('reports')}>
              Tumunu gor
            </Button>
          }
        />
        {recent.length === 0 ? (
          <EmptyState
            icon={<FolderOpen className="size-6" />}
            title="Henuz cikti dosyasi yok"
            message="Bir video isledikten sonra temiz video, seslendirme, kapak ve SEO raporu burada listelenir."
          />
        ) : (
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {recent.map((file) => (
              <div
                key={file.path}
                className="group flex items-center gap-3 rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2"
              >
                <Badge tone={file.kind === 'video' ? 'brand' : file.kind === 'audio' ? 'cyan' : 'neutral'}>
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
                  title="Klasorde goster"
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
      <Panel className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-[11.5px] text-fg-subtle">
        <span>
          Bot klasoru: <span className="font-mono text-fg-muted">{info?.videoForgePath ?? '—'}</span>
        </span>
        <span>
          Cikti klasoru: <span className="font-mono text-fg-muted">{info?.desktop ?? '—'}</span>
        </span>
        <span className="ml-auto">
          {selected ? `${selected.name} seslendirme sesi: ${selected.voiceId}` : null}
        </span>
      </Panel>
    </div>
  )
}
