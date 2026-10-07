import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const root = path.resolve(import.meta.dirname)

/** Dev sunumunda CSP'yi HMR icin gevseten eklenti (uretim CSP'si index.html'de). */
function devCspPlugin() {
  return {
    name: 'vf-dev-csp',
    apply: 'serve' as const,
    transformIndexHtml(html: string): string {
      const DEV_CSP = [
        "default-src 'none'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' vfil:",
        "font-src 'self' data:",
        "connect-src 'self' http://127.0.0.1:5212 ws://127.0.0.1:5212",
        "form-action 'none'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-src 'none'",
      ].join('; ')
      return html.replace(
        /(<meta\s+http-equiv="Content-Security-Policy"\s+content=")[^"]*(")/s,
        `$1${DEV_CSP}$2`,
      )
    },
  }
}

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss(), devCspPlugin()],
  resolve: {
    alias: {
      '@': path.join(root, 'src'),
      '@shared': path.join(root, 'shared'),
    },
  },
  server: {
    port: 5212,
    strictPort: true,
    host: '127.0.0.1',
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'chrome132',
    sourcemap: false,
    minify: 'esbuild',
  },
})
