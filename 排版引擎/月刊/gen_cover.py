#!/usr/bin/env python3
"""共用封面：照八月號（七夕月）的圖層與版式，只換內容。

〔2026-09-16 Jesse〕「中秋月的封面應該要完全參照上個月份封面的排版方式，
不要再重新設計。」

〔第三輪 Jesse 回饋〕
  (a) 七夕月的標題「壓在圖上面」是圖層做出來的（去背人物疊在刊名之上），
      不是單純用漸層把底圖推開。要更雜誌。
  (b) Logo 跟「中秋月」靠太近，七夕月時就調過。

所以這一版照八月配方（brain/products/lava/ig/campaign-recipes.md）的圖層順序：
  底圖 → 上/下 scrim → masthead → wordmark＋刊名 → **去背人物層** → 底部資訊
底圖 素材/cover_v3_9.png（nano_banana_pro，深炭灰棚、硬光），去背層 cover_v3_cutout.png。
兩張比例都是 4:5，都用 object-fit:cover 疊，誤差 <1px（cutout 被 Higgsfield 縮成
1649×2048，比例差 0.0004）。

八月封面量測值（從 v6_貼文_s1_cover_1080x1350.png 偵測奶油字列）：
  細字列    y=70–89   左起 x=66、右止 x=1009
  字標      y=113–146 寬 126、置中
  刊名      y=169–345 三字寬 552、置中；男方髮際遮掉「十」下緣約 55px（≈30%）
  副標      y=1066–1093 置中，項目間用「 · 」
  橘圓      圓心 (540,1192) 直徑 93
  往右滑    y=1261–1281 置中
八月封面 masthead 底下**有**一條很淡的細線（量：y=105–106、x=64–1015、奶油色 alpha≈.27），
**沒有**底部細線、**沒有**底部資訊列。前兩輪的 docstring 寫「沒有細線」是量錯了（線太淡，
亮度只有 71/255）；這一版照量到的值加回 masthead 線，底部仍然不加。同區只有這一條線。

這一版的數值怎麼來的（都是出圖後用 PIL 量，不是 CSS 值猜的）：
  * wordmark 底緣 → 刊名墨頂緣 ≥ 40px。「中」「秋」頂端有墨（「七夕」沒有），
    所以刊名 top 要比八月低；用 TITLE_TOP 調，量出來的值寫在 measure() 的輸出。
  * 男方頭頂（alpha≥128）在 y=267，刊名帶內只有他進入（x≤359）；
    女方頭頂 y=395 在刊名之下。目標：頭遮住「中」下緣 1/4–1/3，三字都認得出來。
  * 去背層邊緣：alpha 先做 1px 收邊（MinFilter 3）再輕柔化，避免髮絲外圈一圈
    半透明的背景色帶（實測 fringe 亮度 33 vs 棚背 38，本來就沒白邊，收邊是保險）。
  * 質感：底部 scrim 只壓底部 1/3（y≥900），上方 scrim 很輕只保 masthead；
    目錄行左段「25,000 人」壓在橘 polo 與手臂上；用「隱藏目錄行再出一張」量墨底下的
    背景亮度，奶油字對背景對比：整行平均 9.9:1、最差 4.7:1（25,000 人段最差 5.0）。
  * 本版量到（2026-09-16）：wordmark 底 147、刊名墨 191–347（高 157）、間距 43px；
    男方頭遮「中」自 y=303 起、45px、28.7%；三字皆完整可辨（Read 逐字看過）。
    整張蓋一層 paper_dark 顆粒 overlay opacity .18。沒有框、沒有色塊。
"""
import os, json, html
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
COPY = json.load(open(os.path.join(HERE, "spec", "copy.json"), encoding="utf-8"))
CREAM = "#F5E6C8"          # 從八月封面取樣的字色，比品牌 soft-yellow 略淡
ORANGE = "#E84224"
LOGO = "file://" + os.path.join(HERE, "素材", "logo-yellow-horizontal.png")
GRAIN = "file://" + os.path.join(HERE, "素材", "textures", "paper_dark.png")
PHOTO = os.path.join(HERE, "素材", "cover_v3_9.png")
CUTOUT_RAW = os.path.join(HERE, "素材", "cover_v3_cutout.png")
CUTOUT = os.path.join(HERE, "素材", "cover_v3_cutout_clean.png")   # 由本檔生成

# 版面數值（1080×1350）
TITLE_SIZE = 198      # 反算：八月刊名三字墨寬 552，本版 172px 只有 479（小 13%），
                      # 刊名就浮在畫面上而不是壓進去。552/479×172 = 198。
