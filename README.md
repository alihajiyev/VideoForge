# VideoForge

YouTube videolarini indirip temizleyen, seslendiren ve SEO raporu ureten bot + masaustu uygulamasi.

- **Bot (Python / Modal)** — 4 adimli islem hattinin tamami bulutta GPU ile calisir: indirme → transkript
  (ucretsiz altyazi veya Modal Whisper) → Gemini metin (seslendirme metni, baslik, etiket, Turkce ceviri)
  → ElevenLabs TTS → ProPainter GPU temizleme → YuNet yuz + CLIP konu kapagi → SEO HTML.
- **Masaustu uygulamasi (`desktop/`)** — Electron 44 + React 19 + Tailwind 4 arayuz. Bot mantigina
  dokunmaz; mevcut Python giris noktalarini alt surec olarak calistirir, canli log akitir, uretilen
  dosyalari ve gecmisi tek yerden yonetir. Ayrintilar: `desktop/README.md`.

## Kanallar

| # | Kanal | Dosya | Islem |
|---|---|---|---|
| 1 | Kino Sekrety (Film Sirlari) | `kinosekrety.py` | `modal run kinosekrety.py --link <url>` |
| 2 | Fakt Za 15 (Ilginc Bilgiler) | `faktza15.py` | `modal run faktza15.py --link <url>` |
| 3 | PopkornFakty (Film Hikayeleri) | `kinok_syjet.py` | `modal run kinok_syjet.py --link <url>` |

Kesif/otomatik secim: `kesif.py --chn <n> --evet` (tek seferlik oneri) ·
Cok gunlu plan: `kesif.py --gun <N> --chn <n> --evet` · Zincir: `haftalik_islet.py --evet`

> **Gun sayisi sabit degil.** `--gun 10` (ya da `--haftalik 10`) yazinca 10 gunluk plan kurulur ve
> zincir 10 video isler. `--haftalik` tek basina yazilirsa `kesif_config.json` icindeki `gun_sayisi`
> (varsayilan 7) kullanilir. Ust sinir 60'tir. Hafta gunu adlari 7'den sonra bastan dongu yapar
> (8. gun Pazartesi, 9. gun Sali...).

## Kurulum

```bash
pip install -r requirements.txt
copy .env.example .env      # sonra .env icine kendi anahtarlarini yaz
py -3 -m modal setup        # Modal oturumu (ilk seferde)
py -3 bulut_kurulum.py      # anahtarlari Modal'a "videoforge-env" secret'i olarak kopyala
```

### Anahtarlar (`.env`)

`GEMINI_API_KEYS` (virgulle ayrilmis, kota siralamasi icin), `ELEVENLABS_API_KEY`, `TRANSCRIPT_API_KEY`.

> `.env` **depoya girmez** (`.gitignore`). Anahtarlar koda yazilmaz; `constants.py` bunlari ortamdan
> okur, `bulut_kurulum.py` bunlari Modal'daki **isimli** `videoforge-env` secret'ine kopyalar.
> Bulut fonksiyonlari bu secret'i `modal.Secret.from_name` ile referans verir.
> Bu depo private tutulur ve anahtarlar sohbet/commit gecmisinde tutulmaz.

#### Neden isimli secret? (Modal bagimlilik hatasi)

Eskiden secret **kosullu** tanimlaniyordu (`dosya varsa ekle`). `.env` lokalde var, Modal imajinda
YOK; bu yuzden fonksiyonun bagimlilik listesi lokalde 3, konteynerde 2 nesne olurdu:

```
modal.exception.ExecutionError: Function has 2 dependencies but container got 3 object ids.
```

Her bulut cagrisi ~40 saniye boyunca tekrar tekrar denenip basarisiz oluyordu. Isimli secret her iki
ortamda da daima 1 bagimlilik uretir. `bulut_kanali.py` ayrica `retries=0` ile acik kayitlidir,
boylece gercek bir hata aninda ve net gorunur.

Anahtarlari `.env` icinde degistirdikten sonra `py -3 bulut_kurulum.py --zorla` calistir
(script anahtarlar degismediyse ag cagrisi yapmaz, otomatik olarak algılar).

## Calistirma

