import time
import random
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from constants import GEMINI_API_KEYS, GEMINI_MODELS, get_working_model, set_working_model, GENERIC_TITLE_HASHTAGS, GENERIC_TAGS
from functions.seo_builder import build_seo_html

class GeminiRateLimiter:
    def __init__(self, min_interval=4.5):
        self.min_interval = min_interval
        self.last_request_time = 0.0

    def wait_if_needed(self):
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            print(f"⏳ Rate limit: {wait_time:.1f}s bekleniyor...")
            time.sleep(wait_time)
        self.last_request_time = time.time()

_rate_limiter = GeminiRateLimiter(min_interval=4.5)

# ------------------------------------------------------------------
# KULLANIM SAYACI (#8): video basina Gemini cagri harcamasi burada birikir.
# reset_gemini_call_stats() her video oncesi sifirlar; rapor SEO HTML'e yazilir.
# ------------------------------------------------------------------
GEMINI_CALL_STATS = {"calls": 0, "success": 0, "fail": 0, "empty": 0, "models": {}, "by_step": {}}


def _stat_model(model_name, outcome):
    m = GEMINI_CALL_STATS["models"].setdefault(model_name, {"calls": 0, "success": 0, "empty": 0, "fail": 0})
    m[outcome] = m.get(outcome, 0) + 1


def _stat_step(label):
    GEMINI_CALL_STATS["by_step"][label] = GEMINI_CALL_STATS["by_step"].get(label, 0) + 1


def reset_gemini_call_stats():
    """Yeni video islemi oncesi sayaclari sifirla (run_orchestrator basinda)."""
    GEMINI_CALL_STATS.update(calls=0, success=0, fail=0, empty=0)
    GEMINI_CALL_STATS["models"].clear()
    GEMINI_CALL_STATS["by_step"].clear()


def gemini_usage_summary():
    """Insan-okur kullanim ozeti dondurur (SEO raporu icin)."""
    parts = [f"{GEMINI_CALL_STATS['calls']} API istegi ({GEMINI_CALL_STATS['success']} basarili, {GEMINI_CALL_STATS['empty']} bos yanit, {GEMINI_CALL_STATS['fail']} hata)"]
    top = sorted(GEMINI_CALL_STATS["models"].items(), key=lambda kv: -(kv[1]["success"] + kv[1]["empty"] + kv[1]["fail"]))[:3]
    if top:
        parts.append("en cok: " + ", ".join(f"{k} ({v['success'] + v['empty'] + v['fail']})" for k, v in top))
    return "; ".join(parts)


# Dogrulama donguleri icin ust sinir (#4): 99 yerine 8 deneme — kalite korunur,
# kotanin bosa harcanmasi engellenir. Her dongu sonunda 'max deneme' uyarisi basar.
MAX_VERIFY_RETRIES = 8

# Son _try_model cagrisi prompt-level hard-block ile mi bitti? (gemini_uret model
# dongusunu kirmak icin kullanir — hard-block tum modellerde aynidir, donguye gerek yok.)
_LAST_HARD_BLOCK = False

# Hangi pipeline adiminin Gemini cagirdigini belirten etiket (sayac raporlamasi icin).
CURRENT_STEP = "diger"


def gemini_step(label):
    """Context-manager: icinde yapilan Gemini cagilarini o adima sayar.
    Ornek: with gemini_step('uzunluk'): ..."""
    return _StepCtx(label)


class _StepCtx:
    def __init__(self, label):
        self.label = label
        self.prev = None

    def __enter__(self):
        global CURRENT_STEP
        self.prev = CURRENT_STEP
        CURRENT_STEP = self.label
        return self

    def __exit__(self, *exc):
        global CURRENT_STEP
        CURRENT_STEP = self.prev
        return False

