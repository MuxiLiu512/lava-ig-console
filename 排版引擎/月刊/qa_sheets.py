"""接縫圖與跨頁並排圖：出完稿之後給圖像識別 QA 用。
用法：python3 qa_sheets.py [輸出資料夾]（預設 九月號/qa/）"""
import os, sys
from PIL import Image, ImageDraw
ROOT = "/Users/mimo/Claude/貼文製造機器人/九月號/成品"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(ROOT), "qa")
NAMES = ["01_cover","02_milestone","03_big","04_more","05_new","06_farewell","07_event","08_end"]

def seam(v, a, b, y0, y1, path, w=300):
    A = Image.open(os.path.join(ROOT, v, a + ".png")); B = Image.open(os.path.join(ROOT, v, b + ".png"))
    im = Image.new("RGB", (w * 2 + 4, y1 - y0), (255, 0, 0))
    im.paste(A.crop((1080 - w, y0, 1080, y1)), (0, 0)); im.paste(B.crop((0, y0, w, y1)), (w + 4, 0))
    im.save(path)

def pair_sheet(v, a, b, path):
    """兩張卡真的並排（中間不留縫），看跨頁是否連續。縮到 50%。"""
    A = Image.open(os.path.join(ROOT, v, a + ".png")); B = Image.open(os.path.join(ROOT, v, b + ".png"))
    im = Image.new("RGB", (2160, 1350)); im.paste(A, (0, 0)); im.paste(B, (1080, 0))
    im.resize((1080, 675), Image.LANCZOS).save(path)

for v in ("B2", "C2"):
    for a, b in [("02_milestone","03_big"),("04_more","05_new"),("06_farewell","07_event")]:
        pair_sheet(v, a, b, os.path.join(OUT, "pair_%s_%s.png" % (v, a[:2])))
# B2 接縫：字帶區 y 420–830
for a, b in [("02_milestone","03_big"),("05_new","06_farewell"),("07_event","08_end")]:
    seam("B2", a, b, 400, 840, os.path.join(OUT, "seam_B2_%s.png" % a[:2]))
print("ok")
