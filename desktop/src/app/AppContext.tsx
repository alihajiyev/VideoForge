import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, unwrap, type RunEvent } from '@/lib/api'
import type {
  AppInfo,
  AppSettings,
  BotGitInfo,
  DownloadProgress,
  EngineConfig,
  EnvCheck,
  JobRequest,
  JobState,
  LogLine,
  RunHistoryItem,
  UpdateInfo,
} from '@shared/types'

export interface Toast {
  id: string
  tone: 'info' | 'success' | 'warn' | 'error'
  title: string
  message?: string
}

type StateSnapshot = Omit<JobState, 'lines'> & { lineCount: number }

interface AppCtx {
  ready: boolean
  info: AppInfo | null
  settings: AppSettings | null
  env: EnvCheck[]
  envLoading: boolean
  envError: string | null
  engine: EngineConfig | null
  job: JobState | null
  history: RunHistoryItem[]
  toasts: Toast[]
  update: UpdateInfo | null
  updateChecking: boolean
  download: DownloadProgress | null
  botGit: BotGitInfo | null
  botGitBusy: boolean
  checkUpdate: () => Promise<UpdateInfo | null>
  downloadUpdate: (assetName: string) => Promise<string | null>
  launchUpdate: (filePath: string) => Promise<void>
  refreshBotGit: (fetchRemote?: boolean) => Promise<void>
  pullBotCode: () => Promise<void>
  refreshEnv: () => Promise<void>
  refreshEngine: () => Promise<void>
  saveSettings: (patch: Partial<AppSettings>) => Promise<void>
  setMode: (mode: AppSettings['mode']) => Promise<void>
  startJob: (req: JobRequest) => Promise<boolean>
  cancelJob: () => Promise<void>
  refreshHistory: () => Promise<void>
  pushToast: (toast: Omit<Toast, 'id'>) => void
  dismissToast: (id: string) => void
}

const Ctx = createContext<AppCtx | null>(null)

export function useApp(): AppCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useApp AppProvider disinda kullanildi')
  return ctx
}