def _time_until_quota_reset():
    pacific = timezone(timedelta(hours=-7))
    now = datetime.now(pacific)
    reset = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now >= reset:
        reset += timedelta(days=1)
    diff = reset - now
    hours = int(diff.total_seconds() // 3600)
    minutes = int((diff.total_seconds() % 3600) // 60)
    turkey = timezone(timedelta(hours=3))
    reset_turkey = reset.astimezone(turkey)
    return hours, minutes, reset_turkey.strftime("%H:%M")

def _try_model(model_name, input_text, system_prompt, channel_name, retry_feedback, json_mode=False):
    global _LAST_HARD_BLOCK
    _LAST_HARD_BLOCK = False
    key_order = random.sample(range(len(GEMINI_API_KEYS)), len(GEMINI_API_KEYS))
    dead_keys = set()
    rpd_exhausted = set()

    def _parse_429(error_msg):
        # NOT: artik cagirma yerinde ayristiriliyor (RPM once kontrol edilmeli).
        lower = error_msg.lower()
        if "requests per minute" in lower or "perminute" in lower:
            return "rpm"
        if "requests per day" in lower or "perday" in lower or "per day" in lower or "daily" in lower or "quota" in lower:
            return "rpd"
        return "rpm"

    for idx in key_order:
        api_key = GEMINI_API_KEYS[idx]
        if idx in dead_keys or idx in rpd_exhausted:
            continue
        for attempt in range(3):
            try:
                try:
                    client = genai.Client(api_key=api_key, http_options={'timeout': 60000})
                except TypeError:
                    client = genai.Client(api_key=api_key)
                if json_mode:
                    # #6: Structured output — model her zaman gecerli JSON dondurur,
                    # regex/parse hatalari azalir. Diger cagilar etkilenmez.
                    config = types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                    )
                else:
                    config = types.GenerateContentConfig(system_instruction=system_prompt)
                contents = input_text
                if retry_feedback:
                    contents += f"\n\nFeedback (previous attempt):\n{retry_feedback}"
                _rate_limiter.wait_if_needed()
                print(f"🔑 [{model_name}] key {idx+1} deneniyor...")
                GEMINI_CALL_STATS["calls"] += 1
                _stat_model(model_name, "calls")
                response = client.models.generate_content(model=model_name, contents=contents, config=config)
                # response.text None DONER EGER model bos yanit verdiyse:
                # - RECITATION / SAFETY bloklandi (finishReason: RECITATION / SAFETY),
                # - maxOutputTokens bitmis (finishReason: MAX_TOKENS, parts bos),
                # - model sadece tool-call dondu.
                # Bu KEY'IN SUCLU DEGILDIR — key'i havuzdan atmak yerine ayni key ile
                # yeniden dene; olmazsa sonraki key'e gec.
                text = None
                try:
                    text = response.text
                except Exception:
                    text = None  # bazi SDK surumlerinde parts yoksa .text raise edebilir
                if text and text.strip():
                    GEMINI_CALL_STATS["success"] += 1
                    _stat_model(model_name, "success")
                    return text.strip()
                # --- BOS YANIT TESHISI ---
                finish_reason = None
                prompt_feedback = None
                try:
                    cands = list(response.candidates or [])
                    if cands:
                        finish_reason = cands[0].finish_reason
                    prompt_feedback = getattr(response, "prompt_feedback", None)
                except Exception:
                    pass
                GEMINI_CALL_STATS["empty"] += 1
                _stat_model(model_name, "empty")
                _stat_step(CURRENT_STEP)
                # HARD-BLOCK: candidates hic yoksa prompt ICERIGI reddedilmistir
                # (SAFETY / PROHIBITED_CONTENT / RECITATION / OTHER). Ayni icerikle
                # diger key'ler/modeller de ayni yaniti verir → donguye girme.
                fb_reason = ""
                if finish_reason is None:
                    # candidates bos (prompt-level block): feedback detayini goster
                    fb_str = str(prompt_feedback or "")
                    fb_reason = fb_str[:150]
                hard_markers = ("PROHIBITED", "BLOCKED", "SAFETY", "OTHER", "RECITATION")
                hard = (finish_reason is None) or any(b in str(finish_reason) for b in hard_markers)
                print(f"⚠️ [Bulut] Gemini ({model_name}, key {idx+1}) bos yanit (finishReason={finish_reason}, feedback={fb_reason or '-'})")
                if hard:
                    print("🛑 [Bulut] Icerik prompt seviyesinde bloklandi (tum keylerde ayni olur), tum denemeler durduruluyor.")
                    _LAST_HARD_BLOCK = True
                    return None
                continue
            except Exception as e:
                error_msg = str(e)
                lower_msg = error_msg.lower()
                if "404" in error_msg:
                    return None
                elif "timed out" in lower_msg or "timeout" in lower_msg or "read error" in lower_msg:
                    if attempt < 2:
                        print(f"⏱️ [{model_name}, key {idx+1}] zaman asimi (90sn), tekrar deneniyor... ({attempt+2}/3)")
                        continue
                    else:
                        print(f"⏱️ [{model_name}, key {idx+1}] 3 kez zaman asimi → sonraki key")
                        break
                elif "429" in error_msg:
                    # Once RPM kontrol et: "per day" alt string'i "requests per minute" icermez ama
                    # bazi mesajlar "perDay" (RPM + RPD limitleri birlikte) icerir — spesifik once.
                    if "requests per minute" in lower_msg or "perminute" in lower_msg:
                        limit_type = "rpm"
                    elif "requests per day" in lower_msg or "perday" in lower_msg or "per day" in lower_msg:
                        limit_type = "rpd"
                    elif "daily" in lower_msg or "quota" in lower_msg:
                        limit_type = "rpd"
                    else:
                        limit_type = "rpm"  # belirsiz 429 → kisa bekle, gunluk kotayi harcama
                    if limit_type == "rpm":
                        wait = min(60 * (attempt + 1), 120)
                        print(f"⏱️ [{model_name}, key {idx+1}] 429 RPM — {wait}sn beklenip ayni key deneniyor...")
                        time.sleep(wait)
                        continue
                    else:
                        print(f"📅 [{model_name}, key {idx+1}] 429 RPD (gunluk kota dolu) → skip")
                        rpd_exhausted.add(idx)
                        break
                elif "503" in error_msg or "504" in error_msg or "deadline" in lower_msg or "deadline_exceeded" in lower_msg:
                    if attempt < 2:
                        print(f"⚠️ [Bulut] Gemini ({model_name}) gecici hata (503/504), 15sn beklenip tekrar deneniyor... ({attempt+2}/3)")
                        time.sleep(15)
                    else:
                        print(f"⚠️ [Bulut] Gemini ({model_name}) gecici hata devam ediyor, model atlaniyor (key'ler korundu)...")
                        return None
                elif "500" in error_msg or "internal" in lower_msg:
                    # 500 INTERNAL = sunucu/model tarafi ariza, key ile ilgisi YOK.
                    # Key'leri havuzdan silme, kisa bekleyip ayni modelde 1 kez daha dene,
                    # olmazsa modeli atla (key'ler saglam kalir).
                    if attempt < 1:
                        print(f"⚠️ [Bulut] Gemini ({model_name}) ic hata (500), 15sn beklenip tekrar deneniyor...")
                        time.sleep(15)
                        continue
                    else:
                        print(f"⚠️ [Bulut] Gemini ({model_name}) 500 vermeye devam ediyor, model atlaniyor (key'ler korundu)...")
                        return None
                else:
                    print(f"⚠️ [Bulut] Gemini ({model_name}, key {idx+1}) kalici hata, havuzdan cikariliyor: {e}")
                    dead_keys.add(idx)
                    break

    all_rpd = len(rpd_exhausted) >= len(GEMINI_API_KEYS) - 1
    if all_rpd:
        print("📅 Tum key'lerin gunluk kotasini dolmus.")
    else:
        print("⚠️ [Bulut] Tum key'ler limitlendi.")
    return None

def gemini_uret(input_text, system_prompt, channel_name, retry_feedback=None, json_mode=False):
    label = " (duzeltme)" if retry_feedback else ""
    print(f"🤖 [Bulut] Gemini AI ({channel_name}) icin devreye giriyor...{label}")

    saved_model = get_working_model()
    if saved_model and saved_model in GEMINI_MODELS:
        print(f"💾 [Bulut] Kayitli model ({saved_model}) ilk olarak deneniyor...")
        result = _try_model(saved_model, input_text, system_prompt, channel_name, retry_feedback, json_mode=json_mode)
        if result:
            print(f"✅ [Bulut] Kayitli model ({saved_model}) calisti.")
            set_working_model(saved_model)
            return result
        print(f"⚠️ [Bulut] Kayitli model ({saved_model}) calismadi, siradaki modele gecilio...")

    models_tried = [saved_model] if saved_model and saved_model in GEMINI_MODELS else []
    for model_name in GEMINI_MODELS:
        if saved_model and model_name == saved_model:
            continue
        result = _try_model(model_name, input_text, system_prompt, channel_name, retry_feedback, json_mode=json_mode)
        if not result and _LAST_HARD_BLOCK:
            print("🛑 [Bulut] Hard-block: diger modeller de ayni icerigi reddedecek, model dongusu kesildi.")
            break
        if result:
            print(f"💾 [Bulut] Calisan model kaydediliyor: {model_name}")
            set_working_model(model_name)
            return result
        models_tried.append(model_name)

    # Tum modeller basarisiz olmasi RPD-dolmasi anlamina GELMEZ — yanlis
    # "kota dolu" banner'i basmak yerine gercek seyi soyle.
    print("\n" + "=" * 60)
    print("❌ TUM MODELLER BASARISIZ (bos yanit / limit / gecici hata).")
    print("   Not: Key'ler kotasi dolmadikca bu kalici degildir; tekrar denemek genelde cozer.")
    print("=" * 60 + "\n")
    return "❌ Gemini ile metin uretilemedi."

def evaluate_topic(tam_metin, raw_title, channel_name):
    # Kesif botundaki konu kapisiyla AYNI kural kitabi (kesif.py gemini_rank gate).
    # Ikisi farkli puan verirse sistem tutarsiz olur — kriterler birebir esitlendi.
    eval_prompt = """You are a YouTube Shorts strategist for a Russian-language Marvel/DC Shorts channel. Evaluate this video topic on a scale of 0.0 to 10.0.

STEP 1 — CLASSIFY using TITLE + TRANSCRIPT together (titles lie; if they disagree, trust the transcript):
- KAZANAN = in-universe content about an A-list hero instantly known to mainstream
  film viewers (Thor, Thanos, Spider-Man, Iron Man, Vision...) plus a known
  conflict/reveal about them. Frame (why/versus/what-if) decides NOTHING by itself:
  "Почему"-titles are this channel's biggest hits (322K, 277K, 179K).
- COP = ANY of: actor/real-world stories (actors, contracts, sets, casting);
  DC universe content; obscure/nerd character or narrow niche speculation/theory.
  Drama, "interesting story", empathy and curiosity are NOT scoring criteria.

STEP 2 — SCORE 0.0-10.0 by predicted mainstream appeal:
- KAZANAN with strong novelty/surprise/viral potential: 6.0-10.0.
- Grey area (known hero but niche detail): 4.0-5.9.
- COP: 0.0-3.9. Off-topic (not Marvel/DC/cinema): 0.0-2.0.

Respond with ONLY a JSON object: {"score": <number>}"""
    raw = gemini_uret(f"Video Title: {raw_title}\n\nTranscript:\n{tam_metin}", eval_prompt, channel_name, json_mode=True)
    if not raw or "❌" in raw:
        return 0.0
    try:
        data = json.loads(raw)
        score = float(data["score"])
        return max(0.0, min(10.0, score))
    except Exception:
        # Eski davranis yedegi: metin icinden sayi ayikla
        m = re.search(r'(\d+\.?\d*)', raw)
        return float(m.group(1)) if m else 0.0


QUESTIONS_BANNED_CHANNELS = {"kinosujet", "попкорнфакты"}


def questions_banned(channel_name):
    """Channels where question sentences are completely forbidden (e.g. ПопкорнФакты)."""
    return (channel_name or "").strip().lower() in QUESTIONS_BANNED_CHANNELS


def python_verify(text, rule_key, char_limit=570, questions_allowed=True):
    """Pure Python verification for deterministic rules. 0 Gemini calls."""
    if rule_key == "hook":
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if questions_allowed:
            return bool(sents and (sents[0].endswith("?") or sents[0].endswith("!")))
        # Questions banned: first sentence must be a statement (no '?')
        return bool(sents and not sents[0].endswith("?"))
    if rule_key == "last_sentence":
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if questions_allowed:
            return bool(sents and sents[-1].endswith("?"))
        # Questions banned: last sentence must be a statement (no '?', not question-shaped)
        return bool(sents and not sents[-1].endswith("?") and not is_question_shaped(sents[-1], "ru"))
    if rule_key == "merged_words":
        return not bool(re.search(r'(?<=[а-яё])(?=[А-ЯЁ])', text))
    if rule_key == "brackets":
        return "[" not in text and "]" not in text
    if rule_key == "latin":
        return not bool(re.search(r'[a-zA-Z]', text))
    if rule_key == "length":
        upper = int(char_limit * 1.1)
        return len(text) <= upper  # short is OK (can't add content), only reject if too long
    if rule_key == "repetition":
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        for i in range(len(sents) - 1):
            words_i = sents[i].lower().split()
            words_next = sents[i + 1].lower().split()
            if len(words_i) > 3 and len(words_next) > 3:
                trigrams_i = set(tuple(words_i[j:j+3]) for j in range(len(words_i) - 2))
                trigrams_next = set(tuple(words_next[j:j+3]) for j in range(len(words_next) - 2))
                if trigrams_i & trigrams_next:
                    return False
        return True
    return True


def is_real_question(sent, lang):
    s = sent.strip()
    if not s.endswith("?"):
        return False
    low = s.lower().lstrip("«„… ")
    if lang == "ru":
        starts = (
            "как", "почему", "что", "зачем", "где", "когда", "кто", "какой", "какая", "какие", "какое",
            "а как", "а почему", "а что", "а зачем", "но как", "но почему", "что если", "а что если",
            "неужели", "разве", "или", "можно", "правда", "так почему", "задумывались", "замечали",
        )
        markers = (" думаешь", " думаете", " считаешь", " считаете", " знаешь", " знаете",
                   " задумывался", " задумывались", " замечали", " заметили", " ли ", " ли,",
                   " не так ли", " правда", " как ты думаешь", " как вы думаете")
    else:
        starts = (
            "wie", "warum", "wieso", "weshalb", "was", "wo", "wann", "wer", "welche", "welcher", "welches",
            "ob", "kann", "kannst", "weißt", "weisst", "glaubst", "denkst", "findest", "meinst",
            "hast du", "bist du", "ist es", "würde", "und was", "aber was", "oder", "stimmt",
        )
        markers = (" du ", " dich ", " glaubst", " denkst", " findest", " meinst", " weißt", " weisst", " stimmt")
    if low.startswith(starts):
        return True
    return any(m in low for m in markers)


def is_question_shaped(sent, lang):
    """Detects question-SHAPED sentences even WITHOUT '?' at the end.
    Catches cases like 'Удастся ли спецслужбам выйти на след.' — the '?'
    may have been stripped but the sentence still asks something."""
    s = sent.strip().rstrip(".!?").strip()
    low = s.lower().lstrip("«„… ")
    if lang == "ru":
        starts = (
            "как", "почему", "что", "зачем", "где", "когда", "кто", "какой", "какая", "какие", "какое",
            "а как", "а почему", "а что", "а зачем", "но как", "но почему", "что если", "а что если",
            "неужели", "разве", "можно", "правда", "удастся", "сможет", "сумеет", "получится",
            "стоит ли", "интересно", "удастся ли", "сможет ли", "сумеет ли", "знаете ли",
        )
        markers = (" ли ", " ли,", " ли.", " думаешь", " думаете", " считаешь", " считаете",
                   " знаешь", " знаете", " удастся ли", " стоит ли", " как ты думаешь",
                   " как вы думаете", " сможетs ли")
    else:
        starts = (
            "wie", "warum", "wieso", "weshalb", "was", "wo", "wann", "wer", "welche", "welcher", "welches",
            "ob", "kann", "kannst", "wird", "werden", "glaubst", "denkst", "findest", "meinst",
            "hast du", "bist du", "ist es", "würde", "und was", "aber was", "oder", "stimmt",
        )
        markers = (" du ", " dich ", " glaubst", " denkst", " findest", " meinst", " weißt", " weisst", " stimmt")
    if low.startswith(starts):
        return True
    return any(m in low for m in markers)


def check_content_rules(voice_text, title_text, tags_text, lang):
    """Rule-based check. Returns list of issue strings. Empty list = all good."""
    issues = []
    if not voice_text:
        issues.append("Voice text is empty")
        return issues
    voice_text = re.sub(r'\*+', '', voice_text).strip()

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]

    # Last sentence must end with ? AND be a real question (question word, not a statement with '?')
    if sentences and not sentences[-1].endswith("?"):
        issues.append(f"Last sentence is not a question: '{sentences[-1][:60]}'")
    elif sentences and not is_real_question(sentences[-1], lang):
        issues.append(f"Last sentence is not a real question (no question word, just '?' on a statement): '{sentences[-1][:60]}'")
    elif not sentences:
        issues.append("Voice text has no sentences")

    # No consecutive sentence repetition (shared trigram = same idea)
    for i in range(len(sentences) - 1):
        words_i = sentences[i].lower().split()
        words_next = sentences[i + 1].lower().split()
        if len(words_i) > 3 and len(words_next) > 3:
            trigrams_i = set(tuple(words_i[j:j+3]) for j in range(len(words_i) - 2))
            trigrams_next = set(tuple(words_next[j:j+3]) for j in range(len(words_next) - 2))
            if trigrams_i & trigrams_next:
                shared = " ".join(list(trigrams_i & trigrams_next)[0])
                issues.append(f"Consecutive sentences repeat ideas: '...{shared}...'")
                break

    # First sentence must end with ? or ! (hook indicator)
    if sentences:
        first = sentences[0].strip()
        if not first.endswith("?") and not first.endswith("!"):
            issues.append(f"First sentence is not a hook (doesn't end with ? or !): '{first[:60]}'")

    # No brackets like [музыка]
    if re.search(r'\[.*?\]', voice_text):
        issues.append("Contains bracket annotations like [музыка]")

    # No Latin characters (RU only)
    if lang == "ru" and re.search(r'[a-zA-Z]', voice_text):
        issues.append("Contains Latin characters")

    # Title should have emoji and hashtag
    if title_text:
        if not re.search(r'[\U0001F600-\U0010FFFF]', title_text):
            issues.append("Title missing emoji")
        if "#" not in title_text:
            issues.append("Title missing hashtag")

    return issues