TITLE_TOP = 190       # h1 的 top；墨頂緣會比它低一點，見 measure()
LOGO_TOP = 112        # 八月配方：刊名區距頂 112
LOGO_H = 36
ZOOM = 1.05           # 底圖＋去背層一起以「頂邊」為錨放大：把男方頭頂往下推，
                      # 讓刊名不用往上擠（往上擠就撞 wordmark 的 40px 間距）。
                      # 第一版 ZOOM=1、176px、top 196：墨 197–356，頭遮「中」48%，太多。
IMG_W, IMG_H = round(1080 * ZOOM), round(1350 * ZOOM)
IMG_LEFT = -(IMG_W - 1080) // 2


def esc(s):
    return html.escape(str(s or ""))


def clean_cutout():
    """去背層收邊：alpha 收 1px，再 0.6px 高斯柔邊。RGB 不動。"""
    im = Image.open(CUTOUT_RAW)
    if im.mode != "RGBA":
        raise SystemExit("去背層不是 RGBA：%s" % im.mode)
    a = im.getchannel("A").filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    im.putalpha(a)
    im.save(CUTOUT)


def cover_html():
    return """<!doctype html><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600&display=swap" rel="stylesheet">
<style>
html,body{margin:0}*{box-sizing:border-box}
.c{width:1080px;height:1350px;position:relative;overflow:hidden;background:#0C0E08;
   font-family:"HarmonyOS Sans TC",-apple-system,sans-serif;-webkit-font-smoothing:antialiased}
.ph,.cut{position:absolute;left:%(img_left)dpx;top:0;width:%(img_w)dpx;height:%(img_h)dpx;object-fit:cover;object-position:50%% 50%%}
/* 上方 scrim 很輕：棚背本來就是深炭灰，只是保 masthead 在任何底圖上都讀得到 */
.scrim-t{position:absolute;left:0;top:0;width:1080px;height:260px;
   background:linear-gradient(180deg,rgba(12,14,8,.55) 0%%,rgba(12,14,8,0) 100%%)}
/* 下方 scrim 只壓底部 1/3：人物衣服（橘 polo、酒紅緞面）在這裡被壓暗，目錄行才讀得到 */
.scrim-b{position:absolute;left:0;top:900px;width:1080px;height:450px;
   background:linear-gradient(0deg,rgba(12,14,8,.94) 0%%,rgba(12,14,8,.88) 40%%,rgba(12,14,8,.62) 72%%,rgba(12,14,8,0) 100%%)}
.grain{position:absolute;inset:0;width:1080px;height:1350px;object-fit:cover;
   mix-blend-mode:overlay;opacity:.18;pointer-events:none}
.rail{position:absolute;left:66px;right:71px;top:66px;display:flex;justify-content:space-between;
   font-family:Inter,sans-serif;font-weight:600;font-size:22px;letter-spacing:.22em;
   text-transform:uppercase;color:%(cream)s;font-variant-numeric:tabular-nums;line-height:28px}
.hair{position:absolute;left:64px;top:105px;width:952px;height:2px;background:rgba(245,230,200,.27)}
.logo{position:absolute;left:50%%;top:%(logo_top)dpx;transform:translateX(-50%%);height:%(logo_h)dpx}
.title{position:absolute;left:0;width:1080px;top:%(title_top)dpx;margin:0;text-align:center;
   font-size:%(title_size)dpx;line-height:1;font-weight:500;letter-spacing:.04em;color:%(cream)s;
   text-indent:-.045em;padding-left:.04em}
.kick{position:absolute;left:0;width:1080px;top:1058px;text-align:center;font-size:32px;
   font-weight:500;letter-spacing:.02em;color:%(cream)s;line-height:44px}
.kick i{font-style:normal;margin:0 22px;opacity:.85}
.cta{position:absolute;left:493px;top:1145px;width:94px;height:94px;border-radius:50%%;
   background:%(orange)s;display:flex;align-items:center;justify-content:center}
.cta svg{width:44px;height:44px}
.swipe{position:absolute;left:0;width:1080px;top:1254px;text-align:center;font-size:24px;
   font-weight:500;letter-spacing:.04em;color:%(cream)s;line-height:32px}
</style>
<div class="c">
  <img class="ph" src="%(photo)s">
  <div class="scrim-t"></div>
  <div class="rail"><span>%(en)s</span><span>2026.09</span></div>
  <div class="hair"></div>
  <img class="logo" src="%(logo)s">
  <h1 class="title">%(title)s</h1>
  <img class="cut" src="%(cutout)s">
  <div class="scrim-b"></div>
  <img class="grain" src="%(grain)s">
  <div class="kick">%(kick)s</div>
  <div class="cta"><svg viewBox="0 0 24 24" fill="none" stroke="%(cream)s" stroke-width="2.6"
     stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h15M13 6l6 6-6 6"/></svg></div>
  <div class="swipe">往右滑</div>
</div>""" % {
        "cream": CREAM, "orange": ORANGE, "logo": LOGO, "grain": GRAIN,
        "photo": "file://" + PHOTO, "cutout": "file://" + CUTOUT,
        "logo_top": LOGO_TOP, "logo_h": LOGO_H,
        "img_left": IMG_LEFT, "img_w": IMG_W, "img_h": IMG_H,
        "title_top": TITLE_TOP, "title_size": TITLE_SIZE,
        "en": esc(COPY["issue_title_en"]),
        "title": esc(COPY["issue_title"]),
        "kick": "<i>·</i>".join(esc(x.strip()) for x in COPY["cover_kicker"].split("·")),
    }


