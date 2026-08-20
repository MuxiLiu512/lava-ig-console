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
    if len(short) < 4:
        return short == long   # 太短的主題只允許全等，防跨主題資料夾互吃
    return short[:6] in long or long[:6] in short


def _still_label(fn):
    """檔名 → (label, source_kind)。
    slide1-TheOffice-2.jpg → ('The Office', None)；slide2-WM-EstherPerel-1.jpg → ('Esther Perel','WM')；
    WM-EstherPerel-1.jpg（無 slide 標籤）→ ('Esther Perel','WM')。source_kind ∈ {WM,OV,OL,None}。"""
    m = re.match(r"slide-?\d+[-_ ]+(.+?)([-_ ]\d+)?\.\w+$", fn, re.I)
    if m:
        core = m.group(1)
    else:
        m = re.match(r"((?:WM|OV|OL|DESIGN|SHOT)-.+?)([-_ ]\d+)?\.\w+$", fn, re.I)
        if not m:
            return None, None
        core = m.group(1)
    sk = None
    m2 = re.match(r"(?i)^(WM|OV|OL|DESIGN|SHOT)[- ](.+)$", core)
    if m2:
        sk, core = m2.group(1).upper(), m2.group(2)
    if sk == "DESIGN":
        core = re.sub(r"-s\d+$", "", core)
    core = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", core)      # HaveI → Have I
    core = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", core)  # IEver → I Ever
    return (core.replace("_", " ").strip() or None), sk


def _slug(s):
    return re.sub(r"[^0-9A-Za-z一-鿿]+", "", s)[:24] or "post"


def _clean_caption(t):
    """IG 說明欄清洗：去渲染標記【】〖〗、去禁用破折號、空白正規化（CJK 換行直接接合）。"""
    t = re.sub(r"[【】〖〗]", "", t or "")
    t = t.replace("——", "，").replace("──", "，")
    t = re.sub(r"\n+", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"([，。；：、！？])\s+", r"\1", t)  # 全形標點後不留空白
    return t.strip()


def _assemble_caption(data):
    """從文案 JSON 組 IG caption：hook + 品牌段 + hashtags。
    排版鐵則（2026-08-03 Jesse 驗收）：首句獨立成行＋空一行；其後逐句斷行；段落間空行——不得糊成字牆。"""
    slides = data.get("slides", [])
    def body_of(pred):
        for s in slides:
            if pred(s):
                return _clean_caption(s.get("body") or s.get("display_copy") or "")
        return ""
    def _sent_lines(text):
        parts = [x.strip() for x in re.split(r"(?<=[。！？!?…])", text) if x.strip()]
        return "\n".join(parts)
    hook = body_of(lambda s: s.get("index") == 1 or "hook" in str(s.get("role", "")).lower())
    brand = body_of(lambda s: "品牌" in str(s.get("role", "")) or "立場" in str(s.get("role", "")))
    first, rest = "", ""
    m = re.match(r"(.+?[。！？!?…])\s*(.*)$", hook, re.S)
    if m:
        first, rest = m.group(1).strip(), m.group(2).strip()
    else:
        first = hook.strip()
    tags = data.get("hashtags", [])
    tagline = " ".join(t if t.startswith("#") else "#" + t for t in tags)
    parts = [p for p in [first, _sent_lines(rest), _sent_lines(brand), tagline] if p]
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
    """近純色圖（生圖失敗的色塊，如整片藍）→ True。無法讀取重試一次（Drive 掛載偶發 EDEADLK），仍失敗才視為壞圖。"""
    from PIL import Image, ImageStat
    import time
    for attempt in (0, 1):
        try:
            im = Image.open(path).convert("RGB").resize((48, 48))
            if max(ImageStat.Stat(im).stddev) < thresh:
                return True
            quads = [im.crop(b) for b in ((0, 0, 24, 24), (24, 0, 48, 24), (0, 24, 24, 48), (24, 24, 48, 48))]
            return all(max(ImageStat.Stat(q).stddev) < 6.0 for q in quads)
        except Exception:
            if attempt == 0:
                time.sleep(0.8)
    return True


def _image_ok(path):
    """品質閘門（W1-5）：解析度／JPEG 壓縮率／模糊偵測。回傳 (ok, reason, metrics)。
    DESIGN 檔（品牌自產漸層）由呼叫端 bypass；門檻校準期間 log-only 不剔除。"""
    try:
        from PIL import Image, ImageStat, ImageFilter
        im = Image.open(path)
        w, h = im.size
        size = os.path.getsize(path)
        metrics = {"w": w, "h": h, "bytes": size}
        if min(w, h) < 700:
            return False, "low_res", metrics
        fmt = (im.format or "").upper()
        if fmt == "JPEG":
            bpp = size / float(w * h)
            metrics["bpp"] = round(bpp, 4)
            if bpp < 0.05:
                return False, "over_compressed", metrics
        g = im.convert("L")
        scale = 512.0 / max(w, h)
        if scale < 1.0:
            g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        mean = ImageStat.Stat(g).mean[0]
        metrics["brightness"] = round(mean, 1)
        if mean >= 40:   # 暗圖豁免：夜景/劇照低對比本來就低變異，不算模糊
            ev = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
            metrics["edge_var"] = round(ev, 1)
            if ev < 60:
                return False, "blurry", metrics
        return True, None, metrics
    except Exception as e:
        return False, "unreadable:%s" % type(e).__name__, {}


