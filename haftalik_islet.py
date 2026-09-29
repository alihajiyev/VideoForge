# -*- coding: utf-8 -*-
"""
VideoForge Cok Gunlu Isletici — kesif.py --haftalik N / --gun N'in urettigi
haftalik_plan.json'u okur, videolari gun sirasina gore TEK TEK (asla ayni
anda degil) 3 adimli zincirden gecirir:

  1. KESIF (zaten yapildi): haftalik_plan.json'daki N video
  2. VIDEOFORGE: her video temizlenir, SEO + ses hazirlanir.
     Cikti: Masaustu/GunN_*/ icinde *_CLEAN.mp4 + *.mp3 + *_SEO.html (+ png)
  3. SHORTSSTUDIO: Gun klasorundeki mp4 + mp3 + SEO html alinir, ShortsStudio'da
     montaj/edit yapilir. Cikti: Masaustu/final_XXXXXX.mp4 (+ Gun klasorune kopya)

Kullanim:
    python kesif.py --gun 10        # once 10 gunluk plan uret (--haftalik 10 ile ayni)
    python haftalik_islet.py        # sonra 3 adimli zinciri sirali islet
    python haftalik_islet.py --basla 3   # 3. gunden devam et (kaldigin yerden)
    python haftalik_islet.py --studio-atla  # sadece VideoForge (eski davranis)
"""
import sys
import os
import argparse
import glob
import json
import re
import shutil
import subprocess
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import link_kayitlimi, init_db
from functions.ui import header, footer_done, footer_fail, info, ok, warn, err

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAN_FILE = os.path.join(BASE_DIR, "haftalik_plan.json")


def sonuc_dosyasi(chn):
    # Kanal bazli sonuc haritasi (tum kanallar art arda kosunca ezilmesin).
    return os.path.join(BASE_DIR, f"haftalik_sonuc_ch{chn}.json")


def plan_toplam(plan, varsayilan=7):
    """Plandaki hedef gun sayisi ('toplam'; eski planlarda da 'toplam')."""
    try:
        return int(plan.get("toplam") or plan.get("gun_sayisi") or varsayilan)
    except Exception:
        return varsayilan


def iptal_edildi():
    """Uygulamadaki 'Durdur' istegi geldi mi?

    Desktop uygulamasi alt surecin ortamina VIDEOFORGE_CANCEL_FILE yazar.
    Surec agaci oldurulemezse bile bot gun aralarinda temiz sekilde durur.
    """
    yol = os.environ.get("VIDEOFORGE_CANCEL_FILE")
    return bool(yol) and os.path.exists(yol)

# Kesif kanal no -> VideoForge bot scripti (VideoForge-Baslat.bat ile ayni eslesme)
CHN_SCRIPT = {
    "1": "kinosekrety.py",   # Kino Sekrety
    "2": "faktza15.py",      # Fakt Za 15
    "3": "kinok_syjet.py",   # PopkornFakty
}

# Kesif kanal no -> ShortsStudio kanal no (ShortsStudio-Editor.bat ile ayni sira:
# 1 Kinosekreti - Film, 2 FaktZa15, 3 PopkornFakty). Sira birebir estir.
CHN_STUDIO_NO = {
    "1": "1",
    "2": "2",
    "3": "3",
}


def _desktop():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def studio_dir_bul():
    """ShortsStudio klasorunu bul (Masaustu/ShortsStudio, yoksa VideoForge'un komsusu)."""
    adaylar = [
        os.path.join(_desktop(), "ShortsStudio"),
        os.path.join(os.path.dirname(BASE_DIR), "ShortsStudio"),
    ]
    for d in adaylar:
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "main.py")):
            return d
    return adaylar[0]


def studio_mevcut(studio_dir):
    return os.path.isdir(studio_dir) and os.path.exists(os.path.join(studio_dir, "main.py"))


def find_gun_klasoru(desktop, gun):
    """Masaustundeki Gun{gun}_* klasorlerinden en yenisini dondur (yoksa None)."""
    desen = os.path.join(desktop, f"Gun{gun}_*")
    adaylar = [d for d in glob.glob(desen) if os.path.isdir(d)]
    if not adaylar:
        return None
    adaylar.sort(key=lambda d: os.path.getmtime(d), reverse=True)
    return adaylar[0]


