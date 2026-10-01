import fs from 'node:fs'
import { getSettings } from './settings'
import { log } from './logger'
import { veriDosyasi } from './paths'
import { isRunning, startJob } from '../python/runner'

/**
 * ZAMANLANMIS GOREV (uygulama acikken)
 * ------------------------------------
 * Kullanici istedigi saatte gunluk kesif veya zincir baslatabilir. Windows
 * Gorev Zamanlayici'ye dokunmadan, yalnizca uygulama acikken calisir; ayni
 * gun ayni saatte ikinci kez tetiklenmez (son calisma diske yazilir).
 */
const KONTROL_MS = 30_000

let sonCalisan: string | null = null
let timer: NodeJS.Timeout | null = null

function dosya(): string {
  return veriDosyasi('zamanlama-son.json')
}

function yukle(): string | null {
  if (sonCalisan !== null) return sonCalisan
  try {
    sonCalisan = fs.readFileSync(dosya(), 'utf8').trim() || null
  } catch {
    sonCalisan = null
  }
  return sonCalisan
}

function kaydet(deger: string): void {
  sonCalisan = deger
  try {
    fs.writeFileSync(dosya(), deger, 'utf8')
  } catch (err) {
    log.warn('zamanlama kaydedilemedi:', err)
  }
}

function iki(n: number): string {
  return String(n).padStart(2, '0')
}

async function kontrol(): Promise<void> {
  try {
    const s = getSettings()
    if (!s.scheduleEnabled) return
    if (isRunning()) return
    const now = new Date()
    const saat = `${iki(now.getHours())}:${iki(now.getMinutes())}`
    if (saat !== s.scheduleTime) return
    const gun = `${now.getFullYear()}-${iki(now.getMonth() + 1)}-${iki(now.getDate())}`
    const anahtar = `${gun} ${s.scheduleTime}`
    if (yukle() === anahtar) return
    kaydet(anahtar)
    log.info('zamanlanmış görev başlıyor:', s.scheduleKind, s.scheduleChannel)
    await startJob({
      kind: s.scheduleKind,
      channelId: s.scheduleChannel,
      gunSayisi: s.gunSayisi,
      haftalik: s.scheduleKind === 'discover',
    })
  } catch (err) {
    log.warn('zamanlama kontrolü hatası:', err)
  }
}

export function zamanlayiciBaslat(): void {
  if (timer) return
  timer = setInterval(() => void kontrol(), KONTROL_MS)
  void kontrol()
}
