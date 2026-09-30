import os
import re
import math
import tempfile
import subprocess
import time
from datetime import datetime, timezone, timedelta

BAKU_TZ = timezone(timedelta(hours=4))

def now_baku():
    return datetime.now(BAKU_TZ)
from elevenlabs.client import ElevenLabs
from constants import SETTINGS, TEXT_FIXES, NAME_FIXES, ELEVENLABS_API_KEY, FRAMES_PER_GPU, MAX_CONCURRENT_GPUS, results_volume, get_video_fps, get_video_duration, OVERHEAD_SECONDS, GPU_COST_PER_SEC, get_char_limit, MOVIE_NAMES_RU, GENERIC_TAGS, PROC_W, PROC_H, CLEANER_GPU, TTS_DOGRULAMA_AKTIF
from functions import maliyet
from functions.transcribe import api_ile_transkript_cek
from functions.gemini_func import gemini_uret, evaluate_topic, run_voice_pipeline, fix_length, reset_gemini_call_stats, gemini_usage_summary, _LAST_HARD_BLOCK
from functions.seo_builder import build_seo_html
from functions.tts_func import tts_verify

def fix_ii(text):
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'(?<![а-яё])ИИ(?![а-яё])|(?<![а-яё])ии(?![а-яё])', 'искусственный интеллект', text)
    text = re.sub(r'\b(с|без|для|у|от|из|до)\s+искусственный\s+интеллект[ом]?\b', r'\1 искусственным интеллектом', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(к|по)\s+искусственный\s+интеллект[у]?\b', r'\1 искусственному интеллекту', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(о|об|в|на|при)\s+искусственный\s+интеллект[е]?\b', r'\1 искусственном интеллекте', text, flags=re.IGNORECASE)
    text = re.sub(r'"([^"]{1,80})"', '«\\1»', text)
    text = re.sub(r'«{2,}', '«', text)
    text = re.sub(r'»{2,}', '»', text)
    # Whitespace & punctuation cleanup (deterministic grammar hygiene)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r' ,', ',', text)
    text = re.sub(r' \.', '.', text)
    text = re.sub(r' \?', '?', text)
    text = re.sub(r' \!', '!', text)
    text = re.sub(r'« ', '«', text)
    text = re.sub(r' »', '»', text)
    for wrong, correct in sorted(NAME_FIXES.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(wrong, correct)
    return text

def verify_movie_names(text, transcript):
    """General rule: a movie named in the voiceover MUST appear in the transcript.
    If the voiceover names a known movie whose (English) title is NOT in the transcript,
    replace it with the primary movie actually discussed in the transcript."""
    if not transcript or not text:
        return text
    tl = transcript.lower()
    # Which movies (by English title) are actually present in the transcript?
    present = [name for name in MOVIE_NAMES_RU if name.lower() in tl]
    if not present:
        return text
    # Primary movie to fall back to = first one found in transcript order
    present_sorted = sorted(present, key=lambda n: tl.index(n.lower()))
    primary_en = present_sorted[0]
    primary_ru = MOVIE_NAMES_RU[primary_en][0]
    # Russian forms that are legitimate (belong to a movie present in the transcript)
    allowed_forms = {form for name in present for form in MOVIE_NAMES_RU[name]}
    # Find known movies mentioned in the voiceover that are NOT in the transcript
    # (check both English titles and their Russian forms)
    for en_name, ru_forms in MOVIE_NAMES_RU.items():
        if en_name in present:
            continue
        # If any meaningful word of this title appears in the transcript, treat it as
        # connected to the video topic (e.g. "Doomsday" inside "Avengers Doomsday") — skip.
        tokens = [w for w in re.findall(r"[A-Za-z']+", en_name) if len(w) > 2]
        if any(w.lower() in tl for w in tokens):
            continue
        # English title itself mentioned (e.g. "no way home" in tags)
        if en_name.lower() in text.lower():
            print(f"[Bulut] Yanlis film adi duzeltiliyor (EN): '{en_name}' -> '{primary_ru}' (transcript: {primary_en})")
            text = re.sub(re.escape(en_name), primary_ru, text, flags=re.IGNORECASE)
        for form in ru_forms:
            if form in text:
                # Only replace if this form is NOT covered by a legitimately-present movie
                if form in allowed_forms:
                    continue
                print(f"[Bulut] Yanlis film adi duzeltiliyor: '{form}' -> '{primary_ru}' (transcript: {primary_en})")
                text = text.replace(form, primary_ru)
                break
    return text


def missing_movie_names(text, transcript):
    """Return Russian forms of transcript-mentioned movies that are NOT present in the text."""
    if not transcript or not text:
        return []
    tl = transcript.lower()
    present = [name for name in MOVIE_NAMES_RU if name.lower() in tl]
    missing = []
    for name in present:
        forms = MOVIE_NAMES_RU[name]
        if not any(form.lower() in text.lower() for form in forms):
            missing.append(forms[0])
    return missing

def _fmt_mmss(sec):
    sec = max(0, int(round(sec)))
    return f"{sec // 60:02d}:{sec % 60:02d}"

def _split_sentences(text):
    parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or "").strip()) if s.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])

def _audio_duration_sec(audio_bytes):
    import tempfile as _tf
    p = os.path.join(_tf.mkdtemp(), "voice.mp3")
    with open(p, "wb") as f:
        f.write(audio_bytes)
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", p]).decode().strip()
        return float(out)
    except Exception:
        return 0.0

def build_voice_timeline(voice_text, audio_bytes):
    sents = _split_sentences(voice_text)
    if not sents or not audio_bytes:
        return [], 0.0
    try:
        total = _audio_duration_sec(audio_bytes)
    except Exception as e:
        print(f"⚠️ [Bulut] Ses suresi olculemedi: {e}")
        return [], 0.0
    if total <= 0:
        return [], 0.0
    weights = [max(1, len(s)) for s in sents]
    wsum = sum(weights)
    timeline = []
    cursor = 0.0
    for i, s in enumerate(sents):
        dur = total * weights[i] / wsum
        start = cursor
        end = total if i == len(sents) - 1 else cursor + dur
        timeline.append({"sentence": s, "start": _fmt_mmss(start), "end": _fmt_mmss(end)})
        cursor = end
    return timeline, total

