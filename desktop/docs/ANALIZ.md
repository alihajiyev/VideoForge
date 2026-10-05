# VideoForge — Bot İncelemesi, Mantık Hataları ve Prompt Önerileri

Bu doküman, botun mevcut kodunun **davranışını bozmadan** yapılabilecek iyileştirmeleri listeler.
GUI (`desktop/`) hiçbir Python dosyasını değiştirmez; sadece `python -m modal run ...` ile mevcut
akışı tetikler ve çıktıyı okur.

## 1. Bot ne yapıyor? (özet akış)

| Adım | Yerel | Bulut (Modal) |
|---|---|---|
| 1/4 | yt-dlp + `cookies.txt` ile indirme | — |
| 2/4 | ücretsiz altyazı denemesi | TikTok/Instagram için `cloud_transcribe` (Whisper small, T4) |
| 3/4 | videoyu buluta yükleme | — |
| 4/4 | — | `cloud_orchestrator`: Gemini metin üretimi → ElevenLabs TTS → ProPainter GPU temizliği → YuNet+CLIP kapak (+ Gemini görsel hakem) → SEO HTML |

Çıktılar `Masaüstü`'ne yazılır: `*_CLEAN.mp4`, `*_VOICEOVER.mp3`, `*_THUMB.png`, `*_SEO.html`
(haftalık modda `Gun\<n>_<başlık>_<rand>` klasörüne). Montaj çıktısı `final_XXXXXX.mp4` ise
render biter bitmez aynı `Gun<n>` klasörüne taşınır — tek klasör, tek sonuç (masaüstü kökünde
ayrı final birikmez).

Gemini katmanı: `gemini_uret` → `_try_model` ile 7 key × model listesi üzerinde döner; boş yanıt,
429 (RPM/RPD), 503/504, 500 durumları ayrı ayrı ele alınır; `PROHIBITED_CONTENT` gibi prompt
seviyesi bloklarda döngü kesilir. Bu kısım gerçekten iyi tasarlanmış.

## 2. Mantık hataları (öncelik sırasına göre)

### 2.1 Kritik — SEO raporu ile gerçek seslendirme metni uyuşmuyor
`functions/orchestrator.py` (run_orchestrator): `build_seo_html` TTS bloğundan **önce** çağrılıyor.
TTS bloğu, ses orijinal videodan uzun çıkarsa metni kısaltıp `sections[v_key]`'i güncelliyor.
HTML yalnızca `voice_timeline` boş değilse yeniden üretiliyor:

```python
seo_html_str = build_seo_html(...)          # <-- TTS öncesi
...
if is_sujet and audio_bytes:                 # metin kısaltılıyor, ses yeniden üretiliyor
    ...
    sections[v_key] = voiceover_text
...
if voice_timeline:                           # <-- sadece bu dalda yeniden üretiliyor
    seo_html_str = build_seo_html(...)
```

Sonuç: beat map üretilemezse rapor, kısaltılmadan önceki (hatalı) metni gösteriyor.
**Düzeltme:** TTS/uzunluk düzeltmelerinden sonra **tek** `build_seo_html` çağrısı yap (ilk çağrıyı kaldır).

### 2.2 Kritik — konu puanı kapısı (evaluate_topic) hiç çalışmıyor
Üç kanal dosyası da sabit `force=True` geçiyor ve `eval_topic` hiç `True` verilmiyor:

```python
response = cloud_orchestrator.remote(..., force=True, ...)   # kinosekrety.py:161, faktza15.py:151, kinok_syjet.py:144
```

`run_orchestrator` içindeki `if eval_topic and not force:` bloğu bu yüzden **ölü kod**.
Ayrıca `force` değişkeni `args.force`'dan okunup hiç kullanılmıyor (`--force` bayrağı işlevsiz).
**Düzeltme:** `force=force, eval_topic=True` (en azından 1-2. kanalda) — konu uygun değilse video
baştan işlenmesin, GPU/ElevenLabs kredisi harcanmasın.

### 2.3 Yüksek — `GEMINI_CALL_STATS["by_step"]` yanlış sayıyor
`_stat_step(CURRENT_STEP)` yalnızca **boş yanıt** dalında çağrılıyor; yani "adım bazında çağrı"
değil, "adım bazında boş yanıt" sayılıyor. SEO raporundaki kullanım özeti yanıltıcı.
**Düzeltme:** `_try_model` içinde `GEMINI_CALL_STATS["calls"] += 1` satırının yanına `_stat_step(CURRENT_STEP)`.

