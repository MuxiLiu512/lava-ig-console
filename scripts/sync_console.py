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
import os, sys, json, re, glob, argparse, subprocess, unicodedata, shutil, datetime
sys.path.insert(0, os.path.dirname(__file__))
from _thumbs import make_thumb

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "data")
ASSETS = os.path.join(REPO, "assets")
DOCS = os.path.join(REPO, "docs")
# Pages 服務 /docs 於站根：docs/finals/<pid>/slide-N.jpg → 下面這個公開 URL，供 IG /media 抓圖
GH_PAGES = "https://muxiliu512.github.io/lava-ig-console"
IG_LONG_EDGE = 1350  # IG 4:5 顯示上限 1080×1350；成品降到此尺寸當公開圖（IG 反正會再壓）
CID = list("abcdefghijkl")  # 單 slide 候選上限 12（重寫輪會累加新舊資料夾的圖）
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


def _now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat() + "+08:00"


# cid→原圖絕對路徑 對照表（本機限定、git-ignored）。渲染時據此取 PT 選定的候選原檔。
LOCAL_SOURCES = os.path.join(DATA, ".local_sources.json")


def _load_local_sources():
    if os.path.exists(LOCAL_SOURCES):
        with open(LOCAL_SOURCES, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_local_sources(d):
    with open(LOCAL_SOURCES, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def _flat_image(path, thresh=8.0):
    """近純色圖（生圖失敗的色塊，如整片藍）→ True。無法讀取也視為壞圖。"""
    try:
        from PIL import Image, ImageStat
        im = Image.open(path).convert("RGB").resize((48, 48))
        return max(ImageStat.Stat(im).stddev) < thresh
    except Exception:
        return True


def _latest_copy_edits(pid, ce_list):
    """操控室文案編輯 → 每個 (slide n, 欄位) 取最新一筆 edited 值。"""
    out = {}
    for e in sorted([e for e in ce_list if e.get("post_id") == pid], key=lambda e: e.get("ts", "")):
        for ed in e.get("edits", []):
            try:
                out[(int(ed["n"]), ed["field"])] = ed.get("edited", "")
            except (KeyError, ValueError, TypeError):
                continue
    return out


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


def reconcile_published(args):
    """對帳：把 ClickUp 已標『已發布』的排程貼文，在 posts.json 也翻成 published。
    補 workflow 10（n8n 無 repo 寫入權）發佈後 posts.json 不會自動翻狀態的缺口。排程 3×/日跑。"""
    token = _read_sync().get("clickup_token")
    if not token:
        print("缺 clickup_token，略過對帳"); return
    if not token.isascii():
        print("clickup_token 疑似 placeholder（含非 ASCII）→ 略過。請在 .sync.json 換成真正的 ClickUp API token（Settings → Apps → API Token）"); return
    def _norm(s):
        return (s or "").strip().replace("佈", "布")
    d = load("posts.json")
    n = 0
    for p in d.get("posts", []):
        if p.get("status") != "scheduled" or not p.get("clickup_task_id"):
            continue
        try:
            task = _clickup("GET", "/task/" + p["clickup_task_id"], token)
        except Exception as e:
            sys.stderr.write("  ! 查 ClickUp 卡 %s 失敗：%s\n" % (p["clickup_task_id"], e)); continue
        if _norm((task.get("status") or {}).get("status")) == "已發布":
            p["status"] = "published"
            p.setdefault("published_at", p.get("publish_at"))
            n += 1
            print("✓ %s → published（ClickUp 已發布）" % p["id"])
    if n and not args.dry_run:
        save("posts.json", d)
    print("對帳完成：翻 %d 篇%s" % (n, "（dry-run 未寫）" if args.dry_run else ""))


# ── 結尾：組 posts.json 條目 ─────────────────────────────────────────
def add_post(args):
    """讀 manifest 檔（見檔頭 schema），產縮圖並 upsert 進 posts.json。"""
    with open(args.manifest, encoding="utf-8") as f:
        m = json.load(f)
    _build_and_write(m)


def _build_and_write(m):
    """manifest dict → 縮圖 + posts.json upsert。final/candidates 的 src 為本機絕對路徑。
    同時把 cid→原圖路徑 寫進 .local_sources.json（渲染時取 PT 選定原檔用）。"""
    pid = m["id"]
    slides = []
    srcmap = {}
    for s in m["slides"]:
        cands = []
        for i, c in enumerate(s.get("candidates", [])):
            if i >= len(CID):
                sys.stderr.write("  ! slide %d 候選超過 %d 張，其餘截斷（清舊資料夾可減量）\n" % (s["n"], len(CID))); break
            if not os.path.exists(c["src"]):
                sys.stderr.write("  ! 缺候選圖 %s\n" % c["src"]); continue
            out = make_thumb(c["src"], os.path.join(ASSETS, pid, "slide-%d%s" % (s["n"], CID[i])))
            entry = {"cid": CID[i], "src": os.path.relpath(out, REPO).replace(os.sep, "/"), "kind": c.get("kind", "generated")}
            if c.get("source_label"):
                entry["source_label"] = c["source_label"]
            if c.get("prompt_hash"):
                entry["prompt_hash"] = c["prompt_hash"]
            cands.append(entry)
            srcmap.setdefault(str(s["n"]), {})[CID[i]] = os.path.abspath(c["src"])
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
    # 操控室的文案編輯覆蓋（重餵不洗掉 PT 改過的字）
    try:
        edits = _latest_copy_edits(pid, load("copy_edits.json").get("edits", []))
        for sl in slides:
            for field in ("heading", "display_copy"):
                if (sl["n"], field) in edits:
                    sl[field] = edits[(sl["n"], field)]
    except FileNotFoundError:
        pass
    post = {
        "id": pid, "topic": m["topic"], "version": m.get("version", 1),
        "status": "awaiting_review", "clickup_task_id": m.get("clickup_task_id"),
        "created_at": m.get("created_at"), "caption": m.get("caption", ""),
        "topic_type": m.get("topic_type", "A-知識型"), "slides": slides,
    }
    d = load("posts.json")
    posts = d.setdefault("posts", [])
    old = next((p for p in posts if p["id"] == pid), None)
    if old and old.get("status") in ("approved", "scheduled", "published"):  # 已核准/已排程/已發佈者不被重餵洗掉
        post["status"] = old["status"]
    if old:
        for k in ("publish_at", "published_at", "media_id", "rendered_at", "candidates_since"):
            if old.get(k):
                post[k] = old[k]
    # 候選圖序列變動 → 舊審核的選圖失效：記 candidates_since；未出成品的 approved 退回待審
    _sig = lambda ss: [(s.get("n"), tuple((c.get("cid"), c.get("kind")) for c in s.get("candidates", []))) for s in ss]
    if old and _sig(old.get("slides", [])) != _sig(slides):
        post["candidates_since"] = _now_iso()
        if post.get("status") == "approved" and not any(s.get("final_src") for s in slides):
            post["status"] = "awaiting_review"
            sys.stderr.write("  ↩ 候選圖已更新，%s 由 approved 退回待審（請重新選圖核准）\n" % pid)
    posts[:] = [p for p in posts if p["id"] != pid]  # upsert
    posts.append(post)
    save("posts.json", d)
    ls = _load_local_sources()
    ls[pid] = {"draft_json": m.get("_draft_json"), "topic": m.get("topic", ""), "sources": srcmap}
    _save_local_sources(ls)
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


def _collect_slide_imgs(dirs, kind, prune=True):
    """從資料夾（遞迴）蒐集 slide-N 圖片 → {n: [(path, label)]}。
    prune=True 時剔除近純色破圖（生圖失敗）；重建舊貼文 cid 對照時須 prune=False 以復刻原始序列。"""
    out = {}
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
            fn = os.path.basename(f)
            if not fn.lower().endswith(IMG_EXT):
                continue
            mm = re.search(r"slide-?(\d+)", fn, re.I)
            if not mm:
                continue
            if prune and _flat_image(f):
                sys.stderr.write("  ✂ 剔除疑似破圖（近純色）：%s\n" % fn)
                continue
            label = _still_label(fn) if kind == "still" else None
            out.setdefault(int(mm.group(1)), []).append((f, label))
    return out


def _scan_dirs(root, ntopic, prune=True):
    """依主題掃 Drive 產出/ 的底圖與劇照資料夾 → (gen, still) 兩個 {n: [(path,label)]}。"""
    subdirs = [d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d) and "ZZ" not in os.path.basename(d)]
    base_dirs = [d for d in subdirs if "底圖" in os.path.basename(d) and _topic_match(ntopic, os.path.basename(d))]
    still_dirs = [d for d in subdirs if "劇照" in os.path.basename(d) and _topic_match(ntopic, os.path.basename(d))]
    return _collect_slide_imgs(base_dirs, "generated", prune), _collect_slide_imgs(still_dirs, "still", prune)


def from_drive(args):
    """掃 Drive 產出/ 的最新一篇（文案 json + 底圖 + 劇照候選）→ 組 manifest → upsert posts.json。
    finals（成品）若未產出可留空；操控室 Mockup 會退回顯示選中的候選底圖。"""
    root = args.drive_root or DRIVE_PRODUCE
    if not os.path.isdir(root):
        sys.exit("✗ 找不到 Drive 產出資料夾：%s（確認 Google Drive 已掛載，或用 --drive-root 指定）" % root)
    if getattr(args, "json", None):
        jf = args.json
        if not os.path.exists(jf):
            sys.exit("✗ 指定的文案 JSON 不存在：%s" % jf)
        # 主題資訊改由 --topic（或檔名）推導；日期由 --post-id 前綴或今天
        base = os.path.basename(args.topic_base or jf) if getattr(args, "topic_base", None) else os.path.basename(jf)
    else:
        jsons = [f for f in glob.glob(os.path.join(root, "*.json"))
                 if "文案" in os.path.basename(f) and "ZZ" not in os.path.basename(f) and "易讀版" not in os.path.basename(f)]
        if args.topic:
            jsons = [f for f in jsons if args.topic in os.path.basename(f)]
        if not jsons:
            sys.exit("✗ 產出/ 內找不到符合的文案 JSON" + ("（topic=%s）" % args.topic if args.topic else ""))
        datekey = lambda f: (re.match(r"(\d{6,8})", os.path.basename(f)) or [None, "0"])[1] if re.match(r"(\d{6,8})", os.path.basename(f)) else "0"
        jf = sorted(jsons, key=lambda f: (datekey(f), os.path.getmtime(f)))[-1]
        base = os.path.basename(jf)
    with open(jf, encoding="utf-8") as f:
        data = json.load(f)
    date = (re.match(r"(\d{6,8})", base) or [None, ""])[1] if re.match(r"(\d{6,8})", base) else ""
    topic_raw = re.sub(r"-?文案初稿.*$", "", re.sub(r"^\d{6,8}[-\s]*", "", os.path.splitext(base)[0]))
    ntopic = _norm_topic(base)
    sys.stderr.write("→ 選中文案：%s（主題核心=%s）\n" % (base, ntopic))

    gen, still = _scan_dirs(root, ntopic)
    sys.stderr.write("→ 底圖 slide 數 %d、劇照 slide 數 %d\n" % (len(gen), len(still)))

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
         "clickup_task_id": args.clickup, "created_at": None, "_draft_json": os.path.abspath(jf),
         "caption": _assemble_caption(data), "topic_type": args.topic_type, "slides": slides}
    ncand = sum(len(s["candidates"]) for s in slides)
    if ncand == 0:
        sys.stderr.write("⚠ 未匹配到任何候選圖——請檢查底圖/劇照資料夾命名是否含主題關鍵字，或用 add-post 手動 manifest。\n")
    _build_and_write(m)


