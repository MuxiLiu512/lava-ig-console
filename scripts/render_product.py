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
# 品牌字型的完整字重。設計系統的 fonts/ 原本只收了 Thin／Regular／Medium，
# 於是尾板整版同一個重量、價格數字比原稿細三分之一，只能用描邊硬撐
# （Jesse 2026-08-23：字重沒有層級）。Bold／Black 原廠就有，2026-08-23 補進 fonts/。
# 實測：原稿 NT$0 的筆寬÷墨高＝0.169，Medium 0.106、Bold 0.145、Black 0.169——
# 也就是原稿那個數字本來就是 Black 畫的，不是 Bold。
F_BOLD  = E.BRAND + "/fonts/HarmonyOS_Sans_TC_Bold.ttf"
F_BLACK = E.BRAND + "/fonts/HarmonyOS_Sans_TC_Black.ttf"
# 品牌色票正本：Lava Design System/colors_and_type.css
DARK  = (12, 14, 8)        # --olive-dark  #0C0E08
CREAM = (255, 230, 169)    # --soft-yellow #FFE6A9
RED   = (232, 66, 36)      # --lava-orange #E84224
INK   = (41, 45, 28)       # --night-olive #292D1C（米底上的深色字）
WHITE = (255, 255, 255)
OFFWHITE = (245, 247, 242)  # --neutral-50 #F5F7F2，大字用；純白壓在近黑底上會刺眼
DIM   = (30, 33, 24)       # 深底上的襯卡

# 原稿全頁左右邊界實測 0.075W（導言、註腳、footer、紅卡左緣量到的都是 81/1080）。
# 這裡原本沿用知識型引擎的 0.055，所以每一張的內容都比原稿寬一點點，
# 疊起來就是「說不出哪裡但就是不一樣」（Jesse 2026-08-23 要求對標）。
MX          = 0.075
TOP_Y       = 0.052        # logo／頁碼上緣
LEAD_FS     = 0.030        # 上方導言
TITLE_FS    = 0.064        # 下方大標起始字級
TITLE_MIN   = 0.044
PAGE_FS     = 0.022
CARD_R      = 0.035        # 卡片圓角（佔 W）

# ── 垂直節奏 ────────────────────────────────────────────────────────
# 第一版每個版型各自寫死 y 值（cy=0.52、by0=0.335…），結果是剩餘空間
# 全部堆在版面下半部變成大片空洞，各張的留白也對不齊（Jesse 2026-08-17 退件）。
# 改成「階梯 + 內容帶」：間距只能取自這個階梯，視覺元件置中於剩餘的帶內，
# 空白由系統分配而不是由硬寫的座標決定。基準 8px 網格 ×3 = 24px。
U   = 24
S_XS, S_SM, S_MD, S_LG, S_XL = U, U*2, U*3, U*5, U*7      # 24 48 72 120 168
GAP_HEADER = S_LG          # logo 底 → 導言
GAP_LEAD   = S_XL          # 導言底 → 內容帶
GAP_STAGE  = S_XL          # 內容帶 → 大標
GAP_TITLE  = S_LG          # 大標底 → footer 上緣
BAND_FILL  = 0.94          # 視覺元件最多吃掉內容帶的比例，四周留呼吸

# 媒體版位的比例與高度：全部量自 Jesse 原稿（1080×1350），不是憑感覺調的。
# hero 原本寫 0.62「手機比例」是為了放 App 截圖；改放真人照片後太窄，
# 臉會被切掉兩側（Jesse 2026-08-23：五官要清晰可見、不要裁切）。
HERO_ASPECT = 0.75         # 原稿卡框 0.394W × 0.419H → 寬高比 0.75
HERO_H      = 0.419        # 卡片總高佔 H
NOTIFY_H    = 0.2325       # 橫幅媒體帶總高佔 H（原稿 3.06:1，舊值 0.205 等於 3.47:1 太扁）

