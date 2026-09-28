import { app, shell } from 'electron'
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type { BotGitInfo, DownloadProgress, UpdateAsset, UpdateInfo } from '@shared/types'
import { IPC } from '@shared/constants'
import { execCapture } from '../core/exec'
import { broadcast } from '../core/events'
import { botPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { log } from '../core/logger'

const TIMEOUT_MS = 20_000

function headers(token: string, accept = 'application/vnd.github+json'): Record<string, string> {
  const h: Record<string, string> = {
    accept,
    'user-agent': `VideoForge/${app.getVersion()}`,
    'x-github-api-version': '2022-11-28',
  }
  if (token) h.authorization = `Bearer ${token}`
  return h
}

/** "v1.2.3" -> [1,2,3]; on surum eki (-beta) yok sayilir. */
export function parseVersion(v: string): number[] {
  const clean = (v || '').trim().replace(/^v/i, '').split('-')[0].split('+')[0]
  const parts = clean.split('.').map((p) => Number.parseInt(p, 10))
  while (parts.length < 3) parts.push(0)
  return parts.map((n) => (Number.isFinite(n) ? n : 0))
}

/** a > b ise 1, a < b ise -1, esitse 0. */
export function compareVersions(a: string, b: string): number {
  const va = parseVersion(a)
  const vb = parseVersion(b)
  for (let i = 0; i < Math.max(va.length, vb.length); i++) {
    const x = va[i] ?? 0
    const y = vb[i] ?? 0
    if (x > y) return 1
    if (x < y) return -1
  }
  return 0
}

interface GhRelease {
  tag_name?: string
  name?: string
  body?: string
  html_url?: string
  published_at?: string
  draft?: boolean
  prerelease?: boolean
  assets?: { name?: string; size?: number; browser_download_url?: string; url?: string; content_type?: string }[]
}

/** GitHub'daki en son surumu kontrol eder. */
export async function checkForUpdate(repoOverride?: string, tokenOverride?: string): Promise<UpdateInfo> {
  const settings = getSettings()
  const repo = (repoOverride || settings.updateRepo || '').trim()
  const token = (tokenOverride ?? settings.githubToken ?? '').trim()
  const base: UpdateInfo = {
    ok: false,
    current: app.getVersion(),
    latest: null,
    available: false,
    notes: '',
    publishedAt: null,
    htmlUrl: null,
    assets: [],
    repo,
    checkedAt: Date.now(),
  }
  if (!repo || !/^[\w.-]+\/[\w.-]+$/.test(repo)) {
    return { ...base, error: 'Guncelleme deposu tanimli degil (owner/repo biciminde olmali).' }
  }

  let res: Response
  try {
    res = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
      headers: headers(token),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
  } catch (err) {
    log.warn('guncelleme kontrolu basarisiz:', err)
    return { ...base, error: `GitHub'a ulasilamadi (${String(err).slice(0, 120)}). Internet baglantisini kontrol edin.` }
  }

  if (res.status === 404) {
    return {
      ...base,
      ok: true,
      error: `Yayinlanmis surum bulunamadi (${repo}). Depo private ise Ayarlar'a 'repo' yetkili bir GitHub token girin; surum hic yayinlanmadiysa 'npm run release' ile yayinlayin.`,
    }
  }
  if (res.status === 401 || res.status === 403) {
    return {
      ...base,
      error: `GitHub erisimi reddedildi (${res.status}). Depo private ise Ayarlar'a gecerli bir GitHub token girin ve 'repo' yetkisi verdiginizden emin olun.`,
    }
  }
  if (!res.ok) {
    return { ...base, error: `GitHub hatasi: ${res.status} ${res.statusText}` }
  }

  let release: GhRelease
  try {
    release = (await res.json()) as GhRelease
  } catch {
    return { ...base, error: 'GitHub yaniti okunamadi.' }
  }

  const latest = (release.tag_name || release.name || '').trim()
  if (!latest) return { ...base, error: 'Surum etiketi bulunamadi.' }

  const assets: UpdateAsset[] = (release.assets ?? [])
    .filter((a) => Boolean(a.name))
    .map((a) => ({
      name: String(a.name),
      size: Number(a.size ?? 0),
      // Private depolarda tarayici adresi token istemez ama 404 dondurur;
      // token varsa API adresi kullanilir (Accept: application/octet-stream).
      url: token && a.url ? String(a.url) : String(a.browser_download_url ?? a.url ?? ''),
      isApiUrl: Boolean(token && a.url),
    }))
    .filter((a) => Boolean(a.url))

  return {
    ok: true,
    current: app.getVersion(),
    latest,
    available: compareVersions(latest, app.getVersion()) > 0,
    notes: (release.body || '').trim().slice(0, 4000),
    publishedAt: release.published_at ?? null,
    htmlUrl: release.html_url ?? null,
    assets,
    repo,
    checkedAt: Date.now(),
  }
}

function downloadDir(): string {
  const dir = path.join(app.getPath('userData'), 'updates')
  fs.mkdirSync(dir, { recursive: true })
  return dir
}

/** Surum dosyasini indirir; ilerlemeyi IPC uzerinden yayinlar. */
export async function downloadUpdate(assetName: string): Promise<{ ok: boolean; path?: string; error?: string }> {
  const info = await checkForUpdate()
  if (!info.ok) return { ok: false, error: info.error }
  const asset = info.assets.find((a) => a.name === assetName)
  if (!asset) return { ok: false, error: `Dosya surumde bulunamadi: ${assetName}` }

  const settings = getSettings()
  const token = (settings.githubToken || '').trim()
  const target = path.join(downloadDir(), asset.name)
  const emit = (patch: Partial<DownloadProgress>): void => {
    broadcast(IPC.updateProgress, {
      name: asset.name,
      received: 0,
      total: asset.size,
      pct: 0,
      done: false,
      ...patch,
    } satisfies DownloadProgress)
  }

  emit({})
  try {
    const res = await fetch(asset.url, {
      headers: headers(token, asset.isApiUrl ? 'application/octet-stream' : 'application/octet-stream'),
      signal: AbortSignal.timeout(10 * 60_000),
    })
    if (!res.ok || !res.body) {
      emit({ done: true, error: `Indirme hatasi: ${res.status}` })
      return { ok: false, error: `Indirme hatasi: ${res.status} ${res.statusText}` }
    }
    const total = Number(res.headers.get('content-length') || asset.size || 0)
    const chunks: Buffer[] = []
    let received = 0
    const reader = res.body.getReader()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      if (value) {
        const buf = Buffer.from(value)
        chunks.push(buf)
        received += buf.length
        emit({ received, total, pct: total ? Math.min(100, Math.round((received / total) * 100)) : 0 })
      }
    }
    fs.writeFileSync(target, Buffer.concat(chunks))
    emit({ received, total, pct: 100, done: true, path: target })
    log.info('guncelleme indirildi:', target)
    return { ok: true, path: target }
  } catch (err) {
    const msg = String(err).slice(0, 200)
    emit({ done: true, error: msg })
    return { ok: false, error: msg }
  }
}

