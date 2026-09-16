#!/usr/bin/env python3
"""C2「成對色塊」：C 版的修正。奶油塊以兩張為一組連續。

〔2026-09-16 Jesse〕「要以兩頁作為 layout 的思考。」

C 版本來就左右交替出血（1L 2R 3L…），但每張的 FL（色塊下緣）各自不同，
所以滑動時色塊高度跳來跳去，兩張並排看不出是同一塊。
這一版改成三組：(1R,2L) (3R,4L) (5R,6L)。同一組共用 FL，
右出血的那張色塊從 x=384 出到右緣，左出血的那張從左緣到 x=696，
滑過去就是一塊 1392px 寬的奶油紙橫跨兩張卡，頂部細字列的翻色也接得上。

FL 不再從 B 反推，改成直接指定（每組一個值），B = FL + 300 + 130n 反過來算，
「第 3 句 bottom 必須等於 B」的驗算照舊。

對齊與間距（Jesse 指出的）：
  · 引文區 bottom 原本 FL−88，序號方塊 top 是 FL−66，只隔 22px。改成 FL−120，隔 54。
  · 主標 top 原本 FL+108，方塊 bottom FL+66，隔 42。維持。
  · 深底文字全部在 x=84 一條軸；色塊內文字在 84（左出血）或 480（右出血）。
  · 引文區改 bottom 錨定。第一版用字數估行數，第 02 張估 2 行實際 3 行，
    「吧。」直接貼到序號方塊上——就是 Jesse 說的「部件壓在一起」。

〔第三輪 2026-09-16 Jesse〕四項：引文斷行不順、整體單調、括弧要成對、色塊要漸層；
另加「黑底過黑，加紙質」。這一輪的決策：

  1. 括弧成對。同組左張只有「（引文開頭、左上），右張只有」（引文結尾、右下），
     兩張並排是一句被引號括住的話。引文改「一組一句」寫在 copy.json 的 pair_quotes：
     left 是前半（尾巴是「，」）、right 是後半（尾巴是「。」）。舊的 sub[0] 留著沒動。
  2. 懸掛式括弧。text-indent 拿掉，引文塊 516px 寬，括弧獨立一欄 72px：
     左張 = 括弧欄在左、文字從 x+72 起；右張 = 文字從軸起、括弧欄在右。
     文字欄 444px，42px 字剛好 10 個全形字一行（實測 10 字 = 416px）。
     括弧字級 176→160。實測 160px 的「墨跡是 43×91，落在 em 框的 (105,1)；
     」落在 (12,59)。用這些數字把墨跡釘到欄位邊上，兩邊對稱：
     「墨跡頂 = 第一行頂 +6（字面頂在 +12）；」墨跡底 = 末行底 −9（字面底在 −15）。
     斷行不交給 text-wrap:balance——它不認得「安然無恙」是一個詞，會從中間切。
     改成 pair_quotes 字串裡的 \\n 就是斷行，每行 ≤10 字，由人決定在哪裡斷。
  3. 色塊漸層。同組共用一條 1392px 的 linear-gradient（#FFE2A0 → #FFF3D6，左深右淺），
     用 background-size:1392px 100% 切成兩半：左張 position 0，右張 −688px
     （右張色塊 left=−8，畫布 x=0 對應漸層 x=696）。並排時是連續的一張紙。
     奶油紙質 paper_cream 疊在色塊上：grayscale + multiply，opacity .45，
     同樣用 1392px 的 size/position 切半，接縫才不會出現紙紋的跳接。
     驗收：左張最右一欄 vs 右張最左一欄，色塊高度內 RGB 差 ≤3（用 PIL 量）。
  4. 深底紙質。paper_dark（平均亮度 66）整張鋪在色塊底下，mix-blend-mode:screen，
     opacity .22。#0C0E08 的亮度 12 → 目標 18–30。放在 DOM 最前面，色塊與文字都壓在它上面，
     所以奶油塊不受影響。
  5. 質感圖素。每張卡在色塊旁邊的深底直欄（左張 x 84–300、右張 x 780–996，y 176–476）
     放一個黑底雙色版畫（素材/elements/*_trim.png），mix-blend-mode:screen 讓黑底消失，
     opacity .65。兩張並排時圖素落在整組的左右外角，像一對書眉。
     沒有放在「主標下方」：兩行主標的卡（2/4/5/6）主標下方只剩 <40px，放不下。
     離頁首列 ≥72px、離序號方塊 ≥58px。配對：01 滿月、02 月相（一天四場）、03 月餅、
     04 玉兔、05 燈籠（送別）、06 桂花（桂花酒）。
  6. h1 補 text-indent:-.045em（brain 規則：中文大字負縮排，左緣才對得齊小字）。
"""
import os, json, html

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "html", "C2")
COPY = json.load(open(os.path.join(HERE, "spec", "copy.json"), encoding="utf-8"))
MANIFEST = json.load(open(os.path.join(HERE, "素材", "elements", "manifest.json"), encoding="utf-8"))

