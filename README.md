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
(cok gunlu modda `Gun<N>_<baslik>_<rastgele>/` klasoru).

Masaustu arayuzu icin:

```bash
cd desktop
npm install
npm run dev            # gelistirme
npm run package        # Windows kurulum + portable exe
npm run test:smoke     # 147 kontrol, uctan uca test
```

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
