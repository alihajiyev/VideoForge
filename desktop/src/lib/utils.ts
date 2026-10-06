export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value >= 100 || i === 0 ? Math.round(value) : value.toFixed(1)} ${units[i]}`
}

/** Yerel bir dosya yolunu <img src> icin guvenli file:// URL'sine cevirir. */
export function fileUrl(p: string): string {
  const normalized = p.replace(/\\/g, '/')
  const segments = normalized.split('/').map((s, i) => (i === 0 ? s : encodeURIComponent(s)))
  return `file:///${segments.join('/')}`
}

/** Botun maliyet metnini ("$0.012") sayiya cevirir; yoksa null. */
export function maliyetUsd(metin: string | null | undefined): number | null {
  if (!metin) return null
  const eslesme = String(metin).replace(',', '.').match(/\d+(?:\.\d+)?/)
  if (!eslesme) return null
  const deger = Number(eslesme[0])
  return Number.isFinite(deger) ? deger : null
}

export function formatUsd(value: number | null | undefined): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  if (n === 0) return '$0'
  if (n < 0.01) return `$${n.toFixed(4)}`
  return `$${n.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** Kalan sureyi "3sa 12dk" / "12dk" biciminde yazar (0 veya negatifte "şimdi"). */
export function formatKalan(ms: number): string {
  const kalan = Math.max(0, ms)
  const dakika = Math.floor(kalan / 60000)
  if (dakika <= 0) return 'şimdi'
  const saat = Math.floor(dakika / 60)
  if (saat > 0) return `${saat}sa ${dakika % 60}dk`
  return `${dakika}dk`
}

export function formatDateTime(ms: number | string | null | undefined): string {
  if (!ms) return '—'
  const d = typeof ms === 'string' ? new Date(ms.replace(' ', 'T')) : new Date(ms)
  if (Number.isNaN(d.getTime())) return String(ms)
  return d.toLocaleString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function formatClock(ms: number | null | undefined): string {
  if (!ms) return '--:--:--'
  return new Date(ms).toLocaleTimeString('tr-TR', { hour12: false })
}

export function formatRelative(ms: number | null | undefined): string {
  if (!ms) return '—'
  const diff = Date.now() - ms
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'az önce'
  if (mins < 60) return `${mins} dk önce`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} saat önce`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} gün önce`
  return formatDateTime(ms)
}

export function formatDuration(startMs: number | null, endMs: number | null): string {
  if (!startMs) return '—'
  const end = endMs ?? Date.now()
  const sec = Math.max(0, Math.round((end - startMs) / 1000))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}sa ${m}dk`
  if (m > 0) return `${m}dk ${s}sn`
  return `${s}sn`
}

export const ARTIFACT_LABEL: Record<string, string> = {
  video: 'Temiz video',
  audio: 'Seslendirme',
  seo: 'SEO raporu',
  thumb: 'Kapak',
  report: 'Keşif raporu',
  plan: 'Çok günlü plan',
  other: 'Dosya',
}

export const KIND_LABEL: Record<string, string> = {
  channel: 'Kanal işlemi',
  discover: 'Keşif',
  weekly: 'Çok günlü zincir',
  clean: 'Temizleme',
  klip: 'Klip Stüdyo',
}
