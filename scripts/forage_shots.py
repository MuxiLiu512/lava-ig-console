#!/usr/bin/env python3
# forage_shots.py — 截圖策展 forager v2.1（品質迴圈＋受眾視角策展）。
#
# 「講誰就截誰」＋三層品質保障（2026-07-30 Jesse 驗收回饋版）：
#  A 抓取驗證：所有下載過驗（bytes/尺寸/純色/白牆），書封 fallback 鏈，YT 影格×3＋縮圖=4 候選
#  B 構圖：16:9 顯著性滿版裁切（取代模糊補邊）；cover 組圖（Weekend Club 式拼貼）；合成後自檢
#  C 策展：候選進 staging → n8n WF14 受眾視角評分排名（Claude vision）→ 多樣性配額 → 優勝才合成
#  D 指標：quality_metrics.jsonl / curation_log.jsonl / forage_learnings.json（牆站策略自累積）
# 版權：引用式使用＋出處標注（HANDOFF §11）。產物一律本地先寫再搬 Drive。
#
# 用法：
#   python3 forage_shots.py --refs refs.json --outdir <Drive底圖資料夾> [--post-id id]
#   python3 forage_shots.py --draft <文案.json> --outdir <dir>   # 讀 slides[].visual_refs＋文案供策展
import os, sys, json, re, argparse, subprocess, tempfile, shutil, hashlib, base64, datetime
from urllib.request import Request, urlopen

from PIL import Image, ImageFilter, ImageStat, ImageDraw

W, H = 1950, 2438
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DATA = os.path.join(REPO, "data")
BROWSE = os.path.expanduser("~/.claude/skills/gstack/browse/dist/browse")   # raw Chrome headless 會與運行中 Chrome 衝突，勿用
YTDLP = os.path.join(SCRIPT_DIR, "bin", "yt-dlp")
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
CURATOR_URL = "https://lavadating.app.n8n.cloud/webhook/lava-ig-curate"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0 Safari/537.36"
LEARN_FP = os.path.join(DATA, "forage_learnings.json")
# 暫存路徑 → 搜尋引擎（apify／ddg）。credits 落檔時併進出處字串。
ENGINE_OF = {}
NOW = lambda: datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ── 驗證 ────────────────────────────────────────────────────────────
def _valid_img(path, min_dim=400, min_bytes=8000):
    """下載/影格驗證：太小、近純色、全黑全白 → (False, 原因)。"""
    try:
        if os.path.getsize(path) < min_bytes:
            return False, "太小(%dB)" % os.path.getsize(path)
        im = Image.open(path).convert("RGB")
        if min(im.size) < min_dim:
            return False, "解析度不足(%dx%d)" % im.size
        s = im.resize((48, 48))
        st = ImageStat.Stat(s)
        if max(st.stddev) < 8:
            return False, "近純色"
        mean = sum(st.mean) / 3
        if mean < 12 or mean > 243:
            return False, "全黑/全白"
        return True, None
    except Exception as e:
        return False, "不可讀:%s" % type(e).__name__


def _whiteness(path):
    """白色佔比（登入牆/空頁偵測）。"""
    try:
        g = Image.open(path).convert("L").resize((64, 64))
        px = list(g.getdata())
        return sum(1 for v in px if v > 235) / len(px)
    except Exception:
        return 1.0


# ── 牆站學習表（快迴圈） ─────────────────────────────────────────────
def _learn_load():
    try:
        return json.load(open(LEARN_FP, encoding="utf-8"))
    except Exception:
        return {}


def _learn_wall(domain, why):
    d = _learn_load()
    rec = d.get(domain) or {"fails": 0}
    rec.update({"strategy": "skip_screenshot", "fails": rec.get("fails", 0) + 1, "why": why, "last": NOW()})
    d[domain] = rec
    os.makedirs(DATA, exist_ok=True)
    tmp = LEARN_FP + ".part"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, LEARN_FP)


def _domain(url):
    m = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return m.lower()


# ── 基礎抓取 ─────────────────────────────────────────────────────────
def _fetch(url, timeout=25):
    r = Request(url, headers={"User-Agent": UA})
    with urlopen(r, timeout=timeout) as f:
        return f.read()


def _yt_id(url):
    for pat in (r"[?&]v=([\w-]{6,})", r"youtu\.be/([\w-]{6,})", r"/shorts/([\w-]{6,})", r"/embed/([\w-]{6,})"):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _tw_id(url):
    m = re.search(r"(?:twitter|x)\.com/[^/]+/status/(\d+)", url)
    return m.group(1) if m else None


def _ig_code(url):
    m = re.search(r"instagram\.com/(?:p|reel|reels)/([\w-]+)", url)
    return m.group(1) if m else None


def _b(*args, timeout=90):
    return subprocess.run([BROWSE] + list(args), capture_output=True, text=True, timeout=timeout)


def _screenshot(target, size, out, viewport_only):
    _b("viewport", size, "--scale", "2")
    nav = _b("goto", target)
    if "Navigated" not in (nav.stdout or "") + (nav.stderr or ""):
        return False
    _b("cleanup", "--all", timeout=40)
    if viewport_only:
        _b("screenshot", "--viewport", out, timeout=60)
    else:
        _b("screenshot", out, timeout=60)
    return os.path.exists(out) and os.path.getsize(out) > 20000


