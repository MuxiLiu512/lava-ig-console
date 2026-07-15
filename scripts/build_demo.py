#!/usr/bin/env python3
# build_demo.py — 用兩篇既有成品（已讀不回 v5、母胎單身）造 Phase 1 驗收假資料。
# 產出 assets/<post-id>/ 縮圖與 data/posts.json。可重複執行（idempotent）。
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
from _thumbs import make_thumb

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENGINE = os.path.abspath(os.path.join(REPO, "..", "排版引擎"))
ASSETS = os.path.join(REPO, "assets")

CID = ["a", "b", "c", "d"]


def rel(p):
    return os.path.relpath(p, REPO).replace(os.sep, "/")


def thumb(src_abs, post_id, name):
    out = make_thumb(src_abs, os.path.join(ASSETS, post_id, name))
    return "assets/" + post_id + "/" + os.path.basename(out)


def final_thumb(src_abs, post_id, n):
    out = make_thumb(src_abs, os.path.join(ASSETS, post_id, "final", "slide-%d" % n))
    return "assets/" + post_id + "/final/" + os.path.basename(out)


# ── 兩篇貼文的來源對照 ─────────────────────────────────────────────
POSTS = []

# Post 1：已讀不回的心理學 v5 — 生成圖為主，多候選，slide3 為劇照(.jpg)
p1_id = "20260712-已讀不回的心理學-v5"
b_v5 = ENGINE + "/底圖/已讀不回的心理學 v5/drive-download-20260710T141224Z-2-001"
b_v2 = ENGINE + "/底圖/已讀不回的心理學 v2/drive-download-20260709T174735Z-2-001"
b_v1 = ENGINE + "/底圖/已讀不回的心理學/drive-download-20260709T103745Z-3-001"
fin1 = ENGINE + "/成品/0712已讀不回的心理學"
# 每 slide 候選：(檔案, kind)
p1_slides = {
    1: [(b_v5 + "/slide-1.png", "generated"), (b_v2 + "/slide-1.png", "generated"), (b_v1 + "/slide-1.png", "generated")],
    2: [(b_v5 + "/slide-2(1).png", "generated"), (b_v2 + "/slide-2.png", "generated")],
    3: [(b_v5 + "/slide-3.jpg", "still"), (b_v2 + "/slide-3.png", "generated")],
    4: [(b_v5 + "/slide-4.png", "generated"), (b_v2 + "/slide-4.png", "generated")],
    5: [(b_v5 + "/slide-5.png", "generated"), (b_v2 + "/slide-5.png", "generated")],
    6: [],  # CTA 公版
}
p1_roles = {1: "Hook", 2: "共感場景", 3: "知識解釋", 4: "知識解釋", 5: "品牌立場", 6: "CTA"}
p1_caption = (
    "比起壞消息，你是不是也更厭惡「已讀不回」？\n\n"
    "那種懸在半空的感覺其實有名字——1920 年代心理學家 Bluma Zeigarnik 發現，"
    "大腦記得「沒做完的事」遠比記得「做完的事」清楚。一則已讀沒回的訊息，"
    "在腦裡就是一張還沒結帳的單子，持續佔用你的注意力。\n\n"
    "這跟你的魅力沒有關係，是聊天室這個設計本身讓每段關係都懸在半空。\n"
    "所以我們決定把聊天室拿掉——配對後回答三個價值觀問題，確認意願，直接約見面。\n\n"
    "出現就好，其他交給我們。\n\n"
    "#已讀不回 #交友軟體 #蔡格尼效應 #心理學 #Lava交友 #不聊天的交友軟體 #線下約會 #約會焦慮"
)

# Post 2：母胎單身 — 全劇照(still)，含出處
# 底圖資料夾名含「」等全形符號，macOS 檔名正規化(NFD)與字面 NFC 不符，改用前綴掃描定位。
p2_id = "20260711-母胎單身其實比你更懂得選擇伴侶"
def _find_dir(parent, prefix):
    for d in os.listdir(parent):
        if d.startswith(prefix):
            return os.path.join(parent, d)
    raise FileNotFoundError(prefix + " under " + parent)
