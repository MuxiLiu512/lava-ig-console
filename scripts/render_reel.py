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
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
F_MED = os.path.join(BRAND, "fonts", "HarmonyOS_Sans_TC_Medium.ttf")
INK = (22, 24, 26, 255)          # 亮底上的深墨
ORANGE = (232, 66, 36, 255)      # Lava Orange，只給重點與品牌線

# ── 字卡語言 v2（2026-08-22，Jesse 參考〈愛情城市〉〈微醺大飯店〉後定向）────
# 三種字體：brand（版面公版）、ming（宋體，電影字卡感）、hand（辰宇落雁體，
# OFL 授權可商用，檔存 repo assets/fonts；原檔 hinting 過複雜，PIL 的 FreeType
# 畫不動（too many function definitions），已用 fontTools 去 hinting 另存 nohint 版）。
FONT_FILES = {
    "brand": (F_MED, 0),
    "ming":  ("/System/Library/Fonts/Supplemental/Songti.ttc", 2),   # Songti TC Bold
    "hand":  (os.path.join(REPO, "assets", "fonts", "ChenYuluoyan-Thin-nohint.ttf"), 0),
}
COLORS = {
    "white": (250, 250, 248, 255), "ink": INK, "orange": ORANGE,
    "cream": (255, 230, 169, 255), "gray": (150, 152, 146, 255),
    "neon_pink": (255, 45, 178, 255), "neon_green": (183, 255, 60, 255),
}
_FCACHE = {}


def _font(key, size):
    path, idx = FONT_FILES.get(key, FONT_FILES["brand"])
    k = (key, size)
    if k not in _FCACHE:
        _FCACHE[k] = ImageFont.truetype(path, size, index=idx)
    return _FCACHE[k]


def _scribble(d, box, color, w=6):
    """手繪感圈註：兩圈帶缺口、微錯位的橢圓（參考稿的白色麥克筆圈選）。"""
    x0, y0, x1, y1 = box
    pad = 26
    d.arc([x0-pad, y0-pad, x1+pad, y1+pad], start=-30, end=318, fill=color, width=w)
    d.arc([x0-pad-7, y0-pad+4, x1+pad+5, y1+pad+9], start=-8, end=300, fill=color, width=max(3, w-2))


def _draw_runs_h(d, lines, base, y):
    """橫排：每行置中，run 可各自字體/顏色/縮放；回傳（結束 y、圈註清單）。"""
    circles = []
    for runs in lines:
        widths, maxh = [], 0
        for r in runs:
            f = _font(r.get("f", "brand"), int(base * r.get("s", 1.0)))
            widths.append(d.textlength(r["t"], font=f)); maxh = max(maxh, f.size)
        x = (W - sum(widths)) / 2
        for r, w in zip(runs, widths):
            fs = int(base * r.get("s", 1.0)); f = _font(r.get("f", "brand"), fs)
            yy = y + (maxh - fs)          # 底對齊，大小字同行不飄
            d.text((x, yy), r["t"], font=f, fill=COLORS.get(r.get("c", "white"), COLORS["white"]))
            if r.get("circle"):
                circles.append(([x, yy, x + w, yy + fs], COLORS.get(r.get("circle") if isinstance(r.get("circle"), str) else r.get("c", "white"), COLORS["neon_pink"])))
            x += w
        y += int(maxh * 1.5)
    return y, circles


def _draw_runs_v(d, lines, base, y_top):
    """直排：一行＝一直欄，右欄先讀（右→左）；字由上而下。微醺大飯店的排法。"""
    circles = []
    col_ws = []
    for runs in lines:
        col_ws.append(max(int(base * r.get("s", 1.0)) for r in runs))
    gap = int(base * 0.55)
    total_w = sum(col_ws) + gap * (len(col_ws) - 1)
    x_right = (W + total_w) / 2
    for runs, cw in zip(lines, col_ws):
        x_right -= cw
        y = y_top
        for r in runs:
            fs = int(base * r.get("s", 1.0)); f = _font(r.get("f", "brand"), fs)
            col = COLORS.get(r.get("c", "white"), COLORS["white"])
            x = x_right + (cw - fs) / 2
            ry0 = y
            for ch in r["t"]:
                d.text((x, y), ch, font=f, fill=col)
                y += int(fs * 1.12)
            if r.get("circle"):
                circles.append(([x - 6, ry0, x + fs + 6, y - int(fs * 0.08)],
                                COLORS.get(r.get("circle") if isinstance(r.get("circle"), str) else "neon_pink", COLORS["neon_pink"])))
            y += int(fs * 0.3)
        x_right -= gap
    return circles


