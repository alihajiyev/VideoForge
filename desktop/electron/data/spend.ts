import fs from 'node:fs'
import type { HarcamaKaydi, HarcamaOzeti, JobKind, KotaBilgisi } from '@shared/types'
import { log } from '../core/logger'
import { veriDosyasi } from '../core/paths'

/**
 * HARCAMA DEFTERI
 * ---------------
 * Bot islerinin Modal GPU maliyetini kalici olarak saklar. Boylece Panel'de
 * "bu ay ne harcadim" gorulebilir ve yeni bir is icin tahmin verilebilir.
 * Botun kendi dosyalarina DOKUNMAZ; yalnizca arayuz tarafinda bir defter tutar.
 */
interface Defter {
  kayitlar: HarcamaKaydi[]
  /** Kota sayaci icin: hangi gun ve kac AI cagrisi */
  aiGun: string
  aiSayi: number
}

const MAKS_KAYIT = 500

let cache: Defter | null = null

function dosya(): string {
  return veriDosyasi('harcama.json')
}

function yukle(): Defter {
  if (cache) return cache
  try {
    const raw = fs.readFileSync(dosya(), 'utf8')
    const parsed = JSON.parse(raw) as Partial<Defter>
    cache = {
      kayitlar: Array.isArray(parsed.kayitlar) ? (parsed.kayitlar as HarcamaKaydi[]) : [],
      aiGun: typeof parsed.aiGun === 'string' ? parsed.aiGun : '',
      aiSayi: Number.isFinite(parsed.aiSayi) ? Number(parsed.aiSayi) : 0,
    }
  } catch {
    cache = { kayitlar: [], aiGun: '', aiSayi: 0 }
  }
  return cache
}

function kaydet(): void {
  try {
    const d = yukle()
    if (d.kayitlar.length > MAKS_KAYIT) d.kayitlar = d.kayitlar.slice(-MAKS_KAYIT)
    fs.writeFileSync(dosya(), JSON.stringify(d, null, 2), 'utf8')
  } catch (err) {
    log.warn('harcama defteri yazilamadi:', err)
  }
}

/** "$0.0123" / "0.0123 USD" / "0,0123" gibi metinden sayi cikarir. */
export function maliyetSayisi(metin: string | null | undefined): number {
  if (!metin) return 0
  const temiz = String(metin).replace(',', '.').replace(/[^0-9.]/g, ' ')
  const eslesme = temiz.match(/\d+(?:\.\d+)?/)
  if (!eslesme) return 0
  const deger = Number(eslesme[0])
  return Number.isFinite(deger) ? deger : 0
}

export function harcamaEkle(kayit: HarcamaKaydi): void {
  const d = yukle()
  d.kayitlar.push(kayit)
  kaydet()
}

/** Gun degistiyse kota sayacini sifirlar ve sayaci arttirir. */
export function aiCagrisiEkle(adet: number): void {
  if (adet <= 0) return
  const d = yukle()
  const bugun = yerelGun()
  if (d.aiGun !== bugun) {
    d.aiGun = bugun
    d.aiSayi = 0
  }
  d.aiSayi += adet
  kaydet()
}

function yerelGun(t: number = Date.now()): string {
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function harcamaOzeti(): HarcamaOzeti {
  const d = yukle()
  const simdi = new Date()
  const ay = simdi.getMonth()
  const yil = simdi.getFullYear()
  let ayUsd = 0
  let bugunUsd = 0
  let isSayisi = 0
  const gunluk = new Map<string, number>()
  const trToplam = new Map<JobKind, { toplam: number; adet: number }>()
  const bugun = yerelGun()

  for (const k of d.kayitlar) {
    const t = new Date(k.t)
    const gun = yerelGun(k.t)
    if (t.getMonth() === ay && t.getFullYear() === yil) {
      ayUsd += k.usd
      isSayisi += 1
      gunluk.set(gun, (gunluk.get(gun) ?? 0) + k.usd)
    }
    if (gun === bugun) bugunUsd += k.usd
    const acc = trToplam.get(k.kind) ?? { toplam: 0, adet: 0 }
    acc.toplam += k.usd
    acc.adet += 1
    trToplam.set(k.kind, acc)
  }

  const gunler = [...gunluk.entries()]
    .map(([g, u]) => ({ gun: g, usd: Number(u.toFixed(4)) }))
    .sort((a, b) => a.gun.localeCompare(b.gun))
    .slice(-30)

  const ortalama: Record<string, number> = {}
  for (const [kind, acc] of trToplam) {
    if (acc.adet >= 1) ortalama[kind] = Number((acc.toplam / acc.adet).toFixed(4))
  }

  return {
    ok: true,
    ayUsd: Number(ayUsd.toFixed(4)),
    bugunUsd: Number(bugunUsd.toFixed(4)),
    isSayisi,
    gunler,
    son: [...d.kayitlar].slice(-12).reverse(),
    ortalama,
  }
}

/** Pasifik saat dilimindeki tarih (kota sifirlanmasi bu saatte olur). */
function pasifikGun(t: number): string {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Los_Angeles',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date(t))
  } catch {
    return yerelGun(t)
  }
}

/** Kotanin sifirlanacagi an: bir sonraki Pasifik gece yarisi (epoch ms). */
function pasifikSifirlanma(simdi: number = Date.now()): number {
  const bugun = pasifikGun(simdi)
  for (let saat = 1; saat <= 26; saat++) {
    const t = simdi + saat * 3600_000
    if (pasifikGun(t) !== bugun) return t
  }
  return simdi + 86_400_000
}

export function kotaBilgisi(limitler: number[], modeller: string[]): KotaBilgisi {
  const d = yukle()
  const bugun = yerelGun()
  if (d.aiGun !== bugun) {
    d.aiGun = bugun
    d.aiSayi = 0
    kaydet()
  }
  return {
    ok: true,
    tarih: bugun,
    aiCagrisi: d.aiSayi,
    sifirlanmaMs: pasifikSifirlanma(),
    limitler,
    modeller,
  }
}
