#!/usr/bin/env python3
# Lava IG 排版引擎 v5 — 依風格規格 v1.1（版型 v5）自 v3 修訂
# v5 變更：內文頁標題移至橘槓上方（黃、超寬自動縮字）；〖〗=Lava Orange 超級重點；
# 「資料來源：」行縮小兩級轉灰 #A5A7A2 置段末；遮罩最深 216/255；頂部 scrim；
# 橘槓 0.068W×(0.0035H+3px)；內文 Regular／標題 Medium；英文整字換行不腰斬；
# 同編號多檔 jpg/gif（劇照/迷因）優先於 png；slide 可設 crop:"top"（滿寬置頂＋黑底內文）
# 用法: python3 render_post_v5.py <文案.json> <底圖資料夾> <輸出資料夾>
import sys, json, os, re
from PIL import Image, ImageDraw, ImageFont

# 品牌資產（字型/logo）。優先用本機 my-site 鏡像；找不到再退回舊 session 路徑。
def _first_dir(cands):
    for c in cands:
        if os.path.isdir(c):
            return c
    return cands[0]
BRAND = _first_dir([
    "/Users/mimo/my-site/brand/Lava Design System",
    os.path.expanduser("~/Downloads/Lava Design System (1)"),
    "/sessions/admiring-charming-newton/mnt/brand/Lava Design System",
])
CTA_STOCK = next((p for p in [
    "/Users/mimo/my-site/brand/ig/20260705 AI 使人降智/最末圖公版.png",
    os.path.expanduser("~/Downloads/最末圖公版.png"),
] if os.path.exists(p)), "/Users/mimo/my-site/brand/ig/20260705 AI 使人降智/最末圖公版.png")
W, H = 1950, 2438   # 4:5（IG 動態滿版上限）；改自 3:4 的 1950×2600
YELLOW = (250, 210, 40)
ORANGE = (232, 66, 36)
ORANGE_DARK = (219, 53, 23)
GRAY_SRC = (165, 167, 162)   # neutral-400 #A5A7A2
WHITE = (255, 255, 255)
F_MED = BRAND + "/fonts/HarmonyOS_Sans_TC_Medium.ttf"
F_REG = BRAND + "/fonts/HarmonyOS_Sans_TC_Regular.ttf"
LOGO = BRAND + "/assets/logos/logo-white-horizontal.png"

# ── 缺字備援字型（2026-08-10）────────────────────────────────────────
# 品牌字型 HarmonyOS Sans TC 不含日文新字體漢字（塩顔坂学…），畫出來是空白。
# 川口春奈篇 slide3 因此整句核心詞消失（「塩顔」「坂口健太郎」「中学聖日記」）。
# 對策：偵測到主字型缺 glyph 才逐段改用備援字型繪製／量測，其餘走原生路徑不受影響。
F_FALLBACK = next((p for p in [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
] if os.path.exists(p)), None)
_FB_CACHE, _GLYPH_CACHE = {}, {}


def _has_glyph(font, ch):
    key = (getattr(font, "path", ""), ch)
    if key not in _GLYPH_CACHE:
        try:
            _GLYPH_CACHE[key] = font.getmask(ch).getbbox() is not None
        except Exception:
            _GLYPH_CACHE[key] = True
    return _GLYPH_CACHE[key]


def _fb_of(font):
    """取同尺寸的備援字型（快取）。"""
    if not F_FALLBACK:
        return None
    size = getattr(font, "size", 40)
    if size not in _FB_CACHE:
        try:
            _FB_CACHE[size] = ImageFont.truetype(F_FALLBACK, size)
        except Exception:
            _FB_CACHE[size] = None
    return _FB_CACHE[size]


def _segments(text, font):
    """[(片段, 字型)]；主字型畫得出來的連續字歸一段，缺字段落換備援字型。"""
    fb = _fb_of(font)
    out, buf, buf_fb = [], "", None
    for ch in text:
        use_fb = bool(fb) and ch.strip() and not _has_glyph(font, ch)
        if buf and use_fb != buf_fb:
            out.append((buf, fb if buf_fb else font)); buf = ""
        buf += ch; buf_fb = use_fb
    if buf:
        out.append((buf, fb if buf_fb else font))
    return out


def _needs_fb(text, font):
    return bool(F_FALLBACK) and any(c.strip() and not _has_glyph(font, c) for c in str(text))


_orig_text, _orig_len = ImageDraw.ImageDraw.text, ImageDraw.ImageDraw.textlength