def find_gun_girdileri(gun_dir):
    """Gun klasorunden ShortsStudio girdilerini bul.

    VideoForge kanala gore farkli son ek kullanir (kinosekrety/kinok_syjet:
    *_VOICEOVER.mp3, faktza15: *_ses.mp3), o yuzden sonek yerine tur aranir.
    Donus: (mp4, mp3, seo_html) ya da eksikse (None, aciklama).
    """
    mp4ler = [f for f in glob.glob(os.path.join(gun_dir, "*.mp4"))
              if not os.path.basename(f).startswith("final_")]
    if not mp4ler:
        return None, "Gun klasorunde .mp4 bulunamadi"
    # *_CLEAN.mp4 tercih edilir, yoksa en buyuk mp4 (ham degil temiz cikti).
    cleanler = [f for f in mp4ler if f.upper().endswith("_CLEAN.MP4")]
    video = cleanler[0] if cleanler else sorted(mp4ler, key=os.path.getsize, reverse=True)[0]

    mp3ler = glob.glob(os.path.join(gun_dir, "*.mp3"))
    if not mp3ler:
        return None, "Gun klasorunde .mp3 bulunamadi"
    voice = [f for f in mp3ler if "VOICEOVER" in os.path.basename(f).upper()]
    ses = [f for f in mp3ler if os.path.basename(f).lower().endswith("_ses.mp3")]
    if voice:
        audio = voice[0]
    elif ses:
        audio = ses[0]
    else:
        audio = sorted(mp3ler, key=os.path.getsize, reverse=True)[0]

    seolar = [f for f in glob.glob(os.path.join(gun_dir, "*.html"))
              if "SEO" in os.path.basename(f).upper()]
    if not seolar:
        return None, "Gun klasorunde *_SEO.html bulunamadi"
    seo = sorted(seolar, key=os.path.getmtime, reverse=True)[0]
    return (video, audio, seo), ""


FINAL_RE = re.compile(r"final_\d+\.mp4")
KILIT_DOSYASI = os.path.join(BASE_DIR, ".haftalik_islet.lock")
KILIT_OMRU_SN = 4 * 3600  # kesin ust sinir: bundan eski kilit her halukarda bayattir


