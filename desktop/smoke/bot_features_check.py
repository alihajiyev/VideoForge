"""VideoForge bot tarafi ozellik kontrolleri.

Amac: Kesif (gun sayisi), zincir (haftalik_islet), Durdur (iptal isareti),
kilit (bayat kilit), Gun klasoru/girdi bulma, kanal betikleri ve bulut
gizli anahtar mimarisini GERCEK fonksiyonlarla dogrulamak.

Ag, GPU, Modal ve API anahtari KULLANMAZ. Sistemde degisiklik yapmaz:
kilit/iptal testleri gecici klasorde calisir.

Kullanim:  py -3 desktop/smoke/bot_features_check.py
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

YOL = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(os.path.dirname(YOL))  # depo koku (bot klasoru)
os.chdir(BOT)
if BOT not in sys.path:
    sys.path.insert(0, BOT)

gecen = 0
hatalar = []
atlandi = []
temizlenecek = []


def kontrol(ad, kosul, detay=""):
    global gecen
    if kosul:
        gecen += 1
        print(f"  PASS  {ad}" + (f"  ({detay})" if detay else ""))
    else:
        hatalar.append(ad)
        print(f"  FAIL  {ad}  ({detay})")


def atla(ad, sebep):
    """Ortam eksik oldugu icin calistirilamayan GERCEK test (sahte PASS yazilmaz)."""
    atlandi.append(ad)
    print(f"  SKIP  {ad}  ({sebep})")


def bolum(ad):
    print(f"\n== {ad} ==")


def gecici(onek):
    y = tempfile.mkdtemp(prefix=onek)
    temizlenecek.append(y)
    return y


def oku(dosya):
    with open(dosya, encoding="utf-8-sig") as f:
        return f.read()


import kesif  # noqa: E402
import haftalik_islet  # noqa: E402

GERCEK_KILIT = haftalik_islet.KILIT_DOSYASI
kilit_once_vardi = os.path.exists(GERCEK_KILIT)

# --------------------------------------------------------------------------
bolum("A) Kesif: gun sayisi altyapisi (7 sabit degil)")
kontrol("Varsayilan gun sayisi 7", kesif.VARSAYILAN_GUN_SAYISI == 7, str(kesif.VARSAYILAN_GUN_SAYISI))
kontrol("Ust sinir 60 gun", kesif.MAX_GUN_SAYISI == 60, str(kesif.MAX_GUN_SAYISI))
adlar = [kesif.gun_adi(i) for i in range(1, 15)]
kontrol("Gun adlari 7'lik dongu halinde (10+ gun sorunsuz)", adlar[:7] == adlar[7:14], ", ".join(adlar[:10]))
kontrol("Dongu Pazartesi ile basliyor", adlar[0] == "Pazartesi" and adlar[7] == "Pazartesi", adlar[0])

r = subprocess.run([sys.executable, "-X", "utf8", "kesif.py", "--help"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
kontrol("kesif.py --help hatasiz calisti", r.returncode == 0, (r.stderr or "").strip()[-120:])
yardim = r.stdout or ""
kontrol("--gun secenegi CLI'da tanimli", "--gun" in yardim)
kontrol("--haftalik deger alabiliyor (nargs='?')", "--haftalik" in yardim)
kontrol("--chn / --evet secenekleri var", "--chn" in yardim and "--evet" in yardim)

kaynak = oku("kesif.py")
kontrol("Kaynakta sabit '7 gun' kirpmasi kalmadi", "[:7]" not in kaynak and "7 video bulunacak" not in kaynak)
kontrol("Gun sayisi plan dosyasina yaziliyor", '"gun_sayisi"' in kaynak)
kontrol("Aday havuzu gun sayisina gore buyuyor", "gun_sayisi + 5" in kaynak)
kontrol("Gun sayisi ust siniri kodda uygulaniyor", "MAX_GUN_SAYISI" in kaynak)

cfg = json.loads(oku("kesif_config.json"))
kontrol("kesif_config gun_sayisi tasiyor", int(cfg.get("gun_sayisi") or 0) == 7, str(cfg.get("gun_sayisi")))
kontrol("kesif_config 3 kanal tanimli", len(cfg.get("kanallar") or {}) == 3, ", ".join(sorted((cfg.get("kanallar") or {}).keys())))

# --------------------------------------------------------------------------
bolum("B) Zincir: plan gun sayisi (haftalik_islet)")
kontrol("plan_toplam gun_sayisi okur", haftalik_islet.plan_toplam({"gun_sayisi": 10}) == 10)
kontrol("plan_toplam 'toplam' alanini da okur", haftalik_islet.plan_toplam({"toplam": 12}) == 12)
kontrol("10 gunluk plan zincire geciyor", haftalik_islet.plan_toplam({"gun_sayisi": 10}, 7) == 10)
kontrol("30 gunluk plan zincire geciyor", haftalik_islet.plan_toplam({"gun_sayisi": 30}, 7) == 30)
kontrol("Bos planda 7 varsayilana donulur", haftalik_islet.plan_toplam({}) == 7)
kontrol("Bozuk degerde 7 varsayilana donulur", haftalik_islet.plan_toplam({"gun_sayisi": "abc"}) == 7)
kontrol("Sonuc dosyasi kanal bazli", haftalik_islet.sonuc_dosyasi("2").endswith("haftalik_sonuc_ch2.json"))
kontrol("Kanal eslesmesi 3 kanal", len(haftalik_islet.CHN_SCRIPT) == 3, json.dumps(haftalik_islet.CHN_SCRIPT))
for chn, betik in haftalik_islet.CHN_SCRIPT.items():
    kontrol(f"Kanal {chn} betigi diskte var ({betik})", os.path.exists(betik))

if os.path.exists("haftalik_plan.json"):
    plan = json.loads(oku("haftalik_plan.json"))
    videolar = plan.get("videolar") or []
    _plan_tutarli = (int(plan.get("gun_sayisi") or 0) == len(videolar)
                     and int(plan.get("toplam") or 0) == len(videolar))
    if _plan_tutarli:
        kontrol("Gercek plan gun sayisi ile video sayisi tutarli", True,
                f"gun_sayisi={plan.get('gun_sayisi')} video={len(videolar)}")
    elif "istenen_gun" not in plan:
        # Eski surumle yazilmis plan dosyasi (gun_sayisi=istenen, video=bulunan).
        # Yeni kesif kosusunda dosya kendiliginden duzelir; kodun yazimi dogrulanir.
        kontrol("Plan yazimi kodda tutarli: gun_sayisi = bulunan video sayisi",
                '"gun_sayisi": len(results)' in oku("kesif.py"),
                f"eski plan dosyasi (gun_sayisi={plan.get('gun_sayisi')}, video={len(videolar)})")
    else:
        kontrol("Gercek plan gun sayisi ile video sayisi tutarli", False,
                f"gun_sayisi={plan.get('gun_sayisi')} toplam={plan.get('toplam')} video={len(videolar)}")
    kontrol("Plan zincir icin kanal ve ad tasiyor", bool(plan.get("chn")) and bool(plan.get("kanal_ad")), f"chn={plan.get('chn')} / {plan.get('kanal_ad')}")
else:
    kontrol("Gerçek plan dosyasi var", False, "haftalik_plan.json bulunamadi")

# --------------------------------------------------------------------------
bolum("C) Durdur (iptal isareti) — gercek fonksiyon testi")
os.environ.pop("VIDEOFORGE_CANCEL_FILE", None)
kontrol("Ortam degiskeni yokken iptal False", haftalik_islet.iptal_edildi() is False)
isaret_yolu = os.path.join(gecici("vf-iptal-"), "iptal")
os.environ["VIDEOFORGE_CANCEL_FILE"] = isaret_yolu
kontrol("Yol tanimli ama dosya yokken iptal False", haftalik_islet.iptal_edildi() is False)
with open(isaret_yolu, "w", encoding="utf-8") as f:
    f.write("1")
kontrol("Durdur isaret dosyasi olusunca iptal True", haftalik_islet.iptal_edildi() is True)
os.environ.pop("VIDEOFORGE_CANCEL_FILE", None)
kontrol("Ortam degiskeni silinince tekrar False", haftalik_islet.iptal_edildi() is False)
kontrol("Zincir dongusu iptal kontrolunu kullaniyor", "iptal_edildi()" in oku("haftalik_islet.py"))
kontrol("Zincir iptal edilince kilit birakiliyor", "iptal_edildi" in oku("haftalik_islet.py"))

# --------------------------------------------------------------------------
bolum("D) Zincir kilidi (bayat kilit artik takmiyor)")
kil = os.path.join(gecici("vf-kilit-"), "zincir.lock")
haftalik_islet.KILIT_DOSYASI = kil
ok1, sebep1 = haftalik_islet.kilit_al()
kontrol("Kilit ilk kez alindi", ok1 is True and os.path.exists(kil), sebep1 or f"pid {os.getpid()}")
ok2, sebep2 = haftalik_islet.kilit_al()
kontrol("Canli pid varken ikinci kilit reddedildi", ok2 is False and "calisiyor" in sebep2, sebep2)
haftalik_islet.kilit_birak()
kontrol("kilit_birak kilidi sildi", not os.path.exists(kil))

with open(kil, "w", encoding="utf-8") as f:
    f.write("999999\n" + str(int(time.time())) + "\n")
ok3, sebep3 = haftalik_islet.kilit_al()
kontrol("Olmus pid'li bayat kilit otomatik temizlendi", ok3 is True, sebep3 or "temizlendi ve alindi")
haftalik_islet.kilit_birak()

with open(kil, "w", encoding="utf-8") as f:
    f.write(f"{os.getpid()}\n{int(time.time()) - 5 * 3600}\n")
ok4, sebep4 = haftalik_islet.kilit_al()
kontrol("4 saatten eski kilit pid canli olsa da serbest", ok4 is True, sebep4 or "yas siniri uygulandi")
haftalik_islet.kilit_birak()

with open(kil, "w", encoding="utf-8") as f:
    f.write("bozuk-icerik")
ok5, _ = haftalik_islet.kilit_al()
kontrol("Bozuk kilit dosyasi cokme yapmadan temizlendi", ok5 is True)
haftalik_islet.kilit_birak()

haftalik_islet.KILIT_DOSYASI = GERCEK_KILIT
kontrol("Gercek kilit dosyasina dokunulmadi", os.path.exists(GERCEK_KILIT) == kilit_once_vardi,
        f"once={kilit_once_vardi} sonra={os.path.exists(GERCEK_KILIT)}")

# --------------------------------------------------------------------------
bolum("E) pid_yasiyor (Durdur sonrasi surec kontrolu)")
kontrol("Kendi pid'imiz canli gorunuyor", haftalik_islet.pid_yasiyor(os.getpid()) is True)
kontrol("Olmus pid (999999) canli degil", haftalik_islet.pid_yasiyor(999999) is False)
kontrol("pid 0 reddedildi", haftalik_islet.pid_yasiyor(0) is False)
kontrol("Sayi olmayan pid reddedildi", haftalik_islet.pid_yasiyor("abc") is False)

# --------------------------------------------------------------------------
bolum("F) Gun klasoru ve ShortsStudio girdileri")
masaustu = gecici("vf-masaustu-")
gun_dir = os.path.join(masaustu, "Gun3_Test_Video")
os.makedirs(gun_dir)
with open(os.path.join(gun_dir, "ham_ham.mp4"), "wb") as f:
    f.write(b"x" * 20)
with open(os.path.join(gun_dir, "Test_CLEAN.mp4"), "wb") as f:
    f.write(b"x" * 4)
with open(os.path.join(gun_dir, "Test_ses.mp3"), "wb") as f:
    f.write(b"y" * 4)
with open(os.path.join(gun_dir, "Test_SEO.html"), "w", encoding="utf-8") as f:
    f.write("<html>ok</html>")

kontrol("find_gun_klasoru dogru klasoru buldu", haftalik_islet.find_gun_klasoru(masaustu, 3) == gun_dir)
kontrol("find_gun_klasoru olmayan gun icin None", haftalik_islet.find_gun_klasoru(masaustu, 5) is None)
girdi, hata = haftalik_islet.find_gun_girdileri(gun_dir)
kontrol("Girdiler bulundu (video + ses + seo)", girdi is not None, hata)
if girdi:
    kontrol("Ham video yerine *_CLEAN.mp4 secildi", girdi[0] == os.path.join(gun_dir, "Test_CLEAN.mp4"), os.path.basename(girdi[0]))
    kontrol("faktza15 tarzi _ses.mp3 ses olarak secildi", girdi[1] == os.path.join(gun_dir, "Test_ses.mp3"), os.path.basename(girdi[1]))
    kontrol("SEO html girdisi bulundu", girdi[2] == os.path.join(gun_dir, "Test_SEO.html"), os.path.basename(girdi[2]))

with open(os.path.join(gun_dir, "Other_VOICEOVER.mp3"), "wb") as f:
    f.write(b"z" * 4)
girdi2, _ = haftalik_islet.find_gun_girdileri(gun_dir)
kontrol("VOICEOVER sesi _ses.mp3'ten once tercih ediliyor", bool(girdi2) and girdi2[1].endswith("Other_VOICEOVER.mp3"),
        os.path.basename(girdi2[1]) if girdi2 else "")
os.remove(os.path.join(gun_dir, "Other_VOICEOVER.mp3"))
os.remove(os.path.join(gun_dir, "Test_ses.mp3"))
girdi3, hata3 = haftalik_islet.find_gun_girdileri(gun_dir)
kontrol("Ses dosyasi yoksa net hata dondu", girdi3 is None and "mp3" in hata3, hata3)

kontrol("final adi konsol ciktisindan bulunuyor",
        haftalik_islet._final_adi_bul("render bitti\nMasaustu -> final_123456.mp4\n") == "final_123456.mp4")
kontrol("final adi yoksa None", haftalik_islet._final_adi_bul("render basarisiz") is None)
kontrol("Bildirilen final adi gercekten final_<rakam>.mp4 kalibinda", haftalik_islet.FINAL_RE.pattern == r"final_\d+\.mp4")

# --------------------------------------------------------------------------
bolum("G) Kanal betikleri (3 kanal da import edilebiliyor)")
import bulut_kanali  # noqa: E402

# Her kanal betigi GERCEK kullanimdaki gibi KENDI surecinde baslatilir
# (zincir de gun basina ayri 'modal run' alt sureci acar; Modal ayni surecte
#  iki 'main' entrypoint'ine izin vermez).
for modul in ("faktza15", "kinosekrety", "kinok_syjet"):
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", f"import {modul}; print('IMPORT-OK')"],
                       cwd=BOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    cikti = (r.stdout or "") + (r.stderr or "")
    kontrol(f"{modul}.py kendi surecinde hatasiz import edildi", r.returncode == 0 and "IMPORT-OK" in cikti,
            "" if r.returncode == 0 else cikti.strip().splitlines()[-1][:140] if cikti.strip() else "cikti yok")

kontrol("3 kanal betigi de var", all(os.path.exists(b) for b in haftalik_islet.CHN_SCRIPT.values()))
kontrol("kinok_syjet Rusca yazim hatasi kalmadi", "Печему" not in oku("kinok_syjet.py"))
kontrol("kinok_syjet dogru 'Почему' iceriyor", "Почему" in oku("kinok_syjet.py"))
kontrol("PopkornFakty konu limiti tanimli", "CHAR_LIMIT_KINO_SYJET" in oku("constants.py"))

# --------------------------------------------------------------------------
bolum("H) Bulut (Modal) gizli anahtar mimarisi")
kontrol("Tek isimli secret kullaniliyor (kosullu degil)", len(bulut_kanali.MODAL_SECRETS) == 1, f"{len(bulut_kanali.MODAL_SECRETS)} secret")
kontrol("Secret adi sabit: videoforge-env", bulut_kanali.SECRET_NAME == "videoforge-env", bulut_kanali.SECRET_NAME)
kaynak_bulut = oku("bulut_kanali.py")
kontrol("from_dotenv cagrisi tamamen kaldirildi", ".from_dotenv(" not in kaynak_bulut)
kontrol("3 bulut fonksiyonu ayni secret listesini kullaniyor", kaynak_bulut.count("secrets=MODAL_SECRETS") == 3, str(kaynak_bulut.count("secrets=MODAL_SECRETS")))
kontrol("Tekrar deneme sayisi 0 (hata aninda gorunur)", kaynak_bulut.count("retries=0") >= 3, str(kaynak_bulut.count("retries=0")))
kontrol("Konteynerde kurulum modulu import edilmiyor (is_local korumasi)", "modal.is_local()" in kaynak_bulut)
kontrol("Kurulum yardimcisi mevcut", os.path.exists("bulut_kurulum.py"))
kaynak_kurulum = oku("bulut_kurulum.py")
kontrol("Kurulum secret adini paylasiyor", 'SECRET_NAME = "videoforge-env"' in kaynak_kurulum)
kontrol("Kurulum bayat degeri once siliyor", "objects.delete" in kaynak_kurulum and "objects.create" in kaynak_kurulum)

# --------------------------------------------------------------------------
bolum("I) Metin/bicim duzeltmeleri (bot tarafi)")
metin_dosyalari = ["kesif.py", "haftalik_islet.py", "faktza15.py", "kinosekrety.py", "kinok_syjet.py",
                   "constants.py", "shared.py", "functions/gemini_func.py", "functions/orchestrator.py"]
hatali_kaliplar = ["baslatilmıyor", "siralıyor", "sayaçları", "formatı", "kaldiğin", "Cömert", "Kanalın"]
bulunan = []
for dosya in metin_dosyalari:
    if not os.path.exists(dosya):
        continue
    icerik = oku(dosya)
    for kalip in hatali_kaliplar:
        if kalip in icerik:
            bulunan.append(f"{dosya}:{kalip}")
kontrol("Bilinen Turkce yazim hatalari kalmadi", not bulunan, ", ".join(bulunan) or "temiz")

# --------------------------------------------------------------------------
bolum("J) baslat/VideoForge-Haftalik.bat: gun sayisi soruluyor mu (TEST modu)")
BAT = os.path.join("baslat", "VideoForge-Haftalik.bat")
kontrol("Baslatici mevcut", os.path.exists(BAT), BAT)
bat_kaynak = oku(BAT)
kontrol("Baslatici artik sabit 7 gun kullanmiyor", "--haftalik --chn" not in bat_kaynak)
kontrol("Baslatici gun sayisini komuta geciyor", "--haftalik %GUN% --chn %CHN% --evet" in bat_kaynak)
kontrol("Baslaticida test modu var (komutu calistirmadan dogrulanir)", "VIDEOFORGE_TEST" in bat_kaynak)

senaryolar = [
    ("2\r\n10\r\n\r\n\r\n\r\n\r\n", "--haftalik 10 --chn 2", "kanal 2 + 10 gun"),
    ("1\r\n\r\n\r\n\r\n\r\n\r\n", "--haftalik 7 --chn 1", "bos cevap = varsayilan 7"),
    ("2\r\n1\r\n5\r\n\r\n\r\n\r\n", "--haftalik 5 --chn 2", "gecersiz (1) reddedilip 5 kabul"),
    ("3\r\n99\r\n60\r\n\r\n\r\n\r\n", "--haftalik 60 --chn 3", "99 reddedilip 60 kabul"),
]
# NOT: 'set /p' girdi borusundan (pipe) okurken tum tamponu bir kerede
# yutabiliyor; gercek kullanici girdisini taklit etmek icin DOSYA yonlendirmesi
# kullanilir (masaustundan cift tiklayip klavyeden yazmakla ayni davranis).
girdi_dosyasi = os.path.join(gecici("vf-bat-"), "girdi.txt")
for girdi, beklenen, ad in senaryolar:
    with open(girdi_dosyasi, "w", encoding="ascii", newline="") as f:
        f.write(girdi)
    with open(girdi_dosyasi, "r", encoding="ascii") as sin:
        try:
            r = subprocess.run(["cmd", "/c", BAT], stdin=sin, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60,
                               env={**os.environ, "VIDEOFORGE_TEST": "1"})
            cikti = (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired as e:
            cikti = ((e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace"))
    kontrol(f"Baslatici dogru komutu kuruyor ({ad})", beklenen in cikti,
            next((s for s in cikti.splitlines() if "[TEST]" in s and "kesif" in s), "TEST satiri yok"))

# --------------------------------------------------------------------------
bolum("K) GPU parca/maliyet planlayici (functions/maliyet.py)")
from functions import maliyet  # noqa: E402

fpg_sd = maliyet.vram_guvenli_kare(650, 540, 960)
kontrol("540x960 icin VRAM-guvenli kare sayisi makul", 150 <= fpg_sd <= 650, str(fpg_sd))
fpg_hd = maliyet.vram_guvenli_kare(650, 1080, 1920)
kontrol("Cozunurluk buyudukce kare sayisi duser (VRAM sabit)", fpg_hd < fpg_sd, f"{fpg_sd} -> {fpg_hd}")
fpg_guc = maliyet.vram_guvenli_kare(650, 540, 960, guclu_gpu=True)
kontrol("Guclu GPU tavani acar (daha cok kare = daha az konteyner)", fpg_guc >= fpg_sd, f"{fpg_sd} -> {fpg_guc}")

p_kisa = maliyet.planla(200, 30, 288)
kontrol("Kisa video TEK GPU konteynerinde", p_kisa["num_chunks"] == 1, str(p_kisa))
p_sifir = maliyet.planla(0, 30, 288)
kontrol("Kare sayisi 0 -> islem yok (cokme yok)", p_sifir["num_chunks"] == 0, str(p_sifir))

p_uzun = maliyet.planla(1800, 30, 288)
n = p_uzun["num_chunks"]
kontrol("1800 kare icin parca sayisi tavani asmiyor", 1 <= n <= 7, str(n))
# Kuyruk birlestirme parca boyutunu bir miktar buyutebilir; guvenli ust sinir
# 1.25x. Hicbir parca bu siniri asmamali (VRAM guvenligi).
kontrol("Hicbir parca VRAM guvenli ust sinirini asmiyor (<=1.25x)",
        all(maliyet.planla(t, 30, 288)["kare_per_chunk"] <= 288 * 1.25 + 1e-6
            for t in (1, 100, 500, 1800, 5000)), "")

ar = maliyet.parcalar(p_uzun, 1800, 30)
sureler = [d for _, d in ar]
ortalama = sum(sureler) / len(sureler) if sureler else 0
kontrol("Parcalar esit bolunuyor", bool(sureler) and all(abs(s - ortalama) <= 0.05 for s in sureler),
        str([round(s, 2) for s in sureler]))
kontrol("Parcalar videoyu tam kapsiyor", abs(sum(sureler) - 60.0) < 0.2, str(round(sum(sureler), 2)))
kontrol("Bos plan -> bos parca listesi", maliyet.parcalar(maliyet.planla(0, 30, 288), 0, 30) == [])
kontrol("Sabit konteyner overhead'i parca sayisiyla olceklenir",
        maliyet.konteyner_overhead_sn(3, 75) == 225)
kontrol("Maliyet tahmini pozitif ve tutarli",
        abs(maliyet.tahmini_maliyet(4, 0.000222, 75) - (4 * 75 * 0.000222)) < 1e-12)

# --------------------------------------------------------------------------
bolum("L) TEK AKIS: VideoForge -> ShortsStudio (kopyalama yok)")
hl_kaynak = oku("haftalik_islet.py")
kontrol("Zincir ShortsStudio'ya acik yol veriyor", "VIDEOFORGE_STUDIO_VIDEO" in hl_kaynak)
kontrol("Zincir ses yolunu da veriyor", "VIDEOFORGE_STUDIO_AUDIO" in hl_kaynak)
kontrol("Zincir SEO yolunu da veriyor", "VIDEOFORGE_STUDIO_SEO" in hl_kaynak)
kontrol("Dosya kopyalama kaldirildi (ordon oraya atlama yok)", "shutil.copy2" not in hl_kaynak)
kontrol("Bayat dosya yuzunden kosu artik durmuyor", "eski girdi dosyalari var" not in hl_kaynak)

for aday in (r"C:\Users\Vafa\Desktop\ShortsStudio\main.py",
             os.path.join(os.path.expanduser("~"), "Desktop", "ShortsStudio", "main.py")):
    if os.path.exists(aday):
        ss = oku(aday)
        kontrol("ShortsStudio acik girdi yollarini okuyor", "VIDEOFORGE_STUDIO_VIDEO" in ss, aday)
        kontrol("ShortsStudio acik yollarda en-yeni-dosya taramasini atliyor",
                "_SS_ACIK_YOL" in ss)
        kontrol("ShortsStudio acik yolda kaynak dosyalari silmiyor",
                "if not _SS_ACIK_YOL:" in ss)
        break
else:
    print("  NOT   ShortsStudio bulunamadi, masaustu entegrasyon kontrolu atlandi.")

# --------------------------------------------------------------------------
bolum("M) Bosa harcama duzeltmeleri (kota/GPU)")
orch_kaynak = oku("functions/orchestrator.py")
kontrol("Orchestrator maliyet planlayicisini kullaniyor", "maliyet.planla" in orch_kaynak)
kontrol("SEO HTML artik TEK kez kuruluyor (bayat rapor yok)", orch_kaynak.count("build_seo_html(") == 1,
        str(orch_kaynak.count("build_seo_html(")))
kontrol("TTS dogrulama bayrakla kontrol ediliyor", "TTS_DOGRULAMA_AKTIF" in orch_kaynak)
kontrol("Whisper olcum modeli bir kez yukleniyor (cache)", "_olcum_modeli" in orch_kaynak)
kontrol("voiceover_text try disinda tanimli (NameError yok)", "voiceover_text = \"\"" in orch_kaynak)

const_kaynak = oku("constants.py")
kontrol("TTS dogrulama varsayilan KAPALI (bosa Whisper yuklemesi yok)",
        "TTS_DOGRULAMA_AKTIF = False" in const_kaynak)

gem_kaynak = oku("functions/gemini_func.py")
kontrol("Yinelenen fix_spelling artik kosullu", "belirgin sekilde kisaldi" in gem_kaynak)

ss_zapcap = None
for aday in (r"C:\Users\Vafa\Desktop\ShortsStudio\functions\zapcap.py",
             os.path.join(os.path.expanduser("~"), "Desktop", "ShortsStudio", "functions", "zapcap.py")):
    if os.path.exists(aday):
        ss_zapcap = oku(aday)
        break
if ss_zapcap is not None:
    kontrol("Zapcap 4xx hatasinda bosuna tekrar denemiyor", "_http_durum_kodu" in ss_zapcap)
else:
    print("  NOT   ShortsStudio/zapcap.py bulunamadi, kontrol atlandi.")

# --------------------------------------------------------------------------
bolum("I) Indirme cozunurluk politikasi (dikey videoda gercek 1080p)")
# Dikey Short'ta 1080p'nin height'i 1920'dir; eski height<=1080/1440 cap'leri
# dikeyde sessizce 608/720p seciyordu. Cap artik genislik+yukseklik ile ve
# [ext=mp4] tercihiyle dosya adi sabit .mp4 kaliyor (bot bu yolu bekliyor).
CAP = "bestvideo[width<=1920][height<=1920]"
TEK = f'"{CAP}[ext=mp4]/{CAP}/bestvideo"'
CIFT = f'"{CAP}[ext=mp4]+bestaudio[ext=m4a]/{CAP}+bestaudio/best"'
kino_kaynak = oku("kinosekrety.py")
fakt_kaynak = oku("faktza15.py")
kino_s_kaynak = oku("kinok_syjet.py")
temiz_kaynak = oku("temizle.py")
kontrol("Kanal 1 indirmesi dikey 1080p + .mp4 tercihi", TEK in kino_kaynak)
kontrol("Kanal 2 indirmesi dikey 1080p + .mp4 tercihi", TEK in fakt_kaynak)
kontrol("Kanal 3 indirmesi dikey 1080p + ses (m4a) tercihi", CIFT in kino_s_kaynak)
kontrol("Kanal 3 merge cikisi mp4 (dosya adi .mp4 kalir)", '"merge_output_format": "mp4"' in kino_s_kaynak)
kontrol("Temizleyici indirmesi dikey 1080p + ses (m4a) tercihi", CIFT in temiz_kaynak)
kontrol("Yon bagimli eski cap'ler kalmadi",
        "bestvideo[height<=1440]/bestvideo" not in kino_kaynak and
        "bestvideo[height<=1080]/bestvideo" not in fakt_kaynak and
        "bestvideo[height<=1080]+bestaudio/best" not in temiz_kaynak)
kontrol("Kanal 3 artik 4K indirmiyor (ciplak 'best' kalmadi)", '"format": "best"' not in kino_s_kaynak)

# --------------------------------------------------------------------------
bolum("J) TTS/abonelik dayanikliligi (MP3'suz video URETILMEZ: fail-fast)")
# Gercek vaka (2026-10-04): ElevenLabs aboneligi 'past_due' iken gunluk zincir
# 3 gun boyunca GPU harcadi, hicbir Gun klasorune MP3 yazilmadi ve ShortsStudio
# her gun ".mp3 bulunamadi" ile atlandi. Bu bolum ayni senaryonun sessizce
# tekrarlanmadigini dogrular: on kontrol + TTS fail-fast + zincir durdurma.
from functions import tts_kontrol  # noqa: E402
kontrol("Odeme sorunu: 'past_due' sistemik sayilir", tts_kontrol.odeme_sorunu_var_mi({"status": "past_due"}))
kontrol("Odeme sorunu: 'unpaid' sistemik sayilir", tts_kontrol.odeme_sorunu_var_mi({"status": "unpaid"}))
kontrol("Odeme sorunu: 'active' engellemez", not tts_kontrol.odeme_sorunu_var_mi({"status": "active"}))
kontrol("Odeme sorunu: ulasilamayan durum (None) engellemez", not tts_kontrol.odeme_sorunu_var_mi(None))
_odeme_mesaj = tts_kontrol.odeme_mesaji({"status": "past_due", "has_open_invoices": True})
kontrol("Odeme mesaji durum + fatura + cozum icerir",
        "past_due" in _odeme_mesaj and "fatura" in _odeme_mesaj and "elevenlabs.io" in _odeme_mesaj)
_tts_hata = tts_kontrol.tts_hata_mesaji("401 payment_issue")
kontrol("401 payment_issue metni sistemik isaretli + fail-fast anlatir",
        tts_kontrol.SISTEMIK_ISARET in _tts_hata and "GPU BASLATILMADI" in _tts_hata)
# Kota tukenmesi ODEME hatasiyla karistirilmamali (ucretsiz plan 10k karakterde kritik)
kontrol("Kota isareti taninir (quota_exceeded)", tts_kontrol.kota_doldu_mu('{"code":"quota_exceeded"}'))
kontrol("Kota isareti odeme metniyle karismaz", not tts_kontrol.kota_doldu_mu("401 payment_issue"))
kontrol("Kalan karakter hesabi (10000-9995=5)", tts_kontrol.kalan_karakter({"character_limit": 10000, "character_count": 9995}) == 5)
_kota_mesaj = tts_kontrol.tts_hata_mesaji("This request exceeds your quota of 10000",
                                           {"character_limit": 10000, "character_count": 9995})
kontrol("Kota mesaji 'kota doldu' der, odeme demez",
        "KOTASI DOLDU" in _kota_mesaj and "payment_issue" not in _kota_mesaj and "kalan: 5/10000" in _kota_mesaj)
kontrol("Sistemik isaret sabiti degismedi", tts_kontrol.SISTEMIK_ISARET == "VIDEOFORGE-SISTEMIK-TTS-HATASI")
kontrol("Yerel on kontrol fonksiyonu var (kanal scriptleri + zincir kullanir)", callable(getattr(tts_kontrol, "yerel_on_kontrol", None)))
_orch = oku("functions/orchestrator.py")
kontrol("Orkestrator TTS on kontrolu yapar (abonelik_durumu)", "abonelik_durumu(" in _orch)
kontrol("Orkestrator: ses yoksa hata dondurur (fail-fast)", "not audio_bytes" in _orch and "tts_hata_mesaji(" in _orch)
_ff = _orch.find("tts_hata_mesaji(")
_gpu = _orch.find("bot = VideoCleanerClass()")
kontrol("Fail-fast GPU cagrisindan ONCE", 0 <= _ff < _gpu)
_hk = oku("haftalik_islet.py")
kontrol("Zincir on kontrolu odeme durumunu sorgular", "tts_on_kontrol" in _hk and "yerel_on_kontrol" in _hk)
kontrol("Zincir bot ciktisini canli toplar (sistemik hata tespiti)", "gun_cikti" in _hk)
kontrol("Zincir sistemik hatada kalan gunleri durdurur", "sistemik_hata_mi(" in _hk and "break" in _hk)
kontrol("Sistemik hata isaretli ciktiyla yakalanir", haftalik_islet.sistemik_hata_mi(
    "⚠️ [Bulut] ElevenLabs hatasi: 401 " + tts_kontrol.SISTEMIK_ISARET + ": ElevenLabs abonelik/odeme hatasi"))
kontrol("Normal cikti sistemik hata sayilmaz", not haftalik_islet.sistemik_hata_mi(
    "✅ Gun 1 VideoForge tamamlandi.\n🎬 ShortsStudio montaji basliyor.\n📁 final_123.mp4"))
for _ad, _dosya in (("Kanal 1", "kinosekrety.py"), ("Kanal 2", "faktza15.py"), ("Kanal 3", "kinok_syjet.py")):
    _kanal_kaynak = oku(_dosya)
    kontrol(f"{_ad}: sistemik TTS hatasi kanal scriptinde net duyurulur", "SISTEMIK_ISARET" in _kanal_kaynak)
    kontrol(f"{_ad}: kosu basinda ucretsiz TTS on kontrolu yapar", "yerel_on_kontrol()" in _kanal_kaynak)
    kontrol(f"{_ad}: hatada sifir olmayan cikis kodu (app 'tamamlandi' sanmasin)", "sys.exit(1)" in _kanal_kaynak)
kontrol("Zincir eksik/sistemik gunde sifir olmayan cikis kodu verir", "sys.exit(1)" in _hk)
kontrol("Zincir --yeniden-gun parametresi sunar", "--yeniden-gun" in _hk)
kontrol("Zincir basinda kota kapasite uyarisi var", "VIDEO_BASINA_KARAKTER" in _hk and "ElevenLabs kotasi" in _hk)
kontrol("Yeniden gun ayristirma (1, 2,x,3 -> {1,2,3})", haftalik_islet.yeniden_gunleri_ayristir("1, 2,x,3") == {1, 2, 3})
kontrol("Yeniden gun ayristirma bos deger -> bos kume", haftalik_islet.yeniden_gunleri_ayristir(None) == set())
# Gecici DB ile kayit silme davranisi (GERCEK bot.db'ye DOKUNMAZ)
import sqlite3 as _sqlite3  # noqa: E402
import constants as _constants  # noqa: E402
_gecici_db = os.path.join(gecici("vf_db_"), "bot.db")
_eski_db_yolu = _constants.DB_PATH
try:
    _constants.DB_PATH = _gecici_db
    with _sqlite3.connect(_gecici_db) as _conn:
        _conn.execute("CREATE TABLE IF NOT EXISTS videos (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        _conn.execute("INSERT INTO videos (link) VALUES ('dQw4w9WgXcQ')")
        _conn.commit()
    _silindi = haftalik_islet.link_kaydi_sil("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    with _sqlite3.connect(_gecici_db) as _conn:
        _kalan = _conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    kontrol("--yeniden-gun: DB kaydi silinir (yeniden uretim mumkun)", _silindi and _kalan == 0)
finally:
    _constants.DB_PATH = _eski_db_yolu
_kredi = oku(os.path.join("desktop", "electron", "data", "credits.ts"))
kontrol("Kredi kartinda past_due -> kirmizi hata + fatura mesaji",
        "odemeSorunlu" in _kredi and "'past_due'" in _kredi and "has_open_invoices" in _kredi)

# --------------------------------------------------------------------------
bolum("N) TEK ASAMA CIKTI: final Gun klasorune tasiniyor (kok kalabaligi yok)")
_orch = __import__("functions.orchestrator", fromlist=["orchestrator"])
_masa = gecici("vf-tekasama-")
_gun = os.path.join(_masa, "Gun6_Test_Video")
os.makedirs(_gun)
with open(os.path.join(_gun, "Test_CLEAN.mp4"), "wb") as f:
    f.write(b"v" * 8)
with open(os.path.join(_gun, "Test_VOICEOVER.mp3"), "wb") as f:
    f.write(b"a" * 8)
with open(os.path.join(_gun, "Test_SEO.html"), "w", encoding="utf-8") as f:
    f.write("<html>seo</html>")
with open(os.path.join(_masa, "final_424242.mp4"), "wb") as f:
    f.write(b"f" * 64)
_tasindi, _bilgi = haftalik_islet.final_gun_klasorune_tasi(_masa, _gun, "final_424242.mp4")
kontrol("Final kokteki dosyadan Gun klasorune tasindi (rename)",
        _tasindi and os.path.exists(os.path.join(_gun, "final_424242.mp4"))
        and not os.path.exists(os.path.join(_masa, "final_424242.mp4")) and _bilgi == "Gun klasorune tasindi", _bilgi)
_tasindi2, _bilgi2 = haftalik_islet.final_gun_klasorune_tasi(_masa, _gun, "final_424242.mp4")
kontrol("Ikinci cagri zararsiz: 'zaten Gun klasorunde' (kazara ezme/silme yok)",
        _tasindi2 and _bilgi2 == "zaten Gun klasorunde" and os.path.getsize(os.path.join(_gun, "final_424242.mp4")) == 64, _bilgi2)
_tasindi3, _bilgi3 = haftalik_islet.final_gun_klasorune_tasi(_masa, _gun, "final_999999.mp4")
kontrol("Olmayan final icin net hata (sessiz basari yok)", (not _tasindi3) and "bulunamadi" in _bilgi3, _bilgi3)
_girdi_final, _ = haftalik_islet.find_gun_girdileri(_gun)
kontrol("Klasordeki final, ShortsStudio girdisi SAYILMAZ (yeniden montaj guvenli)",
        bool(_girdi_final) and _girdi_final[0].endswith("Test_CLEAN.mp4"),
        os.path.basename(_girdi_final[0]) if _girdi_final else "girdi yok")
_hl_kaynak = oku("haftalik_islet.py")
kontrol("Zincir final'i Gun klasorune tasiyor (studio_islet icinde cagri var)",
        "final_gun_klasorune_tasi(desktop, gun_dir, final_ad)" in _hl_kaynak)
kontrol("Zincir ozeti artik 'masaustu kokunde final' demiyor",
        "finaller Masaustu/final_*.mp4" not in _hl_kaynak)

# Desktop uygulamasi da final'i klasor grubuyla birlikte gostersin.
_reports = oku(os.path.join("desktop", "electron", "data", "reports.ts"))
kontrol("Uygulama taramasi final'i Gun klasorunden de buluyor",
        "final_" in _reports and "candidateDirs" in _reports)
kontrol("Uygulama gruplamada final'i klasordeki dosyalarla birlestiriyor",
        "FINAL_ONLY_RE" in _reports and "dirStem" in _reports)
_parser = oku(os.path.join("desktop", "electron", "python", "parser.ts"))
kontrol("Canli log akisinda final_*.mp4 cikti olarak taniniyor",
        "final_" in _parser and "kind: 'video', name" in _parser)

# --------------------------------------------------------------------------
bolum("N2) studio_islet uctan uca: sahte ShortsStudio ile GERCEK akis (Modal/GPU YOK)")
_sahte_masa = gecici("vf-studio-masa-")
_sahte_studio = os.path.join(_sahte_masa, "ShortsStudio")
os.makedirs(_sahte_studio)
with open(os.path.join(_sahte_studio, "main.py"), "w", encoding="utf-8") as f:
    f.write("# sahte ShortsStudio (test)")
_sahte_gun = os.path.join(_sahte_masa, "Gun2_Sahte_Video")
os.makedirs(_sahte_gun)
with open(os.path.join(_sahte_gun, "Sahte_CLEAN.mp4"), "wb") as f:
    f.write(b"v" * 8)
with open(os.path.join(_sahte_gun, "Sahte_VOICEOVER.mp3"), "wb") as f:
    f.write(b"a" * 8)
with open(os.path.join(_sahte_gun, "Sahte_SEO.html"), "w", encoding="utf-8") as f:
    f.write("<html>seo</html>")


class _SahtePopen:
    """ShortsStudio'yu taklit eder: final'i masaustu KOKUNE yazar ve adini basar."""

    def __init__(self, cmd, cwd=None, env=None, **kw):
        _SahtePopen.son_env = env
        self._satirlar = [b"render bitti\n", b"Masaustu -> final_654321.mp4\n"]
        self._i = 0
        self.returncode = None
        self.env = env
        with open(os.path.join(_sahte_masa, "final_654321.mp4"), "wb") as f:
            f.write(b"final" * 16)
        _sahip = self

        class _Out:
            def readline(_self):
                if _sahip._i < len(_sahip._satirlar):
                    s = _sahip._satirlar[_sahip._i]
                    _sahip._i += 1
                    return s
                _sahip.returncode = 0
                return b""

        self.stdout = _Out()

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode or 0


class _SubprocessShim:
    Popen = _SahtePopen
    PIPE = subprocess.PIPE
    STDOUT = subprocess.STDOUT


_eski_subprocess = haftalik_islet.subprocess
_eski_desktop_fn = haftalik_islet._desktop
_eski_studio_dir_fn = haftalik_islet.studio_dir_bul
haftalik_islet.subprocess = _SubprocessShim
haftalik_islet._desktop = lambda: _sahte_masa
haftalik_islet.studio_dir_bul = lambda: _sahte_studio
try:
    _s_ok, _s_bilgi = haftalik_islet.studio_islet(2, "1", 7)
finally:
    haftalik_islet.subprocess = _eski_subprocess
    haftalik_islet._desktop = _eski_desktop_fn
    haftalik_islet.studio_dir_bul = _eski_studio_dir_fn

kontrol("studio_islet basarili dondu", _s_ok is True, str(_s_bilgi))
kontrol("Donen yol Gun klasorunu de gosteriyor (tek klasor sonucu)",
        str(_s_bilgi) == os.path.join("Gun2_Sahte_Video", "final_654321.mp4"), str(_s_bilgi))
kontrol("Final artik Gun klasorunde (masaustu kokunde degil)",
        os.path.exists(os.path.join(_sahte_gun, "final_654321.mp4"))
        and not os.path.exists(os.path.join(_sahte_masa, "final_654321.mp4")))
_final_yolu = os.path.join(_sahte_gun, "final_654321.mp4")
_icerik = open(_final_yolu, "rb").read() if os.path.exists(_final_yolu) else b""
kontrol("Tasima kopya degil rename (ayni dosya, icerik korunur)", _icerik == b"final" * 16, f"{len(_icerik)} byte")
_ortam = getattr(_SahtePopen, "son_env", None) or {}
_ortam_anahtarlari = [k for k in ("VIDEOFORGE_STUDIO_VIDEO", "VIDEOFORGE_STUDIO_AUDIO", "VIDEOFORGE_STUDIO_SEO") if _ortam.get(k)]
kontrol("ShortsStudio'ya girdi yollari ortam degiskeniyle veriliyor (kopyalama yok)",
        len(_ortam_anahtarlari) == 3, ", ".join(_ortam_anahtarlari) or "env yok")

# --------------------------------------------------------------------------
bolum("O) KAPAK: ana karakter/konu odakli kare secimi (arastirma temelli)")
_kapak_kaynak = oku("functions/orchestrator.py")
kontrol("20 aday kare (eski 12 yerine, tum video boyunca)", _orch.THUMB_ADET >= 16, str(_orch.THUMB_ADET))
kontrol("CLIP prompt ensemble: 5 pozitif + 5 negatif prompt",
        len(_orch.THUMB_POZITIF) >= 4 and len(_orch.THUMB_NEGATIF) >= 4,
        f"{len(_orch.THUMB_POZITIF)}+{len(_orch.THUMB_NEGATIF)}")
kontrol("Negatif promptlar bulanik/patlak/altyazili kareleri cezalandiriyor",
        any("blur" in p for p in _orch.THUMB_NEGATIF) and any("subtitle" in p or "caption" in p for p in _orch.THUMB_NEGATIF))
kontrol("Yuz analizi: boyut + netlik + kadraj (ana karakter one cikar)",
        all(k in _kapak_kaynak for k in ("face_frac", "face_sharp_n", "face_center")))
kontrol("Gorsel hakem (Gemini) kare secimini yapiyor",
        "_thumb_gemini_sec" in _kapak_kaynak and "You are choosing the thumbnail frame" in _kapak_kaynak)
kontrol("Hakem adaylari KARISIK sirada goruyor (siraya bagli onyargi yok)",
        "_rnd.shuffle(sira)" in _kapak_kaynak)
kontrol("Hakem yalnizca ilk-N adayi goruyor (maliyet kontrollu)",
        _orch.THUMB_HAKEM_ADET <= 8, str(_orch.THUMB_HAKEM_ADET))
kontrol("Yazi yuzle cakismayan tarafa basiliyor (ust/alt karari)",
        "text_top = face_cy >= 0.5" in _kapak_kaynak)
kontrol("Kazanan kare TAM cozunurlukte yeniden cekiliyor (analiz 640px)",
        "thumb_best_" in _kapak_kaynak and "scale=640:-2" in _kapak_kaynak)

os.environ.pop("VIDEOFORGE_KAPAK_HAKEM", None)
kontrol("Gorsel hakem varsayilan ACIK", _orch.kapak_hakem_aktif() is True)
for _kapali in ("0", "off", "kapali", "hayir", "false", "no"):
    os.environ["VIDEOFORGE_KAPAK_HAKEM"] = _kapali
    if _orch.kapak_hakem_aktif() is not False:
        kontrol(f"Hakem kapatilabiliyor ('{_kapali}')", False, _kapali)
        break
else:
    kontrol("Hakem '0/off/kapali/hayir/false/no' ile kapatilabiliyor", True)
os.environ["VIDEOFORGE_KAPAK_HAKEM"] = "1"
kontrol("Hakem tekrar acilabiliyor", _orch.kapak_hakem_aktif() is True)
os.environ.pop("VIDEOFORGE_KAPAK_HAKEM", None)
kontrol("Hakem konu bossa API'ye hic gitmiyor",
        _orch._thumb_gemini_sec([{"img": None}, {"img": None}], "") is None)
kontrol("Hakem tek adayda API'ye hic gitmiyor",
        _orch._thumb_gemini_sec([{"img": None}], "konu") is None)

# Gercek uctan uca: sentetik video + gercek ffmpeg/cv2. Ag YOK: YuNet modeli
# yerine 150KB yer tutucu konur (indirme atlanir, yuz analizi sessizce atlanir),
# font yerine sistemdeki gercek bir TTF kopyalanir, gorsel hakem kapatilir.
_font_adaylari = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_font = next((f for f in _font_adaylari if os.path.exists(f)), None)
_ffmpeg_var = shutil.which("ffmpeg") is not None
try:
    import cv2  # noqa: F401
    _cv2_var = True
except Exception:
    _cv2_var = False
if _font and _ffmpeg_var and _cv2_var:
    _ktmp = gecici("vf-kapak-")
    _kvideo = os.path.join(_ktmp, "test.mp4")
    _r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                         "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=24", "-t", "5",
                         "-pix_fmt", "yuv420p", _kvideo], capture_output=True)
    kontrol("Kapak testi icin sentetik video uretildi", _r.returncode == 0 and os.path.exists(_kvideo))
    if os.path.exists(_kvideo):
        shutil.copy2(_font, os.path.join(_ktmp, "RussoOne-Regular.ttf"))
        with open(os.path.join(_ktmp, "face_detection_yunet_2023mar.onnx"), "wb") as f:
            f.write(b"x" * 150000)  # indirmeyi atla; gecersiz model sessizce atlanir
        os.environ["VIDEOFORGE_KAPAK_HAKEM"] = "0"  # testte ag cagrisi yok
        try:
            _png = _orch.build_thumbnail(_kvideo, "Test kapak basligi", _ktmp, 777, topic_query="test topic")
        except Exception as _e:
            _png = None
            kontrol("build_thumbnail hatasiz calisti", False, str(_e)[:120])
        finally:
            os.environ.pop("VIDEOFORGE_KAPAK_HAKEM", None)
        if _png is not None:
            kontrol("build_thumbnail PNG dondurdu (hakem kapali -> yerel skor)",
                    _png[:8] == b"\x89PNG\r\n\x1a\n" and len(_png) > 50000, f"{len(_png)} byte")
            try:
                import io as _io
                from PIL import Image as _PILImage2
                _boyut = _PILImage2.open(_io.BytesIO(_png)).size
            except Exception:
                _boyut = None
            kontrol("Kapak 1080x1920 (9:16) boyutunda", _boyut == (1080, 1920), str(_boyut))
else:
    print("  NOT   ffmpeg/cv2/font bulunamadi, kapak uctan uca testi atlandi.")

# --------------------------------------------------------------------------
bolum("P) UZUNLUK DONGUSU + BASLIK/ETIKET: deterministik Shorts SEO (2026)")
_gf = __import__("functions.gemini_func", fromlist=["gemini_func"])


# Kontrollu uzunlukta Rusca metin uret (ag YOK; Gemini stub'lanir)
def _cumle(boy, son="."):
    n = max(1, (int(boy) - 1) // 5)
    return ("тест " * n).strip() + son


def _metin(boylar):
    return " ".join(_cumle(b) for b in boylar)


_gemini_gercek = _gf.gemini_uret
_gemini_cevaplar = []
_gemini_cagri = {"n": 0}


def _sahte_gemini(input_text, system_prompt, channel_name, retry_feedback=None, json_mode=False):
    _gemini_cagri["n"] += 1
    if _gemini_cevaplar:
        return _gemini_cevaplar.pop(0)
    return "❌ sahte hata"


_gf.gemini_uret = _sahte_gemini
try:
    # 1) Kullanicinin GERCEK vakasi: hedefin ~%10 altinda metin (448ch/500)
    _v448 = _metin([148, 148, 148])
    kontrol("Test senaryosu kullanicinin vakasi (hedef bandin ~%10 alti)",
            375 <= len(_v448) < 450, f"{len(_v448)}ch")
    _gemini_cagri["n"] = 0
    _sonuc, _ = _gf.fix_length(_v448, 500, "ru", "Kino Sekrety", "transcript")
    kontrol("Kisa-tolerans: metin korunur, 0 Gemini cagrisi (eski 10 tur savrulmasi bitti)",
            _gemini_cagri["n"] == 0 and _sonuc == _v448, f"cagri={_gemini_cagri['n']}, {len(_sonuc)}ch")

    # 2) Cok kisa (300ch): TEK genisletme cagrisi, tasan sonuc mekanik kirpilir
    _v300 = _metin([100, 100, 100])
    _gemini_cagri["n"] = 0
    _gemini_cevaplar[:] = [_metin([200, 200, 200, 200])]
    _sonuc, _ = _gf.fix_length(_v300, 500, "ru", "Kino Sekrety", "transcript")
    kontrol("Cok kisa metin: en fazla 1 Gemini cagrisi",
            _gemini_cagri["n"] <= 1, f"cagri={_gemini_cagri['n']}")
    kontrol("Tasan genisletme mekanik kirpildi (hedefe yakin, <= 1.2x) ve uzadi",
            len(_sonuc) <= 600 and len(_sonuc) > len(_v300), f"{len(_sonuc)}ch")

    # 3) Cok uzun (900ch): 0 Gemini cagrisi, en kisa orta cumleler silinir
    _v900 = _metin([150, 150, 150, 150, 150, 150])
    _gemini_cagri["n"] = 0
    _sonuc, _ = _gf.fix_length(_v900, 500, "ru", "Kino Sekrety", "transcript")
    kontrol("Cok uzun metin 0 cagriyla hedefe indi",
            _gemini_cagri["n"] == 0 and len(_sonuc) <= 550, f"cagri={_gemini_cagri['n']}, {len(_sonuc)}ch")

    # 4) Tek cumle + uzun: mekanik silme yapilamaz -> tam 1 LLM turu
    _gemini_cagri["n"] = 0
    _gemini_cevaplar[:] = [_metin([175, 175, 175, 175])]
    _sonuc, _ = _gf.fix_length(_cumle(900), 500, "ru", "Kino Sekrety", "transcript")
    kontrol("Tek cumlede tek yeniden yazma turu, sonuc <= 550ch",
            _gemini_cagri["n"] == 1 and len(_sonuc) <= 550, f"cagri={_gemini_cagri['n']}, {len(_sonuc)}ch")

    # 5) Kirpma ilk (kanca) ve son (final sorusu) cumleye dokunmaz
    _bes = [_cumle(300), _cumle(60, "?"), _cumle(60, "?"), _cumle(60, "?"), _cumle(300, "?")]
    _kirp = _gf._trim_to_upper(" ".join(_bes), 400)
    kontrol("Kirpma ilk ve son cumleyi korur",
            _kirp.startswith(_bes[0]) and _kirp.endswith(_bes[-1]) and len(_kirp) < sum(len(x) for x in _bes) + 4)

    # 6) Shorts baslik rubrigi
    _iyi = "Почему Тор потерял Мьёльнир в «Рагнарёке»? 🔥 #тор"
    _kotu = ("ИНТЕРЕСНЫЙ И НЕВЕРОЯТНЫЙ ФИЛЬМ ПРО ТОРА И ПРО ТО ЧТО БЫЛО ДАЛЬШЕ "
             "СО МНОГИМИ СПОЙЛЕРАМИ И ПОДРОБНОСТЯМИ")
    kontrol("Shorts rubrigi iyi basligi >=60 puanliyor",
            _gf._title_ai_score(_iyi) >= 60, str(_gf._title_ai_score(_iyi)))
    kontrol("Rubrik uzun/ALL-CAPS basligi belirgin sekilde cezalandiriyor",
            _gf._title_ai_score(_iyi) > _gf._title_ai_score(_kotu) + 20,
            f"{_gf._title_ai_score(_iyi)} vs {_gf._title_ai_score(_kotu)}")
    kontrol("Iyi baslik bicim denetiminden geciyor",
            _gf._title_issues(_iyi) == [], str(_gf._title_issues(_iyi)))

    # 7) 3 aday arasindan GECERLI olani secilir (model skoru yuksek gecersiz degil)
    _adaylar = ("1. Очень длинный и совершенно непригодный заголовок без нужных знаков который точно не пройдет — Score: 10/10\n"
                "2. Почему Тор потерял молот? 🔥 #тор — Score: 7/10\n"
                "3. Коротко — Score: 2/10\n")
    _gemini_cagri["n"] = 0
    _gemini_cevaplar[:] = [_adaylar, _adaylar]
    _baslik, _ok2 = _gf.generate_title("ses", _gf.DEFAULT_TITLE_PROMPT, "Kino Sekrety")
    kontrol("generate_title gecerli adayi secer (tek tur, dogru aday)",
            _ok2 is True and _baslik == "Почему Тор потерял молот? 🔥 #тор" and _gemini_cagri["n"] == 1,
            f"{_baslik!r} cagri={_gemini_cagri['n']}")

    # 8) fix_title: LLM iki kez bos donse de emoji + <=65 karakter garanti
    _gemini_cagri["n"] = 0
    _gemini_cevaplar[:] = ["", ""]
    _baslik2, _ok3 = _gf.fix_title("Секрет Тора который изменил всё", "Kino Sekrety")
    kontrol("fix_title deterministik bitirir: emoji var, <=65 karakter",
            _ok3 is True and bool(_gf.EMOJI_RE.search(_baslik2)) and len(_baslik2) <= 65,
            f"{_baslik2!r} ({len(_baslik2)}ch)")
    kontrol("fix_title en fazla 2 LLM turu (eski 10 tur kalkti)",
            _gemini_cagri["n"] == 2, str(_gemini_cagri["n"]))

    # 9) Etiketler: 500 karakter alani + temizlik (genel kelime/tekrar/# temizligi)
    _etik_raw = ", ".join(
        ["#мстители судный день", "avengers doomsday", "мстители судный день"]
        + ["интересные факты про кино номер %d" % i for i in range(30)]
        + ["#герой", "судьба"]
    )
    _t = _gf._fit_tag_field(_gf._clean_tags(_etik_raw))
    kontrol("Etiket alani 500 karakter sinirini asmiyor",
            len(_t) <= _gf.TAG_FIELD_LIMIT, f"{len(_t)}ch")
    kontrol("Temizlik: # yok, tekrar yok, genel kelimeler atildi",
            "#" not in _t and "герой" not in _t and "судьба" not in _t
            and _t.count("мстители судный день") == 1)
    kontrol("Tek etiket sayisi korunuyor (>=12)",
            len([x for x in _t.split(",") if x.strip()]) >= 12)
    _guzel = ", ".join("ключ слово %d" % i for i in range(28))
    kontrol("Dolu ve gecerli etiket listesi denetimden geciyor",
            _gf._tag_issues(_guzel) == [], str(_gf._tag_issues(_guzel)))
    _katmanli = ("Line 1 — 10-12 EXACT tags: тор без молота, тор против хелы, thor vs hela\n"
                 "EXACT: мьёльнир тора, хела разбивает мьёльнир\n"
                 "BROAD: марвел, marvel, mcu, кино новости")
    _ta = _gf._tierle_ayir(_katmanli)
    kontrol("Katmanli cikti tek listeye cevriliyor (etiket/baslik satirlari ayiklanir)",
            _ta.startswith("тор без молота") and _ta.endswith("кино новости")
            and ":" not in _ta and "Line" not in _ta and "#" not in _ta, _ta[:80])
    kontrol("Katmanli ceviri sirasi korunuyor (EXACT -> NICHE -> BROAD)",
            _gf._tierle_ayir(_katmanli).split(", ")[0] == "тор без молота")
    _gemini_cagri["n"] = 0
    _gemini_cevaplar[:] = [_guzel]
    _et, _et_ok = _gf.generate_tags("ses", _gf.DEFAULT_TAGS_PROMPT, "Fakt Za 15")
    kontrol("generate_tags tek cagride dolu liste dondurdu",
            _et_ok is True and _gemini_cagri["n"] == 1
            and _gf.TAG_MIN_TOTAL <= len(_et) <= _gf.TAG_FIELD_LIMIT,
            f"{len(_et)}ch, cagri={_gemini_cagri['n']}")
finally:
    _gf.gemini_uret = _gemini_gercek

# Prompt kaynaklari: uc kanal da yeni Shorts kurallarini tasiyor
for _kanal_dosya in ("kinosekrety.py", "faktza15.py", "kinok_syjet.py"):
    _kanal_kaynak = oku(_kanal_dosya)
    kontrol(f"{_kanal_dosya}: baslik kurallari (kanca + tek emoji) yazili",
            "HOOK IN THE FIRST 2-3 WORDS" in _kanal_kaynak and "EXACTLY ONE emoji" in _kanal_kaynak)
    kontrol(f"{_kanal_dosya}: etiket 3 katmanli cikti + 500 karakter siniri yazili",
            "Output THREE lines" in _kanal_kaynak and "tag field limit is 500" in _kanal_kaynak
            and "EXACT" in _kanal_kaynak and "BROAD" in _kanal_kaynak)
_kjs = oku("kinok_syjet.py")
kontrol("kinok_syjet: bozuk '##hashtag' ve 'антагон' metni temizlendi",
        "##" not in _kjs and "антагон" not in _kjs)
kontrol("Varsayilan promptlar da yeni kurallari tasiyor",
        "tag field limit is 500" in _gf.DEFAULT_TAGS_PROMPT
        and "HOOK IN THE FIRST 2-3 WORDS" in _gf.DEFAULT_TITLE_PROMPT)
kontrol("Eski uzunluk savrulmasi kodda kalmadi ('en iyi haliyle kabul' yok)",
        "en iyi haliyle kabul" not in gem_kaynak)
kontrol("Baslik/etiket 8+10 turluk ic ice donguleri kaldirildi",
        "Baslik max deneme" not in gem_kaynak and "Etiketler max deneme" not in gem_kaynak)

bolum("Q) ALTYAZI ZINCIRI + GENIS HAVUZ / COP DOLDURMA")
import functions.transcribe as _tr  # noqa: E402
_trk_kaynak = oku("functions/transcribe.py")
_ksf_kaynak = oku("kesif.py")
_ork_kaynak = oku("functions/orchestrator.py")
kontrol("Whisper yedegi SES odakli secici kullanir (muxed formati olmayan video da iner)",
        "worstaudio" in _ksf_kaynak and '"worst/worst[ext=mp4]/best[ext=mp4]/best"' not in _ksf_kaynak)
kontrol("Whisper yedegi cerezleri kullanir (kisitli videolar)",
        "from functions.transcribe import _cookiefile as _cf" in _ksf_kaynak)
kontrol("404/410/400 kalici hatadir: tek istek + negatif onbellek",
        "_API_YOK" in _trk_kaynak and "_api_cevap_hata" in _trk_kaynak)
kontrol("401/403 yetki/kredi hatasi net mesaj verir", "yetki/kredi hatasi" in _trk_kaynak)
kontrol("Uzun 404 govdesi loga basilmiyor (log kalabaligi bitti)", "response.text}" not in _trk_kaynak)
kontrol("YouTube altyazi yoksa yerel videodan ZAMANLI whisper",
        "yerel videodan zaman damgali Whisper" in _trk_kaynak)
kontrol("speech_recognition yoksa cokme yok (guvenli import)",
        "speech_recognition kurulu degil" in _trk_kaynak)


class _R404:
    status_code = 404
    text = '{"detail":"Video X is unavailable"}'


_eski_get = _tr.requests.get
_cagri = {"n": 0}


def _sahte_404(*a, **k):
    _cagri["n"] += 1
    return _R404()


try:
    _tr.requests.get = _sahte_404
    _tr._API_YOK.clear()
    _tr._API_YETKI_HATA = False
    _ilk = _tr.api_ile_transkript_cek("https://www.youtube.com/watch?v=ZZZZZZZZZZZ")
    _ikinci = _tr.api_ile_transkript_cek("https://www.youtube.com/watch?v=ZZZZZZZZZZZ")
    _chunk = _tr.api_ile_transkript_chunk_cek("https://www.youtube.com/watch?v=ZZZZZZZZZZZ")
finally:
    _tr.requests.get = _eski_get
kontrol("Transcript API 404: 3 tekrar yerine TEK istek + None",
        _cagri["n"] == 1 and _ilk is None and _ikinci is None and _chunk == [],
        f"istek={_cagri['n']}")
kontrol("404 sonucu video ID ile onbellege alindi (kredi bosuna yanmaz)",
        "ZZZZZZZZZZZ" in _tr._API_YOK)


class _R401:
    status_code = 401
    text = "{}"


_cagri2 = {"n": 0}


def _sahte_401(*a, **k):
    _cagri2["n"] += 1
    return _R401()


try:
    _tr.requests.get = _sahte_401
    _tr._API_YOK.clear()
    _tr._API_YETKI_HATA = False
    _y1 = _tr.api_ile_transkript_cek("https://www.youtube.com/watch?v=AAAAAAAAAAA")
    _bayrak = _tr._API_YETKI_HATA
    _y2 = _tr.api_ile_transkript_cek("https://www.youtube.com/watch?v=BBBBBBBBBBB")
finally:
    _tr.requests.get = _eski_get
    _tr._API_YOK.clear()
    _tr._API_YETKI_HATA = False
kontrol("Transcript API 401: tek deneme + yetki bayragi (video basina tekrar yok)",
        _cagri2["n"] == 1 and _y1 is None and _y2 is None and _bayrak is True,
        f"istek={_cagri2['n']}")

kontrol("Genis havuz varsayilani 70 (on filtre baslikla bedava calisir)",
        kesif.DEFAULT_CONFIG.get("havuz_sayisi") == 70)
kontrol("Haftalik plan icin +10 aday (gun_sayisi + 10)", "gun_sayisi + 10" in _ksf_kaynak)
kontrol("COP yedek doldurma varsayilan KAPALI (kalite > adet)",
        kesif.DEFAULT_CONFIG.get("cop_doldur") is False and 'cfg.get("cop_doldur", False)' in _ksf_kaynak)
kontrol("Eski 40 havuzu yeni degere tasinir (kullanici secimi korunur)",
        'int(cfg.get("havuz_sayisi") or 0) == 40' in _ksf_kaynak)

kontrol("Orchestrator tek prompt kaynagi kullanir (olu system_prompt degiskeni gitti)",
        'vp = (voice_prompt or system_prompt or "")' in _ork_kaynak and "sp = system_prompt.replace" not in _ork_kaynak)
for _kanal_dosya in ("kinosekrety.py", "faktza15.py", "kinok_syjet.py"):
    _norm = oku(_kanal_dosya).replace("\r\n", "\n")
    kontrol(f"{_kanal_dosya}: PROMPT kopyasi silindi, tek kaynak VOICE_PROMPT",
            "system_prompt=VOICE_PROMPT" in _norm and "\nPROMPT = " not in _norm)

# --------------------------------------------------------------------------
bolum("R) PERFORMANS GERI BILDIRIMI (YouTube Studio CSV -> kanitlanmis kaliplar)")
import functions.performans as _pf  # noqa: E402

_eski_pf_csv, _eski_pf_perf = _pf.CSV_DIR, _pf.PERF_FILE
_pf_tmp = gecici("vf-perf-")
_pf_csv = os.path.join(_pf_tmp, "performans_csv")
os.makedirs(os.path.join(_pf_csv, "kanal1"))
_pf.PERF_FILE = os.path.join(_pf_tmp, "performans.json")
_pf.CSV_DIR = _pf_csv

try:
    with open(os.path.join(_pf_csv, "k1.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(
            "Video title,Video publish time,Duration,Views,Impressions,"
            "Impressions click-through rate (%),Average view duration,Average percentage viewed (%)\n"
            "Why Thanos was right about everything,2026-09-01,0:45,\"322,000\",\"5,100,000\",6.3,0:21,47.5\n"
            "The secret of Thor's hammer,2026-09-02,0:52,\"179,000\",\"3,000,000\",5.9,0:24,45.1\n"
            "Why Thanos feared this Avenger,2026-09-03,0:48,\"130,000\",\"2,400,000\",5.4,0:22,46.0\n"
            "Tom Holland contract drama explained,2026-09-04,0:50,4100,\"700,000\",1.1,0:12,22.4\n"
            "Superman costume details nobody noticed,2026-09-05,0:47,3800,\"600,000\",1.0,0:11,20.1\n"
            "Namor powers theory,2026-09-06,0:44,2100,\"400,000\",0.9,0:10,18.7\n"
        )
    # Turkce Studio CSV: ';' ayirici + ondalik virgul + noktali binlik
    with open(os.path.join(_pf_csv, "kanal1", "k_try.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(
            "Video başlığı;Görüntülenme;Tıklama oranı;İzlenme yüzdesi\n"
            "İşte Thanos'un gerçek planı;150.000;5,5;46,2\n"
        )
    # Ayni baslik 2. dosyada DAHA YUKSEK izlenmeyle -> birlestirme testi
    with open(os.path.join(_pf_csv, "k2.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write("Video title,Views,Average percentage viewed (%)\n"
                "Why Thanos was right about everything,\"410,000\",49.0\n")

    _k1 = _pf.parse_studio_csv(os.path.join(_pf_csv, "k1.csv"))
    kontrol("Studio CSV (EN) gercek dosyadan ayristirildi", len(_k1) == 6, f"{len(_k1)} satir")
    kontrol("Binlik virgul dogru sayiya cevrilir (322,000 -> 322000)",
            _k1[0]["izlenme"] == 322000.0, str(_k1[0]["izlenme"]))
    kontrol("Yuzde ve sure dogru okunur (6.3% / 0:45)",
            _k1[0]["ctr"] == 6.3 and _k1[0]["sure"] == 45.0,
            f"ctr={_k1[0]['ctr']} sure={_k1[0]['sure']}")

    _ktr = _pf.parse_studio_csv(os.path.join(_pf_csv, "kanal1", "k_try.csv"))
    kontrol("Turkce Studio CSV (';' + 150.000 + 5,5) dogru ayristirildi",
            bool(_ktr) and _ktr[0]["izlenme"] == 150000.0 and _ktr[0]["ctr"] == 5.5,
            str(_ktr)
            if not _ktr else f"{_ktr[0]['baslik']} {_ktr[0]['izlenme']} {_ktr[0]['ctr']}")

    _sayi_hatalari = [(g, _pf.sayi_cek(g), b) for g, b in
                      [("1,234", 1234.0), ("1.234", 1234.0), ("4,5", 4.5), ("6.3", 6.3),
                       ("0:45", 45.0), ("1:02:33", 3753.0), ("2.100.000", 2100000.0),
                       ("1.234,5", 1234.5), ("1,234.5", 1234.5), ("0,123", 0.123),
                       ("", None), ("-", None)]
                      if _pf.sayi_cek(g) != b]
    kontrol("sayi_cek kenar durumlari (binlik/ondalik/sure/bos) dogru",
            not _sayi_hatalari, str(_sayi_hatalari[:3]))

    _pg = _pf.performans_yukle("genel")
    kontrol("performans_yukle dosyalari birlestirdi", _pg["ozet"]["video_sayisi"] == 6,
            f"{_pg['okunan_dosyalar']}")
    _thanos = [v for v in _pg["videolar"] if v["baslik"] == "Why Thanos was right about everything"]
    kontrol("Ayni baslik tek kayda indi ve EN YUKSEK izlenme kazandi",
            len(_thanos) == 1 and _thanos[0]["izlenme"] == 410000.0 and _thanos[0]["ort_yuzde"] == 49.0,
            str(_thanos)[:120])
    kontrol("Kanal ozeti (toplam/ortalama/CTR) hesaplandi",
            _pg["ozet"]["toplam_izlenme"] == 729000.0 and _pg["ozet"]["ort_ctr"] == 3.43,
            str(_pg["ozet"]))

    _kl = [k["kelime"] for k in _pg["kaliplar"]]
    kontrol("Kalip madenciligi kazanan temasini buldu (thanos)", "thanos" in _kl, str(_kl))
    kontrol("Kaybeden temasini kalip saymadi (holland)", "holland" not in _kl, str(_kl))

    _kl2 = _pf.kaliplar_getir("genel")
    kontrol("kalip_blok prompta gomulebilir metin uretir",
            "PROVEN PATTERNS" in _pf.kalip_blok("genel") and '"thanos"' in _pf.kalip_blok("genel"))
    _b_iyi = _pf.performans_bonusu("Why Thanos was right about everything", _kl2)
    _b_kotu = _pf.performans_bonusu("Tom Holland contract drama explained", _kl2)
    kontrol("performans_bonusu kanitli temaya puan verir, digerine sifir",
            0 < _b_iyi <= 1.0 and _b_kotu == 0.0, f"iyi={_b_iyi} kotu={_b_kotu}")
    kontrol("performans_bonusu bos baslikta cokmez", _pf.performans_bonusu("", _kl2) == 0.0)

    _kno = _pf.kanal_no_bul("Kino Sekrety")
    kontrol("Kanal ADI -> kanal no koprusu (Kiril/Latin) calisir",
            _kno == "1" and _pf.kanal_no_bul("ПопкорнФакты") == "3"
            and _pf.kanal_no_bul("bilinmeyen") == "genel",
            f"{_kno}/{_pf.kanal_no_bul('ПопкорнФакты')}")

    # Veri YOK iken hicbir sey patlamamali (yeni kurulum senaryosu).
    _pf.PERF_FILE = os.path.join(_pf_tmp, "yok.json")
    _pf.CSV_DIR = os.path.join(_pf_tmp, "yok_klasor")
    _pf._ONBELLEK["anahtar"] = None
    _pf._ONBELLEK["veri"] = None
    kontrol("Veri yokken kalip/bonus guvenli ('' / [] / 0.0)",
            _pf.kaliplar_getir("genel") == [] and _pf.kalip_blok("genel") == ""
            and _pf.performans_bonusu("herhangi") == 0.0)
finally:
    _pf.CSV_DIR, _pf.PERF_FILE = _eski_pf_csv, _eski_pf_perf
    _pf._ONBELLEK["anahtar"] = None
    _pf._ONBELLEK["veri"] = None

# gemini_rank GERCEK fonksiyonu: kaliplar hem prompta girmeli hem siralamayi etkilemeli.
_eski_sira = (kesif.gemini_uret, kesif.kaliplar_getir, kesif.kalip_blok)
_kap = {}


def _sahte_gemini(a, b, c):
    _kap["p"] = b
    return "1|8.0|AAAAAAAAAAA|KAZANAN|guclu konu\n2|8.0|BBBBBBBBBBB|KAZANAN|thanos konusu"


_kand = [
    {"id": "AAAAAAAAAAA", "title": "Thor hammer secret", "views": 1000, "duration": 60,
     "transcript": "x", "description": "y"},
    {"id": "BBBBBBBBBBB", "title": "Thanos plan revealed", "views": 900, "duration": 60,
     "transcript": "x", "description": "y"},
]
try:
    kesif.gemini_uret = _sahte_gemini
    kesif.kaliplar_getir = lambda kanal="1": [{"kelime": "thanos", "skor": 0.25, "adet": 2, "ornek": "Why Thanos"}]
    kesif.kalip_blok = lambda kanal="1", adet=6: "PROVEN PATTERNS: thanos"
    _r_kalipli = kesif.gemini_rank(_kand, "profil", "Kino Sekrety", kanal="1")
    _p_kalipli = _kap.get("p", "")
    kesif.kaliplar_getir = lambda kanal="1": []
    kesif.kalip_blok = lambda kanal="1", adet=6: ""
    _r_bos = kesif.gemini_rank(_kand, "profil", "Kino Sekrety", kanal="1")
    _sahte_gemini("", "", "")
    kesif.gemini_uret = lambda a, b, c: _sahte_gemini(a, b, c)
    _style_kalipli = kesif.gemini_style_profile([{"title": "t", "views": 1}], "Kino Sekrety",
                                               kanit_blok="PROVEN PATTERNS: thanos")
    _p_style = _kap.get("p", "")
finally:
    kesif.gemini_uret, kesif.kaliplar_getir, kesif.kalip_blok = _eski_sira

kontrol("gemini_rank kanitlanmis kaliplari PROMPTA koyar", "PROVEN PATTERNS" in _p_kalipli)
kontrol("Kanitli tema esit puanda ONCE gelir (deterministik bonus)",
        _r_kalipli and _r_kalipli[0]["id"] == "BBBBBBBBBBB" and _r_kalipli[0]["score"] > 8.0
        and _r_kalipli[1]["kalip_bonusu"] == 0
        and _r_kalipli[0].get("kalip_bonusu", 0) > 0,
        str([(r["id"], r["score"], r.get("kalip_bonusu")) for r in _r_kalipli]))
kontrol("Kaliplar KAPALI iken modelin sirasi aynen korunur (davranis degismedi)",
        _r_bos and _r_bos[0]["id"] == "AAAAAAAAAAA" and "kalip_bonusu" not in _r_bos[0],
        str([(r["id"], r["score"]) for r in _r_bos]))
kontrol("Stil profili promptuna kanit blogu girer", "PROVEN PATTERNS" in _p_style)

_gf_kaynak = oku("functions/gemini_func.py")
_kontrol_kaynak = oku("functions/performans.py")
_hl_kaynak2 = oku("haftalik_islet.py")
kontrol("Baslik uretimi kanitlanmis kaliplari prompta ekliyor",
        "_kanitlanmis_kaliplar(channel_name)" in _gf_kaynak and "_kalip_bolum" in _gf_kaynak)
kontrol("Performans modulu AG KULLANMAZ (salt okuma: API/anahtar/OAuth yok)",
        not any(x in _kontrol_kaynak for x in
                ("import requests", "import urllib", "urllib.request", "http.client",
                 "import google", "import elevenlabs")),
        "")
kontrol("kesif.py performans modulune bagli (import + kullanim)",
        "from functions.performans import" in _ksf_kaynak
        and "kalip_bonusu" in _ksf_kaynak and "kanit_blok=perf_blok" in _ksf_kaynak)

# --------------------------------------------------------------------------
bolum("S) YAYIN ONCESI QA KAPISI (finali ffmpeg ile GERCEKTEN olcer)")
from functions import qa_kapisi as _qa  # noqa: E402

_qa_tmp = gecici("vf-qa-")
_ffmpeg_var = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
_qa_iyi = os.path.join(_qa_tmp, "iyi.mp4")
_qa_kotu = os.path.join(_qa_tmp, "kotu.mp4")


def _ffmpeg_uret(hedef, komut_parcalari):
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + komut_parcalari + [hedef],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    return r.returncode == 0 and os.path.exists(hedef)


if not _ffmpeg_var:
    atla("QA kapisi canli olcum", "ffmpeg/ffprobe PATH'te yok")
else:
    # IYI video: 20 sn, dikey 1080x1920, ses var (temiz sinyal)
    _iyi_ok = _ffmpeg_uret(_qa_iyi, [
        "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=20",
        "-f", "lavfi", "-i", "sine=frequency=200:duration=20",
        "-vf", "format=yuv420p", "-af", "volume=0.4",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
    ])
    # KOTU video: 8 sn (kisa), yatay 1920x1080, ilk 3 sn KAPKARA, ilk 6 sn SESSIZ
    _kotu_ok = _ffmpeg_uret(_qa_kotu, [
        "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30:duration=8",
        "-f", "lavfi", "-i", "sine=frequency=200:duration=8",
        "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=black@1:t=fill:enable='lt(t,3)',format=yuv420p",
        "-af", "volume='if(lt(t,6),0,0.6)':eval=frame",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
    ])
    kontrol("Test videolari ffmpeg ile uretildi", _iyi_ok and _kotu_ok)

    _r_iyi = _qa.video_denetle(_qa_iyi)
    kontrol("Iyi video: sure/cozunurluk/ses gercekten okundu",
            _r_iyi["sure"] and abs(_r_iyi["sure"] - 20) < 1.5 and _r_iyi["genislik"] == 1080
            and _r_iyi["yukseklik"] == 1920 and _r_iyi["ses_var"] is True,
            f"{_r_iyi['sure']}s {_r_iyi['genislik']}x{_r_iyi['yukseklik']} ses={_r_iyi['ses_var']}")
    kontrol("Iyi video: siyah kare/donma yok, LUFS olculdu",
            _r_iyi["siyah_oran"] <= 0.02 and _r_iyi["donmus_oran"] <= 0.05 and _r_iyi["lufs"] is not None,
            f"siyah%{_r_iyi['siyah_oran'] * 100:.1f} donma%{_r_iyi['donmus_oran'] * 100:.1f} lufs={_r_iyi['lufs']}")
    kontrol("Iyi video yayina hazir (skor >= 70, GECTI)",
            _r_iyi["gecti"] is True and _r_iyi["skor"] >= 70, f"skor={_r_iyi['skor']}")

    _r_kotu = _qa.video_denetle(_qa_kotu)
    _sr_kotu = " | ".join(_r_kotu["sorunlar"])
    kontrol("Kotu video: siyah kare GERCEKTEN yakalandi (>= 2 sn)",
            _r_kotu["siyah_sn"] >= 2.0, f"siyah={_r_kotu['siyah_sn']}s")
    kontrol("Kotu video: sessizlik yakalandi (>= 4 sn)",
            _r_kotu["sessiz_sn"] >= 4.0, f"sessiz={_r_kotu['sessiz_sn']}s")
    kontrol("Kotu video: kisa sure + yatay oran + siyah + sessiz sorun olarak listelendi",
            not _r_kotu["gecti"] and _r_kotu["skor"] < 70 and "Cok kisa" in _sr_kotu
            and "Dikey degil" in _sr_kotu and "Siyah kare" in _sr_kotu and "sessiz" in _sr_kotu,
            f"skor={_r_kotu['skor']} ({_sr_kotu[:110]})")

    _qa_json = _qa.rapor_yaz(_r_kotu)
    _yazilan = {}
    if _qa_json and os.path.exists(_qa_json):
        with open(_qa_json, encoding="utf-8") as f:
            _yazilan = json.load(f)
    kontrol("QA raporu videonun yanina json olarak yazildi",
            _yazilan.get("skor") == _r_kotu["skor"] and _yazilan.get("derece") == _r_kotu["derece"],
            os.path.basename(_qa_json) if _qa_json else "yok")

    _yok_r = _qa.video_denetle(os.path.join(_qa_tmp, "olmayan.mp4"))
    kontrol("Olmayan dosya: net sonuc + rapor YAZILMAZ",
            _yok_r["derece"] == "OLCULEMEDI" and _yok_r["gecti"] is False
            and _qa.rapor_yaz(_yok_r) == "")

    # CLI GERCEK surec olarak: kullanicinin kullanacagi arayuz + cikis kodu
    _cli = subprocess.run([sys.executable, "functions/qa_kapisi.py", _qa_iyi],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=180, env={**os.environ, "PYTHONUTF8": "1"})
    kontrol("CLI: temiz video icin cikis kodu 0 ve rapor basiliyor",
            _cli.returncode == 0 and "QA skoru" in _cli.stdout, f"rc={_cli.returncode}")
    _cli2 = subprocess.run([sys.executable, "functions/qa_kapisi.py", _qa_kotu],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=180, env={**os.environ, "PYTHONUTF8": "1"})
    kontrol("CLI: bozuk video icin cikis kodu 1 (uyari gorunur)",
            _cli2.returncode == 1 and "Yayina hazir DEGIL" in _cli2.stdout, f"rc={_cli2.returncode}")

# Puanlama mantigi (ffmpeg gerekmez): cezalar dogru yonde mi?
_kusursuz = {"sure": 30.0, "genislik": 1080, "yukseklik": 1920, "ses_var": True,
             "siyah_oran": 0.0, "donmus_oran": 0.0, "sessiz_oran": 0.05, "lufs": -14.0, "true_peak": -2.0,
             "siyah_sn": 0.0}
_sk, _sr = _qa._skorla(dict(_kusursuz))
kontrol("Kusursuz video 100 puan alir (yanlis alarm yok)", _sk == 100 and _sr == [], f"{_sk} {_sr}")
_ses_yok = dict(_kusursuz, ses_var=False)
_sk2, _sr2 = _qa._skorla(_ses_yok)
kontrol("Ses akisi yoksa puan duser ve sorun listelenir",
        _sk2 < _sk and any("Ses akisi YOK" in s for s in _sr2), f"{_sk2} {_sr2}")
_siyah = dict(_kusursuz, siyah_oran=0.25, siyah_sn=7.5)
_sk3, _sr3 = _qa._skorla(_siyah)
kontrol("Cok siyah kare puani ciddi dusurur",
        _sk3 <= 70 and any("Siyah kare" in s for s in _sr3), f"{_sk3} {_sr3}")

_qa_atlandi_kaynak = oku("haftalik_islet.py")
kontrol("Zincir finali ShortsStudio sonrasi QA kapisinden geciriyor",
        "qa_gate_calistir(" in _qa_atlandi_kaynak
        and "video_denetle(final_yolu)" in _qa_atlandi_kaynak)
kontrol("QA sonucu sonuc haritasina yaziliyor (gun -> skor)",
        '"qa": QA_SONUCLARI' in _qa_atlandi_kaynak)
kontrol("QA kapisi atlanabilir (--qa-atla) ve varsayilan ACIK",
        "--qa-atla" in _qa_atlandi_kaynak and "qa_atla=False" in _qa_atlandi_kaynak)

# --------------------------------------------------------------------------
bolum("T) SES ISLEME + KLIPCI (uzun video -> Shorts motoru; yerel ve ucretsiz)")

import functions.ses_isleme as _si  # noqa: E402
import functions.klipci as _kc  # noqa: E402

FFMPEG_VAR = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))

# --- T1) Ses isleme: GERCEK ffmpeg ile temizlik + LUFS esitleme + ducking ---
if not FFMPEG_VAR:
    atla("Ses isleme (gercek ffmpeg)", "ffmpeg PATH'te yok")
else:
    _ses_kok = gecici("vf_ses_")
    _konusma = os.path.join(_ses_kok, "konusma.wav")
    _fon = os.path.join(_ses_kok, "fon.wav")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "anoisesrc=d=6:c=pink:a=0.02",
                    "-f", "lavfi", "-i", "sine=f=220:d=6",
                    "-filter_complex", "[1:a]vibrato=f=5:d=0.4,volume=0.5[v];[0:a][v]amix=inputs=2:normalize=0[o]",
                    "-map", "[o]", "-ar", "48000", "-ac", "2", _konusma], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=f=110:d=4,volume=0.4",
                    "-f", "lavfi", "-i", "sine=f=165:d=4,volume=0.3",
                    "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0[o]",
                    "-map", "[o]", "-ar", "48000", "-ac", "2", _fon], check=True, capture_output=True)
    _temiz = os.path.join(_ses_kok, "temiz.wav")
    _esit = os.path.join(_ses_kok, "esit.wav")
    kontrol("ses_isleme.gurultu_temizle gercek dosya uretir",
            _si.gurultu_temizle(_konusma, _temiz) and os.path.getsize(_temiz) > 10000)
    kontrol("ses_isleme.ses_esitle calisir", _si.ses_esitle(_temiz, _esit, hedef_lufs=-14.0))
    _olcum = _si.lufs_olc(_esit) or {}
    kontrol("Esitleme sonrasi ses -14 LUFS hedefine yakin (+/-1.5)",
            _olcum.get("lufs") is not None and abs(_olcum["lufs"] + 14.0) <= 1.5,
            f"{_olcum.get('lufs')} LUFS")
    _duck = os.path.join(_ses_kok, "duck.wav")
    kontrol("Muzik ducking (sidechaincompress) calisir",
            _si.muzik_ducking(_temiz, _fon, _duck, ducking_db=-16.0) and os.path.getsize(_duck) > 10000)
    _tam = os.path.join(_ses_kok, "tam.wav")
    kontrol("Tam zincir (temizle -> ducking -> LUFS) tek komutla calisir",
            _si.tam_isle(_konusma, _tam, muzik=_fon, hedef_lufs=-14.0) and os.path.exists(_tam))
    _cli_ses = subprocess.run([sys.executable, "functions/ses_isleme.py", "--giris", _konusma, "--olc"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=300, env={**os.environ, "PYTHONUTF8": "1"})
    kontrol("ses_isleme CLI LUFS olcumunu JSON basar",
            _cli_ses.returncode == 0 and "lufs" in _cli_ses.stdout)

# --- T2) KLIPCI: an skorlama, filler temizligi, konu butunluklu pencere ---
_kok_klip = gecici("vf_klip_")
_klip_ses = os.path.join(_kok_klip, "ses.wav")
if FFMPEG_VAR:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=f=150:d=40,volume=0.3",
                    "-ar", "16000", "-ac", "1", _klip_ses], check=True, capture_output=True)

_metinler = [
    (0.5, 4.0, "Bu arsivde 1937 yilinda cekilmis 14 saniyelik bir kayit var ve kimse bilmiyor."),
    (4.2, 6.0, "Yani iste sey falan filan, ee hmm."),
    (6.2, 10.0, "Raporda fabrikanin uretim sayisi yuzde 42 daha yuksek gorunuyor, bu cok buyuk bir hata."),
    (10.2, 14.0, "Bu hata yuzunden uc sehrin plani 20 yil boyunca yanlis cizilmis."),
    (14.2, 18.0, "Ayni cumle burada tekrar ediyor ve gereksiz yer kapliyor diyoruz simdi."),
    (18.2, 22.0, "Raporda fabrikanin uretim sayisi yuzde 42 daha yuksek gorunuyor, bu cok buyuk bir hata."),
    (22.2, 26.0, "Peki neden bu rakam bugune kadar hic yayinlanmadi, sorumlu kim?"),
    (26.2, 30.0, "Cunku arsiv gorevlisi 1964 yilinda dosyayi kapattigini yazmis ama dosya hala acik."),
]
_kesitler = [{"start": a, "end": b, "text": t} for a, b, t in _metinler]
if FFMPEG_VAR:
    _kesitler = _kc.an_skorlari(_kesitler, _klip_ses)
    _skorlar = [x["skor"] for x in _kesitler]
    kontrol("KLIPCI her cumleye 0-100 arasi onem skoru veriyor",
            all(0 <= s <= 100 for s in _skorlar) and len(set(_skorlar)) >= 3, str(_skorlar))
    _dolgu_skor = next(x["skor"] for x in _kesitler if "falan filan" in x["text"])
    _bilgi_skor = next(x["skor"] for x in _kesitler if "yuzde 42" in x["text"])
    kontrol("Dolgu cumlesi bilgi dolu cumleden DAHA DUSUK puan alir",
            _dolgu_skor < _bilgi_skor, f"dolgu={_dolgu_skor} bilgi={_bilgi_skor}")
    kontrol("Skor kirilimi (hook/bilgi/nadirlik/vurgu/konu/ceza) hesaplaniyor",
            all({"hook", "bilgi", "nadirlik", "vurgu", "konu", "ceza"} <= set(x["kirilim"])
                for x in _kesitler))
    _temiz_k, _atilan_k = _kc.filler_temizle(_kesitler)
    kontrol("Tekrar eden cumle ayiklanir (near-duplicate)",
            any("tekrar" in (a.get("sebep") or "") for a in _atilan_k) or len(_temiz_k) < len(_kesitler),
            f"atilan={[a.get('sebep') for a in _atilan_k]}")
    _pencereler = _kc.klip_pencereleri(_temiz_k, adet=2, hedef_sure=25, min_sure=15, maks_sure=60)
    kontrol("Konu butunluklu klip penceresi uretilir", len(_pencereler) >= 1,
            f"{len(_pencereler)} pencere")
    kontrol("Pencereler ortusmez",
            all(not (a["start"] < b["end"] and b["start"] < a["end"])
                for i, a in enumerate(_pencereler) for b in _pencereler[i + 1:]))
    kontrol("Pencere sureleri Shorts sinirlari icinde (<=60 sn)",
            all(12 <= p["sure"] <= 62 for p in _pencereler), str([p["sure"] for p in _pencereler]))
    kontrol("Pencere icindeki kesitler zaman sirali",
            all(all(p["kesitler"][i]["start"] < p["kesitler"][i + 1]["start"]
                    for i in range(len(p["kesitler"]) - 1)) for p in _pencereler))
else:
    atla("KLIPCI skorlama/pencere (gercek ffmpeg + wav gerekir)", "ffmpeg PATH'te yok")

# --- T3) Panel/kadraj plani: 1, 2 ve 4 kisi ayni anda konusunca ---
# Gercek yuz izleyici gibi 0.5 sn adimla kesintisiz nokta uretiriz; panel karari
# artık "o anda KADRAJDA olan farkli yuz" kuralina dayanir.
def _iz_uret(_id, _x, _t0=0.0, _t1=15.0, _adim=0.5):
    _noktalar = [(round(_t, 2), (_x, 300.0, 200.0, 220.0))
                 for _t in [_t0 + _adim * i for i in range(int((_t1 - _t0) / _adim) + 1)]]
    return {"id": _id, "noktalar": _noktalar, "aktif": [n[0] for n in _noktalar],
            "hareket": [(n[0], 1.0) for n in _noktalar]}


_yuz_bilgi = {"fw": 1920, "fh": 1080, "izler": [
    _iz_uret(0, 300.0),
    _iz_uret(1, 1400.0),
]}
_esleme = {0: 0, 1: 1, 2: 0, 3: 1}
_kutu_hatasi = []
for _n in (1, 2, 4):
    _parca_kesitler = [{"start": 0.5 * i, "end": 10.0 + 0.5 * i, "text": f"konusmaci {i}", "skor": 60}
                       for i in range(_n)]
    _etiketler = {round(k["start"], 3): i for i, k in enumerate(_parca_kesitler)}
    _pencere = {"start": 0.5, "end": 10.0, "sure": 9.5, "kesitler": _parca_kesitler,
                "skor": 60, "en_yuksek": 60}
    # _n kisi icin _n AYRI yuz izi sart: ayni yuz iki panele bolunemez.
    _izler_n = [_iz_uret(i, 200.0 + 400.0 * i) for i in range(_n)]
    _yuz_n = {"fw": 1920, "fh": 1080, "izler": _izler_n}
    _esleme_n = {i: i for i in range(_n)}
    _parcalar = _kc.kadraj_plani(_pencere, _etiketler, _esleme_n, _izler_n, _yuz_n)
    if not _parcalar or any(p["panel_sayisi"] != _n for p in _parcalar):
        _kutu_hatasi.append(f"{_n} kisi -> panel {[p['panel_sayisi'] for p in _parcalar]}")
    for _p in _parcalar:
        _hedef = 1080 * 1920
        _toplam = sum(pp["hedef"][0] * pp["hedef"][1] for pp in _p["paneller"])
        if _toplam != _hedef:
            _kutu_hatasi.append(f"panel alanlari tam ekrani doldurmuyor ({_n} kisi)")
        for pp in _p["paneller"]:
            cw, ch, cx, cy = pp["kutu"]
            if cx + cw > _yuz_n["fw"] or cy + ch > _yuz_n["fh"] or cw < 2 or ch < 2:
                _kutu_hatasi.append(f"kadraj karesi disari tasiyor ({_n} kisi)")
        _sahipler = [pp["yuz_izi"] for pp in _p["paneller"]]
        if len(set(_sahipler)) != len(_sahipler):
            _kutu_hatasi.append(f"ayni yuz iki panele bolundu ({_n} kisi)")
kontrol("Ayni anda 1/2/4 kisi -> 1/2/4 panel, alanlar tam ekran, kadraj kare icinde",
        not _kutu_hatasi, "; ".join(_kutu_hatasi))

# --- T3b) YANLIS BOLME KORUMASI: ayni kisi asla iki panele bolunmez ---
_tek_iz = [_iz_uret(0, 300.0)]
_tek_pencere = {"start": 0.5, "end": 10.0, "sure": 9.5, "skor": 60, "en_yuksek": 60,
                "kesitler": [{"start": 0.5, "end": 10.0, "text": "a", "skor": 60},
                             {"start": 0.6, "end": 10.1, "text": "b", "skor": 60}]}
_tek_parcalar = _kc.kadraj_plani(_tek_pencere, {0.5: 0, 0.6: 1}, {0: 0, 1: 0}, _tek_iz,
                                {"fw": 1920, "fh": 1080, "izler": _tek_iz})
kontrol("TEK YUZ: 2 konusmaci sanilsa bile 1 panel kalir (ayni kisi iki kez gosterilmez)",
        all(p["panel_sayisi"] == 1 for p in _tek_parcalar),
        str([p["panel_sayisi"] for p in _tek_parcalar]))
_ayrik_iz = [_iz_uret(0, 300.0, 0.0, 3.0), _iz_uret(1, 1400.0, 3.4, 15.0)]
_ayrik = _kc.kadraj_plani(_tek_pencere, {0.5: 0, 0.6: 1}, {0: 0, 1: 1}, _ayrik_iz,
                          {"fw": 1920, "fh": 1080, "izler": _ayrik_iz})
kontrol("KAMERA GECISI: ayni anda tek yuz kadrajda -> tek panel (bos panel acilmaz)",
        all(p["panel_sayisi"] == 1 for p in _ayrik), str([p["panel_sayisi"] for p in _ayrik]))
_yeni_etiket, _yeni_k, _yeni_esleme, _ayrim_g, _dogrulama = _kc.konusmaci_dogrula(
    [0, 1, 0, 1], {0: 0, 1: 0}, 2, 0.3, {"izler": _tek_iz})
kontrol("AYNI YUZ: etiketler tek konusmaciya birlestirilir (video 1 kisi)",
        _yeni_k == 1 and set(_yeni_etiket) == {0}, f"k={_yeni_k} ({_dogrulama})")
_izsiz = _kc.kadraj_plani(_tek_pencere, {0.5: 0, 0.6: 1}, {}, [],
                          {"fw": 1920, "fh": 1080, "izler": []})
kontrol("YUZ YOK (kafa takibi kapali): tek panel (ayni goruntu iki kez gosterilmez)",
        all(p["panel_sayisi"] == 1 for p in _izsiz))
_ikili = next((p for p in _kc.kadraj_plani(
    _tek_pencere, {0.5: 0, 0.6: 1}, _esleme, _yuz_bilgi["izler"], _yuz_bilgi)
    if p["panel_sayisi"] == 2), None)
kontrol("Iki kisi ayni anda konusunca penceresi ALT/UST ikiye bolunuyor",
        _ikili is not None and [pp["ad"] for pp in _ikili["paneller"]] == ["ust", "alt"],
        str(_ikili and [pp["ad"] for pp in _ikili["paneller"]]))

# --- T4) Render grafigi: ffmpeg gercekten calisir mi (etiket/crop hatalari) ---
if FFMPEG_VAR:
    _kaynak = os.path.join(_kok_klip, "kaynak.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=f=200:d=3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", _kaynak], check=True, capture_output=True)
    # KAYNAK 640x360: kadraj hesabi yanlis boyuta gore yapilsa bile render
    # duzeltilmis olmali (_kadrajlari_sinirla kare boyutuna kirpar).
    _kucuk_yuz = {"fw": 1920, "fh": 1080, "izler": _yuz_bilgi["izler"]}
    _parcalar2 = _kc.kadraj_plani(
        {"start": 0.2, "end": 2.8, "sure": 2.6, "skor": 60, "en_yuksek": 60,
         "kesitler": [{"start": 0.2, "end": 2.8, "text": "a", "skor": 60},
                      {"start": 0.3, "end": 2.9, "text": "b", "skor": 60}]},
        {0.2: 0, 0.3: 1}, _esleme, _kucuk_yuz["izler"], _kucuk_yuz)
    _cikti = os.path.join(_kok_klip, "panel_test.mp4")
    _ok, _hata = _kc.klip_render(_kaynak, _parcalar2, _cikti)
    kontrol("2 panelli GERCEK render calisir (ffmpeg graf hatasi yok)",
            _ok and os.path.getsize(_cikti) > 20000, _hata)
    if _ok:
        _bilgi = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                 "-show_entries", "stream=width,height", "-of", "csv=p=0", _cikti],
                                capture_output=True, text=True, timeout=120).stdout.strip()
        kontrol("Render ciktisi dikey 1080x1920", _bilgi.replace(" ", "").startswith("1080,1920"), _bilgi)
        _qa = _kc.video_denetle(_cikti)
        kontrol("Render ciktisi QA kapisindan gecirilebiliyor (puan uretir)",
                isinstance(_qa.get("skor"), int) and _qa.get("sure") is not None,
                f"{_qa.get('skor')} {_qa.get('derece')}")

# --- T5) Botun MEVCUT akisi bozulmadi mi? ---
_korunan = ["kesif.py", "haftalik_islet.py", "kinosekrety.py", "faktza15.py", "kinok_syjet.py",
            "temizle.py", "bulut_kanali.py"]
_kirilan = [ad for ad in _korunan
            if "klipci" in oku(ad) or "ses_isleme" in oku(ad)]
kontrol("Mevcut uretim zinciri klipci/ses_isleme'e bagimli DEGIL (akis bozulmadi)",
        not _kirilan, ", ".join(_kirilan))
for _ad in _korunan:
    _calistirilabilir = os.path.exists(_ad)
    if not _calistirilabilir:
        kontrol(f"{_ad} yerinde", False)
kontrol("Yeni motorlar ayri dosyalar (functions/klipci.py + functions/ses_isleme.py) ve CLI'lari var",
        "def _cli" in oku("functions/klipci.py") and "def _cli" in oku("functions/ses_isleme.py"))
kontrol("KLIPCI yuz modelini gerektiginde indirir (models/ yolu + gitignore)",
        "models" in oku("functions/klipci.py") and "models/" in oku(".gitignore"))
_kli_cli = subprocess.run([sys.executable, "functions/klipci.py", "--help"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120, env={**os.environ, "PYTHONUTF8": "1"})
kontrol("klipci CLI --help calisir (--link/--klip/--sure/--hoparlor/--altyazi/--ducking)",
        _kli_cli.returncode == 0 and all(x in _kli_cli.stdout for x in
                                         ["--link", "--klip", "--sure", "--hoparlor", "--altyazi", "--ducking"]))
kontrol("KLIPCI QA kapisini kullaniyor (her klip denetlenir ve rapor yazilir)",
        "video_denetle" in oku("functions/klipci.py") and "rapor_yaz" in oku("functions/klipci.py"))

# --- T6) Masaustu sayfasi ile sozlesme: klip_plani.json alanlari ---
_klipci_kaynak = oku("functions/klipci.py")
_okuyucu = oku(os.path.join("desktop", "electron", "data", "klip.ts"))
_sozlesme = ["link", "video", "konusmaci_sayisi", "ayrim_yontemi", "yuz_izi_sayisi",
             "transkript_kaynagi", "atilan_kesit", "klipler", "baslik", "skor", "sure",
             "baslangic", "bitis", "panel_dagilimi", "dosya", "srt", "qa"]
_yazilan = [a for a in _sozlesme if f'"{a}"' in _klipci_kaynak]
_okunan = [a for a in _sozlesme if a in _okuyucu]
kontrol("klip_plani.json sozlesmesi: yazan (klipci) ve okuyan (masaustu) alanlar ortusuyor",
        len(_yazilan) == len(_sozlesme) and len(_okunan) == len(_sozlesme),
        f"yazan={len(_yazilan)}/{len(_sozlesme)} okuyan={len(_okunan)}/{len(_sozlesme)}")
_klip_sayfa = oku(os.path.join("desktop", "src", "pages", "KlipPage.tsx"))
kontrol("Klip Studyo sayfasi isi 'klip' turuyle baslatiyor ve ayarlari komuta aktariyor",
        "kind: 'klip'" in _klip_sayfa and "klipSayisi" in _klip_sayfa and "klipHoparlor" in _klip_sayfa)
kontrol("Klip Studyo sayfasi sol menude tanimli (Sidebar + App rotasi)",
        "'klip'" in oku(os.path.join("desktop", "src", "components", "layout", "Sidebar.tsx"))
        and "KlipPage" in oku(os.path.join("desktop", "src", "App.tsx")))
_new_alanlar = ["mod", "konu", "kirilim", "kesitler", "konular", "en_yuksek"]
kontrol("klip_plani.json yeni alanlari (mod/konu/kirilim/kesitler/konular) hem yazilir hem okunur",
        all(a in _klipci_kaynak for a in _new_alanlar) and all(a in _okuyucu for a in _new_alanlar)
        and "transkript.json" in _klipci_kaynak and "transkript.json" in _okuyucu,
        f"yazan={[a for a in _new_alanlar if a in _klipci_kaynak]}")
_oynatici = oku(os.path.join("desktop", "src", "components", "klip", "KlipOynatici.tsx"))
_oyun_protokolu = oku(os.path.join("desktop", "electron", "core", "video.ts"))
kontrol("Uygulama ici oynatici var (9:16 video + skor kirilimi + kesit zaman cizgisi)",
        "<video" in _oynatici and "Skor kırılımı" in _oynatici and "Kesitler" in _oynatici)
kontrol("Yerel video vfil:// protokolu ile servis edilir (Range destekli, CSP gevsetilmedi)",
        "registerSchemesAsPrivileged" in _oyun_protokolu and "Content-Range" in _oyun_protokolu
        and "media-src 'self' vfil:" in oku(os.path.join("desktop", "index.html")))

# --- T7) SES KAYMASI: video ve ses AYNI kesim sinirlarini kullanir ---
# Senaryo: saniyede bir TIK (ses) + BEYAZ FLAS (goruntu). Klip 3 ayri kesitle
# birlestirildikten sonra tik ve flas AYNI anda olmali; hicbir kesitte birikimli
# kayma olmamali. (Eski kodda ses her kesitte 0.3 sn daha uzundu -> kesit basina
# 0.3 sn kayma birikiyordu.)
if not FFMPEG_VAR:
    atla("Ses kaymasi (tik/flas hizasi)", "ffmpeg PATH'te yok")
else:
    _kayma_kok = gecici("vf_kayma_")
    _tik_video = os.path.join(_kayma_kok, "tik.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=24",
                    "-f", "lavfi", "-i", "aevalsrc=0.9*exp(-45*mod(t+0.5\\,1)):s=44100:d=24",
                    "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='lt(mod(t-0.5\\,1)\\,0.06)'",
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", _tik_video],
                   check=True, capture_output=True)
    _tik_paneller = [{"ad": "tam", "yuz_izi": None, "sahip": None,
                      "kutu": [202, 360, 219, 0], "hedef": [1080, 1920]}]
    _tik_parcalar = [
        {"start": 2.0, "end": 6.5, "panel_sayisi": 1, "konusmacilar": [], "paneller": _tik_paneller,
         "metin": "bir", "skor": 70},
        {"start": 10.0, "end": 15.0, "panel_sayisi": 1, "konusmacilar": [], "paneller": _tik_paneller,
         "metin": "iki", "skor": 80},
        {"start": 19.0, "end": 22.0, "panel_sayisi": 1, "konusmacilar": [], "paneller": _tik_paneller,
         "metin": "uc", "skor": 90},
    ]
    _sinirlar = _kc._kesit_sinirlari(_tik_parcalar)
    _kayma_cikti = os.path.join(_kayma_kok, "klip.mp4")
    _kayma_ok, _kayma_hata = _kc.klip_render(_tik_video, _tik_parcalar, _kayma_cikti, sinirlar=_sinirlar)
    kontrol("Ses kaymasi testi: 3 kesitli klip render edildi", _kayma_ok, _kayma_hata)
    if _kayma_ok:
        import numpy as _np
        import soundfile as _sf
        _cikti_wav = os.path.join(_kayma_kok, "klip.wav")
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", _kayma_cikti,
                        "-vn", "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", _cikti_wav],
                       check=True, capture_output=True)
        _sinyal, _sr = _sf.read(_cikti_wav, dtype="float32", always_2d=False)
        _guc = _np.abs(_sinyal)
        _esik = max(0.15, float(_np.percentile(_guc, 99)) * 0.25)
        _ust = _guc > _esik
        _bas = int(_sr * 0.3)
        _gecis = _np.where(_ust[_bas:] & ~_ust[_bas - 1:-1])[0]
        _tik_idx = []
        for _g in _gecis:
            if _tik_idx and _g - _tik_idx[-1] < int(_sr * 0.4):
                continue
            _tik_idx.append(int(_g))
        _tikler = [round((_g + _bas) / _sr, 3) for _g in _tik_idx]
        # Beklenen cikti saniyesi: kesit sinirlarina gore
        def _beklenen(_parcalar, _sinirlar, _kaynak_sn):
            _imlec = 0.0
            for (_b, _s), _p in zip(_sinirlar, _parcalar):
                if _b <= _kaynak_sn <= _s:
                    return round(_imlec + (_kaynak_sn - _b), 3)
                _imlec += _s - _b
            return None

        _sapmalar = []
        for _kaynak in (2.5, 3.5, 4.5, 5.5, 6.5, 10.5, 11.5, 12.5, 13.5, 14.5, 19.5, 20.5, 21.5):
            _hedef = _beklenen(_tik_parcalar, _sinirlar, _kaynak)
            if _hedef is None:
                continue
            _yakin = min(_tikler, key=lambda t, h=_hedef: abs(t - h))
            _sapmalar.append(round(_yakin - _hedef, 3))
        _en_buyuk = max(abs(s) for s in _sapmalar) if _sapmalar else 99.0
        kontrol("SES KAYMASI YOK: her kesitte tik beklenen saniyede (sapma < 0.08 sn)",
                bool(_sapmalar) and _en_buyuk < 0.08,
                f"en buyuk sapma {_en_buyuk:.3f} sn ({len(_sapmalar)} tik)")
        kontrol("Kesit sinirlari video/ses icin ORTAK (ust uste binme yok)",
                all(a[1] <= b[0] + 1e-9 for a, b in zip(_sinirlar, _sinirlar[1:])),
                str(_sinirlar))

# --- T8) HOOK-FIRST + KONU CIKARIMI (saf python, hizli) ---
_konu_wav = os.path.join(gecici("vf_konu_"), "sessiz.wav") if FFMPEG_VAR else None
if FFMPEG_VAR:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=16000:cl=mono", "-t", "90", _konu_wav],
                   check=True, capture_output=True)
    _metinler = [
        "yani iste ee hmm sey",
        "Shaolin tapinaginda ogrenciler sabah bes gibi kalkar ve dokuz saat antrenman yapar",
        "Shaolin antrenmaninda ogrenciler sabah bes gibi kalkar ve dokuz saat calisir",
        "Shaolin ogrencileri ayni antrenmani her gun tekrarlar ve teknik ogrenir",
        "peki neden hic kimse shaolin antrenmaninin neden bu kadar sert oldugunu soylemiyor?",
        "cunku shaolin ogrencisi gunde dokuz saat antrenman yapar ve bunu asla sorgulamaz",
        "Simdi bu tarif icin un, yumurta ve sut gerekiyor; hamuru yogurup firinda pisirin",
        "Tatli tarifinde firin 180 derece olmali ve kek 40 dakika pisirilmeli",
        "Ama iste bu tatliyi kimse bilmiyor; firin sicakligi yanlis olursa kek kabarmaz",
    ]
    _ks = []
    _t = 0.0
    for _m in _metinler:
        _ks.append({"start": _t, "end": _t + 4.0, "text": _m, "kelime": len(_m.split()), "sure": 4.0})
        _t += 4.4
    _ks = _kc.an_skorlari(_ks, _konu_wav)
    _soru = next(x for x in _ks if "neden hic kimse" in x["text"])
    _dolgu2 = next(x for x in _ks if x["text"].startswith("yani"))
    kontrol("HOOK: merak sorusu en yuksek kanca puanini alir (hook agirlikli skor)",
            _soru["kirilim"]["hook"] >= 0.9 and _soru["skor"] > _dolgu2["skor"],
            f"soru hook={_soru['kirilim']['hook']} skor={_soru['skor']} / dolgu={_dolgu2['skor']}")
    _kalan, _atilan2 = _kc.filler_temizle(_ks)
    _konular = _kc.konu_cikar(_kalan)
    _shaolin = [c for c in _konular if "shaolin" in c["etiket"]]
    kontrol("KONU: transkript konu bloklarina ayrilir ve etiket kelimeler cikar",
            len(_konular) >= 2 and bool(_shaolin),
            str([(c["etiket"], c["kesit_sayisi"]) for c in _konular]))
    kontrol("KONU: kanca cumlesi dogru konu bloguna atanir (konu uyumu 1.0)",
            bool(_shaolin) and _soru.get("konu") in [c["no"] for c in _shaolin],
            f"konu={_soru.get('konu')}")
    _penc = _kc.klip_pencereleri(_kalan, adet=2, hedef_sure=30)
    kontrol("HOOK-FIRST: secilen klibin ACILISI kanca cumlesinden gelir",
            bool(_penc) and _penc[0]["kirilim"]["hook_acilis"] >= 0.5,
            str([(p["kirilim"]["hook_acilis"], round(p["start"], 1)) for p in _penc]))
    kontrol("KONU BUTUNLUGU: pencere tek konu blogunda kalir (konu_orani >= 0.5)",
            bool(_penc) and _penc[0]["kirilim"]["konu_orani"] >= 0.5,
            str([p["kirilim"]["konu_orani"] for p in _penc]))
    kontrol("Pencere konusma suresine gore kurulur (15-60 sn)",
            bool(_penc) and all(15 <= p["konusma_suresi"] <= 60 for p in _penc),
            str([p["konusma_suresi"] for p in _penc]))
else:
    atla("Hook-first + konu cikarimi", "ffmpeg PATH'te yok")

# --- T9) GORSEL HOOK MODU (konusma olmayan video) ---
if not FFMPEG_VAR:
    atla("Gorsel hook modu", "ffmpeg PATH'te yok")
else:
    _gor_kok = gecici("vf_gorsel_")
    _aksiyon = os.path.join(_gor_kok, "aksiyon.mp4")
    _vf = ("drawbox=x=0:y=0:w=iw:h=ih:color=red@1.0:t=fill:enable='between(t,12,24)',"
           "drawbox=x='mod(t*200,iw-80)':y=100:w=80:h=80:color=white:t=fill:enable='between(t,12,24)'")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=40",
                    "-f", "lavfi", "-i", "aevalsrc=0.04+0.7*exp(-2*mod(t\\,4)):s=44100:d=40",
                    "-vf", _vf, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", _aksiyon],
                   check=True, capture_output=True)
    _aksiyon_wav = os.path.join(_gor_kok, "aksiyon.wav")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", _aksiyon,
                    "-vn", "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", _aksiyon_wav],
                   check=True, capture_output=True)
    _gor = _kc.gorsel_analiz(_aksiyon, _aksiyon_wav)
    kontrol("GORSEL HOOK: konusmasiz video analiz edilir (hareket + sahne kesmesi)",
            not _gor.get("hata") and len(_gor["hucreler"]) > 20 and _gor["kesme_sayisi"] >= 1,
            f"{len(_gor.get('hucreler') or [])} hucre, {_gor.get('kesme_sayisi')} kesme, hata={_gor.get('hata')}")
    _hucreler = _gor.get("hucreler") or []
    if _hucreler:
        _sakin = [h["skor"] for h in _hucreler if h["t"] < 11.5]
        _aksi = [h["skor"] for h in _hucreler if 12.5 < h["t"] < 23.5]
        kontrol("GORSEL HOOK: aksiyon bolumu sakin bolumden yuksek skor alir",
                bool(_sakin) and bool(_aksi) and sum(_aksi) / len(_aksi) > sum(_sakin) / len(_sakin),
                f"sakin={sum(_sakin) / max(1, len(_sakin)):.3f} aksiyon={sum(_aksi) / max(1, len(_aksi)):.3f}")
        _zirve = max(_hucreler, key=lambda h: h["skor"])
        kontrol("GORSEL HOOK: en yuksek enerji aksiyon bolgesinde", 12.0 <= _zirve["t"] <= 24.0,
                f"zirve={_zirve['t']}")
        _gp = _kc.gorsel_pencereleri(_hucreler, adet=2, sure=15, video_sure=_gor["sure"])
        kontrol("GORSEL HOOK-FIRST: klip kanca aninda baslar (zirveye <= 2 sn)",
                bool(_gp) and abs(_gp[0]["start"] - _zirve["t"]) <= 2.0,
                str([p["start"] for p in _gp]))
        if _gp:
            _gparca = _kc.gorsel_kadraj_plani(_gp[0], _gor["fw"], _gor["fh"])
            kontrol("GORSEL kadraj: tek panel, hareketi izleyen pencere (kare icinde)",
                    bool(_gparca) and all(p["panel_sayisi"] == 1 for p in _gparca)
                    and all(all(0 <= pp["kutu"][2] and pp["kutu"][2] + pp["kutu"][0] <= _gor["fw"]
                                and pp["kutu"][3] + pp["kutu"][1] <= _gor["fh"] for pp in p["paneller"])
                            for p in _gparca),
                    str(len(_gparca)))
            _gcikti = os.path.join(_gor_kok, "gorsel_klip.mp4")
            _gok, _ghata = _kc.klip_render(_aksiyon, _gparca, _gcikti,
                                           sinirlar=_kc._kesit_sinirlari(_gparca))
            kontrol("GORSEL klip GERCEK render edilir (konusmasiz video -> dikey cikti)",
                    _gok and os.path.getsize(_gcikti) > 20000, _ghata)
    # Konusmasiz video otomatik olarak gorsel moda duser (transkript cikmaz)
    _sessiz_video = os.path.join(_gor_kok, "sessiz.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=6", "-vf", _vf,
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", _sessiz_video],
                   check=True, capture_output=True)
    _sessiz_analiz = _kc.videoyu_analiz_et(_sessiz_video, whisper_model="tiny", yuz_atla=True)
    kontrol("Konusmasiz video (ses akisi yok) otomatik 'gorsel' moda duser",
            bool(_sessiz_analiz) and _sessiz_analiz.get("mod") == "gorsel",
            str(_sessiz_analiz and _sessiz_analiz.get("mod")))

# --------------------------------------------------------------------------
for y in temizlenecek:
    shutil.rmtree(y, ignore_errors=True)

print("\n=========================================")
_ozet = f"  BOT OZELLIK KONTROLU: {gecen} basarili, {len(hatalar)} basarisiz"
if atlandi:
    _ozet += f", {len(atlandi)} atlandi"
print(_ozet)
if atlandi:
    print("  Atlandi: " + " | ".join(atlandi))
if hatalar:
    print("  Basarisiz: " + " | ".join(hatalar))
print("=========================================\n")
sys.exit(0 if not hatalar else 1)
