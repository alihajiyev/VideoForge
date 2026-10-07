import { protocol } from 'electron'
import fs from 'node:fs'
import path from 'node:path'
import { Readable } from 'node:stream'
import { botPath, desktopDir } from './paths'
import { getSettings } from './settings'

/**
 * YEREL VIDEO OYNATMA PROTOKOLU (vfil://)
 *
 * Uretilen klipler Masaustu/Klipler altinda duruyor. Renderer'da <video src>
 * ile oynatmak icin dosya yolunu dogrudan vermek CSP'ye takilir ve tum diski
 * acar. Bunun yerine kendi protokolumuzu kaydedip SADECE izinli klasorlerden
 * (Masaustu + VideoForge) ve Range isteklerini destekleyerek servis ediyoruz.
 * Boylece kaydirma (seek) da sorunsuz calisir.
 *
 * URL bicimi:  vfil://yerel/<encodeURIComponent(tamYol)>
 */
export const VIDEO_SCHEME = 'vfil'

const MIME: Record<string, string> = {
  '.mp4': 'video/mp4',
  '.m4v': 'video/mp4',
  '.webm': 'video/webm',
  '.mkv': 'video/x-matroska',
  '.mov': 'video/quicktime',
  '.srt': 'text/plain; charset=utf-8',
  '.vtt': 'text/vtt; charset=utf-8',
}

/** Dosya yolu guvenli mi? (yalnizca Masaustu ve VideoForge klasoru) */
export function videoYoluIzinli(hedef: string): boolean {
  try {
    const resolved = path.resolve(hedef)
    const root = botPath(getSettings().videoForgePath)
    const izinli = [desktopDir, root].map((p) => path.resolve(p).toLowerCase())
    const alt = resolved.toLowerCase()
    return izinli.some((a) => alt === a || alt.startsWith(a + path.sep))
  } catch {
    return false
  }
}

/** Uygulama hazir olmadan ONCE cagrilmali (yetki kaydi). */
export function videoSemasiniKaydet(): void {
  try {
    protocol.registerSchemesAsPrivileged([
      {
        scheme: VIDEO_SCHEME,
        privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true, bypassCSP: false },
      },
    ])
  } catch {
    /* zaten kayitli */
  }
}

function yanit(durum: number, metin: string): Response {
  return new Response(metin, { status: durum, headers: { 'Content-Type': 'text/plain; charset=utf-8' } })
}

/** app.whenReady() icinde cagrilir. */
export function videoProtokolunuKaydet(): void {
  try {
    protocol.handle(VIDEO_SCHEME, (istek) => {
      try {
        const url = new URL(istek.url)
        const ham = decodeURIComponent(url.pathname.replace(/^\//, ''))
        if (!ham) return yanit(400, 'yol yok')
        const dosya = path.resolve(ham)
        if (!videoYoluIzinli(dosya)) return yanit(403, 'izin yok')
        let boyut = 0
        try {
          const st = fs.statSync(dosya)
          if (!st.isFile()) return yanit(404, 'dosya degil')
          boyut = st.size
        } catch {
          return yanit(404, 'dosya yok')
        }
        const tip = MIME[path.extname(dosya).toLowerCase()] || 'application/octet-stream'
        const range = istek.headers.get('range') || istek.headers.get('Range')
        if (range) {
          const m = /bytes=(\d*)-(\d*)/.exec(range)
          let bas = m && m[1] ? Number(m[1]) : 0
          let son = m && m[2] ? Number(m[2]) : boyut - 1
          if (!Number.isFinite(bas) || bas < 0) bas = 0
          if (!Number.isFinite(son) || son >= boyut) son = boyut - 1
          if (son < bas) return yanit(416, 'gecersiz aralik')
          const akis = fs.createReadStream(dosya, { start: bas, end: son })
          return new Response(Readable.toWeb(akis) as ReadableStream, {
            status: 206,
            headers: {
              'Content-Type': tip,
              'Content-Length': String(son - bas + 1),
              'Content-Range': `bytes ${bas}-${son}/${boyut}`,
              'Accept-Ranges': 'bytes',
              'Cache-Control': 'no-store',
            },
          })
        }
        const akis = fs.createReadStream(dosya)
        return new Response(Readable.toWeb(akis) as ReadableStream, {
          status: 200,
          headers: {
            'Content-Type': tip,
            'Content-Length': String(boyut),
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-store',
          },
        })
      } catch (err) {
        return yanit(500, String(err))
      }
    })
  } catch {
    /* zaten kayitli */
  }
}
