import os
import re
import subprocess
import tempfile
import shutil
import difflib

def tts_verify(audio_bytes, expected_text, lang="ru"):
    import speech_recognition as sr
    tmp = tempfile.mkdtemp()
    mp3 = os.path.join(tmp, "tts.mp3")
    wav = os.path.join(tmp, "tts.wav")
    with open(mp3, "wb") as f: f.write(audio_bytes)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", mp3, "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav], check=True, capture_output=True)
    r = sr.Recognizer()
    with sr.AudioFile(wav) as source:
        audio = r.record(source)
    try:
        stt_text = r.recognize_whisper(audio, model="small", language=lang)
    except sr.UnknownValueError:
        stt_text = ""
    except sr.RequestError:
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    shutil.rmtree(tmp, ignore_errors=True)
    def norm(s):
        s = s.lower().strip()
        s = re.sub(r'[^\w\s]', '', s)
        return re.sub(r'\s+', ' ', s).strip()
    ne = norm(expected_text)
    ns = norm(stt_text)
    ratio = difflib.SequenceMatcher(None, ne, ns).ratio()
    exp_words = ne.split()
    stt_words = ns.split()
    problem_words = [w for w in exp_words if w not in stt_words]
    return ratio, stt_text, problem_words[:15]