def _text_fb(self, xy, text, *a, **kw):
    font = kw.get("font")
    if not font or not isinstance(text, str) or not _needs_fb(text, font):
        return _orig_text(self, xy, text, *a, **kw)
    x, y = xy
    for seg, f in _segments(text, font):
        kw2 = dict(kw); kw2["font"] = f
        _orig_text(self, (x, y), seg, *a, **kw2)
        x += _orig_len(self, seg, font=f)


def _len_fb(self, text, *a, **kw):
    font = kw.get("font")
    if not font or not isinstance(text, str) or not _needs_fb(text, font):
        return _orig_len(self, text, *a, **kw)
    return sum(_orig_len(self, seg, font=f) for seg, f in _segments(text, font))


ImageDraw.ImageDraw.text = _text_fb
ImageDraw.ImageDraw.textlength = _len_fb
NO_LEAD = set("。，、！？：；）」』…．,.!?;:%）")
MAX_ALPHA = 198   # v5.3：遮罩最深調降（原 216 把背景吃太黑），配合排版緊湊化讓底圖保持可辨識
# 版型 v5.2（07-15）：畫布改 4:5（1950×2438 = IG 動態上限 1080×1350 的 1.806× 超取樣）。
# 原 3:4（1950×2600）發到 IG 動態會被上下裁切約 6%，吃掉頂部 logo 與底部 footer；改 4:5 後滿版不裁。
# 所有座標皆為 W/H 比例，故只動這一行；內文為底部錨定，較矮畫布下文字自動上移。

def fit_bg(path, focus=None):
    """等比放大到蓋滿 4:5 版面後裁切。focus=(fx, fy) 是裁切窗位置（0..1），
    預設置中。語意與 CSS object-position 一致——操控室的裁切預覽用同一套數學，
    所以「拖到哪就裁到哪」，預覽即成品（Jesse 2026-08-20 要求可直接裁切）。"""
    fx, fy = focus or (0.5, 0.5)
    im = Image.open(path).convert("RGB")
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1))
    x = int((im.width - W) * min(max(fx, 0), 1)); y = int((im.height - H) * min(max(fy, 0), 1))
    return im.crop((x, y, x + W, y + H))


def _slide_focus(slide, crop=None):
    """slide.crop_focus（操控室手動裁切）優先；沒有時 crop:'top' 對映 (0.5, 0)。"""
    cf = slide.get("crop_focus") if isinstance(slide, dict) else None
    if isinstance(cf, (list, tuple)) and len(cf) == 2:
        try:
            return (float(cf[0]), float(cf[1]))
        except (TypeError, ValueError):
            pass
    return (0.5, 0.0) if crop == "top" else None

def fit_bg_top(path):
    """crop:top — 滿寬置頂，下方黑底"""
    im = Image.open(path).convert("RGB")
    r = W / im.width
    im = im.resize((W, int(im.height * r)))
    canvas = Image.new("RGB", (W, H), (5, 5, 5))
    canvas.paste(im, (0, 0))
    return canvas

def dyn_overlay(base, content_y, max_alpha=MAX_ALPHA, ambient=55, fade_span=0.30):
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

def top_scrim(base, depth=0.14, alpha=95):
    """v5 頂部漸層 scrim 保護 logo／標題可讀性"""
    d = int(H * depth)
    g = Image.new("L", (1, H), 0)
    for y in range(d):
        g.putpixel((0, y), int(alpha * (1 - y / d)))
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
    y = H - int(H * 0.052) - fs   # footer 底部留白（舒適）
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
    """【】=重點黃、〖〗=超級重點 Lava Orange → (segment, color) 列表；\n 保留。"""
    segs = []
    for part in re.split(r"(【[^】]*】|〖[^〗]*〗)", text):
        if not part: continue
        if part.startswith("【") and part.endswith("】"):
            segs.append((part[1:-1], YELLOW))
        elif part.startswith("〖") and part.endswith("〗"):
            segs.append((part[1:-1], ORANGE))
        else:
            segs.append((part, WHITE))
    return segs

def _tokenize(text):
    """英文單字/數字整字為一 token，不腰斬；其餘逐字。"""
    return re.findall(r"[A-Za-z0-9'’\-]+|\s|.", text)

