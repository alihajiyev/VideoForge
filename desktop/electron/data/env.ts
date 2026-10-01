import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { EnvCheck } from '@shared/types'
import { execCapture } from '../core/exec'
import { botPath, cookiesPath, dbPath, logPath, requiredBotFiles } from '../core/paths'
import { getSettings } from '../core/settings'
import { resolvePython } from '../python/locate'

async function hasBinary(name: string): Promise<{ ok: boolean; detail: string }> {
  const res = await execCapture(name, ['-version'], { timeoutMs: 10_000 })
  if (res.code === 0 || res.code === 1) {
    const out = `${res.stdout}${res.stderr}`.trim().split('\n')[0]
    return { ok: true, detail: out.slice(0, 80) || name }
  }
  return { ok: false, detail: res.error ?? `çıkış kodu ${res.code}` }
}

async function pythonHas(module: string, command: string, args: string[]): Promise<{ ok: boolean; detail: string }> {
  const res = await execCapture(
    command,
    [...args, '-c', `import ${module} as m; print(getattr(m, '__version__', 'yuklu'))`],
    { timeoutMs: 40_000 },
  )
  if (res.code === 0) return { ok: true, detail: res.stdout.trim().slice(0, 60) || 'yüklü' }
  return { ok: false, detail: (res.stderr || 'import edilemedi').trim().split('\n').pop()?.slice(0, 120) || 'import edilemedi' }
}

/**
 * Ortamin botu calistirmaya hazir olup olmadigini kontrol eder.
 * Python paket kontrolleri PARALEL calisir (eskiden sirayla 4+ saniye suruyordu).
 */
export async function envCheck(): Promise<EnvCheck[]> {
  const root = botPath(getSettings().videoForgePath)
  const checks: EnvCheck[] = []

  const py = await resolvePython(true)
  checks.push({
    id: 'python',
    label: 'Python 3.10+',
    ok: py.ok,
    detail: py.python ? `${py.python.label}${py.python.detail ? ` (${py.python.detail})` : ''}` : 'Bulunamadı',
    fix: py.ok ? undefined : 'Python kurun veya Ayarlar > Python yolu alanına tam yolu yazın.',
  })

  const files = requiredBotFiles(root)
  const missing = files.filter((f) => !f.ok).map((f) => f.name)
  checks.push({
    id: 'botfiles',
    label: 'VideoForge dosyaları',
    ok: missing.length === 0,
    detail: missing.length ? `Eksik: ${missing.join(', ')}` : `${root} (${files.length} dosya doğrulandı)`,
    fix: missing.length ? 'Ayarlar > VideoForge klasörü yolunu düzeltin.' : undefined,
  })

  const cmd = py.python?.command ?? 'python'
  const args = py.python?.args ?? []

  const [modal, genai, el, ytdlp, ffmpeg, ffprobe] = await Promise.all([
    pythonHas('modal', cmd, args),
    pythonHas('google.genai', cmd, args),
    pythonHas('elevenlabs', cmd, args),
    pythonHas('yt_dlp', cmd, args),
    hasBinary('ffmpeg'),
    hasBinary('ffprobe'),
  ])

  checks.push({
    id: 'modal',
    label: 'modal paketi',
    ok: modal.ok,
    detail: modal.detail,
    fix: modal.ok ? undefined : `Kurulum: ${root}> python -m pip install -r requirements.txt`,
  })
  checks.push({
    id: 'genai',
    label: 'google-genai',
    ok: genai.ok,
    detail: genai.detail,
    fix: genai.ok ? undefined : 'python -m pip install google-genai==2.24.0',
  })
  checks.push({
    id: 'elevenlabs',
    label: 'elevenlabs',
    ok: el.ok,
    detail: el.detail,
    fix: el.ok ? undefined : 'python -m pip install elevenlabs',
  })
  checks.push({
    id: 'ytdlp',
    label: 'yt-dlp',
    ok: ytdlp.ok,
    detail: ytdlp.detail,
    fix: ytdlp.ok ? undefined : 'python -m pip install -U yt-dlp',
  })
  checks.push({
    id: 'ffmpeg',
    label: 'ffmpeg',
    ok: ffmpeg.ok,
    detail: ffmpeg.detail,
    fix: ffmpeg.ok ? undefined : 'ffmpeg kurun ve PATH değişkenine ekleyin (ses/video işleme için zorunlu).',
  })
  checks.push({
    id: 'ffprobe',
    label: 'ffprobe',
    ok: ffprobe.ok,
    detail: ffprobe.detail,
    fix: ffprobe.ok ? undefined : 'ffprobe ffmpeg paketi ile birlikte gelir.',
  })

  const cookies = cookiesPath(root)
  let cookieOk = false
  let cookieDetail = 'cookies.txt yok'
  try {
    const st = fs.statSync(cookies)
    cookieOk = st.size > 100
    const days = Math.floor((Date.now() - st.mtimeMs) / 86400000)
    cookieDetail = `${(st.size / 1024).toFixed(1)} KB, ${days} gün önce güncellendi`
    if (days > 30) cookieDetail += ' - eski olabilir, yenileyin'
  } catch {
    cookieOk = false
  }
  checks.push({
    id: 'cookies',
    label: 'cookies.txt (YouTube oturumu)',
    ok: cookieOk,
    detail: cookieDetail,
    fix: cookieOk ? undefined : 'Tarayıcıdan YouTube cookies.txt export edip VideoForge klasörüne koyun.',
  })

  const modalToken = path.join(os.homedir(), '.modal.toml')
  checks.push({
    id: 'modaltoken',
    label: 'Modal oturumu',
    ok: fs.existsSync(modalToken),
    detail: fs.existsSync(modalToken) ? 'Giriş yapılmış (.modal.toml)' : '.modal.toml yok',
    fix: fs.existsSync(modalToken) ? undefined : 'VideoForge klasöründe: python -m modal setup',
  })

  const db = dbPath(root)
  checks.push({
    id: 'db',
    label: 'bot.db (işlem geçmişi)',
    ok: fs.existsSync(db),
    detail: fs.existsSync(db) ? 'Mevcut' : 'Yok (ilk çalışmada oluşur)',
  })

  const lg = logPath(root)
  checks.push({
    id: 'log',
    label: 'bot_log.txt',
    ok: fs.existsSync(lg),
    detail: fs.existsSync(lg) ? 'Mevcut' : 'Yok (ilk çalışmada oluşur)',
  })

  return checks
}
