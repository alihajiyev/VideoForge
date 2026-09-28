import os
import sys
import time
import uuid
import gc
import difflib
import subprocess
import tempfile
from pathlib import Path
from constants import results_volume, PROC_W, PROC_H, SMART_TEXT_FILTER, GEMINI_API_KEYS, GEMINI_MODELS


def _text_sim(a, b):
    """OCR metinleri frame'ler arasi hafif degisir ('Peter Parker' -> 'Peter Paker').
    Bulanik benzerlik: 1.0 = ayni, 0.0 = hic alakasiz."""
    if not a or not b:
        return 1.0
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0.0


def _build_tracks(observations, max_gap=24):
    """Frame'ler arasi IoU eslesmesiyle yazilari track'lere bagla.
    Metin benzerligi dusukse (farkli cumleler) daha yuksek IoU sart (ayni nesne
    neredeyse ayni kutudadir); boylece ayni konumdaki farkli altyazi satirlari da
    tek persist track'e birlesir (sonra filigran kuraliyla maskelanir)."""
    tracks = []
    active = []
    for f in sorted(observations.keys()):
        boxes = observations[f]
        used = set()
        for tr in active:
            last_box, last_text = tr['obs'][-1][1], tr['obs'][-1][2]
            best, best_iou = None, 0.0
            for i, b in enumerate(boxes):
                if i in used:
                    continue
                iou = _iou(last_box, b[:4])
                if iou < 0.3:
                    continue
                sim = _text_sim(last_text, b[4])
                need = 0.6 if sim < 0.4 else 0.3
                if iou >= need and iou > best_iou:
                    best, best_iou = i, iou
            if best is not None:
                used.add(best)
                b = boxes[best]
                tr['obs'].append((f, b[:4], b[4]))
                tr['last_f'] = f
        for i, b in enumerate(boxes):
            if i not in used:
                tr = {'obs': [(f, b[:4], b[4])], 'last_f': f}
                tracks.append(tr)
                active.append(tr)
        active = [tr for tr in active if f - tr['last_f'] <= max_gap]
    return tracks


def _detect_cuts(diffs, threshold=25.0):
    cuts = []
    for i in range(1, len(diffs)):
        if diffs[i] > threshold and diffs[i] > 2.0 * max(diffs[max(0, i - 3):i] + [1.0]):
            cuts.append(i)
    return cuts


def _track_height(tr):
    b = tr['obs'][-1][1]
    return max(1.0, b[3] - b[1])


def _classify_tracks(tracks, total_frames, cut_list, proc_w, proc_h):
    """Track'leri siniflandir: filigran (maskela), altyazi zinciri (maskela),
    sahne yazisi (koru), gurultu (koru). Donus: (maskelenecekler, istatistik, belirsizler)"""
    cut_set = cut_list
    n_cuts = len(cut_list)
    watermark, rest, ambiguous = [], [], []
    n_noise = 0
    for tr in tracks:
        first, last = tr['obs'][0][0], tr['obs'][-1][0]
        span = last - first
        if span < 12:  # <0.4s -> OCR gurultusu
            n_noise += 1
            continue
        cuts_inside = sum(1 for c in cut_set if first < c < last)
        is_persistent = cuts_inside >= 2 or span >= 0.4 * total_frames
        if is_persistent:
            if n_cuts < 3 and cuts_inside == 0 and span >= 0.5 * total_frames:
                # Kesintisiz tek-cekim video: filigran mi, dogal sahne yazisi mi?
                # (Superman'in S'i korunsun) -> Gemini arbitration (1 cagri)
                ambiguous.append(tr)
            else:
                watermark.append(tr)
        else:
            rest.append(tr)

    # Stil toplulugu: ayni boyutlarda ve videoya yayilmis cok sayida track = altyazi stili.
    # Konum degistiren seyrek altyazilari yakalar (MARKET gibi izole sahne yazilarini etkilemez).
    subtitle = []
    remaining = sorted(rest, key=lambda t: t['obs'][0][0])
    grouped = [False] * len(remaining)
    for i, t in enumerate(remaining):
        if grouped[i]:
            continue
        h0 = _track_height(t)
        w0 = t['obs'][-1][1][2] - t['obs'][-1][1][0]
        group = [t]
        grouped[i] = True
        for j in range(i + 1, len(remaining)):
            if grouped[j]:
                continue
            u = remaining[j]
            h1 = _track_height(u)
            w1 = u['obs'][-1][1][2] - u['obs'][-1][1][0]
            if abs(h1 - h0) / max(h0, 1) <= 0.3 and abs(w1 - w0) / max(w0, 1) <= 0.4:
                group.append(u)
                grouped[j] = True
        if len(group) >= 4:
            # Altyazi satirlari ZAMANSEL OLARAK CAKISMAZ (biri digerinin yerine gecer).
            # Sahne yazisi (tabela/logo) ise altyaziyla ust uste binebilir -> gruptan elenir.
            group_sorted = sorted(group, key=lambda c: c['obs'][-1][0])
            disjoint = []
            last_end = -1
            for c in group_sorted:
                c_start, c_end = c['obs'][0][0], c['obs'][-1][0]
                if c_start > last_end - 6:  # <=6 frame tasarma toleransi (satir gecisi)
                    disjoint.append(c)
                    last_end = c_end
            if len(disjoint) >= 6:
                coverage = sum(c['obs'][-1][0] - c['obs'][0][0] for c in disjoint) / max(1, total_frames)
                if coverage >= 0.30:
                    subtitle.extend(disjoint)
    in_subtitle = {id(t) for t in subtitle}
    in_watermark = {id(t) for t in watermark}
    scene = [t for t in remaining if id(t) not in in_subtitle]
    stats = {
        'watermark': len(watermark),
        'subtitle': len(subtitle),
        'scene': len(scene),
        'noise': n_noise,
        'ambiguous': len(ambiguous),
        'cuts': n_cuts,
    }
    mask_tracks = watermark + subtitle
    return mask_tracks, scene, stats, ambiguous


