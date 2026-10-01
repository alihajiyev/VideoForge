import fs from 'node:fs'
import { randomUUID } from 'node:crypto'
import type { ChannelId, JobKind, JobRequest, KuyrukDurumu, KuyrukOgesi } from '@shared/types'
import { channelById } from '@shared/channels'
import { getSettings } from './settings'
import { log } from './logger'
import { veriDosyasi } from './paths'
import { isRunning, onJobEnd, startJob } from '../python/runner'
import { broadcast } from './events'

/**
 * IS KUYRUGU
 * ----------
 * Kullanici birden cok link yapistirip sirayla islenmesini isteyebilir.
 * Kuyruk kalici (userData/kuyruk.json) oldugu icin uygulama kapansa da
 * bekleyen isler kaybolmaz. Bir is bitince (iptal/hata dahil) ayarlarda
 * "kuyrukAutoStart" acikca siradaki otomatik baslatilir.
 */
const MAKS = 200

let cache: KuyrukOgesi[] | null = null

function dosya(): string {
  return veriDosyasi('kuyruk.json')
}

function yukle(): KuyrukOgesi[] {
  if (cache) return cache
  try {
    const raw = fs.readFileSync(dosya(), 'utf8')
    const parsed = JSON.parse(raw) as KuyrukOgesi[]
    cache = Array.isArray(parsed) ? parsed : []
  } catch {
    cache = []
  }
  return cache
}

function kaydet(): void {
  try {
    fs.writeFileSync(dosya(), JSON.stringify(yukle(), null, 2), 'utf8')
  } catch (err) {
    log.warn('kuyruk yazilamadi:', err)
  }
}

function baslik(kind: JobKind, channelId: ChannelId, link?: string): string {
  const ch = channelById(channelId)
  if ((kind === 'channel' || kind === 'clean') && link) {
    return ch ? `${ch.name} · ${link}` : link
  }
  if (kind === 'discover') return `Keşif · ${ch?.name ?? channelId}`
  if (kind === 'weekly') return `Zincir · ${ch?.name ?? channelId}`
  return ch?.name ?? 'İş'
}

export interface KuyrukGirdi {
  kind: JobKind
  channelId?: ChannelId
  link?: string
  force?: boolean
  haftalik?: boolean
  gunSayisi?: number
}

export function kuyrukListesi(): KuyrukOgesi[] {
  return yukle()
}

/** Bir veya daha fazla girdiyi kuyruga ekler (cok satirli yapistirma icin). */
export function kuyrugaEkle(girdiler: KuyrukGirdi[]): KuyrukOgesi[] {
  const list = yukle()
  for (const g of girdiler) {
    const channelId = (g.channelId ?? '1') as ChannelId
    const kind = g.kind
    if ((kind === 'channel' || kind === 'clean') && !g.link) continue
    list.push({
      id: randomUUID(),
      kind,
      channelId,
      link: g.link,
      force: Boolean(g.force),
      haftalik: Boolean(g.haftalik),
      gunSayisi: g.gunSayisi,
      status: 'bekliyor',
      title: baslik(kind, channelId, g.link),
      addedAt: Date.now(),
      startedAt: null,
      endedAt: null,
    })
  }
  if (list.length > MAKS) list.length = MAKS
  kaydet()
  return list
}

export function kuyruktanCikar(id: string): KuyrukOgesi[] {
  cache = yukle().filter((o) => o.id !== id)
  kaydet()
  return cache
}

export function kuyruguTemizle(): KuyrukOgesi[] {
  cache = yukle().filter((o) => o.status === 'calisiyor')
  kaydet()
  return cache
}

export function kuyruguBildir(id: string, durum: KuyrukDurumu, at: number): void {
  const list = yukle()
  const oge = list.find((o) => o.id === id)
  if (!oge) return
  oge.status = durum
  if (durum === 'calisiyor') oge.startedAt = at
  else oge.endedAt = at
  kaydet()
}

function istekCevir(oge: KuyrukOgesi): JobRequest {
  return {
    kind: oge.kind,
    channelId: oge.channelId,
    link: oge.link,
    force: oge.force,
    haftalik: oge.haftalik,
    gunSayisi: oge.gunSayisi ?? getSettings().gunSayisi,
  }
}

/** Kuyruktaki siradaki bekleyeni baslatir (calisan is yoksa). */
export async function siradakiniBaslat(): Promise<boolean> {
  if (isRunning()) return false
  const oge = yukle().find((o) => o.status === 'bekliyor')
  if (!oge) return false
  const res = await startJob(istekCevir(oge))
  if (!res.ok) {
    kuyruguBildir(oge.id, 'hata', Date.now())
    log.warn('kuyruk isi baslatilamadi:', res.error)
    return false
  }
  calisanId = oge.id
  kuyruguBildir(oge.id, 'calisiyor', Date.now())
  broadcastKuyruk()
  return true
}

let calisanId: string | null = null

/** Kuyruk degistiginde renderer'a haber ver (canli liste icin). */
function broadcastKuyruk(): void {
  try {
    broadcast('queue:changed', kuyrukListesi())
  } catch {
    /* yoksay */
  }
}

/** Is bitince: calisan ogeyi isaretle ve (ayarliysa) siradakini baslat. */
export function kuyrukBaslat(): void {
  onJobEnd((state) => {
    if (calisanId) {
      const durum: KuyrukDurumu =
        state.status === 'done' ? 'bitti' : state.status === 'cancelled' ? 'iptal' : state.status === 'error' ? 'hata' : 'bekliyor'
      kuyruguBildir(calisanId, durum, Date.now())
      calisanId = null
    }
    broadcastKuyruk()
    if (getSettings().queueAutoStart && !isRunning()) {
      void siradakiniBaslat().then((basladi) => {
        if (!basladi) broadcastKuyruk()
      })
    }
  })
}
