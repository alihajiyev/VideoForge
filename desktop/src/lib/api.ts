import type { VideoForgeApi, Result, RunEvent, ReportGroupPayload } from '@electron/preload'
import { CHANNELS } from '@shared/channels'
import type {
  AppInfo,
  AppSettings,
  BotGitInfo,
  DownloadProgress,
  EngineConfig,
  EnvCheck,
  JobRequest,
  JobState,
  LibraryData,
  ReportPreview,
  RunHistoryItem,
  UpdateInfo,
} from '@shared/types'

export type { ReportGroupPayload, Result, RunEvent }

export const isDesktop = typeof window !== 'undefined' && Boolean((window as unknown as { vfgui?: unknown }).vfgui)

/* ------------------------------------------------------------------ */
/* Tarayici onizleme modu (npm run dev:web) icin sahte veri           */
/* ------------------------------------------------------------------ */

const mockSettings: AppSettings = {
  mode: 'dark',
  videoForgePath: 'C:\\Users\\Vafa\\Desktop\\VideoForge',
  pythonPath: '',
  autoRevealOutput: true,
  logTailLines: 800,
  autoCheckUpdates: true,
  updateRepo: 'alihajiyev/VideoForge',
  githubToken: '',
}

const mockUpdate: UpdateInfo = {
  ok: true,
  current: '1.0.0',
  latest: '1.1.0',
  available: true,
  notes: '- Yeni: link kuyrugu\n- Duzeltme: TTS uzunluk hesabi',
  publishedAt: new Date().toISOString(),
  htmlUrl: 'https://github.com/alihajiyev/VideoForge/releases/tag/v1.1.0',
  assets: [{ name: 'VideoForge-1.1.0-portable.exe', size: 111_300_000, url: 'https://example.com/a.exe', isApiUrl: false }],
  repo: 'alihajiyev/VideoForge',
  checkedAt: Date.now(),
}

const mockGit: BotGitInfo = {
  ok: true,
  isRepo: true,
  isBotRepo: true,
  toplevel: 'C:\\Users\\Vafa\\Desktop\\VideoForge',
  gitAvailable: true,
  branch: 'main',
  commit: 'a1b2c3d',
  subject: 'kota optimizasyonu + parcali fallback',
  dirty: false,
  remote: 'https://github.com/alihajiyev/VideoForge.git',
  behind: 0,
  ahead: 0,
  changedFiles: [],
}

const mockInfo: AppInfo = {
  version: '1.0.0',
  electron: '44.4.3',
  node: '24.16.0',
  platform: 'win32',
  userData: 'C:\\Users\\Vafa\\AppData\\Roaming\\VideoForge',
  desktop: 'C:\\Users\\Vafa\\Desktop',
  videoForgePath: mockSettings.videoForgePath,
  projectRoot: 'C:\\Users\\Vafa\\Desktop\\VideoForge\\desktop',
  cookiesPath: 'C:\\Users\\Vafa\\Desktop\\VideoForge\\cookies.txt',
  dbPath: 'C:\\Users\\Vafa\\Desktop\\VideoForge\\bot.db',
  logPath: 'C:\\Users\\Vafa\\Desktop\\VideoForge\\bot_log.txt',
}

const mockEnv: EnvCheck[] = [
  { id: 'python', label: 'Python 3.10+', ok: true, detail: 'py -3 (Python 3.12)' },
  { id: 'botfiles', label: 'VideoForge dosyalari', ok: true, detail: '7 dosya dogrulandi' },
  { id: 'modal', label: 'modal paketi', ok: true, detail: '1.5.5' },
  { id: 'genai', label: 'google-genai', ok: true, detail: '2.24.0' },
  { id: 'ffmpeg', label: 'ffmpeg', ok: true, detail: 'ffmpeg version 7.1' },
  { id: 'cookies', label: 'cookies.txt', ok: false, detail: '12 gun once guncellendi', fix: 'cookies.txt yenileyin' },
]

const mockEngine: EngineConfig = {
  ok: true,
  models: ['gemini-flash-lite-latest', 'gemini-3.1-flash-lite', 'gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-3-flash-preview'],
  elevenlabs: true,
  hdMode: false,
  procW: 540,
  procH: 960,
  gpu: 'L4',
  costPerSec: 0.000222,
  charLimit: 500,
  charLimitSujet: 570,
  maxConcurrentGpus: 10,
  overheadSeconds: 75,
  smartTextFilter: false,
}