BG, CREAM, ORANGE, WINE, FOOT = "#0C0E08", "#FFE6A9", "#E84224", "#741017", "#B8B58E"
LOGO_Y = "file://" + os.path.join(HERE, "素材", "logo-yellow-horizontal.png")
PAPER_DARK = "file://" + os.path.join(HERE, "素材", "textures", "paper_dark.png")
PAPER_CREAM = "file://" + os.path.join(HERE, "素材", "textures", "paper_cream.png")
ELEM_DIR = os.path.join(HERE, "素材", "elements")
FIELD_W, BLEED = 704, 8
PAIR_W = 2 * (FIELD_W - BLEED)            # 1392：整組色紙的寬度
GRAD = "linear-gradient(90deg,#FFE2A0 0%,#FFE6A9 38%,#FFF3D6 100%)"

# 三組，每組共用一個 FL。n = 主標行數。
PAIR_FL = {(1, 2): 600, (3, 4): 620, (5, 6): 640}
SIDE = {1: "R", 2: "L", 3: "R", 4: "L", 5: "R", 6: "L"}
HEAD = {
    1: ["首次約會免費"],
    2: ["二擇一：", "一天四場"],
    3: ["每天至少滑 40 人"],
    4: ["你看得到", "誰喜歡你了"],
    5: ["破冰卡牌，", "十月說再見"],
    6: ["出示下載畫面，", "招待一杯"],
}
EN = {1: "MILESTONE 25,000", 2: "BIG UPDATE", 3: "MORE SWIPES",
      4: "NEW FEATURE", 5: "FAREWELL", 6: "EVENT"}
ELEM = {1: "full_moon", 2: "crescents", 3: "mooncake",
        4: "rabbit", 5: "lantern", 6: "osmanthus"}
ELEM_BOX = (216, 300)                     # 圖素外框；y 176–476
ELEM_TOP, ELEM_H = 176, 300

# 引文：括弧欄寬、括弧字級與實測墨跡位置（見檔頭 2.）
PULL_W, BR_COL, BR_SIZE = 516, 72, 160
BR_OPEN_INK = (105, 1)                    # 「墨跡左上角在 em 框內的位置
BR_CLOSE_INK = (12, 59, 55, 150)          # 」墨跡 x0,y0,x1,y1


def esc(s):
    return html.escape(str(s or ""))


def pair_quote(n):
    """回 (text, side)：這張卡要放的半句與括弧邊。"""
    for pq in COPY["pair_quotes"]:
        if n == pq["cards"][0]:
            return pq["left"], "open"
        if n == pq["cards"][1]:
            return pq["right"], "close"
    raise KeyError("copy.json 的 pair_quotes 沒有第 %d 張" % n)


