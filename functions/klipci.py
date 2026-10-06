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
MAKS_SURE = 60.0                   # Shorts ust siniri
MIN_KESIT = 0.6                    # bundan kisa transkript parcalari atilir
MAKS_PARCA = 42                    # klip basina en fazla kac kesit (filtergraph siniri)
YSA_ADIM = 0.5                     # yuz tarama adimi (sn)
YSA_KUCUK_W = 128                  # hareket enerjisi icin kucuk kare genisligi
ES_ZAMAN_PENCERE = 1.4             # "ayni anda konusuyor" kabul penceresi (sn)
SILHOUETTE_ESIK = 0.12             # konusmaci ayrimi icin minimum ayrim gucu
FILTRE_UZUN = 0.15                 # iki kesit arasi: bu kadar on/arka pay birakilir

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
    """Videonun sesini 16 kHz mono wav olarak cikarir."""
    komut = [FFMPEG, "-y", "-hide_banner", "-nostats", "-i", video,
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav]
    tamam, _, hata = _calistir(komut, timeout=timeout)
    if not tamam:
        _yaz(f"❌ Ses cikarilamadi: {_hata_son(hata)}")
        return None
    return wav


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

    zorlanan = None
    if str(mod).isdigit():
        zorlanan = max(1, int(mod))
    en_iyi_k, en_iyi_puan, en_iyi_model = 1, -1.0, None
    adaylar = [zorlanan] if zorlanan else range(1, min(4, max(2, len(ozellikler) // 3)) + 1)
    for k in adaylar:
        if k < 2:
            if zorlanan == 1:
                en_iyi_k, en_iyi_puan, en_iyi_model = 1, 0.0, None
                break
            continue
        try:
            model = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
        except Exception:
            continue
        try:
            puan = float(silhouette_score(X, model.labels_))
        except Exception:
            continue
        if puan > en_iyi_puan:
            en_iyi_k, en_iyi_puan, en_iyi_model = k, puan, model
    if en_iyi_model is None or (zorlanan is None and en_iyi_puan < SILHOUETTE_ESIK):
        return [0] * len(kesitler), 1, max(0.0, en_iyi_puan), "tek konusmaci"
    etiketler = [0] * len(kesitler)
    for j, i in enumerate(indeks):
        etiketler[i] = int(en_iyi_model.labels_[j])
    # Eksik kalan kesitler (cok kisa) en yakin komsusundan etiket alir.
    son = 0
    for i in range(len(etiketler)):
        if i in indeks:
            son = etiketler[i]
        else:
            etiketler[i] = son
    return etiketler, en_iyi_k, round(max(0.0, en_iyi_puan), 3), "kmeans"


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


# ---------------------------------------------------------------- 6. skorlama
def _kelimeler(metin):
    return [w for w in re.findall(r"[\w'’]+", (metin or "").lower()) if len(w) > 1]


def _icerik_kelimeleri(metin):
    return [w for w in _kelimeler(metin) if w not in STOP and len(w) >= 3]


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
        # b) hook/merak
        hook = len([w for w in kelimeler if w in HOOK])
        soru = 1 if "?" in metin else 0
        hook_puan = min(1.0, (hook * 0.9 + soru * 1.3) / 2.6)
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
        ham = (0.30 * yogunluk + 0.30 * hook_puan + 0.22 * nadir_puan + 0.18 * vurgu)
        skor = max(0.0, min(1.0, ham - ceza))
        k["skor"] = round(skor * 100, 1)
        k["kirilim"] = {
            "bilgi": round(yogunluk, 2), "hook": round(hook_puan, 2),
            "nadirlik": round(nadir_puan, 2), "vurgu": round(vurgu, 2),
            "dolgu_cezasi": round(ceza, 2),
        }
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


def klip_pencereleri(kesitler, adet=VARSAYILAN_KLIP, hedef_sure=HEDEF_SURE,
                     min_sure=MIN_SURE, maks_sure=MAKS_SURE):
    """Skorlu anlardan konu butunlugu yuksek pencereler uretir.

    Tohum = en yuksek skorlu kesit. Pencere, komsu kesitlerin anahtar kelime
    ortusmesi esik ustunde kaldigi surece ILERI ve GERI genisletilir; boylece
    konu basindan sonuna kadar anlasilir olur (ortadan baslamaz).
    """
    if not kesitler:
        return []
    sirali = sorted(kesitler, key=lambda k: -(k.get("skor") or 0))
    pencereler = []
    for tohum in sirali:
        if len(pencereler) >= adet:
            break
        if any(k["start"] <= tohum["start"] < k["end"] for k in pencereler):
            continue
        # Tohum penceresi zaten secilmis bir klibin icindeyse atla; ama pencere
        # genisledikten sonra ortusme kontrolu tekrar yapilir (asagida).
        bas = kesitler.index(tohum)
        kume = _kume(tohum["text"])
        sure = tohum["end"] - tohum["start"]
        i, j = bas, bas
        while sure < maks_sure:
            genisledi = False
            adaylar = []
            if i > 0:
                adaylar.append((i - 1, "geri"))
            if j < len(kesitler) - 1:
                adaylar.append((j + 1, "ileri"))
            adaylar.sort(key=lambda a: -_ortusme(_kume(kesitler[a[0]]["text"]), kume))
            for idx, yon in adaylar:
                yeni_kume = _kume(kesitler[idx]["text"])
                sure_k = kesitler[idx]["end"] - kesitler[idx]["start"]
                if _ortusme(yeni_kume, kume) < 0.12 and sure >= hedef_sure:
                    continue
                if sure + sure_k > maks_sure:
                    continue
                if yon == "geri":
                    i = idx
                else:
                    j = idx
                kume |= yeni_kume
                sure += sure_k
                genisledi = True
                break
            if not genisledi:
                break
        while sure < min_sure and (i > 0 or j < len(kesitler) - 1):
            if i > 0:
                i -= 1
                sure += kesitler[i]["end"] - kesitler[i]["start"]
            elif j < len(kesitler) - 1:
                j += 1
                sure += kesitler[j]["end"] - kesitler[j]["start"]
            if sure >= min_sure:
                break
        parcalar = kesitler[i:j + 1]
        if not parcalar:
            continue
        # Baslangic kancasi: ilk 3 kesit icinde hook varsa ve sure yetiyorsa basta kullan.
        en_iyi_bas = 0
        for p in range(0, min(3, len(parcalar))):
            if (parcalar[p]["kirilim"]["hook"] if parcalar[p].get("kirilim") else 0) >= 0.35:
                kalan_sure = sum(x["end"] - x["start"] for x in parcalar[p:])
                if kalan_sure >= min_sure:
                    en_iyi_bas = p
                    break
        parcalar = parcalar[en_iyi_bas:]
        bas_yeni = parcalar[0]["start"]
        son_yeni = parcalar[-1]["end"]
        # Secilen pencereler ASLA ortusmez (ayni sahneyi iki kez klip yapmayalim).
        if any(bas_yeni < p["end"] - 0.05 and p["start"] < son_yeni - 0.05 for p in pencereler):
            continue
        pencereler.append({
            "start": bas_yeni,
            "end": son_yeni,
            "sure": round(son_yeni - bas_yeni, 2),
            "kesitler": parcalar,
            "skor": round(float(np.mean([p.get("skor") or 0 for p in parcalar])), 1),
            "en_yuksek": max((p.get("skor") or 0) for p in parcalar),
        })
    pencereler.sort(key=lambda p: -(p["en_yuksek"] * 0.6 + p["skor"] * 0.4))
    return pencereler[:adet]


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
    """Pencereyi panel parcalarina boler: kim konusuyor -> hangi panel.

    Ayni anda (yakin aralikta) kac kisi konusuyorsa o kadar panel acilir:
      1 kisi -> tek panel (tam ekran, kafa takipli)
      2 kisi -> ALT/UST iki panel
      3 kisi -> ust tam + alt ikiye bolunmus
      4 kisi -> 2x2 dort panel
    """
    iz_map = {iz["id"]: iz for iz in izler}
    fw = yuz_bilgi.get("fw") or 1920
    fh = yuz_bilgi.get("fh") or 1080
    kesitler = pencere["kesitler"]
    ust_sinir = int(mod) if (mod and str(mod).isdigit() and int(mod) > 1) else 0
    parcalar = []
    for sira, k in enumerate(kesitler):
        es = _etiket_al(etiketler, k, sira)
        yakin = {es}
        for j, diger in enumerate(kesitler):
            if j == sira:
                continue
            if diger["start"] <= k["end"] + pencere_sn and diger["end"] >= k["start"] - pencere_sn:
                yakin.add(_etiket_al(etiketler, diger, j))
        if ust_sinir:
            yakin = set(sorted(yakin)[:ust_sinir])
        konusmacilar = sorted(yakin)
        duzen = 1 if len(konusmacilar) <= 1 else (2 if len(konusmacilar) == 2 else (3 if len(konusmacilar) == 3 else 4))
        panel_listesi = PANEL[duzen]
        # Kim hangi panele: konusan ilk panele, digerleri sirayla.
        sirali = [es] + [e for e in konusmacilar if e != es]
        paneller = []
        for idx, (ad, pw, ph) in enumerate(panel_listesi):
            sahip = sirali[idx] if idx < len(sirali) else None
            iz_id = yuz_esleme.get(sahip)
            iz = iz_map.get(iz_id) if iz_id is not None else None
            kutu = yuz_kutusu(iz, k["start"], fw, fh) if iz else None
            if kutu is None and len(paneller) == 0:
                kutu = None  # yuz yok -> merkez kadraj
            oran = pw / max(1, ph)
            cw, ch, cx, cy = _pencere_kutusu(kutu, fw, fh, oran)
            paneller.append({"ad": ad, "sahip": sahip, "yuz_izi": iz_id,
                             "kutu": [cw, ch, cx, cy], "hedef": [pw, ph]})
        parca = {"start": k["start"], "end": k["end"], "panel_sayisi": duzen,
                 "konusmacilar": konusmacilar, "paneller": paneller,
                 "metin": k["text"], "skor": k.get("skor")}
        if parcalar and parcalar[-1]["panel_sayisi"] == duzen and \
                parcalar[-1]["konusmacilar"] == konusmacilar and \
                abs(parcalar[-1]["end"] - k["start"]) < 0.4:
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
def _kesit_video_zinciri(kaynak, kesit, paneller, cikis_etiket, onek=""):
    """Bir kesitin video zincirini uretir: trim + (panel birlestirme) + dikey olcek.

    `onek`: ffmpeg etiketleri graf genelinde TEK olmak zorunda oldugu icin her
    kesit icin benzersiz bir on ek (orn. "3_") verilir.
    """
    oncu = f"{kaynak}trim=start={kesit['start']:.3f}:end={kesit['end']:.3f},setpts=PTS-STARTPTS"
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


def _ses_zinciri(parcalar, siddet="orta", etiket="[aout]"):
    """Kesitleri tek ses akisina cevirir + temizlik/loudnorm uygular."""
    n = len(parcalar)
    zincir = []
    if n == 1:
        zincir.append("[0:a]anull[a0]")
    else:
        zincir.append(f"[0:a]asplit={n}" + "".join(f"[a{i}]" for i in range(n)))
    cikislar = []
    for i, p in enumerate(parcalar):
        # Kesitler arasi kisa pay: cumle kirpilirken hece kaybini onler.
        bas = max(0.0, p["start"] - FILTRE_UZUN)
        son = p["end"] + FILTRE_UZUN
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
                altyazi_srt=None, altyazi_yak=False, timeout=7200):
    """Klip parcalarini tek gecisde keser/birlestirir, sesi isler ve yazar."""
    if not parcalar:
        return False, "parca yok"
    if len(parcalar) > MAKS_PARCA:
        parcalar = parcalar[:MAKS_PARCA]
    n = len(parcalar)
    _kadrajlari_sinirla(parcalar, video)
    video_zincir = []
    if n == 1:
        zincir = _kesit_video_zinciri("[0:v]", parcalar[0], parcalar[0]["paneller"], "[v0]")
        video_zincir.append(zincir)
    else:
        video_zincir.append(f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n)))
        for i, p in enumerate(parcalar):
            video_zincir.append(_kesit_video_zinciri(f"[s{i}]", p, p["paneller"], f"[v{i}]",
                                                    onek=f"{i}_"))
    video_zincir.append("".join(f"[v{i}]" for i in range(n)) +
                        ("null[vout]" if n == 1 else f"concat=n={n}:v=1:a=0[vout]"))
    filtre = ";".join(video_zincir + [_ses_zinciri(parcalar, siddet=siddet)])
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


