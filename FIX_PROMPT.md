## 🚨 KRİTİK DÜZELTME: Gemini 429 Hatası Çözümü

### Kök Sorun
`_try_model` fonksiyonunda `google_search` tool'u kullanılıyor. **3.x Flash modelleri free tier'da bu tool'u desteklemiyor.** Tool eklenince anında 429 hatası alıyoruz — tüm key'ler "kota dolu" gibi görünüyor ama aslında sorun tool'un kendisi.

### Kanıt
- `gemini-3.6-flash` + search tool → ❌ 429
- `gemini-3.6-flash` + search tool'suz → ✅ Çalışıyor
- Same for 3.5-flash, 3.5-flash-lite
- Only `gemini-2.5-flash` works with search tool

### Yapılacak Değişiklik

**Dosya:** `functions/gemini_func.py` → `_try_model` fonksiyonu

**ESKİ KOD (sil):**
```python
for attempt in range(3):
    try:
        client = genai.Client(api_key=api_key)
        try:
            search_tool = types.Tool(google_search=types.GoogleSearch())
            config = types.GenerateContentConfig(system_instruction=system_prompt, tools=[search_tool])
        except:
            config = types.GenerateContentConfig(system_instruction=system_prompt)
        contents = input_text
```

**YENİ KOD (yerine yaz):**
```python
for attempt in range(3):
    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(system_instruction=system_prompt)
        contents = input_text
```

Yani `google_search` ile ilgili 3 satırı (try bloğu) tamamen sil, `config = ...` satırını olduğu gibi bırak.

### Ek Düzeltmeler (Aynı Dosyada)

1. **Rate Limiter** — `_try_model`'den önce ekle:
```python
class GeminiRateLimiter:
    def __init__(self, min_interval=4.5):
        self.min_interval = min_interval
        self.last_request_time = 0.0

    def wait_if_needed(self):
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            print(f"⏳ Rate limit: {wait_time:.1f}s bekleniyor...")
            time.sleep(wait_time)
        self.last_request_time = time.time()

_rate_limiter = GeminiRateLimiter(min_interval=4.5)
```

2. **Rate limiter'ı kullan** — `response = client.models.generate_content(...)` satırının HEMEN ÖNÜNE ekle:
```python
_rate_limiter.wait_if_needed()
```

3. **RPD handling** — `_try_model` fonksiyonunun sonundaki `time.sleep(120)` ve `time.sleep(60)` satırlarını sil:
```python
# ESKİ (sil):
all_rpd = len(rpd_exhausted) == len(GEMINI_API_KEYS)
if all_rpd:
    print("📅 ...")
    time.sleep(120)   # ← BU SATIRI SİL
else:
    print("⚠️ ...")
    time.sleep(60)    # ← BU SATIRI SİL
return None

# YENİ (yerine yaz):
all_rpd = len(rpd_exhausted) >= len(GEMINI_API_KEYS) - 1
if all_rpd:
    print("📅 Tum key'lerin gunluk kotasini dolmus.")
else:
    print("⚠️ [Bulut] Tum key'ler limitlendi.")
return None
```

### Import'lara Ekle (Dosyanın Üstüne)
```python
from datetime import datetime, timezone, timedelta
```

### Kota Sıfırlama Hesaplayıcı (fonksiyon olarak ekle)
```python
def _time_until_quota_reset():
    pacific = timezone(timedelta(hours=-7))
    now = datetime.now(pacific)
    reset = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now >= reset:
        reset += timedelta(days=1)
    diff = reset - now
    hours = int(diff.total_seconds() // 3600)
    minutes = int((diff.total_seconds() % 3600) // 60)
    turkey = timezone(timedelta(hours=3))
    reset_turkey = reset.astimezone(turkey)
    return hours, minutes, reset_turkey.strftime("%H:%M")
```

### gemini_uret Fonksiyonundaki Retry Kısmını Değiştir
`gemini_uret` fonksiyonundaki "3dk bekle" kısmını bul ve şöyle değiştir:

```python
# ESKİ (sil):
print("📅 Tum modeller basarisiz. 3dk beklenip son bir kez daha deneniyor...")
time.sleep(180)
for model_name in GEMINI_MODELS:
    result = _try_model(...)
    if result: ...

return "❌ Gemini ile metin uretilemedi."

# YENİ (yerine yaz):
h, m, reset_time = _time_until_quota_reset()
print(f"\n{'='*60}")
print(f"📅 TUM GEMINI KEY'LERIN GUNLUK KOTASI DOLMUS!")
print(f"   Kota sifirlanmasi: ~{h}saat {m}dk sonra (TSİ {reset_time})")
print(f"{'='*60}\n")
return f"❌ Gemini kota dolu — {h}saat {m}dk sonra tekrar dene (TSİ {reset_time})"
```

### Kontrol Listesi
- [ ] `google_search` tool'u `_try_model`'den kaldırıldı
- [ ] `GeminiRateLimiter` sınıfı eklendi
- [ ] `_rate_limiter.wait_if_needed()` API çağrısından önce eklendi
- [ ] RPD bekleme süreleri kaldırıldı (120sn, 60sn → yok)
- [ ] `_time_until_quota_reset()` fonksiyonu eklendi
- [ ] `from datetime import datetime, timezone, timedelta` import edildi
- [ ] `gemini_uret` retry kısmı güncellendi

### Test
Değişikliklerden sonra şunu çalıştır:
```bash
python -c "from functions.gemini_func import gemini_uret; print('Import OK')"
```

Hata almazsan tamam. Alırsan hangi satırda hata verdiğini paylaşırsın.
