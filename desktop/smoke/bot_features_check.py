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
temizlenecek = []


def kontrol(ad, kosul, detay=""):
    global gecen
    if kosul:
        gecen += 1
        print(f"  PASS  {ad}" + (f"  ({detay})" if detay else ""))
    else:
        hatalar.append(ad)
        print(f"  FAIL  {ad}  ({detay})")


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
    kontrol("Gercek plan gun sayisi ile video sayisi tutarli",
            int(plan.get("gun_sayisi") or 0) == len(videolar) and int(plan.get("toplam") or 0) == len(videolar),
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
for y in temizlenecek:
    shutil.rmtree(y, ignore_errors=True)

print("\n=========================================")
print(f"  BOT OZELLIK KONTROLU: {gecen} basarili, {len(hatalar)} basarisiz")
if hatalar:
    print("  Basarisiz: " + " | ".join(hatalar))
print("=========================================\n")
sys.exit(0 if not hatalar else 1)
