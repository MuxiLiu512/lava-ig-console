#!/usr/bin/env python3
"""產品介紹版型 — Lava 自家功能貼文專用（Superlike／成立約會／爽約處理…）。

為什麼要獨立一支：
  知識型貼文的公式是「滿版劇照＋文字疊加」，素材由 forager 從網路抓。
  產品介紹套這個公式會變成**拿別人的照片講自己的功能**——2026-08-17 Jesse 退件，
  原話「產品介紹的內容應該要是特別設計的，例如截圖的樣子，這是最低標」。
  產品介紹的素材只能是自家 App 介面（Drive `01_Product App Process/軟體介面圖/`），
  構圖是設計出來的卡片版面，不是照片疊字。

五種構圖（對照 Jesse 2026-08-17 給的參考稿）：
  hero    封面：中央 App 截圖卡＋紅框光暈＋星標，兩側襯淡卡；大標在下
  diagram 卡片堆疊圖解：淡卡 →（箭頭）→ 紅色重點卡
  notify  模擬推播：照片卡上疊白色通知卡（App icon＋一行粗體）
  price   大字數字卡：紅底圓角卡，小標＋巨大數字＋註腳
  cta     尾板：App Store／Google Play 徽章＋字標＋紅色膠囊按鈕

版面常數集中在這裡，檢查工具一律呼叫本檔函式，不要自己重算（self-check A9）。
"""
import os, sys, json, re, importlib.util
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 引擎位置多路徑尋找：本檔的正本放在 repo（scripts/）以便版控，
# render_post_v5.py 則在 repo 之外的 排版引擎/。寫死相對路徑會讓兩者只能同目錄，
# 而「腳本不在版控」已經害哨兵靜默停擺過兩次（2026-08-03、08-16）。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = next((p for p in [
    os.path.join(_HERE, "render_post_v5.py"),
    os.path.abspath(os.path.join(_HERE, "..", "..", "排版引擎", "render_post_v5.py")),
    os.path.abspath(os.path.join(_HERE, "..", "排版引擎", "render_post_v5.py")),
] if os.path.exists(p)), None)
if not _ENGINE:
    raise SystemExit("找不到 render_post_v5.py（排版引擎/）")
_spec = importlib.util.spec_from_file_location("rp5", _ENGINE)
E = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(E)

W, H = E.W, E.H
# 品牌色票正本：Lava Design System/colors_and_type.css
DARK  = (12, 14, 8)        # --olive-dark  #0C0E08
CREAM = (255, 230, 169)    # --soft-yellow #FFE6A9
RED   = (232, 66, 36)      # --lava-orange #E84224
INK   = (41, 45, 28)       # --night-olive #292D1C（米底上的深色字）
WHITE = (255, 255, 255)
DIM   = (30, 33, 24)       # 深底上的襯卡

MX          = 0.055        # 左右邊界，與 render_post_v5 一致
TOP_Y       = 0.052        # logo／頁碼上緣
LEAD_FS     = 0.030        # 上方導言
TITLE_FS    = 0.064        # 下方大標起始字級
TITLE_MIN   = 0.044
PAGE_FS     = 0.022
CARD_R      = 0.035        # 卡片圓角（佔 W）

CTA_STOCK = E.CTA_STOCK
# 徽章在 1080×1440 公版上的實測座標（純 PIL 掃描非黑列得出，2026-08-17）
BADGE_BOXES = [(104, 150, 517, 272), (104, 295, 517, 416)]


# ── 基礎 ────────────────────────────────────────────────────────────
def _bg(dark=True):
    return Image.new("RGB", (W, H), DARK if dark else CREAM)


def _fg(dark):      return WHITE if dark else INK
def _accent(dark):  return CREAM if dark else RED
def _muted(dark):   return CREAM if dark else (110, 116, 92)


