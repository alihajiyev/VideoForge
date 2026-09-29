# -*- coding: utf-8 -*-
"""VideoForge - Modal gizli anahtar kurulumu.

NEDEN BU DOSYA VAR?
-------------------
API anahtarlari (Gemini / ElevenLabs / Transcript) kodda ve Modal imajinda
duz metin TUTULMAZ. Lokal `.env` dosyasindaki degerler Modal'da
`videoforge-env` adli TEK bir **isimli secret**'e kopyalanir; bulut
fonksiyonlari bu secret'i `modal.Secret.from_name()` ile referans verir.

Eskiden `modal.Secret.from_dotenv()` KOSULLU olarak tanimlaniyordu
(`.env` varsa ekle). Bu ciddi bir hataydi:
  * lokalde `.env` var  -> fonksiyonun bagimlilik listesi 3 nesne
    (secret + imaj + volume)
  * konteynerde `.env` yok (imaja gomulmez) -> 2 nesne (imaj + volume)
Modal konteyneri acarken bu sayilari karsilastirir ve su hatayi verir:

    modal.exception.ExecutionError:
    Function has 2 dependencies but container got 3 object ids.

Sonuc: her bulut cagrisi ~40 saniye boyunca tekrar tekrar denenip basarisiz
oluyor, "Durdur" da gec calisiyor gibi gorunuyordu.

Isimli secret her iki ortamda da DAIMA 1 bagimlilik uretir -> hata biter.

KULLANIM
--------
    python bulut_kurulum.py            # durumu goster, gerekiyorsa kur
    python bulut_kurulum.py --zorla    # anahtarlari her halukarda yeniden yaz
    python bulut_kurulum.py --kontrol  # sadece uzaktaki secret'i kontrol et
"""
import argparse
import hashlib
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
IMZA_PATH = os.path.join(BASE_DIR, ".modal_secret.sig")

# Bulut fonksiyonlarinin referans verdigi isimli secret (bulut_kanali.py ile ayni).
SECRET_NAME = "videoforge-env"


def _basit_parse(yol):
    """python-dotenv yoksa calisan bagimliliksiz .env ayristirici."""
    sozluk = {}
    try:
        with open(yol, "r", encoding="utf-8", errors="replace") as f:
            for satir in f:
                satir = satir.strip()
                if not satir or satir.startswith("#") or "=" not in satir:
                    continue
                anahtar, _, deger = satir.partition("=")
                anahtar = anahtar.strip()
                deger = deger.strip().strip('"').strip("'")
                if anahtar:
                    sozluk[anahtar] = deger
    except Exception:
        pass
    return sozluk


def env_sozlugu():
    """Lokal .env dosyasindaki DOLU anahtar/degerleri sozluk olarak doner."""
    if not os.path.exists(ENV_PATH):
        return {}
    ham = {}
    try:
        from dotenv import dotenv_values
        ham = dict(dotenv_values(ENV_PATH))
    except Exception:
        ham = _basit_parse(ENV_PATH)
    temiz = {}
    for anahtar, deger in ham.items():
        if not anahtar or str(anahtar).startswith("#"):
            continue
        deger = "" if deger is None else str(deger)
        if deger.strip():
            temiz[str(anahtar).strip()] = deger.strip()
    return temiz


def _imza(env_dict):
    """Anahtar/deger kumesinin kisa parmak izi (deger degisince degisir)."""
    ham = json.dumps(env_dict, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(ham).hexdigest()[:32]


def _imza_oku():
    try:
        with open(IMZA_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _imza_yaz(imza):
    try:
        with open(IMZA_PATH, "w", encoding="utf-8") as f:
            f.write(imza)
    except Exception:
        pass


def isimler():
    """Lokal .env icindeki anahtar ADLARI (degerler asla yazdirilmaz)."""
    return sorted(env_sozlugu().keys())


def uzak_isimler():
    """Modal hesabindaki isimli secret adlari. Hata olursa (None, mesaj)."""
    try:
        import modal
        return sorted(s.name for s in modal.Secret.objects.list() if s.name), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def uzakta_var_mi():
    adlar, hata = uzak_isimler()
    if adlar is None:
        return None, hata
    return SECRET_NAME in adlar, ""


def hazirla(zorla=False, sessiz=False):
    """Lokal .env'deki anahtarlari Modal'daki isimli secret'e kopyalar.

    Idempotent: icerik degismediyse AG CAGRISI YAPILMAZ (yerel imza dosyasi
    sayesinde her bot acilisinda sifir gecikme). Donus: (ok, mesaj).
    """
    def _yaz(mesaj, hata=False):
        if not sessiz:
            print(("⚠️  " if hata else "🔐 ") + mesaj)
        return (not hata), mesaj

    env_dict = env_sozlugu()
    if not env_dict:
        return _yaz(
            f"Gizli anahtar bulunamadi: {ENV_PATH} yok ya da bos. "
            "Uygulamada Ayarlar > Gizli anahtarlar bolumunden doldurun.", hata=True)

    imza = _imza(env_dict)
    if not zorla and _imza_oku() == imza:
        return True, "guncel (onbellek)"

    try:
        import modal
    except Exception as exc:
        return _yaz(f"Modal kutuphanesi yuklenemedi: {exc}", hata=True)

    try:
        # Once sil, sonra yaz: icerik gercekten guncellensin (create(allow_existing=True)
        # eski degerleri korur, anahtar degistirince bayat kalirdi).
        modal.Secret.objects.delete(SECRET_NAME, allow_missing=True)
        modal.Secret.objects.create(SECRET_NAME, env_dict)
    except Exception as exc:
        return _yaz(f"Modal secret yazilamadi ({SECRET_NAME}): {type(exc).__name__}: {exc}", hata=True)

    _imza_yaz(imza)
    return True, f"{len(env_dict)} anahtar '{SECRET_NAME}' secret'ine yazildi"


def main():
    parser = argparse.ArgumentParser(description="VideoForge - Modal gizli anahtar kurulumu")
    parser.add_argument("--zorla", action="store_true", help="Anahtarlari her halukarda yeniden yaz")
    parser.add_argument("--kontrol", action="store_true", help="Sadece uzaktaki secret'i kontrol et, yazma")
    parser.add_argument("--sessiz", action="store_true", help="Kisa cikti")
    args = parser.parse_args()

    print("=" * 60)
    print("🔐 VIDEOFORGE - BULUT GIZLI ANAHTAR KURULUMU")
    print("=" * 60)
    adlar = isimler()
    print(f"📄 Lokal kaynak : {ENV_PATH}")
    print(f"🔑 Bulunan anahtarlar: {', '.join(adlar) if adlar else '(yok)'}")

    var, hata = uzakta_var_mi()
    if var is None:
        print(f"☁️  Uzak durum okunamadi: {hata}")
        print("   (Modal hesabina giris yapilmamis olabilir:  python -m modal token new)")
    else:
        print(f"☁️  Modal secret '{SECRET_NAME}': {'VAR ✅' if var else 'YOK ❌'}")

    if args.kontrol:
        print("=" * 60)
        return 0 if var else 1

    if not adlar:
        print("❌ .env bos - anahtar girilmeden bulut calismaz.")
        print("=" * 60)
        return 1

    ok, mesaj = hazirla(zorla=args.zorla, sessiz=False)
    if ok:
        print(f"✅ Kurulum tamam: {mesaj}")
    else:
        print(f"❌ Kurulum basarisiz: {mesaj}")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