def _chunked_clean_retell(tam_metin, channel_name, char_limit):
    """PROHIBITED_CONTENT fallback'i: tum transkript filtre'yi tetikliyor olabilir.
    Transkripti ~600 karakterlik parcalara bolup her parcayi 'temiz, aile dostu'
    anlatima cevirdir; parcalari birlestirip tek metin dondurur. Parca bazinda
    cagrilar ayri oldugu icin kumulatif filtre tetiklenmesi buyuk olasilikla asilir.
    Basarisizsa '' doner."""
    print("🧩 [Bulut] Parcali temiz anlatim fallback'i devreye giriyor...")
    text = (tam_metin or "").strip()
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > 600:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    chunk_prompt = (
        "You sanitize and retell a fragment of a movie story transcript in Russian for a family-friendly YouTube Shorts voiceover. "
        "Keep every plot event and the order, but SOFTEN graphic content: replace explicit violence, gore, "
        "or explicit details with mild, non-graphic wording (e.g. 'some threats', 'a confrontation'). "
        "Output ONLY the retold Russian fragment, 2-4 sentences, no questions, no quotes, no lists.\n\nFragment:\n"
    )
    parts = []
    for i, chunk in enumerate(chunks):
        with gemini_step("parcali-fallback"):
            raw = gemini_uret(chunk, chunk_prompt, channel_name)
        clean = raw if raw and not raw.startswith("❌") else ""
        if clean:
            parts.append(clean.strip())
            print(f"   ✅ Parca {i+1}/{len(chunks)} temizlendi ({len(clean)} ch)")
        else:
            print(f"   ⚠️ Parca {i+1}/{len(chunks)} basarisiz, atlandi")
        time.sleep(0.5)
    merged = " ".join(parts)
    if len(merged) > 60:
        print(f"🧩 [Bulut] Parcali anlatim hazir ({len(parts)}/{len(chunks)} parca, {len(merged)} ch).")
        return merged
    print("🧩 [Bulut] Parcali anlatim yeterli icerik uretemedi.")
    return ""


def generate_voice(tam_metin, voice_prompt, channel_name, lang, max_retries=2, char_limit=570):
    """Step 1: Generate raw voiceover text. Minimal validation — just not empty."""
    lang_label = {"ru": "Russian", "de": "German"}.get(lang, "Russian")
    formatted_prompt = voice_prompt.format(char_limit=char_limit)
    for attempt in range(max_retries + 1):
        raw = gemini_uret(f"Original Transcript:\n{tam_metin}", formatted_prompt, channel_name)
        voice = raw.strip() if raw else ""
        voice = re.sub(r'\*+|\[[^\]]*\]', '', voice).strip()
        if len(voice) > 20 and not voice.startswith("❌"):
            if attempt > 0:
                print(f"✅ [Bulut] Ses metni {attempt+1}. denemede olusturuldu.")
            return voice
        print(f"⚠️ [Bulut] Ses metni basarisiz, yeniden deneniyor... ({attempt+1}/{max_retries+1})")
        if _LAST_HARD_BLOCK:
            # PROHIBITED/SAFETY/RECITATION: ayni icerikle tekrar denemek bosuna —
            # hemen parcali temiz anlatim fallback'ine gec.
            break
    print("⚠️ [Bulut] Max denemeye ulasildi.")
    # Fallback 1: duzenlenmis transkript (ozel karakterler filtre tetikleyicisi olabilir)
    sanitized = tam_metin.replace("\u00ab", '"').replace("\u00bb", '"')
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2014", " - "), ("\u2013", " - ")):
        sanitized = sanitized.replace(a, b)
    with gemini_step("ses-metni-fallback"):
        raw = gemini_uret(f"Original Transcript:\n{sanitized}", formatted_prompt, channel_name)
    voice = raw.strip() if raw else ""
    voice = re.sub(r'\*+|\[[^\]]*\]', '', voice).strip()
    if len(voice) > 20 and not voice.startswith("❌"):
        print("✅ [Bulut] Duzenlenmis transkriptle uretildi.")
        return voice
    # Fallback 2: ozet-mod (filtre daha az tetiklenir)
    summary_prompt = (
        "Retell the following movie transcript in Russian for a YouTube Shorts voiceover, "
        "4-6 declarative sentences, cinematic narrator style, no questions, no quotes, "
        "no special characters. Style guide for reference:\n" + (voice_prompt or "")
    )
    with gemini_step("ses-metni-ozet"):
        raw = gemini_uret(sanitized, summary_prompt, channel_name)
    voice = raw.strip() if raw else ""
    voice = re.sub(r'\*+|\[[^\]]*\]', '', voice).strip()
    if len(voice) > 20 and not voice.startswith("❌"):
        print("✅ [Bulut] Ozet-mod ile uretildi.")
        return voice
    # Fallback 3: parcali temiz anlatim — her parca ayri cagri, filtre buyuk olasilikla asilir
    chunked = _chunked_clean_retell(tam_metin, channel_name, char_limit)
    if chunked:
        return chunked
    print("❌ [Bulut] Tum fallback'ler basarisiz, bos metin donduruluyor.")
    return ""


def fix_hook(voice_text, lang, channel_name, max_retries=2):
    """Step 2: Fix hook — first sentence must end with ? or !. 0 Gemini."""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
    if not sentences:
        return voice_text, False
    first = sentences[0]
    if questions_banned(channel_name):
        # Cinematic narrator channel: questions forbidden — strip '?' from the hook.
        if first.endswith("?"):
            voice_text = voice_text.replace(first, first.rstrip("?").rstrip() + ".", 1)
            print("🔧 [Bulut] Hook fix: soru isareti kaldirildi.")
        # Hook must not be question-SHAPED either (e.g. "Удастся ли..." without '?')
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        if sents and is_question_shaped(sents[0], lang):
            lang_label = {"ru": "Russian", "de": "German"}.get(lang, "Russian")
            print("🔧 [Bulut] Hook soru seklinde, kesin ifadeye cevriliyor...")
            for attempt in range(max_retries + 1):
                fix_prompt = f"""Rewrite ONLY the first sentence of this {lang_label} story-narrator voiceover.
The current first sentence is question-shaped (it asks something). Questions are COMPLETELY FORBIDDEN
on this channel — this is a cinematic third-person narrator channel.
Rewrite it as a declarative, dramatic hook statement that sets the scene. It must NOT end with '?',
must NOT contain question words or "ли" constructions, and must NOT address the viewer.
Keep the same meaning and do not add or invent any facts.

Full voiceover:
{voice_text}

Output ONLY the new first sentence, nothing else."""
                new_first = gemini_uret(f"Original first sentence: {sents[0]}", fix_prompt, channel_name)
                if new_first and not new_first.startswith("❌"):
                    nf = new_first.strip()
                    if nf and not is_question_shaped(nf, lang) and not nf.endswith("?"):
                        voice_text = voice_text.replace(sents[0], nf, 1)
                        print("✅ [Bulut] Hook ifadeye cevrildi.")
                        return voice_text, True
            print("⚠️ [Bulut] Gemini hook'u duzeltemedi, mevcut haliyle devam.")
        return voice_text, True
    # Questions allowed (Kino Sekrety, Fakt Za 15): ensure hook ends with ? or !
    if not first.endswith(("?", "!")):
        voice_text = voice_text.replace(first, first.rstrip(".!") + "!", 1)
        print("🔧 [Bulut] Hook fix: sonuna '!' eklendi.")
    return voice_text, True


