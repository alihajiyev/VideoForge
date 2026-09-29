import { app, BrowserWindow, shell } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { applyTheme, registerIpc } from './ipc'
import { getSettings } from './core/settings'
import { log } from './core/logger'
import { emitWindowState, registerWindowIpc, setMainWindow } from './core/window'
import { cancelJob } from './python/runner'

const DEV_URL = process.env.VITE_DEV_SERVER_URL

let win: BrowserWindow | null = null

/**
 * Pencere/gorev cubugu ikonu (desktop/build/icon.ico).
 * Paketli derlemede asar icinden, dev'de depo kokunden okunur.
 */
function windowIconPath(): string | undefined {
  const adaylar = [
    path.join(app.getAppPath(), 'build', 'icon.ico'),
    path.join(__dirname, '..', 'build', 'icon.ico'),
  ]
  return adaylar.find((p) => {
    try {
      return fs.existsSync(p)
    } catch {
      return false
    }
  })
}

function createWindow(): void {
  win = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 1080,
    minHeight: 680,
    show: false,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#0b0f14',
    icon: windowIconPath(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
    },
  })

  setMainWindow(win)

  win.once('ready-to-show', () => win?.show())
  win.on('maximize', emitWindowState)
  win.on('unmaximize', emitWindowState)
  win.on('focus', emitWindowState)
  win.on('blur', emitWindowState)
  win.on('closed', () => {
    setMainWindow(null)
    win = null
  })

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })

  win.webContents.on('render-process-gone', (_e, details) => {
    log.error('renderer coktu:', details.reason)
  })

  // Teshis kancasi (VF_DIAG=1): paketli derlemede arayuzun gercekten render
  // oldugunu ve IPC cagrilarinin yanitlandigini logdan dogrulamak icin.
  // Normal kullanimda hicbir etkisi yoktur.
  if (process.env.VF_DIAG) {
    win.webContents.on('console-message', (event) => {
      log.info(`RENDERER[${event.level}] ${event.message}`)
    })
    win.webContents.on('did-finish-load', () => {
      const probe = async (tag: string): Promise<void> => {
        try {
          const info = (await win?.webContents.executeJavaScript(
            `(() => ({ dal: document.querySelectorAll('*').length, text: (document.body.textContent || '').length, nav: document.querySelectorAll('nav button').length, theme: document.documentElement.dataset.theme, hasBridge: !!window.vfgui }))()`,
          )) as { dal: number; text: number; nav: number; theme?: string; hasBridge: boolean }
          log.info(`DIAG[${tag}] ${info.dal} dugum, ${info.text} karakter, ${info.nav} menu, tema=${info.theme}, kopru=${info.hasBridge}`)
        } catch (err) {
          log.error(`DIAG[${tag}] okunamadi:`, err)
        }
      }
      void (async () => {
        await probe('yukleme')
        await new Promise((r) => setTimeout(r, 6000))
        await probe('+6sn')
        try {
          const res = await win?.webContents.executeJavaScript(`(async () => {
            const out = {};
            for (const k of ['appInfo','settingsGet','runState','runHistory','envCheck','engineConfig']) {
              const t0 = performance.now();
              try {
                const r = await window.vfgui[k]();
                out[k] = (r && r.ok ? 'ok' : 'hata:' + (r && r.error)) + ' ' + Math.round(performance.now() - t0) + 'ms';
              } catch (e) { out[k] = 'REJECT ' + String(e) + ' ' + Math.round(performance.now() - t0) + 'ms'; }
            }
            return out;
          })()`)
          log.info(`DIAG[ipc] ${JSON.stringify(res)}`)
        } catch (err) {
          log.error('DIAG[ipc] calistirilamadi:', err)
        }
        await probe('son')
      })()
    })
  }

  if (DEV_URL) {
    void win.loadURL(DEV_URL)
  } else {
    void win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  applyTheme(getSettings().mode)
  registerIpc()
  registerWindowIpc()
  createWindow()
  log.info('VideoForge GUI baslatildi', app.isPackaged ? '(uretim)' : '(dev)')

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  cancelJob()
})
