#!/usr/bin/env python3
"""產品介紹貼文的照片候選挑選器。

為什麼不走 forage_shots：
  forager 是去網路上抓別人的圖來講知識型主題。產品介紹講的是自己的功能，
  拿別人的照片是錯的（Jesse 2026-08-17 退件）。素材改取自家品牌照片庫。

為什麼不是 App 截圖：
  Jesse 的參考稿裡卡片放的是真人照片，產品感由引擎畫的設計元件承擔
  （紅框、星標、模擬通知卡）。App 截圖是 375px @1x，縮進卡片會看不清。詳見 self-check F2。

策展仍然是人做的：本工具只負責「把合格的候選放進底圖資料夾」，
挑哪一張由 Jesse 在操控室決定（WF14 視覺策展員恢復連線後可再自動排序）。

用法：
  python3 scripts/pick_product_photos.py <draft.json> <底圖輸出資料夾> [--per-slide 3]
"""
import os, sys, json, glob, argparse, hashlib, importlib.util
from PIL import Image, ImageStat

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))

_spec = importlib.util.spec_from_file_location(
    "rprod", os.path.join(REPO, "scripts", "render_product.py"))
RP = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(RP)

LIB = ("/Users/mimo/Library/CloudStorage/GoogleDrive-service@lava.tw/My Drive/"
       "Lava INC. Assets/02_Marketing/02_行銷素材庫")
# 順序即優先序：宣傳照是為了「單一主體、乾淨背景」拍的，適合當卡片主體；
# 現場攝影是活動紀錄，人多背景雜，縮成小卡看不出在幹嘛，排後面。
SOURCES = ["2025_初版Lava產品宣傳照_帥哥美女圖", "202602_老派Lava現場攝影照"]
NEEDS_PHOTO = ("hero", "notify")     # 只有這兩種構圖有媒體版位
MIN_EDGE = 1200                      # 低於這個放進卡片就要放大，直接不收
WORK_EDGE = 2200                     # 候選存檔長邊（原檔 8448px 太大，操控室載入會卡）


def _usable(path):
    """機械篩：尺寸夠、不是近乎純色、不過暗。判斷「好不好看」不在這裡做。"""
    try:
        im = Image.open(path)
        if min(im.size) < MIN_EDGE:
            return None
        im = im.convert("RGB")
        sm = im.resize((64, 64))
        st = ImageStat.Stat(sm)
        if sum(st.stddev) / 3 < 18:          # 近乎純色／糊掉
            return None
        if sum(st.mean) / 3 < 28:            # 整張過暗，疊在深底上看不出東西
            return None
        return im
    except Exception:
        return None


def _pool():
    out = []
    for d in SOURCES:
        fs = sorted(f for f in glob.glob(os.path.join(LIB, d, "**", "*"), recursive=True)
                    if f.lower().endswith((".jpg", ".jpeg", ".png")))
        out.append(fs)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft"); ap.add_argument("outdir")
    ap.add_argument("--per-slide", type=int, default=3)
    a = ap.parse_args()

    with open(a.draft, encoding="utf-8") as f:
        doc = json.load(f)
    slides = doc.get("slides", [])
    total = len(slides)
    pools = _pool()
    if not any(pools):
        sys.exit("✗ 找不到行銷素材庫（Drive 未掛載？）：%s" % LIB)
    os.makedirs(a.outdir, exist_ok=True)

    used = set()
    for i, s in enumerate(slides, 1):
        idx = int(s.get("index") or i)
        lay = RP.infer_layout(s, idx, total)
        if lay not in NEEDS_PHOTO:
            continue
        # 起點由 draft 標題＋張次決定：同一篇每張起點不同（不會三張都同一批），
        # 但同一篇重跑結果一致（可重現，方便比對）。
        seed = int(hashlib.md5(("%s|%d" % (doc.get("title", ""), idx)).encode()).hexdigest()[:8], 16)
        got = 0
        for pool in pools:                    # 先吃宣傳照，不夠才用現場攝影
            if not pool:
                continue
            n = len(pool)
            for k in range(n):
                if got >= a.per_slide:
                    break
                path = pool[(seed + k * 7) % n]
                if path in used:
                    continue
                im = _usable(path)
                if im is None:
                    continue
                sc = WORK_EDGE / max(im.size)
                if sc < 1:
                    im = im.resize((int(im.width*sc), int(im.height*sc)), Image.LANCZOS)
                # 別寫死 "abc"：--per-slide 只要大於 3 就 IndexError（2026-08-23 選五官清楚
                # 的照片、想一次看 14 張候選時炸掉）。候選數上限應該由參數決定，不是由字串長度。
                cid = "abcdefghijklmnopqrstuvwxyz"[got]
                out = os.path.join(a.outdir, "slide-%d%s.png" % (idx, cid))
                im.save(out)
                used.add(path); got += 1
                print("  ✓ slide-%d%s ← %s (%dx%d)" % (idx, cid, os.path.basename(path)[:34],
                                                       im.width, im.height))
            if got >= a.per_slide:
                break
        if got == 0:
            print("  ✗ slide-%d 沒有合格候選" % idx)
    print("完成 → %s" % a.outdir)


if __name__ == "__main__":
    main()
