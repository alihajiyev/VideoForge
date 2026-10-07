import type { ReactNode } from 'react'
import type { KlipKirilim } from '@shared/types'
import { cn } from '@/lib/utils'

/** Skor 0-100 halka gostergesi (Opus tarzi). */
export function SkorHalkasi({
  skor,
  boyut = 56,
  etiket,
}: {
  skor: number
  boyut?: number
  etiket?: string
}): ReactNode {
  const deger = Math.max(0, Math.min(100, Number(skor) || 0))
  const yaricap = (boyut - 6) / 2
  const cevre = 2 * Math.PI * yaricap
  const renk = deger >= 85 ? 'var(--success)' : deger >= 70 ? 'var(--warn)' : 'var(--danger)'
  return (
    <div className="relative shrink-0" style={{ width: boyut, height: boyut }} title={`Skor ${deger.toFixed(1)}/100`}>
      <svg width={boyut} height={boyut} className="-rotate-90">
        <circle cx={boyut / 2} cy={boyut / 2} r={yaricap} fill="none" stroke="var(--surface-3)" strokeWidth={4} />
        <circle
          cx={boyut / 2}
          cy={boyut / 2}
          r={yaricap}
          fill="none"
          stroke={renk}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={cevre}
          strokeDashoffset={cevre * (1 - deger / 100)}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className="num text-[13px] leading-none font-semibold text-fg">{Math.round(deger)}</span>
        {etiket ? <span className="mt-0.5 text-[9px] text-fg-subtle">{etiket}</span> : null}
      </div>
    </div>
  )
}

interface BarTanimi {
  anahtar: keyof KlipKirilim
  etiket: string
  ipucu: string
  olcek: number
}

const KONUSMA_BARLAR: BarTanimi[] = [
  { anahtar: 'hook_acilis', etiket: 'Hook (açılış)', ipucu: 'Klibin ilk saniyelerindeki kanca cümlesi gücü', olcek: 1 },
  { anahtar: 'hook', etiket: 'Hook (ortalama)', ipucu: 'Kesitlerdeki merak/soru/hitap yoğunluğu', olcek: 1 },
  { anahtar: 'bilgi', etiket: 'Bilgi', ipucu: 'Sayı, tarih, özel isim yoğunluğu', olcek: 1 },
  { anahtar: 'nadirlik', etiket: 'Nadirlik', ipucu: 'Videoda az geçen (özgün) kelimeler', olcek: 1 },
  { anahtar: 'vurgu', etiket: 'Ses vurgusu', ipucu: 'Konuşmanın ses enerjisi', olcek: 1 },
  { anahtar: 'konu', etiket: 'Konuya uyum', ipucu: 'Cümlenin konu bloğuna uyumu (yapay zeka konu analizi)', olcek: 1 },
]

const GORSEL_BARLAR: BarTanimi[] = [
  { anahtar: 'hook_acilis', etiket: 'Hook (açılış)', ipucu: 'Klip başındaki görsel enerji', olcek: 1 },
  { anahtar: 'hareket', etiket: 'Hareket', ipucu: 'Kare farkı (aksiyon yoğunluğu)', olcek: 1 },
  { anahtar: 'ses', etiket: 'Ses enerjisi', ipucu: 'Patlama/müzik yükselmesi', olcek: 1 },
  { anahtar: 'kesme', etiket: 'Sahne kesmesi', ipucu: 'Klip içindeki sert geçiş sayısı (6 = tam puan)', olcek: 6 },
  { anahtar: 'zenginlik', etiket: 'Görsel zenginlik', ipucu: 'Kontrast/detay yoğunluğu', olcek: 1 },
]

function Bar({ etiket, ipucu, deger }: { etiket: string; ipucu: string; deger: number }): ReactNode {
  const yuzde = Math.max(0, Math.min(100, deger * 100))
  const renk = yuzde >= 70 ? 'bg-success' : yuzde >= 45 ? 'bg-warn' : 'bg-danger'
  return (
    <div className="flex items-center gap-2" title={ipucu}>
      <span className="w-[92px] shrink-0 truncate text-[11px] text-fg-muted">{etiket}</span>
      <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[var(--surface-3)]">
        <span className={cn('block h-full rounded-full transition-all duration-500', renk)} style={{ width: `${yuzde}%` }} />
      </span>
      <span className="num w-[34px] shrink-0 text-right text-[10.5px] text-fg-subtle">{Math.round(yuzde)}</span>
    </div>
  )
}

/** Skorun neden bu oldugunu gosteren kirilim barlari. */
export function SkorKirilimi({
  kirilim,
  mod,
  kompakt = false,
}: {
  kirilim: KlipKirilim
  mod: 'konusma' | 'gorsel'
  kompakt?: boolean
}): ReactNode {
  const barlar: BarTanimi[] = mod === 'gorsel' ? GORSEL_BARLAR : KONUSMA_BARLAR
  const liste = barlar
    .map((b) => ({ ...b, deger: Math.max(0, Math.min(1, Number(kirilim[b.anahtar] ?? 0) / b.olcek)) }))
    .filter((b) => !kompakt || b.deger > 0)
  if (!liste.length) return null
  return (
    <div className="flex flex-col gap-1.5">
      {liste.map((b) => (
        <Bar key={String(b.anahtar)} etiket={b.etiket} ipucu={b.ipucu} deger={b.deger} />
      ))}
      {mod === 'konusma' && kirilim.konu_orani != null ? (
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-fg-subtle">
          <span>Konu bütünlüğü: %{Math.round((kirilim.konu_orani ?? 0) * 100)}</span>
          {kirilim.yogunluk != null ? <span>· Konuşma yoğunluğu: %{Math.round(kirilim.yogunluk * 100)}</span> : null}
          {kirilim.ceza != null && kirilim.ceza > 0.05 ? (
            <span className="text-warn">· Dolgu/tekrar cezası: -{Math.round(kirilim.ceza * 100)} puan</span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
