# VideoForge — Harcama (GPU / kota) Rehberi ve Yapılan Tasarruflar

Bu dosya "para nereye gidiyor?" ve "neyi değiştirdik?" sorularını kısa ve net anlatır.
Ayrıntılı mantık incelemesi için `desktop/docs/ANALIZ.md` dosyasına bakın.

## 1. Para nereye gidiyor?

| Kalem | Nerede | Maliyet | Not |
|---|---|---|---|
| **ProPainter GPU temizliği** | `functions/video_proc.py` (her parça ayrı GPU konteyneri) | **en büyük kalem** | Video süresi + parça sayısı ile büyür |
| **EasyOCR (tam kare tarama)** | aynı yer | yüksek | GPU temizliği süresinin çoğu OCR |
| **ShortsStudio render** | `ShortsStudio/functions/pipeline.py` | orta-yüksek | ~460 s GPU / video |
| **Modal konteyner sabit gideri** | her konteyner açılışı | parça başına sabit | Soğuk başlangıç + model yükleme |
| **Gemini kotası** | `functions/gemini_func.py` | kota (RPD/RPM) | Video başına ~15-30 istek |
| **ElevenLabs** | TTS | karakter kotası | Metin uzunluğu ile birebir |
| **Keşif transkript API'si** | `kesif.py` (`transcript_api`) | istek başına ücretli | Altyazısı olmayan adaylar için |

> **Önemli:** `kesif.py` (keşif) GPU **kullanmaz**. "Haftalık keşif zamanı çok harcıyor"
> dediğinizde para aslında zincirin GPU adımlarında (temizlik + ShortsStudio) ve keşifteki
> ücretli transkript API'sinde çıkıyor.

## 2. Bu sürümde yapılan tasarruflar

### GPU parçaları (fonksiyon: `functions/maliyet.py`)
- **Eşit parçalama:** Eskiden parçalar sabit süreyle kesiliyordu; son parça minik kalabiliyordu
  (ör. 1800 karede 72 kare). Minik parça için de **tam bir GPU konteyneri** (soğuk başlangıç +
  EasyOCR/ProPainter model yükleme) açılıyordu. Artık parçalar eşit; minik kuyruk yok.
- **Kuyruk birleştirme:** Kalan son parça küçükse (tavanın %35'inden azsa) öncekiyle birleştirilir.
  Hiçbir parça VRAM güvenli sınırın **1.25 katından** fazla büyümez.
- **Kısa video = tek konteyner:** 288 kareye sığan (yaklaşık 9.6 sn @30fps) videolar tek parça.

### Tekrar eden işler kesildi (`functions/orchestrator.py`, `functions/gemini_func.py`)
- **TTS doğrulama döngüsü** ölü koddu ama her video için boşuna Whisper `small` modelini
  yüklüyordu. Artık `constants.TTS_DOGRULAMA_AKTIF` bayrağı ile kapalı (varsayılan `False`).
- **Whisper ölçüm modeli** modül seviyesinde önbelleğe alındı (video başına yükleme yok).
- **SEO raporu tek kez** kuruluyor; eskiden TTS kısaltmasından **önce** de kuruluyordu ve rapor
  gösterilen seslendirmeyle tutarsız kalabiliyordu (video başına fazladan HTML üretimi).
- **`fix_spelling` iki kez çağrılıyordu** (aynı prompt, +1 Gemini isteği/video). Artık tek çağrı;
  ikinci tur sadece metin belirgin şekilde bozulduysa denenir.

### Tek akış: VideoForge → ShortsStudio (`haftalik_islet.py`, `ShortsStudio/main.py`)
- VideoForge çıktıları **kopyalanmıyor**; tam yollar ortam değişkeniyle veriliyor
  (`VIDEOFORGE_STUDIO_VIDEO` / `_AUDIO` / `_SEO`).
- Eski davranışta ShortsStudio klasöründe kalan **bayat dosyalar** yüzünden koşu, GPU harcandıktan
  **sonra** duruyordu. Bu hata türü tamamen kalktı (en pahalı hata).
- `GunN_*` klasörü tek kaynak olarak kalır; kaynak dosyalar silinmez.
- **Zapcap** 4xx (400 Bad Request) hatasında videoyu boşuna 3 kez yeniden yüklemeyi bıraktı.

### Maliyet görünürlüğü
- `[Bulut] GPU konteyner sabit maliyeti: N parca x ~75sn = $X` satırı artık her işte yazılır.
- ShortsStudio zaten aylık Modal harcamasını (`Modal ham/kalan`) gösterir.

## 3. Daha da düşürmek isterseniz (ayarlar)

| Ayar | Nerede | Etki |
|---|---|---|
| `FRAMES_PER_GPU` (650) | `constants.py` | Yükseltmek parça sayısını (dolayısıyla GPU $) azaltır — VRAM riski |
| `MAX_CONCURRENT_GPUS` (10) | `constants.py` | Düşürmek anlık harcamayı sınırlar, süreyi uzatır |
| `HD_MODE` (`False`) | `constants.py` | `True` yapmak ~2.4x pahalı (önerilmez) |
| `TTS_DOGRULAMA_AKTIF` (`False`) | `constants.py` | `True` yapmak video başına Whisper yükler |
| `transcript_api` (`true`) | `kesif_config.json` | `false` yapmak keşifte ücretli API çağrısını keser (sıralama kalitesi düşebilir) |

## 4. Doğrulama

Bu tasarruflar ağ/GPU gerektirmeden test edilir:

```bash
cd desktop
npm run test:bot     # 108 kontrol (maliyet planlayici + tek akış + harcama duzeltmeleri)
npm run test:smoke   # 265 kontrol
npm run typecheck
```
