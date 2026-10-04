import { spawn, type ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { STAGES, channelById } from '@shared/channels'
import { GUN_SAYISI_VARSAYILAN, IPC, MAX_LOG_LINES, normalGunSayisi } from '@shared/constants'
import type { Artifact, JobRequest, JobState, LogLevel, RunHistoryItem } from '@shared/types'
import { broadcast } from '../core/events'
import { log } from '../core/logger'
import { botPath, desktopDir, ensureDir, planPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { gecmisListesi, gecmiseEkle } from '../core/history'
import { bildir } from '../core/notify'
import { aiCagrisiEkle, harcamaEkle, maliyetSayisi } from '../data/spend'
import { scanArtifactsSince } from '../data/reports'
import { resolvePython } from './locate'
import { parseLine } from './parser'
import type { JobStep } from './types'

let current: JobState | null = null
let child: ChildProcess | null = null
let cancelled = false
let lineCounter = 0

/** Gemini/AI cagrisi sayaci (kota gostergesi icin islenirken sayilir). */
let aiSayaci = 0

/** Is bitiminde tetiklenen kancalar (kuyruk bu kancayi kullanir). */
type JobEndCallback = (state: JobState) => void
const endListeners = new Set<JobEndCallback>()

export function onJobEnd(cb: JobEndCallback): () => void {
  endListeners.add(cb)
  return () => endListeners.delete(cb)
}

/**
 * DURDURMA (Stop) ALTYAPISI
 * -------------------------
 * Eski kod sadece `current.pid`'yi `taskkill /T /F` ile olduruyordu. O pid
 * coktan olmusse (py launcher gibi ara surec) ya da islem agaci tam
 * kapanmazsa `runStep` hic cozulmuyor, is sonsuza kadar "calisiyor" kaliyordu
 * — kullanici "durdur diyorum durmuyor" diyordu. Artik:
 *   1) is boyunca spawn edilen TUM pid'ler takip edilir ve agaclari oldurulur,
 *   2) kapanmayan pid'ler icin artan baskili tekrar denenir,
 *   3) bot tarafi icin iptal isaret dosyasi yazilir (gun aralarinda temiz durur),
 *   4) 8 sn icinde kapanmazsa arayuz serbest birakilir (asla sonsuza kalmaz).
 */
const trackedPids = new Set<number>()
let killCurrentStep: (() => void) | null = null
let cancelFile: string | null = null
let cancelWatchdog: NodeJS.Timeout | null = null

function taskkill(pid: number): void {
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    } else {
      try {
        process.kill(-pid, 'SIGKILL')
      } catch {
        process.kill(pid, 'SIGKILL')
      }
    }
  } catch {
    /* yoksay */
  }
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function writeCancelSentinel(): void {
  if (!cancelFile) return
  try {
    fs.writeFileSync(cancelFile, String(Date.now()), 'utf8')
  } catch {
    /* yoksay */
  }
}

function clearCancelSentinel(): void {
  if (cancelWatchdog) {
    clearTimeout(cancelWatchdog)
    cancelWatchdog = null
  }
  if (cancelFile) {
    try {
      fs.rmSync(cancelFile, { force: true })
    } catch {
      /* yoksay */
    }
  }
}

function emptyStats(): JobState['stats'] {
  return { gpu: null, cost: null, duration: null, gemini: null, chunks: null }
}

/** Renderer'a log satirlarini gonderdigi icin state kopyasinda satirlar yok. */
function snapshot(state: JobState): Omit<JobState, 'lines'> & { lineCount: number } {
  const { lines, ...rest } = state
  return { ...rest, lineCount: lines.length }
}

function emitState(): void {
  if (!current) return
  broadcast(IPC.runEvent, { type: 'state', state: snapshot(current) })
}

function push(level: LogLevel, text: string, stage?: string, artifactName?: string): void {
  if (!current) return
  const line = { i: ++lineCounter, t: Date.now(), level, text }
  if (level === 'ai') aiSayaci += 1
  current.lines.push(line)
  if (current.lines.length > MAX_LOG_LINES) current.lines.splice(0, current.lines.length - MAX_LOG_LINES)
  broadcast(IPC.runEvent, { type: 'line', line })
  if (stage) setStage(stage)
  if (artifactName) addArtifactByName(artifactName)
}

function setStage(stageKey: string): void {
  if (!current) return
  const idx = current.stages.findIndex((s) => s.key === stageKey)
  if (idx >= 0 && idx !== current.stageIndex) {
    current.stageIndex = idx
    current.stepLabel = current.stages[idx].label
    emitState()
  }
}

function addArtifactByName(name: string): void {
  if (!current) return
  if (current.artifacts.some((a) => a.name === name)) return
  const found = scanArtifactsSince(0).find((a) => a.name === name)
  const artifact: Artifact = found ?? {
    kind: 'other',
    name,
    path: path.join(desktopDir, name),
    size: 0,
    mtime: Date.now(),
  }
  current.artifacts.push(artifact)
  emitState()
}

function mergeStats(patch: Partial<JobState['stats']>): void {
  if (!current) return
  current.stats = { ...current.stats, ...patch }
  emitState()
}

/** Is req'ini gercek bot komutlarina cevirir (smoke testinde dogrulanir). */
export function buildSteps(req: JobRequest, base: string[]): { steps: JobStep[]; title: string; subtitle: string } {
  const b = botPath(getSettings().videoForgePath)
  switch (req.kind) {
    case 'channel': {
      const ch = channelById(req.channelId || '1')
      const script = ch?.script || 'kinosekrety.py'
      const args = [...base, '-m', 'modal', 'run', script]
      if (req.link) args.push('--link', req.link)
      if (req.force) args.push('--force')
      if (req.gun && req.gun > 0) {
        args.push('--gun', String(req.gun), '--gun-toplam', String(req.gunToplam || req.gunSayisi || GUN_SAYISI_VARSAYILAN))
      }
      return {
        steps: [{ label: `${ch?.name ?? 'Kanal'} işleniyor`, cmd: args }],
        title: ch ? `${ch.name} - ${ch.niche}` : 'Kanal işlemi',
        subtitle: req.link ? req.link : script,
      }
    }
    case 'discover': {
      const gun = normalGunSayisi(req.gunSayisi)
      const planMode = Boolean(req.haftalik) || gun > GUN_SAYISI_VARSAYILAN
      const args = [...base, 'kesif.py', '--chn', req.channelId || '1', '--evet']
      if (planMode) args.push('--haftalik', String(gun))
      return {
        steps: [{ label: 'Keşif (video önerisi)', cmd: args }],
        title: 'Keşif - Kanal Analizi',
        subtitle: planMode ? `${gun} günlük plan` : 'Tek seferlik öneri',
      }
    }
    case 'weekly': {
      const gun = normalGunSayisi(req.gunSayisi)
      const chn = req.channelId || '1'
      const ch = channelById(chn)
      const kesifArgs = [...base, 'kesif.py', '--haftalik', String(gun), '--chn', chn, '--evet']
      const isletArgs = [...base, 'haftalik_islet.py', '--evet']
      // Bozuk/eksik kalan gunleri yeniden uret: DB kaydi silinip gun bastan islenir.
      const yeniden = (req.yenidenGun ?? '').trim()
      if (yeniden) isletArgs.push('--yeniden-gun', yeniden)
      return {
        steps: [
          { label: `1. Keşif - ${gun} video bulunuyor`, cmd: kesifArgs },
          {
            label: '2. Temizle + SEO + ses zinciri',
            cmd: isletArgs,
            continueWhen: () => fs.existsSync(planPath(b)),
          },
        ],
        title: `${gun} Günlük Zincir - ${ch?.name ?? chn}`,
        subtitle: 'Keşif -> temizle -> SEO -> ses',
      }
    }
    case 'clean': {
      const args = [...base, '-m', 'modal', 'run', 'temizle.py']
      if (req.link) args.push('--link', req.link)
      return {
        steps: [{ label: 'Video temizleme (ProPainter)', cmd: args }],
        title: 'Video Temizleyici',
        subtitle: req.link || '',
      }
    }
  }
}

function runStep(step: JobStep, cwd: string): Promise<number> {
  return new Promise<number>((resolve) => {
    push('step', step.label, undefined)
    let buffer = ''
    let settled = false

    /** Surec kapanmasa bile dongunun tikanmamasini garantiler (durdurma yolu). */
    const finish = (code: number): void => {
      if (settled) return
      settled = true
      killCurrentStep = null
      resolve(code)
    }

    let proc: ChildProcess
    try {
      proc = spawn(step.cmd[0], step.cmd.slice(1), {
        cwd,
        windowsHide: true,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1',
          PYTHONIOENCODING: 'utf-8',
          PYTHONUTF8: '1',
          // Bot gun aralarinda bu dosyayi kontrol eder -> temiz durus.
          ...(cancelFile ? { VIDEOFORGE_CANCEL_FILE: cancelFile } : {}),
        },
      })
    } catch (err) {
      push('err', `Komut başlatılamadı: ${String(err)}`)
      finish(1)
      return
    }

    child = proc
    killCurrentStep = () => finish(130)
    if (proc.pid) trackedPids.add(proc.pid)
    if (current) {
      current.pid = proc.pid ?? null
      emitState()
    }

    const handleChunk = (data: Buffer): void => {
      buffer += data.toString('utf8')
      const parts = buffer.split(/\r?\n|\r/)
      buffer = parts.pop() ?? ''
      for (const raw of parts) {
        const parsed = parseLine(raw)
        if (!parsed.text) continue
        push(parsed.level, parsed.text, parsed.stage, parsed.artifact?.name)
        if (parsed.stats) mergeStats(parsed.stats)
      }
    }

    proc.stdout?.on('data', handleChunk)
    proc.stderr?.on('data', handleChunk)

    proc.on('error', (err) => {
      if (settled) return
      if (proc.pid) trackedPids.delete(proc.pid)
      push('err', `Surec hatasi: ${err.message}`)
      child = null
      finish(1)
    })

    proc.on('close', (code) => {
      if (settled) return
      if (proc.pid) trackedPids.delete(proc.pid)
      if (buffer.trim()) {
        const parsed = parseLine(buffer)
        if (parsed.text) push(parsed.level, parsed.text, parsed.stage)
      }
      child = null
      finish(code ?? 0)
    })
  })
}