/** Indirilen yeni surumu baslatir ve mevcut uygulamadan cikar. */
export function launchDownloaded(filePath: string): { ok: boolean; error?: string } {
  try {
    if (!fs.existsSync(filePath)) return { ok: false, error: 'Indirilen dosya bulunamadi.' }
    const dir = path.resolve(downloadDir()).toLowerCase()
    if (!path.resolve(filePath).toLowerCase().startsWith(dir)) {
      return { ok: false, error: 'Guvenlik: sadece indirilen guncelleme dosyasi baslatilabilir.' }
    }
    if (!/\.(exe|msi)$/i.test(filePath)) return { ok: false, error: 'Desteklenmeyen dosya turu (.exe veya .msi olmali).' }
    spawnDetached(filePath)
    setTimeout(() => app.quit(), 1500)
    return { ok: true }
  } catch (err) {
    return { ok: false, error: String(err) }
  }
}

function spawnDetached(filePath: string): void {
  spawn(filePath, [], { detached: true, stdio: 'ignore', cwd: path.dirname(filePath) }).unref()
}

/* ------------------------------------------------------------------ */
/* Bot kodu (Python) guncellemesi - git                                         */
/* ------------------------------------------------------------------ */

async function git(args: string[], cwd: string): Promise<{ code: number | null; out: string; err: string; error?: string }> {
  const res = await execCapture('git', args, { cwd, timeoutMs: 60_000 })
  return { code: res.code, out: res.stdout.trim(), err: res.stderr.trim(), error: res.error }
}

