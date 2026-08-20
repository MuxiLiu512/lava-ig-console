#!/usr/bin/env python3
# Lava IG 自動排版引擎 v2 — 依風格規格 v0.7 第十節（2026-07-09 六點回饋修訂）
from PIL import Image, ImageDraw, ImageFont

BRAND = "/sessions/clever-sweet-curie/mnt/brand/Lava Design System"
OUT = "/sessions/clever-sweet-curie/mnt/outputs"
W, H = 1950, 2600
YELLOW = (250, 210, 40)        # 重點黃（提高飽和，v0.7）
ORANGE = (232, 66, 36)         # Lava Orange #E84224（橘槓）
ORANGE_DARK = (219, 53, 23)    # Lava Orange Dark #DB3517（英文眉標）
WHITE = (255, 255, 255)

F_MED = BRAND + "/fonts/HarmonyOS_Sans_TC_Medium.ttf"
F_REG = BRAND + "/fonts/HarmonyOS_Sans_TC_Regular.ttf"
LOGO = BRAND + "/assets/logos/logo-white-horizontal.png"
BG = BRAND + "/assets/photos/icebreaker-table.jpg"

def fit_bg(path):
    im = Image.open(path).convert("RGB")
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))

def dyn_overlay(base, content_y, max_alpha=252, ambient=55, fade_span=0.30):
    """上到下漸層：頂部維持 ambient 微遮罩，於 content_y 前 fade_span*H 開始加深，
    到內文起點（橘槓位置）達到最深並持續到底。"""
    fade_start = max(0, content_y - int(H * fade_span))
    g = Image.new("L", (1, H), 0)
    for y in range(H):
        if y <= fade_start:
            a = ambient
        elif y >= content_y:
            a = max_alpha
        else:
            t = (y - fade_start) / (content_y - fade_start)
            t = t * t * (3 - 2 * t)
            a = int(ambient + (max_alpha - ambient) * t)
        g.putpixel((0, y), a)
    g = g.resize((W, H))
    base.paste(Image.new("RGB", (W, H), (5, 5, 5)), (0, 0), g)
    return base

def logo_img(width):
    lg = Image.open(LOGO).convert("RGBA")
    r = width / lg.width
    return lg.resize((width, int(lg.height * r)))

def draw_footer(d):
    fs = int(W * 0.022)
    f = ImageFont.truetype(F_REG, fs)
    y = H - int(H * 0.035) - fs
    d.text((int(W * 0.055), y), "@LAVA_DATING", font=f, fill=WHITE)
    t1, t2 = "LAVA", "不聊天的交友軟體"
    w1 = d.textlength(t1, font=f); w2 = d.textlength(t2, font=f)
    dot_r = fs * 0.10; gap = fs * 0.38
    x = W - int(W * 0.055) - (w1 + gap * 2 + w2)
    d.text((x, y), t1, font=f, fill=WHITE)
    cy = y + fs * 0.58
    d.ellipse([x + w1 + gap - dot_r, cy - dot_r, x + w1 + gap + dot_r, cy + dot_r], fill=WHITE)
    d.text((x + w1 + gap * 2, y), t2, font=f, fill=WHITE)

def draw_eyebrow(d, text, y, fs=None, color=ORANGE_DARK, tracking=0.30):
    """英文眉標：uppercase、寬字距、置中。"""
    fs = fs or int(W * 0.024)
    f = ImageFont.truetype(F_MED, fs)
    text = text.upper()
    gap = fs * tracking
    total = sum(d.textlength(c, font=f) + gap for c in text) - gap
    x = (W - total) / 2
    sw = max(1, int(fs * 0.03))
    for c in text:
        d.text((x, y), c, font=f, fill=color, stroke_width=sw, stroke_fill=color)
        x += d.textlength(c, font=f) + gap
    return y + fs

NO_LEAD = set("。，、！？：；）」』…．,.!?;:%")
def wrap_segments(segments, font, max_w, d):
    lines, cur, cur_w = [], [], 0.0
    for text, color in segments:
        for ch in text:
            if ch == "\n":
                lines.append(cur); cur, cur_w = [], 0.0; continue
            w = d.textlength(ch, font=font)
            if cur_w + w > max_w and cur and ch not in NO_LEAD:
                lines.append(cur); cur, cur_w = [], 0.0
            cur.append((ch, color)); cur_w += w
    if cur: lines.append(cur)
    return lines

def draw_body(d, segments, x, y, font, max_w, lh, stroke=0):
    for line in wrap_segments(segments, font, max_w, d):
        cx = x
        for ch, color in line:
            d.text((cx, y), ch, font=font, fill=color, stroke_width=stroke, stroke_fill=color)
            cx += d.textlength(ch, font=font)
        y += lh
    return y

