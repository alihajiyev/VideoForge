import type { ReactNode } from 'react'
import { CircleStop, Clock, Cpu, DollarSign, FolderOpen, Image, Music, PlayCircle, Sparkles, Video } from 'lucide-react'
import { api } from '@/lib/api'
import { useTicker } from '@/lib/hooks'
import { useApp } from '@/app/AppContext'
import { ARTIFACT_LABEL, formatBytes, formatClock, formatDuration, KIND_LABEL, cn } from '@/lib/utils'
import { Badge, Button, EmptyState, Panel, SectionTitle, StatCard } from '@/components/ui/primitives'
import { ConsoleView } from '@/components/run/ConsoleView'
import { StageTimeline } from '@/components/run/StageTimeline'
import type { PageKey } from '@/components/layout/Sidebar'
import type { Artifact } from '@shared/types'

const STATUS_TONE = { running: 'brand', done: 'success', error: 'danger', cancelled: 'warn' } as const

function ArtifactIcon({ kind }: { kind: Artifact['kind'] }): ReactNode {
  const cls = 'size-3.5'
  if (kind === 'video') return <Video className={cls} />
  if (kind === 'audio') return <Music className={cls} />
  if (kind === 'thumb') return <Image className={cls} />
  return <FolderOpen className={cls} />
}

export function RunPage({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
  const { job, cancelJob, history } = useApp()
  useTicker(job?.status === 'running')

  if (!job) {
    return (
      <Panel className="p-6">
        <EmptyState
          icon={<PlayCircle className="size-7" />}
          title="Aktif islem yok"
          message="Panelden bir kanal ve link secerek islemi baslatin. Islem sirasinda botun tum ciktilari bu sayfada canli akar."
          action={
            <Button variant="primary" icon={<PlayCircle className="size-3.5" />} onClick={() => onNavigate('dashboard')}>
              Panele don
            </Button>
          }
        />
      </Panel>
    )
  }

  const duration = formatDuration(job.startedAt, job.endedAt)
  const stage = job.stages[job.stageIndex]

  return (
    <div className="space-y-3.5">
      <Panel className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-[16px] font-semibold tracking-[-0.01em] text-fg">{job.title}</h1>
              <Badge tone={STATUS_TONE[job.status]} dot={job.status === 'running'}>
                {job.status === 'running' ? 'calisiyor' : job.status === 'done' ? 'tamamlandi' : job.status === 'cancelled' ? 'durduruldu' : 'hata'}
              </Badge>
              <Badge tone="neutral">{KIND_LABEL[job.kind] ?? job.kind}</Badge>
            </div>
            <p className="mt-1 truncate font-mono text-[11.5px] text-fg-subtle" title={job.subtitle}>
              {job.subtitle || '—'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-right">
              <p className="num text-[13px] font-medium text-fg">{duration}</p>
              <p className="text-[10.5px] text-fg-subtle">
                {formatClock(job.startedAt)} · pid {job.pid ?? '—'} · cikis {job.exitCode ?? '—'}
              </p>
            </div>
            {job.status === 'running' ? (
              <Button variant="danger" icon={<CircleStop className="size-3.5" />} onClick={() => void cancelJob()}>
                Durdur
              </Button>
            ) : null}
          </div>
        </div>

        <div className="mt-3.5 border-t border-border pt-3.5">
          <StageTimeline stages={job.stages} index={job.stageIndex} status={job.status} />
          {stage?.hint ? <p className="mt-2 text-[11.5px] text-fg-subtle">Su an: {stage.label} — {stage.hint}</p> : null}
        </div>
      </Panel>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="GPU" value={job.stats.gpu ?? '—'} hint={job.stats.chunks ? `${job.stats.chunks} parca` : 'bekleniyor'} icon={<Cpu className="size-3" />} tone="violet" />
        <StatCard label="Maliyet" value={job.stats.cost ?? '—'} hint="Modal GPU tahmini" icon={<DollarSign className="size-3" />} tone="success" />
        <StatCard label="Gemini kullanimi" value={job.stats.gemini ? job.stats.gemini.split(' ')[0] : '—'} hint={job.stats.gemini ?? 'henuz olculmedi'} icon={<Sparkles className="size-3" />} tone="cyan" />
        <StatCard label="Cikti dosyasi" value={job.artifacts.length} hint={job.stats.duration ? `bot suresi: ${job.stats.duration}` : 'islem sonunda listelenir'} icon={<Clock className="size-3" />} tone="brand" />
      </div>

      {job.artifacts.length > 0 ? (
        <Panel className="p-4">
          <SectionTitle title="Uretilen dosyalar" subtitle="Masaustune yazilan ciktilar" icon={<FolderOpen className="size-4" />} />
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {job.artifacts.map((file) => (
              <div key={file.path} className="group rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2">
                <div className="flex items-center gap-2 text-fg-muted">
                  <ArtifactIcon kind={file.kind} />
                  <span className="text-[11.5px] font-medium">{ARTIFACT_LABEL[file.kind] ?? file.kind}</span>
                  <span className="num ml-auto text-[10.5px] text-fg-subtle">{formatBytes(file.size)}</span>
                </div>
                <p className="mt-1 truncate text-[11.5px] text-fg" title={file.path}>
                  {file.name}
                </p>
                <div className="mt-1.5 flex gap-1.5">
                  <Button size="sm" variant="ghost" onClick={() => void api.shellOpen(file.path)}>
                    Ac
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void api.shellReveal(file.path)}>
                    Klasor
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-[1fr_260px]">
        <ConsoleView lines={job.lines} live={job.status === 'running'} height="h-[460px]" />
        <Panel className="p-3">
          <SectionTitle title="Gecmis" subtitle="Bu oturumdaki isler" />
          <div className="mt-2 space-y-1.5">
            {history.length === 0 ? (
              <p className="py-3 text-center text-[11.5px] text-fg-subtle">Kayit yok</p>
            ) : (
              history.map((item) => (
                <div key={item.id} className="rounded-[9px] border border-border bg-[var(--surface-2)] px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[11.5px] text-fg">{item.title}</span>
                    <span
                      className={cn(
                        'size-1.5 shrink-0 rounded-full',
                        item.status === 'done' ? 'bg-success' : item.status === 'running' ? 'bg-brand' : item.status === 'cancelled' ? 'bg-warn' : 'bg-danger',
                      )}
                    />
                  </div>
                  <p className="text-[10.5px] text-fg-subtle">
                    {formatDuration(item.startedAt, item.endedAt)} · {KIND_LABEL[item.kind] ?? item.kind}
                  </p>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>
    </div>
  )
}
