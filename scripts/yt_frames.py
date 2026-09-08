#!/usr/bin/env python3
"""字幕定位截圖 — 依「這一張要講什麼」去影片裡找那一秒，再抽那一格。

為什麼要有這支〔2026-09-08 Jesse：「很多貼文的照片選擇也過於受限」〕：
  現在 forage_shots.grab_youtube() 抽的是 25%／50%／75% 三格，
  完全不看影片在演什麼。一支 20 分鐘的訪談，第 50% 秒可能是主持人喝水。
  三格盲抽＋一張縮圖＝四個候選，其中通常只有縮圖能用。

  實測未發佈的 16 篇：140 張版位裡有 55 張候選數 ≤2，平均每張只有 4.2 個。
  「受限」不是感覺，是這個數字。

  字幕裡有時間戳。既然我們知道這一張要講「朴恩斌選擇留下的那一刻」，
  就該去字幕裡找講這件事的那幾秒，再抽那幾秒的畫面。

拆成五個環節，每一環都能單獨測、單獨換：
  1 取字幕   yt-dlp 下載自動字幕（json3 或 vtt），不下載影片本體
  2 切片     解析成 [(起, 迄, 文字)]
  3 定位     拿「這一張要講什麼」去比對每一段，選出最像的 N 段
  4 抽格     ffmpeg 對直連串流 range-seek，一段抽三格（避開切點與運鏡糊）
  5 篩選     可用性（尺寸／純色）＋銳利度，同一段只留最好的一格

用法：
  python3 scripts/yt_frames.py --url <YouTube網址> --want "要找的畫面內容" \\
      --n 4 --outdir /tmp/out
  python3 scripts/yt_frames.py --url ... --want ... --dry     # 只印定位結果不抽格
  python3 scripts/yt_frames.py --url ... --list-subs          # 看有哪些字幕

輸出：outdir/ 底下的 jpg，加一份 frames.json（時間戳、字幕原文、銳利度、出處）。
"""
import os, re, sys, json, glob, math, argparse, subprocess, tempfile, shutil

from PIL import Image, ImageFilter, ImageStat

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
YTDLP = os.path.join(SCRIPT_DIR, "bin", "yt-dlp")
FFMPEG = "/opt/homebrew/bin/ffmpeg"
# 字幕語言優先序：中文的比對準確度遠高於英文（我們的文案是中文），
# 但很多歐美片源只有英文自動字幕，所以英文一定要留在鏈上。
SUB_LANGS = ["zh-TW", "zh-Hant", "zh", "zh-CN", "en", "en-US"]


# ── 0 找影片 ─────────────────────────────────────────────────────────
def _source_rules():
    """讀 config/video-sources.md 的優先／避開清單。改這份檔就改得動排序，
    不必動程式碼——它在規則本裡是可編輯的一頁。"""
    fp = os.path.join(os.path.dirname(SCRIPT_DIR), "config", "video-sources.md")
    prefer, avoid, ban, sec = [], [], [], None
    try:
        for ln in open(fp, encoding="utf-8"):
            t = ln.strip()
            if t.startswith("## 優先"):
                sec = "p"; continue
            if t.startswith("## 避開"):
                sec = "a"; continue
            if t.startswith("##"):
                sec = None; continue
            if not t or t.startswith("#") or t.startswith("```"):
                continue
            if sec == "p":
                prefer.append(t.lower())
            elif sec == "a":
                if t.endswith("!"):
                    ban.append(t[:-1].strip().lower())
                else:
                    avoid.append(t.lower())
    except Exception:
        pass
    return prefer, avoid, ban