const mockLibrary: LibraryData = {
  ok: true,
  videos: [
    { id: 42, link: 'dQw4w9WgXcQ', created_at: '2026-09-27 08:12:04' },
    { id: 41, link: '7647993089797164320', created_at: '2026-09-26 19:44:31' },
  ],
  oneriler: [
    { video_id: 'aBc123XyZ-_', skor: 8.4, tip: 'KAZANAN', kanal: '1', tarih: '2026-09-28 06:40:00' },
    { video_id: 'zZ9Y8x7W6v5', skor: 3.1, tip: 'COP', kanal: '3', tarih: '2026-09-28 06:41:12' },
  ],
  settings: { char_limit: '500', working_model: 'gemini-flash-lite-latest' },
  counts: { videos: 2, oneriler: 2 },
}

const mockGroups: ReportGroupPayload[] = [
  {
    key: 'desktop::Mona Lisa',
    dir: 'C:\\Users\\Vafa\\Desktop',
    title: 'Mona Lisa fotografini neden cekmemelisiniz',
    totalBytes: 48_231_113,
    mtime: Date.now() - 3600_000,
    items: [
      { kind: 'video', name: 'Mona_Lisa_798_CLEAN.mp4', path: 'C:\\Users\\Vafa\\Desktop\\Mona_Lisa_798_CLEAN.mp4', size: 44_000_000, mtime: Date.now() - 3600_000 },
      { kind: 'audio', name: 'Mona_Lisa_798_VOICEOVER.mp3', path: 'C:\\Users\\Vafa\\Desktop\\Mona_Lisa_798_VOICEOVER.mp3', size: 1_200_000, mtime: Date.now() - 3600_000 },
      { kind: 'thumb', name: 'Mona_Lisa_798_THUMB.png', path: 'C:\\Users\\Vafa\\Desktop\\Mona_Lisa_798_THUMB.png', size: 800_000, mtime: Date.now() - 3600_000 },
      { kind: 'seo', name: 'Mona_Lisa_798_SEO.html', path: 'C:\\Users\\Vafa\\Desktop\\Mona_Lisa_798_SEO.html', size: 22_000, mtime: Date.now() - 3600_000 },
    ],
  },
]

function withLines(state: Omit<JobState, 'lines'>, lines: JobState['lines']): JobState {
  return { ...state, lines }
}

const listeners = new Set<(e: RunEvent) => void>()
function emitRun(event: RunEvent): void {
  for (const l of listeners) l(event)
}

let mockJob: JobState | null = null

function mockStateSnapshot(req: JobRequest): Omit<JobState, 'lines'> & { lineCount: number } {
  const ch = CHANNELS.find((c) => c.id === (req.channelId || '1'))
  const stages = [
    { key: 'download', label: 'Indirme', hint: 'yt-dlp + cookies.txt' },
    { key: 'transcript', label: 'Transkript', hint: 'Altyazi / Modal GPU' },
    { key: 'upload', label: 'Bulut Yukleme', hint: 'Video -> Modal' },
    { key: 'ai', label: 'AI Pipeline', hint: 'Ses metni + baslik + etiket' },
    { key: 'tts', label: 'Seslendirme', hint: 'ElevenLabs' },
    { key: 'gpu', label: 'GPU Temizlik', hint: 'ProPainter' },
    { key: 'seo', label: 'Kapak + SEO', hint: 'Thumbnail + HTML' },
  ]
  const { lines, ...rest } = { ...mockJob!, lines: [] as JobState['lines'] }
  void lines
  return { ...rest, stages, stageIndex: 0, lineCount: 0, title: ch ? `${ch.name} - ${ch.niche}` : rest.title }
}