def wrap_segments(segments, font, max_w, d):
    lines, cur, cur_w = [], [], 0.0
    for text, color in segments:
        for tok in _tokenize(text):
            if tok == "\n":
                lines.append(cur); cur, cur_w = [], 0.0; continue
            w = d.textlength(tok, font=font)
            if cur_w + w > max_w and cur and tok not in NO_LEAD and not tok.isspace():
                # 行尾不得停在修飾詞（2026-08-11：主標「…都變／最近讓人…」把「最近」拆兩行）
                back = []
                while len(cur) > 1 and cur[-1][0] in NO_TRAIL:
                    back.insert(0, cur.pop())
                lines.append(cur)
                cur = back
                cur_w = sum(d.textlength(t, font=font) for t, _ in back)
                if tok.isspace():  # 行首不留空白
                    continue
            cur.append((tok, color)); cur_w += w
    if cur: lines.append(cur)
    return lines

                                 # 行尾不可留的修飾詞／連接詞：後面必須接內容，斷在這裡等於把詞拆兩半
NO_TRAIL = set("最不很更也都又再還就才將被把讓使令對於和與及跟並而但因所如若則每同各此該其之的地得"
               "太些挺蠻頗極超越沒有在是會能可要想常總正剛快先後從往向給替為由當")


def wrap_semantic(text, color, font, max_w, d):
    """語意優先斷行：先按標點切句，貪婪組行；單句超寬才退回寬度斷，並避免行尾停在修飾詞。
    2026-08-10 Jesse 驗收：封面副標「最近讓台灣人最／心動的臉，都不太／需要你喜歡她」——
    純寬度斷行把「最心動」「不太需要」拆兩行，讀起來像壞掉的字幕。"""
    units, buf = [], ""
    for ch in text:
        buf += ch
        if ch in "，。、；：！？!?…":
            units.append(buf); buf = ""
    if buf:
        units.append(buf)
    lines, cur = [], ""
    for u in units:
        cand = cur + u
        if cur and d.textlength(cand, font=font) > max_w:
            lines.append(cur); cur = u
        else:
            cur = cand
        while d.textlength(cur, font=font) > max_w:   # 單一語意單元仍超寬 → 寬度斷，但不停在修飾詞
            cut = len(cur)
            while cut > 1 and d.textlength(cur[:cut], font=font) > max_w:
                cut -= 1
            while cut > 1 and cur[cut - 1] in NO_TRAIL:
                cut -= 1
            lines.append(cur[:cut]); cur = cur[cut:]
    if cur:
        lines.append(cur)
    return [[(l, color)] for l in lines if l]


                                  # 行尾懸空的分隔標點一律刪（Jesse 早期規則）。
                                  # 保留 」』）〗】＝成對閉合符號，刪了會破壞引號；？！為語氣不刪。
LINE_END_STRIP = set("，、；：。．,;:·…⋯—－-")


def strip_line_ends(lines):
    """對「排版後實際斷出來的每一行」清掉行尾標點。
    strip_trailing_punct 只看文案原本的換行，斷行是排版當下才決定的——
    所以逗號會掛在行尾（Aziz 篇「…威奇托等地，」）。此函式補上這一段。"""
    out = []
    for line in lines:
        line = list(line)
        while line:
            tok, color = line[-1]
            t = tok.rstrip()
            while t and t[-1] in LINE_END_STRIP:
                t = t[:-1].rstrip()
            if t == tok:
                break
            if t:
                line[-1] = (t, color)
                break
            line.pop()
        out.append(line)
    return out


                          # 版面常數：檢查工具必須用這些，不可自行猜字級（2026-08-13 事故）
COVER_TITLE_FS = 0.075    # 封面主標起跳字級（比例於 W），逐級 ×0.92 縮到下限
COVER_TITLE_MIN = 0.05
COVER_SUB_FS = 0.032      # 封面副標
BODY_FS = 0.036           # 內文頁內文
BODY_TITLE_FS = 0.043     # 內文頁標題
MARGIN_X = 0.055          # 左右邊距，可用寬 = W - 2*MARGIN_X*W


def content_width():
    return W - 2 * int(W * MARGIN_X)