# 價格卡字級：拿原稿的**實際墨高**去反解字級得到的，不是用 cap-height 比例估的。
# 先前用 0.72 這個經驗值換算，把 NT$0 估成 0.235W，實際大了 40%（Jesse 2026-08-23 退件）。
# 校準法：在同一支字型下逐級渲染，量 getbbox 高度，取最接近原稿墨高的那級。
FS_PRICE_LABEL  = 0.032    # 原稿墨高 33px@1080 → 0.032W
FS_PRICE_AMOUNT = 0.168    # 原稿墨高 183px@1080 → 0.168W
# 卡內位置全用卡片自身比例表示，卡片改大改小都跟著走（原稿卡 918×392px@1080）
PRICE_PAD_X       = 0.061  # 筆位左內縮 ÷ 卡寬（56/918）
PRICE_LABEL_TOP   = 0.207  # 標籤墨頂 ÷ 卡高（81/392）
PRICE_AMOUNT_TOP  = 0.401  # 數字墨頂 ÷ 卡高（157/392）
FS_PRICE_NOTE = 0.0267     # 原稿註腳墨高 28px@1080（先前 0.036 目測，大了三成）

PRODUCT_TPL_ID = "tpl-product-intro-carousel"
DESIGN_LAYOUTS = ("diagram", "price", "cta")   # 引擎繪製的設計版面，不需要照片


def footer_top():
    """footer 文字的上緣。render_slide 與 lay_price 都要用它定位，
    寫兩份遲早會分岔（self-check A9：同一個數字只能有一個來源）。"""
    return H - int(H * 0.052) - int(W * 0.022)


def frame_specs():
    """媒體版位的取景框比例（寬/高）。操控室裁切預覽的唯一數字來源——
    比例只在這裡宣告，JS 端只消費存進 posts.json 的數字（A9：不准兩邊各算一套）。"""
    return {
        "hero": HERO_ASPECT,
        "notify_portrait": 0.60,                             # lay_notify 直式手機卡
        "notify_landscape": round((W * (1 - 2 * MX)) / (H * NOTIFY_H), 3),
    }
CTA_STOCK = E.CTA_STOCK
# 徽章在 1080×1440 公版上的實測座標（純 PIL 掃描非黑列得出，2026-08-17）
BADGE_BOXES = [(104, 150, 517, 272), (104, 295, 517, 416)]

UPSCALED = []   # 本輪被放大超過 1.5 倍的來源，main() 收尾時報出來


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


def _round_paste(img, src, box, radius, border=None, bw=6, focus=None):
    """把圖片以圓角貼上；border 有值就再描一圈。focus=(fx,fy) 取景位置（0..1），
    預設置中；語意與 fit_bg／CSS object-position 一致，操控室拖到哪就裁到哪。"""
    fx, fy = focus or (0.5, 0.5)
    bx0, by0, bx1, by1 = box
    tw, th = bx1 - bx0, by1 - by0
    im = src.convert("RGB")
    # 等比填滿後依 focus 裁切（不變形、不留邊）
    sc = max(tw / im.width, th / im.height)
    if sc > 1.5:
        # 靜默放大＝靜默糊掉。App 介面圖目前都是 375px 寬的 @1x 匯出，
        # 放進卡片要放大約 2 倍。銳化只能救一點，真正的解法是 Figma 重出 @3x。
        UPSCALED.append((getattr(src, "filename", "?"), round(sc, 2)))
    im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
    if sc > 1.2:
        im = im.filter(ImageFilter.UnsharpMask(radius=max(1, int(sc)), percent=95, threshold=3))
    _x = int((im.width - tw) * min(max(fx, 0), 1)); _y = int((im.height - th) * min(max(fy, 0), 1))
    im = im.crop((_x, _y, _x + tw, _y + th))
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
    """畫 logo 並回傳它的底緣 y——垂直節奏要從實際佔位接續，不能再猜一個分數值。"""
    lg = Image.open(E.LOGO if dark else E.LOGO.replace("white", "black")).convert("RGBA")
    w = int(W * 0.18); lg = lg.resize((w, int(lg.height * w / lg.width)))
    y = int(H * TOP_Y)
    img.paste(lg, (int(W * MX), y), lg)
    return y + lg.height


