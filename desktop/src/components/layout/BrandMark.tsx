import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function BrandMark({ className, size = 26 }: { className?: string; size?: number }): ReactNode {
  return (
    <span
      className={cn(
        'grid shrink-0 place-items-center rounded-[8px] border border-[color-mix(in_oklab,var(--brand)_35%,transparent)]',
        'bg-[linear-gradient(145deg,color-mix(in_oklab,var(--brand)_28%,transparent),transparent)]',
        className,
      )}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 24 24" width={size * 0.62} height={size * 0.62} aria-hidden="true">
        <defs>
          <linearGradient id="vf-flame" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--brand)" />
            <stop offset="55%" stopColor="var(--brand-hi)" />
            <stop offset="100%" stopColor="var(--cyan)" />
          </linearGradient>
        </defs>
        <path
          fill="url(#vf-flame)"
          d="M12 2.6c.5 2.6 2.5 3.6 3.7 5.6 1.2 2 .8 4.1-.6 5.2-.5-1.7-1.7-2.6-2.6-3.6-.3 1.6-1.1 2.5-2 3.4-1.2 1.2-1.6 2.6-1.1 3.9.4 1 .3 1.9-.6 2.7-2.6-1.2-4.4-3.7-4.4-6.6 0-3.6 2.7-5.7 4-8 .9-1.6 1.6-2.7 3.6-2.6Z"
        />
        <path fill="var(--brand-hi)" opacity="0.85" d="M13.6 14.1c1.6 1 2.1 2.4 1.6 3.8-.4 1.1-1.4 1.9-2.9 2.2 1.5-1.4 1.6-2.9.4-4.3-.5-.6-.5-1.3.9-1.7Z" />
      </svg>
    </span>
  )
}
