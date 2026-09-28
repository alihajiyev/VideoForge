import { app } from 'electron'
import fs from 'node:fs'
import path from 'node:path'

let stream: fs.WriteStream | null = null

function file(): fs.WriteStream | null {
  if (stream) return stream
  try {
    const dir = app.getPath('userData')
    fs.mkdirSync(dir, { recursive: true })
    stream = fs.createWriteStream(path.join(dir, 'videoforge-gui.log'), { flags: 'a' })
  } catch {
    stream = null
  }
  return stream
}

function write(level: string, args: unknown[]): void {
  const text = args
    .map((a) => (typeof a === 'string' ? a : (() => { try { return JSON.stringify(a) } catch { return String(a) } })()))
    .join(' ')
  const line = `[${new Date().toISOString()}] ${level} ${text}\n`
  file()?.write(line)
  if (!app.isPackaged) process.stdout.write(line)
}

export const log = {
  info: (...args: unknown[]) => write('INFO ', args),
  warn: (...args: unknown[]) => write('WARN ', args),
  error: (...args: unknown[]) => write('ERROR', args),
}