b2 = _find_dir(ENGINE + "/底圖", "母胎單身")
fin2 = ENGINE + "/成品/母胎單身的人其實比你更懂得選擇伴侶"
p2_slides = {
    1: [(b2 + "/slide1-TheOffice-2.jpg", "still")],
    2: [(b2 + "/slide2-NeverHaveIEver-1.jpg", "still")],
    3: [(b2 + "/slide3-BrooklynNineNine-2.jpg", "still")],
    4: [(b2 + "/slide4-Suits-3.jpg", "still")],
    5: [(b2 + "/slide5-Friends-2.jpg", "still")],
    6: [],
}
p2_roles = {1: "Hook", 2: "共感場景", 3: "知識解釋", 4: "知識解釋", 5: "品牌立場", 6: "CTA"}
p2_srcnote = {1: "The Office", 2: "Never Have I Ever", 3: "Brooklyn Nine-Nine", 4: "Suits", 5: "Friends"}
p2_caption = (
    "母胎單身，其實比你更懂得「選擇」伴侶？\n\n"
    "沒談過戀愛，常被當成缺點。但從沒在關係裡將就過的人，往往對「自己要什麼」"
    "有更清楚的座標——他們不是沒有選擇，而是還沒遇到值得的相遇。\n\n"
    "見面是一場機率遊戲，你需要的是更多高品質的偶然接觸面積。\n"
    "Lava 幫你把「遇到」這件事變簡單：滑動、配對、碰面。\n\n"
    "出現就好，其他交給我們。\n\n"
    "#母胎單身 #單身 #交友軟體 #Lava交友 #線下約會 #擇偶 #感情 #台灣約會"
)


def build_post(post_id, topic, version, slides_src, roles, caption, srcnote=None, clickup="TASK-DEMO"):
    slides = []
    for n in sorted(slides_src.keys()):
        cands = []
        for i, (src, kind) in enumerate(slides_src[n]):
            if not os.path.exists(src):
                print("  ! 缺檔:", src)
                continue
            cid = CID[i]
            s = thumb(src, post_id, "slide-%d%s" % (n, cid))
            c = {"cid": cid, "src": s, "kind": kind}
            if srcnote and kind == "still" and n in srcnote:
                c["source_label"] = srcnote[n]
            cands.append(c)
        # final render
        fin_src = os.path.join(FINMAP[post_id], "final-%02d.png" % n)
        final_src = final_thumb(fin_src, post_id, n) if os.path.exists(fin_src) else None
        slide = {"n": n, "role": roles.get(n, ""), "candidates": cands, "final_src": final_src}
        # 預設選：第一個候選；CTA 無候選
        if cands:
            slide["default_cid"] = cands[0]["cid"]
        slides.append(slide)
    return {
        "id": post_id, "topic": topic, "version": version,
        "status": "awaiting_review", "clickup_task_id": clickup,
        "created_at": None, "caption": caption, "slides": slides,
    }


FINMAP = {p1_id: fin1, p2_id: fin2}

POSTS.append(build_post(p1_id, "已讀不回的心理學", 5, p1_slides, p1_roles, p1_caption, clickup="86ac-demo-01"))
POSTS.append(build_post(p2_id, "母胎單身的人，其實比你更懂得選擇伴侶", 1, p2_slides, p2_roles, p2_caption, srcnote=p2_srcnote, clickup="86ac-demo-02"))

out = {"generated_at": "2026-07-15T18:00:00+08:00", "posts": POSTS}
with open(os.path.join(REPO, "data", "posts.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("✓ posts.json 完成，%d 篇" % len(POSTS))
for p in POSTS:
    print("  -", p["id"], "slides:", len(p["slides"]),
          "candidates:", sum(len(s["candidates"]) for s in p["slides"]))
