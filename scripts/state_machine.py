#!/usr/bin/env python3
"""狀態機與事件折疊 — 平台自治後（脫離 ClickUp，2026-08-30 Jesse 定案）的核心。

設計三原則：
  1. 合法狀態變遷只在這一個檔案定義。八個寫者變成「八個提交事件的人＋一個執行變遷的哨兵」。
     「退回之後誰改狀態」這種問題，答案永遠在 TRANSITIONS 表裡，不再散落各腳本。
  2. 事件是 append-only：瀏覽器把每個決定寫成 events/pending/ 底下的一個新檔
     （新檔永不撞 sha，GitHub API 併發寫也不會互相覆蓋——這就是刀2 的核心）。
  3. 折疊冪等：同一批事件重放一次，結果相同。哨兵掛掉重跑不會壞資料。

事件格式（events/pending/<ts>-<rand>.json）：
  {"type": "post.approve" | "post.reject" | "post.schedule" | "idea.approve" | "idea.reject",
   "target": "<post id 或 idea id>", "ts": iso8601, "by": "console",
   "payload": {...}}   # reject: {feedback}; schedule: {publish_at}; approve: {slide_choices, copy_choice, seconds}
"""
import os, json, re

# 貼文狀態機。rejected 是明確狀態——之前「退回」只寫一筆紀錄、狀態不動，
# 稿在資料裡永遠是待審，重整就跑回佇列（Jesse 2026-08-28 錄影）。
POST_TRANSITIONS = {
    ("awaiting_review", "post.approve"): "approved",
    ("awaiting_review", "post.reject"):  "rejected",
    ("approved",        "post.reject"):  "rejected",
    ("approved",        "post.schedule"): "scheduled",
    ("scheduled",       "post.reject"):  "rejected",     # 排程後反悔也要能退
    ("scheduled",       "post.unschedule"): "approved",  # 取消排程：回到等你排時間（UI 規格 §3D）
    ("awaiting_review", "post.schedule"): None,          # 明確非法：沒核准不能排
}

IDEA_DECISIONS = {"idea.approve": "approve", "idea.reject": "reject"}

# Reels 狀態機〔2026-09-03〕。跟貼文同一套骨架，但多一個「分鏡」關卡。
#
# 為什麼要多這一關：影片是這條管線裡唯一「一按下去就燒錢」的東西。
# 口播 9 點/秒、空景 6.5 點/秒，一支 30 秒的混合片約 137 點。分鏡一張才 7 點。
# 先看分鏡再決定要不要生影片，是把「不喜歡」的成本從 137 點降到 7 點。
#
# 所以合法路徑是：
#   storyboard（分鏡出來了）→ 你確認 → storyboard_ok → 生影片 → video_review
#   → 你確認 → approved → 排程 → 已發佈
# 沒有從 storyboard 直接跳 approved 的路。那條路必須不存在，
# 不是靠介面隱藏按鈕——介面會被繞過，狀態機不會。
REEL_TRANSITIONS = {
    ("storyboard",     "reel.approve_storyboard"): "storyboard_ok",
    ("storyboard",     "reel.reject"):             "rejected",
    ("storyboard_ok",  "reel.generated"):          "video_review",
    ("storyboard_ok",  "reel.reject"):             "rejected",
    ("video_review",   "reel.approve"):            "approved",
    ("video_review",   "reel.reject"):             "rejected",
    ("approved",       "reel.schedule"):           "scheduled",
    ("approved",       "reel.reject"):             "rejected",
    ("scheduled",      "reel.unschedule"):         "approved",
    ("scheduled",      "reel.reject"):             "rejected",
    # 明確非法（寫出來是為了讓錯誤訊息說得出原因，不是靜默拒絕）
    ("storyboard",     "reel.approve"):            None,   # 還沒生影片就想核准整支
    ("storyboard",     "reel.generated"):          None,   # 分鏡沒確認就想生影片＝跳過省錢關卡
    ("storyboard_ok",  "reel.approve"):            None,   # 影片還沒出來
    ("video_review",   "reel.schedule"):           None,   # 沒核准不能排
}