/** Iki yolu Windows/Linux farkini gozeterek karsilastirir. */
function samePath(a: string, b: string): boolean {
  const norm = (p: string): string => path.resolve(p).replace(/[\\/]+$/, '').replace(/\\/g, '/').toLowerCase()
  return norm(a) === norm(b)
}

/**
 * Bot klasorunun git durumu (dal, son commit, degisiklik, uzak fark).
 *
 * Not: git yukari dogru arar; bot klasoru baska bir deponun icindeyse
 * (ornegin kullanici ana klasoru) toplevel farkli cikar ve isBotRepo false olur.
 * Bu durumda guncelleme yapilmaz - kullanicinin ilgisiz deposu cekilmez.
 */
export async function botGitStatus(opts: { fetch?: boolean } = {}): Promise<BotGitInfo> {
  const cwd = botPath(getSettings().videoForgePath)
  const empty: BotGitInfo = {
    ok: false,
    isRepo: false,
    isBotRepo: false,
    toplevel: null,
    gitAvailable: false,
    branch: null,
    commit: null,
    subject: null,
    dirty: false,
    remote: null,
    behind: null,
    ahead: null,
    changedFiles: [],
  }

  const version = await git(['--version'], cwd)
  if (version.error || version.code !== 0) {
    return { ...empty, error: 'git bulunamadi. Git kurup PATH degiskenine ekleyin.' }
  }

  const inside = await git(['rev-parse', '--is-inside-work-tree'], cwd)
  if (inside.code !== 0 || inside.out !== 'true') {
    return { ...empty, gitAvailable: true, error: `${cwd} bir git deposu degil.` }
  }

  // Uzak depodaki yeni commitleri gormek icin istege bagli fetch (varsayilan: yerel bilgi).
  if (opts.fetch) {
    const fetched = await git(['fetch', '--all', '--prune', '--quiet'], cwd)
    if (fetched.code !== 0) log.warn('git fetch basarisiz (yerel bilgi kullanilacak):', fetched.err.slice(0, 200))
  }

  const [toplevelRes, branchRes, symRes, last, remote, status, counts] = await Promise.all([
    git(['rev-parse', '--show-toplevel'], cwd),
    git(['rev-parse', '--abbrev-ref', 'HEAD'], cwd),
    git(['symbolic-ref', '--short', 'HEAD'], cwd),
    git(['log', '-1', '--pretty=%h%x1f%s'], cwd),
    git(['remote', 'get-url', 'origin'], cwd),
    git(['status', '--porcelain'], cwd),
    git(['rev-list', '--left-right', '--count', 'HEAD...@{upstream}'], cwd),
  ])

  const toplevel = toplevelRes.code === 0 && toplevelRes.out ? path.resolve(toplevelRes.out) : null
  // Ilk commit yoksa 'rev-parse --abbrev-ref HEAD' "HEAD" doner; dal adi symbolic-ref'te bulunur.
  const branchOut = branchRes.code === 0 ? branchRes.out : ''
  const branch =
    branchOut && branchOut !== 'HEAD'
      ? branchOut
      : symRes.code === 0 && symRes.out && symRes.out !== 'HEAD'
        ? symRes.out
        : null

  const [commit, subject] = (last.out || '').split('\x1f')
  const changedFiles = status.out ? status.out.split('\n').filter(Boolean).slice(0, 40) : []
  let behind: number | null = null
  let ahead: number | null = null
  if (counts.code === 0 && counts.out) {
    // 'rev-list --left-right --count HEAD...@{upstream}' -> "<solda kalan>\t<sagda kalan>".
    // Sol taraf HEAD'dir (uzaga gonderilmemis commit = ileride),
    // sag taraf upstream'dir (yerelde olmayan commit = geride).
    const [a, b] = counts.out.split(/\s+/).map((n) => Number(n))
    ahead = Number.isFinite(a) ? a : null
    behind = Number.isFinite(b) ? b : null
  }

  return {
    ok: true,
    isRepo: true,
    isBotRepo: toplevel ? samePath(toplevel, cwd) : true,
    toplevel,
    gitAvailable: true,
    branch,
    commit: commit || null,
    subject: subject || null,
    dirty: changedFiles.length > 0,
    remote: remote.code === 0 ? remote.out : null,
    behind,
    ahead,
    changedFiles,
  }
}