# ── 各型抓取器：回傳候選清單 [(path, source_type)] ─────────────────────
def grab_youtube(url, work):
    yid = _yt_id(url)
    cands, rejects = [], []
    # 縮圖
    for name in ("maxresdefault", "hq720", "sddefault"):
        try:
            data = _fetch("https://i.ytimg.com/vi/%s/%s.jpg" % (yid, name))
            p = os.path.join(work, "yt-%s-thumb.jpg" % yid)
            open(p, "wb").write(data)
            ok, why = _valid_img(p, min_dim=380)
            if ok:
                cands.append((p, "yt_thumb")); break
            rejects.append(("thumb", why))
        except Exception:
            continue
    # 影格 ×3（25/50/75%）：串流抽格——拿直連 URL 讓 ffmpeg range-seek，不下載整支影片
    if os.path.exists(YTDLP) and os.path.exists(FFMPEG):
        try:
            meta = subprocess.run([YTDLP, "--no-playlist", "--print", "duration", "--print", "urls",
                                   "-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]/b[height<=1080]/b",
                                   url], capture_output=True, text=True, timeout=90)
            lines = [x for x in (meta.stdout or "").strip().splitlines() if x.strip()]
            dur = float(lines[0]) if lines and re.match(r"^[\d.]+$", lines[0]) else 0
            surl = lines[1] if len(lines) > 1 else None
            if surl and dur > 8:
                for i, frac in enumerate((0.25, 0.5, 0.75)):
                    fp = os.path.join(work, "yt-%s-f%d.jpg" % (yid, i))
                    subprocess.run([FFMPEG, "-ss", str(max(1, int(dur * frac))), "-i", surl,
                                    "-frames:v", "1", "-q:v", "3", "-y", fp],
                                   capture_output=True, timeout=90)
                    # 低清影格閘門：來源是老 webcam/低畫質串流時，放大只會更糊——寧退回縮圖
                    ok, why = _valid_img(fp, min_dim=560)
                    if ok:
                        cands.append((fp, "yt_frame"))
                    else:
                        rejects.append(("f%d" % i, why))
            elif not surl:
                rejects.append(("video", "無串流 URL"))
        except Exception as e:
            rejects.append(("video", type(e).__name__))
    return cands, rejects


def grab_image(url, work):
    """直接圖檔（含書封 fallback 鏈）。"""
    rejects = []
    u = url
    if "covers.openlibrary.org" in u and "default=false" not in u:
        u += ("&" if "?" in u else "?") + "default=false"   # 無封面回 404 而非 43B 佔位圖
    try:
        data = _fetch(u)
        p = os.path.join(work, "img-" + hashlib.md5(url.encode()).hexdigest()[:8] + ".img")
        open(p, "wb").write(data)
        ok, why = _valid_img(p, min_dim=380, min_bytes=6000)
        if ok:
            return [(p, "book" if "openlibrary" in u or "books.google" in u else "image")], rejects
        rejects.append((u[:50], why))
    except Exception as e:
        rejects.append((u[:50], type(e).__name__))
    # 書封 fallback 鏈：OL search API（cover_i）→ Google Books
    mi = re.search(r"isbn/(\d{10,13})", url)
    if mi:
        try:
            j = json.loads(_fetch("https://openlibrary.org/search.json?isbn=%s&fields=cover_i&limit=1" % mi.group(1)).decode())
            ci = ((j.get("docs") or [{}])[0]).get("cover_i")
            if ci:
                data = _fetch("https://covers.openlibrary.org/b/id/%s-L.jpg?default=false" % ci)
                p = os.path.join(work, "olci-%s.jpg" % ci)
                open(p, "wb").write(data)
                ok, why = _valid_img(p, min_dim=300, min_bytes=6000)
                if ok:
                    return [(p, "book")], rejects
                rejects.append(("ol-cover_i", why))
        except Exception as e:
            rejects.append(("ol-search", type(e).__name__))
        try:
            j = json.loads(_fetch("https://www.googleapis.com/books/v1/volumes?q=isbn:" + mi.group(1)).decode())
            th = (((j.get("items") or [{}])[0].get("volumeInfo") or {}).get("imageLinks") or {}).get("thumbnail")
            if th:
                th = th.replace("http://", "https://").replace("zoom=1", "zoom=3")
                data = _fetch(th)
                p = os.path.join(work, "gb-" + mi.group(1) + ".jpg")
                open(p, "wb").write(data)
                ok, why = _valid_img(p, min_dim=300, min_bytes=6000)   # GB 縮圖較小，放寬下限
                if ok:
                    return [(p, "book")], rejects
                rejects.append(("googlebooks", why))
        except Exception as e:
            rejects.append(("googlebooks", type(e).__name__))
    return [], rejects