def _gate_log(rec):
    """image_gate.jsonl append-only（校準期審計；gate-audit 讀這裡）。"""
    outdir = os.path.join(DATA, "archive")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "image_gate.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _latest_copy_edits(pid, ce_list, version=None):
    """操控室文案編輯 → 每個 (slide n, 欄位) 取最新一筆 edited 值。
    version：只吃「無版本標記（舊制）」或「與選定文案版本相符」的編輯（雙寫手比稿用）。"""
    out = {}
    for e in sorted([e for e in ce_list if e.get("post_id") == pid], key=lambda e: e.get("ts", "")):
        for ed in e.get("edits", []):
            if ed.get("version") and version and ed["version"] != version:
                continue
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
        if _norm((task.get("status") or {}).get("status")) in ("已發布", "發布完成"):
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
            _bn = os.path.basename(c["src"])
            if "-DESIGN-" not in _bn and "-SHOT-" not in _bn and _flat_image(c["src"]):
                sys.stderr.write("  ↩ 剔除空圖/破圖候選：%s\n" % _bn); continue
            if "-DESIGN-" not in _bn and "-SHOT-" not in _bn:
                ok, reason, metrics = _image_ok(c["src"])
                if not ok:
                    c["low_q"] = True   # log-only：標記不剔除，門檻用 gate-audit 校準後再升硬閘
                    _gate_log({"ts": _now_iso(), "post_id": pid, "slide": s["n"],
                               "file": os.path.basename(c["src"]), "reason": reason, "metrics": metrics})
                    sys.stderr.write("  ⚠ 低畫質標記（%s）：%s\n" % (reason, os.path.basename(c["src"])))
            try:
                out = make_thumb(c["src"], os.path.join(ASSETS, pid, "slide-%d%s" % (s["n"], CID[i])))
            except Exception as e:   # 截斷/損毀檔（如被 timeout 砍斷的寫入）不拖垮整篇
                sys.stderr.write("  ↩ 縮圖失敗剔除：%s（%s）\n" % (os.path.basename(c["src"]), e)); continue
            entry = {"cid": CID[i], "src": os.path.relpath(out, REPO).replace(os.sep, "/"), "kind": c.get("kind", "generated")}
            if c.get("source_label"):
                entry["source_label"] = c["source_label"]
            if c.get("source_kind"):
                entry["source_kind"] = c["source_kind"]   # WM/OV/OL/DESIGN → UI badge 與法遵標注都靠它
            if c.get("low_q"):
                entry["low_q"] = True
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
    # 操控室的文案編輯覆蓋（重餵不洗掉 PT 改過的字；只吃無版本或選定版本的編輯）
    try:
        _oldrec = next((pp for pp in load("posts.json").get("posts", []) if pp["id"] == pid), None)
        _ver = (_oldrec or {}).get("copy_choice") or ("gpt" if (m.get("_copy_versions") or {}).get("gpt") else None)
        edits = _latest_copy_edits(pid, load("copy_edits.json").get("edits", []), version=_ver)
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
    if m.get("writer_model"):
        post["writer_model"] = m["writer_model"]   # A/B：這篇文案由哪個模型撰寫（成效迴路比較用）
    if m.get("_copy_versions"):
        post["copy_versions"] = m["_copy_versions"]   # 雙寫手比稿：GPT/Claude 兩版 heading/display_copy/caption
    d = load("posts.json")
    posts = d.setdefault("posts", [])
    old = next((p for p in posts if p["id"] == pid), None)
    if old and old.get("status") in ("approved", "scheduled", "published"):  # 已核准/已排程/已發佈者不被重餵洗掉
        post["status"] = old["status"]
    if old:
        for k in ("publish_at", "published_at", "media_id", "rendered_at", "candidates_since", "image_credits", "copy_choice"):
            if old.get(k):
                post[k] = old[k]
        if not post.get("clickup_task_id") and old.get("clickup_task_id"):
            post["clickup_task_id"] = old["clickup_task_id"]   # 重餵漏 --clickup 不得洗掉卡號（否則哨兵會重複入料）
    # 安全網：新版 0 候選不得覆蓋有候選的舊版（Drive 瞬時 I/O 錯誤會把全池誤判破圖清空）
    new_total = sum(len(s["candidates"]) for s in slides)
    old_total = sum(len(s.get("candidates", [])) for s in (old or {}).get("slides", []))
    if new_total == 0 and old_total > 0:
        sys.stderr.write("  ✋ 拒絕覆蓋：新版 0 候選、舊版 %d 候選（疑 Drive 讀取異常），保留舊版 %s\n" % (old_total, pid))
        return
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
    prev = ls.get(pid) or {}
    prev.update({"draft_json": m.get("_draft_json"), "topic": m.get("topic", ""), "sources": srcmap})
    if m.get("_draft_jsons"):
        dj = prev.get("draft_jsons") or {}
        dj.update(m["_draft_jsons"])
        prev["draft_jsons"] = dj   # 雙寫手：兩版文案 JSON 路徑（渲染依 copy_choice 取用）
    ls[pid] = prev   # 合併式更新：保留 last_render_choices 等既有鍵（原本整包覆寫會洗掉）
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
    seen_names = set()   # 跨輪資料夾同名圖去重（F6）
    shot_credits = {}    # {dir: {filename: 出處}}（forager 的 shots_credits.json sidecar）
    for d in sorted(dirs):
        for f in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
            fn = os.path.basename(f)
            if not fn.lower().endswith(IMG_EXT):
                continue
            if fn.lower() in seen_names:
                continue
            mm = re.search(r"slide-?(\d+)", fn, re.I)
            is_design = "-DESIGN-" in fn
            is_shot = "-SHOT-" in fn
            if prune and not is_design and not is_shot and _flat_image(f):
                sys.stderr.write("  ✂ 剔除疑似破圖（近純色）：%s\n" % fn)
                continue
            lb0, sk0 = _still_label(fn)
            if kind == "still" or is_design or is_shot:
                label, sk = lb0, sk0
            else:
                label, sk = None, None
            if is_shot:   # sidecar 有完整出處（帳號/媒體/影片名）就用它取代檔名 slug
                dd = os.path.dirname(f)
                if dd not in shot_credits:
                    try:
                        with open(os.path.join(dd, "shots_credits.json"), encoding="utf-8") as cf:
                            shot_credits[dd] = json.load(cf)
                    except Exception:
                        shot_credits[dd] = {}
                label = shot_credits[dd].get(fn) or label
            seen_names.add(fn.lower())
            # 無 slide 標籤的新來源檔（WM-/OV-/OL-）進 0 號池，之後輪流分配到內容 slides
            key = int(mm.group(1)) if mm else (0 if sk else None)
            if key is None:
                continue
            out.setdefault(key, []).append((f, label, sk))
    return out


def _scan_dirs(root, ntopic, prune=True):
    """依主題掃 Drive 產出/ 的底圖與劇照資料夾 → (gen, still) 兩個 {n: [(path,label)]}。"""
    subdirs = sorted(d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d) and "ZZ" not in os.path.basename(d))
    base_dirs = [d for d in subdirs if "底圖" in os.path.basename(d) and _topic_match(ntopic, os.path.basename(d))]
    _SK = ("劇照", "人物", "書封", "參考圖")
    still_dirs = [d for d in subdirs if any(k in os.path.basename(d) for k in _SK) and _topic_match(ntopic, os.path.basename(d))]
    return _collect_slide_imgs(base_dirs, "generated", prune), _collect_slide_imgs(still_dirs, "still", prune)


