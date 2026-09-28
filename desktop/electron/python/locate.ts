import { execCapture } from '../core/exec'
import type { PythonCommand } from './types'
import { getSettings } from '../core/settings'
import { log } from '../core/logger'

const PROBE_ARGS = ['-c', 'import sys; print(sys.version_info[0], sys.version_info[1])']

const CANDIDATES: PythonCommand[] = [
  { command: 'py', args: ['-3'], label: 'py -3 (Windows Launcher)' },
  { command: 'python', args: [], label: 'python' },
  { command: 'python3', args: [], label: 'python3' },
]

let cached: PythonCommand | null = null
let cachedTried: { label: string; command: string; detail?: string }[] = []

export interface PythonResolution {
  ok: boolean
  python: PythonCommand | null
  tried: { label: string; command: string; detail?: string }[]
}

async function probe(cmd: PythonCommand): Promise<boolean> {
  const res = await execCapture(cmd.command, [...cmd.args, ...PROBE_ARGS], { timeoutMs: 15_000 })
  if (res.error) {
    cmd.detail = res.error
    return false
  }
  const out = (res.stdout || '').trim()
  const [major, minor] = out.split(/\s+/).map((n) => Number(n))
  if (res.code !== 0 || !Number.isFinite(major)) {
    cmd.detail = (res.stderr || 'surum okunamadi').trim().split('\n').pop()?.slice(0, 120)
    return false
  }
  // Modal / google-genai icin Python 3.10+ gerekir.
  if (major < 3 || (major === 3 && minor < 10)) {
    cmd.detail = `Python ${major}.${minor} bulundu - en az 3.10 gerekli`
    return false
  }
  cmd.detail = `Python ${major}.${minor}`
  return true
}

/** python yorumlayicisini bulur (asenkron - ana surec kilitlenmez). */
export async function resolvePython(force = false): Promise<PythonResolution> {
  if (cached && !force) return { ok: true, python: cached, tried: [] }

  const settings = getSettings()
  const list: PythonCommand[] = []
  if (settings.pythonPath.trim()) {
    const p = settings.pythonPath.trim()
    list.push({ command: p, args: [], label: `ayardan: ${p}` })
  }
  list.push(...CANDIDATES)

  const tried: { label: string; command: string; detail?: string }[] = []
  for (const cmd of list) {
    if (await probe(cmd)) {
      cached = cmd
      cachedTried = tried
      log.info('python bulundu:', cmd.label, cmd.detail)
      return { ok: true, python: cmd, tried }
    }
    tried.push({ label: cmd.label, command: cmd.command, detail: cmd.detail })
  }
  cached = null
  cachedTried = tried
  return { ok: false, python: null, tried: cachedTried }
}

export function cachePython(cmd: PythonCommand | null): void {
  cached = cmd
}
