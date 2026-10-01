import fs from 'node:fs'
import path from 'node:path'
import type { KrediServisi } from '@shared/types'
import { botPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { log } from '../core/logger'

/**
 * SERVIS KREDILERI
 *
 * Kullanicinin botu hangi servisleri kullaniyorsa kalan kredisini gosterir.
 * Anahtarlar bot klasorundeki .env dosyasindan okunur (aynen constants.py gibi);
 * Zapcap anahtari .env'de yoksa ShortsStudio/functions/config.py'den alinir.
 *
 * Bot koduna dokunmaz; yalnizca salt-okunur HTTP ile bakiye sorgular.
 */

const TIMEOUT_MS = 15_000

/** Bot klasorundeki .env dosyasini basitce ayristirir (KEY=VALUE). */
function okuEnv(root: string): Record<string, string> {
  const deger: Record<string, string> = {}
  try {
    const metin = fs.readFileSync(path.join(root, '.env'), 'utf8')
    for (const satir of metin.split(/\r?\n/)) {
      const t = satir.trim()
      if (!t || t.startsWith('#') || !t.includes('=')) continue
      const i = t.indexOf('=')
      const k = t.slice(0, i).trim()
      const v = t.slice(i + 1).trim().replace(/^["']|["']$/g, '')
      if (k) deger[k] = v
    }
  } catch {
    /* .env yok - sorun degil */
  }
  return deger
}

/** ShortsStudio klasoru: ayarda belirtilmisse onu, yoksa bot klasorunun kardesini kullanir. */
function shortsStudioDir(root: string): string | null {
  const ayar = (getSettings().shortsStudioPath || '').trim()
  if (ayar) return ayar
  try {
    const kardes = path.resolve(root, '..', 'ShortsStudio')
    return fs.existsSync(kardes) ? kardes : null
  } catch {
    return null
  }
}

/** Zapcap anahtarini once .env'de, yoksa ShortsStudio config.py'de arar. */
function zapcapAnahtari(root: string, env: Record<string, string>): { key: string; kaynak: string | null } {
  if (env.ZAPCAP_API_KEY) return { key: env.ZAPCAP_API_KEY, kaynak: '.env' }
  const ss = shortsStudioDir(root)
  if (ss) {
    try {
      const cfg = fs.readFileSync(path.join(ss, 'functions', 'config.py'), 'utf8')
      const m = /ZAPCAP_API_KEY\s*=\s*["']([A-Za-z0-9_-]+)["']/.exec(cfg)
      if (m) return { key: m[1], kaynak: 'ShortsStudio/functions/config.py' }
    } catch {
      /* config.py yok */
    }
  }
  return { key: '', kaynak: null }
}

interface HttpSonuc {
  ok: boolean
  data: unknown
  error?: string
}

async function jsonGet(url: string, headers: Record<string, string>): Promise<HttpSonuc> {
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(TIMEOUT_MS) })
    if (!res.ok) {
      const text = (await res.text().catch(() => '')).slice(0, 140)
      return { ok: false, data: null, error: `HTTP ${res.status}${text ? ` · ${text}` : ''}` }
    }
    return { ok: true, data: await res.json() }
  } catch (err) {
    return { ok: false, data: null, error: String((err as Error)?.message ?? err).slice(0, 180) }
  }
}

/** ElevenLabs: kalan karakter = character_limit - character_count. */
async function elevenlabs(key: string): Promise<KrediServisi> {
  const ad = 'ElevenLabs (seslendirme)'
  if (!key) {
    return {
      id: 'elevenlabs',
      ad,
      durum: 'anahtar-yok',
      kalan: null,
      toplam: null,
      birim: 'karakter',
      detay: 'Bot klasöründeki .env dosyasına ELEVENLABS_API_KEY ekleyin.',
    }
  }
  const r = await jsonGet('https://api.elevenlabs.io/v1/user/subscription', { 'xi-api-key': key, accept: 'application/json' })
  if (!r.ok || !r.data) return { id: 'elevenlabs', ad, durum: 'hata', kalan: null, toplam: null, birim: 'karakter', hata: r.error }
  const d = r.data as {
    character_count?: number
    character_limit?: number
    tier?: string
    next_character_count_reset_unix?: number
  }
  const limit = Number(d.character_limit ?? 0)
  const used = Number(d.character_count ?? 0)
  return {
    id: 'elevenlabs',
    ad,
    durum: 'ok',
    kalan: Number.isFinite(limit) && limit > 0 ? Math.max(0, limit - used) : null,
    toplam: limit > 0 ? limit : null,
    birim: 'karakter',
    detay: d.tier ? `plan: ${d.tier}` : undefined,
    sifirlanmaMs: d.next_character_count_reset_unix ? d.next_character_count_reset_unix * 1000 : null,
  }
}

/** Zapcap: kalan API bakiyesi (USD). */
async function zapcap(key: string, kaynak: string | null): Promise<KrediServisi> {
  const ad = 'ZapCap (altyazı/efekt)'
  if (!key) {
    return {
      id: 'zapcap',
      ad,
      durum: 'anahtar-yok',
      kalan: null,
      toplam: null,
      birim: 'USD',
      detay: 'Ayarlar’dan ShortsStudio klasörünü gösterin ya da .env içine ZAPCAP_API_KEY ekleyin.',
    }
  }
  const r = await jsonGet('https://api.zapcap.ai/user-billing', { 'X-Api-Key': key, accept: 'application/json' })
  if (!r.ok || !r.data) return { id: 'zapcap', ad, durum: 'hata', kalan: null, toplam: null, birim: 'USD', hata: r.error }
  const bal = Number((r.data as { balance?: string | number }).balance ?? NaN)
  return {
    id: 'zapcap',
    ad,
    durum: 'ok',
    kalan: Number.isFinite(bal) ? bal : null,
    toplam: null,
    birim: 'USD',
    detay: kaynak ? `anahtar: ${kaynak}` : undefined,
  }
}

/** Gemini: resmi kredi API'si yok; anahtar/model bilgisi gosterilir (kota karti tahmini verir). */
function gemini(env: Record<string, string>): KrediServisi {
  const keys = (env.GEMINI_API_KEYS || env.GEMINI_API_KEY || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  return {
    id: 'gemini',
    ad: 'Google Gemini (AI)',
    durum: keys.length ? 'bilgi' : 'anahtar-yok',
    kalan: null,
    toplam: null,
    birim: 'istek',
    detay: keys.length
      ? `${keys.length} anahtar · günlük model kotaları için “Gemini kotası” kartına bakın`
      : '.env içinde GEMINI_API_KEYS bulunamadı',
  }
}

/** Tum servislerin kalan kredisini paralel sorgular. */
export async function kredileriGetir(): Promise<KrediServisi[]> {
  const root = botPath(getSettings().videoForgePath)
  const env = okuEnv(root)
  const zc = zapcapAnahtari(root, env)
  const [el, zp] = await Promise.all([
    elevenlabs((env.ELEVENLABS_API_KEY || '').trim()),
    zapcap(zc.key, zc.kaynak),
  ])
  log.info('krediler sorgulandi:', el.durum, zp.durum)
  return [el, zp, gemini(env)]
}