def srt_yaz(parcalar, yol):
    """Klibin kesilmis zaman cizgisine gore SRT altyazi uretir (ucretsiz)."""
    def _ts(sn):
        ms = int(round(sn * 1000))
        s, ms = divmod(ms, 1000)
        d, s = divmod(s, 60)
        sa, d = divmod(d, 60)
        return f"{sa:02d}:{d:02d}:{s:02d},{ms:03d}"

    satirlar = []
    imlec = 0.0
    for i, p in enumerate(parcalar, start=1):
        sure = max(0.2, p["end"] - p["start"])
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


# ---------------------------------------------------------------- 10. ana akis
def videoyu_analiz_et(video, link=None, dil=None, whisper_model="small", hoparlor="auto",
                      yuz_atla=False, ilerleme=None):
    """Indirilmis videodan: transkript + konusmaci + yuz izleri (analiz katmani)."""
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
    if not kesitler:
        _yaz("❌ Transkript uretilemedi — klip cikarilamaz.")
        shutil.rmtree(gecici, ignore_errors=True)
        return None
    adim(f"✅ {len(kesitler)} konusma kesiti bulundu (kaynak: {kaynak}).")
    adim("🎯 Onemli anlar skorlaniyor...")
    kesitler = an_skorlari(kesitler, wav)
    temiz, atilan = filler_temizle(kesitler)
    if temiz:
        adim(f"🧹 {len(atilan)} gereksiz/dolgu kesiti atildi, {len(temiz)} kesit kaldi.")
    else:
        temiz, atilan = kesitler, []
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
    if not yuz_bilgi.get("fw") or not yuz_bilgi.get("fh"):
        # Kafa takibi atlandi/basarisiz: kadraj icin gercek boyut yine sart.
        yuz_bilgi["fw"], yuz_bilgi["fh"] = video_boyut(video)
    shutil.rmtree(gecici, ignore_errors=True)
    return {
        "video": video, "link": link, "kesitler": temiz, "atilan": atilan,
        "etiketler": {round(kk["start"], 3): e for kk, e in zip(temiz, etiketler)},
        "konusmaci_sayisi": k, "ayrim_gucu": ayrim, "ayrim_yontemi": yontem,
        "yuz": yuz_bilgi, "yuz_esleme": yuz_esleme, "esleme_yontemi": esleme_yontemi,
        "transkript_kaynagi": kaynak,
    }


