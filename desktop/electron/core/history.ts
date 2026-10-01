import fs from 'node:fs'
import type { RunHistoryItem } from '@shared/types'
import { log } from './logger'
import { veriDosyasi } from './paths'

/**
 * IS GECMISI
 * ----------
 * Eski surumde gecmis yalnizca bellekte tutuluyordu; uygulama kapaninca
 * kayboluyordu. Artik her is bitiminde ozet (cikti dosyalari, maliyet, sure)
 * diske yazilir ve "Calistir" sayfasindaki Gecmis listesinde acilabilir.
 */
const MAKS = 50

let cache: RunHistoryItem[] | null = null

function dosya(): string {
  return veriDosyasi('gecmis.json')
}

function yukle(): RunHistoryItem[] {
  if (cache) return cache
  try {
    const raw = fs.readFileSync(dosya(), 'utf8')
    const parsed = JSON.parse(raw) as RunHistoryItem[]
    cache = Array.isArray(parsed)
      ? parsed.map((item) => ({ ...item, artifacts: Array.isArray(item.artifacts) ? item.artifacts : [] }))
      : []
  } catch {
    cache = []
  }
  return cache
}

function kaydet(): void {
  try {
    const list = yukle()
    fs.writeFileSync(dosya(), JSON.stringify(list.slice(0, MAKS), null, 2), 'utf8')
  } catch (err) {
    log.warn('gecmis yazilamadi:', err)
  }
}

export function gecmisListesi(): RunHistoryItem[] {
  return yukle().slice(0, MAKS)
}

export function gecmiseEkle(item: RunHistoryItem): void {
  const list = yukle()
  list.unshift(item)
  if (list.length > MAKS) list.length = MAKS
  kaydet()
}
