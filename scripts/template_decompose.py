#!/usr/bin/env python3
"""範本拆解：把一張參考圖拆成可以照著做的元素。

為什麼要有這支〔2026-09-10 Jesse：「把 template 裡的各項元素進行拆解，
例如字型、圖素、排版方式、呈現風格、內文撰寫方式」〕：

  現在的 data/templates.json 有 23 個範本，但每個只記了**敘事結構**
  （skeleton：cover 放什麼、中段怎麼推進、尾張放什麼）。
  視覺那一面完全空白——沒有色票、沒有版位、沒有明暗結構。
  結果是「我喜歡這張的感覺」這件事沒有辦法被系統接住，
  只能靠 Jesse 每次口頭描述，而口頭描述無法被重複執行。

  拆解要的是**可以照著做的數字**，不是形容詞。
  「暖色調、留白多」不能執行；「主色 #F4E3D0 佔 47%、文字集中在下三分之一、
  上緣留白 18%」可以直接餵給排版引擎。

分成兩層，界線畫清楚：

  A 量得出來的（這支負責，純 PIL，不需要模型也不需要網路）
      色票與佔比、明暗三段結構、文字區在哪一格、留白比例、
      長寬比、文字區與底圖的對比
  B 量不出來的（這支只負責把題目整理好，交給視覺模型或人）
      字型是哪一款、圖素風格（插畫／攝影／3D）、
      情緒語彙、內文撰寫方式

  刻意不假裝 B 也能自動做。字型辨識用像素比對是不可靠的，
  猜錯了會變成「系統說這是 Noto Serif，於是所有稿都用錯字型」——
  一個猜出來的答案比一個空白欄位危險，因為空白會有人去填，猜測不會。

用法：
  python3 scripts/template_decompose.py --image ref.jpg
  python3 scripts/template_decompose.py --dir docs/finals/<post-id>    # 拆整篇
  python3 scripts/template_decompose.py --dir <參考圖資料夾> --save 名稱
      # --save 會寫成 data/templates.json 裡的候選範本（status: candidate）
"""
import os, sys, json, glob, argparse, colorsys, importlib.util

from PIL import Image, ImageFilter, ImageStat

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

GRID_X, GRID_Y = 3, 5          # 版位網格：橫三直五，夠細到分出「下三分之一」又不會碎


# ── A 量得出來的 ────────────────────────────────────────────────────
def palette(im, n=8):
    """主色與佔比。用調色盤量化而不是取平均——平均會把紅配綠算成灰，
    那是一個畫面裡根本不存在的顏色。

    getcolors() 回的是 (count, palette_index)，順序容易記反。
    第一版就寫反了變數名（算出來剛好還是對的，但讀的人會被誤導），
    這裡明寫成 count / pidx。"""
    small = im.convert("RGB").resize((160, 200))
    q = small.quantize(colors=n, method=Image.MEDIANCUT)
    pal = q.getpalette()[: n * 3]
    total = small.size[0] * small.size[1]
    out = []
    for count, pidx in sorted(q.getcolors() or [], reverse=True):
        r, g, b = pal[pidx * 3: pidx * 3 + 3]
        _h, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        out.append({
            "hex": "#%02X%02X%02X" % (r, g, b),
            "share": round(count / total, 3),
            "lightness": round(light, 2), "saturation": round(sat, 2),
        })
    return out


def accents(pal, min_sat=0.30, min_share=0.003, light_range=(0.18, 0.88)):
    """重點色：看得出顏色、面積不必大的那幾個。

    〔為什麼要另外抽〕深色設計量出來的「主色票」會是六個幾乎一樣的黑，
    那對「這個範本長什麼樣」毫無資訊量——真正認得出品牌的是那一點橘、
    那一點黃。佔比門檻刻意設得很低（0.3%）：重點色本來就只佔一小塊，
    用面積排序會把它們全部濾掉。

    〔亮度也要卡，這是第一版的錯〕只用彩度篩會撈回一堆深褐色：
    HLS 的 saturation 在極暗與極亮時會騙人——L=0.05 的顏色算出來 S 可以到 0.5，
    但人眼看到的就是黑。實測第一版拿 Lava 自家貼文跑，四個「重點色」
    全是 #1C120A 這種黑褐，那不是重點色，那就是黑。"""
    lo, hi = light_range
    hits = [c for c in pal
            if c["saturation"] >= min_sat and c["share"] >= min_share
            and lo <= c["lightness"] <= hi]
    return sorted(hits, key=lambda c: -(c["saturation"] * c["share"] ** 0.25))[:4]