def search_videos(query, n=6, timeout=120):
    """用主題搜 YouTube，回傳候選影片。yt-dlp 自帶 ytsearch，不需要 API key。

    〔2026-09-08〕沒有這一步的話，每支影片的網址都要人先找好貼進視覺企劃，
    素材的天花板就是「有人手動貼了幾條連結」。實測搜「朴恩斌 毛骨悚然的戀愛
    訪談」，前五筆全是相關的韓劇宣傳訪談。

    篩選條件都有理由，不是拍腦袋：
      45 秒以下   多半是 Shorts，畫面快切，抽到糊的機率高
      40 分鐘以上 多半是直播重播或完整節目，字幕定位成本高、雜訊多
      觀看數      不是品質保證，但低觀看的多是重製上傳，畫質通常較差
    """
    try:
        r = subprocess.run(
            [YTDLP, "ytsearch%d:%s" % (n, query), "--no-playlist", "--skip-download",
             "--print", "%(id)s\t%(duration)s\t%(view_count)s\t%(title)s\t%(channel)s"],
            capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return [], "搜尋失敗：%s" % type(e).__name__
    prefer, avoid, ban = _source_rules()
    out = []
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        vid, dur, views, title = parts[0], parts[1], parts[2], parts[3]
        chan = parts[4] if len(parts) > 4 else ""
        try:
            dur = float(dur)
        except Exception:
            continue
        if dur < 45 or dur > 2400:
            continue
        blob = (title + " " + chan).lower()
        if any(b and b in blob for b in ban):
            continue
        # 片源分級〔config/video-sources.md〕：官方頻道的畫面沒有第三方台標
        # 與燒死的字幕；新聞台二次上傳每一格都髒。這一步避開，
        # 比抽完格再逐格挑便宜得多，也可靠得多。
        tier = 0
        if any(a and a in blob for a in avoid):
            tier = 2
        elif any(p and p in blob for p in prefer):
            tier = -1
        out.append({"id": vid, "url": "https://www.youtube.com/watch?v=" + vid,
                    "duration": dur, "views": int(views) if views.isdigit() else 0,
                    "title": title[:90], "channel": chan[:50], "tier": tier})
    out.sort(key=lambda x: (x["tier"], -x["views"]))
    return out, (None if out else "搜不到合用的影片（都太短、太長，或全在禁用清單裡）")


# ── 1 取字幕 ─────────────────────────────────────────────────────────
def fetch_subs(url, work, langs=None, timeout=120):
    """下載自動字幕，回傳 [(檔案路徑, 語言)]。只抓字幕不抓影片。

    全部下載回來，不預設哪一軌比較好〔2026-09-08 第一版就踩到〕：
    原本寫死「zh-TW 優先」，結果拿英文的 want 去比中文字幕，命中零。
    哪一軌好用取決於你要找什麼語言的內容，那是呼叫端才知道的事，
    所以這裡只負責拿，選哪一軌交給 pick_track()。"""
    langs = langs or SUB_LANGS
    cmd = [YTDLP, "--no-playlist", "--skip-download",
           "--write-auto-sub", "--write-sub",
           "--sub-langs", ",".join(langs), "--sub-format", "json3/vtt",
           "-o", os.path.join(work, "%(id)s.%(ext)s"), url]
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception as e:
        return [], "yt-dlp 失敗：%s" % type(e).__name__
    found = []
    for lg in langs:
        for ext in ("json3", "vtt"):
            for h in glob.glob(os.path.join(work, "*.%s.%s" % (lg, ext))):
                found.append((h, lg))
    if not found:
        rest = glob.glob(os.path.join(work, "*.json3")) + glob.glob(os.path.join(work, "*.vtt"))
        found = [(h, "?") for h in rest]
    return found, (None if found else "這支影片沒有字幕")


def pick_track(tracks, want, extra=""):
    """哪一軌字幕跟「要找的內容」比較對得上，就用哪一軌。

    我們的文案是中文，但片源常常是歐美／韓國內容、只有英文自動字幕。
    跨語言時真正撐住比對的是專有名詞（Tom Holland、Park Eun-bin、Rizz），
    它們在中英文字幕裡長得一樣——_tokens() 會把它們抽成拉丁詞。
    所以「選分數最高的那一軌」在跨語言情境下也成立。"""
    best = None
    for fp, lg in tracks:
        try:
            segs = merge_segments(load_segments(fp))
        except Exception:
            continue
        if not segs:
            continue
        top = score_segments(segs, want, extra)[:5]
        s = sum(x[0] for x in top)
        if best is None or s > best[0]:
            best = (s, fp, lg, segs)
    return best


# ── 2 切片 ───────────────────────────────────────────────────────────
def parse_json3(fp):
    d = json.load(open(fp, encoding="utf-8"))
    out = []
    for ev in d.get("events") or []:
        segs = ev.get("segs") or []
        txt = "".join(s.get("utf8", "") for s in segs).strip()
        if not txt or txt == "\n":
            continue
        st = (ev.get("tStartMs") or 0) / 1000.0
        du = (ev.get("dDurationMs") or 0) / 1000.0
        out.append((st, st + du, re.sub(r"\s+", " ", txt)))
    return out


_VTT_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")


def parse_vtt(fp):
    """VTT 解析。YouTube 的自動字幕會逐字滾動、同一句重複出現好幾次，
    所以要把連續重複的內容摺疊掉，否則同一句話會佔掉整份 shortlist。"""
    out, cur = [], None
    for line in open(fp, encoding="utf-8", errors="ignore"):
        m = _VTT_TS.search(line)
        if m:
            g = [int(x) for x in m.groups()]
            st = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
            en = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
            cur = [st, en, []]
            out.append(cur)
        elif cur is not None and line.strip():
            cur[2].append(re.sub(r"<[^>]+>", "", line).strip())
    segs = []
    for st, en, parts in out:
        txt = re.sub(r"\s+", " ", " ".join(parts)).strip()
        if not txt:
            continue
        # 滾動字幕：後一句常常整段包含前一句。包含就換掉，不要各留一份。
        if segs and (txt in segs[-1][2] or segs[-1][2] in txt):
            if len(txt) > len(segs[-1][2]):
                segs[-1] = (segs[-1][0], en, txt)
            continue
        segs.append((st, en, txt))
    return segs


def load_segments(fp):
    return parse_json3(fp) if fp.endswith(".json3") else parse_vtt(fp)


def merge_segments(segs, window=6.0):
    """把碎片合併成約 window 秒的段落。自動字幕常常一句話切成三段兩秒的碎片，
    碎片單獨拿去比對，任何一段都不像完整的意思。"""
    out = []
    for st, en, txt in segs:
        if out and st - out[-1][0] < window and len(out[-1][2]) < 120:
            out[-1] = (out[-1][0], en, (out[-1][2] + " " + txt).strip())
        else:
            out.append((st, en, txt))
    return out


# ── 3 定位 ───────────────────────────────────────────────────────────
_CJK = re.compile(r"[一-鿿]")


def _tokens(s):
    """中英混合的比對單位：中文取 bigram（單字太泛），英文取小寫詞。"""
    s = (s or "").lower()
    lat = set(re.findall(r"[a-z][a-z']{2,}", s))
    cjk = "".join(_CJK.findall(s))
    bi = {cjk[i:i + 2] for i in range(len(cjk) - 1)}
    return lat | bi


def score_segments(segs, want, extra=""):
    """回傳 [(分數, 起, 迄, 文字)]，分數高的在前。

    純詞彙比對，不呼叫模型：這一層的任務是把幾百段縮到十幾段。
    最後選哪一段交給模型或人，那時候成本才划算（見檔尾「還沒做的那一環」）。
    """
    w = _tokens(want) | _tokens(extra)
    if not w:
        return []
    out = []
    for st, en, txt in segs:
        t = _tokens(txt)
        if not t:
            continue
        hit = len(w & t)
        if not hit:
            continue
        # 用 Jaccard 而不是命中數：否則長段落只因為字多就贏
        sc = hit / math.sqrt(len(t))
        out.append((round(sc, 4), st, en, txt))
    out.sort(key=lambda x: -x[0])
    return out


def spread(ranked, n, min_gap=20.0):
    """選 n 段，且彼此至少隔 min_gap 秒。
    否則前五名常常是同一分鐘裡的五段，抽出來是五張幾乎一樣的畫面。"""
    picked = []
    for row in ranked:
        if all(abs(row[1] - p[1]) >= min_gap for p in picked):
            picked.append(row)
        if len(picked) >= n:
            break
    return picked


# ── 4 抽格 ───────────────────────────────────────────────────────────
def stream_url(url, timeout=90):
    """拿直連串流 URL 讓 ffmpeg range-seek，不下載整支影片。
    一支 20 分鐘的 1080p 影片下載要幾百 MB，抽四格只需要幾百 KB。"""
    try:
        r = subprocess.run(
            [YTDLP, "--no-playlist", "--print", "duration", "--print", "urls",
             "--print", "title", "--print", "channel",
             "-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]/b[height<=1080]/b", url],
            capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return None, {}, "yt-dlp 取串流失敗：%s" % type(e).__name__
    lines = [x for x in (r.stdout or "").strip().splitlines() if x.strip()]
    if len(lines) < 2:
        return None, {}, "拿不到串流 URL（可能需要登入或已下架）"
    dur = float(lines[0]) if re.match(r"^[\d.]+$", lines[0]) else 0
    meta = {"duration": dur,
            "title": lines[2] if len(lines) > 2 else "",
            "channel": lines[3] if len(lines) > 3 else ""}
    return lines[1], meta, None


def grab_at(surl, t, out, timeout=60):
    subprocess.run([FFMPEG, "-ss", "%.2f" % max(0.0, t), "-i", surl,
                    "-frames:v", "1", "-q:v", "2", "-y", out],
                   capture_output=True, timeout=timeout)
    return os.path.exists(out) and os.path.getsize(out) > 4000


# ── 5 篩選 ───────────────────────────────────────────────────────────
def sharpness(path):
    """銳利度代理值：邊緣圖的標準差。越高越銳利。
    用 PIL 而不是 OpenCV 的 Laplacian variance——本機那份 anaconda Python 是
    x86_64 的 3.7，numpy 一 import 就 Illegal instruction，整條管線會直接死。
    PIL 的 FIND_EDGES 沒有 Laplacian 準，但足以分出「清楚」與「運鏡糊掉」。"""
    try:
        im = Image.open(path).convert("L")
        im.thumbnail((512, 512))
        return round(ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).stddev[0], 2)
    except Exception:
        return 0.0


def usable(path, min_dim=560):
    """沿用 forage_shots 的那一套判準，門檻對齊：太小、近純色、全黑全白都不要。"""
    try:
        if os.path.getsize(path) < 8000:
            return False, "太小"
        im = Image.open(path).convert("RGB")
        if min(im.size) < min_dim:
            return False, "解析度不足 %dx%d" % im.size
        st = ImageStat.Stat(im.resize((48, 48)))
        if max(st.stddev) < 8:
            return False, "近純色"
        mean = sum(st.mean) / 3
        if mean < 12 or mean > 243:
            return False, "全黑或全白"
        return True, None
    except Exception as e:
        return False, "不可讀 %s" % type(e).__name__


# 一段字幕裡抽哪幾個時間點：不抽開頭（常常是鏡頭切換的那一格），
# 也不抽結尾（下一句已經開始，畫面可能又切走了）。
OFFSETS = (0.6, 1.5, 2.6)


# ── 沒有字幕時的辦法：抓鏡頭切換點 ───────────────────────────────────
def scene_frames(url, outdir, window=180, start=5, thresh=0.35, cap=40):
    """沒有字幕就抓「每一個鏡頭的第一格」。

    〔2026-09-08 實測〕台灣娛樂新聞頻道（三立娛樂星聞等）的影片多數
    沒有自動字幕——而那正是我們做韓劇、藝人題材最常用的片源。
    字幕定位對它們完全無效，總不能因此退回盲抽三格。

    ffmpeg 的 scene 偵測會在畫面變化超過門檻時輸出一格，也就是每個鏡頭
    的開頭。實測 150 秒的訪談片段抽到 73 個鏡頭，對比盲抽的 3 格。
    而且每一格都是鏡頭剛切完的穩定畫面，不是運鏡途中的糊格。

    這條路不需要字幕，但也不知道畫面在演什麼——它換來的是「選擇變多」，
    不是「選得更準」。準不準交給後面的策展（WF14）與你。

    ⚠ 已知限制，不要當成沒有：新聞台的二次上傳會把中韓文字幕與自家台標
    燒進畫面（實測 fU6-L0vWsds 每一格都有）。那種圖鋪滿等於把別台的浮水印
    印出去，我們自己的視覺閘門正是為此設了 watermark／credit_leak 兩條 block。
    這是「片源」的問題，不是「哪一格」的問題——同一支影片的每一格都髒。
    所以擋它的正確位置是選片（見 config/video-sources.md），不是逐格偵測。
    我試過用「下方橫帶的邊緣密度」判斷有沒有燒字幕，實測不可用：
    它量的是「下方比中段忙」，分不出「有字」與「背景本來就複雜」，
    在忙碌背景上的字幕會漏判。寧可不放，也不要放一個查不出錯的偵測器。
    """
    surl, meta, err = stream_url(url)
    if err:
        return [], meta, err
    os.makedirs(outdir, exist_ok=True)
    pat = os.path.join(outdir, "scene-%03d.jpg")
    try:
        subprocess.run(
            [FFMPEG, "-ss", str(start), "-t", str(window), "-i", surl,
             "-vf", "select='gt(scene,%s)',scale=1280:-1" % thresh,
             "-vsync", "vfr", "-q:v", "3", "-y", pat, "-loglevel", "error"],
            capture_output=True, timeout=window * 3 + 120)
    except Exception as e:
        return [], meta, "抽鏡頭失敗：%s" % type(e).__name__
    out = []
    for fp in sorted(glob.glob(os.path.join(outdir, "scene-*.jpg")))[:cap]:
        ok, why = usable(fp, min_dim=480)
        if not ok:
            os.remove(fp); continue
        out.append({"file": os.path.basename(fp), "sharpness": sharpness(fp)})
    out.sort(key=lambda x: -x["sharpness"])
    return out, meta, (None if out else "抽到的鏡頭都不合格")


def harvest(url, want, n=4, outdir=".", extra="", dry=False, keep_all=False):
    work = tempfile.mkdtemp(prefix="ytf-")
    report = {"url": url, "want": want, "stages": {}, "frames": []}
    try:
        tracks, err = fetch_subs(url, work)
        if err:
            report["error"] = err
            return report
        chosen = pick_track(tracks, want, extra)
        if not chosen:
            report["error"] = "有字幕但解析後是空的（%d 軌）" % len(tracks)
            return report
        _s, sub, lang, segs = chosen
        report["stages"]["subtitle"] = {
            "lang": lang, "file": os.path.basename(sub),
            "tracks_tried": [l for _f, l in tracks], "match_strength": round(_s, 3)}
        report["stages"]["segments"] = len(segs)

        ranked = score_segments(segs, want, extra)
        picked = spread(ranked, n)
        report["stages"]["matched"] = [
            {"score": s, "at": round(st, 1), "text": tx[:110]} for s, st, en, tx in picked]
        if not picked:
            report["error"] = "字幕裡找不到跟「%s」相關的段落" % want
            return report
        if dry:
            return report

        surl, meta, err = stream_url(url)
        if err:
            report["error"] = err
            return report
        report["stages"]["video"] = meta

        os.makedirs(outdir, exist_ok=True)
        for i, (sc, st, en, tx) in enumerate(picked):
            best = None
            for j, off in enumerate(OFFSETS):
                t = st + off
                if t >= en + 1.5 or (meta.get("duration") and t > meta["duration"] - 1):
                    continue
                fp = os.path.join(work, "f%d-%d.jpg" % (i, j))
                if not grab_at(surl, t, fp):
                    continue
                ok, why = usable(fp)
                if not ok:
                    continue
                sh = sharpness(fp)
                if best is None or sh > best[0]:
                    best = (sh, fp, t)
            if not best:
                report["frames"].append({"at": round(st, 1), "skipped": "這一段抽不到可用的畫面"})
                continue
            sh, fp, t = best
            dst = os.path.join(outdir, "yt-%02d-%.0fs.jpg" % (i, t))
            shutil.copy2(fp, dst)
            im = Image.open(dst)
            report["frames"].append({
                "file": os.path.basename(dst), "at": round(t, 1),
                "score": sc, "sharpness": sh, "size": "%dx%d" % im.size,
                "quote": tx[:160],
                "credit": "%s／%s（%s）" % (meta.get("title", "")[:60],
                                           meta.get("channel", ""), _hhmmss(t)),
                "source_url": "%s&t=%ds" % (url, int(t)) if "watch?v=" in url else url,
            })
        return report
    finally:
        if not keep_all:
            shutil.rmtree(work, ignore_errors=True)


def _hhmmss(t):
    t = int(t)
    return "%d:%02d:%02d" % (t // 3600, (t % 3600) // 60, t % 60) if t >= 3600 \
        else "%d:%02d" % (t // 60, t % 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--search", default="", help="用主題搜影片，取代手動給 --url")
    ap.add_argument("--try-videos", type=int, default=3,
                    help="--search 時最多試幾支（前一支沒字幕或定位失敗就換下一支）")
    ap.add_argument("--want", default="", help="這一張要找的畫面內容")
    ap.add_argument("--extra", default="", help="補充關鍵字（人名、片名）")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--dry", action="store_true", help="只做定位不抽格")
    ap.add_argument("--list-subs", action="store_true")
    ap.add_argument("--scene", action="store_true",
                    help="不靠字幕，直接抽每個鏡頭的第一格（片源沒字幕時用）")
    ap.add_argument("--window", type=int, default=180, help="--scene 掃描前幾秒")
    a = ap.parse_args()

    if a.list_subs:
        subprocess.run([YTDLP, "--list-subs", "--no-playlist", a.url])
        return 0
    if not a.want:
        sys.stderr.write("要給 --want：不知道要找什麼就只能盲抽，那正是現在的問題\n")
        return 2
    if not a.url and not a.search:
        sys.stderr.write("要給 --url 或 --search 其中一個\n")
        return 2

    if a.scene:
        if not a.url:
            sys.stderr.write("--scene 要給 --url\n")
            return 2
        frames, meta, err = scene_frames(a.url, a.outdir, window=a.window)
        print(json.dumps({"url": a.url, "mode": "scene", "video": meta,
                          "frames": frames, "error": err}, ensure_ascii=False, indent=1))
        return 1 if err else 0

    if a.url:
        r = harvest(a.url, a.want, a.n, a.outdir, a.extra, a.dry)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if r.get("error") else 0

    vids, err = search_videos(a.search)
    if err:
        print(json.dumps({"search": a.search, "error": err}, ensure_ascii=False, indent=1))
        return 1
    # 一支一支試：沒字幕、字幕對不上都算失敗，換下一支。
    # 只試一支的話，命中率會被「這支剛好沒字幕」綁架。
    tried = []
    for v in vids[:max(1, a.try_videos)]:
        r = harvest(v["url"], a.want, a.n, a.outdir, a.extra, a.dry)
        r["video_pick"] = v
        tried.append({"url": v["url"], "title": v["title"],
                      "views": v["views"], "error": r.get("error")})
        if not r.get("error") and (a.dry or r.get("frames")):
            r["tried"] = tried
            r["searched"] = [{"title": x["title"], "views": x["views"]} for x in vids[:6]]
            print(json.dumps(r, ensure_ascii=False, indent=1))
            return 0
    print(json.dumps({"search": a.search, "want": a.want,
                      "error": "試了 %d 支都沒成功" % len(tried), "tried": tried},
                     ensure_ascii=False, indent=1))
    return 1


if __name__ == "__main__":
    sys.exit(main())

# ── 還沒做的那一環（刻意留白，不要假裝已經解決）──────────────────────
# 定位目前是純詞彙比對。它解決的是「別再盲抽」，不是「看懂畫面」。
# 兩個已知的失效情境：
#   1 字幕在講 A，畫面在演 B（旁白式影片、B-roll）——詞彙比對會選錯
#   2 文案用的詞跟字幕用的詞不同義（「留下來」vs「沒有離開」）——會漏
# 正解是在 spread() 之後、抽格之前插一層模型：把 top 12 段的文字連同
# 「這一張要講什麼」交給 Claude，讓它挑 4 段並說明理由。成本很低
#   （12 段字幕約 600 token），因為詞彙層已經把幾百段縮到十幾段。
# 更完整的做法是抽完格再用 vision 複審一次「這張畫面真的在演這件事嗎」，
# 那一層跟現有的 WF14 策展是同一件事，應該併進去而不是另開一條。
