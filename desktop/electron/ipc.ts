import { app, ipcMain, nativeTheme, shell } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { IPC } from '@shared/constants'
import type { AppInfo, AppSettings, JobRequest } from '@shared/types'
import { botPath, cookiesPath, dbPath, desktopDir, logPath } from './core/paths'
import { getSettings, setSettings } from './core/settings'
import { log } from './core/logger'
import { cancelJob, getHistory, getState, startJob } from './python/runner'
import { resolvePython } from './python/locate'
import { engineConfig, setCharLimit } from './data/engine'
import { envCheck } from './data/env'
import { forgetLink, readLibrary } from './data/library'
import { readBotLog, weeklyData } from './data/logs'
import { botGitStatus, checkForUpdate, downloadUpdate, launchDownloaded, openReleasePage, pullBotCode } from './update/updater'
import { groupArtifacts, listArtifacts, previewHtml } from './data/reports'
import { harcamaOzeti, kotaBilgisi } from './data/spend'
import {
  kuyrukListesi,
  kuyrugaEkle,
  kuyruktanCikar,
  kuyruguTemizle,
  siradakiniBaslat,
  type KuyrukGirdi,
} from './core/queue'

function ok<T>(data: T): { ok: true; data: T } {
  return { ok: true, data }
}

function fail(error: string): { ok: false; error: string } {
  return { ok: false, error }
}

function appInfo(): AppInfo {
  const root = botPath(getSettings().videoForgePath)
  return {
    version: app.getVersion(),
    electron: process.versions.electron,
    node: process.versions.node,
    platform: process.platform,
    userData: app.getPath('userData'),
    desktop: desktopDir,
    videoForgePath: root,
    projectRoot: path.resolve(__dirname, '..'),
    cookiesPath: cookiesPath(root),
    dbPath: dbPath(root),
    logPath: logPath(root),
  }
}

export function registerIpc(): void {
  ipcMain.handle(IPC.appInfo, () => {
    try {
      return ok(appInfo())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.envCheck, async () => {
    try {
      return ok(await envCheck())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.settingsGet, () => {
    try {
      return ok(getSettings())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.settingsSet, (_e, patch: Partial<AppSettings>) => {
    try {
      const next = setSettings(patch ?? {})
      if (patch?.mode) applyTheme(next.mode)
      if (patch?.pythonPath !== undefined) void resolvePython(true)
      return ok(next)
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.themeSet, (_e, mode: AppSettings['mode']) => {
    try {
      applyTheme(mode)
      return ok(setSettings({ mode }))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.runStart, async (_e, req: JobRequest) => {
    try {
      const res = await startJob(req)
      return res.ok ? ok(getState()) : fail(res.error || 'Islem baslatilamadi')
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.runCancel, async () => {
    try {
      // cancelJob surec agacini oldurup kapanmayi bekler -> await sart.
      return ok(await cancelJob())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.runState, () => {
    try {
      return ok(getState())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.runHistory, () => {
    try {
      return ok(getHistory())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.libraryList, async () => {
    try {
      return ok(await readLibrary())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.libraryForget, async (_e, link: string) => {
    try {
      return ok(await forgetLink(link))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.reportsList, () => {
    try {
      const groups = groupArtifacts(listArtifacts())
      return ok(groups)
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.reportsPreview, (_e, filePath: string) => {
    try {
      if (!isSafePath(filePath)) return fail('Bu dosyaya erisim izni yok.')
      return ok(previewHtml(filePath))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.weeklyPlan, () => {
    try {
      return ok(weeklyData())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.engineConfig, async () => {
    try {
      return ok(await engineConfig())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.engineSetCharLimit, async (_e, value: number) => {
    try {
      const res = await setCharLimit(Number(value) || 500)
      return res.ok ? ok(await engineConfig()) : fail(res.error || 'Kaydedilemedi')
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.logsRead, (_e, tail: number, query: string) => {
    try {
      return ok(readBotLog(tail, query))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.updateCheck, async () => {
    try {
      return ok(await checkForUpdate())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.updateDownload, async (_e, assetName: string) => {
    try {
      return ok(await downloadUpdate(String(assetName || '')))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.updateLaunch, (_e, filePath: string) => {
    try {
      const res = launchDownloaded(String(filePath || ''))
      return res.ok ? ok(true) : fail(res.error || 'Baslatilamadi')
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.updateOpenRelease, async (_e, repo: string) => {
    try {
      const res = await openReleasePage({ repo: String(repo || '') })
      return res.ok ? ok(true) : fail(res.error || 'Acilamadi')
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.botGitStatus, async (_e, fetchRemote?: boolean) => {
    try {
      return ok(await botGitStatus({ fetch: Boolean(fetchRemote) }))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.botGitPull, async () => {
    try {
      return ok(await pullBotCode())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.shellOpen, async (_e, target: string) => {
    try {
      if (!isSafePath(target)) return fail('Bu yola erisim izni yok.')
      if (!fs.existsSync(target)) return fail('Yol bulunamadi.')
      const res = await shell.openPath(target)
      return res ? fail(res) : ok(true)
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.shellReveal, (_e, target: string) => {
    try {
      if (!isSafePath(target)) return fail('Bu yola erisim izni yok.')
      shell.showItemInFolder(target)
      return ok(true)
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.queueList, () => {
    try {
      return ok(kuyrukListesi())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.queueAdd, (_e, items: KuyrukGirdi[]) => {
    try {
      return ok(kuyrugaEkle(Array.isArray(items) ? items : []))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.queueRemove, (_e, id: string) => {
    try {
      return ok(kuyruktanCikar(String(id || '')))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.queueClear, () => {
    try {
      return ok(kuyruguTemizle())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.queueStart, async () => {
    try {
      return ok(await siradakiniBaslat())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.spendSummary, () => {
    try {
      return ok(harcamaOzeti())
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.quotaGet, async () => {
    try {
      const cfg = await engineConfig()
      const limitler = cfg.models.map((_, i) => (i < 3 ? 500 : 20))
      return ok(kotaBilgisi(limitler, cfg.models))
    } catch (err) {
      return fail(String(err))
    }
  })

  ipcMain.handle(IPC.shellOpenExternal, async (_e, url: string) => {
    try {
      if (!/^https?:\/\//i.test(url)) return fail('Sadece http/https adresleri acilabilir.')
      await shell.openExternal(url)
      return ok(true)
    } catch (err) {
      return fail(String(err))
    }
  })
}

/** Sadece masaustu ve VideoForge klasoru altindaki yollara erisim izinli. */
function isSafePath(target: string): boolean {
  try {
    const resolved = path.resolve(target)
    const root = botPath(getSettings().videoForgePath)
    const allowed = [desktopDir, root].map((p) => path.resolve(p).toLowerCase())
    const lower = resolved.toLowerCase()
    return allowed.some((a) => lower === a || lower.startsWith(a + path.sep))
  } catch {
    return false
  }
}

export function applyTheme(mode: AppSettings['mode']): void {
  try {
    nativeTheme.themeSource = mode === 'system' ? 'system' : mode
  } catch (err) {
    log.warn('tema uygulanamadi:', err)
  }
}
