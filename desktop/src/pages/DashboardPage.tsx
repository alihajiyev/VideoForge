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
  Rocket,
} from 'lucide-react'
import { CHANNELS } from '@shared/channels'
import { api, unwrap } from '@/lib/api'
import { useResource } from '@/lib/hooks'
import { useApp, useGunSayisi } from '@/app/AppContext'
import { cn, formatBytes, formatRelative } from '@/lib/utils'
import { Badge, Button, EmptyState, Input, Panel, SectionTitle, Select, Spinner } from '@/components/ui/primitives'
import { GunSayisiSecici } from '@/components/ui/GunSayisiSecici'
import { KurulumRehberi } from '@/components/dashboard/KurulumRehberi'
import { MaliyetKarti } from '@/components/dashboard/MaliyetKarti'
import { KotaKarti } from '@/components/dashboard/KotaKarti'
import { KrediKarti } from '@/components/dashboard/KrediKarti'
import type { PageKey } from '@/components/layout/Sidebar'
import type { Artifact, EnvCheck } from '@shared/types'

/** Ana sayfa ozellik karti: ikon + baslik + aciklama + kendi kontrolleri. */
function FeatureCard({
  step,
  title,
  desc,
  icon,
  tone,
  children,
}: {
  step: number
  title: string
  desc: string
  icon: ReactNode
  tone: 'cyan' | 'brand' | 'violet'
  children: ReactNode
}): ReactNode {
  const toneCls =
    tone === 'cyan' ? 'text-cyan bg-cyan-soft' : tone === 'violet' ? 'text-violet bg-[var(--surface-3)]' : 'text-brand bg-brand-soft'
  return (
    <Panel className="flex flex-col p-4">
      <div className="flex items-center gap-2.5">
        <span className={cn('grid size-9 shrink-0 place-items-center rounded-[10px]', toneCls)}>{icon}</span>
        <div className="min-w-0">
          <p className="num text-[10.5px] tracking-wide text-fg-subtle uppercase">Yöntem {step}</p>
          <h3 className="truncate text-[13.5px] font-semibold text-fg">{title}</h3>
        </div>
      </div>
      <p className="mt-2.5 text-[11.5px] leading-relaxed text-fg-muted">{desc}</p>
      <div className="mt-3 flex flex-1 flex-col justify-end gap-3">{children}</div>
    </Panel>
  )
}

function EnvRow({ check }: { check: EnvCheck }): ReactNode {
  return (
    <div className="flex items-start gap-2 rounded-[9px] border border-border bg-[var(--surface-2)] px-2.5 py-1.5">
      {check.ok ? (
        <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" />
      ) : (
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" />
      )}
      <div className="min-w-0">
        <p className="truncate text-[11.5px] font-medium text-fg">{check.label}</p>
        <p className="truncate text-[10.5px] text-fg-subtle" title={check.detail}>
          {check.detail}
        </p>
      </div>
    </div>
  )
}

