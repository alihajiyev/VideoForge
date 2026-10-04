import type { ReactNode } from 'react'
import { Wallet } from 'lucide-react'
import { useApp } from '@/app/AppContext'
import { Badge, Panel, SectionTitle, Spinner } from '@/components/ui/primitives'
import { cn, formatKalan } from '@/lib/utils'
import { useTicker } from '@/lib/hooks'
import type { KrediServisi } from '@shared/types'

/**
 * Servis kredileri karti: botu besleyen hizmetlerin (ElevenLabs, ZapCap,
 * Gemini...) kalan kredisini/kotasini gosterir. Anahtarlar bot klasorundeki
 * .env dosyasindan (ZapCap icin ShortsStudio config.py'den) okunur.
 */

const DURUM_TONE: Record<KrediServisi['durum'], 'success' | 'warn' | 'danger' | 'neutral'> = {
  ok: 'success',
  'anahtar-yok': 'warn',
  hata: 'danger',
  bilgi: 'neutral',
}

function sayiYaz(n: number, birim: string): string {
  if (birim === 'USD' || birim === 'USD-tahmini') return `$${n < 1 ? n.toFixed(4) : n.toFixed(2)}`
  return new Intl.NumberFormat('tr-TR').format(Math.round(n))
}

function birimEtiket(birim: string): string {
  if (birim === 'karakter') return 'kalan karakter'
  if (birim === 'USD') return 'kalan bakiye'
  if (birim === 'USD-tahmini') return 'tahmini harcama (bu ay)'
  return 'kalan'
}

export function KrediKarti(): ReactNode {
  const { credits, refreshCredits } = useApp()
  useTicker(true)

  return (
    <Panel className="p-3.5">
      <SectionTitle
        title="Servis kredileri"
        subtitle="Kullandığın hizmetlerin kalan bakiyesi"
        icon={<Wallet className="size-4" />}
        right={
          <button
            onClick={() => void refreshCredits()}
            className="text-[11px] text-fg-subtle transition-colors hover:text-fg"
          >
            Yenile
          </button>
        }
      />

      {credits.length === 0 ? (
        <div className="flex items-center gap-2 py-4 text-[12px] text-fg-subtle">
          <Spinner /> Krediler sorgulanıyor...
        </div>
      ) : (
        <div className="mt-3 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
          {credits.map((s) => {
            const oran = s.toplam && s.kalan !== null ? Math.min(100, Math.round((s.kalan / s.toplam) * 100)) : null
            const resetMs = s.sifirlanmaMs ? s.sifirlanmaMs - Date.now() : null
            return (
              <div key={s.id} className="rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[12px] font-medium text-fg" title={s.ad}>
                    {s.ad}
                  </span>
                  <Badge className="ml-auto" tone={DURUM_TONE[s.durum]}>
                    {s.durum === 'ok' ? 'aktif' : s.durum === 'hata' ? 'hata' : s.durum === 'bilgi' ? 'bilgi' : 'anahtar yok'}
                  </Badge>
                </div>

                {s.kalan !== null ? (
                  <div className="mt-1.5 flex items-baseline gap-1.5">
                    <span className="num text-[18px] font-semibold tracking-[-0.02em] text-fg">{sayiYaz(s.kalan, s.birim)}</span>
                    <span className="text-[10.5px] text-fg-subtle">
                      {birimEtiket(s.birim)}
                      {s.toplam ? ` / ${sayiYaz(s.toplam, s.birim)}` : ''}
                    </span>
                  </div>
                ) : null}

                {oran !== null ? (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-3)]">
                    <div
                      className={cn('h-full rounded-full transition-all duration-500', oran <= 15 ? 'bg-danger' : oran <= 35 ? 'bg-warn' : 'bg-success')}
                      style={{ width: `${Math.max(2, oran)}%` }}
                    />
                  </div>
                ) : null}

                {resetMs !== null && resetMs > 0 ? (
                  <p className="mt-1.5 text-[10.5px] text-fg-subtle">Sıfırlanma: {formatKalan(resetMs)}</p>
                ) : null}

                {s.durum === 'hata' && s.hata ? (
                  <p className="mt-1.5 text-[10.5px] text-danger">{s.hata}</p>
                ) : s.detay ? (
                  <p className="mt-1.5 text-[10.5px] text-fg-subtle">{s.detay}</p>
                ) : null}
              </div>
            )
          })}
        </div>
      )}

      <p className="mt-2.5 text-[10.5px] leading-relaxed text-fg-subtle">
        Değerler hizmetlerin kendi API’lerinden canlı okunur (ElevenLabs karakter kotası, ZapCap USD bakiyesi). Gemini için resmî kota uç
        noktası olmadığından “Gemini kotası” kartındaki tahmin kullanılır.
      </p>
    </Panel>
  )
}
