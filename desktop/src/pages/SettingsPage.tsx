import { useEffect, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  CloudDownload,
  Cpu,
  ExternalLink,
  FolderOpen,
  Gauge,
  GitBranch,
  MonitorSmartphone,
  Moon,
  PackageCheck,
  Play,
  RefreshCw,
  Save,
  Sun,
  Sparkles,
  Terminal,
} from 'lucide-react'
import { api, unwrap } from '@/lib/api'
import { useApp } from '@/app/AppContext'
import { cn, formatBytes } from '@/lib/utils'
import { Badge, Button, Input, KeyValue, Panel, Progress, SectionTitle, Spinner, Switch } from '@/components/ui/primitives'

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
  const [charLimit, setCharLimit] = useState('')
  const [token, setToken] = useState('')
  const [repo, setRepo] = useState('')
  const [saving, setSaving] = useState(false)
  const [downloadedPath, setDownloadedPath] = useState<string | null>(null)

  useEffect(() => {
    setBotPath(settings?.videoForgePath ?? '')
    setPyPath(settings?.pythonPath ?? '')
  }, [settings?.videoForgePath, settings?.pythonPath])

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
    await saveSettings({ videoForgePath: botPath.trim(), pythonPath: pyPath.trim() })
    setSaving(false)
    pushToast({ tone: 'success', title: 'Ayarlar kaydedildi', message: 'Ortam kontrolu yenilendi.' })
  }

  const applyCharLimit = async (): Promise<void> => {
    const value = Number(charLimit)
    if (!Number.isFinite(value) || value < 200) {
      pushToast({ tone: 'warn', title: 'Gecersiz deger', message: 'En az 200 karakter olmali.' })
      return
    }
    try {
      await unwrap(api.engineSetCharLimit(value))
      await refreshEngine()
      pushToast({ tone: 'success', title: 'Karakter limiti kaydedildi', message: 'bot.db > settings.char_limit guncellendi.' })
    } catch (err) {
      pushToast({ tone: 'error', title: 'Kaydedilemedi', message: String(err) })
    }
  }

  return (
    <div className="space-y-3.5">
      <div className="grid gap-3.5 xl:grid-cols-2">
        <Panel className="p-4">
          <SectionTitle title="Gorunum" subtitle="Tema secimi aninda uygulanir" icon={<Sun className="size-4" />} />
          <div className="mt-3 grid grid-cols-3 gap-2">
            {(
              [
                { key: 'dark', label: 'Karanlik', icon: <Moon className="size-3.5" /> },
                { key: 'light', label: 'Aydinlik', icon: <Sun className="size-3.5" /> },
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
          <div className="mt-3">
            <Switch
              checked={settings?.autoRevealOutput ?? true}
              onChange={(v) => void saveSettings({ autoRevealOutput: v })}
              label="Islem bitince cikti klasorunu otomatik ac"
              hint="Temiz video, ses ve SEO raporu masaustune yazilir"
            />
          </div>
        </Panel>

        <Panel className="p-4">
          <SectionTitle title="Yollar ve Python" subtitle="Bot klasoru ve yorumlayici" icon={<FolderOpen className="size-4" />} />
          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">VideoForge (bot) klasoru</span>
              <Input value={botPath} onChange={(e) => setBotPath(e.target.value)} placeholder="C:\Users\...\Desktop\VideoForge" />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11.5px] text-fg-subtle">
                Python yolu <span className="text-fg-subtle/70">(bos ise py -3 / python otomatik bulunur)</span>
              </span>
              <Input value={pyPath} onChange={(e) => setPyPath(e.target.value)} placeholder="C:\Python312\python.exe" />
            </label>
            <div className="flex gap-2">
              <Button variant="primary" icon={<Save className="size-3.5" />} loading={saving} onClick={() => void save()}>
                Kaydet ve dogrula
              </Button>
              <Button variant="ghost" icon={<Terminal className="size-3.5" />} onClick={() => void api.shellOpen(settings?.videoForgePath ?? '')}>
                Klasoru ac
              </Button>
            </div>
          </div>
        </Panel>
      </div>

      <Panel className="p-4">
        <SectionTitle
          title="Motor konfigurasyonu"
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
                <Badge tone={engine.hdMode ? 'violet' : 'neutral'}>HD mod: {engine.hdMode ? 'acik' : 'kapali'}</Badge>
                <Badge tone="cyan">{engine.procW}x{engine.procH} isleme</Badge>
                <Badge tone="brand">{engine.gpu}</Badge>
                <Badge tone="neutral">${engine.costPerSec}/sn GPU</Badge>
                <Badge tone={engine.elevenlabs ? 'success' : 'warn'}>ElevenLabs {engine.elevenlabs ? 'acik' : 'kapali'}</Badge>
                <Badge tone="neutral">{engine.maxConcurrentGpus} es zamanli GPU</Badge>
                <Badge tone="neutral">{engine.overheadSeconds}sn baslangic maliyeti</Badge>
              </div>
              <div className="mt-3 rounded-[10px] border border-border bg-[var(--surface-2)] p-3">
                <p className="text-[11.5px] font-medium text-fg-muted">Gemini model sirasi (kota optimizasyonu)</p>
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
                  1-2. kanal: 500-600 araligina kelepcelenir · 3. kanal (PopkornFakty): transcript'in %80'i, taban {engine.charLimitSujet}
                </p>
                <div className="mt-2.5 flex gap-2">
                  <Input value={charLimit} onChange={(e) => setCharLimit(e.target.value)} className="h-8 w-24" />
                  <Button size="sm" variant="secondary" onClick={() => void applyCharLimit()}>
                    Kaydet
                  </Button>
                </div>
              </div>
              <div className="mt-3 rounded-[10px] border border-border bg-[var(--surface-2)] p-3">
                <p className="flex items-center gap-2 text-[11.5px] font-medium text-fg-muted">
                  <Cpu className="size-3.5 text-violet" /> Islem profili
                </p>
                <KeyValue label="Smart text filter" value={engine.smartTextFilter ? 'acik' : 'kapali'} />
                <KeyValue label="Kanal 3 metin modu" value="soru cumlesi yasak (sinematik anlatici)" />
                <KeyValue label="Thumbnail" value="YuNet yuz + CLIP konu skoru" />
                <KeyValue label="Beat map" value="Whisper kelime zamanlari" />
              </div>
            </div>
          </div>
        )}
      </Panel>

      {/* ---------------- Guncelleme ---------------- */}
      <div className="grid gap-3.5 xl:grid-cols-2">
        <Panel className="p-4">
          <SectionTitle
            title="Uygulama guncellemesi"
            subtitle={`Mevcut surum: ${info?.version ?? '—'}`}
            icon={<CloudDownload className="size-4" />}
            right={
              <Button
                size="sm"
                variant="primary"
                loading={updateChecking}
                icon={<RefreshCw className="size-3.5" />}
                onClick={() => void checkUpdate()}
              >
                Guncellemeleri kontrol et
              </Button>
            }
          />

          <div className="mt-3 space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">Surum deposu (owner/repo)</span>
                <Input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="alihajiyev/VideoForge" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11.5px] text-fg-subtle">
                  GitHub token <span className="text-fg-subtle/70">(sadece private depo icin)</span>
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
                label="Acilista otomatik kontrol et"
                hint="Yeni surum varsa basligta uyari cikar"
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
                        Yeni surum: {update.latest}
                      </Badge>
                      <span className="text-[11.5px] text-fg-muted">
                        yuklu: {update.current} · depo: {update.repo}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto"
                        icon={<ExternalLink className="size-3.5" />}
                        onClick={() => void api.updateOpenRelease(update.repo)}
                      >
                        Yayin sayfasi
                      </Button>
                    </div>
                    {update.notes ? (
                      <pre className="mt-2 max-h-28 overflow-y-auto rounded-[8px] border border-border bg-[var(--canvas)]/40 p-2 font-mono text-[11px] whitespace-pre-wrap text-fg-muted" data-selectable>
                        {update.notes}
                      </pre>
                    ) : null}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {/* Yeni surume ait kurulum dosyasi one cikarilir ve birincil
                          renkle isaretlenir. Surumde eski dosya da varsa 'eski surum'
                          etiketi alir; boylece yanlislikla eski kurulum indirilmez. */}
                      {(() => {
                        const hedefSurum = (update.latest ?? '').replace(/^v/i, '')
                        const kurulumlar = update.assets.filter((a) => /\.(exe|msi)$/i.test(a.name))
                        if (kurulumlar.length === 0) {
                          return <span className="text-[11.5px] text-warn">Bu surumde .exe dosyasi yayinlanmamis.</span>
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
                            {a.name} ({formatBytes(a.size)}){guncelMi(a.name) ? '' : ' · eski surum'}
                          </Button>
                        ))
                      })()}
                    </div>
                  </>
                ) : update.ok && !update.error ? (
                  <p className="text-[12px] text-fg-muted">
                    Uygulama guncel ({update.current}). Son kontrol:{' '}
                    {new Date(update.checkedAt).toLocaleTimeString('tr-TR', { hour12: false })}
                  </p>
                ) : (
                  <p className="text-[12px] text-warn">{update.error ?? 'Kontrol edilemedi'}</p>
                )}
              </div>
            ) : (
              <p className="text-[11.5px] text-fg-subtle">
                Private depo icin token girin. Ilk surumu yayinlamak icin:{' '}
                <span className="font-mono">npm run release -- --no-bump</span>, sonraki surumler icin{' '}
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
                  Indirildi: <span className="font-mono">{downloadedPath.split(/[\\/]/).pop()}</span>
                </span>
                <div className="ml-auto flex gap-1.5">
                  <Button size="sm" variant="primary" icon={<Play className="size-3.5" />} onClick={() => void launchUpdate(downloadedPath)}>
                    Yeni surumu baslat
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void api.shellReveal(downloadedPath)}>
                    Klasor
                  </Button>
                </div>
              </div>
            ) : null}
            {download?.done && download.error ? <p className="text-[11.5px] text-danger">Indirme hatasi: {download.error}</p> : null}
          </div>
        </Panel>

        <Panel className="p-4">
          <SectionTitle
            title="Bot kodu guncellemesi (git)"
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
                  Bu klasor kendi git deposu degil; <span className="font-mono">{botGit.toplevel}</span> deposunun icinde
                  gorunuyor. Yanlis depoyu cekmemek icin guncelleme kapatildi.
                </p>
              ) : null}
              <KeyValue label="Dal" value={botGit.branch ?? '—'} />
              <KeyValue label="Son commit" value={`${botGit.commit ?? '—'} — ${botGit.subject ?? ''}`} />
              <KeyValue label="Uzak depo" value={botGit.remote ?? '—'} />
              <KeyValue label="Depo koku" value={botGit.toplevel ?? '—'} />
              <KeyValue
                label="Durum"
                value={
                  botGit.dirty ? (
                    <span className="text-warn">yerel degisiklik var ({botGit.changedFiles.length} dosya)</span>
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
                      : 'guncel'
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
                  Bot kodunu guncelle (git pull)
                </Button>
                {botGit.dirty ? (
                  <Button size="md" variant="ghost" onClick={() => void api.shellOpen(info?.videoForgePath ?? '')}>
                    Degisiklikleri incele
                  </Button>
                ) : null}
              </div>
              <p className="mt-2 text-[11px] text-fg-subtle">
                Guncelleme <span className="font-mono">git pull --ff-only</span> ile yapilir; yerel degisiklik varsa islem
                guvenlik icin durdurulur (hicbir kod kaybolmaz).
              </p>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid gap-3.5 xl:grid-cols-[1.4fr_1fr]">
        <Panel className="p-4">
          <SectionTitle
            title="Ortam kontrolleri"
            subtitle={`${env.filter((e) => e.ok).length}/${env.length} basarili`}
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
          <SectionTitle title="Uygulama bilgisi" subtitle="Yol ve surum detaylari" />
          <div className="mt-2">
            <KeyValue label="Uygulama surumu" value={info?.version ?? '—'} />
            <KeyValue label="Electron / Node" value={`${info?.electron ?? '—'} / ${info?.node ?? '—'}`} />
            <KeyValue label="Bot klasoru" value={info?.videoForgePath ?? '—'} />
            <KeyValue label="Veritabani" value={info?.dbPath ?? '—'} />
            <KeyValue label="Log dosyasi" value={info?.logPath ?? '—'} />
            <KeyValue label="cookies.txt" value={info?.cookiesPath ?? '—'} />
            <KeyValue label="Ayar klasoru" value={info?.userData ?? '—'} />
          </div>
          <p className="mt-3 rounded-[10px] border border-[color-mix(in_oklab,var(--warn)_30%,transparent)] bg-warn-soft px-3 py-2 text-[11.5px] text-warn">
            Guvenlik notu: Gemini, ElevenLabs ve transcript API anahtarlari constants.py icinde duz metin duruyor. Bu klasoru
            GitHub'a yuklemeyin; anahtarlari .env dosyasina tasimanizi onerilir.
          </p>
        </Panel>
      </div>
    </div>
  )
}
