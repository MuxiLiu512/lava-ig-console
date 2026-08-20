#!/usr/bin/env python3
# render_and_archive.py — 套版成成品 → 本機存檔 + 歸檔 Google Drive（寫掛載點自動上雲）。
# 用法: python3 render_and_archive.py <文案.json> <底圖資料夾> <post-id>
# 例:   python3 render_and_archive.py "文案/已讀不回的心理學-v2.json" "底圖/…v5/…" 20260712-已讀不回-v5
import sys, os, shutil, subprocess

ENGINE = os.path.dirname(os.path.abspath(__file__))
LOCAL_OUT = os.path.join(ENGINE, "成品")
DRIVE_OUT = ("/Users/mimo/Library/CloudStorage/GoogleDrive-service@lava.tw/My Drive/"
             "Lava INC. Assets/02_Marketing/98_Lava-IG-AI產文系統/成品")


# 產品介紹走另一套版型（設計卡片，不是滿版劇照＋疊字）。
# 分流放在這裡而不是 sync_console：下游的成品收集、Drive 歸檔、發佈全部不用改。
PRODUCT_TPL = "tpl-product-intro-carousel"
PRODUCT_ENGINE = next((p for p in [
    os.path.abspath(os.path.join(ENGINE, "..", "scripts", "render_product.py")),          # 引擎在 repo 內
    os.path.abspath(os.path.join(ENGINE, "..", "lava-ig-console", "scripts", "render_product.py")),  # 引擎在 repo 外（舊）
] if os.path.exists(p)), "")


def _engine_for(js):
    """依草稿的 template_id 決定用哪支引擎。找不到產品引擎就退回一般版型並出聲，
    不要靜默用錯版型渲染出去（那正是 2026-08-17 被退件的原因）。"""
    try:
        import json
        with open(js, encoding="utf-8") as f:
            tpl = (json.load(f).get("template_id") or "")
    except Exception:
        tpl = ""
    if tpl == PRODUCT_TPL:
        if os.path.exists(PRODUCT_ENGINE):
            print("→ 產品介紹版型（render_product）")
            return PRODUCT_ENGINE
        print("！草稿是產品介紹但找不到 render_product.py，退回一般版型")
    return os.path.join(ENGINE, "render_post_v5.py")


def main(js, bg, pid):
    local = os.path.join(LOCAL_OUT, pid)
    os.makedirs(local, exist_ok=True)
    r = subprocess.run([sys.executable, _engine_for(js), js, bg, local])
    if r.returncode != 0:
        sys.exit("✗ 套版失敗")
    finals = sorted(f for f in os.listdir(local) if f.startswith("final-"))
    print("✓ 本機成品：排版引擎/成品/%s（%d 張，1950×2438 = 4:5）" % (pid, len(finals)))
    if os.path.isdir(os.path.dirname(DRIVE_OUT)):
        drive = os.path.join(DRIVE_OUT, pid)
        os.makedirs(drive, exist_ok=True)
        for f in finals:
            shutil.copy2(os.path.join(local, f), os.path.join(drive, f))
        print("✓ Drive 歸檔：產文系統/成品/%s（寫入掛載點，自動同步上雲）" % pid)
    else:
        print("！找不到 Drive 掛載點，僅存本機（Drive 未掛載時正常）")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("用法: python3 render_and_archive.py <文案.json> <底圖資料夾> <post-id>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