def geom(n):
    fl = next(v for k, v in PAIR_FL.items() if n in k)
    lines = len(HEAD[n])
    left = (SIDE[n] == "L")
    g = {
        "fl": fl, "n": lines,
        "field_left": -BLEED if left else 384,
        "E": 696 if left else 384,
        "text_left": 84 if left else 480,
        "head_top": fl + 108,
        # 漸層與紙紋的切半位移：左出血那張（右張）畫布 x=0 要對到漸層 x=696
        "grad_x": -(PAIR_W // 2 - BLEED) if left else 0,
        # 圖素放在色塊旁的深底直欄
        "elem_left": 780 if left else 84,
    }
    g["s2_top"] = g["head_top"] + 130 * lines + 64
    g["s3_top"] = g["s2_top"] + 74
    g["B"] = g["s3_top"] + 54
    # 規格的驗算反過來：B 必須等於 FL + 300 + 130n
    assert g["B"] == fl + 300 + 130 * lines, "第 %d 張幾何對不上" % n
    return g


BASE = """
html,body{margin:0;padding:0}*{box-sizing:border-box}
.c{width:1080px;height:1350px;background:%(bg)s;position:relative;overflow:hidden;isolation:isolate;
   font-family:"HarmonyOS Sans TC",-apple-system,sans-serif;-webkit-font-smoothing:antialiased}
/* 深底紙質：整張鋪、screen、放在最底層，色塊與文字都在它上面 */
.paper{position:absolute;inset:0;background:url(%(paper_dark)s) center/cover no-repeat;
   mix-blend-mode:screen;opacity:.22}
/* 色塊：1392px 的漸層切成兩半，同組兩張並排是一張連續的紙 */
.field{position:absolute;top:-8px;width:704px;background:%(grad)s;background-size:1392px 100%%;
   background-repeat:no-repeat}
.grain{position:absolute;inset:0;background:url(%(paper_cream)s) 0 0/1392px auto no-repeat;
   mix-blend-mode:multiply;opacity:.45;filter:grayscale(1) contrast(1.25)}
.el{position:absolute;mix-blend-mode:screen;opacity:.65}
.rail{position:absolute;left:84px;right:84px;top:60px;display:flex;justify-content:space-between;
   font-family:Inter,sans-serif;font-weight:500;font-size:20px;line-height:24px;
   letter-spacing:.22em;text-transform:uppercase;font-variant-numeric:tabular-nums}
.rule-top{position:absolute;left:84px;right:84px;top:104px;height:1.5px}
.foot-rule{position:absolute;left:84px;right:84px;top:1244px;height:1.5px;
   background:rgba(255,230,169,.34)}
.foot{position:absolute;left:84px;right:84px;top:1274px;display:flex;justify-content:space-between;
   font-family:Inter,sans-serif;font-weight:500;font-size:20px;line-height:24px;
   letter-spacing:.22em;text-transform:uppercase;color:%(foot)s}
.tick{position:absolute;width:72px;height:6px;background:%(orange)s;top:148px}
.en{position:absolute;top:168px;font-family:Inter,sans-serif;font-weight:500;font-size:22px;
   line-height:28px;letter-spacing:.20em;text-transform:uppercase;color:%(bg)s}
/* 引文區以 bottom 錨定（底 = FL−120），行數再多也往上長，離序號方塊永遠 54px。
   括弧懸掛在獨立一欄：左張欄在左（開引號、對齊第一行），右張欄在右（閉引號、對齊末行）。
   斷行由 copy.json 的 \\n 決定，每行 ≤10 個全形字。 */
.pull{position:absolute;width:%(pull_w)dpx;font-weight:400;font-size:42px;line-height:64px;
   letter-spacing:.01em;color:%(bg)s;white-space:nowrap}
.pull.open{padding-left:%(br_col)dpx}
.pull.close{padding-right:%(br_col)dpx}
.pull .br{position:absolute;font-size:%(br_size)dpx;line-height:1;font-weight:500;color:%(orange)s}
.pull.open .br{left:%(open_x)dpx;top:%(open_y)dpx}
.pull.close .br{left:%(close_x)dpx;bottom:%(close_y)dpx}
.stamp{position:absolute;width:132px;height:132px;background:%(orange)s}
.stamp span{position:absolute;left:0;right:0;top:34px;text-align:center;
   font-family:Inter,sans-serif;font-weight:500;font-size:56px;line-height:64px;
   color:%(bg)s;font-variant-numeric:tabular-nums}
h1{position:absolute;left:84px;width:912px;margin:0;font-weight:500;font-size:116px;
   line-height:130px;letter-spacing:-.04em;text-indent:-.045em;color:%(cream)s}
.s2{position:absolute;left:84px;width:828px;font-weight:400;font-size:34px;line-height:54px;
   color:%(cream)s}
.s3{position:absolute;left:84px;width:828px;font-weight:500;font-size:34px;line-height:54px;
   color:%(orange)s}
""" % {
    "bg": BG, "cream": CREAM, "orange": ORANGE, "foot": FOOT,
    "paper_dark": PAPER_DARK, "paper_cream": PAPER_CREAM, "grad": GRAD,
    "pull_w": PULL_W, "br_col": BR_COL, "br_size": BR_SIZE,
    # 「墨跡左緣落在引文塊左緣、墨跡頂落在第一行頂 +6
    "open_x": -BR_OPEN_INK[0], "open_y": 6 - BR_OPEN_INK[1],
    # 」墨跡右緣落在引文塊右緣、墨跡底落在末行底 −9
    "close_x": PULL_W - BR_CLOSE_INK[2], "close_y": 9 - (BR_SIZE - BR_CLOSE_INK[3]),
}


def page(inner, extra=""):
    return ('<!doctype html><meta charset="utf-8">'
            '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">'
            '<style>%s%s</style>%s' % (BASE, extra, inner))


def rail_flip(g, right_text):
    """翻色裁切。inset 相對元素（left:84 right:84），不是畫布。"""
    fx0 = max(0, g["field_left"]); fx1 = min(1080, g["field_left"] + FIELD_W)
    EL, ER = 84, 996
    dark = "inset(0 %dpx 0 %dpx)" % (max(0, ER - fx1), max(0, fx0 - EL))
    light = ("inset(0 0 0 %dpx)" % max(0, fx1 - EL)) if fx0 <= EL \
        else ("inset(0 %dpx 0 0)" % max(0, ER - fx0))
    txt = '<span>%s</span><span>%s</span>' % (esc(COPY["issue_title_en"]), esc(right_text))
    return ('<div class="rail" style="color:%s;clip-path:%s">%s</div>'
            '<div class="rail" style="color:%s;clip-path:%s">%s</div>'
            '<div class="rule-top" style="background:rgba(12,14,8,.34);clip-path:%s"></div>'
            '<div class="rule-top" style="background:rgba(255,230,169,.34);clip-path:%s"></div>'
            % (BG, dark, txt, CREAM, light, txt, dark, light))


def foot():
    return ('<div class="foot-rule"></div><div class="foot">'
            '<span>@LAVA_DATING</span><span>FEWER TEXTS, BETTER DATES.</span></div>')


def element(n, g):
    """色塊旁深底直欄裡的版畫圖素：contain 進 216×300 的框，置中。"""
    name = ELEM[n]
    m = next(x for x in MANIFEST if x["name"] == name)
    tw, th = m["trim_size"]
    k = min(ELEM_BOX[0] / tw, ELEM_BOX[1] / th)
    w, h = round(tw * k), round(th * k)
    left = g["elem_left"] + (ELEM_BOX[0] - w) // 2
    top = ELEM_TOP + (ELEM_H - h) // 2
    src = "file://" + os.path.join(ELEM_DIR, m["trim_file"])
    return ('<img class="el" src="%s" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">'
            % (src, left, top, w, h))


def pull(n, g):
    text, side = pair_quote(n)
    lines = "<br>".join(esc(x) for x in text.split("\n"))
    bottom = 1350 - (g["fl"] - 120)                      # 引文底 = FL−120，離方塊 54px
    br = "「" if side == "open" else "」"
    return ('<div class="pull %s" style="left:%dpx;bottom:%dpx"><span class="br">%s</span>%s</div>'
            % (side, g["text_left"], bottom, br, lines))


def inner_card(card):
    n = card["n"]; g = geom(n)
    sub = card.get("sub") or ["", "", ""]
    return page(
        '<div class="c"><div class="paper"></div>'
        '<div class="field" style="left:%dpx;height:%dpx;background-position:%dpx 0">'
        '<div class="grain" style="background-position:%dpx 0"></div></div>%s%s'
        '<div class="tick" style="left:%dpx"></div>'
        '<div class="en" style="left:%dpx">%s</div>%s'
        '<div class="stamp" style="left:%dpx;top:%dpx"><span>%02d</span></div>'
        '<h1 style="top:%dpx">%s</h1>'
        '<div class="s2" style="top:%dpx">%s</div>'
        '<div class="s3" style="top:%dpx">%s</div>%s</div>'
        % (g["field_left"], g["fl"] + BLEED, g["grad_x"], g["grad_x"],
           element(n, g), rail_flip(g, "%02d / 06 →" % n),
           g["text_left"], g["text_left"], esc(EN[n]), pull(n, g),
           g["E"] - 66, g["fl"] - 66, n,
           g["head_top"], "<br>".join(esc(x) for x in HEAD[n]),
           g["s2_top"], esc(sub[1]), g["s3_top"], esc(sub[2]), foot()))


def endcard():
    extra = """
    .wine{position:absolute;left:0;top:0;width:1080px;height:700px;background:%(w)s}
    .eh{position:absolute;left:84px;top:300px;width:912px;margin:0;font-size:176px;
      line-height:172px;font-weight:500;letter-spacing:-.05em;color:#FFE6A9}
    .es{position:absolute;left:84px;top:800px;width:828px;font-size:34px;font-weight:400;
      line-height:54px;color:#FFE6A9}
    .et{position:absolute;left:84px;top:960px;font-size:34px;line-height:54px;font-weight:500;
      color:%(o)s}
    .logo{position:absolute;left:50%%;top:56px;transform:translateX(-50%%);height:26px}
    """ % {"w": WINE, "o": ORANGE}
    return page(
        '<div class="c"><div class="paper"></div><div class="wine"></div><img class="logo" src="%s">'
        '<div class="rail" style="color:#FFE6A9"><span>%s</span><span>END</span></div>'
        '<h1 class="eh">出來<br>見面吧</h1><div class="es">%s</div>'
        '<div class="et">fewer texts, better dates.</div>%s</div>'
        % (LOGO_Y, esc(COPY["issue_title_en"]),
           esc(COPY["disclaimer_line"]).replace("，", "，<br>", 1), foot()), extra)


def main():
    os.makedirs(OUT, exist_ok=True)
    files = []
    for c in COPY["cards"]:
        files.append(("%02d_%s" % (c["n"] + 1, EN[c["n"]].split()[0].lower()), inner_card(c)))
    files.append(("08_end", endcard()))
    for name, content in files:
        open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8").write(content)
    print("C2 寫出 %d 張；成對 FL：%s" % (len(files), PAIR_FL))
    for n in range(1, 7):
        g = geom(n)
        print("   %02d %s FL=%d B=%d 方塊 x=%d 漸層位移=%d 圖素=%s"
              % (n, SIDE[n], g["fl"], g["B"], g["E"] - 66, g["grad_x"], ELEM[n]))


if __name__ == "__main__":
    main()
