import os
import re
import json
import time
import random
import glob
import shutil
import tempfile
import subprocess
import requests
from constants import API_KEY, API_URL, platform_tespit_et

# Bu kosuda transcript API'nin KALICI olarak veremedigi videolar (404/400/410)
# + yetki hatasi bayragi. Sebep: ayni video icin (kesif turu + ana kosu)
# tekrar tekrar ucretli istek atilmasin; kredi ve log bosuna yanmasin.
_API_YOK = set()
_API_YETKI_HATA = False


def _api_anahtar(video_url):
    """API sonucunu hatirlamak icin anahtar (video ID varsa o, yoksa URL)."""
    return _youtube_id(video_url) or (video_url or "").strip()


def _api_cevap_hata(response, anahtar):
    """200 disi cevabi siniflandirir. True: cagri sahibi temiz cikmali (None)."""
    global _API_YETKI_HATA
    kod = response.status_code
    if kod in (400, 404, 410):
        # Bu video icin transcript YOK (video kaldirilmis/bolgeye kapali ya da
        # hic altyazisi yok). Kalici: 3 kez tekrar denemek anlamsiz.
        _API_YOK.add(anahtar)
        print(f"ℹ️ [Bulut] Transcript API bu videoda transcript veremiyor (HTTP {kod}) — diger altyazi yollari denenecek.")
        return True
    if kod in (401, 403):
        _API_YETKI_HATA = True
        print(f"❌ [Bulut] Transcript API yetki/kredi hatasi (HTTP {kod}): TRANSCRIPT_API_KEY ve bakiyeni kontrol et.")
        return True
    print(f"❌ [Bulut] Transcript API hatasi: {kod} - {response.text[:200]}")
    return True


