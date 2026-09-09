#!/usr/bin/env python3
"""靈感發想器：把三個已經有的輸入合成「下一篇可以怎麼做」。

為什麼是「合成」而不是「生成」〔2026-09-10 Jesse 要一個靈感發想器〕：

  系統已經有三份彼此不講話的資料：
    data/playbook.json    外面的人說什麼有效（59 條可查核主張）
    data/metrics.json     我們自己做過什麼、成效如何（27 個特徵欄位）
    data/templates.json   我們有哪些骨架（23 個，視覺欄位可由 template_decompose 填）
  三份各自都有用，但沒有任何一支程式同時讀它們。
  「靈感」不是憑空冒出來的東西，是這三者交叉之後浮出來的空白格：
  外面說有效、我們沒做過、而且我們有骨架可以做 → 那就是下一篇。

  所以這支不呼叫任何生成模型。它做的是**找出交集裡的空格**，
  然後把「為什麼建議這個」寫清楚。憑空生成的點子沒有理由可以審查，
  而沒有理由的建議，人只能憑感覺接受或拒絕——那不是決策，是擲骰子。

四種靈感，每一種都有明確的推導路徑：
  1 未做過的骨架   我們有這個範本但從來沒用過 → 為什麼不用？值不值得試一次
  2 外部沒對上的   外面反覆提到某種做法，我們的範本庫沒有對應的骨架
  3 成效落差       同一個特徵有明顯高低分組（樣本夠才講），往高的那邊靠
  4 視覺空白       範本有骨架但沒有視覺拆解 → 補拆解才能被排版引擎執行

用法：
  python3 scripts/inspire.py                 # 印出靈感清單
  python3 scripts/inspire.py --json
  python3 scripts/inspire.py --save          # 寫進 data/inspirations.json 供操控台顯示
"""
import os, sys, json, argparse, collections, importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

# 外部主張的題目 → 我們的範本庫裡「應該要有對應骨架」的關鍵字。
# 對不上就代表我們沒有做那種東西的能力，那是一個可以填的空格。
TOPIC_TO_SKELETON = {
    "carousel":     ["輪播", "多圖", "逐張"],
    "first_slide":  ["cover", "封面", "開場", "鉤子"],
    "saves":        ["收藏", "清單", "懶人包", "步驟", "框架"],
    "shares_weight": ["轉發", "分享", "傳給", "標記朋友"],
    "watch_time":   ["影片", "reel", "分鏡"],
    "reels_length": ["影片", "reel", "分鏡"],
}


def _load(name, default):
    try:
        return SC.load(name)
    except Exception:
        return default


def unused_templates(templates, posts):
    """有骨架但沒用過的範本。用過的定義是 used_by 有紀錄，或有貼文標了這個 template_id。"""
    used = set()
    for p in posts:
        if p.get("template_id"):
            used.add(p["template_id"])
    out = []
    for t in templates:
        if t.get("status") == "candidate":
            continue                     # 候選範本本來就還沒用，不算「被冷落」
        if t["id"] in used or (t.get("used_by") or []):
            continue
        out.append({
            "kind": "未用過的骨架",
            "title": "試一次「%s」" % (t.get("hook_type") or t["id"]),
            "why": "這個範本在庫裡但一篇都沒用過。%s" % (t.get("why_it_works") or "")[:100],
            "how": (t.get("skeleton") or "")[:180],
            "ref": {"template_id": t["id"]},
        })
    return out


