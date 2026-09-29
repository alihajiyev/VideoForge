import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * VideoForge logosu. Uygulamanin her yerinde AYNI gorsel kullanilir:
 * baslik cubugu, acilis ekrani ve favicon (bkz. desktop/public/logo.png).
 *
 * Yol kasten RELATIF ('./logo.png'): paketli uygulamada sayfa `file://`
 * ile aciliyor ve '/logo.png' surucu kokune kacardi.
 */
export function BrandMark({ className, size = 26 }: { className?: string; size?: number }): ReactNode {
  return (
    <span
      className={cn(
        'grid shrink-0 place-items-center overflow-hidden rounded-[8px] border border-[color-mix(in_oklab,var(--brand)_35%,transparent)]',
        'bg-[linear-gradient(145deg,color-mix(in_oklab,var(--brand)_28%,transparent),transparent)]',
        className,
      )}
      style={{ width: size, height: size }}
    >
      <img src="./logo.png" alt="VideoForge" width={size} height={size} className="size-full object-cover" draggable={false} />
    </span>
  )
}
