#!/usr/bin/env python3
"""卡彈偵測：自己找出停住的貼文，說清楚卡在哪、該做什麼，推 LINE 給 Jesse。

為什麼要有這支〔2026-09-01 Jesse：「能做 schedule tasks 確認有沒有卡彈的貼文嗎」〕：
  過去每次都是他自己看到不對，錄影、截圖、貼給我，我才開始查。
  這條路徑的問題不是慢，是「沒被看到的就不存在」——白夜行卡了 6 天，
  是他剛好點進去才發現。偵測應該是系統的責任，不是使用者的。

  每一種卡法都對應一個已經發生過的事故，註記在 CHECKS 裡。
  新的卡法出現時加一條，不要寫成通用的「超過 N 小時就報」——
  那種報警沒有下一步，等於噪音。

用法：
  python3 scripts/stuck_check.py            # 檢查並在有問題時推 LINE
  python3 scripts/stuck_check.py --dry      # 只印報告
  python3 scripts/stuck_check.py --post ID  # 只診斷一篇（操控台按鈕觸發用）
"""
import os, sys, json, argparse, datetime, importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

# 門檻：每個都對應真實事故，不是拍腦袋的數字
SLA_DRAFT_MIN = 45        # 放行 → 入板（排程 15 分 + 撰稿 7 分 + 入板輪 10 分）
SLA_FORAGE_H = 6          # 入板 → 補完圖（每輪補 2 篇，積壓時會慢）
SLA_REVIEW_D = 3          # 等你審超過 3 天＝你可能沒看到，不是你不想審
SLA_RENDER_H = 2          # 核准 → 出成品
SLA_SCHED_H = 2           # 排程時間過了還沒發＝WF10 出事


def _age_h(iso):
    if not iso:
        return None
    try:
        return (datetime.datetime.now().astimezone()
                - datetime.datetime.fromisoformat(iso)).total_seconds() / 3600
    except Exception:
        return None