def map_voice_to_beats_sec(voice_text, source_timeline):
    """Map voiceover sentences onto the SOURCE video timeline proportionally
    by character position (voiceover is a paraphrase of the transcript, so its
    sentence boundaries map by relative position). Returns [{'sentence','start','end'}]
    with times as float seconds."""
    sents = _split_sentences(voice_text)
    if not sents or not source_timeline:
        return []
    chars = [max(1, len(s["text"])) for s in source_timeline]
    starts = [float(s.get("start") or 0) for s in source_timeline]
    ends = [float(s.get("end") or 0) for s in source_timeline]
    total_chars = sum(chars)
    if total_chars <= 0:
        return []

    def t_at(pos):
        acc = 0.0
        for k, n in enumerate(chars):
            a, b = acc, acc + n
            if pos <= b or k == len(chars) - 1:
                local = 0.0 if b <= a else min(max((pos - a) / (b - a), 0.0), 1.0)
                return starts[k] + local * (ends[k] - starts[k])
            acc = b
        return ends[-1]

    total_voice = sum(max(1, len(s)) for s in sents)
    out = []
    cum = 0
    for i, s in enumerate(sents):
        a = cum / total_voice * total_chars
        cum += max(1, len(s))
        b = cum / total_voice * total_chars
        end = ends[-1] if i == len(sents) - 1 else t_at(b)
        out.append({"sentence": s, "start": round(t_at(a), 2), "end": round(end, 2)})
    return out

def map_voice_to_beats(voice_text, source_timeline):
    """Same as map_voice_to_beats_sec but with times as MM:SS strings."""
    return [
        {"sentence": b["sentence"], "start": _fmt_mmss(b["start"]), "end": _fmt_mmss(b["end"])}
        for b in map_voice_to_beats_sec(voice_text, source_timeline)
    ]

def _norm_word(w):
    return re.sub(r'[^\w]', '', (w or '').lower())

def group_words_to_sentences(words, sentences):
    """Align a flat Whisper word list onto known sentences via word-level
    difflib matching (tolerates Whisper mis-hearings). words =
    [{'word','start','end'}]. Returns [{'sentence','start','end'}] in float
    seconds, or None on failure."""
    try:
        import difflib as _dl
        if not words or not sentences:
            return None
        exp_words, owner = [], []
        for si, sent in enumerate(sentences):
            ws = [_norm_word(w) for w in re.findall(r'\S+', sent) if _norm_word(w)]
            if not ws:
                continue
            for w in ws:
                exp_words.append(w)
                owner.append(si)
        rec_idx = [i for i, w in enumerate(words) if _norm_word(w.get("word", ""))]
        rec_clean = [_norm_word(words[i].get("word", "")) for i in rec_idx]
        if not exp_words or not rec_clean:
            return None
        sm = _dl.SequenceMatcher(None, exp_words, rec_clean, autojunk=False)
        if sm.ratio() < 0.45:
            return None
        # expected position -> recognized-clean position (equal blocks only)
        mapping = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for a, b in zip(range(i1, i2), range(j1, j2)):
                    mapping[a] = b
        out = []
        prev_end = 0.0
        for si, sent in enumerate(sentences):
            times = []
            for ei in [k for k, o in enumerate(owner) if o == si]:
                if ei in mapping:
                    wi = rec_idx[mapping[ei]]
                    times.append((float(words[wi].get("start") or 0), float(words[wi].get("end") or 0)))
            if len(times) < 2:
                return None
            s = max(min(t[0] for t in times), prev_end)
            e = max(t[1] for t in times)
            if e <= s:
                return None
            out.append({"sentence": sent, "start": round(s, 2), "end": round(e, 2)})
            prev_end = e
        if len(out) != len([s for s in sentences if [w for w in re.findall(r'\S+', s) if _norm_word(w)]]):
            return None
        return out
    except Exception:
        return None

# Whisper modeli modul seviyesinde bir kez yuklenir. Modal ayni fonksiyon icin
# sicak konteyneri yeniden kullanabildigi icin bu, video basina model indirme +
# yukleme suresini (ve dolayisiyla faturalanan konteyner suresini) keser.
_WHISPER_MEASURE_MODEL = None


def _olcum_modeli(_wh):
    global _WHISPER_MEASURE_MODEL
    if _WHISPER_MEASURE_MODEL is None:
        print("🎙️ [Bulut] Whisper (small) olcum modeli yukleniyor (bir kez)...")
        _WHISPER_MEASURE_MODEL = _wh.load_model("small")
    return _WHISPER_MEASURE_MODEL


def measure_voice_times(voice_text, audio_bytes):
    """Measure REAL per-sentence timings of the produced voiceover MP3 with
    Whisper word timestamps (runs in cloud, no extra TTS credits).
    Returns [{'sentence','start','end'}] in float seconds, or None."""
    try:
        import whisper as _wh
    except Exception as e:
        print(f"⚠️ [Bulut] Whisper yok, ses olcumu atlaniyor: {e}")
        return None
    sents = _split_sentences(voice_text)
    if not sents or not audio_bytes:
        return None
    tmp = tempfile.mkdtemp()
    try:
        mp3 = os.path.join(tmp, "voice_meas.mp3")
        with open(mp3, "wb") as f:
            f.write(audio_bytes)
        model = _olcum_modeli(_wh)
        result = model.transcribe(mp3, word_timestamps=True, language="ru")
        words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                if w.get("word", "").strip():
                    words.append({"word": w["word"].strip(), "start": float(w.get("start", 0)), "end": float(w.get("end", 0))})
        if not words:
            print("⚠️ [Bulut] Whisper kelime uretemedi, tahmini dagitima dusuluyor.")
            return None
        grouped = group_words_to_sentences(words, sents)
        if grouped:
            print(f"✅ [Bulut] Gercek ses zamanlari olculdu: {len(grouped)} cumle.")
            return grouped
        print("⚠️ [Bulut] Kelime-cumle hizalama basarisiz, tahmini dagitima dusuluyor.")
        return None
    except Exception as e:
        print(f"⚠️ [Bulut] Ses olcum hatasi: {e}")
        return None
    finally:
        import shutil as _sh
        _sh.rmtree(tmp, ignore_errors=True)

