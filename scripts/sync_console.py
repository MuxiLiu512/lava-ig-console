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
#   python3 sync_console.py from-drive [--topic 母胎] [--finals-dir DIR]  # 掃 Drive 產出/ 最新一篇
#   python3 sync_console.py mark-consumed R-abc R-def
#   python3 sync_console.py set-status <post_id> approved|published|rejected
#   python3 sync_console.py push "commit 訊息"
#
# 說明：本檔操作的是「工作副本」= 這個 repo 目錄本身。實際推送交給 push_files.sh
# （需 .sync.json）。排程可先 `git pull` 再呼叫，或用 push_files.sh 的 clone-overlay 模式。
import os, sys, json, re, glob, argparse, subprocess, unicodedata
sys.path.insert(0, os.path.dirname(__file__))
from _thumbs import make_thumb

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "data")
ASSETS = os.path.join(REPO, "assets")
DOCS = os.path.join(REPO, "docs")
# Pages 服務 /docs 於站根：docs/finals/<pid>/slide-N.jpg → 下面這個公開 URL，供 IG /media 抓圖
GH_PAGES = "https://muxiliu512.github.io/lava-ig-console"
IG_LONG_EDGE = 1350  # IG 4:5 顯示上限 1080×1350；成品降到此尺寸當公開圖（IG 反正會再壓）
CID = ["a", "b", "c", "d", "e", "f"]
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# Drive 產出資料夾（service@lava.tw 掛載）。--drive-root 可覆寫。
DRIVE_PRODUCE = ("/Users/mimo/Library/CloudStorage/GoogleDrive-service@lava.tw/"
                 "My Drive/Lava INC. Assets/02_Marketing/98_Lava-IG-AI產文系統/產出")

_SUFFIX = ["文案初稿易讀版", "文案初稿", "劇照候選", "劇情畫格", "底圖", "seedream",
           "易讀版", "端到端測試", "v2", "v5", "v1", "(1)", "（1）"]


def _norm_topic(s):
    """去日期前綴、已知後綴、標點空白 → 核心主題字串，供模糊比對。"""
    s = os.path.splitext(s)[0]
    s = re.sub(r"^\d{6,8}[-\s]*", "", s)
    for suf in _SUFFIX:
        s = s.replace(suf, "")
    s = re.sub(r"[\s\-_（）()「」【】、，。？?！!v0-9]", "", s)
    return unicodedata.normalize("NFC", s).strip()


def _topic_match(ntopic, name):
    a, b = ntopic, _norm_topic(name)
    if not a or not b:
        return False
    short, long = sorted([a, b], key=len)
    return short[:6] in long or long[:6] in short


def _still_label(fn):
    """slide1-TheOffice-2.jpg → 'The Office'（駝峰拆詞）。取不到回 None。"""
    m = re.match(r"slide-?\d+[-_ ]+(.+?)([-_ ]\d+)?\.\w+$", fn, re.I)
    if not m:
        return None
    core = m.group(1)
    core = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", core)      # HaveI → Have I
    core = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", core)  # IEver → I Ever
    return core.replace("_", " ").strip() or None


def _slug(s):
    return re.sub(r"[^0-9A-Za-z一-鿿]+", "", s)[:24] or "post"


def _assemble_caption(data):
    """從文案 JSON 組 IG caption：hook + 品牌段 + hashtags。"""
    slides = data.get("slides", [])
    def body_of(pred):
        for s in slides:
            if pred(s):
                return (s.get("display_copy") or s.get("body") or "").replace("\n", " ").strip()
        return ""
    hook = body_of(lambda s: s.get("index") == 1 or "hook" in str(s.get("role", "")).lower())
    brand = body_of(lambda s: "品牌" in str(s.get("role", "")) or "立場" in str(s.get("role", "")))
    tags = data.get("hashtags", [])
    tagline = " ".join(t if t.startswith("#") else "#" + t for t in tags)
    parts = [p for p in [hook, brand, tagline] if p]
    return "\n\n".join(parts)


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


# ── Phase 2 寫回：操控室審核結果 → ClickUp 卡片狀態（單一狀態真相） ──────
# 對應「一張卡走到底」：核准→待排版、退回→退回重生，回饋寫成卡片留言。
# 需 .sync.json 內含 clickup_token（ClickUp Settings → Apps → API Token）。
CLICKUP_STATUS = {
    ("approve", None): "待排版",
    ("reject", "base_image"): "退回重生",
    ("reject", "mockup"): "退回重生",
}


