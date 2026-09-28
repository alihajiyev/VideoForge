import json
from shared import *
from functions.gemini_func import evaluate_topic, run_voice_pipeline
from functions.transcribe import transkript_cek, transkript_cek_zamanli, yt_dlp_ile_alt_yazi_cek
from constants import platform_tespit_et, CHANNEL_NAME_KINO_SYJET, VOICE_ID_KINO_SYJET, CHAR_LIMIT_KINO_SYJET, link_kayitlimi
from functions.ui import header, footer_done, footer_fail, info, ok, warn, err, step
from bulut_kanali import app, cloud_orchestrator, cloud_transcribe  # #2: ortak bulut katmani

PROMPT = """You are a cinematic movie narrator retelling a story in Russian, like a professional voiceover artist.
Rules:
1. ABSOLUTELY FORBIDDEN: question sentences ANYWHERE in the text, with or without a '?' mark. Never use '?' anywhere. Also ban question-SHAPED sentences: never start a sentence with "Удастся ли", "Сможет ли", "Печему", "Как", "Что будет", "Зачем", and never use viewer-addressing patterns such as "Печему?", "Как думаете?", "Согласны?", "А что если...". Every sentence MUST be a declarative statement ending with '.' or '!'.
2. THIRD-PERSON narrator perspective only: retell the action and drama as a voiceover artist would. Never address the viewer.
3. Faithfully retell the transcript in Russian, keeping the original event order exactly as they appear in the transcript. Do NOT add, invent, or change any facts. If you are unsure about a fact, keep it as-is from the transcript.
4. KEEP ALL KEY ACTION DETAILS: never skip vivid action beats from the transcript (where someone hides, jumps, climbs, attacks). These visual moments are what hook the viewer. Condense wording but never drop an action step.
5. Text structure: short sentence, short sentence, long sentence. NEVER repeat the same idea in consecutive sentences. Each sentence MUST add NEW information. Conversational tone, natural Russian, but styled as a movie narrator.
6. Last sentence — a DEFINITIVE concluding statement (verdict or result), never a question and never a question in disguise.
7. Use official Russian movie dub names when applicable: "Противостояние" not "Гражданская война", "УВИ" not "ТВА" / "TVA", "Ваканда" not "Вандакора".
8. CRITICAL: Character limit: approximately {char_limit} characters maximum, which should be about 80% of the original transcript length — condense or rewrite sentences in your own style as needed while keeping the main idea and event order complete and clear.
9. No [music] or —
10. Enclose movie titles in guillemets «» for proper TTS pronunciation (e.g. «Мстители: Судный день»).

Format:
===TITLE_RU===
[cinematic title]
===VOICE_RU===
[4-6 sentences, at most {char_limit} chars, only what's in transcript, no questions, 3rd person narrator style]"""

VOICE_PROMPT = """You are a cinematic movie narrator retelling a story in Russian, like a professional voiceover artist.

Rules:
1. ABSOLUTELY FORBIDDEN: question sentences anywhere in the text, with or without a '?' mark. Never use viewer-addressing patterns such as "Печему?", "Как думаете?", "Согласны?", "А что если...", "Угадаешь?". Every sentence MUST be a declarative statement ending with '.' or '!'.
2. THIRD-PERSON narrator perspective only: retell the action and drama as a voiceover artist would. Never address the viewer.
3. TRANSLATE the transcript into Russian faithfully. Do NOT change, invert, or reinterpret any fact. Keep all key comparisons and reveals exactly as they are in meaning.
4. First sentence — hook sentence that sets the scene, not a question.
5. Text structure: short sentence, short sentence, long sentence. NEVER repeat the same idea in consecutive sentences. Each sentence MUST add NEW information. Add intriguing detail in the middle. Conversational tone, natural Russian, styled as a movie narrator.
6. Last sentence — final part of the story. It must be a DEFINITIVE concluding statement (a verdict or result), never a question and never a question in disguise.
7. MOST IMPORTANT: Retell the transcript faithfully — keep ALL facts and events in their original order. Condense wording only (shorter sentences, remove filler), do NOT drop any facts or details. The target length is {char_limit} characters (about 80% of the original transcript). If the text is too long, rewrite sentences more concisely — NEVER omit events, action beats, or causal explanations. Every fact from the transcript must appear in the retelling.
8. ALWAYS use the official Russian Marvel dub name of every movie/character. NEVER translate a title literally. NEVER replace a movie mentioned in the transcript with a different movie. Official names: "Противостояние" not "Гражданская война", "УВИ" not "ТВА" / "TVA", "Ваканда" not "Вандакора".
9. Use only standard, correct literary Russian. NEVER invent word forms or declensions. If you are unsure how to spell or decline a word, rephrase the sentence to use simpler words you know are correct. NEVER drop a verb or conjunction that the grammar requires — every sentence must be grammatically complete.
10. No [music], -, or *.
11. Enclose movie titles in guillemets «» (e.g. «Мстители: Судный день»).

Write ONLY the voiceover text, no headers or tags."""