def build_video_beat_map(voice_text, source_timeline, fallback_duration):
    """Map voiceover sentences onto the ORIGINAL video timeline.
    Uses real transcript segment timings when available; otherwise falls back
    to proportional mapping over the video duration. Times as MM:SS strings."""
    beats = map_voice_to_beats(voice_text, source_timeline) if source_timeline else []
    if beats:
        return beats
    sents = _split_sentences(voice_text)
    if not sents or not fallback_duration or fallback_duration <= 0:
        return []
    total = float(fallback_duration)
    weights = [max(1, len(s)) for s in sents]
    wsum = sum(weights)
    cursor = 0.0
    out = []
    for i, s in enumerate(sents):
        end = total if i == len(sents) - 1 else cursor + total * weights[i] / wsum
        out.append({"sentence": s, "start": _fmt_mmss(cursor), "end": _fmt_mmss(end)})
        cursor = end
    return out

def _thumb_esc(t):
    t = (t or "").replace("\\", "\\\\").replace(":", "\\:").replace("%", "\\%").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")
    return t.strip()


def build_thumbnail(video_path, title_text, tmp_dir, rand_num, topic_query=""):
    """Profesyonel 9:16 kapak: konu-ilgili + en keskin kare, yuz algilamali
    kadraj, yuzle cakismayan dev yazi + okunabilirlik bandi. Donus: PNG bytes/None."""
    import urllib.request
    font_path = os.path.join(tmp_dir, "RussoOne-Regular.ttf")
    if not os.path.exists(font_path) or os.path.getsize(font_path) < 10000:
        urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/russoone/RussoOne-Regular.ttf", font_path)
    dur = get_video_duration(video_path)
    # 1) Aday kareler (videonun tamami, 12 nokta): keskinlik + yuz bonusu - yazi bandi cezasi.
    #    Eskiden sadece %20-55 arasi 6 kareye bakiliyordu; hook genelde basta, kilit an sonda olur.
    import cv2
    import math as _math
    fracs = [0.05 + i * (0.90 / 11) for i in range(12)]
    cands = []
    for frac in fracs:
        fp = os.path.join(tmp_dir, f"thumb_cand_{rand_num}_{int(frac*100)}.jpg")
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(round(dur * frac, 2)), "-i", video_path, "-frames:v", "1", "-q:v", "2", fp], check=True)
            img = cv2.imread(fp)
        except Exception:
            img = None
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        bright = float(gray.mean())
        h0 = gray.shape[0]
        band = gray[int(h0 * 0.72):, :]
        band_edge = float(cv2.Laplacian(band, cv2.CV_64F).var()) if band.size else 0.0
        cands.append({"img": img, "sharp": sharp, "bright": bright,
                      "band_ratio": band_edge / (sharp + 1e-6), "face": None, "face_frac": 0.0})
    if not cands:
        return None
    # Cok karanlik / patlak kareleri ele (hepsi elenirse vazgec, hepsini tut)
    ok_c = [c for c in cands if 40.0 <= c["bright"] <= 240.0]
    pool = ok_c if ok_c else cands
    pool.sort(key=lambda c: -c["sharp"])
    # 2) Bulaniklik eleme: en keskin karenin %3'unden dusuk olanlar elenir
    #    (hepsi elenirse vazgecilir). Baraj bilerek gevsek: yumusak ama konulu
    #    kareler yarisabilir, sadece motion-blur copu elenir. Konu birincil
    #    kriter oldugu icin keskinlik artik siralama degil, eleme yapar.
    max_sharp_all = max(c["sharp"] for c in pool)
    _blur_cut = max(30.0, 0.03 * max_sharp_all)
    gated = [c for c in pool if c["sharp"] >= _blur_cut]
    if not gated:
        gated = pool
    # 3) Kalanlarda yuz ara (YuNet bir kez yuklenir)
    face = None
    try:
        yunet_path = os.path.join(tmp_dir, "face_detection_yunet_2023mar.onnx")
        if not os.path.exists(yunet_path) or os.path.getsize(yunet_path) < 100000:
            urllib.request.urlretrieve("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", yunet_path)
        detector = None
        for c in gated:
            fh, fw = c["img"].shape[:2]
            if detector is None:
                detector = cv2.FaceDetectorYN_create(yunet_path, "", (fw, fh))
            else:
                try:
                    detector.setInputSize((fw, fh))
                except Exception:
                    pass
            _, faces = detector.detect(c["img"])
            if faces is not None:
                scored = [f for f in faces if len(f) > 14 and float(f[14]) > 0.6]
                if scored:
                    b = max(scored, key=lambda f: float(f[2]) * float(f[3]))
                    c["face"] = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                    c["face_frac"] = (float(b[2]) * float(b[3])) / max(1.0, float(fw * fh))
        print(f"[Bulut] Kapak: {sum(1 for c in gated if c['face'])} adayda yuz bulundu.")
    except Exception as e:
        print(f"[Bulut] Yuz algilama atlandi: {str(e)[:80]}")
    # 4) Konu-ilgisi (CLIP, ViT-B/32): KALAN TUM kareler konuyla puanlanir.
    #     Basarisiz olursa sessizce eski skora donulur (bot kirilmaz).
    _clip_ok = False
    if topic_query:
        try:
            import torch
            import clip as clip_lib
            from PIL import Image as _PILImage
            _device = "cuda" if torch.cuda.is_available() else "cpu"
            _model, _pre = clip_lib.load("ViT-B/32", device=_device)
            _tok = clip_lib.tokenize([topic_query[:70]]).to(_device)
            with torch.no_grad():
                _tfeat = _model.encode_text(_tok)
                _tfeat = _tfeat / _tfeat.norm(dim=-1, keepdim=True)
            _targets = gated
            _ims = []
            for c in _targets:
                h_c, w_c = c["img"].shape[:2]
                cw_c = int(h_c * 9 / 16)
                if c["face"] is not None:
                    fx_c = c["face"][0] + c["face"][2] / 2
                    x0_c = int(min(max(fx_c - cw_c / 2, 0), max(0, w_c - cw_c)))
                else:
                    x0_c = max(0, (w_c - cw_c) // 2)
                _ims.append(_PILImage.fromarray(cv2.cvtColor(c["img"][:, x0_c:x0_c + cw_c], cv2.COLOR_BGR2RGB)))
            with torch.no_grad():
                _ifeat = _model.encode_image(torch.stack([_pre(im) for im in _ims]).to(_device))
                _ifeat = _ifeat / _ifeat.norm(dim=-1, keepdim=True)
                _sims = (_ifeat @ _tfeat.T).squeeze(1).tolist()
            if isinstance(_sims, float):
                _sims = [_sims]
            for c, _s in zip(_targets, _sims):
                c["clip_raw"] = float(_s)
            _clip_ok = True
            print(f"[Bulut] Kapak: konu-ilgisi (CLIP) uygulandi: '{topic_query[:40]}'")
        except Exception as e:
            print(f"[Bulut] CLIP atlandi (eski skorla devam): {str(e)[:80]}")
    # 5) Skor: konu skorlari ayrisiyorsa KONU-BIRINCIL, yoksa klasik.
    #    Soyut konuda ("neden", "sir") CLIP tum karelere benzer puan verir,
    #    ayrisma dusuk olur ve otomatik klasik moda dusulur.
    _sims_all = [c.get("clip_raw", 0.0) for c in gated]
    _spread = (max(_sims_all) - min(_sims_all)) if _sims_all else 0.0
    _topic_first = bool(topic_query) and _clip_ok and _spread >= 0.03
    for c in gated:
        c["clip"] = ((c.get("clip_raw", 0.0) - min(_sims_all)) / (_spread + 1e-6)) if _spread > 0 else 0.0
    max_sharp = max(c["sharp"] for c in gated)
    def _score(c):
        sharp_n = _math.log1p(c["sharp"]) / _math.log1p(max_sharp + 1e-6)
        # Yuz bonusu: cok kucuk yuzler genelde yanlis alarm, dev yuzler
        # (asiri yakin plan) kirpinca taninmaz hale gelir.
        ff = c["face_frac"]
        if 0.02 <= ff <= 0.55:
            face_b = min(1.5, ff * 5.0)
        elif ff > 0.55:
            face_b = -0.8
        else:
            face_b = 0.0
        text_p = min(1.2, max(0.0, c["band_ratio"] - 1.6) * 0.8)
        if _topic_first:
            return c.get("clip", 0.0) * 2.0 + face_b * 0.5 + sharp_n * 0.5 - text_p
        return sharp_n + face_b + c.get("clip", 0.0) * 1.2 - text_p
    if _topic_first:
        print(f"[Bulut] Kapak: konu-birincil mod (ayrisma {_spread:.3f}).")
    else:
        print(f"[Bulut] Kapak: klasik mod (konu ayrismadi).")
    best = max(gated, key=_score)
    best_img, best_score = best["img"], best["sharp"]
    face = best["face"]
    if face is not None:
        print(f"[Bulut] Kapak: yuzlu kare secildi, yazi yuzle cakismayacak.")
    # 3) Basliktan kisa kapak yazisi (max 4 kelime, emoji/hashtag yok, buyuk harf)
    clean = re.sub(r'#\S+', ' ', title_text or "")
    clean = re.sub(r'[\U0001F300-\U0010FFFF»«"“”]+', ' ', clean).replace(":", " ").strip()
    words = clean.split()
    if len(words) > 4:
        words = words[:4]
    if not words:
        return None
    # 4) 9:16 kirp — yuz varsa yuz ortali, yuz ustteyse yazi alta ve tersi
    h, w = best_img.shape[:2]
    cw = int(h * 9 / 16)
    if face is not None:
        fx = face[0] + face[2] / 2
        x0 = int(min(max(fx - cw / 2, 0), max(0, w - cw)))
        face_cy = (face[1] + face[3] / 2) / h
        text_top = face_cy < 0.5
    else:
        x0 = max(0, (w - cw) // 2)
        text_top = True
    # Efekt YOK: kirp + duz resize, fotograf oldugu gibi kalir.
    # (Kontrast/doygunluk/unsharp, dusuk kaliteli karelerde bantlanma yapiyordu.)
    crop = best_img[:, x0:x0 + cw]
    crop = cv2.resize(crop, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
    from PIL import Image, ImageDraw, ImageFont
    pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).convert("RGBA")
    # Yazi: kontur disinda arka plan karartma yok, foto tertemiz durur.
    draw = ImageDraw.Draw(pil)

    def _tw(ln, size):
        f = ImageFont.truetype(font_path, size)
        bb = draw.textbbox((0, 0), ln, font=f, stroke_width=7)
        return bb[2] - bb[0], f

    # Satir dagilimi: en dengeli bolunme (piksel genisligine gore)
    up = [w.upper() for w in words]
    if len(up) <= 2:
        lines = [" ".join(up)]
    else:
        best, best_m = None, None
        for k in range(1, len(up)):
            l1, l2 = " ".join(up[:k]), " ".join(up[k:])
            m = max(_tw(l1, 150)[0], _tw(l2, 150)[0])
            if best_m is None or m < best_m:
                best, best_m = [l1, l2], m
        lines = best
    lines = [l[:26] for l in lines if l]
    # Otomatik sigdirma + yuzle cakismayan konum
    rendered = []
    for ln in lines[:2]:
        size = 150
        tw, font = _tw(ln, size)
        while tw > 980 and size > 64:
            size -= 10
            tw, font = _tw(ln, size)
        rendered.append((ln, font, tw, size))
    total_h = sum(s + 50 for _, _, _, s in rendered)
    y = 140 if text_top else 1920 - 140 - total_h
    for ln, font, tw, size in rendered:
        draw.text(((1080 - tw) / 2, y), ln, font=font, fill="#FFDD00",
                  stroke_width=7, stroke_fill="black")
        y += size + 50
    out_path = os.path.join(tmp_dir, f"thumb_{rand_num}.png")
    pil.convert("RGB").save(out_path)
    with open(out_path, "rb") as f:
        return f.read()

def run_orchestrator(link, rand_num, video_bytes, raw_title, tam_metin, system_prompt, voice_id, lang, channel_name, VideoCleanerClass, eval_topic=False, force=False, voice_prompt=None, title_prompt=None, tags_prompt=None, source_timeline=None):
    print(f"\n☁️ [BULUT] Sunucu aktif edildi. Yerelden gelen video isleniyor...")
    process_start = now_baku()
    reset_gemini_call_stats()  # #8: video basina Gemini kullanim sayaci
    tmp_dir = tempfile.mkdtemp()
    clean_title = re.sub(r'[\\/*?:"<>|]', "", raw_title).replace(" ", "_")
    gercek_ham_yol = os.path.join(tmp_dir, f"raw_video_{rand_num}.mp4")
    with open(gercek_ham_yol, "wb") as f: f.write(video_bytes)
    try:
        source_dur = get_video_duration(gercek_ham_yol)
    except Exception:
        source_dur = 0
    print("🌐 [Bulut] Yerel transkript kullaniliyor...")
    if not tam_metin:
        print(f"❌ [Bulut] Transkript yok, islem durduruluyor.")
        return {"prompt_user": False, "score": 0, "error": "Transcript fetch failed", "video_bytes": None, "seo_html": "", "audio_bytes": None, "title": clean_title, "gpu_wall_time": 0, "num_chunks": 0}
    if eval_topic and not force:
        score = evaluate_topic(tam_metin, raw_title, channel_name)
        print(f"📊 [Bulut] Konu puani: {score}/10")
        if score < 2:
            return {"error": f"Puan dusuk ({score}/10). Konu yeterli degil, islem atlaniyor. --force flag'i ile atlayabilirsin.", "video_bytes": None, "seo_html": "", "audio_bytes": None, "title": clean_title, "gpu_wall_time": 0, "num_chunks": 0}
        print("✅ [Bulut] Konu puani yeterli, devam ediliyor...")
    # Stage 1: Run decomposed pipeline (each rule sequential, targeted fixes only)
    # Char limit is channel-aware:
    # - ПопкорнФакты (3. kanal): dynamic ~80% of transcript (e.g. 800 -> ~640),
    #   never below CHAR_LIMIT_KINO_SYJET floor.
    # - Kino Sekrety / Fakt Za 15 (1-2. kanal): fixed 500-600 window
    #   (DB degeri ne olursa olsun bu araliga kelepcelenir).
    # - ПопкорнФакты (3. kanal): NO fixed count. Dynamic ~80% of transcript
    #   as first guess, then self-tested against the real TTS audio below:
    #   if the voiceover runs longer than the source video, it is shortened
    #   (chronology preserved) until it fits.
    from constants import CHAR_LIMIT_KINO_SYJET
    is_sujet = (channel_name or "").strip().lower() in ("kinosujet", "попкорнфакты")
    if is_sujet:
        char_limit = max(CHAR_LIMIT_KINO_SYJET, int(len(tam_metin) * 0.8))
    else:
        char_limit = min(600, max(500, get_char_limit()))
    sp = system_prompt.replace("{char_limit}", str(char_limit))
    vp = (voice_prompt or system_prompt).replace("{char_limit}", str(char_limit))

    def _regen_shorter(current_text, new_limit):
        """Regenerate the voiceover at the target length instead of blindly
        deleting sentences (which could drop the best part). Chronology and
        key facts are preserved by prompt; returns new text or None."""
        try:
            regen_prompt = (vp or "") + (
                f"\n\nCRITICAL: The text must be between {int(new_limit*0.7)} and {new_limit} characters. "
                f"Current version ({len(current_text)} chars) is too long. "
                f"Retell the transcript faithfully in your own words, keeping ALL events in their ORIGINAL ORDER. "
                f"Condense wording and drop the least important details first — never drop whole key events. "
                f"NEVER drop the fact that explains WHY a theory or conclusion is plausible. "
                f"Keep the hook question first and the final question last."
            )
            if "{char_limit}" in regen_prompt:
                regen_prompt = regen_prompt.replace("{char_limit}", str(new_limit))
            fresh = gemini_uret(f"Original Transcript:\n{tam_metin}", regen_prompt, channel_name, retry_feedback=f"Previous version was {len(current_text)} chars (limit {new_limit}). Shorten while keeping fact order and key events.")
            if _LAST_HARD_BLOCK:
                print("🛑 [Bulut] Hard-block: yeniden uretim denemeleri durduruldu.")
                return None
            if fresh and not fresh.startswith("❌") and len(fresh) > 20 and len(fresh) < len(current_text) and len(fresh) <= int(new_limit * 1.05):
                return fresh.strip()
            print(f"⚠️ [Bulut] Yeniden uretim hedefi tutturamadi ({len(fresh) if fresh else 0}ch), yedek kisaltmaya geciliyor...")
        except Exception as e:
            print(f"⚠️ [Bulut] Yeniden uretim hatasi: {e}")
        return None

    sections, seo_html_str = run_voice_pipeline(
        tam_metin, raw_title, vp, title_prompt, tags_prompt,
        channel_name, lang, char_limit
    )
    v_key = f"voice_{lang}"
    if not sections.get(v_key):
        print("❌ [Bulut] Ses metni bos, GPU temizligi baslatilmiyor.")
        return {"prompt_user": False, "score": 0, "error": "Voice generation failed (kota/hata)", "video_bytes": None, "seo_html": "", "audio_bytes": None, "title": clean_title, "gpu_wall_time": 0, "num_chunks": 0}

    # Post-process: TEXT_FIXES on title/tags, normalize tags
    t_key = f"title_{lang}"
    for k in list(sections.keys()):
        if sections.get(k):
            sections[k] = fix_ii(sections[k])
    if sections.get(v_key) and tam_metin:
        sections[v_key] = verify_movie_names(sections[v_key], tam_metin)
        if sections.get(t_key):
            sections[t_key] = verify_movie_names(sections[t_key], tam_metin)
        if sections.get("tags"):
            sections["tags"] = verify_movie_names(sections["tags"], tam_metin)
        # Missing-movie check: if the transcript names a movie that the voiceover omits,
        # ask Gemini once to weave it in naturally (targeted, deterministic trigger).
        missing = missing_movie_names(sections[v_key], tam_metin)
        if missing:
            print(f"⚠️ [Bulut] Eksik film adi tespit edildi: {missing}. Gemini ile ekleniyor...")
            from functions.gemini_func import gemini_uret
            add_prompt = (
                "The following Russian voiceover for a YouTube Short is missing a movie that "
                f"IS mentioned in the original transcript: {', '.join(missing)}.\n"
                "Rewrite the voiceover so it naturally mentions that movie's Russian name exactly "
                "as given (with correct Russian declension), keeping ALL existing facts, their order, "
                "the hook question, the middle question, and the final question. Do NOT add any new "
                "facts. Output ONLY the rewritten Russian voiceover text.\n\nVoiceover:\n"
                + sections[v_key]
            )
            fresh = gemini_uret(tam_metin, add_prompt, channel_name)
            if fresh and not fresh.startswith("❌") and len(fresh) > 20 and len(fresh) < int(char_limit * 1.2):
                still_missing = missing_movie_names(fresh, tam_metin)
                if not still_missing or len(still_missing) < len(missing):
                    sections[v_key] = fresh.strip()
                    print(f"✅ [Bulut] Eksik film adi eklendi: {still_missing or []} kaldi.")
            else:
                print("⚠️ [Bulut] Gemini eksik film adi ekleyemedi, mevcut haliyle devam.")
    if sections.get("tags"):
        t = sections["tags"]
        if "," not in t and " " in t:
            t = ", ".join(t.split())
        seen = set()
        deduped = []
        for tag in t.split(","):
            tag = tag.strip()
            tag_l = tag.lower()
            if tag_l == "мcu":
                tag_l = "mcu"
            if tag_l and tag_l not in seen and tag_l not in GENERIC_TAGS:
                seen.add(tag_l)
                deduped.append(tag_l)
        sections["tags"] = ", ".join(deduped)

    # SEO HTML artik BURADA kurulmaz: TTS sonrasi metin kisaltilabildigi icin
    # erken kurulan rapor bayat kaliyordu (bkz. eski hata #2.1). Tek kurum
    # asagida, tum metin/ses duzeltmeleri bittikten sonra yapilir.
    try:
        usage_note = gemini_usage_summary()
        print(f"📊 [Bulut] Gemini kullanimi: {usage_note}")
    except Exception:
        usage_note = ""
    seo_html_str = ""

    audio_bytes = None
    voiceover_text = ""  # TTS blogu hata verse de asagida tanimli kalsin (NameError onlendi)
    if SETTINGS["ELEVENLABS_ENABLED"]:
        try:
            print("🎙️ [Bulut] ElevenLabs ile seslendirme (TTS) hazirlaniyor...")
            voiceover_text = sections.get(v_key, "").strip()
            voiceover_text = re.sub(r'\[[^\]]*\]', '', voiceover_text).strip()
            voiceover_text = re.sub(r'[\u201E\u201F\u2018\u2019\u201C\u201D"]', '', voiceover_text).strip()
            # Apply TEXT_FIXES one final time
            for wrong, correct in TEXT_FIXES.items():
                voiceover_text = re.sub(re.escape(wrong), correct, voiceover_text, flags=re.IGNORECASE)
            # Pre-TTS guard (ПопкорнФакты): estimate spoken duration BEFORE spending
            # ElevenLabs credits. Russian TTS @1.0x ≈ 15.5 char/sec (measured).
            # If the estimate exceeds the source video, shorten first (order kept).
            if is_sujet and voiceover_text and source_dur > 0:
                est_dur = len(voiceover_text) / 15.5
                if est_dur > source_dur:
                    pre_limit = max(200, int(len(voiceover_text) * (source_dur * 0.95) / est_dur))
                    print(f"🔧 [Bulut] TTS oncesi: tahmini ses {est_dur:.1f}sn > video {source_dur:.1f}sn, {pre_limit}ch hedefiyle yeniden uretiliyor (kredi israfi onlendi)...")
                    fresh = _regen_shorter(voiceover_text, pre_limit)
                    shorter = fresh if fresh else fix_length(voiceover_text, pre_limit, lang, channel_name, tam_metin, voice_prompt=vp)[0]
                    if len(shorter) < len(voiceover_text):
                        voiceover_text = shorter.strip()
                        sections[v_key] = voiceover_text
                        print(f"✅ [Bulut] Metin kisaltildi ({len(voiceover_text)} karakter), simdi TTS'ye gidiyor.")
            if voiceover_text:
                print(f"✅ [Bulut] Seslendirme metni bulundu ({len(voiceover_text)} karakter).")
                print(f"📤 [Bulut] ElevenLabs'a gonderilecek metin:\n\"\"\"{voiceover_text}\"\"\"")
                # TEK TTS cagrisi. Eski retry dongusu her durumda ilk turda break
                # ediyordu (olu kod) ama her video icin bosuna `tts_verify` cagirip
                # Whisper small modelini yukluyordu. Dogrulama artik acik bir
                # bayrakla kapatilabilir; davranis ayni, bosa harcama yok.
                client_el = ElevenLabs(api_key=ELEVENLABS_API_KEY)
                el_response = client_el.text_to_speech.convert(voice_id=voice_id, text=voiceover_text, language_code=lang, output_format="mp3_44100_128", voice_settings={"speed": 1.0})
                audio_bytes = el_response if isinstance(el_response, bytes) else b"".join(el_response)
                print("✅ [Bulut] Seslendirme MP3 olarak basariyla olusturuldu.")
                if TTS_DOGRULAMA_AKTIF:
                    vr = tts_verify(audio_bytes, voiceover_text, lang)
                    if vr is not None:
                        ratio, _stt_text, problem_words = vr
                        if ratio >= 0.90:
                            print(f"✅ [Bulut] TTS dogrulama basarili (eslesme: {ratio:.0%})")
                        else:
                            print(f"⚠️ [Bulut] TTS dogrulama dusuk (eslesme: {ratio:.0%}). Sorunlu kelimeler: {', '.join(problem_words[:8])}")
            else:
                print(f"⚠️ [Bulut] Seslendirme metni bulunamadi ({v_key} etiketi yok).")
        except Exception as e:
            print(f"⚠️ [Bulut] ElevenLabs hatasi: {e}")

    # ПопкорнФакты self-test: voiceover must not outlast the source video.
    # Measure the real MP3 duration; if too long, recalculate the char
    # budget proportionally and shorten (chronology preserved), then
    # re-synthesize. Max 2 correction rounds.
    if is_sujet and audio_bytes:
        try:
            _voice_mp3 = os.path.join(tmp_dir, f"voice_check_{rand_num}.mp3")
            for _round in range(2):
                with open(_voice_mp3, "wb") as f: f.write(audio_bytes)
                audio_dur = get_video_duration(_voice_mp3)
                print(f"🎙️ [Bulut] Ses testi: seslendirme {audio_dur:.1f}sn / orijinal video {source_dur:.1f}sn")
                if audio_dur <= source_dur or source_dur <= 0:
                    break
                new_limit = max(200, int(len(voiceover_text) * (source_dur * 0.95) / audio_dur))
                print(f"🔧 [Bulut] Ses orijinalden uzun, {new_limit}ch hedefiyle yeniden uretiliyor (sira korunuyor)...")
                fresh = _regen_shorter(voiceover_text, new_limit)
                shorter = fresh if fresh else fix_length(voiceover_text, new_limit, lang, channel_name, tam_metin, voice_prompt=vp)[0]
                if len(shorter) >= len(voiceover_text):
                    print("⚠️ [Bulut] Kisaltma ise yaramadi, mevcut ses kabul ediliyor.")
                    break
                voiceover_text = shorter.strip()
                sections[v_key] = voiceover_text
                client_el = ElevenLabs(api_key=ELEVENLABS_API_KEY)
                el_response = client_el.text_to_speech.convert(voice_id=voice_id, text=voiceover_text, language_code=lang, output_format="mp3_44100_128", voice_settings={"speed": 1.0})
                audio_bytes = el_response if isinstance(el_response, bytes) else b"".join(el_response)
                print(f"✅ [Bulut] Kisaltilmis ses yeniden uretildi ({len(voiceover_text)} karakter).")
        except Exception as e:
            print(f"⚠️ [Bulut] Ses uzunluk testi atlandi: {e}")

    video_final_yolu = os.path.join(tmp_dir, f"sessiz_hazirlik_{rand_num}.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", gercek_ham_yol, "-an", "-r", "30", "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", "-g", "30", "-movflags", "+faststart", video_final_yolu], check=True)

    fps = get_video_fps(video_final_yolu)
    dur = get_video_duration(video_final_yolu)
    total_frames = int(dur * fps)
    # GPU parca plani (bkz. functions/maliyet.py): VRAM-guvenli kare sayisi + ESIT
    # parcalama + kuyruk birlestirme. Sabit-sureli bolmenin aksine minik son parca
    # kalmaz; boylece bosuna GPU konteyneri (soguk baslangic + model yukleme)
    # acilmaz. Karar tamamen saf fonksiyonda, bulut davranisi degismez.
    frames_per_gpu = maliyet.vram_guvenli_kare(FRAMES_PER_GPU, PROC_W, PROC_H,
                                               guclu_gpu=(CLEANER_GPU != "L4"))
    chunk_plani = maliyet.planla(total_frames, fps, frames_per_gpu)
    num_chunks = chunk_plani["num_chunks"]
    if chunk_plani.get("kuyruk_birlesti"):
        print("🧩 [Bulut] Kuyruk parcasi birlestirildi (bosuna GPU konteyneri onlendi).")

    # Beat map: map each voiceover sentence onto the ORIGINAL video timeline
    # (real transcript segment timings when available, else proportional over
    # the video duration) so downstream tools (e.g. ShortsStudio) don't guess.
    voice_timeline = []
    try:
        voice_timeline = build_video_beat_map(sections.get(v_key, ""), source_timeline, dur)
    except Exception as e:
        print(f"⚠️ [Bulut] Beat map uretilemedi: {e}")
    # SEO raporu varsayilanlari: beat map uretilemese de rapor kurulabilsin.
    audio_timeline, voice_audio_dur = voice_timeline, dur
    beatmap_json = None
    src_list, src_dur = [], float(dur or 0)
    if voice_timeline:
        print(f"🗺️ [Bulut] Beat map hazir: {len(voice_timeline)} cumle haritalandi.")
        # REAL voiceover sentence times: measure the produced MP3 with Whisper
        # word timestamps (cloud-side, no extra TTS credits). Fallback: proportional.
        voice_measured = None
        try:
            voice_measured = measure_voice_times(sections.get(v_key, ""), audio_bytes)
        except Exception as e:
            print(f"⚠️ [Bulut] Ses olcumu basarisiz: {e}")
        # HTML timeline: show sentences on the VOICEOVER AUDIO timeline so
        # timestamps match what viewers hear in the produced MP3.
        try:
            if voice_measured:
                audio_timeline = [
                    {"sentence": v["sentence"], "start": _fmt_mmss(v["start"]), "end": _fmt_mmss(v["end"])}
                    for v in voice_measured
                ]
                voice_audio_dur = _audio_duration_sec(audio_bytes) or voice_measured[-1]["end"]
            else:
                audio_timeline, voice_audio_dur = build_voice_timeline(sections.get(v_key, ""), audio_bytes)
        except Exception as e:
            print(f"⚠️ [Bulut] Ses zaman cizelgesi uretilemedi: {e}")
            audio_timeline, voice_audio_dur = voice_timeline, dur
        # Machine-readable beat map for ShortsStudio: each voiceover sentence
        # with REAL voice times + mapped SOURCE video range (float seconds).
        beatmap_json = None
        try:
            beats_sec = map_voice_to_beats_sec(sections.get(v_key, ""), source_timeline)
            vtimes = {v["sentence"]: v for v in (voice_measured or [])}
            beats_out = []
            for i, b in enumerate(beats_sec):
                vt = vtimes.get(b["sentence"])
                if vt is None and voice_measured and i < len(voice_measured):
                    vt = voice_measured[i]
                beats_out.append({
                    "sentence": b["sentence"],
                    "voice_start": round(float(vt["start"]), 2) if vt else None,
                    "voice_end": round(float(vt["end"]), 2) if vt else None,
                    "src_start": round(float(b["start"]), 2),
                    "src_end": round(float(b["end"]), 2),
                })
            if beats_out and all(x["voice_start"] is not None for x in beats_out):
                beatmap_json = beats_out
                print(f"✅ [Bulut] Beat map JSON hazir: {len(beats_out)} cumle (gercek ses + kaynak aralik).")
            else:
                print("⚠️ [Bulut] Beat map JSON eksik ses zamanli, gomulmedi.")
        except Exception as e:
            print(f"⚠️ [Bulut] Beat map JSON uretilemedi: {e}")
        try:
            src_list, src_dur = [], float(dur or 0)
            for s in (source_timeline or []):
                ts, te = float(s.get("start") or 0), float(s.get("end") or 0)
                if te > ts and (s.get("text") or "").strip():
                    src_list.append({"sentence": s["text"].strip(), "start": _fmt_mmss(ts), "end": _fmt_mmss(te)})
                    src_dur = max(src_dur, te)
            if not src_list and tam_metin and dur and dur > 0:
                # No timed transcript (e.g. TikTok/Instagram): fall back to
                # proportional split of transcript sentences over the video.
                sents = [s for s in _split_sentences(tam_metin) if s.strip()]
                weights = [max(1, len(s)) for s in sents]
                wsum = sum(weights) or 1
                cursor = 0.0
                for i, s in enumerate(sents):
                    end = float(dur) if i == len(sents) - 1 else cursor + float(dur) * weights[i] / wsum
                    src_list.append({"sentence": s.strip(), "start": _fmt_mmss(cursor), "end": _fmt_mmss(end)})
                    cursor = end
                src_dur = float(dur)
                print(f"🗺️ [Bulut] Orijinal zaman cizelgesi orantili dagitildi: {len(src_list)} cumle / {src_dur:.1f}sn.")
        except Exception as e:
            print(f"⚠️ [Bulut] Orijinal zaman cizelgesi hazirlanamadi: {e}")
            src_list, src_dur = [], float(dur or 0)
    # TEK SEO kurulumu: tum metin/ses duzeltmeleri ve beat map hazir olduktan
    # sonra. Boylece rapor, gosterilen seslendirme metniyle HER ZAMAN tutarli.
    seo_html_str = build_seo_html(sections, raw_title, tam_metin, channel_name, lang, start_time=process_start, end_time=now_baku(), timeline=audio_timeline, audio_duration=voice_audio_dur, source_timeline=src_list, source_duration=src_dur, beatmap=beatmap_json, usage_note=usage_note)

    print(f"✂️ [Bulut] Toplam {total_frames} Frame tespit edildi. (FPS: {fps:.2f})")
    print(f"🚀 [Bulut] Video {num_chunks} farkli parcaya bolunuyor (Her biri ~{int(chunk_plani['kare_per_chunk'] or 0)} frame @ {PROC_W}x{PROC_H} isleme)...")
    print(f"💸 [Bulut] GPU konteyner sabit maliyeti: {num_chunks} parca x ~{int(OVERHEAD_SECONDS)}sn = ${maliyet.tahmini_maliyet(num_chunks, GPU_COST_PER_SEC, OVERHEAD_SECONDS):.4f} (islem suresi haric)")

    araliklar = maliyet.parcalar(chunk_plani, total_frames, fps)
    if not araliklar:
        araliklar = [(0.0, 0.0)]  # sure bilinmiyorsa tek parca: tum video
    num_chunks = len(araliklar)
    bytes_list = []
    for i, (baslangic, sure) in enumerate(araliklar):
        part_path = os.path.join(tmp_dir, f"part_{i}.mp4")
        ff_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video_final_yolu, "-ss", str(baslangic)]
        if sure > 0:
            ff_cmd += ["-t", str(sure)]
        ff_cmd += ["-c:v", "libx264", "-crf", "16", "-preset", "superfast", "-pix_fmt", "yuv420p", part_path]
        subprocess.run(ff_cmd, check=True)
        with open(part_path, "rb") as f: bytes_list.append(f.read())

    bot = VideoCleanerClass()
    print(f"⚡ [Bulut] {num_chunks} {CLEANER_GPU} GPU ({MAX_CONCURRENT_GPUS}'er grup)...")
    total_gpu_sec = 0
    result_ids = []
    for batch_start in range(0, num_chunks, MAX_CONCURRENT_GPUS):
        batch = bytes_list[batch_start:batch_start + MAX_CONCURRENT_GPUS]
        batch_len = len(batch)
        batch_end = min(batch_start + MAX_CONCURRENT_GPUS, num_chunks)
        t0 = time.time()
        batch_ids = list(bot.clean.map(batch))
        t1 = time.time()
        result_ids.extend(batch_ids)
        total_gpu_sec += (t1 - t0) * batch_len
        pct = min(100, int(batch_end / num_chunks * 100))
        print(f"   ✓ Grup {batch_start//MAX_CONCURRENT_GPUS + 1}/{(num_chunks-1)//MAX_CONCURRENT_GPUS+1} ({pct}%)")
    gpu_wall_time = total_gpu_sec

    print("🪡 [Bulut] GPU islemleri bitti. Temiz parcalar birlestiriliyor...")
    results_volume.reload()
    list_file = os.path.join(tmp_dir, "concat_list.txt")
    with open(list_file, "w") as f:
        for i, rid in enumerate(result_ids):
            result_path = f"/results/{rid}.mp4"
            clean_part_path = os.path.join(tmp_dir, f"clean_{i}.mp4")
            with open(result_path, "rb") as src, open(clean_part_path, "wb") as dst: dst.write(src.read())
            os.remove(result_path)
            f.write(f"file '{clean_part_path}'\n")
    results_volume.commit()

    final_merged_path = os.path.join(tmp_dir, "final_merged.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", final_merged_path], check=True)

    with open(final_merged_path, "rb") as f: final_video_bytes = f.read()

    thumb_bytes = None
    try:
        # CLIP konu sorgusu Ingilizce olmali (CLIP Ingilizce egitimli):
        # kaynak videonun orijinal basligi kullanilir.
        _topic = re.sub(r'[\U0001F300-\U0010FFFF]+', ' ', raw_title or "").strip()[:70]
        thumb_bytes = build_thumbnail(final_merged_path, sections.get(t_key, raw_title), tmp_dir, rand_num, topic_query=_topic)
        if thumb_bytes:
            print(f"[Bulut] Kapak hazir ({len(thumb_bytes)//1024}KB).")
    except Exception as e:
        print(f"⚠️ [Bulut] Kapak uretilemedi: {e}")

    return {"error": None, "video_bytes": final_video_bytes, "seo_html": seo_html_str, "audio_bytes": audio_bytes, "title": clean_title, "gpu_wall_time": gpu_wall_time, "num_chunks": num_chunks, "beat_map": voice_timeline, "thumb_bytes": thumb_bytes}