# ── 渲染核准貼文：用 PT 在操控室選定的底圖出成品 ─────────────────────
ENGINE_DIR = os.path.abspath(os.path.join(REPO, "..", "排版引擎"))


def _rebuild_sources(p):
    """無 .local_sources 的舊貼文：復刻 from-drive 掃描邏輯重建 cid→原圖，並以 (cid,kind) 序列驗證。"""
    ntopic = _norm_topic(p.get("topic", ""))
    gen, still = _scan_dirs(DRIVE_PRODUCE, ntopic, prune=False)  # 復刻原始（未剔破圖）序列
    srcs = {}
    for s in p.get("slides", []):
        n = s["n"]
        cand_paths = ([(path, "generated") for path, _ in gen.get(n, [])]
                      + [(path, "still") for path, _ in still.get(n, [])])
        built = []
        for i, (path, kind) in enumerate(cand_paths):
            if not os.path.exists(path):
                continue
            built.append((CID[i], path, kind))
        want = [(c["cid"], c["kind"]) for c in s.get("candidates", [])]
        got = [(cid, kind) for cid, _, kind in built]
        if want != got:
            return None, "slide %d 候選序列不符（重掃 %s ≠ posts %s）" % (n, got, want)
        srcs[str(n)] = {cid: path for cid, path, _ in built}
    return srcs, None