def draw_footer(d, dark):
    """深底原本直接呼叫引擎公版，但公版把邊界寫死 0.055。產品版型的 MX 改成 0.075 之後
    footer 會單獨留在舊位置、跟整頁差 0.02W（2026-08-23）。所以兩種底色都自己畫，
    邊界一律取本檔的 MX，這樣以後改 MX 不會再漏掉某個元件。"""
    col = WHITE if dark else INK
    fs = int(W * 0.022); f = ImageFont.truetype(E.F_REG, fs)
    y = H - int(H * 0.052) - fs
    d.text((int(W * MX), y), "@LAVA_DATING", font=f, fill=col)
    t1, t2 = "LAVA", "不聊天的交友軟體"
    w1 = d.textlength(t1, font=f); w2 = d.textlength(t2, font=f)
    dot_r = fs * 0.10; gap = fs * 0.38
    x = W - int(W * MX) - (w1 + gap*2 + w2)
    d.text((x, y), t1, font=f, fill=col)
    cy = y + fs * 0.58
    d.ellipse([x+w1+gap-dot_r, cy-dot_r, x+w1+gap+dot_r, cy+dot_r], fill=col)
    d.text((x + w1 + gap*2, y), t2, font=f, fill=col)


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


def draw_lead(d, text, dark, y, font_path=None):
    """上方導言：兩三行小字。行尾標點同 title_lines 的規則——
    作者手打的斷行保留，寬度造成的斷行才清。
    font_path 讓呼叫端降字重（尾板要用 Regular 才拉得開層級）。"""
    if not (text or "").strip():
        return y
    col = _lead_color(dark)
    fs = int(W * LEAD_FS); f = ImageFont.truetype(font_path or E.F_MED, fs)
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
def _focus(slide):
    cf = slide.get("crop_focus")
    if isinstance(cf, (list, tuple)) and len(cf) == 2:
        try:
            return (float(cf[0]), float(cf[1]))
        except (TypeError, ValueError):
            pass
    return None


def _star(d, cx, cy, r, fill=WHITE):
    import math
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.42
        a = math.radians(-90 + i * 36)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    d.polygon(pts, fill=fill)


def lay_hero(img, d, slide, shot, dark, band):
    """封面：中央截圖卡＋紅框光暈＋星標徽章，兩側襯卡。整組置中於內容帶。"""
    top, bot = band; bh = bot - top
    ch = int(min(H * HERO_H / 2, bh * BAND_FILL / 2))   # ch＝半高
    cw = int(ch * HERO_ASPECT)
    cx, cy = W // 2, (top + bot) // 2
    box = [cx - cw, cy - ch, cx + cw, cy + ch]
    r = int(W * CARD_R)
    sw = int(cw * 0.78)                            # 襯卡只從主卡後面露一角
    for sgn in (-1, 1):
        scx = cx + sgn * int(cw * 1.35)
        sb = [scx - sw, box[1] + int(ch*0.36), scx + sw, box[3] - int(ch*0.26)]
        d.rounded_rectangle(sb, radius=r, fill=DIM if dark else (240, 214, 150),
                            outline=(58, 62, 46) if dark else (232, 200, 132), width=4)
    img = _glow(img, box, r, RED, spread=0.035, alpha=120)
    d = ImageDraw.Draw(img)
    if shot:
        _round_paste(img, shot, box, r, border=RED, bw=int(W*0.005), focus=_focus(slide))
        d = ImageDraw.Draw(img)
    else:
        d.rounded_rectangle(box, radius=r, fill=DIM, outline=RED, width=int(W*0.005))
    br = int(W * 0.042)                            # 星標徽章壓在卡片下緣
    d.rounded_rectangle([cx - br, box[3] - br, cx + br, box[3] + br],
                        radius=int(br*0.32), fill=RED)
    _star(d, cx, box[3], int(br*0.52))
    return img, d


