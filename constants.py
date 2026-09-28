import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="modal._utils.async_utils")
import modal
import os
import time
import random
import subprocess
import requests
import yt_dlp
from pathlib import Path
import gc
import re
import math
import difflib
import tempfile
from google import genai
from google.genai import types
import base64
from elevenlabs.client import ElevenLabs
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

# Test links: never recorded in the DB (exempt from duplicate-link tracking)
TEST_LINK_IDS = {"7647993089797164320"}

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS videos (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS oneriler (video_id TEXT PRIMARY KEY, skor REAL, tip TEXT, tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        # Kanal kolonu migrasyonu (eski DB'lerde yoksa ekle)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(oneriler)").fetchall()]
            if "kanal" not in cols:
                conn.execute("ALTER TABLE oneriler ADD COLUMN kanal TEXT DEFAULT '1'")
                conn.execute("UPDATE oneriler SET kanal='1' WHERE kanal IS NULL OR kanal=''")
            # Ayni video iki kanala da onerilebilsin: PK (video_id, kanal) olmali
            pk = [r[1] for r in conn.execute("PRAGMA table_info(oneriler)").fetchall() if r[5] > 0]
            if pk != ["video_id", "kanal"]:
                conn.execute("""CREATE TABLE IF NOT EXISTS oneriler_new
                    (video_id TEXT NOT NULL, skor REAL, tip TEXT, kanal TEXT NOT NULL DEFAULT '1',
                     tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     PRIMARY KEY (video_id, kanal))""")
                conn.execute("""INSERT OR REPLACE INTO oneriler_new (video_id, skor, tip, kanal, tarih)
                    SELECT video_id, skor, tip, COALESCE(NULLIF(kanal,''),'1'),
                           COALESCE(tarih, CURRENT_TIMESTAMP) FROM oneriler""")
                conn.execute("DROP TABLE oneriler")
                conn.execute("ALTER TABLE oneriler_new RENAME TO oneriler")
        except Exception:
            pass

def platform_tespit_et(link: str) -> str:
    link = link.strip()
    if re.search(r'(youtube\.com|youtu\.be)', link):
        return "youtube"
    elif re.search(r'tiktok\.com', link):
        return "tiktok"
    elif re.search(r'instagram\.com', link):
        return "instagram"
    return "youtube"

def _video_id_cek(link: str) -> str:
    platform = platform_tespit_et(link)
    if platform == "youtube":
        m = re.search(r'(?:v=|/shorts/|youtu\.be/|/embed/|/live/)([A-Za-z0-9_-]{11})', link)
        return m.group(1) if m else link.strip()
    elif platform == "tiktok":
        m = re.search(r'/video/(\d+)', link)
        return m.group(1) if m else link.strip()
    elif platform == "instagram":
        m = re.search(r'/(?:reel|p)/([A-Za-z0-9_-]+)', link)
        return m.group(1) if m else link.strip()
    return link.strip()

def link_kayitlimi(link: str) -> bool:
    vid = _video_id_cek(link)
    if vid in TEST_LINK_IDS:
        return False
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT 1 FROM videos WHERE link = ? OR link LIKE ?", (vid, f"%{vid}%")).fetchone()
            return row is not None
    except Exception:
        return False

def link_kaydet(link: str):
    vid = _video_id_cek(link)
    if vid in TEST_LINK_IDS:
        return
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR IGNORE INTO videos (link) VALUES (?)", (vid,))
            conn.commit()
    except Exception:
        pass

def oneri_kaydet(video_id: str, skor: float, tip: str = "", kanal: str = "1"):
    """Kesif onerisini kaydet — ana bot ayni puani kullanir (kanal bazli)."""
    vid = _video_id_cek(video_id)
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO oneriler (video_id, skor, tip, kanal) VALUES (?, ?, ?, ?)",
                         (vid, float(skor), tip or "", str(kanal or "1")))
            conn.commit()
    except Exception:
        pass

def oneri_getir(link: str, kanal: str = None):
    """Videonun kesif puani varsa (skor, tip) doner, yoksa None.
    kanal verilirse sadece o kanalin onerisi dikkate alinir."""
    vid = _video_id_cek(link)
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            if kanal is None:
                row = conn.execute("SELECT skor, tip FROM oneriler WHERE video_id = ?", (vid,)).fetchone()
            else:
                row = conn.execute("SELECT skor, tip FROM oneriler WHERE video_id = ? AND kanal = ?",
                                   (vid, str(kanal))).fetchone()
            return (float(row[0]), row[1]) if row else None
    except Exception:
        return None

def get_working_model():
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='working_model'").fetchone()
            return row[0] if row else None
    except Exception:
        return None

def set_working_model(model_name):
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('working_model', ?)", (model_name,))
            conn.commit()
    except Exception:
        pass

def get_char_limit():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='char_limit'").fetchone()
        return int(row[0]) if row else 500

def set_char_limit(limit):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('char_limit', ?)", (str(limit),))
        conn.commit()

def get_url(b64_str):
    return base64.b64decode(b64_str).decode('utf-8')

OVERHEAD_SECONDS = 75
FRAMES_PER_GPU = 650
MAX_CONCURRENT_GPUS = 10

# ProPainter kalite ayarlari
# SD (HD_MODE=False) -> 540x960  @ L4   ~$0.50-0.60/video (kanitlanmis + unsharp)
# HD (HD_MODE=True)  -> 640x1136 @ L40S ~$0.85/video    (bir tik daha net)
HD_MODE = False
PROC_W, PROC_H = (640, 1136) if HD_MODE else (540, 960)
CLEANER_GPU = "L40S" if HD_MODE else "L4"
GPU_COST_PER_SEC = 0.000542 if HD_MODE else 0.000222

# Akilli yazi filtresi: altyazi/filigran maskelanir, sahne yazisi korunur
# (Superman'in S'i, tabelalar). False -> eski davranis (her OCR yazisi maskelanir)
SMART_TEXT_FILTER = False

# ---------------------------------------------------------------------------
# GIZLI ANAHTARLAR (#12): kodun icinde duz metin TUTULMAZ, VideoForge
# klasorundeki .env dosyasindan okunur (.env .gitignore'da -> repoya girmez).
#   GEMINI_API_KEYS=anahtar1,anahtar2,...
#   ELEVENLABS_API_KEY=...
#   TRANSCRIPT_API_KEY=...
# Sablon icin .env.example dosyasina bakin.
# Bulutta (Modal) ayni degerler modal.Secret.from_dotenv() ile ortam degiskeni
# olarak enjekte edilir (bulut_kanali.py) - .env imaja gomulmez.
# ---------------------------------------------------------------------------


def _load_env_file():
    """Lokal .env dosyasini ortam degiskenlerine yukler.
    python-dotenv varsa onu kullanir, yoksa bagimliliksiz basit ayristirici calisir."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        return
    except Exception:
        pass
    try:
        with open(env_path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


def _env_key_list(name):
    """Virgulle ayrilmis anahtar listesini okur (bosluklar temizlenir)."""
    return [k.strip() for k in os.getenv(name, "").split(",") if k.strip()]


_load_env_file()

GEMINI_API_KEYS = _env_key_list("GEMINI_API_KEYS")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
API_KEY = os.getenv("TRANSCRIPT_API_KEY", "").strip()
API_URL = get_url("aHR0cHM6Ly90cmFuc2NyaXB0YXBpLmNvbS9hcGkvdjIveW91dHViZS90cmFuc2NyaXB0")

if not GEMINI_API_KEYS:
    print("⚠️ GEMINI_API_KEYS bos - VideoForge klasorunde .env dosyasi olusturun (.env.example'a bakin).")
# Model sirasi KOTA TABLOSUNA GORE optimize edildi (AI Studio free tier, key basina):
#   - Flash Lite ailesi  : RPD 500/gun  -> ONCE (botun ana yuku bunlarda)
#   - Flash ailesi       : RPD 20/gun   -> yedek olarak sonda
#   - gemini-2.5-flash   : kaldirildi (404 'no longer available to new users')
#   - gemini-2.5-flash-lite: kaldirildi (eski nesil + bugun kota zaten asilmis 30/20)
GEMINI_MODELS = [
    "gemini-flash-lite-latest",   # RPD 500
    "gemini-3.1-flash-lite",      # RPD 500
    "gemini-3.5-flash-lite",      # RPD 500
    "gemini-3.8-flash",           # RPD 20 (yeni nesil, test edildi: calisiyor)
    "gemini-3-flash-preview",     # RPD 20
    "gemini-3.6-flash",           # RPD 20
    "gemini-3.5-flash",           # RPD 20
    "gemini-3.7-flash",           # RPD 20
]

SETTINGS = {"ELEVENLABS_ENABLED": True}

TEXT_FIXES = {
    "Ğ’ÑĞ½ÑŒÑƒ": "Ğ’ĞµĞ½Ñ", "Ğ²ÑĞ½ÑŒÑƒ": "Ğ²ĞµĞ½Ñ",
    "Ğ’ĞµĞ½Ğ²Ñƒ": "Ğ’ĞµĞ½Ñ", "Ğ²ĞµĞ½Ğ²Ñƒ": "Ğ²ĞµĞ½Ñ",
    "â€”": ", ", "â€“": ", ",
    ": ": " ", ":": " ",
    "\u201c": "", "\u201d": "", "\u2014": " ", "\u2013": " ", "\"": "",
    "MCU": "киновселенная Марвел", "mcu": "киновселенная марвел",
    "Marvel": "Марвел", "marvel": "марвел",
    "YouTube": "Ютьюб", "youtube": "ютьюб",
    "TVA": "УВИ", "tva": "уви", "ТВА": "УВИ", "тва": "уви",
    "Вандакора": "Ваканды", "вандакора": "ваканды",
    "Вандакор": "Ваканда", "вандакор": "ваканда",
    "биУВИ": "битва УВИ", "БиУВИ": "Битва УВИ", "битваУВИ": "битва УВИ",
    "УВИ УВИ": "УВИ", "уви уви": "уви",
    "битва УВИ Тор": "битва — Тор", "битва УВИ Тора": "битва Тора",
    "УВИ Тор": "— Тор", "УВИ Тора": "Тора", "УВИ Тором": "Тором",
    "трейлер Мстители:": "трейлер Мстителей:", "трейлер Мстители ": "трейлер Мстителей ",
    "трейлера Мстители:": "трейлера Мстителей:", "трейлера Мстители ": "трейлера Мстителей ",
    "из трейлера Мстители": "из трейлера Мстителей",
    "Гражданская война": "Противостояние",
    "гражданская война": "противостояние",
    # Peter Parker → Человек-паук (all case forms)
    "Питер Паркер": "Человек-паук", "Питер Паркера": "Человека-паука", "Питеру Паркеру": "Человеку-пауку",
    "Питера Паркера": "Человека-паука", "Питером Паркером": "Человеком-пауком", "Питере Паркере": "Человеке-пауке",
    "питер паркер": "человек-паук", "питер паркера": "человека-паука", "питеру паркеру": "человеку-пауку",
    "питера паркера": "человека-паука", "питером паркером": "человеком-пауком", "питере паркере": "человеке-пауке",
    "Паркер": "Человек-паук", "Паркера": "Человека-паука", "Паркеру": "Человеку-пауку",
    "Паркера": "Человека-паука", "Паркером": "Человеком-пауком", "Паркере": "Человеке-пауке",
    "паркер": "человек-паук", "паркера": "человека-паука", "паркеру": "человеку-пауку",
    "паркера": "человека-паука", "паркером": "человеком-пауком", "паркере": "человеке-пауке",
}

NAME_FIXES = {
    "Каллам": "Кулл", "Каллама": "Кулла", "Калламом": "Куллом", "Калламе": "Кулле",
    "Каллум": "Кулл", "Каллума": "Кулла", "Каллумом": "Куллом",
    "Калл": "Кулл", "Калла": "Кулла", "Каллом": "Куллом",
    "Кузнец Обсидиан": "Кулл Обсидиан", "Кузнеца Обсидиана": "Кулла Обсидиана",
    "Куда Обсидиан": "Кулл Обсидиан",
    "Marvel": "Марвел", "marvel": "марвел",
    "страйкер": "гром-секира", "Страйкер": "Гром-секира", "страйкером": "гром-секирой", "Страйкером": "Гром-секирой",
    "штормбрейкер": "гром-секира", "Штормбрейкер": "Гром-секира", "шторм-брейкер": "гром-секира", "Шторм-брейкер": "Гром-секира",
    "штормбрейкером": "гром-секирой", "Штормбрейкером": "Гром-секирой", "шторм-брейкером": "гром-секирой", "Шторм-брейкером": "Гром-секирой",
    "со гром-секирой": "с гром-секирой", "со гром-секирой,": "с гром-секирой,",
    "громсекира": "гром-секира", "Громсекира": "Гром-секира", "громсекирой": "гром-секирой", "Громсекирой": "Гром-секирой",
    "громсекиры": "гром-секиры", "громсекиру": "гром-секиру", "громсекире": "гром-секире",
    "человеков-пауков": "людей-пауков", "человеков-паука": "людей-паука",
    "всех человеков-пауков": "всех людей-пауков", "всех человеков-паука": "всех людей-паука",
    "темной измерении": "тёмном измерении", "темной измерение": "тёмном измерении",
    "темном измерении": "тёмном измерении",
    "в «Война бесконечности»": "в «Войне бесконечности»", "в «война бесконечности»": "в «войне бесконечности»",
}

# Vague abstract single-word concepts that carry no search volume and are unrelated to a video's
# concrete topic. Filtered out of generated tags deterministically. English + Russian.
GENERIC_TAGS = {
    # Russian
    "солдат", "сердце", "выбор", "технологии", "технология", "наследие", "герой", "герои",
    "преемник", "будущее", "дружба", "судьба", "секрет", "секреты", "сила", "мощь", "правда",
    "ложь", "месть", "любовь", "ненависть", "жизнь", "смерть", "мужество", "мудрость",
    "гений", "успех", "талант", "приключение", "приключения", "магия", "маги", "волшебство",
    "мастерство", "опасность", "предательство", "цель", "мечта", "мечты", "идея", "идеи",
    "знание", "знания", "время", "война", "мир", "история", "истории", "новое", "важное",
    "ответ", "вопрос", "главное", "теория", "теории", "факт", "факты", "тайна", "тайны",
    "решение", "решения", "значение", "ценность", "человек", "люди", "героизм", "подвиг",
    "память", "будущее", "прошлое", "настоящее", "реальность", "опасный", "секретное",
    "уникальность", "способность", "способности", "характер", "личность", "миссия",
    # English
    "soldier", "heart", "choice", "technology", "technologies", "legacy", "hero", "heroes",
    "successor", "future", "friendship", "destiny", "secret", "secrets", "power", "truth",
    "lie", "lies", "revenge", "love", "hate", "life", "death", "courage", "wisdom", "genius",
    "success", "talent", "adventure", "adventures", "magic", "danger", "betrayal", "goal",
    "dream", "dreams", "idea", "ideas", "knowledge", "time", "war", "peace", "story",
    "stories", "answer", "question", "theory", "theories", "fact", "facts", "mystery",
    "mysteries", "decision", "decisions", "meaning", "value", "human", "people", "heroism",
    "memory", "past", "future", "reality", "ability", "abilities", "personality", "mission",
}

# English movie titles (as they appear in English transcripts) → official Russian dub names.
# Used to verify the voiceover names only movies that actually appear in the transcript.
MOVIE_NAMES_RU = {
    "Brand New Day": ["Новый день", "новый день", "нового дня", "новом дне"],
    "Spider-Man: Brand New Day": ["Человек-паук: Новый день", "новый день", "нового дня", "новом дне"],
    "Far From Home": ["Вдали от дома", "вдали от дома"],
    "No Way Home": ["Нет пути домой", "нет пути домой"],
    "Homecoming": ["Возвращение домой", "возвращение домой"],
    "Secret Wars": ["Секретные войны", "секретные войны"],
    "Doomsday": ["Судный день", "судный день", "судном дне", "судного дня"],
    "Avengers Doomsday": ["Мстители: Судный день", "судный день", "судном дне", "судного дня"],
    "Avengers: Doomsday": ["Мстители: Судный день", "судный день", "судном дне", "судного дня"],
    "Avengers: Secret Wars": ["Мстители: Секретные войны", "секретные войны"],
    "Avengers: Endgame": ["Мстители: Финал", "мстители: финал", "финал"],
    "Infinity War": ["Война бесконечности", "война бесконечности"],
    "Civil War": ["Противостояние", "противостояние"],
    "Guardians of the Galaxy": ["Стражи Галактики", "стражи галактики"],
}

# Generic, channel-level topics that must NEVER become a title hashtag.
# Russian only capitalizes proper names inside a sentence, so capitalized words in
# the voiceover body ARE the concrete topics; only these generic ones are filtered out.
GENERIC_TITLE_HASHTAGS = {
    # Channel / brand level
    "марвел", "marvel", "mcu", "мси", "вмc", "dc", "комикс", "комиксы", "вселенная",
    "киновселенная", "кино", "кинo", "фильм", "фильмы", "видео", "шортс", "shorts", "short",
    "youtube", "ютьюб", "история", "истории",
    # Vague / abstract
    "факты", "факт", "интересное", "интересный", "топ", "секрет", "секреты", "тайна",
    "тайны", "герой", "герои", "ответ", "вопрос", "главное", "человек", "люди", "мир",
    "война", "войны", "финал", "день", "время", "сила", "смерть", "жизнь", "что", "почему",
}

def get_video_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.check_output(cmd).decode().strip())

def get_video_fps(path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", path]
    out = subprocess.check_output(cmd).decode().strip()
    try:
        num, den = out.split('/')
        return float(num) / float(den)
    except:
        return 30.0

results_volume = modal.Volume.from_name("fgt-clean-results", create_if_missing=True)

# ПопкорнФакты (3. kanal, eski ad: KinoSujet) konfigürasyonu
CHANNEL_NAME_KINO_SYJET = "ПопкорнФакты"
VOICE_ID_KINO_SYJET = "LHi3adMlU7AICv8Yxpmm"
CHAR_LIMIT_KINO_SYJET = 570  # Varsayılan, transcript oranında ayarlanacak