def _glow(img, box, radius, color=RED, spread=0.05, alpha=150):
    """卡片後方的暈光。做法是畫一張放大的圓角實心圖再高斯模糊疊回去。"""
    pad = int(W * spread)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle([box[0]-pad, box[1]-pad, box[2]+pad, box[3]+pad],
                        radius=radius + pad, fill=color + (alpha,))
    lay = lay.filter(ImageFilter.GaussianBlur(pad * 0.75))
    img.alpha_composite(lay) if img.mode == "RGBA" else img.paste(
        Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB"), (0, 0))
    return img


def _round_paste(img, src, box, radius, border=None, bw=6):
    """把圖片以圓角貼上；border 有值就再描一圈。"""
    bx0, by0, bx1, by1 = box
    tw, th = bx1 - bx0, by1 - by0
    im = src.convert("RGB")
    # 等比填滿後置中裁切（不變形、不留邊）
    sc = max(tw / im.width, th / im.height)
    im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
    im = im.crop(((im.width - tw)//2, (im.height - th)//2,
                  (im.width - tw)//2 + tw, (im.height - th)//2 + th))
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tw-1, th-1], radius=radius, fill=255)
    img.paste(im, (bx0, by0), mask)
    if border:
        ImageDraw.Draw(img).rounded_rectangle(list(box), radius=radius, outline=border, width=bw)
    return img


def draw_pagination(d, idx, total, dark):
    if not idx or not total or idx <= 1:
        return
    fs = int(W * PAGE_FS); f = ImageFont.truetype(E.F_REG, fs)
    txt = "  ".join(list("%02d" % idx) + ["/"] + list("%02d" % total))
    d.text((W - int(W * MX) - d.textlength(txt, font=f), int(H * TOP_Y) + fs//3),
           txt, font=f, fill=_muted(dark))


def draw_logo(img, dark):
    lg = Image.open(E.LOGO if dark else E.LOGO.replace("white", "black")).convert("RGBA")
    w = int(W * 0.18); lg = lg.resize((w, int(lg.height * w / lg.width)))
    img.paste(lg, (int(W * MX), int(H * TOP_Y)), lg)


def draw_footer(d, dark):
    """深底沿用引擎公版；米底要換深色字，引擎那支寫死白色。"""
    if dark:
        return E.draw_footer(d)
    fs = int(W * 0.022); f = ImageFont.truetype(E.F_REG, fs)
    y = H - int(H * 0.052) - fs
    d.text((int(W * MX), y), "@LAVA_DATING", font=f, fill=INK)
    t1, t2 = "LAVA", "不聊天的交友軟體"
    w1 = d.textlength(t1, font=f); w2 = d.textlength(t2, font=f)
    dot_r = fs * 0.10; gap = fs * 0.38
    x = W - int(W * MX) - (w1 + gap*2 + w2)
    d.text((x, y), t1, font=f, fill=INK)
    cy = y + fs * 0.58
    d.ellipse([x+w1+gap-dot_r, cy-dot_r, x+w1+gap+dot_r, cy+dot_r], fill=INK)
    d.text((x + w1 + gap*2, y), t2, font=f, fill=INK)


# ── 文字塊 ──────────────────────────────────────────────────────────
def _recolor(lines, base, accent):
    """引擎的 parse_highlight 固定吐 WHITE／YELLOW／ORANGE；
    產品版型是雙色系統（深底=米色重點、米底=紅色重點），在這裡改寫顏色。"""
    out = []
    for line in lines:
        out.append([(tok, accent if col in (E.YELLOW, E.ORANGE) else base) for tok, col in line])
    return out


def title_lines(text, d, dark, max_w=None):
    """下方大標的斷行與字級（含逐級縮字）。檢查工具要驗排版一律呼叫本函式。

    行尾標點的處理與知識型貼文不同：self-check A7「行尾標點一律刪除」針對的是
    **排版當下才決定的斷行**（逗號被擠到行尾）。產品版型的大標是手寫短句，
    作者打的 \n 後面那個句號是語氣的一部分（Jesse 2026-08-17 參考稿：
    「不只喜歡你。／這次約會，我請。」兩行都有句號）。
    所以只清「同一段被寬度拆開」產生的行尾，段落自己的結尾原封不動。
    """
    max_w = max_w or (W - 2*int(W * MX))
    fs = int(W * TITLE_FS)
    paras = [p for p in (text or "").split("\n") if p.strip()]
    while True:
        f = ImageFont.truetype(E.F_MED, fs)
        lines = []
        for para in paras:
            wrapped = E.wrap_segments(E.parse_highlight(para.strip()), f, max_w, d)
            if len(wrapped) > 1:                       # 被寬度拆開才清行尾
                wrapped = E.strip_line_ends(wrapped[:-1]) + wrapped[-1:]
            lines += wrapped
        if len(lines) <= 3 or fs <= int(W * TITLE_MIN):
            return _recolor(lines, _fg(dark), _accent(dark)), f, fs
        fs = int(fs * 0.93)


def draw_title(img, d, text, dark, bottom):
    """大標貼齊 bottom（footer 上緣往上留白），由下往上長。"""
    if not (text or "").strip():
        return bottom          # price 版型沒有下方大標，靠數字卡本身承擔
    lines, f, fs = title_lines(text, d, dark)
    lh = int(fs * 1.30)
    y = bottom - len(lines) * lh
    E.draw_lines(d, lines, int(W * MX), y, f, lh)
    return y


def _lead_color(dark):
    """深底＝米色；米底＝深灰。紅色在米底上要留給重點字，導言用了會搶焦點
    （Jesse 參考稿第 3 張的導言是深灰不是紅）。"""
    return CREAM if dark else (92, 98, 76)


def draw_lead(d, text, dark, y):
    """上方導言：兩三行小字。行尾標點同 title_lines 的規則——
    作者手打的斷行保留，寬度造成的斷行才清。"""
    if not (text or "").strip():
        return y
    col = _lead_color(dark)
    fs = int(W * LEAD_FS); f = ImageFont.truetype(E.F_MED, fs)
    lh = int(fs * 1.55); max_w = int(W * 0.62)
    lines = []
    for para in [x for x in text.split("\n") if x.strip()]:
        wrapped = E.wrap_semantic(para.strip(), col, f, max_w, d)
        if len(wrapped) > 1:
            wrapped = E.strip_line_ends(wrapped[:-1]) + wrapped[-1:]
        lines += wrapped
    lines = _recolor(lines[:3], col, _accent(dark))
    E.draw_lines(d, lines, int(W * MX), y, f, lh)
    return y + len(lines) * lh


# ── 五種構圖 ────────────────────────────────────────────────────────
def _star(d, cx, cy, r, fill=WHITE):
    import math
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.42
        a = math.radians(-90 + i * 36)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    d.polygon(pts, fill=fill)


def lay_hero(img, d, slide, shot, dark):
    """封面：中央截圖卡＋紅框光暈＋星標徽章，兩側襯淡卡。"""
    ch = int(H * 0.245); cw = int(ch * 0.62)       # 手機比例
    cx, cy = W // 2, int(H * 0.315)
    box = [cx - cw, cy - ch, cx + cw, cy + ch]
    r = int(W * CARD_R)
    # 兩側襯卡：窄一點、短一點，只從主卡後面露出一角（參考稿是 peek 不是並排）
    sw = int(cw * 0.78)
    for sgn in (-1, 1):
        scx = cx + sgn * int(cw * 1.35)
        sb = [scx - sw, box[1] + int(ch*0.36), scx + sw, box[3] - int(ch*0.26)]
        d.rounded_rectangle(sb, radius=r, fill=DIM if dark else (240, 214, 150),
                            outline=(58, 62, 46) if dark else (232, 200, 132), width=4)
    img = _glow(img, box, r, RED, spread=0.035, alpha=120)
    d = ImageDraw.Draw(img)
    if shot:
        _round_paste(img, shot, box, r, border=RED, bw=int(W*0.005))
        d = ImageDraw.Draw(img)
    else:
        d.rounded_rectangle(box, radius=r, fill=DIM, outline=RED, width=int(W*0.005))
    # 星標徽章壓在卡片下緣
    br = int(W * 0.042)
    bb = [cx - br, box[3] - br, cx + br, box[3] + br]
    d.rounded_rectangle(bb, radius=int(br*0.32), fill=RED)
    _star(d, cx, box[3], int(br*0.52))
    return img, d


def lay_diagram(img, d, slide, shot, dark):
    """卡片堆疊圖解：兩張淡卡 →（箭頭）→ 紅色重點卡＋星＋標籤。"""
    cy = int(H * 0.52); ch = int(H * 0.135); cw = int(ch * 0.72)
    r = int(W * 0.028)
    lx = int(W * 0.30)
    for i, sgn in enumerate((-1, 0)):
        off = int(cw * 0.42 * i)
        sb = [lx - cw + off, cy - ch + int(ch*0.10*i), lx + cw + off, cy + ch]
        d.rounded_rectangle(sb, radius=r, fill=DIM if dark else (240, 214, 150),
                            outline=(58, 62, 46) if dark else (232, 200, 132), width=4)
    # 箭頭
    ax0, ax1 = int(W * 0.47), int(W * 0.585)
    d.line([(ax0, cy), (ax1, cy)], fill=_accent(dark), width=7)
    hw = int(W * 0.016)
    d.polygon([(ax1 + hw, cy), (ax1 - hw*0.3, cy - hw*0.75), (ax1 - hw*0.3, cy + hw*0.75)], fill=_accent(dark))
    # 重點卡
    rx = int(W * 0.755)
    rb = [rx - cw, cy - ch, rx + cw, cy + ch]
    img = _glow(img, rb, r, RED, spread=0.03, alpha=130); d = ImageDraw.Draw(img)
    d.rounded_rectangle(rb, radius=r, fill=RED)
    _star(d, rx, cy - int(ch*0.18), int(W*0.045))
    lbl = (slide.get("focus_label") or "你").strip()
    fs = int(W * 0.030); f = ImageFont.truetype(E.F_MED, fs)
    d.text((rx - d.textlength(lbl, font=f)/2, cy + int(ch*0.30)), lbl, font=f, fill=WHITE)
    return img, d


def lay_notify(img, d, slide, shot, dark):
    """模擬推播：媒體卡＋壓在其上的白色通知卡。

    版位會依來源比例切換——橫幅生活照走寬卡（同 Jesse 參考稿），
    直式 App 截圖走置中手機卡（硬塞進寬卡會被放大 4 倍只剩兩行字，2026-08-17 實測）。
    """
    r = int(W * 0.022)
    portrait = bool(shot) and (shot.height / max(1, shot.width)) > 1.2
    if portrait:
        ch = int(H * 0.225); cw = int(ch * 0.60)
        cx = W // 2; cy = int(H * 0.375)
        box = [cx - cw, cy - ch, cx + cw, cy + ch]
        _round_paste(img, shot, box, r, border=(58, 62, 46) if dark else (232, 200, 132), bw=4)
        d = ImageDraw.Draw(img)
        bx0, bx1, by1 = int(W * MX), W - int(W * MX), box[3] - int(ch * 0.30)
    else:
        bx0, bx1 = int(W * MX), W - int(W * MX)
        by0 = int(H * 0.195); by1 = by0 + int(H * 0.205)
        if shot:
            _round_paste(img, shot, [bx0, by0, bx1, by1], r)
        else:
            d.rounded_rectangle([bx0, by0, bx1, by1], radius=r, fill=DIM)
        d = ImageDraw.Draw(img)
    # 通知卡
    nh = int(H * 0.088); ny0 = by1 - int(nh * 0.42)
    _shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(_shadow).rounded_rectangle(
        [bx0, ny0 + int(nh*0.10), bx1, ny0 + nh + int(nh*0.10)],
        radius=int(W*0.020), fill=(0, 0, 0, 90))
    img.paste(Image.alpha_composite(img.convert("RGBA"),
              _shadow.filter(ImageFilter.GaussianBlur(int(W*0.010)))).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx0, ny0, bx1, ny0 + nh], radius=int(W*0.020), fill=WHITE)
    ir = int(nh * 0.30); ix = bx0 + int(W * 0.030); iy = ny0 + nh//2
    d.rounded_rectangle([ix, iy - ir, ix + 2*ir, iy + ir], radius=int(ir*0.42), fill=RED)
    _star(d, ix + ir, iy, int(ir * 0.52))
    tx = ix + 2*ir + int(W * 0.022)
    f_s = ImageFont.truetype(E.F_REG, int(W * 0.019))
    f_b = ImageFont.truetype(E.F_MED, int(W * 0.030))
    d.text((tx, iy - int(nh*0.30)), "L A V A", font=f_s, fill=(150, 152, 146))
    d.text((tx, iy - int(nh*0.06)), (slide.get("notify_text") or "有人送出了 Superlike"),
           font=f_b, fill=(20, 20, 18))
    return img, d


def lay_price(img, d, slide, shot, dark):
    """大字數字卡：紅底圓角，小標＋巨大數字；註腳在卡下方。"""
    bx0, bx1 = int(W * MX), W - int(W * MX)
    by0 = int(H * 0.335); by1 = by0 + int(H * 0.20)
    r = int(W * 0.030)
    img = _glow(img, [bx0, by0, bx1, by1], r, RED, spread=0.03, alpha=110)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=r, fill=RED)
    lab = (slide.get("price_label") or "").strip()
    amt = (slide.get("price_amount") or "").strip()
    px = bx0 + int(W * 0.032)
    if lab:
        f = ImageFont.truetype(E.F_MED, int(W * 0.030))
        d.text((px, by0 + int(H * 0.028)), lab, font=f, fill=WHITE)
    if amt:
        fs = int(W * 0.115)
        while fs > int(W * 0.05):
            f = ImageFont.truetype(E.F_MED, fs)
            if d.textlength(amt, font=f) <= (bx1 - bx0) - 2*int(W*0.032):
                break
            fs = int(fs * 0.93)
        d.text((px, by0 + int(H * 0.070)), amt, font=f, fill=WHITE)
    note = (slide.get("price_note") or "").strip()
    if note:
        f = ImageFont.truetype(E.F_REG, int(W * 0.026))
        d.text((px, by1 + int(H * 0.030)), note, font=f, fill=_accent(dark))
    return img, d