def grab_browser(url, work):
    """推文/IG embed/網頁截圖（含牆站策略）。"""
    rejects = []
    tid, igc = _tw_id(url), _ig_code(url)
    dom = _domain(url)
    learn = _learn_load()
    if not tid and not igc and (learn.get(dom) or {}).get("strategy") == "skip_screenshot":
        return [], [(dom, "已知牆站，跳過截圖")]
    if tid:
        target, size, st, vp = "https://platform.twitter.com/embed/Tweet.html?id=%s&theme=light&width=1000" % tid, "1050x1400", "tweet", False
    elif igc:
        target, size, st, vp = "https://www.instagram.com/p/%s/embed/captioned/" % igc, "900x1600", "ig", False
    else:
        target, size, st, vp = url, "1440x1900", "article", True
    out = os.path.join(work, "shot-" + hashlib.md5(url.encode()).hexdigest()[:8] + ".png")
    try:
        if not _screenshot(target, size, out, vp):
            return [], [(dom, "截圖失敗")]
    except subprocess.TimeoutExpired:
        return [], [(dom, "browse timeout")]
    wh = _whiteness(out)
    if wh > 0.90:
        _learn_wall(dom, "近白頁 %.0f%%（登入牆/空頁）" % (wh * 100))
        return [], [(dom, "白頁牆 %.0f%%" % (wh * 100))]
    ok, why = _valid_img(out, min_dim=500)
    if not ok:
        return [], [(dom, why)]
    return [(out, st)], rejects


def _apify_images(query, want):
    """Apify Google Images → [{m: 原圖URL, t: 縮圖URL, w, h}]。沒設 token 就回空，交給 DDG 備援。

    為什麼換掉 DuckDuckGo〔2026-08-25 Jesse 退件：「來源看起來就沒有上網找過，
    不是媒體的品質」〕：舊版刮的是 DDG 的未公開 i.js 端點，要先從 HTML 撈 vqd token，
    對方一改版就整條斷；而且 DDG 的圖片索引本來就比 Google 弱，排序差＝相關性差。
    Apify 走正式 API、回傳真實長寬，可以在下載前就濾掉小圖。
    """
    tok = _sync_get("apify_token")
    if not tok:
        return []
    # 預設 johnvc：2026-08-25 兩支實測「Park Eun-bin drama still」——
    # hooli（4.48★、6028 人、Apify 官方）回的是狗美容、莎麗上衣、阿里巴巴，幾乎全不相關；
    # johnvc（5.00★、147 人、社群）前 10 筆 9 筆命中，來源是 Korea Herald／SCMP／Forbes／Tatler。
    # 教訓：Apify 的「成功率 99.9%」只計「有沒有跑完」，不計結果對不對——星等與官方維護
    # 都不能取代實測。johnvc 還便宜 19 倍（$0.10 vs $1.90／千張）。
    actor = _sync_get("apify_image_actor") or "johnvc~google-images-api"
    url = ("https://api.apify.com/v2/acts/%s/run-sync-get-dataset-items?token=%s"
           % (actor, tok))
    body = json.dumps({"queries": [query], "maxResultsPerQuery": max(want * 3, 20)}).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as r:
            rows = json.load(r)
    except Exception as e:
        sys.stderr.write("  ! Apify 圖搜失敗（%s），改用備援\n" % type(e).__name__)
        return []
    out = []
    for x in rows if isinstance(rows, list) else []:
        m = x.get("imageUrl") or x.get("image") or ""
        t = x.get("thumbnailUrl") or x.get("thumbnail") or m
        w = int(x.get("imageWidth") or x.get("width") or 0)
        h = int(x.get("imageHeight") or x.get("height") or 0)
        if m and w >= 850:
            out.append({"m": m, "t": t, "w": w, "h": h})
    return out


def _sync_get(key):
    """讀 .sync.json 的設定值。token 永遠只在本機，不進 repo。"""
    try:
        with open(os.path.join(REPO, ".sync.json"), encoding="utf-8") as f:
            return json.load(f).get(key) or ""
    except Exception:
        return ""


