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
  klipDurum: 'klip:durum',
  engineConfig: 'engine:config',
  engineSetCharLimit: 'engine:setCharLimit',
  logsRead: 'logs:read',
  updateCheck: 'update:check',
  updateDownload: 'update:download',
  updateLaunch: 'update:launch',
  updateOpenRelease: 'update:openRelease',
  updateProgress: 'update:progress',
  updateAutoState: 'updateauto:state',
  updateAutoCheck: 'updateauto:check',
  updateAutoInstall: 'updateauto:install',
  updateAutoChanged: 'updateauto:changed',
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
  queueList: 'queue:list',
  queueAdd: 'queue:add',
  queueRemove: 'queue:remove',
  queueClear: 'queue:clear',
  queueStart: 'queue:start',
  spendSummary: 'spend:summary',
  quotaGet: 'quota:get',
  creditsGet: 'credits:get',
  secretsGet: 'secrets:get',
  secretsSet: 'secrets:set',
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
  ok: 'Başarılı',
  warn: 'Uyarı',
  err: 'Hata',
  step: 'Adım',
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
  { re: /^klip_\d+.*\.mp4$/i, kind: 'video' },
]

export const MAX_LOG_LINES = 4000

/** KLIPCI cikti klasoru adi (Masaustu/Klipler/<video adi>). */
export const KLIP_KLASOR = 'Klipler'

/** Klip penceresi sinirlari (functions/klipci.py ile ayni hedefler). */
export const KLIP_SAYISI_MIN = 1
export const KLIP_SAYISI_MAX = 10
export const KLIP_SAYISI_VARSAYILAN = 3
export const KLIP_SURE_MIN = 15
export const KLIP_SURE_MAX = 60
export const KLIP_SURE_VARSAYILAN = 45

export function normalKlipSayisi(value?: number | string | null): number {
  const v = Math.floor(Number(value))
  if (!Number.isFinite(v) || v < KLIP_SAYISI_MIN) return KLIP_SAYISI_VARSAYILAN
  return Math.min(KLIP_SAYISI_MAX, v)
}

export function normalKlipSuresi(value?: number | string | null): number {
  const v = Math.floor(Number(value))
  if (!Number.isFinite(v) || v < KLIP_SURE_MIN) return KLIP_SURE_VARSAYILAN
  return Math.min(KLIP_SURE_MAX, v)
}

/** Kesif planinin gun sayisi sinirlari (7 sabit degil, kullanici seciyor). */
export const GUN_SAYISI_MIN = 2
export const GUN_SAYISI_MAX = 60
export const GUN_SAYISI_VARSAYILAN = 7

/**
 * Kullanici girdisini gecerli bir gun sayisina cevirir.
 * Gecersiz/bos degerde varsayilana (7) doner; ust sinir 60'tir.
 */
export function normalGunSayisi(value?: number | string | null): number {
  const v = Math.floor(Number(value))
  if (!Number.isFinite(v) || v < GUN_SAYISI_MIN) return GUN_SAYISI_VARSAYILAN
  return Math.min(GUN_SAYISI_MAX, v)
}
