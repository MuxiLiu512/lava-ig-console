#!/usr/bin/env python3
# iterate_harness.py — 排程B（每日 21:30）迭代引擎。
#
# 流程（對應 PLAN §6 排程B）：
#   1) 收集：未 consumed reviews（含 feedback）、metrics 近 7 天、approved proposals、rollback_requests
#   2) 先執行回滾請求（git 還原 config 至目標版本狀態，保留歷史 → 新 cfg 版本）
#   3) 套用已核准提案（改 config → commit → log，proposal.status=applied）
#   4) 分析 feedback＋成效 → 分級：
#        低風險 → 直接改 config、commit、log(auto_applied=true)
#        高風險 → 只寫 proposals.json，等操控室核准
#   5) 寫 iterate_log、輸出摘要（push 由呼叫端用 push_files.sh 處理）
#
# 護欄：不動 Drive 正本；單日自動生效上限 3 項；某類改動 7 天內被回滾過 → 一律降為提案。
#
# 分析部分（feedback → 改動）採「規則基線 + LLM 增補」：本檔內建可靠的規則分類（見 RULES），
# cron 上的 Claude 可在呼叫本檔前，把更細緻的判斷寫成同格式的 change dict 交給 apply_change()。
import os, sys, json, re, subprocess, datetime, argparse

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "data")
CONFIG = os.path.join(REPO, "config")
MAX_AUTO_PER_DAY = 3
ROLLBACK_LOOKBACK_DAYS = 7
TODAY = os.environ.get("LAVA_TODAY")  # 測試可注入；否則用系統日期


def today():
    return datetime.date.fromisoformat(TODAY) if TODAY else datetime.date.today()


def now_iso():
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write("\n")


def git(*a, check=True):
    return subprocess.run(["git", "-C", REPO, *a], check=check, capture_output=True, text=True)


def next_cfg_version(log):
    mx = 0
    for v in log.get("versions", []):
        m = re.match(r"cfg-(\d+)", v["v"])
        if m:
            mx = max(mx, int(m.group(1)))
    return "cfg-%03d" % (mx + 1)


def commit_config(msg):
    """把 config/ 變更 commit，回傳短 sha（無變更回 None）。"""
    git("add", "config", "data/iterate_log.json", check=False)
    st = git("status", "--porcelain", "config", check=False).stdout.strip()
    if not st:
        return None
    git("commit", "-m", msg)
    return git("rev-parse", "--short", "HEAD").stdout.strip()


def log_version(log, v, risk, auto, changes, trigger, commit=None, rollback_of=None):
    log.setdefault("versions", []).append({
        "v": v, "date": today().isoformat(), "commit": commit, "risk": risk,
        "auto_applied": auto, "changes": changes, "trigger": trigger, "rollback_of": rollback_of,
    })


# ── 護欄：7 天內被回滾過的類別降級 ────────────────────────────────────
def recently_rolled_back_categories(log):
    cutoff = today() - datetime.timedelta(days=ROLLBACK_LOOKBACK_DAYS)
    cats = set()
    for v in log.get("versions", []):
        if v.get("rollback_of"):
            try:
                d = datetime.date.fromisoformat(v["date"])
            except Exception:
                continue
            if d >= cutoff:
                for ch in v.get("changes", []):
                    cats.add(categorize(ch))
    return cats


# ── 規則分類：feedback 文字 → 低風險改動 ─────────────────────────────
# 每條 rule：(比對正則, 類別, 目標檔, 產生改動的函式)
def categorize(text):
    t = text.lower()
    if any(k in t for k in ["手指", "finger", "手臂", "hand", "臉", "face", "穿模", "anatom"]):
        return "negative_prompt"
    if any(k in t for k in ["禁用詞", "用語", "加價", "手續費", "漲價"]):
        return "banned_word"
    if any(k in t for k in ["光線", "色溫", "冷", "暖", "亮", "暗", "lighting", "配比"]):
        return "lighting_ratio"
    if any(k in t for k in ["版型", "排版", "字級", "遮罩", "layout", "橘槓"]):
        return "layout"
    if any(k in t for k in ["語氣", "文案", "口吻", "tone", "hook"]):
        return "copy_tone"
    return "misc"


HIGH_RISK = {"lighting_ratio", "layout", "copy_tone"}  # 影響全部貼文 → 提案


def append_line(path, line, marker="<!-- 迭代增補從這行以下 append"):
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    if line.strip() in txt:
        return False
    txt = txt.rstrip() + "\n" + line + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return True


