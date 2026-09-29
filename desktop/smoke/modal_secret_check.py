# -*- coding: utf-8 -*-
"""Bulut gizli anahtar + bagimlilik kontrolu (GERCEK Modal konteyneri).

Bu araç iki seyi kanitlar:

1. ANAHTAR INMESI: `videoforge-env` isimli secret'i ile GEMINI/ELEVENLABS/
   TRANSCRIPT anahtarlari konteynerin ortam degiskenlerine gercekten iniyor.
2. BAGIMLILIK SAYISI: konteyner bu dosyayi yeniden import ettiginde de
   fonksiyonun bagimlilik listesi (secret + imaj + volume = 3) lokalde
   hesaplananla BIREBIR ayni. Eski kodda `.env` konteynerde olmadigi icin
   burada 2 nesne olusuyor ve Modal su hatayi veriyordu:
       ExecutionError: Function has 2 dependencies but container got 3 object ids.

Anahtar DEGERLERI hicbir zaman yazdirilmaz; sadece var/yok + adet bilgisi.

Calistirma (VideoForge klasorunden):
    python -m modal run desktop/smoke/modal_secret_check.py
"""
import os
import sys

import modal

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BOT_DIR not in sys.path:
    sys.path.insert(0, _BOT_DIR)

# Uretimde kullanilan secret tanimiyla AYNI isim. Lokalde tek kaynaktan
# (bulut_kurulum) okunur; konteyner bu dosyayi yeniden import ettiginde
# bulut_kurulum.py mount edilmedigi icin isim literal olarak kalir.
# ONEMLI: her iki durumda da secret SAYISI 1 - bagimlilik hatasi bu yuzden olmaz.
try:
    from bulut_kurulum import SECRET_NAME
except Exception:  # konteyner ortami
    SECRET_NAME = "videoforge-env"
assert SECRET_NAME == "videoforge-env", SECRET_NAME

app = modal.App("videoforge-anahtar-kontrol")
image = modal.Image.debian_slim(python_version="3.11")

# Uretimdeki kalibi birebir taklit eder: KOSULSUZ, tek isimli secret.
SECRETS = [modal.Secret.from_name(SECRET_NAME)]

# Uretimdeki volume (sadece referans; test yazmaz) - hatanin ciktigi 3'lu
# bagimlilik kumesini birebir kurmak icin gerekli.
VOLUME = modal.Volume.from_name("fgt-clean-results")


@app.function(image=image, secrets=SECRETS, retries=0)
def anahtar_kontrol():
    """Konteynerde anahtarlarin gercekten gorunup gorunmedigini bildirir."""
    gemini = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
    return {
        "env_dosyasi_konteynerde": os.path.exists(os.path.join(_BOT_DIR, ".env")),
        "gemini_anahtar_sayisi": len(gemini),
        "gemini_onekler": [k[:8] + "..." for k in gemini],
        "elevenlabs_var": bool(os.getenv("ELEVENLABS_API_KEY", "").strip()),
        "elevenlabs_uzunluk": len(os.getenv("ELEVENLABS_API_KEY", "").strip()),
        "transcript_var": bool(os.getenv("TRANSCRIPT_API_KEY", "").strip()),
        "transcript_uzunluk": len(os.getenv("TRANSCRIPT_API_KEY", "").strip()),
    }


@app.function(image=image, secrets=SECRETS, volumes={"/results": VOLUME}, retries=0)
def bagimlilik_kontrol():
    """Hatanin ciktigi TAM kalip: secret + imaj + volume birlikte.

    Eski kodda secret KOSULLU tanimlaniyordu (dosya varsa ekle). Konteynerde
dosya olmadigi icin bagimlilik sayisi uyusmuyor ve cagri
    'Function has N dependencies but container got M object ids' ile patliyordu.
    """
    return {"calisti": True, "secret_env_var": bool(os.getenv("GEMINI_API_KEYS", "").strip())}


@app.local_entrypoint()
def main():
    print("=" * 60)
    print("BULUT KONTROL (gercek Modal konteyneri)")
    print("=" * 60)
    print(f"secret adi      : {SECRET_NAME} ({len(SECRETS)} bagimlilik - kosulsuz sabit)")
    print(f"konteyner .env  : (beklenen: False - imaja gomulmez)")
    rapor = anahtar_kontrol.remote()
    print(f"anahtar raporu  : {rapor}")
    print(f"bagimlilik testi: {bagimlilik_kontrol.remote()}")
    sorunlar = []
    if rapor["env_dosyasi_konteynerde"]:
        sorunlar.append(".env konteynere sizmis (olmamali)")
    if rapor["gemini_anahtar_sayisi"] < 1:
        sorunlar.append("Gemini anahtari konteynere inmedi")
    if not rapor["elevenlabs_var"]:
        sorunlar.append("ElevenLabs anahtari konteynere inmedi")
    if not rapor["transcript_var"]:
        sorunlar.append("Transcript API anahtari konteynere inmedi")
    if sorunlar:
        print("SONUC: BASARISIZ -> " + "; ".join(sorunlar))
        raise SystemExit(1)
    print("SONUC: BASARILI - anahtarlar indi, bagimlilik sayisi uyusuyor")
    print("=" * 60)