def _read_json_retry(path, tries=4, wait=3.0):
    """Drive 掛載讀檔：檔案剛從雲端同步下來、本地尚在 hydration 時會撞 EDEADLK/EAGAIN，退避重試。"""
    import errno, time
    last = None
    for i in range(tries):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except OSError as e:
            if getattr(e, "errno", None) not in (errno.EDEADLK, errno.EAGAIN, errno.EIO):
                raise
            last = e
            time.sleep(wait * (i + 1))
    raise last


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
            _ntq = _norm_topic(args.topic)  # frag 已是正規化字串 → 檔名側也正規化再比（v 剝除 bug 兩側抵消）
            jsons = [f for f in jsons if args.topic in os.path.basename(f)
                     or (_ntq and _ntq in _norm_topic(os.path.basename(f)))]
        if not jsons:
            sys.exit("✗ 產出/ 內找不到符合的文案 JSON" + ("（topic=%s）" % args.topic if args.topic else ""))
        datekey = lambda f: (lambda mm: ("0" if not mm else (mm.group(1) if len(mm.group(1)) == 8 else "20" + mm.group(1))))(re.match(r"(\d{6,8})", os.path.basename(f)))
        jf = sorted(jsons, key=lambda f: (datekey(f), os.path.getmtime(f)))[-1]
        base = os.path.basename(jf)
    # 雙寫手比稿：找同日期同主題的 -GPT / -Claude 兩版（預設顯示 GPT 版）
    versions = {}
    if not getattr(args, "json", None):
        _bnt = _norm_topic(base)
        _dk = (re.match(r"(\d{6,8})", base) or [None, ""])[1] if re.match(r"(\d{6,8})", base) else ""
        for f2 in glob.glob(os.path.join(root, "*.json")):
            b2 = os.path.basename(f2)
            if "文案" not in b2 or "易讀版" in b2 or "ZZ" in b2:
                continue
            if _dk and not b2.startswith(_dk):
                continue
            if not _topic_match(_bnt, b2):
                continue
            mkey = "claude" if "-Claude" in b2 else ("gpt" if "-GPT" in b2 else None)
            if mkey and (mkey not in versions or os.path.getmtime(f2) > os.path.getmtime(versions[mkey])):
                versions[mkey] = f2
        if versions:
            jf = versions.get("gpt") or versions[sorted(versions)[0]]
            base = os.path.basename(jf)
            sys.stderr.write("→ 雙寫手版本：%s\n" % "、".join(sorted(versions)))
    data = _read_json_retry(jf)
    date = (re.match(r"(\d{6,8})", base) or [None, ""])[1] if re.match(r"(\d{6,8})", base) else ""
    topic_raw = re.sub(r"-?文案初稿.*$", "", re.sub(r"^\d{6,8}[-\s]*", "", os.path.splitext(base)[0]))
    ntopic = _norm_topic(base)
    sys.stderr.write("→ 選中文案：%s（主題核心=%s）\n" % (base, ntopic))
    pid = args.post_id or ("%s-%s" % (date or "draft", _slug(ntopic)))

    # 設計底：2026-07-29 Jesse 否決抽象漸層版（「沒有意義的東西」）→ 停用；
    # 生成器保留待 v2（timeleft 式拼貼文字卡，需與渲染文字合成預覽）再啟用
    INCLUDE_DESIGN = False
    try:
        if not INCLUDE_DESIGN:
            raise RuntimeError("design bg disabled by Jesse 2026-07-29")
        _subs = sorted(d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d) and "ZZ" not in os.path.basename(d))
        _bds = [d for d in _subs if "底圖" in os.path.basename(d) and _topic_match(ntopic, os.path.basename(d))]
        _bd = max(_bds, key=os.path.getmtime) if _bds else os.path.join(root, "%s %s 底圖" % (date or "20260000", topic_raw[:24]))
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen_design_bg.py"),
                        "--draft", jf, "--outdir", _bd, "--post-id", pid], check=False, timeout=300)
    except Exception as e:
        sys.stderr.write("  ! 設計底生成失敗（不阻斷）：%s\n" % e)
    gen, still = _scan_dirs(root, ntopic)
    sys.stderr.write("→ 底圖 slide 數 %d、劇照 slide 數 %d\n" % (len(gen), len(still)))

    slides = []
    pool = list(still.get(0, []))   # 無 slide 標籤的新來源（WM/OV/OL）→ 輪流分配到內容 slides
    content_ns = [s.get("index") for s in data.get("slides", []) if (s.get("role") or "") != "CTA"]
    pool_assign = {}
    for i, item in enumerate(pool):
        tgt = content_ns[i % max(1, len(content_ns))] if content_ns else 1
        pool_assign.setdefault(tgt, []).append(item)
    for s in data.get("slides", []):
        n = s.get("index")
        cands = []
        gen_items = list(gen.get(n, []))
        # 截圖策展（SHOT）最優先——這是撰稿指定的「講誰就截誰」素材（素材線 v2）
        for path, label, sk in gen_items:
            if sk == "SHOT":
                cands.append({"src": path, "kind": "still", "source_kind": "SHOT", "source_label": label or "截圖"})
        # 劇照/新來源次之（原本 gen 在前導致 CID 12 格被生圖吃光、新來源被截斷）
        for path, label, sk in (still.get(n, []) + pool_assign.get(n, [])):
            c = {"src": path, "kind": "still"}
            if label:
                c["source_label"] = label
            if sk:
                c["source_kind"] = sk
            cands.append(c)
        for path, label, sk in gen_items:      # DESIGN 已停用（Jesse 2026-07-29 否決抽象漸層底）
            if sk == "DESIGN" and INCLUDE_DESIGN:
                cands.append({"src": path, "kind": "design", "source_kind": "DESIGN", "source_label": label or "design"})
        for path, label, sk in gen_items:
            if sk not in ("DESIGN", "SHOT"):
                cands.append({"src": path, "kind": "generated"})
        final = None
        if args.finals_dir:
            for ext in (".png", ".jpg", ".webp"):
                fp = os.path.join(args.finals_dir, "final-%02d%s" % (n, ext))
                if os.path.exists(fp):
                    final = fp; break
        slides.append({"n": n, "role": str(s.get("role", "")), "final": final, "candidates": cands,
                       "heading": s.get("heading", ""), "display_copy": s.get("display_copy", "")})

    copy_versions = {}
    for mk, path in versions.items():
        try:
            with open(path, encoding="utf-8") as f:
                dv = json.load(f)
            copy_versions[mk] = {"caption": _assemble_caption(dv), "slides": {
                str(s.get("index")): {"heading": s.get("heading", ""), "display_copy": s.get("display_copy", "")}
                for s in dv.get("slides", [])}}
        except Exception as e:
            sys.stderr.write("  ! 讀 %s 版文案失敗：%s\n" % (mk, e))
    m = {"id": pid, "topic": topic_raw, "version": args.version,
         "clickup_task_id": args.clickup, "created_at": None, "_draft_json": os.path.abspath(jf),
         "caption": _assemble_caption(data), "topic_type": args.topic_type, "slides": slides,
         "writer_model": data.get("writer_model"),
         "_copy_versions": copy_versions or None,
         "_draft_jsons": {k: os.path.abspath(v) for k, v in versions.items()} or None}
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
        cand_paths = ([(path, "generated") for path, *_ in gen.get(n, [])]
                      + [(path, "still") for path, *_ in still.get(n, [])])
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
    datekey = lambda f: (lambda mm: ("0" if not mm else (mm.group(1) if len(mm.group(1)) == 8 else "20" + mm.group(1))))(re.match(r"(\d{6,8})", os.path.basename(f)))
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
        if not p or p.get("status") == "published":
            continue
        if getattr(args, "only", None) and pid != args.only:
            continue   # --only 必須最先判斷，否則其他篇的訊息會混進來（2026-08-12）
        if (p.get("status") == "scheduled" and not getattr(args, "force", False)
                and all(s.get("public_url") for s in p["slides"] if s.get("candidates"))):
            # 已排程且成品齊 → 原則不動（成品缺＝重餵洗掉，放行往下重渲染，否則 WF10 到點發不出去）。
            # 例外（2026-08-11 Jesse：改了文案卻發到舊版）：排程後才存的文案編輯／審核若比 rendered_at 新，
            # 仍必須重出——否則修改靜默失效，且 WF10 到點把舊版發上 IG，無法回收。
            _ts = [e.get("ts", "") for e in ce_list if e.get("post_id") == pid] + [r.get("ts", "")]
            _newest = max([t for t in _ts if t] or [""])
            if not (_newest and p.get("rendered_at") and _newest > p["rendered_at"]):
                continue
            print("   ↻ %s 排程後有新修改（%s）→ 重出成品" % (pid[:22], _newest[:16]))
        dec, scope = r.get("decision"), r.get("scope")
        if dec == "reject" and scope == "base_image":
            if p.get("status") != "awaiting_review":
                p["status"] = "awaiting_review"  # 退回底圖 → 回佇列等新候選
            skipped.append((pid, "退回底圖：等重生候選"))
            continue
        if dec != "approve" and not (dec == "reject" and scope == "mockup"):
            continue
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
        if dec == "approve" and not stale and p.get("status") == "awaiting_review":
            p["status"] = "approved"  # 舊版核准未持久化的補正（stale 審核不補：需重新選圖核准）
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
        djs = entry.get("draft_jsons") or {}
        choice = r.get("copy_choice") or p.get("copy_choice") or ("gpt" if djs.get("gpt") else (sorted(djs)[0] if djs else None))
        jf = (djs.get(choice) if choice else None) or entry.get("draft_json")
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
        credits = {}   # {n: 圖上來源標示}；用「實際選定」的候選判斷（劇照/人物照才標）
        for s in p.get("slides", []):
            if not s.get("candidates"):
                continue  # CTA 公版由引擎處理
            n = s["n"]
            cid = None
            if reuse_paths:  # 重渲染：沿用上次成功渲染的原檔（cid 已失效不可用）
                path = reuse_paths.get(str(n))
                if path:  # 反查 cid 以取得出處標籤
                    cid = next((c for c, pth in (srcs.get(str(n)) or {}).items() if os.path.abspath(pth) == os.path.abspath(path)), None)
            else:
                cid = choices.get(n) or s.get("default_cid") or s["candidates"][0]["cid"]
                path = (srcs.get(str(n)) or {}).get(cid)
            if not path or not os.path.exists(path):
                skipped.append((pid, "slide %d 選圖原檔不存在" % n)); ok = False; break
            if _flat_image(path):
                skipped.append((pid, "slide %d 選圖疑似破圖，請到操控室改選其他候選再核准" % n)); ok = False; break
            cand = next((c for c in s["candidates"] if c.get("cid") == cid), None)
            if cand and cand.get("kind") == "still" and cand.get("source_label"):
                lb = cand["source_label"]
                sk = cand.get("source_kind")
                if not sk:
                    m3 = re.match(r"(?i)^(WM|OV|OL)[- ](.+)$", lb)
                    if m3:
                        sk, lb = m3.group(1).upper(), m3.group(2)
                if sk == "SHOT":
                    # forager 的內部標籤（a-mood44830 / b-personfc29a 這類 role+hash）不是出處，
                    # 印上去等於在成品洩漏檔名。情緒圖本就不標（Jesse 2026-08-01 裁決），其餘無真出處時一律留白。
                    if re.match(r"^[a-z]-(mood|person|book|article|evidence|still)[0-9a-f]{4,}$", lb):
                        pass
                    else:
                        credits[n] = "圖片來源：%s（截圖引用）" % lb
                elif sk == "WM":
                    credits[n] = "圖片來源：Wikimedia Commons（%s，自由授權）" % lb
                elif sk == "OL":
                    credits[n] = "圖片來源：Open Library 書封（%s）" % lb
                elif sk == "OV":
                    credits[n] = "圖片來源：Openverse 創用 CC（%s）" % lb
                else:
                    credits[n] = "圖片來源：《%s》劇照，版權屬原權利方" % lb
            chosen_paths[str(n)] = os.path.abspath(path)
            shutil.copy2(path, os.path.join(bgdir, "slide-%d%s" % (n, os.path.splitext(path)[1].lower())))
        if not ok:
            continue
        with open(jf, encoding="utf-8") as f:
            draft = json.load(f)
        # 變更紀錄：這輪跟上次渲染比，哪幾張換了圖（Jesse 2026-08-10：自動化改了什麼要看得到）
        prev = (entry.get("last_render_choices") or {})
        moved = [n for n, pth in chosen_paths.items()
                 if prev.get(n) and os.path.abspath(prev[n]) != os.path.abspath(pth)]
        if moved:
            r_note = (r.get("feedback") or "").strip()
            p.setdefault("change_log", []).append({
                "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "what": "換底圖：第 %s 張" % "、".join(sorted(moved, key=int)),
                "why": r_note[:120] or "依最新審核選圖重出",
                "by": r.get("id", ""),
            })
            p["change_log"] = p["change_log"][-20:]
        edits = _latest_copy_edits(pid, ce_list, version=choice)
        # 操控室手動裁切（posts.json slides[].crop_focus）→ 注入 draft，引擎據此裁切。
        # 預覽與成品同一套 object-position 數學，拖到哪裁到哪。
        _crops = {str(s2.get("n")): s2.get("crop_focus")
                  for s2 in p.get("slides", []) if s2.get("crop_focus")}
        for s in draft.get("slides", []):
            _cfv = _crops.get(str(s.get("index")))
            if _cfv:
                s["crop_focus"] = _cfv
            for field in ("heading", "display_copy"):
                key = (int(s.get("index", -1)), field)
                if key in edits:
                    s[field] = edits[key]
            if int(s.get("index", -1)) in credits:
                s["render_credit"] = credits[int(s["index"])]   # 圖上小字來源標示（引擎繪製）
        if credits:
            p["image_credits"] = ["第 %d 張：%s" % (n, credits[n].replace("圖片來源：", "")) for n in sorted(credits)]
        # 封面文案自我審查（機械、零 AI）——規則正本 config/self-check.md
        _cov = next((s for s in draft.get("slides", []) if int(s.get("index", 0) or 0) == 1), None)
        p["cover_head"] = ((_cov or {}).get("heading") or "").strip()
        cf = _copy_self_check(p, draft) + _hook_repeat_check(p, draft, posts_d.get("posts", []))
        if cf:
            p["copy_flags"] = cf
            for x in cf:
                print("   %s 封面：%s" % ("🔴" if x["severity"] == "block" else "🟡", x["detail"]))
        else:
            p.pop("copy_flags", None)
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
        p.pop("render_note", None)   # 渲染成功清掉卡住原因
        if choice:
            p["copy_choice"] = choice
            p["writer_model"] = "claude-sonnet-4-6" if choice == "claude" else "gpt-5.6"  # A/B：以 PT 選定版本計
        # 重出完成 → 自動恢復排程。操控室按核准會把狀態降回 approved（避免在成品還沒更新前
        # 被 WF10 發到舊圖），publish_at 一直保留著；成品更新完成才放回 scheduled。
        # Jesse 2026-08-12：改圖核准後排程消失，得重設時間——那是這個降級沒有回程造成的。
        if p.get("status") == "approved" and p.get("publish_at"):
            p["status"] = "scheduled"
            print("   ⏰ %s 成品已更新 → 恢復排程 %s" % (pid[:20], p["publish_at"][:16]))
        rendered.append((pid, p.get("clickup_task_id") or "", jf, chosen_paths))
        sys.stderr.write("✓ 渲染 %s（文案版 %s，選圖 %s，文案編輯 %d 處）\n" % (pid, choice or "-", r.get("slide_choices"), len(edits)))
    # 卡住原因寫進貼文 → 操控室直接看得到，不再只躺在哨兵 log。
    # 但「已渲染且無新變更」是冪等 skip，不是卡住——寫進 render_note 會讓
    # 操控室把好稿誤判成「卡住」（2026-08-19 看板實測：天氣變差被掛進卡住側欄）。
    # 良性 skip 不寫入，且要清掉殘留的舊 note。
    _BENIGN = ("已渲染且無新變更",)
    for pid, why in skipped:
        if pid not in posts:
            continue
        if why in _BENIGN:
            posts[pid].pop("render_note", None)
        else:
            posts[pid]["render_note"] = why
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
    # 完稿通知：改完文案／換完圖後不知道何時真的出好（Jesse 2026-08-12）。
    # 成品重出完成即在 ClickUp 卡留言並推播，附上排程時間與 final review 連結。
    _tok = _read_sync().get("clickup_token")
    for pid, cuid, _, _ in rendered:
        p = posts.get(pid) or {}
        if not (cuid and _tok and _tok.isascii()):
            continue
        try:
            n_fin = len([s for s in p.get("slides", []) if s.get("public_url")])
            when = p.get("publish_at")
            sched = ("　排程：**%s** 到點自動發佈" % when[:16].replace("T", " ")) if when and p.get("status") == "scheduled" \
                else "　尚未排程（到操控室設定發佈時間）"
            qa = p.get("qa") or {}
            nblk = len([i for i in qa.get("issues", []) if i.get("severity") == "block"])
            flags = p.get("copy_flags") or []
            warn = ""
            if nblk or flags:
                warn = "\n⚠ 總檢：%d 項須修%s" % (nblk, ("、封面檢查 %d 項" % len(flags)) if flags else "")
            _clickup("POST", "/task/%s/comment" % cuid, _tok, {
                "comment_text": "✅ **成品已重出**（%d 張）——你剛才的修改已套用，可做 final review。\n%s%s\n"
                                "操控室：https://muxiliu512.github.io/lava-ig-console/" % (n_fin, sched, warn),
                "notify_all": True})
        except Exception as e:
            sys.stderr.write("  ! 完稿通知失敗 %s：%s\n" % (pid[:20], e))
    for pid, cuid, _, _ in rendered:
        print("✓RENDERED %s clickup=%s" % (pid, cuid or "-"))
    for pid, why in skipped:
        print("⏭ %s：%s" % (pid, why))
    if not rendered and not skipped:
        print("無待渲染的核准貼文")


