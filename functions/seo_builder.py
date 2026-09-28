def build_seo_html(sections, raw_title, original_transcript, channel_name="", lang="ru", start_time=None, end_time=None, timeline=None, audio_duration=None, source_timeline=None, source_duration=None, beatmap=None, usage_note=None):
    t_lang = sections.get(f"title_{lang}", raw_title)
    t_tr = sections.get("title_tr", "")
    tags = sections.get("tags", "")
    tag_items = [t.strip() for t in tags.split(",") if t.strip()]
    if len(tag_items) <= 1 and " " in tags:
        tag_items = [t.strip() for t in tags.split() if t.strip()]
    tags_csv = ", ".join(tag_items)
    v_lang = sections.get(f"voice_{lang}", "")
    v_tr = sections.get("voice_tr", "")
    tr_tr = sections.get("transcript_tr", "")
    time_cards = ""
    if start_time or end_time:
        start_str = start_time.strftime("%H:%M:%S") if start_time else "-"
        end_str = end_time.strftime("%H:%M:%S") if end_time else "-"
        time_cards = f"""
<div id="time" class="card">
  <div class="label">Processing Time</div>
  <div class="voice">Start: {start_str} &nbsp;|&nbsp; End: {end_str}</div>
</div>
"""
    timeline_card = ""
    if timeline:
        rows = "\n".join(
            f'<div class="tl-row"><div class="tl-time">{t["start"]} - {t["end"]}</div><div class="tl-text">{t["sentence"]}</div></div>'
            for t in timeline
        )
        dur_note = f" (toplam {audio_duration:.1f}sn)" if audio_duration else ""
        timeline_card = f"""
<div id="timeline" class="card">
  <div class="label">Seslendirme Zaman Cizelgesi (bizim ses){dur_note}</div>
  {rows}
</div>
"""
    source_card = ""
    if source_timeline:
        src_rows = "\n".join(
            f'<div class="tl-row"><div class="tl-time">{t["start"]} - {t["end"]}</div><div class="tl-text">{t["sentence"]}</div></div>'
            for t in source_timeline
        )
        src_note = f" (toplam {source_duration:.1f}sn)" if source_duration else ""
        source_card = f"""
<div id="source_timeline" class="card">
  <div class="label">Orijinal Zaman Cizelgesi (videonun sesi){src_note}</div>
  {src_rows}
</div>
"""
    beatmap_tag = ""
    if beatmap:
        import json as _json
        beatmap_tag = (
            '\n<script type="application/json" id="beatmap-data">'
            + _json.dumps(beatmap, ensure_ascii=False)
            + "</script>"
        )
    usage_card = ""
    if usage_note:
        usage_card = f"""
<div id="usage" class="card">
  <div class="label">Gemini Kullanimi (#8)</div>
  <div class="voice" style="font-size:14px;">{usage_note}</div>
</div>
"""
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{t_lang}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0a0a0f; color: #e8e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 32px 16px; }}
  .container {{ max-width: 680px; margin: 0 auto; }}
  .card {{ background: #13131f; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #1e1e2e; }}
  .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #58587a; margin-bottom: 8px; }}
  .title {{ font-size: 22px; font-weight: 700; line-height: 1.3; }}
  .title-tr {{ color: #787899; font-size: 14px; font-style: italic; margin-top: 4px; }}
  .tags {{ color: #787899; font-size: 13px; line-height: 1.8; }}
  .tags span {{ display: inline-block; background: #1a1a2e; padding: 2px 10px; border-radius: 4px; margin: 2px 4px 2px 0; color: #a0a0c0; }}
  .voice {{ font-size: 17px; line-height: 1.7; }}
  .voice-tr {{ color: #787899; font-size: 14px; font-style: italic; margin-top: 12px; }}
  .transcript {{ color: #68689a; font-size: 13px; line-height: 1.6; font-style: italic; }}
  .tl-row {{ display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid #1a1a2e; }}
  .tl-row:last-child {{ border-bottom: none; }}
  .tl-time {{ flex: 0 0 130px; color: #7c7cff; font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .tl-text {{ color: #c8c8e0; font-size: 14px; line-height: 1.5; }}
</style>
</head>
<body>
<div class="container">

<div id="title" class="card">
  <div class="label">Title</div>
  <div class="title">{t_lang}</div>
  <div class="title-tr">{t_tr}</div>
</div>

{time_cards}
<div id="tags" class="card">
  <div class="label">Tags</div>
  <div class="tags">{tags_csv}</div>
</div>

{usage_card}

<div id="voice_text" class="card">
  <div class="label">Voiceover</div>
  <div class="voice">{v_lang}</div>
  <div class="voice-tr">{v_tr}</div>
</div>

{timeline_card}

{source_card}
{beatmap_tag}
<div id="transcript" class="card">
  <div class="label">Original Transcript</div>
  <div class="transcript">{original_transcript}</div>
  <div class="voice-tr" style="margin-top:12px;">{tr_tr}</div>
</div>

</div>
</body>
</html>"""
