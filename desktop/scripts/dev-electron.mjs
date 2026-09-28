/**
 * Dev runner: main/preload derler, Vite dev sunucusunu bekler, Electron'u baslatir.
 * main/preload kaynaklari degisince Electron'u yeniden baslatir.
 * Not: wait-on paketine bagimlilik YOK - hafif fetch polling kullanilir.
 */
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as esbuild from 'esbuild'

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const DEV_URL = 'http://127.0.0.1:5212'

const common = {
  bundle: true,
  platform: 'node',
  target: 'node22',
  format: 'cjs',
  sourcemap: false,
  logLevel: 'warning',
  external: ['electron'],
  alias: { '@shared': path.join(root, 'shared') },
  define: { 'process.env.NODE_ENV': JSON.stringify('development') },
}

const targets = [
  { ...common, entryPoints: [path.join(root, 'electron/main.ts')], outfile: path.join(root, 'dist-electron/main.cjs') },
  { ...common, entryPoints: [path.join(root, 'electron/preload.ts')], outfile: path.join(root, 'dist-electron/preload.cjs') },
]

let child = null

function startElectron() {
  if (child) {
    child.removeAllListeners('exit')
    child.kill()
    child = null
  }
  const electronBin = path.join(root, 'node_modules', 'electron', 'cli.js')
  child = spawn(process.execPath, [electronBin, '.'], {
    cwd: root,
    stdio: 'inherit',
    env: { ...process.env, NODE_ENV: 'development', VITE_DEV_SERVER_URL: DEV_URL },
  })
  child.on('exit', (code) => {
    if (code !== null && code !== 0) console.error(`[dev] electron exited with code ${code}`)
  })
}

let restarting = false
async function rebuildAndRestart() {
  if (restarting) return
  restarting = true
  try {
    for (const t of targets) await esbuild.build(t)
    console.log('[dev] main process rebuilt - restarting electron')
    startElectron()
  } catch (err) {
    console.error('[dev] build failed:', err.message)
  } finally {
    setTimeout(() => { restarting = false }, 200)
  }
}

async function waitForDevServer(url, timeoutMs = 90_000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      /* sunucu henuz hazir degil */
    }
    await new Promise((r) => setTimeout(r, 400))
  }
  throw new Error(`Vite dev server did not start within ${timeoutMs / 1000}s: ${url}`)
}

console.log('[dev] waiting for vite dev server...')
await waitForDevServer(DEV_URL)
console.log('[dev] building electron main process...')
for (const t of targets) await esbuild.build(t)
startElectron()

const contexts = await Promise.all(
  targets.map((t) => esbuild.context({ ...t, plugins: [{ name: 'notify', setup(build) { build.onEnd((r) => { if (!r.errors.length && child) rebuildAndRestart() }) } }] })),
)
await Promise.all(contexts.map((c) => c.watch()))

process.on('SIGINT', () => { child?.kill(); process.exit(0) })
