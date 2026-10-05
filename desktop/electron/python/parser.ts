import type { ArtifactKind, JobStats, LogLevel } from '@shared/types'

const ANSI = /\u001b\[[0-9;]*[A-Za-z]/g

export function stripAnsi(input: string): string {
  return input.replace(ANSI, '')
}

export interface ParsedLine {
  level: LogLevel
  text: string
  /** Bu satir hangi aşamaya ait (STAGES anahtari) */
  stage?: string
  /** Cikti dosyasi ipucu */
  artifact?: { kind: ArtifactKind; name: string }
  /** Kapanis istatistikleri */
  stats?: Partial<JobStats>
}

/** Botun ui.py cikti bicimi: "[12:34:56] › mesaj" / "[12:34:56] [1/4] mesaj" */
const STEP_RE = /^\[(\d{2}:\d{2}:\d{2})\]\s*\[(\d+)\/(\d+)\]\s+(.*)$/
const LINE_RE = /^(?:\[(\d{2}:\d{2}:\d{2})\]\s*)?(?:[│|]\s*)?([›»✓!✕·])\s*(.*)$/

const STAGE_HINTS: { re: RegExp; stage: string }[] = [
  { re: /(yerel bilgisayarda indiriliyor|indirme hatasi|yt-dlp|cookies\.txt|Yerel indirme tamamlandi)/i, stage: 'download' },
  { re: /(transkript|altyazi|transcript|whisper)/i, stage: 'transcript' },
  { re: /(veriler buluta|buluta yukleniyor|Sunucu aktif|yukleniyor)/i, stage: 'upload' },
  { re: /(ses metni|hook|son cumle|tekrar kontrol|birlesik kelime|parantez|latin|yazim|gramer|uzunluk|baslik|etiket|pipeline|turkce cevir|Gemini)/i, stage: 'ai' },
  { re: /(elevenlabs|seslendirme|tts|ses testi|ses uzunluk)/i, stage: 'tts' },
  { re: /(propainter|frame|parcalara bolunuyor|temiz parcalar|gpu|temizlik)/i, stage: 'gpu' },
  { re: /(kapak|seo|beat map|zaman cizelgesi|ses zamani)/i, stage: 'seo' },
  { re: /(kaynak kanal|kaynak tarama|kanal taraniyor|toplan)|kaynak/i, stage: 'collect' },
  { re: /(stil profil|siralama|puan|rank)/i, stage: 'rank' },
  { re: /(html rapor|rapor|haftalik plan|gunluk plan|plan json)/i, stage: 'report' },
]

function detectStage(text: string): string | undefined {
  for (const h of STAGE_HINTS) {
    if (h.re.test(text)) return h.stage
  }
  return undefined
}

function detectArtifact(text: string): { kind: ArtifactKind; name: string } | undefined {
  const m = text.match(/([^\s/\\:]+\.(?:mp4|mp3|html|png|json))\s*$/i)
  if (!m) return undefined
  const name = m[1]
  if (/_CLEAN\.mp4$/i.test(name)) return { kind: 'video', name }
  if (/_VOICEOVER\.mp3$/i.test(name)) return { kind: 'audio', name }
  if (/_SEO\.html$/i.test(name)) return { kind: 'seo', name }
  if (/_THUMB\.png$/i.test(name)) return { kind: 'thumb', name }
  if (/^final_\d+\.mp4$/i.test(name)) return { kind: 'video', name }
  if (/^Kesif-Rapor.*\.html$/i.test(name)) return { kind: 'report', name }
  if (/^haftalik_plan\.json$/i.test(name) || /^haftalik_sonuc.*\.json$/i.test(name)) return { kind: 'plan', name }
  return undefined
}

const DUR_RE = /Sure:\s*([^|]+)\|\s*GPU:\s*([^|]+)\|\s*Maliyet:\s*(\S+)/
const GEM_RE = /Gemini kullanimi:\s*(.+)$/
const CHUNK_RE = /(\d+)\s*farkli parcaya bolunuyor/

function detectStats(text: string): Partial<JobStats> | undefined {
  const dur = text.match(DUR_RE)
  if (dur) {
    const gpuPart = dur[2].trim()
    const chunks = Number((gpuPart.match(/(\d+)\s*x/) || [])[1])
    return {
      duration: dur[1].trim(),
      gpu: gpuPart,
      cost: dur[3].trim(),
      chunks: Number.isFinite(chunks) ? chunks : null,
    }
  }
  const gem = text.match(GEM_RE)
  if (gem) return { gemini: gem[1].trim() }
  const ch = text.match(CHUNK_RE)
  if (ch) return { chunks: Number(ch[1]) }
  return undefined
}

/** Tek ham satiri yapilandirilmis log satirina cevirir. */
export function parseLine(raw: string): ParsedLine {
  const clean = stripAnsi(raw).replace(/\s+$/, '')
  const text = clean.trim()
  if (!text) return { level: 'raw', text: '' }

  const step = text.match(STEP_RE)
  if (step) {
    return { level: 'step', text: step[4], stage: detectStage(step[4]) ?? undefined }
  }

  const line = text.match(LINE_RE)
  if (line) {
    const icon = line[2]
    const body = line[3]
    const level: LogLevel =
      icon === '✓' ? 'ok' : icon === '!' ? 'warn' : icon === '✕' ? 'err' : 'info'
    return {
      level,
      text: body,
      stage: detectStage(body),
      artifact: detectArtifact(body),
      stats: detectStats(body),
    }
  }

  // Botun dogrudan print() ciktilari: emoji ile baslayanlar seviye ipucu tasir.
  const level: LogLevel = /(^|\s)❌/.test(text)
    ? 'err'
    : /(^|\s)⚠️/.test(text)
      ? 'warn'
      : /(^|\s)✅/.test(text)
        ? 'ok'
        : /🤖|🧠|Gemini/.test(text)
          ? 'ai'
          : /⚡|🎮|ProPainter/.test(text)
            ? 'gpu'
            : /🎙️|🔊|ElevenLabs/.test(text)
              ? 'tts'
              : 'info'

  return {
    level,
    text,
    stage: detectStage(text),
    artifact: detectArtifact(text),
    stats: detectStats(text),
  }
}
