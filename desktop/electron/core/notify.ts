import { Notification } from 'electron'
import { getSettings } from './settings'
import { log } from './logger'

/**
 * Masaustu bildirimi: is bitince kullanici baska bir pencerede olsa bile
 * haberdar olur. Ayarlardan kapatilabilir (varsayilan acik).
 */
export function bildir(baslik: string, govde: string): void {
  try {
    if (!getSettings().notifyOnComplete) return
    if (!Notification.isSupported()) return
    new Notification({ title: baslik, body: govde, silent: false }).show()
  } catch (err) {
    log.warn('bildirim gosterilemedi:', err)
  }
}
