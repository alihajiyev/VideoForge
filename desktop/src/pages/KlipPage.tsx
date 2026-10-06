import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Clapperboard,
  FolderOpen,
  ListChecks,
  Music,
  RefreshCw,
  Scissors,
  Square,
  Sparkles,
  UserRound,
  Video,
} from 'lucide-react'
import type { KlipDurumu } from '@shared/types'
import {
  KLIP_SAYISI_MAX,
  KLIP_SAYISI_VARSAYILAN,
  KLIP_SURE_VARSAYILAN,
  normalKlipSayisi,
  normalKlipSuresi,
} from '@shared/constants'
import { api, unwrap } from '@/lib/api'
import { useApp } from '@/app/AppContext'
import { useTicker } from '@/lib/hooks'
import { cn, formatBytes, formatDuration, formatRelative } from '@/lib/utils'
import { Badge, Button, EmptyState, Input, Panel, SectionTitle, Select, Switch } from '@/components/ui/primitives'
import { ConsoleView } from '@/components/run/ConsoleView'
import { StageTimeline } from '@/components/run/StageTimeline'
import type { PageKey } from '@/components/layout/Sidebar'

const HOPARLOR_SECENEK = [
  { value: 'auto', etiket: 'Otomatik (kaç kişi konuşuyorsa)' },
  { value: '1', etiket: 'Tek kişi (tam ekran + kafa takibi)' },
  { value: '2', etiket: 'İki kişi (alt/üst panel)' },
  { value: '3', etiket: 'Üç kişi (üst tam + alt iki)' },
  { value: '4', etiket: 'Dört kişi (2x2 panel)' },
]

const SURE_SECENEK = [20, 30, 45, 60]

const ALTYAZI_SECENEK = [
  { value: 'srt', etiket: 'SRT dosyası (ücretsiz, önerilen)' },
  { value: 'yak', etiket: 'Videoya yak (kısa videolarda pahalı, uzun sürer)' },
  { value: 'yok', etiket: 'Altyazı yok' },
]

/**
 * KLIP STÜDYO — uzun video linkini dikey Shorts'lara çevirir.
 *
 * Bot tarafında `functions/klipci.py` çalışır: transkript + önem skoru +
 * gereksiz sahne temizliği + konuşmacı ayırma + kafa takibi + 1/2/4 panelli
 * dikey montaj. Hepsi yerel ve ücretsiz (yt-dlp + ffmpeg + Whisper + OpenCV).
 */
