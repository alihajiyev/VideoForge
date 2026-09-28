# -*- coding: utf-8 -*-
"""Bulut anahtar kontrolu (#12 dogrulama araci).

VideoForge klasorundeki .env dosyasinin Modal ortamina gercekten enjekte
edildigini GERCEK bir Modal konteynerinde kontrol eder. Anahtar DEGERLERI
yazdirilmaz, sadece var/yok ve sayi bilgisi gosterilir.

Calistirma (VideoForge klasorunden):
    python -m modal run desktop/smoke/modal_secret_check.py
"""
import os
import modal

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = modal.App("videoforge-anahtar-kontrol")
image = modal.Image.debian_slim(python_version="3.11")


def _secrets():
    if os.path.exists(os.path.join(_BOT_DIR, ".env")):
        return [modal.Secret.from_dotenv(path=_BOT_DIR)]
    return []


@app.function(image=image, secrets=_secrets())
def kontrol():
    gemini = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
    rapor = {
        "gemini_anahtar_sayisi": len(gemini),
        "gemini_onekler": [k[:8] + "..." for k in gemini],
        "elevenlabs_var": bool(os.getenv("ELEVENLABS_API_KEY", "").strip()),
        "elevenlabs_uzunluk": len(os.getenv("ELEVENLABS_API_KEY", "").strip()),
        "transcript_var": bool(os.getenv("TRANSCRIPT_API_KEY", "").strip()),
        "transcript_uzunluk": len(os.getenv("TRANSCRIPT_API_KEY", "").strip()),
    }
    print("BULUT ANAHTAR RAPORU:", rapor)
    return rapor


@app.local_entrypoint()
def main():
    print(kontrol.remote())