def band_brightness(im):
    """上／中／下三段的平均亮度。這一組數字認得出常見的版型：
    上暗下亮＝標題壓在暗部、內文在亮底；三段接近＝滿版照片直接壓字。"""
    g = im.convert("L")
    w, h = g.size
    out = {}
    for name, (a, b) in (("top", (0, .33)), ("mid", (.33, .66)), ("bottom", (.66, 1.0))):
        crop = g.crop((0, int(h * a), w, int(h * b)))
        out[name] = round(ImageStat.Stat(crop).mean[0] / 255, 3)
    return out


def text_grid(im):
    """哪幾格有「像文字」的東西。

    判法：邊緣密度。文字是高頻的細筆畫，邊緣強度遠高於平滑的背景或散景。
    這招分不出「文字」與「複雜紋理」——所以回傳的名稱叫 busy 不叫 text，
    不要在下游把它當成「這裡一定有字」。
    """
    g = im.convert("L")
    g.thumbnail((360, 450))
    e = g.filter(ImageFilter.FIND_EDGES)
    w, h = e.size
    cells, vals = [], []
    for gy in range(GRID_Y):
        row = []
        for gx in range(GRID_X):
            c = e.crop((int(w * gx / GRID_X), int(h * gy / GRID_Y),
                        int(w * (gx + 1) / GRID_X), int(h * (gy + 1) / GRID_Y)))
            v = ImageStat.Stat(c).stddev[0]
            row.append(round(v, 1)); vals.append(v)
        cells.append(row)
    if not vals:
        return {"grid": cells, "busy_rows": [], "whitespace": None}
    hi = max(vals)
    busy_rows = [i for i, row in enumerate(cells) if hi and max(row) > hi * 0.55]
    quiet = sum(1 for v in vals if hi and v < hi * 0.25)
    return {"grid": cells, "busy_rows": busy_rows,
            "whitespace": round(quiet / len(vals), 2)}


def contrast_of(im):
    """整張的明暗對比（標準差）。低＝灰濛濛，高＝黑白分明。"""
    g = im.convert("L")
    g.thumbnail((320, 400))
    return round(ImageStat.Stat(g).stddev[0] / 255, 3)


def measure(path):
    im = Image.open(path)
    w, h = im.size
    pal = palette(im, n=12)
    acc = accents(pal)
    bands = band_brightness(im)
    tg = text_grid(im)
    return {
        "file": os.path.basename(path),
        "size": "%dx%d" % (w, h),
        "aspect": round(w / h, 3),
        "palette": pal[:6],
        "dominant": pal[0]["hex"] if pal else None,
        "accents": [c["hex"] for c in acc],
        "bands": bands,
        "band_pattern": _band_pattern(bands),
        "busy_rows": tg["busy_rows"],
        "text_zone": _zone_name(tg["busy_rows"]),
        "whitespace": tg["whitespace"],
        "contrast": contrast_of(im),
    }


def _band_pattern(b):
    """把三個亮度數字翻成一句人看得懂的話。這是給人讀的標籤，
    下游要做判斷請用原始數字，不要 parse 這句話。"""
    t, m, bo = b["top"], b["mid"], b["bottom"]
    spread = max(t, m, bo) - min(t, m, bo)
    if spread < 0.08:
        return "三段亮度接近（多半是滿版照片直接壓字）"
    if t < m < bo:
        return "上暗下亮"
    if t > m > bo:
        return "上亮下暗"
    if m < t and m < bo:
        return "中段最暗（常見於中間放照片、上下留白）"
    return "亮度不規則"


def _zone_name(rows):
    if not rows:
        return "沒有明顯的密集區"
    if set(rows) <= {0, 1}:
        return "上半部"
    if set(rows) <= {3, 4}:
        return "下半部"
    if set(rows) <= {1, 2, 3}:
        return "中段"
    return "分散在多處"


# ── B 量不出來的：把題目整理好交出去 ────────────────────────────────
UNMEASURABLE = [
    ("字型", "這是哪一款字體？粗細與字寬如何？中英文是否混排、混排時怎麼配？"),
    ("圖素", "底圖是攝影、插畫、3D 還是純色塊？有沒有反覆出現的圖形元件（線框、圓點、色帶）？"),
    ("呈現風格", "整體給人的感覺（雜誌感／手作感／科技感／復古），以及它靠什麼手法達成？"),
    ("內文撰寫方式", "第一句用什麼句型開場？句子長短的節奏？稱謂是你／我們／第三人稱？"),
]


def brief(measured):
    """交給視覺模型或人的題目卡。附上量到的數字當背景，
    問題只問量不出來的部分——把已經知道的事再問一次是浪費。"""
    return {
        "measured": measured,
        "ask": [{"dimension": d, "question": q} for d, q in UNMEASURABLE],
        "note": "上面 measured 的數字是程式量出來的，可以直接信。"
                "ask 裡的問題要靠視覺模型或人回答，回答後填回同一筆記錄的 style 欄位。",
    }