/**
 * Bot kodunu GitHub'dan yeniler (git pull --ff-only).
 * Yerel degisiklik varsa islem reddedilir - kimsenin isi kaybolmaz.
 */
export async function pullBotCode(): Promise<{ ok: boolean; output: string; error?: string; info: BotGitInfo }> {
  const cwd = botPath(getSettings().videoForgePath)
  const before = await botGitStatus()
  if (!before.ok) return { ok: false, output: '', error: before.error, info: before }
  if (!before.isBotRepo) {
    return {
      ok: false,
      output: '',
      error: `Bot klasoru kendi git deposu degil, '${before.toplevel ?? 'baska bir depo'}' deposunun icinde. Guvenlik icin guncelleme yapilmadi - Ayarlar'dan bot klasorunu kendi deposuyla gosterin.`,
      info: before,
    }
  }
  if (before.dirty) {
    return {
      ok: false,
      output: '',
      error: `Yerel degisiklikler var (${before.changedFiles.length} dosya) - cakismayi onlemek icin guncelleme yapilmadi. Once commit edin veya degisiklikleri geri alin.`,
      info: before,
    }
  }

  const fetchRes = await git(['fetch', '--all', '--prune'], cwd)
  if (fetchRes.code !== 0) {
    return { ok: false, output: fetchRes.err || fetchRes.out, error: `git fetch basarisiz: ${fetchRes.err.slice(0, 300)}`, info: before }
  }
  const pullRes = await git(['pull', '--ff-only'], cwd)
  const after = await botGitStatus()
  if (pullRes.code !== 0) {
    return {
      ok: false,
      output: `${fetchRes.out}\n${pullRes.err}`.trim(),
      error: `git pull basarisiz: ${pullRes.err.slice(0, 300)}`,
      info: after,
    }
  }
  log.info('bot kodu guncellendi:', after.commit)
  return { ok: true, output: `${fetchRes.out}\n${pullRes.out}`.trim(), info: after }
}

/** Surum sayfasini tarayicida acar. */
export async function openReleasePage(info: { htmlUrl?: string | null; repo?: string | null }): Promise<{ ok: boolean; error?: string }> {
  const repo = (info.repo || getSettings().updateRepo || '').trim()
  const url = info.htmlUrl || (repo ? `https://github.com/${repo}/releases` : '')
  if (!url) return { ok: false, error: 'Surum adresi bilinmiyor.' }
  try {
    await shell.openExternal(url)
    return { ok: true }
  } catch (err) {
    return { ok: false, error: String(err) }
  }
}
