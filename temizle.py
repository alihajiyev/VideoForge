import sys, subprocess, os

if __name__ == "__main__":
    from functions.ui import header, footer_done, info, C
    link = input(f"{C.CYAN}🔗 YouTube linkini yapistir:{C.RESET} ").strip()
    header("🧹 VIDEO TEMIZLEYICI (ProPainter)", "Modal bulut temizlik")
    info("Motor atesleniyor, lutfen pencereyi kapatma...")
    subprocess.run(["python", "-m", "modal", "run", "temizle.py", "--link", link])
    footer_done("Islem tamamlandi!")
    input("Cikmak icin Enter'a bas...")
else:
    from shared import *
    try:
        from functions.ui import C
    except Exception:
        class C:
            BLUE = ''; GREEN = ''; YELLOW = ''; RED = ''
            CYAN = ''; MAGENTA = ''; BOLD = ''; RESET = ''
            GRAY = ''

    app = modal.App("video-temizle", image=image)

    @app.cls(gpu=CLEANER_GPU, image=image, cpu=4, memory=16384, timeout=3600, volumes={"/results": results_volume})
    class VideoCleaner:
        @modal.method()
        def clean(self, video_bytes: bytes):
            return run_clean(video_bytes)

    @app.function(image=image, cpu=4, memory=8192, timeout=3600, volumes={"/results": results_volume})
    def cloud_temizle(link, rand_num, video_bytes):
        tmp_dir = tempfile.mkdtemp()
        raw_path = os.path.join(tmp_dir, f"raw_{rand_num}.mp4")
        with open(raw_path, "wb") as f: f.write(video_bytes)
        ses_yol = os.path.join(tmp_dir, f"ses_{rand_num}.aac")
        ses_kontrol = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", raw_path], capture_output=True, text=True)
        var_ses = ses_kontrol.stdout.strip() == "audio"
        if var_ses:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", raw_path, "-vn", "-c:a", "aac", "-b:a", "128k", ses_yol], check=True)
        sessiz_yol = os.path.join(tmp_dir, f"sessiz_{rand_num}.mp4")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", raw_path, "-an", "-r", "30", "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", "-g", "30", "-movflags", "+faststart", sessiz_yol], check=True)

        fps = get_video_fps(sessiz_yol)
        dur = get_video_duration(sessiz_yol)
        chunk_dur_sec = FRAMES_PER_GPU / fps
        num_chunks = math.ceil(dur / chunk_dur_sec)
        total_frames = int(dur * fps)

        print(f"{C.BLUE}[1/4]{C.RESET} Video analiz edildi ({C.BOLD}{int(dur)}sn{C.RESET}, {C.BOLD}{fps:.2f}fps{C.RESET}) → {C.YELLOW}{total_frames}{C.RESET} frame, {C.CYAN}{num_chunks}{C.RESET} parca")

        bytes_list = []
        for i in range(num_chunks):
            start_time = i * chunk_dur_sec
            part_path = os.path.join(tmp_dir, f"part_{i}.mp4")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", sessiz_yol, "-ss", str(start_time), "-t", str(chunk_dur_sec), "-c:v", "libx264", "-crf", "16", "-preset", "superfast", "-pix_fmt", "yuv420p", part_path], check=True)
            with open(part_path, "rb") as f: bytes_list.append(f.read())

        bot = VideoCleaner()
        print(f"{C.BLUE}[2/4]{C.RESET} {C.CYAN}{num_chunks}{C.RESET} parca {C.MAGENTA}{MAX_CONCURRENT_GPUS}'er{C.RESET} grupla {C.BOLD}L4 GPU{C.RESET}'da temizleniyor...")
        total_gpu_sec = 0
        result_ids = []
        for batch_start in range(0, num_chunks, MAX_CONCURRENT_GPUS):
            batch = bytes_list[batch_start:batch_start + MAX_CONCURRENT_GPUS]
            batch_len = len(batch)
            batch_end = min(batch_start + MAX_CONCURRENT_GPUS, num_chunks)
            t0 = time.time()
            batch_ids = list(bot.clean.map(batch))
            t1 = time.time()
            result_ids.extend(batch_ids)
            total_gpu_sec += (t1 - t0) * batch_len
            pct = min(100, int(batch_end / num_chunks * 100))
            bar = '█' * (pct // 10) + '░' * (10 - pct // 10)
            print(f"   {C.GREEN}✓{C.RESET} Grup {C.YELLOW}{batch_start//MAX_CONCURRENT_GPUS + 1}/{(num_chunks-1)//MAX_CONCURRENT_GPUS+1}{C.RESET} {C.GRAY}[{bar}]{C.RESET} {C.BOLD}{pct}%{C.RESET}")
        gpu_wall = total_gpu_sec

        print(f"{C.BLUE}[3/4]{C.RESET} {C.BOLD}Temiz parcalar birlestiriliyor{C.RESET}...")
        results_volume.reload()
        list_file = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_file, "w") as f:
            for i, rid in enumerate(result_ids):
                result_path = f"/results/{rid}.mp4"
                clean_part_path = os.path.join(tmp_dir, f"clean_{i}.mp4")
                with open(result_path, "rb") as src, open(clean_part_path, "wb") as dst: dst.write(src.read())
                os.remove(result_path)
                f.write(f"file '{clean_part_path}'\n")
        results_volume.commit()

        sessiz_final = os.path.join(tmp_dir, "sessiz_final.mp4")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", sessiz_final], check=True)
        if var_ses:
            print(f"{C.BLUE}[4/4]{C.RESET} {C.BOLD}Ses ekleniyor{C.RESET}...")
            sesli_final = os.path.join(tmp_dir, "sesli_final.mp4")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", sessiz_final, "-i", ses_yol, "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", "-shortest", sesli_final], check=True)
            with open(sesli_final, "rb") as f: final_bytes = f.read()
        else:
            with open(sessiz_final, "rb") as f: final_bytes = f.read()
        return {"video_bytes": final_bytes, "num_chunks": num_chunks, "gpu_wall_time": gpu_wall, "total_frames": total_frames, "has_audio": var_ses, "dur": dur, "fps": fps}

    @app.local_entrypoint()
    def main(link: str = None):
        # yt-dlp guncelle
        subprocess.run([sys.executable, "-m", "pip", "install", "-U", "--quiet", "yt-dlp"], capture_output=True)
        print(f"\n{C.YELLOW}{'='*55}{C.RESET}")
        print(f"{C.BOLD}{C.CYAN} 🧹 VIDEO TEMIZLEYICI (ProPainter) 🧹{C.RESET}")
        print(f"{C.YELLOW}{'='*55}{C.RESET}\n")
        start_total = time.time()
        rand_num = random.randint(100, 999)
        tmp = tempfile.mkdtemp()
        video_path = os.path.join(tmp, f"raw_{rand_num}.mp4")
        # Baslik al
        title_res = subprocess.run([sys.executable, "-m", "yt_dlp", "--print", "title", "--cookies", "cookies.txt", "--remote-components", "ejs:github", "--quiet", "--no-playlist", "--no-progress", link], capture_output=True, text=True)
        raw_title = title_res.stdout.strip() or "video"
        # Video + ses birlikte indir (subprocess, merge saglam)
        subprocess.run([sys.executable, "-m", "yt_dlp", "-f", "bestvideo[height<=1080]+bestaudio/best", "--merge-output-format", "mp4", "-o", video_path, "--cookies", "cookies.txt", "--remote-components", "ejs:github", "--quiet", "--no-playlist", "--no-progress", link], check=True)
        if not os.path.exists(video_path):
            print(f"{C.RED}❌ Video indirilemedi!{C.RESET}")
            return
        print(f"{C.GREEN}📥{C.RESET} Indirildi: {C.BOLD}{raw_title}{C.RESET}")
        with open(video_path, "rb") as f: v_bytes = f.read()
        print(f"{C.MAGENTA}🧹{C.RESET} Temizlik basliyor...\n")
        result = cloud_temizle.remote(link, rand_num, v_bytes)
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        safe_title = re.sub(r'[\\/*?:"<>|\n]', "", raw_title)[:50].strip()
        out_name = os.path.join(desktop, f"{safe_title}_{rand_num}_CLEAN.mp4")
        with open(out_name, "wb") as f: f.write(result["video_bytes"])
        total_time = time.time() - start_total
        gpu_cost = (result["gpu_wall_time"] + OVERHEAD_SECONDS * result["num_chunks"]) * GPU_COST_PER_SEC
        print(f"\n{C.GREEN}{'='*50}{C.RESET}")
        print(f"{C.BOLD}{C.GREEN}✅ TEMIZLIK BASARIYLA TAMAMLANDI.{C.RESET}")
        print(f"{C.GREEN}{'='*50}{C.RESET}")
        print(f"{C.CYAN}⏱️ {C.RESET}Toplam Sure:     {C.BOLD}{int(total_time // 60)} dakika {int(total_time % 60)} saniye{C.RESET}")
        print(f"{C.CYAN}⚡ {C.RESET}GPU:             {C.YELLOW}{result['num_chunks']}x{C.RESET} L4 (paralel: {C.MAGENTA}{MAX_CONCURRENT_GPUS}'er{C.RESET})")
        print(f"{C.CYAN}🎞️ {C.RESET}Frame:           {C.YELLOW}{result['total_frames']}{C.RESET} ({result['dur']:.0f}sn @ {C.BOLD}{result['fps']:.2f}fps{C.RESET})")
        ses_str = f"{C.GREEN}Evet{C.RESET}" if result['has_audio'] else f"{C.RED}Hayir{C.RESET}"
        print(f"{C.CYAN}🔊 {C.RESET}Ses:             {ses_str}")
        print(f"{C.CYAN}💸 {C.RESET}Maliyet:         {C.YELLOW}${gpu_cost:.4f}{C.RESET}")
        print(f"{C.GRAY}{'-'*50}{C.RESET}")
        print(f"{C.GREEN}📁{C.RESET} Kaydedildi: {C.BOLD}{os.path.basename(out_name)}{C.RESET}")
        print(f"{C.GREEN}{'='*50}{C.RESET}\n")
