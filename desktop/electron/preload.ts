import { contextBridge, ipcRenderer } from 'electron'
import { IPC } from '@shared/constants'
import type {
  AppInfo,
  AppSettings,
  Artifact,
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
  LogLine,
  ReportPreview,
  RunHistoryItem,
  UpdateInfo,
} from '@shared/types'

export interface ReportGroupPayload {
  key: string
  dir: string
  title: string
  items: Artifact[]
  totalBytes: number
  mtime: number
}

export type Result<T> = { ok: true; data: T } | { ok: false; error: string }

export type RunEvent =
  | { type: 'start'; state: Omit<JobState, 'lines'> & { lineCount: number }; req: JobRequest }
  | { type: 'line'; line: LogLine }
  | { type: 'state'; state: Omit<JobState, 'lines'> & { lineCount: number } }
  | { type: 'end'; state: Omit<JobState, 'lines'> & { lineCount: number } }

const api = {
  appInfo: (): Promise<Result<AppInfo>> => ipcRenderer.invoke(IPC.appInfo),
  envCheck: (): Promise<Result<EnvCheck[]>> => ipcRenderer.invoke(IPC.envCheck),
  settingsGet: (): Promise<Result<AppSettings>> => ipcRenderer.invoke(IPC.settingsGet),
  settingsSet: (patch: Partial<AppSettings>): Promise<Result<AppSettings>> => ipcRenderer.invoke(IPC.settingsSet, patch),
  themeSet: (mode: AppSettings['mode']): Promise<Result<AppSettings>> => ipcRenderer.invoke(IPC.themeSet, mode),

  runStart: (req: JobRequest): Promise<Result<JobState | null>> => ipcRenderer.invoke(IPC.runStart, req),
  runCancel: (): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.runCancel),
  runState: (): Promise<Result<JobState | null>> => ipcRenderer.invoke(IPC.runState),
  runHistory: (): Promise<Result<RunHistoryItem[]>> => ipcRenderer.invoke(IPC.runHistory),

  libraryList: (): Promise<Result<LibraryData>> => ipcRenderer.invoke(IPC.libraryList),
  libraryForget: (link: string): Promise<Result<{ ok: boolean; deleted?: number; error?: string }>> =>
    ipcRenderer.invoke(IPC.libraryForget, link),

  reportsList: (): Promise<Result<ReportGroupPayload[]>> => ipcRenderer.invoke(IPC.reportsList),
  reportsPreview: (filePath: string): Promise<Result<ReportPreview>> => ipcRenderer.invoke(IPC.reportsPreview, filePath),

  weeklyPlan: (): Promise<Result<unknown>> => ipcRenderer.invoke(IPC.weeklyPlan),
  engineConfig: (): Promise<Result<EngineConfig>> => ipcRenderer.invoke(IPC.engineConfig),
  engineSetCharLimit: (value: number): Promise<Result<EngineConfig>> => ipcRenderer.invoke(IPC.engineSetCharLimit, value),

  logsRead: (tail: number, query: string): Promise<Result<{ ok: boolean; path: string; size: number; mtime: number; lines: string[]; totalLines: number; error?: string }>> =>
    ipcRenderer.invoke(IPC.logsRead, tail, query),

  shellOpen: (target: string): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.shellOpen, target),
  shellReveal: (target: string): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.shellReveal, target),
  shellOpenExternal: (url: string): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.shellOpenExternal, url),

  updateCheck: (): Promise<Result<UpdateInfo>> => ipcRenderer.invoke(IPC.updateCheck),
  updateDownload: (assetName: string): Promise<Result<{ ok: boolean; path?: string; error?: string }>> =>
    ipcRenderer.invoke(IPC.updateDownload, assetName),
  updateLaunch: (filePath: string): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.updateLaunch, filePath),
  updateOpenRelease: (repo: string): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.updateOpenRelease, repo),
  autoUpdateState: (): Promise<Result<AutoUpdateState>> => ipcRenderer.invoke(IPC.updateAutoState),
  autoUpdateCheck: (): Promise<Result<AutoUpdateState>> => ipcRenderer.invoke(IPC.updateAutoCheck),
  autoUpdateInstall: (): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.updateAutoInstall),
  onAutoUpdateChanged: (cb: (state: AutoUpdateState) => void): (() => void) => {
    const handler = (_e: unknown, payload: AutoUpdateState): void => cb(payload)
    ipcRenderer.on(IPC.updateAutoChanged, handler)
    return () => ipcRenderer.removeListener(IPC.updateAutoChanged, handler)
  },
  botGitStatus: (fetchRemote = false): Promise<Result<BotGitInfo>> =>
    ipcRenderer.invoke(IPC.botGitStatus, fetchRemote),
  botGitPull: (): Promise<Result<{ ok: boolean; output: string; error?: string; info: BotGitInfo }>> =>
    ipcRenderer.invoke(IPC.botGitPull),
  onUpdateProgress: (cb: (progress: DownloadProgress) => void): (() => void) => {
    const handler = (_e: unknown, payload: DownloadProgress): void => cb(payload)
    ipcRenderer.on(IPC.updateProgress, handler)
    return () => ipcRenderer.removeListener(IPC.updateProgress, handler)
  },

  queueList: (): Promise<Result<KuyrukOgesi[]>> => ipcRenderer.invoke(IPC.queueList),
  queueAdd: (items: unknown[]): Promise<Result<KuyrukOgesi[]>> => ipcRenderer.invoke(IPC.queueAdd, items),
  queueRemove: (id: string): Promise<Result<KuyrukOgesi[]>> => ipcRenderer.invoke(IPC.queueRemove, id),
  queueClear: (): Promise<Result<KuyrukOgesi[]>> => ipcRenderer.invoke(IPC.queueClear),
  queueStartNext: (): Promise<Result<boolean>> => ipcRenderer.invoke(IPC.queueStart),
  onQueueChanged: (cb: (items: KuyrukOgesi[]) => void): (() => void) => {
    const handler = (_e: unknown, payload: KuyrukOgesi[]): void => cb(payload)
    ipcRenderer.on('queue:changed', handler)
    return () => ipcRenderer.removeListener('queue:changed', handler)
  },
  spendSummary: (): Promise<Result<HarcamaOzeti>> => ipcRenderer.invoke(IPC.spendSummary),
  quotaGet: (): Promise<Result<KotaBilgisi>> => ipcRenderer.invoke(IPC.quotaGet),
  creditsGet: (): Promise<Result<KrediServisi[]>> => ipcRenderer.invoke(IPC.creditsGet),
  secretsGet: (): Promise<Result<GizliAnahtarlar>> => ipcRenderer.invoke(IPC.secretsGet),
  secretsSet: (patch: Partial<GizliAnahtarlar>): Promise<Result<GizliAnahtarlar>> => ipcRenderer.invoke(IPC.secretsSet, patch),

  winMinimize: (): Promise<boolean> => ipcRenderer.invoke(IPC.winMinimize),
  winMaximize: (): Promise<boolean> => ipcRenderer.invoke(IPC.winMaximize),
  winClose: (): Promise<boolean> => ipcRenderer.invoke(IPC.winClose),
  winState: (): Promise<{ maximized: boolean; focused: boolean }> => ipcRenderer.invoke(IPC.winState),

  onRunEvent: (cb: (event: RunEvent) => void): (() => void) => {
    const handler = (_e: unknown, payload: RunEvent): void => cb(payload)
    ipcRenderer.on(IPC.runEvent, handler)
    return () => ipcRenderer.removeListener(IPC.runEvent, handler)
  },
  onWindowState: (cb: (state: { maximized: boolean; focused: boolean }) => void): (() => void) => {
    const handler = (_e: unknown, payload: { maximized: boolean; focused: boolean }): void => cb(payload)
    ipcRenderer.on(IPC.winStateChanged, handler)
    return () => ipcRenderer.removeListener(IPC.winStateChanged, handler)
  },
}

contextBridge.exposeInMainWorld('vfgui', api)

export type VideoForgeApi = typeof api
