import { useMemo, useState, type ReactNode } from 'react'
import { ArrowDownToLine, Copy, Search, Trash2 } from 'lucide-react'
import type { LogLevel, LogLine } from '@shared/types'
import { cn } from '@/lib/utils'
import { useAutoScroll, useCopy, useTicker } from '@/lib/hooks'
import { IconButton, Input } from '@/components/ui/primitives'

const LEVEL_CLASS: Record<LogLevel, string> = {
  info: 'text-fg-muted',
  ok: 'text-success',
  warn: 'text-warn',
  err: 'text-danger',
  step: 'text-brand font-semibold',
  ai: 'text-cyan',
  gpu: 'text-violet',
  tts: 'text-ember',
  raw: 'text-fg-subtle',
}

const LEVEL_GLYPH: Record<LogLevel, string> = {
  info: '›',
  ok: '✓',
  warn: '!',
  err: '✕',
  step: '▸',
  ai: '◆',
  gpu: '▲',
  tts: '♪',
  raw: ' ',
}

const FILTERS: { key: 'all' | 'important' | 'errors'; label: string }[] = [
  { key: 'all', label: 'Tümü' },
  { key: 'important', label: 'Önemli' },
  { key: 'errors', label: 'Sadece hata' },
]

export function ConsoleView({
  lines,
  className,
  live = false,
  height = 'h-[420px]',
  onClear,
}: {
  lines: LogLine[]
  className?: string
  live?: boolean
  height?: string
  onClear?: () => void
}): ReactNode {
  const [filter, setFilter] = useState<'all' | 'important' | 'errors'>('all')
  const [query, setQuery] = useState('')
  const [copied, copy] = useCopy()
  useTicker(live)
  const scrollRef = useAutoScroll<HTMLDivElement>(lines.length, live)

  const visible = useMemo(() => {
    let out = lines
    if (filter === 'important') out = out.filter((l) => l.level !== 'info' && l.level !== 'raw')
    if (filter === 'errors') out = out.filter((l) => l.level === 'err' || l.level === 'warn')
    const q = query.trim().toLowerCase()
    if (q) out = out.filter((l) => l.text.toLowerCase().includes(q))
    return out.slice(-2000)
  }, [lines, filter, query])

  const text = useMemo(() => visible.map((l) => l.text).join('\n'), [visible])

  return (
    <div className={cn('panel flex flex-col overflow-hidden', className)}>
      <div className="flex items-center gap-2 border-b border-border px-2.5 py-2">
        <div className="flex items-center gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                'rounded-[7px] px-2 py-1 text-[11.5px] font-medium transition-colors',
                filter === f.key ? 'bg-brand-soft text-brand' : 'text-fg-subtle hover:bg-[var(--surface-2)] hover:text-fg-muted',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-52">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-fg-subtle" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Kayıtlarda ara..."
            className="h-8 pl-8 text-[12px]"
          />
        </div>
        <IconButton onClick={() => copy(text)} title="Kayıtları kopyala">
          <Copy className={cn('size-3.5', copied && 'text-success')} />
        </IconButton>
        {onClear ? (
          <IconButton onClick={onClear} title="Temizle">
            <Trash2 className="size-3.5" />
          </IconButton>
        ) : null}
        {live ? (
          <IconButton onClick={() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight }} title="En alta in">
            <ArrowDownToLine className="size-3.5" />
          </IconButton>
        ) : null}
      </div>

      <div ref={scrollRef} className={cn('overflow-y-auto bg-[var(--canvas)]/40 px-2.5 py-2 font-mono text-[11.5px] leading-[1.65]', height)} data-selectable>
        {visible.length === 0 ? (
          <p className="px-1 py-6 text-center text-[12px] text-fg-subtle">Gösterilecek kayıt yok.</p>
        ) : (
          visible.map((line) => (
            <div key={line.i} className="flex gap-2 whitespace-pre-wrap">
              <span className="num shrink-0 text-fg-subtle/70">
                {new Date(line.t).toLocaleTimeString('tr-TR', { hour12: false })}
              </span>
              <span className={cn('w-3 shrink-0 text-center', LEVEL_CLASS[line.level])}>{LEVEL_GLYPH[line.level]}</span>
              <span className={cn('flex-1 break-words', LEVEL_CLASS[line.level])}>{line.text}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