def lay_diagram(img, d, slide, shot, dark, band):
    """卡片堆疊圖解：兩張淡卡 →（箭頭）→ 紅色重點卡。"""
    top, bot = band
    cy = (top + bot) // 2
    # 0.155 是量出來的，不是調出來的：Jesse 原稿（1080×1350）紅卡佔 0.276W × 0.310H，
    # 半高即 0.155H，而 cw/ch 實測 0.712 與既有的 0.72 一致（2026-08-23）。
    ch = int(min(H * 0.155, (bot - top) * BAND_FILL / 2))
    cw = int(ch * 0.72); r = int(W * 0.028)
    lx = int(W * 0.30)
    for i in range(2):
        off = int(cw * 0.42 * i)
        sb = [lx - cw + off, cy - ch + int(ch*0.10*i), lx + cw + off, cy + ch]
        d.rounded_rectangle(sb, radius=r, fill=DIM if dark else (240, 214, 150),
                            outline=(58, 62, 46) if dark else (232, 200, 132), width=4)
    ax0, ax1 = int(W * 0.47), int(W * 0.585)
    d.line([(ax0, cy), (ax1, cy)], fill=_accent(dark), width=7)
    hw = int(W * 0.016)
    d.polygon([(ax1 + hw, cy), (ax1 - hw*0.3, cy - hw*0.75), (ax1 - hw*0.3, cy + hw*0.75)],
              fill=_accent(dark))
    rx = int(W * 0.755)
    rb = [rx - cw, cy - ch, rx + cw, cy + ch]
    img = _glow(img, rb, r, RED, spread=0.03, alpha=130); d = ImageDraw.Draw(img)
    d.rounded_rectangle(rb, radius=r, fill=RED)
    _star(d, rx, cy - int(ch*0.18), int(W*0.045))
    lbl = (slide.get("focus_label") or "你").strip()
    f = ImageFont.truetype(E.F_MED, int(W * 0.030))
    d.text((rx - d.textlength(lbl, font=f)/2, cy + int(ch*0.30)), lbl, font=f, fill=WHITE)
    return img, d


def lay_notify(img, d, slide, shot, dark, band):
    """模擬推播：媒體卡＋壓在其上的白色通知卡。

    版位依來源比例切換——橫幅生活照走寬卡（同 Jesse 參考稿），
    直式 App 截圖走置中手機卡（硬塞進寬卡會被放大 4 倍只剩兩行字，2026-08-17 實測）。
    """
    top, bot = band; bh = bot - top
    r = int(W * 0.022)
    nh = int(H * 0.088)                     # 通知卡高
    over = int(nh * 0.58)                   # 通知卡凸出媒體卡下緣的部分
    portrait = bool(shot) and (shot.height / max(1, shot.width)) > 1.2
    if portrait:
        ch = int(min(H * 0.225, (bh * BAND_FILL - over) / 2))
        cw = int(ch * 0.60)
        cx = W // 2; cy = top + (bh - over) // 2
        box = [cx - cw, cy - ch, cx + cw, cy + ch]
        _round_paste(img, shot, box, r, border=(58, 62, 46) if dark else (232, 200, 132), bw=4, focus=_focus(slide))
        d = ImageDraw.Draw(img)
        bx0, bx1, by1 = int(W * MX), W - int(W * MX), box[3] - int(ch * 0.30)
    else:
        bx0, bx1 = int(W * MX), W - int(W * MX)
        card_h = int(min(H * NOTIFY_H, bh * BAND_FILL - over))
        by0 = top + (bh - card_h - over) // 2
        by1 = by0 + card_h
        if shot:
            _round_paste(img, shot, [bx0, by0, bx1, by1], r, focus=_focus(slide))
        else:
            d.rounded_rectangle([bx0, by0, bx1, by1], radius=r, fill=DIM)
        d = ImageDraw.Draw(img)
    ny0 = by1 - int(nh * 0.42)
    _sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(_sh).rounded_rectangle(
        [bx0, ny0 + int(nh*0.10), bx1, ny0 + nh + int(nh*0.10)],
        radius=int(W*0.020), fill=(0, 0, 0, 90))
    img.paste(Image.alpha_composite(img.convert("RGBA"),
              _sh.filter(ImageFilter.GaussianBlur(int(W*0.010)))).convert("RGB"), (0, 0))
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


