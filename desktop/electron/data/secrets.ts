import fs from 'node:fs'
import path from 'node:path'
import type { AltyaziMotoru, GizliAnahtarlar } from '@shared/types'
import { botPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { log } from '../core/logger'

/**
 * GIZLI ANAHTARLAR / KANAL AYARLARI
 * ---------------------------------
 * API anahtarlarini, ses (voice ID) ve altyazi motorunu uygulamadan
 * duzenlenebilir kilar. Tek kaynak bot klasorundeki `.env` dosyasidir; ayni
 * degerler ShortsStudio'nun `functions/config.py` dosyasina da yazilir
 * (ZapCap anahtari/sablonu + altyazi motoru orada okunur).
 *
 * Bot ve ShortsStudio PYTHON MANTIGINA dokunulmaz: yalnizca .env ve config.py
 * icindeki deger satirlari guncellenir. Bos/gecersiz degerler eski davranisi
 * koruyacak sekilde varsayilanlara duser.
 */

const VOICE_DEFAULT_CH1 = 'M1CSR3PJBsfWU6ZquG3C'
const VOICE_DEFAULT_CH2 = 'M1CSR3PJBsfWU6ZquG3C'
const VOICE_DEFAULT_CH3 = 'LHi3adMlU7AICv8Yxpmm'
const MOTORLER: AltyaziMotoru[] = ['auto', 'zapcap', 'yerel', 'remotion']

function envPath(root: string): string {
  return path.join(root, '.env')
}

/** Bot klasorundeki .env dosyasini basitce ayristirir (KEY=VALUE). */
function okuEnv(root: string): Record<string, string> {
  const deger: Record<string, string> = {}
  try {
    const metin = fs.readFileSync(envPath(root), 'utf8')
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
  if (ayar && fs.existsSync(path.join(ayar, 'functions', 'config.py'))) return ayar
  try {
    const kardes = path.resolve(root, '..', 'ShortsStudio')
    return fs.existsSync(path.join(kardes, 'functions', 'config.py')) ? kardes : null
  } catch {
    return null
  }
}

/** ShortsStudio config.py icindeki ZAPCAP/ALTYAZI degerlerini regex ile okur. */
function ssConfigOku(dir: string | null): Record<string, string> {
  const sonuc: Record<string, string> = {}
  if (!dir) return sonuc
  try {
    const cfg = fs.readFileSync(path.join(dir, 'functions', 'config.py'), 'utf8')
    const al = (ad: string): string | null => {
      const m = new RegExp(`^\\s*${ad}\\s*=\\s*["']([^"']*)["']`, 'm').exec(cfg)
      return m ? m[1] : null
    }
    const zk = al('ZAPCAP_API_KEY')
    const zt = al('ZAPCAP_TEMPLATE_ID')
    const am = al('ALTYAZI_MOTORU')
    if (zk !== null) sonuc.ZAPCAP_API_KEY = zk
    if (zt !== null) sonuc.ZAPCAP_TEMPLATE_ID = zt
    if (am !== null) sonuc.ALTYAZI_MOTORU = am
  } catch {
    /* config.py okunamadi */
  }
  return sonuc
}

/** .env dosyasindaki verilen anahtarlari gunceller; olmayanlari sona ekler. */
function envYaz(root: string, patch: Record<string, string>): void {
  const yol = envPath(root)
  let satirlar: string[] = []
  try {
    satirlar = fs.readFileSync(yol, 'utf8').split(/\r?\n/)
  } catch {
    satirlar = []
  }
  const kalan = new Map(Object.entries(patch))
  const yeni = satirlar.map((satir) => {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=/.exec(satir)
    if (m && kalan.has(m[1])) {
      const v = kalan.get(m[1]) as string
      kalan.delete(m[1])
      return `${m[1]}=${v}`
    }
    return satir
  })
  for (const [k, v] of kalan) yeni.push(`${k}=${v}`)
  // Dosya sonundaki gereksiz bos satirlari kirp, tek yeni satir birak.
  while (yeni.length > 1 && yeni[yeni.length - 1].trim() === '') yeni.pop()
  fs.writeFileSync(yol, yeni.join('\n') + '\n', 'utf8')
}

/** ShortsStudio config.py icindeki ZapCap + altyazi motoru degerlerini gunceller. */
function shortsStudioYaz(dir: string | null, deger: { zapcapApiKey?: string; zapcapTemplateId?: string; altyaziMotoru?: AltyaziMotoru }): boolean {
  if (!dir) return false
  const yol = path.join(dir, 'functions', 'config.py')
  try {
    let cfg = fs.readFileSync(yol, 'utf8')
    const degistir = (ad: string, val: string): void => {
      const re = new RegExp(`^\\s*${ad}\\s*=\\s*["'][^"']*["']`, 'm')
      if (re.test(cfg)) cfg = cfg.replace(re, `${ad} = "${val}"`)
      else cfg = cfg.replace(/^(ZAPCAP_TEMPLATE_ID\s*=.*)$/m, `$1\n${ad} = "${val}"`) // sablon satirindan sonra ekle
    }
    if (deger.zapcapApiKey !== undefined) degistir('ZAPCAP_API_KEY', deger.zapcapApiKey)
    if (deger.zapcapTemplateId !== undefined) degistir('ZAPCAP_TEMPLATE_ID', deger.zapcapTemplateId)
    if (deger.altyaziMotoru !== undefined) degistir('ALTYAZI_MOTORU', deger.altyaziMotoru)
    fs.writeFileSync(yol, cfg, 'utf8')
    return true
  } catch (err) {
    log.warn('ShortsStudio config yazilamadi:', err)
    return false
  }
}

/** Etkin degerler: .env once, yoksa ShortsStudio config.py, yoksa varsayilan. */
export function gizliAnahtarlariGetir(): GizliAnahtarlar {
  const root = botPath(getSettings().videoForgePath)
  const env = okuEnv(root)
  const dir = shortsStudioDir(root)
  const ss = ssConfigOku(dir)
  const motorHam = (env.ALTYAZI_MOTORU || ss.ALTYAZI_MOTORU || 'auto').trim() as AltyaziMotoru
  return {
    geminiApiKeys: env.GEMINI_API_KEYS || env.GEMINI_API_KEY || '',
    elevenlabsApiKey: env.ELEVENLABS_API_KEY || '',
    transcriptApiKey: env.TRANSCRIPT_API_KEY || '',
    zapcapApiKey: env.ZAPCAP_API_KEY || ss.ZAPCAP_API_KEY || '',
    zapcapTemplateId: env.ZAPCAP_TEMPLATE_ID || ss.ZAPCAP_TEMPLATE_ID || '',
    altyaziMotoru: MOTORLER.includes(motorHam) ? motorHam : 'auto',
    voiceCh1: env.VOICE_ID_CH1 || VOICE_DEFAULT_CH1,
    voiceCh2: env.VOICE_ID_CH2 || VOICE_DEFAULT_CH2,
    voiceCh3: env.VOICE_ID_CH3 || VOICE_DEFAULT_CH3,
    envPath: envPath(root),
    shortsStudioFound: Boolean(dir),
  }
}

/** Verilen degerleri .env'e (ve mumkunse ShortsStudio config.py'ye) yazar. */
export function gizliAnahtarlariYaz(patch: Partial<GizliAnahtarlar>): GizliAnahtarlar {
  const root = botPath(getSettings().videoForgePath)
  const envPatch: Record<string, string> = {}
  const koy = (anahtar: string, deger: string | undefined): void => {
    if (deger !== undefined) envPatch[anahtar] = deger.trim()
  }
  koy('GEMINI_API_KEYS', patch.geminiApiKeys)
  koy('ELEVENLABS_API_KEY', patch.elevenlabsApiKey)
  koy('TRANSCRIPT_API_KEY', patch.transcriptApiKey)
  koy('ZAPCAP_API_KEY', patch.zapcapApiKey)
  koy('ZAPCAP_TEMPLATE_ID', patch.zapcapTemplateId)
  koy('VOICE_ID_CH1', patch.voiceCh1)
  koy('VOICE_ID_CH2', patch.voiceCh2)
  koy('VOICE_ID_CH3', patch.voiceCh3)
  if (patch.altyaziMotoru !== undefined) envPatch.ALTYAZI_MOTORU = patch.altyaziMotoru

  envYaz(root, envPatch)

  const dir = shortsStudioDir(root)
  const ssYazildi = shortsStudioYaz(dir, {
    zapcapApiKey: patch.zapcapApiKey,
    zapcapTemplateId: patch.zapcapTemplateId,
    altyaziMotoru: patch.altyaziMotoru,
  })

  log.info('gizli anahtarlar kaydedildi:', Object.keys(envPatch).join(','), ssYazildi ? '(ShortsStudio guncellendi)' : '')

  // Modal secret'i (bulut) yeni anahtarlarla tazelemek icin botu bir kez
  // bilgilendirmeye gerek yok: bulut_kanali.py ilk bulut cagrisinda imza
  // degistigini gorup secret'i otomatik yeniden yazar.
  return gizliAnahtarlariGetir()
}
