import json
import os
from shared import *
from functions.gemini_func import evaluate_topic
from functions.transcribe import api_ile_transkript_cek, transkript_cek, transkript_cek_zamanli, yt_dlp_ile_alt_yazi_cek
from constants import platform_tespit_et
from functions.ui import header, footer_done, footer_fail, info, ok, warn, err, step
from bulut_kanali import app, cloud_orchestrator, cloud_transcribe  # #2: ortak bulut katmani

PROMPT = """You write Russian scripts for YouTube Shorts about interesting facts.

Rules:
1. Retell the transcript in your own words (not literal translation)
2. First sentence — hook question
3. Last sentence — question related to the topic, answer NOT in the text
4. No [music] or —

Format:
===TITLE_RU===
[hook question] [1-2 emojis] #[hashtag]
===TAGS===
15 comma-separated tags
===VOICE_RU===
[4-6 sentences, ~600 chars, only facts from transcript]"""

VOICE_PROMPT = """You write Russian voiceover text for YouTube Shorts about interesting facts.

Rules:
1. Retell the transcript in your own words (not literal translation)
2. First sentence — hook question to grab viewer attention
3. Last sentence — REAL viewer-opinion question ending with ?, answer NOT in the text. It MUST ask the viewer's opinion and make them want to comment, e.g. "А как ты думаешь, ...?" or "А ты как считаешь, ...?". NEVER end with a "how/why/when" question about a mechanism the text already explained, and NEVER end with a statement that merely has "?" stuck on it. The final question must be one that cannot be answered from the text alone.
4. MOST IMPORTANT: Focus on the transcript's MAIN TOPIC and MAIN LOGIC, not on listing every fact. If the character limit does NOT allow covering every fact, cover ONLY the most important facts that support the main point — condense or rewrite sentences in your own style as needed, but NEVER break the order of the facts as they appear in the transcript. Drop the least important details first. NEVER drop the fact that explains WHY a theory or conclusion is plausible — that cause/effect detail IS the main logic and must be kept even if you must shorten other sentences to fit. Keep the main idea complete and clear.
5. No [music] or —
6. ALWAYS use the official Russian dub name of every movie/character mentioned. NEVER translate a title literally. If you do NOT know the official Russian dub name, keep the original English name in guillemets «» (e.g. «Secret Wars»), never an invented Russian translation.
7. Use only standard, correct literary Russian. NEVER invent word forms or declensions. If you are unsure how to spell or decline a word, rephrase the sentence to use simpler words you know are correct. NEVER drop a verb or conjunction that the grammar requires — every sentence must be grammatically complete.

Write ONLY the voiceover text, no headers or tags."""

TITLE_PROMPT = """Based on this voiceover text, write a YouTube Shorts title.

Voiceover:
{voice_text}

Rules:
1. Title — strong hook question about the video's MAIN TOPIC/CONCEPT, not just the first sentence
2. Add 1-2 emojis at the end, before the hashtag
3. #hashtag(s) MUST come from the video's ACTUAL content: name ONE or TWO key topics actually discussed (2 hashtags if 2 topics are covered, 1 if only 1). NEVER use generic hashtags like #факты, #интересное, #топ, #шортс, #shorts. Do not leave a space before #.
4. CRITICAL LENGTH BUDGET: the hook question text (before emoji) MUST be SHORT — max 38 characters — because the topic hashtag(s) will be appended at the end. TOTAL title (hook + emoji + hashtags) must NOT exceed 65 characters. Never cut a word in the middle.
5. Use natural Russian words. NEVER use medical terms (e.g. "тремор", "судорога", "спазм") or weird literal translations.
6. NEVER name a movie that is not in the voiceover/transcript. If you mention a movie, use its official Russian dub name; if you do NOT know it, keep the English name in guillemets «» — never substitute a different movie."""

