import fs from 'node:fs'
import path from 'node:path'
import type { KrediServisi } from '@shared/types'
import { botPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { log } from '../core/logger'
import { execCapture } from '../core/exec'
import { resolvePython } from '../python/locate'
import { harcamaOzeti } from './spend'

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
  /** HTTP durum kodu (hata halinde de dolu olur) */
  status?: number
}

async function jsonGet(url: string, headers: Record<string, string>): Promise<HttpSonuc> {
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(TIMEOUT_MS) })
    if (!res.ok) {
      const text = (await res.text().catch(() => '')).slice(0, 140)
      return { ok: false, data: null, status: res.status, error: `HTTP ${res.status}${text ? ` · ${text}` : ''}` }
    }
    return { ok: true, data: await res.json(), status: res.status }
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

/**
 * TranscriptAPI: resmi API'de bakiye uc noktasi YOK (openapi.json yalnizca 13
 * youtube yolu listeler; MCP araclarinda da kredi araci bulunmuyor). Bu yuzden
 * UCRETSIZ /youtube/info uc noktasiyla canli durum okunur: 200 = anahtar gecerli
 * ve en az 1 kredi var, 402 = kredi bitti. Kesin sayi dashboard'da gorunur.
 */
async function transcriptapi(key: string): Promise<KrediServisi> {
  const ad = 'TranscriptAPI (transkript)'
  const baglanti = 'https://transcriptapi.com/dashboard'
  if (!key) {
    return {
      id: 'transcriptapi',
      ad,
      durum: 'anahtar-yok',
      kalan: null,
      toplam: null,
      birim: 'istek',
      detay: 'Bot klasöründeki .env dosyasına TRANSCRIPT_API_KEY ekleyin (Ayarlar’dan da girilebilir).',
      baglanti,
    }
  }
  const r = await jsonGet('https://transcriptapi.com/api/v2/youtube/info?video_url=dQw4w9WgXcQ', {
    Authorization: `Bearer ${key}`,
    accept: 'application/json',
  })
  // 200 = anahtar gecerli + en az 1 kredi. 404 yalnizca "video bulunamadi"
  // demektir (kimlik dogrulama gecmistir), bu yuzden anahtar YINE gecerlidir.
  if (r.ok || r.status === 404) {
    return {
      id: 'transcriptapi',
      ad,
      durum: 'ok',
      kalan: null,
      toplam: null,
      birim: 'istek',
      detay: 'Anahtar geçerli · kredi mevcut (≥1). TranscriptAPI kesin bakiye uç noktası yayınlamıyor; tam sayı dashboard’da.',
      baglanti,
    }
  }
  if (r.status === 402) {
    return { id: 'transcriptapi', ad, durum: 'hata', kalan: 0, toplam: null, birim: 'istek', hata: 'Kredi bitti (HTTP 402). Dashboard’dan yükleme yapın.', baglanti }
  }
  if (r.status === 401 || r.status === 403) {
    return { id: 'transcriptapi', ad, durum: 'hata', kalan: null, toplam: null, birim: 'istek', hata: `Anahtar reddedildi (HTTP ${r.status}).`, baglanti }
  }
  return { id: 'transcriptapi', ad, durum: 'hata', kalan: null, toplam: null, birim: 'istek', hata: r.error, baglanti }
}

interface ModalOzet {
  /** Bu ay kalan dahil compute (USD) */
  kalan: number
  /** Aylik dahil compute (USD) */
  toplam: number
  /** Bu ay tuketilen kredi (USD) */
  tuketilen: number
  /** Bu ay toplam kullanim (metered, USD) */
  harcanan: number
}

/** Modal bakiye sorgusu ~10-20 sn surer; paneller tekrar tekrar sormasin diye onbellek. */
let modalCache: { t: number; veri: ModalOzet | null } | null = null
const MODAL_CACHE_MS = 3 * 60_000

