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

Kesif/otomatik secim: `kesif.py --chn <n> --evet [--haftalik]` · Haftalik zincir: `haftalik_islet.py --evet`

## Kurulum

```bash
pip install -r requirements.txt
copy .env.example .env      # sonra .env icine kendi anahtarlarini yaz
py -3 -m modal setup        # Modal oturumu (ilk seferde)
```

### Anahtarlar (`.env`)

`GEMINI_API_KEYS` (virgulle ayrilmis, kota siralamasi icin), `ELEVENLABS_API_KEY`, `TRANSCRIPT_API_KEY`.

> `.env` **depoya girmez** (`.gitignore`). Anahtarlar koda yazilmaz; `constants.py` bunlari ortamdan
> okur, Modal gorevlerine `bulut_kanali.py` icindeki `modal.Secret.from_dotenv` ile enjekte edilir.
> Bu depo private tutulur ve anahtarlar sohbet/commit gecmisinde tutulmaz.

## Calistirma

```bash
py -3 -X utf8 -m modal run kinosekrety.py --link https://youtu.be/XXXX
py -3 -X utf8 -m modal run faktza15.py --link https://youtu.be/XXXX --force
py -3 -X utf8 -m modal run kinok_syjet.py --link https://youtu.be/XXXX --gun 2 --gun-toplam 7
```

Ciktilar Masaustu'ne yazilir: `*_CLEAN.mp4`, `*_VOICEOVER.mp3`, `*_THUMB.png`, `*_SEO.html`
(haftalik modda `Gun<N>_<baslik>_<rastgele>/` klasoru).

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