def grab_imagesearch(query, work, want=6, source_type="mood"):
    """圖片搜尋（Bing Images via browse daemon）→ 抓 top N 原圖並驗證。
    視覺企劃層 v2.2：人物多場合照/情緒場景圖/持書照都靠這個（wknd 的 art direction 做法）。"""
    cands, rejects = [], []
    STOCK_BLOCK = ("alamy.", "gettyimages.", "shutterstock.", "istockphoto.", "dreamstime.",
                   "123rf.", "depositphotos.", "freepik.", "vecteezy.", "stock.adobe.",
                   "qiantucdn.", "58pic.", "nipic.", "mindframe.", "magnific.", "canva.",
                   "envato.", "pond5.", "bigstockphoto.", "shutterfly.", "photodune.", "stocksy.")
    # 主要來源：Apify Google Images（排序品質遠勝 DDG）。沒 token 或失敗就落到下面的備援。
    pairs = [x for x in _apify_images(query, want)
             if not any(sb in x["m"] for sb in STOCK_BLOCK)]
    if pairs:
        src_name = "apify"
    else:
        src_name = "ddg"
    try:
        if pairs:
            raise StopIteration          # 已有 Apify 結果，跳過備援
        from urllib.parse import quote
        # DuckDuckGo Images API：l=us-en 鎖美區（Bing 會被 geo/cookies 蓋掉 mkt 而撈回中文商用圖庫）；
        # thumbnail 走 DDG 官方代理必可抓（縮圖先策展），image=原圖 URL 供勝者抓取；附原始寬高可預濾
        html = _fetch("https://duckduckgo.com/?q=%s&iax=images&ia=images" % quote(query)).decode(errors="ignore")
        mv = re.search(r"vqd=([\d-]+)", html) or re.search(r'vqd="([^"]+)"', html)
        if not mv:
            return [], [(query[:40], "ddg vqd 不可得")]
        j = json.loads(_fetch("https://duckduckgo.com/i.js?l=us-en&o=json&q=%s&vqd=%s&f=,,,&p=1" % (quote(query), mv.group(1))).decode(errors="ignore"))
        pairs = []
        for res in j.get("results", []):
            img_u = res.get("image") or ""
            if any(s in img_u for s in STOCK_BLOCK):
                continue
            if res.get("width", 0) >= 850 and img_u and res.get("thumbnail"):
                pairs.append({"m": img_u, "t": res["thumbnail"]})
            if len(pairs) >= want * 3:
                break
    except StopIteration:
        pass
    except Exception as e:
        if not pairs:
            return [], [(query[:40], "圖搜:%s" % type(e).__name__)]
    if pairs:
        sys.stderr.write("    圖搜來源 %s：%d 筆\n" % (src_name, len(pairs)))
    # 縮圖先行：staging 用 Bing 縮圖（永遠抓得到→無「盜連站倖存偏差」），策展勝出後才抓原圖
    for it in pairs:
        if len(cands) >= want:
            break
        tu = it.get("t") or it["m"]
        try:
            data = _fetch(tu, timeout=15)
            p = os.path.join(work, "is-" + hashlib.md5(it["m"].encode()).hexdigest()[:10] + ".img")
            open(p, "wb").write(data)
            ok, why = _valid_img(p, min_dim=260, min_bytes=6000)   # 縮圖階段放寬；原圖階段再嚴驗
            if ok:
                # 帶上搜尋引擎：Jesse 2026-08-27 要「標注照片的來源」，
                # 而且劇照與 Apify 兩條路並存時，要能分辨哪張是誰找來的，
                # 否則永遠無法比較兩個來源的品質（這正是「看不出差異」的原因）。
                ENGINE_OF[p] = src_name
                cands.append((p, source_type, it["m"]))
            else:
                rejects.append((tu[:40], why))
        except Exception as e:
            rejects.append((tu[:40], type(e).__name__))
    return cands, rejects


def grab(url, work):
    if _yt_id(url):
        return grab_youtube(url, work)
    if re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I) or "covers.openlibrary" in url or "books.google" in url:
        return grab_image(url, work)
    return grab_browser(url, work)


# ── 構圖 ─────────────────────────────────────────────────────────────
def _autocrop(im):
    g = im.convert("L")
    bg = g.getpixel((2, 2))
    try:
        from PIL import ImageChops
        diff = ImageChops.difference(g, Image.new("L", g.size, bg))
        bbox = diff.getbbox()
        if bbox:
            pad = 14
            l, t, r, b = bbox
            return im.crop((max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad)))
    except Exception:
        pass
    return im