TAGS_PROMPT = """Based on this voiceover text, write 15 comma-separated tags.

Voiceover:
{voice_text}

Rules:
1. Exactly 15 tags, comma-separated
2. No # symbols
3. Mix of Russian and English keywords for search volume
4. MOST IMPORTANT — every tag must be a SPECIFIC, SEARCHABLE keyword directly tied to THIS video's content. Concrete terms only: names, places, historical events, objects, people, dates. NEVER use vague abstract concepts like "история", "факты", "тайна", "тайны", "знание", "жизнь", "смерть", "время", "учёный", "великие" — a viewer would never search those words, and YouTube cannot match them to this video's content.
5. Every tag must appear in the voiceover OR be a direct alias of something in it. Do not tag generic terms that fit any facts video.

Write ONLY the tags, one line."""

# Ses (voice ID) uygulamadan .env'deki VOICE_ID_CH2 ile degistirilebilir.
VOICE_ID = os.environ.get("VOICE_ID_CH2", "M1CSR3PJBsfWU6ZquG3C")
LANG = "ru"
CHANNEL_NAME = "Fakt Za 15"

@app.local_entrypoint()
def main(link: str = None, gun: int = 0, gun_toplam: int = 0):
    subprocess.run(["python", "-m", "pip", "install", "-U", "--quiet", "yt-dlp", "openai-whisper", "SpeechRecognition", "curl_cffi"], capture_output=True)
    ensure_fresh_ytdlp()
    header("🧠 FAKT ZA 15 - ILGINC BILGILER AI TEMIZLEYICI", "Fakt Za 15 kanali secildi")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", "-f", action="store_true", help="Skip topic evaluation")
    parser.add_argument("--gun", type=int, default=0, help="Cok gunlu plan gun no (1..N: cikti kendi GunN klasorune yazilir)")
    parser.add_argument("--gun-toplam", type=int, default=0, help="Cok gunlu plan toplam gun (video) sayisi")
    args, _ = parser.parse_known_args()
    force = args.force
    gun = args.gun or gun or 0
    gun_toplam = args.gun_toplam or gun_toplam or 0
    if gun > 0:
        info(f"📅 Cok gunlu plan: {gun}. gun / {gun_toplam or '?'}")
    if not link:
        link = input("Linki yapistir: ").strip()
    platform = platform_tespit_et(link)
    info(f"🔍 Platform: {platform.upper()}")
    init_db()
    if link_kayitlimi(link):
        err("Bu link daha once islenmis!")
        beep(False)
        footer_fail("Islem atlandi")
        return
    rand_num = random.randint(100, 999)
    tmp = tempfile.mkdtemp()
    video_path = os.path.join(tmp, f"raw_{rand_num}.mp4")
    current_dir = os.getcwd()
    cookies_path = os.path.join(current_dir, "cookies.txt")
    title_cmd = ["python", "-m", "yt_dlp", "--print", "title", "--cookies", cookies_path, "--quiet", "--no-playlist", "--no-progress", link]
    if platform == "youtube":
        title_cmd += ["--remote-components", "ejs:github"]
    title_res = subprocess.run(title_cmd, capture_output=True, text=True)
    raw_title = title_res.stdout.strip() or "video"
    if platform == "youtube":
        dl_cmd = ["python", "-m", "yt_dlp", "-f", "bestvideo[height<=1080]/bestvideo", "-o", video_path, "--cookies", cookies_path, "--remote-components", "ejs:github", "--quiet", "--no-playlist", "--no-progress", link]
    else:
        dl_cmd = ["python", "-m", "yt_dlp", "-f", "best", "-o", video_path, "--cookies", cookies_path, "--quiet", "--no-playlist", "--no-progress", link]
    subprocess.run(dl_cmd, check=True)
    if not os.path.exists(video_path):
        err("Video indirilemedi!")
        beep(False)
        footer_fail("Indirme basarisiz")
        return
    step(1, 4, f"Indirildi: {raw_title}")
    # Transcript (TikTok/Instagram: Modal GPU'da uretilir, bilgisayar yorulmaz)
    step(2, 4, "Transkript cekiliyor...")
    if platform in ("tiktok", "instagram"):
        print("🌐 Ucretsiz altyazi deneniyor...")
        tam_metin = yt_dlp_ile_alt_yazi_cek(link)
        source_timeline = []
        if not tam_metin:
            print("🎙️ Zaman damgali transcript bulutta (Modal GPU) uretiliyor...")
            try:
                with open(video_path, "rb") as f: tv_bytes = f.read()
                tam_metin, source_timeline = cloud_transcribe.remote(tv_bytes)
            except Exception as e:
                print(f"⚠️ [Bulut] Uzak transcript basarisiz: {e}, yerele dusuluyor...")
                tam_metin, source_timeline = transkript_cek_zamanli(link, video_path)
    else:
        tam_metin, source_timeline = transkript_cek_zamanli(link, video_path)
    if tam_metin and not force:
        kayitli = oneri_getir(link, kanal="2")
        if kayitli is not None:
            score, _tip = kayitli
            info(f"📊 Konu puani: {score}/10 (kesif onerisinden alindi, yeniden puanlanmadi)")
        else:
            score = evaluate_topic(tam_metin, raw_title, CHANNEL_NAME)
            info(f"📊 Konu puani: {score}/10")
        if score < 5.5:
            err("Puan dusuk, atlaniyor. Tekrar icin --force kullan.")
            beep(False)
            footer_fail("Konu puani yetersiz")
            return
    elif not tam_metin:
        err("Transcript alinamadi, islem durduruluyor.")
        beep(False)
        footer_fail("Transcript yok")
        return
    with open(video_path, "rb") as f: v_bytes = f.read()
    step(3, 4, "Temizlik + AI basliyor...")
    response = cloud_orchestrator.remote(link, rand_num, v_bytes, raw_title, tam_metin, force=True, source_timeline=source_timeline,
                                          system_prompt=PROMPT, voice_id=VOICE_ID, lang=LANG, channel_name=CHANNEL_NAME,
                                          voice_prompt=VOICE_PROMPT, title_prompt=TITLE_PROMPT, tags_prompt=TAGS_PROMPT)
    if response.get("error"):
        err(f"Hata: {response['error']}")
        beep(False)
        footer_fail("Bulut islemi basarisiz")
        return
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    out_dir = desktop
    if gun > 0:
        out_dir = os.path.join(desktop, f"Gun{gun}_{guvenli_klasor_adi(response['title'])}_{rand_num}")
        os.makedirs(out_dir, exist_ok=True)
    seo_html_str = response.get("seo_html", "")
    audio_bytes = response.get("audio_bytes")
    if audio_bytes:
        audio_path = os.path.join(out_dir, f"{response['title']}_{rand_num}_ses.mp3")
        with open(audio_path, "wb") as f: f.write(audio_bytes)
        ok(f"Ses: {os.path.basename(audio_path)}")
    if response.get("thumb_bytes"):
        thumb_path = os.path.join(out_dir, f"{response['title']}_{rand_num}_THUMB.png")
        with open(thumb_path, "wb") as f: f.write(response["thumb_bytes"])
        ok(f"🖼️ Kapak: {os.path.basename(thumb_path)}")
    if seo_html_str:
        seo_path = os.path.join(out_dir, f"{response['title']}_{rand_num}_SEO.html")
        with open(seo_path, "w", encoding="utf-8") as f: f.write(seo_html_str)
        ok(f"SEO: {os.path.basename(seo_path)}")
    clean_path = os.path.join(out_dir, f"{response['title']}_{rand_num}_CLEAN.mp4")
    with open(clean_path, "wb") as f: f.write(response["video_bytes"])
    link_kaydet(link)
    gpu_cost = (response["gpu_wall_time"] + OVERHEAD_SECONDS * response["num_chunks"]) * GPU_COST_PER_SEC
    step(4, 4, "Sonuclar yazildi")
    if gun > 0:
        ok(f"📁 Klasor: {os.path.basename(out_dir)} (4 dosya icinde)")
    footer_done(f"TAMAM! Video: {os.path.basename(clean_path)}")
    ok(f"GPU: {response['gpu_wall_time']:.1f}s | Maliyet: ${gpu_cost:.4f} | Parca: {response['num_chunks']}")
    beep(True)