def summarize(rows):
    """一整篇（多張）的共同特徵。範本是整篇的性格，不是單張的。"""
    if not rows:
        return {}
    def avg(k):
        vs = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        return round(sum(vs) / len(vs), 3) if vs else None
    zones = {}
    for r in rows:
        zones[r["text_zone"]] = zones.get(r["text_zone"], 0) + 1
    pats = {}
    for r in rows:
        pats[r["band_pattern"]] = pats.get(r["band_pattern"], 0) + 1
    # 全篇色票：把每張的主色收集起來，出現最多次的排前面
    hexes, accs = {}, {}
    for r in rows:
        for c in r["palette"][:3]:
            hexes[c["hex"]] = hexes.get(c["hex"], 0) + c["share"]
        for hx in r.get("accents") or []:
            accs[hx] = accs.get(hx, 0) + 1
    return {
        "slides": len(rows),
        "aspect": avg("aspect"),
        "avg_contrast": avg("contrast"),
        "avg_whitespace": avg("whitespace"),
        "text_zone_dominant": max(zones, key=zones.get) if zones else None,
        "text_zone_spread": zones,
        "band_pattern_dominant": max(pats, key=pats.get) if pats else None,
        "palette_top": [h for h, _ in sorted(hexes.items(), key=lambda x: -x[1])[:5]],
        "accents_top": [h for h, _ in sorted(accs.items(), key=lambda x: -x[1])[:4]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="")
    ap.add_argument("--dir", default="")
    ap.add_argument("--save", default="", help="存成候選範本的名稱")
    ap.add_argument("--json", action="store_true", help="只輸出 JSON")
    a = ap.parse_args()

    paths = []
    if a.image:
        paths = [a.image]
    elif a.dir:
        for ext in ("jpg", "jpeg", "png", "webp"):
            paths += glob.glob(os.path.join(a.dir, "*." + ext))
        paths.sort()
    if not paths:
        sys.stderr.write("要給 --image 或 --dir（而且裡面要有圖）\n")
        return 2

    rows = []
    for p in paths:
        try:
            rows.append(measure(p))
        except Exception as e:
            sys.stderr.write("  ✗ %s：%s\n" % (os.path.basename(p), e))
    if not rows:
        sys.stderr.write("沒有一張讀得起來\n")
        return 1

    summ = summarize(rows)
    out = {"source": a.image or a.dir, "summary": summ,
           "slides": rows, "brief": brief(summ)}

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print("拆解 %s（%d 張）\n" % (out["source"], len(rows)))
        print("  長寬比      %s" % summ["aspect"])
        print("  主色票      %s" % "、".join(summ["palette_top"]))
        print("  重點色      %s" % ("、".join(summ["accents_top"]) or "（沒有明顯的彩度重點）"))
        print("  明暗結構    %s" % summ["band_pattern_dominant"])
        print("  文字集中在  %s   %s" % (summ["text_zone_dominant"], summ["text_zone_spread"]))
        print("  留白比例    %s" % summ["avg_whitespace"])
        print("  明暗對比    %s" % summ["avg_contrast"])
        print("\n  量不出來、要人或視覺模型回答的：")
        for q in out["brief"]["ask"]:
            print("    · %s：%s" % (q["dimension"], q["question"]))

    if a.save:
        doc = SC.load("templates.json")
        tid = "TPL-" + "".join(ch for ch in a.save if ch.isalnum() or ch in "-_")[:24]
        existing = next((t for t in doc.get("templates", []) if t.get("id") == tid), None)
        rec = {
            "id": tid, "hook_type": a.save, "type": "post", "status": "candidate",
            "skeleton": "（拆解自參考圖，敘事結構待填）",
            "why_it_works": "（待填）", "fit_for_lava": "（待填）",
            "used_by": [], "evidence": out["source"],
            # 視覺拆解結果。數字是量出來的，style 那一欄是留給人／視覺模型填的。
            "visual": summ,
            "style": {d: "" for d, _ in UNMEASURABLE},
            "decomposed_at": SC._now_iso(),
        }
        if existing:
            existing.update({k: v for k, v in rec.items() if k not in ("style",)})
            existing.setdefault("style", rec["style"])
        else:
            doc.setdefault("templates", []).append(rec)
        SC.save("templates.json", doc)
        print("\n✓ 已存成候選範本 %s（狀態 candidate，要你在規則本補完 style 與骨架才會被撰稿挑用）" % tid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
