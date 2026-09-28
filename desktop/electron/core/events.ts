import { BrowserWindow } from 'electron'

/** Tum pencerelere olay gonderir (kanal calisirken canli log akisi). */
export function broadcast(channel: string, payload: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send(channel, payload)
  }
}
