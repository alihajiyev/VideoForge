import json
import os
from shared import *
from functions.gemini_func import evaluate_topic
from functions.transcribe import api_ile_transkript_cek, transkript_cek, transkript_cek_zamanli, yt_dlp_ile_alt_yazi_cek
from constants import platform_tespit_et
from functions.ui import header, footer_done, footer_fail, info, ok, warn, err, step, bar, C
from bulut_kanali import app, cloud_orchestrator, cloud_transcribe  # #2: ortak bulut katmani

PROMPT = """You write Russian scripts for YouTube Shorts about Marvel/DC.

Rules:
1. Faithfully retell the transcript in Russian. Do NOT add, invent, or change any facts. If you are unsure about a fact, use Google Search to verify — but do NOT make things up. Stick to what the transcript says.
2. First sentence — hook question
3. Text structure: short sentence, short sentence, long sentence. NEVER repeat the same idea in consecutive sentences. Each sentence MUST add NEW information. Add an intriguing question in the middle. Conversational tone, natural Russian.
4. Last sentence — question related to the topic, answer NOT in the text
5. Use official Russian Marvel dub names: "Противостояние" not "Гражданская война", "УВИ" not "ТВА" / "TVA", "инкурсия" not "вторжение" for multiverse incursions, "Ваканда" not "Вандакора".
6. No [music] or —
7. Character limit: EXACTLY {char_limit} characters maximum, not more.
8. Enclose movie titles in guillemets «» for proper TTS pronunciation (e.g. «Мстители: Судный день»).

Format:
===TITLE_RU===
[hook question] [1-2 emojis] #[hashtag]
===TAGS===
15 comma-separated tags
===VOICE_RU===
[4-6 sentences, at most {char_limit} chars, only what's in transcript]"""

VOICE_PROMPT = """You write Russian voiceover text for YouTube Shorts about Marvel/DC.

Rules:
1. TRANSLATE the transcript into Russian faithfully. Do NOT change, invert, or reinterpret any fact. Do NOT add explanations, conclusions, or interpretations not in the original transcript. Keep all key comparisons and reveals exactly as they are in meaning.
2. First sentence — hook question ending with ? based on the transcript's main surprising point.
3. Text structure: short sentence, short sentence, long sentence. NEVER repeat the same idea in consecutive sentences. Each sentence MUST add NEW information. Add an intriguing middle question (e.g. "The result?" or "Why?"). Conversational tone.
4. Last sentence — REAL viewer-opinion question ending with ?, answer NOT in the text. It MUST ask the viewer's opinion and make them want to comment, e.g. "А как ты думаешь, ...?" or "А ты как считаешь, ...?". NEVER end with a "how/why/when" question (как/почему/когда) about a mechanism the text already explained, and NEVER end with a statement that merely has "?" stuck on it — a statement with "?" is not a real question and breaks the flow. The final question must be one that cannot be answered from the text alone.
5. ALWAYS use the official Russian Marvel dub name of every movie/character. NEVER translate a title literally. NEVER replace a movie mentioned in the transcript with a different movie — even a famous one. The movies you name MUST be exactly the ones in the transcript. If you do NOT know the official Russian dub name, keep the original English name in guillemets «» (e.g. «Brand New Day»), never an invented Russian translation and never a substitute movie. Official names: "Противостояние" not "Гражданская война", "УВИ" not "ТВА" / "TVA", "инкурсия" not "вторжение" for multiverse incursions, "Ваканда" not "Вандакора".
6. MOST IMPORTANT: Focus on the transcript's MAIN TOPIC and MAIN LOGIC, not on listing every fact. If {char_limit} characters do NOT allow covering every fact, cover ONLY the most important facts that support the main point — condense or rewrite sentences in your own style as needed, but NEVER break the order of the facts as they appear in the transcript. Drop the least important details first. NEVER drop the fact that explains WHY a theory or conclusion is plausible — that cause/effect detail IS the main logic and must be kept even if you must shorten other sentences to fit. Keep the main idea complete and clear.
7. No [music], -, or *.
8. Enclose movie titles in guillemets «» (e.g. «Мстители: Судный день»).
9. Use only standard, correct literary Russian. NEVER invent word forms or declensions. If you are unsure how to spell or decline a word, rephrase the sentence to use simpler words you know are correct. NEVER drop a verb or conjunction that the grammar requires — every sentence must be grammatically complete (e.g. "он понял, что не молот делал его сильным, а он сам сделал молот легендарным" — the verb "сделал" and "что" must be present; never write "а он сам молот легендарным").

Write ONLY the voiceover text, no headers or tags."""

