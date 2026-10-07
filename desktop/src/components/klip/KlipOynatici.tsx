import { useEffect, useRef, type ReactNode } from 'react'
import { Clock, ExternalLink, FolderOpen, Languages, LayoutPanelTop, Sparkles, X } from 'lucide-react'
import type { KlipKlasoru, KlipOgesi } from '@shared/types'
import { Badge, Button } from '@/components/ui/primitives'
import { SkorHalkasi, SkorKirilimi } from '@/components/klip/SkorGostergesi'
import { formatBytes, cn } from '@/lib/utils'
import { klipVideoUrl, sureMetni } from '@/lib/video'

/** Panel dagilimini okunur metne cevirir ({"1": 4, "2": 2} -> "1li x4 · 2li x2"). */
export function panelMetni(dagilim: Record<string, number>): string {
  const parcalar = Object.entries(dagilim || {})
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([n, c]) => `${n}li ×${c}`)
  return parcalar.join(' · ')
}

/**
 * KLIP OYNATICI — uretilen klibi uygulamadan cikmadan izle.
 *
 * Video, main process'in `vfil://` protokolu ile servis edilir (yerel dosya,
 * Range destekli). Yaninda skor kirilimi ve kesit zaman cizgisi (hangi saniyede
 * ne konusuldu) gosterilir.
 */