def _read_sync():
    p = os.path.join(REPO, ".sync.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _clickup(method, path, token, body=None):
    import urllib.request
    req = urllib.request.Request(
        "https://api.clickup.com/api/v2" + path, method=method,
        headers={"Authorization": token, "Content-Type": "application/json"},
        data=json.dumps(body).encode("utf-8") if body else None)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def apply_reviews(args):
    """讀未回寫的審核 → 改對應 ClickUp 卡片狀態＋留回饋，標 clickup_synced。
    與 pipeline 的 consumed 分開（那個管重生），本旗標只管 ClickUp 狀態回寫。"""
    token = _read_sync().get("clickup_token")
    reviews = load("reviews.json")
    posts = {p["id"]: p for p in load("posts.json").get("posts", [])}
    todo = [r for r in reviews.get("reviews", []) if not r.get("clickup_synced")]
    if not todo:
        print("無待回寫審核"); return
    for r in todo:
        post = posts.get(r["post_id"]) or {}
        cid = post.get("clickup_task_id")
        status = CLICKUP_STATUS.get((r.get("decision"), r.get("scope")))
        line = "%s → 卡片 %s → %s" % (r["post_id"], cid, status)
        if args.dry_run or not token or not cid or not status:
            reason = "dry-run" if args.dry_run else ("缺 clickup_token" if not token else ("缺 clickup_task_id" if not cid else "無對應狀態"))
            print("(%s) %s" % (reason, line)); continue
        _clickup("PUT", "/task/" + cid, token, {"status": status})
        if r.get("decision") == "approve":
            msg = "✅ 操控室核准（選圖 %s）。狀態→待排版，準備渲染排程。" % r.get("slide_choices", {})
        else:
            where = "底圖" if r.get("scope") == "base_image" else "排版"
            msg = "↩ 操控室退回%s：%s（狀態→退回重生）" % (where, r.get("feedback", ""))
        _clickup("POST", "/task/" + cid + "/comment", token, {"comment_text": msg, "notify_all": True})
        r["clickup_synced"] = True
        print("✓ " + line)
    if not args.dry_run:
        save("reviews.json", reviews)


# ── 結尾：組 posts.json 條目 ─────────────────────────────────────────
def add_post(args):
    """讀 manifest 檔（見檔頭 schema），產縮圖並 upsert 進 posts.json。"""
    with open(args.manifest, encoding="utf-8") as f:
        m = json.load(f)
    _build_and_write(m)


def _build_and_write(m):
    """manifest dict → 縮圖 + posts.json upsert。final/candidates 的 src 為本機絕對路徑。"""
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
        public_url = None
        if s.get("final") and os.path.exists(s["final"]):
            fo = make_thumb(s["final"], os.path.join(ASSETS, pid, "final", "slide-%d" % s["n"]))
            final_src = os.path.relpath(fo, REPO).replace(os.sep, "/")
            public_url = _publish_final(s["final"], pid, s["n"])  # 全圖公開版供 IG 發佈
        slide = {"n": s["n"], "role": s.get("role", ""), "candidates": cands, "final_src": final_src}
        if public_url:
            slide["public_url"] = public_url
        if s.get("heading"):
            slide["heading"] = s["heading"]
        if s.get("display_copy"):
            slide["display_copy"] = s["display_copy"]
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
    old = next((p for p in posts if p["id"] == pid), None)
    if old and old.get("status") == "scheduled":  # 已排程者不被重餵洗掉排程
        post["status"] = "scheduled"
        if old.get("publish_at"):
            post["publish_at"] = old["publish_at"]
    posts[:] = [p for p in posts if p["id"] != pid]  # upsert
    posts.append(post)
    save("posts.json", d)
    print("✓ posts.json 已 upsert：%s（%d slides，%d 候選）" % (pid, len(slides), sum(len(s["candidates"]) for s in slides)))


def _publish_final(src, pid, n):
    """成品全圖 → IG 可抓的公開 JPEG（docs/finals/<pid>/slide-N.jpg，Pages 公開）。回傳公開 URL 或 None。"""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        outdir = os.path.join(DOCS, "finals", pid)
        os.makedirs(outdir, exist_ok=True)
        im = Image.open(src).convert("RGB")
        w, h = im.size
        scale = min(1.0, IG_LONG_EDGE / max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        im.save(os.path.join(outdir, "slide-%d.jpg" % n), "JPEG", quality=90, optimize=True)
    except Exception as e:
        sys.stderr.write("  ! 公開圖產生失敗 slide-%d：%s\n" % (n, e))
        return None
    from urllib.parse import quote
    return "%s/finals/%s/slide-%d.jpg" % (GH_PAGES, quote(pid), n)


def _collect_slide_imgs(dirs, kind):
    """從資料夾（遞迴）蒐集 slide-N 圖片 → {n: [(path, label)]}。"""
    out = {}
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
            fn = os.path.basename(f)
            if not fn.lower().endswith(IMG_EXT):
                continue
            mm = re.search(r"slide-?(\d+)", fn, re.I)
            if not mm:
                continue
            label = _still_label(fn) if kind == "still" else None
            out.setdefault(int(mm.group(1)), []).append((f, label))
    return out


def from_drive(args):
    """掃 Drive 產出/ 的最新一篇（文案 json + 底圖 + 劇照候選）→ 組 manifest → upsert posts.json。
    finals（成品）若未產出可留空；操控室 Mockup 會退回顯示選中的候選底圖。"""
    root = args.drive_root or DRIVE_PRODUCE
    if not os.path.isdir(root):
        sys.exit("✗ 找不到 Drive 產出資料夾：%s（確認 Google Drive 已掛載，或用 --drive-root 指定）" % root)
    jsons = [f for f in glob.glob(os.path.join(root, "*.json"))
             if "文案" in os.path.basename(f) and "ZZ" not in os.path.basename(f) and "易讀版" not in os.path.basename(f)]
    if args.topic:
        jsons = [f for f in jsons if args.topic in os.path.basename(f)]
    if not jsons:
        sys.exit("✗ 產出/ 內找不到符合的文案 JSON" + ("（topic=%s）" % args.topic if args.topic else ""))
    datekey = lambda f: (re.match(r"(\d{6,8})", os.path.basename(f)) or [None, "0"])[1] if re.match(r"(\d{6,8})", os.path.basename(f)) else "0"
    jf = sorted(jsons, key=lambda f: (datekey(f), os.path.getmtime(f)))[-1]
    with open(jf, encoding="utf-8") as f:
        data = json.load(f)
    base = os.path.basename(jf)
    date = (re.match(r"(\d{6,8})", base) or [None, ""])[1] if re.match(r"(\d{6,8})", base) else ""
    topic_raw = re.sub(r"-?文案初稿.*$", "", re.sub(r"^\d{6,8}[-\s]*", "", os.path.splitext(base)[0]))
    ntopic = _norm_topic(base)
    sys.stderr.write("→ 選中文案：%s（主題核心=%s）\n" % (base, ntopic))

    subdirs = [d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d) and "ZZ" not in os.path.basename(d)]
    base_dirs = [d for d in subdirs if "底圖" in os.path.basename(d) and _topic_match(ntopic, os.path.basename(d))]
    still_dirs = [d for d in subdirs if "劇照" in os.path.basename(d) and _topic_match(ntopic, os.path.basename(d))]
    sys.stderr.write("→ 底圖資料夾 %d 個、劇照資料夾 %d 個\n" % (len(base_dirs), len(still_dirs)))
    gen = _collect_slide_imgs(base_dirs, "generated")
    still = _collect_slide_imgs(still_dirs, "still")

    slides = []
    for s in data.get("slides", []):
        n = s.get("index")
        cands = []
        for path, _ in gen.get(n, []):
            cands.append({"src": path, "kind": "generated"})
        for path, label in still.get(n, []):
            c = {"src": path, "kind": "still"}
            if label:
                c["source_label"] = label
            cands.append(c)
        final = None
        if args.finals_dir:
            for ext in (".png", ".jpg", ".webp"):
                fp = os.path.join(args.finals_dir, "final-%02d%s" % (n, ext))
                if os.path.exists(fp):
                    final = fp; break
        slides.append({"n": n, "role": str(s.get("role", "")), "final": final, "candidates": cands,
                       "heading": s.get("heading", ""), "display_copy": s.get("display_copy", "")})

    pid = args.post_id or ("%s-%s" % (date or "draft", _slug(ntopic)))
    m = {"id": pid, "topic": topic_raw, "version": args.version,
         "clickup_task_id": args.clickup, "created_at": None,
         "caption": _assemble_caption(data), "topic_type": args.topic_type, "slides": slides}
    ncand = sum(len(s["candidates"]) for s in slides)
    if ncand == 0:
        sys.stderr.write("⚠ 未匹配到任何候選圖——請檢查底圖/劇照資料夾命名是否含主題關鍵字，或用 add-post 手動 manifest。\n")
    _build_and_write(m)


def push(args):
    paths = ["data/posts.json", "data/reviews.json"]
    # 一併把新 assets 推上（保守起見推整個 assets）
    paths.append("assets")
    paths.append("docs/finals")  # IG 公開圖（Pages 服務，供 workflow 10 發佈抓圖）
    r = subprocess.run(["bash", os.path.join(REPO, "scripts", "push_files.sh"), args.message] + paths)
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description="Lava IG 操控室 同步工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull-reviews").set_defaults(func=pull_reviews)
    a = sub.add_parser("add-post"); a.add_argument("--manifest", required=True); a.set_defaults(func=add_post)
    a = sub.add_parser("from-drive", help="掃 Drive 產出/ 最新一篇，組 posts.json")
    a.add_argument("--drive-root", help="覆寫 Drive 產出資料夾路徑")
    a.add_argument("--topic", help="只選檔名含此字串的文案")
    a.add_argument("--post-id", help="覆寫貼文 id（預設 日期-主題）")
    a.add_argument("--finals-dir", help="成品資料夾（有 final-0N.png 時填，供 Mockup）")
    a.add_argument("--version", type=int, default=1)
    a.add_argument("--clickup", default=None)
    a.add_argument("--topic-type", default="A-知識型")
    a.set_defaults(func=from_drive)
    a = sub.add_parser("mark-consumed"); a.add_argument("ids", nargs="+"); a.set_defaults(func=mark_consumed)
    a = sub.add_parser("set-status"); a.add_argument("post_id"); a.add_argument("status"); a.set_defaults(func=set_status)
    a = sub.add_parser("apply-reviews", help="操控室審核 → ClickUp 卡片狀態回寫"); a.add_argument("--dry-run", action="store_true"); a.set_defaults(func=apply_reviews)
    a = sub.add_parser("push"); a.add_argument("message"); a.set_defaults(func=push)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