def pid_yasiyor(pid):
    """Verilen islem numarasi hala calisiyor mu? (Windows/macOS/Linux)"""
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            cikti = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                   capture_output=True, text=True, timeout=15)
            return str(pid) in (cikti.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _final_adi_bul(cikti):
    """ShortsStudio ciktisindaki final dosya adini dondur (son eslesme gecerli).
    main.py bitiste 'Masaustu -> final_XXXXXX.mp4' basar; baska final adi
    gecmez. Bulunamazsa None (render basarisiz demektir)."""
    eslesmeler = FINAL_RE.findall(cikti or "")
    return eslesmeler[-1] if eslesmeler else None


def kilit_al():
    """Zincir kilidi: ayni anda 2 kosu calismasin (girdi/final karismasini onler).

    Bayat kilit artik SAATLE degil, GERCEK islem kontroluyle anlasilir:
    kilidi tutan pid olmusse kilit hemen serbest kalir. Eskiden bir kosu
    yarida kesilince (Durdur / pencere kapanmasi) 4 saat boyunca
    "Baska bir haftalik zincir calisiyor olabilir" hatasi veriyordu.
    Donus: (True, '') ya da (False, sebep)."""
    try:
        fd = os.open(KILIT_DOSYASI, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n{time.time():.0f}\n")
        return True, ""
    except FileExistsError:
        pass
    except Exception as e:
        return False, f"Kilit yazilamadi: {e}"
    try:
        with open(KILIT_DOSYASI, "r", encoding="utf-8") as f:
            satirlar = f.read().split()
        pid = int(satirlar[0]) if satirlar else 0
        yas = time.time() - float(satirlar[1]) if len(satirlar) > 1 else 0
    except Exception:
        pid, yas = 0, 0
    # Gercekten calisan bir zincir mi? (pid canli VE kilit makul yasta)
    if pid and yas < KILIT_OMRU_SN and pid_yasiyor(pid):
        return False, (f"Baska bir zincir calisiyor (pid {pid}, {int(yas)}sn). "
                       f"Bitmesini bekle. Takildiysa: {KILIT_DOSYASI} dosyasini sil.")
    # pid olmus ya da cok eski -> kilit bayat, temizle ve yeniden dene.
    if pid:
        print(f"🔓 Bayat kilit temizlendi (pid {pid} artik calismiyor).")
    try:
        os.remove(KILIT_DOSYASI)
    except Exception:
        pass
    return kilit_al()


def kilit_birak():
    try:
        if os.path.exists(KILIT_DOSYASI):
            os.remove(KILIT_DOSYASI)
    except Exception:
        pass


def studio_islet(gun, chn, gun_toplam=0):
    """3. adim: Gun klasorundeki ciktiyi ShortsStudio'dan gecir.

    Donus: (True, final_dosya_adi) ya da (False, hata_mesaji).
    Tek render yapilir; final SADECE Masaustu/final_XXXXXX.mp4 olarak cikar
    (Gun klasorune kopya birakilmaz — hangi finalin hangi gune ait oldugu
    konsol ozeti + haftalik_sonuc_chN.json'da yaziyor).
    """
    desktop = _desktop()
    studio_dir = studio_dir_bul()
    if not studio_mevcut(studio_dir):
        return False, f"ShortsStudio bulunamadi: {studio_dir}"

    gun_dir = find_gun_klasoru(desktop, gun)
    if not gun_dir:
        return False, f"Masaustunde Gun{gun}_* klasoru bulunamadi (VideoForge ciktisi yok?)"

    girdiler, hata = find_gun_girdileri(gun_dir)
    if not girdiler:
        return False, hata
    video_path, audio_path, seo_path = girdiler

    # ShortsStudio kokte kalan eski girdiler varsa karismasin diye dur.
    # (main.py en yeni mp4/mp3'u secer ama SEO html'i rastgele [0] secer — bayat dosya risk.)
    onceki_mp4 = [f for f in glob.glob(os.path.join(studio_dir, "*.mp4"))
                  if not os.path.basename(f).startswith("final_")]
    onceki_mp3 = glob.glob(os.path.join(studio_dir, "*.mp3"))
    onceki_seo = [f for f in glob.glob(os.path.join(studio_dir, "*.html"))
                  if "SEO" in os.path.basename(f).upper()]
    if onceki_mp4 or onceki_mp3 or onceki_seo:
        return False, ("ShortsStudio klasorunde eski girdi dosyalari var "
                       "(main.py yanlis dosyayi secebilir). Lutfen ShortsStudio klasorundeki "
                       ".mp4/.mp3/*SEO*.html dosyalarini temizleyip tekrar calistir.")

    studio_no = CHN_STUDIO_NO.get(str(chn), "1")

    hedef_video = os.path.join(studio_dir, os.path.basename(video_path))
    hedef_audio = os.path.join(studio_dir, os.path.basename(audio_path))
    hedef_seo = os.path.join(studio_dir, os.path.basename(seo_path))
    kopyalanan = []
    try:
        shutil.copy2(video_path, hedef_video)
        kopyalanan.append(hedef_video)
        shutil.copy2(audio_path, hedef_audio)
        kopyalanan.append(hedef_audio)
        shutil.copy2(seo_path, hedef_seo)
        kopyalanan.append(hedef_seo)
    except Exception as e:
        for f in kopyalanan:
            try:
                os.remove(f)
            except Exception:
                pass
        return False, f"ShortsStudio'ya kopyalama hatasi: {e}"

    info(f"🎬 ShortsStudio montaji basliyor (Gun {gun}, kanal no {studio_no})...")
    info(f"   Video: {os.path.basename(video_path)}")
    info(f"   Ses:   {os.path.basename(audio_path)}")
    env = dict(os.environ)
    env["CHANNEL_NUM"] = studio_no
    # ShortsStudio emoji basar (✅/›); pipe'li stdout cp1254'e dusup
    # UnicodeEncodeError veriyor. UTF-8 moda zorla (ShortsStudio koduna dokunmadan).
    env["PYTHONUTF8"] = "1"
    cmd = [sys.executable, "-m", "modal", "run", "main.py"]
    # Ciktiyi CANLI goster + topla: final adi BU kosunun kendi ciktisindan
    # okunur (tahmin/set-farki yok — paralel kosu baskasinin finalini
    # kapamaz; main.py hata halinde bile 0 doner, o yuzden returncode yetmez).
    cikti_parcalari = []
    studio_rc = 999
    try:
        proc = subprocess.Popen(cmd, cwd=studio_dir, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while True:
            satir = proc.stdout.readline()
            if not satir and proc.poll() is not None:
                break
            if satir:
                try:
                    metin = satir.decode("utf-8", errors="replace")
                except Exception:
                    metin = ""
                cikti_parcalari.append(metin)
                print(metin, end="" if metin.endswith("\n") else "\n")
        studio_rc = proc.wait()
    except Exception as e:
        warn(f"ShortsStudio calistirma hatasi: {e}")
    finally:
        # Basarida main.py girdileri kendisi siler; basarisizlikta arta kalan
        # kopyalarimizi temizle ki sonraki gun yanlis dosyayi secmesin.
        for f in kopyalanan:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

    if studio_rc != 0:
        return False, f"ShortsStudio modal run returncode={studio_rc}"

    final_ad = _final_adi_bul("".join(cikti_parcalari))
    if not final_ad or not os.path.exists(os.path.join(desktop, final_ad)):
        return False, ("ShortsStudio ciktisinda gecerli final dosya adi yok "
                       "(render basarisiz olabilir; cikti yukarida).")

    return True, final_ad


def main():
    parser = argparse.ArgumentParser(description="VideoForge Cok Gunlu Isletici - plani 3 adimli zincirle sirali islet")
    parser.add_argument("--basla", type=int, default=1, help="Kacinci gunden baslasin (varsayilan 1)")
    parser.add_argument("--evet", action="store_true", help="Onay sormadan basla")
    parser.add_argument("--studio-atla", action="store_true", help="3. adimi (ShortsStudio montaji) atla, sadece VideoForge")
    parser.add_argument("--sadece-studio", type=int, default=0, help="SADECE 3. adim: verilen gunun Gun klasorunu montajla (VideoForge atlanir, DB'ye bakilmaz). Ornek: --sadece-studio 1 --chn 2")
    parser.add_argument("--chn", default=None, help="--sadece-studio ile kullanilir: hedef kanal no (yoksa plandan alinir)")
    args = parser.parse_args()

    if not os.path.exists(PLAN_FILE):
        err(f"Plan bulunamadi: {PLAN_FILE}")
        print("Once sunu calistir:  python kesif.py --gun 10   (10 gunluk plan icin)")
        return

    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        plan = json.load(f)

    chn = str(args.chn or plan.get("chn", "1"))

    # Kurtarma modu: VideoForge ciktisi hazir ama finali olmayan gunun montaji.
    if args.sadece_studio:
        if str(chn) not in CHN_STUDIO_NO:
            err(f"Kanal {chn} icin ShortsStudio eslesmesi yok.")
            return
        kilit_ok, kilit_msg = kilit_al()
        if not kilit_ok:
            err(kilit_msg)
            return
        try:
            print(f" [Adim 3/3] ShortsStudio montaji (Gun {args.sadece_studio}, kanal {chn})...")
            studio_ok, studio_bilgi = studio_islet(args.sadece_studio, chn, plan_toplam(plan))
        finally:
            kilit_birak()
        if studio_ok:
            ok(f"✅ Gun {args.sadece_studio} final hazir: {studio_bilgi}")
        else:
            err(f"❌ Montaj olmadi: {studio_bilgi}")
        return
    script = CHN_SCRIPT.get(chn)
    if not script:
        err(f"Kanal {chn} icin bot eslesmesi yok.")
        return
    if not os.path.exists(os.path.join(BASE_DIR, script)):
        err(f"Bot scripti bulunamadi: {script}")
        return

    videolar = sorted(plan.get("videolar", []), key=lambda v: v.get("gun", 99))
    toplam = plan_toplam(plan, len(videolar))
    gun_sayisi = plan.get("gun_sayisi") or toplam
    kanal_ad = plan.get("kanal_ad", f"Kanal {chn}")

    init_db()
    # Daha once islenmisler atlanir (kaldigin yerden devam bedava gelir)
    kuyruk = []
    atlanan = 0
    for v in videolar:
        if v.get("gun", 1) < args.basla:
            continue
        if link_kayitlimi(v["link"]):
            print(f"⏭️ Gun {v['gun']} atlandi (daha once islenmis): {v.get('baslik', '?')[:50]}")
            atlanan += 1
            continue
        kuyruk.append(v)

    if not kuyruk:
        ok("Islenecek video kalmadi (hepsi islenmis ya da baslangic gununden once).")
        return

    studio_var = studio_mevcut(studio_dir_bul()) and not args.studio_atla
    adimlar = "Kesif ✓ → VideoForge → ShortsStudio" if studio_var else "Kesif ✓ → VideoForge (ShortsStudio ATLANDI)"
    header(f"📅 VIDEOFORGE {gun_sayisi} GUNLUK ZINCIR",
           f"{kanal_ad} | {len(kuyruk)} video sirayla islenecek (gun {kuyruk[0]['gun']}-{kuyruk[-1]['gun']}/{toplam}) | {adimlar}")
    for v in kuyruk:
        print(f"  📅 {v['gun']}. Gun ({v.get('gun_adi', '')}) [Skor {v.get('skor', '?')}] {v.get('baslik', '?')[:55]}")
    if atlanan:
        print(f"  ⏭️ {atlanan} video daha once islendigi icin atlanacak.")
    print(f"\n⏳ Tahmini sure: ~{len(kuyruk) * 15} dk (video basina VideoForge ~5-15 dk + ShortsStudio ~3-8 dk, sirayla).")
    print("   VideoForge ciktilari masaustunde kendi GunN klasorune, finaller Masaustu/final_*.mp4 olarak yazilir.\n")

    if not args.evet:
        cevap = input("Baslasin mi? (e/h): ").strip().lower()
        if cevap not in ("e", "evet", "y", "yes", ""):
            print("Iptal edildi.")
            return

    # Kilit: 2 bat ust uste acilirsa girdiler/finaller karisir (yasanmis vaka).
    kilit_ok, kilit_msg = kilit_al()
    if not kilit_ok:
        err(kilit_msg)
        return

    basarili, basarisiz = [], []
    studio_eksik = []  # VideoForge OK ama ShortsStudio basarisiz
    final_haritasi = {}  # gun -> final dosya adi
    kesildi = False
    for i, v in enumerate(kuyruk, 1):
        gun = v["gun"]
        if iptal_edildi():
            print("\n⛔ Durdurma istegi alindi - zincir durduruluyor (islenmis gunler korunur).")
            kesildi = True
            break
        print("\n" + "=" * 60)
        print(f" 🎬 GUN {gun}/{toplam} ({i}/{len(kuyruk)} bu kosuda) — {v.get('gun_adi', '')}")
        print(f"    {v.get('baslik', '?')[:70]}")
        print(f"    {v['link']}")
        print("=" * 60)
        print(f" [Adim 2/3] VideoForge temizlik + SEO + ses...")
        cmd = [sys.executable, "-m", "modal", "run", script,
               "--link", v["link"], "--gun", str(gun), "--gun-toplam", str(toplam)]
        try:
            r = subprocess.run(cmd, cwd=BASE_DIR)
            ok_code = (r.returncode == 0 and link_kayitlimi(v["link"]))
        except Exception as e:
            warn(f"Calistirma hatasi: {e}")
            ok_code = False
        if not ok_code:
            err(f"❌ Gun {gun} basarisiz (atlandi, DB'ye islenmedi). Sonraki videoya geciliyor...")
            basarisiz.append(gun)
            continue
        ok(f"✅ Gun {gun} VideoForge tamamlandi.")
        if args.studio_atla:
            basarili.append(gun)
            continue
        print(f" [Adim 3/3] ShortsStudio montaj...")
        studio_ok, studio_bilgi = studio_islet(gun, chn, toplam)
        if studio_ok:
            ok(f"✅ Gun {gun} final hazir: {studio_bilgi}")
            basarili.append(gun)
            final_haritasi[str(gun)] = studio_bilgi
        else:
            err(f"⚠️ Gun {gun} VideoForge OK ama ShortsStudio olmadi: {studio_bilgi}")
            err(f"   (Kurtarma: python haftalik_islet.py --sadece-studio {gun} --chn {chn})")
            studio_eksik.append(gun)

    print("\n" + "=" * 60)
    print(f" 📅 {gun_sayisi} GUNLUK KOSU OZETI (3 ADIMLI ZINCIR)")
    print("=" * 60)
    desktop = _desktop()
    print(f"  ✅ Tam final hazir gunler: {basarili if basarili else 'yok'}")
    if studio_eksik:
        print(f"  ⚠️ VideoForge OK / Studio eksik gunler: {studio_eksik} (Gun klasoru hazir, montaj tekrar denenebilir)")
    if basarisiz:
        print(f"  ❌ Basarisiz gunler: {basarisiz} (linkler islenmedi sayilir, tekrar kosuda otomatik denenir)")
    for g in sorted(final_haritasi, key=int):
        print(f"     Gun {g} → {final_haritasi[g]}")
    print(f"  📁 Gun klasorleri + finaller masaustunde: {desktop}")
    try:
        sonuc_file = sonuc_dosyasi(chn)
        with open(sonuc_file, "w", encoding="utf-8") as f:
            json.dump({"chn": chn, "kanal_ad": kanal_ad, "tarih": time.strftime("%Y-%m-%d %H:%M"),
                       "tam_final": basarili, "studio_eksik": studio_eksik,
                       "basarisiz": basarisiz, "finaller": final_haritasi},
                      f, indent=2, ensure_ascii=False)
        print(f"  💾 Sonuc haritasi: {sonuc_file}")
    except Exception as e:
        warn(f"Sonuc dosyasi yazilamadi: {e}")
    kilit_birak()
    if kesildi:
        footer_fail("Kullanici durdurdu - kalan gunler sonraki kosuda otomatik devam eder")
    elif basarisiz or studio_eksik:
        footer_fail("Kosu bitti, eksik gunler var")
    else:
        footer_done(f"Plan tamamlandi! {len(basarili)} gun final hazir 🎉")


if __name__ == "__main__":
    main()
