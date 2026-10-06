import fs from 'node:fs'
import path from 'node:path'
import { KLIP_KLASOR } from '@shared/constants'
import type { Artifact, ArtifactKind, ReportPreview } from '@shared/types'
import { desktopDir } from '../core/paths'

const PATTERNS: { re: RegExp; kind: ArtifactKind }[] = [
  { re: /_CLEAN\.mp4$/i, kind: 'video' },
  { re: /_VOICEOVER\.mp3$/i, kind: 'audio' },
  { re: /_SEO\.html$/i, kind: 'seo' },
  { re: /_THUMB\.png$/i, kind: 'thumb' },
  { re: /^Kesif-Rapor.*\.html$/i, kind: 'report' },
  { re: /_final\.mp4$/i, kind: 'video' },
  { re: /^final_.*\.mp4$/i, kind: 'video' },
  { re: /^klip_\d+.*\.mp4$/i, kind: 'video' },
]

export function classify(name: string): ArtifactKind | null {
  for (const p of PATTERNS) if (p.re.test(name)) return p.kind
  return null
}

function candidateDirs(kok: string = desktopDir): string[] {
  const dirs = [kok]
  try {
    for (const entry of fs.readdirSync(kok, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue
      if (/^Gun\d+_/i.test(entry.name) || /^Gun\d+/i.test(entry.name)) dirs.push(path.join(kok, entry.name))
      // KLIPCI ciktilari: Masaustu/Klipler/<video adi>/*.mp4
      if (entry.name === KLIP_KLASOR) {
        const klipKok = path.join(kok, entry.name)
        dirs.push(klipKok)
        try {
          for (const alt of fs.readdirSync(klipKok, { withFileTypes: true })) {
            if (alt.isDirectory()) dirs.push(path.join(klipKok, alt.name))
          }
        } catch {
          /* Klipler okunamadi */
        }
      }
    }
  } catch {
    /* Desktop okunamadi */
  }
  return dirs
}

function collect(dirs: string[], sinceMs: number | null, limit: number): Artifact[] {
  const out: Artifact[] = []
  for (const dir of dirs) {
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      if (!entry.isFile()) continue
      const kind = classify(entry.name)
      if (!kind) continue
      const full = path.join(dir, entry.name)
      try {
        const st = fs.statSync(full)
        if (sinceMs !== null && st.mtimeMs < sinceMs) continue
        out.push({ kind, name: entry.name, path: full, size: st.size, mtime: st.mtimeMs })
      } catch {
        /* atla */
      }
    }
  }
  out.sort((a, b) => b.mtime - a.mtime)
  return out.slice(0, limit)
}

/** Belirli bir zamandan sonra uretilen cikti dosyalari (is bitince kullanilir). */
export function scanArtifactsSince(sinceMs: number, kok?: string): Artifact[] {
  return collect(candidateDirs(kok), sinceMs, 200)
}

/** Tum uretilmis cikti dosyalari (kutuphane ekrani). `kok` testler icin gecersiz kilinabilir. */
export function listArtifacts(kok?: string): Artifact[] {
  return collect(candidateDirs(kok), null, 600)
}

export interface ReportGroup {
  key: string
  dir: string
  title: string
  items: Artifact[]
  totalBytes: number
  mtime: number
}

function stripSuffix(name: string): string {
  return name
    .replace(/_(CLEAN|VOICEOVER|SEO|THUMB)\.[^.]+$/i, '')
    .replace(/\.(mp4|mp3|html|png)$/i, '')
    .replace(/_\d{3}$/, '')
    .replace(/_/g, ' ')
    .trim()
}

/** Sadece 'final_123456.mp4' (montaj cikti adi) — kardes dosyalarla ayni grup. */
const FINAL_ONLY_RE = /^final_\d+\.mp4$/i