def _ts_older(ts, days):
    """ISO 字串（含 +08:00 時區）是否早於 N 天前。解析失敗 → False（保守保留）。"""
    try:
        t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
        return (datetime.datetime.now() - t).days > days
    except Exception:
        return False


def _append_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── #6：把 demo/測試/廢棄貼文移出主檔（不動 IG，只讓自動化不再碰它） ──────
def archive_post(args):
    d = load("posts.json")
    keep, moved = [], []
    ids = set(args.ids)
    for p in d.get("posts", []):
        if p["id"] in ids:
            if args.note:
                p["archived_note"] = args.note
            p["archived_at"] = _now_iso()
            p["no_publish"] = True  # 雙保險：即使誤留主檔也不會被 WF10 發佈
            moved.append(p)
        else:
            keep.append(p)
    if not moved:
        print("! 找不到要歸檔的貼文：%s" % ", ".join(ids)); return
    d["posts"] = keep
    save("posts.json", d)
    ap = os.path.join(DATA, "archived-posts.json")
    arch = {"posts": []}
    if os.path.exists(ap):
        with open(ap, encoding="utf-8") as f:
            arch = json.load(f)
    arch["posts"].extend(moved)
    with open(ap, "w", encoding="utf-8") as f:
        json.dump(arch, f, ensure_ascii=False, indent=2); f.write("\n")
    for p in moved:
        print("✓ 歸檔 %s → data/archived-posts.json（status was %s）" % (p["id"], p.get("status")))