export function KlipPage({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
  const { job, startJob, cancelJob, pushToast, settings } = useApp()
  const [link, setLink] = useState('')
  const [adet, setAdet] = useState<number>(KLIP_SAYISI_VARSAYILAN)
  const [sure, setSure] = useState<number>(KLIP_SURE_VARSAYILAN)
  const [hoparlor, setHoparlor] = useState('auto')
  const [altyazi, setAltyazi] = useState<'yok' | 'srt' | 'yak'>('srt')
  const [planSadece, setPlanSadece] = useState(false)
  const [yuzAtla, setYuzAtla] = useState(false)
  const [ducking, setDucking] = useState(false)
  const [muzik, setMuzik] = useState('')
  const [durum, setDurum] = useState<KlipDurumu | null>(null)
  const [yukleniyor, setYukleniyor] = useState(false)

  // Bot klasörü ayarlı mı? (üretim için gerekli)
  const hazir = Boolean(settings?.videoForgePath)
  const benimIsim = job?.kind === 'klip'
  const calisiyor = benimIsim && job?.status === 'running'
  const tick = useTicker(calisiyor)
  void tick

  const yenile = useCallback(
    async (sessiz = true) => {
      if (!sessiz) setYukleniyor(true)
      try {
        setDurum(await unwrap(api.klipDurum()))
      } catch (err) {
        if (!sessiz) pushToast({ tone: 'error', title: 'Klipler okunamadı', message: String(err) })
      } finally {
        if (!sessiz) setYukleniyor(false)
      }
    },
    [pushToast],
  )

  useEffect(() => {
    void yenile()
  }, [yenile])

  // İş bittiğinde çıktı listesini tazele.
  const durumAnahtar = `${job?.status ?? ''}-${job?.endedAt ?? 0}`
  useEffect(() => {
    if (job?.kind !== 'klip') return
    if (job.status === 'running') return
    void yenile()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [durumAnahtar])

  const basla = useCallback(async () => {
    const temiz = link.trim()
    if (!/^https?:\/\//i.test(temiz)) {
      pushToast({ tone: 'warn', title: 'Link gerekli', message: 'http:// veya https:// ile başlayan bir video linki girin.' })
      return
    }
    if (ducking && !muzik.trim()) {
      pushToast({ tone: 'warn', title: 'Müzik dosyası gerekli', message: 'Ducking için fon müziği dosya yolunu yazın.' })
      return
    }
    const ok = await startJob({
      kind: 'klip',
      link: temiz,
      klipSayisi: normalKlipSayisi(adet),
      klipSuresi: normalKlipSuresi(sure),
      klipHoparlor: hoparlor,
      klipAltyazi: altyazi,
      klipPlanSadece: planSadece,
      klipYuzAtla: yuzAtla,
      klipDucking: ducking,
      klipMuzik: muzik_yolu(muzik),
    })
    if (ok) {
      pushToast({
        tone: 'info',
        title: 'Klip Stüdyo başladı',
        message: planSadece ? 'Sadece analiz + plan çıkarılıyor (render yok).' : `${normalKlipSayisi(adet)} klip üretiliyor.`,
      })
      if (!benimIsim) onNavigate('klip')
    }
  }, [link, adet, sure, hoparlor, altyazi, planSadece, yuzAtla, ducking, muzik, startJob, pushToast, onNavigate, benimIsim])

  const klipler = useMemo(
    () => (durum?.klasorler ?? []).flatMap((k) => k.klipler.map((i) => ({ ...i, klasor: k.klasor, klasorAd: k.ad }))),
    [durum],
  )
  const iyiKlip = klipler.filter((k) => (k.qaPuan ?? 0) >= 70).length

  return (
    <div className="flex flex-col gap-5">
      <SectionTitle
        icon={<Scissors className="size-4" />}
        title="Klip Stüdyo"
        subtitle="Uzun videoyu önemli anlarından dikey Shorts'a çevir (yerel + ücretsiz: yt-dlp, ffmpeg, Whisper, OpenCV)"
        right={
          <Button
            variant="ghost"
            size="sm"
            icon={<RefreshCw className={cn('size-3.5', yukleniyor && 'animate-spin')} />}
            onClick={() => void yenile(false)}
          >
            Çıktıları yenile
          </Button>
        }
      />

      {/* ------------------------------- form ------------------------------- */}
      <Panel className="flex flex-col gap-4 p-4">
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-[12px] font-medium text-fg-muted">
            <Video className="size-3.5" />
            Uzun video linki (reportaj, podcast, röportaj)
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={link}
              onChange={(e) => setLink(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void basla()
              }}
              placeholder="https://www.youtube.com/watch?v=..."
              disabled={calisiyor}
              className="flex-1"
            />
            {calisiyor ? (
              <Button variant="danger" icon={<Square className="size-3.5" />} onClick={() => void cancelJob()}>
                Durdur
              </Button>
            ) : (
              <Button variant="primary" icon={<Sparkles className="size-3.5" />} onClick={() => void basla()}>
                Shorts üret
              </Button>
            )}
          </div>
          <p className="text-[11.5px] leading-relaxed text-fg-subtle">
            Video indirilir, konuşma metne çevrilir, cümleler önem puanına göre skorlanır; dolgu/tekrar eden
            yerler ve ölü hava atılır. Konuşan kişi kadraja alınır; aynı anda iki kişi konuşuyorsa pencere alt/üst
            ikiye, dört kişi konuşuyorsa 2x2 dörde bölünür.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] text-fg-subtle">Klip sayısı</span>
            <Select value={String(adet)} onChange={(e) => setAdet(normalKlipSayisi(e.target.value))} disabled={calisiyor}>
              {Array.from({ length: KLIP_SAYISI_MAX }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n} klip{n === KLIP_SAYISI_VARSAYILAN ? ' (önerilen)' : ''}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] text-fg-subtle">Hedef süre (sn)</span>
            <Select value={String(sure)} onChange={(e) => setSure(normalKlipSuresi(e.target.value))} disabled={calisiyor}>
              {SURE_SECENEK.map((s) => (
                <option key={s} value={s}>
                  {s} saniye
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 text-[11.5px] text-fg-subtle">
              <UserRound className="size-3" />
              Panel / konuşmacı modu
            </span>
            <Select value={hoparlor} onChange={(e) => setHoparlor(e.target.value)} disabled={calisiyor}>
              {HOPARLOR_SECENEK.map((h) => (
                <option key={h.value} value={h.value}>
                  {h.etiket}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[11.5px] text-fg-subtle">Altyazı</span>
            <Select
              value={altyazi}
              onChange={(e) => setAltyazi(e.target.value as 'yok' | 'srt' | 'yak')}
              disabled={calisiyor}
            >
              {ALTYAZI_SECENEK.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.etiket}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <div className="grid gap-3 border-t border-border pt-3 sm:grid-cols-2 lg:grid-cols-4">
          <Switch
            checked={planSadece}
            onChange={setPlanSadece}
            label="Sadece analiz (render yok)"
            hint="Hızlı: skorları ve seçilen anları gör"
          />
          <Switch
            checked={yuzAtla}
            onChange={setYuzAtla}
            label="Kafa takibini atla"
            hint="Daha hızlı; kadraj merkezde kalır"
          />
          <Switch
            checked={ducking}
            onChange={setDucking}
            label="Fon müziği (ducking)"
            hint="Konuşma varken müzik kısılır"
          />
          <label className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 text-[11.5px] text-fg-subtle">
              <Music className="size-3" />
              Müzik dosyası (opsiyonel)
            </span>
            <Input
              value={muzik}
              onChange={(e) => setMuzik(e.target.value)}
              placeholder="C:\muzik\fon.mp3"
              disabled={calisiyor || !ducking}
            />
          </label>
        </div>

        {!hazir ? (
          <p className="text-[11.5px] text-warn">
            VideoForge klasörü ayarlı değil — Ayarlar &gt; VideoForge klasörü bölümünden yolu belirtin.
          </p>
        ) : null}
      </Panel>

      {/* --------------------------- canlı işlem --------------------------- */}
      {benimIsim && job ? (
        <Panel className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={calisiyor ? 'brand' : job.status === 'done' ? 'success' : job.status === 'cancelled' ? 'warn' : 'danger'} dot={calisiyor}>
              {calisiyor ? 'çalışıyor' : job.status === 'done' ? 'bitti' : job.status === 'cancelled' ? 'durduruldu' : 'hata'}
            </Badge>
            <span className="truncate text-[12.5px] text-fg">{job.title}</span>
            <span className="ml-auto text-[11.5px] text-fg-subtle">
              {formatDuration(job.startedAt, job.endedAt)}
            </span>
          </div>
          <StageTimeline stages={job.stages} index={job.stageIndex} status={job.status} />
          <ConsoleView lines={job.lines} live={calisiyor} height="h-[320px]" />
          {!calisiyor ? (
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" icon={<RefreshCw className="size-3.5" />} onClick={() => void yenile(false)}>
                Çıktıları yükle
              </Button>
              {job.status !== 'done' ? (
                <Button variant="ghost" size="sm" onClick={() => onNavigate('run')}>
                  Çalıştır sayfasında aç
                </Button>
              ) : null}
            </div>
          ) : null}
        </Panel>
      ) : null}

      {/* ----------------------------- çıktılar ---------------------------- */}
      <Panel className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <ListChecks className="size-4 text-fg-subtle" />
          <span className="text-[13.5px] font-semibold text-fg">Üretilen klipler</span>
          {durum ? (
            <Badge tone="neutral">
              {durum.toplamKlip} klip · {durum.klasorler.length} video
            </Badge>
          ) : null}
          {klipler.length ? <Badge tone={iyiKlip ? 'success' : 'warn'}>{iyiKlip} tanesi QA eşiğini geçti</Badge> : null}
        </div>

        {durum && !durum.klasorler.length ? (
          <EmptyState
            icon={<Clapperboard className="size-7" />}
            title="Henüz klip yok"
            message="Yukarıya uzun bir video linki yapıştırıp “Shorts üret” düğmesine basın. Çıktılar Masaüstü/Klipler klasörüne yazılır."
          />
        ) : null}

        {durum?.klasorler.map((k) => (
          <div key={k.klasor} className="flex flex-col gap-2 rounded-[10px] border border-border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-[13px] font-medium text-fg">{k.ad}</span>
              <Badge tone="neutral">{k.konusmaciSayisi} konuşmacı</Badge>
              {k.yuzIziSayisi ? <Badge tone="cyan">{k.yuzIziSayisi} yüz izi</Badge> : null}
              {k.atilanKesit ? <Badge tone="neutral">{k.atilanKesit} gereksiz kesit atıldı</Badge> : null}
              <span className="ml-auto text-[11px] text-fg-subtle">{formatRelative(k.mtime)}</span>
              <Button variant="ghost" size="sm" icon={<FolderOpen className="size-3.5" />} onClick={() => void api.shellReveal(k.klasor)}>
                Klasör
              </Button>
            </div>

            <div className="flex flex-col gap-1.5">
              {k.klipler.map((klip) => (
                <div
                  key={`${k.klasor}-${klip.no}`}
                  className="flex flex-wrap items-center gap-2 rounded-[8px] bg-[var(--surface-2)] px-3 py-2"
                >
                  <span className="num text-[12px] font-semibold text-fg-subtle">#{klip.no}</span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-fg" title={klip.baslik}>
                    {klip.baslik || 'Klip'}
                  </span>
                  <Badge tone="neutral">skor {klip.skor.toFixed(1)}</Badge>
                  <Badge tone="neutral">{klip.sure.toFixed(1)} sn</Badge>
                  <span className="text-[11px] text-fg-subtle">
                    panel: {Object.entries(klip.panelDagilimi).map(([n, c]) => `${n}li x${c}`).join(' · ') || '—'}
                  </span>
                  {klip.boyut ? <span className="text-[11px] text-fg-subtle">{formatBytes(klip.boyut)}</span> : null}
                  {klip.qaPuan !== null ? (
                    <Badge tone={klip.qaPuan >= 85 ? 'success' : klip.qaPuan >= 70 ? 'warn' : 'danger'}>
                      QA {klip.qaPuan}
                    </Badge>
                  ) : klip.hata ? (
                    <Badge tone="danger">render hatası</Badge>
                  ) : null}
                  {klip.hata ? <span className="text-[11px] text-danger">{klip.hata}</span> : null}
                  {klip.dosyaVar ? (
                    <Button variant="secondary" size="sm" icon={<Video className="size-3.5" />} onClick={() => void api.shellOpen(klip.dosya as string)}>
                      Aç
                    </Button>
                  ) : (
                    <Badge tone="warn">dosya yok</Badge>
                  )}
                </div>
              ))}
            </div>

            {k.klipler.some((kl) => kl.qaSorunlar.length) ? (
              <ul className="flex flex-col gap-1 pl-1">
                {k.klipler
                  .filter((kl) => kl.qaSorunlar.length)
                  .map((kl) => (
                    <li key={`${k.klasor}-${kl.no}-qa`} className="text-[11.5px] text-warn">
                      #{kl.no}: {kl.qaSorunlar.join(' · ')}
                    </li>
                  ))}
              </ul>
            ) : null}
          </div>
        ))}
      </Panel>
    </div>
  )
}

/** Müzik yolu: boş bırakılırsa undefined döner (bot varsayılanı kullanır). */
function muzik_yolu(yol: string): string | undefined {
  const temiz = yol.trim()
  return temiz ? temiz : undefined
}
