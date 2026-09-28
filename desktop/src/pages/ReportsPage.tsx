import { useMemo, useState, type ReactNode } from 'react'
import { Eye, FileText, FolderOpen, Image, Music, RefreshCw, Search, Video } from 'lucide-react'
import { api, unwrap } from '@/lib/api'
import { useResource } from '@/lib/hooks'
import { useApp } from '@/app/AppContext'
import { ARTIFACT_LABEL, formatBytes, formatRelative, cn } from '@/lib/utils'
import { Badge, Button, EmptyState, Input, Panel, SectionTitle, Spinner } from '@/components/ui/primitives'
import type { Artifact, ReportPreview } from '@shared/types'

function Icon({ kind }: { kind: Artifact['kind'] }): ReactNode {
  const cls = 'size-3.5'
  if (kind === 'video') return <Video className={cls} />
  if (kind === 'audio') return <Music className={cls} />
  if (kind === 'thumb') return <Image className={cls} />
  if (kind === 'report') return <FileText className={cls} />
  return <FolderOpen className={cls} />
}

export function ReportsPage(): ReactNode {
  const { job, pushToast } = useApp()
  const [query, setQuery] = useState('')
  const [sel, setSel] = useState<string | null>(null)
  const [preview, setPreview] = useState<ReportPreview | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)

  const reports = useResource(() => unwrap(api.reportsList()), [job?.endedAt], { intervalMs: 20000 })

  const groups = useMemo(() => {
    const list = reports.data ?? []
    const q = query.trim().toLowerCase()
    return q ? list.filter((g) => `${g.title} ${g.dir}`.toLowerCase().includes(q)) : list
  }, [reports.data, query])

  const active = groups.find((g) => g.key === sel) ?? groups[0] ?? null

  const openPreview = async (path: string): Promise<void> => {
    setLoadingPreview(true)
    setPreview(null)
    try {
      setPreview(await unwrap(api.reportsPreview(path)))
    } catch (err) {
      pushToast({ tone: 'error', title: 'Rapor okunamadi', message: String(err) })
    } finally {
      setLoadingPreview(false)
    }
  }

  return (
    <div className="grid gap-3.5 xl:grid-cols-[340px_1fr]">
      <Panel className="overflow-hidden">
        <div className="border-b border-border p-3.5">
          <SectionTitle
            title="Cikti dosyalari"
            subtitle={`${groups.length} is klasoru`}
            icon={<FolderOpen className="size-4" />}
            right={
              <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', reports.loading && 'animate-spin')} />} onClick={() => reports.reload()} />
            }
          />
          <div className="relative mt-3">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-fg-subtle" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Baslik veya klasor ara..." className="h-8 pl-8 text-[12px]" />
          </div>
        </div>
        <div className="max-h-[calc(100vh-230px)] overflow-y-auto">
          {reports.loading && !reports.data ? (
            <div className="flex items-center justify-center gap-2 py-14 text-[12px] text-fg-subtle">
              <Spinner /> Masaustu taraniyor...
            </div>
          ) : groups.length === 0 ? (
            <EmptyState icon={<FolderOpen className="size-6" />} title="Cikti bulunamadi" message="Masaustunde _CLEAN.mp4, _VOICEOVER.mp3, _SEO.html veya Kesif-Rapor dosyasi yok." />
          ) : (
            groups.map((g) => (
              <button
                key={g.key}
                onClick={() => {
                  setSel(g.key)
                  setPreview(null)
                }}
                className={cn(
                  'w-full border-b border-border/60 px-3.5 py-2.5 text-left transition-colors last:border-0',
                  active?.key === g.key ? 'bg-brand-soft' : 'hover:bg-[var(--surface-2)]',
                )}
              >
                <p className={cn('truncate text-[12.5px] font-medium', active?.key === g.key ? 'text-brand' : 'text-fg')} title={g.title}>
                  {g.title || 'Isimsiz is'}
                </p>
                <div className="mt-1 flex items-center gap-2 text-[10.5px] text-fg-subtle">
                  <span>{formatBytes(g.totalBytes)}</span>
                  <span>·</span>
                  <span>{formatRelative(g.mtime)}</span>
                  <span className="ml-auto flex gap-1">
                    {g.items.map((i) => (
                      <span key={i.path} className="text-fg-subtle/80">
                        <Icon kind={i.kind} />
                      </span>
                    ))}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </Panel>

      {!active ? (
        <Panel className="p-6">
          <EmptyState icon={<FileText className="size-7" />} title="Soldan bir is secin" message="Secilen isin tum ciktilari (video, ses, kapak, SEO raporu) burada gorunur." />
        </Panel>
      ) : (
        <div className="space-y-3.5">
          <Panel className="p-4">
            <SectionTitle title={active.title || 'Is'} subtitle={active.dir} icon={<FileText className="size-4" />} />
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {active.items.map((item) => (
                <div key={item.path} className="rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-fg-muted">
                      <Icon kind={item.kind as Artifact['kind']} />
                    </span>
                    <span className="text-[11.5px] font-medium text-fg-muted">{ARTIFACT_LABEL[item.kind] ?? item.kind}</span>
                    <span className="num ml-auto text-[10.5px] text-fg-subtle">{formatBytes(item.size)}</span>
                  </div>
                  <p className="mt-1 truncate font-mono text-[11px] text-fg" title={item.path}>
                    {item.name}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Button size="sm" icon={<Eye className="size-3.5" />} onClick={() => void api.shellOpen(item.path)}>
                      Ac
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void api.shellReveal(item.path)}>
                      Klasorde goster
                    </Button>
                    {item.kind === 'seo' ? (
                      <Button size="sm" variant="outline" loading={loadingPreview} onClick={() => void openPreview(item.path)}>
                        Onizle
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          {preview || loadingPreview ? (
            <Panel className="p-4">
              <SectionTitle title="SEO raporu onizlemesi" subtitle={preview?.ok ? preview.title || 'baslik yok' : 'yukleniyor'} icon={<FileText className="size-4" />} />
              {loadingPreview ? (
                <div className="flex items-center gap-2 py-8 text-[12px] text-fg-subtle">
                  <Spinner /> Rapor okunuyor...
                </div>
              ) : preview?.ok ? (
                <div className="mt-3 space-y-2.5">
                  {preview.headings?.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {preview.headings.map((h, i) => (
                        <Badge key={`${h}-${i}`} tone="brand">
                          {h.slice(0, 40)}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                  {preview.sections?.length ? (
                    <div className="grid gap-2 lg:grid-cols-2">
                      {preview.sections.map((sec, i) => (
                        <div key={`${sec.label}-${i}`} className="rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2.5">
                          <p className="text-[10.5px] font-semibold tracking-wide text-fg-subtle uppercase">{sec.label}</p>
                          <p
                            className="mt-1 max-h-40 overflow-y-auto text-[11.5px] leading-relaxed whitespace-pre-wrap text-fg"
                            data-selectable
                          >
                            {sec.text || '—'}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <pre className="max-h-72 overflow-y-auto rounded-[10px] border border-border bg-[var(--canvas)]/45 p-3 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap text-fg-muted" data-selectable>
                      {preview.text}
                    </pre>
                  )}
                </div>
              ) : (
                <p className="mt-2 text-[12px] text-danger">{preview?.error ?? 'Okunamadi'}</p>
              )}
            </Panel>
          ) : null}
        </div>
      )}
    </div>
  )
}
