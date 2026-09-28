import { BrowserWindow, ipcMain } from 'electron'
import { IPC } from '@shared/constants'

let mainWindow: BrowserWindow | null = null

export function setMainWindow(win: BrowserWindow | null): void {
  mainWindow = win
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow
}

export function windowState(): { maximized: boolean; focused: boolean } {
  return {
    maximized: Boolean(mainWindow && !mainWindow.isDestroyed() && mainWindow.isMaximized()),
    focused: Boolean(mainWindow && !mainWindow.isDestroyed() && mainWindow.isFocused()),
  }
}

export function emitWindowState(): void {
  const win = mainWindow
  if (win && !win.isDestroyed()) win.webContents.send(IPC.winStateChanged, windowState())
}

/** Kucult / buyut / kapat / durum sorgusu IPC handler'lari. */
export function registerWindowIpc(): void {
  ipcMain.handle(IPC.winMinimize, () => {
    mainWindow?.minimize()
    return true
  })
  ipcMain.handle(IPC.winMaximize, () => {
    const win = mainWindow
    if (!win) return false
    if (win.isMaximized()) win.unmaximize()
    else win.maximize()
    emitWindowState()
    return win.isMaximized()
  })
  ipcMain.handle(IPC.winClose, () => {
    mainWindow?.close()
    return true
  })
  ipcMain.handle(IPC.winState, () => windowState())
}