# ── #5：資料檔瘦身（reviews/copy_edits 過期歸檔、insights 快照裁切） ─────
def archive_data(args):
    days = args.days
    pub = {p["id"] for p in load("posts.json").get("posts", []) if p.get("status") == "published"}
    # reviews：保留未 consumed 或 N 天內；其餘搬 archive
    rv = load("reviews.json"); keep, old = [], []
    for r in rv.get("reviews", []):
        if r.get("consumed") and _ts_older(r.get("ts"), days):
            old.append(r)
        else:
            keep.append(r)
    if old:
        _append_jsonl(os.path.join(DATA, "archive", "reviews.jsonl"), old)
        rv["reviews"] = keep; save("reviews.json", rv)
    # copy_edits：published 貼文且 N 天前的編輯搬 archive（語氣樣本已進 harness）
    ce = load("copy_edits.json"); ckeep, cold = [], []
    for e in ce.get("edits", []):
        if e.get("post_id") in pub and _ts_older(e.get("ts"), days):
            cold.append(e)
        else:
            ckeep.append(e)
    if cold:
        _append_jsonl(os.path.join(DATA, "archive", "copy_edits.jsonl"), cold)
        ce["edits"] = ckeep; save("copy_edits.json", ce)
    # insights：每篇只留 N 天內快照（至少留最新 1 筆）
    ins = load("insights.json"); trimmed = 0
    for mid, m in (ins.get("media") or {}).items():
        snaps = m.get("snapshots") or []
        if len(snaps) <= 1:
            continue
        fresh = [s for s in snaps if not _ts_older(s.get("day"), days)]
        if not fresh:
            fresh = snaps[-1:]
        if len(fresh) != len(snaps):
            trimmed += len(snaps) - len(fresh); m["snapshots"] = fresh
    if trimmed:
        save("insights.json", ins)
    print("✓ 歸檔：reviews %d 筆、copy_edits %d 筆、insights 裁切 %d 快照（門檻 %d 天）"
          % (len(old), len(cold), trimmed, days))


ALERT_CARD = "86eyckbur"   # 🔧 Lava IG 系統告警日誌
POSTQA_URL = "https://lavadating.app.n8n.cloud/webhook/lava-ig-postqa"

# 公版對話式開場（單獨當標題＝空洞 hook；只能當前綴）——config/self-check.md A1/A2
_HOLLOW = (r"^欸[，,、…⋯\.]*\s*你(有沒有|知不知道)", r"^你(有沒有|知不知道)發現", r"^有沒有發現",
           r"^欸[，,、…⋯\.]*\s*$", r"^你(們)?知道嗎")
_NO_TRAIL = set("最不很更也都又再還就才將被把讓使令對於和與及跟並而但因所如若則每同各此該其之的地得")


def _copy_self_check(post, draft):
    """封面文案機械檢查（零 AI，每次渲染跑）。規則正本 config/self-check.md。"""
    flags = []
    slides = draft.get("slides") or []
    cover = next((s for s in slides if int(s.get("index", 0) or 0) == 1), None)
    if not cover:
        return flags
    head = (cover.get("heading") or "").strip()
    topic = post.get("topic") or ""
    # A1 空洞 hook：剝掉公版開場後若無實質內容 → 讀者不知道要發現什麼。
    # （原以「與 topic 字面共詞」判定過嚴：主標用同義說法時會誤報，2026-08-11 修正）
    rest = head
    for pat in _HOLLOW:
        rest = re.sub(pat, "", rest)
    rest = re.sub(r"^[，,、—－\-…⋯\.：:？?！!\s]+", "", rest).strip()
    if any(re.search(p, head) for p in _HOLLOW) and len(rest) < 6:
        flags.append({"code": "hollow_hook", "severity": "block",
                      "detail": "封面主標「%s」只有公版開場、沒有主題內容，讀者不知道要發現什麼" % head[:20],
                      "fix": "開場後補上主題的具體說法（人名／現象／反差），對話式開場只能當前綴"})
    # A3 副標詞中斷行（引擎已語意斷行，此為回歸驗證）
    for ln in [l.strip() for l in (cover.get("display_copy") or "").split("\n") if l.strip()]:
        if ln and ln[-1] in _NO_TRAIL:
            flags.append({"code": "bad_linebreak", "severity": "warn",
                          "detail": "封面副標有一行以修飾詞「%s」結尾（%s）" % (ln[-1], ln[-12:]),
                          "fix": "改在標點處斷句，或縮短該行"})
            break
    return flags


def _hook_repeat_check(post, draft, posts_all):
    """A2 開場濫用：近 5 篇封面主標前 6 字重複。"""
    slides = draft.get("slides") or []
    cover = next((s for s in slides if int(s.get("index", 0) or 0) == 1), None)
    head = ((cover or {}).get("heading") or "").strip()
    if len(head) < 6:
        return []
    pre = head[:6]
    recent = [p for p in posts_all if p.get("id") != post.get("id")
              and p.get("status") in ("published", "scheduled", "approved")][-5:]
    hits = [p["id"] for p in recent if (p.get("cover_head") or "").startswith(pre)]
    if hits:
        return [{"code": "hook_repeat", "severity": "warn",
                 "detail": "封面開場「%s…」與近期 %d 篇重複（%s）" % (pre, len(hits), hits[0][:18]),
                 "fix": "換一種開場句型，同型近 5 篇最多 1 次"}]
    return []