def _find_draft_json(ntopic):
    jsons = [f for f in glob.glob(os.path.join(DRIVE_PRODUCE, "*.json"))
             if "文案" in os.path.basename(f) and "ZZ" not in os.path.basename(f)
             and "易讀版" not in os.path.basename(f) and _topic_match(ntopic, os.path.basename(f))]
    if not jsons:
        return None
    datekey = lambda f: (re.match(r"(\d{6,8})", os.path.basename(f)) or [None, "0"])[1] if re.match(r"(\d{6,8})", os.path.basename(f)) else "0"
    return sorted(jsons, key=lambda f: (datekey(f), os.path.getmtime(f)))[-1]


def render_approved(args):
    """讀最新審核（approve／退回排版）＋文案編輯 → 用 PT 選定底圖渲染 → 歸檔 → 附回操控室。
    冪等：posts.json 的 rendered_at 晚於（審核 ts、文案編輯 ts 最大值）就跳過。"""
    posts_d = load("posts.json")
    posts = {p["id"]: p for p in posts_d.get("posts", [])}
    reviews = load("reviews.json").get("reviews", [])
    ce_list = load("copy_edits.json").get("edits", [])
    ls = _load_local_sources()
    latest = {}
    for r in reviews:  # 依序覆蓋 → 每篇取最後一筆
        if r.get("post_id"):
            latest[r["post_id"]] = r
    rendered, skipped = [], []
    for pid, r in latest.items():
        p = posts.get(pid)
        if not p or p.get("status") in ("scheduled", "published"):
            continue
        if getattr(args, "only", None) and pid != args.only:
            continue
        dec, scope = r.get("decision"), r.get("scope")
        if dec == "reject" and scope == "base_image":
            if p.get("status") != "awaiting_review":
                p["status"] = "awaiting_review"  # 退回底圖 → 回佇列等新候選
            skipped.append((pid, "退回底圖：等重生候選"))
            continue
        if dec != "approve" and not (dec == "reject" and scope == "mockup"):
            continue
        if dec == "approve" and p.get("status") == "awaiting_review":
            p["status"] = "approved"  # 舊版核准未持久化的補正
        want_ts = r.get("ts", "")
        for e in ce_list:
            if e.get("post_id") == pid and e.get("ts", "") > want_ts:
                want_ts = e["ts"]
        if not getattr(args, "force", False) and p.get("rendered_at") and p["rendered_at"] >= want_ts and all(
                s.get("public_url") for s in p["slides"] if s.get("final_src") or s.get("candidates")):
            skipped.append((pid, "已渲染且無新變更"))
            continue
        entry = ls.get(pid) or {}
        # 候選圖在審核之後被更新過 → 該審核的 cid 選圖已失效
        stale = bool(p.get("candidates_since")) and r.get("ts", "") < p["candidates_since"]
        reuse_paths = entry.get("last_render_choices") if stale else None
        if stale and not reuse_paths:
            if p.get("status") == "approved":
                p["status"] = "awaiting_review"
            skipped.append((pid, "候選圖已更新且無前次渲染紀錄 → 退回待審，請重新選圖核准"))
            continue
        srcs = entry.get("sources")
        if not srcs and not reuse_paths:
            srcs, err = _rebuild_sources(p)
            if err:
                skipped.append((pid, "圖源重建失敗：" + err))
                continue
        jf = entry.get("draft_json")
        if not jf or not os.path.exists(jf):
            jf = _find_draft_json(_norm_topic(p.get("topic", "")))
        if not jf:
            skipped.append((pid, "找不到文案 JSON"))
            continue
        choices = {}
        for k, v in (r.get("slide_choices") or {}).items():
            try:
                choices[int(k)] = v
            except ValueError:
                pass
        work = os.path.join(ENGINE_DIR, ".render-tmp", pid)
        bgdir = os.path.join(work, "bg")
        if os.path.isdir(work):
            shutil.rmtree(work)
        os.makedirs(bgdir)
        ok = True
        chosen_paths = {}
        for s in p.get("slides", []):
            if not s.get("candidates"):
                continue  # CTA 公版由引擎處理
            n = s["n"]
            if reuse_paths:  # 重渲染：沿用上次成功渲染的原檔（cid 已失效不可用）
                path = reuse_paths.get(str(n))
            else:
                cid = choices.get(n) or s.get("default_cid") or s["candidates"][0]["cid"]
                path = (srcs.get(str(n)) or {}).get(cid)
            if not path or not os.path.exists(path):
                skipped.append((pid, "slide %d 選圖原檔不存在" % n)); ok = False; break
            if _flat_image(path):
                skipped.append((pid, "slide %d 選圖疑似破圖，請到操控室改選其他候選再核准" % n)); ok = False; break
            chosen_paths[str(n)] = os.path.abspath(path)
            shutil.copy2(path, os.path.join(bgdir, "slide-%d%s" % (n, os.path.splitext(path)[1].lower())))
        if not ok:
            continue
        with open(jf, encoding="utf-8") as f:
            draft = json.load(f)
        edits = _latest_copy_edits(pid, ce_list)
        for s in draft.get("slides", []):
            for field in ("heading", "display_copy"):
                key = (int(s.get("index", -1)), field)
                if key in edits:
                    s[field] = edits[key]
        pj = os.path.join(work, "draft.json")
        with open(pj, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False)
        if args.dry_run:
            print("(dry-run) 會渲染 %s：選圖 %s，文案編輯 %d 處" % (pid, r.get("slide_choices"), len(edits)))
            continue
        rr = subprocess.run([sys.executable, os.path.join(ENGINE_DIR, "render_and_archive.py"), pj, bgdir, pid],
                            cwd=ENGINE_DIR, capture_output=True, text=True)
        if rr.returncode != 0:
            skipped.append((pid, "渲染失敗：" + (rr.stderr or rr.stdout)[-300:].strip()))
            continue
        p["rendered_at"] = _now_iso()
        rendered.append((pid, p.get("clickup_task_id") or "", jf, chosen_paths))
        sys.stderr.write("✓ 渲染 %s（選圖 %s，文案編輯 %d 處）\n" % (pid, r.get("slide_choices"), len(edits)))
    if not args.dry_run:
        save("posts.json", posts_d)
    # 附回操控室：finals 縮圖 + 公開圖（重餵；guard 會保留 approved/rendered_at/文案編輯）
    for pid, cuid, jf, chosen_paths in rendered:
        p = posts[pid]
        ns = argparse.Namespace(drive_root=None, topic=None, post_id=pid, clickup=p.get("clickup_task_id"),
                                finals_dir=os.path.join(ENGINE_DIR, "成品", pid), version=p.get("version", 1),
                                topic_type=p.get("topic_type", "A-知識型"),
                                json=os.path.join(ENGINE_DIR, ".render-tmp", pid, "draft.json"),
                                topic_base=os.path.basename(jf))
        from_drive(ns)
        ls = _load_local_sources()
        if pid in ls:
            ls[pid]["draft_json"] = os.path.abspath(jf)  # 還原成 Drive 正本（scratch 會被清）
            ls[pid]["last_render_choices"] = chosen_paths  # 供文案微調後重渲染沿用同組圖
            _save_local_sources(ls)
    for pid, cuid, _, _ in rendered:
        print("✓RENDERED %s clickup=%s" % (pid, cuid or "-"))
    for pid, why in skipped:
        print("⏭ %s：%s" % (pid, why))
    if not rendered and not skipped:
        print("無待渲染的核准貼文")


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
    a.add_argument("--json", default=None, help="直接指定文案 JSON（跳過掃描選擇）")
    a.add_argument("--topic-base", default=None, help="與 --json 併用：主題推導用的原始檔名")
    a.set_defaults(func=from_drive)
    a = sub.add_parser("render-approved", help="核准/退回排版 → 用 PT 選定底圖渲染成品並附回操控室")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--force", action="store_true", help="忽略 rendered_at 閘門（引擎修復後重出成品用）")
    a.add_argument("--only", default=None, help="只處理指定 post-id")
    a.set_defaults(func=render_approved)
    a = sub.add_parser("mark-consumed"); a.add_argument("ids", nargs="+"); a.set_defaults(func=mark_consumed)
    a = sub.add_parser("set-status"); a.add_argument("post_id"); a.add_argument("status"); a.set_defaults(func=set_status)
    a = sub.add_parser("apply-reviews", help="操控室審核 → ClickUp 卡片狀態回寫"); a.add_argument("--dry-run", action="store_true"); a.set_defaults(func=apply_reviews)
    a = sub.add_parser("reconcile-published", help="ClickUp 已發布 → posts.json 翻 published（補發佈回寫缺口）"); a.add_argument("--dry-run", action="store_true"); a.set_defaults(func=reconcile_published)
    a = sub.add_parser("push"); a.add_argument("message"); a.set_defaults(func=push)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
