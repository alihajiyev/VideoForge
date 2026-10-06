# -*- coding: utf-8 -*-
"""Performans geri bildirim dongusu — YouTube Studio CSV'sinden (salt-okuma).

NEDEN: Bot su ana kadar kor uretiyordu; algoritmaya "neyin tuttugunu" hic
sormuyordu. Bu modul kendi kanalinin GERCEK olcum verisiyle (izlenme, CTR,
ortalama izlenme yuzdesi) kanitlanmis kalıplari cikarir ve iki yere enjekte eder:
  1) kesif.py  -> aday videolarin siralamasi (deterministik skor bonusu + prompt)
  2) baslik promptu (gemini_func.generate_title)

NASIL VERI GELIR (anahtar/OAuth/upload YOK -> shadowban riski YOK):
  YouTube Studio > Icerik sayfasi > "Disa aktar" (CSV) ile indirdigin dosyalari
  VideoForge klasorundeki  performans_csv/  klasorune birak:
      performans_csv/*.csv            -> tum kanallar icin ortak veri ("genel")
      performans_csv/kanal1/*.csv     -> sadece 1. kanal (varsa "genel"i ezer)
  Sonra bir kez:  py -3 functions/performans.py
  (kesif.py her calistiginda zaten dosyayi okuyup kullanir.)

Cikti: performans.json
    {"guncelleme": ..., "kanallar": {"genel": {..., "videolar": [...], "kaliplar": [...]}}}
"""
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(BASE_DIR, "performans_csv")
PERF_FILE = os.path.join(BASE_DIR, "performans.json")

# Hiç veri yokken kalip uretilmesin: en az bu kadar video gerekir.
MIN_VIDEO_KALIP = 5
# Kalıp madenciliğinde tutulacak en fazla kalıp sayısı.
VARSAYILAN_KALIP_SAYISI = 8
# Baslik promptuna giren kalıp sayısı (prompt şişmesin).
PROMPT_KALIP_SAYISI = 6

# ---------------------------------------------------------------------------
# 1) CSV OKUMA — YouTube Studio'nun EN ve TR basliklarini birlikte destekler.
# ---------------------------------------------------------------------------
# Sira ONEMLI: "ortalama izlenme suresi (%)" satiri hem 'ort_yuzde' hem 'izlenme'
# anahtarina uyar; ozel olan once bakilmali.
_ALAN_SIRASI = (
    ("baslik", ("video title", "video başlığı", "video basligi", "başlık", "baslik")),
    ("ctr", ("click-through rate", "click through rate", "tıklama oranı", "tiklama orani", "ctr")),
    ("ort_yuzde", ("average percentage viewed", "average view duration (%)",
                   "ortalama izlenme süresi (%)", "izlenme yüzdesi")),
    ("ort_sn", ("average view duration", "ortalama izlenme süresi", "ortalama izlenme")),
    ("izlenme_saati", ("watch time", "izlenme süresi (saat)", "izlenme süresi")),
    ("gosterim", ("impressions", "gösterim", "gosterim")),
    ("izlenme", ("views", "görüntülenme", "izlenme")),
    ("begeni", ("likes", "beğeni", "begeni")),
    ("yorum", ("comments", "yorum")),
    ("abone", ("subscribers", "abone")),
    ("tarih", ("publish time", "yayın tarihi", "yayin tarihi", "tarih")),
    ("sure", ("duration", "süre", "sure")),
)

_SAYI_ALANLARI = ("ctr", "ort_yuzde", "ort_sn", "izlenme_saati", "gosterim",
                  "izlenme", "begeni", "yorum", "abone", "sure")


def _sure_sn(metin):
    """'0:45' / '1:02:33' -> saniye."""
    parca = metin.split(":")
    try:
        parca = [float(x) for x in parca]
    except Exception:
        return None
    if len(parca) == 3:
        return parca[0] * 3600 + parca[1] * 60 + parca[2]
    if len(parca) == 2:
        return parca[0] * 60 + parca[1]
    return parca[0] if parca else None


def _binlik_mi(parca):
    """Ayiriciyla bolunmus parcalar BINLIK grubu mu?

    '1,234' ve '2.100.000' -> binlik (izlenme).
    '4,5' / '6.3' / '0,123' -> ondalik (CTR, yuzde).
    """
    if len(parca) < 2 or not parca[0].isdigit() or parca[0] == "0":
        return False
    return all(p.isdigit() and len(p) == 3 for p in parca[1:])