def _post_qa(pid, finals_dir):
    """成篇視覺總檢（WF15）：把整篇成品送 Claude vision，抓單張看不出來的問題。
    2026-08-05 Aziz 事件：三張都是同一本書封、slide5 浮水印漏網、credit 印出內部檔名——
    每張單看都過閘門，合起來才露餡。逐張把關擋不住的，只有全篇把關擋得住。"""
    import base64, io, urllib.request
    from PIL import Image
    imgs = sorted(glob.glob(os.path.join(finals_dir, "slide-*.jpg")),
                  key=lambda f: int(re.search(r"slide-(\d+)", f).group(1)))
    if len(imgs) < 3:
        return None
    post = next((x for x in load("posts.json").get("posts", []) if x["id"] == pid), {})
    heads = {s.get("n"): s.get("heading", "") for s in post.get("slides", [])}
    slides = []
    for f in imgs:
        n = int(re.search(r"slide-(\d+)", f).group(1))
        im = Image.open(f).convert("RGB")
        im.thumbnail((820, 1025))   # 浮水印是細筆畫平鋪，壓太小會消失（520px 時 Magnific 浮水印漏檢）
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        slides.append({"n": n, "heading": heads.get(n, ""),
                       "b64": base64.b64encode(buf.getvalue()).decode()})
    body = json.dumps({"post_id": pid, "slides": slides}).encode()
    req = urllib.request.Request(POSTQA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode())


def post_qa(args):
    """發佈前全篇檢查；block 級問題會擋住排程（操控室顯示待修）。"""
    posts_d = load("posts.json")
    targets = [p for p in posts_d.get("posts", [])
               if (p["id"] == args.post_id if args.post_id else p.get("status") in ("approved", "scheduled"))]
    if not targets:
        print("無可檢查的貼文"); return
    for p in targets:
        fd = os.path.join(REPO, "docs", "finals", p["id"])
        if not os.path.isdir(fd):
            print("⏭ %s：無成品" % p["id"][:26]); continue
        try:
            res = _post_qa(p["id"], fd)
        except Exception as e:
            print("! %s 總檢失敗：%s" % (p["id"][:26], e)); continue
        if not res:
            print("⏭ %s：成品不足 3 張" % p["id"][:26]); continue
        issues = res.get("issues") or []
        blocks = [i for i in issues if i.get("severity") == "block"]
        p["qa"] = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                   "pass": not blocks, "issues": issues, "rhythm": res.get("rhythm_note", "")}
        mark = "🔴 %d 項須修" % len(blocks) if blocks else ("🟡 %d 項提醒" % len(issues) if issues else "✅ 通過")
        print("%s %s" % (mark, p["id"][:30]))
        for i in issues:
            print("   [%s] 第 %s 張：%s → %s" % (i.get("severity", "?"),
                  "、".join(str(x) for x in (i.get("slides") or [])), i.get("detail", ""), i.get("fix", "")))
        if res.get("rhythm_note"):
            print("   節奏：%s" % res["rhythm_note"])
    save("posts.json", posts_d)


def alert(args):
    """哨兵自報告警（管線自身停擺時，n8n 的 errorWorkflow 抓不到——它只看 n8n 執行）。"""
    token = _read_sync().get("clickup_token")
    if not token or not token.isascii():
        print("缺 clickup_token，略過告警"); return
    ts = datetime.datetime.now().astimezone().strftime("%m-%d %H:%M")
    try:
        _clickup("POST", "/task/%s/comment" % ALERT_CARD, token,
                 {"comment_text": "⚠ [%s] 哨兵告警：%s" % (ts, args.message), "notify_all": True})
        print("✓ 告警已送出")
    except Exception as e:
        print("! 告警送出失敗：%s" % e)


def rendered_lines(args):
    """把「圖上實際會印出來的每一行」寫進 posts.json，供操控室與文字框對照。
    獨立成一步而非塞在 render_approved 裡——渲染流程中途會 refeed 重建 posts.json，
    寫在裡面會被沖掉（2026-08-12 實測）。哨兵在 render 之後呼叫。"""
    import check_typography as ct
    d = load("posts.json")
    ls = _load_local_sources()
    ce_list = load("copy_edits.json").get("edits", [])
    n_ok = 0
    for p in d.get("posts", []):
        if p.get("status") == "published" and not getattr(args, "all", False):
            continue
        if getattr(args, "post_id", None) and p["id"] != args.post_id:
            continue
        e = ls.get(p["id"]) or {}
        jf = e.get("draft_json") or (e.get("draft_jsons") or {}).get("claude")
        if not jf or not os.path.exists(jf):
            continue
        try:
            draft = _read_json_retry(jf)
        except Exception:
            continue
        edits = _latest_copy_edits(p["id"], ce_list, version=p.get("copy_choice"))
        rl = {}
        for s_ in draft.get("slides", []):
            n = int(s_.get("index", 0) or 0)
            if not n:
                continue
            head = s_.get("heading") or ""
            body = s_.get("display_copy") or ""
            if (n, "heading") in edits:
                head = edits[(n, "heading")]
            if (n, "display_copy") in edits:
                body = edits[(n, "display_copy")]
            head = ct.E.strip_trailing_punct(re.sub(r"[【】〖〗]", "", head))
            body = ct.E.strip_trailing_punct(body)
            f_h = ct.ImageFont.truetype(ct.E.F_MED, int(ct.E.W * 0.043))
            f_b = ct.ImageFont.truetype(ct.E.F_MED if n == 1 else ct.E.F_REG,
                                        int(ct.E.W * (0.032 if n == 1 else 0.036)))
            mw_b = int(ct.E.W * (0.78 if n == 1 else 0.86))
            out = []
            for para in [x for x in head.split("\n") if x.strip()]:
                out += ["".join(t for t, _ in L)
                        for L in ct._lines_for(para, f_h, int(ct.E.W * 0.86), False)]
            if out:
                out.append("")
            for para in [x for x in body.split("\n") if x.strip()]:
                out += ["".join(t for t, _ in L) for L in ct._lines_for(para, f_b, mw_b, n == 1)]
            rl[str(n)] = out
        if rl:
            p["rendered_lines"] = rl
            n_ok += 1
    save("posts.json", d)
    print("✓ 已更新 %d 篇的「圖上實際呈現」文字" % n_ok)


