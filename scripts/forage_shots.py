#!/usr/bin/env python3
# forage_shots.py — 截圖策展 forager（素材線 v2，2026-07-29 Jesse 拍板）。
#
# 「講誰就截誰」：每張 slide 的 visual_refs（URL＋frame_hint）→ 實際去源頭抓畫面：
#   youtube  → i.ytimg.com maxresdefault 縮圖直抓（免瀏覽器）
#   twitter  → platform.twitter.com 官方 embed 頁 headless 截圖
#   instagram→ /embed/captioned 頁 headless 截圖
#   book     → Open Library / Google Books 封面直抓
#   其他 URL → Chrome headless 整頁截圖（文章/官網/研究頁）
# 合成 1950×2438（引擎原生尺寸，零引擎改動）：主體置頂部 62%（引擎遮罩壓暗底部），
# 長寬差過大用模糊延伸底。輸出 slideN-SHOT-<slug>.png ＋ shots_credits.json（feed 讀出處）。
# 版權立場：引用式使用＋出處標注（社群慣行標準；owner 2026-07-29 編輯決策，見 HANDOFF §11）。
# 一律本地先寫再搬 Drive（Drive 直寫會 timeout/截斷——2026-07-29 教訓）。
#
# 用法：
#   python3 forage_shots.py --refs refs.json --outdir <Drive底圖資料夾>
#   python3 forage_shots.py --draft <文案.json> --outdir <dir>   # 讀 slides[].visual_refs
#   refs.json: [{"slide":2,"url":"https://youtu.be/..","frame_hint":"...","credit":"Aziz Ansari／Netflix"}]
import os, sys, json, re, argparse, subprocess, tempfile, shutil, hashlib
from urllib.request import Request, urlopen

from PIL import Image, ImageFilter

W, H = 1950, 2438
BROWSE = os.path.expanduser("~/.claude/skills/gstack/browse/dist/browse")   # gstack browse daemon（raw Chrome headless 在本機會與運行中的 Chrome 衝突卡死，勿用）
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0 Safari/537.36"


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