TITLE_PROMPT = """Based on this voiceover text, write a YouTube Shorts title.

Voiceover:
{voice_text}

Rules:
1. Title — strong hook about the video's MAIN TOPIC/CONCEPT, not just the first sentence
2. Add 1-2 emojis at the end
3. ##hashtag(s) MUST come from the video's ACTUAL content: name ONE or TWO key characters/topics actually discussed in the voiceover, in official Russian form (e.g. if Spider-Man vs Green Goblin → "#черный ###главный антагонíst). Use 2 hashtags if the video compares or discusses 2 subjects, 1 hashtag if only 1 main subject. NEVER use generic channel hashtags like ##кино, ##фильм, ##шортс, ##shorts, ##факты. Do not leave a space before #.
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
6. Spell-check every tag: no typos (e.g. "Секретные войны" not "Секретные Wars" misspelled variants).
7. MOST IMPORTANT — every tag must be a SPECIFIC, SEARCHABLE keyword directly tied to THIS video's content and this channel's niche (cinema/film stories). Concrete terms only: character names, movie titles, actor names, specific locations/objects/abilities. NEVER use vague abstract concepts like "герой", "солдат", "сердце", "выбор", "технологии", "наследие", "преемник", "будущее" — a viewer would never search those words, and YouTube cannot match them to this video's content.

Write ONLY the tags, one line."""

VOICE_ID = VOICE_ID_KINO_SYJET
LANG = "ru"
CHANNEL_NAME = CHANNEL_NAME_KINO_SYJET

@app.local_entrypoint()
def main(link: str = None, gun: int = 0, gun_toplam: int = 0):
    subprocess.run(["python", "-m", "pip", "install", "-U", "--quiet", "yt-dlp"], capture_output=True)
    ensure_fresh_ytdlp()
    header("☁️  ПОПКОРНФАКТЫ - FILM HIKAYESI AI TEMIZLEYICI ☁️", "ПопкорнФакты kanali secildi")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", "-f", action="store_true", help="Skip topic evaluation")
    parser.add_argument("--gun", type=int, default=0, help="Haftalik plan gun no (1-7: cikti kendi klasorune yazilir)")
    parser.add_argument("--gun-toplam", type=int, default=0, help="Haftalik plan toplam video sayisi")
    args, _ = parser.parse_known_args()
    force = args.force
    gun = args.gun or gun or 0
    gun_toplam = args.gun_toplam or gun_toplam or 0
    if gun > 0:
        info(f"📅 Haftalik plan: {gun}. gun / {gun_toplam or '?'}")
    if not link:
        link = input("🔗 Linki yapistir ve Enter'a bas: ")
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
    ydl_opts = {"format": "best", "outtmpl": local_video_path, "cookiefile": cookies_path, "quiet": True, "noplaylist": True, "remote_components": {"ejs:github"}}
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
    if platform_tespit_et(link) in ("tiktok", "instagram"):
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
    # 3. kanal puansiz calisir: konu/oner puani yok, transcript varsa devam.
    if not tam_metin:
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