import type { ChannelDef, JobKind, StageDef } from './types'

/** Kanal tanimlari - bot dosyalarindaki gercek degerlerle birebir ayni. */
export const CHANNELS: ChannelDef[] = [
  {
    id: '1',
    name: 'Kino Sekrety',
    niche: 'Film Sirlari',
    script: 'kinosekrety.py',
    voiceId: 'M1CSR3PJBsfWU6ZquG3C',
    accent: 'from-sky-500/20 to-indigo-500/10',
    note: 'Marvel/DC film sirlari. Hook sorusu serbest.',
  },
  {
    id: '2',
    name: 'Fakt Za 15',
    niche: 'Ilginc Bilgiler',
    script: 'faktza15.py',
    voiceId: 'M1CSR3PJBsfWU6ZquG3C',
    accent: 'from-emerald-500/20 to-teal-500/10',
    note: '15 saniyelik ilginc bilgi formati.',
  },
  {
    id: '3',
    name: 'PopkornFakty',
    niche: 'Film Hikayeleri (Rus anlatim)',
    script: 'kinok_syjet.py',
    voiceId: 'LHi3adMlU7AICv8Yxpmm',
    accent: 'from-amber-500/20 to-orange-600/10',
    note: 'Sinematik anlatici modu: soru cumlesi YASAK, transcript orani %80.',
  },
]

export function channelById(id: string): ChannelDef | undefined {
  return CHANNELS.find((c) => c.id === id)
}

/** Is adimlarindan olusan zaman cizelgesi (botun gercek akisina gore). */
export const STAGES: Record<JobKind, StageDef[]> = {
  channel: [
    { key: 'download', label: 'Indirme', hint: 'yt-dlp + cookies.txt' },
    { key: 'transcript', label: 'Transkript', hint: 'Altyazi / Modal GPU' },
    { key: 'upload', label: 'Bulut Yukleme', hint: 'Video -> Modal' },
    { key: 'ai', label: 'AI Pipeline', hint: 'Ses metni + baslik + etiket' },
    { key: 'tts', label: 'Seslendirme', hint: 'ElevenLabs + dogrulama' },
    { key: 'gpu', label: 'GPU Temizlik', hint: 'ProPainter parcalari' },
    { key: 'seo', label: 'Kapak + SEO', hint: 'Thumbnail + HTML rapor' },
  ],
  discover: [
    { key: 'collect', label: 'Kaynak Tarama', hint: 'Kaynak kanal videolari' },
    { key: 'transcript', label: 'Transkript', hint: 'Alt yazi / Whisper' },
    { key: 'rank', label: 'Gemini Siralama', hint: 'Stil profili + puan' },
    { key: 'report', label: 'Rapor / Plan', hint: 'HTML + gunluk plan' },
  ],
  weekly: [
    { key: 'discover', label: '1. Kesif', hint: 'Secilen gun sayisi kadar video' },
    { key: 'plan', label: '2. Plan', hint: 'Skor sirasi = gun sirasi' },
    { key: 'render', label: '3. Islem Zinciri', hint: 'Temizle + SEO + ses' },
    { key: 'studio', label: '4. ShortsStudio', hint: 'Montaj (varsa)' },
  ],
  clean: [
    { key: 'download', label: 'Indirme', hint: 'yt-dlp' },
    { key: 'upload', label: 'Bulut Yukleme', hint: 'Modal' },
    { key: 'gpu', label: 'ProPainter Temizlik', hint: 'GPU' },
    { key: 'output', label: 'Cikti', hint: 'Masaustu' },
  ],
}