### 2.4 Yüksek — TTS doğrulama döngüsü hiç tekrar denemiyor
`MAX_TTS_RETRIES = 2` olsa da döngüdeki her dal (`ratio >= 0.90`, aksi halde) `break` ediyor;
doğrulama başarısız olsa bile "aynı ses kabul ediliyor" denip çıkılıyor. Yani retry mekanizması ölü,
üstelik `tts_verify` boşuna Whisper small modelini yüklüyor (yerel, yavaş).
**Düzeltme:** ya gerçek bir düzeltme turu ekle (sorunlu kelimeler için metni yumuşat + yeniden sentez),
ya da doğrulamayı `MAX_TTS_RETRIES=0` ile tamamen kapat ve kredi/zaman harcamayı bırak.

### 2.5 Yüksek — `fix_latin_text` Latin harflerini siliyor
```python
result = re.sub(r'[a-zA-Z]+', lambda m: ... translate(..., 'abc...Z'), result)
```
`TEXT_FIXES`'te olmayan her Latin kelime harf harf siliniyor → "Spider-Man" → "-" gibi bozuk çıktı.
**Düzeltme:** harf silme yerine harf çevirisi (транслитерация) uygula; sözlükte olmayan marka/kişi
adları için önce Rusça karşılığını dene (`TEXT_FIXES`), yoksa kelimeyi tamamen at (harfleri tek tek silme).

### 2.6 Orta — `TEXT_FIXES` iki noktayı siliyor, prompt ise korunmasını istiyor
`TEXT_FIXES` içinde `": " → " "` ve `":" → " "` var. TTS öncesi bu kural uygulandığı için
`«Мстители: Судный день»` → `«Мстители Судный день»` oluyor; oysa prompt kural 10 açıkça
"film adlarını «» içine al" diyor. **Düzeltme:** iki nokta temizliğini yalnızca `«...»` dışında uygula.

### 2.7 Orta — `fix_spelling` her video için 2 kez çağrılıyor
`run_voice_pipeline` adım 7c ve 7c2 aynı fonksiyonu arka arkaya çağırıyor (kota: video başına
+2 Gemini isteği, 7 anahtarın 500 RPD limitinde hissedilir). İki çağrı da aynı prompt'u kullanıyor
(zaten hem yazım hem eksik fiil/bağlaç istiyor). **Düzeltme:** ikinci çağrıyı kaldır veya yalnızca
ilk çağrı `len(out) < len(in) * 0.7` ise tekrar dene.

### 2.8 Orta — Whisper modelleri her işte yeniden yükleniyor
- Bulut: `measure_voice_times` her video için `whisper.load_model("small")` (model indirme + yükleme).
- Yerel: `tts_func.tts_verify` her çağrıda modeli yeniden yüklüyor.
**Düzeltme:** model nesnesini modül seviyesinde (bulutta `@modal.cls` örneği ile) cache'le.
Bu, video başına 1-3 dakika ve ölçülebilir GPU maliyeti tasarrufu sağlar.

### 2.9 Orta — ölü kod ve kış saati hatası
- `_parse_429()` hiç çağrılmıyor (mantık `_try_model` içine kopyalanmış).
- `_time_until_quota_reset()` hiç çağrılmıyor **ve** sabit `-7` saat kullanıyor; Kasım–Mart
  arası Pacific saat dilimi `-8`'dir → kota sıfırlanma saati 1 saat kayar. (Emin olmak için
  `zoneinfo.ZoneInfo("America/Los_Angeles")` kullan.)
- `_thumb_esc()` (orchestrator) tanımlı ama kullanılmıyor.

### 2.10 Orta — sessiz harf hatası: "Печему"
`kinok_syjet.py` satır 11 ve 31'de yasak kalıp listesinde `"Печему"` yazıyor (doğrusu `"Почему"`).
Modelin yasak listesini yanlış öğrenmesine yol açabilecek bir yazım hatası. `VOICE_PROMPT`'ta da var.

### 2.11 Küçük — `voiceover_text` tanımsız kalma riski
`orchestrator.py` içindeki `if is_sujet and audio_bytes:` bloğu, `voiceover_text` yalnızca TTS
`try` bloğunun içinde tanımlandığı için savunmasız. `try` dışında `voiceover_text = ""` ile
başlatmak NameError riskini sıfırlar.

