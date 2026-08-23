#!/usr/bin/env python3
# verify_pipeline.py — 操控室品質驗證 harness（以使用者可見狀態為準，不是以工作流跑成功為準）。
# 檢查每篇待審貼文：候選數、來源組成（劇照/Wiki/CC/書封/生成）、破圖、無標來源劇照。
# exit code：0=全綠，1=有紅燈。
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(__file__))
from sync_console import load, REPO, _flat_image


def _shot_broken(path):
    """截圖破圖判定：全黑/全白（抓取失敗的典型形態）。"""
    try:
        from PIL import Image, ImageStat
        st = ImageStat.Stat(Image.open(path).convert("L").resize((48, 48)))
        return (st.mean[0] < 12 or st.mean[0] > 243) and st.stddev[0] < 10
    except Exception:
        return True

def main():
    posts = load("posts.json").get("posts", [])
    audit = [p for p in posts if p.get("status") in ("awaiting_review", "approved")]
    bad, skipped = 0, 0
    print("%-30s %4s │ %s" % ("貼文", "候選", "來源組成（劇照/Wiki/CC/書封/生成）＋紅燈"))
    print("─" * 86)
    for p in audit:
        # 外部設計稿（Jesse 或設計端直接交成品圖）沒有 forager 候選，
        # 套抓取檢查會永遠亮「候選過少／只有生成圖」兩盞假紅燈（2026-08-23 superlike 那篇抓到）。
        # 這裡不是放行，是宣告「抓取檢查對這篇不適用」——品質由交稿端負責。
        if p.get("asset_origin"):
            print("%-30s %4s │ 外部設計稿，抓取檢查不適用" % (p["id"][:30], "—"))
            skipped += 1
            continue
        kinds = collections.Counter()
        flats, nolabel, lowq = 0, 0, 0
        total = 0
        for s in p.get("slides", []):
            for c in s.get("candidates", []):
                total += 1
                if c.get("low_q"):
                    lowq += 1
                sk = c.get("source_kind")
                if sk:
                    kinds[sk] += 1
                elif c.get("kind") == "still":
                    kinds["劇照"] += 1
                    if not c.get("source_label"):
                        nolabel += 1
                else:
                    kinds["生成"] += 1
                src = os.path.join(REPO, c.get("src", ""))
                if c.get("source_kind") == "SHOT" or "-SHOT-" in src:
                    # 策展截圖：不做近純色判定（文章白底合法），但全黑/全白＝破圖（v2.1 backstop）
                    if os.path.exists(src) and _shot_broken(src):
                        flats += 1
                    continue
                if c.get("source_kind") == "DESIGN" or "-DESIGN-" in src:
                    continue   # 設計底（漸層）天然近純色，不算破圖
                if os.path.exists(src) and _flat_image(src):
                    flats += 1
        mix = " ".join("%s×%d" % (k, v) for k, v in sorted(kinds.items()))
        flags = []
        if total < 8:
            flags.append("⚠候選過少")
        if flats:
            flags.append("🔴破圖×%d" % flats)
        if nolabel:
            flags.append("⚠劇照無出處×%d" % nolabel)
        if lowq:
            flags.append("⚠低畫質×%d" % lowq)
        if not (kinds.get("SHOT") or kinds.get("WM") or kinds.get("OV") or kinds.get("OL")) and kinds.get("劇照", 0) == 0:
            flags.append("⚠只有生成圖")
        if flats or total < 8:
            bad += 1
        print("%-30s %4d │ %s %s" % (p["id"][:30], total, mix, " ".join(flags)))
    print("─" * 86)
    n = len(audit) - skipped
    print("結論：%d/%d 篇綠燈%s" % (n - bad, n, "（外部設計稿 %d 篇不計）" % skipped if skipped else ""))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