LOGOS = {
    "white": os.path.join(BRAND, "assets", "logos", "logo-white-horizontal.png"),
    "black": os.path.join(BRAND, "assets", "logos", "logo-black-horizontal.png"),
    "orange": os.path.join(BRAND, "assets", "logos", "logo-orange-horizontal.png"),
}


def card_png(card, out):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fs = int(card.get("size", 68))
    y = int(H * card.get("y", 0.24))
    lg = card.get("logo")
    if lg:
        lp = LOGOS.get(lg.get("variant", "white"), LOGOS["white"])
        li = Image.open(lp).convert("RGBA")
        lw = int(W * float(lg.get("w", 0.5)))
        li = li.resize((lw, int(li.height * lw / li.width)))
        im.paste(li, (int((W - lw) / 2), int(H * float(lg.get("y", 0.30)))), li)
    if card.get("handle"):
        fh = _font("brand", 30)
        t = "@LAVA_DATING"
        d.text(((W - d.textlength(t, font=fh)) / 2, int(H * float(card.get("handle_y", 0.72)))),
               t, font=fh, fill=COLORS["gray"])
    if card.get("lines"):                      # v2：runs 語法（雙字體/變色/圈註/直排）
        if card.get("layout") == "v":
            circles = _draw_runs_v(d, card["lines"], fs, y)
        else:
            _, circles = _draw_runs_h(d, card["lines"], fs, y)
        for box, col in circles:
            _scribble(d, box, col)
    elif card.get("text"):                     # v1 相容：單字體白/墨字
        f = ImageFont.truetype(F_MED, fs)
        for line in card["text"].split("\n"):
            w = d.textlength(line, font=f)
            d.text(((W - w) / 2, y), line, font=f, fill=INK)
            y += int(fs * 1.45)
    if card.get("brand"):
        y = int(H * card.get("brand_y", 0.62)) if card.get("lines") else y
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
    intro = spec.get("intro_fade")
    if intro:
        # 黑底開場：字卡先講話，影像晚點浮現（微醺大飯店的開場手法）
        chain += ",fade=in:st=%.2f:d=%.2f" % (float(intro.get("st", 1.0)), float(intro.get("d", 1.4)))
    ec = spec.get("endcard_video")
    if ec:
        # 品牌尾板（Jesse 2026-08-22）：結尾不能只剩聲音，影像模糊淡出、
        # Logo 與產品 hook 接手。做法：split 出一路 gblur＋壓暗，xfade 溶接回主路。
        chain += "[vpre]"
        filters.append(chain)
        filters.append("[vpre]split[ea][eb]")
        filters.append("[eb]gblur=sigma=%s,eq=brightness=-%.2f[eb2]"
                       % (ec.get("blur", 16), float(ec.get("darken", 0.22))))
        filters.append("[ea][eb2]xfade=transition=fade:duration=%.2f:offset=%.2f[v0]"
                       % (float(ec.get("d", 0.7)), float(ec.get("t0"))))
    else:
        chain += "[v0]"
        filters.append(chain)
    for i, c in enumerate(cards):
        png = os.path.join(tmp, "c%d.png" % i)
        card_png(c, png)
        inputs += ["-framerate", "30", "-loop", "1", "-t", "%.2f" % total, "-i", png]
        t0, t1 = float(c["t0"]), float(c["t1"])
        if c.get("cut"):
            # 快閃卡：硬切不淡，靠 overlay enable 控制時窗（參考片的文字快閃節奏）
            filters.append("[%d:v]format=rgba[c%d]" % (i + 1, i))
        else:
            fade = "format=rgba,fade=in:st=%.2f:d=0.25:alpha=1" % t0
            if not c.get("hold"):
                fade += ",fade=out:st=%.2f:d=0.25:alpha=1" % (t1 - 0.25)
            filters.append("[%d:v]%s[c%d]" % (i + 1, fade, i))
        _en = "enable='between(t,%.3f,%.3f)'" % (t0, t1) if c.get("cut") else ""
        filters.append("[v%d][c%d]overlay%s[v%d]" % (i, i, ("=" + _en) if _en else "", i + 1))
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