def fix_last_sentence(voice_text, lang, channel_name, max_retries=2):
    """Step 3: Fix last sentence. Channel-aware:
    - Questions banned (e.g. ПопкорнФакты): every sentence must be a statement —
      convert any '?' sentence into a plain statement ending with '.'.
    - Default channels: last sentence must end with ? AND be a real engagement
      question (comment bait)."""
    if questions_banned(channel_name):
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        changed = False
        for s in sents:
            if s.endswith("?"):
                voice_text = voice_text.replace(s, s.rstrip("?").rstrip() + ".", 1)
                changed = True
        if changed:
            print("🔧 [Bulut] Soru cümleleri ifadeye çevrildi (soru yasak kanal).")
        # A '?'-stripped sentence can still be question-SHAPED (e.g. "Удастся ли ... .").
        # Rewrite it as a definitive closing statement via Gemini.
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        if sents and is_question_shaped(sents[-1], lang):
            lang_label = {"ru": "Russian", "de": "German"}.get(lang, "Russian")
            print("🔧 [Bulut] Son cumle soru seklinde, kesin bitis cumlesine cevriliyor...")
            for attempt in range(max_retries + 1):
                fix_prompt = f"""Rewrite ONLY the last sentence of this {lang_label} story-narrator voiceover.
The current last sentence is question-shaped (it asks something). Questions are COMPLETELY FORBIDDEN
on this channel — this is a cinematic third-person narrator channel.
Rewrite it as a DEFINITIVE closing statement: a verdict or result that ends the story.
It must NOT end with '?', must NOT contain question words or "ли" constructions, and must NOT
address the viewer. Keep the same meaning and do not add or invent any facts.

Full voiceover:
{voice_text}

Output ONLY the new last sentence, nothing else."""
                new_last = gemini_uret(f"Original last sentence: {sents[-1]}", fix_prompt, channel_name)
                if new_last and not new_last.startswith("❌"):
                    nl = new_last.strip()
                    if nl and not is_question_shaped(nl, lang) and not nl.endswith("?"):
                        voice_text = voice_text.replace(sents[-1], nl, 1)
                        print("✅ [Bulut] Son cumle kesin bitis cumlesine cevrildi.")
                        return voice_text, True
            print("⚠️ [Bulut] Gemini son cumleyi duzeltemedi, mevcut haliyle devam.")
        return voice_text, True
    issues = check_content_rules(voice_text, "", "", lang)
    if not any(i.startswith("Last sentence") for i in issues):
        return voice_text, True
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
    if not sentences:
        return voice_text, False
    last = sentences[-1].rstrip(".!")
    # Pure-Python first pass: only add '?' if missing and it IS a question-shaped sentence
    if not last.endswith("?"):
        sentences[-1] = last + "?"
        voice_text = " ".join(sentences)
        print(f"🔧 [Bulut] Son cümle Python force-fix: '?' eklendi.")
    # If it still isn't a REAL question (statement with '?'), rewrite via Gemini
    sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
    if sents and not is_real_question(sents[-1], lang):
        lang_label = {"ru": "Russian", "de": "German"}.get(lang, "Russian")
        print(f"🔧 [Bulut] Son cumle gercek soru degil, etkilesim sorusuna cevriliyor...")
        for attempt in range(max_retries + 1):
            if lang == "ru":
                fix_prompt = f"""Rewrite ONLY the last sentence of this {lang_label} voiceover.
The current last sentence is NOT a real question — it is a statement with "?" stuck on the end.
Rewrite it as a REAL viewer-opinion question in Russian that makes people want to comment, e.g.:
"А как ты думаешь, ...?" / "А ты как считаешь, ...?" / "Как по-твоему, ...?"
The question must ask the viewer's opinion about the topic, MUST end with "?", and its answer
must NOT already be given in the text.

Full voiceover:
{voice_text}

Output ONLY the new last sentence, nothing else."""
            else:
                fix_prompt = f"""Rewrite ONLY the last sentence of this {lang_label} voiceover.
The current last sentence is NOT a real question — it is a statement with "?" stuck on the end.
Rewrite it as a REAL viewer-opinion question in German that makes people want to comment, e.g.:
"Was denkst du, ...?" / "Wie findest du, ...?" / "Was ist deine Meinung, ...?"
The question must ask the viewer's opinion about the topic, MUST end with "?", and its answer
must NOT already be given in the text.

Full voiceover:
{voice_text}

Output ONLY the new last sentence, nothing else."""
            new_last = gemini_uret(f"Original last sentence: {sents[-1]}", fix_prompt, channel_name)
            if new_last and not new_last.startswith("❌"):
                nl = new_last.strip().rstrip(",")
                if nl.endswith("?") and is_real_question(nl, lang):
                    voice_text = voice_text.replace(sents[-1], nl, 1)
                    print(f"✅ [Bulut] Son cumle etkilesim sorusuna cevrildi.")
                    return voice_text, True
        print("⚠️ [Bulut] Gemini son cumleyi duzeltemedi, mevcut haliyle devam.")
    return voice_text, True


def fix_repetition(voice_text, lang, channel_name, max_retries=10):
    """Step 4: Fix consecutive sentence repetition. Uses trigram matching — 0 Gemini calls."""
    while True:
        issues = check_content_rules(voice_text, "", "", lang)
        rep_issues = [i for i in issues if i.startswith("Consecutive")]
        if not rep_issues:
            return voice_text, True

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        changed = False
        i = 0
        while i < len(sentences) - 1:
            words_i = sentences[i].lower().split()
            words_next = sentences[i + 1].lower().split()
            # Check for shared trigrams (3+ consecutive words)
            trigrams_i = set(tuple(words_i[j:j+3]) for j in range(len(words_i) - 2))
            trigrams_next = set(tuple(words_next[j:j+3]) for j in range(len(words_next) - 2))
            shared = trigrams_i & trigrams_next
            if shared:
                shared_phrase = " ".join(list(shared)[0])
                print(f"🔧 [Bulut] Cümle tekrarı trigram ile tespit edildi: '...{shared_phrase}...', ikincisi siliniyor.")
                del sentences[i + 1]
                changed = True
            else:
                i += 1
        if changed:
            voice_text = " ".join(sentences)
        else:
            break
    return voice_text, False


def fix_merged_words(voice_text):
    """Split merged words like 'битваУВИ' → 'битва УВИ'. No Gemini."""
    # Lowercase followed by uppercase → likely word merge
    voice_text = re.sub(r'(?<=[а-яё])(?=[А-ЯЁ])', ' ', voice_text)
    # Two uppercase abbreviations merged like 'УВИУВИ' → check known patterns via TEXT_FIXES
    from constants import TEXT_FIXES
    for wrong, correct in TEXT_FIXES.items():
        voice_text = voice_text.replace(wrong, correct)
    return voice_text