def draw_center_segline(d, segline, y, font, stroke=0):
    total = sum(d.textlength(t, font=font) for t, _ in segline)
    x = (W - total) / 2
    for t, color in segline:
        d.text((x, y), t, font=font, fill=color, stroke_width=stroke, stroke_fill=color)
        x += d.textlength(t, font=font)

def draw_pill_arrow(d, cy_top):
    """黃色膠囊箭頭：比例約 1.8:1、粗描邊。回傳底部 y。"""
    pw, ph = int(W * 0.125), int(W * 0.070)
    px = (W - pw) / 2
    stroke = int(W * 0.0055)
    d.rounded_rectangle([px, cy_top, px + pw, cy_top + ph], radius=ph / 2, outline=YELLOW, width=stroke)
    ay = cy_top + ph / 2
    ax0, ax1 = px + pw * 0.26, px + pw * 0.74
    aw = int(W * 0.0055)
    d.line([ax0, ay, ax1, ay], fill=YELLOW, width=aw)
    d.line([ax1 - ph * 0.26, ay - ph * 0.24, ax1, ay], fill=YELLOW, width=aw)
    d.line([ax1 - ph * 0.26, ay + ph * 0.24, ax1, ay], fill=YELLOW, width=aw)
    return cy_top + ph

# ============ 內文版 ============
CONTENT_Y = int(H * 0.60)          # 橘槓位置；遮罩據此動態計算
img = fit_bg(BG)
img = dyn_overlay(img, CONTENT_Y)
d = ImageDraw.Draw(img)
lg = logo_img(int(W * 0.18))
mx = int(W * 0.055)
img.paste(lg, (mx, int(H * 0.038)), lg)

fs_t = int(W * 0.045)
f_title = ImageFont.truetype(F_MED, fs_t)
d.text((mx, int(H * 0.038) + lg.height + int(H * 0.012)),
       "大腦討厭「未完成」，遠超過討厭「結束」",
       font=f_title, fill=YELLOW, stroke_width=int(fs_t * 0.02), stroke_fill=YELLOW)

d.rectangle([mx, CONTENT_Y, mx + int(W * 0.05), CONTENT_Y + int(H * 0.005)], fill=ORANGE)
f_body = ImageFont.truetype(F_MED, int(W * 0.036))
segs = [
    ("心理學家 Bluma Zeigarnik 發現，人對未完成事件的注意力遠高於已完成事件，這就是", WHITE),
    ("蔡格尼效應（Zeigarnik Effect）", YELLOW),
    ("。\n一個已讀沒回的對話，在大腦裡是一個", WHITE),
    ("持續消耗資源的懸空迴路", YELLOW),
    ("，它會佔住你的注意力，", WHITE),
    ("直到迴路被關閉為止", YELLOW),
    ("。", WHITE),
]
draw_body(d, segs, mx, CONTENT_Y + int(H * 0.018), f_body, W - 2 * mx, int(W * 0.036 * 1.75))
draw_footer(d)
img.save(OUT + "/POC-內文版.png")

# ============ 封面版 ============
COVER_ANCHOR = int(H * 0.42)       # 主視覺文字重心；遮罩往下全暗
img2 = fit_bg(BG)
img2.paste(Image.new("RGB", (W, H), (5, 5, 5)), (0, 0), Image.new("L", (W, H), 120))
img2 = dyn_overlay(img2, COVER_ANCHOR, max_alpha=205, ambient=70, fade_span=0.25)
d2 = ImageDraw.Draw(img2)
img2.paste(lg, (mx, int(H * 0.038)), lg)

y = int(H * 0.245)
y = draw_eyebrow(d2, "Read but no reply", y) + int(H * 0.028)

fs_m = int(W * 0.082)
f_main = ImageFont.truetype(F_MED, fs_m)
sw_m = int(fs_m * 0.018)
main_lines = [
    [("你盯著", WHITE), ("「已讀」", YELLOW), ("兩個字", WHITE)],
    [("比等一個", WHITE), ("壞消息", YELLOW), ("還難受", WHITE)],
]
for line in main_lines:
    draw_center_segline(d2, line, y, f_main, stroke=sw_m)
    y += int(fs_m * 1.38)

y += int(H * 0.040)
y = draw_pill_arrow(d2, y) + int(H * 0.032)

fs_s = int(W * 0.034)
f_sub = ImageFont.truetype(F_MED, fs_s)
for t in ["訊息已讀，對方沒有回", "你的焦慮不是想太多", "是大腦面對不確定性的預設反應"]:
    tw = d2.textlength(t, font=f_sub)
    d2.text(((W - tw) / 2, y), t, font=f_sub, fill=YELLOW)
    y += int(fs_s * 1.9)
draw_footer(d2)
img2.save(OUT + "/POC-封面版.png")
print("done")
