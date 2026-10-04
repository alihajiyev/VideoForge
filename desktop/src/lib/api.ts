import type { VideoForgeApi, Result, RunEvent, ReportGroupPayload } from '@electron/preload'
import { CHANNELS } from '@shared/channels'
import type {
  AppInfo,
  AppSettings,
  AutoUpdateState,
  BotGitInfo,
  DownloadProgress,
  EngineConfig,
  EnvCheck,
  GizliAnahtarlar,
  HarcamaOzeti,
  JobRequest,
  JobState,
  KotaBilgisi,
  KrediServisi,
  KuyrukOgesi,
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
  gunSayisi: 7,
  notifyOnComplete: true,
  queueAutoStart: true,
  onboardingDone: false,
  scheduleEnabled: false,
  scheduleTime: '09:00',
  scheduleKind: 'discover',
  scheduleChannel: '1',
  shortsStudioPath: '',
}

const mockUpdate: UpdateInfo = {
  ok: true,
  current: '1.0.0',
  latest: '1.1.0',
  available: true,
  notes: '- Yeni: link kuyruğu\n- Düzeltme: TTS uzunluk hesabı',
  publishedAt: new Date().toISOString(),
  htmlUrl: 'https://github.com/alihajiyev/VideoForge/releases/tag/v1.1.0',
  assets: [{ name: 'VideoForge-1.1.0-portable.exe', size: 111_300_000, url: 'https://example.com/a.exe', isApiUrl: false }],
  repo: 'alihajiyev/VideoForge',
  checkedAt: Date.now(),
}

