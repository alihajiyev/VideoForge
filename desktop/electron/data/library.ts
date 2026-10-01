import fs from 'node:fs'
import type { LibraryData } from '@shared/types'
import { execCapture } from '../core/exec'
import { botPath, dbPath } from '../core/paths'
import { getSettings } from '../core/settings'
import { resolvePython } from '../python/locate'
import { log } from '../core/logger'

/** Python stdlib sqlite3 ile bot.db'yi okur (better-sqlite3 gibi yerel modul gerekmez). */
const READ_SCRIPT = `
import json, sqlite3, sys
db = sys.argv[1]
out = {"ok": True, "videos": [], "oneriler": [], "settings": {}, "counts": {"videos": 0, "oneriler": 0}}
try:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    def rows(sql):
        try:
            return [dict(r) for r in conn.execute(sql).fetchall()]
        except Exception:
            return []
    out["videos"] = rows("SELECT id, link, COALESCE(created_at, '') AS created_at FROM videos ORDER BY id DESC LIMIT 2000")
    out["oneriler"] = [
        {
            "video_id": r.get("video_id", ""),
            "skor": float(r.get("skor") or 0),
            "tip": r.get("tip") or "",
            "kanal": str(r.get("kanal") or "1"),
            "tarih": str(r.get("tarih") or ""),
        }
        for r in rows("SELECT video_id, skor, tip, kanal, tarih FROM oneriler ORDER BY tarih DESC LIMIT 2000")
    ]
    out["settings"] = {r["key"]: str(r["value"]) for r in rows("SELECT key, value FROM settings")}
    out["counts"] = {"videos": len(out["videos"]), "oneriler": len(out["oneriler"])}
    conn.close()
except Exception as e:
    out["ok"] = False
    out["error"] = str(e)
print(json.dumps(out, ensure_ascii=False))
`

const FORGET_SCRIPT = `
import sqlite3, sys, json
db, link = sys.argv[1], sys.argv[2]
try:
    conn = sqlite3.connect(db)
    cur = conn.execute("DELETE FROM videos WHERE link = ? OR link LIKE ?", (link, "%" + link + "%"))
    conn.commit()
    print(json.dumps({"ok": True, "deleted": cur.rowcount}))
    conn.close()
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
`

async function runPython(script: string, args: string[], timeoutMs = 25_000): Promise<{ ok: boolean; out: string; err?: string }> {
  const py = await resolvePython()
  if (!py.ok || !py.python) return { ok: false, out: '', err: 'Python bulunamadı' }
  const res = await execCapture(py.python.command, [...py.python.args, '-X', 'utf8', '-c', script, ...args], {
    timeoutMs,
    cwd: botPath(getSettings().videoForgePath),
  })
  if (res.error) return { ok: false, out: '', err: res.error }
  if (res.code !== 0) return { ok: false, out: res.stdout, err: (res.stderr || '').slice(-600) }
  return { ok: true, out: res.stdout }
}

export async function readLibrary(): Promise<LibraryData> {
  const empty: LibraryData = {
    ok: false,
    videos: [],
    oneriler: [],
    settings: {},
    counts: { videos: 0, oneriler: 0 },
  }
  const db = dbPath(botPath(getSettings().videoForgePath))
  if (!fs.existsSync(db)) return { ...empty, error: `bot.db bulunamadı: ${db}` }
  const res = await runPython(READ_SCRIPT, [db])
  if (!res.ok) return { ...empty, error: res.err || 'bot.db okunamadi' }
  const line = res.out.trim().split('\n').pop() || '{}'
  try {
    const parsed = JSON.parse(line) as LibraryData
    return { ...empty, ...parsed }
  } catch (err) {
    log.warn('library parse hatasi:', err)
    return { ...empty, error: 'bot.db çıktısı çözülemedi' }
  }
}

export async function forgetLink(link: string): Promise<{ ok: boolean; deleted?: number; error?: string }> {
  const clean = (link || '').trim()
  if (!clean) return { ok: false, error: 'Bos link' }
  const db = dbPath(botPath(getSettings().videoForgePath))
  const res = await runPython(FORGET_SCRIPT, [db, clean], 15_000)
  if (!res.ok) return { ok: false, error: res.err || 'Silinemedi' }
  try {
    return JSON.parse(res.out.trim().split('\n').pop() || '{}') as { ok: boolean; deleted: number }
  } catch {
    return { ok: false, error: 'Çıktı çözülemedi' }
  }
}
