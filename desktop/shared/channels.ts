import type { ChannelDef, JobKind, StageDef } from './types'

/** Kanal tanimlari - bot dosyalarindaki gercek degerlerle birebir ayni. */
export const CHANNELS: ChannelDef[] = [
  {
    id: '1',
    name: 'Kino Sekrety',
    niche: 'Film sırları',
    script: 'kinosekrety.py',
    voiceId: 'M1CSR3PJBsfWU6ZquG3C',
    accent: 'from-sky-500/20 to-indigo-500/10',
    note: 'Marvel/DC film sırları. Açılış sorusu serbest.',
  },
  {
    id: '2',
    name: 'Fakt Za 15',
    niche: 'İlginç bilgiler',
    script: 'faktza15.py',
    voiceId: 'M1CSR3PJBsfWU6ZquG3C',
    accent: 'from-emerald-500/20 to-teal-500/10',
    note: 'Kısa, merak uyandıran bilgi formatı.',
  },
  {
    id: '3',
    name: 'PopkornFakty',
    niche: 'Film hikâyeleri (Rusça anlatım)',
    script: 'kinok_syjet.py',
    voiceId: 'LHi3adMlU7AICv8Yxpmm',
    accent: 'from-amber-500/20 to-orange-600/10',
    note: 'Sinematik anlatıcı: soru cümlesi yasak, transkript oranı %80.',
  },
]

export function channelById(id: string): ChannelDef | undefined {
  return CHANNELS.find((c) => c.id === id)
}

/** Is adimlarindan olusan zaman cizelgesi (botun gercek akisina gore). */
export const STAGES: Record<JobKind, StageDef[]> = {
  channel: [
    { key: 'download', label: 'İndirme', hint: 'yt-dlp + cookies.txt' },
    { key: 'transcript', label: 'Transkript', hint: 'Altyazı / Modal GPU' },
    { key: 'upload', label: 'Buluta yükleme', hint: 'Video → Modal' },
    { key: 'ai', label: 'AI işleme', hint: 'Ses metni, başlık, etiket' },
    { key: 'tts', label: 'Seslendirme', hint: 'ElevenLabs + doğrulama' },
    { key: 'gpu', label: 'GPU temizleme', hint: 'ProPainter parçaları' },
    { key: 'seo', label: 'Kapak + SEO', hint: 'Kapak görseli + HTML rapor' },
  ],
  discover: [
    { key: 'collect', label: 'Kaynak taraması', hint: 'Kaynak kanal videoları' },
    { key: 'transcript', label: 'Transkript', hint: 'Altyazı / Whisper' },
    { key: 'rank', label: 'Gemini sıralama', hint: 'Stil profili + puan' },
    { key: 'report', label: 'Rapor / plan', hint: 'HTML + günlük plan' },
  ],
  weekly: [
    { key: 'discover', label: '1. Keşif', hint: 'Seçilen gün sayısı kadar video' },
    { key: 'plan', label: '2. Plan', hint: 'Skor sırası = gün sırası' },
    { key: 'render', label: '3. İşlem zinciri', hint: 'Temizle + SEO + ses' },
    { key: 'studio', label: '4. ShortsStudio', hint: 'Montaj (kuruluysa)' },
  ],
  clean: [
    { key: 'download', label: 'İndirme', hint: 'yt-dlp' },
    { key: 'upload', label: 'Buluta yükleme', hint: 'Modal' },
    { key: 'gpu', label: 'ProPainter temizleme', hint: 'GPU' },
    { key: 'output', label: 'Çıktı', hint: 'Masaüstü' },
  ],
  /* KLIPCI: uzun video -> dikey Shorts (yerel, anahtarsiz). */
  klip: [
    { key: 'download', label: 'İndirme', hint: 'yt-dlp (cookies.txt)' },
    { key: 'transcript', label: 'Transkript', hint: 'Altyazı → API → Whisper' },
    { key: 'score', label: 'Önem skoru', hint: 'Bilgi yoğunluğu + hook' },
    { key: 'clean', label: 'Gereksiz temizlik', hint: 'Dolgu + tekrar + sessizlik' },
    { key: 'speaker', label: 'Konuşmacı ayırma', hint: 'KMeans (ses parmak izi)' },
    { key: 'face', label: 'Kafa takibi', hint: 'YuNet yüz izleme' },
    { key: 'render', label: 'Dikey montaj', hint: '1/2/4 panel + kafa takibi' },
    { key: 'qa', label: 'QA kapısı', hint: '15-60 sn · -14 LUFS · siyah kare' },
  ],
}
