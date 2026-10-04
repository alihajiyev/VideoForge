# -*- coding: utf-8 -*-
"""ElevenLabs abonelik/odeme on kontrolu + sistemik TTS hata isareti.

Kok neden (gercek haftalik kosu, 2026-10-04): ElevenLabs aboneligi 'past_due'
(odenmemis fatura) iken TTS cagrisi HTTP 401 / payment_issue doner. Eski akis
bunu YALNIZCA uyari sayip devam ediyordu:
  - 4x L4 GPU yine calisiyor (gun basina $0.28-$0.44 bosa gidiyor),
  - Gun klasorune MP3 hic yazilmiyor,
  - ShortsStudio her gun "Gun klasorunde .mp3 bulunamadi" ile atlaniyor.
Yani "gun tamamlandi" gorunuyor ama sesi olmadigi icin cikti ise yaramiyor.

Bu modul:
  1. UCRETSIZ abonelik ucnoktasindan odeme sorununu ONCEDEN tespit eder
     (gunluk zincir ve tekil video kosusu GPU'ya hic girmeden net mesajla durur).
  2. Hata metinlerinde kullanilan SISTEMIK_ISARET sabitini tanimlar; gunluk
     zincir (haftalik_islet.py) bu isareti gorunce kalan gunleri durdurur.
"""
import json
import urllib.request

SUBSCRIPTION_URL = "https://api.elevenlabs.io/v1/user/subscription"

# Bu abonelik durumlarinda TTS KESIN calismaz (odeme bekliyor/gecmis).
ODEME_SORUNLU_DURUMLAR = {"past_due", "unpaid", "incomplete", "incomplete_expired"}

# Bot ciktisinda sistemik hata isareti (haftalik_islet.py bu isareti arar).
SISTEMIK_ISARET = "VIDEOFORGE-SISTEMIK-TTS-HATASI"

ODEME_COZUM = ("Cozum: elevenlabs.io > Billing bolumunden bekleyen faturayi tamamla / "
               "odeme yontemini guncelle; abonelik 'active' olunca komutu tekrar calistir "
               "(islenmemis gunler otomatik devam eder).")


def abonelik_durumu(api_key, timeout=8):
    """Abonelik/odeme durumunu UCRETSIZ ucnoktadan okur. Ulasilamazsa None.

    None donmesi 'sorun yok' DEMEK DEGILDIR; yalnizca ag/anahtar kaynakli
    belirsizliktir ve zinciri engellemeyiz (yanlis pozitifle mesgul etmemek icin).
    """
    if not api_key:
        return None
    try:
        istek = urllib.request.Request(
            SUBSCRIPTION_URL,
            headers={"xi-api-key": api_key, "accept": "application/json"},
        )
        with urllib.request.urlopen(istek, timeout=timeout) as cevap:
            return json.loads(cevap.read().decode("utf-8"))
    except Exception:
        return None


def odeme_sorunu_var_mi(durum):
    """Kesin odeme sorunu mu? (durum None/beklenmedik ise False.)"""
    if not isinstance(durum, dict):
        return False
    return str(durum.get("status", "")).strip().lower() in ODEME_SORUNLU_DURUMLAR


def yerel_on_kontrol(timeout=8):
    """Yerel (GPU'suz) on kontrol: constants + .env anahtariyla abonelik sorgusu.

    Hem gunluk zincir (haftalik_islet.py) hem kanal scriptleri kosuya baslamadan
    once bunu cagirir. Yalnizca KESIN odeme sorununda engellenir; ag hatasinda
    (durum None) zincir bloklanmaz.
    Donus: (True, '') ya da (False, 'net Turkce mesaj').
    """
    try:
        from constants import SETTINGS, ELEVENLABS_API_KEY
    except Exception:
        return True, ""
    if not SETTINGS.get("ELEVENLABS_ENABLED", True):
        return True, ""
    durum = abonelik_durumu(ELEVENLABS_API_KEY, timeout=timeout)
    if odeme_sorunu_var_mi(durum):
        return False, odeme_mesaji(durum)
    return True, ""


def odeme_mesaji(durum):
    """Zincir on kontrolu icin net Turkce mesaj (abonelik verisiyle)."""
    parca = "ElevenLabs aboneliginde odeme sorunu var"
    if isinstance(durum, dict):
        st = str(durum.get("status", "")).strip()
        if st:
            parca += f" (durum: {st}"
            if durum.get("has_open_invoices"):
                parca += ", odenmemis fatura var"
            parca += ")"
    return (f"{parca}. Ses (TTS) uretilemez; bosuna indirme/transkript/GPU yapilmadi. "
            f"{ODEME_COZUM}")


def tts_hata_mesaji(kok_hata=None, abonelik=None):
    """TTS uretilemediginde kullanilacak sistemik hata metni (fail-fast)."""
    kok = str(kok_hata or "")
    odeme = ("payment_issue" in kok) or ("payment_required" in kok) or ("401" in kok) \
        or odeme_sorunu_var_mi(abonelik)
    if odeme:
        return (f"{SISTEMIK_ISARET}: ElevenLabs abonelik/odeme hatasi (401 payment_issue). "
                f"Ses (TTS) uretilemedi; video URETILMEDI ve GPU BASLATILMADI "
                f"(bosa para harcanmadi, MP3'suz cikti yazilmadi). {ODEME_COZUM}")
    detay = f" ({kok[:180]})" if kok else ""
    return (f"{SISTEMIK_ISARET}: ElevenLabs ses (TTS) uretilemedi{detay}. "
            f"Video URETILMEDI ve GPU BASLATILMADI (bosa para harcanmadi). "
            f"ElevenLabs anahtarini ve abonelik durumunu kontrol edip tekrar dene.")
