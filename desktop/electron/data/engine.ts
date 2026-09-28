import fs from 'node:fs'
import path from 'node:path'
import type { EngineConfig } from '@shared/types'
import { execCapture } from '../core/exec'
import { botPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { resolvePython } from '../python/locate'
import { readLibrary } from './library'

function readIfExists(p: string): string {
  try {
    return fs.readFileSync(p, 'utf8')
  } catch {
    return ''
  }
}

function num(src: string, name: string): number | null {
  const m = src.match(new RegExp(`${name}\\s*=\\s*(-?[0-9.]+)`))
  return m ? Number(m[1]) : null
}

function boolVal(src: string, name: string): boolean {
  const m = src.match(new RegExp(`${name}\\s*=\\s*(True|False)`))
  return m ? m[1] === 'True' : false
}

/** constants.py + bot.db'den motor konfigurasyonunu okur (import etmeden, yan etkisiz). */
export async function engineConfig(): Promise<EngineConfig> {
  const root = botPath(getSettings().videoForgePath)
  const constants = readIfExists(path.join(root, 'constants.py'))
  const base: EngineConfig = {
    ok: false,
    models: [],
    elevenlabs: false,
    hdMode: false,
    procW: 540,
    procH: 960,
    gpu: 'L4',
    costPerSec: 0.000222,
    charLimit: 500,
    charLimitSujet: 570,
    maxConcurrentGpus: 10,
    overheadSeconds: 75,
    smartTextFilter: false,
  }
  if (!constants) return { ...base, error: `constants.py okunamadi: ${root}` }

  const modelBlock = constants.match(/GEMINI_MODELS\s*=\s*\[([\s\S]*?)\]/)
  const models = modelBlock ? [...modelBlock[1].matchAll(/["']([^"']+)["']/g)].map((m) => m[1]) : []

  const hd = boolVal(constants, 'HD_MODE')
  const settingsBlock = constants.match(/SETTINGS\s*=\s*\{([^}]*)\}/)
  const elevenlabs = settingsBlock ? /ELEVENLABS_ENABLED["']?\s*:\s*True/.test(settingsBlock[1]) : false

  const db = await readLibrary()
  const charLimit = Number(db.settings?.char_limit || 500)

  return {
    ok: true,
    models,
    elevenlabs,
    hdMode: hd,
    procW: hd ? 640 : 540,
    procH: hd ? 1136 : 960,
    gpu: hd ? 'L40S' : 'L4',
    costPerSec: hd ? 0.000542 : 0.000222,
    charLimit: Number.isFinite(charLimit) ? charLimit : 500,
    charLimitSujet: num(constants, 'CHAR_LIMIT_KINO_SYJET') ?? 570,
    maxConcurrentGpus: num(constants, 'MAX_CONCURRENT_GPUS') ?? 10,
    overheadSeconds: num(constants, 'OVERHEAD_SECONDS') ?? 75,
    smartTextFilter: boolVal(constants, 'SMART_TEXT_FILTER'),
  }
}

/** bot.db settings tablosuna char_limit yazar (bot ayni degeri okur). */
export async function setCharLimit(value: number): Promise<{ ok: boolean; error?: string }> {
  const v = Math.max(200, Math.min(3000, Math.round(value)))
  const root = botPath(getSettings().videoForgePath)
  const file = path.join(root, 'bot.db')
  if (!fs.existsSync(file)) return { ok: false, error: 'bot.db yok' }

  const py = await resolvePython()
  if (!py.ok || !py.python) return { ok: false, error: 'Python bulunamadi' }

  const script =
    'import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);' +
    'c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)");' +
    "c.execute(\"INSERT OR REPLACE INTO settings (key,value) VALUES ('char_limit',?)\",(sys.argv[2],));c.commit();" +
    'print("ok")'
  const res = await execCapture(py.python.command, [...py.python.args, '-c', script, file, String(v)], {
    timeoutMs: 15_000,
  })
  if (res.code !== 0) return { ok: false, error: (res.stderr || res.error || 'yazilamadi').slice(-300) }
  return { ok: true }
}
