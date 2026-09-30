# VideoForge Desktop

VideoForge botunun (Python/Modal) masaüstü arayüzü. **Bot mantığı değiştirilmedi** — uygulama
mevcut Python giriş noktalarını alt süreç olarak çalıştırır, çıktısını canlı log olarak akıtır ve
üretilen dosyaları (video, ses, kapak, SEO raporu) tek yerden yönetir.

## Teknoloji

- Electron 44 (frameless pencere, contextIsolation)
- React 19 + Vite 7 + Tailwind CSS 4 + TypeScript (strict)
- Koyu/açık tema (token tabanlı tasarım sistemi, `src/styles/globals.css`)
- Yerel `better-sqlite3` yok: `bot.db` okuma/yazma Python stdlib `sqlite3` ile yapılır

## Kurulum

```bash
cd desktop
npm install
npm run dev        # gelistirme (vite + electron)
npm run build      # uretim derlemesi
npm run package    # Windows kurulum + portable -> release/
npm run release    # surum numarasini yukseltip paketler ve GitHub'a yukler (--dry ile deneme)
npm run typecheck  # tsc --noEmit
npm run test:smoke # uctan uca arayuz testi (265 kontrol) - asagiya bakin
npm run test:bot   # bot tarafi ozellik testi (108 kontrol, ag/GPU kullanmaz)
npm run test:all   # typecheck + test:bot + test:smoke
```

## Testler

`npm run test:smoke` gercek Electron ana surecinde 265 kontrol calistirir:

- Python tespiti, ortam kontrolu, `bot.db` okuma, `constants.py` ayristirma, Masaustu taramasi, log/plan okuma
- Log ayristirici (ANSI, seviye, asama, cikti dosyasi, istatistik yakalama)
- Uretilen bot komutlarinin birebir dogrulanmasi (modal run / kesif / haftalik zincir / temizleyici)
- Girdi korumalari (gecersiz link, VideoForge olmayan klasor, olmayan klasor)
- **Gecici klasorde sahte bot ile tam is akisi**: canli log akisi, asama ilerlemesi, cikti tespiti, iptal (taskkill)
- **Gizli BrowserWindow ile gercek renderer testi**: preload koprusu, IPC cagrilari, React render,
  sayfa gecisi, tema degisimi, arayuzden is baslatma, yol korumasi, konsol hatasi kontrolu
- **Tum sayfalar tek tek**: menu butonlariyla Panel/Calistir/Kutuphane/Cikti/Kesif/Loglar/Ayarlar
  gezilir, her sayfanin icerigi gercekten cizildiginden emin olunur (konsol hatasi sifir olmali)
- **Pencere kontrolleri**: kucult/buyut/geri kucult/durum sorgusu ve ayri bir pencerede kapatma
- **Tum IPC kanallari**: ayar okuma/yazma, tema, motor karakter limiti (kopya bot.db uzerinde),
  islem gecmisi, bos islem iptali, cikti onizlemesi, yol korumalari, guncelleme kontrolu
- **Kutuphane kaydi silme**: gercek `bot.db` kopyasi uzerinde siler, gercek dosyaya dokunmadigini dogrular
- **Ikon/kurulum**: `logo.ico`'nun paketli exe'ye gomuldugu ve `logo.png`'nin `file://` altinda
  yuklendigi (naturalWidth) kontrol edilir; NSIS sihirbaz ayarlari dogrulanir
- **Guncelleme sistemi**: surum karsilastirma, gecersiz depo, private depo icin token'li gercek
  GitHub kontrolu ve gercek kurulum dosyasi indirmesi, indirme/baslatma yol korumalari
- **Bot kodu guncellemesi (git)**: dal/commit okuma, fetch'li uzak fark (geride/ileride yonu),
  gercek `git pull --ff-only` ile dosya yenileme, kirli agacta ve ust depoda reddetme

`npm run test:bot`, ag/GPU kullanmadan bot tarafini dogrular (108 kontrol): kesif gun sayisi,
zincir/kilit, durdurma isareti, Gun klasoru girdileri, **GPU parca/maliyet planlayici
(`functions/maliyet.py`)**, **tek akis (VideoForge -> ShortsStudio, kopyalama yok)**, bulut secret
mimarisi ve bosa harcama duzeltmeleri (tek SEO kurulumu, TTS dogrulama bayragi, yinelenen
Gemini cagrisi, Zapcap 4xx tekrar denemesi).

Test gercek botu ve API kotalarini kullanmaz (sahte bot dosyalari + gecici `userData`);
depo/indirme testleri ise gercek GitHub deposunu ve oradaki surumu kullanir.

Kurulum/sorun teshisi icin `VF_DIAG=1` ortam degiskeni ile calistirilirsa uygulama, renderer
istatistiklerini (dugum sayisi, IPC yanit sureleri) `%APPDATA%/VideoForge/videoforge-gui.log`
dosyasina yazar.

## Bot ile ilişkisi

Uygulama `python -X utf8 -m modal run <kanal dosyası> --link <url>` komutlarını çalıştırır:

| Islem | Komut |
|---|---|
| Kanal 1 (Kino Sekrety) | `modal run kinosekrety.py --link ...` |
| Kanal 2 (Fakt Za 15) | `modal run faktza15.py --link ...` |
| Kanal 3 (PopkornFakty) | `modal run kinok_syjet.py --link ...` |
| Kesif (tek seferlik) | `python kesif.py --chn <n> --evet` |
| Cok gunlu plan | `python kesif.py --haftalik <N> --chn <n> --evet` |
| Cok gunlu zincir | `kesif.py --haftalik <N> --chn <n> --evet` → `haftalik_islet.py --evet` |

