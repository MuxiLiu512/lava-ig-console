#!/usr/bin/env python3
"""成效歸因的地基：把「每篇貼文的特徵」與「它的市場成效」接起來。

為什麼一定要先有這支〔2026-08-26 Jesse 提問〕：
  Jesse 問「逐步收斂最重要的因素是什麼，是時事熱度還是發佈時間還是人物知名度
  還是撰文風格？」——誠實的答案是：**現在的資料回答不了**。
  我們有輸出（reach／互動，insights.json 每天快照），但從來沒有記錄輸入。
  沒有特徵就沒有相關性可算，任何「洞見」都只是看圖說故事。
  metrics.json 至今是空的（entries: 0），iterate_harness 的成效那條手臂
  從來沒有資料可用。

本檔做的事（純機械、不需 LLM）：
  1. 從 posts.json 抽出每篇的結構化特徵：題型、hook 型式、發佈時段與星期、
     slide 數、字數、圖片來源配比（劇照／人物／截圖／生成）、是否綁名人或時事、
     撰寫模型、模板、有沒有被退回過、Jesse 改了幾處文案。
  2. 從 insights.json 取該篇最新一筆快照當結果：reach、互動、互動率、
     分享率、收藏率、profile_visits、follows。
  3. 寫成 metrics.json 的 entries（iterate_harness 已經在讀這個格式）。
  4. 印一份誠實的分組比較：每組樣本數一併印出來，n 太小就明說不可下結論。

它不做的事：不做因果推論。觀察性資料只能給相關與方向，真正要驗因果
必須用 hypotheses.json 設計對照（同期、單一變因、預先宣告成功指標）。
"""
import os, re, json, argparse, importlib.util, collections, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

CELEB = re.compile(r"[A-Z][a-z]+\s+[A-Z][a-z]+|東野圭吾|朴恩斌|Joeman|川口春奈|茲維列夫")
NEWSY = re.compile(r"今天|今日|熱搜|大結局|走了|上榜|推爆|進了牛津|剛(剛)?宣布")


def features(p, reviews):
    """一篇貼文的輸入特徵。全部是發佈當下就決定、且事後可重現的東西。"""
    slides = p.get("slides", [])
    body = "".join((s.get("heading") or "") + (s.get("display_copy") or "") for s in slides)
    topic = p.get("topic") or ""
    kinds = collections.Counter()
    for s in slides:
        for c in (s.get("candidates") or []):
            kinds[c.get("source_kind") or c.get("kind") or "?"] += 1
    tot = max(sum(kinds.values()), 1)
    pub = p.get("published_at") or p.get("publish_at") or ""
    try:
        dt = datetime.datetime.fromisoformat(pub)
    except Exception:
        dt = None
    rj = [r for r in reviews if r.get("post_id") == p["id"]]
    return {
        "topic_type": p.get("topic_type") or "未分類",
        "template_id": p.get("template_id") or "無",
        "writer_model": p.get("writer_model") or "未記錄",
        "slides": len(slides),
        "chars": len(body),
        "hook_len": len((slides[0].get("display_copy") or "") if slides else ""),
        "has_celebrity": bool(CELEB.search(topic)),
        "is_newsy": bool(NEWSY.search(topic)),
        "publish_hour": dt.hour if dt else None,
        "publish_weekday": dt.weekday() if dt else None,   # 0=週一
        "img_still_pct": round(100 * kinds.get("still", 0) / tot),
        "img_shot_pct": round(100 * kinds.get("SHOT", 0) / tot),
        "img_person_pct": round(100 * (kinds.get("WM", 0) + kinds.get("OV", 0)) / tot),
        "img_generated_pct": round(100 * kinds.get("generated", 0) / tot),
        "was_rejected": any(r.get("decision") == "reject" for r in rj),
        "review_rounds": len(rj),
    }