def grab(url, workdir):
    """URL → 本地原始截圖/圖檔路徑。回傳 (path, kind) 或 (None, 原因)。"""
    yid = _yt_id(url)
    if yid:
        for name in ("maxresdefault", "hq720", "hqdefault"):
            try:
                data = _fetch("https://i.ytimg.com/vi/%s/%s.jpg" % (yid, name))
                if len(data) > 5000:   # 404 佔位圖很小
                    p = os.path.join(workdir, "yt-%s.jpg" % yid)
                    open(p, "wb").write(data)
                    return p, "youtube"
            except Exception:
                continue
        return None, "yt 縮圖不可得"
    if url.startswith("http") and re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I):
        try:
            data = _fetch(url)
            p = os.path.join(workdir, "img-" + hashlib.md5(url.encode()).hexdigest()[:8] + ".img")
            open(p, "wb").write(data)
            return p, "image"
        except Exception as e:
            return None, "直抓失敗:%s" % e
    # 需要瀏覽器的來源 → gstack browse daemon；官方 embed 頁優先（乾淨、無登入牆）
    tid = _tw_id(url)
    igc = _ig_code(url)
    if tid:
        target = "https://platform.twitter.com/embed/Tweet.html?id=%s&theme=light&width=1000" % tid
        size, kind = "1050x1400", "twitter"
    elif igc:
        target = "https://www.instagram.com/p/%s/embed/captioned/" % igc
        size, kind = "900x1600", "instagram"
    else:
        target, size, kind = url, "1440x1900", "web"
    out = os.path.join(workdir, "shot-" + hashlib.md5(url.encode()).hexdigest()[:8] + ".png")

    def _b(*args, timeout=60):
        return subprocess.run([BROWSE] + list(args), capture_output=True, text=True, timeout=timeout)

    try:
        _b("viewport", size, "--scale", "2", timeout=90)
        nav = _b("goto", target, timeout=90)
        if "Navigated" not in (nav.stdout or "") + (nav.stderr or ""):
            return None, "goto 失敗:%s" % (nav.stdout or nav.stderr or "")[:60]
        if kind == "web":
            _b("cleanup", "--all", timeout=30)   # 清 cookie 橫幅/廣告/黏頭
            _b("screenshot", "--viewport", out, timeout=60)   # 只截首屏（標題+主圖）＝人類截文章的方式
        else:
            _b("screenshot", out, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "browse daemon timeout"
    if os.path.exists(out) and os.path.getsize(out) > 20000:
        return out, kind
    return None, "截圖失敗/空白"


def _autocrop(im, kind):
    """裁掉 embed 頁四周留白（推文/IG embed 卡片外圍是純白）。"""
    if kind not in ("twitter", "instagram", "web"):
        return im
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


def compose(src_path, kind):
    """原始截圖 → 1950×2438。近比例直接 cover；比例差大＝模糊延伸底＋主體置頂部（引擎遮罩壓暗底部）。"""
    im = Image.open(src_path).convert("RGB")
    im = _autocrop(im, kind)
    ar = im.width / im.height
    if ar <= 1.05:   # 近 4:5 或更長（文章/embed 卡）→ 滿版、鎖頂部裁切（標題主圖在上方）
        scale = max(W / im.width, H / im.height)
        im2 = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        x = (im2.width - W) // 2
        return im2.crop((x, 0, x + W, H))
    # 寬圖（yt 16:9）/超長圖 → 模糊放大當底，主體 contain 置上方
    bg = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(60))
    bg = Image.eval(bg, lambda v: int(v * 0.55))   # 壓暗防搶戲
    fw = int(W * 0.94)
    fh = round(fw / ar)
    if fh > int(H * 0.66):
        fh = int(H * 0.66)
        fw = round(fh * ar)
    fg = im.resize((fw, fh), Image.LANCZOS)
    y = int(H * 0.30) - fh // 2
    y = max(int(H * 0.045), y)
    bg.paste(fg, ((W - fw) // 2, y))
    return bg


def _slug(url, kind):
    yid = _yt_id(url)
    if yid:
        return "yt" + yid[:8]
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0]).split(".")[0]
    return (kind[:2] + host)[:14]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", help="refs.json：[{slide,url,frame_hint,credit}]")
    ap.add_argument("--draft", help="文案 JSON（讀 slides[].visual_refs）")
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    refs = []
    if a.refs:
        refs = json.load(open(a.refs, encoding="utf-8"))
    elif a.draft:
        d = json.load(open(a.draft, encoding="utf-8"))
        for s in d.get("slides", []):
            for vr in (s.get("visual_refs") or []):
                refs.append({"slide": s.get("index"), "url": vr.get("url"),
                             "frame_hint": vr.get("frame_hint", ""), "credit": vr.get("credit", "")})
    if not refs:
        sys.exit("✗ 無 refs（--refs 或 --draft 的 visual_refs 皆空）")
    os.makedirs(a.outdir, exist_ok=True)
    credfile = os.path.join(a.outdir, "shots_credits.json")
    credits = {}
    if os.path.exists(credfile):
        try:
            credits = json.load(open(credfile, encoding="utf-8"))
        except Exception:
            credits = {}
    work = tempfile.mkdtemp(prefix="forage-", dir="/private/tmp")   # browse daemon 只允許寫 /private/tmp 或 repo 內
    made, failed = 0, []
    for r in refs:
        url = (r.get("url") or "").strip()
        n = r.get("slide") or 1
        if not url:
            continue
        raw, kind = grab(url, work)
        if not raw:
            failed.append((n, url, kind)); continue
        fn = "slide%d-SHOT-%s.png" % (n, _slug(url, kind))
        fp = os.path.join(a.outdir, fn)
        if os.path.exists(fp):
            continue   # 冪等
        local = os.path.join(work, fn)
        compose(raw, kind).save(local, "PNG", optimize=True)
        tmp = fp + ".part"
        shutil.copyfile(local, tmp)
        os.replace(tmp, fp)
        credits[fn] = r.get("credit") or url
        made += 1
        print("✓ slide%d %s ← %s" % (n, fn, url[:70]))
    if credits:
        tmpc = credfile + ".part"
        json.dump(credits, open(tmpc, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmpc, credfile)
    shutil.rmtree(work, ignore_errors=True)
    print("完成：%d 張截圖 → %s" % (made, a.outdir))
    for n, url, why in failed:
        print("  ✗ slide%d %s（%s）" % (n, url[:60], why))
    sys.exit(1 if (failed and not made) else 0)


if __name__ == "__main__":
    main()