def external_gaps(claims, templates):
    """外面反覆提到、我們的範本庫沒有對應骨架的做法。

    「反覆提到」的門檻設 3 條以上不同來源的主張——
    單一來源講一次可能只是那個作者的偏好，不足以推動我們開新骨架。
    """
    by_topic = collections.defaultdict(list)
    for c in claims:
        by_topic[c["topic"]].append(c)
    blob = " ".join((t.get("skeleton") or "") + (t.get("hook_type") or "")
                    for t in templates).lower()
    out = []
    for topic, rows in sorted(by_topic.items(), key=lambda x: -len(x[1])):
        kws = TOPIC_TO_SKELETON.get(topic)
        if not kws or len(rows) < 3:
            continue
        if any(k.lower() in blob for k in kws):
            continue                     # 已經有對應的骨架了
        srcs = sorted({r["source"] for r in rows})
        out.append({
            "kind": "外面在講、我們沒有的做法",
            "title": "補一個「%s」型的骨架" % topic,
            "why": "外部有 %d 條主張講到這件事（%d 個來源），但我們 %d 個範本裡沒有一個"
                   "對得上「%s」。" % (len(rows), len(srcs), len(templates), "／".join(kws)),
            "how": "代表性主張：" + rows[0]["text"][:150],
            "ref": {"topic": topic, "sources": srcs[:3]},
        })
    return out


NUMERIC = ("interaction_rate", "reach", "save_rate", "share_rate")


def outcome_gaps(entries, min_per_group=3):
    """同一個特徵下有明顯高低分組 → 往高的那邊靠。

    **這裡不做統計檢定，也不宣稱因果。** 檢定是 hypotheses.py 的工作，
    而且我們的樣本量（9 筆）本來就不夠。這一層只做「值得注意的落差」，
    輸出一律標明樣本數，並寫「這是線索不是結論」。
    分不出高低（差距小於 30%）就不講——微小差異在 n=3 的時候完全是雜訊。
    """
    out = []
    if len(entries) < 6:
        return out
    cats = ["template_id", "topic_type", "has_celebrity", "publish_weekday"]
    for cat in cats:
        for metric in ("interaction_rate", "reach"):
            g = collections.defaultdict(list)
            for e in entries:
                k = e.get(cat)
                v = e.get(metric)
                if k in (None, "") or v in (None, ""):
                    continue
                g[str(k)].append(float(v))
            g = {k: v for k, v in g.items() if len(v) >= min_per_group}
            if len(g) < 2:
                continue
            means = {k: sum(v) / len(v) for k, v in g.items()}
            hi = max(means, key=means.get); lo = min(means, key=means.get)
            if means[lo] <= 0 or means[hi] / means[lo] < 1.3:
                continue
            out.append({
                "kind": "成效落差（線索，不是結論）",
                "title": "%s＝%s 的%s比 %s 高 %.0f%%" % (
                    cat, hi, "互動率" if metric == "interaction_rate" else "觸及",
                    lo, 100 * (means[hi] / means[lo] - 1)),
                "why": "樣本 %s n=%d、%s n=%d。這個樣本量不足以做檢定，"
                       "只能當作「值得刻意再試幾篇」的線索。"
                       % (hi, len(g[hi]), lo, len(g[lo])),
                "how": "下一批刻意多排幾篇 %s＝%s 的，累積到各組 8 篇再讓 hypotheses 判定。"
                       % (cat, hi),
                "ref": {"feature": cat, "metric": metric,
                        "means": {k: round(v, 2) for k, v in means.items()}},
            })
    return out


def visual_gaps(templates):
    """有骨架但沒有視覺拆解的範本。沒有視覺欄位，排版引擎就只能照預設做，
    範本之間看起來會一模一樣——那等於沒有範本。"""
    out = []
    missing = [t for t in templates if not t.get("visual") and t.get("status") != "candidate"]
    if not missing:
        return out
    out.append({
        "kind": "視覺空白",
        "title": "%d 個範本只有敘事結構，沒有視覺拆解" % len(missing),
        "why": "沒有色票、版位、明暗結構這些數字，排版引擎只能照預設做，"
               "所以不同範本產出的圖看起來會一樣——那等於沒有範本。",
        "how": "找一張你喜歡的參考圖，跑 "
               "python3 scripts/template_decompose.py --dir <資料夾> --save <名稱>，"
               "再到規則本補完字型與風格那幾欄。",
        "ref": {"templates": [t["id"] for t in missing][:8]},
    })
    return out