const mockAutoUpdate: AutoUpdateState = {
  durum: 'hazir',
  current: '1.1.1',
  version: '1.2.1',
  pct: 100,
  received: 113_000_000,
  total: 113_000_000,
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
  { id: 'botfiles', label: 'VideoForge dosyaları', ok: true, detail: '7 dosya doğrulandı' },
  { id: 'modal', label: 'modal paketi', ok: true, detail: '1.5.5' },
  { id: 'genai', label: 'google-genai', ok: true, detail: '2.24.0' },
  { id: 'ffmpeg', label: 'ffmpeg', ok: true, detail: 'ffmpeg version 7.1' },
  { id: 'cookies', label: 'cookies.txt', ok: false, detail: '12 gün önce güncellendi', fix: 'cookies.txt yenileyin' },
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

const mockSecrets: GizliAnahtarlar = {
  geminiApiKeys: 'AQ.Ab8RN6...anahtar1,AQ.Ab8RN6...anahtar2',
  elevenlabsApiKey: 'sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx',
  transcriptApiKey: '',
  zapcapApiKey: '6ecaf707e2edc30d9cbe723de13cae446301a15799aad831d52d0ad379472a9e',
  zapcapTemplateId: '6255949c-4a52-4255-8a67-39ebccfaa3ef',
  altyaziMotoru: 'auto',
  voiceCh1: 'M1CSR3PJBsfWU6ZquG3C',
  voiceCh2: 'M1CSR3PJBsfWU6ZquG3C',
  voiceCh3: 'LHi3adMlU7AICv8Yxpmm',
  envPath: 'C:\\Users\\Vafa\\Desktop\\VideoForge\\.env',
  shortsStudioFound: true,
}

const mockLibrary: LibraryData = {
  ok: true,
  videos: [
    { id: 42, link: 'dQw4w9WgXcQ', created_at: '2026-09-27 08:12:04' },
    { id: 41, link: '7647993089797164320', created_at: '2026-09-26 19:44:31' },
  ],
  oneriler: [
    { video_id: 'aBc123XyZ-_', skor: 8.4, tip: 'KAZANAN', kanal: '1', tarih: '2026-09-28 06:40:00' },
    { video_id: 'zZ9Y8x7W6v5', skor: 3.1, tip: 'ÇÖP', kanal: '3', tarih: '2026-09-28 06:41:12' },
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
    { key: 'download', label: 'İndirme', hint: 'yt-dlp + cookies.txt' },
    { key: 'transcript', label: 'Transkript', hint: 'Altyazi / Modal GPU' },
    { key: 'upload', label: 'Bulut Yükleme', hint: 'Video -> Modal' },
    { key: 'ai', label: 'AI Pipeline', hint: 'Ses metni + başlık + etiket' },
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
      title: ch ? `${ch.name} - ${ch.niche}` : 'Keşif',
      subtitle: req.link || '',
      status: 'running',
      stages: [],
      stageIndex: 0,
      stepLabel: 'Başlıyor',
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
      ['ok', 'İndirme tamamlandı'],
      ['step', 'Transkript çekiliyor...'],
      ['ok', 'Transkript hazır (4820 karakter)'],
      ['info', 'Sunucu aktif edildi. Yerelden gelen video işleniyor...'],
      ['ai', 'Ses metni oluşturuluyor...'],
      ['ok', 'Hook OK'],
      ['ok', 'Uzunluk OK'],
      ['tts', 'ElevenLabs ile seslendirme hazırlanıyor...'],
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
  queueList: async () => ({ ok: true, data: [] as KuyrukOgesi[] }),
  queueAdd: async (items) => ({ ok: true, data: items as KuyrukOgesi[] }),
  queueRemove: async () => ({ ok: true, data: [] as KuyrukOgesi[] }),
  queueClear: async () => ({ ok: true, data: [] as KuyrukOgesi[] }),
  queueStartNext: async () => ({ ok: true, data: false }),
  onQueueChanged: () => () => {},
  secretsGet: async (): Promise<Result<GizliAnahtarlar>> => ({ ok: true, data: mockSecrets }),
  secretsSet: async (patch: Partial<GizliAnahtarlar>): Promise<Result<GizliAnahtarlar>> => ({
    ok: true,
    data: { ...mockSecrets, ...patch },
  }),
  creditsGet: async (): Promise<Result<KrediServisi[]>> => ({
    ok: true,
    data: [
      { id: 'elevenlabs', ad: 'ElevenLabs (seslendirme)', durum: 'ok', kalan: 59957, toplam: 121012, birim: 'karakter', detay: 'plan: creator' },
      { id: 'zapcap', ad: 'ZapCap (altyazı/efekt)', durum: 'ok', kalan: 0.0056, toplam: null, birim: 'USD' },
      {
        id: 'gemini',
        ad: 'Google Gemini (AI)',
        durum: 'bilgi',
        kalan: null,
        toplam: null,
        birim: 'istek',
        detay: '7 anahtar · günlük model kotaları için “Gemini kotası” kartına bakın',
      },
    ],
  }),
  spendSummary: async (): Promise<Result<HarcamaOzeti>> => ({
    ok: true,
    data: {
      ok: true,
      ayUsd: 1.284,
      bugunUsd: 0.096,
      isSayisi: 6,
      gunler: [
        { gun: '2026-09-24', usd: 0.18 },
        { gun: '2026-09-25', usd: 0.31 },
        { gun: '2026-09-26', usd: 0.12 },
        { gun: '2026-09-27', usd: 0.4 },
        { gun: '2026-09-28', usd: 0.17 },
        { gun: '2026-09-29', usd: 0.096 },
      ],
      son: [
        { t: Date.now() - 3600_000, baslik: 'Kino Sekrety - Film sırları', kind: 'channel', usd: 0.096, saniye: 412 },
        { t: Date.now() - 7_200_000, baslik: '7 Günlük Zincir - Kino Sekrety', kind: 'weekly', usd: 0.17, saniye: 733 },
      ],
      ortalama: { channel: 0.09, weekly: 0.17, discover: 0.02 },
    },
  }),
  quotaGet: async (): Promise<Result<KotaBilgisi>> => ({
    ok: true,
    data: {
      ok: true,
      tarih: '2026-09-30',
      aiCagrisi: 34,
      sifirlanmaMs: Date.now() + 3 * 3600_000,
      limitler: [500, 500, 500, 20, 20],
      modeller: mockEngine.models,
    },
  }),
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
      text: 'Örnek rapor içeriği (tarayıcı önizleme modu).',
    },
  }),
  weeklyPlan: async () => ({ ok: true, data: { ok: true, plan: [], results: [] } }),
  engineConfig: async () => ({ ok: true, data: mockEngine }),
  engineSetCharLimit: async (v: number) => ({ ok: true, data: { ...mockEngine, charLimit: v } }),
  logsRead: async () => ({
    ok: true,
    data: { ok: true, path: mockInfo.logPath, size: 1024, mtime: Date.now(), lines: ['[12:00:00] Oturum başladı', '[12:00:01] › İşlem sürüyor'], totalLines: 2 },
  }),
  updateCheck: async () => ({ ok: true, data: mockUpdate }),
  updateDownload: async () => ({ ok: true, data: { ok: true, path: 'C:\\tmp\\VideoForge-1.1.1-portable.exe' } }),
  updateLaunch: async () => ({ ok: true, data: true }),
  updateOpenRelease: async () => ({ ok: true, data: true }),
  autoUpdateState: async () => ({ ok: true, data: mockAutoUpdate }),
  autoUpdateCheck: async () => ({ ok: true, data: mockAutoUpdate }),
  autoUpdateInstall: async () => ({ ok: true, data: true }),
  onAutoUpdateChanged: () => () => {},
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
