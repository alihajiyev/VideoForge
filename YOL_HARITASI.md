# VideoForge — Ücretsiz Araçlarla Yapılabilecek Özellik Listesi

Tarih: 2026-10-06 · Sürüm 2: **sadece ücretsiz / açık kaynak**. Ücretli servise dayanan maddeler listeden çıkarıldı (bkz. sondaki "ÇIKARILANLAR" bölümü).

Kısaltma: **VF** = VideoForge bot (kesif/gemini/üretim), **SS** = ShortsStudio (Remotion/ffmpeg render), **DP** = Electron masaüstü panel.

> Kural: her maddede kullanılacak araç **açık kaynak veya ücretsiz API** olacak. Lisans uyarıları ⚠️ ile işaretli.

---

## ✅ UYGULANDI (bu turda eklenen kod)

| Madde | Nerede | Ne yapıyor |
|---|---|---|
| **24** — Uzun video → Shorts | `functions/klipci.py` (+ masaüstünde **Klip Stüdyo** sayfası) | Link ver → transkript → önem skoru → dolgu/tekrar/ölü hava temizliği → konu bütünlüklü pencere → konuşmacı ayırma → kafa takibi → **1 / 2 (alt-üst) / 3 / 4 (2x2) panelli** dikey render → her klip QA'dan geçer |
| **7** — Müzik ducking | `functions/ses_isleme.py: muzik_ducking` | ffmpeg `sidechaincompress` ile konuşma varken müziği kısar (eski düz `amix` yerine) |
| **11** — Ses temizliği + sabit seviye | `functions/ses_isleme.py: gurultu_temizle, ses_esitle` | `afftdn` gürültü temizliği + 2 geçişli `loudnorm` (-14 LUFS); ölçüm `ebur128` ile doğrulanır |
| **12** — Filler/sessizlik/bad-take temizliği | `functions/klipci.py: filler_temizle` | Dolgu cümleleri, tekrar eden içerik (shingle benzerliği) ve sessizlik atılır → jump-cut |
| **10 (kısmen)** — Reframe | `functions/klipci.py: yuz_izleri / konusmaci_yuz_esle / kadraj_plani` | OpenCV YuNet ile yüz izleme + dudak hareketinden konuşmacı eşleme; kadraj konuşana göre kayar |