def lay_price(img, d, slide, shot, dark, band):
    """大字數字卡：紅底圓角，小標＋巨大數字；註腳在卡下方，整組置中。"""
    top, bot = band; bh = bot - top
    bx0, bx1 = int(W * MX), W - int(W * MX)
    note = (slide.get("price_note") or "").strip()
    # 註腳不佔內容帶：原稿裡它貼在版面底部（實測 0.862H，footer 之上），
    # 不是黏在紅卡下緣。掛在帶內會同時吃掉卡片高度、又讓卡片被推離視覺中心。
    fs_note = int(W * FS_PRICE_NOTE)
    f_note = ImageFont.truetype(E.F_REG, fs_note)
    card_h = int(min(H * 0.290, bh * BAND_FILL))    # 原稿實測 0.290H（舊值 0.20 偏小）
    by0 = top + (bh - card_h) // 2
    by1 = by0 + card_h
    r = int(W * 0.030)
    img = _glow(img, [bx0, by0, bx1, by1], r, RED, spread=0.022, alpha=70)   # 原稿暈光很收斂
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=r, fill=RED)
    # 卡內定位一律用「卡片自身的比例」＋墨水對齊，不用間距階梯往下堆。
    # 階梯是版面級的節奏，套進卡片內部就會和原稿對不上（Jesse 2026-08-23 兩次退件）：
    # 原稿的標籤墨頂在卡高 20.7%、數字墨頂在 40.1%、數字墨底距卡底 13.3%。
    # 另外 d.text 的 y 是 ascent 頂不是墨頂，直接餵座標必偏，所以先扣掉 getbbox 的位移。
    cw_, chh = bx1 - bx0, by1 - by0
    penx = bx0 + int(cw_ * PRICE_PAD_X)
    lab = (slide.get("price_label") or "").strip()
    amt = (slide.get("price_amount") or "").strip()

    def _ink_text(txt, f, ink_top):
        d.text((penx, ink_top - f.getbbox(txt)[1]), txt, font=f, fill=WHITE)

    if lab:
        _ink_text(lab, ImageFont.truetype(E.F_MED, int(W * FS_PRICE_LABEL)),
                  by0 + int(chh * PRICE_LABEL_TOP))
    if amt:
        fs = int(W * FS_PRICE_AMOUNT)
        ink_top = by0 + int(chh * PRICE_AMOUNT_TOP)
        while fs > int(W * 0.05):
            f = ImageFont.truetype(F_BLACK, fs)          # 原稿就是 Black
            bb = f.getbbox(amt)
            if (bb[2] - bb[0] <= cw_ - 2 * int(cw_ * PRICE_PAD_X)
                    and ink_top + (bb[3] - bb[1]) <= by1 - int(chh * 0.10)):
                break
            fs = int(fs * 0.93)
        _ink_text(amt, f, ink_top)
    if note:
        # 貼齊 footer 上方（原稿實測 0.862H），由下往上長，長句自動斷行
        lines = _recolor(E.wrap_semantic(note, _accent(dark), f_note, bx1 - bx0, d),
                         _accent(dark), _accent(dark))
        lh = int(fs_note * 1.4)
        E.draw_lines(d, lines, bx0, footer_top() - S_LG - len(lines) * lh, f_note, lh)
    return img, d