def sayi_cek(deger):
    """'1,234' / '1.234' / '4,5%' / '0:45' gibi Studio degerlerini float yapar.

    NOT: Tek ayirici + 3 haneli grup binlik sayilir ('1.234' -> 1234,
    '1,234' -> 1234). Studio izlenmeleri tam sayi, CTR/yuzde 1-2 ondaliktir;
    bu yuzden kural pratikte cakismaz.
    """
    if deger is None:
        return None
    s = str(deger).strip().replace("\u00a0", " ")
    if not s or s in {"-", "--", "—", "–", "n/a", "N/A"}:
        return None
    s = s.replace("%", "").replace(" ", "")
    if ":" in s:
        return _sure_sn(s)
    nokta, virgul = s.rfind("."), s.rfind(",")
    if nokta >= 0 and virgul >= 0:
        if nokta > virgul:          # 1,234.5 -> nokta ondalik
            s = s.replace(",", "")
        else:                       # 1.234,5 -> virgul ondalik
            s = s.replace(".", "").replace(",", ".")
    elif virgul >= 0:
        parca = s.split(",")
        if _binlik_mi(parca):
            s = s.replace(",", "")          # 1,234 -> binlik
        else:
            s = s.replace(",", ".")         # 4,5 -> ondalik
    elif nokta >= 0:
        parca = s.split(".")
        if _binlik_mi(parca):
            s = s.replace(".", "")          # 1.234 -> binlik
    try:
        return float(s)
    except Exception:
        m = re.findall(r"-?\d+(?:\.\d+)?", s)
        return float(m[0]) if m else None


def _csv_satirlari(yol):
    """CSV'yi satir listesi olarak oku (BOM, ; ayirici ve bozuk satirlara dayanikli)."""
    for kodlama in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            with open(yol, "r", encoding=kodlama, newline="") as f:
                ornek = f.read(4096)
                f.seek(0)
                try:
                    lehce = csv.Sniffer().sniff(ornek, delimiters=",;\t")
                    ayirici = lehce.delimiter
                except Exception:
                    ayirici = ";" if ornek.count(";") > ornek.count(",") else ","
                return [satir for satir in csv.reader(f, delimiter=ayirici)]
        except Exception:
            continue
    return []


def _alan_esle(hucre):
    """Baslik hucresini alan adina cevirir (yoksa None)."""
    h = (hucre or "").strip().lower().replace("  ", " ")
    if not h:
        return None
    for alan, anahtarlar in _ALAN_SIRASI:
        if any(a in h for a in anahtarlar):
            return alan
    return None


def _baslik_satiri_bul(satirlar):
    """Baslik satirini ve kolon->alan eslesmesini bulur (Total/ustbilgi satirlarini atlar)."""
    for i, satir in enumerate(satirlar):
        if not satir or len(satir) < 2:
            continue
        eslesme = {}
        for j, hucre in enumerate(satir):
            alan = _alan_esle(hucre)
            if alan and alan not in eslesme:
                eslesme[alan] = j
        if "baslik" in eslesme and len(eslesme) >= 2:
            return i, eslesme
    return None, {}


def _bos_mu(baslik):
    b = (baslik or "").strip().lower()
    return (not b) or b in {"total", "totals", "toplam", "sum", "genel toplam"}


def parse_studio_csv(yol):
    """Bir Studio CSV'sini kayit listesine cevirir.

    Donus: [{"baslik": str, "izlenme": float|None, "ctr": ..., ...}, ...]
    Zorunlu tek alan 'baslik'tir; bulunamazsa bos liste doner.
    """
    satirlar = _csv_satirlari(yol)
    if not satirlar:
        return []
    bas_idx, eslesme = _baslik_satiri_bul(satirlar)
    if bas_idx is None:
        return []
    kayitlar = []
    for satir in satirlar[bas_idx + 1:]:
        if not satir or len(satir) <= eslesme["baslik"]:
            continue
        kayit = {}
        for alan, j in eslesme.items():
            kayit[alan] = (satir[j].strip() if j < len(satir) else "")
        if _bos_mu(kayit.get("baslik")):
            continue
        for alan in _SAYI_ALANLARI:
            if alan in kayit:
                kayit[alan] = sayi_cek(kayit[alan])
        # Izlenme yoksa gosterim x CTR ile tahmin et (Studio bazen vermez).
        if not kayit.get("izlenme") and kayit.get("gosterim") and kayit.get("ctr"):
            kayit["izlenme"] = round(kayit["gosterim"] * kayit["ctr"] / 100.0, 1)
            kayit["tahmini_izlenme"] = True
        kayitlar.append(kayit)
    return kayitlar


