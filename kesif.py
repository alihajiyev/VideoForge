# -*- coding: utf-8 -*-
"""
VideoForge Kesif - Kanal analizi ve video oneri araci
Kaynak kanalin son videolarini analiz eder, senin kanalin tarzina en uygun
ve daha once islenmemis 3-5 videoyu onerir. Ana bottan bagimsizdir.
"""
import sys
import os
import re
import argparse
import json
import difflib
import time
import random
import shutil
import subprocess
import tempfile
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import yt_dlp

from constants import link_kayitlimi, oneri_kaydet, platform_tespit_et
from functions.gemini_func import gemini_uret
from functions.transcribe import fetch_subs_ytdlp, api_ile_transkript_cek, yt_dlp_ile_alt_yazi_cek
from functions.ui import header, footer_done, footer_fail, info, ok, warn, err, step
from shared import ensure_fresh_ytdlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "kesif_config.json")
PLAN_FILE = os.path.join(BASE_DIR, "haftalik_plan.json")
VIDIQ_KEY = "vidiq_4OjOZi1vxbUEWY_DHFs_fWHbANpXjbG86uNN1AG"

# Cok gunlu plan: skor sirasi = paylasim sirasi (1. gun Pazartesi ...).
# Gun sayisi ARTIK SABIT DEGIL: --gun N / --haftalik N ile secilir.
GUN_ADLARI = {1: "Pazartesi", 2: "Sali", 3: "Carsamba", 4: "Persembe",
              5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
VARSAYILAN_GUN_SAYISI = 7
MAX_GUN_SAYISI = 60


def gun_adi(sira):
    """1 tabanli gun numarasi -> hafta gunu adi (7'den sonra bastan dongu)."""
    try:
        sira = int(sira)
    except Exception:
        return f"Gun {sira}"
    return GUN_ADLARI.get(((sira - 1) % 7) + 1, f"Gun {sira}")

DEFAULT_CONFIG = {
    "kaynak_video_limit": 20,
    "own_video_limit": 30,
    "aday_sayisi": 6,
    "oneri_sayisi": 5,
    # --haftalik / --gun deger verilmeden calistirilirsa kac gunluk plan kurulsun
    "gun_sayisi": 7,
    "transcript_ytdlp": True,
    "transcript_api": True,
    "whisper_yedek": True,
    "havuz_sayisi": 40,
    "kanallar": {
        "1": {
            "ad": "Kino Sekrety",
            "nis": "Marvel/DC sinema Shorts",
            "own_channel": "https://www.youtube.com/channel/UCDxooL2M22LvKI32dREyjfQ",
            "kaynak_kanallar": [],
        },
    },
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Eski tek-kanalli config -> kanallar["1"]'e tasi (veri kaybi yok).
            # NOT: setdefault'tan ONCE bakilmali, yoksa varsayilan kanallar
            # eklenip migrasyon sarti hic saglanmaz.
            if "kanallar" not in cfg or not isinstance(cfg["kanallar"], dict):
                flat_own = cfg.pop("own_channel", None)
                flat_src = cfg.pop("kaynak_kanallar", None)
                cfg["kanallar"] = {
                    "1": {
                        "ad": "Kino Sekrety",
                        "nis": "Marvel/DC sinema Shorts",
                        "own_channel": flat_own or DEFAULT_CONFIG["kanallar"]["1"]["own_channel"],
                        "kaynak_kanallar": flat_src if isinstance(flat_src, list) else [],
                    }
                }
                save_config(cfg)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            for _no, _p in cfg["kanallar"].items():
                if isinstance(_p, dict):
                    _p.setdefault("ad", f"Kanal {_no}")
                    _p.setdefault("nis", "")
                    _p.setdefault("own_channel", "")
                    _p.setdefault("kaynak_kanallar", [])
            return cfg
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def normalize_channel_url(link):
    """Kanal linkini Shorts sekmesine yonlendir.
    TikTok/Instagram'da sekme eki yoktur, oldugu gibi birakilir.
    /shorts zaten yaziliysa dokunma; yoksa sonuna ekle."""
    link = link.strip().rstrip("/")
    if "tiktok.com" in link or "instagram.com" in link:
        return link
    if link.endswith("/shorts"):
        return link
    if "/channel/" in link or "/@" in link or "/c/" in link or "/user/" in link:
        return link + "/shorts"
    if link.startswith("@"):
        return f"https://www.youtube.com/{link}/shorts"
    if link.startswith("UC") and len(link) == 24:
        return f"https://www.youtube.com/channel/{link}/shorts"
    return f"https://www.youtube.com/@{link}/shorts"


# Onceden cozulmus TikTok secUid'leri (playwright ile dogrulandi, WAF bypass gerektirmez)
TIKTOK_SECUId_CACHE = {
    "bayefendifilm1": "MS4wLjABAAAAF6Ad6iToW-9K_yNTwjunUv_UJVFIzfd7Qj4X1WL3f-Z-4DbE1LKjQ3lqf_0ui2Lr",
    "anh.phan0485": "MS4wLjABAAAARug7HxSo-zye5OfMCRr8eUpAHsW5wxTEdS432PaY7IwxtNQzIl0wspy1-KlYYefH",
}

def _tiktok_resolve_secuid_playwright(username):
    """Cache'teki secUid'i dondurur; yoksa None.
    Playwright subprocess Windows modal loop ile cakistigi icin artik
    kesif icinde dogrudan calistirilmiyor — cache yeterlidir."""
    return TIKTOK_SECUId_CACHE.get(username)


def _tiktok_videos_via_creator_api(sec_uid, username, limit=20):
    """TikTok creator/item_list API ile video listesi (WAF bypass, yt-dlp bypass).
    Donus: [(id, title, views, duration)]"""
    import string as _str
    out = []
    cursor = int(time.time() * 1e3)
    seen = set()
    for _ in range(5):  # max 5 sayfa = 75 video, limit'e yetisir
        if len(out) >= limit:
            break
        device_id = str(random.randint(7250000000000000000, 7325099899999994577))
        query = {
            'aid': '1988', 'app_language': 'en', 'app_name': 'tiktok_web',
            'browser_language': 'en-US', 'browser_name': 'Mozilla', 'browser_online': 'true',
            'browser_platform': 'Win32', 'browser_version': '5.0 (Windows)', 'channel': 'tiktok_web',
            'cookie_enabled': 'true', 'count': '15', 'cursor': cursor, 'device_id': device_id,
            'device_platform': 'web_pc', 'focus_state': 'true', 'from_page': 'user', 'history_len': '2',
            'is_fullscreen': 'false', 'is_page_visible': 'true', 'language': 'en', 'os': 'windows',
            'priority_region': '', 'referer': '', 'region': 'US', 'screen_height': '1080',
            'screen_width': '1920', 'secUid': sec_uid, 'type': '1', 'tz_name': 'UTC',
            'verifyFp': 'verify_' + ''.join(random.choices(_str.hexdigits, k=7)), 'webcast_language': 'en',
        }
        try:
            r = requests.get('https://www.tiktok.com/api/creator/item_list/', params=query,
                             headers={'User-Agent': 'Mozilla/5.0', 'Referer': f'https://www.tiktok.com/@{username}'}, timeout=15)
            j = r.json()
        except Exception as e:
            print(f"   ⚠️ creator API hatasi: {str(e)[:60]}")
            break
        items = j.get('itemList') or []
        if not items:
            break
        for it in items:
            vid = str(it.get('id') or '')
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append({
                'id': vid,
                'title': (it.get('desc') or '').strip()[:200] or vid,
                'views': int(it.get('stats', {}).get('playCount') or 0),
                'duration': int((it.get('video', {}).get('duration') or 0)),
            })
            if len(out) >= limit:
                break
        # pagination: en eski videonun createTime'ini cursor yap
        try:
            last = items[-1]
            cursor = int(last.get('createTime', 0) * 1e3) - 1
        except Exception:
            cursor -= 7 * 86400000
        if not j.get('hasMorePrevious'):
            break
        time.sleep(0.8)
    return out


def _tiktok_resolve_user_id(username):
    """TikTok @kullanici -> secUid cozer (once playwright, sonra curl_cffi fallback)."""
    sec = _tiktok_resolve_secuid_playwright(username)
    if sec:
        return sec
    for url in (f"https://www.tiktok.com/@{username}", f"https://m.tiktok.com/@{username}"):
        try:
            try:
                from curl_cffi import requests as creq
                r = creq.get(url, impersonate="chrome", timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                html = r.text if hasattr(r, "text") else ""
            except Exception:
                r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 AppleWebKit/537.36"})
                html = r.text
            m = re.search(r'"secUid"\s*:\s*"([^"]+)"', html)
            if m:
                return m.group(1)
            m = re.search(r'"userId"\s*:\s*"(\d+)"', html)
            if m:
                return m.group(1)
        except Exception:
            continue
    return None


def yt_channel_videos(channel_url, limit=20):
    """Kanali son videolarini flat-playlist ile ceker (API kotasi gerekmez).
    Shorts sekmesi yoksa /videos'a dener. TikTok icin userId fallback'i vardir."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": limit,
        "skip_download": True,
    }
    # yt-dlp TikTok extractoru son surum degilse secondary user ID hatasi verir
    # -> sessizce guncellemeyi dene (ana botlardakiyle ayni mantik)
    try:
        ensure_fresh_ytdlp()
    except Exception:
        pass
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
    except Exception as e:
        msg = str(e)
        if "tiktok" in channel_url.lower() and "secondary user ID" in msg:
            m = re.search(r'@([^/?#]+)', channel_url)
            username = m.group(1) if m else ""
            print(f"   ⚠️ TikTok extractor guncelleniyor / userId cozuluyor ({username})...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "-U", "--quiet", "yt-dlp"], capture_output=True, timeout=120)
                import importlib
                importlib.reload(yt_dlp)
            except Exception:
                pass
            # 1) guncel surumle tekrar dene
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(channel_url, download=False)
            except Exception as e2:
                if "secondary user ID" not in str(e2) and "Failed to parse JSON" not in str(e2):
                    raise
                # 2) userId ile tiktokuser: semasi (yt-dlp'nin onerdigi yol)
                uid = _tiktok_resolve_user_id(username) if username else None
                if uid:
                    alt_url = f"tiktokuser:{uid}"
                    print(f"   🔁 TikTok fallback: {alt_url} deneniyor...")
                    try:
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(alt_url, download=False)
                    except Exception as e3:
                        # 3) Dogrudan creator/item_list API (playwright secUid + web API) — yt-dlp bypass
                        print(f"   ⚠️ tiktokuser semasi da olmadi ({str(e3)[:70]}), creator API deneniyor...")
                        api_videos = _tiktok_videos_via_creator_api(uid, username, limit=limit)
                        if api_videos:
                            print(f"   ✅ Creator API: {len(api_videos)} video bulundu (yt-dlp bypass)")
                            return username or channel_url, api_videos
                        raise
                else:
                    # secUid cozulemedi ama yine de creator API'yi dene (playwright ile bulunabilir)
                    api_videos = _tiktok_videos_via_creator_api(uid or "", username, limit=limit) if username else []
                    if api_videos:
                        return username or channel_url, api_videos
                    raise
        elif "shorts" in channel_url and ("does not have" in msg or "404" in msg):
            fallback_url = channel_url.rsplit("/shorts", 1)[0] + "/videos"
            print(f"   ⚠️ Shorts sekmesi yok, /videos deneniyor...")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(fallback_url, download=False)
        else:
            raise
    channel_name = info.get("channel") or info.get("uploader") or info.get("title") or channel_url
    out = []
    for e in (info.get("entries") or []):
        if not e or not e.get("id"):
            continue
        out.append({
            "id": e["id"],
            "title": e.get("title") or "",
            "views": e.get("view_count") or 0,
            "duration": e.get("duration") or 0,
        })
    return channel_name, out


def bot_db_processed(vid, url_hint=""):
    """Islenmis mi? ID + platform URL'lerine bak (TikTok/YouTube)."""
    try:
        if not vid or not str(vid).strip():
            return False
        vid = str(vid).strip()
        if link_kayitlimi(vid):
            return True
        if url_hint and link_kayitlimi(url_hint):
            return True
        # YouTube varyantlari (TikTok ID'leri icin zararsiz)
        if link_kayitlimi(f"https://www.youtube.com/watch?v={vid}"):
            return True
        if link_kayitlimi(f"https://youtu.be/{vid}"):
            return True
        return False
    except Exception:
        return False


def fetch_transcript_api(vid):
    """Ucretli transcript API (ana botla ayni) — hizli, throttling yok.
    Basarisizsa None doner, akis durmaz."""
    try:
        time.sleep(random.uniform(1, 2))
        txt = api_ile_transkript_cek(f"https://www.youtube.com/watch?v={vid}")
        if txt:
            return txt[:2500]
    except Exception as e:
        print(f"   ⚠️ transcript API olmadi ({str(e)[:60]})")
    return None


def _aday_url(kaynak_link, vid):
    """Aday videonun tam kaynak URL'si (platforma gore kurulur)."""
    plat = platform_tespit_et(kaynak_link or "")
    if plat == "tiktok":
        m = re.search(r'tiktok\.com/@([^/?#]+)', kaynak_link or "")
        user = m.group(1) if m else ""
        if user:
            return f"https://www.tiktok.com/@{user}/video/{vid}"
        return f"https://www.tiktok.com/video/{vid}"
    if plat == "instagram":
        return f"https://www.instagram.com/reel/{vid}"
    return f"https://www.youtube.com/watch?v={vid}"


def fetch_transcript_for(c, api_yedek=True):
    """Adaya platforma gore transcript: YouTube -> altyazi + API yedek;
    TikTok/Instagram -> ucretsiz altyazi (API YouTube-disi calismaz)."""
    if c.get("platform", "youtube") == "youtube":
        tr = fetch_subs_ytdlp(c["id"])
        if not tr and api_yedek:
            tr = fetch_transcript_api(c["id"])
        return tr
    tr = yt_dlp_ile_alt_yazi_cek(c.get("url") or c["id"])
    return tr[:2500] if tr else None


def fetch_description(url):
    """Videonun aciklamasini ceker (transcript yoksa kapi buna + basliga bakar).
    Tam URL alir (YouTube, TikTok, Instagram). Basarisizsa None doner, akis durmaz."""
    try:
        time.sleep(random.uniform(1, 2))
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "retries": 2}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        desc = (info.get("description") or "").strip()
        return desc[:800] if desc else None
    except Exception as e:
        print(f"   ⚠️ aciklama alinamadi ({str(e)[:60]})")
        return None


_WHISPER_MODEL = None

def fetch_whisper_fallback(vid, url_hint=""):
    """Son care (sadece altyazi yoksa): en dusuk kalitede indir -> Whisper base -> sil.
    Model bir kez yuklenir, tmp her seferinde temizlenir.
    TikTok/Instagram icin url_hint verilirse oradan indirir."""
    global _WHISPER_MODEL
    try:
        import whisper
    except Exception:
        print("   ⬇️ openai-whisper kuruluyor (ilk seferlik, biraz surer)...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "openai-whisper"], capture_output=True, timeout=900)
            import whisper
        except Exception as e:
            print(f"   ⚠️ whisper kurulamadi: {str(e)[:60]}")
            return None
    tmp = tempfile.mkdtemp()
    try:
        vp = os.path.join(tmp, "v.mp4")
        indirme_url = url_hint or f"https://www.youtube.com/watch?v={vid}"
        opts = {"quiet": True, "no_warnings": True, "format": "worst/worst[ext=mp4]/best[ext=mp4]/best",
                "outtmpl": vp, "retries": 2, "sleep_requests": 2}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([indirme_url])
        if not os.path.exists(vp) or os.path.getsize(vp) < 10000:
            return None
        if _WHISPER_MODEL is None:
            print("   🎙️ Whisper modeli yukleniyor (ilk seferlik)...")
            _WHISPER_MODEL = whisper.load_model("base")
        print("   🎙️ Whisper desifre ediyor (CPU)...")
        res = _WHISPER_MODEL.transcribe(vp)
        txt = (res.get("text") or "").strip()
        return txt[:2500] if txt else None
    except Exception as e:
        print(f"   ⚠️ whisper yedegi olmadi ({str(e)[:60]})")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def vidiq_trends(query="marvel"):
    """vidIQ API denemesi. vidIQ'un bu anahtarla erisilebilir public API'si YOKTUR
    (test edildi: tum endpoint'ler 404 / HTML donuyor). Bu yuzden config'de
    vidiq_enabled=False gelir; acilissa bile hata sessizce yutulur."""
    try:
        r = requests.get(
            "https://api.vidiq.com/v1/keywords",
            params={"query": query},
            headers={"Authorization": f"Bearer {VIDIQ_KEY}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        return {"hata": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"hata": str(e)[:80]}


def build_html_report(results, style, own_name, src_links, adaylar):
    """Ana bottaki SEO raporu tarzinda koyu-tema HTML rapor uretir."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    src_text = ", ".join(src_links)
    style_html = ""
    if style:
        bullets = "".join(
            f"<div class='bullet'>• {b.strip().lstrip('-•* ').strip()}</div>"
            for b in style.strip().split("\n") if b.strip()
        )
        style_html = f"""
<div id="stil" class="card">
  <div class="label">Kanal Stil Profili — Neyin Tutuyor?</div>
  {bullets}
</div>"""
    cards = []
    for r in results:
        c = next((x for x in adaylar if x["id"] == r["id"]), None)
        title = c["title"] if c else "?"
        views = f"{c['views']:,}".replace(",", ".") if c else "?"
        src = c["source"] if c else "?"
        dur = f"{c['duration']/60:.1f} dk" if c and c.get("duration") else "?"
        tr_ok = "✅ Var" if c and c.get("transcript") else "⚠️ Yok"
        score_color = "#4ade80" if r["score"] >= 8 else ("#facc15" if r["score"] >= 6 else "#94a3b8")
        tip = r.get("tip", "?")
        tip_badge = "💥 KAZANAN TİP" if tip == "KAZANAN" else ("📉 ÇÖP TİP" if tip == "COP" else "")
        gun_badge = ""
        if r.get("gun"):
            gun_badge = f"<div class='gun'>📅 {r['gun']}. Gün — {r.get('gun_adi', '')}</div>"
        href = (c.get("url") if c and c.get("url") else f"https://www.youtube.com/watch?v={r['id']}")
        cards.append(f"""
<div class="card video-card">
  {gun_badge}
  <div class="rank-row">
    <span class="rank">#{r['rank']}</span>
    <span class="score" style="color:{score_color};border-color:{score_color}">Skor {r['score']}</span>
  </div>
  <div class="title">{title}</div>
  <div class="meta">📺 Kaynak: {src} &nbsp;|&nbsp; 👁️ {views} izlenme &nbsp;|&nbsp; ⏱️ {dur} &nbsp;|&nbsp; Transkript: {tr_ok} &nbsp;|&nbsp; {tip_badge}</div>
  <div class="reason">💡 {r['reason']}</div>
  <a class="btn" href="{href}" target="_blank">▶️ Videoya Git</a>
</div>""")
    videos_html = "\n".join(cards)

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>VideoForge Keşif Raporu — {now}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0a0a0f; color: #e8e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 32px 16px; }}
  .container {{ max-width: 720px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .tarih {{ color: #787899; font-size: 13px; margin-bottom: 24px; }}
  .card {{ background: #13131f; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #1e1e2e; }}
  .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #58587a; margin-bottom: 12px; }}
  .bullet {{ padding: 6px 0; line-height: 1.6; color: #c8c8e0; border-bottom: 1px solid #1a1a2e; }}
  .bullet:last-child {{ border-bottom: none; }}
  .video-card {{ padding: 20px; }}
  .rank-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
  .rank {{ font-size: 20px; font-weight: 700; color: #7c7cff; }}
  .score {{ font-size: 13px; font-weight: 700; border: 1px solid; border-radius: 6px; padding: 3px 10px; }}
  .title {{ font-size: 17px; font-weight: 600; line-height: 1.4; margin-bottom: 8px; }}
  .meta {{ color: #787899; font-size: 12px; margin-bottom: 10px; }}
  .reason {{ background: #1a1a2e; border-radius: 8px; padding: 10px 14px; font-size: 14px; line-height: 1.5; color: #c8c8e0; margin-bottom: 14px; }}
  .btn {{ display: inline-block; background: #7c7cff; color: white; text-decoration: none; padding: 8px 18px; border-radius: 8px; font-size: 13px; font-weight: 600; }}
  .btn:hover {{ background: #9494ff; }}
  .gun {{ display: inline-block; background: #1e3a5f; color: #7cc4ff; font-weight: 700; font-size: 14px; border-radius: 8px; padding: 5px 14px; margin-bottom: 10px; }}
  .kaynak {{ color: #787899; font-size: 12px; word-break: break-all; }}
</style>
</head>
<body>
<div class="container">
  <h1>🎯 VideoForge Keşif Raporu</h1>
  <div class="tarih">{now} &nbsp;|&nbsp; Kanalım: {own_name} &nbsp;|&nbsp; Kaynaklar: <span class="kaynak">{src_text}</span></div>
  {style_html}
  <div class="card">
    <div class="label">Önerilen Videolar (En Uygun {len(results)})</div>
    <div style="color:#787899;font-size:13px;">Skorlar kanalının stiline uygunluğu gösterir. 8+ = kesin işle.</div>
  </div>
  {videos_html}
</div>
</body>
</html>"""


def gemini_style_profile(own_videos, channel_name):
    lines = "\n".join(f"- {v['title']} | {v['views']:,} izlenme" for v in own_videos)
    prompt = f"""You are a YouTube strategist for a Russian-language YouTube Shorts channel ("{channel_name}").
Below are the channel's recent videos with view counts.

{lines}

Tasks:
1. Identify which topics/styles OVER-perform (views clearly above average) and which under-perform.
2. Write a concise STYLE PROFILE: 5-8 bullets describing what content, topics, and title patterns fit this channel best.

IMPORTANT: Write the style profile in TURKISH (the channel owner only understands Turkish).
Output ONLY the style profile bullets in Turkish, nothing else."""
    raw = gemini_uret("Analyze my channel", prompt, "VideoForge-Kesif")
    return raw if raw and not raw.startswith("❌") else ""


def gemini_prefilter(candidates, kanal="1", nis=""):
    """1. asama: genis havuzu SADECE basliga gore kabaca suz.
    Comert davranir: supheli olan ELENMEZ, ust asamada transcript ile
    bakilir. Donus: KAZANAN adayi ID listesi (sira onemsiz)."""
    lines = "\n".join(f'ID={c["id"]} | {c["views"]:,} views | "{c["title"]}"' for c in candidates)
    if str(kanal) == "1":
        gorev = """You filter Marvel/DC YouTube Shorts topics. Below are candidate videos (ID | views | title).

TASK: Keep every video about an A-list hero instantly known to mainstream film viewers
(Thor, Thanos, Spider-Man, Iron Man, Vision...) or a known conflict/reveal about them.
DROP only: obscure/minor characters nobody knows, narrow nerd speculation, off-topic
(non-Marvel/DC/cinema).

BE GENEROUS: frame (why/versus/what-if) decides nothing — "Почему" titles are this
channel's biggest hits. If unsure, KEEP it — the upper stage checks the transcript.
Output ONLY the kept video IDs, one per line, nothing else."""
    elif str(kanal) == "3":
        gorev = f"""You filter film-story YouTube Shorts topics ({nis or "film hikayeleri"}).
Below are candidate videos (ID | views | title).

TASK: Keep every video that retells a movie/TV-series scene or plot
(drama, thriller, romance, comedy — any genre with a story).
DROP only: non-story content (vlogs, pranks, pure facts without a plot,
music/dance, gaming clips, ads).

BE GENEROUS: if it has a story, KEEP it — the upper stage checks the transcript.
Output ONLY the kept video IDs, one per line, nothing else."""
    else:
        gorev = f"""You filter interesting-facts YouTube Shorts topics ({nis or "general knowledge"}).
Below are candidate videos (ID | views | title).

TASK: Keep every video about a genuinely interesting fact, science, history,
space, nature, human body, technology or psychology topic with curiosity gap.
DROP only: vlogs, pranks, music/dance, gaming-only clips, narrow insider
speculation, or anything with no factual hook.

BE GENEROUS: if unsure, KEEP it — the upper stage checks the transcript.
Output ONLY the kept video IDs, one per line, nothing else."""
    prompt = f"""{gorev}

{lines}"""
    raw = gemini_uret("Prefilter candidates", prompt, "VideoForge-Kesif")
    if not raw or raw.startswith("❌"):
        return [c["id"] for c in candidates]
    valid_ids = {c["id"] for c in candidates}
    kept = []
    for line in raw.split("\n"):
        line = line.strip().strip("`").strip("*").strip()
        if line in valid_ids and line not in kept:
            kept.append(line)
        else:
            found = [v for v in valid_ids if v in line and v not in kept]
            kept.extend(found)
    return kept if kept else [c["id"] for c in candidates]


def gemini_rank(candidates, style_profile, own_name, konu_filtresi=True, kanal="1", nis="", cop_dahil=False, limit=10):
    src_lines = []
    for c in candidates:
        dur_min = c["duration"] / 60 if c["duration"] else 0
        tr = (c.get("transcript") or "")[:1200]
        desc = (c.get("description") or "")[:500]
        src_lines.append(f'ID={c["id"]} | {c["views"]:,} views | {dur_min:.1f} min | "{c["title"]}"\nTRANSCRIPT: {tr or "(yok)"}\nDESCRIPTION: {desc or "(yok)"}')
    src_text = "\n\n".join(src_lines)

    if str(kanal) == "1":
        gate = ""
        if konu_filtresi:
            gate = """
CRITICAL TOPIC GATE (kanal verisiyle kanitlanmis):
Once her adayi iki tipten birine sok — BASLIK + TRANSCRIPT + ACIKLAMA'nin
UCUNE BIRLIKTE bakarak karar ver. Tek kanita guvenme.

ONEMLI DUZELTME (kanal verisi): CERCEVE (neden/versus/what-if) tek basina
belirleyici DEGILDIR. "Почему" ile baslayan videolar kanalimizin en buyuk
hitleri (322K, 277K, 179K, 130K, 92K, 82K); "Что если" de 82K/44K yapti.
Yani "aciklama = COP" ya da "versus = KAZANAN" gibi cerceve kurallari YANLIS
ve bizim kazananlari eler. Cerceveyi elestirme, ICERIGE bak:
- KAZANAN = EVREN-ICI A-list icerik: ana akim film izleyicisinin HEMEN TANIDIGI
  kahraman + onun hakkinda bilinen bir catisma/reveal (Thor, Thanos, Spider-Man,
  Iron Man, Vision; "Кто страдал больше" 166K, "Секрет Таноса" 76K).
  Tek kritik girdi budur (tiklama + yorum tartismasi).
- COP = sunlardan HERHANGI biri:
  a) AKTOR / GERCEK DUNYA: aktorler, kontratlar, set hikayeleri, casting,
     oyuncu dedikodusu (Tom Holland, SLJ kontrati, Cavill, Tobey). Evren-ici
     karakter reveal'i degildir, bu kanalda yeri yok.
  b) DC EVRENI (Superman vb.): bu kanalin kazanan dagilimi MCU'dur.
  c) Obskur/nerd karakter ya da dar nis spekulasyon/teori (Namor 38K,
     Mordo 34K, Heimdall gizemi, Ant-Man fizigi 671).
  Drama, "ilginc hikaye", empati, merak unsuru PUAN KRITERI DEGILDIR — bunlar
  flop eden cerceveyi yuksek puanlatir. Duygusal gorunen aciklama yuksek
  puan ALAMAZ.
- Gri alan (tanidik kahraman ama nis detay): COP sayma, dusuk puanla sirala.
  Suphede kalma ama adil ol — veri karar verene kadar muhafazakar.
Baslik KAZANAN gorunup transcript lore ise COP'tur; baslik zayif gorunup
transcript A-list catisma ise KAZANAN'dir. Uc kanita da bak.

RANKING ORDER (baglayici):
1. Karakter taninirligi + konu gucu (ne kadar mainstream) — BIRINCIL kriter.
2. Izlenme sayisi — sadece ikincil, esit tiplerde bag cozer.
Kaynak kanalin kendi hiti senin kitlene uymayabilir; yuksek izlenmeli nis icerik,
dusuk izlenmeli A-list icerigin ONUNE GECEMEZ.
"""
    elif str(kanal) == "3":
        gate = """
TOPIC GATE (film-hikayesi kanali):
Her adayi BASLIK + TRANSCRIPT + ACIKLAMA'nin UCUNE BIRLIKTE bakarak iki
tipten birine sok:
- KAZANAN = net bir film/dizi hikayesi: izleyicinin "sonu ne oldu?" diye
  merak edecegi, yorumda tartisacagi olay orgusu (ihanet, entrika, intikam,
  ask, gerilim). Diyalog/twist iceren sahneler en gucludur.
- COP = sunlardan HERHANGI biri:
  a) Hikaye yok: sadece bilgi listesi, vlog, prank, dans/muzik, oyun klibi.
  b) Yaris-yamalak anlatim: transcript kopuk, olay akisi anlasilmiyor.
  c) Baslik hikaye vaat edip transcript bossa cikiyorsa COP'tur.
RANKING ORDER: hikaye gucu (merak + duygusal etki) birincil, izlenme ikincil.
"""
    else:
        gate = """
TOPIC GATE (genel kultur kanali):
Her adayi BASLIK + TRANSCRIPT + ACIKLAMA'nin UCUNE BIRLIKTE bakarak iki
tipten birine sok:
- KAZANAN = merak uyandiran somut bilgi: bilim, tarih, uzay, doga, insan
  vucudu, teknoloji, psikoloji — izleyicinin "bunu bilmiyordum" diyecegi,
  yorumda tartisacagi konu.
- COP = sunlardan HERHANGI biri:
  a) Vlog, prank, dans/muzik, oyun klibi — bilgi kancasi yok.
  b) Dar icerik: sadece belli bir oyunun/dizinin hayranini ilgilendiren
     detay, magazin dedikodusu.
  c) Baslik bilgi vaat edip transcript bossa cikiyorsa COP'tur.
RANKING ORDER: konu gucu (merak + tartisma potansiyeli) birincil, izlenme ikincil.
"""

    if str(kanal) == "3":
        nis_ad = nis or "film hikayeleri Shorts"
    elif str(kanal) == "1":
        nis_ad = nis or "Marvel/DC Shorts"
    else:
        nis_ad = nis or "ilginc bilgiler Shorts"
    prompt = f"""You are a YouTube strategist for the Russian-language {nis_ad} channel "{own_name}".

MY CHANNEL STYLE PROFILE:
{style_profile or f"(analiz yapilamadi - genel {nis_ad} bilgisiyle karar ver)"}
{gate}
CANDIDATE VIDEOS from a source channel (ID | views | duration | title):

{src_text}

TASK: Score each candidate 0-10 for how well it fits my channel's style and audience.
- Videos matching the channel niche ({nis_ad}) fit best. Off-topic videos score low.
- Consider viral potential and how well the topic matches my style profile.
- Decide from TITLE + TRANSCRIPT + DESCRIPTION together (+views); if transcript is missing, decide from title + description.

Output EXACTLY one line per ranked video, best first, top {limit} only:
RANK|SCORE|VIDEO_ID|TYPE|Short reason in Turkish (max 15 words)
TYPE is KAZANAN or COP (see topic gate above; if gate disabled, still classify honestly).

Example: 1|9.2|qE6nSXZtt-w|KAZANAN|Tanosa karsi son savas, kanalimizin en iyi konusu
Output ONLY those lines, nothing else."""
    raw = gemini_uret("Rank candidate videos", prompt, "VideoForge-Kesif")
    if not raw or raw.startswith("❌"):
        return []
    valid_ids = {c["id"] for c in candidates}
    results = []
    for line in raw.split("\n"):
        line = line.strip().strip("`").strip("*").strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        first = parts[0].upper().replace("RANK", "").replace(".", "").strip()
        if not first.isdigit():
            continue
        score_raw = "".join(ch for ch in parts[1] if ch.isdigit() or ch == ".")
        if not score_raw:
            continue
        vid = parts[2]
        # video ID satirin herhangi bir yerinde olabilir
        if vid not in valid_ids:
            found = [v for v in valid_ids if v in line]
            if not found:
                continue
            vid = found[0]
        try:
            rank = int(first)
            score = float(score_raw)
        except Exception:
            continue
        if len(parts) >= 5 and parts[3].upper().replace("Ç", "C").replace("Ö", "O") in ("KAZANAN", "COP"):
            tip = "KAZANAN" if parts[3].upper().startswith("KAZ") else "COP"
            reason = "|".join(parts[4:])[:150]
        else:
            tip = "?"
            reason = "|".join(parts[3:])[:150]
        if konu_filtresi and not cop_dahil and tip == "COP":
            continue  # cop tip direkt cope (haftalik modda yedek olarak tutulur)
        results.append({"rank": rank, "score": score, "id": vid, "reason": reason, "tip": tip})
    if not results:
        print(f"⚠️ Gemini ham cevabi parse edilemedi:\n{raw[:400]}")
    results.sort(key=lambda r: r["rank"])
    return results


def main():
    parser = argparse.ArgumentParser(description="VideoForge Kesif - Kanal analizi ve video oneri")
    parser.add_argument("--kanal", help="Kaynak kanal linki (birden fazlaysa virgulle ayir)", default=None)
    parser.add_argument("--adet", type=int, default=None, help="Kanal basina islenecek video sayisi")
    parser.add_argument("--chn", help="Hedef kanal no (config'deki kanallar: 1, 2...)", default=None)
    parser.add_argument("--haftalik", nargs="?", const=0, type=int, default=None,
                        help="Cok gunlu plan modu. Deger vermezsen config'deki gun sayisi (7). Ornek: --haftalik 10")
    parser.add_argument("--gun", type=int, default=None,
                        help="Plan kac gunluk olsun (--haftalik ile ayni is). Ornek: --gun 10")
    parser.add_argument("--evet", action="store_true", help="Hicbir sey sorma: config'deki kayitli kaynak kanallarla devam et (--chn sart)")
    args = parser.parse_args()

    cfg = load_config()
    kanallar = cfg.get("kanallar", {})

    # 0) HEDEF KANAL SECIMI (--evet varsa soru sorulmaz, --chn sarttir)
    chn = (args.chn or "").strip()
    if chn not in kanallar:
        if args.chn:
            print(f"❌ Config'de '{args.chn}' kanali yok. Mevcut: {', '.join(sorted(kanallar))}")
            return
        if args.evet:
            print(f"❌ --evet ile kanal sorulmaz; --chn gerekli. Mevcut: {', '.join(sorted(kanallar))}")
            return
        print("\n📺 Hedef kanal sec:")
        for no in sorted(kanallar, key=lambda x: int(x) if x.isdigit() else x):
            p = kanallar[no]
            print(f"  {no} - {p.get('ad', no)} ({p.get('nis', '')})")
        chn = input("Secim: ").strip()
        if chn not in kanallar:
            print("❌ Gecersiz secim.")
            return
    profil = kanallar[chn]
    kanal_ad = profil.get("ad", f"Kanal {chn}")
    nis = profil.get("nis", "")
    own_url = profil.get("own_channel", "")
    if not own_url:
        print(f"❌ {kanal_ad} icin own_channel config'de bos.")
        return
    src_limit = args.adet or cfg["kaynak_video_limit"]

    # 0b) PLAN MODU + GUN SAYISI (7 artik sabit degil, kullanici seciyor)
    if args.gun and args.gun > 0:
        gun_sayisi = args.gun
    elif args.haftalik and args.haftalik > 0:
        gun_sayisi = args.haftalik                 # --haftalik 10
    elif args.haftalik is not None:
        gun_sayisi = int(cfg.get("gun_sayisi") or VARSAYILAN_GUN_SAYISI)  # ciplak --haftalik
    else:
        gun_sayisi = 0                             # tek seferlik oneri modu
    if gun_sayisi > MAX_GUN_SAYISI:
        warn(f"Gun sayisi {MAX_GUN_SAYISI} ile sinirlandi (istenen: {gun_sayisi}).")
        gun_sayisi = MAX_GUN_SAYISI

    haftalik = gun_sayisi > 0
    # Plan modunda siralamaya genis havuz gerekir: kaynak cesitliligi kotasi
    # (kaynak basina max 3) yuzunden aday sayisi gun sayisindan fazla olmali.
    aday_sayisi = max(int(cfg["aday_sayisi"]), gun_sayisi + 5) if haftalik else int(cfg["aday_sayisi"])
    oneri_sayisi = gun_sayisi if haftalik else cfg["oneri_sayisi"]
    if haftalik:
        print(f"\n📅 COK GUNLU PLAN MODU: {gun_sayisi} video bulunacak; skor sirasi = paylasim sirasi "
              f"(1. gun Pazartesi ... {gun_sayisi}. gun {gun_adi(gun_sayisi)})")

    header("VIDEOFORGE KESIF - KANAL ANALIZI & VIDEO ONERI", f"{kanal_ad} | Kaynak tarama + stil profili + siralama")

    # 0) vidIQ (varsayilan kapali — public API'si yok, test edildi)
    if cfg.get("vidiq_enabled"):
        print("\n📡 vidIQ trend denemesi...")
        vq = vidiq_trends("marvel")
        if "hata" in vq:
            print(f"   ⚠️ vidIQ erisilemedi ({vq['hata']}) — Gemini trend bilgisi kullanilacak.")
        else:
            print(f"   ✅ vidIQ yanit alindi: {str(vq)[:120]}")

    # 1) KAYNAK KANALLAR (kanal profilindeki hazir liste + terminalde secim)
    hazir = [k.strip() for k in profil.get("kaynak_kanallar", []) if k.strip()]
    if args.kanal:
        src_links = [k.strip() for k in args.kanal.split(",") if k.strip()]
    elif args.evet:
        # Tam otomatik: kayitli liste, soru yok.
        src_links = hazir
        print(f"\n📋 Kayitli kaynak kanallar otomatik kullaniliyor ({len(src_links)} adet).")
    else:
        if hazir:
            print("\n📋 Kayitli kaynak kanallar:")
            for i, k in enumerate(hazir, 1):
                print(f"  {i}) {k}")
        extra = input("\n🔗 Kaynak kanal linki (birden fazlaysa virgulle ayir): ").strip()
        if extra:
            src_links = [k.strip() for k in extra.split(",") if k.strip()]
        else:
            src_links = hazir
    if not src_links:
        print("❌ Kanal linki verilmedi.")
        return

    # 2) KENDI KANALIM - stil profili
    print(f"\n📊 Kanalin analiz ediliyor: {own_url}")
    try:
        own_name, own_videos = yt_channel_videos(own_url, cfg["own_video_limit"])
    except Exception as e:
        print(f"❌ Kanal verisi alinamadi: {e}")
        return
    print(f"   ✅ {own_name} — {len(own_videos)} video bulundu")
    if not own_videos:
        print("❌ Kanalinda video bulunamadi.")
        return

    print("🤖 Gemini stil profili cikariyor...")
    style = gemini_style_profile(own_videos, own_name)
    if style:
        print("   ✅ Stil profili hazir.")
    else:
        print("   ⚠️ Stil profili olusturulamadi, genel bilgilerle devam.")

    # 3) KAYNAK KANALLARI TARA
    all_candidates = []
    tik_tok_channel_hatasi = False
    for link in src_links:
        # TikTok tek video linki doğrudan aday olarak eklenebilir (kanal taramasi bozukken yedek yol)
        if "tiktok.com" in link and "/video/" in link:
            print(f"\n📥 Tek video kaynagi: {link}")
            try:
                opts = {"quiet": True, "no_warnings": True, "skip_download": True}
                cf = None
                try:
                    from functions.transcribe import _cookiefile as _cf
                    cf = _cf()
                except Exception:
                    pass
                if cf:
                    opts["cookiefile"] = cf
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                vid = info.get("id") or _youtube_id(link) or link
                v = {"id": vid, "title": info.get("title") or "", "views": info.get("view_count") or 0,
                     "duration": info.get("duration") or 0, "source": info.get("uploader") or "TikTok",
                     "platform": "tiktok", "url": link}
                if not bot_db_processed(v["id"], v["url"]):
                    all_candidates.append(v)
                    print(f"   ✅ Tek video eklendi: {v['title'][:50]}")
                else:
                    print(f"   ⏭️ Zaten islenmis, atlandi")
            except Exception as e:
                print(f"   ❌ Tek video alinamadi: {e}")
            continue
        url = normalize_channel_url(link)
        print(f"\n📥 Kaynak kanal taraniyor: {url}")
        try:
            src_name, videos = yt_channel_videos(url, src_limit)
        except Exception as e:
            print(f"   ❌ Alinamadi: {e}")
            if "tiktok" in link.lower() and "secondary user ID" in str(e):
                tik_tok_channel_hatasi = True
            continue
        print(f"   ✅ {src_name} — {len(videos)} video")
        yeni = 0
        for v in videos:
            v["source"] = src_name
            v["platform"] = platform_tespit_et(link)
            v["url"] = _aday_url(link, v["id"])
            if v["duration"] and v["duration"] < 15:
                continue  # cok kisa parca/teaser videolari
            if bot_db_processed(v["id"], v["url"]):
                continue  # daha once islenmis
            yeni += 1
            all_candidates.append(v)
        print(f"   🆕 Islenmemis ve uygun: {yeni}")

    if not all_candidates:
        if tik_tok_channel_hatasi:
            print("\n❌ TikTok kanal listesi su an yt-dlp tarafinda bozuk (TikTok WAF + secondary user ID hatasi).")
            print("   Bu senin hatan degil — yt-dlp'nin TikTok extractor'i guncel TikTok sayfalarini okuyamiyor.")
            print("   Gecici cozum: TikTok icin kanal linki yerine 7-10 tane VIDEO linkini kaynak olarak gir.")
            print("   Ornek: https://www.tiktok.com/@bayefendifilm1/video/7663613589609024801")
            print("   Kesif bu videolari tek tek aday olarak toplayacak (tek video taramasi calisiyor).")
        else:
            print("\n❌ Islenmemis uygun video bulunamadi (hepsi daha once islenmis olabilir).")
        return

    if not all_candidates:
        print("\n❌ Islenmemis uygun video bulunamadi (hepsi daha once islenmis olabilir).")
        return

    # 4) GENIS HAVUZ -> on filtre (baslik) -> transcriptli dar havuz -> siralama
    # Izlenmesi orta ama tipi guclu video kaybolmasin diye kapi genis havuzda baslar.
    all_candidates.sort(key=lambda v: -(v["views"] or 0))
    havuz_sayisi = cfg.get("havuz_sayisi", 40)
    havuz = all_candidates[:havuz_sayisi]
    print(f"\n🔍 Genis havuz: {len(havuz)} video (izlenme sirali)")
    print("🤖 On filtre: basliga gore kaba eleme...")
    secilen_idler = gemini_prefilter(havuz, kanal=chn, nis=nis)
    secilen = [v for v in havuz if v["id"] in secilen_idler]
    print(f"   ✅ On filtreden gecen: {len(secilen)}")
    adaylar = secilen[:aday_sayisi]
    if cfg.get("transcript_ytdlp", True):
        api_yedek = cfg.get("transcript_api", True)
        print(f"\n🌐 {len(adaylar)} adayin transkripti cekiliyor (once ucretsiz altyazi, olmazsa API yedek)...")
        for c in adaylar:
            c["transcript"] = fetch_transcript_for(c, api_yedek=api_yedek)
            c["description"] = fetch_description(c.get("url") or _aday_url("", c["id"]))
            print(f"   {'✅' if c['transcript'] else '⚠️'} {c['id']} — {c['title'][:50]}")
        eksikler = [c for c in adaylar if not c.get("transcript")]
        if eksikler:
            print(f"\n🔁 Altyazisi alinamayan {len(eksikler)} video icin 20sn beklenip tek tur daha deneniyor...")
            time.sleep(20)
            for c in eksikler:
                c["transcript"] = fetch_transcript_for(c, api_yedek=api_yedek)
                print(f"   {'✅' if c['transcript'] else '⚠️'} {c['id']} — {c['title'][:50]}")
        hala_yok = [c for c in adaylar if not c.get("transcript")]
        if hala_yok and cfg.get("whisper_yedek", True):
            print(f"\n🎙️ Hala altyazisiz {len(hala_yok)} video icin Whisper yedegi (en dusuk kalite, is bitince silinir)...")
            for c in hala_yok:
                tr = fetch_whisper_fallback(c["id"], c.get("url", ""))
                c["transcript"] = tr
                print(f"   {'✅' if tr else '⚠️'} {c['id']} — {c['title'][:50]}")
    else:
        print(f"\n✅ Altyazi kapali, {len(adaylar)} aday baslik + izlenme ile degerlendiriliyor")

    # 5) GEMINI SIRALAMA (+ konu kapisi)
    konu_filtresi = cfg.get("konu_filtresi", True)
    print(f"\n🤖 Gemini video secip siraliyor... (konu filtresi: {'ACIK' if konu_filtresi else 'KAPALI'})")
    results = gemini_rank(adaylar, style, own_name, konu_filtresi=konu_filtresi, kanal=chn, nis=nis,
                          cop_dahil=haftalik, limit=(max(15, gun_sayisi + 5) if haftalik else 10))
    if not results:
        print("❌ Gemini oneri uretemedi (kota dolu olabilir).")
        return
    # Kaynak cesitliligi: tek kanala kilitlenmeyi onle (kaynak basina max 3, deliksiz).
    def _src_of(r):
        c = next((x for x in adaylar if x["id"] == r["id"]), None)
        return c["source"] if c else "?"
    def _kotala(liste, cap):
        dagitik, sayac = [], {}
        for r in liste:
            s = _src_of(r)
            if sayac.get(s, 0) >= cap:
                continue
            sayac[s] = sayac.get(s, 0) + 1
            dagitik.append(r)
        return dagitik
    def _dagilim_yaz(liste):
        sayac = {}
        for r in liste:
            s = _src_of(r)
            sayac[s] = sayac.get(s, 0) + 1
        print("   📊 Kaynak dagilimi: " + ", ".join(f"{s} x{n}" for s, n in sorted(sayac.items(), key=lambda x: -x[1])))
    if haftalik:
        # N GARANTI, kademeli: KAZANAN+kota -> KAZANAN kotasiz -> COP yedek (isaretli).
        # Kaynak kotasi gun sayisina gore buyur; aksi halde 3 kaynakta 9'dan
        # sonra tavana takilip listeyi COP dolduruyordu.
        kaynak_kotasi = max(3, (gun_sayisi + 2) // 3)
        kazananlar = [r for r in results if r.get("tip") != "COP"]
        cop_yedek = [r for r in results if r.get("tip") == "COP"]
        final = _kotala(kazananlar, kaynak_kotasi)[:gun_sayisi]
        if len(final) < gun_sayisi:
            alinan = {r["id"] for r in final}
            final += [r for r in _kotala(kazananlar, 99) if r["id"] not in alinan][:gun_sayisi - len(final)]
        cop_eklendi = 0
        if len(final) < gun_sayisi:
            alinan = {r["id"] for r in final}
            for r in [r for r in cop_yedek if r["id"] not in alinan][:gun_sayisi - len(final)]:
                r["reason"] = "⚠️ YEDEK (COP tip): " + r.get("reason", "")
                final.append(r)
                cop_eklendi += 1
        results = final
        for i, r in enumerate(results, 1):
            r["rank"] = i
        _dagilim_yaz(results)
        if cop_eklendi:
            print(f"   ⚠️ {cop_eklendi} gun COP yedekle dolduruldu (KAZANAN yetmedi, raporda isaretli).")
        if len(results) < gun_sayisi:
            print(f"   ⚠️ Taze aday yetmedi ({len(adaylar)} aday tarandi): plan {len(results)} video ile kuruldu.")
            print(f"      Cozum: kaynak kanallara yeni video gelince tekrar calistir ya da --adet'i yukselt.")
    else:
        results = results[:oneri_sayisi]
        dagitik = _kotala(results, 3)
        _dagilim_yaz(dagitik)
        if len(dagitik) < len(results):
            print(f"   ⚠️ Tek-kaynak kilidi: {len(results) - len(dagitik)} video kaynak kotasindan elendi")
        results = dagitik
    for r in results:
        oneri_kaydet(r["id"], r["score"], r.get("tip", ""), kanal=chn)
    print(f"   💾 {len(results)} oneri puani veritabanina kaydedildi (kanal {chn}: {kanal_ad} — ana bot ayni puani kullanacak).")

    # 5b) COK GUNLU PLAN — skor sirasi = gun sirasi, haftalik_plan.json'a yazilir.
    # haftalik_islet.py bu dosyayi okuyup videolari sirayla VideoForge'dan gecirir.
    if haftalik:
        for i, r in enumerate(results, 1):
            r["gun"] = i
            r["gun_adi"] = gun_adi(i)
        plan = {
            "chn": chn,
            "kanal_ad": kanal_ad,
            "tarih": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "toplam": len(results),
            # Plan DOSYASINDA gun sayisi her zaman GERCEKTE bulunan video sayisidir:
            # 19 istenip 15 bulununca eski kod gun_sayisi=19 yaziyordu; zincir basligi
            # "19 gunluk" gosterip 15 gun isliyordu ve test tutarliligi kirmizi kaliyordu.
            "gun_sayisi": len(results),
            "istenen_gun": gun_sayisi,
            "videolar": [],
        }
        for r in results:
            c = next((x for x in adaylar if x["id"] == r["id"]), None)
            link = (c.get("url") if c and c.get("url") else f"https://www.youtube.com/watch?v={r['id']}")
            plan["videolar"].append({
                "gun": r["gun"],
                "gun_adi": r["gun_adi"],
                "id": r["id"],
                "link": link,
                "baslik": c["title"] if c else "?",
                "kaynak": c["source"] if c else "?",
                "skor": r["score"],
                "tip": r.get("tip", ""),
                "sebep": r.get("reason", ""),
            })
        with open(PLAN_FILE, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
        print(f"   📅 {len(results)} GUNLUK PLAN yazildi: {PLAN_FILE}")
        if len(results) < gun_sayisi:
            print(f"   ⚠️ Istenen {gun_sayisi} video, bulunan {len(results)}: plan {len(results)} gun ile olustu.")

    # 6) RAPOR — Masaustune HTML (ana bottaki SEO raporu tarzinda)
    html = build_html_report(results, style, own_name, src_links, adaylar)
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    etiket = f"{gun_sayisi}Gun" if haftalik else f"Ch{chn}"
    rapor_path = os.path.join(desktop, f"Kesif-Rapor_{etiket}_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
    with open(rapor_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("\n" + "=" * 60)
    print(f" {f'{gun_sayisi} GUNLUK PLAN' if haftalik else f'ONERILEN VIDEOLAR (TOP {len(results)})'}")
    print("=" * 60)
    for r in results:
        c = next((x for x in adaylar if x["id"] == r["id"]), None)
        title = c["title"] if c else "?"
        link = (c.get("url") if c and c.get("url") else f"https://www.youtube.com/watch?v={r['id']}")
        gun_satiri = f"📅 {r['gun']}. Gun ({r['gun_adi']}) — " if haftalik else f"{r['rank']}. "
        print(f"{gun_satiri}[Skor {r['score']}] {title[:60]}")
        print(f"   {link}")
        print(f"   Sebep: {r['reason']}")
    print("\n" + "=" * 60)
    print(f"💾 HTML rapor masaustune kaydedildi:")
    print(f"   {rapor_path}")
    if haftalik:
        print(f"\n▶️ {gun_sayisi} gunluk zinciri sirali isletmek icin:  python haftalik_islet.py")
        print(f"   (videolar tek tek, gun sirasina gore VideoForge'dan gecer)")


if __name__ == "__main__":
    main()
