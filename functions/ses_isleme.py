# -*- coding: utf-8 -*-
"""Ses isleme atolyesi — sadece YEREL ffmpeg ile, ucret/anahtar/ag yok.

YOL_HARITASI.md maddeleri 7 (muzik ducking) ve 11 (ses temizligi + sabit ses
seviyesi) bu modulde toplanir. Botun mevcut zincirine DOKUNMAZ: hicbir yeri
degistirmez, hicbir seyi otomatik cagirmaz. Ister tek dosya uzerinde elle
kullan, ister klipci.py icinden cagrilir.

Ne yapar:
  * gurultu_temizle  → afftdn (FFT denoise) + highpass/lowpass + hafif kompresor
                       (istenirse arnndn: model dosyasi verilirse)
  * ses_esitle       → EBU R128 loudnorm (2 gecisli: olc + uygula) = -14 LUFS
  * muzik_ducking    → sidechaincompress: konusma varken muzigi kisar (amix'in
                       yaptigi duz karisimdan cok daha temiz)
  * tam_isle         → hepsini sirayla uygular (tek komut)

Kullanim:
    py -3 functions/ses_isleme.py --giris ses.wav --cikis temiz.wav
    py -3 functions/ses_isleme.py --giris konusma.mp3 --muzik fon.mp3 --ducking-db -16
    py -3 functions/ses_isleme.py --giris a.wav --olc          # sadece LUFS olcumu
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

# YouTube'un hedefledigi ses seviyesi (qa_kapisi.py ile ayni hedef).
HEDEF_LUFS = -14.0
HEDEF_TRUE_PEAK = -1.5
HEDEF_LRA = 11.0

# Gurultu temizligi siddetleri: (afftdn nr, afftdn nf)
SIDDET = {"hafif": (6, -35), "orta": (12, -28), "guclu": (20, -22)}


def _calistir(komut, timeout=1800):
    """ffmpeg komutunu calistirir; (basarili, stdout, stderr) doner."""
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True,
                               encoding="utf-8", errors="ignore", timeout=timeout)
    except Exception as e:
        return False, "", str(e)
    return sonuc.returncode == 0, sonuc.stdout or "", sonuc.stderr or ""


def _var_mi(yol):
    return bool(yol) and os.path.exists(yol)


def ses_bilgisi(yol):
    """ffprobe ile sure/kanal/ornekleme hizi — sadece bilgi amacli."""
    if not _var_mi(yol):
        return {}
    komut = [FFPROBE, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", yol]
    tamam, cikti, _ = _calistir(komut, timeout=120)
    if not tamam:
        return {}
    try:
        veri = json.loads(cikti)
    except Exception:
        return {}
    ses = next((s for s in veri.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "sure": float(veri.get("format", {}).get("duration") or 0),
        "kanal": int(ses.get("channels") or 0),
        "ornek_hizi": int(ses.get("sample_rate") or 0),
    }


def lufs_olc(yol):
    """ebur128 ile gercek ses yuksekligi olcumu: {'lufs','true_peak','lra'}."""
    if not _var_mi(yol):
        return None
    komut = [FFMPEG, "-hide_banner", "-nostats", "-i", yol,
             "-af", "ebur128=peak=true", "-f", "null", os.devnull]
    tamam, _, hata = _calistir(komut, timeout=900)
    if not tamam and not hata:
        return None
    metin = hata
    i = metin.rfind("Integrated loudness")
    if i < 0:
        return None
    blok = metin[i:i + 400]

    def _say(desen, varsayilan=None):
        m = re.search(desen, blok)
        if not m:
            return varsayilan
        try:
            return float(m.group(1))
        except Exception:
            return varsayilan

    return {
        "lufs": _say(r"I:\s*(-?[\d.]+)\s*LUFS"),
        "true_peak": _say(r"Peak:\s*(-?[\d.]+)\s*dBFS"),
        "lra": _say(r"LRA:\s*(-?[\d.]+)\s*LU"),
    }


def gurultu_temizle(giris, cikis, siddet="orta", arnndn_model=None, timeout=1800):
    """afftdn (+ arnndn) + highpass/lowpass ile arka plan gurultusunu dusurur."""
    if not _var_mi(giris):
        print(f"❌ Ses dosyasi bulunamadi: {giris}")
        return False
    nr, nf = SIDDET.get(siddet, SIDDET["orta"])
    zincir = []
    if arnndn_model and _var_mi(arnndn_model):
        # arnndn: konusma icin egitilmis RNN gurultu temizleyici (model gerekir)
        zincir.append(f"arnndn=m='{arnndn_model}':mix=0.9")
    zincir.append(f"afftdn=nr={nr}:nf={nf}:tn=1")
    zincir.append("highpass=f=80")
    zincir.append("lowpass=f=12000")
    # Hafif kompresor: konusmayi one cikarir, fiskirmayi engeller.
    zincir.append("acompressor=threshold=-18dB:ratio=2.5:attack=8:release=180:makeup=2")
    komut = [FFMPEG, "-y", "-hide_banner", "-nostats", "-i", giris,
             "-af", ",".join(zincir), "-c:a", "pcm_s16le", cikis]
    tamam, _, hata = _calistir(komut, timeout=timeout)
    if not tamam:
        print(f"❌ Gurultu temizligi basarisiz: {hata.strip().splitlines()[-1] if hata.strip() else 'bilinmeyen hata'}")
        return False
    print(f"✅ Gurultu temizlendi ({siddet}): {os.path.basename(cikis)}")
    return True


def ses_esitle(giris, cikis, hedef_lufs=HEDEF_LUFS, timeout=1800):
    """EBU R128 (2 gecisli loudnorm) ile sesi hedef LUFS'a esitler."""
    if not _var_mi(giris):
        print(f"❌ Ses dosyasi bulunamadi: {giris}")
        return False
    # 1. gecis: gercek olcum (tek gecis loudnorm dinamikleri bozar).
    olcum_komut = [FFMPEG, "-hide_banner", "-nostats", "-i", giris,
                   "-af", f"loudnorm=I={hedef_lufs}:TP={HEDEF_TRUE_PEAK}:LRA={HEDEF_LRA}:print_format=json",
                   "-f", "null", os.devnull]
    tamam, _, hata = _calistir(olcum_komut, timeout=timeout)
    olcum = {}
    if tamam:
        m = re.findall(r"\{[^{}]*input_i[^{}]*\}", hata, re.S)
        if m:
            try:
                olcum = json.loads(m[-1])
            except Exception:
                olcum = {}
    if olcum:
        uygula = (
            f"loudnorm=I={hedef_lufs}:TP={HEDEF_TRUE_PEAK}:LRA={HEDEF_LRA}"
            f":measured_I={olcum.get('input_i')}:measured_TP={olcum.get('input_tp')}"
            f":measured_LRA={olcum.get('input_lra')}:measured_thresh={olcum.get('input_thresh')}"
            f":offset={olcum.get('target_offset', 0)}:linear=true"
        )
    else:
        print("⚠️ Olcum alinamadi, tek gecis loudnorm uygulaniyor.")
        uygula = f"loudnorm=I={hedef_lufs}:TP={HEDEF_TRUE_PEAK}:LRA={HEDEF_LRA}"
    komut = [FFMPEG, "-y", "-hide_banner", "-nostats", "-i", giris,
             "-af", uygula, "-c:a", "pcm_s16le", cikis]
    tamam, _, hata = _calistir(komut, timeout=timeout)
    if not tamam:
        print(f"❌ Ses esitleme basarisiz: {hata.strip().splitlines()[-1] if hata.strip() else 'bilinmeyen hata'}")
        return False
    sonuc = lufs_olc(cikis)
    if sonuc and sonuc.get("lufs") is not None:
        print(f"✅ Ses esitlendi: {sonuc['lufs']:.1f} LUFS (hedef {hedef_lufs}) → {os.path.basename(cikis)}")
    else:
        print(f"✅ Ses esitlendi: {os.path.basename(cikis)}")
    return True