def cover_title_lines(heading, d):
    """封面主標的實際斷行結果，含動態縮字。回傳 (lines, font, fs)。

    抽成公用函式的原因（2026-08-13）：check_typography.py 原本自己寫死 W*0.043 與 W*0.86
    去重算斷行，但引擎實際是 W*0.075 起跳、逐級縮到 W*0.05、寬度 W*0.89。
    字級差 57%、寬度不同，算出來的斷點跟印出來的完全是兩回事，
    所以「9 篇全過」是假的。渲染與檢查必須共用同一段邏輯，這是單一真理來源。
    """
    segs = parse_highlight(strip_trailing_punct(heading))
    max_w = content_width()
    fs = int(W * COVER_TITLE_FS)
    while True:
        f = ImageFont.truetype(F_MED, fs)
        lines = strip_line_ends(wrap_segments(segs, f, max_w, d))
        if len(lines) <= 3 or fs <= int(W * COVER_TITLE_MIN):
            return lines, f, fs
        fs = int(fs * 0.92)


def draw_lines(d, lines, x, y, font, lh):
    for line in lines:
        cx = x
        for tok, color in line:
            d.text((cx, y), tok, font=font, fill=color)
            cx += d.textlength(tok, font=font)
        y += lh if line else int(lh * 0.55)   # 空行=段落間距，收窄避免文字塊過高（遮罩跟著變大）
    return y


def lines_height(lines, lh):
    """與 draw_lines 相同的段落間距規則計算總高。"""
    return sum(lh if line else int(lh * 0.55) for line in lines)


def draw_credit(d, text, footer_top):
    """圖片來源標示（小字灰，貼在 footer 上方）——人物照/書封/劇照的授權標註。回傳其高度。"""
    if not text:
        return 0
    fs = int(W * 0.017)
    f = ImageFont.truetype(F_REG, fs)
    d.text((int(W * 0.055), footer_top - int(fs * 1.5)), text, font=f, fill=GRAY_SRC)
    return int(fs * 1.9)

def split_sources(text):
    """把「資料來源：」開頭行抽出（v5 置段末縮小灰色）。"""
    body_lines, src_lines = [], []
    for ln in text.split("\n"):
        (src_lines if ln.strip().startswith("資料來源") else body_lines).append(ln)
    return "\n".join(body_lines).strip("\n"), src_lines

_TRAIL_PUNCT = set("。，、！？；：…‥．·.,!?;:～〜~—―─–ｰ－-")

def strip_trailing_punct(text):
    """句尾標點（含破折號 ──、--）一律省略；逐行處理，容許緊貼的 〗】 收尾標記。"""
    out = []
    for ln in text.split("\n"):
        s = ln.rstrip()
        changed = True
        while changed and s:
            changed = False
            if s[-1] in _TRAIL_PUNCT:
                s = s[:-1].rstrip(); changed = True
            elif s[-1] in "〗】" and len(s) >= 2 and s[-2] in _TRAIL_PUNCT:
                s = s[:-2].rstrip() + s[-1]; changed = True
        out.append(s)
    return "\n".join(out)


def draw_eyebrow(d, text, y):
    fs = int(W * 0.024); f = ImageFont.truetype(F_MED, fs)
    text = text.upper(); gap = fs * 0.30
    total = sum(d.textlength(c, font=f) + gap for c in text) - gap
    while total > W * 0.88 and fs > int(W * 0.014):   # 過長 eyebrow 縮字防爆框
        fs -= 2; f = ImageFont.truetype(F_MED, fs); gap = fs * 0.30
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