> **Gun sayisi secilebilir (7 sabit degil).** "Kac gunluk plan?" alani **hem Panel hem Kesif**
sayfasinda vardir (ayni bilesen; hazir secenekler 3/7/10/14/30). `N=10` secilince 10 video bulunur,
plan `haftalik_plan.json`'a 10 gun olarak yazilir, zincir 10 videoyu sirayla isler. Alan `ayarlar`
dosyasinda saklanir (`gunSayisi`, 2-60), yazdiktan ~0.4 sn sonra kendiliginden kaydedilir; Panel'de
"N gunluk plan olustur" / "N gunluk zincir" dugmeleri ve Kesif sayfasi ayni sayiyi gosterir.
> Hafta gunu adlari 7'den sonra bastan dongu yapar. `gunSayisi` alani `JobRequest` icinde tasinir
> ve `normalGunSayisi()` ile dogrulanir (gecersiz deger -> 7, ust sinir -> 60).
| Temizleyici | `modal run temizle.py --link ...` |

- Bot klasoru varsayilani: gelistirmede depo koku, paketli uygulamada `Masaustu\VideoForge`
  (Ayarlar'dan degistirilebilir).
- Python yorumlayicisi `py -3` → `python` → `python3` sirasiyla otomatik bulunur.
- Ortam kontrolleri: Python surumu, bot dosyalari, modal, google-genai, elevenlabs, yt-dlp,
  ffmpeg/ffprobe, `cookies.txt` tazeligi, Modal oturumu (`~/.modal.toml`).

## Guncelleme sistemi

Ayarlar sayfasinda iki guncelleme bolumu vardir:

1. **Uygulama guncellemesi** — GitHub deposundaki en son surumu (`releases/latest`) okur; yeni surum
   varsa notlari ve `.exe` dosyalarini gosterir, ilerleme cubuguyla indirir, "Yeni surumu baslat"
   ile kurulumu acar. `Acilista otomatik kontrol et` anahtari kapatilabilir.
   - Depo private ise Ayarlar'a `repo` yetkili bir GitHub token girilir (token sadece makinede
     saklanir, surum isteklerinde `Authorization` basligi olarak kullanilir).
   - Ayni surum varsa "Uygulama guncel (surum)" yazar.
2. **Bot kodu guncellemesi (git)** — bot klasorunun dalini, son commit'ini, uzak depo farkini
   (geride/ileride) ve yerel degisiklikleri gosterir; `git pull --ff-only` ile kodu yeniler.
   Yerel degisiklik varsa veya klasor kendi deposu degilse (ust klasordeki baska bir depoya aitse)
   islem guvenlik icin reddedilir.

### Surum yayinlama

```bash
npm run release              # patch surumu yukseltir (1.0.0 -> 1.0.1), derler, GitHub'a yayinlar
npm run release -- minor     # minor surum
npm run release -- --dry     # hicbir sey yayinlamaz, sadece derler ve plani yazar
npm run release -- --no-bump # surumu yukseltmeden mevcut surumu (ilk surum) yayinlar
npm run release -- --skip-build --upload-only   # derlemeden yeniden yukler
```

Arac `git commit` + `git tag vX.Y.Z` + `git push` yapar, sonra `gh release create` ile kurulum
(nsis) ve portable `.exe` dosyalarini surum olarak yukler. Ayni surum tekrar yayinlanirsa dosyalar
`--clobber` ile guncellenir. Not: 106 MB'lik kurulum dosyalari depoya degil, surum (release)
eklerine yuklenir - GitHub'in 100 MB'lik dosya siniri bu yuzden sorun olmaz.

## Guvenlik

- **API anahtarlari kodda tutulmaz**: `GEMINI_API_KEYS`, `ELEVENLABS_API_KEY`, `TRANSCRIPT_API_KEY`
  depo kokundeki `.env` dosyasindan okunur (`.env` git'e girmez, `.env.example` sablonu vardir).
  Modal gorevlerine `videoforge-env` adli **isimli** Modal secret'i ile enjekte edilir
  (`python bulut_kurulum.py` `.env`'i bu secret'e kopyalar/gunceller).
- **Kosullu Modal nesnesi yok**: secret listesi sabittir; `.env` dosyasinin varligina gore
değismez. Eskiden kosullu tanim yuzunden fonksiyon lokalde 3, konteynerde 2 bagimlilik
hesapliyor ve `Function has 2 dependencies but container got 3 object ids` hatasi aliniyordu.
- Ortam kontrolu ve dosya islemleri yalnizca `Masaustu` ve VideoForge klasoru altindaki yollara izin
  verir. Renderer'da Node entegrasyonu kapali; tum yetkiler `preload.ts` icindeki dar IPC yuzeyinden gecer.
- Guncelleme dosyasi yalnizca uygulamanin kendi indirme klasorunden ve sadece `.exe`/`.msi`
  uzantisiyla baslatilabilir.
- Depo kokundeki `gonder.py`, commit oncesi dosyalarda anahtar benzeri metin arar ve bulursa
  gonderimi durdurur.

## Dokumanlar

- `docs/ANALIZ.md` — bot incelemesi: mantik hatalari, prompt onerileri, yol haritasi.
- `../README.md` — depo geneli: bot kurulumu, `.env`, GitHub'a guncelleme gonderme.
