# -*- coding: utf-8 -*-
"""Yayin oncesi QA kapisi — videoyu yayina cikmadan ONCE olcer ve skorlar.

NEDEN: Bot final videoyu urettikten sonra ona hicbir sey SORMUYORDU; siyah
kareyle baslayan, sesi kesik, 70 saniyelik (Shorts sayilmayan) bir video da
"basarili" sayiliyordu. Bu modul final dosyayi ffmpeg ile gercekten acar:

  * sure + en-boy orani (dikey Shorts araliginda mi)
  * siyah kare suresi  (blackdetect)   -> acilista bos ekran / render hatasi
  * donmus kare suresi (freezedetect)  -> takilan sahne
  * sessizlik suresi   (silencedetect) -> bos/kopuk ses
  * ses yuksekligi     (ebur128 LUFS)  -> YouTube'un hedefledigi -14 LUFS

Cikti: puan (0-100), derece (GECTI/ORTA/ZAYIF), Turkce sorun listesi ve
videonun yanina yazilan <ad>_qa.json raporu. Hicbir sey yuklenmez, ag/anahtar
kullanilmaz; sadece yerel ffmpeg calisir.

Kullanim:
    py -3 functions/qa_kapisi.py <video.mp4>
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

# Shorts hedefleri (YouTube Shorts: 3 dk'a kadar ama bu kanal 25-60 sn uretiyor)
HEDEF_MIN_SN = 15.0
HEDEF_MAKS_SN = 60.0
# YouTube normalde -14 LUFS'a normalize eder; +/-4 LU disi "ses zayif/yuksek".
HEDEF_LUFS = -14.0
LUFS_TOLERANS = 4.0
# Bu puanin alti "yayina hazir degil" kabul edilir (1 tur yeniden uretim onerilir).
KALITE_ESIGI = 70
VARSAYILAN_TIMEOUT = 900


def _calistir(cmd, timeout=VARSAYILAN_TIMEOUT):
    """ffmpeg/ffprobe calistir; cikti/stderr metnini dondur (hata firlatmaz)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} bulunamadi (PATH'e ekleyin)"
    except subprocess.TimeoutExpired:
        return 124, "", f"zaman asimi ({timeout}s)"
    except Exception as e:  # pragma: no cover - beklenmeyen
        return 1, "", str(e)


def yuvarlak(deger, basamak=2):
    try:
        return round(float(deger) + 0.0, basamak)
    except Exception:
        return None


def ffprobe_bilgi(path):
    """Konteyner + akis bilgisi (sure, cozunurluk, fps, ses var mi)."""
    kod, cikti, hata = _calistir([
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ], timeout=120)
    bilgi = {"ok": False, "hata": "", "sure": None, "genislik": None, "yukseklik": None,
             "fps": None, "ses_var": False, "ses_sure": None, "video_kodek": None,
             "ses_kodek": None}
    if kod != 0 or not cikti.strip():
        bilgi["hata"] = (hata or "").strip()[:300] or f"ffprobe exit={kod}"
        return bilgi
    try:
        veri = json.loads(cikti)
    except Exception as e:
        bilgi["hata"] = f"ffprobe JSON okunamadi: {e}"
        return bilgi
    bilgi["ok"] = True
    try:
        bilgi["sure"] = float((veri.get("format") or {}).get("duration"))
    except Exception:
        bilgi["sure"] = None
    for akis in veri.get("streams") or []:
        tip = akis.get("codec_type")
        if tip == "video" and bilgi["genislik"] is None:
            bilgi["genislik"] = akis.get("width")
            bilgi["yukseklik"] = akis.get("height")
            bilgi["video_kodek"] = akis.get("codec_name")
            for anahtar in ("r_frame_rate", "avg_frame_rate"):
                fps = _fps_cek(akis.get(anahtar))
                if fps:
                    bilgi["fps"] = fps
                    break
            if bilgi["sure"] is None:
                try:
                    bilgi["sure"] = float(akis.get("duration"))
                except Exception:
                    pass
        elif tip == "audio":
            bilgi["ses_var"] = True
            bilgi["ses_kodek"] = akis.get("codec_name")
            try:
                bilgi["ses_sure"] = float(akis.get("duration"))
            except Exception:
                pass
    return bilgi


def _fps_cek(deger):
    if not deger or "/" not in str(deger):
        return None
    try:
        pay, payda = str(deger).split("/")
        payda = float(payda)
        return round(float(pay) / payda, 3) if payda else None
    except Exception:
        return None


def _video_olcum(path, timeout):
    """Sarih kare + donmus kare suresini TEK ffmpeg gecisinde olcer."""
    kod, _, hata = _calistir([
        FFMPEG, "-nostdin", "-hide_banner", "-i", path,
        "-vf", "blackdetect=d=0.1:pix_th=0.10,freezedetect=n=-60dB:d=1.5",
        "-an", "-f", "null", os.devnull,
    ], timeout=timeout)
    siyah = sum(float(x) for x in re.findall(r"black_duration:\s*([0-9.]+)", hata))
    donmus = sum(float(x) for x in re.findall(r"freeze_duration:\s*([0-9.]+)", hata))
    return {"siyah_sn": round(siyah, 2), "donmus_sn": round(donmus, 2),
            "olcum_ok": kod == 0, "hata": (hata or "")[:200] if kod != 0 else ""}


def _ses_olcum(path, timeout):
    """Sessizlik + yukseklik (LUFS) olcumu; ses akisi yoksa ses_var=False doner."""
    kod, _, hata = _calistir([
        FFMPEG, "-nostdin", "-hide_banner", "-i", path,
        "-vn", "-af", "silencedetect=noise=-35dB:d=0.5,ebur128=peak=true",
        "-f", "null", os.devnull,
    ], timeout=timeout)
    sessizlik = sum(float(x) for x in re.findall(r"silence_duration:\s*([0-9.]+)", hata))
    lufs = None
    eslesme = re.findall(r"\bI:\s*(-?[0-9.]+)\s*LUFS", hata)
    if eslesme:
        lufs = float(eslesme[-1])
    tepe = None
    eslesme = re.findall(r"Peak:\s*(-?[0-9.]+)\s*dBFS", hata)
    if eslesme:
        tepe = float(eslesme[-1])
    ses_yok = bool(re.search(r"does not contain any stream|matches no streams", hata or ""))
    return {"sessiz_sn": round(sessizlik, 2), "lufs": yuvarlak(lufs),
            "true_peak": yuvarlak(tepe), "ses_yok": ses_yok,
            "olcum_ok": kod == 0 and not ses_yok, "hata": (hata or "")[:200] if kod != 0 else ""}


def video_denetle(path, timeout=VARSAYILAN_TIMEOUT):
    """Bir video dosyasini olcup puanlar. Donus: rapor sozlugu (her zaman doner)."""
    path = os.path.abspath(path)
    rapor = {
        "dosya": os.path.basename(path), "yol": path, "tarih": None,
        "sure": None, "genislik": None, "yukseklik": None, "fps": None,
        "ses_var": False, "siyah_sn": 0.0, "donmus_sn": 0.0, "sessiz_sn": 0.0,
        "lufs": None, "true_peak": None,
        "siyah_oran": 0.0, "donmus_oran": 0.0, "sessiz_oran": 0.0,
        "sorunlar": [], "skor": 0, "derece": "OLCULEMEDI", "gecti": False,
        "olcum_hata": "",
    }
    if not os.path.exists(path):
        rapor["olcum_hata"] = "Dosya yok"
        rapor["sorunlar"] = ["Dosya bulunamadi"]
        return rapor

    bilgi = ffprobe_bilgi(path)
    if not bilgi["ok"]:
        rapor["olcum_hata"] = f"ffprobe: {bilgi['hata']}"
        rapor["sorunlar"] = ["Video okunamadi (bozuk/eksik render)"]
        return rapor

    rapor.update({"sure": yuvarlak(bilgi["sure"]), "genislik": bilgi["genislik"],
                  "yukseklik": bilgi["yukseklik"], "fps": bilgi["fps"],
                  "ses_var": bool(bilgi["ses_var"])})
    sure = bilgi["sure"] or 0.0

    vo = _video_olcum(path, timeout)
    rapor["siyah_sn"] = vo["siyah_sn"]
    rapor["donmus_sn"] = vo["donmus_sn"]
    so = _ses_olcum(path, timeout)
    rapor["sessiz_sn"] = so["sessiz_sn"]
    rapor["lufs"] = so["lufs"]
    rapor["true_peak"] = so["true_peak"]
    if not vo["olcum_ok"] or not so["olcum_ok"]:
        rapor["olcum_hata"] = (vo["hata"] or so["hata"] or "ffmpeg olcumu tamamlanmadi")[:200]

    if sure > 0:
        rapor["siyah_oran"] = yuvarlak(rapor["siyah_sn"] / sure, 4)
        rapor["donmus_oran"] = yuvarlak(rapor["donmus_sn"] / sure, 4)
        rapor["sessiz_oran"] = yuvarlak(rapor["sessiz_sn"] / sure, 4)

    skor, sorunlar = _skorla(rapor)
    rapor["skor"] = skor
    rapor["sorunlar"] = sorunlar
    rapor["derece"] = "GECTI" if skor >= 85 else ("ORTA" if skor >= KALITE_ESIGI else "ZAYIF")
    rapor["gecti"] = skor >= KALITE_ESIGI
    rapor["tarih"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return rapor


def _skorla(rapor):
    """100'den ceza duserek puan + Turkce sorun listesi uretir."""
    puan = 100
    sorunlar = []
    sure = rapor.get("sure") or 0.0
    w, h = rapor.get("genislik"), rapor.get("yukseklik")

    if not rapor.get("ses_var"):
        puan -= 30
        sorunlar.append("Ses akisi YOK (video sessiz yayinlanir)")
    if sure and sure < HEDEF_MIN_SN:
        puan -= 25
        sorunlar.append(f"Cok kisa: {sure:.1f} sn (< {HEDEF_MIN_SN:.0f} sn)")
    elif sure and sure > HEDEF_MAKS_SN:
        puan -= 10
        sorunlar.append(f"Uzun: {sure:.1f} sn (> {HEDEF_MAKS_SN:.0f} sn, Shorts sinirinda)")
    if w and h and h < w * 1.5:
        puan -= 15
        sorunlar.append(f"Dikey degil: {w}x{h} (Shorts 9:16 ister)")

    siyah = rapor.get("siyah_oran") or 0.0
    if siyah > 0.15:
        puan -= 30
        sorunlar.append(f"Siyah kare cok fazla: %{siyah * 100:.1f} (render/acilis hatasi?)")
    elif siyah > 0.05:
        puan -= 20
        sorunlar.append(f"Siyah kare var: %{siyah * 100:.1f}")
    elif rapor.get("siyah_sn"):
        puan -= 5
        sorunlar.append(f"Az siyah kare: {rapor['siyah_sn']:.1f} sn")

    donmus = rapor.get("donmus_oran") or 0.0
    if donmus > 0.20:
        puan -= 20
        sorunlar.append(f"Goruntu donuyor: %{donmus * 100:.1f} (kare takilmasi)")
    elif donmus > 0.10:
        puan -= 12
        sorunlar.append(f"Kisa donma: %{donmus * 100:.1f}")

    sessiz = rapor.get("sessiz_oran") or 0.0
    if rapor.get("ses_var"):
        if sessiz > 0.45:
            puan -= 20
            sorunlar.append(f"Sesin %{sessiz * 100:.1f}'i sessiz (kopuk ses/susma)")
        elif sessiz > 0.25:
            puan -= 10
            sorunlar.append(f"Sessizlik yuksek: %{sessiz * 100:.1f}")

    lufs = rapor.get("lufs")
    if rapor.get("ses_var"):
        if lufs is None:
            puan -= 5
            sorunlar.append("Ses yuksekligi olculemedi")
        elif abs(lufs - HEDEF_LUFS) > LUFS_TOLERANS:
            puan -= 10
            yon = "kisik" if lufs < HEDEF_LUFS else "yuksek"
            sorunlar.append(f"Ses {yon}: {lufs:.1f} LUFS (hedef {HEDEF_LUFS:.0f} +/-{LUFS_TOLERANS:.0f})")
    tepe = rapor.get("true_peak")
    if tepe is not None and tepe > -0.5:
        puan -= 8
        sorunlar.append(f"True peak {tepe:.1f} dBFS (kirpilma riski)")

    return max(0, min(100, int(round(puan)))), sorunlar


def rapor_yaz(rapor, klasor=None):
    """Raporu videonun yanina <ad>_qa.json olarak yaz; yolu dondur."""
    yol = rapor.get("yol") or ""
    if not yol or not os.path.exists(yol):
        return ""  # olmayan dosya icin rapor yazma (CLI yanlis yol verilmis olabilir)
    klasor = klasor or (os.path.dirname(yol) or ".")
    kok = os.path.splitext(os.path.basename(yol))[0] or "video"
    hedef = os.path.join(klasor, f"{kok}_qa.json")
    try:
        with open(hedef, "w", encoding="utf-8") as f:
            json.dump(rapor, f, indent=2, ensure_ascii=False)
        return hedef
    except Exception:
        return ""


def rapor_metni(rapor):
    """Terminal icin kisa, okunur rapor metni."""
    if rapor.get("derece") == "OLCULEMEDI":
        return f"❌ QA olculemedi: {rapor.get('olcum_hata', '?')}"
    ikon = {"GECTI": "✅", "ORTA": "⚠️", "ZAYIF": "❌"}.get(rapor["derece"], "?")
    satir = [
        f"{ikon} QA skoru {rapor['skor']}/100 ({rapor['derece']}) — {rapor['dosya']}",
        f"   sure {rapor['sure']}s | {rapor['genislik']}x{rapor['yukseklik']} | "
        f"siyah {rapor['siyah_oran'] * 100:.1f}% | donma {rapor['donmus_oran'] * 100:.1f}% | "
        f"sessiz {rapor['sessiz_oran'] * 100:.1f}% | {rapor['lufs']} LUFS",
    ]
    for s in rapor.get("sorunlar") or []:
        satir.append(f"   • {s}")
    if rapor.get("gecti"):
        satir.append("   ✅ Yayina hazir.")
    else:
        satir.append("   ⚠️ Yayina hazir DEGIL — duzeltip yeniden uretmek icin 1 tur onerilir.")
    return "\n".join(satir)


def denetle_ve_yaz(path, yaz=True, bas=True):
    """Video denetle -> raporu bas -> json yaz. Donus: rapor sozlugu."""
    rapor = video_denetle(path)
    if bas:
        print(rapor_metni(rapor))
    if yaz:
        hedef = rapor_yaz(rapor)
        if hedef and bas:
            print(f"   📄 {hedef}")
    return rapor


def _cli(argv):
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if not argv:
        print("Kullanim: py -3 functions/qa_kapisi.py <video.mp4> [video2.mp4 ...]")
        return 2
    son = 0
    for yol in argv:
        rapor = denetle_ve_yaz(yol)
        if not rapor.get("gecti"):
            son = 1
    return son


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
