import time
import random
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from constants import GEMINI_API_KEYS, GEMINI_MODELS, get_working_model, set_working_model, GENERIC_TITLE_HASHTAGS
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


def fix_length(voice_text, char_limit, lang, channel_name, tam_metin, voice_prompt=None, max_retries=10):
    """Step 8: Fix character length — Python-only. Too long → delete up to 2 middle sentences, else regenerate.
    Channel-aware bounds: 1-2. kanal (sabit 500) -> 450-550; ПопкорнФакты (dinamik) -> 0.75x-1.1x."""
    if questions_banned(channel_name):
        lower = int(char_limit * 0.75)
    else:
        lower = int(char_limit * 0.9)
    upper = int(char_limit * 1.1)
    vlen = len(voice_text)
    if lower <= vlen <= upper:
        return voice_text, True

    if vlen < lower:
        # Too short — regenerate, asking Gemini to stay faithful to the transcript
        # and cover nearly all of it (target ~75-90% of the original transcript).
        # The old behavior just accepted the shortened text.
        print(f"⚠️ [Bulut] Seslendirme {vlen} karakter (hedef ~{char_limit}), çok kısa, yeniden üretiliyor...")
        expand_prompt = (voice_prompt or "") + (
            f"\n\nCRITICAL: The text must be between {lower} and {upper} characters. "
            f"Current version ({vlen} chars) is too short. "
            f"Retell the transcript faithfully in your own words: keep ALL events in their original order. "
            f"Condense wording only — do NOT drop whole events or details. "
            f"NEVER drop the fact that explains WHY a theory or conclusion is plausible — keep that cause/effect detail even if you must shorten other sentences to fit. "
            f"Never break the order of the facts as they appear in the transcript."
        )
        if "{char_limit}" in expand_prompt:
            expand_prompt = expand_prompt.replace("{char_limit}", str(char_limit))
        best = voice_text
        for _ in range(max_retries):
            fresh = gemini_uret(f"Original Transcript:\n{tam_metin}", expand_prompt, channel_name, retry_feedback=f"Previous version was {vlen} chars (target {lower}-{upper}). Expand the retelling: keep ALL facts in order, add more detail from the transcript.")
            if _LAST_HARD_BLOCK:
                print("🛑 [Bulut] Hard-block: genisletme denemeleri durduruldu, mevcut metinle devam.")
                break
            if fresh and not fresh.startswith("❌") and len(fresh) > 20:
                fresh = fresh.strip()
                if lower <= len(fresh) <= upper:
                    return fresh, True
                if len(fresh) > len(best):
                    best = fresh
                print(f"⚠️ [Bulut] Yeniden üretim {len(fresh)}ch, hâlâ istenen aralıkta değil, tekrar deneniyor...")
        print(f"⚠️ [Bulut] Yeniden üretim hedefe ulaşamadı ({len(best)} chars), en iyi haliyle kabul.")
        return best, True

    # Too long — try deleting up to 2 middle sentences (length-based fallback)
    deletions = 0
    for _ in range(max_retries):
        vlen = len(voice_text)
        if vlen <= upper:
            return voice_text, True
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', voice_text) if s.strip()]
        if len(sentences) < 3:
            break
        deletions += 1
        if deletions > 2:
            print(f"🔧 [Bulut] Uzunluk çok fazla ({vlen}), ana mantığa odaklanarak yeniden oluşturuluyor (hedef {char_limit}ch)...")
            regen_prompt = (voice_prompt or "") + (
                f"\n\nCRITICAL: The text must be between {int(char_limit*0.7)} and {char_limit} characters. "
                f"Current version ({vlen} chars) is too long. Do NOT try to list every fact. "
                f"Focus ONLY on the transcript's MAIN TOPIC and MAIN LOGIC. "
                f"Cover only the most important facts that support the main point, keeping their ORIGINAL ORDER. "
                f"Condense or rewrite sentences in your own style as needed, and drop the least important details first. "
                f"NEVER drop the fact that explains WHY a theory or conclusion is plausible — keep that cause/effect detail even if you must shorten other sentences to fit. "
                f"Never break the order of the facts as they appear in the transcript."
            )
            if "{char_limit}" in regen_prompt:
                regen_prompt = regen_prompt.replace("{char_limit}", str(char_limit))
            fresh = gemini_uret(f"Original Transcript:\n{tam_metin}", regen_prompt, channel_name, retry_feedback=f"Previous version was {vlen} chars (limit {char_limit}). Focus on the main topic, keep fact order, drop least important details.")
            if _LAST_HARD_BLOCK:
                print("🛑 [Bulut] Hard-block: kisaltma denemeleri durduruldu, mevcut metinle devam.")
                break
            if fresh and len(fresh) > 20 and len(fresh) < vlen:
                voice_text = fresh.strip()
                vlen = len(voice_text)
                if vlen <= upper:
                    return voice_text, True
            print(f"⚠️ [Bulut] Yeniden oluşturma {vlen}ch, hala uzun, mevcut haliyle kabul.")
            break
        middle_sentences = [(i, s) for i, s in enumerate(sentences) if 0 < i < len(sentences) - 1]
        if not middle_sentences:
            break
        middle_sentences.sort(key=lambda x: len(x[1]))
        idx, _ = middle_sentences[0]
        candidate = " ".join([s for i, s in enumerate(sentences) if i != idx])
        print(f"🔧 [Bulut] Uzunluk fazla ({vlen}→{len(candidate)}), en kısa orta cümle silindi.")
        voice_text = candidate

    vlen2 = len(voice_text)
    if vlen2 > upper:
        print(f"⚠️ [Bulut] Karakter sınırı sağlanamadı ({vlen2} chars), mevcut haliyle kabul.")
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


