# -*- coding: utf-8 -*-
"""GPU parca (chunk) ve maliyet planlayicisi — SAF (pure) modul.

Neden var?
----------
Temizleme (ProPainter) her parca icin AYRI bir GPU konteyneri acar; her konteyner
kendi soguk baslangicini + EasyOCR/ProPainter model yuklemesini oder. Bu yuzden
"parca sayisi" dogrudan harcamadir.

Eski mantik parcalari SABIT sureyle boluyordu:
    chunk_dur = frames_per_gpu / fps
    num_chunks = ceil(dur / chunk_dur)
    ...  -ss i*chunk_dur -t chunk_dur  ile kesiyordu
Bu ikincil bir hata uretiyordu: son parca cok kucuk kalabiliyordu (or. 1800 karede
son parca 72 kare = ~2.4sn). O kucuk parca icin de TAM bir GPU konteyneri aciliyor
(soguk baslangic + model yukleme = bosuna harcama).

Bu modul parcalari ESIT boler (kimse minik kalmaz) ve son parcayi oncekiyle
birlestirerek parca sayisini (dolayisiyla konteyner sayisini) azaltir. Tum kararlar
burada, test edilebilir saf fonksiyonlarda; bulut kodu sadece sonucu kullanir.
"""
import math

# Kuyruk birlestirme esigi: son %35'lik parca tek basina konteyneri hak etmez.
VARSAYILAN_KUYRUK_ORANI = 0.35
# Birlestirme sonrasi hicbir parca bu orandan fazla buyumesin (VRAM guvenligi).
# 1.25: tavanin %25'i kadar tolerans. ProPainter VRAM'i `subvideo_length` ile
# sinirli oldugu ve konteynerde 16GB RAM bulundugu icin guvenli marj.
VARSAYILAN_MAX_BUYUME = 1.25
VARSAYILAN_MIN_KARE = 150


def vram_guvenli_kare(frames_per_gpu, proc_w, proc_h, baseline_w=360, baseline_h=640,
                      guclu_gpu=False):
    """Cozunurluge gore VRAM-guvenli kare sayisi.

    360x640 taban cizgisinde `frames_per_gpu` kare sinirindaydi. Islem
    cozunurlugu buyudukce kare sayisi ayni oranda duser (piksel basina VRAM
    sabit kalir). Guclu GPU'da (L40S) tavan `frames_per_gpu`e kadar acilir.
    """
    fpg = int(frames_per_gpu * (baseline_w * baseline_h) / max(1, proc_w * proc_h))
    fpg = max(VARSAYILAN_MIN_KARE, fpg)
    if guclu_gpu:
        fpg = min(int(frames_per_gpu), fpg * 2)
    return fpg


def planla(toplam_kare, fps, frames_per_gpu, min_kare=VARSAYILAN_MIN_KARE,
           kuyruk_orani=VARSAYILAN_KUYRUK_ORANI, max_buyume=VARSAYILAN_MAX_BUYUME):
    """Toplam kare sayisini GPU-guvenli esit parcalara bol.

    Donus: {"num_chunks": int, "frames_per_gpu": int, "chunk_dur_sec": float,
            "kare_per_chunk": float, "kuyruk_birlesti": bool}

    Toplam kare 0 ise num_chunks=0 (cagiran taraf islem yapmaz).
    """
    try:
        toplam_kare = int(toplam_kare)
        fps = float(fps)
    except Exception:
        return {"num_chunks": 0, "frames_per_gpu": max(1, int(min_kare)),
                "chunk_dur_sec": 0.0, "kare_per_chunk": 0.0, "kuyruk_birlesti": False}
    fpg = max(1, int(min_kare), int(frames_per_gpu))
    if toplam_kare <= 0 or fps <= 0:
        return {"num_chunks": 0, "frames_per_gpu": fpg, "chunk_dur_sec": 0.0,
                "kare_per_chunk": 0.0, "kuyruk_birlesti": False}

    num = max(1, math.ceil(toplam_kare / fpg))
    kuyruk_birlesti = False
    # Kuyruk birlestirme: bir parca eksiltince hicbir parca `max_buyume`den
    # fazla buyumuyorsa birlestir (minik son parca icin bosuna GPU acmayalim).
    while num >= 2 and (toplam_kare / (num - 1)) <= fpg * max_buyume:
        num -= 1
        kuyruk_birlesti = True

    kare_per_chunk = toplam_kare / num
    return {
        "num_chunks": num,
        "frames_per_gpu": fpg,
        "chunk_dur_sec": kare_per_chunk / fps,
        "kare_per_chunk": kare_per_chunk,
        "kuyruk_birlesti": kuyruk_birlesti,
    }


def parcalar(plan, toplam_kare, fps):
    """Plandan esit (start_sec, dur_sec) araliklari uretir.

    Sabit sureli bolmenin aksine hepsi neredeyse esit; minik son parca olmaz.
    """
    n = int(plan.get("num_chunks") or 0)
    if n <= 0 or toplam_kare <= 0 or fps <= 0:
        return []
    toplam_sure = toplam_kare / float(fps)
    birim = toplam_sure / n
    out = []
    cursor = 0.0
    for i in range(n):
        # Son parca yuvarlama artigini alir; boylece hicbir parca minik kalmaz
        # ve toplam video suresi tam kapsanir.
        dur = max(0.0, toplam_sure - cursor) if i == n - 1 else birim
        out.append((round(cursor, 3), round(dur, 3)))
        cursor += dur
    return out


def konteyner_overhead_sn(num_chunks, overhead_seconds):
    """Kac kare islenirse islensin her GPU konteynerinin odedigi sabit sure.

    Bu, chunk sayisini azaltmanin neden dogrudan tasarruf oldugunun olcusu.
    """
    try:
        return max(0, int(num_chunks)) * float(overhead_seconds)
    except Exception:
        return 0.0


def tahmini_maliyet(num_chunks, gpu_cost_per_sec, overhead_seconds):
    """Yalnizca KONTEYNER SABIT MALIYETI (alt sinir) tahmini, USD.

    Gercek islem suresi buna eklenir; bu deger "parca sayisini dusurunce
    kazanilan para"yi gostermek icin vardir.
    """
    return konteyner_overhead_sn(num_chunks, overhead_seconds) * float(gpu_cost_per_sec)
