import fs from 'node:fs'
import path from 'node:path'
import { KLIP_KLASOR } from '@shared/constants'
import type {
  KlipDurumu,
  KlipKesit,
  KlipKirilim,
  KlipKlasoru,
  KlipMod,
  KlipOtoBilgi,
  KlipOgesi,
  KlipTranskript,
  TranskriptKesit,
} from '@shared/types'
import { desktopDir } from '../core/paths'

/**
 * KLIPCI cikti klasorlerini okur (functions/klipci.py -> klip_plani.json).
 * Hicbir sey calistirmaz, sadece dosya okur; motor kapaliyken de guvenli.
 */
export function klipKok(): string {
  const override = (process.env.VF_KLIP_ROOT || '').trim()
  return override || path.join(desktopDir, KLIP_KLASOR)
}

function sayi(deger: unknown, varsayilan = 0): number {
  const v = Number(deger)
  return Number.isFinite(v) ? v : varsayilan
}

function metin(deger: unknown, varsayilan = ''): string {
  return typeof deger === 'string' ? deger : varsayilan
}

function mod(deger: unknown): KlipMod {
  return deger === 'gorsel' ? 'gorsel' : 'konusma'
}

function kirilim(ham: unknown): KlipKirilim {
  const kaynak = (ham || {}) as Record<string, unknown>
  const cikti: KlipKirilim = {}
  for (const anahtar of [
    'hook',
    'hook_acilis',
    'bilgi',
    'nadirlik',
    'vurgu',
    'konu',
    'konu_orani',
    'yogunluk',
    'ceza',
    'hareket',
    'ses',
    'kesme',
    'zenginlik',
  ] as const) {
    const v = kaynak[anahtar]
    cikti[anahtar] = v === undefined || v === null ? null : sayi(v)
  }
  return cikti
}

function kesitler(ham: unknown): KlipKesit[] {
  if (!Array.isArray(ham)) return []
  return ham.slice(0, 200).map((k) => {
    const kk = (k || {}) as Record<string, unknown>
    return {
      bas: sayi(kk.bas),
      son: sayi(kk.son),
      panel: sayi(kk.panel, 1),
      metin: metin(kk.metin),
      skor: kk.skor === undefined || kk.skor === null ? null : sayi(kk.skor),
    }
  })
}

function dosyaBilgi(yol: string | null | undefined): { var: boolean; boyut: number } {
  if (!yol) return { var: false, boyut: 0 }
  try {
    const st = fs.statSync(yol)
    return { var: st.isFile(), boyut: st.size }
  } catch {
    return { var: false, boyut: 0 }
  }
}

function klipOgesi(ham: Record<string, unknown>, indeks: number): KlipOgesi {
  const dosya = typeof ham.dosya === 'string' && ham.dosya ? ham.dosya : null
  const bilgi = dosyaBilgi(dosya)
  const qa = (ham.qa || {}) as Record<string, unknown>
  const srt = typeof ham.srt === 'string' && ham.srt && fs.existsSync(ham.srt) ? ham.srt : null
  return {
    no: sayi(ham.no, indeks + 1),
    baslik: metin(ham.baslik, 'Klip') || 'Klip',
    mod: mod(ham.mod),
    konu: metin(ham.konu),
    kirilim: kirilim(ham.kirilim),
    kesitler: kesitler(ham.kesitler),
    skor: sayi(ham.skor),
    enYuksek: sayi(ham.en_yuksek, sayi(ham.skor)),
    sure: sayi(ham.sure),
    baslangic: sayi(ham.baslangic),
    bitis: sayi(ham.bitis),
    panelDagilimi: (ham.panel_dagilimi as Record<string, number>) || {},
    dosya,
    dosyaVar: bilgi.var,
    boyut: bilgi.boyut,
    srt,
    qaPuan: qa.puan === undefined || qa.puan === null ? null : sayi(qa.puan),
    qaDerece: typeof qa.derece === 'string' ? qa.derece : null,
    qaSorunlar: Array.isArray(qa.sorunlar) ? qa.sorunlar.map((s) => String(s)) : [],
    hata: typeof ham.hata === 'string' ? ham.hata : undefined,
  }
}

/** plan.oto -> arayuz tipi (otomatik mod bilgisi; yoksa null). */
function otoOku(ham: unknown): KlipOtoBilgi | null {
  if (!ham || typeof ham !== 'object') return null
  const o = ham as Record<string, unknown>
  const esik = sayi(o.skor_esigi, Number.NaN)
  return {
    klipSayisi: Boolean(o.klip_sayisi),
    sure: Boolean(o.sure),
    aday: sayi(o.aday),
    secilen: sayi(o.secilen),
    atlanan: sayi(o.atlanan),
    skorEsigi: Number.isFinite(esik) ? esik : null,
    sureUst: sayi(o.sure_ust),
  }
}

