import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  ChevronDown,
  Clapperboard,
  FileText,
  FolderOpen,
  LayoutDashboard,
  ListChecks,
  Music,
  RefreshCw,
  Scissors,
  Sparkles,
  Square,
  UserRound,
  Video,
  Wand2,
  Waypoints,
} from 'lucide-react'
import type { KlipDurumu, KlipKlasoru, KlipOgesi, KlipTranskript } from '@shared/types'
import {
  KLIP_OTO,
  KLIP_OTO_SURE_MAX,
  KLIP_SAYISI_MAX,
  normalKlipSayisi,
  normalKlipSuresi,
} from '@shared/constants'
import { api, unwrap } from '@/lib/api'
import { useApp } from '@/app/AppContext'
import { useTicker } from '@/lib/hooks'
import { cn, formatDuration, formatRelative } from '@/lib/utils'
import { sureMetni } from '@/lib/video'
import { Badge, Button, EmptyState, Input, Panel, Progress, SectionTitle, Select, Switch } from '@/components/ui/primitives'
import { ConsoleView } from '@/components/run/ConsoleView'
import { StageTimeline } from '@/components/run/StageTimeline'
import { KlipKart } from '@/components/klip/KlipKart'
import { KlipOynatici } from '@/components/klip/KlipOynatici'
import { panelMetni } from '@/components/klip/KlipOynatici'
import type { PageKey } from '@/components/layout/Sidebar'

const HOPARLOR_SECENEK = [
  { value: 'auto', etiket: 'Otomatik — aynı anda kaç kişi konuşuyorsa' },
  { value: '1', etiket: 'Tek kişi — tam ekran + kafa takibi' },
  { value: '2', etiket: 'En fazla 2 panel (alt/üst)' },
  { value: '3', etiket: 'En fazla 3 panel (üst tam + alt iki)' },
  { value: '4', etiket: 'En fazla 4 panel (2x2)' },
]

const SURE_SECENEK = [20, 30, 45, 60]

const ALTYAZI_SECENEK = [
  { value: 'srt', etiket: 'SRT dosyası (ücretsiz, önerilen)' },
  { value: 'yak', etiket: 'Videoya yak (uzun sürer)' },
  { value: 'yok', etiket: 'Altyazı yok' },
]

/** Hızlı hazır ayarlar: tıklayınca klip sayısı + süre birlikte değişir. */
const HAZIR_AYARLAR: { ad: string; adet: number; sure: number; not: string }[] = [
  { ad: 'Hızlı test', adet: 1, sure: 20, not: 'tek klip, kısa' },
  { ad: 'Dengeli', adet: 3, sure: 45, not: 'önerilen' },
  { ad: 'Çok çıktı', adet: 5, sure: 30, not: '5 klip x 30 sn' },
  { ad: 'Uzun anlatım', adet: 2, sure: 60, not: '60 saniyelik' },
]

const AKIS_ADIMLARI: { icon: ReactNode; baslik: string; metin: string }[] = [
  { icon: <FileText className="size-4" />, baslik: '1. Transkript', metin: 'Video iner, hangi saniyede ne konuşulduğu zamanlı olarak çıkarılır.' },
  { icon: <Wand2 className="size-4" />, baslik: '2. Konu + hook', metin: 'Cümleler konu bloklarına ayrılır; kanca cümle klibin başına yerleştirilir.' },
  { icon: <Waypoints className="size-4" />, baslik: '3. Sahne planı', metin: 'Konuşma süresine göre sahne kurulur; kaç kişi aynı anda konuşuyorsa o kadar panel.' },
  { icon: <LayoutDashboard className="size-4" />, baslik: '4. Dikey montaj', metin: '9:16 montaj + ses temizliği + altyazı + QA kapısı.' },
]

/**
 * KLIP STÜDYO — uzun video linkini dikey Shorts'lara çevirir (Opus Clip tarzı).
 *
 * Bot tarafında `functions/klipci.py` çalışır: zamanlı transkript -> konu
 * blokları -> hook-first skor -> konuşmacı/panel planı -> ses temizliği ->
 * 9:16 montaj -> QA. Konuşma yoksa (ör. savaş sahnesi) görsel hook moduna geçer.
 */