Not: 10. maddenin LUT/grain kısmı ve MediaPipe yerine OpenCV YuNet kullanıldı (Python 3.14'te mediapipe wheel'i yok, OpenCV 5 zaten kurulu; model 232 KB, ilk kullanımda `models/` altına iner ve `.gitignore`'da).

**Akışı bozmama garantisi:** yeni motorlar ayrı dosyalar; `kesif.py`, `haftalik_islet.py`, kanal betikleri ve `temizle.py` içinde `klipci`/`ses_isleme` **hiç import edilmiyor** (bot testleri bunu ayrıca kontrol ediyor).

---

## 0) Bizde ZATEN olanlar (rakiplerin çoğunda yok)

| Özellik | Rakiplerde | Bizde |
|---|---|---|
| Otomatik fikir + haftalık plan + script üretimi | Kısmen | Var (kesif.py + haftalik_plan.json) |
| Kendi kanal verisinden kazanan kalıp madenciliği | Yok | Var (performans.py) |
| Yayın öncesi teknik QA kapısı (siyah/donma/sessizlik/LUFS) | Yok | Var (qa_kapisi.py) |
| TTS + Whisper + ffmpeg/Remotion render, tamamen yerel | Bulutta, kredili | Var |
| Kredi sistemi / abonelik zorunluluğu | Var | Yok |

---

## 1) Ücretsiz araç seti (neyi neyle yapacağız)

| İhtiyaç | Ücretsiz araç | Lisans |
|---|---|---|
| Konuşma tanıma | faster-whisper / openai-whisper | MIT |
| TTS (seslendirme) | **Kokoro-82M** (82M, CPU'da bile çalışır, 54 ses) veya **Piper** | Kokoro: Apache-2.0 ✅ ticari OK · Piper: MIT |
| ⚠️ Kaçınılacak TTS | **XTTS-v2 / Coqui** | CPML — **ticari kullanıma kapalı**, monetize kanalda kullanılamaz |
| Ses temizleme | ffmpeg `afftdn` + `arnndn` (RNNoise modeli) | GPL ffmpeg, ek model gerekmez |
| Müzik/kaynak ayırma (stem) | demucs | MIT ✅ |
| Müzik ducking | ffmpeg `sidechaincompress` | GPL |
| Beat/ritim analizi | librosa | ISC |
| Yüz/nesne takibi | MediaPipe + OpenCV | Apache-2.0 |
| Ücretsiz stok video/görsel | Pexels API, Pixabay API, Coverr API, Openverse | Pexels: ücretsiz, atıf şart değil · Pixabay: atıf şart değil · **Openverse içerik lisansı değişir → CC-BY ise açıklamaya atıf şart** |
| Ücretsiz müzik/SFX | Pixabay Music, Free Music Archive (CC0 filtrele), Coverr | CC0 tercih et |
| Trend/arama verisi | YouTube autocomplete (public endpoint), pytrends, YouTube Data API v3 (ücretsiz kota ~10k birim/gün) | ücretsiz |
| Rakipten veri | yt-dlp (zaten var) | Unlicense |
| Aktarım (upload) | ❌ yok — elle yükleme (senin kuralın) | — |
| Telif parmak izi | chromaprint / `fpcalc` | LGPL |

⚠️ **Not:** `Wav2Lip` gibi "ücretsiz" görünen dudak senkronu repoları **ticari kullanıma kapalı** (araştırma lisansı). Kanalların zaten yüzsüz (faceless) olduğu için dudak senkronu **hiç gerekmiyor** → bu madde tamamen çıkarıldı.

✅ **Bu makinede doğrulandı (2026-10-06):** kurulu ffmpeg 8.0.1'de `sidechaincompress`, `afftdn`, `arnndn`, `lut3d`, `zoompan`, `noise`, `silencedetect`, `ebur128` filtrelerinin hepsi var. Python 3.14.5'te `kokoro`, `piper-tts`, `faster-whisper`, `librosa`, `mediapipe`, `demucs` paketlerinin kurulabilir wheel'i mevcut (pip dry-run ile test edildi, indirilmedi).

---

## P0 — Hemen, en yüksek etki / sıfır maliyet

1. **Hook A/B üretimi (3 hook + otomatik skor)** — OpusClip "virality score" mantığı
   - Ücretsiz araç: mevcut Gemini kotası + `performans.py` kalıp skoru (ikisi de var).
   - Nerede: VF + SS · Etki: **çok yüksek** · Zorluk: Orta
2. **Rakip/outlier madenciliği** — 1of10 / vidIQ Outliers mantığı
   - Ücretsiz araç: `yt-dlp` + YouTube RSS (`feeds/videos.xml`) — API anahtarı bile gerekmez.
   - Nerede: VF (kesif.py'ye modül) · Etki: yüksek · Zorluk: Düşük
3. **Kapak/thumbnail üretimi + A/B** — TubeBuddy A/B, YouTube "Test & Compare" (YouTube'un kendi özelliği ücretsiz)
   - Ücretsiz araç: videodan kare çek (ffmpeg) + PIL ile kompozisyon; istersen yerel Stable Diffusion (ComfyUI).
   - Nerede: VF + DP · Etki: yüksek · Zorluk: Düşük-Orta
4. **Çoklu varyant çıktı (2-3 kesim)** — OpusClip bir videodan onlarca klip üretir
   - Ücretsiz araç: mevcut render hattını parametrikleştir (hook + kapak + müzik).
   - Nerede: VF + SS · Etki: yüksek · Zorluk: Orta (render süresi 2x)
5. **Trend radarı** — vidIQ günlük fikir akışı
   - Ücretsiz araç: YouTube autocomplete + pytrends + rakip yeni yüklemeleri.
   - Nerede: VF · Etki: Orta-yüksek · Zorluk: Düşük
6. **Altyazı kalite katmanı** — Submagic animasyonlu altyazı
   - Ücretsiz araç: Whisper zaman damgaları + Remotion animasyonu.
   - Nerede: SS + QA · Etki: Orta-yüksek · Zorluk: Orta

## P1 — Kurgu kalitesi (ShortsStudio, hepsi ücretsiz)

7. **Müzik ducking + ses tasarımı (SFX)** — Submagic  ✅ **UYGULANDI**
   - ffmpeg `sidechaincompress`; SFX için CC0 (Pixabay/FMA) veya ffmpeg ile sentez.
   - Etki: yüksek · Zorluk: **Düşük** (şu an düz `amix`, en hızlı kazanç)
   - Durum: `functions/ses_isleme.py` — tek dosya üzerinde de çalışır (`py -3 functions/ses_isleme.py --giris konusma.mp3 --muzik fon.mp3 --cikis out.wav`), klipci.py içinden de kullanılır.
8. **Sahne-eşleşmeli B-roll** — OpusClip AI B-roll
   - Pexels/Pixabay/Coverr ücretsiz API + transcript anahtar kelime eşleşmesi. ⚠️ CC-BY içerikte açıklamaya atıf.
   - Etki: yüksek · Zorluk: Yüksek
9. **Ritim motoru (auto-zoom + beat hizalama)** — Submagic Auto Zoom
   - librosa onset/beat + ffmpeg `zoompan`.
   - Etki: Orta-yüksek · Zorluk: Orta
10. **Yüz takipli reframe + kanal LUT/grain** — OpusClip ReframeAnything
    - MediaPipe + ffmpeg `lut3d` (ücretsiz .cube) + `noise` filtresi.
    - Etki: Orta · Zorluk: Orta
11. **Ses temizliği + sabit marka sesi** — Descript Studio Sound  ✅ **UYGULANDI (ses temizliği kısmı)**
    - ffmpeg `afftdn`/`arnndn` + Kokoro'da tek ses seçip tüm kanallarda sabitlemek.
    - **Bonus:** TTS'i Kokoro'ya çevirirsen ElevenLabs aboneliğinden de kurtulursun (tam ücretsiz iş akışı).
    - Etki: Orta-yüksek · Zorluk: Orta
12. **Filler/silence/bad-take temizliği** — Descript, OpusClip  ✅ **UYGULANDI**
    - ffmpeg `silencedetect` (QA'da zaten var) + Whisper kelime zamanları.
    - Etki: Orta · Zorluk: Düşük
13. **Çok dilli kanal açılımı (ücretsiz)** — Descript/Kling dublaj mantığı, ama ücretsiz
    - LLM ile çeviri + Kokoro/Piper ile o dilde seslendirme + o dilde altyazı. Yüzsüz kanal olduğu için dudak senkronu gerekmez.
    - Etki: **çok yüksek** (tek üretim → N kanal) · Zorluk: Orta

## P2 — Operasyon (masaüstü panel, hepsi ücretsiz)

14. **Uygulama içi inceleme paneli (önizle → düzelt → yeniden render)** — OpusClip in-app editor
    - Electron zaten var; ek maliyet yok. Etki: çok yüksek · Zorluk: Orta
15. **Analitik panosu** (retention/CTR + hangi kalıp kazandı) — performans.json var, grafik yok. Etki: yüksek · Zorluk: Düşük-Orta
16. **Marka kiti/şablonlar** (intro/outro/logo/font/renk) — OpusClip brand templates. Etki: Orta · Zorluk: Düşük
17. **İçerik takvimi + yayın kuyruğu** (yükleme YOK, elle yükleme için hazır paket). Etki: Orta · Zorluk: Düşük
18. **Seri/bölüm yapısı + otomatik numaralandırma.** Etki: Orta · Zorluk: Düşük
19. **Yayın saati / başlık A/B testi** — YouTube Test & Compare ücretsiz. Etki: Orta · Zorluk: Düşük

## P3 — Farklılaştırıcı (rakiplerde de düzgün yok)

20. **Telif & claim riski kontrolü** (film/dizi klipleri için) — chromaprint/fpcalc + OpenCV sahne eşleşmesi. Bizim nişte kritik. Etki: yüksek · Zorluk: Orta
21. **Tek "yayına hazır mı" skoru** — kalıp skoru (performans.py) + QA skoru (qa_kapisi.py) birleşimi. Zorluk: Düşük
22. **İzleyici simülasyonu** — LLM'e "bu Short'u kaydırır mıydın?" (mevcut Gemini kotası). Zorluk: Düşük
23. **Yorum madenciliği → yeni fikir** — YouTube Data API v3 ücretsiz kotası. Zorluk: Düşük
24. **Kendi uzun videolarından Shorts çıkarma** — yt-dlp + Whisper + ffmpeg (OpusClip ClipAnything mantığı, ücretsiz). Zorluk: Orta  ✅ **UYGULANDI** (`functions/klipci.py` + masaüstü **Klip Stüdyo** sayfası)

---

## ÇIKARILANLAR (ücretli olduğu için silindi)

| Çıkarılan | Neden |
|---|---|
| Çok dilli dublaj + dudak senkronu (Descript, HeyGen, Kling, Sync API) | Hepsi ücretli. Ücretsiz alternatif olarak 13. madde (çeviri + yerel TTS) konuldu. Wav2Lip tipi "ücretsiz" repolar ticari kullanıma kapalı olduğu için kullanılmadı. |
| AI video üretimi ile B-roll (Veo, Sora, Runway, Kling, Mirage AI aktörler) | Ücretli/kredili. Yerine ücretsiz stok API'ler (Pexels/Pixabay/Coverr) — madde 8. |
| Bulut klip servisleri (OpusClip, Submagic, Vizard, Klap, Captions, quso.ai, Pikzels) | Hepsi abonelik. Sadece "kimde var" referansı olarak kaldı. |
| Ses klonlama (XTTS-v2, ticari ses klon API'leri) | XTTS-v2 lisansı (CPML) ticari kullanıma kapalı; monetize kanalda riskli. Yerine Kokoro sabit sesi — madde 11. |
| Growth/analitik SaaS (vidIQ, TubeBuddy Pro, 1of10, Satura, Orbit) | Ücretli. Yerine YouTube Data API ücretsiz kotası + yt-dlp + kendi CSV akışımız. |
| OpusClip Business API / webhook | Ücretli ve tek kişilik kullanımda gereksiz. |
| Studio Sound / DeepFilterNet bulut servisleri | Yerine ffmpeg native (afftdn/arnndn) — madde 11. |

---

## Özet öneri (ücretsiz, sırayla)

**1 → 2 → 3 → 7 → 14 → 13 → 8 → 11**

(Bu turda 24, 7, 11, 12 ve 10'un reframe kısmı uygulandı; sıradaki en mantıklı adım **2 → 1 → 3**.)

Gerekçe: önce **dağıtım tarafı** (hook A/B, rakip outlier, kapak), sonra **en ucuz büyük kalite kazancı** (müzik ducking), sonra **iş akışı** (inceleme paneli), sonra **ölçek** (çok dilli kanal + ücretsiz TTS), en son **pahalı kalite** (stok B-roll).

Toplam ek maliyet: **0 TL** (tek gereken: ücretsiz API anahtarları — Pexels/Pixabay; alternatifi Openverse/Wikimedia).
