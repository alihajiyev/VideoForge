import { app } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { autoUpdater } from 'electron-updater'
import type { AutoUpdateState } from '@shared/types'
import { IPC } from '@shared/constants'
import { broadcast } from '../core/events'
import { getSettings } from '../core/settings'
import { log } from '../core/logger'

/**
 * UYGULAMA ICI OTOMATIK GUNCELLEME (electron-updater)
 *
 * Ayarlar > "Guncellemeleri kontrol et" artik setup dosyasi indirip elle
 * calistirmayi gerektirmez: yeni surum arka planda indirilir ve uygulama
 * kapanirken (veya "Simdi guncelle" ile) sessizce kurulup yeniden baslar.
 *
 * Calismasi icin derlemede resources/app-update.yml ve depoda latest.yml
 * olmalidir. Ikisi de electron-builder'in publish yapilandirmasiyla uretilir
 * (bkz. electron-builder.yml + scripts/release.mjs).
 */

let durum: AutoUpdateState = {
  durum: 'bosta',
  current: app.getVersion(),
  version: null,
  pct: 0,
  received: 0,
  total: 0,
}

let kuruldu = false
let destekli = false

/** app-update.yml uretilmis mi (paketli derleme + publish yapilandirmasi)? */
function destekVar(): boolean {
  if (!app.isPackaged) return false
  try {
    return fs.existsSync(path.join(process.resourcesPath, 'app-update.yml'))
  } catch {
    return false
  }
}

function yayinla(patch: Partial<AutoUpdateState> = {}): void {
  durum = { ...durum, ...patch }
  broadcast(IPC.updateAutoChanged, durum)
}

export function otomatikDurum(): AutoUpdateState {
  return durum
}

export function otomatikDestekli(): boolean {
  return destekli
}

/** Uygulama acilirken bir kez cagrilir; electron-updater olaylarini renderer'a aktarir. */
export function otomatikGuncellemeBaslat(): void {
  if (kuruldu) return
  kuruldu = true
  destekli = destekVar()
  durum = { ...durum, durum: destekli ? 'bosta' : 'kapali' }
  if (!destekli) {
    log.info('otomatik guncelleme devre disi (paketli derleme veya app-update.yml yok)')
    return
  }

  // Indirmeyi biz yonetiriz; kurulum uygulama kapaninca otomatik yapilir.
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.logger = {
    info: (m?: unknown) => log.info('[updater]', String(m)),
    warn: (m?: unknown) => log.warn('[updater]', String(m)),
    error: (m?: unknown) => log.error('[updater]', String(m)),
    debug: () => undefined,
  }

  autoUpdater.on('checking-for-update', () => yayinla({ durum: 'kontrol' }))
  autoUpdater.on('update-available', (info) => {
    log.info('guncelleme mevcut:', info.version)
    yayinla({ durum: 'mevcut', version: info.version })
  })
  autoUpdater.on('update-not-available', () => yayinla({ durum: 'guncel', pct: 0 }))
  autoUpdater.on('download-progress', (p) =>
    yayinla({ durum: 'indiriliyor', pct: Math.round(p.percent), received: p.transferred, total: p.total }),
  )
  autoUpdater.on('update-downloaded', (info) => {
    log.info('guncelleme indirildi:', info.version)
    yayinla({ durum: 'hazir', version: info.version, pct: 100 })
  })
  autoUpdater.on('error', (err) => {
    log.warn('otomatik guncelleme hatasi:', err)
    yayinla({ durum: 'hata', error: String(err?.message ?? err).slice(0, 300) })
  })
}

/** Kontrolu tetikler (Ayarlar butonu ya da acilis). Indirme otomatik baslar. */
export async function otomatikKontrol(): Promise<AutoUpdateState> {
  if (!destekli) return durum
  try {
    await autoUpdater.checkForUpdates()
  } catch (err) {
    log.warn('otomatik guncelleme kontrolu basarisiz:', err)
    yayinla({ durum: 'hata', error: String((err as Error)?.message ?? err).slice(0, 300) })
  }
  return durum
}

/** Acilista otomatik kontrol (ayarda aciksa). */
export async function otomatikAcilisKontrol(): Promise<void> {
  if (!destekli) return
  if (!getSettings().autoCheckUpdates) return
  await otomatikKontrol()
}

/** Indirilen guncellemeyi sessizce kurup uygulamayi yeniden baslatir. */
export function otomatikKur(): { ok: boolean; error?: string } {
  if (!destekli) return { ok: false, error: 'Otomatik guncelleme bu derlemede kullanilabilir degil.' }
  if (durum.durum !== 'hazir') return { ok: false, error: 'Indirilmis bir guncelleme yok.' }
  try {
    setImmediate(() => autoUpdater.quitAndInstall(false, true))
    return { ok: true }
  } catch (err) {
    return { ok: false, error: String((err as Error)?.message ?? err) }
  }
}