# ── 入料哨兵：ClickUp 在製中卡 × Drive 草稿 → 自動餵進 posts.json（零 AI）──
def ingest_new(args):
    """掃「在製中」且名為 IG貼文｜、尚未在 posts.json 的卡：Drive 有草稿就 from-drive 餵入。
    取代 Claude feed Part A 的機械部分；哨兵每 10 分呼叫（--limit 控制單輪量）。"""
    import urllib.parse
    token = _read_sync().get("clickup_token")
    if not token or not token.isascii():
        print("缺 clickup_token，略過入料"); return
    root = DRIVE_PRODUCE
    if not os.path.isdir(root):
        print("Drive 未掛載，略過入料"); return
    known = {p.get("clickup_task_id") for p in load("posts.json").get("posts", [])}
    try:   # 已歸檔者不得被當新卡重新入料（清存貨後的防迴圈）
        known |= {p.get("clickup_task_id") for p in load("archived-posts.json").get("posts", [])}
    except FileNotFoundError:
        pass
    try:
        tasks = _clickup("GET", "/list/901819351278/task?" +
                         urllib.parse.urlencode({"statuses[]": "在製中"}), token).get("tasks", [])
    except Exception as e:
        print("! ClickUp 查詢失敗：%s" % e); return
    todo = [t for t in tasks if t["id"] not in known
            and (t.get("name") or "").startswith("IG貼文｜")
            and "端到端測試" not in (t.get("name") or "")]
    fed = 0
    for t in todo:
        if fed >= (args.limit or 3):
            break
        topic_full = t["name"].split("｜", 1)[1]
        nt = _norm_topic(topic_full)
        # 比對兩側都走 _norm_topic：卡名與檔名的空白/標點/v+數字剝除互相抵消（「Lava」→「Laa」bug 修正）
        cand = [(x, _norm_topic(os.path.basename(x))) for x in glob.glob(os.path.join(root, "*.json"))
                if "文案初稿" in os.path.basename(x)]
        frag = next((f for f in (nt[:6], nt[:4]) if f and any(f in nb for _, nb in cand)), None)
        if not frag:
            print("⏭ 無草稿：%s" % t["name"][:36]); continue
        newest = max((x for x, nb in cand if frag in nb), key=os.path.getmtime)
        mdate = re.match(r"(\d{6,8})", os.path.basename(newest))
        pid = (mdate.group(1) if mdate else "20260000") + "-" + _slug(nt)[:12]
        ns = argparse.Namespace(drive_root=None, topic=frag, post_id=pid, finals_dir=None,
                                version=1, clickup=t["id"], topic_type="A-知識型",
                                json=None, topic_base=None)
        try:
            from_drive(ns); fed += 1
        except SystemExit:
            print("⏭ 餵入失敗：%s" % t["name"][:36])
        except Exception as e:
            print("⏭ 餵入錯誤 %s：%s" % (t["name"][:24], e))
    print("入料完成：%d 篇（佇列剩 %d 張未入）" % (fed, max(0, len(todo) - fed)))


# ── #2：發佈後把該主題舊輪 Drive 產出資料夾搬 ZZ-歸檔（控候選爆量） ──────
def archive_drive_rounds(args):
    root = args.drive_root or DRIVE_PRODUCE
    if not os.path.isdir(root):
        print("⏭ Drive 產出資料夾未掛載，略過：%s" % root); return
    p = next((x for x in load("posts.json").get("posts", []) if x["id"] == args.post_id), None)
    if not p:
        print("! 找不到貼文 %s" % args.post_id); return
    ntopic = _norm_topic(p.get("topic", "") or args.post_id)
    # 目前這一輪用到的資料夾（渲染來源＋沿用選圖）＝絕不搬
    ls = _load_local_sources().get(args.post_id, {})
    live = set()
    def _vals(x):
        return list(x.values()) if isinstance(x, dict) else (x if isinstance(x, list) else [])
    for src in _vals(ls.get("sources")) + _vals(ls.get("last_render_choices")):
        if isinstance(src, str):
            live.add(os.path.dirname(os.path.abspath(src)))
    matching = [d for d in glob.glob(os.path.join(root, "*"))
                if os.path.isdir(d) and "ZZ" not in os.path.basename(d) and _topic_match(ntopic, os.path.basename(d))]
    if not matching:
        print("⏭ %s：Drive 無符合主題的產出資料夾" % args.post_id); return
    newest = max(matching, key=os.path.getmtime)  # 保底：永遠保留最新一輪當存參
    if p.get("status") == "published":
        to_move = [d for d in matching if d != newest]           # 已發佈＝這篇完工，舊輪全歸檔
    else:
        to_move = [d for d in matching if os.path.abspath(d) not in live and d != newest]  # 在製中：保護渲染來源
    if not to_move:
        print("⏭ %s：無舊輪可歸檔（僅 %d 輪）" % (args.post_id, len(matching))); return
    dest = os.path.join(root, "ZZ-歸檔")
    os.makedirs(dest, exist_ok=True)
    if args.dry_run:
        for d in to_move:
            print("[dry] 將搬 %s → ZZ-歸檔/" % os.path.basename(d))
        return
    n = 0
    for d in to_move:
        tgt = os.path.join(dest, os.path.basename(d))
        if os.path.exists(tgt):
            tgt += "-" + datetime.datetime.now().strftime("%H%M%S")
        try:
            shutil.move(d, tgt); n += 1
        except Exception as e:
            sys.stderr.write("  ! 搬 %s 失敗：%s\n" % (os.path.basename(d), e))
    print("✓ %s：歸檔 %d 個舊輪資料夾 → ZZ-歸檔/（保留最新輪＋當前渲染來源）" % (args.post_id, n))


def forage_pending(args):
    """掃最近的 Claude 文案稿：有 visual_refs 但底圖資料夾缺對應 SHOT 檔 → 呼叫 forage_shots.py 實地截圖。
    素材線 v2（截圖策展）；哨兵每輪執行，--limit 控制單輪處理篇數。"""
    root = DRIVE_PRODUCE
    if not os.path.isdir(root):
        print("Drive 未掛載，略過 forage"); return
    jfs = sorted([f for f in glob.glob(os.path.join(root, "*.json"))
                  if "文案初稿" in os.path.basename(f) and "-Claude" in os.path.basename(f)
                  and "ZZ" not in os.path.basename(f)
                  # Drive 同步產生的同名副本「… (1).json」會被當成另一篇重抓一次
                  # （2026-08-17 實測 Drive 上有 4 份）。主檔才是流程的真值。
                  and not re.search(r"\(\d+\)\.json$", os.path.basename(f))],
                 key=os.path.getmtime, reverse=True)[:40]
    # 取樣範圍原本寫死「最新 8 份草稿」，2026-08-17 抓到後果：
    # 8/08 那批就有 10 份，8/03 那批 7 篇直接落在窗外，**永遠排不進來補素材**
    # （產品機制圖解缺 s2/s7 卡了兩週）。改成依「還缺不缺」而不是「新不新」——
    # 已補齊的草稿在下面 missing 判斷就 continue，成本只有幾次 glob。
    # 用正面表列而非「排除已發佈」：窗口放大後，Drive 裡還有大量沒有對應貼文的舊稿
    # （已歸檔、GPT 版本、實驗稿），實測 40 份裡有 16 份是這種，全抓等於白燒時間。
    pend = [ (x.get("topic") or "") for x in load("posts.json").get("posts", [])
             if x.get("status") != "published" ]
    done = 0
    for jf in jfs:
        if done >= (args.limit or 2):
            break
        try:
            d = _read_json_retry(jf)
        except Exception as e:
            print("⏭ forage 讀稿失敗 %s：%s" % (os.path.basename(jf)[:24], e))
            continue
        refs = []
        for s in d.get("slides", []):
            for vr in (s.get("visual_refs") or []):
                if vr.get("url") or vr.get("query"):   # v2.2：query 型（圖搜）與 url 型並收，role 一併傳遞
                    refs.append({"slide": s.get("index") or 1, "url": vr.get("url", ""),
                                 "query": vr.get("query", ""), "role": vr.get("role", ""),
                                 "frame_hint": vr.get("frame_hint", ""), "credit": vr.get("credit", ""),
                                 "heading": s.get("heading", ""), "display_copy": s.get("display_copy", "")})
        if not refs:
            continue
        base = os.path.basename(jf)
        date = (re.match(r"(\d{6,8})", base) or [None, ""])[1] if re.match(r"(\d{6,8})", base) else ""
        topic_raw = re.sub(r"-?文案初稿.*$", "", re.sub(r"^\d{6,8}[-\s]*", "", os.path.splitext(base)[0]))
        ntopic = _norm_topic(base)
        if not any(_topic_match(ntopic, t) for t in pend if t):
            continue
        subdirs = [dd for dd in glob.glob(os.path.join(root, "*")) if os.path.isdir(dd) and "ZZ" not in os.path.basename(dd)]
        bds = [dd for dd in subdirs if "底圖" in os.path.basename(dd) and _topic_match(ntopic, os.path.basename(dd))]
        bd = max(bds, key=os.path.getmtime) if bds else os.path.join(root, "%s %s 底圖" % (date or "20260000", topic_raw[:24]))
        missing = [r for r in refs if not glob.glob(os.path.join(bd, "slide%d-SHOT-*" % r["slide"]))]
        if not missing:
            continue
        rf = os.path.join("/private/tmp", "forage-refs-%d.json" % os.getpid())
        with open(rf, "w", encoding="utf-8") as f:
            json.dump(missing, f, ensure_ascii=False)
        sys.stderr.write("→ forage %s（%d refs）\n" % (base[:40], len(missing)))
        try:
            subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "forage_shots.py"),
                            "--refs", rf, "--outdir", bd], check=False, timeout=1500)   # 逐 slide 策展較慢；中斷則下輪續抓
        except subprocess.TimeoutExpired:
            sys.stderr.write("  ! forage timeout（下輪續抓缺檔）\n")
        done += 1
    print("forage-pending：處理 %d 篇" % done)


