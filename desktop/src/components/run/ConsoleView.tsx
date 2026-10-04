import { useMemo, useState, type ReactNode } from 'react'
import { ArrowDownToLine, Copy, Search, TerminalSquare, Trash2 } from 'lucide-react'
import type { LogLevel, LogLine } from '@shared/types'
import { cn } from '@/lib/utils'
import { useAutoScroll, useCopy, useTicker } from '@/lib/hooks'
import { IconButton, Input } from '@/components/ui/primitives'

/** Seviye -> yazi rengi (metin ve glif). */
const LEVEL_TEXT: Record<LogLevel, string> = {
  info: 'text-fg-muted',
  ok: 'text-success',
  warn: 'text-warn',
  err: 'text-danger',
  step: 'text-brand-text font-semibold',
  ai: 'text-cyan',
  gpu: 'text-violet',
  tts: 'text-ember',
  raw: 'text-fg-subtle',
}

/** Seviye -> sol accent cizgisi. */
const LEVEL_BAR: Record<LogLevel, string> = {
  info: 'border-l-transparent',
  ok: 'border-l-success',
  warn: 'border-l-warn',
  err: 'border-l-danger',
  step: 'border-l-brand',
  ai: 'border-l-cyan',
  gpu: 'border-l-violet',
  tts: 'border-l-ember',
  raw: 'border-l-transparent',
}

/** Seviye -> satir arka plani (hata/uyarilar hafifce one cikar). */
const LEVEL_BG: Record<LogLevel, string> = {
  info: '',
  ok: '',
  warn: 'bg-[var(--warn-soft)]',
  err: 'bg-[var(--danger-soft)]',
  step: 'bg-[var(--brand-soft)]',
  ai: '',
  gpu: '',
  tts: '',
  raw: '',
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

/** Renklendirilecek tokenlar: URL'ler, dosya adlari/yollari ve oklar. */
const TOKEN_RE = /(https?:\/\/[^\s]+|(?:[A-Za-z]:\\|\/)[^\s]*?\.\w+|[\w][\w.-]*\.(?:py|json|mp4|html|srt|txt|wav|mp3|db|ckpt)|✅|❌|⚠️)/g

function highlight(text: string): ReactNode {
  if (!TOKEN_RE.test(text)) return text
  TOKEN_RE.lastIndex = 0
  const parcalar: ReactNode[] = []
  let son = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = TOKEN_RE.exec(text)) !== null) {
    if (m.index > son) parcalar.push(text.slice(son, m.index))
    const tok = m[0]
    let cls = 'text-brand-hi'
    if (/^https?:\/\//.test(tok)) cls = 'text-cyan underline decoration-cyan/40 underline-offset-2'
    else if (/^✅|^✓/.test(tok)) cls = 'text-success'
    else if (/^❌|^✕/.test(tok)) cls = 'text-danger'
    else if (/^⚠️/.test(tok)) cls = 'text-warn'
    parcalar.push(
      <span key={`t${i++}`} className={cls}>
        {tok}
      </span>,
    )
    son = m.index + tok.length
  }
  if (son < text.length) parcalar.push(text.slice(son))
  return parcalar
}

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
  const hatalar = useMemo(() => lines.reduce((n, l) => (l.level === 'err' ? n + 1 : n), 0), [lines])

  return (
    <div className={cn('panel flex flex-col overflow-hidden', className)}>
      {/* Terminal basligi: kirmizi/sari/yesil noktalar + canli durum */}
      <div className="flex items-center gap-2 border-b border-border bg-[var(--surface-2)] px-2.5 py-2">
        <div className="hidden items-center gap-[5px] pr-1 sm:flex" aria-hidden>
          <span className="size-[9px] rounded-full bg-[#ff5f57]" />
          <span className="size-[9px] rounded-full bg-[#febc2e]" />
          <span className="size-[9px] rounded-full bg-[#28c840]" />
        </div>
        <div className="flex items-center gap-1.5 text-fg-subtle">
          <TerminalSquare className="size-3.5 text-brand" />
          <span className="font-mono text-[11px] tracking-tight">videoforge · konsol</span>
        </div>
        {live ? (
          <span className="flex items-center gap-1.5 rounded-full bg-[var(--success-soft)] px-2 py-[1px] text-[10.5px] font-medium text-success">
            <span className="size-1.5 animate-pulse-soft rounded-full bg-success" />
            canlı
          </span>
        ) : lines.length > 0 ? (
          <span className="rounded-full bg-[var(--surface-3)] px-2 py-[1px] text-[10.5px] text-fg-subtle">
            {hatalar > 0 ? `${hatalar} hata` : 'bitti'}
          </span>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden items-center gap-1 md:flex">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={cn(
                  'rounded-[7px] px-2 py-1 text-[11.5px] font-medium transition-colors',
                  filter === f.key ? 'bg-brand-soft text-brand-text' : 'text-fg-subtle hover:bg-[var(--surface-2)] hover:text-fg-muted',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="relative w-40 lg:w-52">
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
      </div>

      <div
        ref={scrollRef}
        className={cn('overflow-y-auto bg-[var(--canvas)] px-1.5 py-2 font-mono text-[11.5px] leading-[1.6]', height)}
        data-selectable
      >
        {visible.length === 0 ? (
          <div className="flex flex-col items-center gap-1.5 px-1 py-10 text-center">
            <TerminalSquare className="size-6 text-fg-subtle/50" />
            <p className="text-[12px] text-fg-subtle">Gösterilecek kayıt yok.</p>
            <p className="font-mono text-[11px] text-fg-subtle/70">$ bot çıktısı burada canlı akar…</p>
          </div>
        ) : (
          visible.map((line) => (
            <div
              key={line.i}
              className={cn(
                'group flex gap-2 border-l-2 py-[1px] pr-2 pl-2 whitespace-pre-wrap transition-colors hover:bg-[var(--surface-2)]',
                LEVEL_BAR[line.level],
                LEVEL_BG[line.level],
              )}
            >
              <span className="num shrink-0 select-none text-fg-subtle/60 tabular-nums">
                {new Date(line.t).toLocaleTimeString('tr-TR', { hour12: false })}
              </span>
              <span className={cn('w-3 shrink-0 text-center select-none', LEVEL_TEXT[line.level])}>{LEVEL_GLYPH[line.level]}</span>
              <span className={cn('flex-1 break-words', LEVEL_TEXT[line.level])}>{highlight(line.text)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
