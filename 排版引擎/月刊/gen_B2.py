#!/usr/bin/env python3
"""B2「連續字帶」：B 版的修正。字牆不再是每張各自一面牆，
而是一條橫跨七張卡的連續帶子，每張卡只是它的一段窗口。

〔2026-09-16 Jesse〕「everyday 的 A 跟 Y 會超出這個文字框，
那你下一頁的左側應該也要有 A 跟 Y 才對。要以兩頁為單位來設計，
務必要以兩頁作為 layout 的思考。」

做法：所有卡片共用**同一份**字帶 DOM，總寬 7×1080。第 k 張卡把它往左推
k×1080px，再用畫布裁掉。連續性是結構保證的，不是對出來的——
同一份 DOM 不可能在兩張卡上長得不一樣。

第一版（字級 276）的錯：字寬是用「每字母 0.478em」估的，實際量出來是
0.55–0.58em，長字溢出 300px，直接壓在下一張的字上。
這一版不估，**量**：先用無頭 Chrome 量每個字的實際寬度，再反算字級與字距，
寫完 HTML 之後再量一次整條帶子，溢出量不在範圍內就直接報錯。

規則（一條軸、一個溢出量）：
  · 所有元件左緣在 x=96。
  · 上排長字全部 8 個字母，每個字用字距微調到同一個寬度 1032px，
    所以每一張都剛好溢出 48px 到下一張左緣，離下一張的字 48px。
  · 下排橘字是這張的關鍵字，自然字距，必須在 x=984 之前結束。
  · 字帶 bottom 828、細線 904（隔 76）、中文 top 944（隔 40）。

第三輪〔2026-09-16 Jesse〕「接縫 OK，但視覺上稍微太單調。請在黑色區域加上一些
設計素材……黑底過黑，加紙質材質。」

  紙質：素材/textures/paper_dark.png 滿版 <img>，mix-blend-mode:screen。
    只能用 screen 不能用 overlay——overlay 在暗底上是 2×a×b，會把 #0C0E08 壓得更黑。
    透明度是反算的：底 L≈12、紙 L≈67，screen 後 ≈76，合成 L = 12 + 64×α；
    目標背景亮度 18–30 → α 落在 .10–.28，取 .22（量出來的空白區平均 L 見 main() 印出）。
    紙放在最底層，字帶、細線、字都在它上面，所以細線不會被紙吃掉。
  圖素：素材/elements/*_trim.png（黑底兩色版畫），<img> + mix-blend-mode:screen，
    黑底就消失。放置表在 PLACE（card → element, x, y, w, opacity），一律資料不散在 HTML。
    位置只用兩個空區：
      A 區 = 章節標（y 172）與字帶頂（y 478）之間，元素一律 bottom=430（離字帶 48），
        右緣貼 x=984，跟左邊的章節標形成一左一右；高度 250–280，它是材質不是主角。
      B 區 = 下排橘字右側（x ≥ 橘字右緣+48）、上排字下方 48px 起（y 701–856），
        只給尾板用一次（星點），其他卡不塞，留白本來就是這版的語言。
    每張一個主題圖素，對應那張的文案：燈籠＝慶祝破 25,000；三個月相＝一天四輪；
    星點散布＝每天 40 人；玉兔回頭＝誰喜歡你；桂花枝＝溫柔道別；切開的月餅＝招待一杯；
    滿月＝收尾（Jesse：滿月放收尾卡最合理）。星點在尾板再用一次，其餘每個圖素只用一次。
    透明度 .62（滿月 .70）：奶油色 ×.62 後亮度 ≈137，低於中文標題（228）、
    又不搶下排橘字，橘字仍是版面上最飽和的一層。
  兩個踩過的坑（都在 decor() 的註解裡）：opacity 與遮罩一定要跟 mix-blend-mode 放在同一個
    <img> 上，放在外層 div 會把 div 變成獨立合成群組，黑底整塊露出來；裁切的散點層要加
    橢圓遮罩（半徑 = 框的一半）讓邊緣淡出，否則框邊會有半顆星。量過遮罩不會壓暗底色
    （帶內外中位數都是 L 27）。
  自檢：check_layout() 量出章節標的實際寬度、拿 verify() 量到的橘字右緣，
    逐一算圖素框到每個文字框的距離，< 48px 就報錯；x 也擋在 96–984 之內，
    不壓接縫（字帶從那裡溢出）。
"""
import os, re, json, html, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "html", "B2")
COPY = json.load(open(os.path.join(HERE, "spec", "copy.json"), encoding="utf-8"))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