def _saliency_crop(im, focus_x=None):
    """寬圖 → 4:5 滿版。focus_x（策展員 vision 回報的主體水平位置 0-100）優先；無則邊緣+膚色掃描。"""
    scale = max(W / im.width, H / im.height)
    big = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    if big.width <= W + 8:
        x = (big.width - W) // 2
        return big.crop((x, 0, x + W, H))
    if focus_x is not None:
        X = int(big.width * focus_x / 100 - W / 2)
        X = max(0, min(big.width - W, X))
        return big.crop((X, 0, X + W, H))
    small = big.resize((big.width // 8, big.height // 8))
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES)
    # 膚色圖（人臉/手的粗略偵測）：主體權重遠高於背景欄杆/枝葉的硬邊
    px = small.load()
    skin = Image.new("L", small.size, 0)
    sp = skin.load()
    for yy in range(small.height):
        for xx in range(small.width):
            r, g, bch = px[xx, yy][:3]
            # r-g ≥ 12 排除米色牆/淺木頭（牆面 r≈g，膚色紅通道明顯高）
            if r > 90 and g > 40 and bch > 20 and (r - g) >= 12 and g >= bch and (r - bch) > 18 and (r - g) < 90:
                sp[xx, yy] = 255
    win = W // 8
    best_x, best_e = 0, -1
    step = max(4, (small.width - win) // 32)
    for x in range(0, small.width - win + 1, step):
        box = (x, 0, x + win, small.height)
        e = ImageStat.Stat(edges.crop(box)).mean[0]
        s = ImageStat.Stat(skin.crop(box)).mean[0]
        cx = (x + win / 2) / small.width
        score = e * 0.4 + s * 2.2   # 膚色主導；邊緣其次
        score *= 1.0 - 0.15 * abs(cx - 0.5)
        if score > best_e:
            best_e, best_x = score, x
    X = min(big.width - W, best_x * 8)
    return big.crop((X, 0, X + W, H))


def compose(src_path, source_type, focus_x=None):
    im = Image.open(src_path).convert("RGB")
    if source_type in ("tweet", "ig", "article", "book"):
        im = _autocrop(im)
    ar = im.width / im.height
    if ar <= 1.05:   # 直式/近 4:5（文章/embed/書封）→ 滿版鎖頂
        scale = max(W / im.width, H / im.height)
        im2 = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        x = (im2.width - W) // 2
        out = im2.crop((x, 0, x + W, H))
    else:
        # 寬圖（yt 16:9）→ 頂錨完整呈現＋下方漸層入黑（Jesse 裁決：不強制滿版，
        # 引擎文字壓下半部、遮罩會漸層變黑——圖保完整、構圖美觀優先）。
        # focus_x 仍用於超寬圖的水平取景（寬到 top 區塞不下時輕裁）。
        tw = W
        th = round(tw * im.height / im.width)
        if th < int(H * 0.34):   # 過寬（如超寬螢幕）→ 依 focus_x 輕裁到 16:9 再頂錨
            im = _saliency_crop_to(im, 16 / 9, focus_x)
            th = round(W * im.height / im.width)
        top = im.resize((tw, th), Image.LANCZOS)
        # 底場：影像底緣模糊延伸並壓暗，與引擎遮罩無縫銜接
        strip = im.crop((0, int(im.height * 0.7), im.width, im.height))
        field = strip.resize((W, H - th), Image.LANCZOS).filter(ImageFilter.GaussianBlur(90))
        field = Image.eval(field, lambda v: int(v * 0.30))
        out = Image.new("RGB", (W, H))
        out.paste(top, (0, 0))
        out.paste(field, (0, th))
        # 接縫 220px 漸層融合
        fade_h = min(220, H - th)
        if fade_h > 10:
            seam_src = top.crop((0, th - fade_h, W, th)) if th >= fade_h else top
            dark = Image.eval(seam_src.resize((W, fade_h)).filter(ImageFilter.GaussianBlur(40)), lambda v: int(v * 0.30))
            mask = Image.new("L", (W, fade_h))
            md = ImageDraw.Draw(mask)
            for yy in range(fade_h):
                md.line([(0, yy), (W, yy)], fill=int(255 * yy / fade_h))
            out.paste(dark, (0, th - fade_h), mask)
    if source_type in ("yt_frame", "yt_thumb"):
        out = out.filter(ImageFilter.UnsharpMask(radius=2, percent=85, threshold=3))   # 放大後補銳
    return out


def _saliency_crop_to(im, target_ar, focus_x=None):
    """把超寬圖水平裁到 target_ar（focus_x 取景）。"""
    tw = int(im.height * target_ar)
    if tw >= im.width:
        return im
    if focus_x is not None:
        X = int(im.width * focus_x / 100 - tw / 2)
    else:
        X = (im.width - tw) // 2
    X = max(0, min(im.width - tw, X))
    return im.crop((X, 0, X + tw, im.height))


def compose_collage(items, seed=7):
    """Cover 組圖（Weekend Club 式）：白框卡全幅散排。items=[(path, source_type, dedup_key)]。
    v2.1.2：①同源去重（同支影片只進一張）②旋轉用 RGBA 透明角（原本黑角蓋卡＝破圖感）③環境底＝首圖模糊放大，不再是死黑。"""
    import random
    rnd = random.Random(seed)
    seen_keys, picks = set(), []
    for it in items:
        p, st = it[0], it[1]
        key = it[2] if len(it) > 2 and it[2] else p
        if key in seen_keys:
            continue
        seen_keys.add(key)
        picks.append((p, st))
        if len(picks) >= 5:
            break
    # 環境底：用第一張模糊放大壓暗（有機質感），避免大片死黑像破圖
    try:
        base = Image.open(picks[0][0]).convert("RGB")
        bg = base.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(80))
        bg = Image.eval(bg, lambda v: int(v * 0.32))
    except Exception:
        bg = Image.new("RGB", (W, H), (16, 16, 18))
    n = Image.effect_noise((W // 2, H // 2), 18).resize((W, H)).convert("L")
    bg = Image.blend(bg, Image.merge("RGB", (n, n, n)), 0.04)
    slots = [(0.02, 0.02, 0.56), (0.46, 0.09, 0.52), (0.03, 0.37, 0.52), (0.48, 0.47, 0.50), (0.20, 0.70, 0.56)]
    for i, (p, st) in enumerate(picks):
        try:
            im = Image.open(p).convert("RGB")
            if st in ("tweet", "ig", "article", "book"):
                im = _autocrop(im)
            fx, fy, fw = slots[i % len(slots)]
            tw = int(W * fw)
            th = int(tw * im.height / im.width)
            th = min(th, int(H * 0.38))
            im = im.resize((tw, int(tw * im.height / im.width)), Image.LANCZOS)
            if im.height > th:
                im = im.crop((0, 0, tw, th))
            card = Image.new("RGBA", (im.width + 24, im.height + 24), (245, 243, 238, 255))
            card.paste(im, (12, 12))
            card = card.rotate(rnd.uniform(-3.5, 3.5), expand=True, fillcolor=(0, 0, 0, 0))
            bg.paste(card.convert("RGB"), (int(W * fx), int(H * fy)), card.split()[3])   # alpha 遮罩＝透明角
        except Exception:
            continue
    return bg


# ── 策展（WF14 受眾視角） ────────────────────────────────────────────
def _b64_small(path, max_px=512):
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_px, max_px))
    import io
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78)
    return base64.b64encode(buf.getvalue()).decode()


