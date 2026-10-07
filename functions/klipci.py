# -*- coding: utf-8 -*-
"""KLIPCI — uzun videoyu Shorts'a ceviren yerel motor (ucretsiz, anahtarsiz).

NEDEN: Bot su an "kaynak videoyu bul -> bastan sona yeniden anlat" akisiyla
calisiyor (kesif.py + haftalik_islet.py). Ama piyasada asil istenen sey baska:
ELDEKI uzun videoyu (reportaj, podcast, roportaj) alip icinden ONEMLI anlari
bulup dikey Shorts olarak kesmek. OpusClip/opus.pro'nun yaptigi is bu.
Bu modul o isi YEREL ve UCRETSIZ yapar: yt-dlp + ffmpeg + Whisper + OpenCV.

Ne yapar (adim adim):
  1. INDİR        : link -> mp4 (yt-dlp, cookies.txt varsa kullanilir)
  2. TRANSKRIPT    : yt-dlp altyazisi (ucretsiz) -> Transcript API -> Whisper
  3. AN SKORLAMA   : her cumle 0-100 puanlanir (bilgi yogunlugu, hook/merak
                     kelimeleri, sayi/tarih/ozel isim, nadirlik=TF-IDF,
                     ses vurgusu, filler cezasi)
  4. FILLER TEMİZ  : "yani/iste/ee/hmm/you know" gibi dolgu cumleleri ve
                     tekrar eden (near-duplicate) cumleler atilir; sessizlik
                     kesilir -> jump-cut (olu hava yok, "gereksiz sahne yok")
  5. KONU BUTUNLUGU: skorlu bir an tohum secilir, anahtar-kelime ortusmesi ile
                     konunun BASINDAN SONUNA kadar genisletilir (baglam
                     kopmaz, ortadan baslamaz)
  6. KONUSMACI     : kesitler MFCC/F0/centroid ozellikleriyle KMeans ile
                     konusmacilara ayrilir (sklearn; model indirmez)
  7. YUZ TAKİBİ    : YuNet (OpenCV) ile yuzler bulunur, izlenir; konusan
                     kisinin yuzune dudak hareketi enerjisi ile eslenir
  8. RENDER        : 9:16 dikey kadraj. Tek konusan -> tek panel + kafa takibi.
                     2 kisi konusuyor -> ALT/UST 2 panel. 4 kisi -> 4 panel.
  9. SES           : afftdn temizlik + loudnorm (-14 LUFS) + istenirse fon
                     muzigi ducking (ses_isleme.py ile ayni zincir)
 10. QA            : her klip qa_kapisi.py ile denetlenir (siyah kare, donma,
                     sessizlik, sure, LUFS) ve klip_plani.json'a yazilir.

Botun mevcut akisina DOKUNMAZ: yeni dosya, yeni CLI, hicbir sey import etmiyor.
Istersen bot zincirinin SONUNA ekleyebilirsin (bkz. YOL_HARITASI.md madde 24).

Kullanim:
    py -3 functions/klipci.py --link "https://youtube.com/watch?v=XXXX" --klip 3
    py -3 functions/klipci.py --yerel "C:\\video\\reportaj.mp4" --sure 40
    py -3 functions/klipci.py --link ... --plan-sadece          # sadece analiz
    py -3 functions/klipci.py --link ... --hoparlor 4 --ducking --muzik fon.mp3
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime

import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from functions.qa_kapisi import video_denetle, rapor_yaz  # noqa: E402
from functions import ses_isleme  # noqa: E402

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")
ISLETIM = sys.platform

# ---------------------------------------------------------------- sabitler
OUT_W, OUT_H = 1080, 1920          # Shorts dikey cozunurluk
HEDEF_SPK = 48000                  # ffmpeg ic karisim ornekleme hizi

VARSAYILAN_KLIP = 3                # kac klip uretilsin
HEDEF_SURE = 45.0                  # hedef klip suresi (sn)
MIN_SURE = 15.0                    # Shorts alt siniri (qa_kapisi ile ayni)
MAKS_SURE = 60.0                   # Shorts ust siniri (elle secilen sureler)
# --- OTOMATIK MOD (--klip 0 / --sure 0): sayiyi ve sureyi motor secer ---
OTO_KLIP = 0                       # --klip 0 => otomatik: ne kadar ilginc sahne varsa
OTO_MAKS_KLIP = 20                 # emniyet siniri (render suresi / disk)
OTO_SKOR_TABAN = 45.0              # otomatik modda kabul edilen en dusuk pencere skoru
OTO_SKOR_ORAN = 0.72               # en iyi pencereye gore goreli taban (skor * oran)
OTO_SURE = 0                       # --sure 0 => otomatik: sureyi icerik belirler
OTO_MAKS_SURE = 90.0               # otomatik sure ust siniri (kullanici istegi)
OTO_DOYUM = 0.62                   # sonraki kesit bu orandan zayifsa pencere buyumez
OTO_BOSLUK = 3.0                   # otomatik modda bu kadar boslukta pencere kapanir
MIN_KESIT = 0.6                    # bundan kisa transkript parcalari atilir
MAKS_PARCA = 42                    # klip basina en fazla kac kesit (filtergraph siniri)
YSA_ADIM = 0.5                     # yuz tarama adimi (sn)
YSA_KUCUK_W = 128                  # hareket enerjisi icin kucuk kare genisligi
ES_ZAMAN_PENCERE = 1.4             # "ayni anda konusuyor" kabul penceresi (sn)
GORUNUR_TOL = 0.35                 # yuz izi bu yakinlikta "kadrajda" sayilir (sn = bir tarama adimi)
SILHOUETTE_ESIK = 0.22             # konusmaci ayrimi icin minimum ayrim gucu
FILTRE_UZUN = 0.15                 # iki kesit arasi: bu kadar on/arka pay birakilir

# --- gorunsel hook modu (konusma olmayan videolar: savas sahnesi, spor, doga) ---
GORSEL_ADIM = 0.4                  # gorsel analiz ornekleme adimi (sn)
GORSEL_KUCUK_W = 96                # hareket analizi icin kucuk kare genisligi
GORSEL_BLOK = 4                    # hareket merkezi icin 4x4 blok izgarasi
LEAD_IN_MAKS = 8.0                 # kancadan once en fazla kac saniye baglam (konusma modu)
MIN_KONUSMA_KESIT = 4              # bundan az konusma kesiti varsa gorunsel hook modu
MIN_KONUSMA_SANIYE = 8.0           # toplam konusma bunun altindaysa gorunsel hook modu

# Skor agirliklari: HOOK birinci sirada (kanca cumlesi klibi tasir).
AGIRLIK = {"hook": 0.40, "bilgi": 0.20, "nadirlik": 0.16, "vurgu": 0.10, "konu": 0.14}

YUZ_MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
                 "face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUZ_MODEL_ADI = "face_detection_yunet_2023mar.onnx"

# Dolgu (filler) kelimeleri: TR + EN + RU (kanallar TR/RU uretiyor)
FILLER = {
    "yani", "iste", "işte", "sey", "şey", "hmm", "hm", "ee", "eee", "aa", "eeh",
    "falan", "filan", "aslinda", "işin", "acikcasi", "açıkçası", "sonucta",
    "sonuçta", "neyse", "tamam", "peki", "evet", "hayir", "hayır", "yok",
    "um", "uh", "erm", "like", "basically", "actually", "literally", "you",
    "know", "mean", "well", "sort", "kind", "anyway", "so", "right",
    "ну", "это", "вот", "как", "бы", "короче", "значит", "так", "типа",
}

# Merak/hook tetikleyicileri (konusmanin EN DEGERLI cümleleri)
HOOK = {
    "ama", "fakat", "ancak", "aslinda", "aslında", "sir", "sır", "sirri",
    "sırrı", "gizli", "gizem", "sok", "şok", "inanilmaz", "inanılmaz", "ilk",
    "en", "hic", "hiç", "neden", "nasil", "nasıl", "nicin", "niçin", "kim",
    "ne", "nerede", "gercek", "gerçek", "yanlis", "yanlış", "hata", "buyuk",
    "büyük", "kesfetti", "keşfetti", "yapti", "yaptı", "oldu", "olacak",
    "beklenmedik", "herkes", "kimse", "asla", "sadece", "tek", "yuzunden",
    "yüzünden", "cunku", "çünkü", "mesela", "ornegin", "örneğin",
    "but", "why", "how", "what", "never", "secret", "hidden", "first",
    "shocking", "incredible", "because", "however", "mistake", "biggest",
    "почему", "как", "секрет", "впервые", "самый", "шок", "ошибка", "потому",
}

# Izleyiciye dogrudan hitap eden kelimeler (Shorts kancasi icin degerli)
HITAP = {
    "sen", "siz", "size", "seni", "sana", "bana", "bizi", "bize", "benim",
    "kanka", "arkadaslar", "arkadaşlar", "izleyici", "izleyenler", "dostum",
    "you", "your", "yours", "ты", "вы", "вам", "вас",
}

# Turkce/Rusca/Ingilizce basit stopword listesi (nadirlik hesabinda kullanilir)
STOP = {
    "bir", "bu", "su", "şu", "ve", "ile", "icin", "için", "olan", "olarak",
    "daha", "cok", "çok", "kadar", "gibi", "ama", "ancak", "veya", "ya",
    "mi", "mu", "mü", "de", "da", "ki", "ne", "var", "yok", "ise", "hem",
    "the", "and", "that", "this", "with", "for", "was", "are", "were", "you",
    "his", "her", "its", "not", "but", "from", "they", "have", "has", "had",
    "и", "в", "не", "на", "что", "это", "как", "то", "все", "он", "она",
    "был", "была", "были", "для", "или", "но", "из", "у", "же", "бы",
}


# ---------------------------------------------------------------- yardimci
def _yaz(mesaj):
    print(mesaj, flush=True)


def _calistir(komut, timeout=7200):
    """ffmpeg/ffprobe calistirir: (basarili, stdout, stderr)."""
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True,
                               encoding="utf-8", errors="ignore", timeout=timeout)
    except Exception as e:
        return False, "", str(e)
    return sonuc.returncode == 0, sonuc.stdout or "", sonuc.stderr or ""


def _hata_son(hata):
    satirlar = [s for s in (hata or "").strip().splitlines() if s.strip()]
    return satirlar[-1][:220] if satirlar else "bilinmeyen hata"


def masaustu():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _slug(metin, uzunluk=48):
    metin = re.sub(r"[^\w\s-]", "", (metin or "klip"), flags=re.UNICODE).strip()
    metin = re.sub(r"\s+", "_", metin)
    return (metin[:uzunluk] or "klip").strip("_")


def _filtre_yolu(yol):
    """ffmpeg filter argumaninda Windows yolu icin kacis."""
    return yol.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


# ---------------------------------------------------------------- 1. indirme
def video_suresi(video):
    """ffprobe ile video suresi (sn); okunamazsa 0."""
    komut = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video]
    tamam, cikti, _ = _calistir(komut, timeout=120)
    if not tamam:
        return 0.0
    try:
        return float((cikti or "0").strip().splitlines()[0])
    except Exception:
        return 0.0


def video_boyut(video):
    """ffprobe ile gercek kare boyutu (kadraj sinirlamasi icin)."""
    komut = [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video]
    tamam, cikti, _ = _calistir(komut, timeout=120)
    if not tamam:
        return 0, 0
    m = re.match(r"\s*(\d+)\s*[x,]\s*(\d+)", cikti or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def yt_dlp_indir(link, hedef_klasor, maks_yukseklik=1080):
    """yt-dlp ile videoyu indirir; (video_yolu, baslik) doner."""
    try:
        import yt_dlp
    except Exception:
        _yaz("❌ yt-dlp kurulu degil. (pip install yt-dlp)")
        return None, ""
    os.makedirs(hedef_klasor, exist_ok=True)
    cikti = os.path.join(hedef_klasor, "%(id)s.%(ext)s")
    ayar = {
        "format": (f"bestvideo[height<={maks_yukseklik}][ext=mp4]+bestaudio[ext=m4a]/"
                   f"bestvideo[height<={maks_yukseklik}]+bestaudio/best[height<={maks_yukseklik}]/best"),
        "merge_output_format": "mp4",
        "outtmpl": cikti,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
    }
    cook = os.path.join(BASE_DIR, "cookies.txt")
    if os.path.exists(cook):
        ayar["cookiefile"] = cook
    bilgi = {}
    try:
        with yt_dlp.YoutubeDL(ayar) as ydl:
            bilgi = ydl.extract_info(link, download=True) or {}
    except Exception as e:
        _yaz(f"❌ Indirme hatasi: {str(e)[:200]}")
        return None, ""
    dosya = None
    if bilgi.get("requested_downloads"):
        aday = bilgi["requested_downloads"][0].get("filepath")
        if aday and os.path.exists(aday):
            dosya = aday
    if not dosya:
        vid = bilgi.get("id") or ""
        for uzanti in (".mp4", ".mkv", ".webm"):
            aday = os.path.join(hedef_klasor, f"{vid}{uzanti}")
            if os.path.exists(aday):
                dosya = aday
                break
    if not dosya:
        _yaz("❌ Indirilen dosya bulunamadi.")
        return None, ""
    return dosya, (bilgi.get("title") or os.path.basename(dosya))


# ---------------------------------------------------------------- 2. ses
def ses_cikar(video, wav, timeout=3600):
    """Videonun sesini 16 kHz mono wav olarak cikarir.

    Ses akisi YOKSA (sessiz/animasyon video) bos dosya yerine videonun suresi
    kadar SESSIZ wav uretilir; boylece gorsel hook modu da calisir.
    """
    komut = [FFMPEG, "-y", "-hide_banner", "-nostats", "-i", video,
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav]
    tamam, _, hata = _calistir(komut, timeout=timeout)
    if tamam:
        return wav
    sure = video_suresi(video)
    if sure > 0:
        _yaz(f"🔇 Ses akisi yok — {sure:.1f} sn sessiz ses uretiliyor (gorsel hook modu).")
        sessiz = [FFMPEG, "-y", "-hide_banner", "-nostats", "-f", "lavfi",
                  "-i", "anullsrc=r=16000:cl=mono", "-t", f"{sure:.3f}",
                  "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav]
        tamam2, _, _ = _calistir(sessiz, timeout=timeout)
        if tamam2:
            return wav
    _yaz(f"❌ Ses cikarilamadi: {_hata_son(hata)}")
    return None


def ses_oku(wav, baslangic=0.0, sure=None, sr=16000):
    """wav icinden tek bir bolumu float32 numpy dizisi olarak okur (bellek dostu)."""
    try:
        import soundfile as sf
    except Exception:
        return None, sr
    try:
        bas = int(max(0.0, baslangic) * sr)
        adet = int(sure * sr) if sure else -1
        veri, gercek_sr = sf.read(wav, start=bas, frames=adet, dtype="float32", always_2d=False)
        if veri.ndim > 1:
            veri = veri.mean(axis=1)
        return np.asarray(veri, dtype=np.float32), int(gercek_sr)
    except Exception:
        return None, sr


def rms(sinyal):
    if sinyal is None or sinyal.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(sinyal.astype(np.float64))) + 1e-12))


# ---------------------------------------------------------------- 3. transkript
def transkript_al(link, video, dil=None, whisper_model="small"):
    """Zamanli transkript: yt-dlp altyazisi (ucretsiz) -> API -> Whisper."""
    from functions.transcribe import transkript_cek_zamanli, whisper_ile_zamanli_transkript_cek
    kesitler = []
    kaynak = "yok"
    if link:
        try:
            _, kesitler = transkript_cek_zamanli(link, video)
        except Exception as e:
            _yaz(f"⚠️ Altyazi/transkript yolu hata verdi: {str(e)[:120]}")
        if kesitler:
            kaynak = "altyazi/api"
    if not kesitler and video:
        _yaz(f"🎙️ Altyazi yok — Whisper ({whisper_model}) ile yerel transkript uretiliyor (biraz surebilir)...")
        _, kesitler = whisper_ile_zamanli_transkript_cek(video, model_adi=whisper_model)
        if kesitler:
            kaynak = f"whisper:{whisper_model}"
    temiz = []
    for k in kesitler or []:
        try:
            bas = float(k.get("start") or 0.0)
            son = float(k.get("end") or 0.0)
        except Exception:
            continue
        metin = (k.get("text") or "").strip()
        if not metin or son - bas < 0.25:
            continue
        temiz.append({"start": round(bas, 3), "end": round(son, 3), "text": metin})
    return temiz, kaynak


# ---------------------------------------------------------------- 4. konusmaci ayrimi
def _mel_filtre(sr, n_fft, n_mels=26, fmin=50.0, fmax=7600.0):
    def hz_mel(f):
        return 2595.0 * math.log10(1.0 + f / 700.0)

    def mel_hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    noktalar = np.linspace(hz_mel(fmin), hz_mel(fmax), n_mels + 2)
    hz = mel_hz(noktalar)
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    filtre = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        sol, orta, sag = bins[m - 1], bins[m], bins[m + 1]
        if orta <= sol:
            orta = min(sol + 1, n_fft // 2)
        if sag <= orta:
            sag = min(orta + 1, n_fft // 2 + 1)
        for k in range(sol, orta):
            filtre[m - 1, k] = (k - sol) / max(1, orta - sol)
        for k in range(orta, sag):
            filtre[m - 1, k] = (sag - k) / max(1, sag - orta)
    return filtre


def _mfcc(sinyal, sr, n_mfcc=20, n_fft=400, hop=160, n_mels=26):
    """Bagimlilik yok: mel filtre bankasi + DCT-II ile MFCC (numpy)."""
    if sinyal is None or sinyal.size < n_fft:
        return None
    kare_sayisi = 1 + (sinyal.size - n_fft) // hop
    if kare_sayisi < 2:
        return None
    adimlar = np.lib.stride_tricks.as_strided(
        sinyal, shape=(kare_sayisi, n_fft),
        strides=(sinyal.strides[0] * hop, sinyal.strides[0]))
    pencere = np.hanning(n_fft).astype(np.float32)
    spektrum = np.abs(np.fft.rfft(adimlar * pencere, axis=1)) ** 2
    mel = spektrum @ _mel_filtre(sr, n_fft, n_mels).T
    log_mel = np.log(mel + 1e-10)
    n = np.arange(n_mels)
    k = np.arange(n_mfcc + 1).reshape(-1, 1)
    dct = np.cos(math.pi * k * (2 * n + 1) / (2 * n_mels)) * np.sqrt(2.0 / n_mels)
    dct[0] *= 1 / math.sqrt(2)
    katsayi = log_mel @ dct.T
    return katsayi[:, 1:]


def _f0(sinyal, sr, fmin=70.0, fmax=400.0, n_fft=400, hop=160):
    """Otokorelasyon tabanli temel frekans (perde) tahmini."""
    if sinyal is None or sinyal.size < n_fft * 2:
        return 0.0, 0.0
    kare_sayisi = 1 + (sinyal.size - n_fft) // hop
    adimlar = np.lib.stride_tricks.as_strided(
        sinyal, shape=(kare_sayisi, n_fft),
        strides=(sinyal.strides[0] * hop, sinyal.strides[0]))
    kareler = adimlar - adimlar.mean(axis=1, keepdims=True)
    gecik_min = max(2, int(sr / fmax))
    gecik_maks = min(n_fft - 2, int(sr / fmin))
    if gecik_maks <= gecik_min:
        return 0.0, 0.0
    degerler = []
    for kare in kareler:
        if rms(kare) < 0.005:
            continue
        oto = np.correlate(kare, kare, mode="full")[len(kare) - 1:]
        bolum = oto[gecik_min:gecik_maks]
        if bolum.size == 0 or oto[0] <= 0:
            continue
        en_iyi = int(np.argmax(bolum)) + gecik_min
        if bolum.max() / oto[0] < 0.32:
            continue
        degerler.append(sr / en_iyi)
    if not degerler:
        return 0.0, 0.0
    return float(np.median(degerler)), float(np.std(degerler))


def kesit_ozellikleri(sinyal, sr):
    """Bir kesitin konusmaci parmak izi: MFCC ort/std + perde + centroid + zcr + rms."""
    if sinyal is None or sinyal.size < 1600:
        return None
    mfcc = _mfcc(sinyal, sr)
    if mfcc is None:
        return None
    f0, f0_std = _f0(sinyal, sr)
    spektrum = np.abs(np.fft.rfft(sinyal * np.hanning(sinyal.size)))
    frekanslar = np.fft.rfftfreq(sinyal.size, 1.0 / sr)
    toplam = float(spektrum.sum()) + 1e-9
    centroid = float((spektrum * frekanslar).sum() / toplam)
    zcr = float(np.mean(np.abs(np.diff(np.sign(sinyal))) > 0))
    return np.concatenate([
        mfcc.mean(axis=0), mfcc.std(axis=0),
        np.array([f0 / 200.0, f0_std / 100.0, centroid / 4000.0, zcr, rms(sinyal) * 8.0],
                 dtype=np.float32),
    ]).astype(np.float32)


def _ayrim_guvenilir(X, etiketler, k):
    """Kume dengeli mi ve merkezler yeterince uzak mi? (yanlis bolme korumasi)"""
    if k < 2:
        return True
    etiketler = np.asarray(etiketler)
    n = etiketler.size
    boyutlar = [int((etiketler == c).sum()) for c in range(k)]
    if min(boyutlar) < max(3, int(round(n * 0.15))):
        return False
    merkezler = np.vstack([X[etiketler == c].mean(axis=0) for c in range(k)])
    d_min = min(float(np.linalg.norm(merkezler[a] - merkezler[b]))
                for a in range(k) for b in range(a + 1, k))
    yayilim = float(np.mean(np.linalg.norm(X - merkezler[etiketler], axis=1))) + 1e-6
    return d_min >= 1.5 * yayilim


def _etiketle(kesitler, indeks, kume_etiketleri):
    """Kume etiketlerini kesit sirasina yayar (kisa kesitler komsusundan alir)."""
    etiketler = [0] * len(kesitler)
    for j, i in enumerate(indeks):
        etiketler[i] = int(kume_etiketleri[j])
    son = 0
    kume = set(indeks)
    for i in range(len(etiketler)):
        if i in kume:
            son = etiketler[i]
        else:
            etiketler[i] = son
    return etiketler


def hoparlor_ayir(kesitler, wav, mod="auto", sr=16000):
    """Kesitleri konusmacilara ayirir. Donus: (etiketler, k, ayrim_gucu, yontem)."""
    ozellikler = []
    indeks = []
    for i, k in enumerate(kesitler):
        parca, _ = ses_oku(wav, k["start"], max(0.3, k["end"] - k["start"]), sr)
        oz = kesit_ozellikleri(parca, sr)
        if oz is not None:
            ozellikler.append(oz)
            indeks.append(i)
    if len(ozellikler) < 4:
        return [0] * len(kesitler), 1, 0.0, "yetersiz veri"
    X = np.vstack(ozellikler)
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-6)
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    # Ayni ses parmak izine sahip kesitler TEK konusmacidir: tam tekrarlar
    # elenip kumeleme onlarin uzerinde yapilir. Aksi halde 2 kisi 3-4 kumeye
    # bolunebiliyordu (ayni noktanin keyfi bolunmesi).
    Xu = np.unique(np.round(X, 3), axis=0)
    if Xu.shape[0] < 3:
        # Kumeleme icin cok az benzersiz parmak izi var: dogrudan uzaklik karari.
        if Xu.shape[0] == 2 and float(np.linalg.norm(Xu[0] - Xu[1])) >= 2.0:
            yakin0 = np.linalg.norm(X - Xu[0], axis=1) <= np.linalg.norm(X - Xu[1], axis=1)
            return (_etiketle(kesitler, indeks, (~yakin0).astype(int)), 2, 1.0,
                    "uzaklik (2 benzersiz ses)")
        return [0] * len(kesitler), 1, 0.0, "tek konusmaci (ayni ses parmak izi)"

    zorlanan = None
    if str(mod).isdigit():
        zorlanan = max(1, int(mod))
    en_iyi_k, en_iyi_puan, en_iyi_model = 1, -1.0, None
    if zorlanan == 1:
        return [0] * len(kesitler), 1, 0.0, "tek konusmaci (zorlanmis)"
    adaylar = [zorlanan] if zorlanan else range(1, min(4, max(2, len(ozellikler) // 3)) + 1)
    adaylar = [k for k in adaylar if k and 2 <= k <= Xu.shape[0]]
    denemeler = []
    for k in adaylar:
        try:
            model = KMeans(n_clusters=k, n_init=10, random_state=0).fit(Xu)
        except Exception:
            continue
        try:
            puan = float(silhouette_score(Xu, model.labels_))
        except Exception:
            continue
        # Yanlis bolmeyi engelle: kume boyutlari (KESIT duzeyinde) dengeli ve
        # merkezler birbirinden yeterince uzak olmali. Aksi halde "tek kisi =
        # iki konusmaci" hatasi olusur.
        if not zorlanan and (puan < SILHOUETTE_ESIK or
                             not _ayrim_guvenilir(X, model.predict(X), k)):
            continue
        denemeler.append((k, puan, model))
    if denemeler:
        # Comertlik (parsimony): en iyi puana cok yakin olan EN KUCUK k secilir.
        # Aksi halde 2 kisi 3-4 konusmaci sanilabiliyordu.
        zirve = max(p for _k, p, _m in denemeler)
        en_iyi_k, en_iyi_puan, en_iyi_model = min(
            (d for d in denemeler if d[1] >= zirve - 0.03), key=lambda d: d[0])
    if en_iyi_model is None:
        # Kullanici zorladiysa (--hoparlor 2) yine de uygula; ama guven dusuk
        # oldugu icin panel katmani yuz izleriyle ayrica dogrulanir.
        if zorlanan and zorlanan <= Xu.shape[0]:
            try:
                model = KMeans(n_clusters=zorlanan, n_init=10, random_state=0).fit(Xu)
                puan = float(silhouette_score(Xu, model.labels_))
                return (_etiketle(kesitler, indeks, model.predict(X)), zorlanan,
                        round(max(0.0, puan), 3), "kmeans (zorlanmis, ayrim zayif)")
            except Exception:
                pass
        return [0] * len(kesitler), 1, round(max(0.0, en_iyi_puan), 3), "tek konusmaci (ayrim zayif)"
    return (_etiketle(kesitler, indeks, en_iyi_model.predict(X)), en_iyi_k,
            round(max(0.0, en_iyi_puan), 3), "kmeans")


# ---------------------------------------------------------------- 5. yuz takibi
def yuz_modeli(indir=True):
    """YuNet modelini dondurur (yoksa indirir). Bulunamazsa None."""
    klasor = os.path.join(BASE_DIR, "models")
    yol = os.path.join(klasor, YUZ_MODEL_ADI)
    if os.path.exists(yol):
        return yol
    if not indir:
        return None
    try:
        os.makedirs(klasor, exist_ok=True)
        _yaz("⬇️ Yuz modeli indiriliyor (YuNet, 232 KB, bir kez)...")
        gecici = yol + ".tmp"
        urllib.request.urlretrieve(YUZ_MODEL_URL, gecici)
        os.replace(gecici, yol)
        _yaz(f"✅ Yuz modeli hazir: {yol}")
        return yol
    except Exception as e:
        _yaz(f"⚠️ Yuz modeli indirilemedi ({str(e)[:100]}) — kafa takibi yapilamayacak.")
        return None


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    kesisim = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    birlesim = aw * ah + bw * bh - kesisim
    return kesisim / birlesim if birlesim > 0 else 0.0


def _ic_ice_ele(kutular):
    """YuNet ayni yuz icin ic ice (farkli olcekli) birden fazla kutu dondurur.
    IoU tabanli NMS bunlari silmez cunku biri digerinin ICINDE kalir; bu yuzden
    buyuk kutudan kucuk olana dogru gidip ic ice olanlari eleriz."""
    kabuller = []
    for x, y, w, h, g in sorted(kutular, key=lambda k: -(k[2] * k[3])):
        ic = False
        for ax, ay, aw, ah, _ag in kabuller:
            if (ax - 0.15 * aw <= x + w / 2 <= ax + aw + 0.15 * aw and
                    ay - 0.15 * ah <= y + h / 2 <= ay + ah + 0.15 * ah):
                ic = True
                break
        if not ic:
            kabuller.append((x, y, w, h, g))
    return kabuller


def yuz_izleri(video, adim=YSA_ADIM, model_yolu=None, maks_kare=20000):
    """Yuzleri tarayip izler (track) cikarir.

    Donus: {fw, fh, fps, sure, izler:[{id, noktalar:[(t,x,y,w,h)], hareket:[(t,enerji)], aktif:[t]}],
             kucuk:[{t, gri, olcek}]}
    """
    import cv2
    sonuc = {"fw": 0, "fh": 0, "fps": 30.0, "sure": 0.0, "izler": [], "hata": ""}
    if not os.path.exists(video):
        sonuc["hata"] = "video yok"
        return sonuc
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sonuc["hata"] = "video acilamadi"
        return sonuc
    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    kare_sayisi = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sonuc.update({"fw": fw, "fh": fh, "fps": float(fps),
                  "sure": kare_sayisi / fps if fps else 0.0})
    if not model_yolu:
        model_yolu = yuz_modeli()
    if not model_yolu or not os.path.exists(model_yolu):
        sonuc["hata"] = "yuz modeli yok"
        cap.release()
        return sonuc
    try:
        dedektor = cv2.FaceDetectorYN.create(model_yolu, "", (320, 320), 0.55, 0.4, 5000)
    except Exception as e:
        sonuc["hata"] = f"model yuklenemedi: {str(e)[:80]}"
        cap.release()
        return sonuc
    adim_kare = max(1, int(round(fps * adim)))
    kucuk_w = min(YSA_KUCUK_W, fw or YSA_KUCUK_W)
    kucuk_h = max(2, int(round(kucuk_w * (fh / fw)))) if fw else 72
    ornekler = []      # (t, [(x,y,w,h)], gri_kucuk)
    idx = 0
    while len(ornekler) < maks_kare:
        if not cap.grab():
            break
        if idx % adim_kare == 0:
            tamam, kare = cap.retrieve()
            if not tamam:
                break
            gri = cv2.cvtColor(kare, cv2.COLOR_BGR2GRAY)
            kucuk = cv2.resize(gri, (kucuk_w, kucuk_h), interpolation=cv2.INTER_AREA)
            dedektor.setInputSize((fw, fh))
            try:
                _, yuzler = dedektor.detect(kare)
            except Exception:
                yuzler = None
            kutular = []
            if yuzler is not None:
                for y in yuzler:
                    x, yy, w, h = (float(v) for v in y[:4])
                    guven = float(y[-1]) if len(y) > 14 else 0.9
                    if guven < 0.55 or w < fw * 0.02:
                        continue
                    kutular.append((x, yy, w, h, guven))
            ornekler.append({"t": idx / fps, "kutular": _ic_ice_ele(kutular), "gri": kucuk})
        idx += 1
    cap.release()
    if not ornekler:
        sonuc["hata"] = "kare okunamadi"
        return sonuc

    # Izleme: IoU + merkez yakinligi ile acgozlu eslestirme.
    izler = []
    for orn in ornekler:
        kullanilan = set()
        for (x, y, w, h, guven) in sorted(orn["kutular"], key=lambda k: -k[4]):
            en_iyi, en_iyi_puan = None, 0.0
            for j, iz in enumerate(izler):
                if j in kullanilan or not iz["noktalar"]:
                    continue
                son_t, (sx, sy, sw, sh) = iz["noktalar"][-1]
                if orn["t"] - son_t > max(3.0, adim * 6):
                    continue
                puan = _iou((x, y, w, h), (sx, sy, sw, sh))
                merkez_mesafe = math.hypot((x + w / 2) - (sx + sw / 2),
                                           (y + h / 2) - (sy + sh / 2))
                if merkez_mesafe < fw * 0.10:
                    puan = max(puan, 0.35)
                    # Konum yakinligi da kimlik sinyali (sabit kamera/podcast).
                    puan += 0.25 * (1 - merkez_mesafe / (fw * 0.10))
                if puan > en_iyi_puan:
                    en_iyi, en_iyi_puan = j, puan
            if en_iyi is not None and en_iyi_puan >= 0.25:
                izler[en_iyi]["noktalar"].append((orn["t"], (x, y, w, h)))
                kullanilan.add(en_iyi)
            elif guven >= 0.7:
                izler.append({"id": len(izler), "noktalar": [(orn["t"], (x, y, w, h))]})

    # Kisa/gurultulu izleri at + hareket enerjisi (dudak aktivitesi) hesapla.
    en_az = max(2, int(len(ornekler) * 0.03))
    temiz_izler = []
    for iz in izler:
        if len(iz["noktalar"]) < en_az:
            continue
        iz["aktif"] = [t for t, _ in iz["noktalar"]]
        iz["hareket"] = []
        temiz_izler.append(iz)
    for a, b in zip(ornekler, ornekler[1:]):
        if not a["kutular"] and not b["kutular"]:
            continue
        olcek_x = kucuk_w / max(1, fw)
        olcek_y = kucuk_h / max(1, fh)
        fark = None
        for iz in temiz_izler:
            son = [k for k in iz["noktalar"] if k[0] <= a["t"]]
            if not son or a["t"] - son[-1][0] > max(2.0, adim * 4):
                continue
            x, y, w, h = son[-1][1]
            x1 = max(0, min(kucuk_w - 2, int(x * olcek_x)))
            y1 = max(0, min(kucuk_h - 2, int(y * olcek_y)))
            x2 = max(x1 + 1, min(kucuk_w, int((x + w) * olcek_x)))
            y2 = max(y1 + 1, min(kucuk_h, int((y + h) * olcek_y)))
            a_blok = a["gri"][y1:y2, x1:x2].astype(np.float32)
            b_blok = b["gri"][y1:y2, x1:x2].astype(np.float32)
            if a_blok.size == 0 or a_blok.shape != b_blok.shape:
                continue
            if fark is None:
                fark = float(np.mean(np.abs(a_blok - b_blok)))
            enerji = float(np.mean(np.abs(a_blok - b_blok)))
            iz["hareket"].append((b["t"], enerji))
    # Ayni konumda cogalan izleri birlestir (ikiz izler).
    temiz_izler.sort(key=lambda i: -len(i["noktalar"]))
    birlesik = []
    for iz in temiz_izler:
        ort = np.mean([n[1][:2] for n in iz["noktalar"]], axis=0) if iz["noktalar"] else None
        ikiz = False
        for var in birlesik:
            if not var["noktalar"] or ort is None:
                continue
            var_ort = np.mean([n[1][:2] for n in var["noktalar"]], axis=0)
            if math.hypot(*(ort - var_ort)) < fw * 0.06:
                ikiz = True
                break
        if not ikiz:
            birlesik.append(iz)
    for yeni, iz in enumerate(birlesik):
        iz["id"] = yeni
    sonuc["izler"] = birlesik
    sonuc["ornek_sayisi"] = len(ornekler)
    return sonuc


def konusmaci_yuz_esle(kesitler, etiketler, izler):
    """Her konusmaci -> yuz izi. Dudak hareket enerjisi + perde profil ile eslesir.

    Yontem: konusmaci konusurken hangi yuz bolgesinde piksel degisimi (dudak
    hareketi) en yuksekse o iz o konusmacidir. Tek yuz varsa hepsi ona baglanir.
    """
    esleme = {}
    if not izler:
        return esleme, "yuz yok"
    if len(izler) == 1:
        return {e: izler[0]["id"] for e in set(etiketler)}, "tek yuz"
    konusmaci_aralik = {}
    for k, e in zip(kesitler, etiketler):
        konusmaci_aralik.setdefault(e, []).append((k["start"], k["end"]))
    iz_hareket = {iz["id"]: dict(iz.get("hareket") or []) for iz in izler}
    for e, araliklar in konusmaci_aralik.items():
        puanlar = {iz["id"]: [] for iz in izler}
        for iz in izler:
            for t, enerji in (iz.get("hareket") or []):
                if any(a - 0.3 <= t <= b + 0.3 for a, b in araliklar):
                    puanlar[iz["id"]].append(enerji)
        ortalama = {}
        for iz_id, deger in puanlar.items():
            tumu = list(iz_hareket.get(iz_id, {}).values())
            if not deger or not tumu:
                continue
            ort_tum = float(np.mean(tumu)) + 1e-6
            ortalama[iz_id] = float(np.mean(deger)) / ort_tum
        if ortalama:
            esleme[e] = max(ortalama.items(), key=lambda x: x[1])[0]
    # Eslenmeyen konusmacilari bos izlere dagit (en cok konusandan baslayarak).
    kullanilan = set(esleme.values())
    bos = [iz["id"] for iz in izler if iz["id"] not in kullanilan]
    for e in sorted(konusmaci_aralik, key=lambda e: -len(konusmaci_aralik[e])):
        if e in esleme or not bos:
            continue
        esleme[e] = bos.pop(0)
    return esleme, "dudak hareketi"


def yuz_kutusu(iz, t, fw, fh):
    """t anina en yakin yuz kutusu (yoksa cok yakinsa onu kullanir)."""
    if not iz or not iz.get("noktalar"):
        return None
    noktalar = iz["noktalar"]
    en_yakin = min(noktalar, key=lambda n: abs(n[0] - t))
    if abs(en_yakin[0] - t) > 8.0:
        return None
    return en_yakin[1]


def iz_gorunur(iz, t, tol=GORUNUR_TOL):
    """Yuz izi t aninda kadrajda mi? (kamera gecislerinde bos panel acmamak icin)"""
    if not iz:
        return False
    return any(abs(n[0] - t) <= tol for n in (iz.get("noktalar") or []))


def konusmaci_dogrula(etiketler, yuz_esleme, k, ayrim, yuz_bilgi):
    """Konusmaci etiketlerini YUZ IZLERIYLE dogrular.

    Ayni yuz izine dusen iki konusmaci etiketi ASLINDA ayni kisidir. Bu adim
    olmadan tek kisilik video "2 konusmaci" sanilip ayni kisi iki panele
    bolunuyordu. Donus: (etiketler, k, yuz_esleme, ayrim, yontem).
    """
    esleme = dict(yuz_esleme or {})
    if k <= 1 or not etiketler:
        return etiketler, (1 if etiketler else k), esleme, ayrim, "tek konusmaci"
    izler = (yuz_bilgi or {}).get("izler") or []
    if not izler:
        return etiketler, k, esleme, ayrim, "yuz yok (dogrulanamadi)"
    gecerli = {iz["id"] for iz in izler}
    gruplar = {}
    for e in sorted(set(etiketler)):
        iz = esleme.get(e)
        anahtar = ("iz", iz) if (iz is not None and iz in gecerli) else ("etiket", e)
        gruplar.setdefault(anahtar, len(gruplar))
    if len(gruplar) == len(set(etiketler)):
        return etiketler, k, esleme, ayrim, "yuz izleriyle dogrulandi"
    anahtar = {}
    for e in sorted(set(etiketler)):
        iz = esleme.get(e)
        anahtar[e] = gruplar[("iz", iz) if (iz is not None and iz in gecerli) else ("etiket", e)]
    yeni_etiket = [anahtar[e] for e in etiketler]
    yeni_esleme = {}
    for e in sorted(set(etiketler)):
        iz = esleme.get(e)
        if iz is not None and iz in gecerli:
            yeni_esleme[anahtar[e]] = iz
    return yeni_etiket, len(gruplar), yeni_esleme, ayrim, "ayni yuz -> birlestirildi"


# ---------------------------------------------------------------- 6. skorlama
def _kelimeler(metin):
    return [w for w in re.findall(r"[\w'’]+", (metin or "").lower()) if len(w) > 1]


def _icerik_kelimeleri(metin):
    return [w for w in _kelimeler(metin) if w not in STOP and len(w) >= 3]


def _skor_hesapla(k):
    """Kirilim bilesenlerinden 0-100 skor uretir (HOOK birinci sirada).

    konu (konuya uyum) bileseni 'konu_cikar' adiminda doldurulur; once 0.5
    (notr) kabul edilir ki erken asamada skor anlamsiz sismesin.
    """
    c = k.get("kirilim") or {}
    ham = (AGIRLIK["hook"] * float(c.get("hook", 0.0)) +
           AGIRLIK["bilgi"] * float(c.get("bilgi", 0.0)) +
           AGIRLIK["nadirlik"] * float(c.get("nadirlik", 0.0)) +
           AGIRLIK["vurgu"] * float(c.get("vurgu", 0.0)) +
           AGIRLIK["konu"] * float(c.get("konu", 0.5)))
    skor = max(0.0, min(1.0, ham - float(c.get("ceza", 0.0))))
    k["skor"] = round(skor * 100, 1)
    return k["skor"]


def an_skorlari(kesitler, wav, sr=16000):
    """Her kesiti 0-100 arasi puanlar; gerekce kirilimini de doner."""
    if not kesitler:
        return kesitler
    belgeler = [_icerik_kelimeleri(k["text"]) for k in kesitler]
    toplam = len(kesitler)
    df = {}
    for belge in belgeler:
        for kelime in set(belge):
            df[kelime] = df.get(kelime, 0) + 1
    rms_listesi = []
    for k in kesitler:
        parca, _ = ses_oku(wav, k["start"], max(0.2, k["end"] - k["start"]), sr)
        k["rms"] = round(rms(parca) if parca is not None else 0.0, 5)
        rms_listesi.append(k["rms"])
    rms_ort = float(np.mean(rms_listesi)) + 1e-6
    tum_kelimeler = sum(len(b) for b in belgeler) or 1
    for k, belge in zip(kesitler, belgeler):
        metin = k["text"]
        kucuk = metin.lower()
        kelimeler = _kelimeler(metin)
        kelime_sayisi = max(1, len(kelimeler))
        # a) bilgi yogunlugu: sayi/tarih/yuzde + ozel isim (buyuk harf) + birim
        sayi = len(re.findall(r"\b\d[\d.,:]*\b", metin))
        yuzde = len(re.findall(r"%\s*\d|\d\s*%", metin))
        ozel = len([w for w in re.findall(r"\b[A-ZÇĞİÖŞÜА-Я][\w'’]+", metin)][1:])
        yogunluk = min(1.0, (sayi * 1.1 + yuzde * 1.4 + ozel * 0.9) / 3.2)
        # b) HOOK (kanca): merak kelimesi + soru + hitap + haykiris isareti.
        #    Kullanici istegi: kanca cumlesi skorun EN AGIR bileseni.
        hook = len([w for w in kelimeler if w in HOOK])
        soru = 1 if "?" in metin else 0
        hitap = len([w for w in kelimeler if w in HITAP])
        unlem = metin.count("!")
        hook_puan = min(1.0, (hook * 0.8 + soru * 1.2 + hitap * 0.5 + unlem * 0.3) / 2.2)
        # c) nadirlik (TF-IDF benzeri: tum videoda gecmeyen kelimeler degerli)
        if belge:
            nadir = float(np.mean([math.log((toplam + 1) / (df.get(w, 0) + 1)) for w in belge]))
            nadir_puan = min(1.0, nadir / math.log(toplam + 1) * 1.35)
        else:
            nadir_puan = 0.0
        # d) ses vurgusu
        vurgu = min(1.0, (k["rms"] / rms_ort) / 1.35)
        # e) dolgu ve tekrar cezalari
        dolgu = len([w for w in kelimeler if w in FILLER]) / kelime_sayisi
        ceza = min(0.85, dolgu * 4.0)
        if kelime_sayisi <= 3:
            ceza = min(0.95, ceza + 0.45)
        # f) uzunluk dengesi: 6-40 kelime ideal
        if kelime_sayisi < 6:
            ceza = min(0.95, ceza + (6 - kelime_sayisi) * 0.05)
        elif kelime_sayisi > 45:
            ceza = min(0.95, ceza + 0.12)
        k["kirilim"] = {
            "hook": round(hook_puan, 2), "bilgi": round(yogunluk, 2),
            "nadirlik": round(nadir_puan, 2), "vurgu": round(vurgu, 2),
            "konu": 0.5,          # konu_cikar() adiminda gercek deger yazilir
            "ceza": round(ceza, 2),
        }
        _skor_hesapla(k)
        k["kelime"] = kelime_sayisi
        k["sure"] = round(k["end"] - k["start"], 2)
    return kesitler


def filler_temizle(kesitler):
    """Dolgu ve tekrar eden kesitleri ayiklar. Donus: (kalanlar, atilanlar)."""
    kalan, atilan = [], []
    gorulen = []
    for k in kesitler:
        kelimeler = _kelimeler(k["text"])
        if len(k["text"]) < 2 or (k.get("sure") or 0) < MIN_KESIT:
            atilan.append({**k, "sebep": "cok kisa"})
            continue
        icerik = [w for w in kelimeler if w not in FILLER]
        if len(icerik) <= 1:
            atilan.append({**k, "sebep": "sadece dolgu"})
            continue
        if (k.get("kelime") or len(kelimeler)) <= 3 and (k.get("skor") or 0) < 25:
            atilan.append({**k, "sebep": "bilgi yok"})
            continue
        # Near-duplicate: ayni kelime kumesi 3'lü gruplar (shingle) ile
        uchlu = {" ".join(icerik[i:i + 3]) for i in range(max(1, len(icerik) - 2))}
        tekrar = False
        for onceki in gorulen[-40:]:
            if not uchlu or not onceki:
                continue
            kesisim = len(uchlu & onceki) / max(1, min(len(uchlu), len(onceki)))
            if kesisim >= 0.6:
                tekrar = True
                break
        if tekrar:
            atilan.append({**k, "sebep": "tekrar eden icerik"})
            continue
        gorulen.append(uchlu)
        kalan.append(k)
    return kalan, atilan


# ---------------------------------------------------------------- 7. pencere plani
def _kume(metin):
    return set(_icerik_kelimeleri(metin))


def _ortusme(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _tfidf_vektor(belge, idf):
    v = {}
    for w in belge:
        v[w] = v.get(w, 0.0) + 1.0
    for w in list(v):
        v[w] *= idf.get(w, 1.0)
    return v


def _normalle(v):
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    for w in list(v):
        v[w] /= norm
    return v


def _kosinus(a, b):
    if len(a) > len(b):
        a, b = b, a
    return float(sum(x * b.get(w, 0.0) for w, x in a.items()))


def konu_cikar(kesitler, maks_konu=8, esik=0.12):
    """Transkriptteki KONU bloklarini bulur (yerel, model indirmez).

    Amac: "yapay zeka konuyu anlasin". Yontem: TF-IDF vektorleri uzerinde zaman
    sirali acgozlu kumeleme. Her kesite 'konu' (blok no), 'konu_etiket' (blogun
    en ayirt edici kelimeleri), kirilim['konu'] (bloga uyum) ve 'konu_basi'
    yazilir; skorlar bu konu uyumu ile YENIDEN hesaplanir.

    Donus: zaman sirali konu listesi (etiket + sure + ortalama skor).
    """
    if not kesitler:
        return []
    belgeler = [_icerik_kelimeleri(k["text"]) for k in kesitler]
    n = len(kesitler)
    df = {}
    for belge in belgeler:
        for kelime in set(belge):
            df[kelime] = df.get(kelime, 0) + 1
    idf = {w: math.log((n + 1) / (c + 1)) + 1.0 for w, c in df.items()}
    vektorler = [_tfidf_vektor(b, idf) for b in belgeler]
    bloklar = []
    for i, v in enumerate(vektorler):
        if not v:
            continue
        en_iyi, en_iyi_puan = None, 0.0
        for bi, blok in enumerate(bloklar):
            puan = _kosinus(v, blok["merkez"])
            if puan > en_iyi_puan:
                en_iyi, en_iyi_puan = bi, puan
        if en_iyi is not None and (en_iyi_puan >= esik or len(bloklar) >= maks_konu):
            bloklar[en_iyi]["uyeler"].append(i)
            for w, x in v.items():
                bloklar[en_iyi]["toplam"][w] = bloklar[en_iyi]["toplam"].get(w, 0.0) + x
            bloklar[en_iyi]["merkez"] = _normalle(dict(bloklar[en_iyi]["toplam"]))
        else:
            bloklar.append({"toplam": dict(v), "merkez": _normalle(dict(v)), "uyeler": [i]})
    konular = []
    for bi, blok in enumerate(bloklar):
        terimler = sorted(blok["merkez"].items(), key=lambda x: -x[1])
        etiket = ", ".join(w for w, _ in terimler[:3])
        konular.append({"no": bi, "etiket": etiket or f"konu {bi + 1}",
                        "uyeler": list(blok["uyeler"])})
    if not konular:
        return []
    atanmis = {i for blok in bloklar for i in blok["uyeler"]}
    # Bos vektorlu (sayi/tek kelime) kesitleri en yakin zaman komsusunun konusuna ver.
    for i in range(n):
        if i in atanmis:
            continue
        onceki = next((j for j in range(i - 1, -1, -1) if j in atanmis), None)
        sonraki = next((j for j in range(i + 1, n) if j in atanmis), None)
        hedef = (onceki if onceki is not None and (sonraki is None or i - onceki <= sonraki - i)
                 else sonraki)
        if hedef is None:
            konular[0]["uyeler"].append(i)
            continue
        for konu in konular:
            if hedef in konu["uyeler"]:
                konu["uyeler"].append(i)
                break
    for konu in konular:
        for i in konu["uyeler"]:
            k = kesitler[i]
            k["konu"] = konu["no"]
            k["konu_etiket"] = konu["etiket"]
            if i in atanmis:
                uyum = _kosinus(vektorler[i], bloklar[konu["no"]]["merkez"])
                k.setdefault("kirilim", {})["konu"] = round(min(1.0, uyum * 1.8), 2)
    for i, k in enumerate(kesitler):
        k.setdefault("konu", 0)
        kirilim = k.setdefault("kirilim", {})
        if not isinstance(kirilim.get("konu"), (int, float)):
            kirilim["konu"] = 0.5
        onceki = kesitler[i - 1] if i else None
        k["konu_basi"] = bool(onceki is None or onceki.get("konu") != k.get("konu")
                              or (k["start"] - onceki["end"]) > 1.5)
    for k in kesitler:
        _skor_hesapla(k)
    for konu in konular:
        uyeler = sorted(konu.pop("uyeler"))
        konu["kesit_sayisi"] = len(uyeler)
        konu["baslangic"] = round(kesitler[uyeler[0]]["start"], 2) if uyeler else 0.0
        konu["bitis"] = round(kesitler[uyeler[-1]]["end"], 2) if uyeler else 0.0
        konu["skor"] = round(float(np.mean([kesitler[i].get("skor") or 0 for i in uyeler])), 1) if uyeler else 0.0
        konu["baslik"] = kesitler[uyeler[0]]["text"][:70] if uyeler else ""
    konular.sort(key=lambda c: c["baslangic"])
    return konular


def _konusma_suresi(kesitler, bas, son):
    """bas..son (dahil) arasindaki GERCEK konusma suresi (sessizlik haric)."""
    return float(sum(kesitler[i]["end"] - kesitler[i]["start"] for i in range(bas, son + 1)))


def _acilis_skoru(k):
    """Kesitin klip ACILISI olma degeri: kanca + skor + konu basi."""
    c = k.get("kirilim") or {}
    return (0.45 * float(c.get("hook", 0.0)) + 0.30 * (k.get("skor") or 0) / 100.0 +
            0.15 * (1.0 if k.get("konu_basi") else 0.0) + 0.10 * float(c.get("nadirlik", 0.0)))


def oto_pencereleri_sec(pencereler, taban=OTO_SKOR_TABAN, oran=OTO_SKOR_ORAN,
                        maks=OTO_MAKS_KLIP):
    """Otomatik secim: kac klip olacagini kullanici degil VIDEO belirler.

    En iyi pencereye gore goreli bir skor tabani hesaplanir; bu esigi gecen
    BUTUN pencereler secilir (en fazla `maks`). Boylece "5 ilginc sahne varken
    3 klip secmek" gibi sahne kaybi olmaz, zayif sahneler de uretilmez.
    Donus: (secilen_pencereler, skor_esigi).
    """
    if not pencereler:
        return [], 0.0
    en_iyi = max(float(p.get("skor") or 0.0) for p in pencereler)
    esik = max(float(taban), float(oran) * en_iyi)
    secilen = [p for p in pencereler if float(p.get("skor") or 0.0) >= esik][:maks]
    if not secilen:
        secilen = pencereler[:1]      # hicbiri esigi gecmediyse en iyi sahne yine uretilir
    return secilen, round(esik, 1)


def _oto_deger(deger, tip=int):
    """'oto'/'otomatik'/'auto' ya da 0 -> 0 (otomatik mod); aksi halde sayi."""
    metin = str(deger).strip().lower()
    if metin in ("oto", "otomatik", "auto", ""):
        return 0
    return tip(float(metin))


def klip_pencereleri(kesitler, adet=VARSAYILAN_KLIP, hedef_sure=HEDEF_SURE,
                     min_sure=MIN_SURE, maks_sure=MAKS_SURE,
                     oto=False, oto_sure=False):
    """Hook-first + konu farkindalikli klip pencereleri.

    1. Tohum: ACILIS skoru (kanca cumlesi / konu basi) en yuksek kesit.
    2. Pencere ILERI buyur; hedef sureye ulasinca KONU BLOGUNU degistirmez
       (konu butunlugu), uzun sessizlik bosluğunu atlar.
    3. Sahne, dolgu ve sessizlik atildiktan sonra kalan GERCEK konusma suresine
       gore kurulur (min_sure .. maks_sure).
    4. Pencereler ASLA ortusmez.
    5. oto=True      -> sabit klip sayisi yok: butun uygun pencereler dondurulur
                        (secimi oto_pencereleri_sec yapar).
    6. oto_sure=True -> hedef sure yok: pencere, kesit skoru ortalamanin
                        OTO_DOYUM katindan asagi dusunce kapanir (en fazla 90 sn).
    """
    if not kesitler:
        return []
    n = len(kesitler)
    adet_etkin = max(1, int(adet))
    sirali = sorted(range(n), key=lambda i: -_acilis_skoru(kesitler[i]))
    pencereler = []
    for tohum in sirali:
        if len(pencereler) >= adet_etkin * 4:
            break
        if any(p["start"] <= kesitler[tohum]["start"] < p["end"] for p in pencereler):
            continue
        bas = son = tohum
        konu = kesitler[tohum].get("konu")
        kanca_t = kesitler[tohum]["start"]
        sure = _konusma_suresi(kesitler, bas, son)
        ortalama = float(kesitler[tohum].get("skor") or 0.0)
        pencere_basi = kesitler[bas]["start"]
        # 1) AYNI KONU blogunda ileri buyu (konu butunlugu bozulmaz).
        while son + 1 < n:
            sonraki = kesitler[son + 1]
            yeni = sure + (sonraki["end"] - sonraki["start"])
            # Ust sinir HEM gercek konusma suresi HEM klibin ekranda kalacagi span icin
            # gecerli: hedef 45 sn olan kullanici 70 sn'lik klip almaz.
            if (yeni > maks_sure or sonraki["end"] - pencere_basi > maks_sure
                    or sonraki.get("konu") != konu):
                break
            if oto_sure:
                # Otomatik sure: pencere UST USTE iki zayif kesitte kapanir (skor
                # ortalamanin OTO_DOYUM katindan dusukse) ya da uzun bosluk baslarsa.
                # Tek bir sakin cumle klibi kesmez, ilgi tamamen dusunce keser.
                esik = OTO_DOYUM * ortalama
                skor1 = float(sonraki.get("skor") or 0.0)
                skor2 = (float(kesitler[son + 2].get("skor") or 0.0)
                         if son + 2 < n else skor1)
                if sure >= min_sure and skor1 < esik and skor2 < esik:
                    break
                if sonraki["start"] - kesitler[son]["end"] > OTO_BOSLUK:
                    break
            elif sure >= hedef_sure and sonraki["start"] - kesitler[son]["end"] > 2.0:
                break
            son += 1
            sure = yeni
            ortalama = (ortalama * (son - bas) + float(sonraki.get("skor") or 0.0)) / (son - bas + 1)
        # 2) Kancadan ONCE sinirli baglam ekle (kanca ilk 8 saniyede kalsin).
        while bas > 0:
            onceki = kesitler[bas - 1]
            yeni = sure + (onceki["end"] - onceki["start"])
            if (yeni > maks_sure or kesitler[son]["end"] - onceki["start"] > maks_sure
                    or onceki.get("konu") != konu):
                break
            if kanca_t - onceki["start"] > LEAD_IN_MAKS:
                break
            bas -= 1
            sure = yeni
        # 3) Hala kisa ise konu disina tasarak doldur (once ileri, sonra geri).
        while sure < min_sure and (son + 1 < n or bas > 0):
            ileri = (son + 1 < n and
                     sure + (kesitler[son + 1]["end"] - kesitler[son + 1]["start"]) <= maks_sure)
            if ileri:
                son += 1
                sure += kesitler[son]["end"] - kesitler[son]["start"]
            elif bas > 0:
                bas -= 1
                sure += kesitler[bas]["end"] - kesitler[bas]["start"]
            else:
                break
            if sure >= min_sure:
                break
        parcalar = kesitler[bas:son + 1]
        if not parcalar:
            continue
        bas_yeni = parcalar[0]["start"]
        son_yeni = parcalar[-1]["end"]
        konusma = sum(p["end"] - p["start"] for p in parcalar)
        if konusma < min_sure or konusma > maks_sure:
            continue
        if any(bas_yeni < p["end"] - 0.05 and p["start"] < son_yeni - 0.05 for p in pencereler):
            continue
        span = max(0.01, son_yeni - bas_yeni)
        yogunluk = min(1.0, konusma / span)
        konu_orani = sum(1 for p in parcalar if p.get("konu") == parcalar[0].get("konu")) / len(parcalar)
        kirilim = {a: round(float(np.mean([(p.get("kirilim") or {}).get(a, 0.0) for p in parcalar])), 2)
                   for a in ("hook", "bilgi", "nadirlik", "vurgu", "konu")}
        # Acilis kancasi: klibin ILK 8 saniyesindeki en guclu kanca cumlesi.
        acilis_hook = [float((p.get("kirilim") or {}).get("hook", 0.0)) for p in parcalar
                       if p["start"] - bas_yeni <= LEAD_IN_MAKS]
        kirilim["hook_acilis"] = round(max(acilis_hook) if acilis_hook else 0.0, 2)
        kirilim["konu_orani"] = round(konu_orani, 2)
        kirilim["yogunluk"] = round(yogunluk, 2)
        skor = (0.42 * kirilim["hook_acilis"] +
                0.20 * (float(np.mean([p.get("skor") or 0 for p in parcalar])) / 100.0) +
                0.16 * kirilim["nadirlik"] + 0.12 * konu_orani + 0.10 * yogunluk)
        pencereler.append({
            "start": bas_yeni, "end": son_yeni,
            "sure": round(son_yeni - bas_yeni, 2),
            "konusma_suresi": round(konusma, 2),
            "kesitler": parcalar,
            "skor": round(skor * 100, 1),
            "en_yuksek": max((p.get("skor") or 0) for p in parcalar),
            "konu": parcalar[0].get("konu_etiket") or "",
            "konu_no": parcalar[0].get("konu"),
            "kirilim": kirilim,
        })
    pencereler.sort(key=lambda p: -p["skor"])
    if oto:
        return pencereler[:OTO_MAKS_KLIP]
    return pencereler[:adet_etkin]


# ---------------------------------------------------------------- 8. panel/kadraj plani
def _pencere_kutusu(kutu, fw, fh, oran):
    """Yuz kutusuna gore verilen en-boy oraninda kayan kadraj penceresi."""
    # Hedef en-boy oranini koruyan EN BUYUK pencere (kalan alan sonra olceklenir).
    if fh * oran <= fw:
        ch = float(fh)
        cw = ch * oran
    else:
        cw = float(fw)
        ch = cw / oran
    cw = min(cw, fw)
    ch = min(ch, fh)
    if kutu is None:
        cx = (fw - cw) / 2
        cy = (fh - ch) / 2
    else:
        x, y, w, h = kutu
        cx = x + w / 2 - cw / 2
        cy = y + h / 2 - ch / 2
        # Basin ustunde nefes payi birak (kafa ortada dursun).
        cy -= ch * 0.06
    cx = max(0.0, min(fw - cw, cx))
    cy = max(0.0, min(fh - ch, cy))
    cw, ch = int(cw) // 2 * 2, int(ch) // 2 * 2
    cx, cy = int(cx) // 2 * 2, int(cy) // 2 * 2
    return max(2, cw), max(2, ch), max(0, cx), max(0, cy)


PANEL = {
    1: [("tam", OUT_W, OUT_H)],
    2: [("ust", OUT_W, OUT_H // 2), ("alt", OUT_W, OUT_H // 2)],
    3: [("ust", OUT_W, OUT_H // 2), ("sol", OUT_W // 2, OUT_H // 2),
        ("sag", OUT_W // 2, OUT_H // 2)],
    4: [("sol-ust", OUT_W // 2, OUT_H // 2), ("sag-ust", OUT_W // 2, OUT_H // 2),
        ("sol-alt", OUT_W // 2, OUT_H // 2), ("sag-alt", OUT_W // 2, OUT_H // 2)],
}


def _etiket_al(etiketler, kesit, varsayilan_index=0):
    """Kesit -> konusmaci etiketi (sozluk: baslangic saniyesi -> etiket)."""
    if isinstance(etiketler, dict):
        return etiketler.get(round(kesit["start"], 3), 0)
    try:
        return etiketler[varsayilan_index]
    except Exception:
        return 0


def kadraj_plani(pencere, etiketler, yuz_esleme, izler, yuz_bilgi,
                 pencere_sn=ES_ZAMAN_PENCERE, mod="auto"):
    """Kesitleri panel parcalarina boler.

    ONEMLI: Panel sayisi ARTIK konusmaci etiketi sayisindan degil, o anda
    KADRAJDA GERCEKTEN GORUNEN FARKLI YUZ sayisindan gelir:
      * tek yuz kadrajda             -> tek panel (tam ekran + kafa takibi)
      * ayni anda 2/3/4 farkli yuz   -> 2/3/4 panel
    Boylece (a) tek kisilik videoda ayni kisi iki panele bolunmez,
    (b) kamera gecisinde kadrajda olmayan kisi icin bos panel acilmaz.
    """
    iz_map = {iz["id"]: iz for iz in izler}
    fw = yuz_bilgi.get("fw") or 1920
    fh = yuz_bilgi.get("fh") or 1080
    kesitler = pencere["kesitler"]
    ust_sinir = int(mod) if (mod and str(mod).isdigit() and int(mod) > 1) else 0
    parcalar = []
    for sira, k in enumerate(kesitler):
        es = _etiket_al(etiketler, k, sira)
        # Konusan + ayni konusma anindaki (yakin araliktaki) diger konusmacilar.
        yakin = {es}
        for j, diger in enumerate(kesitler):
            if j == sira:
                continue
            if diger["start"] <= k["end"] + pencere_sn and diger["end"] >= k["start"] - pencere_sn:
                yakin.add(_etiket_al(etiketler, diger, j))
        # Etiket -> yuz izi; sadece o an kadrajda olan FARKLI izler panel alir.
        adaylar = []
        for e in [es] + sorted(x for x in yakin if x != es):
            iz_id = yuz_esleme.get(e)
            if iz_id is None or iz_id not in iz_map or iz_id in adaylar:
                continue
            if not iz_gorunur(iz_map[iz_id], k["start"]):
                continue
            adaylar.append(iz_id)
        if ust_sinir:
            adaylar = adaylar[:ust_sinir]
        duzen = 1
        if len(adaylar) >= 2:
            duzen = 4 if len(adaylar) >= 4 else len(adaylar)
        panel_listesi = PANEL[duzen]
        paneller = []
        for idx, (ad, pw, ph) in enumerate(panel_listesi):
            iz_id = adaylar[idx] if idx < len(adaylar) else None
            iz = iz_map.get(iz_id) if iz_id is not None else None
            kutu = yuz_kutusu(iz, k["start"], fw, fh) if iz else None
            oran = pw / max(1, ph)
            cw, ch, cx, cy = _pencere_kutusu(kutu, fw, fh, oran)
            paneller.append({"ad": ad, "yuz_izi": iz_id, "sahip": iz_id,
                             "kutu": [cw, ch, cx, cy], "hedef": [pw, ph]})
        parca = {"start": k["start"], "end": k["end"], "panel_sayisi": duzen,
                 "konusmacilar": sorted(adaylar), "paneller": paneller,
                 "metin": k["text"], "skor": k.get("skor")}
        if (parcalar and parcalar[-1]["panel_sayisi"] == duzen and
                parcalar[-1]["konusmacilar"] == sorted(adaylar) and
                abs(parcalar[-1]["end"] - k["start"]) < 0.4):
            parcalar[-1]["end"] = k["end"]
            parcalar[-1]["metin"] = (parcalar[-1]["metin"] + " " + k["text"]).strip()
            parcalar[-1]["strateji"] = "birlesik"
            for p_yeni, p_eski in zip(paneller, parcalar[-1]["paneller"]):
                p_eski["kutu"] = [int((a + b) / 2) // 2 * 2 for a, b in zip(p_eski["kutu"], p_yeni["kutu"])]
        else:
            parca["strateji"] = "tek"
            parcalar.append(parca)
    return parcalar


# ---------------------------------------------------------------- 9. render
def _kesit_sinirlari(parcalar, pay=FILTRE_UZUN):
    """Her kesit icin ON/AYNI payli tek sinir cifti: (bas, son).

    SES KAYMASI'nin sebebi buydu: video kesiti [start, end] ile, ses kesiti
    [start-0.15, end+0.15] ile kirpiliyordu. Ses her kesitte 0.3 sn daha uzun
    oldugu icin concat sonrasi kacinci kesitteyse o kadar geriye kayiyordu.
    Artik video ve ses AYNI (bas, son) araligini kullanir; kenarlardaki kucuk
    pay hece kaybini onler, ust uste binme de kirpilir.
    """
    sinirlar = []
    onceki_son = None
    for p in parcalar:
        bas = max(0.0, float(p["start"]) - pay)
        son = float(p["end"]) + pay
        if onceki_son is not None and bas < onceki_son:
            bas = onceki_son
        if son - bas < 0.2:
            son = bas + 0.2
        sinirlar.append((round(bas, 3), round(son, 3)))
        onceki_son = son
    return sinirlar


def _kesit_video_zinciri(kaynak, kesit, paneller, cikis_etiket, onek="", sinir=None):
    """Bir kesitin video zincirini uretir: trim + (panel birlestirme) + dikey olcek.

    `onek`: ffmpeg etiketleri graf genelinde TEK olmak zorunda oldugu icin her
    kesit icin benzersiz bir on ek (orn. "3_") verilir.
    `sinir`: ses ile AYNI olmasi gereken (bas, son) kesim siniri.
    """
    bas, son = sinir if sinir else (kesit["start"], kesit["end"])
    oncu = f"{kaynak}trim=start={bas:.3f}:end={son:.3f},setpts=PTS-STARTPTS"
    kuyruk = f"fps=30,format=yuv420p,setsar=1{cikis_etiket}"
    if len(paneller) == 1:
        cw, ch, cx, cy = paneller[0]["kutu"]
        pw, ph = paneller[0]["hedef"]
        return f"{oncu},crop={cw}:{ch}:{cx}:{cy},scale={pw}:{ph}:flags=bicubic,{kuyruk}"
    n = len(paneller)
    adlar = [f"{onek}p{i}" for i in range(n)]
    parcalar = [f"{oncu},split={n}" + "".join(f"[{a}]" for a in adlar)]
    q = []
    for i, p in enumerate(paneller):
        cw, ch, cx, cy = p["kutu"]
        pw, ph = p["hedef"]
        etiket = f"{onek}q{i}"
        parcalar.append(f"[{adlar[i]}]crop={cw}:{ch}:{cx}:{cy},"
                        f"scale={pw}:{ph}:force_original_aspect_ratio=increase,"
                        f"crop={pw}:{ph},setsar=1,format=yuv420p[{etiket}]")
        q.append(f"[{etiket}]")
    if n == 2:
        parcalar.append(f"{q[0]}{q[1]}vstack=inputs=2")
    elif n == 3:
        parcalar.append(f"{q[1]}{q[2]}hstack=inputs=2[{onek}alt]")
        parcalar.append(f"{q[0]}[{onek}alt]vstack=inputs=2")
    elif n == 4:
        parcalar.append(f"{q[0]}{q[1]}hstack=inputs=2[{onek}ust]")
        parcalar.append(f"{q[2]}{q[3]}hstack=inputs=2[{onek}alt]")
        parcalar.append(f"[{onek}ust][{onek}alt]vstack=inputs=2")
    else:
        cw, ch, cx, cy = paneller[0]["kutu"]
        return f"{oncu},crop={cw}:{ch}:{cx}:{cy},scale={OUT_W}:{OUT_H},{kuyruk}"
    # Son panel zincirinin cikisi dogrudan hedef etikete baglanir.
    parcalar[-1] = parcalar[-1] + "," + kuyruk
    return ";".join(parcalar)


def _kadrajlari_sinirla(parcalar, video):
    """Kadraj pencerelerini GERCEK kare boyutuna gore kirpar.

    Kafa takibi atlandiginda ya da yuz taramasi basarisiz oldugunda kadraj
    varsayilan (1920x1080) boyuta gore hesaplanmis olabilir; 720p ya da dikey
    bir kaynakta bu "crop boyutu kareden buyuk" hatasi verirdi.
    """
    fw, fh = video_boyut(video)
    if not fw or not fh:
        return
    for p in parcalar:
        for panel in p.get("paneller") or []:
            cw, ch, cx, cy = panel["kutu"]
            if cw <= fw and ch <= fh:
                continue
            oran = min(fw / cw, fh / ch)
            merkez_x = cx + cw / 2
            merkez_y = cy + ch / 2
            cw = max(2, int(cw * oran) // 2 * 2)
            ch = max(2, int(ch * oran) // 2 * 2)
            cx = max(0, min(fw - cw, int(merkez_x - cw / 2) // 2 * 2))
            cy = max(0, min(fh - ch, int(merkez_y - ch / 2) // 2 * 2))
            panel["kutu"] = [cw, ch, cx, cy]


def _ses_zinciri(parcalar, siddet="orta", etiket="[aout]", sinirlar=None):
    """Kesitleri tek ses akisina cevirir + temizlik/loudnorm uygular.

    `sinirlar`: video ile AYNI kesim sinirlari (ses kaymasini onler).
    """
    n = len(parcalar)
    zincir = []
    if n == 1:
        zincir.append("[0:a]anull[a0]")
    else:
        zincir.append(f"[0:a]asplit={n}" + "".join(f"[a{i}]" for i in range(n)))
    cikislar = []
    for i, p in enumerate(parcalar):
        bas, son = sinirlar[i] if sinirlar else (p["start"], p["end"])
        zincir.append(
            f"[a{i}]atrim=start={bas:.3f}:end={son:.3f},asetpts=PTS-STARTPTS,"
            f"aformat=sample_fmts=fltp:sample_rates={HEDEF_SPK}:channel_layouts=stereo[au{i}]")
        cikislar.append(f"[au{i}]")
    if n == 1:
        zincir.append("[au0]anull[aconcat]")
    else:
        zincir.append("".join(cikislar) + f"concat=n={n}:v=0:a=1[aconcat]")
    nr, nf = ses_isleme.SIDDET.get(siddet, ses_isleme.SIDDET["orta"])
    zincir.append(f"[aconcat]afftdn=nr={nr}:nf={nf}:tn=1,highpass=f=80,"
                  f"acompressor=threshold=-18dB:ratio=2.5:attack=8:release=180,"
                  f"loudnorm=I={ses_isleme.HEDEF_LUFS}:TP={ses_isleme.HEDEF_TRUE_PEAK}:"
                  f"LRA={ses_isleme.HEDEF_LRA},aformat=sample_rates={HEDEF_SPK}:"
                  f"channel_layouts=stereo{etiket}")
    return ";".join(zincir)


# aktif gurultu siddeti (klip_render tarafindan set edilir)


def klip_render(video, parcalar, cikis, muzik=None, ducking_db=-16.0, siddet="orta",
                altyazi_srt=None, altyazi_yak=False, timeout=7200, sinirlar=None):
    """Klip parcalarini tek gecisde keser/birlestirir, sesi isler ve yazar.

    Video ve ses AYNI `sinirlar` ile kirpilir -> kesitler arasi ses kaymasi yok.
    """
    if not parcalar:
        return False, "parca yok"
    if len(parcalar) > MAKS_PARCA:
        parcalar = parcalar[:MAKS_PARCA]
        if sinirlar:
            sinirlar = sinirlar[:MAKS_PARCA]
    n = len(parcalar)
    if not sinirlar or len(sinirlar) != n:
        sinirlar = _kesit_sinirlari(parcalar)
    _kadrajlari_sinirla(parcalar, video)
    video_zincir = []
    if n == 1:
        zincir = _kesit_video_zinciri("[0:v]", parcalar[0], parcalar[0]["paneller"], "[v0]",
                                      sinir=sinirlar[0])
        video_zincir.append(zincir)
    else:
        video_zincir.append(f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n)))
        for i, p in enumerate(parcalar):
            video_zincir.append(_kesit_video_zinciri(f"[s{i}]", p, p["paneller"], f"[v{i}]",
                                                    onek=f"{i}_", sinir=sinirlar[i]))
    video_zincir.append("".join(f"[v{i}]" for i in range(n)) +
                        ("null[vout]" if n == 1 else f"concat=n={n}:v=1:a=0[vout]"))
    filtre = ";".join(video_zincir + [_ses_zinciri(parcalar, siddet=siddet, sinirlar=sinirlar)])
    gecici = cikis + ".sessiz.mp4"
    komut = [FFMPEG, "-y", "-hide_banner", "-nostats", "-i", video,
             "-filter_complex", filtre, "-map", "[vout]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-r", "30",
             "-c:a", "aac", "-b:a", "160k", "-ar", str(HEDEF_SPK), "-ac", "2",
             "-movflags", "+faststart", gecici]
    tamam, _, hata = _calistir(komut, timeout=timeout)
    if not tamam:
        try:
            os.remove(gecici)
        except Exception:
            pass
        return False, _hata_son(hata)

    kaynak = gecici
    # 1) Fon muzigi: konusma varken kisan ducking (ikinci gecis, video kopyalanir)
    if muzik and os.path.exists(muzik):
        tmp = tempfile.mkdtemp(prefix="vf_klip_")
        try:
            ses_wav = os.path.join(tmp, "ses.wav")
            ok1, _, _ = _calistir([FFMPEG, "-y", "-hide_banner", "-nostats", "-i", kaynak,
                                   "-vn", "-c:a", "pcm_s16le", ses_wav], timeout=timeout)
            karisim = os.path.join(tmp, "karisim.wav")
            if ok1 and ses_isleme.muzik_ducking(ses_wav, muzik, karisim, ducking_db=ducking_db):
                muxlu = cikis + ".muzik.mp4"
                ok2, _, hata2 = _calistir(
                    [FFMPEG, "-y", "-hide_banner", "-nostats", "-i", kaynak, "-i", karisim,
                     "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                     "-b:a", "160k", "-shortest", "-movflags", "+faststart", muxlu],
                    timeout=timeout)
                if ok2:
                    kaynak = muxlu
                else:
                    _yaz(f"⚠️ Muzik mux hatasi: {_hata_son(hata2)}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    # 2) Altyazi yakma (istenirse)
    if altyazi_yak and altyazi_srt and os.path.exists(altyazi_srt):
        yanmis = cikis + ".alt.mp4"
        stil = ("FontName=Arial,FontSize=15,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=2,Shadow=0,MarginV=140,Bold=1")
        ok3, _, hata3 = _calistir(
            [FFMPEG, "-y", "-hide_banner", "-nostats", "-i", kaynak,
             "-vf", f"subtitles='{_filtre_yolu(altyazi_srt)}':force_style='{stil}'",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "copy", "-movflags", "+faststart", yanmis], timeout=timeout)
        if ok3:
            kaynak = yanmis
        else:
            _yaz(f"⚠️ Altyazi yakilamadi ({_hata_son(hata3)}), altyazisiz surum kullaniliyor.")
    try:
        os.replace(kaynak, cikis)
        if kaynak != gecici and os.path.exists(gecici):
            os.remove(gecici)
    except Exception as e:
        return False, f"cikti yazilamadi: {str(e)[:120]}"
    return True, ""


def srt_yaz(parcalar, yol, sinirlar=None):
    """Klibin kesilmis zaman cizgisine gore SRT altyazi uretir (ucretsiz).

    Zaman cizgisi render ile AYNI `sinirlar` uzerinden kurulur; boylece altyazi
    da sesten kaymaz.
    """
    def _ts(sn):
        ms = int(round(sn * 1000))
        s, ms = divmod(ms, 1000)
        d, s = divmod(s, 60)
        sa, d = divmod(d, 60)
        return f"{sa:02d}:{d:02d}:{s:02d},{ms:03d}"

    if not sinirlar or len(sinirlar) != len(parcalar):
        sinirlar = _kesit_sinirlari(parcalar)
    satirlar = []
    imlec = 0.0
    for i, p in enumerate(parcalar, start=1):
        bas, son = sinirlar[i - 1]
        sure = max(0.2, son - bas)
        metin = (p.get("metin") or "").strip()
        if not metin:
            continue
        satirlar.append(f"{i}\n{_ts(imlec)} --> {_ts(imlec + sure)}\n{metin}\n")
        imlec += sure
    if not satirlar:
        return None
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar))
    return yol


# ---------------------------------------------------------------- 9b. gorsel hook modu
def _sure_metni(saniye):
    """saniye -> "1:12" (baslik/slug icin)."""
    s = max(0, int(round(saniye or 0)))
    return f"{s // 60}:{s % 60:02d}"


def _merkez_pencere(merkez, fw, fh, oran, dolgu=0.92):
    """Hareket merkezine gore istenen en-boy oraninda kadraj penceresi."""
    if fh * oran <= fw:
        ch = float(fh) * dolgu
        cw = ch * oran
    else:
        cw = float(fw) * dolgu
        ch = cw / oran
    cx = float(merkez[0]) * fw - cw / 2
    cy = float(merkez[1]) * fh - ch / 2
    cx = max(0.0, min(fw - cw, cx))
    cy = max(0.0, min(fh - ch, cy))
    return max(2, int(cw) // 2 * 2), max(2, int(ch) // 2 * 2), int(cx) // 2 * 2, int(cy) // 2 * 2


def gorsel_analiz(video, wav=None, adim=GORSEL_ADIM, sr=16000, maks_ornek=30000):
    """Konusma OLMAYAN videolar icin gorsel hook analizi (yerel, hizli).

    Marvel savas sahnesi gibi konusmasiz videolarda sahne secimi konusmaya gore
    yapilamaz; bu yuzden GORSEL enerji olculur:
      * kare farki                -> HAREKET (aksiyon yogunlugu)
      * histogram farki           -> SAHNE KESMESI (yeni sahne = hook)
      * gri standart sapma        -> gorsel zenginlik/kontrast
      * ses RMS (varsa)           -> vurgu (patlama, muzik yukselmesi)
      * 4x4 blok farki            -> HAREKET MERKEZI (akilli dikey kadraj)
    """
    import cv2
    sonuc = {"adim": adim, "sure": 0.0, "fw": 0, "fh": 0, "fps": 30.0,
             "hucreler": [], "kesme_sayisi": 0, "hata": ""}
    if not os.path.exists(video):
        sonuc["hata"] = "video yok"
        return sonuc
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sonuc["hata"] = "video acilamadi"
        return sonuc
    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    kare_sayisi = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sonuc.update({"fw": fw, "fh": fh, "fps": float(fps),
                  "sure": kare_sayisi / fps if fps else 0.0})
    kucuk_w = min(GORSEL_KUCUK_W, fw or GORSEL_KUCUK_W)
    kucuk_h = max(GORSEL_BLOK, int(round(kucuk_w * (fh / fw)))) if fw else 54
    if kucuk_w >= GORSEL_BLOK:
        kucuk_w -= kucuk_w % GORSEL_BLOK
    if kucuk_h >= GORSEL_BLOK:
        kucuk_h -= kucuk_h % GORSEL_BLOK
    adim_kare = max(1, int(round(fps * adim)))
    idx = 0
    ornekler = []
    while len(ornekler) < maks_ornek:
        if not cap.grab():
            break
        if idx % adim_kare == 0:
            tamam, kare = cap.retrieve()
            if not tamam:
                break
            gri = cv2.cvtColor(cv2.resize(kare, (kucuk_w, kucuk_h),
                                          interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gri], [0], None, [32], [0, 256]).flatten()
            hist = hist / (float(hist.sum()) + 1e-9)
            ornekler.append({"t": idx / fps, "gri": gri, "hist": hist})
        idx += 1
    cap.release()
    if len(ornekler) < 3:
        sonuc["hata"] = "kare okunamadi"
        return sonuc
    hareket, kesme, kontrast, merkezler = [], [], [], []
    for a, b in zip(ornekler, ornekler[1:]):
        fark = np.abs(a["gri"].astype(np.float32) - b["gri"].astype(np.float32))
        hareket.append(float(fark.mean()))
        kesme.append(float(0.5 * np.abs(a["hist"] - b["hist"]).sum()))
        kontrast.append(float(b["gri"].std()))
        bh, bw = fark.shape
        bh -= bh % GORSEL_BLOK
        bw -= bw % GORSEL_BLOK
        if bh >= GORSEL_BLOK and bw >= GORSEL_BLOK:
            blok = fark[:bh, :bw].reshape(GORSEL_BLOK, bh // GORSEL_BLOK,
                                          GORSEL_BLOK, bw // GORSEL_BLOK).mean(axis=(1, 3))
            toplam = float(blok.sum()) + 1e-6
            bx = float((blok.sum(axis=0) * (np.arange(GORSEL_BLOK) + 0.5)).sum() / toplam) / GORSEL_BLOK
            by = float((blok.sum(axis=1) * (np.arange(GORSEL_BLOK) + 0.5)).sum() / toplam) / GORSEL_BLOK
            merkezler.append((bx, by))
        else:
            merkezler.append((0.5, 0.5))
    sesler = []
    for o in ornekler[1:]:
        parca, _ = ses_oku(wav, o["t"], adim, sr) if wav else (None, sr)
        sesler.append(rms(parca) if parca is not None else 0.0)

    def _nrm(dizi, yuzdelik=95.0):
        if not dizi:
            return list(dizi)
        tavan = float(np.percentile(dizi, yuzdelik)) + 1e-9
        return [min(1.0, float(v) / tavan) for v in dizi]

    hareket_n = _nrm(hareket)
    ses_n = _nrm(sesler)
    kontrast_n = _nrm(kontrast)
    kesme_esik = float(np.mean(kesme) + 1.5 * (np.std(kesme) + 1e-6)) if kesme else 0.0
    kesme_n = [1.0 if v >= kesme_esik and v > 0.06 else 0.0 for v in kesme]
    yumusak = ([float(np.mean(hareket_n[max(0, i - 1):i + 2])) for i in range(len(hareket_n))]
               if len(hareket_n) >= 3 else hareket_n)
    hucreler = []
    for i, o in enumerate(ornekler[1:]):
        skor = (0.45 * yumusak[i] + 0.25 * kesme_n[i] + 0.18 * ses_n[i] + 0.12 * kontrast_n[i])
        hucreler.append({
            "t": round(o["t"], 2), "skor": round(skor, 3),
            "hareket": round(hareket_n[i], 3), "kesme": int(kesme_n[i]),
            "ses": round(ses_n[i], 3), "zenginlik": round(kontrast_n[i], 3),
            "merkez": [round(merkezler[i][0], 3), round(merkezler[i][1], 3)],
        })
    sonuc["hucreler"] = hucreler
    sonuc["kesme_sayisi"] = int(sum(kesme_n))
    return sonuc


def _gorsel_oto_son(hucreler, zirve_i, bas, video_sure, min_sure, maks_sure):
    """Gorsel hook klibinin suresini ICERIK belirler (otomatik sure).

    Klibin acilisindaki enerji zirvesi referans alinir; enerji zirvenin
    OTO_DOYUM katindan asagi dusunce pencere kapanir (en fazla maks_sure).
    """
    zirve = max(1e-6, float(hucreler[zirve_i].get("skor") or 0.0))
    esik = OTO_DOYUM * zirve
    son = bas
    while son + 2.0 <= video_sure and son - bas < maks_sure:
        blok = [float(h.get("skor") or 0.0) for h in hucreler
                if son < h["t"] <= min(video_sure, son + 2.0)]
        if blok and (sum(blok) / len(blok)) < esik and son - bas >= min_sure:
            break
        son = min(video_sure, son + 2.0)
    if son - bas < min_sure:
        son = min(video_sure, bas + min_sure)
    return round(son, 2)


def gorsel_pencereleri(hucreler, adet=VARSAYILAN_KLIP, sure=HEDEF_SURE,
                       min_sure=MIN_SURE, maks_sure=MAKS_SURE, video_sure=None,
                       oto=False, oto_sure=False):
    """Hook-first gorsel pencereler: en yuksek enerjili an klibin ACILISINDA.

    oto=True: kac pencere olacagini video belirler (skor esigini gecenler).
    oto_sure=True: pencere uzunlugunu enerji egrisi belirler (maks OTO_MAKS_SURE).
    """
    if not hucreler:
        return []
    if not video_sure:
        video_sure = hucreler[-1]["t"] + GORSEL_ADIM
    hedef = max(min_sure, min(maks_sure, float(sure)))
    adet_etkin = OTO_MAKS_KLIP if oto else max(1, int(adet))
    indeksler = sorted(range(len(hucreler)), key=lambda i: -hucreler[i]["skor"])
    pencereler = []
    for i in indeksler:
        if len(pencereler) >= adet_etkin:
            break
        bas = hucreler[i]["t"]
        if oto_sure:
            son = _gorsel_oto_son(hucreler, i, bas, video_sure, min_sure, maks_sure)
        else:
            son = min(video_sure, bas + hedef)
        if son - bas < min_sure:
            bas = max(0.0, son - min_sure)
        if any(bas < p["end"] - 0.2 and p["start"] < son - 0.2 for p in pencereler):
            continue
        ic = [h for h in hucreler if bas <= h["t"] < son]
        if not ic:
            continue
        acilis = [h["skor"] for h in ic if h["t"] - bas <= 2.0] or [ic[0]["skor"]]
        kirilim = {
            "hook_acilis": round(float(np.mean(acilis)), 2),
            "hareket": round(float(np.mean([h["hareket"] for h in ic])), 2),
            "ses": round(float(np.mean([h["ses"] for h in ic])), 2),
            "kesme": int(sum(h["kesme"] for h in ic)),
            "zenginlik": round(float(np.mean([h["zenginlik"] for h in ic])), 2),
        }
        skor = (0.45 * kirilim["hook_acilis"] + 0.25 * kirilim["hareket"] +
                0.20 * kirilim["ses"] + 0.10 * min(1.0, kirilim["kesme"] / 6.0))
        pencereler.append({
            "start": round(bas, 2), "end": round(son, 2),
            "sure": round(son - bas, 2), "konusma_suresi": 0.0,
            "kesitler": [], "hucreler": ic,
            "skor": round(skor * 100, 1), "en_yuksek": round(skor * 100, 1),
            "konu": "görsel hook", "konu_no": 0, "kirilim": kirilim,
        })
    pencereler.sort(key=lambda p: -p["skor"])
    if oto:
        return pencereler[:OTO_MAKS_KLIP]
    return pencereler[:adet_etkin]


def gorsel_kadraj_plani(pencere, fw, fh, adim=4.0):
    """Gorsel hook klibini 1 panelli parcalara boler; kadraj hareketi izler."""
    hucreler = pencere.get("hucreler") or []
    if not hucreler:
        return []
    oran = OUT_W / OUT_H
    parcalar = []
    i = 0
    while i < len(hucreler):
        t0 = hucreler[i]["t"]
        blok = [h for h in hucreler if t0 <= h["t"] < t0 + adim]
        if not blok:
            break
        agirlik = sum(h["hareket"] + 0.01 for h in blok)
        mx = sum(h["merkez"][0] * (h["hareket"] + 0.01) for h in blok) / agirlik
        my = sum(h["merkez"][1] * (h["hareket"] + 0.01) for h in blok) / agirlik
        merkez = [0.5 + (mx - 0.5) * 0.85, 0.5 + (my - 0.5) * 0.85]
        bas = t0
        son = min(pencere["end"], t0 + adim)
        if son - bas < 0.3:
            break
        cw, ch, cx, cy = _merkez_pencere(merkez, fw, fh, oran)
        paneller = [{"ad": "tam", "yuz_izi": None, "sahip": None,
                     "kutu": [cw, ch, cx, cy], "hedef": [OUT_W, OUT_H]}]
        parcalar.append({"start": round(bas, 2), "end": round(son, 2), "panel_sayisi": 1,
                         "konusmacilar": [], "paneller": paneller, "metin": "",
                         "skor": pencere.get("skor"), "strateji": "gorsel"})
        i += len(blok)
    return parcalar


# ---------------------------------------------------------------- 10. ana akis
def videoyu_analiz_et(video, link=None, dil=None, whisper_model="small", hoparlor="auto",
                      yuz_atla=False, ilerleme=None):
    """Indirilmis videodan analiz katmani.

    Konusma VARSA  -> 'konusma' modu: zamanli transkript -> konu bloklari ->
                      hook skoru -> konusmaci/panel plani.
    Konusma YOKSA  -> 'gorsel' modu: sahne kesmesi + hareket + ses ile
                      gorsel hook plani (or. savas/aksiyon sahnesi).
    """
    def adim(mesaj):
        _yaz(mesaj)
        if ilerleme:
            ilerleme(mesaj)

    gecici = tempfile.mkdtemp(prefix="vf_klip_analiz_")
    wav = os.path.join(gecici, "ses.wav")
    adim("🎧 Ses cikariliyor...")
    if not ses_cikar(video, wav):
        shutil.rmtree(gecici, ignore_errors=True)
        return None
    adim("📝 Transkript hazirlaniyor (yt-dlp altyazisi -> API -> Whisper)...")
    kesitler, kaynak = transkript_al(link, video, dil=dil, whisper_model=whisper_model)
    toplam_konusma = sum(max(0.0, float(k["end"]) - float(k["start"])) for k in (kesitler or []))
    yeterli = len(kesitler or []) >= MIN_KONUSMA_KESIT and toplam_konusma >= MIN_KONUSMA_SANIYE
    if not yeterli:
        adim(f"🎬 Konusma yok/az ({len(kesitler or [])} kesit, {toplam_konusma:.1f} sn) — GORSEL HOOK "
             f"modu: sahne kesmesi + hareket + ses enerjisi analiz ediliyor...")
        gorsel = gorsel_analiz(video, wav)
        if gorsel.get("hata"):
            _yaz(f"❌ Gorsel analiz de yapilamadi: {gorsel['hata']}")
            shutil.rmtree(gecici, ignore_errors=True)
            return None
        adim(f"✅ {len(gorsel['hucreler'])} enerji hucresi, {gorsel['kesme_sayisi']} sahne kesmesi bulundu.")
        shutil.rmtree(gecici, ignore_errors=True)
        return {
            "mod": "gorsel", "video": video, "link": link, "kesitler": [], "atilan": [],
            "konular": [], "etiketler": {}, "konusmaci_sayisi": 0, "ayrim_gucu": 0.0,
            "ayrim_yontemi": "konusma yok",
            "yuz": {"fw": gorsel.get("fw") or 0, "fh": gorsel.get("fh") or 0,
                    "izler": [], "sure": gorsel.get("sure") or 0.0, "hata": ""},
            "yuz_esleme": {}, "esleme_yontemi": "yok",
            "transkript_kaynagi": kaynak or "yok (gorsel hook modu)",
            "gorsel": gorsel,
        }
    adim(f"✅ {len(kesitler)} konusma kesiti bulundu (kaynak: {kaynak}, {toplam_konusma:.1f} sn konusma).")
    adim("🎯 Onemli anlar skorlaniyor (hook-first)...")
    kesitler = an_skorlari(kesitler, wav)
    temiz, atilan = filler_temizle(kesitler)
    if temiz:
        adim(f"🧹 {len(atilan)} gereksiz/dolgu kesiti atildi, {len(temiz)} kesit kaldi.")
    else:
        temiz, atilan = kesitler, []
    adim("🧠 Konu bloklari cikariliyor (hangi saniyede ne konusuluyor)...")
    konular = konu_cikar(temiz)
    if konular:
        en_iyi = max(konular, key=lambda c: c["skor"])
        adim(f"✅ {len(konular)} konu blogu bulundu (en guclu: “{en_iyi['etiket']}”).")
    adim(f"🗣️ Konusmacilar ayriliyor (mod: {hoparlor})...")
    etiketler, k, ayrim, yontem = hoparlor_ayir(temiz, wav, mod=hoparlor)
    adim(f"👥 {k} konusmaci bulundu (ayrim gucu {ayrim}, {yontem}).")
    yuz_bilgi = {"fw": 0, "fh": 0, "izler": [], "hata": ""}
    yuz_esleme, esleme_yontemi = {}, "yok"
    if not yuz_atla:
        adim("🙂 Yuzler taranıyor ve izleniyor (kafa takibi icin)...")
        yuz_bilgi = yuz_izleri(video)
        if yuz_bilgi.get("hata"):
            _yaz(f"⚠️ Yuz takibi yapilamadi: {yuz_bilgi['hata']} — merkez kadraj kullanilacak.")
        else:
            adim(f"✅ {len(yuz_bilgi['izler'])} yuz izi bulundu.")
        yuz_esleme, esleme_yontemi = konusmaci_yuz_esle(temiz, etiketler, yuz_bilgi["izler"])
        # KRITIK DOGRULAMA: ayni yuz izine dusen konusmaci etiketleri ASLINDA ayni
        # kisidir; birlestirilmezse tek kisi iki panele bolunuyordu.
        yeni_etiketler, k2, yuz_esleme, ayrim, dogrulama = konusmaci_dogrula(
            etiketler, yuz_esleme, k, ayrim, yuz_bilgi)
        if k2 != k:
            adim(f"🔧 Ayni yuz birden fazla konusmaciya dustu — {k} konusmaci {k2} kisiye indirildi.")
        etiketler, k = yeni_etiketler, k2
        esleme_yontemi = f"{esleme_yontemi} + {dogrulama}"
    if not yuz_bilgi.get("fw") or not yuz_bilgi.get("fh"):
        # Kafa takibi atlandi/basarisiz: kadraj icin gercek boyut yine sart.
        yuz_bilgi["fw"], yuz_bilgi["fh"] = video_boyut(video)
    shutil.rmtree(gecici, ignore_errors=True)
    return {
        "mod": "konusma", "video": video, "link": link, "kesitler": temiz,
        "atilan": atilan, "konular": konular,
        "etiketler": {round(kk["start"], 3): e for kk, e in zip(temiz, etiketler)},
        "konusmaci_sayisi": k, "ayrim_gucu": ayrim, "ayrim_yontemi": yontem,
        "yuz": yuz_bilgi, "yuz_esleme": yuz_esleme, "esleme_yontemi": esleme_yontemi,
        "transkript_kaynagi": kaynak,
    }


def klip_uret(link=None, yerel=None, adet=VARSAYILAN_KLIP, sure=HEDEF_SURE,
              hoparlor="auto", cikis_klasoru=None, muzik=None, ducking=False,
              altyazi="srt", whisper_model="small", dil=None, yuz_atla=False,
              plan_sadece=False, indir_klasoru=None, muzik_db=-20.0):
    """Uzun video -> N adet dikey Shorts + rapor. Donus: (basarili, plan).

    adet=0 (OTO_KLIP) -> OTOMATIK: video kac ilginc sahne veriyorsa o kadar klip.
    sure=0 (OTO_SURE) -> OTOMATIK: sureyi icerik belirler, en fazla OTO_MAKS_SURE.
    """
    baslangic = datetime.now()
    oto_adet = int(adet) <= OTO_KLIP
    oto_sure = float(sure) <= OTO_SURE
    adet_etkin = OTO_MAKS_KLIP if oto_adet else max(1, int(adet))
    hedef_sure_etkin = (OTO_MAKS_SURE if oto_sure
                        else max(MIN_SURE, min(MAKS_SURE, float(sure))))
    oto_bilgi = {"klip_sayisi": oto_adet, "sure": oto_sure, "aday": 0,
                 "secilen": 0, "atlanan": 0, "skor_esigi": None,
                 "sure_ust": OTO_MAKS_SURE if oto_sure else hedef_sure_etkin}
    _yaz("=" * 68)
    _yaz("🎬 KLIPCI — uzun video -> Shorts (yerel, ucretsiz)")
    _yaz("=" * 68)
    if oto_adet:
        _yaz(f"🧠 Otomatik klip sayisi: video kac ilginc sahne verirse o kadar "
             f"(en fazla {OTO_MAKS_KLIP}).")
    if oto_sure:
        _yaz(f"⏱️ Otomatik sure: icerige gore, en fazla {OTO_MAKS_SURE:.0f} sn.")
    gecici_indirme = None
    try:
        if not yerel:
            if not link:
                _yaz("❌ Kaynak gerekli: --link ya da --yerel")
                return False, {}
            hedef = indir_klasoru or tempfile.mkdtemp(prefix="vf_klip_indir_")
            if not indir_klasoru:
                gecici_indirme = hedef
            _yaz("⬇️ Video indiriliyor (yt-dlp)...")
            video, baslik = yt_dlp_indir(link, hedef)
            if not video:
                return False, {}
            _yaz(f"✅ Indirildi: {os.path.basename(video)}")
        else:
            video = os.path.abspath(yerel)
            if not os.path.exists(video):
                _yaz(f"❌ Yerel video bulunamadi: {video}")
                return False, {}
            baslik = os.path.splitext(os.path.basename(video))[0]
        analiz = videoyu_analiz_et(video, link=link, dil=dil, whisper_model=whisper_model,
                                   hoparlor=hoparlor, yuz_atla=yuz_atla)
        if not analiz:
            return False, {}

        gorsel_mod = analiz.get("mod") == "gorsel"
        if gorsel_mod:
            _yaz("🧩 Konusma yok — gorsel hook pencereleri seciliyor (sahne kesmesi + hareket + ses)...")
            pencereler = gorsel_pencereleri(analiz["gorsel"]["hucreler"], adet=adet_etkin,
                                            sure=hedef_sure_etkin, maks_sure=hedef_sure_etkin,
                                            video_sure=analiz["gorsel"].get("sure"),
                                            oto=oto_adet, oto_sure=oto_sure)
        else:
            _yaz("🧩 Klip pencereleri seciliyor (hook-first + konu butunlugu)...")
            pencereler = klip_pencereleri(analiz["kesitler"], adet=adet_etkin,
                                          hedef_sure=hedef_sure_etkin, maks_sure=hedef_sure_etkin,
                                          oto=oto_adet, oto_sure=oto_sure)
        if oto_adet and pencereler:
            _aday = len(pencereler)
            _secilen, _esik = oto_pencereleri_sec(pencereler)
            oto_bilgi.update({"aday": _aday, "secilen": len(_secilen), "skor_esigi": _esik,
                              "atlanan": max(0, _aday - len(_secilen))})
            _yaz(f"🎯 Otomatik secim: {_aday} uygun sahne bulundu, {len(_secilen)} tanesi secildi "
                 f"(skor esigi {_esik}, {oto_bilgi['atlanan']} zayif sahne atlandi).")
            pencereler = _secilen
        if not pencereler:
            _yaz("❌ Uygun klip penceresi bulunamadi.")
            return False, {}
        kok = cikis_klasoru or os.path.join(masaustu(), "Klipler", _slug(baslik))
        os.makedirs(kok, exist_ok=True)
        plan = {
            "olusturma": baslangic.strftime("%Y-%m-%d %H:%M:%S"),
            "baslik": baslik, "link": link or "", "video": video,
            "mod": "gorsel" if gorsel_mod else "konusma",
            "sure": round(analiz["yuz"].get("sure") or 0, 2),
            "transkript_kaynagi": analiz["transkript_kaynagi"],
            "konusmaci_sayisi": analiz["konusmaci_sayisi"],
            "ayrim_gucu": analiz["ayrim_gucu"], "ayrim_yontemi": analiz["ayrim_yontemi"],
            "yuz_izi_sayisi": len(analiz["yuz"].get("izler") or []),
            "yuz_esleme": {str(a): b for a, b in analiz["yuz_esleme"].items()},
            "esleme_yontemi": analiz["esleme_yontemi"],
            "oto": oto_bilgi,
            "atilan_kesit": len(analiz["atilan"]),
            "atilan_ornek": [{"metin": a["text"][:90], "sebep": a.get("sebep")}
                             for a in analiz["atilan"][:12]],
            "konular": [{"no": c.get("no"), "etiket": c.get("etiket"),
                          "baslangic": c.get("baslangic"), "bitis": c.get("bitis"),
                          "kesit_sayisi": c.get("kesit_sayisi"), "skor": c.get("skor"),
                          "baslik": c.get("baslik")} for c in (analiz.get("konular") or [])],
            "cikis_klasoru": kok, "klipler": [],
        }
        if analiz.get("konular"):
            _yaz("📚 Konu haritasi: " + " | ".join(
                f"{c['etiket']} ({_sure_metni(c['baslangic'])}-{_sure_metni(c['bitis'])}, skor {c['skor']})"
                for c in analiz["konular"][:6]))
        if not gorsel_mod:
            # Transkript haritasi (hangi saniyede ne konusuldu) diske yazilir;
            # masaustu arayuzu bunu okuyup gosterebilsin.
            try:
                with open(os.path.join(kok, "transkript.json"), "w", encoding="utf-8") as f:
                    json.dump({
                        "kaynak": analiz["transkript_kaynagi"],
                        "kesitler": [{"bas": k["start"], "son": k["end"], "metin": k["text"],
                                      "skor": k.get("skor"), "konu": k.get("konu"),
                                      "konu_etiket": k.get("konu_etiket"),
                                      "konu_basi": bool(k.get("konu_basi")),
                                      "kirilim": k.get("kirilim")} for k in analiz["kesitler"]],
                    }, f, ensure_ascii=False, indent=2)
            except Exception as e:
                _yaz(f"⚠️ transkript.json yazilamadi: {str(e)[:100]}")
        for idx, pencere in enumerate(pencereler, start=1):
            if gorsel_mod:
                parcalar = gorsel_kadraj_plani(pencere, analiz["yuz"].get("fw") or 1920,
                                               analiz["yuz"].get("fh") or 1080)
            else:
                parcalar = kadraj_plani(pencere, analiz["etiketler"], analiz["yuz_esleme"],
                                        analiz["yuz"].get("izler") or [], analiz["yuz"],
                                        mod=hoparlor)
            if not parcalar:
                continue
            if gorsel_mod:
                baslik_metni = (f"Görsel hook · {_sure_metni(pencere['start'])} "
                                f"(hareket {pencere['kirilim'].get('hareket')}, "
                                f"kesme {pencere['kirilim'].get('kesme')})")
                dosya_slug = f"sahne_{_sure_metni(pencere['start']).replace(':', 'm')}s"
            else:
                baslik_metni = pencere["kesitler"][0]["text"][:110]
                dosya_slug = _slug(pencere["kesitler"][0]["text"], 32)
            dosya = os.path.join(kok, f"klip_{idx:02d}_{dosya_slug}.mp4")
            sinirlar = _kesit_sinirlari(parcalar)
            srt_yolu = os.path.splitext(dosya)[0] + ".srt"
            if not gorsel_mod:
                srt_yaz(parcalar, srt_yolu, sinirlar)
            panel_ozet = {p["panel_sayisi"]: 0 for p in parcalar}
            for p in parcalar:
                panel_ozet[p["panel_sayisi"]] = panel_ozet.get(p["panel_sayisi"], 0) + 1
            kayit = {
                "no": idx, "mod": "gorsel" if gorsel_mod else "konusma",
                "baslik": baslik_metni,
                "konu": pencere.get("konu") or "",
                "kirilim": pencere.get("kirilim") or {},
                "skor": pencere["skor"], "en_yuksek": round(pencere["en_yuksek"], 1),
                "baslangic": round(pencere["start"], 2), "bitis": round(pencere["end"], 2),
                "sure": pencere["sure"], "kesit_sayisi": len(parcalar),
                "panel_dagilimi": {str(a): b for a, b in panel_ozet.items()},
                "dosya": dosya, "srt": srt_yolu if os.path.exists(srt_yolu) else None,
                "kesitler": [{"bas": round(p["start"], 2), "son": round(p["end"], 2),
                              "panel": p["panel_sayisi"], "metin": p["metin"][:140],
                              "skor": p.get("skor")} for p in parcalar],
            }
            if plan_sadece:
                kayit["dosya"] = None
                _yaz(f"   • Klip {idx}: {pencere['sure']} sn, skor {pencere['skor']}, "
                     f"konu '{kayit['konu']}', panel dagilimi {panel_ozet} (plan modu: render yok)")
                plan["klipler"].append(kayit)
                continue
            _yaz(f"🎞️ Klip {idx}/{len(pencereler)} render ediliyor "
                 f"({pencere['sure']} sn, {len(parcalar)} kesit, panel {panel_ozet})...")
            tamam, hata = klip_render(
                video, parcalar, dosya, muzik=muzik if ducking else None,
                altyazi_srt=srt_yolu, altyazi_yak=(altyazi == "yak" and not gorsel_mod),
                sinirlar=sinirlar)
            if not tamam:
                kayit["hata"] = hata
                _yaz(f"   ❌ Render hatasi: {hata}")
            else:
                rapor = video_denetle(dosya)
                qa_yolu = rapor_yaz(rapor)
                kayit["qa"] = {"puan": rapor.get("skor"), "derece": rapor.get("derece"),
                               "sorunlar": rapor.get("sorunlar"), "dosya": qa_yolu}
                _yaz(f"   ✅ {os.path.basename(dosya)} — QA {rapor.get('skor')}/100 "
                     f"({rapor.get('derece')})")
                for sorun in (rapor.get("sorunlar") or [])[:3]:
                    _yaz(f"      ⚠️ {sorun}")
            plan["klipler"].append(kayit)

        plan_yolu = os.path.join(kok, "klip_plani.json")
        with open(plan_yolu, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        plan["plan_dosyasi"] = plan_yolu
        _yaz("-" * 68)
        _yaz(f"📁 Cikti klasoru: {kok}")
        _yaz(f"📄 Plan: {plan_yolu}")
        gecen = [k for k in plan["klipler"] if (k.get("qa") or {}).get("puan", 0) >= 70]
        _yaz(f"✅ {len(plan['klipler'])} klip hazir — {len(gecen)} tanesi QA esigini gecti.")
        return True, plan
    finally:
        if gecici_indirme:
            shutil.rmtree(gecici_indirme, ignore_errors=True)


def _cli(argv=None):
    if ISLETIM == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    p = argparse.ArgumentParser(description="VideoForge KLIPCI — uzun video -> Shorts (yerel)")
    p.add_argument("--link", help="Uzun video linki (YouTube/TikTok/Instagram)")
    p.add_argument("--yerel", help="Yerel video dosyasi (indirme yok)")
    p.add_argument("--klip", type=lambda d: _oto_deger(d, int), default=VARSAYILAN_KLIP,
                   help="Kac klip uretilsin (0 ya da 'oto' = OTOMATIK: video kac ilginc "
                        f"sahne verirse o kadar, en fazla {OTO_MAKS_KLIP})")
    p.add_argument("--sure", type=lambda d: _oto_deger(d, float), default=HEDEF_SURE,
                   help="Hedef klip suresi sn (0 ya da 'oto' = OTOMATIK: sureyi icerik "
                        f"belirler, en fazla {OTO_MAKS_SURE:.0f} sn)")
    p.add_argument("--hoparlor", default="auto", help="auto | 1 | 2 | 3 | 4 (panel sayisi)")
    p.add_argument("--cikis", help="Cikis klasoru (varsayilan: Masaustu/Klipler/<video>)")
    p.add_argument("--muzik", help="Fon muzigi dosyasi")
    p.add_argument("--ducking", action="store_true", help="Muzigi konusma varken kis")
    p.add_argument("--muzik-db", type=float, default=-20.0, help="Muzik seviyesi (dB)")
    p.add_argument("--altyazi", choices=["yok", "srt", "yak"], default="srt")
    p.add_argument("--whisper-model", default="small", help="Altyazi yoksa Whisper modeli")
    p.add_argument("--dil", help="Dil ipucu (tr/en/ru) — Whisper icin")
    p.add_argument("--yuz-atla", action="store_true", help="Yuz taramasini atla (hizli)")
    p.add_argument("--plan-sadece", action="store_true", help="Sadece analiz/plan (render yok)")
    a = p.parse_args(argv)
    tamam, plan = klip_uret(
        link=a.link, yerel=a.yerel,
        adet=a.klip if a.klip <= 0 else max(1, a.klip),
        sure=a.sure if a.sure <= 0 else max(MIN_SURE, a.sure),
        hoparlor=a.hoparlor, cikis_klasoru=a.cikis, muzik=a.muzik, ducking=a.ducking,
        muzik_db=a.muzik_db, altyazi=a.altyazi, whisper_model=a.whisper_model, dil=a.dil,
        yuz_atla=a.yuz_atla, plan_sadece=a.plan_sadece)
    return 0 if tamam else 1


if __name__ == "__main__":
    sys.exit(_cli())
