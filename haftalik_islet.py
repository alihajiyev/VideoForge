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
import subprocess
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import link_kayitlimi, init_db
from functions.ui import header, footer_done, footer_fail, info, ok, warn, err
from functions.tts_kontrol import SISTEMIK_ISARET, yerel_on_kontrol

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


def tts_on_kontrol():
    """Zinciri baslatmadan once ElevenLabs abonelik/odeme durumunu kontrol et.

    Gercek vaka (2026-10-04): abonelik 'past_due' iken 7 gunun her birinde TTS
    401 payment_issue dondu; kod bunu uyari sayip devam ettigi icin gun basina
    $0.28-$0.44 GPU harcandi ve hicbir gunun MP3'u cikmadi (ShortsStudio hep
    atlandi). Artik zincir GPU'ya/indirmeye hic girmeden net mesajla durur.
    Yalnizca KESIN odeme sorununda engellenir; ag hatasi zinciri bloklamaz.
    Donus: (True, '') ya da (False, 'net Turkce mesaj').
    """
    return yerel_on_kontrol()


def sistemik_hata_mi(cikti):
    """Bot ciktisinda tum gunlerde tekrarlanacak sistemik hata isareti var mi?

    VideoForge bulut katmani (functions/tts_kontrol.py SISTEMIK_ISARET) TTS/
    abonelik hatasinda bu isareti hata metnine koyar. Isaret gorulurse kalan
    gunler bu hata yuzunden bosuna kosardi; zincir durdurulur.
    """
    return SISTEMIK_ISARET in (cikti or "")


def sistemik_hata_ozeti(cikti, sinir=600):
    """Sistemik hata satirini cikti metninden cek (ozet/kayit icin)."""
    for satir in (cikti or "").splitlines():
        if SISTEMIK_ISARET in satir:
            return satir.strip()[:sinir]
    return "ElevenLabs ses (TTS) hatasi - tum gunlerde tekrarlanir (abonelik/odeme kontrol et)."


def yeniden_gunleri_ayristir(deger):
    """'--yeniden-gun 1,2,3' degerini gun kumesine cevir (gecersiz parcalar atilir)."""
    kume = set()
    for parca in str(deger or "").split(","):
        parca = parca.strip()
        if parca.isdigit():
            kume.add(int(parca))
    return kume