def apply_low_risk(change):
    """change: {category, summary, payload}. 回傳 True 表示有實際改檔。"""
    cat = change["category"]
    if cat == "negative_prompt":
        return append_line(os.path.join(CONFIG, "gen-prompt-template.md"),
                           "- （迭代 %s）負面 prompt 追加：%s" % (today().isoformat(), change["payload"]))
    if cat == "banned_word":
        p = os.path.join(CONFIG, "banned-words.txt")
        return append_line(p, change["payload"])
    if cat == "misc":
        return append_line(os.path.join(CONFIG, "qc-checklist.md"),
                           "- [ ] （迭代 %s）%s" % (today().isoformat(), change["payload"]))
    return False


# ── 主流程 ──────────────────────────────────────────────────────────
def run(args):
    reviews_d = load("reviews.json"); metrics_d = load("metrics.json")
    props_d = load("proposals.json"); log = load("iterate_log.json")
    summary = {"rollbacks": 0, "applied_proposals": 0, "auto_changes": 0, "new_proposals": 0, "feedback_consumed": 0, "copy_absorbed": 0, "perf_signal": 0}

    # 2) 回滾請求
    for req in log.get("rollback_requests", []):
        if req.get("consumed"):
            continue
        target = req["target_v"]
        tv = next((v for v in log["versions"] if v["v"] == target), None)
        v = next_cfg_version(log)
        changes = ["回滾 config 至 %s 狀態" % target]
        commit = None
        if tv and tv.get("commit") and not args.dry_run:
            # 以目標 commit 的 config/ 覆蓋現況 → 前進一個 commit（保留完整歷史）
            r = git("checkout", tv["commit"], "--", "config", check=False)
            if r.returncode == 0:
                commit = commit_config("%s: rollback → %s [risk:low] [auto]" % (v, target))
        log_version(log, v, "low", True, changes,
                    {"reviews": [], "metrics_window": None}, commit=commit, rollback_of=target)
        req["consumed"] = True; summary["rollbacks"] += 1
        sys.stderr.write("↩ 回滾 → %s（新版本 %s）\n" % (target, v))

    # 3) 套用已核准提案
    for pr in props_d.get("proposals", []):
        if pr.get("status") != "approved":
            continue
        v = next_cfg_version(log)
        applied = append_line(os.path.join(CONFIG, "style-notes.md"),
                              "- （提案 %s / %s）%s" % (pr["pid"], today().isoformat(), pr.get("diff_summary", pr["title"])))
        commit = None if args.dry_run else commit_config("%s: apply %s — %s [risk:%s] [approved:%s]" % (v, pr["pid"], pr["title"], pr.get("risk", "high"), pr["pid"]))
        log_version(log, v, pr.get("risk", "high"), False, ["套用提案 %s：%s" % (pr["pid"], pr["title"])],
                    {"reviews": [], "metrics_window": None, "proposal": pr["pid"]}, commit=commit)
        pr["status"] = "applied"; pr["applied_at"] = now_iso()
        summary["applied_proposals"] += 1
        sys.stderr.write("✅ 套用提案 %s（%s）\n" % (pr["pid"], v))

    # 4) 分析 feedback → 分級
    downgraded = recently_rolled_back_categories(log)
    auto_budget = MAX_AUTO_PER_DAY
    pending_reviews = [r for r in reviews_d.get("reviews", []) if not r.get("consumed") and r.get("feedback")]
    trig_reviews = []
    for r in pending_reviews:
        fb = r["feedback"]; cat = categorize(fb); trig_reviews.append(r.get("id"))
        summary["feedback_consumed"] += 1
        change = {"category": cat, "summary": fb[:60], "payload": fb.strip()}
        high = cat in HIGH_RISK or cat in downgraded
        if high:
            pid = "P-%s-%02d" % (today().strftime("%Y%m%d"), summary["new_proposals"] + 1)
            props_d.setdefault("proposals", []).append({
                "pid": pid, "risk": "high", "title": "依回饋調整：%s" % fb[:24],
                "diff_summary": "來自審核回饋，需人工判斷影響範圍：%s" % fb.strip(),
                "evidence": ["review %s feedback" % r.get("id"), "分類：%s%s" % (cat, "（7天內曾回滾→降級）" if cat in downgraded else "")],
                "status": "pending", "created_at": now_iso(), "decided_at": None,
            })
            summary["new_proposals"] += 1
        elif auto_budget > 0:
            if apply_low_risk(change):
                v = next_cfg_version(log)
                commit = None if args.dry_run else commit_config("%s: %s [risk:low] [auto]" % (v, change["summary"]))
                log_version(log, v, "low", True, ["(%s) %s" % (cat, change["payload"][:60])],
                            {"reviews": [r.get("id")], "metrics_window": metrics_window(metrics_d)}, commit=commit)
                auto_budget -= 1; summary["auto_changes"] += 1
                sys.stderr.write("⚙︎ 自動生效（%s）%s\n" % (cat, change["payload"][:40]))
        else:
            sys.stderr.write("⏸ 已達單日自動上限，%s 留待明日或轉提案\n" % cat)

    # 5) 吸收操控室的文案編輯 → 語氣學習（低風險自動；把你改後的句子當偏好範例）
    ce = load("copy_edits.json")
    absorbed = 0
    for e in ce.get("edits", []):
        if e.get("consumed"):
            continue
        for ed in e.get("edits", []):
            line = "- （語氣範例 %s，來自你對「%s」的修改）偏好寫法：%s" % (
                today().isoformat(), (e.get("post_id", "") or "")[:20], (ed.get("edited", "") or "").replace("\n", " ")[:120])
            if append_line(os.path.join(CONFIG, "style-notes.md"), line):
                absorbed += 1
        e["consumed"] = True
    if absorbed and not args.dry_run:
        v = next_cfg_version(log)
        commit = commit_config("%s: 吸收 %d 則文案語氣範例 [risk:low] [auto]" % (v, absorbed))
        log_version(log, v, "low", True, ["吸收操控室文案編輯的語氣範例 %d 則" % absorbed],
                    {"reviews": [], "metrics_window": None}, commit=commit)
        sys.stderr.write("✎ 吸收文案語氣範例 %d 則 → style-notes\n" % absorbed)
    summary["copy_absorbed"] = absorbed

    # 6) 成效回饋 → 選題/撰稿信號（讀 insights.json，最近有數據的貼文按互動率排序，高/低成效寫進 style-notes 供 looping 拆解）
    ins = load("insights.json").get("media", {})
    _posts_by_id = {p["id"]: p for p in load("posts.json").get("posts", [])}
    scored = []
    for mid, m in ins.items():
        snaps = m.get("snapshots", [])
        if not snaps:
            continue
        last = snaps[-1]; reach = last.get("reach", 0) or 0
        if reach < 30:  # 樣本太小不列入
            continue
        er = round((last.get("total_interactions", 0) or 0) / reach * 1000) / 10.0
        writer = (_posts_by_id.get(m.get("post_id") or "", {}) or {}).get("writer_model", "")
        label = (m.get("topic") or str(mid)[:10]) + ("（寫手 %s）" % ("GPT" if "gpt" in writer else "Claude") if writer else "")
        scored.append((er, label, last))
    if len(scored) >= 3 and not args.dry_run:
        scored.sort(reverse=True)
        top, bot = scored[0], scored[-1]
        perf_line = ("- （成效觀察 %s）高成效：「%s」互動率 %.1f%%（觸及 %d、分享 %d、追蹤+%d）；低成效：「%s」%.1f%%。"
                     "選題與撰稿向高成效模式靠攏，拆解其 hook／切角／情緒。" % (
                         today().isoformat(), top[1][:24], top[0], top[2].get("reach", 0), top[2].get("shares", 0),
                         top[2].get("follows", 0), bot[1][:24], bot[0]))
        if append_line(os.path.join(CONFIG, "style-notes.md"), perf_line):
            v = next_cfg_version(log)
            commit = commit_config("%s: 成效回饋 top/bottom 主題 [risk:low] [auto]" % v)
            log_version(log, v, "low", True, ["成效觀察：高「%s」%.1f%% / 低「%s」%.1f%%" % (top[1][:16], top[0], bot[1][:16], bot[0])],
                        {"reviews": [], "metrics_window": today().isoformat()}, commit=commit)
            sys.stderr.write("📊 成效回饋 → style-notes（高:%s %.1f%% / 低:%s %.1f%%）\n" % (top[1][:12], top[0], bot[1][:12], bot[0]))
            summary["perf_signal"] = 1

    if not args.dry_run:
        save("reviews.json", reviews_d)  # 註：consumed 由排程A處理發布後才標；此處僅 harness 記錄
        save("proposals.json", props_d)
        save("iterate_log.json", log)
        save("copy_edits.json", ce)
        # 把 data 變更也 commit（config 已在 commit_config 內處理）
        git("add", "data/proposals.json", "data/iterate_log.json", "data/copy_edits.json", check=False)
        if git("status", "--porcelain", "data", check=False).stdout.strip():
            git("commit", "-m", "iterate: 更新 proposals/log %s" % today().isoformat(), check=False)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.stderr.write("── 迭代摘要：回滾 %d｜套用提案 %d｜自動生效 %d｜新提案 %d｜消化回饋 %d ──\n" %
                     (summary["rollbacks"], summary["applied_proposals"], summary["auto_changes"], summary["new_proposals"], summary["feedback_consumed"]))


def metrics_window(metrics_d):
    days = sorted(set(e.get("published_at") for e in metrics_d.get("entries", []) if e.get("published_at")))
    return "%s–%s" % (days[0], days[-1]) if days else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="不改檔、不 commit，只印將發生的動作")
    run(ap.parse_args())