def outcome(media):
    """最新一筆快照＝目前累積成效。互動率用 reach 當分母（IG 的排序邏輯看的是率不是量）。"""
    snaps = media.get("snapshots") or []
    if not snaps:
        return None
    s = snaps[-1]
    reach = max(int(s.get("reach") or 0), 1)
    inter = int(s.get("total_interactions") or 0)
    return {
        "day": s.get("day"), "reach": reach, "interactions": inter,
        "interaction_rate": round(100 * inter / reach, 2),
        "share_rate": round(100 * int(s.get("shares") or 0) / reach, 2),
        "save_rate": round(100 * int(s.get("saved") or 0) / reach, 2),
        "profile_visits": int(s.get("profile_visits") or 0),
        "follows": int(s.get("follows") or 0),
    }


def build():
    posts = SC.load("posts.json").get("posts", [])
    reviews = SC.load("reviews.json").get("reviews", [])
    ins = SC.load("insights.json").get("media", {})
    by_pid = {v.get("post_id"): v for v in ins.values() if v.get("post_id")}
    entries = []
    for p in posts:
        if p.get("status") != "published":
            continue
        m = by_pid.get(p["id"]) or ins.get(str(p.get("media_id") or ""), {})
        o = outcome(m) if m else None
        if not o:
            continue
        entries.append({"post_id": p["id"], "topic": p.get("topic", "")[:40],
                        "published_at": (p.get("published_at") or "")[:10],
                        **features(p, reviews), **o})
    return entries


def report(entries, min_n=3):
    """分組比較。每組印樣本數；n < min_n 一律標示不可下結論——這是誠實的底線。"""
    if not entries:
        print("沒有可用資料（已發佈且有成效快照的貼文為 0）"); return
    print("樣本：%d 篇已發佈且有成效數字\n" % len(entries))
    base = sum(e["interaction_rate"] for e in entries) / len(entries)
    print("全體平均互動率 %.2f%%\n" % base)

    def group(name, keyfn):
        buckets = collections.defaultdict(list)
        for e in entries:
            k = keyfn(e)
            if k is not None:
                buckets[k].append(e)
        print("── %s ──" % name)
        for k, v in sorted(buckets.items(), key=lambda x: -sum(y["interaction_rate"] for y in x[1]) / len(x[1])):
            avg = sum(y["interaction_rate"] for y in v) / len(v)
            flag = "" if len(v) >= min_n else "  ⚠ n 太小，不可下結論"
            print("   %-16s n=%-2d 互動率 %.2f%%（%+.2f）%s" % (str(k)[:16], len(v), avg, avg - base, flag))
        print()

    group("題型", lambda e: e["topic_type"])
    group("有無名人", lambda e: "有名人" if e["has_celebrity"] else "無名人")
    group("是否時事", lambda e: "時事" if e["is_newsy"] else "非時事")
    group("發佈時段", lambda e: None if e["publish_hour"] is None
          else ("早上" if e["publish_hour"] < 12 else "下午" if e["publish_hour"] < 18 else "晚上"))
    group("是否被退過", lambda e: "退過重做" if e["was_rejected"] else "一次過")
    group("劇照佔比", lambda e: "劇照>50%" if e["img_still_pct"] > 50 else "劇照≤50%")

    print("── 誠實的限制 ──")
    print("   1. n=%d，任何分組差異都可能是雜訊。IG 觸及本身的變異就很大。" % len(entries))
    print("   2. 這是觀察性資料，只能看相關，不能說因果——")
    print("      例如「時事題互動率高」也可能只是因為時事題剛好都排在晚上發。")
    print("   3. 要驗因果必須設計對照：同期、只變一個因素、事前宣告成功指標。")
    print("      見 data/hypotheses.json。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    entries = build()
    report(entries)
    if not a.dry:
        SC.save("metrics.json", {"note": "每篇貼文的特徵×成效。由 learn_features.py 產出，iterate_harness 讀取。",
                                 "updated_at": SC._now_iso(), "entries": entries})
        print("\n已寫入 data/metrics.json（%d 筆）" % len(entries))


if __name__ == "__main__":
    main()
