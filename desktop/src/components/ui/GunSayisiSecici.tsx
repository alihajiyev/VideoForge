import type { ReactNode } from 'react'
import { GUN_SAYISI_MAX, GUN_SAYISI_MIN, normalGunSayisi } from '@shared/constants'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/primitives'

/** Hazir secenekler (tiklayinca gecerli aralikta dogrudan ayarlanir). */
const HAZIR_GUNLER = [3, 7, 10, 14, 30]

/**
 * Cok gunlu plan icin gun sayisi secici (Panel ve Kesif sayfalari ayni bileseni
 * kullanir; deger ayarlarda saklandigi icin iki sayfada da ayni sayi gorunur).
 *
 * `onChange(gun, kaydet)` => kaydet=true iken secim diske yazilir (blur veya
 * hazir secenek tiklamasi). Yazarken her tus vurusunda dosya yazilmaz.
 */
export function GunSayisiSecici({
  value,
  onChange,
  disabled = false,
  id = 'gun-sayisi',
  className,
  hint = true,
}: {
  value: number
  onChange: (gun: number, kaydet: boolean) => void
  disabled?: boolean
  id?: string
  className?: string
  hint?: boolean
}): ReactNode {
  const gun = normalGunSayisi(value)
  return (
    <div className={className}>
      <label className="text-[11.5px] font-medium text-fg-muted" htmlFor={id}>
        Kaç günlük plan?
      </label>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <Input
          id={id}
          type="number"
          inputMode="numeric"
          min={GUN_SAYISI_MIN}
          max={GUN_SAYISI_MAX}
          value={value}
          disabled={disabled}
          aria-label="Kaç günlük plan"
          onChange={(e) => onChange(Number(e.target.value), false)}
          onBlur={() => onChange(gun, true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onChange(gun, true)
          }}
          className="w-[80px] text-center"
        />
        {HAZIR_GUNLER.map((n) => (
          <button
            key={n}
            type="button"
            disabled={disabled}
            aria-pressed={n === gun}
            onClick={() => onChange(n, true)}
            className={cn(
              'num rounded-[8px] border px-2 py-1 text-[11px] transition-colors disabled:opacity-50',
              n === gun
                ? 'border-brand bg-brand-soft text-fg'
                : 'border-border bg-[var(--surface-2)] text-fg-muted hover:border-border-strong',
            )}
          >
            {n}
          </button>
        ))}
      </div>
      {hint ? (
        <p className="mt-1 text-[10.5px] leading-relaxed text-fg-subtle">
          {gun} video üretilir; skor sırası = paylaşım sırası ({GUN_SAYISI_MIN}-{GUN_SAYISI_MAX}).
        </p>
      ) : null}
    </div>
  )
}
