import type { LogLevel } from './types'

/** IPC kanal isimleri - tek yerde tanimli, hem main hem preload kullanir. */
export const IPC = {
  appInfo: 'app:info',
  envCheck: 'env:check',
  settingsGet: 'settings:get',
  settingsSet: 'settings:set',
  themeSet: 'theme:set',
  runStart: 'run:start',
  runCancel: 'run:cancel',
  runState: 'run:state',
  runHistory: 'run:history',
  runEvent: 'run:event',
  libraryList: 'library:list',
  libraryForget: 'library:forget',
  reportsList: 'reports:list',
  reportsPreview: 'reports:preview',
  weeklyPlan: 'weekly:plan',
  engineConfig: 'engine:config',
  engineSetCharLimit: 'engine:setCharLimit',
  logsRead: 'logs:read',
  updateCheck: 'update:check',
  updateDownload: 'update:download',
  updateLaunch: 'update:launch',
  updateOpenRelease: 'update:openRelease',
  updateProgress: 'update:progress',
  botGitStatus: 'botgit:status',
  botGitPull: 'botgit:pull',
  winMinimize: 'win:minimize',
  winMaximize: 'win:maximize',
  winClose: 'win:close',
  winState: 'win:state',
  winStateChanged: 'win:stateChanged',
  shellOpen: 'shell:open',
  shellReveal: 'shell:reveal',
  shellOpenExternal: 'shell:openExternal',
} as const

/** Botun ui.py ciktilarindaki seviye ikonlari. */
export const LEVEL_ICON: Record<LogLevel, string> = {
  info: '›',
  ok: '✓',
  warn: '!',
  err: '✕',
  step: '#',
  ai: 'AI',
  gpu: 'GPU',
  tts: 'TTS',
  raw: ' ',
}

export const LEVEL_LABEL: Record<LogLevel, string> = {
  info: 'Bilgi',
  ok: 'Basarili',
  warn: 'Uyari',
  err: 'Hata',
  step: 'Adim',
  ai: 'Gemini',
  gpu: 'GPU',
  tts: 'Ses',
  raw: 'Ham',
}

/** Masaustunde uretilen cikti dosya kaliplari. */
export const ARTIFACT_SUFFIXES: { re: RegExp; kind: 'video' | 'audio' | 'seo' | 'thumb' | 'report' }[] = [
  { re: /_CLEAN\.mp4$/i, kind: 'video' },
  { re: /_VOICEOVER\.mp3$/i, kind: 'audio' },
  { re: /_SEO\.html$/i, kind: 'seo' },
  { re: /_THUMB\.png$/i, kind: 'thumb' },
  { re: /^Kesif-Rapor.*\.html$/i, kind: 'report' },
]

export const MAX_LOG_LINES = 4000
