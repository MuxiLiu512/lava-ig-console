#!/usr/bin/env python3
"""禁句自動修：機械規則造成的違規，用機械方式修掉。

為什麼可以自動修〔Jesse 2026-08-27：要一天發三篇〕：
  排程瓶頸不在排程器，在閘門——10 篇待發稿裡 7 篇卡在文案禁句，
  合計 44 個破折號。整篇退回重寫要 6 分鐘＋一次模型額度，
  但「把破折號換成句號或冒號」是純字串操作，沒有任何判斷成分。

  只修「改法唯一」的規則。判斷性的（赦免式安慰、AI 腔）一律不碰，
  留給人或重寫——自動改寫語意是在製造新的問題。

修法：
  A—B  → 若 B 是轉折（但／而／卻）：刪破折號，前句收句號
        → 否則：破折號換成冒號（多為「概念—解釋」結構）
  行尾破折號 → 直接刪

改完會重跑 copy_check 驗證，並把原文備份進 copy_fix_log.jsonl 以便回溯。
"""
import os, re, json, argparse, importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)
_spec2 = importlib.util.spec_from_file_location("cc", os.path.join(_HERE, "copy_check.py"))
CC = importlib.util.module_from_spec(_spec2); _spec2.loader.exec_module(CC)

TURN = "但而卻只是就才卻反而其實"


def fix_dash(t):
    if not t:
        return t, 0
    n = 0
    def rep(m):
        nonlocal n
        n += 1
        nxt = m.group(1)
        if not nxt:
            return ""                       # 行尾破折號直接刪
        if nxt[0] in TURN:
            return "。" if m.group(0)[0] not in "，、" else "，"
        return "："
    out = re.sub(r"——\s*(.?)", lambda m: rep(m) + (m.group(1) or ""), t)
    out = re.sub(r"。\s*。", "。", out)
    out = re.sub(r"[，。：]\s*$", lambda m: m.group(0).strip(), out)
    return out, n


def fix_post(p):
    changed = 0
    before = {"topic": p.get("topic"), "caption": p.get("caption"),
              "slides": [(s.get("heading"), s.get("display_copy")) for s in p.get("slides", [])]}
    t, n = fix_dash(p.get("topic")); p["topic"] = t; changed += n
    c, n = fix_dash(p.get("caption")); p["caption"] = c; changed += n
    for s in p.get("slides", []):
        h, n = fix_dash(s.get("heading")); s["heading"] = h; changed += n
        d, n = fix_dash(s.get("display_copy")); s["display_copy"] = d; changed += n
    return changed, before


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    doc = SC.load("posts.json")
    total, touched = 0, 0
    log = []
    for p in doc.get("posts", []):
        if a.post and p["id"] != a.post:
            continue
        if p.get("status") in ("published", "scheduled"):
            continue
        pre = CC.check_post(p)
        dash = pre["counts"].get("破折號", 0)
        if not dash:
            continue
        n, before = fix_post(p)
        post = CC.check_post(p)
        p["copy"] = post
        left = post["counts"].get("破折號", 0)
        print("%-32s 破折號 %d → %d%s" % (p["id"][:32], dash, left,
              "  ⚠ 仍有殘留" if left else ""))
        other = {k: v for k, v in post["counts"].items() if k != "破折號"}
        if other:
            print("     其餘需人工：%s" % other)
        log.append({"post_id": p["id"], "ts": SC._now_iso(), "fixed": n, "before": before})
        total += n; touched += 1
    if a.dry:
        print("\n--dry：未寫檔（%d 篇、%d 處）" % (touched, total)); return
    if touched:
        SC.save("posts.json", doc)
        fp = os.path.join(SC.DATA, "copy_fix_log.jsonl")
        with open(fp, "a", encoding="utf-8") as f:
            for r in log:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("\n✓ 已修 %d 篇、%d 處；原文備份在 data/copy_fix_log.jsonl" % (touched, total))
    else:
        print("沒有需要修的破折號")


if __name__ == "__main__":
    main()