BG, INK, ACC, WALL = "#0C0E08", "#FFE6A9", "#E84224", "#33381F"
RULE = "rgba(255,230,169,.28)"
FONTS_LINK = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;900&display=swap" rel="stylesheet">'

ASSETS = os.path.join(HERE, "素材")
PAPER = os.path.join(ASSETS, "textures", "paper_dark.png")
PAPER_OPACITY = 0.22         # 見檔頭：合成 L = 12 + 64×α → 26
ELEMENTS = {m["name"]: (os.path.join(ASSETS, "elements", m["trim_file"]), m["trim_size"])
            for m in json.load(open(os.path.join(ASSETS, "elements", "manifest.json"), encoding="utf-8"))}
EL_OPACITY = 0.62
MIN_GAP = 48                 # 圖素框 ↔ 任何文字框
A_BOTTOM = 430               # A 區圖素底緣：字帶頂 478 − 48

# 放置表：card → [(element, x, y, w, opacity[, crop_h])]。
# 高度由圖素長寬比算出；有 crop_h 的（星點散布）用 w 縮放後只露出中間 crop_h 高的一段。
PLACE = {
    "02_milestone": [("lantern",   789, 150, 195, EL_OPACITY)],
    "03_big":       [("crescents", 624, 180, 360, EL_OPACITY)],
    "04_more":      [("stars",     524, 150, 460, EL_OPACITY, 280)],
    "05_new":       [("rabbit",    829, 151, 155, EL_OPACITY)],
    "06_farewell":  [("osmanthus", 758, 150, 226, EL_OPACITY)],
    "07_event":     [("mooncake",  686, 150, 298, EL_OPACITY)],
    "08_end":       [("full_moon", 704, 142, 280, 0.70),
                     ("stars",     684, 706, 300, 0.50, 150)],
}

X = 96                       # 唯一的左軸
CARD_W = 1080
N_CARDS = 7                  # 六張內頁 + 尾板；封面照八月版式沒有字帶
RIGHT_EDGE = CARD_W - X      # 984：下排字的右界
GAP = 48                     # 溢出片段 → 下一張第一個字 的空隙
TARGET_W = CARD_W - GAP      # 1032：上排每個字的目標寬度；溢出 = X + TARGET_W − CARD_W = 48
TRACK0 = -0.055              # 基準字距（em）
SCALE_X = 0.86
LINE_H = 0.80

# 每張卡在字帶上的兩個字：上排長字（8 字母，會跨頁），下排橘色關鍵字。
STRIP = [
    ("THOUSAND", "FREE"),        # 01 25,000 人 · 首次約會免費
    ("MATCHING", "FOUR"),        # 02 二擇一 · 一天四場
    ("EVERYDAY", "FORTY"),       # 03 每天 40 人
    ("SOMEBODY", "LIKED"),       # 04 誰喜歡你
    ("FAREWELL", "CARDS"),       # 05 破冰卡牌退場
    ("TOGETHER", "CHEERS"),      # 06 聯名場 · 招待一杯
    ("OUTDOORS", "MEET"),        # 尾板 出來見面吧
]
HEAD = {
    1: "首次約會免費", 2: "二擇一：一天四場", 3: "每天至少滑 40 人",
    4: "你看得到誰喜歡你了", 5: "破冰卡牌，十月說再見", 6: "出示下載畫面，招待一杯",
}
EN = {1: "MILESTONE", 2: "BIG UPDATE", 3: "MORE SWIPES",
      4: "NEW FEATURE", 5: "FAREWELL", 6: "EVENT"}