TITLE_PROMPT = """Based on this voiceover text, write a YouTube Shorts title.

Voiceover:
{voice_text}

Rules:
1. Title — strong hook question about the video's MAIN TOPIC/CONCEPT, not just the first sentence
2. Add 1-2 emojis at the end, before the hashtag
3. #hashtag(s) MUST come from the video's ACTUAL content: name ONE or TWO key characters/topics actually discussed in the voiceover, in official Russian form (e.g. if Deadpool vs Wolverine → "#дедпул #росомаха"). Use 2 hashtags if the video compares or discusses 2 subjects, 1 hashtag if only 1 main subject. NEVER use generic channel hashtags like #марвел, #кино, #фильм, #шортс, #shorts, #факты. Do not leave a space before #.
4. CRITICAL LENGTH BUDGET: the hook question text (before emoji) MUST be SHORT — max 38 characters — because the topic hashtag(s) will be appended at the end. TOTAL title (hook + emoji + hashtags) must NOT exceed 65 characters. Never cut a word in the middle.
5. Use natural Russian words. NEVER use medical terms (e.g. "тремор", "судорога", "спазм") or weird literal translations.
6. NEVER name a movie that is not in the voiceover/transcript. If you mention a movie, use its official Russian dub name; if you do NOT know it, keep the English name in guillemets «» — never substitute a different movie."""

TAGS_PROMPT = """Based on this voiceover text, write 15 comma-separated tags.

Voiceover:
{voice_text}

Rules:
1. Exactly 15 tags, comma-separated
2. No # symbols
3. Mix of Russian and English keywords for search volume (e.g. "Мстители Судный день", "Avengers Doomsday", "MCU", "Marvel", "УВИ", "инкурсия")
4. Use correct movie names: "Avengers Doomsday" not "Avengers Judgement Day" or "Avengers Doom".
5. ONLY use movie names and character names that actually appear in the transcript. NEVER use a movie that is not mentioned in the transcript (e.g. if the transcript is about "Spider-Man: Brand New Day", do NOT tag "Spider-Man: No Way Home").
6. Spell-check every tag: no typos (e.g. "Секретные войны" not "Секретные войны" misspelled variants).
7. MOST IMPORTANT — every tag must be a SPECIFIC, SEARCHABLE keyword directly tied to THIS video's content and this channel's niche (Marvel/DC movies). Concrete terms only: character names, movie titles, actor names, specific locations/objects/abilities. NEVER use vague abstract concepts like "герой", "солдат", "сердце", "выбор", "технологии", "наследие", "преемник", "будущее" — a viewer would never search those words, and YouTube cannot match them to this video's content.
8. Every tag must appear in the voiceover OR be a direct alias of something in it (e.g. for "Тор" you may tag "Thor", "Тор 4", "Thor Love and Thunder" if that movie is the topic). Do not tag generic fan terms that fit any Marvel video.

Write ONLY the tags, one line."""

# Ses (voice ID) uygulamadan Ayarlar > API anahtarları bolumunden .env'e yazilir
# (VOICE_ID_CH1). .env yoksa eski sabit deger korunur -> bot bozulmaz.
VOICE_ID = os.environ.get("VOICE_ID_CH1", "M1CSR3PJBsfWU6ZquG3C")
LANG = "ru"
CHANNEL_NAME = "Kino Sekrety"