def curate(staged, copy_by_slide, slide_intent=None):
    """staged={n:[{id,path,source_type,credit}]} → WF14 評分排名。失敗＝啟發式降級。回傳 (ranking{n:[id...]}, scores, curated_bool)。"""
    payload = {"slides": []}
    for n in sorted(staged):
        cds = staged[n]
        if not cds:
            continue
        cp = copy_by_slide.get(n, {})
        it = (slide_intent or {}).get(n, {})
        payload["slides"].append({
            "n": n, "heading": cp.get("heading", ""), "display_copy": cp.get("display_copy", "")[:200],
            "role": it.get("role", ""), "intent_query": it.get("query", ""),
            "candidates": [{"id": c["id"], "source_type": c["source_type"], "b64": _b64_small(c["path"])} for c in cds]})
    ranking, scores, focus = {}, {}, {}
    ok_any = False
    for sl in payload["slides"]:   # 逐 slide 分批（整包 30+ 張會逾時；單批 ≤8 張穩定）
        try:
            req = Request(CURATOR_URL, data=json.dumps({"slides": [sl]}).encode(), headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=150) as f:
                res = json.loads(f.read().decode())
            v = (res.get("slides") or {}).get(str(sl["n"])) or (res.get("slides") or {}).get(sl["n"])
            if v and v.get("ranking"):
                ranking[sl["n"]] = v["ranking"]
                scores[sl["n"]] = v.get("scores", {})
                for cid_, fx in (v.get("focus") or {}).items():
                    try:
                        focus[cid_] = max(0, min(100, int(fx)))
                    except Exception:
                        pass
                ok_any = True
            else:
                sys.stderr.write("  ! s%s 策展回應無 ranking → 該張啟發式\n" % sl["n"])
        except Exception as e:
            sys.stderr.write("  ! s%s 策展失敗（%s）→ 該張啟發式\n" % (sl["n"], type(e).__name__))
    if ok_any:
        pref = {"yt_frame": 0, "mood": 0, "person": 0, "book": 1, "article": 1, "tweet": 3, "ig": 4, "image": 5, "yt_thumb": 6}
        for n, cds in staged.items():
            if n not in ranking:
                ranking[n] = [c["id"] for c in sorted(cds, key=lambda c: pref.get(c["source_type"], 9))]
        return ranking, scores, focus, True
    pref = {"yt_frame": 0, "article": 1, "book": 2, "tweet": 3, "ig": 4, "image": 5, "yt_thumb": 6}
    ranking = {n: [c["id"] for c in sorted(cds, key=lambda c: pref.get(c["source_type"], 9))] for n, cds in staged.items()}
    return ranking, {}, {}, False


def apply_quota(staged, ranking, max_thumb=2):
    """多樣性配額：全篇 yt_thumb 首選 ≤ max_thumb，超額改用該 slide 次選的非縮圖。"""
    id2 = {c["id"]: c for cds in staged.values() for c in cds}
    thumbs = [n for n in ranking if ranking[n] and id2.get(ranking[n][0], {}).get("source_type") == "yt_thumb"]
    for n in thumbs[max_thumb:]:
        alt = next((cid for cid in ranking[n][1:] if id2.get(cid, {}).get("source_type") != "yt_thumb"), None)
        if alt:
            ranking[n] = [alt] + [c for c in ranking[n] if c != alt]
    return ranking


