import fs from 'node:fs'
import path from 'node:path'
import { KLIP_KLASOR } from '@shared/constants'
import type { KlipDurumu, KlipKlasoru, KlipOgesi } from '@shared/types'
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
    baslik: String(ham.baslik || 'Klip'),
    skor: sayi(ham.skor),
    sure: sayi(ham.sure),
    baslangic: sayi(ham.baslangic),
    bitis: sayi(ham.bitis),
    panelDagilimi: (ham.panel_dagilimi as Record<string, number>) || {},
    dosya: bilgi.var ? dosya : dosya,
    dosyaVar: bilgi.var,
    boyut: bilgi.boyut,
    srt,
    qaPuan: qa.puan === undefined || qa.puan === null ? null : sayi(qa.puan),
    qaDerece: typeof qa.derece === 'string' ? qa.derece : null,
    qaSorunlar: Array.isArray(qa.sorunlar) ? qa.sorunlar.map((s) => String(s)) : [],
    hata: typeof ham.hata === 'string' ? ham.hata : undefined,
  }
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
    link: String(plan.link || ''),
    video: String(plan.video || ''),
    konusmaciSayisi: sayi(plan.konusmaci_sayisi, 1),
    konusmaciYontemi: String(plan.ayrim_yontemi || ''),
    yuzIziSayisi: sayi(plan.yuz_izi_sayisi),
    transkriptKaynagi: String(plan.transkript_kaynagi || ''),
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