@app.local_entrypoint()
def main(link: str = None, gun: int = 0, gun_toplam: int = 0):
    subprocess.run(["python", "-m", "pip", "install", "-U", "--quiet", "yt-dlp", "openai-whisper", "SpeechRecognition", "curl_cffi"], capture_output=True)
    ensure_fresh_ytdlp()
    header("☁️  VIDEO INDIRICI & AI TEMIZLEYICI (KINO SEKRETY) ☁️", "Kino Sekrety kanali secildi")
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
        link = input("🔗 Linki yapistir ve Enter'a bas: ")
    platform = platform_tespit_et(link)
    info(f"🔍 Platform: {platform.upper()}")
    init_db()
    if link_kayitlimi(link):
        err("Bu link daha once islenmis!")
        footer_fail("Islem atlandi")
        return
    step(1, 4, "Video yerel bilgisayarda indiriliyor (cookies.txt ile)...")
    start_total_time = time.time()
    rand_num = random.randint(100, 999)
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    local_tmp_dir = tempfile.mkdtemp()
    local_video_path = os.path.join(local_tmp_dir, f"yerel_raw_{rand_num}.mp4")
    current_dir = os.getcwd()
    cookies_path = os.path.join(current_dir, "cookies.txt")
    if platform == "youtube":
        # Cap'i GENISLIK+YUKSEKLIK ile ver: dikey Short'ta 1080p'nin height'i 1920'dir;
        # eski height<=1440 cap'i dikeyde sessizce 720x1280'e dusuruyordu.
        # [ext=mp4] tercihi: dosya adi sabit .mp4 kaliyor (bot bu yolu bekliyor).
        ydl_opts = {"format": "bestvideo[width<=1920][height<=1920][ext=mp4]/bestvideo[width<=1920][height<=1920]/bestvideo", "outtmpl": local_video_path, "cookiefile": cookies_path, "quiet": True, "noplaylist": True, "remote_components": {"ejs:github"}}
    else:
        ydl_opts = {"format": "best", "outtmpl": local_video_path, "cookiefile": cookies_path, "quiet": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            video_info = ydl.extract_info(link, download=True)
            raw_title = video_info.get("title", "video")
    except Exception as e:
        err(f"Yerel indirme hatasi: {e}")
        warn("cookies.txt dosyasinin bu script ile ayni klasorde oldugundan emin ol.")
        beep(False)
        footer_fail("Indirme basarisiz")
        return
    # Transcript (TikTok/Instagram: Modal GPU'da uretilir, bilgisayar yorulmaz)
    step(2, 4, "Transkript cekiliyor...")
    if platform in ("tiktok", "instagram"):
        print("🌐 Ucretsiz altyazi deneniyor...")
        tam_metin = yt_dlp_ile_alt_yazi_cek(link)
        source_timeline = []
        if not tam_metin:
            print("🎙️ Zaman damgali transcript bulutta (Modal GPU) uretiliyor...")
            try:
                with open(local_video_path, "rb") as f: tv_bytes = f.read()
                tam_metin, source_timeline = cloud_transcribe.remote(tv_bytes)
            except Exception as e:
                print(f"⚠️ [Bulut] Uzak transcript basarisiz: {e}, yerele dusuluyor...")
                tam_metin, source_timeline = transkript_cek_zamanli(link, local_video_path)
    else:
        tam_metin, source_timeline = transkript_cek_zamanli(link, local_video_path)
    if tam_metin and not force:
        kayitli = oneri_getir(link, kanal="1")
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
    step(3, 4, "Yerel indirme tamamlandi, veriler buluta yukleniyor...")
    with open(local_video_path, "rb") as f: v_bytes = f.read()
    step(4, 4, "Bulut GPU + AI islemleri basliyor...")
    response = cloud_orchestrator.remote(link, rand_num, v_bytes, raw_title, tam_metin, force=True, source_timeline=source_timeline,
                                          system_prompt=PROMPT, voice_id=VOICE_ID, lang=LANG, channel_name=CHANNEL_NAME,
                                          voice_prompt=VOICE_PROMPT, title_prompt=TITLE_PROMPT, tags_prompt=TAGS_PROMPT)
    if response.get("error"):
        err(f"Islem iptal edildi: {response['error']}")
        beep(False)
        footer_fail("Bulut islemi basarisiz")
        return
    out_dir = desktop_path
    if gun > 0:
        out_dir = os.path.join(desktop_path, f"Gun{gun}_{guvenli_klasor_adi(response['title'])}_{rand_num}")
        os.makedirs(out_dir, exist_ok=True)
    out_name = os.path.join(out_dir, f"{response['title']}_{rand_num}_CLEAN.mp4")
    seo_html_desktop_yolu = os.path.join(out_dir, f"{response['title']}_{rand_num}_SEO.html")
    with open(out_name, "wb") as f: f.write(response["video_bytes"])
    audio_out_name = None
    if response.get("audio_bytes"):
        audio_out_name = os.path.join(out_dir, f"{response['title']}_{rand_num}_VOICEOVER.mp3")
        with open(audio_out_name, "wb") as f: f.write(response["audio_bytes"])
    if response.get("thumb_bytes"):
        thumb_out_name = os.path.join(out_dir, f"{response['title']}_{rand_num}_THUMB.png")
        with open(thumb_out_name, "wb") as f: f.write(response["thumb_bytes"])
        ok(f"🖼️ Kapak: {os.path.basename(thumb_out_name)}")
    with open(seo_html_desktop_yolu, "w", encoding="utf-8") as f: f.write(response["seo_html"])
    link_kaydet(link)
    total_time = time.time() - start_total_time
    gpu_wall_time = response["gpu_wall_time"]
    num_chunks = response["num_chunks"]
    gpu_cost = (response["gpu_wall_time"] + OVERHEAD_SECONDS * response["num_chunks"]) * GPU_COST_PER_SEC
    footer_done("ZAFER! Bulut islemi tamamlandi")
    ok(f"⏱️ Sure: {int(total_time // 60)}dk {int(total_time % 60)}sn | GPU: {num_chunks}x {CLEANER_GPU} | Maliyet: ${gpu_cost:.4f}")
    if gun > 0:
        ok(f"📁 Klasor: {os.path.basename(out_dir)} (4 dosya icinde)")
    ok(f"📁 Video: {os.path.basename(out_name)}")
    if response.get("audio_bytes"):
        ok(f"🎤 Ses: {os.path.basename(audio_out_name)}")
    ok(f"🔥 SEO: {os.path.basename(seo_html_desktop_yolu)}")
    beep(True)