def api_ile_transkript_cek(video_url):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {"video_url": video_url, "format": "text", "include_timestamp": "false"}
    anahtar = _api_anahtar(video_url)
    if _API_YETKI_HATA or anahtar in _API_YOK:
        return None
    for attempt in range(3):
        try:
            response = requests.get(API_URL, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                return response.json().get("transcript", "")
            elif response.status_code in (408, 429, 500, 502, 503, 504):
                print(f"⚠️ [Bulut] Transcript API gecici hata ({response.status_code}), tekrar deneniyor... ({attempt+1}/3)")
                time.sleep(2 * (attempt + 1))
                continue
            else:
                _api_cevap_hata(response, anahtar)
                return None
        except Exception as e:
            print(f"❌ [Bulut] Transcript API baglanti hatasi: {e}")
            if attempt < 2:
                time.sleep(2)
                continue
            return None
    return None

def api_ile_transkript_chunk_cek(video_url):
    """Fetch the transcript with per-chunk timings (start + duration, seconds)."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {"video_url": video_url, "format": "json", "include_timestamp": "true"}
    anahtar = _api_anahtar(video_url)
    if _API_YETKI_HATA or anahtar in _API_YOK:
        return []
    for attempt in range(3):
        try:
            response = requests.get(API_URL, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                chunks = data.get("transcript") or []
                return [
                    {
                        "text": str(c.get("text") or ""),
                        "start": float(c.get("start") or 0),
                        "duration": float(c.get("duration") or 0),
                    }
                    for c in chunks
                    if isinstance(c, dict) and c.get("text")
                ]
            elif response.status_code in (408, 429, 500, 502, 503, 504):
                print(f"⚠️ [Bulut] Transcript API gecici hata ({response.status_code}), tekrar deneniyor... ({attempt+1}/3)")
                time.sleep(2 * (attempt + 1))
                continue
            else:
                _api_cevap_hata(response, anahtar)
                return []
        except Exception as e:
            print(f"❌ [Bulut] Transcript API baglanti hatasi: {e}")
            if attempt < 2:
                time.sleep(2)
                continue
            return []
    return []

def transkript_zaman_cizelgesi(video_url):
    """Merged sentence-level timeline: [{text, start, end}] in seconds.
    yt-dlp altyazi (ucretsiz) -> API (yedek) -> bos."""
    vid = _youtube_id(video_url)
    if vid:
        _, sentences = fetch_subs_zamanli(vid)
        if sentences:
            return sentences
    print("⚠️ yt-dlp altyazi vermedi, Transcript API deneniyor (yedek)...")
    chunks = api_ile_transkript_chunk_cek(video_url)
    sentences = []
    cur_text, cur_start, cur_end = [], None, None
    for c in chunks:
        t = re.sub(r'\[[^\]]*\]', '', c["text"]).strip()
        if not t:
            continue
        if cur_start is None:
            cur_start = c["start"]
        cur_text.append(t)
        cur_end = c["start"] + c["duration"]
        if re.search(r'[.!?]["»)\]]?$', t):
            sentences.append({"text": " ".join(cur_text).strip(), "start": round(cur_start, 2), "end": round(cur_end, 2)})
            cur_text, cur_start, cur_end = [], None, None
    if cur_text and cur_start is not None:
        sentences.append({"text": " ".join(cur_text).strip(), "start": round(cur_start, 2), "end": round(cur_end, 2)})
    return sentences

def transkript_cek_zamanli(link, video_path=None):
    """One-pass fetch: returns (transcript_text, source_timeline).
    source_timeline = [{'text','start','end'}] in seconds for the SOURCE video,
    [] if timings unavailable (fallback paths)."""
    platform = platform_tespit_et(link)
    if platform == "youtube":
        # Once ucretsiz yt-dlp altyazisi, olmazsa Transcript API (tek tur).
        timeline = transkript_zaman_cizelgesi(link)
        if timeline:
            text = " ".join(s["text"] for s in timeline)
            return text, timeline
        # Altyazi/API yok: yerel videodan ZAMAN damgali Whisper. Eskiden burada
        # transkript_cek() cagrilip altyazi + API IKINCI kez deniyordu (bosa
        # istek + log kalabaligi), sonra zamansiz whisper'a dusuluyordu.
        if video_path:
            print("🎙️ Altyazi/API yok — yerel videodan zaman damgali Whisper uretiliyor...")
            text, tl = whisper_ile_zamanli_transkript_cek(video_path)
            if text:
                return text, tl
            text = whisper_ile_transkript_cek(video_path)
            return (text or None), []
        text = transkript_cek(link)
        return (text if text else None), []
    if platform in ("tiktok", "instagram") and video_path:
        print("🌐 Ucretsiz altyazi deneniyor...")
        alt = yt_dlp_ile_alt_yazi_cek(link)
        if alt:
            return alt, []
        print("🎙️ Zaman damgali transcript Whisper ile uretiliyor (biraz surebilir)...")
        text, tl = whisper_ile_zamanli_transkript_cek(video_path)
        if text:
            return text, tl
    text = transkript_cek(link, video_path)
    return (text if text else None), []

def whisper_ile_zamanli_transkript_cek(video_path, model_adi="small"):
    """Timed transcript via openai-whisper: returns (text, timeline) with
    real per-sentence start/end seconds measured from the video's audio."""
    try:
        import whisper
    except Exception:
        print("⚠️ openai-whisper kurulu degil, zamansiz transkripte dusuluyor.")
        return None, []
    tmp = tempfile.mkdtemp()
    wav_path = os.path.join(tmp, "audio.wav")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            wav_path
        ], capture_output=True, check=True)
        model = whisper.load_model(model_adi)
        result = model.transcribe(wav_path)
        sentences = []
        cur_text, cur_start, cur_end = [], None, None
        for seg in result.get("segments", []):
            t = re.sub(r'\[[^\]]*\]', '', (seg.get("text") or "")).strip()
            if not t:
                continue
            if cur_start is None:
                cur_start = float(seg.get("start") or 0)
            cur_text.append(t)
            cur_end = float(seg.get("end") or cur_start)
            if re.search(r'[.!?]["»)\]]?$', t):
                sentences.append({"text": " ".join(cur_text).strip(), "start": round(cur_start, 2), "end": round(cur_end, 2)})
                cur_text, cur_start, cur_end = [], None, None
        if cur_text and cur_start is not None:
            sentences.append({"text": " ".join(cur_text).strip(), "start": round(cur_start, 2), "end": round(cur_end, 2)})
        text = " ".join(s["text"] for s in sentences)
        print(f"✅ Zaman damgali transcript hazir: {len(sentences)} cumle.")
        return (text if text else None), sentences
    except Exception as e:
        print(f"⚠️ Zamanli Whisper hatasi: {e}")
        return None, []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def whisper_ile_transkript_cek(video_path, dil=None):
    try:
        import speech_recognition as sr
    except Exception:
        print("⚠️ speech_recognition kurulu degil, zamansiz Whisper yedegi atlaniyor.")
        return None
    tmp = tempfile.mkdtemp()
    wav_path = os.path.join(tmp, "audio.wav")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            wav_path
        ], capture_output=True, check=True)
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
        kwargs = {"model": "small"}
        if dil:
            kwargs["language"] = dil
        text = r.recognize_whisper(audio, **kwargs)
        return text
    except Exception as e:
        print(f"⚠️ Whisper hatasi: {e}")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _cookiefile():
    """Proje kokundeki cookies.txt varsa yolu, yoksa None.
    Hassas/yasli-kisitli videolarda altyazi cekimi giris gerektirir."""
    try:
        adaylar = [
            os.path.join(os.getcwd(), "cookies.txt"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cookies.txt"),
        ]
        for p in adaylar:
            if p and os.path.exists(p):
                return p
    except Exception:
        pass
    return None

def yt_dlp_ile_alt_yazi_cek(link):
    import yt_dlp
    tmp = tempfile.mkdtemp()
    try:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "tr"],
            "subtitlesformat": "vtt",
            "outtmpl": os.path.join(tmp, "%(id)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ignoreerrors": True,
        }
        cf = _cookiefile()
        if cf:
            ydl_opts["cookiefile"] = cf
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([link])
        for f in os.listdir(tmp):
            if f.endswith(".vtt"):
                with open(os.path.join(tmp, f), "r", encoding="utf-8") as fh:
                    return _parse_vtt(fh.read())
        return None
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _parse_vtt(vtt_text):
    lines = []
    for line in vtt_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:") or "-->" in line or line.isdigit():
            continue
        lines.append(line)
    return " ".join(lines)