# ---------------------------------------------------------------------------
# 2) BIRLESTIRME — ayni baslik birden fazla dosyada olabilir (en yuksek deger).
# ---------------------------------------------------------------------------
def _baslik_anahtar(baslik):
    """Basligi karsilastirma anahtarina cevir (emoji/noktalama/buyuk-kucuk farki yok)."""
    t = (baslik or "").lower()
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", " ", t)  # emoji
    t = re.sub(r"[^\w\s]+", " ", t, flags=re.UNICODE)
    return " ".join(t.split())


def _csv_dosyalari(kanal):
    """Verilen kanal icin okunacak CSV yollari (kok + kanal alt klasoru)."""
    yollar = sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
    kanal = str(kanal or "genel")
    if kanal != "genel":
        for ad in (f"kanal{kanal}", f"kanal {kanal}", f"ch{kanal}", f"kanal_{kanal}"):
            for alt in sorted(glob.glob(os.path.join(CSV_DIR, "*"))):
                if os.path.isdir(alt) and os.path.basename(alt).lower() == ad.lower():
                    yollar += sorted(glob.glob(os.path.join(alt, "*.csv")))
    return yollar


def videolari_birlestir(kayitlar):
    """Ayni basligi tek kayda indirger; olcum alanlarinda EN YUKSEK deger kazanir."""
    birlesik = {}
    for k in kayitlar:
        anahtar = _baslik_anahtar(k.get("baslik"))
        if not anahtar:
            continue
        var = birlesik.get(anahtar)
        if var is None:
            birlesik[anahtar] = dict(k)
            continue
        for alan, deger in k.items():
            if isinstance(deger, (int, float)) and not isinstance(deger, bool):
                eski = var.get(alan)
                if eski is None or deger > eski:
                    var[alan] = deger
            elif alan == "tarih" and deger and not var.get("tarih"):
                var[alan] = deger
    return list(birlesik.values())


# ---------------------------------------------------------------------------
# 3) KALIP MADENCILIGI — kazananlarin dilini cikar (deterministik, LLM yok).
# ---------------------------------------------------------------------------
_STOP = {
    # Rusca
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще",
    "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли",
    "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя",
    "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже",
    "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти",
    "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех",
    "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть",
    "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего",
    "них", "какая", "много", "разве", "три", "эту", "моя", "впрочем", "хорошо",
    "свою", "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя",
    "такой", "им", "более", "всегда", "конечно", "всю", "между", "это",
    # Ingilizce
    "the", "and", "for", "you", "not", "are", "with", "this", "that", "from",
    "they", "was", "his", "her", "she", "but", "all", "can", "will", "what",
    "why", "how", "who", "when", "where", "its", "has", "have", "their", "them",
    # Genel / kanal ust seviye (isaret gucu dusuk)
    "shorts", "short", "видео", "шортс", "youtube", "ютьюб", "фильм", "кино",
    "marvel", "марвел", "mcu", "мси", "факты", "факт", "top", "топ", "the",
}


def _kelimeler(baslik):
    """Basliktan anlamli kelime ve iki-kelime obekleri cikar."""
    t = (baslik or "").lower()
    t = re.sub(r"#\S+", " ", t)                                  # hashtag'ler
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", " ", t)  # emoji
    t = re.sub(r"[^\w\s]+", " ", t, flags=re.UNICODE)
    ham = t.split()
    kelimeler = [w for w in ham if len(w) >= 4 and w not in _STOP and not w.isdigit()]
    # Obekler KOMSU ham kelimelerden kurulur (araya atilan kisa kelime obekleri bozmasin).
    obekler = [f"{a} {b}" for a, b in zip(ham, ham[1:])
               if len(a) >= 4 and len(b) >= 4 and a not in _STOP and b not in _STOP
               and not a.isdigit() and not b.isdigit()]
    return kelimeler + obekler