export function AppProvider({ children }: { children: ReactNode }): ReactNode {
  const [ready, setReady] = useState(false)
  const [info, setInfo] = useState<AppInfo | null>(null)
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [env, setEnv] = useState<EnvCheck[]>([])
  const [envLoading, setEnvLoading] = useState(false)
  const [envError, setEnvError] = useState<string | null>(null)
  const [engine, setEngine] = useState<EngineConfig | null>(null)
  const [job, setJob] = useState<JobState | null>(null)
  const [history, setHistory] = useState<RunHistoryItem[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])
  const [update, setUpdate] = useState<UpdateInfo | null>(null)
  const [updateChecking, setUpdateChecking] = useState(false)
  const [download, setDownload] = useState<DownloadProgress | null>(null)
  const [botGit, setBotGit] = useState<BotGitInfo | null>(null)
  const [botGitBusy, setBotGitBusy] = useState(false)
  const linesRef = useRef<LogLine[]>([])

  const pushToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    setToasts((prev) => [...prev.slice(-3), { ...toast, id }])
    window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000)
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const refreshEnv = useCallback(async () => {
    setEnvLoading(true)
    try {
      setEnv(await unwrap(api.envCheck()))
      setEnvError(null)
    } catch (err) {
      setEnvError(err instanceof Error ? err.message : String(err))
    } finally {
      setEnvLoading(false)
    }
  }, [])

  const refreshEngine = useCallback(async () => {
    try {
      setEngine(await unwrap(api.engineConfig()))
    } catch (err) {
      pushToast({ tone: 'error', title: 'Motor ayarlari okunamadi', message: String(err) })
    }
  }, [pushToast])

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await unwrap(api.runHistory()))
    } catch {
      /* yoksay */
    }
  }, [])

  const checkUpdate = useCallback(async (): Promise<UpdateInfo | null> => {
    setUpdateChecking(true)
    try {
      const info = await unwrap(api.updateCheck())
      setUpdate(info)
      return info
    } catch (err) {
      const failed: UpdateInfo = {
        ok: false,
        error: err instanceof Error ? err.message : String(err),
        current: '—',
        latest: null,
        available: false,
        notes: '',
        publishedAt: null,
        htmlUrl: null,
        assets: [],
        repo: '',
        checkedAt: Date.now(),
      }
      setUpdate(failed)
      return failed
    } finally {
      setUpdateChecking(false)
    }
  }, [])

  const startDownload = useCallback(
    async (assetName: string): Promise<string | null> => {
      try {
        const res = await unwrap(api.updateDownload(assetName))
        if (!res.ok || !res.path) {
          pushToast({ tone: 'error', title: 'Indirme basarisiz', message: res.error })
          return null
        }
        pushToast({ tone: 'success', title: 'Guncelleme indirildi', message: 'Baslatmak icin "Yeni surumu baslat" dugmesine basin.' })
        return res.path
      } catch (err) {
        pushToast({ tone: 'error', title: 'Indirme basarisiz', message: String(err) })
        return null
      }
    },
    [pushToast],
  )

  const launchUpdate = useCallback(
    async (filePath: string): Promise<void> => {
      try {
        await unwrap(api.updateLaunch(filePath))
      } catch (err) {
        pushToast({ tone: 'error', title: 'Yeni surum baslatilamadi', message: String(err) })
      }
    },
    [pushToast],
  )

  const refreshBotGit = useCallback(async (fetchRemote = false): Promise<void> => {
    try {
      setBotGit(await unwrap(api.botGitStatus(fetchRemote)))
    } catch (err) {
      setBotGit(null)
      pushToast({ tone: 'warn', title: 'Git durumu okunamadi', message: String(err) })
    }
  }, [pushToast])

  const pullBotCode = useCallback(async (): Promise<void> => {
    setBotGitBusy(true)
    try {
      const res = await unwrap(api.botGitPull())
      setBotGit(res.info)
      if (res.ok) {
        pushToast({ tone: 'success', title: 'Bot kodu guncellendi', message: res.info.commit ? `Son commit: ${res.info.commit}` : undefined })
        void refreshEnv()
        void refreshEngine()
      } else {
        pushToast({ tone: 'warn', title: 'Bot kodu guncellenemedi', message: res.error })
      }
    } catch (err) {
      pushToast({ tone: 'error', title: 'Git hatasi', message: String(err) })
    } finally {
      setBotGitBusy(false)
    }
  }, [pushToast, refreshEnv, refreshEngine])

  // Ilk yukleme
  useEffect(() => {
    let alive = true
    void (async () => {
      try {
        const [i, s, j, h] = await Promise.all([
          unwrap(api.appInfo()),
          unwrap(api.settingsGet()),
          unwrap(api.runState()),
          unwrap(api.runHistory()),
        ])
        if (!alive) return
        setInfo(i)
        setSettings(s)
        if (j) {
          linesRef.current = j.lines ?? []
          setJob(j)
        }
        setHistory(h)
      } catch (err) {
        pushToast({ tone: 'error', title: 'Baslatma hatasi', message: String(err) })
      } finally {
        if (alive) setReady(true)
      }
    })()
    void refreshEnv()
    void refreshEngine()
    void refreshBotGit()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Otomatik guncelleme kontrolu (ayarli ve uygulama hazir oldugunda)
  useEffect(() => {
    if (!ready) return
    if (!settings?.autoCheckUpdates) return
    void checkUpdate()
  }, [ready, settings?.autoCheckUpdates, checkUpdate])

  // Indirme ilerlemesi
  useEffect(() => {
    const off = api.onUpdateProgress((progress) => setDownload(progress))
    return off
  }, [])

  // Tema uygula
  useEffect(() => {
    const mode = settings?.mode ?? 'dark'
    const prefersLight = window.matchMedia?.('(prefers-color-scheme: light)').matches
    const resolved = mode === 'system' ? (prefersLight ? 'light' : 'dark') : mode
    document.documentElement.dataset.theme = resolved
  }, [settings?.mode])

  // Canli is olaylari
  useEffect(() => {
    const off = api.onRunEvent((event: RunEvent) => {
      if (event.type === 'line') {
        linesRef.current = [...linesRef.current, event.line].slice(-4000)
        setJob((prev) => (prev ? { ...prev, lines: linesRef.current } : prev))
        return
      }
      if (event.type === 'start') {
        linesRef.current = []
        const { lineCount, ...rest } = event.state
        void lineCount
        setJob({ ...rest, lines: [] })
        return
      }
      setJob((prev) => {
        const { lineCount, ...rest } = event.state
        void lineCount
        return { ...rest, lines: prev?.lines ?? linesRef.current }
      })
      if (event.type === 'end') {
        const status = event.state.status
        const found = event.state.artifacts.length
        pushToast({
          tone: status === 'done' ? 'success' : status === 'cancelled' ? 'warn' : 'error',
          title:
            status === 'done'
              ? 'Islem tamamlandi'
              : status === 'cancelled'
                ? 'Islem durduruldu'
                : 'Islem hata ile bitti',
          message: status === 'done' ? `${found} cikti dosyasi hazir` : undefined,
        })
        void refreshHistory()
      }
    })
    return off
  }, [pushToast, refreshHistory])

  const saveSettings = useCallback(
    async (patch: Partial<AppSettings>) => {
      try {
        const next = await unwrap(api.settingsSet(patch))
        setSettings(next)
        if (patch.videoForgePath !== undefined || patch.pythonPath !== undefined) {
          const fresh = await unwrap(api.appInfo())
          setInfo(fresh)
          void refreshEnv()
          void refreshEngine()
        }
      } catch (err) {
        pushToast({ tone: 'error', title: 'Ayar kaydedilemedi', message: String(err) })
      }
    },
    [pushToast, refreshEnv, refreshEngine],
  )

  const setMode = useCallback(
    async (mode: AppSettings['mode']) => {
      setSettings((prev) => (prev ? { ...prev, mode } : prev))
      try {
        await unwrap(api.themeSet(mode))
      } catch {
        /* yoksay */
      }
    },
    [],
  )

  const startJob = useCallback(
    async (req: JobRequest) => {
      try {
        await unwrap(api.runStart(req))
        return true
      } catch (err) {
        pushToast({ tone: 'error', title: 'Islem baslatilamadi', message: err instanceof Error ? err.message : String(err) })
        return false
      }
    },
    [pushToast],
  )

  const cancelJob = useCallback(async () => {
    try {
      await unwrap(api.runCancel())
    } catch (err) {
      pushToast({ tone: 'error', title: 'Durdurulamadi', message: String(err) })
    }
  }, [pushToast])

  const value = useMemo<AppCtx>(
    () => ({
      ready,
      info,
      settings,
      env,
      envLoading,
      envError,
      engine,
      job,
      history,
      toasts,
      update,
      updateChecking,
      download,
      botGit,
      botGitBusy,
      checkUpdate,
      downloadUpdate: startDownload,
      launchUpdate,
      refreshBotGit,
      pullBotCode,
      refreshEnv,
      refreshEngine,
      saveSettings,
      setMode,
      startJob,
      cancelJob,
      refreshHistory,
      pushToast,
      dismissToast,
    }),
    [
      ready,
      info,
      settings,
      env,
      envLoading,
      envError,
      engine,
      job,
      history,
      toasts,
      update,
      updateChecking,
      download,
      botGit,
      botGitBusy,
      checkUpdate,
      startDownload,
      launchUpdate,
      refreshBotGit,
      pullBotCode,
      refreshEnv,
      refreshEngine,
      saveSettings,
      setMode,
      startJob,
      cancelJob,
      refreshHistory,
      pushToast,
      dismissToast,
    ],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export type { StateSnapshot }
