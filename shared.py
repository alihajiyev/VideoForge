import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*WindowsSelectorEventLoopPolicy.*")
import os
import sys as _sys


class _TeeLogger:
    """#7: stdout'u ayni anda terminal ve log dosyasina yazar.
    Tek dosyada doner (append); her kanal scripti acilista loglari uzatir."""

    def __init__(self, path):
        self.terminal = _sys.stdout
        try:
            self.file = open(path, "a", encoding="utf-8", buffering=1, errors="replace")
        except Exception:
            self.file = None

    def write(self, data):
        try:
            self.terminal.write(data)
        except Exception:
            pass
        if self.file:
            try:
                self.file.write(data)
            except Exception:
                pass

    def flush(self):
        try:
            self.terminal.flush()
        except Exception:
            pass
        if self.file:
            try:
                self.file.flush()
            except Exception:
                pass


def _setup_file_logging():
    try:
        from datetime import datetime as _dt
        _base = os.path.dirname(os.path.abspath(__file__))
        _log_path = os.path.join(_base, "bot_log.txt")
        _sys.stdout = _TeeLogger(_log_path)
        _stamp = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*60}\n🆕 Oturum basladi: {_stamp}\n{'='*60}")
    except Exception:
        pass  # log dosyasi acilamazsa sessizce stdout'a devam


_setup_file_logging()
import modal
import os
import sys
import time
import random
import re
import math
import difflib
import tempfile
import sqlite3
import base64
import subprocess
import argparse
import yt_dlp
from pathlib import Path

try:
    import winsound
    HAS_WINSOUND = True
except:
    HAS_WINSOUND = False

def beep(success=True):
    if not HAS_WINSOUND:
        print('\a', end='', flush=True)
        return
    if success:
        winsound.Beep(800, 150)
        winsound.Beep(1200, 200)
    else:
        winsound.Beep(200, 400)
        winsound.Beep(150, 600)

def guvenli_klasor_adi(title, max_len=60):
    """Video basligini Windows klasor adina cevirir (haftalik mod ciktisi icin).
    Yasak karakterleri temizler, uzunlugu kisar, bos kalirsa 'video' doner."""
    t = (title or "video").strip()
    for ch in '<>:"/\\|?*':
        t = t.replace(ch, "")
    t = " ".join(t.split())
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0]
    return t.strip() or "video"

def _norm_ver(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return (str(v),)

def ensure_fresh_ytdlp():
    """pip upgrade sonrasi calisan surec hâlâ eski yt-dlp kodunu kullanir
    (import bir kez yapilir). Kurulan surum ile yuklu surum farkliysa
    scripti yeni surumle otomatik yeniden baslatir."""
    try:
        import importlib.metadata as _md
        installed = _md.version("yt-dlp")
    except Exception:
        return
    try:
        loaded = yt_dlp.version.__version__
    except Exception:
        return
    if _norm_ver(installed) != _norm_ver(loaded):
        print(f"🔄 yt-dlp guncellendi ({loaded} → {installed}), yeni surumle yeniden baslatiliyor...")
        a0 = sys.argv[0].replace("/", os.sep)
        if a0.endswith("__main__.py"):
            # 'python -m <pkg> ...' ile baslatilmis: ayni sekilde devam et
            pkg = os.path.basename(os.path.dirname(os.path.abspath(a0)))
            os.execv(sys.executable, [sys.executable, "-m", pkg] + sys.argv[1:])
        elif a0.endswith(".py"):
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            os.execv(a0, sys.argv)

from constants import (
    init_db, link_kayitlimi, link_kaydet, get_url, oneri_kaydet, oneri_getir,
    GPU_COST_PER_SEC, OVERHEAD_SECONDS, FRAMES_PER_GPU, MAX_CONCURRENT_GPUS,
    get_video_duration, get_video_fps,
    GEMINI_API_KEYS, GEMINI_MODELS,
    TEXT_FIXES, SETTINGS, ELEVENLABS_API_KEY,
    API_KEY, API_URL, DB_PATH, results_volume,
    PROC_W, PROC_H, CLEANER_GPU,
)
from functions.transcribe import api_ile_transkript_cek
from functions.gemini_func import gemini_uret
from functions.seo_builder import build_seo_html
from functions.tts_func import tts_verify
from functions.video_proc import run_clean
from functions.orchestrator import run_orchestrator

_BASE = os.path.dirname(os.path.abspath(__file__))

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "wget", "ffmpeg", "libgl1", "libglib2.0-0", "nodejs", "libsndfile1")
    .pip_install("torch", "torchvision", "easyocr", "opencv-python-headless", "numpy", "einops", "scipy", "tqdm", "langdetect", "requests", "matplotlib", "imageio-ffmpeg", "yt-dlp", "google-genai==2.24.0", "pytubefix", "pytube", "elevenlabs", "python-dotenv", "SpeechRecognition", "openai-whisper", "soundfile", "pillow", "git+https://github.com/openai/CLIP.git")
    .run_commands(
        f"git clone {get_url('aHR0cHM6Ly9naXRodWIuY29tL3NjemhvdS9Qcm9QYWludGVyLmdpdA==')} /ProPainter",
        "mkdir -p /ProPainter/weights",
        f"wget -q -O /ProPainter/weights/ProPainter.pth {get_url('aHR0cHM6Ly9naXRodWIuY29tL3NjemhvdS9Qcm9QYWludGVyL3JlbGVhc2VzL2Rvd25sb2FkL3YwLjEuMC9Qcm9QYWludGVyLnB0aA==')}",
        f"wget -q -O /ProPainter/weights/raft-things.pth {get_url('aHR0cHM6Ly9naXRodWIuY29tL3NjemhvdS9Qcm9QYWludGVyL3JlbGVhc2VzL2Rvd25sb2FkL3YwLjEuMC9yYWZ0LXRoaW5ncy5wdGg=')}",
        f"wget -q -O /ProPainter/weights/recurrent_flow_completion.pth {get_url('aHR0cHM6Ly9naXRodWIuY29tL3NjemhvdS9Qcm9QYWludGVyL3JlbGVhc2VzL2Rvd25sb2FkL3YwLjEuMC9yZWN1cnJlbnRfZmxvd19jb21wbGV0aW9uLnB0aA==')}",
        "sed -i 's/imageio.mimwrite/#imageio.mimwrite/g' /ProPainter/inference_propainter.py"
    )
    .run_commands('python -c "import easyocr; easyocr.Reader([\'tr\', \'en\'], gpu=False)"')
    .run_commands('python -c "import clip; clip.load(\'ViT-B/32\', device=\'cpu\')"')
    .add_local_file(os.path.join(_BASE, "shared.py"), "/root/shared.py")
    .add_local_file(os.path.join(_BASE, "constants.py"), "/root/constants.py")
    .add_local_dir(os.path.join(_BASE, "functions"), "/root/functions")
)