def kalip_madenciligi(videolar, adet=VARSAYILAN_KALIP_SAYISI):
    """En iyi videolarin basliklarindaki kelimeleri/obekleri kalip olarak cikarir.

    Skor = (kazananlarda gorulme orani) - (digerlerinde gorulme orani).
    Yani "sadece bu videoda cikti" degil, "iyilerde kotulerden FAZLA cikti".
    En az 2 videoda gecmeyen kelime kalip sayilmaz.
    Donus: [{"kelime": ..., "skor": float, "adet": int, "ust_adet": int, "ornek": str}, ...]
    """
    gecerli = [v for v in videolar if (v.get("baslik") or "").strip()
               and isinstance(v.get("izlenme"), (int, float)) and v["izlenme"] > 0]
    if len(gecerli) < MIN_VIDEO_KALIP:
        return []
    gecerli.sort(key=lambda v: -v["izlenme"])
    kesme = max(1, round(len(gecerli) / 3))
    # Her videonun kelime kumesi BIR kez cikarilir (skor + ornek aramasi bunu kullanir).
    sozluk = {id(v): set(_kelimeler(v["baslik"])) for v in gecerli}
    ust, alt = gecerli[:kesme], gecerli[kesme:]

    def sayim(liste):
        s = {}
        for v in liste:
            for w in sozluk[id(v)]:
                s[w] = s.get(w, 0) + 1
        return s

    ust_say, alt_say = sayim(ust), sayim(alt)
    toplam_say = sayim(gecerli)
    n_ust = len(ust)
    n_alt = max(1, len(alt))
    satirlar = []
    for kelime, adet_ust in ust_say.items():
        # Tek videoda gecen kelime kalip sayilmaz (sans/tesaduf filtresi).
        if toplam_say.get(kelime, 0) < 2:
            continue
        skor = (adet_ust / n_ust) - (alt_say.get(kelime, 0) / n_alt)
        if skor <= 0:
            continue
        ornek = next((v["baslik"].strip() for v in ust if kelime in sozluk[id(v)]), "")
        satirlar.append({"kelime": kelime, "skor": round(skor, 4),
                         "adet": toplam_say[kelime], "ust_adet": adet_ust, "ornek": ornek})
    satirlar.sort(key=lambda r: (-r["skor"], -r["adet"], r["kelime"]))
    return satirlar[:adet]


def _tam(x, basamak=2):
    """Tam sayiysa int dondur: ciktilar/promptlar 641000.0 yerine 641000 gostersin."""
    try:
        y = round(float(x), basamak)
    except Exception:
        return x
    return int(y) if float(y).is_integer() else y


def ozet_cikar(videolar):
    """Kanal ozeti: toplam/ortalama izlenme, ortalama CTR, en iyi video."""
    izlenmeler = [v["izlenme"] for v in videolar if isinstance(v.get("izlenme"), (int, float))]
    ctrler = [v["ctr"] for v in videolar if isinstance(v.get("ctr"), (int, float))]
    yuzdeler = [v["ort_yuzde"] for v in videolar if isinstance(v.get("ort_yuzde"), (int, float))]
    en_iyi = max(videolar, key=lambda v: v.get("izlenme") or 0, default=None)
    return {
        "video_sayisi": len(videolar),
        "toplam_izlenme": _tam(sum(izlenmeler)) if izlenmeler else 0,
        "ort_izlenme": _tam(sum(izlenmeler) / len(izlenmeler)) if izlenmeler else 0,
        "ort_ctr": _tam(sum(ctrler) / len(ctrler)) if ctrler else None,
        "ort_izlenme_yuzdesi": _tam(sum(yuzdeler) / len(yuzdeler)) if yuzdeler else None,
        "en_iyi_baslik": (en_iyi or {}).get("baslik", ""),
        "en_iyi_izlenme": _tam((en_iyi or {}).get("izlenme") or 0),
    }


# ---------------------------------------------------------------------------
# 4) DISK — performans.json oku/yaz.
# ---------------------------------------------------------------------------
def _perf_oku():
    try:
        with open(PERF_FILE, "r", encoding="utf-8") as f:
            veri = json.load(f)
        if isinstance(veri, dict) and isinstance(veri.get("kanallar"), dict):
            return veri
    except Exception:
        pass
    return {"guncelleme": "", "kanallar": {}}