const mockApi: VideoForgeApi = {
  appInfo: async () => ({ ok: true, data: mockInfo }),
  envCheck: async () => ({ ok: true, data: mockEnv }),
  settingsGet: async () => ({ ok: true, data: mockSettings }),
  settingsSet: async (patch: Partial<AppSettings>) => ({
    ok: true,
    data: { ...mockSettings, ...patch },
  }),
  themeSet: async (mode) => ({ ok: true, data: { ...mockSettings, mode } }),
  runStart: async (req: JobRequest) => {
    const ch = CHANNELS.find((c) => c.id === (req.channelId || '1'))
    mockJob = {
      id: 'mock-1',
      kind: req.kind,
      title: ch ? `${ch.name} - ${ch.niche}` : 'Kesif',
      subtitle: req.link || '',
      status: 'running',
      stages: [],
      stageIndex: 0,
      stepLabel: 'Basliyor',
      startedAt: Date.now(),
      endedAt: null,
      exitCode: null,
      pid: 1234,
      lines: [],
      artifacts: [],
      stats: { gpu: null, cost: null, duration: null, gemini: null, chunks: null },
      error: null,
    }
    emitRun({ type: 'start', state: mockStateSnapshot(req), req })
    let i = 0
    const script: [string, string][] = [
      ['step', 'Video yerel bilgisayarda indiriliyor (cookies.txt ile)...'],
      ['ok', 'Indirme tamamlandi'],
      ['step', 'Transkript cekiliyor...'],
      ['ok', 'Transkript hazir (4820 karakter)'],
      ['info', 'Sunucu aktif edildi. Yerelden gelen video isleniyor...'],
      ['ai', 'Ses metni olusturuluyor...'],
      ['ok', 'Hook OK'],
      ['ok', 'Uzunluk OK'],
      ['tts', 'ElevenLabs ile seslendirme hazirlaniyor...'],
      ['gpu', 'Toplam 640 Frame tespit edildi. (FPS: 30.00)'],
    ]
    const timer = setInterval(() => {
      if (i >= script.length) {
        clearInterval(timer)
        return
      }
      const [level, text] = script[i++]
      emitRun({ type: 'line', line: { i, t: Date.now(), level: level as never, text } })
    }, 700)
    return { ok: true, data: mockJob }
  },
  runCancel: async () => ({ ok: true, data: true }),
  runState: async () => ({ ok: true, data: mockJob }),
  runHistory: async () => ({ ok: true, data: [] as RunHistoryItem[] }),
  libraryList: async () => ({ ok: true, data: mockLibrary }),
  libraryForget: async () => ({ ok: true, data: { ok: true, deleted: 1 } }),
  reportsList: async () => ({ ok: true, data: mockGroups }),
  reportsPreview: async (): Promise<Result<ReportPreview>> => ({
    ok: true,
    data: {
      ok: true,
      title: 'SEO Raporu',
      headings: [],
      sections: [
        { label: 'Title', text: 'Sır Açıklandı! 🤫 #arjantin #ada' },
        { label: 'Tags', text: 'arjantin, ada, gizem' },
        { label: 'Voiceover', text: 'Знаете ли вы, что...' },
      ],
      text: 'Ornek rapor icerigi (tarayici onizleme modu).',
    },
  }),
  weeklyPlan: async () => ({ ok: true, data: { ok: true, plan: [], results: [] } }),
  engineConfig: async () => ({ ok: true, data: mockEngine }),
  engineSetCharLimit: async (v: number) => ({ ok: true, data: { ...mockEngine, charLimit: v } }),
  logsRead: async () => ({
    ok: true,
    data: { ok: true, path: mockInfo.logPath, size: 1024, mtime: Date.now(), lines: ['[12:00:00] Oturum basladi', '[12:00:01] › Islem suruyor'], totalLines: 2 },
  }),
  updateCheck: async () => ({ ok: true, data: mockUpdate }),
  updateDownload: async () => ({ ok: true, data: { ok: true, path: 'C:\\tmp\\VideoForge-1.1.0-portable.exe' } }),
  updateLaunch: async () => ({ ok: true, data: true }),
  updateOpenRelease: async () => ({ ok: true, data: true }),
  botGitStatus: async () => ({ ok: true, data: mockGit }),
  botGitPull: async () => ({ ok: true, data: { ok: true, output: 'Already up to date.', info: mockGit } }),
  onUpdateProgress: (cb: (p: DownloadProgress) => void) => {
    void cb
    return () => {}
  },
  shellOpen: async () => ({ ok: true, data: true }),
  shellReveal: async () => ({ ok: true, data: true }),
  shellOpenExternal: async () => ({ ok: true, data: true }),
  winMinimize: async () => true,
  winMaximize: async () => false,
  winClose: async () => true,
  winState: async () => ({ maximized: false, focused: true }),
  onRunEvent: (cb) => {
    listeners.add(cb)
    return () => listeners.delete(cb)
  },
  onWindowState: () => () => {},
}

export const api: VideoForgeApi = isDesktop
  ? (window as unknown as { vfgui: VideoForgeApi }).vfgui
  : mockApi

/** IPC sonucunu acar; hata varsa firlatir. */
export async function unwrap<T>(promise: Promise<Result<T>>): Promise<T> {
  const res = await promise
  if (!res.ok) throw new Error(res.error)
  return res.data
}

export { withLines }