def broken_links(posts, templates, entries):
    """資料斷點：某個欄位該有值卻大量空白 → 下游的分析永遠算不出東西。

    〔為什麼這也算靈感〕最好的點子如果沒有資料可以驗證，做了也學不到。
    2026-09-10 實測：27 篇貼文裡 25 篇沒有 template_id，
    也就是「哪個範本比較有效」這個問題**在資料層就已經無解**——
    不是分析寫得不好，是輸入根本不存在。這種斷點比缺點子更值得先修。
    """
    out = []
    live = [p for p in posts if p.get("status") != "rejected"]
    if live:
        no_tpl = [p for p in live if not p.get("template_id")]
        if len(no_tpl) / len(live) > 0.5 and templates:
            out.append({
                "kind": "資料斷點（先修這個，不然學不到東西）",
                "title": "%d/%d 篇貼文沒有標範本，範本成效永遠算不出來" % (len(no_tpl), len(live)),
                "why": "範本庫有 %d 個，但貼文沒有記錄自己用了哪一個。"
                       "learn_features 的 template_id 欄位因此大多是空的，"
                       "hypotheses 也就永遠檢定不了「哪個範本比較有效」。"
                       "這不是分析不夠好，是輸入不存在。" % len(templates),
                "how": "撰稿流程（n8n WF01）產稿時要把選用的 template_id 寫進稿檔，"
                       "add_post 再帶進 posts.json。舊稿可由審稿台補標。",
                "ref": {"missing": len(no_tpl), "total": len(live)},
            })
    if entries:
        for col, label in (("template_id", "範本"), ("topic_type", "題型"),
                           ("has_celebrity", "有無名人")):
            empty = [e for e in entries if e.get(col) in (None, "")]
            if len(empty) / len(entries) > 0.5:
                out.append({
                    "kind": "資料斷點（先修這個，不然學不到東西）",
                    "title": "成效表的「%s」欄位 %d/%d 是空的" % (label, len(empty), len(entries)),
                    "why": "這一欄空著，任何以它分組的比較都做不了。",
                    "how": "回頭補 learn_features 的取值路徑，或補上游的紀錄。",
                    "ref": {"column": col, "empty": len(empty), "total": len(entries)},
                })
    return out


def build():
    posts = _load("posts.json", {}).get("posts", [])
    templates = _load("templates.json", {}).get("templates", [])
    claims = _load("playbook.json", {}).get("claims", [])
    entries = _load("metrics.json", {}).get("entries", [])
    ideas = (broken_links(posts, templates, entries)
             + unused_templates(templates, posts)
             + external_gaps(claims, templates)
             + outcome_gaps(entries)
             + visual_gaps(templates))
    return {
        "note": "靈感＝三份資料交叉後浮出來的空白格，不是模型憑空生成的。"
                "每一條都附推導理由，理由不成立就該否決它。",
        "generated_at": SC._now_iso(),
        "inputs": {"posts": len(posts), "templates": len(templates),
                   "external_claims": len(claims), "metrics_rows": len(entries)},
        "inspirations": ideas,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    d = build()
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        i = d["inputs"]
        print("輸入：貼文 %d、範本 %d、外部主張 %d、成效 %d 筆\n"
              % (i["posts"], i["templates"], i["external_claims"], i["metrics_rows"]))
        by = collections.defaultdict(list)
        for x in d["inspirations"]:
            by[x["kind"]].append(x)
        if not d["inspirations"]:
            print("沒有靈感。這通常代表輸入太少（外部主張或成效資料還沒累積），"
                  "不代表沒有可做的事。")
        for kind, rows in by.items():
            print("## %s（%d）" % (kind, len(rows)))
            for r in rows[:6]:
                print("  • %s" % r["title"])
                print("      為什麼：%s" % r["why"][:120])
                print("      怎麼做：%s" % r["how"][:120])
            if len(rows) > 6:
                print("  …另外還有 %d 條" % (len(rows) - 6))
            print()
    if a.save:
        SC.save("inspirations.json", d)
        print("✓ 已寫入 data/inspirations.json（%d 條）" % len(d["inspirations"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