def _gemini_arbitrate(frames_dir, tr, orig_w, orig_h, proc_w, proc_h):
    """Belirsiz persistent track icin 1 Gemini cagrisi: filigran mi sahne yazisi mi?
    Hata/olmama durumunda None -> koru (guvenli varsayilan)."""
    try:
        import cv2
        from PIL import Image
        from google import genai
        from google.genai import types
        sx, sy = orig_w / proc_w, orig_h / proc_h
        crops = []
        texts = []
        for f, box, text in (tr['obs'][0], tr['obs'][-1]):
            path = os.path.join(frames_dir, f"{f:05d}.jpg")
            img = cv2.imread(path)
            if img is None:
                continue
            x1, y1, x2, y2 = int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy)
            pad = 40
            x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
            x2, y2 = min(img.shape[1], x2 + pad), min(img.shape[0], y2 + pad)
            crop = img[y1:y2, x1:x2].copy()
            cv2.rectangle(crop, (max(0, int(box[0] * sx) - x1), max(0, int(box[1] * sy) - y1)),
                          (min(crop.shape[1] - 1, int(box[2] * sx) - x1), min(crop.shape[0] - 1, int(box[3] * sy) - y1)),
                          (0, 255, 0), 2)
            crops.append(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
            if text:
                texts.append(text)
        if len(crops) < 2:
            return None
        client = genai.Client(api_key=GEMINI_API_KEYS[0], http_options={'timeout': 30000})
        prompt = (
            "These are two crops from the same video at different moments. The green box marks the same text region. "
            "Is this region a watermark/overlay added ON TOP of the video (channel logo, username, moving stamp) "
            "or a NATURAL PART of the scene (character clothing logo like Superman's S, a street sign, a shop sign)? "
            f"The text in the region reads: '{' / '.join(texts[:2])}'. "
            "Reply with exactly one word: WATERMARK or SCENE."
        )
        r = client.models.generate_content(
            model=GEMINI_MODELS[0], contents=[prompt] + crops,
            config=types.GenerateContentConfig(system_instruction="You classify video text regions. Answer with one word only."),
        )
        out = (r.text or '').strip().upper()
        if 'WATERMARK' in out:
            return True
        if 'SCENE' in out:
            return False
        return None
    except Exception as e:
        print(f"⚠️ [Bulut] Gemini arbitration basarisiz (koru): {str(e)[:80]}")
        return None


def _write_masks(mask_tracks, masks_dir, total_frames, proc_w, proc_h):
    """Maskeli track'lerden her frame icin maske PNG'si uret (ara frameler interpolasyon)."""
    import cv2
    import numpy as np
    kernel = np.ones((8, 8), np.uint8)
    boxes_per_frame = [[] for _ in range(total_frames)]
    for tr in mask_tracks:
        obs = tr['obs']
        for f in range(obs[0][0], obs[-1][0] + 1):
            # interpolasyon: f'e en yakin iki gozlem arasinda lineer
            prev_o, next_o = obs[0], obs[-1]
            for o in obs:
                if o[0] <= f:
                    prev_o = o
                if o[0] >= f:
                    next_o = o
                    break
            if next_o[0] == prev_o[0]:
                box = prev_o[1]
            else:
                t = (f - prev_o[0]) / (next_o[0] - prev_o[0])
                pb, nb = prev_o[1], next_o[1]
                box = tuple(pb[k] + (nb[k] - pb[k]) * t for k in range(4))
            boxes_per_frame[f].append(box)
    for f in range(total_frames):
        mask = np.zeros((proc_h, proc_w), dtype=np.uint8)
        for (x1, y1, x2, y2) in boxes_per_frame[f]:
            cv2.rectangle(mask, (int(x1) - 8, int(y1) - 8), (int(x2) + 8, int(y2) + 8), 255, -1)
        mask = cv2.dilate(mask, kernel, iterations=1)
        cv2.imwrite(os.path.join(masks_dir, f"{f:05d}.png"), mask)


def run_clean(video_bytes):
    import cv2
    import numpy as np
    import shutil
    import easyocr
    import torch
    sys.path.append("/ProPainter")
    tmp_dir = tempfile.mkdtemp()
    in_v = os.path.join(tmp_dir, "input.mp4")
    with open(in_v, "wb") as f: f.write(video_bytes)
    cap = cv2.VideoCapture(in_v)
    fps = cap.get(cv2.CAP_PROP_FPS)
    orig_w, orig_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames_dir = os.path.join(tmp_dir, "frames"); os.makedirs(frames_dir)
    masks_dir = os.path.join(tmp_dir, "masks"); os.makedirs(masks_dir)
    reader = easyocr.Reader(['en', 'tr'], gpu=True)
    # HER FRAME taranmali: animasyonlu (daktilo tarzi) altyazilarda 2 frame'lik ornekleme
    # kelime sonlarini kaciriyor ("stronger" -> "st er"). Tam tarama ~100sn/konteyner, butce icinde.
    OCR_EVERY_N = 1

    if SMART_TEXT_FILTER:
        # ================= YENI: TRACK-BASED SINIFLANDIRMA =================
        count = 0
        t_ocr = 0.0
        ocr_count = 0
        observations = {}
        diffs = []
        prev_small = None
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            cv2.imwrite(os.path.join(frames_dir, f"{count:05d}.jpg"), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            small = cv2.resize(frame, (PROC_W, PROC_H), interpolation=cv2.INTER_AREA)
            gray = cv2.resize(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (96, 54))
            diffs.append(0.0 if prev_small is None else float(np.mean(cv2.absdiff(gray, prev_small))))
            prev_small = gray
            if count % OCR_EVERY_N == 0:
                t0 = time.time()
                # TAM COZUNURLUKTE tespit (540p kacirma sorunu icin) -> PROC koordinatlarina olcek
                res = reader.readtext(frame, paragraph=True)
                sx, sy = PROC_W / frame.shape[1], PROC_H / frame.shape[0]
                t_ocr += time.time() - t0
                ocr_count += 1
                if res:
                    boxes = []
                    for b in res:
                        bbox, text = b[0], b[1]
                        pts = np.array(bbox, dtype=np.float64).reshape(-1, 2)
                        if pts.shape[0] < 2:
                            continue
                        boxes.append((
                            float(pts[:, 0].min() * sx), float(pts[:, 1].min() * sy),
                            float(pts[:, 0].max() * sx), float(pts[:, 1].max() * sy),
                            str(text),
                        ))
                    if boxes:
                        observations[count] = boxes
            count += 1
        cap.release()
        print(f"🔎 [Bulut] OCR bitti: {t_ocr:.0f}s ({ocr_count}/{count} frame, {OCR_EVERY_N}x ornekleme)")

        tracks = _build_tracks(observations)
        cut_list = _detect_cuts(diffs)
        mask_tracks, scene_tracks, stats, ambiguous = _classify_tracks(tracks, count, cut_list, PROC_W, PROC_H)
        print(f"🎯 [Bulut] Track analizi: {len(tracks)} track | {stats['watermark']} filigran, "
              f"{stats['subtitle']} altyazi, {stats['scene']} sahne yazisi (koru), "
              f"{stats['noise']} gurultu | {stats['cuts']} sahne kesmesi")
        for tr in ambiguous:
            print("🤔 [Bulut] Belirsiz persistent track -> Gemini soruluyor...")
            verdict = _gemini_arbitrate(frames_dir, tr, orig_w, orig_h, PROC_W, PROC_H)
            if verdict is True:
                mask_tracks.append(tr)
                print("🧹 [Bulut] Gemini: WATERMARK -> maskelaniyor")
            else:
                scene_tracks.append(tr)
                print("🛡️ [Bulut] Gemini: SCENE -> korunuyor")
        if mask_tracks:
            _write_masks(mask_tracks, masks_dir, count, PROC_W, PROC_H)
        else:
            for f in range(count):
                cv2.imwrite(os.path.join(masks_dir, f"{f:05d}.png"), np.zeros((PROC_H, PROC_W), dtype=np.uint8))
        print(f"🧹 [Bulut] Maskelenecek track: {len(mask_tracks)} | Korunan sahne yazisi: {len(scene_tracks)}")
    else:
        # ================= ESKI DAVRANIS (rollback icin aynen korundu) =================
        kernel = np.ones((8, 8), np.uint8)
        count = 0
        t_ocr = 0.0
        ocr_count = 0
        last_mask = None
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if count % OCR_EVERY_N == 0:
                t0 = time.time()
                # TAM COZUNURLUKTE tespit: 540p OCR kucuk/ince yazilari kaciriyordu.
                # Kutular isleme boyutuna olceklenir, maske yine PROC boyutunda kalir.
                mask = np.zeros((PROC_H, PROC_W), dtype=np.uint8)
                res = reader.readtext(frame, paragraph=True)
                sx, sy = PROC_W / frame.shape[1], PROC_H / frame.shape[0]
                for (bbox, text) in res:
                    pts = np.array(bbox, dtype=np.float64).reshape(-1, 2)
                    if pts.shape[0] < 2:
                        continue
                    x1 = pts[:, 0].min() * sx
                    y1 = pts[:, 1].min() * sy
                    x2 = pts[:, 0].max() * sx
                    y2 = pts[:, 1].max() * sy
                    cv2.rectangle(mask, (int(x1) - 8, int(y1) - 8), (int(x2) + 8, int(y2) + 8), 255, -1)
                mask = cv2.dilate(mask, kernel, iterations=1)
                t_ocr += time.time() - t0
                ocr_count += 1
                last_mask = mask
            else:
                mask = last_mask
            cv2.imwrite(os.path.join(frames_dir, f"{count:05d}.jpg"), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            cv2.imwrite(os.path.join(masks_dir, f"{count:05d}.png"), mask)
            count += 1
        cap.release()
        print(f"🔎 [Bulut] OCR bitti: {t_ocr:.0f}s ({ocr_count}/{count} frame OCR'landi, {OCR_EVERY_N}x ornekleme)")

    del reader; gc.collect()
    if torch.cuda.is_available(): torch.cuda.empty_cache(); torch.cuda.ipc_collect()
    out_root = os.path.join(tmp_dir, "out")
    propainter_env = {**os.environ, "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
    subprocess.run(["python", "inference_propainter.py", "--video", frames_dir, "--mask", masks_dir, "--output", out_root, "--save_frames", "--fp16", "--width", str(PROC_W), "--height", str(PROC_H), "--raft_iter", "12", "--neighbor_length", "8", "--subvideo_length", "40"], cwd="/ProPainter", check=True, stdout=subprocess.DEVNULL, env=propainter_env)
    final_frames_dir = os.path.join(tmp_dir, "final_frames"); os.makedirs(final_frames_dir)
    all_pngs = sorted(list(Path(out_root).rglob("*.png")))
    for i, png_path in enumerate(all_pngs): shutil.move(str(png_path), os.path.join(final_frames_dir, f"{i:05d}.png"))
    final_mp4 = os.path.join(tmp_dir, "final.mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps), "-i", f"{final_frames_dir}/%05d.png", "-vf", f"scale={orig_w}:{orig_h}:flags=lanczos,unsharp=5:5:0.5:5:5:0.0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", final_mp4], check=True)
    with open(final_mp4, "rb") as f: result_bytes = f.read()
    result_id = str(uuid.uuid4())
    with open(f"/results/{result_id}.mp4", "wb") as f: f.write(result_bytes)
    results_volume.commit()
    return result_id
