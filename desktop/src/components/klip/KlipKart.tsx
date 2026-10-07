import { useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Clapperboard, Eye, LayoutPanelTop, Play } from 'lucide-react'
import type { KlipOgesi } from '@shared/types'
import { Badge } from '@/components/ui/primitives'
import { SkorHalkasi } from '@/components/klip/SkorGostergesi'
import { panelMetni } from '@/components/klip/KlipOynatici'
import { cn, formatBytes } from '@/lib/utils'
import { klipVideoUrl, sureMetni } from '@/lib/video'

/**
 * KLIP KARTI — Opus Clip tarzi 9:16 kart.
 *
 * Fareyle uzerine gelince video sessiz olarak onizlenir; tiklayinca uygulama
 * ici oynatici acilir. Skor halkasi + QA rozeti + konu ve panel bilgisi gosterilir.
 */
export function KlipKart({ klip, onIzle }: { klip: KlipOgesi; onIzle: () => void }): ReactNode {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [onizlemede, setOnizlemede] = useState(false)
  const url = klipVideoUrl(klip.dosya)
  const oynatilabilir = Boolean(klip.dosyaVar && url)

  const baslat = (): void => {
    setOnizlemede(true)
    const v = videoRef.current
    if (!v) return
    v.currentTime = 0
    void v.play().catch(() => {})
  }

  const durdur = (): void => {
    setOnizlemede(false)
    const v = videoRef.current
    if (!v) return
    v.pause()
    v.currentTime = 0.01
  }

  return (
    <div
      className={cn(
        'group flex cursor-pointer flex-col gap-2 rounded-[12px] border border-border bg-[var(--surface)] p-2 transition-colors',
        'hover:border-border-strong hover:bg-[var(--surface-2)]',
      )}
      onClick={onIzle}
      onMouseEnter={baslat}
      onMouseLeave={durdur}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onIzle()
        }
      }}
      title="İzle (skor kırılımı ve kesitler)"
    >
      {/* --------------------------- video onizleme --------------------------- */}
      <div className="thumb relative aspect-[9/16] w-full overflow-hidden bg-black">
        {oynatilabilir ? (
          <video
            ref={videoRef}
            src={url}
            className="size-full object-cover"
            muted
            loop
            playsInline
            preload="metadata"
          />
        ) : (
          <div
            className="grid size-full place-items-center px-3 text-center"
            style={{ background: 'radial-gradient(120% 90% at 30% 10%, #2a2a2c, #131315)' }}
          >
            <span className="flex flex-col items-center gap-1.5 text-fg-muted">
              <Clapperboard className="size-6 opacity-70" />
              <span className="text-[11px] leading-snug">
                {klip.hata ? 'Render hatası' : 'Sadece plan — video üretilmedi'}
              </span>
              <span className="text-[10px] text-fg-subtle">Sadece analiz modu</span>
            </span>
          </div>
        )}

        {/* skor halkasi */}
        <div className="pointer-events-none absolute top-2 left-2 rounded-full bg-[var(--overlay)] p-0.5 backdrop-blur-sm">
          <SkorHalkasi skor={klip.skor} boyut={46} />
        </div>

        {/* QA rozeti */}
        {klip.qaPuan !== null ? (
          <div className="pointer-events-none absolute top-2 right-2">
            <Badge tone={klip.qaPuan >= 85 ? 'success' : klip.qaPuan >= 70 ? 'warn' : 'danger'}>
              QA {klip.qaPuan}
            </Badge>
          </div>
        ) : klip.hata ? (
          <div className="pointer-events-none absolute top-2 right-2">
            <Badge tone="danger">
              <AlertTriangle className="size-3" /> hata
            </Badge>
          </div>
        ) : null}

        {/* sure + mod */}
        <div className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-1.5">
          <Badge tone={klip.mod === 'gorsel' ? 'violet' : 'cyan'}>
            {klip.mod === 'gorsel' ? 'görsel' : 'konuşma'}
          </Badge>
          <Badge tone="neutral">{klip.sure.toFixed(0)} sn</Badge>
        </div>

        {/* oynat dugmesi */}
        <span
          className={cn(
            'pointer-events-none absolute inset-0 grid place-items-center transition-opacity',
            onizlemede ? 'opacity-0' : 'opacity-100',
          )}
        >
          <span className="grid size-12 place-items-center rounded-full bg-[var(--overlay)] text-white backdrop-blur-sm transition-transform group-hover:scale-105">
            <Play className="size-5 translate-x-[1px] fill-current" />
          </span>
        </span>
      </div>

      {/* ------------------------------ alt bilgi ------------------------------ */}
      <div className="flex flex-col gap-1 px-0.5">
        <p className="line-clamp-2 text-[12px] leading-snug font-medium text-fg" title={klip.baslik}>
          {klip.baslik}
        </p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-fg-subtle">
          <span className="num font-semibold text-fg-muted">#{klip.no}</span>
          <span className="num">kaynak {sureMetni(klip.baslangic)}</span>
          {klip.konu ? <span className="truncate">· {klip.konu}</span> : null}
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-fg-subtle">
          {Object.keys(klip.panelDagilimi || {}).length ? (
            <span className="inline-flex items-center gap-1">
              <LayoutPanelTop className="size-3" />
              {panelMetni(klip.panelDagilimi)}
            </span>
          ) : null}
          {klip.boyut ? <span>{formatBytes(klip.boyut)}</span> : null}
          <span className="ml-auto inline-flex items-center gap-1 text-cyan opacity-0 transition-opacity group-hover:opacity-100">
            <Eye className="size-3" /> izle
          </span>
        </div>
      </div>
    </div>
  )
}
