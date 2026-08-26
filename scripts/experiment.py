#!/usr/bin/env python3
"""每日三篇的實驗排程器：把「發文」變成「跑實驗」。

Jesse 2026-08-27：「每天都發三篇貼文，來進行主題、風格、素材、撰寫文案口吻、
模板的快速測試及迭代」。

為什麼一天三篇才做得起來：
  一天一篇的話，要累積到單一因素兩組各 8 篇需要 16 天，中間任何策略調整都會
  污染樣本。一天三篇＝一天就是一組完整的對照（同日、同受眾、同演算法狀態），
  時段與當日熱度被自然控制住，剩下的差異才可能來自我們要測的那個因素。

三個時段（依現有 9 篇觀察資料，下午 8.13% vs 晚上 3.28%，但 n 太小尚未驗證）：
  12:30 / 18:30 / 21:00

指派規則：
  1. 每天從已核准（approved、事實與文案閘門皆過）的稿裡挑三篇。
  2. 當日有 running 的假說時，優先挑「能填補該假說較少那一組」的稿，
     並在 posts.json 標 experiment{hypothesis, arm}。
  3. 同一天三篇不得同題型，避免題型與時段糾纏。
  4. 挑不滿三篇就只排實際有的，不硬湊——寧可少發，不可為了湊數發爛稿。

安全設計：
  - 只寫 status=scheduled + publish_at，實際發佈仍由 n8n WF10 執行。
  - 預設 --dry：不加 --commit 只印計畫，不動資料。這是不可逆動作的前一道人閘。
  - 事實或文案有 block 的稿一律不排（與不變量 I9 同一條線）。
"""
import os, json, argparse, importlib.util, datetime, collections

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

SLOTS = [(12, 30), (18, 30), (21, 0)]


def blocks(p, key):
    return [i for i in ((p.get(key) or {}).get("issues") or [])
            if (i.get("severity") or i.get("sev")) == "block"]


def eligible(posts):
    """可排程的稿：已核准、沒卡住、事實與文案都沒有 block。"""
    out = []
    for p in posts:
        if p.get("status") != "approved" or p.get("render_note"):
            continue
        if blocks(p, "fact") or blocks(p, "copy"):
            continue
        if any(not s.get("candidates") and not s.get("final_src") and not s.get("public_url")
               and "CTA" not in str(s.get("role", ""))
               for s in p.get("slides", [])):
            continue
        out.append(p)
    return out


def arm_of(p, h):
    """這篇稿天然落在假說的哪一組。只讀已存在的特徵，不改稿。"""
    v = h.get("variable")
    if v == "has_celebrity":
        import re
        celeb = re.compile(r"[A-Z][a-z]+\s+[A-Z][a-z]+|東野圭吾|朴恩斌|Joeman|川口春奈")
        return "綁名人／作品" if celeb.search(p.get("topic") or "") else "純概念"
    if v == "topic_type":
        return p.get("topic_type") or "未分類"
    return None


def plan(day, posts, hyps, metrics):
    elig = eligible(posts)
    if not elig:
        return [], "沒有可排程的稿（需已核准且事實／文案閘門皆過、無缺料）"
    # 各假說目前兩組的樣本數，優先補少的那一組
    counts = collections.defaultdict(collections.Counter)
    for e in metrics:
        for h in hyps:
            if h.get("status") != "running":
                continue
            v = h.get("variable")
            if v == "has_celebrity":
                counts[h["id"]]["綁名人／作品" if e.get("has_celebrity") else "純概念"] += 1
    running = [h for h in hyps if h.get("status") == "running" and h.get("variable") == "has_celebrity"]

    picked, used_types = [], set()
    for slot in SLOTS:
        best, best_score = None, None
        for p in elig:
            if p in picked or (p.get("topic_type") or "") in used_types:
                continue
            score = 0
            tag = None
            for h in running:
                a = arm_of(p, h)
                if a:
                    # 樣本少的那一組加分：讓實驗自己把缺口補起來
                    score += max(0, 20 - counts[h["id"]][a])
                    tag = {"hypothesis": h["id"], "arm": a}
            if best_score is None or score > best_score:
                best, best_score, best_tag = p, score, tag
        if best is None:
            break
        picked.append(best)
        used_types.add(best.get("topic_type") or "")
        dt = datetime.datetime.combine(day, datetime.time(*slot)).astimezone()
        best["_slot"] = dt
        best["_exp"] = best_tag
        if best_tag:
            counts[best_tag["hypothesis"]][best_tag["arm"]] += 1
    return picked, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD，預設明天")
    ap.add_argument("--commit", action="store_true", help="真的寫入排程（預設只印計畫）")
    a = ap.parse_args()
    day = (datetime.date.fromisoformat(a.date) if a.date
           else datetime.date.today() + datetime.timedelta(days=1))
    doc = SC.load("posts.json")
    hyps = SC.load("hypotheses.json").get("hypotheses", [])
    metrics = SC.load("metrics.json").get("entries", [])
    picked, why = plan(day, doc.get("posts", []), hyps, metrics)
    print("排程日：%s（每日三篇：%s）\n" % (day, "、".join("%02d:%02d" % s for s in SLOTS)))
    if not picked:
        print("✗ " + (why or "無可排稿件")); return
    for p in picked:
        exp = p.get("_exp")
        print("  %s  %s" % (p["_slot"].strftime("%H:%M"), (p.get("topic") or p["id"])[:38]))
        print("        題型 %s%s" % (p.get("topic_type") or "未分類",
              ("｜實驗 %s／%s" % (exp["hypothesis"], exp["arm"])) if exp else ""))
    print("\n共 %d 篇。" % len(picked))
    if not a.commit:
        print("這是計畫，還沒寫入。確認無誤後加 --commit 才會真的排程。")
        return
    for p in picked:
        q = next(x for x in doc["posts"] if x["id"] == p["id"])
        q["status"] = "scheduled"
        q["publish_at"] = p["_slot"].isoformat(timespec="seconds")
        if p.get("_exp"):
            q["experiment"] = p["_exp"]
        q.pop("_slot", None); q.pop("_exp", None)
    for x in doc["posts"]:
        x.pop("_slot", None); x.pop("_exp", None)
    SC.save("posts.json", doc)
    print("✓ 已寫入排程（%d 篇）。實際發佈仍由 n8n WF10 執行。" % len(picked))


if __name__ == "__main__":
    main()
