#!/usr/bin/env python3
"""假說評估器：每天檢查登記簿裡的假說，樣本夠了才判定，不夠就明說還差幾篇。

為什麼要有這支〔Jesse 2026-08-26〕：
  「數據搜集、分析後產生洞見、洞見產生假說、假說驗證方式的設計＆執行、
   各節點審視是否顯著。迭代」——前半段（搜集、分析）由 learn_features.py 做，
  這支負責後半段：把假說從 proposed 推到 running，樣本夠了做檢定，
  再把結論寫回登記簿。

  最重要的設計是**它會拒絕下結論**。n 不夠就停在 running 並印出還差幾篇。
  這條線上最大的風險不是算錯，是在 n=4 的時候宣布「晚上發比較好」然後
  據此改掉整個排程策略——那不是學習，是把雜訊當訊號。

統計方法刻意保守：只用 Welch t 檢定的近似（樣本小、變異不等），
且門檻設 p<0.05 併要求效果量 |d|>0.5。兩個都過才算顯著。
"""
import os, json, math, argparse, importlib.util, collections

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)


def _stats(xs):
    n = len(xs)
    if n == 0:
        return 0, 0.0, 0.0
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1) if n > 1 else 0.0
    return n, m, v


def welch(a, b):
    """回傳 (t, 近似 p, Cohen's d)。小樣本用常態近似，只當粗篩，不當定論。"""
    na, ma, va = _stats(a); nb, mb, vb = _stats(b)
    if na < 2 or nb < 2:
        return None, None, None
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return None, None, None
    t = (ma - mb) / se
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    sp = math.sqrt(((na - 1) * va + (nb - 1) * vb) / max(na + nb - 2, 1))
    d = (ma - mb) / sp if sp else 0.0
    return t, p, d


def arm_values(h, entries, reviews):
    """把兩組的觀測值取出來。不同 metric 走不同資料源。"""
    m = h.get("metric")
    var = h.get("variable")
    if m in ("interaction_rate", "reach", "share_rate", "save_rate"):
        buckets = collections.defaultdict(list)
        for e in entries:
            if var == "publish_hour":
                hh = e.get("publish_hour")
                if hh is None:
                    continue
                k = "下午" if 12 <= hh < 18 else ("晚上" if hh >= 18 else "早上")
                if k == "早上":
                    continue
            elif var == "has_celebrity":
                k = "綁名人／作品" if e.get("has_celebrity") else "純概念"
            else:
                k = str(e.get(var))
            buckets[k].append(e.get(m) or 0)
        return dict(buckets)
    # 退回率類：以 reviews 計數，單位是「每篇的退回次數」
    if m in ("reject_rate_visual", "reject_rate_copy"):
        return {}          # 需要換源/上線切點的標記，資料齊備後再實作
    return {}


def evaluate(h, entries, reviews):
    arms = arm_values(h, entries, reviews)
    need = h.get("min_n_per_arm", 8)
    if not arms:
        return "running", "此 metric 尚無可用資料源（需先累積標記）", None
    names = list(arms.keys())
    if len(names) < 2:
        return "running", "只有一組資料（%s），另一組還沒有樣本" % (names[0] if names else "無"), None
    a, b = arms[names[0]], arms[names[1]]
    if len(a) < need or len(b) < need:
        return "running", "樣本不足：%s n=%d、%s n=%d，各需 %d" % (
            names[0], len(a), names[1], len(b), need), None
    t, p, d = welch(a, b)
    if p is None:
        return "running", "無法檢定（變異為零）", None
    sig = p < 0.05 and abs(d) > 0.5
    _, ma, _ = _stats(a); _, mb, _ = _stats(b)
    detail = {"arm_a": names[0], "mean_a": round(ma, 2), "n_a": len(a),
              "arm_b": names[1], "mean_b": round(mb, 2), "n_b": len(b),
              "p": round(p, 4), "cohens_d": round(d, 2)}
    return ("supported" if sig and ma > mb else "refuted" if sig else "running",
            "p=%.3f d=%.2f%s" % (p, d, "" if sig else "（未達顯著，繼續累積）"), detail)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    doc = SC.load("hypotheses.json")
    entries = SC.load("metrics.json").get("entries", [])
    reviews = SC.load("reviews.json").get("reviews", [])
    print("假說登記簿（樣本 %d 篇）\n" % len(entries))
    changed = 0
    for h in doc.get("hypotheses", []):
        if h.get("status") in ("supported", "refuted"):
            print("  ✔ %-20s %s" % (h["id"], h["status"])); continue
        st, msg, detail = evaluate(h, entries, reviews)
        mark = {"supported": "✅", "refuted": "❌", "running": "⏳"}[st]
        print("  %s %-20s %s" % (mark, h["id"], msg))
        print("     %s" % h["statement"])
        if h.get("status") != st or h.get("result") != detail:
            h["status"] = st; h["result"] = detail; changed += 1
    if changed and not a.dry:
        doc["updated_at"] = SC._now_iso()
        SC.save("hypotheses.json", doc)
        print("\n登記簿已更新（%d 條）" % changed)


if __name__ == "__main__":
    main()
