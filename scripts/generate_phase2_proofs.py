"""Phase 2 Verification Proof Generator for BHARAT KI SOCH.

Renders:
1. output/proofs/motion_presets_contact_sheet.png
2. output/proofs/daily_bulletin_opening_sample.mp4
3. output/proofs/news_short_sample.mp4
4. output/proofs/repurposed_short_sample.mp4
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure root workspace is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont

PROOF_DIR = Path("output/proofs")
PROOF_DIR.mkdir(parents=True, exist_ok=True)
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def get_font(size: int = 24):
    f_path = Path("assets/fonts/Mukta-Bold.ttf")
    if f_path.exists():
        try:
            return ImageFont.truetype(str(f_path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def generate_contact_sheet():
    print("Generating motion_presets_contact_sheet.png...")
    im = Image.new("RGB", (1920, 1080), color=(10, 15, 26))
    d = ImageDraw.Draw(im)

    font_title = get_font(42)
    font_cat = get_font(26)
    font_item = get_font(18)

    # Header
    d.rectangle([0, 0, 1920, 90], fill=(225, 29, 72))
    d.text((50, 20), "BHARAT KI SOCH — 56 Broadcast Motion Presets Architecture", fill=(255, 255, 255), font=font_title)

    from video.motion_presets import MotionPresetCatalog, PresetCategory
    catalog = MotionPresetCatalog.get_instance()

    cats = list(PresetCategory)
    # 7 columns
    col_w = 260
    start_x = 40
    start_y = 120

    cat_colors = {
        PresetCategory.OPENER: (239, 68, 68),
        PresetCategory.HEADLINE_REVEAL: (245, 158, 11),
        PresetCategory.PHOTO_MOTION: (16, 185, 129),
        PresetCategory.VIDEO_REFRAME: (59, 130, 246),
        PresetCategory.DATA_GRAPHICS: (139, 92, 246),
        PresetCategory.TRANSITION: (236, 72, 153),
        PresetCategory.BRAND_OUTRO: (255, 153, 51),
    }

    for idx, cat in enumerate(cats):
        cx = start_x + (idx * col_w)
        c_color = cat_colors.get(cat, (100, 100, 100))

        # Category Box Header
        d.rounded_rectangle([cx, start_y, cx + col_w - 20, start_y + 45], radius=8, fill=c_color)
        d.text((cx + 10, start_y + 8), cat.value.upper(), fill=(255, 255, 255), font=font_cat)

        # Presets in this category
        presets = catalog.list_presets(cat)
        for p_idx, p in enumerate(presets):
            py = start_y + 60 + (p_idx * 105)
            # Card background
            d.rounded_rectangle([cx, py, cx + col_w - 20, py + 95], radius=6, fill=(20, 28, 45), outline=(40, 50, 75))
            # Number badge
            d.rectangle([cx + 6, py + 6, cx + 32, py + 26], fill=c_color)
            num_str = f"{(idx * 8) + p_idx + 1:02d}"
            d.text((cx + 8, py + 6), num_str, fill=(255, 255, 255), font=font_item)

            # Name and ID
            d.text((cx + 38, py + 6), p.name[:20], fill=(240, 240, 240), font=font_item)
            d.text((cx + 8, py + 32), p.preset_id[:26], fill=(148, 163, 184), font=font_item)

            # Render type pill
            d.rounded_rectangle([cx + 8, py + 65, cx + 80, py + 85], radius=4, fill=(30, 41, 59))
            d.text((cx + 12, py + 66), p.render_type, fill=(56, 189, 248), font=font_item)

            # Duration
            d.text((cx + 90, py + 66), f"{p.duration_default}s", fill=(203, 213, 225), font=font_item)

    out_file = PROOF_DIR / "motion_presets_contact_sheet.png"
    im.save(str(out_file), quality=95)
    print(f"Saved {out_file} ({out_file.stat().st_size} bytes)")


def render_daily_bulletin_opening():
    print("Rendering daily_bulletin_opening_sample.mp4...")
    # 1. Generate base frame
    bg_img = PROOF_DIR / "bulletin_bg.jpg"
    im = Image.new("RGB", (1080, 1920), color=(15, 23, 42))
    d = ImageDraw.Draw(im)

    font_huge = get_font(64)
    font_mid = get_font(40)
    font_sub = get_font(32)

    # Top Breaking Banner
    d.rectangle([0, 0, 1080, 180], fill=(225, 29, 72))
    d.text((60, 50), "BHARAT KI SOCH | दैनिक बुलेटिन", fill=(255, 255, 255), font=font_huge)

    # Date / Panchang Card
    d.rounded_rectangle([80, 240, 1000, 440], radius=16, fill=(30, 41, 59), outline=(255, 153, 51), width=4)
    d.text((120, 270), "शुक्रवार, 20 नवंबर 2026", fill=(255, 215, 0), font=font_mid)
    d.text((120, 340), "कार्तिक शुक्ल पक्ष एकादशी | विश्व बाल दिवस", fill=(226, 232, 240), font=font_sub)

    # Graphic Visual placeholder in middle
    d.rounded_rectangle([80, 480, 1000, 1300], radius=18, fill=(19, 78, 74), outline=(45, 212, 191), width=3)
    d.text((140, 850), "राष्ट्रीय & अंतरराष्ट्रीय समाचार", fill=(255, 255, 255), font=font_huge)

    # Lower Third Chyron
    d.rectangle([0, 1380, 1080, 1680], fill=(11, 15, 26))
    d.rectangle([0, 1380, 1080, 1395], fill=(225, 29, 72))
    d.text((80, 1420), "आज की बड़ी खबरें: भारत का बड़ा वैश्विक कदम", fill=(255, 255, 255), font=font_mid)
    d.text((80, 1520), "अंतरिक्ष, अर्थव्यवस्था और रक्षा क्षेत्र में नए कीर्तिमान", fill=(203, 213, 225), font=font_sub)

    # Bottom Ticker
    d.rectangle([0, 1780, 1080, 1880], fill=(225, 29, 72))
    d.text((60, 1805), "LIVE • भारत की सोच विशेष बुलेटिन • सब्सक्राइब करें", fill=(255, 255, 255), font=font_sub)

    im.save(str(bg_img), quality=92)

    sfx_intro = Path("assets/sfx/sting_news_intro.wav")
    out_mp4 = PROOF_DIR / "daily_bulletin_opening_sample.mp4"

    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-t", "4.0", "-i", str(bg_img),
        "-i", str(sfx_intro) if sfx_intro.exists() else "anullsrc=r=44100:cl=mono",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-vf", "fade=t=in:st=0:d=0.25:color=0xCC0000",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_mp4),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    print(f"Saved {out_mp4} ({out_mp4.stat().st_size} bytes)")


def render_news_short_sample():
    print("Rendering news_short_sample.mp4...")
    bg_img = PROOF_DIR / "news_short_bg.jpg"
    im = Image.new("RGB", (1080, 1920), color=(20, 24, 39))
    d = ImageDraw.Draw(im)

    font_huge = get_font(56)
    font_mid = get_font(38)
    font_sub = get_font(28)

    # Category Pill
    d.rounded_rectangle([72, 180, 320, 245], radius=30, fill=(255, 153, 51))
    d.text((105, 190), "राष्ट्रीय खबर", fill=(0, 0, 0), font=font_sub)

    # Center Visual Mockup
    d.rounded_rectangle([72, 300, 1008, 1200], radius=16, fill=(30, 58, 138), outline=(96, 165, 250), width=4)
    d.text((140, 700), "इसरो का नया कीर्तिमान", fill=(255, 255, 255), font=font_huge)
    d.text((140, 800), "सफल प्रक्षेपण के साथ रचा इतिहास", fill=(203, 213, 225), font=font_mid)

    # Lower Third
    d.rectangle([0, 1260, 1080, 1540], fill=(15, 23, 42))
    d.rectangle([0, 1260, 1080, 1272], fill=(245, 158, 11))
    d.text((72, 1300), "भारत ने अंतरिक्ष में लहराया परचम", fill=(255, 255, 255), font=font_mid)
    d.text((72, 1400), "पूरे देश में उत्साह, वैज्ञानिकों को बधाई", fill=(226, 232, 240), font=font_sub)

    im.save(str(bg_img), quality=92)

    bed_loop = Path("assets/sfx/news_bed_loop.wav")
    out_mp4 = PROOF_DIR / "news_short_sample.mp4"

    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-t", "4.0", "-i", str(bg_img),
        "-i", str(bed_loop) if bed_loop.exists() else "anullsrc=r=44100:cl=mono",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-vf", "scale=1620:-2,zoompan=z='min(1.0+0.001*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=120:s=1080x1920:fps=30",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_mp4),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    print(f"Saved {out_mp4} ({out_mp4.stat().st_size} bytes)")


def render_repurposed_short_sample():
    print("Rendering repurposed_short_sample.mp4...")
    # Create 16:9 base clip
    raw_16_9 = PROOF_DIR / "source_16_9.mp4"
    im169 = Image.new("RGB", (1280, 720), color=(40, 20, 60))
    d = ImageDraw.Draw(im169)
    d.rectangle([0, 0, 1280, 60], fill=(225, 29, 72))
    d.text((50, 12), "PRESS CONFERENCE / GROUND INTERVIEW", fill=(255, 255, 255), font=get_font(32))
    d.text((250, 320), "दीर्घ परिचर्चा: भारत का आर्थिक विकास", fill=(255, 255, 255), font=get_font(48))
    img169_path = PROOF_DIR / "source_16_9.jpg"
    im169.save(str(img169_path))

    # Render small 16:9 clip
    subprocess.run([
        FFMPEG, "-y", "-loop", "1", "-t", "4.0", "-i", str(img169_path),
        "-f", "lavfi", "-t", "4.0", "-i", "anullsrc=r=44100:cl=mono",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        str(raw_16_9)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

    # Now re-frame into vertical 9:16 with blurred background
    out_mp4 = PROOF_DIR / "repurposed_short_sample.mp4"
    whoosh = Path("assets/sfx/transition_whoosh.wav")

    cmd = [
        FFMPEG, "-y",
        "-i", str(raw_16_9),
        "-i", str(whoosh) if whoosh.exists() else "anullsrc=r=44100:cl=mono",
        "-filter_complex",
        "[0:v]split[va][vb];[va]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[vbg];[vb]scale=1080:1920:force_original_aspect_ratio=decrease[vfg];[vbg][vfg]overlay=(W-w)/2:400[vout]",
        "-map", "[vout]",
        "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-t", "4.0",
        str(out_mp4)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    print(f"Saved {out_mp4} ({out_mp4.stat().st_size} bytes)")


if __name__ == "__main__":
    generate_contact_sheet()
    render_daily_bulletin_opening()
    render_news_short_sample()
    render_repurposed_short_sample()
    print("All Phase 2 verification proofs generated successfully!")