function konularOku(ham: unknown): KlipKlasoru['konular'] {
  if (!Array.isArray(ham)) return []
  return ham.map((c, i) => {
    const cc = (c || {}) as Record<string, unknown>
    return {
      no: sayi(cc.no, i),
      etiket: metin(cc.etiket, `konu ${i + 1}`),
      baslangic: sayi(cc.baslangic),
      bitis: sayi(cc.bitis),
      kesitSayisi: sayi(cc.kesit_sayisi),
      skor: sayi(cc.skor),
    }
  })
}

function klasorOku(klasor: string): KlipKlasoru | null {
  const planYolu = path.join(klasor, 'klip_plani.json')
  let plan: Record<string, unknown>
  try {
    plan = JSON.parse(fs.readFileSync(planYolu, 'utf8')) as Record<string, unknown>
  } catch {
    return null
  }
  let mtime = Date.now()
  try {
    mtime = fs.statSync(planYolu).mtimeMs
  } catch {
    /* yoksay */
  }
  const kliplerHam = Array.isArray(plan.klipler) ? (plan.klipler as Record<string, unknown>[]) : []
  const klipler = kliplerHam.map((k, i) => klipOgesi(k, i))
  return {
    klasor,
    ad: path.basename(klasor),
    mtime,
    link: metin(plan.link),
    video: metin(plan.video),
    mod: mod(plan.mod),
    oto: otoOku(plan.oto),
    konular: konularOku(plan.konular),
    transkriptVar: fs.existsSync(path.join(klasor, 'transkript.json')),
    konusmaciSayisi: sayi(plan.konusmaci_sayisi, 1),
    konusmaciYontemi: metin(plan.ayrim_yontemi),
    yuzIziSayisi: sayi(plan.yuz_izi_sayisi),
    transkriptKaynagi: metin(plan.transkript_kaynagi),
    atilanKesit: sayi(plan.atilan_kesit),
    planDosyasi: planYolu,
    klipler,
  }
}

export function klipDurumu(kok: string = klipKok()): KlipDurumu {
  const bos: KlipDurumu = { ok: true, kok, klasorler: [], toplamKlip: 0, enIyiPuan: null }
  let girdiler: fs.Dirent[]
  try {
    girdiler = fs.readdirSync(kok, { withFileTypes: true })
  } catch {
    return bos
  }
  const klasorler: KlipKlasoru[] = []
  for (const girdi of girdiler) {
    if (!girdi.isDirectory()) continue
    const veri = klasorOku(path.join(kok, girdi.name))
    if (veri) klasorler.push(veri)
  }
  klasorler.sort((a, b) => b.mtime - a.mtime)
  const puanlar = klasorler
    .flatMap((k) => k.klipler.map((i) => i.qaPuan))
    .filter((p): p is number => p !== null)
  return {
    ok: true,
    kok,
    klasorler,
    toplamKlip: klasorler.reduce((toplam, k) => toplam + k.klipler.length, 0),
    enIyiPuan: puanlar.length ? Math.max(...puanlar) : null,
  }
}

/**
 * Tek bir klasorun transkript haritasi: hangi saniyede ne konusuldu.
 * (klipci.py -> transkript.json; sadece konusma modunda yazilir.)
 */
export function klipTranskript(klasor: string): KlipTranskript {
  const bos: KlipTranskript = { ok: true, kaynak: '', kesitler: [] }
  if (!klasor || !videoYolu(klasor)) {
    return { ...bos, ok: false, error: 'Gecersiz klasor' }
  }
  const yol = path.join(klasor, 'transkript.json')
  let ham: Record<string, unknown>
  try {
    ham = JSON.parse(fs.readFileSync(yol, 'utf8')) as Record<string, unknown>
  } catch {
    return bos
  }
  const hamKesitler = Array.isArray(ham.kesitler) ? (ham.kesitler as Record<string, unknown>[]) : []
  const kesitler: TranskriptKesit[] = hamKesitler.map((k) => ({
    bas: sayi(k.bas),
    son: sayi(k.son),
    metin: metin(k.metin),
    skor: k.skor === undefined || k.skor === null ? null : sayi(k.skor),
    konu: k.konu === undefined || k.konu === null ? null : sayi(k.konu),
    konuEtiket: metin(k.konu_etiket),
    konuBasi: Boolean(k.konu_basi),
  }))
  return { ok: true, kaynak: metin(ham.kaynak), kesitler }
}

/** Klasor yolu yalnizca izinli kokler altindaysa true. */
function videoYolu(hedef: string): boolean {
  try {
    const resolved = path.resolve(hedef)
    const izinli = [desktopDir, klipKok()].map((p) => path.resolve(p).toLowerCase())
    const alt = resolved.toLowerCase()
    return izinli.some((a) => alt === a || alt.startsWith(a + path.sep))
  } catch {
    return false
  }
}
