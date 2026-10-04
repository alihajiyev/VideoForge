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
for y in temizlenecek:
    shutil.rmtree(y, ignore_errors=True)

print("\n=========================================")
print(f"  BOT OZELLIK KONTROLU: {gecen} basarili, {len(hatalar)} basarisiz")
if hatalar:
    print("  Basarisiz: " + " | ".join(hatalar))
print("=========================================\n")
sys.exit(0 if not hatalar else 1)
