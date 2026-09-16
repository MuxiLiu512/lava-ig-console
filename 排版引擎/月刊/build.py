#!/usr/bin/env python3
"""九月號卡片產線：HTML → 精準 1080x1350 PNG。

為什麼是 HTML 不是 Pillow〔2026-09-16〕：
  這一期要的是雜誌版面——細分隔線、字距、多欄網格、文字壓邊。
  那些在 Pillow 裡每一樣都要手算座標，在 CSS 裡是一行。
  而且三個藝術指導要並行迭代，改 CSS 比改繪圖座標快一個數量級。

為什麼是無頭 Chrome 不是瀏覽器面板：
  面板的截圖會被縮放，拿不到精準像素。無頭 Chrome 加
  --force-device-scale-factor=1 --window-size=1080,1350 出來就是 1080x1350，
  已實測確認。IG 的 4:5 規格容不下「差不多」。

字型：HarmonyOS Sans TC，已安裝在 ~/Library/Fonts。
  只有 Thin(100) / Regular(400) / Medium(500) 三個字重——
  任何「粗中文標題」只能靠字級與字距做出重量，不能指望 Bold。

用法：
  python3 build.py --dir A            # 只出 A 版
  python3 build.py --dir A --card 3   # 只出 A 版第 3 張（迭代用）
  python3 build.py --all              # 三版全出
"""
import os, sys, glob, argparse, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1080, 1350


def render(html_path, png_path, w=W, h=H):
    """一個 HTML 檔 → 一張精準尺寸的 PNG。

    --virtual-time-budget 給字型與圖片載入的時間。設太短會拍到還沒套用字型的
    系統預設字，而那個失敗是靜默的：圖出得來，只是字長得不對。
    """
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    r = subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1", "--window-size=%d,%d" % (w, h),
         "--virtual-time-budget=6000", "--screenshot=" + png_path,
         "file://" + os.path.abspath(html_path)],
        capture_output=True, timeout=120)
    if not os.path.exists(png_path):
        return False, (r.stderr or b"").decode("utf-8", "ignore")[-300:]
    try:
        from PIL import Image
        size = Image.open(png_path).size
        if size != (w, h):
            return False, "尺寸不對：%s（要 %dx%d）" % (size, w, h)
    except Exception as e:
        return False, "讀不回來：%s" % e
    return True, None


def check(png_path):
    """出圖之後的自我檢查。三條，每一條都對應一種「圖出得來但其實壞了」。"""
    from PIL import Image, ImageStat
    im = Image.open(png_path).convert("RGB")
    st = ImageStat.Stat(im.resize((64, 80)))
    problems = []
    # 1 整張近純色＝CSS 沒套上或內容沒渲染出來
    if max(st.stddev) < 6:
        problems.append("整張近純色，內容可能沒渲染")
    # 2 全黑或全白＝背景色吃掉了文字
    mean = sum(st.mean) / 3
    if mean < 6 or mean > 250:
        problems.append("全黑或全白")
    # 3 右下角一整塊空＝內容溢出畫布被裁掉（雜誌版面最常見的失敗）
    w, h = im.size
    corner = ImageStat.Stat(im.crop((int(w * .55), int(h * .82), w, h)).resize((32, 32)))
    if max(corner.stddev) < 3 and max(st.stddev) > 20:
        problems.append("右下角整塊空白，可能有內容溢出被裁掉")
    return problems


def build_one(direction, card_name):
    html = os.path.join(HERE, "html", direction, card_name + ".html")
    png = os.path.join(HERE, "成品", direction, card_name + ".png")
    if not os.path.exists(html):
        return None
    ok, err = render(html, png)
    if not ok:
        print("  ✗ %-22s %s" % (card_name, err))
        return False
    probs = check(png)
    print("  %s %-22s %s" % ("⚠" if probs else "✓", card_name,
                             "；".join(probs) if probs else ""))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="")
    ap.add_argument("--card", default="")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    dirs = ["A", "B", "C"] if a.all else ([a.dir] if a.dir else [])
    if not dirs:
        sys.stderr.write("要給 --dir A|B|C 或 --all\n"); return 2
    if not os.path.exists(CHROME):
        sys.stderr.write("找不到 Chrome：%s\n" % CHROME); return 1

    total, bad = 0, 0
    for d in dirs:
        src = os.path.join(HERE, "html", d)
        if not os.path.isdir(src):
            print("⏭ %s 版還沒有 HTML" % d); continue
        names = sorted(os.path.splitext(os.path.basename(p))[0]
                       for p in glob.glob(os.path.join(src, "*.html")))
        if a.card:
            names = [n for n in names if a.card in n]
        print("\n== %s 版（%d 張）" % (d, len(names)))
        for n in names:
            r = build_one(d, n)
            total += 1
            if r is False:
                bad += 1
    print("\n共 %d 張，失敗 %d 張" % (total, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