```bash
py -3 -X utf8 -m modal run kinosekrety.py --link https://youtu.be/XXXX
py -3 -X utf8 -m modal run faktza15.py --link https://youtu.be/XXXX --force
py -3 -X utf8 -m modal run kinok_syjet.py --link https://youtu.be/XXXX --gun 2 --gun-toplam 7
```

Ciktilar Masaustu'ne yazilir: `*_CLEAN.mp4`, `*_VOICEOVER.mp3`, `*_THUMB.png`, `*_SEO.html`
(cok gunlu modda `Gun<N>_<baslik>_<rastgele>/` klasoru). ShortsStudio montaji bitince
`final_XXXXXX.mp4` de **ayni klasore** tasinir: her gunun TUM ciktisi tek klasordedir,
masaustu kokunde ayri final dosyasi birikmez.

Masaustu arayuzu icin:

```bash
cd desktop
npm install
npm run dev            # gelistirme
npm run package        # Windows kurulum + portable exe
npm run test:smoke     # 314 kontrol, uctan uca test (Electron ana sureci)
npm run test:bot       # 319 kontrol, Python tarafi (kesif/zincir/QA/ses isleme/klip motoru)
npm run check:klip-ui  # gercek arayuz: Klip Studyo formu + oynatici (ag + gercek klipci kosusu)
```

## Performans geri bildirimi (opsiyonel, salt-okuma)

Bot, urettigi videolarin algoritmada **neyin tuttugunu** artik okuyabiliyor. Bunun icin API,
OAuth veya yukleme GEREKMEZ (shadowban riski yok):

1. YouTube Studio > **Icerik** sayfasi > **Disa aktar** (CSV) ile kendi kanalinin verisini indir.
2. `.csv` dosyalarini `VideoForge/performans_csv/` klasorune birak (kanal bazli ayirmak icin
   `performans_csv/kanal1/`, `kanal2/`, `kanal3/`). Hem Ingilizce hem Turkce Studio basliklari okunur.
3. Bir kez calistir: `py -3 functions/performans.py`

Bu adim `performans.json` uretir: video bazli izlenme/CTR/izlenme yuzdesi + **kazanilan kaliplar**
(kazanan videolarin basliklarinda gecip kaybedenlerde gecmeyen kelimeler). Sonrasinda:

- `kesif.py` adaylari siralarken kanitli temaya **deterministik bonus** verir (en fazla +1.0 puan);
  kaliplar hem siralama promptuna hem stil profiline girer.
- Baslik uretimi ayni kaliplari prompta ekler (basliklar tahmin yerine gercek veriye yaslanir).

Veri yoksa hicbir davranis degismez. Tazeleme: yeni CSV'leri klasore birak, 3. adimi tekrarla.

## Yayin oncesi QA kapisi

ShortsStudio montaji biter bitmez final dosya **gercekten olculur** (yerel ffmpeg, ag yok):

| Olcum | Ne yakalar |
|---|---|
| sure + en-boy orani | 15 sn alti / 60 sn ustu, dikey olmayan cikti |
| siyah kare (blackdetect) | siyah acilis, eksik render |
| donmus kare (freezedetect) | takilan sahne |
| sessizlik (silencedetect) | kopuk / bos ses |
| ses seviyesi (ebur128 LUFS) | hedef -14 LUFS'tan uzak ses (cok kisik/yuksek) |

Puan 100 uzerinden hesaplanir; 70 altinda **uyari** verir ve duzeltme komutunu basar
(`python haftalik_islet.py --yeniden-gun N` ya da `--sadece-studio N --chn X`). Otomatik harcama
YAPMAZ, karar sende kalir. Rapor finalin yanina `<final>_qa.json` olarak yazilir. Tek video denemek icin:

```bash
py -3 functions/qa_kapisi.py "C:\Users\...\Gun1_...\final_123456.mp4"
```

QA adimini atlamak icin zincire `--qa-atla` ekle.

## Klip Studyo (uzun video → Shorts)

Masaustu uygulamasindaki **Klip Studyo** sayfasi, elindeki uzun videoyu (roportaj, podcast, belgesel)
OpusClip mantigiyla dikey Shorts'lara cevirir — tamami yerel ve ucretsiz:

```bash
py -3 -X utf8 functions/klipci.py --link "https://youtube.com/watch?v=XXXX" --klip 3 --sure 45
py -3 -X utf8 functions/klipci.py --link "https://youtube.com/watch?v=XXXX" --klip 0 --sure 0  # OTOMATIK
py -3 -X utf8 functions/klipci.py --yerel "C:\\video\\reportaj.mp4" --plan-sadece   # sadece analiz
```

**Otomatik mod (`--klip 0 --sure 0`, masaüstünde varsayılan):** kaç klip üretileceğine video karar verir —
skoru yüksek **bütün ilginç sahneler** üretilir (en fazla 20 klip), zayıf sahneler atlanır; süre de içeriğe
göre ayarlanır (anlatım güçlüyse klip uzar, ilgi düşerse kapanır, **en fazla 90 sn**). Yani "5 ilginç sahne
varken 3 klip seçip 2 sahneyi boşa atmak" olmaz.

1. **Zamanli transkript** cikarilir (yt-dlp altyazisi → Transcript API → yerel Whisper): hangi saniyede
   ne konusuldugu belli olur.
2. **Konu bloklari** (TF-IDF kumeleme) + her cumleye **hook-first skor**: kanca cumlesi %40 agirlik,
   ardindan bilgi yogunlugu, nadirlik (TF-IDF), ses vurgusu ve konuya uyum. Dolgu/tekrar cumleleri atilir.
3. **Sahne plani**: kanca cumlesi klibin ilk 8 saniyesinde kalacak sekilde, konusma suresi uzerinden
   (15-60 sn) ve **tek konu blogu** icinde kurulur; pencereler asla ortusmez.
4. **Panel plani**: kac kisi **ayni anda kadrajda** ise o kadar panel (1/2/3/4). Ayni yuze dusen
   konusmacilar tek kisiye birlesir; boylece tek kisilik video iki panele bolunmez.
5. **Gorsel hook modu**: konusma yoksa (or. savas/aksiyon sahnesi) sahne kesmesi + hareket + ses enerjisi
   ile hook bulunur, kadraj hareket merkezini izler.
6. **Ses**: `afftdn` temizlik + `loudnorm` (-14 LUFS) + istege bagli fon muzigi ducking. Video ve ses
   **ayni kesim sinirlarini** kullanir (kesit basina kayma olmaz).
7. **Otomatik secim**: sayı/süre otomatikken motor en iyi pencereye göre **göreli skor eşiği** hesaplar;
eşiği geçen bütün sahneler üretilir, zayıflar atlanır (`plan.oto`: aday / seçilen / atlanan / eşik).
8. **QA kapisi**: her klip olculur (siyah kare, donma, sessizlik, LUFS, sure) ve `klip_plani.json`'a yazilir.

Cikti klasoru: `Masaustu/Klipler/<video adi>/` — `klip_plani.json`, `transkript.json`, klipler + SRT.
Masaustu sayfasi bu klasoru okur; klipleri **uygulama icinde oynatir** (`vfil://` protokolu, Range
destekli), skor kirilimini ve kesit zaman cizgisini gosterir.

## Guncellemeler

Ayarlar sayfasindaki **Uygulama guncellemesi** bolumu, bu deponun en son surumunu okuyup yeni `.exe`
dosyasini indirir (**Bot kodu guncellemesi (git)** bolumu ise bot kodunu `git pull --ff-only` ile
yeniler). Depo private oldugu icin uygulamaya `repo` yetkili bir GitHub token girilir.

Yeni surum yayinlamak:

```bash
cd desktop
npm run release            # 1.0.0 -> 1.0.1: derler, etiketler, GitHub surumunu yayinlar
```

Bot kodundaki degisiklikleri GitHub'a gondermek (anahtar sizinti kontrolu yapar):

```bash
py -3 gonder.py "gemini promptlari guncellendi"
py -3 gonder.py "yeni ozellik" --surum     # masaustu surumunu de yayinlar
```

## Test

`desktop/npm run test:smoke` gercek Electron ana surecinde bot komutlarini, canli log akisini, iptali,
renderer/preload koprusunu, guncelleme indirmeyi ve git guncellemesini dogrular. Gercek bot kotasi
harcanmaz (sahte bot dosyalari + gecici klasorler kullanilir).
