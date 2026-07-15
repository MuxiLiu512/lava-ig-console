#!/usr/bin/env python3
# sync_console.py — 生產管線 ↔ 操控室 repo 的橋接（排程A 頭尾各呼叫一次）。
#
# 管線「開頭」：pull-reviews → 取未 consumed 的審核指令交給 pipeline 處理。
# 管線「結尾」：add-post → 產縮圖＋組 posts.json 條目；push → 推 data/ 與 assets/。
#            mark-consumed → 處理完的 review 標 true。
#
# 用法：
#   python3 sync_console.py pull-reviews                 # 印出未處理審核（JSON）
#   python3 sync_console.py add-post --manifest post.json
#   python3 sync_console.py mark-consumed R-abc R-def
#   python3 sync_console.py set-status <post_id> approved|published|rejected
#   python3 sync_console.py push "commit 訊息"
#
# 說明：本檔操作的是「工作副本」= 這個 repo 目錄本身。實際推送交給 push_files.sh
# （需 .sync.json）。排程可先 `git pull` 再呼叫，或用 push_files.sh 的 clone-overlay 模式。
import os, sys, json, argparse, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from _thumbs import make_thumb

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "data")
ASSETS = os.path.join(REPO, "assets")
CID = ["a", "b", "c", "d", "e"]


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── 開頭：取未處理審核 ───────────────────────────────────────────────
def pull_reviews(args):
    reviews = load("reviews.json").get("reviews", [])
    pending = [r for r in reviews if not r.get("consumed")]
    print(json.dumps({"pending": pending}, ensure_ascii=False, indent=2))
    # 供排程判讀的摘要走 stderr，不污染 stdout 的 JSON
    for r in pending:
        act = "核准發布" if r["decision"] == "approve" else ("退回底圖→只重生被退slide" if r.get("scope") == "base_image" else "退回排版→重跑渲染")
        sys.stderr.write("• %s | %s | choices=%s | %s\n" % (r["post_id"], act, r.get("slide_choices"), r.get("feedback", "")[:40]))


def mark_consumed(args):
    d = load("reviews.json")
    ids = set(args.ids)
    n = 0
    for r in d.get("reviews", []):
        if r.get("id") in ids and not r.get("consumed"):
            r["consumed"] = True; n += 1
    save("reviews.json", d)
    print("✓ 標記 consumed：%d 筆" % n)


def set_status(args):
    d = load("posts.json")
    for p in d.get("posts", []):
        if p["id"] == args.post_id:
            p["status"] = args.status
            print("✓ %s → %s" % (args.post_id, args.status)); break
    else:
        print("! 找不到貼文 %s" % args.post_id)
    save("posts.json", d)


# ── 結尾：組 posts.json 條目 ─────────────────────────────────────────
def add_post(args):
    """manifest 描述一篇已渲染貼文，產縮圖並 upsert 進 posts.json。
    manifest schema：見檔頭。final/candidates 的 src 為本機絕對路徑。"""
    with open(args.manifest, encoding="utf-8") as f:
        m = json.load(f)
    pid = m["id"]
    slides = []
    for s in m["slides"]:
        cands = []
        for i, c in enumerate(s.get("candidates", [])):
            if not os.path.exists(c["src"]):
                sys.stderr.write("  ! 缺候選圖 %s\n" % c["src"]); continue
            out = make_thumb(c["src"], os.path.join(ASSETS, pid, "slide-%d%s" % (s["n"], CID[i])))
            entry = {"cid": CID[i], "src": os.path.relpath(out, REPO).replace(os.sep, "/"), "kind": c.get("kind", "generated")}
            if c.get("source_label"):
                entry["source_label"] = c["source_label"]
            if c.get("prompt_hash"):
                entry["prompt_hash"] = c["prompt_hash"]
            cands.append(entry)
        final_src = None
        if s.get("final") and os.path.exists(s["final"]):
            fo = make_thumb(s["final"], os.path.join(ASSETS, pid, "final", "slide-%d" % s["n"]))
            final_src = os.path.relpath(fo, REPO).replace(os.sep, "/")
        slide = {"n": s["n"], "role": s.get("role", ""), "candidates": cands, "final_src": final_src}
        if cands:
            slide["default_cid"] = cands[0]["cid"]
        slides.append(slide)
    post = {
        "id": pid, "topic": m["topic"], "version": m.get("version", 1),
        "status": "awaiting_review", "clickup_task_id": m.get("clickup_task_id"),
        "created_at": m.get("created_at"), "caption": m.get("caption", ""),
        "topic_type": m.get("topic_type", "A-知識型"), "slides": slides,
    }
    d = load("posts.json")
    posts = d.setdefault("posts", [])
    posts[:] = [p for p in posts if p["id"] != pid]  # upsert
    posts.append(post)
    save("posts.json", d)
    print("✓ posts.json 已 upsert：%s（%d slides，%d 候選）" % (pid, len(slides), sum(len(s["candidates"]) for s in slides)))


def push(args):
    paths = ["data/posts.json", "data/reviews.json"]
    # 一併把新 assets 推上（保守起見推整個 assets）
    paths.append("assets")
    r = subprocess.run(["bash", os.path.join(REPO, "scripts", "push_files.sh"), args.message] + paths)
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description="Lava IG 操控室 同步工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull-reviews").set_defaults(func=pull_reviews)
    a = sub.add_parser("add-post"); a.add_argument("--manifest", required=True); a.set_defaults(func=add_post)
    a = sub.add_parser("mark-consumed"); a.add_argument("ids", nargs="+"); a.set_defaults(func=mark_consumed)
    a = sub.add_parser("set-status"); a.add_argument("post_id"); a.add_argument("status"); a.set_defaults(func=set_status)
    a = sub.add_parser("push"); a.add_argument("message"); a.set_defaults(func=push)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
