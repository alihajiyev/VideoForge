import { useEffect, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  Bell,
  CalendarClock,
  Captions,
  CheckCircle2,
  CloudDownload,
  Eye,
  EyeOff,
  ExternalLink,
  FolderOpen,
  Gauge,
  GitBranch,
  KeyRound,
  MonitorSmartphone,
  Moon,
  PackageCheck,
  Play,
  RefreshCw,
  Save,
  Sun,
  Sparkles,
  Terminal,
  Volume2,
} from 'lucide-react'
import { CHANNELS } from '@shared/channels'
import { api, unwrap } from '@/lib/api'
import { useApp } from '@/app/AppContext'
import { cn, formatBytes } from '@/lib/utils'
import { Badge, Button, Input, KeyValue, Panel, Progress, SectionTitle, Select, Spinner, Switch } from '@/components/ui/primitives'
import type { AltyaziMotoru, GizliAnahtarlar } from '@shared/types'

/** Gizli metin alani: varsayilan olarak maskeli, goz simgesiyle acilir. */
function SecretInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}): ReactNode {
  const [acik, setAcik] = useState(false)
  return (
    <div className="relative">
      <Input
        type={acik ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        className="pr-9 font-mono text-[12px]"
      />
      <button
        type="button"
        onClick={() => setAcik((v) => !v)}
        title={acik ? 'Gizle' : 'Göster'}
        className="absolute top-1/2 right-2 -translate-y-1/2 text-fg-subtle transition-colors hover:text-fg"
      >
        {acik ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
      </button>
    </div>
  )
}

const MOTOR_ETIKET: Record<AltyaziMotoru, string> = {
  auto: 'Otomatik (varsayılan: 3. kanal yerel, diğerleri ZapCap)',
  zapcap: 'ZapCap (şablon ile profesyonel altyazı)',
  yerel: 'Yerel karaoke (ücretsiz, ZapCap gerekmez)',
  remotion: 'Remotion (karaoke kompozit)',
}

export function SettingsPage(): ReactNode {
  const {
    settings,
    saveSettings,
    setMode,
    env,
    envLoading,
    refreshEnv,
    engine,
    refreshEngine,
    info,
    pushToast,
    update,
    updateChecking,
    download,
    autoUpdate,
    installAutoUpdate,
    botGit,
    botGitBusy,
    checkUpdate,
    downloadUpdate,
    launchUpdate,
    refreshBotGit,
    pullBotCode,
  } = useApp()
  const [botPath, setBotPath] = useState('')
  const [pyPath, setPyPath] = useState('')
  const [ssPath, setSsPath] = useState('')
  const [charLimit, setCharLimit] = useState('')
  const [token, setToken] = useState('')
  const [repo, setRepo] = useState('')
  const [saving, setSaving] = useState(false)
  const [downloadedPath, setDownloadedPath] = useState<string | null>(null)
  const [sec, setSec] = useState<GizliAnahtarlar | null>(null)
  const [secSaving, setSecSaving] = useState(false)

  useEffect(() => {
    void api
      .secretsGet()
      .then((r) => {
        if (r.ok) setSec(r.data)
      })
      .catch(() => undefined)
  }, [])

  const secKoy = (patch: Partial<GizliAnahtarlar>): void => setSec((prev) => (prev ? { ...prev, ...patch } : prev))

  const secKaydet = async (): Promise<void> => {
    if (!sec) return
    setSecSaving(true)
    try {
      const next = await unwrap(
        api.secretsSet({
          geminiApiKeys: sec.geminiApiKeys,
          elevenlabsApiKey: sec.elevenlabsApiKey,
          transcriptApiKey: sec.transcriptApiKey,
          zapcapApiKey: sec.zapcapApiKey,
          zapcapTemplateId: sec.zapcapTemplateId,
          altyaziMotoru: sec.altyaziMotoru,
          voiceCh1: sec.voiceCh1,
          voiceCh2: sec.voiceCh2,
          voiceCh3: sec.voiceCh3,
        }),
      )
      setSec(next)
      pushToast({
        tone: 'success',
        title: 'Anahtarlar kaydedildi',
        message: next.shortsStudioFound ? '.env ve ShortsStudio config.py güncellendi.' : '.env güncellendi (ShortsStudio klasörü bulunamadı).',
      })
      void refreshEnv()
    } catch (err) {
      pushToast({ tone: 'error', title: 'Kaydedilemedi', message: String(err) })
    } finally {
      setSecSaving(false)
    }
  }

  useEffect(() => {
    setBotPath(settings?.videoForgePath ?? '')
    setPyPath(settings?.pythonPath ?? '')
    setSsPath(settings?.shortsStudioPath ?? '')
  }, [settings?.videoForgePath, settings?.pythonPath, settings?.shortsStudioPath])

  useEffect(() => {
    setCharLimit(engine ? String(engine.charLimit) : '')
  }, [engine?.charLimit])

  useEffect(() => {
    setRepo(settings?.updateRepo ?? '')
    setToken(settings?.githubToken ?? '')
  }, [settings?.updateRepo, settings?.githubToken])

  useEffect(() => {
    if (download?.done && download.path) setDownloadedPath(download.path)
  }, [download?.done, download?.path])

  const mode = settings?.mode ?? 'dark'

  const save = async (): Promise<void> => {
    setSaving(true)
    await saveSettings({ videoForgePath: botPath.trim(), pythonPath: pyPath.trim(), shortsStudioPath: ssPath.trim() })
    setSaving(false)
    pushToast({ tone: 'success', title: 'Ayarlar kaydedildi', message: 'Ortam kontrolü yenilendi.' })
  }

  const applyCharLimit = async (): Promise<void> => {
    const value = Number(charLimit)
    if (!Number.isFinite(value) || value < 200) {
      pushToast({ tone: 'warn', title: 'Geçersiz değer', message: 'En az 200 karakter olmalı.' })
      return
    }
    try {
      await unwrap(api.engineSetCharLimit(value))
      await refreshEngine()
      pushToast({ tone: 'success', title: 'Karakter limiti kaydedildi', message: 'bot.db > settings.char_limit güncellendi.' })
    } catch (err) {
      pushToast({ tone: 'error', title: 'Kaydedilemedi', message: String(err) })
    }
  }

  return (
    <div className="space-y-3.5">
      <div className="grid gap-3.5 xl:grid-cols-2">
        <Panel className="p-4">
          <SectionTitle title="Görünüm" subtitle="Tema seçimi anında uygulanır" icon={<Sun className="size-4" />} />
          <div className="mt-3 grid grid-cols-3 gap-2">
            {(
              [
                { key: 'dark', label: 'Karanlık', icon: <Moon className="size-3.5" /> },
                { key: 'light', label: 'Aydınlık', icon: <Sun className="size-3.5" /> },
                { key: 'system', label: 'Sistem', icon: <MonitorSmartphone className="size-3.5" /> },
              ] as const
            ).map((opt) => (
              <button
                key={opt.key}
                onClick={() => void setMode(opt.key)}
                className={cn(
                  'flex flex-col items-center gap-1.5 rounded-[11px] border px-3 py-3 transition-colors',
                  mode === opt.key ? 'border-brand bg-brand-soft text-brand' : 'border-border bg-[var(--surface-2)] text-fg-muted hover:border-border-strong',
                )}
              >
                {opt.icon}
                <span className="text-[12px] font-medium">{opt.label}</span>
              </button>
            ))}
          </div>
          <div className="mt-3 space-y-3">
            <Switch
              checked={settings?.autoRevealOutput ?? true}
              onChange={(v) => void saveSettings({ autoRevealOutput: v })}
              label="İşlem bitince çıktı klasörünü otomatik aç"
              hint="Temiz video, ses ve SEO raporu masaüstüne yazılır"
            />
            <Switch
              checked={settings?.notifyOnComplete ?? true}
              onChange={(v) => void saveSettings({ notifyOnComplete: v })}
              label="İş bitince masaüstü bildirimi göster"
              hint="Bildirim, iş tamamlandığında Windows bildirim merkezinde görünür"
            />
            <Switch
              checked={settings?.queueAutoStart ?? true}
              onChange={(v) => void saveSettings({ queueAutoStart: v })}
              label="Kuyrukta sıradaki işi otomatik başlat"
              hint="Bir iş bitince kuyruktaki bekleyen iş kendiliğinden başlar"
            />
          </div>
        </Panel>

        <Panel className="p-4">
          <SectionTitle title="Yollar ve Python" subtitle="Bot klasörü ve Python yorumlayıcısı" icon={<FolderOpen className="size-4" />} />
          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">VideoForge (bot) klasörü</span>
              <Input value={botPath} onChange={(e) => setBotPath(e.target.value)} placeholder="C:\Users\...\Desktop\VideoForge" />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">
                Python yolu <span className="text-fg-subtle/70">(boş ise py -3 / python otomatik bulunur)</span>
              </span>
              <Input value={pyPath} onChange={(e) => setPyPath(e.target.value)} placeholder="C:\Python312\python.exe" />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">
                ShortsStudio klasörü <span className="text-fg-subtle/70">(ZapCap kredisi için; boş = bot klasörünün yanındaki ShortsStudio)</span>
              </span>
              <Input value={ssPath} onChange={(e) => setSsPath(e.target.value)} placeholder="C:\Users\...\Desktop\ShortsStudio" />
            </label>
            <div className="flex gap-2">
              <Button variant="primary" icon={<Save className="size-3.5" />} loading={saving} onClick={() => void save()}>
                Kaydet ve doğrula
              </Button>
              <Button variant="ghost" icon={<Terminal className="size-3.5" />} onClick={() => void api.shellOpen(settings?.videoForgePath ?? '')}>
                Klasörü aç
              </Button>
            </div>
          </div>
        </Panel>
      </div>

      {/* ---------------- API anahtarları + sesler + altyazı ---------------- */}
      <Panel className="p-4">
        <SectionTitle
          title="API anahtarları ve servisler"
          subtitle="Uygulamadan değiştir · botun .env dosyasına yazılır"
          icon={<KeyRound className="size-4" />}
          right={
            sec ? (
              <Badge tone={sec.shortsStudioFound ? 'success' : 'warn'}>
                {sec.shortsStudioFound ? 'ShortsStudio bağlı' : 'ShortsStudio yok'}
              </Badge>
            ) : null
          }
        />
        {!sec ? (
          <div className="flex items-center gap-2 py-8 text-[12px] text-fg-subtle">
            <Spinner /> Anahtarlar okunuyor...
          </div>
        ) : (
          <>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <label className="block lg:col-span-2">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">Gemini API anahtarları (virgülle ayırın)</span>
                <SecretInput value={sec.geminiApiKeys} onChange={(v) => secKoy({ geminiApiKeys: v })} placeholder="AQ.Ab8... , AQ.Ab8..." />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">ElevenLabs API anahtarı</span>
                <SecretInput value={sec.elevenlabsApiKey} onChange={(v) => secKoy({ elevenlabsApiKey: v })} placeholder="sk_..." />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">
                  Transcript API anahtarı <span className="text-fg-subtle/70">(yedek transkript; opsiyonel)</span>
                </span>
                <SecretInput value={sec.transcriptApiKey} onChange={(v) => secKoy({ transcriptApiKey: v })} placeholder="(opsiyonel)" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">ZapCap API anahtarı</span>
                <SecretInput value={sec.zapcapApiKey} onChange={(v) => secKoy({ zapcapApiKey: v })} placeholder="ZapCap anahtarı" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">
                  ZapCap şablon ID <span className="text-fg-subtle/70">(altyazı stili)</span>
                </span>
                <Input
                  value={sec.zapcapTemplateId}
                  onChange={(e) => secKoy({ zapcapTemplateId: e.target.value })}
                  className="font-mono text-[12px]"
                  placeholder="6255949c-..."
                />
              </label>
              <label className="block lg:col-span-2">
                <span className="mb-1 flex items-center gap-1.5 text-[11.5px] text-fg-subtle">
                  <Captions className="size-3.5" /> Altyazı motoru
                </span>
                <Select value={sec.altyaziMotoru} onChange={(e) => secKoy({ altyaziMotoru: e.target.value as AltyaziMotoru })}>
                  {(Object.keys(MOTOR_ETIKET) as AltyaziMotoru[]).map((k) => (
                    <option key={k} value={k}>
                      {MOTOR_ETIKET[k]}
                    </option>
                  ))}
                </Select>
              </label>
            </div>

            <div className="mt-4 border-t border-border pt-3.5">
              <p className="flex items-center gap-1.5 text-[12px] font-medium text-fg-muted">
                <Volume2 className="size-3.5 text-brand" /> Kanal sesleri (ElevenLabs voice ID)
              </p>
              <div className="mt-2 grid gap-3 lg:grid-cols-3">
                {CHANNELS.map((ch, i) => {
                  const alan = (['voiceCh1', 'voiceCh2', 'voiceCh3'] as const)[i]
                  return (
                    <label key={ch.id} className="block">
                      <span className="mb-1 block text-[11.5px] text-fg-subtle">
                        {ch.id} · {ch.name}
                      </span>
                      <Input
                        value={sec[alan]}
                        onChange={(e) => {
                          const v = e.target.value
                          if (alan === 'voiceCh1') secKoy({ voiceCh1: v })
                          else if (alan === 'voiceCh2') secKoy({ voiceCh2: v })
                          else secKoy({ voiceCh3: v })
                        }}
                        className="font-mono text-[12px]"
                        placeholder="voice_id"
                      />
                    </label>
                  )
                })}
              </div>
            </div>

            <div className="mt-3.5 flex flex-wrap items-center gap-2">
              <Button variant="primary" icon={<Save className="size-3.5" />} loading={secSaving} onClick={() => void secKaydet()}>
                Anahtarları kaydet
              </Button>
              <Badge tone="neutral" className="font-mono">
                {sec.envPath}
              </Badge>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-fg-subtle">
              Değerler bot klasöründeki <span className="font-mono">.env</span> dosyasına yazılır; ZapCap anahtarı, şablon ve altyazı motoru ayrıca
              ShortsStudio <span className="font-mono">functions/config.py</span> dosyasına işlenir. Anahtarları sohbette/ekran görüntüsünde paylaşmayın.
            </p>
          </>
        )}
      </Panel>

      <Panel className="p-4">
        <SectionTitle
          title="Motor yapılandırması"
          subtitle="constants.py ve bot.db'den okunur"
          icon={<Gauge className="size-4" />}
          right={
            <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} onClick={() => void refreshEngine()}>
              Yenile
            </Button>
          }
        />
        {!engine ? (
          <div className="flex items-center gap-2 py-8 text-[12px] text-fg-subtle">
            <Spinner /> Okunuyor...
          </div>
        ) : (
          <div className="mt-3 grid gap-4 lg:grid-cols-[1fr_1fr]">
            <div>
              <div className="flex flex-wrap gap-2">
                <Badge tone={engine.hdMode ? 'violet' : 'neutral'}>HD mod: {engine.hdMode ? 'açık' : 'kapalı'}</Badge>
                <Badge tone="cyan">{engine.procW}x{engine.procH} işleme</Badge>
                <Badge tone="brand">{engine.gpu}</Badge>
                <Badge tone="neutral">${engine.costPerSec}/sn GPU</Badge>
                <Badge tone={engine.elevenlabs ? 'success' : 'warn'}>ElevenLabs {engine.elevenlabs ? 'açık' : 'kapalı'}</Badge>
                <Badge tone="neutral">{engine.maxConcurrentGpus} eş zamanlı GPU</Badge>
                <Badge tone="neutral">{engine.overheadSeconds}sn başlangıç maliyeti</Badge>
              </div>
              <div className="mt-3 rounded-[10px] border border-border bg-[var(--surface-2)] p-3">
                <p className="text-[11.5px] font-medium text-fg-muted">Gemini model sırası (kota optimizasyonu)</p>
                <ol className="mt-1.5 space-y-0.5">
                  {engine.models.map((m, i) => (
                    <li key={m} className="flex items-center gap-2 font-mono text-[11px] text-fg-muted">
                      <span className="num text-fg-subtle">{i + 1}.</span>
                      {m}
                      {i < 3 ? <Badge tone="success">RPD 500</Badge> : <Badge tone="warn">RPD 20</Badge>}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
            <div>
              <div className="rounded-[10px] border border-border bg-[var(--surface-2)] p-3">
                <p className="flex items-center gap-2 text-[11.5px] font-medium text-fg-muted">
                  <Sparkles className="size-3.5 text-cyan" /> Seslendirme karakter limiti
                </p>
                <p className="mt-1 text-[11px] text-fg-subtle">
                  1-2. kanal: 500-600 aralığına sabitlenir · 3. kanal (PopkornFakty): transkriptin %80'i, taban {engine.charLimitSujet}
                </p>
                <div className="mt-2.5 flex gap-2">
                  <Input value={charLimit} onChange={(e) => setCharLimit(e.target.value)} className="h-8 w-24" />
                  <Button size="sm" variant="secondary" onClick={() => void applyCharLimit()}>
                    Kaydet
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </Panel>

      {/* ---------------- Guncelleme ---------------- */}
      <div className="grid gap-3.5 xl:grid-cols-2">
        <Panel className="p-4">
          <SectionTitle
            title="Uygulama güncellemesi"
            subtitle={`Mevcut sürüm: ${info?.version ?? '—'}`}
            icon={<CloudDownload className="size-4" />}
            right={
              <Button
                size="sm"
                variant="primary"
                loading={updateChecking}
                icon={<RefreshCw className="size-3.5" />}
                onClick={() => void checkUpdate()}
              >
                Güncellemeleri kontrol et
              </Button>
            }
          />

          <div className="mt-3 space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">Sürüm deposu (owner/repo)</span>
                <Input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="alihajiyev/VideoForge" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">
                  GitHub token <span className="text-fg-subtle/70">(sadece private depo için)</span>
                </span>
                <Input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="ghp_... (bos = public depo)"
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Switch
                checked={settings?.autoCheckUpdates ?? true}
                onChange={(v) => void saveSettings({ autoCheckUpdates: v })}
                label="Açılışta otomatik kontrol et"
                hint="Yeni sürüm varsa başlıkta uyarı çıkar"
              />
              <Button
                size="sm"
                variant="secondary"
                icon={<Save className="size-3.5" />}
                onClick={() => void saveSettings({ updateRepo: repo.trim(), githubToken: token.trim() })}
              >
                Depoyu kaydet
              </Button>
            </div>

            {autoUpdate && autoUpdate.durum !== 'kapali' ? (
              <div className="rounded-[10px] border border-[color-mix(in_oklab,var(--brand)_32%,transparent)] bg-brand-soft px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="brand" dot={autoUpdate.durum === 'indiriliyor' || autoUpdate.durum === 'kontrol'}>
                    Uygulama içi güncelleme
                  </Badge>
                  <span className="text-[12px] text-fg-muted">
                    {autoUpdate.durum === 'kontrol'
                      ? 'Kontrol ediliyor...'
                      : autoUpdate.durum === 'guncel'
                        ? `Uygulama güncel (v${autoUpdate.current})`
                        : autoUpdate.durum === 'mevcut'
                          ? `Yeni sürüm v${autoUpdate.version ?? ''} bulundu, indiriliyor...`
                          : autoUpdate.durum === 'indiriliyor'
                            ? `Yeni sürüm v${autoUpdate.version ?? ''} indiriliyor (%${autoUpdate.pct})`
                            : autoUpdate.durum === 'hazir'
                              ? `v${autoUpdate.version ?? ''} indirildi. Yeniden başlatınca kurulacak.`
                              : `Güncelleme hatası: ${autoUpdate.error ?? 'bilinmiyor'}`}
                  </span>
                  {autoUpdate.durum === 'hazir' ? (
                    <Button
                      size="sm"
                      variant="primary"
                      className="ml-auto"
                      icon={<RefreshCw className="size-3.5" />}
                      onClick={() => void installAutoUpdate()}
                    >
                      Şimdi güncelle ve yeniden başlat
                    </Button>
                  ) : null}
                </div>
                {autoUpdate.durum === 'indiriliyor' ? (
                  <div className="mt-2">
                    <Progress value={autoUpdate.pct} />
                  </div>
                ) : null}
                {autoUpdate.durum === 'hazir' ? (
                  <p className="mt-2 text-[11px] text-fg-subtle">
                    Kurulum setup sihirbazı olmadan sessizce yapılır; uygulama kendini yeniden başlatır.
                  </p>
                ) : null}
              </div>
            ) : null}

            {update ? (
              <div
                className={cn(
                  'rounded-[10px] border px-3 py-2.5',
                  update.available
                    ? 'border-[color-mix(in_oklab,var(--brand)_35%,transparent)] bg-brand-soft'
                    : update.ok
                      ? 'border-border bg-[var(--surface-2)]'
                      : 'border-[color-mix(in_oklab,var(--warn)_30%,transparent)] bg-warn-soft',
                )}
              >
                {update.available ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="brand" dot>
                        Yeni sürüm: {update.latest}
                      </Badge>
                      <span className="text-[11.5px] text-fg-muted">
                        yüklü: {update.current} · depo: {update.repo}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto"
                        icon={<ExternalLink className="size-3.5" />}
                        onClick={() => void api.updateOpenRelease(update.repo)}
                      >
                        Yayın sayfası
                      </Button>
                    </div>
                    {update.notes ? (
                      <pre className="mt-2 max-h-28 overflow-y-auto rounded-[8px] border border-border bg-[var(--canvas)]/40 p-2 font-mono text-[11px] whitespace-pre-wrap text-fg-muted" data-selectable>
                        {update.notes}
                      </pre>
                    ) : null}
                    {autoUpdate && autoUpdate.durum !== 'kapali' ? null : (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {/* Yeni surume ait kurulum dosyasi one cikarilir ve birincil
                          renkle isaretlenir. Surumde eski dosya da varsa 'eski surum'
                          etiketi alir; boylece yanlislikla eski kurulum indirilmez. */}
                      {(() => {
                        const hedefSurum = (update.latest ?? '').replace(/^v/i, '')
                        const kurulumlar = update.assets.filter((a) => /\.(exe|msi)$/i.test(a.name))
                        if (kurulumlar.length === 0) {
                          return <span className="text-[11.5px] text-warn">Bu sürümde .exe dosyası yayınlanmamış.</span>
                        }
                        const guncelMi = (ad: string) => !hedefSurum || ad.includes(hedefSurum)
                        const sirali = [...kurulumlar].sort(
                          (a, b) => Number(guncelMi(b.name)) - Number(guncelMi(a.name))
                        )
                        return sirali.map((a) => (
                          <Button
                            key={a.name}
                            size="sm"
                            variant={guncelMi(a.name) ? 'primary' : 'secondary'}
                            icon={<CloudDownload className="size-3.5" />}
                            loading={download?.name === a.name && !download.done}
                            onClick={() => void downloadUpdate(a.name).then((p) => setDownloadedPath(p))}
                          >
                            {a.name} ({formatBytes(a.size)}){guncelMi(a.name) ? '' : ' · eski sürüm'}
                          </Button>
                        ))
                      })()}
                    </div>
                    )}
                  </>
                ) : update.ok && !update.error ? (
                  <p className="text-[12px] text-fg-muted">
                    Uygulama güncel ({update.current}). Son kontrol:{' '}
                    {new Date(update.checkedAt).toLocaleTimeString('tr-TR', { hour12: false })}
                  </p>
                ) : (
                  <p className="text-[12px] text-warn">{update.error ?? 'Kontrol edilemedi'}</p>
                )}
              </div>
            ) : (
              <p className="text-[11.5px] text-fg-subtle">
                Private depo için token girin. İlk sürümü yayınlamak için:{' '}
                <span className="font-mono">npm run release -- --no-bump</span>, sonraki sürümler için{' '}
                <span className="font-mono">npm run release</span>
              </p>
            )}

            {download && !download.done ? (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11.5px] text-fg-muted">
                  <span className="truncate">{download.name} indiriliyor...</span>
                  <span className="num">
                    {formatBytes(download.received)} / {formatBytes(download.total)} ({download.pct}%)
                  </span>
                </div>
                <Progress value={download.pct} tone="cyan" />
              </div>
            ) : null}

            {downloadedPath ? (
              <div className="flex flex-wrap items-center gap-2 rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2">
                <PackageCheck className="size-3.5 text-success" />
                <span className="text-[11.5px] text-fg-muted">
                  İndirildi: <span className="font-mono">{downloadedPath.split(/[\\/]/).pop()}</span>
                </span>
                <div className="ml-auto flex gap-1.5">
                  <Button size="sm" variant="primary" icon={<Play className="size-3.5" />} onClick={() => void launchUpdate(downloadedPath)}>
                    Yeni sürümü başlat
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void api.shellReveal(downloadedPath)}>
                    Klasör
                  </Button>
                </div>
              </div>
            ) : null}
            {download?.done && download.error ? <p className="text-[11.5px] text-danger">İndirme hatası: {download.error}</p> : null}
          </div>
        </Panel>

        <Panel className="p-4">
          <SectionTitle
            title="Bot kodu güncellemesi (git)"
            subtitle={info?.videoForgePath}
            icon={<GitBranch className="size-4" />}
            right={
              <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} onClick={() => void refreshBotGit(true)}>
                Yenile
              </Button>
            }
          />
          {!botGit ? (
            <div className="flex items-center gap-2 py-6 text-[12px] text-fg-subtle">
              <Spinner /> Git durumu okunuyor...
            </div>
          ) : !botGit.ok ? (
            <p className="mt-3 rounded-[10px] border border-[color-mix(in_oklab,var(--warn)_30%,transparent)] bg-warn-soft px-3 py-2 text-[11.5px] text-warn">
              {botGit.error}
            </p>
          ) : (
            <div className="mt-2">
              {!botGit.isBotRepo ? (
                <p className="mb-2 rounded-[10px] border border-[color-mix(in_oklab,var(--warn)_30%,transparent)] bg-warn-soft px-3 py-2 text-[11.5px] text-warn">
                  Bu klasör kendi git deposu değil; <span className="font-mono">{botGit.toplevel}</span> deposunun içinde
                  görünüyor. Yanlış depoyu çekmemek için güncelleme kapatıldı.
                </p>
              ) : null}
              <KeyValue label="Dal" value={botGit.branch ?? '—'} />
              <KeyValue label="Son commit" value={`${botGit.commit ?? '—'} — ${botGit.subject ?? ''}`} />
              <KeyValue label="Uzak depo" value={botGit.remote ?? '—'} />
              <KeyValue label="Depo kökü" value={botGit.toplevel ?? '—'} />
              <KeyValue
                label="Durum"
                value={
                  botGit.dirty ? (
                    <span className="text-warn">yerel değişiklik var ({botGit.changedFiles.length} dosya)</span>
                  ) : (
                    <span className="text-success">temiz</span>
                  )
                }
              />
              <KeyValue
                label="Uzak fark"
                value={
                  botGit.behind === null
                    ? 'bilinmiyor (upstream yok)'
                    : botGit.behind > 0
                      ? `${botGit.behind} yeni commit var`
                      : 'güncel'
                }
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  icon={<GitBranch className="size-3.5" />}
                  loading={botGitBusy}
                  disabled={botGit.dirty || !botGit.isBotRepo}
                  onClick={() => void pullBotCode()}
                >
                  Bot kodunu güncelle (git pull)
                </Button>
                {botGit.dirty ? (
                  <Button size="md" variant="ghost" onClick={() => void api.shellOpen(info?.videoForgePath ?? '')}>
                    Değişiklikleri incele
                  </Button>
                ) : null}
              </div>
              <p className="mt-2 text-[11px] text-fg-subtle">
                Güncelleme <span className="font-mono">git pull --ff-only</span> ile yapılır; yerel değişiklik varsa işlem
                güvenlik için durdurulur (hiçbir kod kaybolmaz).
              </p>
            </div>
          )}
        </Panel>
      </div>

      <Panel className="p-4">
        <SectionTitle
          title="Otomasyon ve bildirimler"
          subtitle="Uygulama açıkken günlük otomatik çalıştırma"
          icon={<CalendarClock className="size-4" />}
        />
        <div className="mt-3 space-y-3">
          <Switch
            checked={settings?.scheduleEnabled ?? false}
            onChange={(v) => void saveSettings({ scheduleEnabled: v })}
            label="Günlük zamanlanmış görev"
            hint="Seçilen saatte otomatik olarak başlar (uygulama açıkken çalışır)"
          />
          <div className="grid gap-2.5 sm:grid-cols-[120px_170px_190px]">
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">Saat</span>
              <Input
                type="time"
                value={settings?.scheduleTime ?? '09:00'}
                disabled={!settings?.scheduleEnabled}
                onChange={(e) => void saveSettings({ scheduleTime: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">Görev</span>
              <Select
                value={settings?.scheduleKind ?? 'discover'}
                disabled={!settings?.scheduleEnabled}
                onChange={(e) => void saveSettings({ scheduleKind: e.target.value as 'discover' | 'weekly' })}
              >
                <option value="discover">Keşif (öneri topla)</option>
                <option value="weekly">Çok günlü zincir (üret)</option>
              </Select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">Kanal</span>
              <Select
                value={settings?.scheduleChannel ?? '1'}
                disabled={!settings?.scheduleEnabled}
                onChange={(e) => void saveSettings({ scheduleChannel: e.target.value as '1' | '2' | '3' })}
              >
                {CHANNELS.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} · {c.name}
                  </option>
                ))}
              </Select>
            </label>
          </div>
          <div className="flex items-start gap-2 rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2 text-[11.5px] text-fg-subtle leading-relaxed">
            <Bell className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" />
            <span>
              Zamanlanmış görev yalnızca uygulama açıkken tetiklenir ve aynı gün aynı saatte ikinci kez çalışmaz. Gün sayısı için
              Panel'deki “Kaç günlük plan?” değeri kullanılır.
            </span>
          </div>
        </div>
      </Panel>

      <div className="grid gap-3.5 xl:grid-cols-[1.4fr_1fr]">
        <Panel className="p-4">
          <SectionTitle
            title="Ortam kontrolleri"
            subtitle={`${env.filter((e) => e.ok).length}/${env.length} başarılı`}
            icon={<CheckCircle2 className="size-4" />}
            right={
              <Button size="sm" variant="ghost" icon={<RefreshCw className={cn('size-3.5', envLoading && 'animate-spin')} />} onClick={() => void refreshEnv()}>
                Yeniden kontrol
              </Button>
            }
          />
          <div className="mt-3 grid gap-2">
            {env.map((check) => (
              <div key={check.id} className="flex items-start gap-2.5 rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2">
                {check.ok ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success" /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn" />}
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] font-medium text-fg">{check.label}</p>
                  <p className="truncate text-[11px] text-fg-subtle" title={check.detail}>
                    {check.detail}
                  </p>
                  {!check.ok && check.fix ? <p className="mt-0.5 text-[11px] text-warn">{check.fix}</p> : null}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="p-4">
          <SectionTitle title="Uygulama bilgisi" subtitle={`VideoForge ${info?.version ?? '—'} · Electron ${info?.electron ?? '—'}`} />
          <div className="mt-2">
            <KeyValue label="Bot klasörü" value={info?.videoForgePath ?? '—'} />
            <KeyValue label="Ayar klasörü" value={info?.userData ?? '—'} />
          </div>
          <p className="mt-3 rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2 text-[11.5px] text-fg-subtle leading-relaxed">
            Anahtarları yukarıdaki <span className="text-fg-muted">“API anahtarları ve servisler”</span> bölümünden değiştirebilirsin; değerler botun{' '}
            <span className="font-mono text-fg-muted">.env</span> dosyasına yazılır ve sürüm kontrolüne girmez.
          </p>
        </Panel>
      </div>
    </div>
  )
}
