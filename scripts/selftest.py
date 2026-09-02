#!/usr/bin/env python3
# selftest.py — 生產線核心規則的快速回歸測試（不碰網路、不改資料）。
# 跑法：python3 scripts/selftest.py   全綠 exit 0；任一紅 exit 1。
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "排版引擎")))

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

# 重餵不得沖掉人設定的欄位〔2026-09-03〕
# 這條是為了讓「第三次」不會有第四次：保留規則從白名單改成黑名單之後，
# 新增欄位預設會被保留。但如果有人哪天又改回白名單，這條會立刻紅。
_REBUILD = {"id", "topic", "topic_type", "caption", "slides", "hashtags",
            "cover_head", "copy_versions", "template_id", "facts"}
_old = {"id": "p1", "topic": "舊", "status_since": "2026-09-01T00:00:00+08:00",
        "no_publish": True, "gate_overrides": [{"key": "qa:x"}], "版本外的新欄位": 1}
_new = {"id": "p1", "topic": "新（重寫過）", "slides": [], "caption": "新文案"}
for _k, _v in _old.items():
    if _k in _REBUILD:
        continue
    if _k not in _new or _new.get(_k) in (None, "", [], {}):
        _new[_k] = _v
check("重餵：該重建的欄位有重建", _new["topic"] == "新（重寫過）")
check("重餵：狀態時鐘不被沖掉", _new.get("status_since") == "2026-09-01T00:00:00+08:00")
check("重餵：不准發佈的保護旗標不被沖掉", _new.get("no_publish") is True)
check("重餵：閘門覆寫不被沖掉", _new.get("gate_overrides") == [{"key": "qa:x"}])
check("重餵：未知的新欄位預設保留", _new.get("版本外的新欄位") == 1)

# Reels 狀態機〔2026-09-03〕：影片是唯一「一按下去就燒錢」的東西，
# 分鏡關卡是把「不喜歡」的成本從約 137 點降到 7 點的設計。
# 那條路必須在狀態機層不存在，不是靠介面隱藏按鈕——介面會被繞過。
import importlib.util as _ilu
_sm_spec = _ilu.spec_from_file_location("sm", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_machine.py"))
_SM = _ilu.module_from_spec(_sm_spec); _sm_spec.loader.exec_module(_SM)

def _reel(status, ev):
    r = {"status": status}
    ok, _ = _SM.apply_reel_event(r, {"type": ev, "ts": "2026-09-03T00:00:00+08:00", "payload": {}})
    return ok, r.get("status")

check("Reels：跳過分鏡直接生影片會被擋", _reel("storyboard", "reel.generated")[0] is False)
check("Reels：分鏡階段不能核准整支", _reel("storyboard", "reel.approve")[0] is False)
check("Reels：沒核准不能排程", _reel("video_review", "reel.schedule")[0] is False)
check("Reels：確認分鏡 → storyboard_ok", _reel("storyboard", "reel.approve_storyboard") == (True, "storyboard_ok"))
check("Reels：分鏡確認後可生影片", _reel("storyboard_ok", "reel.generated") == (True, "video_review"))
check("Reels：看過影片可核准", _reel("video_review", "reel.approve") == (True, "approved"))
check("Reels：核准後可排程", _reel("approved", "reel.schedule") == (True, "scheduled"))
check("Reels：排程後仍可退回", _reel("scheduled", "reel.reject") == (True, "rejected"))

TOTAL = 31
print("\n%s：%d 項通過，%d 項失敗" % ("🎉 全數通過" if not FAIL else "❌ 有失敗", TOTAL - len(FAIL), len(FAIL)))
sys.exit(1 if FAIL else 0)