export function getState(): JobState | null {
  return current
}

export function getHistory(): RunHistoryItem[] {
  return gecmisListesi()
}

export function isRunning(): boolean {
  return Boolean(current && current.status === 'running')
}

export async function startJob(req: JobRequest): Promise<{ ok: boolean; error?: string }> {
  if (isRunning()) return { ok: false, error: 'Zaten çalışan bir iş var. Önce onu durdurun.' }

  const settings = getSettings()
  const b = botPath(settings.videoForgePath)
  if (!b || !fs.existsSync(b)) {
    return { ok: false, error: `VideoForge klasörü bulunamadı: ${b}` }
  }
  if (!fs.existsSync(path.join(b, 'shared.py'))) {
    return { ok: false, error: `${b} bir VideoForge klasörü gibi görünmüyor (shared.py yok).` }
  }
  if (req.kind === 'channel' || req.kind === 'clean') {
    if (!req.link || !/^https?:\/\//i.test(req.link)) {
      return { ok: false, error: 'Geçerli bir video linki girin (http/https).' }
    }
  }

  const py = await resolvePython()
  if (!py.ok || !py.python) {
    return { ok: false, error: 'Python bulunamadı. Ayarlar > Python yolu bölümünden belirtin.' }
  }

  const base = [py.python.command, ...py.python.args, '-X', 'utf8']
  const built = buildSteps(req, base)
  const stages = STAGES[req.kind]

  cancelled = false
  aiSayaci = 0
  trackedPids.clear()
  killCurrentStep = null
  clearCancelSentinel()
  cancelFile = path.join(os.tmpdir(), `videoforge-cancel-${randomUUID()}.flag`)
  current = {
    id: randomUUID(),
    kind: req.kind,
    title: built.title,
    subtitle: built.subtitle,
    status: 'running',
    stages,
    stageIndex: 0,
    stepLabel: stages[0]?.label ?? 'Basliyor',
    startedAt: Date.now(),
    endedAt: null,
    exitCode: null,
    pid: null,
    lines: [],
    artifacts: [],
    stats: emptyStats(),
    error: null,
  }

  const jobStarted = Date.now()
  broadcast(IPC.runEvent, { type: 'start', state: snapshot(current), req })
  log.info('iş başlatıldı:', built.title, '| komut:', built.steps.map((s) => s.cmd.join(' ')).join(' && '))

  void (async () => {
    let lastCode = 0
    try {
      for (const step of built.steps) {
        if (cancelled) break
        lastCode = await runStep(step, b)
        if (cancelled) break
        if (lastCode !== 0) {
          push('err', `Adım başarısız oldu (çıkış kodu ${lastCode}): ${step.label}`)
          break
        }
        if (step.continueWhen && !step.continueWhen()) {
          push('warn', 'Sonraki adım için gerekli dosya oluşmadı (örn. haftalik_plan.json), zincir durduruldu.')
          break
        }
      }
    } catch (err) {
      push('err', `Beklenmeyen hata: ${String(err)}`)
      lastCode = 1
    }

    if (!current) return
    // Cikti dosyalarini yeniden tara (islem sirasinda uretilenler)
    const found = scanArtifactsSince(jobStarted - 5000)
    for (const a of found) {
      if (!current.artifacts.some((x) => x.name === a.name)) current.artifacts.push(a)
    }
    current.exitCode = lastCode
    current.endedAt = Date.now()
    current.pid = null
    current.error = cancelled ? null : lastCode === 0 ? null : `Çıkış kodu ${lastCode}`
    current.status = cancelled ? 'cancelled' : lastCode === 0 ? 'done' : 'error'
    if (current.artifacts.length) current.stageIndex = current.stages.length - 1
    const sureMs = current.endedAt && current.startedAt ? current.endedAt - current.startedAt : null
    gecmiseEkle({
      id: current.id,
      kind: current.kind,
      title: current.title,
      status: current.status,
      startedAt: current.startedAt,
      endedAt: current.endedAt,
      exitCode: current.exitCode,
      cost: current.stats.cost,
      durationMs: sureMs,
      artifacts: current.artifacts,
    })
    // Maliyet defteri + gunluk AI kotasi sayaci (Panel ve kota gostergesi kullanir).
    const usd = maliyetSayisi(current.stats.cost)
    if (usd > 0) {
      harcamaEkle({
        t: current.endedAt ?? Date.now(),
        baslik: current.title,
        kind: current.kind,
        usd,
        saniye: sureMs ? Math.round(sureMs / 1000) : null,
      })
    }
    if (aiSayaci > 0) aiCagrisiEkle(aiSayaci)
    push(
      current.status === 'done' ? 'ok' : current.status === 'cancelled' ? 'warn' : 'err',
      current.status === 'done'
        ? `İşlem tamamlandı. ${current.artifacts.length} çıktı dosyası bulundu.`
        : current.status === 'cancelled'
          ? 'İşlem kullanıcı tarafından durduruldu.'
          : 'İşlem hatalarla bitti. Logları kontrol edin.',
    )
    emitState()
    broadcast(IPC.runEvent, { type: 'end', state: snapshot(current) })
    const biten = current
    clearCancelSentinel()

    const folders = new Set(biten.artifacts.map((a) => path.dirname(a.path)))
    for (const folder of folders) {
      try {
        ensureDir(folder)
      } catch {
        /* yoksay */
      }
    }

    // Bildirim: is bitince masaustu bildirimi (Ayarlar'dan kapatilabilir).
    const ozet =
      biten.status === 'done'
        ? `${biten.artifacts.length} çıktı dosyası hazır${biten.stats.cost ? ` · ${biten.stats.cost}` : ''}`
        : biten.status === 'cancelled'
          ? 'İşlem durduruldu'
          : 'İşlem hatalarla bitti'
    bildir(biten.title, ozet)

    // Kuyruk kancalari: siradaki bekleyen is burada (en sonda) baslatilir; boylece
    // yeni isin iptal dosyasi eski isin temizligiyle karismaz.
    for (const cb of endListeners) {
      try {
        cb(biten)
      } catch (err) {
        log.warn('is bitis kancasi hatasi:', err)
      }
    }
  })()

  return { ok: true }
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

/**
 * Islemleri durdurur: once bot tarafina iptal isareti, sonra TUM surec
 * agaclarini oldurur, kapanmayanlar icin artan baskili tekrar dener ve
 * 8 sn icinde kapanmazsa arayuzu serbest birakir (asla sonsuza kadar
 * "calisiyor" kalmaz). Renderer bunu bekleyebilsin diye Promise doner.
 */
export async function cancelJob(): Promise<boolean> {
  if (!current || current.status !== 'running') return false
  cancelled = true
  push('warn', 'Durdurma isteği gönderildi...')

  // 1) Bot tarafi: haftalik zincir gun aralarinda bu dosyayi gorup temiz durur.
  writeCancelSentinel()

  // 2) Bu is boyunca spawn edilen TUM pid'ler (sadece sonuncu degil).
  const pids = new Set<number>(trackedPids)
  if (current.pid) pids.add(current.pid)

  if (!pids.size) {
    push('warn', 'Durdurulacak canlı süreç bulunamadı, işlem kapatılıyor.')
    killCurrentStep?.()
    return true
  }

  for (const pid of pids) taskkill(pid)

  // 3) Artan baski: once kisa bekle, hala yasayanlari zorla kapat.
  await sleep(1500)
  const kalan = [...pids].filter(isAlive)
  for (const pid of kalan) taskkill(pid)
  if (kalan.length) push('warn', `Kapanmayan ${kalan.length} süreç için zorla kapatma tekrarlandı...`)

  if (child) {
    try {
      child.kill()
    } catch {
      /* yoksay */
    }
  }

  // 4) Son guvenlik agi: 8 sn icinde kapanmazsa UI'yi serbest birak.
  if (cancelWatchdog) clearTimeout(cancelWatchdog)
  cancelWatchdog = setTimeout(() => {
    cancelWatchdog = null
    if (current && current.status === 'running') {
      push('warn', 'Süreç ağacı 8 saniyede kapanmadı - arayüz serbest bırakılıyor (arka planda kalıntı olabilir).')
      killCurrentStep?.()
    }
  }, 8000)

  return true
}
