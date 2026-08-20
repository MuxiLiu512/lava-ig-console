#!/usr/bin/env python3
# Lava IG 排版引擎 v3 — 整篇渲染：讀文案 JSON＋底圖資料夾 → 輸出成品
# 用法: python3 render_post.py <文案.json> <底圖資料夾> <輸出資料夾>
import sys, json, os, re
from PIL import Image, ImageDraw, ImageFont

BRAND = "/sessions/clever-sweet-curie/mnt/brand/Lava Design System"
CTA_STOCK = "/sessions/clever-sweet-curie/mnt/brand/ig/20260705 AI 使人降智/最末圖公版.png"
W, H = 1950, 2600
YELLOW = (250, 210, 40)
ORANGE = (232, 66, 36)
ORANGE_DARK = (219, 53, 23)
WHITE = (255, 255, 255)
F_MED = BRAND + "/fonts/HarmonyOS_Sans_TC_Medium.ttf"
F_REG = BRAND + "/fonts/HarmonyOS_Sans_TC_Regular.ttf"
LOGO = BRAND + "/assets/logos/logo-white-horizontal.png"
NO_LEAD = set("。，、！？：；）」』…．,.!?;:%）")

def fit_bg(path):
    im = Image.open(path).convert("RGB")
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
    x = (im.width - W) // 2; y = (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))

def dyn_overlay(base, content_y, max_alpha=252, ambient=55, fade_span=0.30):
    fade_start = max(0, content_y - int(H * fade_span))
    g = Image.new("L", (1, H), 0)
    for y in range(H):
        if y <= fade_start: a = ambient
        elif y >= content_y: a = max_alpha
        else:
            t = (y - fade_start) / (content_y - fade_start); t = t*t*(3-2*t)
            a = int(ambient + (max_alpha - ambient) * t)
        g.putpixel((0, y), a)
    base.paste(Image.new("RGB", (W, H), (5,5,5)), (0,0), g.resize((W, H)))
    return base

_logo = None
def logo_img():
    global _logo
    if _logo is None:
        lg = Image.open(LOGO).convert("RGBA")
        w = int(W * 0.18)
        _logo = lg.resize((w, int(lg.height * w / lg.width)))
    return _logo

def draw_footer(d):
    fs = int(W * 0.022); f = ImageFont.truetype(F_REG, fs)
    y = H - int(H * 0.035) - fs
    d.text((int(W * 0.055), y), "@LAVA_DATING", font=f, fill=WHITE)
    t1, t2 = "LAVA", "不聊天的交友軟體"
    w1 = d.textlength(t1, font=f); w2 = d.textlength(t2, font=f)
    dot_r = fs * 0.10; gap = fs * 0.38
    x = W - int(W * 0.055) - (w1 + gap*2 + w2)
    d.text((x, y), t1, font=f, fill=WHITE)
    cy = y + fs * 0.58
    d.ellipse([x+w1+gap-dot_r, cy-dot_r, x+w1+gap+dot_r, cy+dot_r], fill=WHITE)
    d.text((x + w1 + gap*2, y), t2, font=f, fill=WHITE)

def parse_highlight(text):
    """display_copy 的【】標記 → (segment, color) 列表；行以 \n 保留。"""
    segs = []
    for part in re.split(r"(【[^】]*】)", text):
        if not part: continue
        if part.startswith("【") and part.endswith("】"):
            segs.append((part[1:-1], YELLOW))
        else:
            segs.append((part, WHITE))
    return segs

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

def draw_body(d, segments, x, y, font, max_w, lh):
    for line in wrap_segments(segments, font, max_w, d):
        cx = x
        for ch, color in line:
            d.text((cx, y), ch, font=font, fill=color)
            cx += d.textlength(ch, font=font)
        y += lh
    return y

def draw_eyebrow(d, text, y):
    fs = int(W * 0.024); f = ImageFont.truetype(F_MED, fs)
    text = text.upper(); gap = fs * 0.30
    total = sum(d.textlength(c, font=f) + gap for c in text) - gap
    x = (W - total) / 2; sw = max(1, int(fs * 0.03))
    for c in text:
        d.text((x, y), c, font=f, fill=ORANGE_DARK, stroke_width=sw, stroke_fill=ORANGE_DARK)
        x += d.textlength(c, font=f) + gap
    return y + fs

def draw_pill_arrow(d, top):
    pw, ph = int(W*0.125), int(W*0.070); px = (W-pw)/2
    st = int(W*0.0055)
    d.rounded_rectangle([px, top, px+pw, top+ph], radius=ph/2, outline=YELLOW, width=st)
    ay = top + ph/2; ax0, ax1 = px+pw*0.26, px+pw*0.74
    d.line([ax0, ay, ax1, ay], fill=YELLOW, width=st)
    d.line([ax1-ph*0.26, ay-ph*0.24, ax1, ay], fill=YELLOW, width=st)
    d.line([ax1-ph*0.26, ay+ph*0.24, ax1, ay], fill=YELLOW, width=st)
    return top + ph

