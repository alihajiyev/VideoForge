import { useMemo, useState, type ReactNode } from 'react'
import { ExternalLink, RefreshCw, ScrollText, Search } from 'lucide-react'
import { api, unwrap } from '@/lib/api'
import { useResource } from '@/lib/hooks'
import { cn, formatBytes, formatRelative } from '@/lib/utils'
import { Badge, Button, EmptyState, Input, Panel, SectionTitle, Select, Spinner } from '@/components/ui/primitives'

export function LogsPage(): ReactNode {
  const [tail, setTail] = useState(800)
  const [query, setQuery] = useState('')
  const [live, setLive] = useState(true)

  const log = useResource(() => unwrap(api.logsRead(tail, query)), [tail, query], { intervalMs: live ? 5000 : 0 })

  const highlighted = useMemo(() => log.data?.lines ?? [], [log.data])

  return (
    <div className="space-y-3.5">
      <Panel className="p-4">
        <SectionTitle
          title="bot_log.txt"
          subtitle={log.data?.ok ? `${log.data.totalLines} satir · ${formatBytes(log.data.size)} · ${formatRelative(log.data.mtime)}` : 'Log dosyasi okunuyor'}
          icon={<ScrollText className="size-4" />}
          right={
            <div className="flex items-center gap-2">
              <Select value={String(tail)} onChange={(e) => setTail(Number(e.target.value))} className="h-8 w-32 text-[12px]">
                <option value="200">Son 200</option>
                <option value="800">Son 800</option>
                <option value="2000">Son 2000</option>
                <option value="5000">Son 5000</option>
              </Select>
              <Button size="sm" variant={live ? 'primary' : 'secondary'} onClick={() => setLive((v) => !v)}>
                {live ? 'Canli' : 'Duraklatildi'}
              </Button>
              <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', log.loading && 'animate-spin')} />} onClick={() => log.reload()} />
              <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />} onClick={() => void api.shellOpen(log.data?.path ?? '')} />
            </div>
          }
        />
        <div className="relative mt-3">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-fg-subtle" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Log icinde ara (orn. PROHIBITED, hata, GPU)" className="h-8 pl-8 text-[12px]" />
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        {log.loading && !log.data ? (
          <div className="flex items-center justify-center gap-2 py-14 text-[12px] text-fg-subtle">
            <Spinner /> Log okunuyor...
          </div>
        ) : !log.data?.ok ? (
          <EmptyState
            icon={<ScrollText className="size-6" />}
            title="Log dosyasi bulunamadi"
            message={log.data?.error ?? 'Bot ilk kez calistiginda bot_log.txt olusur.'}
          />
        ) : highlighted.length === 0 ? (
          <EmptyState icon={<Search className="size-6" />} title="Eslesen satir yok" message="Arama terimini degistirin." />
        ) : (
          <div className="max-h-[calc(100vh-320px)] overflow-y-auto px-3 py-2 font-mono text-[11.5px] leading-[1.7]" data-selectable>
            {highlighted.map((line, idx) => {
              const level = /✕|❌|hata|error/i.test(line)
                ? 'text-danger'
                : /⚠️|uyari|warn/i.test(line)
                  ? 'text-warn'
                  : /✅|✓/i.test(line)
                    ? 'text-success'
                    : /Gemini|🤖/i.test(line)
                      ? 'text-cyan'
                      : /GPU|⚡|ProPainter/i.test(line)
                        ? 'text-violet'
                        : 'text-fg-muted'
              return (
                <div key={`${idx}-${line.slice(0, 12)}`} className={cn('break-words whitespace-pre-wrap', level)}>
                  {line || ' '}
                </div>
              )
            })}
          </div>
        )}
      </Panel>

      <Panel className="flex flex-wrap items-center gap-3 px-4 py-3 text-[11.5px] text-fg-subtle">
        <Badge tone="neutral">dosya: {log.data?.path ?? '—'}</Badge>
        <span>Oturum ayraci satirlari (=====) her bot baslangicinda eklenir.</span>
      </Panel>
    </div>
  )
}
