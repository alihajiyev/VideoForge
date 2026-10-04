import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * VideoForge logosu — YouTube oynat butonu tarzi: kirmizi dolgu + beyaz ucgen.
 * Uygulamanin her yerinde AYNI gorsel kullanilir (baslik cubugu, komut paleti).
 * Vektor cizilir; masaustu kisayol ikonu icin desktop/public/logo.png kullanilir.
 */
export function BrandMark({ className, size = 26 }: { className?: string; size?: number }): ReactNode {
  return (
    <span
      className={cn('inline-grid shrink-0 place-items-center', className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label="VideoForge"
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 36 26"
        preserveAspectRatio="xMidYMid meet"
        className="block"
        aria-hidden="true"
      >
        <rect width="36" height="26" rx="6.5" fill="var(--brand)" />
        <path d="M14.2 7.4 L24.2 13 L14.2 18.6 Z" fill="#fff" />
      </svg>
    </span>
  )
}