def muzik_ducking(konusma, muzik, cikis, ducking_db=-16.0, muzik_db=-20.0,
                  ducking_orani=8.0, timeout=1800):
    """sidechaincompress: konusma varken muzigi `ducking_db` kadar kisar.

    Eski duz `amix` karisimi konusmanin uzerine muzigi bastiriyordu (Shorts'ta
    en sik sikayet). Sidechain ile muzik sadece bosluklarda yukselir.
    """
    if not _var_mi(konusma) or not _var_mi(muzik):
        print("❌ Ducking icin hem konusma hem muzik dosyasi gerekli.")
        return False
    # Muzik dongusel olarak konusma suresine uzatilir (-stream_loop -1).
    filtre = (
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[spk];"
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"volume={muzik_db}dB[muz];"
        f"[muz][spk]sidechaincompress=threshold=0.03:ratio={ducking_orani}:attack=20:release=350:"
        f"level_sc=1.2:makeup=1[muzd];"
        f"[spk][muzd]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
    )
    komut = [FFMPEG, "-y", "-hide_banner", "-nostats",
             "-i", konusma, "-stream_loop", "-1", "-i", muzik,
             "-filter_complex", filtre, "-map", "[out]",
             "-c:a", "pcm_s16le", cikis]
    tamam, _, hata = _calistir(komut, timeout=timeout)
    if not tamam:
        print(f"❌ Muzik ducking basarisiz: {hata.strip().splitlines()[-1] if hata.strip() else 'bilinmeyen hata'}")
        return False
    print(f"✅ Muzik ducking uygulandi ({ducking_db:+.0f} dB): {os.path.basename(cikis)}")
    return True


