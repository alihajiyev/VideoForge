/**
 * Smoke testi derlemesi: smoke/*.ts -> dist-smoke/*.cjs
 * Electron ana surec baglaminda calisir (gercek modulleri test eder).
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as esbuild from 'esbuild'

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)))

await esbuild.build({
  entryPoints: [path.join(root, 'smoke/smoke.ts'), path.join(root, 'smoke/klip_page_check.ts')],
  outdir: path.join(root, 'dist-smoke'),
  outExtension: { '.js': '.cjs' },
  bundle: true,
  platform: 'node',
  target: 'node22',
  format: 'cjs',
  sourcemap: false,
  logLevel: 'info',
  external: ['electron'],
  charset: 'utf8',
  alias: { '@shared': path.join(root, 'shared') },
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
})
console.log('[build-smoke] smoke testleri derlendi')
