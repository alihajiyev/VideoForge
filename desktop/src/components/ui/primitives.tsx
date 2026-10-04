import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
type ButtonSize = 'sm' | 'md' | 'lg'

/**
 * YouTube gorunumu: dolu butonlar hap (pill) seklinde ve dolgusuz/ince kenarli
 * ikincil butonlar kullanilir. Birincil renk YouTube kirmizisi + beyaz metin.
 */
const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-brand text-white hover:bg-brand-hi border border-transparent',
  secondary: 'bg-[var(--surface-2)] text-fg border border-transparent hover:bg-[var(--surface-3)]',
  ghost: 'bg-transparent text-fg-muted hover:text-fg hover:bg-[var(--surface-2)] border border-transparent',
  danger: 'bg-danger-soft text-danger border border-transparent hover:bg-danger hover:text-white',
  outline: 'bg-transparent text-fg border border-border-strong hover:bg-[var(--surface-2)]',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-[12px] gap-1.5 rounded-full',
  md: 'h-9 px-3.5 text-[13px] gap-2 rounded-full',
  lg: 'h-11 px-5 text-[13.5px] gap-2 rounded-full',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps): ReactNode {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center font-medium transition-all duration-150 select-none',
        'disabled:cursor-not-allowed disabled:opacity-45 active:scale-[0.985]',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" /> : icon}
      {children}
    </button>
  )
}

/** YouTube ikon butonu: daire uzerinde hover dolgusu. */
export function IconButton({
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>): ReactNode {
  return (
    <button
      className={cn(
        'grid size-9 place-items-center rounded-full text-fg transition-colors',
        'hover:bg-[var(--surface-3)] disabled:opacity-40',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}

export function Panel({
  className,
  children,
  flat = false,
}: {
  className?: string
  children: ReactNode
  flat?: boolean
}): ReactNode {
  return <div className={cn(flat ? 'panel-flat' : 'panel', className)}>{children}</div>
}

export function SectionTitle({
  title,
  subtitle,
  right,
  icon,
}: {
  title: string
  subtitle?: string
  right?: ReactNode
  icon?: ReactNode
}): ReactNode {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex min-w-0 items-center gap-2.5">
        {icon ? <span className="shrink-0 text-fg-subtle">{icon}</span> : null}
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold tracking-[-0.01em] text-fg">{title}</h2>
          {subtitle ? <p className="mt-0.5 truncate text-[12px] text-fg-muted">{subtitle}</p> : null}
        </div>
      </div>
      {right ? <div className="shrink-0">{right}</div> : null}
    </div>
  )
}

type Tone = 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'cyan' | 'violet'

/** YouTube chip rozetleri: cercevesiz, dolgulu, hap. */
const TONES: Record<Tone, string> = {
  neutral: 'bg-[var(--surface-3)] text-fg-muted',
  brand: 'bg-brand-soft text-brand',
  success: 'bg-success-soft text-success',
  warn: 'bg-warn-soft text-warn',
  danger: 'bg-danger-soft text-danger',
  cyan: 'bg-cyan-soft text-cyan',
  violet: 'bg-[color-mix(in_oklab,var(--violet)_15%,transparent)] text-violet',
}

export function Badge({
  tone = 'neutral',
  children,
  className,
  dot = false,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
  dot?: boolean
}): ReactNode {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-[3px] text-[11.5px] font-medium whitespace-nowrap',
        TONES[tone],
        className,
      )}
    >
      {dot ? <span className="size-1.5 rounded-full bg-current" /> : null}
      {children}
    </span>
  )
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>): ReactNode {
  return (
    <input
      className={cn(
        'h-9 w-full rounded-[8px] border border-border bg-[var(--surface-2)] px-3 text-[13px] text-fg',
        'placeholder:text-fg-subtle transition-colors focus:border-cyan focus:outline-none',
        className,
      )}
      {...rest}
    />
  )
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>): ReactNode {
  return (
    <select
      className={cn(
        'h-9 w-full appearance-none rounded-[8px] border border-border bg-[var(--surface-2)] px-3 text-[13px] text-fg',
        'transition-colors focus:border-cyan focus:outline-none',
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  )
}

export function Switch({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label?: string
  hint?: string
  disabled?: boolean
}): ReactNode {
  return (
    <label className={cn('flex items-center gap-3', disabled && 'opacity-50')}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-5 w-9 shrink-0 rounded-full transition-colors',
          checked ? 'bg-cyan' : 'bg-[var(--surface-3)]',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 size-4 rounded-full bg-white shadow transition-all',
            checked ? 'left-[20px]' : 'left-0.5',
          )}
        />
      </button>
      {label ? (
        <span className="leading-tight">
          <span className="block text-[13px] text-fg">{label}</span>
          {hint ? <span className="block text-[11.5px] text-fg-subtle">{hint}</span> : null}
        </span>
      ) : null}
    </label>
  )
}

export function Progress({ value, tone = 'brand' }: { value: number; tone?: 'brand' | 'cyan' | 'success' }): ReactNode {
  const pct = Math.max(0, Math.min(100, value))
  const bar = tone === 'brand' ? 'bg-brand' : tone === 'cyan' ? 'bg-cyan' : 'bg-success'
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-3)]">
      <div className={cn('h-full rounded-full transition-all duration-500', bar)} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string
  value: ReactNode
  hint?: string
  icon?: ReactNode
  /** Geriye donuk uyumluluk icin kabul edilir; gorsel renk kullanilmaz. */
  tone?: Tone
}): ReactNode {
  return (
    <Panel className="px-4 py-3">
      <div className="flex items-center gap-2 text-fg-muted">
        {icon ? <span className="shrink-0">{icon}</span> : null}
        <span className="truncate text-[12px] font-medium">{label}</span>
      </div>
      <div className="num mt-1 text-[21px] leading-tight font-semibold tracking-[-0.02em] text-fg">{value}</div>
      {hint ? <div className="mt-0.5 text-[11.5px] text-fg-subtle">{hint}</div> : null}
    </Panel>
  )
}

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon?: ReactNode
  title: string
  message?: string
  action?: ReactNode
}): ReactNode {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-6 py-10 text-center">
      {icon ? <div className="mb-1 text-fg-subtle opacity-60">{icon}</div> : null}
      <p className="text-[14px] font-medium text-fg">{title}</p>
      {message ? <p className="max-w-sm text-[12px] leading-relaxed text-fg-muted">{message}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}

export function Spinner({ className }: { className?: string }): ReactNode {
  return <Loader2 className={cn('size-4 animate-spin text-fg-subtle', className)} />
}

export function KeyValue({ label, value, mono = true }: { label: string; value: ReactNode; mono?: boolean }): ReactNode {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5">
      <span className="shrink-0 text-[12px] text-fg-subtle">{label}</span>
      <span className={cn('text-right text-[12px] text-fg', mono && 'font-mono text-[11.5px]')}>{value}</span>
    </div>
  )
}
