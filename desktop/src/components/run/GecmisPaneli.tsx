import { useState, type ReactNode } from 'react'
import { ChevronDown, Clock, FolderOpen, History } from 'lucide-react'
import { api } from '@/lib/api'
import { useApp } from '@/app/AppContext'
import { Badge, Button, Panel, SectionTitle } from '@/components/ui/primitives'
import { ARTIFACT_LABEL, formatBytes, formatRelative, formatUsd, KIND_LABEL, maliyetUsd, cn } from '@/lib/utils'

const DURUM_TONE = { done: 'success', error: 'danger', cancelled: 'warn', running: 'brand' } as const
const DURUM_LABEL: Record<string, string> = {
  done: 'tamamlandı',
  error: 'hata',
  cancelled: 'durduruldu',
  running: 'çalışıyor',
}

function sureYaz(ms: number | null): string {
  if (!ms || ms <= 0) return '—'
  const sn = Math.round(ms / 1000)
  const dk = Math.floor(sn / 60)
  if (dk > 0) return `${dk}dk ${sn % 60}sn`
  return `${sn}sn`
}

/**
 * Gecmis paneli: kalici is gecmisi. Bir ise tiklayinca cikti dosyalari, maliyet
 * ve sure ayrintisi acilir. Bot koduna dokunmaz; ana surecte gecmis.json tutulur.
 */
export function GecmisPaneli(): ReactNode {
  const { history } = useApp()
  const [acik, setAcik] = useState<string | null>(null)

  return (
    <Panel className="p-3">
      <SectionTitle title="Geçmiş" subtitle="Son işler · ayrıntı için tıkla" icon={<History className="size-4" />} />
      <div className="mt-2 space-y-1.5">
        {history.length === 0 ? (
          <p className="py-3 text-center text-[11.5px] text-fg-subtle">Kayıt yok</p>
        ) : (
          history.map((item) => {
            const acikMi = acik === item.id
            const usd = maliyetUsd(item.cost)
            return (
              <div key={item.id} className="rounded-[9px] border border-border bg-[var(--surface-2)]">
                <button
                  onClick={() => setAcik(acikMi ? null : item.id)}
                  className="flex w-full items-center gap-2 px-2.5 py-2 text-left"
                  aria-expanded={acikMi}
                >
                  <span
                    className={cn(
                      'size-1.5 shrink-0 rounded-full',
                      item.status === 'done'
                        ? 'bg-success'
                        : item.status === 'running'
                          ? 'bg-brand'
                          : item.status === 'cancelled'
                            ? 'bg-warn'
                            : 'bg-danger',
                    )}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[11.5px] text-fg" title={item.title}>
                      {item.title}
                    </span>
                    <span className="block text-[10.5px] text-fg-subtle">
                      {formatRelative(item.startedAt)} · {sureYaz(item.durationMs)} · {KIND_LABEL[item.kind] ?? item.kind}
                    </span>
                  </span>
                  <ChevronDown className={cn('size-3.5 shrink-0 text-fg-subtle transition-transform', acikMi && 'rotate-180')} />
                </button>
                {acikMi ? (
                  <div className="border-t border-border px-2.5 py-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={DURUM_TONE[item.status] ?? 'neutral'}>{DURUM_LABEL[item.status] ?? item.status}</Badge>
                      <Badge tone="neutral">
                        <Clock className="size-3" /> {sureYaz(item.durationMs)}
                      </Badge>
                      {usd !== null ? <Badge tone="cyan">{formatUsd(usd)}</Badge> : null}
                      {item.exitCode !== null ? <Badge tone="neutral">çıkış {item.exitCode}</Badge> : null}
                    </div>
                    {item.artifacts.length === 0 ? (
                      <p className="mt-2 text-[11px] text-fg-subtle">Bu iş için çıktı dosyası kaydedilmedi.</p>
                    ) : (
                      <div className="mt-2 space-y-1">
                        {item.artifacts.map((a) => (
                          <div key={a.path} className="flex items-center gap-2 text-[11px]">
                            <span className="truncate text-fg" title={a.path}>
                              {a.name}
                            </span>
                            <span className="shrink-0 text-fg-subtle">
                              {ARTIFACT_LABEL[a.kind] ?? a.kind} · {formatBytes(a.size)}
                            </span>
                            <span className="ml-auto flex shrink-0 gap-1">
                              <Button size="sm" variant="ghost" onClick={() => void api.shellOpen(a.path)}>
                                Aç
                              </Button>
                              <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3" />} onClick={() => void api.shellReveal(a.path)} />
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )
          })
        )}
      </div>
    </Panel>
  )
}
