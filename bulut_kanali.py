# -*- coding: utf-8 -*-
"""Ortak Modal bulut katmani (#2 refactor).

Daha once her kanal dosyasi (kinok_syjet, kinosekrety, faktza15) ayni
app + VideoCleaner + cloud_orchestrator + cloud_transcribe bloklarini
kopyaliyordu. Artik TEK yerde tanimli; kanal dosyalari import eder.

Kanal-specific veriler (prompt, voice_id, kanal adi) remote cagriya
parametre olarak gecilir — davranis birebir ayni kalir.

GIZLI ANAHTARLAR
----------------
API anahtarlari ISIMLI tek bir Modal secret'inden gelir
(`videoforge-env`). Lokal `.env` icerigi `bulut_kurulum.py` ile oraya
kopyalanir. Burada modal'in "from_dotenv" yardimcisi KULLANILMAZ:

  from_dotenv `.env` yoksa bos liste donuyordu -> lokalde 3 bagimlilik
  (secret + imaj + volume), konteynerde 2 (imaj + volume). Modal bunu
  soyle reddediyor:
      Function has 2 dependencies but container got 3 object ids.
  Isimli secret her iki ortamda daima AYNI sayida (1) bagimlilik uretir.

KULLANIM (kanal dosyasinda):
    from bulut_kanali import app, cloud_orchestrator, cloud_transcribe
    ...
    response = cloud_orchestrator.remote(
        link, rand_num, v_bytes, raw_title, tam_metin, force=True,
        source_timeline=source_timeline,
        system_prompt=PROMPT, voice_id=VOICE_ID, lang=LANG,
        channel_name=CHANNEL_NAME, voice_prompt=VOICE_PROMPT,
        title_prompt=TITLE_PROMPT, tags_prompt=TAGS_PROMPT,
    )
"""
import modal
from shared import *
from functions.orchestrator import run_orchestrator
from functions.video_proc import run_clean

# Bulut fonksiyonlarinin referans verdigi isimli secret (bulut_kurulum.py ile ayni).
SECRET_NAME = "videoforge-env"

# DIKKAT: kosulsuz ve sabit. Bagimlilik sayisi lokalde de, konteynerde de 1.
MODAL_SECRETS = [modal.Secret.from_name(SECRET_NAME)]

app = modal.App("videoforge", image=image)

# Lokal kosuda anahtarlarin buluta kopyalandigindan emin ol. Icerik
# degismediyse tek dosya okumasi yapilir, ag cagrisi OLMAZ. Konteynerde
# (modal.is_local() False) hic calismaz - konteyner kendi env'ini kullanir.
if modal.is_local():
    try:
        from bulut_kurulum import hazirla as _secret_hazirla
        _secret_hazirla()
    except Exception as _exc:  # kurulum atlanirsa bulut cagrisi net hata verir
        print(f"⚠️ [Bulut] Gizli anahtar kurulumu atlandi: {_exc}")


class BulutHatasi(RuntimeError):
    """Kullaniciya gosterilecek, anlasilir mesaji olan bulut hatasi."""


def bulut_hatasi_mesaji(exc):
    """Modal/kutuphane hatalarini tek satirlik anlasilir Turkce mesaja cevirir."""
    metin = str(exc)
    dusuk = metin.lower()
    if "dependencies but container got" in metin:
        return (f"Bulut bagimlilik uyusmazligi (Modal secret '{SECRET_NAME}'). "
                "Cozum:  python bulut_kurulum.py --zorla  ve tekrar dene.")
    if "not found" in dusuk or "notfound" in dusuk:
        return (f"Modal'da '{SECRET_NAME}' gizli anahtari yok. "
                "Cozum:  python bulut_kurulum.py --zorla")
    if "token" in dusuk or "unauthorized" in dusuk or "authentication" in dusuk or "profile" in dusuk:
        return "Modal hesabina giris yapilmamis. Cozum:  python -m modal token new"
    if "quota" in dusuk or "rate limit" in dusuk or "429" in metin:
        return "Bulut kotasi doldu, biraz sonra tekrar dene."
    return metin.strip().splitlines()[-1][:300] if metin.strip() else type(exc).__name__


