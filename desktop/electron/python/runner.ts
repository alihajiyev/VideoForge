import { spawn, type ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { STAGES, channelById } from '@shared/channels'
import { IPC, MAX_LOG_LINES } from '@shared/constants'
import type { Artifact, JobRequest, JobState, LogLevel, RunHistoryItem } from '@shared/types'
import { broadcast } from '../core/events'
import { log } from '../core/logger'
import { botPath, desktopDir, ensureDir, planPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { scanArtifactsSince } from '../data/reports'
import { resolvePython } from './locate'
import { parseLine } from './parser'
import type { JobStep } from './types'

let current: JobState | null = null
let child: ChildProcess | null = null
let cancelled = false
let lineCounter = 0
const history: RunHistoryItem[] = []

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
      if (req.gun && req.gun > 0) args.push('--gun', String(req.gun), '--gun-toplam', String(req.gunToplam || 7))
      return {
        steps: [{ label: `${ch?.name ?? 'Kanal'} isleniyor`, cmd: args }],
        title: ch ? `${ch.name} - ${ch.niche}` : 'Kanal islemi',
        subtitle: req.link ? req.link : script,
      }
    }
    case 'discover': {
      const args = [...base, 'kesif.py', '--chn', req.channelId || '1', '--evet']
      if (req.haftalik) args.push('--haftalik')
      return {
        steps: [{ label: 'Kesif (video onerisi)', cmd: args }],
        title: 'Kesif - Kanal Analizi',
        subtitle: req.haftalik ? 'Haftalik mod: 7 video' : 'Tek seferlik oneri',
      }
    }
    case 'weekly': {
      const chn = req.channelId || '1'
      const ch = channelById(chn)
      const kesifArgs = [...base, 'kesif.py', '--haftalik', '--chn', chn, '--evet']
      const isletArgs = [...base, 'haftalik_islet.py', '--evet']
      return {
        steps: [
          { label: '1. Kesif - 7 video bulunuyor', cmd: kesifArgs },
          {
            label: '2. Temizle + SEO + ses zinciri',
            cmd: isletArgs,
            continueWhen: () => fs.existsSync(planPath(b)),
          },
        ],
        title: `Haftalik Zincir - ${ch?.name ?? chn}`,
        subtitle: 'Kesif -> temizle -> SEO -> ses',
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
        },
      })
    } catch (err) {
      push('err', `Komut baslatilamadi: ${String(err)}`)
      resolve(1)
      return
    }

    child = proc
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
      settled = true
      push('err', `Surec hatasi: ${err.message}`)
      child = null
      resolve(1)
    })

    proc.on('close', (code) => {
      if (settled) return
      settled = true
      if (buffer.trim()) {
        const parsed = parseLine(buffer)
        if (parsed.text) push(parsed.level, parsed.text, parsed.stage)
      }
      child = null
      resolve(code ?? 0)
    })
  })
}

export function getState(): JobState | null {
  return current
}

export function getHistory(): RunHistoryItem[] {
  return history.slice(0, 30)
}

export function isRunning(): boolean {
  return Boolean(current && current.status === 'running')
}

export async function startJob(req: JobRequest): Promise<{ ok: boolean; error?: string }> {
  if (isRunning()) return { ok: false, error: 'Zaten calisan bir is var. Once onu durdurun.' }

  const settings = getSettings()
  const b = botPath(settings.videoForgePath)
  if (!b || !fs.existsSync(b)) {
    return { ok: false, error: `VideoForge klasoru bulunamadi: ${b}` }
  }
  if (!fs.existsSync(path.join(b, 'shared.py'))) {
    return { ok: false, error: `${b} bir VideoForge klasoru gibi gorunmuyor (shared.py yok).` }
  }
  if (req.kind === 'channel' || req.kind === 'clean') {
    if (!req.link || !/^https?:\/\//i.test(req.link)) {
      return { ok: false, error: 'Gecerli bir video linki girin (http/https).' }
    }
  }

  const py = await resolvePython()
  if (!py.ok || !py.python) {
    return { ok: false, error: 'Python bulunamadi. Ayarlar > Python yolu bolumunden belirtin.' }
  }

  const base = [py.python.command, ...py.python.args, '-X', 'utf8']
  const built = buildSteps(req, base)
  const stages = STAGES[req.kind]

  cancelled = false
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
  log.info('is baslatildi:', built.title, '| komut:', built.steps.map((s) => s.cmd.join(' ')).join(' && '))

  void (async () => {
    let lastCode = 0
    try {
      for (const step of built.steps) {
        if (cancelled) break
        lastCode = await runStep(step, b)
        if (cancelled) break
        if (lastCode !== 0) {
          push('err', `Adim basarisiz oldu (cikis kodu ${lastCode}): ${step.label}`)
          break
        }
        if (step.continueWhen && !step.continueWhen()) {
          push('warn', 'Sonraki adim icin gerekli dosya olusmadi (orn. haftalik_plan.json), zincir durduruldu.')
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
    current.error = cancelled ? null : lastCode === 0 ? null : `Cikis kodu ${lastCode}`
    current.status = cancelled ? 'cancelled' : lastCode === 0 ? 'done' : 'error'
    if (current.artifacts.length) current.stageIndex = current.stages.length - 1
    history.unshift({
      id: current.id,
      kind: current.kind,
      title: current.title,
      status: current.status,
      startedAt: current.startedAt,
      endedAt: current.endedAt,
      exitCode: current.exitCode,
    })
    if (history.length > 30) history.pop()
    push(
      current.status === 'done' ? 'ok' : current.status === 'cancelled' ? 'warn' : 'err',
      current.status === 'done'
        ? `Islem tamamlandi. ${current.artifacts.length} cikti dosyasi bulundu.`
        : current.status === 'cancelled'
          ? 'Islem kullanici tarafindan durduruldu.'
          : 'Islem hatalarla bitti. Loglari kontrol edin.',
    )
    emitState()
    broadcast(IPC.runEvent, { type: 'end', state: snapshot(current) })

    const folders = new Set(current.artifacts.map((a) => path.dirname(a.path)))
    for (const folder of folders) {
      try {
        ensureDir(folder)
      } catch {
        /* yoksay */
      }
    }
  })()

  return { ok: true }
}

export function cancelJob(): boolean {
  if (!current || current.status !== 'running') return false
  cancelled = true
  const pid = current.pid
  push('warn', 'Durdurma istegi gonderildi...')
  if (pid) {
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true })
      } else {
        try {
          process.kill(-pid, 'SIGTERM')
        } catch {
          process.kill(pid, 'SIGTERM')
        }
      }
    } catch (err) {
      push('warn', `Surec durdurulamadi: ${String(err)}`)
    }
  }
  if (child) {
    try {
      child.kill()
    } catch {
      /* yoksay */
    }
  }
  return true
}