def fix_latin_text(voice_text, lang):
    """Step 5: Remove Latin characters (regex + TEXT_FIXES, no Gemini)."""
    from constants import TEXT_FIXES
    if lang != "ru":
        return voice_text
    result = voice_text
    for wrong, correct in TEXT_FIXES.items():
        result = re.sub(re.escape(wrong), correct, result, flags=re.IGNORECASE)
    if re.search(r'[a-zA-Z]', result):
        result = re.sub(r'[a-zA-Z]+', lambda m: str(m.group(0)).translate(str.maketrans('', '', 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')), result)
    return result


def fix_brackets(voice_text):
    """Remove bracket annotations, no Gemini needed."""
    return re.sub(r'\[[^\]]*\]', '', voice_text).strip()


def fix_movie_titles(text):
    """Add missing colon in Russian movie titles like Мстители Война → Мстители: Война."""
    text = re.sub(r'Мстител[а-яё]+\s+(Война|Финал|Судный)', r'Мстители: \1', text, flags=re.IGNORECASE)
    text = re.sub(r'Человек[а-яё-]*\s*паук[а-яё]*\s+(Вдали|Нет|Возвращение)', r'Человек-паук: \1', text, flags=re.IGNORECASE)
    text = re.sub(r'Первый\s+мстител[а-яё]+\s+(Другая|Противостояние|Иная)', r'Первый мститель: \1', text, flags=re.IGNORECASE)
    return text


def fix_spelling(text, channel_name):
    """Fix Russian spelling/grammar errors using Gemini. One call."""
    prompt = """Check this Russian text for spelling and grammar errors. Fix:
1. Spelling/declension errors (incorrect name declensions, missing letters in names, wrong case endings).
2. GRAMMATICALLY INCOMPLETE sentences: missing verbs or conjunctions required by the structure. E.g. "а он сам молот легендарным" is incomplete — it must be "а он сам сделал молот легендарным". "он понял не молот делал его сильным" is missing "что" — must be "он понял, что не молот делал его сильным". Every sentence must be a complete, correct Russian sentence.
Rules:
1. NEVER invent word forms or declensions. Use only standard, correct literary Russian. If a word has an unusual/invented form, replace it with the correct standard form, or rephrase the sentence to use simpler words you know are correct.
2. NEVER translate movie/character names literally and NEVER replace a movie mentioned in the original transcript with a different movie. Use the official Russian dub name. If you are unsure of the official name, keep the original English name in guillemets «» instead of an invented Russian translation or a substitute movie.
3. NEVER change the meaning, order of facts, or any real content. Only fix grammar, spelling, and missing verbs/conjunctions.
4. Output ONLY the corrected Russian text, nothing else. If no errors, output the original text unchanged."""
    raw = gemini_uret(text, prompt, channel_name)
    return raw.strip() if raw and not raw.startswith("❌") and len(raw) > 20 else text


def _sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text or "") if s.strip()]


def _trim_to_upper(text, upper, max_delete=3):
    """Deterministik kisaltma: en kisa ORTA cumleleri silip <= upper'a iner.
    Ilk cumle (kanca) ve son cumle (final sorusu) ASLA silinmez; en az 3 cumle
    korunur. Silme yetmezse metin degismeden doner (LLM'e tek tur sansi verilir)."""
    sents = _sentences(text)
    if len(sents) <= 3:
        return text
    removed = 0
    while len(" ".join(sents)) > upper and removed < max_delete and len(sents) > 3:
        middle = [(i, s) for i, s in enumerate(sents) if 0 < i < len(sents) - 1]
        if not middle:
            break
        i, _ = min(middle, key=lambda x: len(x[1]))
        sents.pop(i)
        removed += 1
    return " ".join(sents)


def fix_length(voice_text, char_limit, lang, channel_name, tam_metin, voice_prompt=None, max_retries=2):
    """Step 8: Uzunlugu hedefe oturt — DETERMINISTIK ve sinirli.

    Eski davranis: +/-%10 bant icin Gemini'ye 10 kez "su aralikta yaz" diyordu;
    LLM karakter sayamadigi icin kosular savruluyordu (448 -> 674 -> ... -> 836)
    ve her video ~10 bos Gemini cagrisi yakiyordu. Yeni kural seti:
      * bant icinde           -> 0 cagri (degismedi)
      * hafif kisa (>= 0.75x) -> kabul, 0 cagri (kisa ses zararsiz; ses/video
        eslesmesi kisaltma tarafinda guvenlidir)
      * cok kisa              -> TEK genisletme cagrisi; tasarsa mekanik kirp
      * cok uzun              -> once mekanik cumle silme, sonra TEK yeniden
        yazma; sonuc asla girdiden uzun olmaz
    Toplam en fazla ~2 Gemini cagrisi; cikti deterministik."""
    lower = int(char_limit * 0.75) if questions_banned(channel_name) else int(char_limit * 0.9)
    upper = int(char_limit * 1.1)
    vlen = len(voice_text)
    if lower <= vlen <= upper:
        return voice_text, True

    if vlen > upper:
        # 1) Mekanik: en kisa orta cumleleri sil (0 Gemini cagrisi)
        trimmed = _trim_to_upper(voice_text, upper)
        if len(trimmed) <= upper:
            print(f"🔧 [Bulut] Uzunluk fazla ({vlen}→{len(trimmed)}), en kısa orta cümle(ler) silindi.")
            return trimmed, True
        if _LAST_HARD_BLOCK:
            return trimmed, True
        # 2) Tek yeniden yazma turu (ana mantik odakli)
        print(f"🔧 [Bulut] Uzunluk çok fazla ({vlen}), ana mantığa odaklanarak tek kez yeniden oluşturuluyor (hedef {char_limit}ch)...")
        regen_prompt = (voice_prompt or "") + (
            f"\n\nCRITICAL: The text must be between {int(char_limit*0.7)} and {char_limit} characters. "
            f"Current version ({vlen} chars) is too long. Do NOT try to list every fact. "
            f"Focus ONLY on the transcript's MAIN TOPIC and MAIN LOGIC. "
            f"Cover only the most important facts that support the main point, keeping their ORIGINAL ORDER. "
            f"Condense or rewrite sentences in your own style as needed, and drop the least important details first. "
            f"NEVER drop the fact that explains WHY a theory or conclusion is plausible. "
            f"Never break the order of the facts as they appear in the transcript."
        )
        if "{char_limit}" in regen_prompt:
            regen_prompt = regen_prompt.replace("{char_limit}", str(char_limit))
        fresh = gemini_uret(f"Original Transcript:\n{tam_metin}", regen_prompt, channel_name,
                            retry_feedback=f"Previous version was {vlen} chars (limit {char_limit}). Focus on the main topic, keep fact order, drop least important details.")
        if fresh and not fresh.startswith("❌") and len(fresh) > 20:
            fresh = _trim_to_upper(fresh.strip(), upper)
            if len(fresh) <= upper:
                print(f"✅ [Bulut] Yeniden yazim hedefe indi ({len(fresh)}ch).")
                return fresh, True
            if len(fresh) < len(trimmed):
                trimmed = fresh
        print(f"⚠️ [Bulut] Uzunluk hedefe tam inilemedi ({len(trimmed)}ch), en kısa haliyle kabul.")
        return trimmed, True

    # --- Ses metni hedefin ALTINDA ---
    soft_lower = int(char_limit * 0.75)
    if vlen >= soft_lower:
        print(f"ℹ️ [Bulut] Seslendirme {vlen}ch (hedef ~{char_limit}): kısa taraf toleransında kabul edildi.")
        return voice_text, True
    print(f"⚠️ [Bulut] Seslendirme {vlen} karakter (hedef ~{char_limit}), çok kısa — tek genişletme turu...")
    expand_prompt = (voice_prompt or "") + (
        f"\n\nCRITICAL: The text must be between {lower} and {upper} characters. "
        f"Current version ({vlen} chars) is too short. "
        f"Retell the transcript faithfully in your own words: keep ALL events in their original order. "
        f"Condense wording only — do NOT drop whole events or details. "
        f"NEVER drop the fact that explains WHY a theory or conclusion is plausible — keep that cause/effect detail even if you must shorten other sentences to fit. "
        f"Never break the order of the facts as they appear in the transcript."
    )
    if "{char_limit}" in expand_prompt:
        expand_prompt = expand_prompt.replace("{char_limit}", str(lower))
    if _LAST_HARD_BLOCK:
        return voice_text, True
    fresh = gemini_uret(f"Original Transcript:\n{tam_metin}", expand_prompt, channel_name,
                        retry_feedback=f"Previous version was {vlen} chars (target {lower}-{upper}). Expand the retelling: keep ALL facts in order, add more detail from the transcript.")
    if fresh and not fresh.startswith("❌") and len(fresh) > 20:
        fresh = _trim_to_upper(fresh.strip(), upper)
        if len(fresh) > vlen:
            print(f"✅ [Bulut] Genişletme sonucu {len(fresh)}ch kabul edildi (hedef bant {lower}-{upper}).")
            return fresh, True
    print(f"⚠️ [Bulut] Genişletme yeterli olmadı, mevcut metin korunuyor ({vlen}ch).")
    return voice_text, True


def fix_title_hashtags(title_text, tags_text):
    """Put the video's MAIN topic(s) as 1-2 Russian hashtags at the end of the title.

    Uses the already-generated tags list (clean nominative nouns) instead of scanning
    the voiceover (which would yield declined forms like #таносом). Takes the first 1-2
    tags that are concrete, fully Russian and not generic channel words. Falls back to
    the original title when no usable tag exists."""
    if not title_text or not tags_text:
        return title_text
    topics = []
    for raw in re.split(r'[,;]', tags_text):
        tag = raw.strip().strip('#').strip()
        if not tag or not re.search(r'[А-Яа-яЁё]', tag):
            continue
        norm = "".join(ch for ch in tag.lower() if ch not in " -") 
        norm = norm.lstrip('#').strip('-')
        if len(norm) < 3 or len(norm) > 35:
            continue
        if not re.fullmatch(r'[а-яё]+', norm):
            continue
        if norm in GENERIC_TITLE_HASHTAGS:
            continue
        if norm not in topics:
            topics.append(norm)
        if len(topics) == 2:
            break
    if not topics:
        return title_text
    cleaned = re.sub(r'#\S+', ' ', title_text)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip().rstrip()
    if not cleaned:
        cleaned = title_text
    # Keep emoji (usually at the end of the hook) and trim text by WHOLE WORDS only
    emojis = re.findall(r'[\U0001F000-\U0010FFFF\u2600-\u27BF]+', cleaned)
    body = re.sub(r'[\U0001F000-\U0010FFFF\u2600-\u27BF]+', '', cleaned).strip().rstrip()
    if not body:
        body = cleaned

    def build(chosen, body_text):
        hs = " ".join("#" + t for t in chosen)
        tail = " ".join(emojis[:2]) + (" " + hs if hs else "")
        return (f"{body_text} {tail}".strip() if body_text else tail).strip()

    for count in (2, 1):
        result = build(topics[:count], body)
        if len(result) <= 65:
            break
    else:
        result = build(topics[:1], body)
        while len(result) > 65 and body:
            body = body.rsplit(" ", 1)[0].rstrip()
            result = build(topics[:1], body)
        if len(result) > 65:
            return title_text
    if result != title_text:
        print(f"🔧 [Bulut] Hashtag ana konuya gore ayarlandi: {' '.join('#' + t for t in topics[:2])}")
    return result


# ------------------------------------------------------------------
# BASLIK + ETIKET — profesyonel Shorts SEO (2026 arastirmasi)
#  * Shorts baslik denetleyicileri: 40-60 karakter ideal, ilk 2-3 kelime kanca,
#    anahtar kelime ilk 30 karakterde, 1 emoji, 1-2 hashtag; ALL-CAPS/hype cezasi.
#  * YouTube etiket alani 500 karakter (virguller dahil). Profesyonel yapi:
#    "spesifik -> nis -> genel" piramidi, long-tail + yazim varyantlari; alakasiz
#    etiketler erisimi bozar (silme/yayilma dususu).
# ------------------------------------------------------------------
TITLE_MAX_LEN = 65
EMOJI_RE = re.compile(r'[\U0001F000-\U0010FFFF\u2600-\u27BF]')
TAG_FIELD_LIMIT = 500
TAG_MIN_COUNT = 20
TAG_MIN_TOTAL = 300
TAG_MAX_ITEM = 60

# Ilk kelime CTR kararini verir: kanca acilislari
_HOOK_OPENERS = (
    "почему", "как", "зачем", "что", "кто", "когда", "где", "какой", "какая",
    "это", "вот", "так", "секрет", "главный", "самый", "все", "никто", "однажды",
    "представь", "узнай", "смотри", "стоп",
)
_TITLE_HYPE = ("шок", "невероятн", "смотри до конца", "вы не поверите", "безумие", "сенсац")
_CHANNEL_EMOJI = {"kino sekrety": "🔥", "fakt za 15": "🤯", "попкорнфакты": "🎬"}


def _title_ai_score(title):
    """Deterministik Shorts baslik skoru (0-100). Profesyonel Shorts baslik
    denetleyicilerinin agirlik sirasini taklit eder (uzunluk > kanca acilisi >
    ozgulluk > emoji/hashtag hijyeni > kelime sayisi). generate_title bunu
    modelin 1-10 skoruyla birlestirip EN IYI GECERLI adayi secer."""
    t = (title or "").strip()
    if not t:
        return 0
    score = 0
    n = len(t)
    body = EMOJI_RE.sub("", re.sub(r'#\S+', '', t)).strip()
    body = re.sub(r'\s{2,}', ' ', body)
    # 1) Uzunluk (22): mobil feed ~40-60 karakter gosterir
    if 35 <= n <= 60:
        score += 22
    elif 30 <= n <= 65:
        score += 14
    elif n < 30:
        score += 6
    # 2) Kanca acilisi (18)
    first = re.sub(r'^[«"\'(\s]+', '', body).split(" ")[0].lower() if body else ""
    if first in _HOOK_OPENERS:
        score += 18
    elif body[:1].isupper():
        score += 6
    # 3) Bilgi boslugu / soru (8)
    if "?" in t:
        score += 8
    # 4) Ozgulluk: ilk 30 karakterde ozel isim (10)
    head = body[:30]
    if re.search(r'\b[А-ЯЁ][а-яё]{2,}', head) or re.search(r'\b[A-Z][a-z]{2,}', head):
        score += 10
    # 5) Emoji hijyeni (12): tam 1 ideal
    e = len(EMOJI_RE.findall(t))
    score += 12 if e == 1 else (6 if e == 0 else (4 if e == 2 else 0))
    # 6) Hashtag hijyeni (12): 1-2 ideal
    h = len(re.findall(r'#\S+', t))
    score += 12 if 1 <= h <= 2 else (6 if h == 0 else 2)
    # 7) Kelime sayisi 5-12 (8)
    w = len(body.split())
    score += 8 if 5 <= w <= 12 else 3
    # 8) Hype / ALL-CAPS cezasi (10)
    caps = [x for x in body.split() if len(x) > 2 and x.isupper()]
    if len(caps) >= 2:
        score -= 6
    if any(k in t.lower() for k in _TITLE_HYPE):
        score -= 4
    return max(0, min(100, score))


def _title_issues(title):
    issues = []
    if not EMOJI_RE.search(title or ""):
        issues.append("emoji missing")
    if "#" not in (title or ""):
        issues.append("hashtag missing")
    if len(title or "") > TITLE_MAX_LEN:
        issues.append(f"too long ({len(title)} chars)")
    return issues


def _finalize_title(title, channel_name=""):
    """0 Gemini cagrisiyla basligi kurala uydur (son sans): tek emoji (yoksa
    kanal emojisi), hashtag'ler sonda, <= 65 karakter (kuyruktan kelime kirpma),
    hashtag yoksa basliktaki ozel isimden deterministik hashtag turetir."""
    t = re.sub(r'\s{2,}', ' ', re.sub(r'\*+', '', (title or "").strip())).strip()
    if not t:
        return t
    found = EMOJI_RE.findall(t)
    t = re.sub(r'\s{2,}', ' ', EMOJI_RE.sub('', t)).strip()
    m = re.search(r'((?:\s*#[^\s#]+)+\s*)$', t)
    hashes = re.findall(r'#[^\s#]+', m.group(1)) if m else []
    body = (t[:m.start()].strip() if m else t).strip()
    emoji = found[0] if found else _CHANNEL_EMOJI.get((channel_name or "").strip().lower(), "🔥")
    if not hashes:
        words = re.findall(r'[А-ЯЁ][а-яё\-]{2,}', body)
        for w in (words[1:] + words[:1]):
            cand = w.lower()
            if len(cand) >= 3 and cand not in GENERIC_TITLE_HASHTAGS:
                hashes = ['#' + cand]
                break

    def build(b, hs, em):
        parts = [b]
        if em:
            parts.append(em)
        if hs:
            parts.append(" ".join(hs[:2]))
        return " ".join(x for x in parts if x).strip()

    result = build(body, hashes, emoji)
    while len(result) > TITLE_MAX_LEN and len(body.split()) > 3:
        body = body.rsplit(" ", 1)[0].rstrip(" ,;:—-")
        result = build(body, hashes, emoji)
    if len(result) > TITLE_MAX_LEN and hashes:
        for _ in range(len(hashes)):
            hashes = hashes[:-1]
            result = build(body, hashes, emoji)
            if len(result) <= TITLE_MAX_LEN:
                break
    return result


def _kanitlanmis_kaliplar(channel_name):
    """Kendi kanalinin YouTube Studio verisinden cikan kanitlanmis kaliplar.

    Veri yoksa bos doner (davranis degismez). Salt-okuma: API/anahtar yok.
    """
    try:
        from functions.performans import kalip_blok, kanal_no_bul
        return kalip_blok(kanal_no_bul(channel_name))
    except Exception:
        return ""


def generate_title(voice_text, title_prompt_template, channel_name, max_retries=2):
    """Baslik uret: her turda 3 aday + model skoru gelir; adaylar Python'un
    Shorts rubrigiyle puanlanir ve EN IYI GECERLI aday secilir. Gecersiz
    cikarsa en fazla 2 tur; sonra tek fix_title (eski 5x3 + 10'luk dongu kalkti)."""
    title_sysp = title_prompt_template.format(voice_text=voice_text)
    # Kanitlanmis kaliplar (varsa) prompta eklenir: basliklar gercek veriye yaslanir.
    _blok = _kanitlanmis_kaliplar(channel_name)
    _kalip_bolum = f"\n{_blok}\n" if _blok else ""
    score_prompt = f"""{title_sysp}
{_kalip_bolum}
IMPORTANT — Write 3 different title options. Score each 1-10 for clickability (hook strength, curiosity gap, keyword clarity).

Format:
1. [Title 1] — Score: X/10
2. [Title 2] — Score: X/10
3. [Title 3] — Score: X/10"""
    best_any, best_any_total = "", -1
    best_valid, best_valid_total = "", -1
    for attempt in range(max(1, max_retries)):
        raw = gemini_uret("Create 3 title options with scores.", score_prompt, channel_name)
        if raw:
            for line in raw.split("\n"):
                m = re.match(r'\d+[\.\)]\s*(.+?)\s*[—-]\s*Score:\s*(\d+)/10', line.strip(), re.IGNORECASE)
                if not m:
                    continue
                cand = re.sub(r'\*+', '', m.group(1)).strip()
                total = _title_ai_score(cand) + int(m.group(2)) * 3
                if total > best_any_total:
                    best_any, best_any_total = cand, total
                if not _title_issues(cand) and total > best_valid_total:
                    best_valid, best_valid_total = cand, total
            if best_valid:
                return best_valid, True
        print(f"⚠️ [Bulut] Başlık adayları kural dışı, tur tekrar ediliyor... ({attempt+1}/{max_retries})")
    if best_any:
        return fix_title(best_any, channel_name)
    return "", False


def fix_title(title_text, channel_name, max_retries=2):
    """Baslik bicim sorunlarini duzelt: en fazla 2 LLM turu, sonra DETERMINISTIK
    bitirme (tek emoji + hashtag + <=65 karakter). Eskiden 10 tura kadar
    donuyordu; artik tur sinirli ve cikti garanti."""
    title_text = re.sub(r'\*+', '', (title_text or "").strip())
    for attempt in range(max(1, max_retries)):
        issues = _title_issues(title_text)
        if not issues:
            return title_text, True
        print(f"🔧 [Bulut] Başlık düzeltiliyor: {', '.join(issues)}... ({attempt+1}/{max_retries})")
        fix_prompt = f"""Fix this YouTube Shorts title: {', '.join(issues)}.
Keep the same topic and hook. Rules: hook in the first 2-3 words, the topic keyword as a plain word,
exactly ONE emoji before the hashtags, 1-2 topic hashtags, max {TITLE_MAX_LEN} characters total.

Current title: {title_text}

Output ONLY the fixed title, one line."""
        raw = gemini_uret(f"Fix title: {title_text[:60]}", fix_prompt, channel_name)
        if raw and not raw.startswith("❌"):
            cleaned = re.sub(r'\*+', '', raw).strip()
            if cleaned:
                title_text = cleaned
    return _finalize_title(title_text, channel_name), True


def _clean_tags(raw):
    """Etiket listesini deterministik temizle: # yok, kucuk harf, tekrarsiz,
    GENERIC_TAGS (genel/soyut kelimeler) atilir, cumle gibi uzun etiketler atilir."""
    if not raw:
        return ""
    out, seen = [], set()
    for it in re.split(r'[,\n;]+', raw):
        tag = re.sub(r'\s{2,}', ' ', (it or "").strip().strip('"').strip("'")).strip()
        tag = tag.lstrip('#').strip().strip('.').strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen or key in GENERIC_TAGS:
            continue
        if len(tag) < 3 or len(tag) > TAG_MAX_ITEM:
            continue
        if not re.search(r'[а-яёa-z0-9]', key):
            continue
        if ":" in tag:
            # Baslik/etiket satiri ("Line 1:", "Here are the tags:") etiket degildir
            continue
        if len(key.split()) > 8:
            # Cumle gibi etiketler arama terimi degildir (gercek long-tail 4-6 kelime olabilir)
            continue
        seen.add(key)
        out.append(key)
    return ", ".join(out)


# Modelin ekleyebilecegi katman basliklari: "Line 1 — 10-12 EXACT tags:", "EXACT:",
# "ТОЧНЫЕ ТЕГИ:" ... Etiket listesine sizmamalari icin deterministik ayiklama.
_TIER_ETIKET_RE = re.compile(
    r'^\s*(?:line\s*\d{1,2}\s*[—\-–:.]?\s*)?'
    r'\(?\s*\d{0,3}\s*(?:[-–—]\s*\d{1,3})?\s*[\.\):]?\s*'
    r'(?:EXACT|NICHE|BROAD|LONG[- ]?TAIL|ТОЧНЫЕ|НИШЕВЫЕ|ШИРОКИЕ)\s*(?:TAGS?|ТЕГИ)?\s*[\-–—:]\s*',
    re.IGNORECASE)


def _tierle_ayir(raw):
    """Modelin 3 satirlik katmanli etiket ciktisini tek listeye cevir (sira korunur):
    Line 1 EXACT -> Line 2 NICHE -> Line 3 BROAD. YouTube ilk etiketlere daha cok
    agirlik verdigi icin sira onemlidir. Tek satir gelirse klasik temizlik uygulanir."""
    lines = [l.strip() for l in (raw or "").splitlines() if l.strip()]
    if not lines:
        return ""
    parcalar = []
    for line in lines:
        line = _TIER_ETIKET_RE.sub("", line).strip()
        if not line or line.endswith(":"):
            continue
        parcalar.append(line)
    return _clean_tags(", ".join(parcalar))


def _fit_tag_field(tags_text, limit=TAG_FIELD_LIMIT, min_count=12):
    """500 karakter alan sinirini asarsa SONDAKI (en genel) etiketlerden kirp."""
    items = [t.strip() for t in (tags_text or "").split(",") if t.strip()]
    while len(", ".join(items)) > limit and len(items) > min_count:
        items.pop()
    return ", ".join(items)


def _tag_issues(tags_text):
    """Etiket alani denetimi: YouTube alani 500 karakter (virguller dahil)."""
    if not tags_text:
        return ["empty"]
    issues = []
    if "#" in tags_text:
        issues.append("no # symbols")
    count = len([t for t in tags_text.split(",") if t.strip()])
    if count < TAG_MIN_COUNT:
        issues.append(f"only {count} tags (need {TAG_MIN_COUNT}+)")
    total = len(tags_text)
    if total > TAG_FIELD_LIMIT:
        issues.append(f"{total} chars > {TAG_FIELD_LIMIT} field limit")
    if total < TAG_MIN_TOTAL:
        issues.append(f"only {total} chars (fill the {TAG_FIELD_LIMIT}-char field)")
    return issues


def generate_tags(voice_text, tags_prompt_template, channel_name, max_retries=2):
    """Etiket uret: profesyonel piramit promptu (spesifik -> nis -> genel) +
    500 karakter alan siniri. En fazla 2 tur; sonra deterministik temiz liste
    dondurulur (eski 10 + 10 turluk dongu kaldirildi)."""
    tags_sysp = tags_prompt_template.format(voice_text=voice_text)
    tags = ""
    for attempt in range(max(1, max_retries)):
        raw = gemini_uret("Create tags for this voiceover.", tags_sysp, channel_name)
        tags = _fit_tag_field(_tierle_ayir(raw.strip() if raw else ""))
        issues = _tag_issues(tags)
        if not issues:
            return tags, True
        print(f"⚠️ [Bulut] Etiket sorunları: {', '.join(issues)}, yeniden deneniyor... ({attempt+1}/{max_retries})")
    return tags, False


def fix_tags(tags_text, channel_name, max_retries=1):
    """Etiket bicim sorunlarini TEK turda duzelt, sonra deterministik bitir."""
    issues = _tag_issues(tags_text)
    if not issues:
        return tags_text, True
    print(f"🔧 [Bulut] Etiket düzeltiliyor: {', '.join(issues)}...")
    fix_prompt = f"""Fix these YouTube tags: {', '.join(issues)}.
Rules: KEEP every existing tag (fix, do not replace), then ADD more 2-4 word long-tail keyword phrases
about the same topic until the list has 24-30 tags and the whole text is 350-{TAG_FIELD_LIMIT} characters
(commas and spaces count). Order: most specific first, broadest last. Russian + English, no # symbols,
no vague abstract words, no near-duplicate tags.
Current tags: {tags_text}
Output exactly 3 lines (EXACT / NICHE / BROAD), comma-separated, no labels."""
    raw = gemini_uret("Fix tags", fix_prompt, channel_name)
    if raw and not raw.startswith("❌"):
        fixed = _fit_tag_field(_tierle_ayir(raw.strip()))
        if fixed:
            tags_text = fixed
    return tags_text, True


def translate_to_turkish(text, text_label, channel_name):
    """Translate a text to Turkish. Verifies completeness (length) and retries if truncated."""
    prompt = f"""Translate the COMPLETE {text_label} below to Turkish. Keep the same meaning, tone, and hook question style.

{text_label}:
{text}

Rules:
1. Translate EVERY sentence from start to finish — NEVER stop early, NEVER skip or summarize parts.
2. Output ONLY the Turkish translation, nothing else (no notes, no original text)."""
    expected_min = max(30, int(len(text) * 0.45))
    best = ""
    for attempt in range(3):
        raw = gemini_uret(f"Translate {text_label} to Turkish", prompt, channel_name)
        if not raw or raw.startswith("❌"):
            continue
        out = raw.strip()
        if len(out) >= expected_min:
            return out
        if len(out) > len(best):
            best = out
        print(f"⚠️ [Bulut] {text_label} cevirisi cok kisa ({len(out)}/{len(text)} karakter), tekrar deneniyor... ({attempt+1}/3)")
    return best if best else text


DEFAULT_TITLE_PROMPT = """Based on this voiceover text, write ONE YouTube Shorts title.

Voiceover:
{voice_text}

Rules (Shorts mobil feed'e gore — hepsi zorunlu):
1. ONE hook, ONE promise — a strong hook about the video's MAIN TOPIC/CONCEPT, not just the first sentence.
2. HOOK IN THE FIRST 2-3 WORDS: mobile feed shows only ~40 characters, so open with the hook word (Почему / Как / Зачем / Что / Кто / Секрет / Вот / Это).
3. MAIN KEYWORD EARLY: the main topic name MUST appear as a PLAIN WORD inside the first 30 characters (not only inside a hashtag).
4. Hook text (before the emoji) max 40 characters. TOTAL title (hook + 1 emoji + 1-2 hashtags) max 60 characters, hard limit 65. Never cut a word in the middle.
5. EXACTLY ONE emoji, placed right before the hashtags.
6. 1-2 hashtags max, taken from the video's ACTUAL content. NEVER generic (#кино, #шортс, #shorts, #факты, #марвел). No space before #.
7. Numbers score extra when the topic naturally has one (year, count, "3 факта").
8. Concrete and specific: no vague hype ("смотри до конца", "невероятно", "шок"), no ALL-CAPS words, no promise the voiceover does not deliver.
9. NEVER name a movie/character that is not in the voiceover; use official Russian dub names, «English» in guillemets when unsure.

Write ONLY the title, one line."""

DEFAULT_TAGS_PROMPT = """Based on this voiceover text, write the YouTube tag list for a Russian Shorts video.

Voiceover:
{voice_text}

Rules:
1. Output THREE lines in this exact order, comma-separated, no # symbols, no line labels:
   - Line 1 — 10-12 EXACT tags: exact topic names viewers type (official Russian form + English original) and long-tail phrases from THIS video. Write them as PHRASES of 2-4 words, not single words — viewers search phrases (e.g. "тор без молота", "хела против тора", "мстители судный день финал", "avengers doomsday ending explained").
   - Line 2 — 10-12 NICHE tags: the niche keywords tied to this video's sub-topic (character nicknames, actor names, specific objects/abilities/places/events).
   - Line 3 — 4-6 BROAD tags: e.g. "марвел", "mcu", "marvel", "кино новости"
2. Total 24-30 tags, 350-500 characters INCLUDING commas (YouTube's tag field limit is 500). Fill the field as far as GENUINELY RELEVANT keywords allow — never pad with junk, near-duplicates or made-up words. Most specific first, broadest last — YouTube weighs the first tags more.
3. Include ONLY real alternative spellings viewers actually type (with/without hyphen, Latin vs Russian, singular/plural) — NEVER invent typos or garbled word forms; every tag must be a correctly spelled real keyword. Single-word tags are allowed only in the BROAD tier.
4. ONLY real names/topics that appear in the voiceover or are direct aliases of it. Correct official names ("Avengers Doomsday" not "Avengers Judgement Day").
5. NEVER use vague abstract concepts (герой, судьба, наследие, технологии) — no search volume, filtered out automatically.
6. Spell every tag correctly (except intentional common variants).

Output exactly 3 lines (EXACT / NICHE / BROAD), comma-separated, no labels."""


def run_voice_pipeline(tam_metin, raw_title, voice_prompt, title_prompt_template, tags_prompt_template, channel_name, lang, char_limit):
    """Main pipeline: sequential decomposed steps. Each rule must pass before next starts."""
    if title_prompt_template is None:
        title_prompt_template = DEFAULT_TITLE_PROMPT
    if tags_prompt_template is None:
        tags_prompt_template = DEFAULT_TAGS_PROMPT
    lang_label = {"ru": "Russian", "de": "German"}.get(lang, "Russian")
    t_key = f"title_{lang}"
    v_key = f"voice_{lang}"

    # === STEP 1: GENERATE VOICE ===
    print("🎤 [Bulut] Ses metni olusturuluyor...")
    with gemini_step("ses-metni"):
        voice_text = generate_voice(tam_metin, voice_prompt, channel_name, lang, char_limit=char_limit)
    if not voice_text:
        print("❌ [Bulut] Ses metni olusturulamadi (tum fallback'ler basarisiz), pipeline durduruluyor.")
        return {t_key: "", "tags": "", v_key: "", "title_tr": "", "voice_tr": "", "transcript_tr": ""}, ""

    # === STEP 2: FIX HOOK (Python verified, loops until pass) ===
    print("🔗 [Bulut] Hook kontrol ediliyor...")
    qa = not questions_banned(channel_name)
    for _ in range(MAX_VERIFY_RETRIES):
        voice_text, hook_ok = fix_hook(voice_text, lang, channel_name)
        if hook_ok:
            hook_ok = python_verify(voice_text, "hook", char_limit, questions_allowed=qa)
        if hook_ok:
            break
        print("🔁 [Bulut] Hook basarisiz, yeniden deneniyor...")
    else:
        print("⚠️ [Bulut] Hook max deneme, mevcut haliyle devam.")
    print("✅ [Bulut] Hook OK")

    # === STEP 3: FIX LAST SENTENCE (Python verified, loops until pass) ===
    print("❓ [Bulut] Son cumle kontrol ediliyor...")
    for _ in range(MAX_VERIFY_RETRIES):
        voice_text, last_ok = fix_last_sentence(voice_text, lang, channel_name)
        if last_ok:
            last_ok = python_verify(voice_text, "last_sentence", char_limit, questions_allowed=qa)
        if last_ok:
            break
        print("🔁 [Bulut] Son cumle basarisiz, yeniden deneniyor...")
    else:
        print("⚠️ [Bulut] Son cumle max deneme, mevcut haliyle devam.")
    print("✅ [Bulut] Son cumle OK")

    # === STEP 4: FIX REPETITION (Python verified, loops until pass) ===
    print("🔄 [Bulut] Tekrar kontrol ediliyor...")
    for _ in range(MAX_VERIFY_RETRIES):
        voice_text, rep_ok = fix_repetition(voice_text, lang, channel_name)
        if rep_ok:
            rep_ok = python_verify(voice_text, "repetition", char_limit)
        if rep_ok:
            break
        print("🔁 [Bulut] Tekrar basarisiz, yeniden deneniyor...")
    else:
        print("⚠️ [Bulut] Tekrar max deneme, mevcut haliyle devam.")
    print("✅ [Bulut] Tekrar OK")

    # === STEP 5: FIX MERGED WORDS (Python verified, loops until pass) ===
    print("🔤 [Bulut] Birleşik kelimeler kontrol ediliyor...")
    for _ in range(MAX_VERIFY_RETRIES):
        voice_text = fix_merged_words(voice_text)
        merge_ok = python_verify(voice_text, "merged_words", char_limit)
        if merge_ok:
            break
        print("🔁 [Bulut] Birleşik kelime sorunu, tekrar deneniyor...")
    else:
        print("⚠️ [Bulut] Birleşik kelime max deneme, mevcut haliyle devam.")
    print("✅ [Bulut] Birleşik kelime OK")

    # === STEP 6: BRACKETS (Python verified, loops until pass) ===
    print("📐 [Bulut] Parantez kontrol ediliyor...")
    for _ in range(MAX_VERIFY_RETRIES):
        voice_text = fix_brackets(voice_text)
        br_ok = python_verify(voice_text, "brackets", char_limit)
        if br_ok:
            break
        print("🔁 [Bulut] Parantez sorunu, tekrar deneniyor...")
    else:
        print("⚠️ [Bulut] Parantez max deneme, mevcut haliyle devam.")
    print("✅ [Bulut] Parantez OK")

    # === STEP 7: LATIN TEXT (Python verified, loops until pass) ===
    print("🔡 [Bulut] Latin karakter kontrol ediliyor...")
    for _ in range(MAX_VERIFY_RETRIES):
        voice_text = fix_latin_text(voice_text, lang)
        lat_ok = python_verify(voice_text, "latin", char_limit)
        if lat_ok:
            break
        print("🔁 [Bulut] Latin karakter sorunu, tekrar deneniyor...")
    else:
        print("⚠️ [Bulut] Latin karakter max deneme, mevcut haliyle devam.")
    print("✅ [Bulut] Latin karakter OK")

    # === STEP 7b: MOVIE TITLE COLONS (regex, 0 Gemini) ===
    voice_text = fix_movie_titles(voice_text)

    # === STEP 7c: RUSSIAN SPELLING + GRAMMAR COMPLETENESS (Gemini, tek cagri) ===
    # Eskiden AYNI prompt iki kez cagriliyordu (video basina +1 Gemini istegi,
    # 7 anahtarin 500 RPD limitinde hissedilir kota israfi). Tek cagri hem yazimi
    # hem eksik fiil/baglaci duzeltir (prompt zaten ikisini de istiyor).
    # Ikinci tur SADECE ilk tur metni belirgin sekilde kisa/bozuk cikardiysa
    # (deterministik tetik) tekrarlanir.
    print("📝 [Bulut] Rusca yazim + gramer kontrol ediliyor...")
    onceki_uzunluk = len(voice_text)
    voice_text = fix_spelling(voice_text, channel_name)
    if len(voice_text) < onceki_uzunluk * 0.7:
        print("📝 [Bulut] Metin belirgin sekilde kisaldi, gramer turu bir kez daha deneniyor...")
        fixed_again = fix_spelling(voice_text, channel_name)
        if len(fixed_again) >= len(voice_text) * 0.7:
            voice_text = fixed_again
    # === STEP 8: CHARACTER LENGTH (fix_length handles everything, no verify needed) ===
    print("📏 [Bulut] Uzunluk kontrol ediliyor...")
    voice_text, _ = fix_length(voice_text, char_limit, lang, channel_name, tam_metin, voice_prompt=voice_prompt)
    print("✅ [Bulut] Uzunluk OK")

    # === STEP 9: GENERATE TITLE (tek gecis; deterministik bitirme) ===
    # Eski hali: 8 tur x 5 deneme + 10 turluk fix dongusu. Simdi: generate_title
    # en fazla 2 tur (3 aday) + gerekirse TEK fix_title; fix_title kendi icinde
    # 2 LLM turu ile sinirli, sonra 0 cagriyla kurallara uydurur.
    print("📰 [Baslik olusturuluyor...")
    title_text, title_ok = generate_title(voice_text, title_prompt_template, channel_name)
    if not title_ok:
        print("⚠️ [Bulut] Baslik uretilemedi, son duzeltme turu...")
        title_text, _ = fix_title(title_text, channel_name)
    print("✅ [Bulut] Baslik OK")

    # === STEP 10: GENERATE TAGS (tek gecis; 500 karakter alani) ===
    print("🏷️ [Bulut] Etiketler olusturuluyor...")
    tags_text, tags_ok = generate_tags(voice_text, tags_prompt_template, channel_name)
    if not tags_ok:
        print("⚠️ [Bulut] Etiket formati tam tutmadi, tek duzeltme turu...")
        tags_text, _ = fix_tags(tags_text, channel_name)
    print("✅ [Bulut] Etiketler OK")

    # Derive the title's hashtag(s) from the video's main topics in the generated tags
    title_text = fix_title_hashtags(title_text, tags_text)

    # === STEP 10b: TAGS LOWERCASE + DEDUP (voice_text keeps proper casing) ===
    tags_text = tags_text.lower()
    # Deduplicate tags while preserving order
    seen = set()
    deduped = []
    for t in tags_text.split(","):
        t_stripped = t.strip()
        if t_stripped and t_stripped not in seen:
            seen.add(t_stripped)
            deduped.append(t_stripped)
    tags_text = ", ".join(deduped)

    # === STEP 10c: FINAL HOOK/LAST SENTENCE SAFETY CHECK ===
    if questions_banned(channel_name):
        # ПопкорнФакты: strip all question marks, convert to statements
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        changed = False
        for s in sents:
            if s.endswith("?"):
                voice_text = voice_text.replace(s, s.rstrip("?").rstrip() + ".", 1)
                changed = True
        if changed:
            print("🔧 [Bulut] Final question strip: sorular ifadeye çevrildi.")
    else:
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        if sents:
            first = sents[0]
            if not first.endswith("?") and not first.endswith("!"):
                voice_text = voice_text.replace(first, first.rstrip(".") + "?", 1)
                print("🔧 [Bulut] Final hook fix: '?' eklendi.")
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        if sents:
            last = sents[-1]
            if not last.endswith("?"):
                voice_text = voice_text.replace(last, last.rstrip(".!") + "?", 1)
                print("🔧 [Bulut] Final last sentence fix: '?' eklendi.")

    # === STEP 11: TURKISH TRANSLATIONS ===
    print("🇹🇷 [Bulut] Turkce ceviriler olusturuluyor...")
    title_tr = translate_to_turkish(title_text, "Title", channel_name)
    voice_tr = translate_to_turkish(voice_text, "Voiceover text", channel_name)
    transcript_tr = translate_to_turkish(tam_metin, "Transcript", channel_name)

    # === BUILD SEO HTML ===
    sections = {t_key: title_text, "tags": tags_text, v_key: voice_text,
                "title_tr": title_tr, "voice_tr": voice_tr, "transcript_tr": transcript_tr}
    seo_html_str = build_seo_html(sections, raw_title, tam_metin, channel_name, lang)

    print(f"✅ [Bulut] Pipeline basariyla tamamlandi: voice={len(voice_text)}ch, title OK, tags OK")
    return sections, seo_html_str
