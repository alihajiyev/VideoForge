# -*- coding: utf-8 -*-
"""Ortak Modal bulut katmani (#2 refactor).

Daha once her kanal dosyasi (kinok_syjet, kinosekrety, faktza15) ayni
app + VideoCleaner + cloud_orchestrator + cloud_transcribe bloklarini
kopyaliyordu. Artik TEK yerde tanimli; kanal dosyalari import eder.

Kanal-specific veriler (prompt, voice_id, kanal adi) remote cagriya
parametre olarak gecilir — davranis birebir ayni kalir.

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

app = modal.App("videoforge", image=image)


def _modal_secrets():
    """API anahtarlarini Modal ortamina .env'den enjekte eder (imaja GOMULMEZ).
    .env yoksa bos liste doner; o durumda anahtarlar zaten ortam degiskeninde olmalidir.
    Anahtarlar kodda duz metin tutulmaz (bkz. constants.py)."""
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            return [modal.Secret.from_dotenv(path=os.path.dirname(os.path.abspath(__file__)))]
        print("⚠️ [Bulut] .env bulunamadi - API anahtarlari Modal secret'i ile enjekte edilmeyecek.")
    except Exception as exc:
        print(f"⚠️ [Bulut] Modal secret yuklenemedi: {exc}")
    return []


MODAL_SECRETS = _modal_secrets()


@app.cls(gpu=CLEANER_GPU, image=image, cpu=4, memory=16384, timeout=3600, volumes={"/results": results_volume}, secrets=MODAL_SECRETS)
class VideoCleaner:
    @modal.method()
    def clean(self, video_bytes: bytes):
        return run_clean(video_bytes)


@app.function(image=image, cpu=4, memory=8192, timeout=3600, volumes={"/results": results_volume}, secrets=MODAL_SECRETS)
def cloud_orchestrator(link, rand_num, video_bytes, raw_title, tam_metin, eval_topic=False, force=False, source_timeline=None,
                       system_prompt=None, voice_id=None, lang="ru", channel_name=None,
                       voice_prompt=None, title_prompt=None, tags_prompt=None):
    return run_orchestrator(link, rand_num, video_bytes, raw_title, tam_metin, system_prompt, voice_id, lang, channel_name, VideoCleaner, eval_topic, force,
                            voice_prompt=voice_prompt, title_prompt=title_prompt, tags_prompt=tags_prompt, source_timeline=source_timeline)


@app.function(image=image, cpu=2, memory=8192, timeout=1200, gpu="T4", secrets=MODAL_SECRETS)
def cloud_transcribe(video_bytes: bytes):
    """Zaman damgali transcript Modal GPU'da uretilir (bilgisayar yorulmaz)."""
    import tempfile, os
    tmp = tempfile.mkdtemp()
    vp = os.path.join(tmp, "src.mp4")
    with open(vp, "wb") as f: f.write(video_bytes)
    from functions.transcribe import whisper_ile_zamanli_transkript_cek
    return whisper_ile_zamanli_transkript_cek(vp, model_adi="small")