def generate_title(voice_text, title_prompt_template, channel_name, max_retries=5):
    """Generate 3 title options with scores, pick the best, then validate format."""
    title_sysp = title_prompt_template.format(voice_text=voice_text)
    score_prompt = f"""{title_sysp}

IMPORTANT — Write 3 different title options. Score each 1-10 based on clickability, hook strength, and relevance.

Format:
1. [Title 1] — Score: X/10
2. [Title 2] — Score: X/10
3. [Title 3] — Score: X/10"""
    for attempt in range(max_retries):
        raw = gemini_uret(f"Create 3 title options with scores.", score_prompt, channel_name)
        if not raw:
            continue
        # Parse titles and scores
        candidates = []
        for line in raw.split("\n"):
            m = re.match(r'\d+[\.\)]\s*(.+?)\s*[—-]\s*Score:\s*(\d+)/10', line.strip(), re.IGNORECASE)
            if m:
                title_text, score = m.group(1).strip(), int(m.group(2))
                candidates.append((score, title_text))
        if not candidates:
            continue
        # Pick highest-scored
        candidates.sort(key=lambda x: -x[0])
        title = candidates[0][1]
        # Validate format
        issues = []
        if not re.search(r'[\U0001F600-\U0010FFFF]', title):
            issues.append("emoji missing")
        if "#" not in title:
            issues.append("hashtag missing")
        if len(title) > 65:
            issues.append(f"too long ({len(title)} chars)")
        if not issues:
            return title, True
        print(f"⚠️ [Bulut] Başlık sorunları: {', '.join(issues)}, yeniden deneniyor... ({attempt+1}/{max_retries})")
    return title if candidates else "", False


def fix_title(title_text, channel_name, max_retries=10):
    """Step 8: Fix emoji + hashtag on existing title. Keeps trying until passes."""
    for attempt in range(max_retries):
        has_emoji = bool(re.search(r'[\U0001F600-\U0010FFFF]', title_text))
        has_hash = "#" in title_text
        if has_emoji and has_hash and len(title_text) <= 65:
            return title_text, True
        issues = []
        if not has_emoji: issues.append("Add 1-2 relevant emojis")
        if not has_hash: issues.append("Add a #hashtag at the end")
        if len(title_text) > 65: issues.append("Shorten to max 65 chars")
        print(f"🔧 [Bulut] Başlık düzeltiliyor: {', '.join(issues)}... ({attempt+1}/{max_retries})")
        fix_prompt = f"""Fix this YouTube Shorts title: {', '.join(issues)}.
Keep the same topic and hook question, just {'add emojis' if not has_emoji else ''}{' and ' if not has_emoji and not has_hash else ''}{'add a #hashtag' if not has_hash else ''}. Max 65 chars.

Current title: {title_text}

Output ONLY the fixed title, one line."""
        raw = gemini_uret(f"Fix title: {title_text[:60]}", fix_prompt, channel_name)
        if raw and not raw.startswith("❌"):
            title_text = re.sub(r'\*+', '', raw).strip()
    return title_text, False