def write(version_dir):
    out = os.path.join(HERE, "html", version_dir)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "01_cover.html"), "w", encoding="utf-8") as f:
        f.write(cover_html())


def measure(png_path):
    """從出圖量：wordmark 底緣、刊名墨頂/底緣、頭頂遮住刊名多少。
    奶油字偵測：接近 #F5E6C8 (245,230,200)：R>225、R-G<25、G-B 在 15–50。
    第一版用「R>200 且 R-B>25」會把男方臉上的反光（R-G≥30）也算進去，墨底緣量到 445。"""
    im = Image.open(png_path).convert("RGB")
    px = im.load()

    def is_cream(p):
        r, g, b = p
        return r > 225 and r - g < 25 and 15 <= g - b <= 50

    def cream_rows(y0, y1, x0, x1):
        rows = []
        for y in range(y0, y1):
            n = 0
            for x in range(x0, x1):
                if is_cream(px[x, y]):
                    n += 1
            rows.append((y, n))
        return rows

    # wordmark：soft-yellow logo（實測 (253,232,170)），R>200、G>150、B<190、R-B>60
    logo_bottom = None
    for y in range(LOGO_TOP - 4, LOGO_TOP + LOGO_H + 12):
        if any(px[x, y][0] > 200 and px[x, y][1] > 150 and px[x, y][2] < 190 and px[x, y][0] - px[x, y][2] > 60
               for x in range(440, 640)):
            logo_bottom = y
    title_rows = [(y, n) for y, n in cream_rows(LOGO_TOP + LOGO_H, TITLE_TOP + TITLE_SIZE + 10, 250, 830) if n >= 6]
    ink_top, ink_bottom = title_rows[0][0], title_rows[-1][0]
    # 刊名墨的 x 範圍
    xs = [x for x in range(200, 880) if any(is_cream(px[x, y]) for y in range(ink_top, ink_bottom, 3))]
    # 去背層在版面座標的 alpha（照 CSS 的 cover＋ZOOM 放置）
    ap = cutout_alpha_in_frame().load()
    # 遮蔽：只看第一個字「中」的 x 帶（男方只會碰到它），頭要遮到 ≥12px 寬才算「進入」；
    # 髮尖一兩個像素碰到不算，否則量出來的比例會虛高。
    zhong_x0, zhong_x1 = xs[0], xs[0] + int(TITLE_SIZE * 0.9)
    head_top_in_title = None
    for y in range(ink_top, ink_bottom + 1):
        if sum(1 for x in range(zhong_x0, zhong_x1) if ap[x, y] >= 128) >= 12:
            head_top_in_title = y
            break
    ink_h = ink_bottom - ink_top + 1
    covered = (ink_bottom - head_top_in_title + 1) if head_top_in_title else 0
    return {
        "logo_bottom": logo_bottom, "ink_top": ink_top, "ink_bottom": ink_bottom, "ink_h": ink_h,
        "logo_gap": ink_top - logo_bottom - 1,
        "title_x": (xs[0], xs[-1]), "head_top_in_zhong": head_top_in_title,
        "covered_px": covered, "covered_ratio": round(covered / ink_h, 3),
    }


def cutout_alpha_in_frame():
    """把 clean cutout 的 alpha 照 CSS（object-fit:cover、ZOOM、頂邊錨）放進 1080×1350。"""
    cut = Image.open(CUTOUT)
    s = max(IMG_W / cut.width, IMG_H / cut.height)
    cw, ch = round(cut.width * s), round(cut.height * s)
    a = cut.getchannel("A").resize((cw, ch), Image.LANCZOS)
    a = a.crop(((cw - IMG_W) // 2, (ch - IMG_H) // 2, (cw - IMG_W) // 2 + IMG_W, (ch - IMG_H) // 2 + IMG_H))
    frame = Image.new("L", (1080, 1350), 0)
    frame.paste(a, (IMG_LEFT, 0))
    return frame


if __name__ == "__main__":
    clean_cutout()
    for v in ("B2", "C2"):
        write(v)
    print("封面（八月圖層版式）寫入 B2、C2；去背層收邊 →", CUTOUT)