def performans_yukle(kanal="genel", kaydet=True):
    """CSV'leri oku, birlestir, ozet + kaliplari cikar ve performans.json'a yaz."""
    yollar = _csv_dosyalari(kanal)
    kayitlar = []
    okunan = []
    for yol in yollar:
        try:
            k = parse_studio_csv(yol)
        except Exception:
            k = []
        if k:
            kayitlar += k
            okunan.append((os.path.basename(yol), len(k)))
    videolar = videolari_birlestir(kayitlar)
    girdi = {
        "okunan_dosyalar": okunan,
        "ozet": ozet_cikar(videolar),
        "videolar": sorted(videolar, key=lambda v: -(v.get("izlenme") or 0)),
        "kaliplar": kalip_madenciligi(videolar),
    }
    if kaydet:
        veri = _perf_oku()
        veri["kanallar"][str(kanal)] = girdi
        veri["guncelleme"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            os.makedirs(BASE_DIR, exist_ok=True)
            with open(PERF_FILE, "w", encoding="utf-8") as f:
                json.dump(veri, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    return girdi


def performans_yukle_tumu():
    """performans_csv/ kokunu + kanalN alt klasorlerini tek seferde isler."""
    kanallar = ["genel"]
    try:
        for ad in sorted(os.listdir(CSV_DIR)):
            yol = os.path.join(CSV_DIR, ad)
            if not os.path.isdir(yol):
                continue
            m = re.match(r"(?:kanal|ch)[ _]?(\d+)$", ad.strip(), re.IGNORECASE)
            if m:
                kanallar.append(m.group(1))
    except Exception:
        pass
    return {k: performans_yukle(k) for k in kanallar}


_ONBELLEK = {"anahtar": None, "veri": None}


def _kanal_verisi(kanal="genel"):
    """performans.json'dan kanal verisi (dosya degismedikce onbellekten)."""
    try:
        damga = (os.path.getmtime(PERF_FILE), os.path.getsize(PERF_FILE))
    except Exception:
        return None
    if _ONBELLEK["anahtar"] == damga and _ONBELLEK["veri"] is not None:
        veri = _ONBELLEK["veri"]
    else:
        veri = _perf_oku()
        _ONBELLEK["anahtar"] = damga
        _ONBELLEK["veri"] = veri
    kanallar = veri.get("kanallar", {})
    girdi = kanallar.get(str(kanal)) if kanal else None
    if not girdi and kanal not in (None, "", "genel"):
        girdi = kanallar.get("genel")
    return girdi


def kaliplar_getir(kanal="genel"):
    """Kanal icin kanitlanmis kaliplar (yoksa bos liste)."""
    girdi = _kanal_verisi(kanal)
    if not girdi:
        return []
    kaliplar = girdi.get("kaliplar") or []
    return kaliplar if isinstance(kaliplar, list) else []


def kalip_blok(kanal="genel", adet=PROMPT_KALIP_SAYISI):
    """Prompt'a gomulecek 'kanitlanmis kaliplar' metni (veri yoksa '')."""
    girdi = _kanal_verisi(kanal)
    if not girdi:
        return ""
    kaliplar = (girdi.get("kaliplar") or [])[:adet]
    if not kaliplar:
        return ""
    ozet = girdi.get("ozet") or {}
    satir = [
        f"PROVEN PATTERNS from my channel's real YouTube Studio data "
        f"({ozet.get('video_sayisi', 0)} videos, avg {ozet.get('ort_izlenme', 0)} views):",
    ]
    for k in kaliplar:
        ornek = (k.get("ornek") or "").strip()
        satir.append(f'- "{k["kelime"]}" (seen in top performers; e.g. "{ornek[:70]}")')
    satir.append("These words/topics are PROVEN to perform on my channel. "
                 "Prefer them when choosing the topic and the hook, and give such candidates "
                 "a clearly higher score.")
    return "\n".join(satir)


# Kiril -> Latin: config kanal adi Latin ('PopkornFakty'), bot scripti Kiril
# ('ПопкорнФакты') yaziyor; ikisini ayni anahtara indirmek icin kucuk tablo.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _ad_anahtar(ad):
    """Kanal adini karsilastirma anahtarina indirger (harf/ayirici farklari silinir)."""
    s = (ad or "").strip().lower()
    s = "".join(_TRANSLIT.get(ch, ch) for ch in s)
    return re.sub(r"[^a-z0-9]+", "", s)


def kanal_no_bul(ad, varsayilan="genel"):
    """Kanal ADINDAN (ornegin "Kino Sekrety") kesif config'indeki kanal numarasini bulur.

    Baslik uretimi kanal adi alir, performans verisi ise kanal no ile tutulur;
    bu kucuk kopru ikisini birlestirir (Kiril/Latin yazim farki da esitlenir).
    Bulunamazsa 'genel' doner.
    """
    hedef = _ad_anahtar(ad)
    if not hedef:
        return varsayilan
    try:
        with open(os.path.join(BASE_DIR, "kesif_config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for no, profil in (cfg.get("kanallar") or {}).items():
            if isinstance(profil, dict) and _ad_anahtar(profil.get("ad")) == hedef:
                return str(no)
    except Exception:
        pass
    return varsayilan


def performans_bonusu(baslik, kaliplar=None, kanal="genel"):
    """Baslik kanitlanmis kaliplarla ortusuyorsa 0..1 arasi DETERMINISTIK bonus.

    Amac: kesif siralamasinda esit kalitedeki adaylarda kanitli temayi one almak.
    En fazla +1.0 puan etki eder (skor 0-10 oldugu icin olculu bir agirlik).
    """
    if kaliplar is None:
        kaliplar = kaliplar_getir(kanal)
    if not kaliplar or not baslik:
        return 0.0
    t = _baslik_anahtar(baslik)
    agirlik = 0.0
    for k in kaliplar:
        kelime = (k.get("kelime") or "").strip().lower()
        if kelime and kelime in t:
            agirlik += max(0.05, float(k.get("skor") or 0))
    if agirlik <= 0:
        return 0.0
    return round(min(1.0, agirlik / 0.6), 3)


def durum_metni():
    """Terminal icin kisa ozet (kac video, kac kalip)."""
    veri = _perf_oku()
    kanallar = veri.get("kanallar", {})
    if not kanallar:
        return f"Performans verisi yok. CSV'leri suraya birakin: {CSV_DIR}"
    parcalar = []
    for ad, girdi in sorted(kanallar.items()):
        ozet = girdi.get("ozet") or {}
        parcalar.append(f"kanal {ad}: {ozet.get('video_sayisi', 0)} video, "
                        f"{len(girdi.get('kaliplar') or [])} kalip")
    return f"Performans verisi ({veri.get('guncelleme', '?')}): " + " | ".join(parcalar)


def _cli():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(f"📂 CSV klasoru : {CSV_DIR}")
    if not os.path.isdir(CSV_DIR):
        print("⚠️  Klasor yok — olusturuldu. YouTube Studio > Icerik > 'Disa aktar' CSV'lerini buraya kopyala.")
        try:
            os.makedirs(CSV_DIR, exist_ok=True)
        except Exception:
            pass
        return 0
    sonuc = performans_yukle_tumu()
    bulundu = False
    for kanal, girdi in sonuc.items():
        ozet = girdi.get("ozet") or {}
        if not ozet.get("video_sayisi"):
            continue
        bulundu = True
        print(f"\n📊 Kanal {kanal}: {ozet['video_sayisi']} video, "
              f"toplam {ozet['toplam_izlenme']:,} izlenme, ort {ozet['ort_izlenme']:,}"
              + (f", ort CTR %{ozet['ort_ctr']}" if ozet.get("ort_ctr") else ""))
        print(f"   En iyi: {ozet.get('en_iyi_baslik', '')[:70]} ({ozet.get('en_iyi_izlenme', 0):,} izlenme)")
        for k in girdi.get("kaliplar") or []:
            print(f"   • {k['kelime']:<24} skor {k['skor']:<7} (orn: {k['ornek'][:48]})")
    if not bulundu:
        print("⚠️  Kullanilabilir satir bulunamadi. Dosyalar YouTube Studio CSV'si mi?")
        print("   Beklenen kolonlar (EN/TR): Video title/Video başlığı, Views/Görüntülenme, ...")
        return 1
    print(f"\n💾 Yazildi: {PERF_FILE}")
    print("✅ kesif.py ve baslik uretimi bu veriyi artik otomatik kullanacak.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