STRIP_CSS = """
.strip{position:absolute;top:0;left:0;font-family:Inter,sans-serif;font-weight:900;
   letter-spacing:%(t).4fem;text-transform:uppercase;white-space:nowrap;
   font-size:%(font)dpx;line-height:%(lh)s;color:%(wall)s}
.strip span{position:absolute;display:inline-block;transform:scaleX(%(sx)s);transform-origin:left top}
.strip .hot{color:%(acc)s}
"""


def esc(s):
    return html.escape(str(s or ""))


def measure(spans_html, font_px, page_w):
    """無頭 Chrome 量每個 span 的實際框：回傳 [(text, left, right)]。

    字型載好才量（document.fonts.ready）；量的是 transform 之後的框，
    也就是畫面上真正佔的寬度。
    """
    css = STRIP_CSS % {"t": TRACK0, "font": font_px, "lh": LINE_H, "wall": WALL,
                       "acc": ACC, "sx": SCALE_X}
    doc = ('<!doctype html><meta charset="utf-8">%s<style>body{margin:0;width:%dpx}%s</style>'
           '<div class="strip">%s</div><pre id="out"></pre>'
           '<script>document.fonts.ready.then(()=>{const o=[];'
           'document.querySelectorAll(".strip span").forEach(e=>{const r=e.getBoundingClientRect();'
           'o.push(e.textContent+"\\t"+r.left.toFixed(2)+"\\t"+r.right.toFixed(2))});'
           'document.getElementById("out").textContent=o.join("\\n")})</script>'
           % (FONTS_LINK, page_w, css, spans_html))
    fd, path = tempfile.mkstemp(suffix=".html"); os.close(fd)
    open(path, "w", encoding="utf-8").write(doc)
    r = subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--window-size=%d,2000" % page_w,
                        "--virtual-time-budget=8000", "--dump-dom", "file://" + path],
                       capture_output=True, timeout=120)
    os.unlink(path)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout.decode("utf-8", "ignore"), re.S)
    if not m or not m.group(1).strip():
        raise SystemExit("量測失敗：Chrome 沒回傳寬度（字型或網路？）")
    rows = []
    for line in html.unescape(m.group(1)).strip().split("\n"):
        t, l, rr = line.split("\t")
        rows.append((t, float(l), float(rr)))
    return rows


def em_widths(words):
    """每個字在 100px、基準字距下的寬度（em）。"""
    spans = "".join('<span style="left:0;top:%dpx">%s</span>' % (i * 100, w)
                    for i, w in enumerate(words))
    return {t: (r - l) / 100.0 for t, l, r in measure(spans, 100, 6000)}


def plan():
    """反算字級與每個長字的字距。

    字級由最寬的長字決定（它用基準字距剛好 1032px）。
    其他長字比它窄，補字距讓寬度也到 1032：
      量到的寬 u（em）含 scaleX 與基準字距，所以
      W(L) = F × (u + SCALE_X × n × (L − TRACK0))，解 W = TARGET_W。
    """
    words = sorted({w for pair in STRIP for w in pair})
    em = em_widths(words)
    long_words = [p[0] for p in STRIP]
    font = int(TARGET_W / max(em[w] for w in long_words))
    track = {}
    for w in long_words:
        track[w] = (TARGET_W / font - em[w]) / (SCALE_X * len(w)) + TRACK0
    return font, track, em


def strip_dom(font, track):
    """整條字帶。每個字絕對定位在它那張卡的 X 軸上，上排長字溢到右邊那張。"""
    rows = []
    for r in (0, 1):
        for k, pair in enumerate(STRIP):
            word = pair[r]
            style = "left:%dpx;top:%dpx" % (k * CARD_W + X, int(r * font * LINE_H))
            if r == 0:
                style += ";letter-spacing:%.4fem" % track[word]
            rows.append('<span class="w%s" style="%s">%s</span>'
                        % (" hot" if r == 1 else "", style, esc(word)))
    return "".join(rows)