def render_cover(slide, bg_path, out_path, eyebrow="LAVA DATING", crop=None):
    _cf = _slide_focus(slide, crop)
    img = fit_bg(bg_path, _cf) if _cf else (fit_bg_top(bg_path) if crop == "top" else fit_bg(bg_path))
    img.paste(Image.new("RGB", (W,H), (5,5,5)), (0,0), Image.new("L", (W,H), 88))   # 全域壓暗回調（原 120 太黑）
    img = dyn_overlay(img, int(H*0.42), max_alpha=190, ambient=60, fade_span=0.25)
    img = top_scrim(img)
    d = ImageDraw.Draw(img)
    lg = logo_img(); mx = int(W*0.055)
    img.paste(lg, (mx, int(H*0.052)), lg)   # logo 頂部留白（舒適）
    y = draw_eyebrow(d, eyebrow, int(H*0.245)) + int(H*0.028)
    max_w = W - 2*mx
    footer_top = H - int(H*0.052) - int(W*0.022)   # cover 安全區下界（footer 上緣）
    # 主標：換行＋超過 3 行自動縮字（防長標題爆框/壓副標）
    lines, f_main, fs_m = cover_title_lines(slide.get("heading", ""), d)
    sw = max(1, int(fs_m*0.018))
    for line in lines:
        total = sum(d.textlength(tok, font=f_main) for tok, _ in line)
        cx = (W - total) / 2
        for tok, color in line:
            d.text((cx, y), tok, font=f_main, fill=color, stroke_width=sw, stroke_fill=color)
            cx += d.textlength(tok, font=f_main)
        y += int(fs_m * 1.38)
    y += int(H*0.035)
    y = draw_pill_arrow(d, y) + int(H*0.030)
    # 副標：逐行換行（原本沒換行會左右爆框）＋整塊塞不進 footer 安全區就逐級縮字
    _dc = strip_trailing_punct(slide.get("display_copy", "")); _hd = slide.get("heading", "")
    # 副標不得句中截斷（2026-08-03 Jesse 驗收）：全收→縮字去 fit；仍放不下才「整句」丟尾行
    sub_lines = [re.sub(r"[【】〖〗]", "", l.strip()) for l in _dc.split("\n") if l.strip() and l.strip() not in _hd][:6]
    # 文案自帶的爛換行要修掉（2026-08-11）：WF01 產出的 display_copy 常在詞中間硬斷
    # （「最近讓台灣人最／心動的臉，都不太／需要你喜歡她」），引擎若照單全收就原樣印出。
    # 行尾停在修飾詞＝斷點不合法 → 與下一行合併，交還給 wrap_semantic 依標點重斷。
    _merged = []
    for _ln in sub_lines:
        if _merged and _merged[-1] and _merged[-1][-1] in NO_TRAIL:
            _merged[-1] += _ln
        else:
            _merged.append(_ln)
    sub_lines = _merged
    if len(sub_lines) > 4:
        while len(sub_lines) > 4 and not re.search(r"[。！？!?…」』]$", sub_lines[-1]):
            sub_lines.pop()   # 尾行若句子未完，往前退到完整句收尾
    wrapped, f_sub, lh_s = [], None, 0
    for scale in (1.0, 0.92, 0.84, 0.76, 0.68):
        fs_s = int(W*0.032*scale)
        f_sub = ImageFont.truetype(F_MED, fs_s)
        lh_s = int(fs_s * 1.7)
        wrapped = []
        for t in sub_lines:
            wrapped += strip_line_ends(wrap_semantic(t, YELLOW, f_sub, max_w, d))
        if y + len(wrapped) * lh_s <= footer_top - int(H*0.02):
            break
    for line in wrapped:
        total = sum(d.textlength(tok, font=f_sub) for tok, _ in line)
        cx = (W - total) / 2
        for tok, _ in line:
            d.text((cx, y), tok, font=f_sub, fill=YELLOW)
            cx += d.textlength(tok, font=f_sub)
        y += lh_s
    draw_credit(d, slide.get("render_credit") or "", footer_top)
    draw_footer(d)
    img.save(out_path)

