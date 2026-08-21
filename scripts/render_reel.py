#!/usr/bin/env python3
"""Reels 合成器：AI 底片 ＋ 程式化字卡 → 9:16 成品。

設計依據（docs/design/Reels-* 研究結論，Jesse 2026-08-21 核准開做樣片）：
  AI 只負責「無臉會呼吸的底」；文字與節奏由程式控制，不叫模型畫字。
  字卡速度守 Netflix 繁中字幕上限（9 字/秒），實際控制在 4.5 字/秒以下。
  滿版無邊框、結尾凍格延長利於循環（IG 排序看含重播的總觀看秒數）。

用法：
  python3 scripts/render_reel.py <spec.json>
spec 格式見 data/reels/ 下的範例。
"""
import os, sys, json, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BRAND = "/Users/mimo/my-site/brand/Lava Design System"
F_MED = os.path.join(BRAND, "fonts", "HarmonyOS_Sans_TC_Medium.ttf")
INK = (22, 24, 26, 255)          # 亮底上的深墨
ORANGE = (232, 66, 36, 255)      # Lava Orange，只給重點與品牌線


def card_png(card, out):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fs = int(card.get("size", 68))
    f = ImageFont.truetype(F_MED, fs)
    y = int(H * card.get("y", 0.24))
    for line in card["text"].split("\n"):
        w = d.textlength(line, font=f)
        d.text(((W - w) / 2, y), line, font=f, fill=INK)
        y += int(fs * 1.45)
    if card.get("brand"):
        y += int(fs * 0.35)
        d.rectangle([W/2 - 36, y, W/2 + 36, y + 6], fill=ORANGE)
        y += 30
        fb = ImageFont.truetype(F_MED, 30)
        t = "LAVA · 不聊天的交友軟體"
        d.text(((W - d.textlength(t, font=fb)) / 2, y), t, font=fb, fill=INK)
        y += 48
        fh = ImageFont.truetype(F_MED, 26)
        t2 = "@LAVA_DATING"
        d.text(((W - d.textlength(t2, font=fh)) / 2, y), t2, font=fh, fill=(120, 122, 118, 255))
    im.save(out)


def main(spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    base, cards = spec["base"], spec["cards"]
    freeze = float(spec.get("freeze", 0))
    total = float(spec["duration"]) + freeze
    tmp = tempfile.mkdtemp(prefix="reel-")
    inputs, filters = ["-i", base], []
    chain = "[0:v]scale=%d:%d" % (W, H)
    if freeze:
        chain += ",tpad=stop_mode=clone:stop_duration=%.2f" % freeze
    chain += "[v0]"
    filters.append(chain)
    for i, c in enumerate(cards):
        png = os.path.join(tmp, "c%d.png" % i)
        card_png(c, png)
        inputs += ["-framerate", "30", "-loop", "1", "-t", "%.2f" % total, "-i", png]
        t0, t1 = float(c["t0"]), float(c["t1"])
        # 淡入淡出走 alpha，柔而不搶；最後一張留到片尾不淡出（凍格＝品牌停留）
        fade = "format=rgba,fade=in:st=%.2f:d=0.25:alpha=1" % t0
        if not c.get("hold"):
            fade += ",fade=out:st=%.2f:d=0.25:alpha=1" % (t1 - 0.25)
        filters.append("[%d:v]%s[c%d]" % (i + 1, fade, i))
        filters.append("[v%d][c%d]overlay[v%d]" % (i, i, i + 1))
    out = spec["out"]
    cmd = ["ffmpeg", "-y"] + inputs
    audio = spec.get("audio")
    if audio and os.path.exists(audio):
        cmd += ["-i", audio]
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v%d]" % len(cards)]
    if audio and os.path.exists(audio):
        cmd += ["-map", "%d:a" % (len(cards) + 1), "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-t", "%.2f" % total, "-r", "30", "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("✗ ffmpeg：" + r.stderr[-600:])
    print("✓ %s（%.1fs，%d 張字卡%s）" % (out, total, len(cards), "，含音軌" if audio else "，無音軌"))


if __name__ == "__main__":
    main(sys.argv[1])