export function KlipOynatici({
  klip,
  klasor,
  onClose,
  onAc,
  onKlasor,
}: {
  klip: KlipOgesi
  klasor: KlipKlasoru
  onClose: () => void
  onAc: (yol: string) => void
  onKlasor: (yol: string) => void
}): ReactNode {
  const videoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    const tus = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', tus)
    return () => window.removeEventListener('keydown', tus)
  }, [onClose])

  const url = klipVideoUrl(klip.dosya)
  const kesitler = klip.kesitler || []
  const enYuksekKesit = kesitler.reduce((en, k) => Math.max(en, k.skor ?? 0), 0)
  // Klip zaman cizgisi: her kesit kendi suresi kadar yer kaplar (motorun
  // kesim sinirlari 0.15 sn pay ile ayni uzunlukta). Boylece "kaynak 2:14"
  // satirina tiklandiginda video dogru saniyeye gider.
  const kesitBaslangici = (indeks: number): number => {
    let t = 0
    for (let i = 0; i < indeks; i++) {
      const k = kesitler[i]
      t += Math.max(0.2, k.son - k.bas + 0.3)
    }
    return t
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[var(--overlay)] p-4 backdrop-blur-[2px] sm:p-8"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="panel my-auto grid w-full max-w-[1020px] gap-4 p-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ------------------------------ video ------------------------------ */}
        <div className="flex flex-col gap-3">
          <div className="relative overflow-hidden rounded-[12px] border border-border bg-black">
            {klip.dosyaVar && url ? (
              <video
                ref={videoRef}
                src={url}
                className="aspect-[9/16] max-h-[62vh] w-full bg-black object-contain"
                controls
                autoPlay
                playsInline
                preload="metadata"
              />
            ) : (
              <div className="grid aspect-[9/16] max-h-[62vh] w-full place-items-center text-center text-[12px] text-fg-muted">
                {klip.hata ? `Render hatası: ${klip.hata}` : 'Video dosyası bulunamadı (plan modunda render yok).'}
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {klip.dosyaVar ? (
              <>
                <Button size="sm" variant="secondary" icon={<ExternalLink className="size-3.5" />} onClick={() => onAc(klip.dosya as string)}>
                  Varsayılan oynatıcı
                </Button>
                <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => onKlasor(klasor.klasor)}>
                  Klasörü aç
                </Button>
              </>
            ) : null}
            {klip.srt ? (
              <Button size="sm" variant="ghost" icon={<Languages className="size-3.5" />} onClick={() => onAc(klip.srt as string)}>
                Altyazı (SRT)
              </Button>
            ) : null}
          </div>
        </div>

        {/* --------------------------- skor + detay --------------------------- */}
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex items-start gap-3">
            <SkorHalkasi skor={klip.skor} boyut={62} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone={klip.mod === 'gorsel' ? 'violet' : 'cyan'}>
                  {klip.mod === 'gorsel' ? 'Görsel hook' : 'Konuşma'}
                </Badge>
                <Badge tone="neutral">{klip.sure.toFixed(1)} sn</Badge>
                {klip.qaPuan !== null ? (
                  <Badge tone={klip.qaPuan >= 85 ? 'success' : klip.qaPuan >= 70 ? 'warn' : 'danger'}>
                    QA {klip.qaPuan} {klip.qaDerece ?? ''}
                  </Badge>
                ) : null}
              </div>
              <p className="mt-1.5 line-clamp-3 text-[13px] leading-snug font-medium text-fg">{klip.baslik}</p>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-fg-subtle">
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3" />
                  kaynak {sureMetni(klip.baslangic)} – {sureMetni(klip.bitis)}
                </span>
                {klip.konu ? (
                  <span className="inline-flex items-center gap-1">
                    <Sparkles className="size-3" />
                    konu: {klip.konu}
                  </span>
                ) : null}
                {Object.keys(klip.panelDagilimi || {}).length ? (
                  <span className="inline-flex items-center gap-1">
                    <LayoutPanelTop className="size-3" />
                    {panelMetni(klip.panelDagilimi)}
                  </span>
                ) : null}
                {klip.boyut ? <span>{formatBytes(klip.boyut)}</span> : null}
              </div>
            </div>
            <button
              className="grid size-8 shrink-0 place-items-center rounded-full text-fg-muted transition-colors hover:bg-[var(--surface-3)] hover:text-fg"
              onClick={onClose}
              aria-label="Kapat"
            >
              <X className="size-4" />
            </button>
          </div>

          <div className="rounded-[10px] border border-border bg-[var(--surface-2)] p-3">
            <p className="mb-2 text-[11.5px] font-semibold tracking-wide text-fg-muted uppercase">
              Skor kırılımı — neden bu puan?
            </p>
            <SkorKirilimi kirilim={klip.kirilim || {}} mod={klip.mod} />
          </div>

          {kesitler.length ? (
            <div className="flex min-h-0 flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <p className="text-[11.5px] font-semibold tracking-wide text-fg-muted uppercase">
                  Kesitler — klip içinde ne konuşuldu
                </p>
                <span className="text-[11px] text-fg-subtle">
                  {kesitler.length} kesit · en yüksek {Math.round(enYuksekKesit)}
                </span>
              </div>
              <div className="flex max-h-[220px] flex-col gap-1 overflow-y-auto pr-1">
                {kesitler.map((k, i) => (
                  <button
                    key={`${k.bas}-${i}`}
                    className="flex items-start gap-2 rounded-[8px] border border-transparent bg-[var(--surface-2)] px-2.5 py-1.5 text-left transition-colors hover:border-border hover:bg-[var(--surface-3)]"
                    title="Kaynağa gitmek için tıklayın"
                    onClick={() => {
                      const v = videoRef.current
                      if (!v?.duration) return
                      const ofset = kesitBaslangici(i)
                      v.currentTime = Math.max(0, Math.min(v.duration - 0.2, ofset))
                      void v.play().catch(() => {})
                    }}
                  >
                    <span className="num mt-[1px] w-[46px] shrink-0 text-[11px] text-cyan">{sureMetni(k.bas)}</span>
                    <span className="min-w-0 flex-1 text-[12px] leading-snug text-fg">
                      {k.metin || <span className="text-fg-subtle">(konuşma yok — görsel sahne)</span>}
                    </span>
                    <span
                      className={cn(
                        'num mt-[1px] shrink-0 text-[11px]',
                        (k.skor ?? 0) >= 70 ? 'text-success' : (k.skor ?? 0) >= 50 ? 'text-warn' : 'text-fg-subtle',
                      )}
                    >
                      {k.skor != null ? Math.round(k.skor) : '—'}
                    </span>
                    <span className="mt-[1px] shrink-0 text-[10px] text-fg-subtle">{k.panel}li</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {klip.qaSorunlar.length ? (
            <ul className="flex flex-col gap-1 rounded-[10px] border border-border bg-[var(--surface-2)] p-3">
              {klip.qaSorunlar.map((s) => (
                <li key={s} className="text-[11.5px] text-warn">
                  ⚠ {s}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  )
}