/**
 * Modal: `modal billing summary --json` cikmasindan bu ayin GERCEK kullanimini
 * ve uygulanan krediyi okur. Kalan bakiye = aylik dahil compute - bu ay
 * uygulanan kredi (adjustments.credits). Modal'in kendi muhasebesine dayanir.
 */
async function modalOzet(aylikKredi: number): Promise<ModalOzet | null> {
  if (modalCache && Date.now() - modalCache.t < MODAL_CACHE_MS) return modalCache.veri
  const py = await resolvePython()
  if (!py.ok || !py.python) {
    modalCache = { t: Date.now(), veri: null }
    return null
  }
  const res = await execCapture(
    py.python.command,
    [...py.python.args, '-m', 'modal', 'billing', 'summary', '--json'],
    { timeoutMs: 60_000 },
  )
  if (res.code !== 0) {
    log.info('modal billing okunamadi:', (res.stderr || res.error || '').trim().split('\n').pop()?.slice(0, 160))
    modalCache = { t: Date.now(), veri: null }
    return null
  }
  try {
    const ham = res.stdout.slice(Math.max(0, res.stdout.indexOf('{')))
    const json = JSON.parse(ham) as { metered_cost?: string; adjustments?: { credits?: string } }
    const tuketilen = Math.abs(Number(json.adjustments?.credits ?? 0)) || 0
    const harcanan = Number(json.metered_cost ?? 0) || 0
    const veri: ModalOzet = {
      kalan: Math.max(0, aylikKredi - tuketilen),
      toplam: aylikKredi,
      tuketilen,
      harcanan,
    }
    modalCache = { t: Date.now(), veri }
    return veri
  } catch (err) {
    log.warn('modal billing json ayristirilamadi:', err)
    modalCache = { t: Date.now(), veri: null }
    return null
  }
}

/** Modal karti: gercek bakiye; okunamazsa uygulama defterinden tahmine duser. */
async function modal(aylikKredi: number, tahminiAyUsd: number): Promise<KrediServisi> {
  const ad = 'Modal (GPU bulut)'
  const baglanti = 'https://modal.com/settings/usage'
  const ozet = await modalOzet(aylikKredi)
  if (!ozet) {
    return {
      id: 'modal',
      ad,
      durum: 'bilgi',
      kalan: Number.isFinite(tahminiAyUsd) ? tahminiAyUsd : null,
      toplam: aylikKredi,
      birim: 'USD-tahmini',
      detay: 'Modal faturalama API’sine ulaşılamadı (giriş yapılmamış olabilir). Uygulamanın kendi defterinden bu ayın tahmini GPU harcaması gösteriliyor.',
      baglanti,
    }
  }
  return {
    id: 'modal',
    ad,
    durum: 'ok',
    kalan: ozet.kalan,
    toplam: ozet.toplam,
    birim: 'USD',
    detay: `Bu ay kullanılan dahil compute: $${ozet.tuketilen.toFixed(2)} · aylık toplam kullanım: $${ozet.harcanan.toFixed(2)} · her ay yenilenir`,
    baglanti,
  }
}

/** Tum servislerin kalan kredisini paralel sorgular. */
export async function kredileriGetir(): Promise<KrediServisi[]> {
  const root = botPath(getSettings().videoForgePath)
  const env = okuEnv(root)
  const zc = zapcapAnahtari(root, env)
  const ayar = getSettings()
  const aylikKredi = Number.isFinite(ayar.modalAylikKredi) && ayar.modalAylikKredi > 0 ? ayar.modalAylikKredi : 30
  const ayUsd = harcamaOzeti().ayUsd
  const [el, zp, ta, md] = await Promise.all([
    elevenlabs((env.ELEVENLABS_API_KEY || '').trim()),
    zapcap(zc.key, zc.kaynak),
    transcriptapi((env.TRANSCRIPT_API_KEY || '').trim()),
    modal(aylikKredi, ayUsd),
  ])
  log.info('krediler sorgulandi:', el.durum, zp.durum, ta.durum, md.durum)
  return [el, zp, ta, md, gemini(env)]
}
