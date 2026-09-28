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
  haftalik?: boolean
  gun?: number
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
}