def verify(font, track):
    """寫完再量一次整條帶子。上排每個字溢出 GAP±3px；下排在 984 前結束。"""
    rows = measure(strip_dom(font, track), font, CARD_W * N_CARDS)
    bad = []
    report = []
    hot_right = {}
    for t, l, r in rows:
        k = int(l // CARD_W)
        local_r = r - k * CARD_W
        if t in dict(STRIP):                            # 上排
            spill = local_r - CARD_W
            report.append("   %-9s 溢出 %+5.1fpx" % (t, spill))
            if abs(spill - GAP) > 3:
                bad.append("%s 溢出 %.1f（要 %d）" % (t, spill, GAP))
        else:                                           # 下排
            report.append("   %-9s 右緣 %6.1f" % (t, local_r))
            hot_right[t] = local_r
            if local_r > RIGHT_EDGE:
                bad.append("%s 右緣 %.1f 超過 %d" % (t, local_r, RIGHT_EDGE))
    return report, bad, hot_right


def base_css(font):
    row = int(font * LINE_H)
    wh = row * 2 + 8
    return """
html,body{margin:0;padding:0}*{box-sizing:border-box}
.c{width:1080px;height:1350px;background:%(bg)s;position:relative;overflow:hidden;isolation:isolate;
   font-family:"HarmonyOS Sans TC",-apple-system,sans-serif;-webkit-font-smoothing:antialiased}
.paper{position:absolute;left:0;top:0;width:1080px;height:1350px;object-fit:cover;
   mix-blend-mode:screen;opacity:%(paper_op).2f;pointer-events:none}
.el{position:absolute;overflow:hidden;pointer-events:none}
.el img{position:absolute;left:0;display:block;mix-blend-mode:screen}
.rule{position:absolute;left:%(x)dpx;right:%(x)dpx;height:1px;background:%(rule)s}
.micro{position:absolute;font-family:Inter,sans-serif;font-weight:500;font-size:20px;
   line-height:24px;letter-spacing:.24em;text-transform:uppercase;
   color:rgba(255,230,169,.55);font-variant-numeric:tabular-nums}
.sect{position:absolute;left:%(x)dpx;top:144px;font-family:Inter,sans-serif;font-weight:600;
   font-size:24px;line-height:28px;letter-spacing:.20em;color:%(acc)s;
   font-variant-numeric:tabular-nums}
.sect b{font-weight:600;margin-right:32px}
/* 字帶視窗：高度 = 兩行；整條帶子在裡面往左推 k×1080 */
.win{position:absolute;left:0;top:%(wtop)dpx;width:1080px;height:%(wh)dpx;overflow:hidden}
%(strip)s
.zh{position:absolute;left:%(x)dpx;width:888px;top:944px}
.zh h1{margin:0 0 14px;font-weight:500;font-size:72px;line-height:92px;letter-spacing:.02em;
   color:%(ink)s}
.zh p{margin:0;font-weight:400;font-size:32px;line-height:50px;letter-spacing:.04em;
   color:rgba(255,230,169,.74)}
""" % {"bg": BG, "rule": RULE, "acc": ACC, "ink": INK, "x": X, "paper_op": PAPER_OPACITY,
       "wh": wh, "wtop": 828 - row * 2,
       "strip": STRIP_CSS % {"t": TRACK0, "font": font, "lh": LINE_H, "wall": WALL,
                             "acc": ACC, "sx": SCALE_X}}


def page(css, inner):
    return '<!doctype html><meta charset="utf-8">%s<style>%s</style>%s' % (FONTS_LINK, css, inner)


def el_box(item):
    """放置表一列 → (name, x, y, w, h, opacity, img_h)。h 是框高，img_h 是圖縮放後的高。"""
    name, x, y, w, op = item[:5]
    sw, sh = ELEMENTS[name][1]
    img_h = int(round(w * sh / sw))
    h = item[5] if len(item) > 5 else img_h
    return name, x, y, w, h, op, img_h


def decor(card_name):
    """紙質 + 這張卡的圖素。放在 DOM 最前面，所以在所有文字與細線之下。"""
    out = ['<img class="paper" src="file://%s">' % PAPER]
    for item in PLACE.get(card_name, []):
        name, x, y, w, h, op, img_h = el_box(item)
        # opacity 一定要跟 mix-blend-mode 放在同一個 <img> 上：放在外層 div 會讓 div 變成
        # 獨立的合成群組，img 只跟透明的 div 混合，黑底就整塊露出來（第一版踩到）。
        style = "width:%dpx;top:%dpx;opacity:%.2f" % (w, -(img_h - h) // 2, op)
        if h != img_h:
            # 裁切的散點層：硬切會在框邊留半顆星。橢圓遮罩（半徑 = 框的一半）讓邊緣淡出，
            # 遮罩一樣要放在 img 上，理由同 opacity。
            mask = "radial-gradient(ellipse %dpx %dpx at 50%% 50%%, #000 45%%, transparent 100%%)" % (w // 2, h // 2)
            style += ";-webkit-mask-image:%s;mask-image:%s" % (mask, mask)
        out.append('<div class="el" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">'
                   '<img src="file://%s" style="%s"></div>'
                   % (x, y, w, h, ELEMENTS[name][0], style))
    return "".join(out)


def measure_boxes(css, inner_html):
    """量任意一段 HTML 裡 .m 元素的框（left, top, right, bottom）。章節標寬度用這個量。"""
    doc = ('<!doctype html><meta charset="utf-8">%s<style>body{margin:0;width:1080px}%s</style>'
           '%s<pre id="out"></pre>'
           '<script>document.fonts.ready.then(()=>{const o=[];'
           'document.querySelectorAll(".m").forEach(e=>{const r=e.getBoundingClientRect();'
           'o.push([r.left,r.top,r.right,r.bottom].map(v=>v.toFixed(1)).join("\\t"))});'
           'document.getElementById("out").textContent=o.join("\\n")})</script>'
           % (FONTS_LINK, css, inner_html))
    fd, path = tempfile.mkstemp(suffix=".html"); os.close(fd)
    open(path, "w", encoding="utf-8").write(doc)
    r = subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--window-size=1080,2000",
                        "--virtual-time-budget=8000", "--dump-dom", "file://" + path],
                       capture_output=True, timeout=120)
    os.unlink(path)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout.decode("utf-8", "ignore"), re.S)
    if not m or not m.group(1).strip():
        raise SystemExit("量測失敗：Chrome 沒回傳框")
    return [tuple(float(v) for v in line.split("\t"))
            for line in html.unescape(m.group(1)).strip().split("\n")]