def lay_cta(img, d, slide, shot, dark):
    """尾板：商店徽章（取自 CTA 公版）＋字標＋一句話＋紅色膠囊按鈕。"""
    src = Image.open(CTA_STOCK).convert("RGB")
    bw = int(W * 0.30)
    y = int(H * 0.055)
    for bx0, by0, bx1, by1 in BADGE_BOXES:
        bd = src.crop((bx0, by0, bx1, by1))
        bh = int(bd.height * bw / bd.width)
        img.paste(bd.resize((bw, bh), Image.LANCZOS), (int(W * MX), y))
        y += bh + int(H * 0.012)
    return img, d


LAYOUTS = {"hero": lay_hero, "diagram": lay_diagram, "notify": lay_notify,
           "price": lay_price, "cta": lay_cta}


# ── 單張渲染 ────────────────────────────────────────────────────────
def _pill(d, text, x, y, dark):
    fs = int(W * 0.036); f = ImageFont.truetype(E.F_MED, fs)
    tw = d.textlength(text, font=f)
    pad_x, pad_y = int(W * 0.045), int(fs * 0.62)
    sr = int(fs * 0.40)
    bw = int(sr*2 + W*0.018 + tw + pad_x*2)
    bh = int(fs + pad_y*2)
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=bh//2, fill=RED)
    _star(d, x + pad_x + sr, y + bh//2, sr)
    d.text((x + pad_x + sr*2 + int(W*0.018), y + pad_y - int(fs*0.06)), text, font=f, fill=WHITE)
    return y + bh


def _render_cta(slide, out_path, dark=True):
    img = _bg(dark); d = ImageDraw.Draw(img)
    img, d = lay_cta(img, d, slide, None, dark)
    y = int(H * 0.335)
    lg = Image.open(E.LOGO if dark else E.LOGO.replace("white", "black")).convert("RGBA")
    lw = int(W * 0.42); lg = lg.resize((lw, int(lg.height * lw / lg.width)))
    img.paste(lg, (int(W * MX), y), lg); d = ImageDraw.Draw(img)
    y += lg.height - int(H * 0.004)
    f = ImageFont.truetype(E.F_MED, int(W * 0.062))
    d.text((int(W * MX), y), "不聊天的交友軟體", font=f, fill=_fg(dark))
    y += int(W * 0.062 * 1.5)
    d.line([(int(W*MX), y), (int(W*MX) + int(W*0.075), y)], fill=RED, width=int(H*0.004))
    y += int(H * 0.030)
    y = draw_lead(d, slide.get("display_copy") or "", dark, y) + int(H * 0.020)
    hl = (slide.get("heading") or "").strip()
    if hl:
        fh = ImageFont.truetype(E.F_MED, int(W * 0.052))
        d.text((int(W * MX), y), re.sub(r"[【】〖〗]", "", hl), font=fh, fill=_accent(dark))
        y += int(W * 0.052 * 1.6)
    _pill(d, (slide.get("cta_button") or "打開 Lava"), int(W * MX), int(H * 0.815), dark)
    draw_footer(d, dark)
    img.save(out_path, quality=95)
    return out_path


def render_slide(slide, shot_path, out_path, idx=None, total=None):
    layout = (slide.get("product_layout") or "diagram").strip()
    dark = (slide.get("bg") or "dark") != "cream"
    if layout == "cta":
        return _render_cta(slide, out_path, dark)

    img = _bg(dark); d = ImageDraw.Draw(img)
    draw_logo(img, dark); d = ImageDraw.Draw(img)
    draw_pagination(d, idx, total, dark)

    shot = None
    if shot_path and os.path.exists(shot_path):
        shot = Image.open(shot_path)

    footer_top = H - int(H * 0.052) - int(W * 0.022)
    if layout == "hero":
        img, d = lay_hero(img, d, slide, shot, dark)
        eyebrow = (slide.get("eyebrow") or "").strip()
        eb_h = int(H * 0.075) if eyebrow else 0
        ty = draw_title(img, d, slide.get("heading") or "", dark, footer_top - int(H*0.055) - eb_h)
        if eyebrow:
            fs = int(W * 0.028); f = ImageFont.truetype(E.F_MED, fs)
            d.text((int(W * MX), footer_top - int(H*0.070)),
                   "  ".join(eyebrow.upper()), font=f, fill=RED)
    else:
        draw_lead(d, slide.get("display_copy") or "", dark, int(H * 0.135))
        img, d = LAYOUTS[layout](img, d, slide, shot, dark)
        draw_title(img, d, slide.get("heading") or "", dark, footer_top - int(H * 0.055))
    draw_footer(d, dark)
    img.save(out_path, quality=95)
    return out_path


def main(json_path, shots_dir, out_dir):
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    slides = doc.get("slides", [])
    os.makedirs(out_dir, exist_ok=True)
    total = len(slides)
    for i, s in enumerate(slides, 1):
        shot = s.get("shot") or ""
        sp = os.path.join(shots_dir, shot) if shot and shots_dir else ""
        out = os.path.join(out_dir, "slide-%d.jpg" % i)
        render_slide(s, sp, out, idx=i, total=total)
        print("✓ slide-%d [%s] %s" % (i, s.get("product_layout") or "diagram",
                                      os.path.basename(shot) if shot else "無截圖"))
    print("完成 %d 張 → %s" % (total, out_dir))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