### 2.12 Küçük — `link_kayitlimi` LIKE ile kısmi eşleşme yapıyor
```python
conn.execute("SELECT 1 FROM videos WHERE link = ? OR link LIKE ?", (vid, f"%{vid}%"))
```
`_video_id_cek` beklenmedik bir linkte tüm URL'yi döndürürse `LIKE` yanlış pozitif üretebilir.
Sadece `link = ?` üzerinden gitmek (ve kayıt sırasında ID'yi normalize etmek) yeterli.

### 2.13 Güvenlik — anahtarlar ve cookies koda gömülü
`constants.py` içinde 7 Gemini anahtarı, ElevenLabs anahtarı ve transcript API anahtarı düz metin.
`cookies.txt` de repoda; bu dosya YouTube oturumunuzu taşır.
**Düzeltme:** `.env` (python-dotenv zaten `requirements.txt`'te) + değerleri
`os.getenv("GEMINI_API_KEY_1", "...")` şeklinde oku; `cookies.txt`'i `.gitignore`'a al ve
paylaştığınız repolar için YouTube oturumunu iptal edin.

### 2.14 Küçük — yerel `google-genai` sürüm uyumsuzluğu
`requirements.txt` ve Modal imajı `google-genai==2.24.0` pinliyor; bu makinede kurulu sürüm **2.7.0**.
Yerel testlerle bulut davranışı farklı olabilir. Tek sürüme sabitlemek en güvenlisi.

## 3. Prompt iyileştirmeleri (kaliteyi somut artıracaklar)

1. **Sayı ve simge kuralı (en yüksek etki).** ElevenLabs rakamları zaman zaman İngilizce okuyor.
   Ekle: *"Tüm sayıları Rusça kelimeyle yaz (6 → шесть, 15 → пятнадцать, %40 → сорок процентов).
   %, $, &, /, + simgelerini kullanma."*
2. **Halüsinasyon kilidi.** Mevcut "do not invent facts" çok soyut kalıyor. Somut liste ver:
   *"Transcript'te geçmeyen aktör adı, çıkış tarihi, gişe rakamı, süre, ödül veya sahne UYDURMA.
   Emin değilsen o bilgiyi tamamen atla."*
3. **Film adı sözlüğünü prompt'a enjekte et.** `MOVIE_NAMES_RU` şu an yalnızca **sonradan** düzeltme
   yapıyor. Transcript'te geçen İngilizce adları bulup prompt'a *"Bu video şu filmleri içeriyor:
   Civil War → «Противостояние», Avengers: Doomsday → «Мстители: Судный день»"* şeklinde eklemek
   ilk seferde doğru ismi üretir; post-hoc düzeltme ve "eksik film adı" için harcanan Gemini
   çağrıları azalır.
4. **Dolgu girişleri yasakla.** *"Cümleye 'Итак', 'Кстати', 'Как мы знаем', 'А вы знали',
   'В этом видео' ile başlama."* Anlatı temposunu belirgin şekilde iyileştirir.
5. **Ritim kuralı.** *"İlk cümle en fazla 12 kelime (hook). İki cümle üst üste aynı kelimeyle
   başlamasın."* Şu anki tekrar filtresi yalnızca 3'lü n-gram tekrarını yakalıyor; ardışık
   başlangıç tekrarları yakalanmıyor.
6. **Etiketleri JSON olarak iste.** `generate_tags` içinde `json_mode=True` ile
   `{"tags": [...]}` döndürmek, `fix_tags` döngüsünü (10 denemeye kadar) gereksiz kılar.
   Video başına kaydedilen kota doğrudan kalite bütçesine döner.
7. **Yasak kalıpları tek metinde tanımla.** `PROMPT` ve `VOICE_PROMPT` aynı kuralları farklı
   kelimelerle yazıyor ve ikisinde de "Печему" yazım hatası var. Ortak bir
   `BANNED_PATTERNS` sabiti tek yerden iki prompt'a enjekte edilsin.
8. **Uzunluk stratejisi.** 3. kanalda asıl kısıt ses süresi. Şu an sıra "Gemini ile kısalt →
   TTS → süre ölç → tekrar kısalt". Tersine çevirmek (önce tahmini süre kontrolü, sadece
   gerekiyorsa tek Gemini çağrısı) kredi ve süre tasarrufu sağlar; mevcut pre-TTS tahmin adımı
   zaten var, sadece `fix_length`'in genişletme döngüsünü (10 çağrı) bu adımın arkasına almak yeterli.

## 4. Uygulama tarafında eklenebilecekler (GUI hazır altyapı)

- **Kalıcı iş geçmişi** (şu an yalnızca oturum belleği): işlem özetleri + süre + maliyet SQLite'a.
- **Kuyruk modu:** birden fazla linki sıraya alıp tek tek işlemek (bot zaten tek videoya göre tasarlı).
- **Kota panosu:** yerel Gemini çağrı sayacı + "kotanın sıfırlanmasına kalan süre" (2.9 düzeltilirse doğru çalışır).
- **Prompt sürüm yönetimi:** prompt'ları `prompts/*.txt`'e taşıyıp GUI'den düzenlemek; dosya yoksa
  kanal dosyasındaki mevcut sabit kullanılır → bot mantığı bozulmaz, A/B testi mümkün olur.
- **Bildirim:** işlem bitince Telegram/ntfy mesajı (uzun GPU işlerinde beklemeyi bitirir).
- **Kapak A/B:** `build_thumbnail` iki farklı kare/başlık ile üretilip GUI'de yan yana gösterilsin. (Uygulandı: kare seçiminde yerel kalite + YuNet yüz analizi + CLIP prompt-ensemble, son karar Gemini görsel hakemde.)