def rect_gap(a, b):
    """兩個 (l,t,r,b) 框的最短距離；重疊為 0。"""
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def check_layout(css, font, hot_right):
    """圖素框 vs 文字框 ≥ MIN_GAP、x 在 96–984 之內。文字框：上細字列、章節標（量的）、
    字帶上排（全寬）、下排橘字（verify 量到的右緣）、中文區、下細字列。"""
    row = int(font * LINE_H)
    top = 828 - row * 2
    sect_html = "".join('<div class="sect m" style="top:%dpx"><b>%02d</b>%s</div>' % (200 * n, n, esc(EN[n]))
                        for n in sorted(EN))
    sect_w = {n: r - l for n, (l, t, r, b) in zip(sorted(EN), measure_boxes(css, sect_html))}
    bad = []
    for card, items in PLACE.items():
        n = int(card[:2]) - 1
        boxes = [("上細字", (X, 56, CARD_W - X, 80)),
                 ("字帶上排", (0, top, CARD_W, top + row)),
                 ("字帶橘字", (X, top + row, hot_right[STRIP[n - 1][1]], top + 2 * row)),
                 ("中文區", (X, 944, CARD_W - X, 1150)),
                 ("下細字", (X, 1230, CARD_W - X, 1254))]
        if n in EN:
            boxes.append(("章節標", (X, 144, X + sect_w[n], 172)))
        for item in items:
            name, x, y, w, h, op, img_h = el_box(item)
            box = (x, y, x + w, y + h)
            if x < X or x + w > CARD_W - X:
                bad.append("%s %s 超出 96–984（%d–%d）" % (card, name, x, x + w))
            for label, tb in boxes:
                g = rect_gap(box, tb)
                if g < MIN_GAP:
                    bad.append("%s %s 離%s只有 %.0fpx" % (card, name, label, g))
    return bad