def render_content(slide, bg_path, out_path, crop=None):
    mx = int(W*0.055)
    body_text, src_lines = split_sources(slide.get("display_copy", ""))
    body_text = strip_trailing_punct(body_text)                 # #2 句尾標點省略
    body_segs = parse_highlight(body_text)
    title = strip_trailing_punct(re.sub(r"[【】〖〗]", "", slide.get("heading", "")))
    tmp = Image.new("RGB", (1,1)); dt = ImageDraw.Draw(tmp)
    max_w = W - 2*mx
    gap_tb = int(H*0.016)          # 標題與橘槓間距
    bar_h = int(H*0.0035) + 3      # v5 橘槓高
    body_gap = int(H*0.016)        # 橘槓與內文間距

    # 安全版面界線：標題不越過 logo 下緣、內文底不壓到 footer（#1 統一防呆）
    logo_bottom = int(H*0.052) + logo_img().height
    top_limit = logo_bottom + int(H*0.030)
    footer_top = H - int(H*0.052) - int(W*0.022)
    credit = slide.get("render_credit") or ""
    body_bottom_limit = footer_top - int(H*0.045) - (int(W*0.017*1.9) if credit else 0)

    # 自適應縮字：由基準級距往下試，直到（標題＋槓＋內文＋來源）整塊落在安全區內
    fit = None
    for scale in (1.0, 0.95, 0.90, 0.85, 0.80, 0.75):   # 0.70 級距移除：字太小不可讀（2026-08-03）；過長靠 WF01 字數上限管
        fs_b = max(12, int(W*0.036*scale)); f_body = ImageFont.truetype(F_REG, fs_b)
        fs_src = max(10, int(W*0.027*scale)); f_src = ImageFont.truetype(F_REG, fs_src)
        fs_t = int(W*0.043*scale); f_title = ImageFont.truetype(F_MED, fs_t)
        while dt.textlength(title, font=f_title) > max_w and fs_t > int(W*0.024):
            fs_t -= 2; f_title = ImageFont.truetype(F_MED, fs_t)
        lh = int(fs_b*1.60); lh_src = int(fs_src*1.55); title_h = int(fs_t*1.25)
        body_lines = strip_line_ends(wrap_segments(body_segs, f_body, max_w, dt))
        src_wrapped = []
        for s in src_lines:
            src_wrapped += strip_line_ends(wrap_segments([(strip_trailing_punct(re.sub(r"[【】〖〗]", "", s)), GRAY_SRC)], f_src, max_w, dt))
        body_h = lines_height(body_lines, lh) + (int(H*0.012) + lines_height(src_wrapped, lh_src) if src_wrapped else 0)
        block_h = title_h + gap_tb + bar_h + body_gap + body_h
        fit = (fs_t, f_title, title_h, f_body, lh, body_lines, f_src, lh_src, src_wrapped, body_h)
        if top_limit + block_h <= body_bottom_limit:
            break
    fs_t, f_title, title_h, f_body, lh, body_lines, f_src, lh_src, src_wrapped, body_h = fit

    # 底部錨定：內文塊底貼齊 body_bottom_limit；極端過高才夾在 top_limit
    body_top = body_bottom_limit - body_h
    bar_y = body_top - body_gap - bar_h
    title_y = bar_y - gap_tb - title_h
    if title_y < top_limit:
        title_y = top_limit
        bar_y = title_y + title_h + gap_tb
        body_top = bar_y + bar_h + body_gap

    _cf = _slide_focus(slide, crop)
    img = fit_bg(bg_path, _cf) if _cf else (fit_bg_top(bg_path) if crop == "top" else fit_bg(bg_path))
    img = dyn_overlay(img, title_y)                    # 遮罩錨定標題起點，標題落在暗區
    img = top_scrim(img)
    d = ImageDraw.Draw(img)
    img.paste(logo_img(), (mx, int(H*0.052)), logo_img())   # logo 頂部留白（舒適）
    d.text((mx, title_y), title, font=f_title,
           fill=YELLOW, stroke_width=max(1, int(fs_t*0.02)), stroke_fill=YELLOW)
    d.rectangle([mx, bar_y, mx+int(W*0.068), bar_y+bar_h], fill=ORANGE)
    y = draw_lines(d, body_lines, mx, body_top, f_body, lh)
    if src_wrapped:
        y += int(H*0.012)
        draw_lines(d, src_wrapped, mx, y, f_src, lh_src)
    draw_credit(d, credit, footer_top)
    draw_footer(d)
    img.save(out_path)

EXT_PRIORITY = {"jpg": 0, "jpeg": 0, "gif": 0, "png": 1}   # v5：劇照/迷因（jpg/gif）優先於生成圖（png）

def collect_bgs(bg_dir):
    """遞迴收集 slide 底圖；寬鬆匹配 slide-N / slideN 前綴；jpg/gif 優先於 png；同級取 exact 名優先。"""
    cands = {}
    for root, _, files in os.walk(bg_dir):
        for fn in files:
            m = re.match(r"slide-?(\d+)", fn, re.I)
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
            if not m or ext not in EXT_PRIORITY: continue
            idx = int(m.group(1))
            exact = 0 if re.fullmatch(r"slide-%d\.%s" % (idx, ext), fn, re.I) else 1
            key = (EXT_PRIORITY[ext], exact, fn)
            cands.setdefault(idx, []).append((key, os.path.join(root, fn)))
    return {i: sorted(v)[0][1] for i, v in cands.items()}

def main(json_path, bg_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    data = json.load(open(json_path))
    bgs = collect_bgs(bg_dir)
    eyebrow = data.get("eyebrow_en") or "LAVA DATING"
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
        crop = s.get("crop")
        if i == 1 or role == "Hook":
            render_cover(s, bg, out, eyebrow=eyebrow, crop=crop)
            results.append((i, "封面" + ("(crop:top)" if crop == "top" else ""), out))
        else:
            render_content(s, bg, out, crop=crop)
            results.append((i, "內文" + ("(crop:top)" if crop == "top" else ""), out))
    for r in results: print(r)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
