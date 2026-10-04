/** Renderer <-> Electron arasindaki tum veri sozlesmeleri. */

export type ChannelId = '1' | '2' | '3'

export interface ChannelDef {
  id: ChannelId
  name: string
  niche: string
  script: string
  voiceId: string
  accent: string
  note: string
}

export type JobKind = 'channel' | 'discover' | 'weekly' | 'clean'
export type JobStatus = 'running' | 'done' | 'error' | 'cancelled'

export type LogLevel = 'info' | 'ok' | 'warn' | 'err' | 'step' | 'ai' | 'gpu' | 'tts' | 'raw'

export interface LogLine {
  /** monoton artan sira numarasi (render icin) */
  i: number
  /** epoch ms */
  t: number
  level: LogLevel
  text: string
}

export interface StageDef {
  key: string
  label: string
  hint?: string
}

export type ArtifactKind = 'video' | 'audio' | 'seo' | 'thumb' | 'report' | 'plan' | 'other'

export interface Artifact {
  kind: ArtifactKind
  name: string
  path: string
  size: number
  mtime: number
}

export interface JobStats {
  gpu: string | null
  cost: string | null
  duration: string | null
  gemini: string | null
  chunks: number | null
}

export interface JobRequest {
  kind: JobKind
  channelId?: ChannelId
  link?: string
  force?: boolean
  /** Kesif plan modu (gunSayisi > 1 ile birlikte kullanilir). */
  haftalik?: boolean
  /** Kac gunluk plan kurulsun (7 sabit degil). */
  gunSayisi?: number
  /** Tek video islenirken: bu videonun plandaki gun numarasi. */
  gun?: number
  /** Tek video islenirken: planin toplam gun sayisi. */
  gunToplam?: number
}

export interface JobState {
  id: string
  kind: JobKind
  title: string
  subtitle: string
  status: JobStatus
  stages: StageDef[]
  stageIndex: number
  stepLabel: string
  startedAt: number | null
  endedAt: number | null
  exitCode: number | null
  pid: number | null
  lines: LogLine[]
  artifacts: Artifact[]
  stats: JobStats
  error: string | null
}

export interface EnvCheck {
  id: string
  label: string
  ok: boolean
  detail: string
  fix?: string
}

export interface AppSettings {
  mode: 'dark' | 'light' | 'system'
  videoForgePath: string
  pythonPath: string
  autoRevealOutput: boolean
  logTailLines: number
  /** Uygulama acilirken guncelleme kontrol edilsin mi */
  autoCheckUpdates: boolean
  /** Surum yayinlari icin GitHub deposu (owner/repo) */
  updateRepo: string
  /** Private depo yayinlari icin opsiyonel GitHub token (bos = public) */
  githubToken: string
  /** Cok gunlu plan/zincir kac gun olsun (7 sabit degil, 2-60) */
  gunSayisi: number
  /** Is bitince masaustu bildirimi gosterilsin mi */
  notifyOnComplete: boolean
  /** Kuyrukta is bitince siradaki otomatik baslatilsin mi */
  queueAutoStart: boolean
  /** Ilk kurulum rehberi kapatildi mi */
  onboardingDone: boolean
  /** Gunluk otomatik calisma (uygulama acikken) aktif mi */
  scheduleEnabled: boolean
  /** Zamanlanmis gorev saati (HH:MM, yerel saat) */
  scheduleTime: string
  /** Zamanlanmis gorev turu */
  scheduleKind: 'discover' | 'weekly'
  /** Zamanlanmis gorevin kanali */
  scheduleChannel: ChannelId
  /** ShortsStudio klasoru (Zapcap anahtarini okumak icin; bos = bot klasorunun kardesi) */
  shortsStudioPath: string
}

/** Kuyrukta bekleyen/tamamlanan isler (coklu link isleme icin). */
export type KuyrukDurumu = 'bekliyor' | 'calisiyor' | 'bitti' | 'hata' | 'iptal'

export interface KuyrukOgesi {
  id: string
  kind: JobKind
  channelId: ChannelId
  link?: string
  force?: boolean
  haftalik?: boolean
  gunSayisi?: number
  status: KuyrukDurumu
  title: string
  addedAt: number
  startedAt: number | null
  endedAt: number | null
}

/** Tek bir isin harcama kaydi (Modal GPU maliyeti). */
export interface HarcamaKaydi {
  t: number
  baslik: string
  kind: JobKind
  usd: number
  saniye: number | null
}

export interface HarcamaOzeti {
  ok: boolean
  /** Bu takvim ayindaki toplam harcama (USD) */
  ayUsd: number
  bugunUsd: number
  /** Ay icindeki is sayisi */
  isSayisi: number
  /** Gunluk toplamlar (son 30 gun, eski -> yeni) */
  gunler: { gun: string; usd: number }[]
  /** Son kayitlar (yeni -> eski) */
  son: HarcamaKaydi[]
  /** Ayni turdeki islerin ortalama maliyeti (is oncesi tahmin icin) */
  ortalama: Record<string, number>
}

/** Gemini gunluk kota gostergesi (tahmini). */
export interface KotaBilgisi {
  ok: boolean
  /** Yerel tarih (YYYY-MM-DD) */
  tarih: string
  /** Bugun sayilan AI cagrisi (tahmini) */
  aiCagrisi: number
  /** Kotanin sifirlanacagi an (epoch ms, Pasifik gece yarisi) */
  sifirlanmaMs: number
  /** Gunluk istek limitleri (kuvvetli -> zayif modeller) */
  limitler: number[]
  modeller: string[]
}

