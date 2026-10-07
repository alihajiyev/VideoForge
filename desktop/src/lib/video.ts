/**
 * Yerel klip videolari icin URL uretir.
 *
 * main process `vfil://` protokolunu kaydeder (electron/core/video.ts): sadece
 * izinli klasorlerden servis eder ve Range (kaydirma) destekler. Boylece
 * CSP'yi gevsetmeden uretilen klipleri uygulama icinde oynatabiliyoruz.
 */
export const VIDEO_SCHEME = 'vfil'

export function klipVideoUrl(dosya: string | null | undefined): string {
  if (!dosya) return ''
  return `${VIDEO_SCHEME}://yerel/${encodeURIComponent(dosya)}`
}

/** Dosya adini (uzantisiz) insan okunur bicime cevirir. */
export function dosyaAdi(yol: string | null | undefined): string {
  if (!yol) return ''
  const parcalar = yol.split(/[\\/]/)
  return parcalar[parcalar.length - 1] || yol
}

/** Saniyeyi "1:04" biciminde yazar. */
export function sureMetni(saniye: number | null | undefined): string {
  const s = Math.max(0, Math.round(Number(saniye) || 0))
  const dk = Math.floor(s / 60)
  const sn = s % 60
  if (dk >= 60) {
    const sa = Math.floor(dk / 60)
    return `${sa}:${String(dk % 60).padStart(2, '0')}:${String(sn).padStart(2, '0')}`
  }
  return `${dk}:${String(sn).padStart(2, '0')}`
}