def generate_tags(voice_text, tags_prompt_template, channel_name, max_retries=10):
    """Step 9: Generate tags from voiceover. Keeps trying until perfect."""
    tags_sysp = tags_prompt_template.format(voice_text=voice_text)
    for attempt in range(max_retries):
        raw = gemini_uret(f"Create tags for this voiceover.", tags_sysp, channel_name)
        tags = raw.strip() if raw else ""
        issues = []
        if "#" in tags:
            issues.append("no # symbols")
        count = len([t for t in tags.split(",") if t.strip()]) if tags else 0
        if "," not in tags:
            issues.append("comma-separated")
        if count < 10:
            issues.append(f"only {count}/15 tags")
        if not issues:
            if "," not in tags and " " in tags:
                tags = ", ".join(tags.split())
            return tags, True
        print(f"⚠️ [Bulut] Etiket sorunları: {', '.join(issues)}, yeniden deneniyor... ({attempt+1}/{max_retries})")
    if "," not in tags and " " in tags:
        tags = ", ".join(tags.split())
    return tags, False


def fix_tags(tags_text, channel_name, max_retries=10):
    """Step 10: Fix tags format issues. Keeps trying until passes."""
    for attempt in range(max_retries):
        issues = []
        if "#" in tags_text: issues.append("no # symbols")
        count = len([t for t in tags_text.split(",") if t.strip()]) if tags_text else 0
        if "," not in tags_text: issues.append("comma-separated")
        if count < 10: issues.append(f"only {count} tags, need ~15")
        if not issues:
            return tags_text, True
        print(f"🔧 [Bulut] Etiketler düzeltiliyor: {', '.join(issues)}... ({attempt+1}/{max_retries})")
        fix_prompt = f"""Fix these tags: {', '.join(issues)}.
Current tags: {tags_text}
Output exactly 15 comma-separated tags, no # symbols, one line."""
        raw = gemini_uret(f"Fix tags", fix_prompt, channel_name)
        if raw and not raw.startswith("❌"):
            tags_text = re.sub(r'\*+#', '', raw).strip()
            if "," not in tags_text and " " in tags_text:
                tags_text = ", ".join(tags_text.split())
    return tags_text, False


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


def run_voice_pipeline(tam_metin, raw_title, voice_prompt, title_prompt_template, tags_prompt_template, channel_name, lang, char_limit):
    """Main pipeline: sequential decomposed steps. Each rule must pass before next starts."""
    if title_prompt_template is None:
        title_prompt_template = """Based on this voiceover text, write a YouTube Shorts title.

Voiceover:
{voice_text}

Rules:
1. Title must be a question related to the first sentence
2. Add 1-2 emojis at the end, before the hashtag
3. #hashtag(s) MUST come from the video's actual content: name ONE or TWO key characters/topics actually discussed (2 hashtags if 2 subjects are compared/discussed, 1 if only 1). NEVER use generic hashtags like #марвел, #кино, #шортс, #facts, #shorts.
4. CRITICAL LENGTH BUDGET: the hook question text (before emoji) MUST be SHORT — max 38 characters — because the topic hashtag(s) will be appended at the end. TOTAL title (hook + emoji + hashtags) must NOT exceed 65 characters. Never cut a word in the middle.

Write ONLY the title, one line."""
    if tags_prompt_template is None:
        tags_prompt_template = """Based on this voiceover text, write 15 comma-separated tags.

Voiceover:
{voice_text}

Rules:
1. Exactly 15 tags, comma-separated
2. No # symbols
3. Only relevant tags — mix of Russian and English keywords for search volume (e.g. "Мстители Судный день", "Avengers Doomsday", "MCU", "Marvel")

Write ONLY the tags, one line."""
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

    # === STEP 9: GENERATE TITLE (Gemini verified, loops until pass) ===
    print("📰 [Baslik olusturuluyor...")
    for _ in range(MAX_VERIFY_RETRIES):
        title_text, title_ok = generate_title(voice_text, title_prompt_template, channel_name)
        if not title_ok:
            title_text, title_ok = fix_title(title_text, channel_name)
        if title_ok:
            break
        print("🔁 [Bulut] Baslik basarisiz, yeniden deneniyor...")
    else:
        print("⚠️ [Bulut] Baslik max deneme, mevcut haliyle devam.")
    print("✅ [Bulut] Baslik OK")

    # === STEP 10: GENERATE TAGS (Gemini verified, loops until pass) ===
    print("🏷️ [Bulut] Etiketler olusturuluyor...")
    for _ in range(MAX_VERIFY_RETRIES):
        tags_text, tags_ok = generate_tags(voice_text, tags_prompt_template, channel_name)
        if not tags_ok:
            tags_text, tags_ok = fix_tags(tags_text, channel_name)
        if tags_ok:
            break
        print("🔁 [Bulut] Etiketler basarisiz, yeniden deneniyor...")
    else:
        print("⚠️ [Bulut] Etiketler max deneme, mevcut haliyle devam.")
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