def diagnose(posts, ideas, only=None):
    """回傳 [(嚴重度, 標題, 卡在哪, 下一步)]。嚴重度：bad / warn。"""
    out = []
    ids = set()
    for p in posts:
        ids.add(p["id"])
        if p.get("clickup_task_id"):
            ids.add(p["clickup_task_id"])

    # 1) 放行了但稿沒進來〔2026-08-24 事故：放行後 19 小時無聲無息〕
    for i in ideas:
        if i.get("decision") != "approve":
            continue
        tid = i.get("task_id") or i.get("id")
        if tid in ids:
            continue                       # 已入板（用 id 比對，不用主題字串）
        if only and tid != only:
            continue
        h = _age_h(i.get("decided_at"))
        if h and h * 60 > SLA_DRAFT_MIN:
            out.append(("bad" if h > 3 else "warn",
                        (i.get("title") or tid)[:40],
                        "放行後 %.0f 小時稿還沒進來（正常 %d 分）" % (h, SLA_DRAFT_MIN),
                        "到工作台按「重跑撰稿」，或查 n8n WF01 執行紀錄"))

    for p in posts:
        if only and p["id"] != only:
            continue
        st = p.get("status")
        title = (p.get("topic") or p["id"])[:40]
        since = p.get("status_since") or p.get("created_at") or p.get("rendered_at")

        # 2) 缺圖太久〔2026-08-25 事故：七篇掛在缺料，補圖每輪都在跑、每輪都白跑〕
        if st in ("awaiting_review", "approved"):
            miss = [s.get("n") for s in p.get("slides", [])
                    if SC._lacks_material(s)] if hasattr(SC, "_lacks_material") else [
                    s.get("n") for s in p.get("slides", [])
                    if not (s.get("candidates") or s.get("final_src") or s.get("public_url"))
                    and "CTA" not in str(s.get("role", ""))
                    and str(s.get("product_layout") or "") not in ("diagram", "price", "cta")]
            h = _age_h(since)
            if miss and h and h > SLA_FORAGE_H:
                out.append(("bad" if h > 24 else "warn", title,
                            "第 %s 張缺圖已 %.0f 小時" % ("、".join(map(str, miss)), h),
                            "工作台按「重新生成這篇」，或審稿台改用純文字卡"))

        # 3) 等你審太久（這條是提醒你，不是系統故障）
        if st == "awaiting_review":
            h = _age_h(since)
            if h and h / 24 > SLA_REVIEW_D:
                out.append(("warn", title, "等你審已 %.0f 天" % (h / 24),
                            "到審稿台審它，或退回重做"))

        # 4) 核准了卻沒出成品〔render-approved 沒跑或渲染失敗〕
        if st == "approved" and not p.get("render_note"):
            h = _age_h(p.get("approved_at") or since)
            done = all(s.get("public_url") for s in p.get("slides", []) if s.get("candidates"))
            if h and h > SLA_RENDER_H and not done:
                out.append(("bad", title, "核准後 %.0f 小時還沒出成品" % h,
                            "查哨兵日誌的 render-approved 是否報錯"))

        # 5) 排程時間過了還沒發〔WF10 或 IG token 出事，最貴的一種〕
        if st == "scheduled" and p.get("publish_at"):
            h = _age_h(p["publish_at"])
            if h and h > SLA_SCHED_H:
                out.append(("bad", title, "排定時間已過 %.0f 小時仍未發佈" % h,
                            "查 n8n WF10 執行紀錄與 IG token 是否過期"))

        # 6b) 已排程卻違反閘門〔2026-09-01：Laa 篇帶著視覺 block 排進明晚發佈〕
        if st == "scheduled":
            ovk = {o.get("key") for o in (p.get("gate_overrides") or [])}
            bl = []
            for gate, key in (("fact", "fact"), ("qa", "qa")):
                for idx, i in enumerate((p.get(gate) or {}).get("issues", [])):
                    if (i.get("severity") or i.get("sev")) == "block" and \
                       key + ":" + str(i.get("line") or i.get("detail") or idx)[:60] not in ovk:
                        bl.append(i)
            if bl:
                out.append(("bad", title,
                            "已排程（%s）但閘門有 %d 項未過" % (str(p.get("publish_at"))[:16], len(bl)),
                            "到審稿台處理或取消排程，否則到點會照發"))

        # 6) 渲染卡住的明確標記
        if p.get("render_note") and st != "published":
            out.append(("bad", title, "排版卡住：%s" % str(p["render_note"])[:60],
                        "到審稿台看該篇，多半要換圖或改字"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--post", default=None)
    a = ap.parse_args()
    posts = SC.load("posts.json").get("posts", [])
    try:
        ideas = SC.load("ideas.json").get("ideas", [])
    except FileNotFoundError:
        ideas = []
    rows = diagnose(posts, ideas, only=a.post)
    if not rows:
        print("✓ 沒有卡住的貼文")
        return
    bad = [r for r in rows if r[0] == "bad"]
    print("卡彈 %d 件（嚴重 %d）：" % (len(rows), len(bad)))
    for sev, title, where, todo in rows:
        print("  %s %s\n     卡在：%s\n     下一步：%s" % ("⛔" if sev == "bad" else "⚠", title, where, todo))
    if a.dry:
        print("\n--dry：未推播")
        return
    # 只有「嚴重」才推播——警告級每天都可能有幾件，天天推會變成沒人看的噪音
    if not bad:
        print("（只有警告級，不推播）")
        return
    lines = ["⚠ 產線卡彈 %d 件（嚴重 %d）：" % (len(rows), len(bad)), ""]
    for sev, title, where, todo in bad[:6]:
        lines += ["• %s" % title, "  卡在：%s" % where, "  下一步：%s" % todo, ""]
    if len(bad) > 6:
        lines.append("…另外還有 %d 件" % (len(bad) - 6))
    lines.append("操控台：https://muxiliu512.github.io/lava-ig-console/")
    try:
        SC._line_notify("\n".join(lines))
        print("\n✓ 已推 LINE")
    except Exception as e:
        print("\n! LINE 推播失敗：%s" % e)


if __name__ == "__main__":
    main()