/**
 * Tek asamali cikti: final artik GunN klasorunun ICINE yazilir (kopya yok).
 * Bu yuzden 'final_*.mp4' kendi adiyla ayri grup olmamali; klasordeki
 * video+ses+kapak+SEO ile TEK sonuc olarak gruplanmali. Her klasor icin
 * baskin kok ad (stem) bir kez hesaplanir.
 */
function dirStemMap(items: Artifact[]): Map<string, string> {
  const sayac = new Map<string, Map<string, number>>()
  for (const it of items) {
    if (FINAL_ONLY_RE.test(it.name)) continue
    const dir = path.dirname(it.path)
    const s = stripSuffix(it.name)
    if (!s) continue
    const m = sayac.get(dir) ?? new Map<string, number>()
    m.set(s, (m.get(s) ?? 0) + 1)
    sayac.set(dir, m)
  }
  const out = new Map<string, string>()
  for (const [dir, m] of sayac) {
    let enIyi = ''
    let enCok = 0
    for (const [s, n] of m) {
      if (n > enCok || (n === enCok && enIyi && s < enIyi)) {
        enIyi = s
        enCok = n
      }
    }
    if (enIyi) out.set(dir, enIyi)
  }
  return out
}

/** Ayni videoya ait ciktilari (video + ses + kapak + SEO) gruplar. */
export function groupArtifacts(items: Artifact[]): ReportGroup[] {
  const map = new Map<string, ReportGroup>()
  const dirStem = dirStemMap(items)
  for (const item of items) {
    const dir = path.dirname(item.path)
    // final_*.mp4: ayni klasordeki (GunN) diger ciktilarla ayni grupta gorunsun.
    const stem = FINAL_ONLY_RE.test(item.name) && dirStem.get(dir)
      ? dirStem.get(dir)!
      : stripSuffix(item.name)
    const key = `${dir}::${stem}`
    let group = map.get(key)
    if (!group) {
      group = { key, dir, title: stem || item.name, items: [], totalBytes: 0, mtime: 0 }
      map.set(key, group)
    }
    group.items.push(item)
    group.totalBytes += item.size
    group.mtime = Math.max(group.mtime, item.mtime)
  }
  const groups = [...map.values()]
  groups.sort((a, b) => b.mtime - a.mtime)
  for (const g of groups) {
    g.items.sort((a, b) => a.kind.localeCompare(b.kind))
  }
  return groups
}

function decodeEntities(s: string): string {
  return s
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}

function htmlToText(html: string): string {
  return decodeEntities(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(div|p|li|tr|h[1-6])>/gi, '\n')
      .replace(/<[^>]+>/g, ' '),
  )
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{2,}/g, '\n')
    .trim()
}

/**
 * SEO raporu onizlemesi. Rapor yapisi: <div class="card"><div class="label">Baslik</div>...
 * Bolumleri "label -> icerik" olarak ayiklar (h1/h2 kullanilmiyor).
 */
export function previewHtml(filePath: string): ReportPreview {
  try {
    const raw = fs.readFileSync(filePath, 'utf8')
    const title = decodeEntities((raw.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] || '').trim())
    const sections: { label: string; text: string }[] = []

    // Her <div class="label">X</div> sonrasi icerik, bir sonraki label'a kadar.
    const re = /<div class="label">([\s\S]*?)<\/div>([\s\S]*?)(?=<div class="label">|<\/body>|$)/gi
    for (const m of raw.matchAll(re)) {
      const label = htmlToText(m[1]).replace(/\s+/g, ' ').trim()
      const body = htmlToText(m[2]).slice(0, 900)
      if (label || body) sections.push({ label: label || 'Bolum', text: body })
    }

    // Yedek: h1/h2 varsa (kesif raporu) onlari da baslik olarak al
    const headings = [...raw.matchAll(/<h[12][^>]*>([\s\S]*?)<\/h[12]>/gi)]
      .map((m) => htmlToText(m[1]).replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 12)

    const text = htmlToText(raw).slice(0, 4000)
    return { ok: true, title, headings, sections, text }
  } catch (err) {
    return { ok: false, error: String(err) }
  }
}