BADGE_BOTTOM = [0]


def lay_cta(img, d, slide, shot, dark, band=None):
    """尾板的商店徽章。徽章直接取自 CTA 公版的實測座標，不自行仿製
    （Apple／Google 的徽章有使用規範，畫一個像的等於仿冒）。"""
    src = Image.open(CTA_STOCK).convert("RGB")
    bw = int(W * 0.30)
    y = int(H * TOP_Y)
    for bx0, by0, bx1, by1 in BADGE_BOXES:
        bd = src.crop((bx0, by0, bx1, by1))
        bh = int(bd.height * bw / bd.width)
        img.paste(bd.resize((bw, bh), Image.LANCZOS), (int(W * MX), y))
        y += bh + S_XS
    BADGE_BOTTOM[0] = y - S_XS
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
    """尾板：徽章 → 字標 → 標語 → 紅線 → 導言 → 重點句 → 按鈕，全部走間距階梯。

    字重層級：品牌字型只有 Thin／Regular／Medium 三個字重，沒有 Bold。
    尾板原本整版都用 Medium，於是四段文字看起來一樣重，讀者不知道先看哪一句
    （Jesse 2026-08-23：字重沒有層級，看起來很吃力）。做法是兩端拉開——
    標語用 Medium＋描邊做假粗體，導言降到 Regular，中間留給 Medium。
    """
    img = _bg(dark); d = ImageDraw.Draw(img)
    img, d = lay_cta(img, d, slide, None, dark)
    y = BADGE_BOTTOM[0] + S_XL
    lg = Image.open(E.LOGO if dark else E.LOGO.replace("white", "black")).convert("RGBA")
    lw = int(W * 0.42); lg = lg.resize((lw, int(lg.height * lw / lg.width)))
    img.paste(lg, (int(W * MX), y), lg); d = ImageDraw.Draw(img)
    y += lg.height + S_LG                    # 標語再往下讓一階
    fs_tag = int(W * 0.074)                  # 0.062 → 0.074
    # 改用真的 Bold 字重，不再描邊。描邊在中文會吃掉「歸」「線」的內部空隙，
    # 放大後看起來就像選錯字型（Jesse 2026-08-23）。
    tag_col = OFFWHITE if dark else INK      # 純白在近黑底上過刺眼
    d.text((int(W * MX), y), (slide.get("tagline") or "讓社交回歸線下"),
           font=ImageFont.truetype(F_BOLD, fs_tag), fill=tag_col)
    y += int(fs_tag * 1.25) + S_LG
    d.line([(int(W*MX), y), (int(W*MX) + int(W*0.075), y)], fill=RED, width=int(H*0.004))
    y += S_LG
    y = draw_lead(d, slide.get("display_copy") or "", dark, y, font_path=E.F_REG) + S_LG
    hl = re.sub(r"[【】〖〗]", "", (slide.get("heading") or "").strip())
    if hl:
        fs_h = int(W * 0.052)
        d.text((int(W * MX), y), hl, font=ImageFont.truetype(E.F_MED, fs_h), fill=_accent(dark))
        y += int(fs_h * 1.25)
    ftop = footer_top()
    _pill(d, (slide.get("cta_button") or "打開 Lava"), int(W * MX),
          max(y + S_XL, ftop - S_LG - int(W * 0.036 + W*0.036*1.24)), dark)
    draw_footer(d, dark)
    img.save(out_path)
    return out_path


