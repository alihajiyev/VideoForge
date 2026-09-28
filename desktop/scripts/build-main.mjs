/**
 * Ana surec (main + preload) derlemesi - esbuild.
 * Uretimde minify; dev'de izlenebilir.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as esbuild from 'esbuild'

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const watch = process.argv.includes('--watch')
const production = !watch

/** @type {import('esbuild').BuildOptions} */
const common = {
  bundle: true,
  platform: 'node',
  target: 'node22',
  format: 'cjs',
  sourcemap: false,
  minify: production,
  legalComments: 'none',
  charset: 'utf8',
  drop: production ? ['debugger'] : [],
  logLevel: 'info',
  external: ['electron'],
  alias: {
    '@shared': path.join(root, 'shared'),
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(production ? 'production' : 'development'),
  },
}

const targets = [
  {
    ...common,
    entryPoints: [path.join(root, 'electron/main.ts')],
    outfile: path.join(root, 'dist-electron/main.cjs'),
  },
  {
    ...common,
    entryPoints: [path.join(root, 'electron/preload.ts')],
    outfile: path.join(root, 'dist-electron/preload.cjs'),
  },
]

if (watch) {
  const contexts = await Promise.all(targets.map((t) => esbuild.context(t)))
  await Promise.all(contexts.map((c) => c.watch()))
  console.log('[build-main] watching electron sources...')
} else {
  for (const t of targets) await esbuild.build(t)
  console.log('[build-main] main + preload derlendi')
}
