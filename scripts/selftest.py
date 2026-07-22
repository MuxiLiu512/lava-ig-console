#!/usr/bin/env python3
# selftest.py — 生產線核心規則的快速回歸測試（不碰網路、不改資料）。
# 跑法：python3 scripts/selftest.py   全綠 exit 0；任一紅 exit 1。
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "排版引擎")))

FAIL = []


def check(name, cond, note=""):
    print(("✓ " if cond else "✗ ") + name + (("  → " + note) if (note and not cond) else ""))
    if not cond:
        FAIL.append(name)


# 1) 句尾標點省略（含 ——、全半形句點；【】〖〗收尾保留）
from render_post_v5 import strip_trailing_punct as sp  # noqa: E402
check("句號省略", sp("認識了。") == "認識了", sp("認識了。"))
check("破折號省略", sp("提出——") == "提出", sp("提出——"))
check("半形句點省略", sp("1360-1380.") == "1360-1380"[:9], sp("1360-1380."))
check("問句保留？省略", sp("是什麼時候？") == "是什麼時候", sp("是什麼時候？"))
check("括號收尾保留", sp("決定【哪些話能被看見】。") == "決定【哪些話能被看見】", sp("決定【哪些話能被看見】。"))
check("〗前標點剔除", sp("〖剩下的，是你的事。〗") == "〖剩下的，是你的事〗", sp("〖剩下的，是你的事。〗"))
check("多行各自處理", sp("第一行，\n第二行——") == "第一行\n第二行")

# 2) 破圖偵測（近純色=壞；有內容=好）
from sync_console import _flat_image, _latest_copy_edits, _norm_topic, _topic_match  # noqa: E402
from PIL import Image  # noqa: E402
import random  # noqa: E402
tmp = tempfile.mkdtemp()
flat = os.path.join(tmp, "flat.png")
Image.new("RGB", (200, 250), (30, 80, 200)).save(flat)  # 純藍色塊
noisy = os.path.join(tmp, "noisy.png")
im = Image.new("RGB", (64, 64))
im.putdata([(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for _ in range(64 * 64)])
im.save(noisy)
check("純色圖判定為破圖", _flat_image(flat) is True)
check("正常圖不誤判", _flat_image(noisy) is False)
check("讀不到的檔視為破圖", _flat_image(os.path.join(tmp, "nope.png")) is True)

# 3) 文案編輯合併：同欄位取最新
ce = [
    {"post_id": "p1", "ts": "2026-07-17T10:00:00", "edits": [{"n": 1, "field": "heading", "edited": "舊"}]},
    {"post_id": "p1", "ts": "2026-07-17T12:00:00", "edits": [{"n": 1, "field": "heading", "edited": "新"}]},
    {"post_id": "p2", "ts": "2026-07-17T13:00:00", "edits": [{"n": 2, "field": "display_copy", "edited": "別篇"}]},
]
m = _latest_copy_edits("p1", ce)
check("copy_edits 取最新", m.get((1, "heading")) == "新")
check("copy_edits 不跨篇", (2, "display_copy") not in m)

# 4) 主題比對
check("topic 正規化", _norm_topic("20260717-「Pitch Your Friend」正在歐美爆紅-文案初稿.json").startswith("PitchYourFriend"))
check("topic 模糊比對", _topic_match(_norm_topic("Pitch Your Friend 正在歐美爆紅"), "20260717 Pitch Your Friend 底圖"))

# 5) IG 說明欄清洗（去標記/破折號/空白正規化）
from sync_console import _clean_caption  # noqa: E402
check("caption 去標記", _clean_caption("都〖認識彼此〗的【高度重疊】") == "都認識彼此的高度重疊")
check("caption 去破折號", "——" not in _clean_caption("前任介紹的朋友——他們的圈子"))
check("caption 標點後無空白", _clean_caption("像廢話，  但背後有邏輯") == "像廢話，但背後有邏輯")
check("caption 換行接合", _clean_caption("第一行\n第二行") == "第一行第二行")

TOTAL = 18
print("\n%s：%d 項通過，%d 項失敗" % ("🎉 全數通過" if not FAIL else "❌ 有失敗", TOTAL - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
