#!/usr/bin/env python3
# weekly_report.py — 排程C（每週六 10:00）成效＋迭代週報。
# 彙整本週（週日–週五）：成效表＋WoW、審核統計、迭代 changelog＋因果說明、下週實驗建議。
# 產出 週報/YYYY-Wnn.md（推 repo，操控室「週報」入口讀取），並可另存本地 貼文製造機器人/週報/。
#
# 用法：python3 weekly_report.py [--week YYYY-Wnn] [--local-copy /abs/dir]
import os, sys, json, argparse, datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "data")
OUT = os.path.join(REPO, "週報")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def iso_week(d):
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def week_range(d):
    # 週日–週五（PLAN 定義）。d.isoweekday(): Mon=1..Sun=7
    sunday = d - datetime.timedelta(days=(d.isoweekday() % 7))
    return sunday, sunday + datetime.timedelta(days=5)


def in_range(ds, lo, hi):
    try:
        x = datetime.date.fromisoformat(ds)
    except Exception:
        return False
    return lo <= x <= hi


def build(args):
    ref = datetime.date.fromisoformat(args.ref) if args.ref else datetime.date.today()
    week = args.week or iso_week(ref)
    lo, hi = week_range(ref)
    plo, phi = lo - datetime.timedelta(days=7), hi - datetime.timedelta(days=7)

    posts = {p["id"]: p for p in load("posts.json").get("posts", [])}
    metrics = load("metrics.json").get("entries", [])
    reviews = load("reviews.json").get("reviews", [])
    log = load("iterate_log.json")

    def week_metrics(a, b):
        return [e for e in metrics if in_range(e.get("published_at", ""), a, b)]
    cur, prev = week_metrics(lo, hi), week_metrics(plo, phi)

    def agg(entries, k):
        return sum(e.get(k, 0) for e in entries)
    def wow(k):
        c, p = agg(cur, k), agg(prev, k)
        if not p:
            return "—"
        return "%+.0f%%" % ((c - p) / p * 100)

    L = []
    L.append("# Lava IG 週報 %s" % week)
    L.append("")
    L.append("> 期間：%s（週日）– %s（週五）｜產於 %s" % (lo, hi, datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()))
    L.append("")

    # 一、成效
    L.append("## 一、發布成效")
    if cur:
        L.append("")
        L.append("| 貼文 | 觸及 | 讚 | 珍藏 | 分享 | 留言 | 追蹤+ |")
        L.append("|---|--:|--:|--:|--:|--:|--:|")
        for e in cur:
            name = posts.get(e["post_id"], {}).get("topic", e["post_id"])[:16]
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                name, e.get("reach", 0), e.get("likes", 0), e.get("saves", 0),
                e.get("shares", 0), e.get("comments", 0), e.get("follows", 0)))
        L.append("")
        L.append("**本週合計 vs 上週（WoW）**：觸及 %s｜珍藏 %s｜追蹤增量 %s" % (wow("reach"), wow("saves"), wow("follows")))
    else:
        L.append("")
        L.append("_本週無成效資料（可能尚未輸入或未發布）。_")
    L.append("")

    # 二、審核統計
    wk_reviews = [r for r in reviews if in_range((r.get("ts", "")[:10]), lo, hi)]
    napp = sum(1 for r in wk_reviews if r.get("decision") == "approve")
    nrej = sum(1 for r in wk_reviews if r.get("decision") == "reject")
    total = napp + nrej
    L.append("## 二、審核統計")
    L.append("")
    L.append("- 審核筆數：%d（核准 %d｜退回 %d）" % (total, napp, nrej))
    L.append("- 核准率：%s" % ("%.0f%%" % (napp / total * 100) if total else "—"))
    scopes = {}
    for r in wk_reviews:
        if r.get("decision") == "reject":
            scopes[r.get("scope", "unknown")] = scopes.get(r.get("scope", "unknown"), 0) + 1
    if scopes:
        L.append("- 退回原因：" + "｜".join("%s %d" % ("底圖" if k == "base_image" else "排版" if k == "mockup" else k, v) for k, v in scopes.items()))
    L.append("")

    # 三、迭代 changelog + 因果
    wk_versions = [v for v in log.get("versions", []) if in_range(v.get("date", ""), lo, hi)]
    L.append("## 三、迭代 changelog（本週）")
    L.append("")
    if wk_versions:
        for v in wk_versions:
            kind = "回滾" if v.get("rollback_of") else ("自動生效" if v.get("auto_applied") else "人工核准")
            L.append("### %s · %s · %s（%s風險）" % (v["v"], v.get("date"), kind, "高" if v.get("risk") == "high" else "低"))
            for ch in v.get("changes", []):
                L.append("- %s" % ch)
            trg = v.get("trigger", {})
            causal = []
            if trg.get("reviews"):
                causal.append("觸發自審核回饋 %s" % ", ".join(trg["reviews"]))
            if trg.get("metrics_window"):
                causal.append("參考成效區間 %s" % trg["metrics_window"])
            if v.get("rollback_of"):
                causal.append("回滾自 %s" % v["rollback_of"])
            if v.get("commit"):
                causal.append("commit %s" % v["commit"])
            if causal:
                L.append("  - _因果：%s_" % "；".join(causal))
            L.append("")
    else:
        L.append("_本週無 config 變更。_")
        L.append("")

    # 四、下週實驗建議（啟發式）
    L.append("## 四、下週實驗建議")
    L.append("")
    sugg = []
    if cur:
        best = max(cur, key=lambda e: e.get("saves", 0))
        sugg.append("珍藏最高為「%s」→ 複製其可截圖元素（金句卡／公式）到下週題型。" % posts.get(best["post_id"], {}).get("topic", best["post_id"])[:16])
    pend = [p for p in load("proposals.json").get("proposals", []) if p.get("status") == "pending"]
    if pend:
        sugg.append("尚有 %d 則待審提案，建議本週內決策以免累積：%s。" % (len(pend), "、".join(p["title"][:18] for p in pend[:3])))
    if not sugg:
        sugg.append("資料量尚少，先累積 2–3 週成效再做 A/B 設計。")
    for s in sugg:
        L.append("- %s" % s)
    L.append("")

    md = "\n".join(L)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, week + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print("✓ 週報產出：%s" % os.path.relpath(path, REPO))
    if args.local_copy:
        os.makedirs(args.local_copy, exist_ok=True)
        with open(os.path.join(args.local_copy, week + ".md"), "w", encoding="utf-8") as f:
            f.write(md)
        print("✓ 本地備份：%s" % os.path.join(args.local_copy, week + ".md"))
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", help="覆寫週別 YYYY-Wnn")
    ap.add_argument("--ref", help="參考日期 YYYY-MM-DD（決定本週範圍），預設今天")
    ap.add_argument("--local-copy", help="另存一份到此本地資料夾")
    build(ap.parse_args())