def render_cover(slide, bg_path, out_path, eyebrow="LAVA DATING"):
    img = fit_bg(bg_path)
    img.paste(Image.new("RGB", (W,H), (5,5,5)), (0,0), Image.new("L", (W,H), 120))
    img = dyn_overlay(img, int(H*0.42), max_alpha=205, ambient=70, fade_span=0.25)
    d = ImageDraw.Draw(img)
    lg = logo_img(); mx = int(W*0.055)
    img.paste(lg, (mx, int(H*0.038)), lg)
    y = draw_eyebrow(d, eyebrow, int(H*0.245)) + int(H*0.028)
    fs_m = int(W*0.075); f_main = ImageFont.truetype(F_MED, fs_m); sw = int(fs_m*0.018)
    # 主標：heading 依【】混色（無標記則全白），自動換行置中
    segs = parse_highlight(slide.get("heading", ""))
    lines = wrap_segments(segs, f_main, W - 2*mx, d)
    for line in lines:
        total = sum(d.textlength(ch, font=f_main) for ch, _ in line)
        cx = (W - total) / 2
        for ch, color in line:
            d.text((cx, y), ch, font=f_main, fill=color, stroke_width=sw, stroke_fill=color)
            cx += d.textlength(ch, font=f_main)
        y += int(fs_m * 1.38)
    y += int(H*0.035)
    y = draw_pill_arrow(d, y) + int(H*0.030)
    # 副標：display_copy 去掉 heading 重複行後的其餘行，黃色置中
    sub_lines = [l for l in slide.get("display_copy", "").split("\n") if l.strip() and l.strip() not in slide.get("heading", "")]
    fs_s = int(W*0.032); f_sub = ImageFont.truetype(F_MED, fs_s)
    for t in sub_lines[:4]:
        t = t.replace("【", "").replace("】", "")
        tw = d.textlength(t, font=f_sub)
        d.text(((W-tw)/2, y), t, font=f_sub, fill=YELLOW)
        y += int(fs_s * 1.85)
    draw_footer(d)
    img.save(out_path)

def render_content(slide, bg_path, out_path):
    body_segs = parse_highlight(slide.get("display_copy", ""))
    f_body = ImageFont.truetype(F_MED, int(W*0.034))
    tmp = Image.new("RGB", (1,1)); dt = ImageDraw.Draw(tmp)
    mx = int(W*0.055)
    n_lines = len(wrap_segments(body_segs, f_body, W - 2*mx, dt))
    lh = int(W*0.034*1.72)
    body_h = n_lines * lh
    content_y = max(int(H*0.42), H - int(H*0.085) - body_h - int(H*0.025))
    img = dyn_overlay(fit_bg(bg_path), content_y)
    d = ImageDraw.Draw(img)
    lg = logo_img()
    img.paste(lg, (mx, int(H*0.038)), lg)
    title = slide.get("heading", "")
    fs_t = int(W*0.043)
    f_title = ImageFont.truetype(F_MED, fs_t)
    max_tw = W - 2*mx
    while d.textlength(title, font=f_title) > max_tw and fs_t > int(W*0.030):
        fs_t -= 2
        f_title = ImageFont.truetype(F_MED, fs_t)
    d.text((mx, int(H*0.038)+lg.height+int(H*0.012)), title, font=f_title,
           fill=YELLOW, stroke_width=max(1, int(fs_t*0.02)), stroke_fill=YELLOW)
    d.rectangle([mx, content_y, mx+int(W*0.05), content_y+int(H*0.005)], fill=ORANGE)
    draw_body(d, body_segs, mx, content_y+int(H*0.018), f_body, W-2*mx, lh)
    draw_footer(d)
    img.save(out_path)

def main(json_path, bg_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    data = json.load(open(json_path))
    bgs = {}
    for fn in os.listdir(bg_dir):
        m = re.match(r"slide-(\d+)\.(png|jpg|jpeg)$", fn, re.I)
        if m: bgs[int(m.group(1))] = os.path.join(bg_dir, fn)
    results = []
    for s in data["slides"]:
        i = s["index"]; role = str(s.get("role", ""))
        out = os.path.join(out_dir, f"final-{i:02d}.png")
        if "CTA" in role.upper():
            im = fit_bg(CTA_STOCK); im.save(out)
            results.append((i, "CTA公版", out)); continue
        bg = bgs.get(i)
        if not bg:
            results.append((i, "缺底圖，跳過", None)); continue
        if i == 1 or role == "Hook":
            render_cover(s, bg, out)
            results.append((i, "封面", out))
        else:
            render_content(s, bg, out)
            results.append((i, "內文", out))
    for r in results: print(r)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