def _youtube_id(url):
    m = re.search(r'(?:v=|/shorts/|youtu\.be/|/embed/|/live/)([A-Za-z0-9_-]{11})', url or "")
    return m.group(1) if m else None


def _dedupe_blocks(text):
    """Otomatik altyazidaki art arda tekrar eden kelime bloklarini temizler."""
    words = text.split()
    changed = True
    while changed:
        changed = False
        out, i, n = [], 0, len(words)
        while i < n:
            matched = False
            for L in range(min(12, (n - i) // 2), 0, -1):
                if words[i:i + L] == words[i + L:i + 2 * L]:
                    out.extend(words[i:i + L])
                    i += 2 * L
                    matched, changed = True, True
                    break
            if not matched:
                out.append(words[i])
                i += 1
        words = out
    return " ".join(words)


def _vtt_cues(path):
    """VTT/SRT -> [(start, end, text)] gercek zamanli.
    YouTube VTT'leri timestamp ile metin arasina bos satir koyar,
    bu yuzden blok degil satir satir okunur."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception:
        return []
    def ts(t):
        t = t.strip().replace(",", ".")
        parts = t.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            return float(parts[0])
        except Exception:
            return None
    cues = []
    cur_s, cur_e, cur_lines = None, None, []
    def flush():
        nonlocal cur_s, cur_e, cur_lines
        if cur_s is not None and cur_lines:
            text = re.sub(r"<[^>]+>", " ", " ".join(cur_lines))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                cues.append((cur_s, cur_e, text))
        cur_s, cur_e, cur_lines = None, None, []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE", "REGION")):
            continue
        if "-->" in line:
            flush()
            a, _, b = line.partition("-->")
            b = b.split()[0] if b.split() else b
            s, e = ts(a), ts(b)
            if s is None or e is None or e <= s:
                continue
            cur_s, cur_e = s, e
            continue
        if line.isdigit():
            continue
        if cur_s is not None:
            cur_lines.append(line)
    flush()
    return cues


def _srv3_cues(path):
    """srv3/json3 -> [(start, end, text)] gercek zamanli."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        return []
    cues = []
    for ev in data.get("events", []):
        t0 = (ev.get("tStartMs") or 0) / 1000.0
        dur = (ev.get("dDurationMs") or 0) / 1000.0
        text = "".join((seg.get("utf8") or "") for seg in ev.get("segs", []) or []).strip()
        if text and text != "\n" and dur > 0:
            cues.append((t0, t0 + dur, text))
    return cues


def _cues_to_sentences(cues):
    """Cue listesi -> cumle bazli [{text, start, end}]."""
    sentences = []
    cur_text, cur_start, cur_end = [], None, None
    for s, e, t in cues:
        t = re.sub(r'\[[^\]]*\]', '', t).strip()
        if not t:
            continue
        if cur_start is None:
            cur_start = s
        cur_text.append(t)
        cur_end = e
        if re.search(r'[.!?]["»)\]]?$', t):
            sentences.append({"text": _dedupe_blocks(" ".join(cur_text)).strip(), "start": round(cur_start, 2), "end": round(cur_end, 2)})
            cur_text, cur_start, cur_end = [], None, None
    if cur_text and cur_start is not None:
        sentences.append({"text": _dedupe_blocks(" ".join(cur_text)).strip(), "start": round(cur_start, 2), "end": round(cur_end, 2)})
    return [s for s in sentences if s["text"]]


def ytdlp_sub_files(vid):
    """Altyazi dosyalarini indirir, (tmpdir, [dosyalar]) doner. 429 korumali."""
    import yt_dlp
    tmp = tempfile.mkdtemp()
    try:
        time.sleep(random.uniform(3, 6))
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "writesubtitles": True, "writeautomaticsub": True,
            "subtitleslangs": ["en.*", "ru.*", "id.*"],
            "subtitlesformat": "vtt/srv3/ttml/best",
            "outtmpl": os.path.join(tmp, "%(id)s"),
            "retries": 2, "fragment_retries": 2,
            "sleep_requests": 3, "sleep_subtitles": 5, "ignoreerrors": True,
        }
        cf = _cookiefile()
        if cf:
            opts["cookiefile"] = cf
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
        files = [f for f in glob.glob(os.path.join(tmp, "*"))
                 if os.path.splitext(f)[1].lower() in (".vtt", ".srv3", ".json3", ".ttml", ".srt")]
        return tmp, files
    except Exception as e:
        print(f"   ⚠️ altyazi alinamadi ({str(e)[:70]})")
        shutil.rmtree(tmp, ignore_errors=True)
        return None, []


def fetch_subs_zamanli(vid):
    """yt-dlp altyazi -> (metin, zamanli_cumleler). Olmazsa (None, [])."""
    tmp, files = ytdlp_sub_files(vid)
    if not tmp:
        return None, []
    try:
        best = []
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            cues = _srv3_cues(f) if ext in (".srv3", ".json3") else _vtt_cues(f)
            sents = _cues_to_sentences(cues)
            if len(sents) > len(best):
                best = sents
        if not best:
            return None, []
        return " ".join(s["text"] for s in best)[:4000], best
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fetch_subs_ytdlp(vid):
    """yt-dlp altyazi -> duz metin (kesif icin). Olmazsa None."""
    text, _ = fetch_subs_zamanli(vid)
    return text[:2500] if text else None


def transkript_cek(link, video_path=None):
    platform = platform_tespit_et(link)
    if platform == "youtube":
        vid = _youtube_id(link)
        if vid:
            yt_text, _ = fetch_subs_zamanli(vid)
            if yt_text:
                return yt_text
        print("⚠️ yt-dlp altyazi vermedi, API ile deneniyor (yedek)...")
        api_text = api_ile_transkript_cek(link)
        if api_text:
            return api_text
        if video_path:
            print("⚠️ API de vermedi, yerel videodan Whisper ile cekiliyor...")
            text, _tl = whisper_ile_zamanli_transkript_cek(video_path)
            if text:
                return text
            return whisper_ile_transkript_cek(video_path)
        return None
    elif platform == "tiktok":
        alt_text = yt_dlp_ile_alt_yazi_cek(link)
        if alt_text:
            return alt_text
        if video_path:
            print("🎙️ TikTok transcript Whisper ile uretiliyor...")
            result = whisper_ile_transkript_cek(video_path)
            if result:
                return result
        return None
    elif platform == "instagram":
        alt_text = yt_dlp_ile_alt_yazi_cek(link)
        if alt_text:
            return alt_text
        if video_path:
            print("🎙️ Instagram transcript Whisper ile uretiliyor...")
            return whisper_ile_transkript_cek(video_path)
        return None
    return None