def render_slide(slide, shot_path, out_path, idx=None, total=None):
    """垂直節奏：logo → GAP_HEADER → 導言 → GAP_LEAD →〔內容帶〕→ GAP_STAGE → 大標 → GAP_TITLE → footer。
    視覺元件置中於內容帶，所以剩餘空白會平均分配，不會全部堆在下半部。"""
    layout = (slide.get("product_layout") or "diagram").strip()
    dark = (slide.get("bg") or "dark") != "cream"
    if layout == "cta":
        return _render_cta(slide, out_path, dark)

    img = _bg(dark); d = ImageDraw.Draw(img)
    logo_bottom = draw_logo(img, dark); d = ImageDraw.Draw(img)
    draw_pagination(d, idx, total, dark)

    shot = Image.open(shot_path) if (shot_path and os.path.exists(shot_path)) else None
    ftop = footer_top()

    # 封面沒有導言，改用下方的 eyebrow 標籤；其餘版型 display_copy 走導言
    eyebrow = (slide.get("eyebrow") or "").strip() if layout == "hero" else ""
    fs_eb = int(W * 0.028)
    eb_h = (int(fs_eb * 1.25) + S_LG) if eyebrow else 0

    lead_bottom = logo_bottom
    if layout != "hero":
        lead_bottom = draw_lead(d, slide.get("display_copy") or "", dark,
                                logo_bottom + GAP_HEADER)

    lines, f_t, fs_t = title_lines(slide.get("heading") or "", d, dark)
    lh = int(fs_t * 1.30)
    title_h = len(lines) * lh
    title_top = ftop - GAP_TITLE - eb_h - title_h

    band = (lead_bottom + GAP_LEAD, title_top - GAP_STAGE)
    img, d = LAYOUTS[layout](img, d, slide, shot, dark, band)

    if lines:
        E.draw_lines(d, lines, int(W * MX), title_top, f_t, lh)
    if eyebrow:
        d.text((int(W * MX), title_top + title_h + S_LG),
               "  ".join(eyebrow.upper()), font=ImageFont.truetype(E.F_MED, fs_eb), fill=RED)
    draw_footer(d, dark)
    img.save(out_path)
    return out_path


def infer_layout(slide, idx, total):
    """草稿沒寫 product_layout 時的推斷。WF01 目前還不會產這個欄位（n8n 斷線中），
    先讓引擎自己看得懂，之後 WF01 補上明確欄位就直接覆蓋這裡。"""
    lay = (slide.get("product_layout") or "").strip()
    if lay:
        return lay
    if "CTA" in str(slide.get("role", "")).upper() or idx == total:
        return "cta"
    if (slide.get("price_amount") or "").strip():
        return "price"
    if (slide.get("notify_text") or "").strip():
        return "notify"
    if idx == 1 or str(slide.get("role", "")) == "Hook":
        return "hero"
    return "diagram"


def main(json_path, bg_dir, out_dir):
    """與 render_post_v5.main 同簽章、同輸出命名，可直接替代。
    每張的圖沿用操控室選好的底圖（bg_dir/slide-N.*），不另外開一套素材路徑——
    Jesse 的選圖流程因此完全不用改。"""
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    slides = doc.get("slides", [])
    os.makedirs(out_dir, exist_ok=True)
    bgs = E.collect_bgs(bg_dir) if bg_dir and os.path.isdir(bg_dir) else {}
    total = len(slides)
    for i, s in enumerate(slides, 1):
        idx = int(s.get("index") or i)
        lay = infer_layout(s, idx, total)
        s = dict(s, product_layout=lay)
        shot = bgs.get(idx)
        if not shot and s.get("shot") and bg_dir:
            cand = os.path.join(bg_dir, s["shot"])
            shot = cand if os.path.exists(cand) else None
        out = os.path.join(out_dir, "final-%02d.png" % idx)
        render_slide(s, shot, out, idx=idx, total=total)
        print((idx, lay, os.path.basename(shot) if shot else "無圖", out))
    if UPSCALED:
        print("⚠ 來源解析度不足，被放大：")
        for fn, sc in UPSCALED:
            print("   %-46s ×%.2f" % (os.path.basename(str(fn))[:46], sc))
        print("   App 介面圖是 375px 寬的 @1x 匯出，需從 Figma 重出 @3x（1125px）才會真的銳利。")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("用法: python3 render_product.py <文案.json> <底圖資料夾> <輸出資料夾>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