export function KlipPage({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
  const { job, startJob, cancelJob, pushToast, settings } = useApp()
  const [link, setLink] = useState('')
  // Varsayilan OTOMATIK: sayiyi ve sureyi video belirler (klipci.py --klip 0 / --sure 0).
  const [adet, setAdet] = useState<number>(KLIP_OTO)
  const [sure, setSure] = useState<number>(KLIP_OTO)
  const [hoparlor, setHoparlor] = useState('auto')
  const [altyazi, setAltyazi] = useState<'yok' | 'srt' | 'yak'>('srt')
  const [planSadece, setPlanSadece] = useState(false)
  const [yuzAtla, setYuzAtla] = useState(false)
  const [ducking, setDucking] = useState(false)
  const [muzik, setMuzik] = useState('')
  const [gelismis, setGelismis] = useState(false)
  const [durum, setDurum] = useState<KlipDurumu | null>(null)
  const [yukleniyor, setYukleniyor] = useState(false)
  const [onizleme, setOnizleme] = useState<{ klip: KlipOgesi; klasor: KlipKlasoru } | null>(null)
  const [acikTranskript, setAcikTranskript] = useState<string | null>(null)
  const [transkriptler, setTranskriptler] = useState<Record<string, KlipTranskript>>({})

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
  const ortalamaSkor = klipler.length ? klipler.reduce((t, k) => t + (k.skor || 0), 0) / klipler.length : 0

  const transkriptAc = useCallback(
    async (klasor: string) => {
      if (acikTranskript === klasor) {
        setAcikTranskript(null)
        return
      }
      setAcikTranskript(klasor)
      if (transkriptler[klasor]) return
      try {
        const veri = await unwrap(api.klipTranskript(klasor))
        setTranskriptler((onceki) => ({ ...onceki, [klasor]: veri }))
      } catch (err) {
        pushToast({ tone: 'error', title: 'Transkript okunamadı', message: String(err) })
      }
    },
    [acikTranskript, transkriptler, pushToast],
  )

  const asamaYuzdesi = benimIsim && job?.stages?.length ? ((job.stageIndex + 1) / job.stages.length) * 100 : 0

  return (
    <div className="flex flex-col gap-5">
      <SectionTitle
        icon={<Scissors className="size-4" />}
        title="Klip Stüdyo"
        subtitle="Uzun videodan kanca odaklı dikey Shorts: transkript → konu + hook → sahne planı → 9:16 montaj"
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

      {/* ------------------------------ üretim ------------------------------ */}
      <Panel className="relative overflow-hidden p-0">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.5]"
          style={{ background: 'radial-gradient(900px 260px at 12% -20%, var(--brand-soft), transparent 70%)' }}
        />
        <div className="relative flex flex-col gap-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface-3)] px-2.5 py-1 text-[11px] font-medium text-fg-muted">
              <Sparkles className="size-3 text-cyan" />
              yerel + ücretsiz (yt-dlp · ffmpeg · Whisper · OpenCV)
            </span>
            {durum ? <Badge tone="neutral">{durum.toplamKlip} klip · {durum.klasorler.length} video</Badge> : null}
            {klipler.length ? <Badge tone={iyiKlip ? 'success' : 'warn'}>{iyiKlip} tanesi QA eşiğini geçti</Badge> : null}
            {klipler.length ? <Badge tone="cyan">ortalama skor {ortalamaSkor.toFixed(1)}</Badge> : null}
          </div>

          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-[12px] font-medium text-fg-muted">
              <Video className="size-3.5" />
              Uzun video linki (röportaj, podcast, belgesel)
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
                className="h-11 flex-1 rounded-full px-4 text-[13.5px]"
              />
              {calisiyor ? (
                <Button variant="danger" size="lg" icon={<Square className="size-3.5" />} onClick={() => void cancelJob()}>
                  Durdur
                </Button>
              ) : (
                <Button variant="primary" size="lg" icon={<Sparkles className="size-4" />} onClick={() => void basla()}>
                  Shorts üret
                </Button>
              )}
            </div>
            <p className="text-[11.5px] leading-relaxed text-fg-subtle">
              Video indirilir, <strong className="font-medium text-fg-muted">hangi saniyede ne konuşulduğu</strong> zamanlı
              çıkarılır; cümleler konu bloklarına ayrılır ve <strong className="font-medium text-fg-muted">hook
              (kanca)</strong> en yüksek puanı alır. Konuşma yoksa (ör. savaş sahnesi) sahne kesmesi + hareket + ses
              enerjisiyle görsel hook moduna geçer.
            </p>
          </div>

          {/* En sik kullanilan iki ayar HEP acikta; gerisi "Gelismis ayarlar" icinde. */}
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex w-[150px] flex-col gap-1.5">
              <span className="text-[11.5px] text-fg-subtle">Klip sayısı</span>
              <Select value={String(adet)} onChange={(e) => setAdet(normalKlipSayisi(e.target.value))} disabled={calisiyor}>
                <option value={KLIP_OTO}>Otomatik — kaç sahne varsa (önerilen)</option>
                {Array.from({ length: KLIP_SAYISI_MAX }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>
                    {n} klip
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex w-[190px] flex-col gap-1.5">
              <span className="text-[11.5px] text-fg-subtle">Hedef süre (sn)</span>
              <Select value={String(sure)} onChange={(e) => setSure(normalKlipSuresi(e.target.value))} disabled={calisiyor}>
                <option value={KLIP_OTO}>Otomatik — içeriğe göre (maks {KLIP_OTO_SURE_MAX} sn)</option>
                {SURE_SECENEK.map((s) => (
                  <option key={s} value={s}>
                    {s} saniye
                  </option>
                ))}
              </Select>
            </label>
            <div className="flex flex-wrap gap-2">
              {HAZIR_AYARLAR.map((h) => {
                const secili = adet === h.adet && sure === h.sure
                return (
                  <button
                    key={h.ad}
                    className={cn('chip', secili && 'chip-active')}
                    onClick={() => {
                      setAdet(h.adet)
                      setSure(h.sure)
                    }}
                    disabled={calisiyor}
                    type="button"
                  >
                    {h.ad}
                    <span className={cn('text-[10.5px]', secili ? 'opacity-80' : 'text-fg-subtle')}>{h.not}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <button
            type="button"
            className="flex w-fit items-center gap-1.5 text-[12px] font-medium text-fg-muted transition-colors hover:text-fg"
            onClick={() => setGelismis((v) => !v)}
          >
            <ChevronDown className={cn('size-3.5 transition-transform', gelismis && 'rotate-180')} />
            Gelişmiş ayarlar
          </button>

          {gelismis ? (
            <div className="flex flex-col gap-3 border-t border-border pt-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="flex flex-col gap-1.5">
                  <span className="flex items-center gap-1.5 text-[11.5px] text-fg-subtle">
                    <UserRound className="size-3" />
                    Panel / konuşmacı
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

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Switch checked={planSadece} onChange={setPlanSadece} label="Sadece analiz (render yok)" hint="Hızlı: skorları ve seçilen anları gör" />
                <Switch checked={yuzAtla} onChange={setYuzAtla} label="Kafa takibini atla" hint="Daha hızlı; kadraj merkezde kalır" />
                <Switch checked={ducking} onChange={setDucking} label="Fon müziği (ducking)" hint="Konuşma varken müzik kısılır" />
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
            </div>
          ) : null}

          {!hazir ? (
            <p className="text-[11.5px] text-warn">
              VideoForge klasörü ayarlı değil — Ayarlar &gt; VideoForge klasörü bölümünden yolu belirtin.
            </p>
          ) : null}

          {adet === KLIP_OTO || sure === KLIP_OTO ? (
            <p className="rounded-[10px] border border-cyan/25 bg-cyan/5 px-3 py-2 text-[11.5px] leading-relaxed text-fg-muted">
              <strong className="font-medium text-cyan">Otomatik mod:</strong> KAÇ klip üretileceğine video karar
              veriyor — skoru yüksek <strong className="font-medium text-fg">bütün ilginç sahneler</strong> üretilir
              (en fazla 20 klip), zayıf sahneler boşuna çıkarılmaz. Süre de içeriğe göre ayarlanır: anlatım
              güçlüyse klip uzar, ilgi düşerse kapanır (en fazla {KLIP_OTO_SURE_MAX} sn).
            </p>
          ) : null}

          <div className="grid gap-2 border-t border-border pt-3 sm:grid-cols-2 lg:grid-cols-4">
            {AKIS_ADIMLARI.map((a) => (
              <div key={a.baslik} className="flex items-start gap-2">
                <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[var(--surface-3)] text-cyan">
                  {a.icon}
                </span>
                <span className="min-w-0">
                  <span className="block text-[12px] font-medium text-fg">{a.baslik}</span>
                  <span className="block text-[11px] leading-snug text-fg-subtle">{a.metin}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      {/* --------------------------- canlı işlem --------------------------- */}
      {benimIsim && job ? (
        <Panel className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={calisiyor ? 'brand' : job.status === 'done' ? 'success' : job.status === 'cancelled' ? 'warn' : 'danger'} dot={calisiyor}>
              {calisiyor ? 'çalışıyor' : job.status === 'done' ? 'bitti' : job.status === 'cancelled' ? 'durduruldu' : 'hata'}
            </Badge>
            <span className="truncate text-[12.5px] text-fg">{job.title}</span>
            <span className="ml-auto text-[11.5px] text-fg-subtle">{formatDuration(job.startedAt, job.endedAt)}</span>
          </div>
          <Progress value={asamaYuzdesi} tone={calisiyor ? 'cyan' : 'success'} />
          <StageTimeline stages={job.stages} index={job.stageIndex} status={job.status} />
          <ConsoleView lines={job.lines} live={calisiyor} height="h-[280px]" />
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
          {durum?.enIyiPuan !== null && durum?.enIyiPuan !== undefined ? (
            <Badge tone={durum.enIyiPuan >= 85 ? 'success' : durum.enIyiPuan >= 70 ? 'warn' : 'danger'}>
              en iyi QA {durum.enIyiPuan}
            </Badge>
          ) : null}
        </div>

        {durum && !durum.klasorler.length ? (
          <EmptyState
            icon={<Clapperboard className="size-7" />}
            title="Henüz klip yok"
            message="Yukarıya uzun bir video linki yapıştırıp “Shorts üret” düğmesine basın. Çıktılar Masaüstü/Klipler klasörüne yazılır."
          />
        ) : null}

        {(durum?.klasorler ?? []).map((k) => {
          const enIyi = k.klipler.reduce<KlipOgesi | null>((en, i) => (!en || i.skor > en.skor ? i : en), null)
          const qaDerece = k.klipler.find((i) => i.qaDerece)?.qaDerece ?? null
          const qaPuan = enIyi?.qaPuan ?? null
          const transkript = transkriptler[k.klasor]
          return (
            <div key={k.klasor} className="flex flex-col gap-3 rounded-[12px] border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="grid size-8 place-items-center rounded-[8px] bg-[var(--surface-3)] text-cyan">
                  {k.mod === 'gorsel' ? <Wand2 className="size-4" /> : <Scissors className="size-4" />}
                </span>
                <span className="truncate text-[13px] font-semibold text-fg">{k.ad}</span>
                <Badge tone={k.mod === 'gorsel' ? 'violet' : 'cyan'}>{k.mod === 'gorsel' ? 'görsel hook' : 'konuşma'}</Badge>
                {k.mod === 'konusma' ? <Badge tone="neutral">{k.konusmaciSayisi} konuşmacı</Badge> : null}
                {k.yuzIziSayisi ? <Badge tone="cyan">{k.yuzIziSayisi} yüz izi</Badge> : null}
                {k.konular.length ? <Badge tone="neutral">{k.konular.length} konu bloğu</Badge> : null}
                {k.transkriptKaynagi ? <Badge tone="neutral">{k.transkriptKaynagi}</Badge> : null}
                {k.atilanKesit ? <Badge tone="neutral">{k.atilanKesit} gereksiz kesit atıldı</Badge> : null}
                {k.oto?.klipSayisi ? (
                  <Badge tone="brand">
                    otomatik seçim: {k.oto.secilen} sahne
                    {k.oto.atlanan ? ` · ${k.oto.atlanan} zayıf atlandı` : ''}
                    {k.oto.skorEsigi !== null ? ` · eşik ${Math.round(k.oto.skorEsigi)}` : ''}
                  </Badge>
                ) : null}
                {k.oto?.sure ? <Badge tone="brand">otomatik süre · maks {Math.round(k.oto.sureUst)} sn</Badge> : null}
                {qaPuan !== null && qaDerece ? (
                  <Badge tone={qaPuan >= 85 ? 'success' : qaPuan >= 70 ? 'warn' : 'danger'}>
                    en iyi QA {qaPuan}/100 {qaDerece}
                  </Badge>
                ) : null}
                <span className="ml-auto text-[11px] text-fg-subtle">{formatRelative(k.mtime)}</span>
                {k.transkriptVar ? (
                  <Button variant="ghost" size="sm" icon={<FileText className="size-3.5" />} onClick={() => void transkriptAc(k.klasor)}>
                    {acikTranskript === k.klasor ? 'Transkripti kapat' : 'Transkript'}
                  </Button>
                ) : null}
                <Button variant="ghost" size="sm" icon={<FolderOpen className="size-3.5" />} onClick={() => void api.shellReveal(k.klasor)}>
                  Klasör
                </Button>
              </div>

              {k.konular.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {k.konular.map((c) => (
                    <span
                      key={`${k.klasor}-konu-${c.no}`}
                      className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-2.5 py-1 text-[11px] text-fg-muted"
                      title={c.etiket}
                    >
                      <span className="text-fg-subtle">konu {c.no + 1}</span>
                      <span className="max-w-[190px] truncate font-medium text-fg">{c.etiket}</span>
                      <span className="num text-fg-subtle">
                        {sureMetni(c.baslangic)}–{sureMetni(c.bitis)} · {c.skor}
                      </span>
                    </span>
                  ))}
                </div>
              ) : null}

              {acikTranskript === k.klasor ? (
                <div className="flex max-h-[260px] flex-col gap-1 overflow-y-auto rounded-[10px] border border-border bg-[var(--surface-2)] p-2">
                  {!transkript ? (
                    <span className="px-1 py-2 text-[11.5px] text-fg-subtle">Transkript yükleniyor…</span>
                  ) : transkript.kesitler.length ? (
                    transkript.kesitler.map((t, i) => (
                      <div key={`${t.bas}-${i}`} className="flex items-start gap-2 rounded-[6px] px-1.5 py-1 hover:bg-[var(--surface-3)]">
                        <span className="num mt-[1px] w-[46px] shrink-0 text-[11px] text-cyan">{sureMetni(t.bas)}</span>
                        {t.konuBasi ? <span className="mt-[1px] shrink-0 text-[10px] text-fg-subtle">▸ konu</span> : null}
                        <span className="min-w-0 flex-1 text-[12px] leading-snug text-fg">{t.metin}</span>
                        <span className="num mt-[1px] shrink-0 text-[11px] text-fg-subtle">{t.skor != null ? Math.round(t.skor) : '—'}</span>
                      </div>
                    ))
                  ) : (
                    <span className="px-1 py-2 text-[11.5px] text-fg-subtle">Transkript dosyası bulunamadı.</span>
                  )}
                </div>
              ) : null}

              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {k.klipler.map((klip) => (
                  <KlipKart key={`${k.klasor}-${klip.no}`} klip={klip} onIzle={() => setOnizleme({ klip, klasor: k })} />
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

              {k.klipler.some((kl) => Object.keys(kl.panelDagilimi).length) ? (
                <p className="text-[11px] text-fg-subtle">
                  Panel özeti:{' '}
                  {k.klipler
                    .map((kl) => `#${kl.no} ${panelMetni(kl.panelDagilimi) || '—'}`)
                    .join(' · ')}
                </p>
              ) : null}
            </div>
          )
        })}
      </Panel>

      {onizleme ? (
        <KlipOynatici
          klip={onizleme.klip}
          klasor={onizleme.klasor}
          onClose={() => setOnizleme(null)}
          onAc={(yol) => void api.shellOpen(yol)}
          onKlasor={(yol) => void api.shellReveal(yol)}
        />
      ) : null}
    </div>
  )
}

/** Müzik yolu: boş bırakılırsa undefined döner (bot varsayılanı kullanır). */
function muzik_yolu(yol: string): string | undefined {
  const temiz = yol.trim()
  return temiz ? temiz : undefined
}