def rails(right):
    return ('<div class="rule" style="top:96px"></div>'
            '<div class="rule" style="top:904px"></div>'
            '<div class="rule" style="top:1206px"></div>'
            '<div class="micro" style="left:%dpx;top:56px">%s</div>'
            '<div class="micro" style="right:%dpx;top:56px">%s</div>'
            '<div class="micro" style="left:%dpx;top:1230px">@LAVA_DATING</div>'
            '<div class="micro" style="right:%dpx;top:1230px">FEWER TEXTS, BETTER DATES.</div>'
            % (X, esc(COPY["issue_title_en"]), X, esc(right), X, X))


def window(k, dom):
    """第 k 張卡（0 起算）看到的那一段字帶。"""
    return ('<div class="win"><div style="position:absolute;left:%dpx;top:0" class="strip">%s</div></div>'
            % (-k * CARD_W, dom))


def card_name(n):
    return "%02d_%s" % (n + 1, EN[n].split()[0].lower())


def inner_card(card, css, dom):
    n = card["n"]
    sub = card.get("sub") or ["", "", ""]
    return page(css,
        '<div class="c">%s%s%s'
        '<div class="sect"><b>%02d</b>%s</div>'
        '<div class="zh"><h1>%s</h1><p>%s<br>%s</p></div>'
        '</div>' % (decor(card_name(n)), rails("%02d / 06 →" % n), window(n - 1, dom), n, esc(EN[n]),
                    esc(HEAD[n]), esc(sub[1]), esc(sub[2])))


def endcard(css, dom):
    # 免責一句在「，」處斷行，兩行等長；口號已在底部細字列，不重複。
    note = esc(COPY["disclaimer_line"]).replace("，", "，<br>", 1)
    return page(css,
        '<div class="c">%s%s%s'
        '<div class="zh"><h1>出來見面吧</h1><p>%s</p></div>'
        '</div>' % (decor("08_end"), rails("END"), window(6, dom), note))


def main():
    os.makedirs(OUT, exist_ok=True)
    font, track, em = plan()
    report, bad, hot_right = verify(font, track)
    print("B2 字帶字級 %dpx（最寬長字 %s）" % (font, max((p[0] for p in STRIP), key=lambda w: em[w])))
    print("\n".join(report))
    if bad:
        raise SystemExit("字帶量測不過：\n   " + "\n   ".join(bad))
    css = base_css(font)
    bad = check_layout(css, font, hot_right)
    if bad:
        raise SystemExit("圖素放置不過：\n   " + "\n   ".join(bad))
    print("圖素放置檢查通過：%d 個框，離所有文字框 ≥ %dpx、x 在 %d–%d" % (
        sum(len(v) for v in PLACE.values()), MIN_GAP, X, CARD_W - X))
    dom = strip_dom(font, track)
    files = []
    for c in COPY["cards"]:
        files.append((card_name(c["n"]), inner_card(c, css, dom)))
    files.append(("08_end", endcard(css, dom)))
    for name, content in files:
        open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8").write(content)
    print("B2 寫出 %d 張內頁＋尾板；上排字距：%s" % (
        len(files), "  ".join("%s %+.3f" % (w, t) for w, t in track.items())))


if __name__ == "__main__":
    main()
