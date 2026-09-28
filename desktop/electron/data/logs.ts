import fs from 'node:fs'
import path from 'node:path'
import type { WeeklyPlanItem } from '@shared/types'
import { botPath, logPath } from '../core/paths'
import { getSettings } from '../core/settings'

export interface WeeklyData {
  ok: boolean
  plan: WeeklyPlanItem[]
  results: { channel: string; items: WeeklyPlanItem[] }[]
  error?: string
}

/** haftalik_plan.json + haftalik_sonuc_ch*.json dosyalarini okur. */
export function weeklyData(): WeeklyData {
  const root = botPath(getSettings().videoForgePath)
  const out: WeeklyData = { ok: true, plan: [], results: [] }
  try {
    const planFile = path.join(root, 'haftalik_plan.json')
    if (fs.existsSync(planFile)) {
      const parsed = JSON.parse(fs.readFileSync(planFile, 'utf8'))
      out.plan = Array.isArray(parsed) ? parsed : (parsed.videolar ?? parsed.plan ?? [])
    }
  } catch (err) {
    out.ok = false
    out.error = `Plan okunamadi: ${String(err)}`
  }
  try {
    for (const file of fs.readdirSync(root)) {
      const m = file.match(/^haftalik_sonuc_ch(\d+)\.json$/i)
      if (!m) continue
      const parsed = JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'))
      const items = Array.isArray(parsed) ? parsed : (parsed.sonuclar ?? parsed.videolar ?? [])
      out.results.push({ channel: m[1], items })
    }
  } catch (err) {
    out.ok = false
    out.error = `${out.error ? `${out.error} | ` : ''}Sonuc dosyalari okunamadi: ${String(err)}`
  }
  return out
}

export interface LogRead {
  ok: boolean
  path: string
  size: number
  mtime: number
  lines: string[]
  totalLines: number
  error?: string
}

/** bot_log.txt son N satirini dondurur. */
export function readBotLog(tail = 800, query = ''): LogRead {
  const file = logPath(botPath(getSettings().videoForgePath))
  const base: LogRead = { ok: false, path: file, size: 0, mtime: 0, lines: [], totalLines: 0 }
  try {
    const st = fs.statSync(file)
    const raw = fs.readFileSync(file, 'utf8')
    const all = raw.split(/\r?\n/)
    const filtered = query.trim()
      ? all.filter((l) => l.toLowerCase().includes(query.trim().toLowerCase()))
      : all
    const limit = Math.max(50, Math.min(5000, tail))
    return {
      ok: true,
      path: file,
      size: st.size,
      mtime: st.mtimeMs,
      lines: filtered.slice(-limit),
      totalLines: all.length,
    }
  } catch (err) {
    return { ...base, error: String(err) }
  }
}
