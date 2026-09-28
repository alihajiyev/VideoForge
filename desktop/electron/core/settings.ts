import { app } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import type { AppSettings } from '@shared/types'
import { defaultBotPath } from './paths'
import { log } from './logger'

export const DEFAULT_UPDATE_REPO = 'alihajiyev/VideoForge'

/** Eski varsayilan depo adi: kayitli ayarlarda kaldiysa yeni adrese tasinir. */
const LEGACY_UPDATE_REPOS = ['alihajiyev/VideoForge-updates']

function defaults(): AppSettings {
  return {
    mode: 'dark',
    videoForgePath: defaultBotPath(),
    pythonPath: '',
    autoRevealOutput: true,
    logTailLines: 800,
    autoCheckUpdates: true,
    updateRepo: DEFAULT_UPDATE_REPO,
    githubToken: '',
  }
}

function filePath(): string {
  return path.join(app.getPath('userData'), 'settings.json')
}

let cached: AppSettings | null = null

export function getSettings(): AppSettings {
  if (cached) return cached
  const base = defaults()
  try {
    const raw = fs.readFileSync(filePath(), 'utf8')
    const parsed = JSON.parse(raw) as Partial<AppSettings>
    cached = { ...base, ...parsed }
    // Depo adi degistiyse eski kayitli degeri tasi (kullanici kendi adresini girdiyse dokunma).
    if (cached.updateRepo && LEGACY_UPDATE_REPOS.includes(cached.updateRepo.trim())) {
      cached = { ...cached, updateRepo: DEFAULT_UPDATE_REPO }
    }
  } catch {
    cached = base
  }
  return cached
}

export function setSettings(patch: Partial<AppSettings>): AppSettings {
  const next = { ...getSettings(), ...patch }
  cached = next
  try {
    fs.writeFileSync(filePath(), JSON.stringify(next, null, 2), 'utf8')
  } catch (err) {
    log.warn('settings yazilamadi:', err)
  }
  return next
}