def link_kaydi_sil(link):
    """DB'deki 'islenmis' kaydini sil (--yeniden-gun icin).

    Kanal scriptleri de ayni kayda bakip "Bu link daha once islenmis!" diyerek
    durur; bir gunu yeniden uretmek icin kaydin kaldirilmasi SART.
    """
    try:
        import sqlite3
        from constants import DB_PATH, _video_id_cek, init_db
        init_db()
        vid = _video_id_cek(link)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM videos WHERE link = ? OR link LIKE ?", (vid, f"%{vid}%"))
            conn.commit()
        return True
    except Exception as e:
        warn(f"DB kaydi silinemedi ({link}): {e}")
        return False

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

    TEK AKIS (kopyalama YOK): VideoForge ciktilari GunN klasorunde kalir; tam
    yollari ShortsStudio'ya ortam degiskeniyle verilir. Boylece eski davranistaki
    "en yeni dosyayi bul" mantigi ve ShortsStudio kokunde biriken bayat dosyalar
    sorunu tamamen ortadan kalkar (eskiden bayat dosya yuzunden kosu, GPU
    harcandiktan SONRA duruyordu — en pahali hata turu).

    Donus: (True, final_dosya_adi) ya da (False, hata_mesaji).
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

    studio_no = CHN_STUDIO_NO.get(str(chn), "1")
    info(f"🎬 ShortsStudio montaji basliyor (Gun {gun}, kanal no {studio_no})...")
    info(f"   Video: {os.path.basename(video_path)}")
    info(f"   Ses:   {os.path.basename(audio_path)}")

    env = dict(os.environ)
    env["CHANNEL_NUM"] = studio_no
    # ShortsStudio emoji basar (✅/›); pipe'li stdout cp1254'e dusup
    # UnicodeEncodeError veriyor. UTF-8 moda zorla (ShortsStudio koduna dokunmadan).
    env["PYTHONUTF8"] = "1"
    # TEK AKIS: kopya yerine acik yollar. GunN klasoru tek kaynak olarak kalir.
    env["VIDEOFORGE_STUDIO_VIDEO"] = os.path.abspath(video_path)
    env["VIDEOFORGE_STUDIO_AUDIO"] = os.path.abspath(audio_path)
    env["VIDEOFORGE_STUDIO_SEO"] = os.path.abspath(seo_path)
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
    parser.add_argument("--yeniden-gun", default=None, help="DB'de islenmis gorunse bile bu gunleri YENIDEN uret (or. --yeniden-gun 1,2,3). MP3'suz/eksik kalan gunleri duzeltmek icin: kayit silinir, gun bastan uretilir.")
    args = parser.parse_args()

    if not os.path.exists(PLAN_FILE):
        err(f"Plan bulunamadi: {PLAN_FILE}")
        print("Once sunu calistir:  python kesif.py --gun 10   (10 gunluk plan icin)")
        sys.exit(1)

    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        plan = json.load(f)

    chn = str(args.chn or plan.get("chn", "1"))

    # Kurtarma modu: VideoForge ciktisi hazir ama finali olmayan gunun montaji.
    if args.sadece_studio:
        if str(chn) not in CHN_STUDIO_NO:
            err(f"Kanal {chn} icin ShortsStudio eslesmesi yok.")
            sys.exit(1)
        kilit_ok, kilit_msg = kilit_al()
        if not kilit_ok:
            err(kilit_msg)
            sys.exit(1)
        try:
            print(f" [Adim 3/3] ShortsStudio montaji (Gun {args.sadece_studio}, kanal {chn})...")
            studio_ok, studio_bilgi = studio_islet(args.sadece_studio, chn, plan_toplam(plan))
        finally:
            kilit_birak()
        if studio_ok:
            ok(f"✅ Gun {args.sadece_studio} final hazir: {studio_bilgi}")
        else:
            err(f"❌ Montaj olmadi: {studio_bilgi}")
            sys.exit(1)
        return
    script = CHN_SCRIPT.get(chn)
    if not script:
        err(f"Kanal {chn} icin bot eslesmesi yok.")
        sys.exit(1)
    if not os.path.exists(os.path.join(BASE_DIR, script)):
        err(f"Bot scripti bulunamadi: {script}")
        sys.exit(1)

    videolar = sorted(plan.get("videolar", []), key=lambda v: v.get("gun", 99))
    toplam = plan_toplam(plan, len(videolar))
    gun_sayisi = plan.get("gun_sayisi") or toplam
    kanal_ad = plan.get("kanal_ad", f"Kanal {chn}")

    init_db()
    # --yeniden-gun: bu gunler DB'de islenmis olsa bile kaydi silinip bastan uretilir
    yeniden = yeniden_gunleri_ayristir(args.yeniden_gun)
    # Daha once islenmisler atlanir (kaldigin yerden devam bedava gelir)
    kuyruk = []
    atlanan = 0
    for v in videolar:
        if v.get("gun", 1) < args.basla:
            continue
        if v.get("gun") in yeniden:
            link_kaydi_sil(v["link"])
            print(f"🔁 Gun {v['gun']} --yeniden-gun ile YENIDEN uretilecek (DB kaydi silindi).")
            kuyruk.append(v)
            continue
        if link_kayitlimi(v["link"]):
            print(f"⏭️ Gun {v['gun']} atlandi (daha once islenmis): {v.get('baslik', '?')[:50]}")
            atlanan += 1
            continue
        kuyruk.append(v)

    if not kuyruk:
        ok("Islenecek video kalmadi (hepsi islenmis ya da baslangic gununden once).")
        return

    # TTS ON KONTROLU (ucretsiz): abonelik odemesi dustuyse 7 gunu bosuna kosma.
    # Yalnizca KESIN odeme sorununda durur; ag/ucnokta hatasi zinciri bloklamaz.
    tts_ok, tts_mesaj = tts_on_kontrol()
    if not tts_ok:
        err("🛑 ElevenLabs odeme sorunu: haftalik zincir BASLATILMADI (bosuna indirme/transkript/GPU yapilmadi).")
        print(f"   {tts_mesaj}")
        footer_fail("ElevenLabs abonelik/odeme sorunu - zincir durduruldu")
        sys.exit(1)  # uygulama bunu 'tamamlandi' sanmasin

    # KAPASITE UYARISI: ucretsiz/az kotali planda kalan karakter bu kosuya yetiyor mu?
    # (Video basina ~550 karakter; kota dolarsa zincir o gun temiz durur, GPU harcanmaz.)
    try:
        from constants import ELEVENLABS_API_KEY
        from functions.tts_kontrol import abonelik_durumu, kalan_karakter, VIDEO_BASINA_KARAKTER
        _abonelik = abonelik_durumu(ELEVENLABS_API_KEY)
        _kalan = kalan_karakter(_abonelik)
        _tahmin = len(kuyruk) * VIDEO_BASINA_KARAKTER
        if _kalan is not None:
            if _kalan < _tahmin:
                warn(f"🎙️ ElevenLabs kotasi: kalan {_kalan} karakter, bu kosu ~{_tahmin} gerektirir "
                     f"({len(kuyruk)} video x ~{VIDEO_BASINA_KARAKTER}). Kota dolarsa zincir o gun temiz durur "
                     f"(GPU harcanmaz); plani kisalt ya da aylik sifirlanmayi bekle.")
            else:
                print(f"🎙️ ElevenLabs kotasi: kalan {_kalan} karakter, bu kosu ~{_tahmin} "
                      f"({len(kuyruk)} video) -> YETERLI.")
    except Exception:
        pass

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
        sys.exit(1)

    basarili, basarisiz = [], []
    studio_eksik = []  # VideoForge OK ama ShortsStudio basarisiz
    final_haritasi = {}  # gun -> final dosya adi
    kesildi = False
    sistemik_hata = ""  # tum gunlerde tekrarlanan hata (or. TTS/abonelik) -> zincir durur
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
        gun_cikti = []
        try:
            # Ciktiyi CANLI goster + topla: TTS/abonelik gibi tum gunlerde
            # tekrarlanacak hata varsa kalan gunleri bosuna kosmayalim.
            r_env = dict(os.environ)
            r_env["PYTHONUTF8"] = "1"  # emoji basan bot ciktisi cp1254'te cokmesin
            proc = subprocess.Popen(cmd, cwd=BASE_DIR, env=r_env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            while True:
                satir = proc.stdout.readline()
                if not satir and proc.poll() is not None:
                    break
                if satir:
                    metin = satir.decode("utf-8", errors="replace")
                    gun_cikti.append(metin)
                    print(metin, end="" if metin.endswith("\n") else "\n")
            ok_code = (proc.wait() == 0 and link_kayitlimi(v["link"]))
        except Exception as e:
            warn(f"Calistirma hatasi: {e}")
            ok_code = False
        if sistemik_hata_mi("".join(gun_cikti)):
            # Or. ElevenLabs odeme/abonelik hatasi: her gun ayni sekilde patlar.
            # Kalan gunleri kosmak para/zaman kaybi olur; kilit birakilir, kalan
            # gunler sonraki kosuda otomatik devam eder (link kaydedilmedi).
            sistemik_hata = sistemik_hata_ozeti("".join(gun_cikti))
            basarisiz.append(gun)
            print("\n" + "🛑" * 3)
            err("HAFTALIK ZINCIR DURDURULDU: sistemik ses (TTS) hatasi - kalan gunler de ayni hatayla patlardi.")
            err(f"   {sistemik_hata}")
            err(f"   Sorunu cozup ayni komutu tekrar calistir; Gun {gun} ve sonrasi kaldigi yerden devam eder.")
            break
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
    if sistemik_hata:
        print(f"  🛑 Zincir sistemik hata yuzunden erken durduruldu: {sistemik_hata}")
        print("     (Ses/abonelik sorunu cozulunce ayni komutu tekrar calistir; kalan gunler otomatik devam eder.)")
    print(f"  📁 Gun klasorleri + finaller masaustunde: {desktop}")
    try:
        sonuc_file = sonuc_dosyasi(chn)
        with open(sonuc_file, "w", encoding="utf-8") as f:
            json.dump({"chn": chn, "kanal_ad": kanal_ad, "tarih": time.strftime("%Y-%m-%d %H:%M"),
                       "tam_final": basarili, "studio_eksik": studio_eksik,
                       "basarisiz": basarisiz, "finaller": final_haritasi,
                       "sistemik_hata": sistemik_hata},
                      f, indent=2, ensure_ascii=False)
        print(f"  💾 Sonuc haritasi: {sonuc_file}")
    except Exception as e:
        warn(f"Sonuc dosyasi yazilamadi: {e}")
    kilit_birak()
    if kesildi:
        footer_fail("Kullanici durdurdu - kalan gunler sonraki kosuda otomatik devam eder")
    elif sistemik_hata:
        footer_fail("Sistemik ses hatasi - zincir durduruldu (sorunu cozunce kaldigi yerden devam eder)")
        sys.exit(1)  # sessiz 'tamamlandi' yok: ciktilar eksik
    elif basarisiz or studio_eksik:
        footer_fail("Kosu bitti, eksik gunler var")
        sys.exit(1)
    else:
        footer_done(f"Plan tamamlandi! {len(basarili)} gun final hazir 🎉")


if __name__ == "__main__":
    main()