# ── 主流程 ───────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs")
    ap.add_argument("--draft")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--post-id", default=None)
    a = ap.parse_args()
    refs, copy_by_slide = [], {}
    if a.refs:
        refs = json.load(open(a.refs, encoding="utf-8"))
        for r in refs:
            if r.get("heading") or r.get("display_copy"):
                copy_by_slide[r.get("slide") or 1] = {"heading": r.get("heading", ""), "display_copy": r.get("display_copy", "")}
    elif a.draft:
        d = json.load(open(a.draft, encoding="utf-8"))
        for s in d.get("slides", []):
            n = s.get("index") or 1
            copy_by_slide[n] = {"heading": s.get("heading", ""), "display_copy": s.get("display_copy", "")}
            for vr in (s.get("visual_refs") or []):
                if vr.get("url") or vr.get("query"):
                    refs.append({"slide": n, "url": vr.get("url", ""), "query": vr.get("query", ""),
                                 "role": vr.get("role", ""), "frame_hint": vr.get("frame_hint", ""),
                                 "credit": vr.get("credit", "")})
    if not refs:
        sys.exit("✗ 無 refs")
    os.makedirs(a.outdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="forage-", dir="/private/tmp")   # browse daemon 只允許 /private/tmp 或 repo
    try:   # 死 ref 記憶：同一 (url|query|role) 連敗 2 次後不再重試（防哨兵每輪燒 timeout）
        _learn = json.load(open(LEARN_FP, encoding="utf-8"))
    except Exception:
        _learn = {}
    ref_fails = dict(_learn.get("ref_fails") or {})
    staged, all_rejects, cid = {}, [], 0
    slide_intent = {}
    for r in refs:
        n = r.get("slide") or 1
        role = (r.get("role") or "").strip().lower()
        q = (r.get("query") or "").strip()
        u = (r.get("url") or "").strip()
        if not u and not q:
            continue
        rkey = hashlib.md5(("%s|%s|%s" % (u, q, role)).encode()).hexdigest()[:12]
        if ref_fails.get(rkey, 0) >= 2:
            sys.stderr.write("  ⏭ s%d 死ref跳過（連敗%d）：%s\n" % (n, ref_fails[rkey], (u or q)[:48]))
            continue
        if not role:
            role = "evidence" if u else "mood"
        cands, rejects = [], []
        try:
            # 視覺企劃層（v2.2）：按角色決定找圖方式——wknd 的 art direction 邏輯
            if q and role in ("person", "mood", "book"):
                cands, rejects = grab_imagesearch(q, work, want=(5 if role == "book" else 7), source_type=role)
                if u and role == "person":   # 人物張補指定影片的影格（多場合多樣性）
                    c2, r2 = grab(u, work); cands += c2; rejects += r2
                if not cands and u:          # 圖搜空手 → 退回 URL 路徑
                    c2, r2 = grab(u, work); cands += c2; rejects += r2
            elif u:
                cands, rejects = grab(u, work)
        except Exception as e:
            rejects = [((u or q)[:50], type(e).__name__)]
        all_rejects += [(n,) + x for x in rejects]
        credit_val = "" if role == "mood" else (r.get("credit") or u or q)   # 情緒圖不標出處（Jesse 2026-08-01 裁決，wknd 同標準）
        slide_intent.setdefault(n, {"role": role, "query": q or r.get("frame_hint", "")})
        for c_it in cands:
            p, st = c_it[0], c_it[1]
            murl = c_it[2] if len(c_it) > 2 else None
            cid += 1
            staged.setdefault(n, []).append({"id": "c%d" % cid, "path": p, "source_type": st,
                                             "credit": credit_val, "murl": murl, "role": role,
                                             "src_key": _yt_id(u) or hashlib.md5(open(p, "rb").read(8192)).hexdigest()[:10]})
        if cands:
            sys.stderr.write("  ✓ s%d %s → %d 候選\n" % (n, (r.get("url") or "")[:56], len(cands)))
            ref_fails.pop(rkey, None)
        else:
            sys.stderr.write("  ✗ s%d %s（%s）\n" % (n, (r.get("url") or "")[:56], "; ".join("%s:%s" % x for x in rejects)[:80]))
            ref_fails[rkey] = ref_fails.get(rkey, 0) + 1
    try:   # 回寫死 ref 記憶（re-read merge：避免蓋掉 grab_browser 期間累積的牆站學習）
        cur = json.load(open(LEARN_FP, encoding="utf-8"))
    except Exception:
        cur = {}
    mg = cur.setdefault("ref_fails", {})
    for k, v in ref_fails.items():
        mg[k] = max(v, mg.get(k, 0))
    try:
        json.dump(cur, open(LEARN_FP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    if not staged:
        print("完成：0 張（全部抓取失敗）")
        _metrics(a, refs, staged, all_rejects, {}, False, 0, False)
        sys.exit(1)
    ranking, scores, focus, curated = curate(staged, copy_by_slide, slide_intent)
    ranking = apply_quota(staged, ranking)
    _log_curation(a, staged, ranking, scores, curated)
    # 合成優勝（每 slide 首選＋次選）；cover（最小 slide）優先組圖
    id2 = {c["id"]: c for cds in staged.values() for c in cds}
    credfile = os.path.join(a.outdir, "shots_credits.json")
    credits = {}
    if os.path.exists(credfile):
        try:
            credits = json.load(open(credfile, encoding="utf-8"))
        except Exception:
            credits = {}
    made, selfrej = 0, 0
    winners_all = []
    for n in sorted(ranking):
        for cid_ in ranking[n][:1]:
            winners_all.append(id2[cid_])
    cover_n = min(ranking) if ranking else 1
    id2score = {}
    for n, sc in scores.items():
        id2score.update(sc)
    MIN_SCORE = 5   # 分數線：策展 top 也低於此＝該張寧缺勿爛（防「垃圾裡挑垃圾」）
    resolved = {}   # {n: [c...]}，murl 已換抓原圖並通過嚴驗
    for n in sorted(ranking):
        keep = []
        for cid_ in ranking[n]:
            if len(keep) >= 2:
                break
            c = id2[cid_]
            if curated and id2score.get(cid_) is not None and id2score[cid_] < MIN_SCORE:
                continue
            path = c["path"]
            if c.get("murl"):   # 縮圖先策展；勝者才抓原圖（避開盜連倖存偏差）
                try:
                    data = _fetch(c["murl"], timeout=25)
                    fpth = os.path.join(work, "full-" + hashlib.md5(c["murl"].encode()).hexdigest()[:10] + ".img")
                    open(fpth, "wb").write(data)
                    ok, why = _valid_img(fpth, min_dim=550, min_bytes=15000)
                    if not ok:
                        sys.stderr.write("  ↩ 原圖不合格 %s（%s）→ 用次名\n" % (c["murl"][:44], why)); continue
                    path = fpth
                except Exception as e:
                    sys.stderr.write("  ↩ 原圖抓取失敗（%s）→ 用次名\n" % type(e).__name__); continue
            keep.append(dict(c, path=path, _cid=cid_))
        if not keep and ranking[n]:
            sys.stderr.write("  ✋ s%d 全部候選未達分數線/原圖不可得，該張不出 SHOT\n" % n)
        resolved[n] = keep
    winners_all = [ks[0] for ks in (resolved[n] for n in sorted(resolved)) if ks]
    if len(winners_all) >= 3:
        seed = sum(ord(ch) for ch in (a.post_id or os.path.basename(a.outdir))) & 0xFFFF
        col = compose_collage([(c["path"], c["source_type"], c.get("src_key")) for c in winners_all], seed)
        fn = "slide%d-SHOT-b-collage.png" % cover_n   # 封面雙版：a=單張 hero（wknd 式）、b=組圖（timeleft 式），操控室挑
        if _write_checked(col, os.path.join(a.outdir, fn), work):
            credits[fn] = "組圖：" + "；".join(dict.fromkeys(c["credit"] for c in winners_all[:4] if c["credit"]))
            made += 1
        else:
            selfrej += 1
    for n in sorted(resolved):
        for rank_i, c in enumerate(resolved[n]):
            eng = ENGINE_OF.get(c["path"], "")
            slug = ("ap" if eng == "apify" else "") + \
                   re.sub(r"[^A-Za-z0-9]+", "", c["source_type"])[:10] + hashlib.md5(c["path"].encode()).hexdigest()[:5]
            is_cover_dual = (n == cover_n and len(winners_all) >= 3)
            letter = ("a" if rank_i == 0 else ("c" if is_cover_dual else "b"))   # 封面：a=hero、b=組圖、c=次選
            fn = "slide%d-SHOT-%s-%s.png" % (n, letter, slug)
            fp = os.path.join(a.outdir, fn)
            if os.path.exists(fp):
                continue
            img = compose(c["path"], c["source_type"], focus.get(c["_cid"]))
            if _write_checked(img, fp, work):
                eng = ENGINE_OF.get(c["path"])
                credits[fn] = c["credit"] + ("（%s）" % {"apify": "Google 圖片", "ddg": "DuckDuckGo"}.get(eng, eng) if eng else "")
                made += 1
            else:
                selfrej += 1
    if credits:
        tmpc = credfile + ".part"
        json.dump(credits, open(tmpc, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmpc, credfile)
    shutil.rmtree(work, ignore_errors=True)
    _metrics(a, refs, staged, all_rejects, scores, curated, made, len(winners_all) >= 3, selfrej)
    print("完成：%d 張（策展%s，候選 %d，抓取剔除 %d，自檢剔除 %d）" %
          (made, "✓" if curated else "降級", sum(len(v) for v in staged.values()), len(all_rejects), selfrej))
    sys.exit(0 if made else 1)


def _write_checked(img, fp, work):
    """合成後自檢（黑白/純色）→ 本地寫 → 搬 Drive。"""
    local = os.path.join(work, os.path.basename(fp))
    img.save(local, "PNG", optimize=True)
    ok, why = _valid_img(local, min_dim=500, min_bytes=30000)
    if not ok:
        sys.stderr.write("  ↩ 自檢剔除 %s（%s）\n" % (os.path.basename(fp), why))
        return False
    tmp = fp + ".part"
    shutil.copyfile(local, tmp)
    os.replace(tmp, fp)
    return True


def _log_curation(a, staged, ranking, scores, curated):
    try:
        os.makedirs(DATA, exist_ok=True)
        rec = {"ts": NOW(), "post": a.post_id or os.path.basename(a.outdir), "curated": curated,
               "slides": {str(n): {"candidates": [{"id": c["id"], "type": c["source_type"]} for c in staged[n]],
                                    "ranking": ranking.get(n, []), "scores": scores.get(n, {})} for n in staged}}
        with open(os.path.join(DATA, "curation_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _metrics(a, refs, staged, rejects, scores, curated, made, collage, selfrej=0):
    try:
        os.makedirs(DATA, exist_ok=True)
        mix = {}
        for cds in staged.values():
            for c in cds:
                mix[c["source_type"]] = mix.get(c["source_type"], 0) + 1
        allsc = [v for s in scores.values() for v in s.values() if isinstance(v, (int, float))]
        rec = {"ts": NOW(), "post": a.post_id or os.path.basename(a.outdir), "refs": len(refs),
               "candidates": sum(len(v) for v in staged.values()), "fetch_rejects": len(rejects),
               "self_check_rejects": selfrej, "composed": made, "collage": collage, "curated": curated,
               "source_mix": mix, "curator_avg": round(sum(allsc) / len(allsc), 2) if allsc else None}
        with open(os.path.join(DATA, "quality_metrics.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