def _secret_yeniden_olustur():
    """Uzak secret kaybolduysa yerel onbellegi yok sayip yeniden yazar."""
    try:
        from bulut_kurulum import hazirla as _hazirla
        return _hazirla(zorla=True, sessiz=True)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _secret_yok_hatasi(metin):
    """Hata mesaji 'isimli secret bulunamadi' ile ilgili mi?"""
    dusuk = metin.lower()
    if SECRET_NAME.lower() in dusuk:
        return True
    return "secret" in dusuk and ("not found" in dusuk or "notfound" in dusuk)


def bulut_cagir(hedef, *args, **kwargs):
    """`.remote()` cagrisini sarar: hatalari BulutHatasi'na cevirir.

    Boylece kanal scriptleri tek yerde anlasilir hata mesaji alir; Modal'in
    ham traceback'i kullaniciyi bogmaz.

    AYRICA: uzaktaki gizli anahtar kaybolmussa (Modal tarafinda silinmis ya da
    hesap/ortam degismis) yerel imza onbellegi bunu GOREMEZ ve ayni hata her
    kosuda tekrarlardi. Bu durumda secret'i BIR KEZ zorla yeniden olusturup
    cagriyi tekrar deneriz; kullanici hicbir sey yapmadan kurtulur."""
    try:
        return hedef.remote(*args, **kwargs)
    except BulutHatasi:
        raise
    except Exception as exc:
        if _secret_yok_hatasi(str(exc)):
            ok, _mesaj = _secret_yeniden_olustur()
            if ok:
                try:
                    return hedef.remote(*args, **kwargs)
                except Exception as exc2:
                    raise BulutHatasi(bulut_hatasi_mesaji(exc2)) from exc2
        raise BulutHatasi(bulut_hatasi_mesaji(exc)) from exc


# retries=0: hata alinca Modal ~40 saniye boyunca 10 kez tekrar deniyordu
# (kota/islem bosa gidiyor, "Durdur" gec calisiyor gibi gorunuyordu).
# Kanal scriptleri zaten videoyu siradaki kosuda yeniden dener, o yuzden
# hizli ve net basarisizlik dogru davranis.
@app.cls(gpu=CLEANER_GPU, image=image, cpu=4, memory=16384, timeout=3600,
         volumes={"/results": results_volume}, secrets=MODAL_SECRETS, retries=0)
class VideoCleaner:
    @modal.method()
    def clean(self, video_bytes: bytes):
        return run_clean(video_bytes)


@app.function(image=image, cpu=4, memory=8192, timeout=3600,
              volumes={"/results": results_volume}, secrets=MODAL_SECRETS, retries=0)
def cloud_orchestrator(link, rand_num, video_bytes, raw_title, tam_metin, eval_topic=False, force=False, source_timeline=None,
                       system_prompt=None, voice_id=None, lang="ru", channel_name=None,
                       voice_prompt=None, title_prompt=None, tags_prompt=None):
    return run_orchestrator(link, rand_num, video_bytes, raw_title, tam_metin, system_prompt, voice_id, lang, channel_name, VideoCleaner, eval_topic, force,
                            voice_prompt=voice_prompt, title_prompt=title_prompt, tags_prompt=tags_prompt, source_timeline=source_timeline)


@app.function(image=image, cpu=2, memory=8192, timeout=1200, gpu="T4",
              secrets=MODAL_SECRETS, retries=0)
def cloud_transcribe(video_bytes: bytes):
    """Zaman damgali transcript Modal GPU'da uretilir (bilgisayar yorulmaz)."""
    import tempfile, os
    tmp = tempfile.mkdtemp()
    vp = os.path.join(tmp, "src.mp4")
    with open(vp, "wb") as f: f.write(video_bytes)
    from functions.transcribe import whisper_ile_zamanli_transkript_cek
    return whisper_ile_zamanli_transkript_cek(vp, model_adi="small")