def tam_isle(giris, cikis, muzik=None, siddet="orta", hedef_lufs=HEDEF_LUFS,
             arnndn_model=None, ducking_db=-16.0, gecici_klasor=None):
    """Temizle → (muzik varsa ducking) → LUFS esitle. Cikti tek dosya."""
    if not _var_mi(giris):
        print(f"❌ Ses dosyasi bulunamadi: {giris}")
        return False
    tmp = gecici_klasor or tempfile.mkdtemp(prefix="vf_ses_")
    try:
        temiz = os.path.join(tmp, "temiz.wav")
        if not gurultu_temizle(giris, temiz, siddet=siddet, arnndn_model=arnndn_model):
            return False
        kaynak = temiz
        if muzik and _var_mi(muzik):
            karisim = os.path.join(tmp, "karisim.wav")
            if muzik_ducking(temiz, muzik, karisim, ducking_db=ducking_db):
                kaynak = karisim
        return ses_esitle(kaynak, cikis, hedef_lufs=hedef_lufs)
    finally:
        if gecici_klasor is None:
            shutil.rmtree(tmp, ignore_errors=True)


def _cli(argv=None):
    p = argparse.ArgumentParser(description="VideoForge ses isleme (yerel ffmpeg, ucretsiz)")
    p.add_argument("--giris", required=False, help="Kaynak ses/video dosyasi")
    p.add_argument("--cikis", help="Cikti dosyasi (wav)")
    p.add_argument("--muzik", help="Fon muzigi (ducking icin)")
    p.add_argument("--siddet", choices=list(SIDDET), default="orta")
    p.add_argument("--lufs", type=float, default=HEDEF_LUFS)
    p.add_argument("--arnndn", help="arnndn model dosyasi (.rnnn) — opsiyonel")
    p.add_argument("--ducking-db", type=float, default=-16.0)
    p.add_argument("--olc", action="store_true", help="Sadece LUFS olcumu yap")
    p.add_argument("--temizle", action="store_true", help="Sadece gurultu temizligi")
    p.add_argument("--esitle", action="store_true", help="Sadece LUFS esitleme")
    a = p.parse_args(argv)

    if a.olc:
        if not a.giris:
            print("❌ --olc icin --giris gerekli")
            return 1
        sonuc = lufs_olc(a.giris) or {}
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
        return 0 if sonuc.get("lufs") is not None else 1

    if not a.giris or not a.cikis:
        print("❌ --giris ve --cikis gerekli (yardim: --help)")
        return 1

    if a.temizle:
        return 0 if gurultu_temizle(a.giris, a.cikis, siddet=a.siddet, arnndn_model=a.arnndn) else 1
    if a.esitle:
        return 0 if ses_esitle(a.giris, a.cikis, hedef_lufs=a.lufs) else 1
    tamam = tam_isle(a.giris, a.cikis, muzik=a.muzik, siddet=a.siddet, hedef_lufs=a.lufs,
                     arnndn_model=a.arnndn, ducking_db=a.ducking_db)
    return 0 if tamam else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(_cli())