def apply_reel_event(reel, ev):
    """Reels 的狀態變遷。與 apply_post_event 同規則：非法變遷不動資料、回報原因。"""
    t = ev["type"]
    cur = reel.get("status") or "storyboard"
    key = (cur, t)
    if key not in REEL_TRANSITIONS or REEL_TRANSITIONS[key] is None:
        why = {
            ("storyboard", "reel.generated"): "分鏡還沒確認。先看分鏡再生影片，可以把「不喜歡」的成本從約 137 點降到 7 點",
            ("storyboard", "reel.approve"): "影片還沒生出來，沒有東西可以核准",
            ("storyboard_ok", "reel.approve"): "影片還在生，等它出來再核准",
            ("video_review", "reel.schedule"): "還沒核准，不能排程",
        }.get(key)
        return False, ("不能這樣做：%s" % why) if why else ("非法變遷 %s --%s--> ?（維持原狀）" % (cur, t))
    nxt = REEL_TRANSITIONS[key]
    reel["status"] = nxt
    reel["status_since"] = ev.get("ts")
    pay = ev.get("payload") or {}
    if t == "reel.schedule":
        reel["publish_at"] = pay.get("publish_at")
    if t == "reel.unschedule":
        reel.pop("publish_at", None)
    if t == "reel.reject":
        reel["rejected_at"] = ev.get("ts")
        reel["reject_feedback"] = (pay.get("feedback") or "")[:500]
        # 只重做被勾選的段落，已確認的不重生、不重扣點〔藍圖 §7 ⑤〕
        if pay.get("segments"):
            reel["redo_segments"] = pay["segments"]
    return True, "%s --%s--> %s" % (cur, t, nxt)


def apply_post_event(post, ev):
    """回傳 (是否有變化, 訊息)。非法變遷不動資料、回報原因——寧可拒絕，不可默默亂跳。"""
    t = ev["type"]
    cur = post.get("status")
    key = (cur, t)
    if key not in POST_TRANSITIONS or POST_TRANSITIONS[key] is None:
        return False, "非法變遷 %s --%s--> ?（維持原狀）" % (cur, t)
    nxt = POST_TRANSITIONS[key]
    post["status"] = nxt
    post["status_since"] = ev.get("ts")   # UI 的「已多久」唯一來源（規格 §2.2）
    pay = ev.get("payload") or {}
    if t == "post.schedule":
        post["publish_at"] = pay.get("publish_at")
    if t == "post.unschedule":
        post.pop("publish_at", None)
    if t == "post.approve" and pay.get("copy_choice"):
        post["copy_choice"] = pay["copy_choice"]
    if t == "post.reject":
        post["rejected_at"] = ev.get("ts")
        post["reject_feedback"] = (pay.get("feedback") or "")[:500]
    return True, "%s --%s--> %s" % (cur, t, nxt)


def apply_idea_event(idea, ev):
    d = IDEA_DECISIONS.get(ev["type"])
    if not d:
        return False, "未知 idea 事件 %s" % ev["type"]
    if idea.get("decision") == d:
        return False, "冪等：已是 %s" % d
    idea["decision"] = d
    idea["decided_at"] = ev.get("ts")
    idea["reason"] = (ev.get("payload") or {}).get("feedback") or ""
    idea["applied"] = False        # 由 events-apply 的後續動作（觸發撰稿）翻 True
    return True, "idea → %s" % d


def new_id(prefix="w"):
    """平台原生 id：不可變、與內容無關。取代主題字串當外鍵（本週 bug 家族的根）。"""
    return "%s-%s" % (prefix, os.urandom(4).hex())


ID_RE = re.compile(r"^[wip]-[0-9a-f]{8}$")


def is_native_id(s):
    return bool(ID_RE.match(str(s or "")))