def quality_report(args):
    """素材線品質趨勢（quality_metrics.jsonl＋curation_log.jsonl）＋紅線判定。
    紅線：破圖>0＝🔴；YT 縮圖佔比>30%＝🟡；策展降級率>50%＝🟡。目標線見 HANDOFF §11。"""
    import collections
    def _load_jl(name):
        fp = os.path.join(DATA, name)
        rows = []
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        return rows
    cutoff = (datetime.datetime.now().astimezone() - datetime.timedelta(days=args.days)).isoformat()
    qm = [r for r in _load_jl("quality_metrics.jsonl") if r.get("ts", "") >= cutoff]
    if not qm:
        print("（近 %d 天無 forage 紀錄）" % args.days); return
    mix = collections.Counter()
    for r in qm:
        for k, v in (r.get("source_mix") or {}).items():
            mix[k] += v
    total_cand = sum(mix.values()) or 1
    thumb_pct = 100.0 * mix.get("yt_thumb", 0) / total_cand
    curated_ok = sum(1 for r in qm if r.get("curated"))
    scores = [r["curator_avg"] for r in qm if r.get("curator_avg") is not None]
    selfrej = sum(r.get("self_check_rejects", 0) for r in qm)
    fetchrej = sum(r.get("fetch_rejects", 0) for r in qm)
    composed = sum(r.get("composed", 0) for r in qm)
    print("素材線品質報告（近 %d 天，%d 次 forage）" % (args.days, len(qm)))
    print("─" * 60)
    print("合成產出：%d 張｜抓取剔除：%d｜合成自檢剔除：%d" % (composed, fetchrej, selfrej))
    print("候選來源組成：", "  ".join("%s×%d" % kv for kv in mix.most_common()))
    print("策展成功率：%d/%d（%.0f%%）｜策展平均分：%s" %
          (curated_ok, len(qm), 100.0 * curated_ok / len(qm),
           ("%.1f" % (sum(scores) / len(scores))) if scores else "—"))
    print("組圖 cover：%d 次" % sum(1 for r in qm if r.get("collage")))
    flags = []
    # 破圖以 harness 為準（操控室現況）
    import subprocess as _sp
    hv = _sp.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_pipeline.py")],
                 capture_output=True, text=True)
    broken = hv.stdout.count("🔴")
    if broken:
        flags.append("🔴 操控室存在破圖 ×%d（硬線：必須=0）" % broken)
    if thumb_pct > 30:
        flags.append("🟡 YT 縮圖佔比 %.0f%%（目標 ≤30%%）" % thumb_pct)
    if curated_ok < len(qm) * 0.5:
        flags.append("🟡 策展降級率 %.0f%%（WF14 不穩）" % (100 - 100.0 * curated_ok / len(qm)))
    print("紅線：", "；".join(flags) if flags else "✅ 全綠")
    print("（人類訊號——實選 vs 策展 top1 命中率、退圖率——累積於 curation_log/reviews，PMM 週回顧彙整）")


def gate_audit(args):
    """image_gate.jsonl 審計：按原因/貼文彙總，供校準門檻後決定是否升硬閘。"""
    fp = os.path.join(DATA, "archive", "image_gate.jsonl")
    if not os.path.exists(fp):
        print("（尚無低畫質紀錄）"); return
    import collections
    recs = []
    with open(fp, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    if args.days:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)).isoformat()
        recs = [r for r in recs if r.get("ts", "") >= cutoff]
    by_reason = collections.Counter(r.get("reason", "?") for r in recs)
    by_post = collections.Counter(r.get("post_id", "?") for r in recs)
    print("低畫質標記 %d 筆（近 %s 天）" % (len(recs), args.days or "∞"))
    print("按原因：", "  ".join("%s×%d" % kv for kv in by_reason.most_common()))
    print("按貼文：")
    for pid, n in by_post.most_common(10):
        print("  %-32s %d" % (pid[:32], n))
    print("最近 %d 筆：" % min(args.tail, len(recs)))
    for r in recs[-args.tail:]:
        print("  %s │ %s │ s%s │ %-14s │ %s" % (r.get("ts", "")[:16], r.get("post_id", "")[:24],
                                                r.get("slide"), r.get("reason"), r.get("file")))


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
    a = sub.add_parser("ingest-new", help="在製中卡×Drive 草稿 → 自動餵進操控室（哨兵用）"); a.add_argument("--limit", type=int, default=3); a.set_defaults(func=ingest_new)
    a = sub.add_parser("archive-post", help="把 demo/廢棄貼文移出主檔（不動 IG）"); a.add_argument("ids", nargs="+"); a.add_argument("--note", default=None); a.set_defaults(func=archive_post)
    a = sub.add_parser("archive-data", help="reviews/copy_edits 過期歸檔、insights 快照裁切"); a.add_argument("--days", type=int, default=90); a.set_defaults(func=archive_data)
    a = sub.add_parser("archive-drive-rounds", help="發佈後把該主題舊輪 Drive 產出搬 ZZ-歸檔"); a.add_argument("post_id"); a.add_argument("--drive-root", default=None); a.add_argument("--dry-run", action="store_true"); a.set_defaults(func=archive_drive_rounds)
    a = sub.add_parser("forage-pending", help="截圖策展：visual_refs 缺 SHOT 檔的稿實地截圖（哨兵用）"); a.add_argument("--limit", type=int, default=2); a.set_defaults(func=forage_pending)
    a = sub.add_parser("quality-report", help="素材線品質趨勢＋紅線（quality_metrics/curation_log）"); a.add_argument("--days", type=int, default=7); a.set_defaults(func=quality_report)
    a = sub.add_parser("gate-audit", help="低畫質標記審計（image_gate.jsonl 彙總）"); a.add_argument("--days", type=int, default=None); a.add_argument("--tail", type=int, default=8); a.set_defaults(func=gate_audit)
    a = sub.add_parser("post-qa", help="成篇視覺總檢（WF15）：撞主體/浮水印/不可讀/出處異常"); a.add_argument("--post-id", default=None); a.set_defaults(func=post_qa)
    a = sub.add_parser("rendered-lines", help="計算圖上實際呈現的逐行文字（供操控室對照）"); a.add_argument("--post-id", default=None); a.add_argument("--all", action="store_true"); a.set_defaults(func=rendered_lines)
    a = sub.add_parser("alert", help="哨兵自報告警 → ClickUp 告警日誌卡留言"); a.add_argument("message"); a.set_defaults(func=alert)
    a = sub.add_parser("push"); a.add_argument("message"); a.set_defaults(func=push)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
