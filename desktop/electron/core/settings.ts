import { app } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import type { AppSettings } from '@shared/types'
import { GUN_SAYISI_VARSAYILAN, normalGunSayisi } from '@shared/constants'
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
    gunSayisi: GUN_SAYISI_VARSAYILAN,
    notifyOnComplete: true,
    queueAutoStart: true,
    onboardingDone: false,
    scheduleEnabled: false,
    scheduleTime: '09:00',
    scheduleKind: 'discover',
    scheduleChannel: '1',
  }
}

/** Zamanlama saatini gecerli "HH:MM" bicimine ceker. */
function duzeltSaat(value: string | undefined): string {
  const m = /^(\d{1,2}):(\d{2})$/.exec((value ?? '').trim())
  if (!m) return '09:00'
  const h = Math.min(23, Math.max(0, Number(m[1])))
  const dk = Math.min(59, Math.max(0, Number(m[2])))
  return `${String(h).padStart(2, '0')}:${String(dk).padStart(2, '0')}`
}

/** Kayitli gun sayisini gecerli araliga ceker (bozuk/eski deger 7'ye doner). */
function duzeltGunSayisi(ayar: AppSettings): AppSettings {
  const sayi = normalGunSayisi(ayar.gunSayisi)
  const saat = duzeltSaat(ayar.scheduleTime)
  const kanal = (['1', '2', '3'] as const).includes(ayar.scheduleChannel) ? ayar.scheduleChannel : '1'
  const tur = ayar.scheduleKind === 'weekly' ? 'weekly' : 'discover'
  return {
    ...ayar,
    gunSayisi: sayi,
    scheduleTime: saat,
    scheduleChannel: kanal,
    scheduleKind: tur,
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
    cached = duzeltGunSayisi({ ...base, ...parsed })
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
  const next = duzeltGunSayisi({ ...getSettings(), ...patch })
  cached = next
  try {
    fs.writeFileSync(filePath(), JSON.stringify(next, null, 2), 'utf8')
  } catch (err) {
    log.warn('settings yazilamadi:', err)
  }
  return next
}