export function DashboardPage({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
  const { env, envLoading, refreshEnv, startJob, job, info } = useApp()
  const [channelId, setChannelId] = useState<string>('1')
  const [link, setLink] = useState('')
  const [busy, setBusy] = useState<'' | 'kesif' | 'link' | 'uretim'>('')

  const reports = useResource(() => unwrap(api.reportsList()), [job?.endedAt], { intervalMs: 15000 })
  const recent: Artifact[] = (reports.data ?? []).flatMap((g) => g.items).slice(0, 8)

  const running = job?.status === 'running'
  const [gunSayisi, setGunSayisi] = useGunSayisi()

  const baslat = async (tur: 'kesif' | 'link' | 'uretim'): Promise<void> => {
    setBusy(tur)
    let ok = false
    if (tur === 'kesif') {
      ok = await startJob({ kind: 'discover', channelId: channelId as '1' | '2' | '3', haftalik: true, gunSayisi })
    } else if (tur === 'link') {
      ok = await startJob({ kind: 'channel', channelId: channelId as '1' | '2' | '3', link: link.trim() })
    } else {
      ok = await startJob({ kind: 'weekly', channelId: channelId as '1' | '2' | '3', haftalik: true, gunSayisi })
    }
    setBusy('')
    if (ok) onNavigate('run')
  }

  const eksik = env.filter((e) => !e.ok).length

  return (
    <div className="space-y-3.5">
      {/* Baslik */}
      <Panel className="app-bg flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-[18px] leading-tight font-semibold tracking-[-0.02em] text-fg">
            Video<span className="gradient-text">Forge</span>
          </h1>
          <p className="mt-0.5 text-[12px] text-fg-muted">
            Üç yöntem: keşif, tek link işleme ve N günlük keşif + üretim. Tüm çıktılar masaüstüne bırakılır.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="neutral">
            Bot: <span className="font-mono">{info?.videoForgePath ?? '—'}</span>
          </Badge>
          <Badge tone={eksik ? 'warn' : 'success'}>{eksik ? `${eksik} eksik kurulum` : 'ortam hazır'}</Badge>
        </div>
      </Panel>

      {/* 3 ozellik */}
      <div className="grid gap-3.5 lg:grid-cols-3">
        {/* 1) Kesif */}
        <FeatureCard
          step={1}
          title="Keşif yap"
          tone="cyan"
          icon={<Compass className="size-4.5" />}
          desc="Kaynak kanalları tarar, Gemini ile puanlar ve seçtiğin gün sayısı kadar video bulur. Sonucu masaüstüne HTML raporu olarak bırakır."
        >
          <GunSayisiSecici value={gunSayisi} onChange={setGunSayisi} disabled={running} hint={false} />
          <Button
            variant="primary"
            icon={<Compass className="size-3.5" />}
            loading={busy === 'kesif'}
            disabled={running}
            onClick={() => void baslat('kesif')}
          >
            {gunSayisi} günlük keşif · HTML
          </Button>
        </FeatureCard>

        {/* 2) Link ile uretim */}
        <FeatureCard
          step={2}
          title="Link ile video üret"
          tone="brand"
          icon={<Link2 className="size-4.5" />}
          desc="Verdiğin TikTok/YouTube linkini indirir, zamanlı keser, seslendirir, temizler ve SEO raporuyla birlikte üretir."
        >
          <Select value={channelId} onChange={(e) => setChannelId(e.target.value)} disabled={running} aria-label="Kanal">
            {CHANNELS.map((ch) => (
              <option key={ch.id} value={ch.id}>
                {ch.name} — {ch.niche}
              </option>
            ))}
          </Select>
          <div className="relative">
            <Link2 className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-fg-subtle" />
            <Input
              value={link}
              onChange={(e) => setLink(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && link.trim()) void baslat('link')
              }}
              placeholder="TikTok veya YouTube linkini yapıştır"
              className="pl-9"
            />
          </div>
          <Button
            variant="primary"
            icon={<Play className="size-3.5" />}
            loading={busy === 'link'}
            disabled={!link.trim() || running}
            onClick={() => void baslat('link')}
          >
            Videoyu üret
          </Button>
        </FeatureCard>

        {/* 3) N gunluk uretim */}
        <FeatureCard
          step={3}
          title="N günlük üretim"
          tone="violet"
          icon={<Layers className="size-4.5" />}
          desc="Hem keşif yapar hem seçtiğin gün sayısı kadar videoyu sırayla üretir. Hepsini masaüstüne bırakır."
        >
          <GunSayisiSecici value={gunSayisi} onChange={setGunSayisi} disabled={running} id="gun-sayisi-uretim" hint={false} />
          <Button
            variant="secondary"
            icon={<Layers className="size-3.5" />}
            loading={busy === 'uretim'}
            disabled={running}
            onClick={() => void baslat('uretim')}
          >
            {gunSayisi} gün keşif + üretim
          </Button>
        </FeatureCard>
      </div>

      <KurulumRehberi onNavigate={onNavigate} />

      {/* Maliyet + kota + krediler */}
      <div className="grid gap-3 lg:grid-cols-2">
        <MaliyetKarti />
        <KotaKarti />
      </div>
      <KrediKarti />

      {/* Son ciktilar */}
      <Panel className="p-4">
        <SectionTitle
          title="Son üretilen dosyalar"
          subtitle="Masaüstü ve gün klasörleri taranır"
          icon={<FolderOpen className="size-4" />}
          right={
            <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', reports.loading && 'animate-spin')} />} onClick={() => reports.reload()}>
              Yenile
            </Button>
          }
        />
        {reports.loading && !reports.data ? (
          <div className="flex items-center justify-center gap-2 py-10 text-[12px] text-fg-subtle">
            <Spinner /> Taranıyor...
          </div>
        ) : recent.length === 0 ? (
          <EmptyState
            icon={<FolderOpen className="size-6" />}
            title="Henüz çıktı dosyası yok"
            message="Bir yöntem çalıştırdıktan sonra üretilen video, seslendirme, kapak ve HTML raporları burada listelenir."
          />
        ) : (
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {recent.map((file) => (
              <div key={file.path} className="group flex items-center gap-3 rounded-[9px] border border-border bg-[var(--surface-2)] px-3 py-2">
                <Badge tone="neutral">
                  {file.kind === 'video' ? 'mp4' : file.kind === 'audio' ? 'mp3' : file.kind === 'thumb' ? 'png' : file.kind === 'report' ? 'html' : 'dosya'}
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

      {/* Ortam durumu (kucuk) */}
      <Panel className="p-4">
        <SectionTitle
          title="Ortam durumu"
          subtitle={`${env.filter((e) => e.ok).length}/${env.length} kontrol başarılı`}
          icon={<Rocket className="size-4" />}
          right={
            <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', envLoading && 'animate-spin')} />} onClick={() => void refreshEnv()}>
              Yenile
            </Button>
          }
        />
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {envLoading && !env.length ? (
            <div className="flex items-center gap-2 py-4 text-[12px] text-fg-subtle">
              <Spinner /> Kontrol ediliyor...
            </div>
          ) : (
            env.slice(0, 9).map((check) => <EnvRow key={check.id} check={check} />)
          )}
        </div>
      </Panel>
    </div>
  )
}
