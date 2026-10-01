import { app } from 'electron'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export const desktopDir = path.join(os.homedir(), 'Desktop')

/** dist-electron/main.cjs -> uygulama koku (desktop klasoru). */
export function appRoot(): string {
  return path.resolve(__dirname, '..')
}

/** Varsayilan VideoForge (bot) klasoru. */
export function defaultBotPath(): string {
  if (app.isPackaged) return path.join(desktopDir, 'VideoForge')
  return path.resolve(appRoot(), '..')
}

export function botPath(override?: string): string {
  const p = (override || '').trim()
  return p || defaultBotPath()
}

/** Bot klasorunde olmasi zorunlu dosyalar. */
export function requiredBotFiles(root: string): { name: string; ok: boolean }[] {
  const files = ['shared.py', 'constants.py', 'bulut_kanali.py', 'kinok_syjet.py', 'kinosekrety.py', 'faktza15.py', 'kesif.py']
  return files.map((name) => ({ name, ok: fs.existsSync(path.join(root, name)) }))
}

export function cookiesPath(root: string): string {
  return path.join(root, 'cookies.txt')
}

export function dbPath(root: string): string {
  return path.join(root, 'bot.db')
}

export function logPath(root: string): string {
  return path.join(root, 'bot_log.txt')
}

export function planPath(root: string): string {
  return path.join(root, 'haftalik_plan.json')
}

/**
 * Arayuzun kalici veri dosyasi (ayar disi: harcama, gecmis, kuyruk, zamanlama).
 * Testler/otomasyon VF_DATA_DIR ile kendi gecici klasorune yonlendirebilir;
 * boylece gercek kullanici verisi kirletilmez.
 */
export function veriDosyasi(name: string): string {
  const override = (process.env.VF_DATA_DIR || '').trim()
  const dir = override || app.getPath('userData')
  ensureDir(dir)
  return path.join(dir, name)
}

export function ensureDir(p: string): void {
  try {
    fs.mkdirSync(p, { recursive: true })
  } catch {
    /* yoksay */
  }
}