export interface UpdateAsset {
  name: string
  size: number
  url: string
  isApiUrl: boolean
}

export interface UpdateInfo {
  ok: boolean
  error?: string
  current: string
  latest: string | null
  available: boolean
  notes: string
  publishedAt: string | null
  htmlUrl: string | null
  assets: UpdateAsset[]
  repo: string
  checkedAt: number
}

export interface BotGitInfo {
  ok: boolean
  error?: string
  isRepo: boolean
  /** Bot klasoru git deposunun kendisi mi (baska bir deponun icinde degil mi)? */
  isBotRepo: boolean
  /** Deponun kok klasoru (git rev-parse --show-toplevel). */
  toplevel: string | null
  gitAvailable: boolean
  branch: string | null
  commit: string | null
  subject: string | null
  dirty: boolean
  remote: string | null
  behind: number | null
  ahead: number | null
  changedFiles: string[]
}

export interface DownloadProgress {
  name: string
  received: number
  total: number
  pct: number
  done: boolean
  error?: string
  path?: string
}

/** Uygulama ici otomatik guncelleme durumu (electron-updater). */
export type AutoUpdateDurum =
  | 'kapali' // desteklenmiyor (paketli degil / yapilandirma yok)
  | 'bosta' // henuz kontrol edilmedi
  | 'kontrol' // kontrol ediliyor
  | 'guncel' // yeni surum yok
  | 'mevcut' // yeni surum var, indirme basladi/bekliyor
  | 'indiriliyor'
  | 'hazir' // indirildi, yeniden baslatinca kurulur
  | 'hata'

export interface AutoUpdateState {
  durum: AutoUpdateDurum
  /** Uygulamanin su anki surumu */
  current: string
  /** Bulunan yeni surum (varsa) */
  version: string | null
  /** Indirme yuzdesi (0-100) */
  pct: number
  received: number
  total: number
  error?: string
}

/** Bir hizmetin kalan kredi/kota durumu (ElevenLabs, Zapcap, Gemini...). */
export type KrediDurum = 'ok' | 'anahtar-yok' | 'hata' | 'bilgi'

export interface KrediServisi {
  id: string
  ad: string
  durum: KrediDurum
  /** Kalan miktar (varsa) */
  kalan: number | null
  /** Toplam miktar (varsa) */
  toplam: number | null
  /** Olcu birimi: 'karakter' | 'USD' | 'istek' | '' */
  birim: string
  detay?: string
  hata?: string
  /** Kotanin sifirlanacagi an (epoch ms, varsa) */
  sifirlanmaMs?: number | null
}

/** Altyazi motorlari: ShortsStudio final kompozitini nasil bastigi. */
export type AltyaziMotoru = 'auto' | 'zapcap' | 'yerel' | 'remotion'

/** Uygulamadan duzenlenen gizli anahtarlar, sesler ve altyazi ayari. */
export interface GizliAnahtarlar {
  geminiApiKeys: string
  elevenlabsApiKey: string
  transcriptApiKey: string
  zapcapApiKey: string
  zapcapTemplateId: string
  altyaziMotoru: AltyaziMotoru
  voiceCh1: string
  voiceCh2: string
  voiceCh3: string
  /** Bot klasorundeki .env yolu (bilgi amacli) */
  envPath: string
  /** ShortsStudio klasoru bulundu mu (ZapCap/template oraya da yazilir) */
  shortsStudioFound: boolean
}

export interface LibraryVideo {
  id: number
  link: string
  created_at: string
}

export interface LibraryOneri {
  video_id: string
  skor: number
  tip: string
  kanal: string
  tarih: string
}

export interface LibraryData {
  ok: boolean
  error?: string
  videos: LibraryVideo[]
  oneriler: LibraryOneri[]
  settings: Record<string, string>
  counts: { videos: number; oneriler: number }
}

export interface EngineConfig {
  ok: boolean
  error?: string
  models: string[]
  elevenlabs: boolean
  hdMode: boolean
  procW: number
  procH: number
  gpu: string
  costPerSec: number
  charLimit: number
  charLimitSujet: number
  maxConcurrentGpus: number
  overheadSeconds: number
  smartTextFilter: boolean
}

export interface WeeklyPlanItem {
  gun?: number
  baslik?: string
  link?: string
  kanal?: string
  skor?: number
  tip?: string
  [key: string]: unknown
}

export interface AppInfo {
  version: string
  electron: string
  node: string
  platform: string
  userData: string
  desktop: string
  videoForgePath: string
  projectRoot: string
  cookiesPath: string
  dbPath: string
  logPath: string
}

export interface ReportPreview {
  ok: boolean
  error?: string
  title?: string
  headings?: string[]
  /** Rapor icindeki bolumler (label -> metin) */
  sections?: { label: string; text: string }[]
  text?: string
}

export interface RunHistoryItem {
  id: string
  kind: JobKind
  title: string
  status: JobStatus
  startedAt: number | null
  endedAt: number | null
  exitCode: number | null
  /** Botun bildirdigi maliyet metni (orn. "$0.012") */
  cost: string | null
  /** Sure (ms) */
  durationMs: number | null
  /** Is sonunda bulunan cikti dosyalari */
  artifacts: Artifact[]
}