def klip_uret(link=None, yerel=None, adet=VARSAYILAN_KLIP, sure=HEDEF_SURE,
              hoparlor="auto", cikis_klasoru=None, muzik=None, ducking=False,
              altyazi="srt", whisper_model="small", dil=None, yuz_atla=False,
              plan_sadece=False, indir_klasoru=None, muzik_db=-20.0):
    """Uzun video -> N adet dikey Shorts + rapor. Donus: (basarili, plan)."""
    baslangic = datetime.now()
    _yaz("=" * 68)
    _yaz("🎬 KLIPCI — uzun video -> Shorts (yerel, ucretsiz)")
    _yaz("=" * 68)
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

        _yaz("🧩 Klip pencereleri seciliyor (konu butunlugu + skor)...")
        pencereler = klip_pencereleri(analiz["kesitler"], adet=adet, hedef_sure=sure)
        if not pencereler:
            _yaz("❌ Uygun klip penceresi bulunamadi.")
            return False, {}
        kok = cikis_klasoru or os.path.join(masaustu(), "Klipler", _slug(baslik))
        os.makedirs(kok, exist_ok=True)
        plan = {
            "olusturma": baslangic.strftime("%Y-%m-%d %H:%M:%S"),
            "baslik": baslik, "link": link or "", "video": video,
            "sure": round(analiz["yuz"].get("sure") or 0, 2),
            "transkript_kaynagi": analiz["transkript_kaynagi"],
            "konusmaci_sayisi": analiz["konusmaci_sayisi"],
            "ayrim_gucu": analiz["ayrim_gucu"], "ayrim_yontemi": analiz["ayrim_yontemi"],
            "yuz_izi_sayisi": len(analiz["yuz"].get("izler") or []),
            "yuz_esleme": {str(a): b for a, b in analiz["yuz_esleme"].items()},
            "esleme_yontemi": analiz["esleme_yontemi"],
            "atilan_kesit": len(analiz["atilan"]),
            "atilan_ornek": [{"metin": a["text"][:90], "sebep": a.get("sebep")}
                             for a in analiz["atilan"][:12]],
            "cikis_klasoru": kok, "klipler": [],
        }
        for idx, pencere in enumerate(pencereler, start=1):
            parcalar = kadraj_plani(pencere, analiz["etiketler"], analiz["yuz_esleme"],
                                    analiz["yuz"].get("izler") or [], analiz["yuz"],
                                    mod=hoparlor)
            if not parcalar:
                continue
            dosya = os.path.join(kok, f"klip_{idx:02d}_{_slug(pencere['kesitler'][0]['text'], 32)}.mp4")
            srt_yolu = os.path.splitext(dosya)[0] + ".srt"
            srt_yaz(parcalar, srt_yolu)
            panel_ozet = {p["panel_sayisi"]: 0 for p in parcalar}
            for p in parcalar:
                panel_ozet[p["panel_sayisi"]] = panel_ozet.get(p["panel_sayisi"], 0) + 1
            kayit = {
                "no": idx,
                "baslik": pencere["kesitler"][0]["text"][:110],
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
                     f"panel dagilimi {panel_ozet} (plan modu: render yok)")
                plan["klipler"].append(kayit)
                continue
            _yaz(f"🎞️ Klip {idx}/{len(pencereler)} render ediliyor "
                 f"({pencere['sure']} sn, {len(parcalar)} kesit, panel {panel_ozet})...")
            tamam, hata = klip_render(
                video, parcalar, dosya, muzik=muzik if ducking else None,
                altyazi_srt=srt_yolu, altyazi_yak=(altyazi == "yak"))
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
    p.add_argument("--klip", type=int, default=VARSAYILAN_KLIP, help="Kac klip uretilsin")
    p.add_argument("--sure", type=float, default=HEDEF_SURE, help="Hedef klip suresi (sn)")
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
        link=a.link, yerel=a.yerel, adet=max(1, a.klip), sure=max(MIN_SURE, a.sure),
        hoparlor=a.hoparlor, cikis_klasoru=a.cikis, muzik=a.muzik, ducking=a.ducking,
        muzik_db=a.muzik_db, altyazi=a.altyazi, whisper_model=a.whisper_model, dil=a.dil,
        yuz_atla=a.yuz_atla, plan_sadece=a.plan_sadece)
    return 0 if tamam else 1


if __name__ == "__main__":
    sys.exit(_cli())
