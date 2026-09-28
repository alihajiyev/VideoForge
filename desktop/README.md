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
npm run package    # Windows exe (nsis + portable) -> release/
npm run typecheck  # tsc --noEmit
npm run test:smoke # uctan uca test (91 kontrol) - asagiya bakin
```

## Testler

`npm run test:smoke` gercek Electron ana surecinde 91 kontrol calistirir:

- Python tespiti, ortam kontrolu, `bot.db` okuma, `constants.py` ayristirma, Masaustu taramasi, log/plan okuma
- Log ayristirici (ANSI, seviye, asama, cikti dosyasi, istatistik yakalama)
- Uretilen bot komutlarinin birebir dogrulanmasi (modal run / kesif / haftalik zincir / temizleyici)
- Girdi korumalari (gecersiz link, VideoForge olmayan klasor, olmayan klasor)
- **Gecici klasorde sahte bot ile tam is akisi**: canli log akisi, asama ilerlemesi, cikti tespiti, iptal (taskkill)
- **Gizli BrowserWindow ile gercek renderer testi**: preload koprusu, IPC cagrilari, React render,
  sayfa gecisi, tema degisimi, arayuzden is baslatma, yol korumasi, konsol hatasi kontrolu

Test gercek botu ve API kotalarini kullanmaz (sahte bot dosyalari + gecici `userData`).

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
| Kesif | `python kesif.py --chn <n> --evet [--haftalik]` |
| Haftalik zincir | `kesif.py --haftalik --chn <n> --evet` → `haftalik_islet.py --evet` |
| Temizleyici | `modal run temizle.py --link ...` |

- Bot klasoru varsayilani: gelistirmede depo koku, paketli uygulamada `Masaustu\VideoForge`
  (Ayarlar'dan degistirilebilir).
- Python yorumlayicisi `py -3` → `python` → `python3` sirasiyla otomatik bulunur.
- Ortam kontrolleri: Python surumu, bot dosyalari, modal, google-genai, elevenlabs, yt-dlp,
  ffmpeg/ffprobe, `cookies.txt` tazeligi, Modal oturumu (`~/.modal.toml`).

## Guvenlik

Ortam kontrolu ve dosya islemleri yalnizca `Masaustu` ve VideoForge klasoru altindaki yollara izin
verir. Renderer'da Node entegrasyonu kapali; tum yetkiler `preload.ts` icindeki dar IPC yuzeyinden gecer.

## Dokumanlar

- `docs/ANALIZ.md` — bot incelemesi: mantik hatalari, prompt onerileri, yol haritasi.
