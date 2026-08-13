#!/usr/bin/env python3
"""訊號蒐集器：把選題來源從 n8n 搬到本機。

為什麼在本機而不在 n8n：
  來源清單是**易變**的（今天加 14 個國外媒體，明天可能再加），
  n8n 的 workflow 每改一次都要重新發布且連線不穩。
  改成本機抓 → 產出 data/signals/latest.json → push，
  n8n WF05 只要讀這一個檔就好，加來源不用動 n8n。

分層（依訊號性質，不是依地理）：
  tw_local     台灣在地討論與新聞：PTT／中央社／自由／聯合／ETtoday／女人迷／Google News/Trends
  competitor   競品與對標：App Store 評論（競品痛點是最好的貼文角度）
  global_pop   歐美流行文化媒體：GQ／Vogue／Dazed／i-D／Highsnobiety／Hypebeast／The Cut 等
  global_forum 歐美討論區：Reddit
  research     學術與預印本：PsyArXiv／OpenAlex

用法：
  python3 scripts/collect_signals.py              # 抓全部，寫 data/signals/latest.json
  python3 scripts/collect_signals.py --tier tw_local
  python3 scripts/collect_signals.py --health     # 只檢查來源健康度，不寫檔
"""
import os, sys, json, re, time, argparse, datetime
import urllib.request, urllib.error
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT_DIR = os.path.join(REPO, "data", "signals")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0 Safari/537.36")

# 相關性關鍵字：歐美流行文化媒體多數內容與約會無關（時尚單品、名人動態），
# 不過濾的話 digest 會被雜訊淹沒。中英各一組，命中任一即收。
# 相關性判準分兩級（實測：單一寬鬆清單會把 Timex 手錶、哥本哈根時裝週判成相關，
# 因為 "love"／"ex " 這類通用詞在時尚報導裡到處都是）。
#   STRONG 命中標題或摘要即收
#   WEAK   只有在**標題**命中才收，出現在內文不算
KW_STRONG_EN = ("dating", "relationship", "romance", "romantic", "situationship",
                "breakup", "break up", "divorce", "hookup", "monogamy", "polyamor",
                "heartbreak", "intimacy", "loneliness", "matchmaking", "swipe right",
                "tinder", "hinge app", "bumble", "dating app", "love language",
                "attachment style", "red flag", "green flag", "ghosting", "situationships")
KW_WEAK_EN = ("love", "single", "singles", "marriage", "married", "couple", "partner",
              "crush", "flirt", "attraction", "chemistry", "commitment", "boyfriend",
              "girlfriend", "husband", "wife", "desire", "lonely", "friendship", "wedding")
KW_STRONG_TW = ("約會", "交友", "戀愛", "曖昧", "分手", "告白", "脫單", "聯誼", "相親",
                "劈腿", "渣男", "渣女", "已讀不回", "戀愛腦", "配對", "擇偶", "遠距離",
                "情侶", "另一半", "男友", "女友", "交往", "失戀", "追求者", "感情")
KW_WEAK_TW = ("單身", "婚", "心動", "喜歡的人", "調情", "孤獨", "寂寞", "親密", "吸引",
              "戀人", "離婚", "告白", "分居", "曖昧期")


# 人物／書籍／概念層專用判準：這一層要的是「心靈、做事風格、魅力」，
# 用約會關鍵字去濾會把 Aeon、Farnam Street 的好文章全部濾掉。
KW_MIND = ("habit", "discipline", "ambition", "mindset", "identity", "self", "ego",
           "confidence", "charisma", "authentic", "vulnerab", "shame", "regret",
           "meaning", "purpose", "motivation", "willpower", "attention", "focus",
           "decision", "judgment", "bias", "success", "failure", "resilience",
           "creativity", "craft", "mastery", "practice", "ritual", "solitude",
           "friendship", "trust", "status", "envy", "comparison", "belonging",
           "psychology", "philosoph", "emotion", "empathy", "boundaries",
           "manifest", "luck", "serendipity", "obsession", "perfectionism")


def _relevant_mind(title, desc=""):
    blob = (title + " " + desc).lower()
    return "strong" if any(k in blob for k in KW_MIND) else None


def _relevant(title, desc="", nofilter=False, tier=None):
    """回傳 None（不收）或 'strong'／'weak'／'raw'。
    過濾不可能完美（時裝週報導也會命中 wedding），所以不追求零雜訊，
    改成把相關度標進資料裡，讓下游選題引擎自己權衡。"""
    if nofilter:
        return "raw"
    if tier == "mind":
        return _relevant_mind(title, desc)
    t_low, all_low = title.lower(), (title + " " + desc).lower()
    if any(k in all_low for k in KW_STRONG_EN) or any(k in (title + " " + desc) for k in KW_STRONG_TW):
        return "strong"
    if any(k in t_low for k in KW_WEAK_EN) or any(k in title for k in KW_WEAK_TW):
        return "weak"
    return None


SOURCES = [
    # ── 台灣在地 ────────────────────────────────────────────────────
    dict(id="ptt_boygirl", name="PTT Boy-Girl", tier="tw_local", kind="ptt",
         url="https://www.ptt.cc/bbs/Boy-Girl/index.html"),
    dict(id="ptt_women", name="PTT WomenTalk", tier="tw_local", kind="ptt",
         url="https://www.ptt.cc/bbs/WomenTalk/index.html"),
    dict(id="ptt_marriage", name="PTT marriage", tier="tw_local", kind="ptt",
         url="https://www.ptt.cc/bbs/marriage/index.html"),
    dict(id="gtrends_tw", name="Google Trends TW", tier="tw_local", kind="rss",
         url="https://trends.google.com/trending/rss?geo=TW", nofilter=True),
    dict(id="cna_life", name="中央社 生活", tier="tw_local", kind="rss",
         url="https://feeds.feedburner.com/rsscna/lifehealth"),
    dict(id="cna_social", name="中央社 社會", tier="tw_local", kind="rss",
         url="https://feeds.feedburner.com/rsscna/social"),
    dict(id="ltn", name="自由時報", tier="tw_local", kind="rss",
         url="https://news.ltn.com.tw/rss/all.xml"),
    dict(id="ettoday", name="ETtoday", tier="tw_local", kind="rss",
         url="https://feeds.feedburner.com/ettoday/realtime"),
    dict(id="womany", name="女人迷", tier="tw_local", kind="rss",
         url="https://womany.net/read/feed", nofilter=True),
    dict(id="gnews_dating", name="Google News 交友軟體", tier="tw_local", kind="rss", nofilter=True,
         url="https://news.google.com/rss/search?q=%E4%BA%A4%E5%8F%8B%E8%BB%9F%E9%AB%94&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"),
    dict(id="gnews_dcard", name="Google News Dcard熱帖", tier="tw_local", kind="rss", nofilter=True,
         url="https://news.google.com/rss/search?q=dcard+%E6%84%9F%E6%83%85&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"),

    # ── 競品痛點（App Store 評論）────────────────────────────────────
    # 2026-08-12 實測：Tinder(547702041) 與 Bumble(930441707) 的 customerreviews JSON
    # 皆回 200 但 feed 內無 entry 欄位（Apple 端已不回評論）。停用待查替代路徑。
    dict(id="ios_tinder", name="Tinder 台灣評論", tier="competitor", kind="itunes", enabled=False,
         url="https://itunes.apple.com/tw/rss/customerreviews/page=1/id=547702041/sortby=mostrecent/json"),
    dict(id="ios_bumble", name="Bumble 台灣評論", tier="competitor", kind="itunes", enabled=False,
         url="https://itunes.apple.com/tw/rss/customerreviews/page=1/id=930441707/sortby=mostrecent/json"),

    # ── 歐美流行文化媒體（Jesse 2026-08-12 指定加入）──────────────────
    dict(id="gq", name="GQ", tier="global_pop", kind="rss",
         url="https://www.gq.com/feed/rss"),
    dict(id="vogue", name="Vogue", tier="global_pop", kind="rss",
         url="https://www.vogue.com/feed/rss"),
    dict(id="thecut", name="The Cut / NY Mag", tier="global_pop", kind="rss",
         url="https://feeds.feedburner.com/nymag/fashion"),
    dict(id="dazed", name="Dazed", tier="global_pop", kind="rss",
         url="https://www.dazeddigital.com/rss"),
    dict(id="i_d", name="i-D", tier="global_pop", kind="rss",
         url="https://i-d.co/feed"),
    dict(id="highsnobiety", name="Highsnobiety", tier="global_pop", kind="rss",
         url="https://www.highsnobiety.com/feed"),
    dict(id="hypebeast", name="Hypebeast", tier="global_pop", kind="rss",
         url="https://hypebeast.com/feed"),
    dict(id="refinery29", name="Refinery29", tier="global_pop", kind="rss",
         url="https://www.refinery29.com/en-us/rss.xml"),
    dict(id="papermag", name="PAPER", tier="global_pop", kind="rss",
         url="https://www.papermag.com/feeds/feed.rss"),
    dict(id="interview", name="Interview Magazine", tier="global_pop", kind="rss",
         url="https://www.interviewmagazine.com/feed"),
    dict(id="cosmo", name="Cosmopolitan", tier="global_pop", kind="rss",
         url="https://www.cosmopolitan.com/rss/all.xml/"),
    dict(id="elle", name="ELLE", tier="global_pop", kind="rss",
         url="https://www.elle.com/rss/all.xml/"),
    dict(id="psyche", name="Psyche", tier="global_pop", kind="rss",
         url="https://psyche.co/feed.rss"),

    # ── 歐美討論區 ──────────────────────────────────────────────────
    # .json 從本機 IP 一律 403（n8n 雲端 IP 可以）；.rss 實測 200，故走 RSS
    dict(id="r_dating_advice", name="r/dating_advice", tier="global_forum", kind="rss",
         url="https://www.reddit.com/r/dating_advice/hot/.rss", nofilter=True),
    dict(id="r_relationships", name="r/relationships", tier="global_forum", kind="rss",
         url="https://www.reddit.com/r/relationships/hot/.rss", nofilter=True),
    dict(id="r_tinder", name="r/Tinder", tier="global_forum", kind="rss",
         url="https://www.reddit.com/r/Tinder/hot/.rss", nofilter=True),
    dict(id="r_over30", name="r/datingoverthirty", tier="global_forum", kind="rss",
         url="https://www.reddit.com/r/datingoverthirty/hot/.rss", nofilter=True),

    # ── 人物／書籍／概念（Jesse 2026-08-12 指定）─────────────────────
    # 用途：人物誌、書摘、概念拆解三類選題。對標 @heavenravenofficial 的
    # Tom Holland 顯化篇（27.7k 讚）：人物成就 + 概念翻轉 + 合作者證言鏈。
    dict(id="aeon", name="Aeon 長文", tier="mind", kind="rss",
         url="https://aeon.co/feed.rss"),
    dict(id="fs_blog", name="Farnam Street", tier="mind", kind="rss",
         url="https://fs.blog/feed/", nofilter=True),
    dict(id="bigthink", name="Big Think", tier="mind", kind="rss",
         url="https://bigthink.com/feed/"),
    dict(id="marginalian", name="The Marginalian", tier="mind", kind="rss",
         url="https://www.themarginalian.org/feed/"),
    dict(id="nextbigidea", name="Next Big Idea 書摘", tier="mind", kind="rss",
         url="https://nextbigideaclub.com/magazine/feed/", nofilter=True),
    dict(id="lithub", name="Literary Hub", tier="mind", kind="rss",
         url="https://lithub.com/feed/"),
    dict(id="ted", name="TED Talks", tier="mind", kind="rss",
         url="https://feeds.feedburner.com/TEDTalks_video"),

    # ── 學術（新研究比媒體早 6-12 個月）──────────────────────────────
    dict(id="psyarxiv", name="PsyArXiv 預印本", tier="research", kind="osf",
         url="https://api.osf.io/v2/preprints/?filter[provider]=psyarxiv&sort=-date_published&page[size]=30"),
]


_DOMAIN_LAST = {}
_DOMAIN_LOCK = __import__("threading").Lock()
# 同網域最小間隔：Reddit 對同 IP 併發很敏感（4 個 sub 併發抓 → 429）
_MIN_GAP = {"reddit.com": 8.0, "ptt.cc": 1.0, "feedburner.com": 0.5}


def _throttle(url):
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    key = ".".join(host.split(".")[-2:])
    gap = _MIN_GAP.get(key, 0)
    if not gap:
        return
    with _DOMAIN_LOCK:
        wait = gap - (time.time() - _DOMAIN_LAST.get(key, 0))
        if wait > 0:
            time.sleep(wait)
        _DOMAIN_LAST[key] = time.time()


def _fetch(url, timeout=25, retries=2):
    """逾時放寬並重試：Hypebeast 首抓常逾時、女人迷偶發連線重置、Reddit 併發會 429。"""
    last = None
    for i in range(retries + 1):
        try:
            _throttle(url)
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*",
                                                       "Cookie": "over18=1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            if i < retries:
                time.sleep(2.0 * (i + 1))   # 429 需要退避，線性加長
    raise last


def _clean(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return unescape(s).strip()


def parse_rss(body, src):
    items = []
    blocks = re.findall(r"<(?:item|entry)[\s>].*?</(?:item|entry)>", body, re.S) or \
             re.findall(r"<(?:item|entry)>.*?</(?:item|entry)>", body, re.S)
    for b in blocks:
        mt = re.search(r"<title[^>]*>(.*?)</title>", b, re.S)
        ml = re.search(r"<link[^>]*>(.*?)</link>", b, re.S) or re.search(r'<link[^>]*href="([^"]+)"', b)
        md = re.search(r"<(?:description|summary|content:encoded)[^>]*>(.*?)</(?:description|summary|content:encoded)>", b, re.S)
        title = _clean(mt.group(1)) if mt else ""
        if not title:
            continue
        desc = _clean(md.group(1))[:280] if md else ""
        rel = _relevant(title, desc, src.get("nofilter"), src.get("tier"))
        if not rel:
            continue
        items.append({"title": title, "url": _clean(ml.group(1)) if ml else "",
                      "note": desc[:160], "rel": rel})
    return items


def parse_ptt(body, src):
    out = []
    for m in re.finditer(r'<div class="nrec">(?:<span[^>]*>)?([^<]*)(?:</span>)?</div>'
                         r'[\s\S]*?<a href="(/bbs/[^"]+)">([^<]+)</a>', body):
        push, href, title = m.group(1).strip(), m.group(2), _clean(m.group(3))
        if title.startswith("[公告]") or "板規" in title:
            continue
        out.append({"title": title, "url": "https://www.ptt.cc" + href,
                    "metric": "推 %s" % (push or "0")})
    return out


def parse_reddit(body, src):
    d = json.loads(body)
    out = []
    for c in (d.get("data") or {}).get("children") or []:
        j = c.get("data") or {}
        out.append({"title": j.get("title", ""), "url": "https://reddit.com" + j.get("permalink", ""),
                    "metric": "%s ups / %s 留言" % (j.get("ups"), j.get("num_comments"))})
    return out


def parse_itunes(body, src):
    d = json.loads(body)
    entries = ((d.get("feed") or {}).get("entry")) or []
    out = []
    for e in entries[1:] if isinstance(entries, list) else []:
        title = ((e.get("title") or {}).get("label") or "")
        content = ((e.get("content") or {}).get("label") or "")
        rating = ((e.get("im:rating") or {}).get("label") or "")
        if not title:
            continue
        out.append({"title": title, "url": "", "metric": "%s★" % rating,
                    "note": content[:200]})
    return out


def parse_osf(body, src):
    d = json.loads(body)
    out = []
    for x in d.get("data", []):
        a = x.get("attributes") or {}
        t = a.get("title") or ""
        rel = _relevant(t, a.get("description") or "", False)
        if not rel:
            continue
        out.append({"title": t, "rel": rel, "url": (x.get("links") or {}).get("html") or "",
                    "note": (a.get("description") or "")[:200],
                    "metric": (a.get("date_published") or "")[:10]})
    return out


PARSERS = {"rss": parse_rss, "ptt": parse_ptt, "reddit": parse_reddit,
           "itunes": parse_itunes, "osf": parse_osf}


def collect_one(src, limit=12):
    t0 = time.time()
    rec = {"id": src["id"], "name": src["name"], "tier": src["tier"], "url": src["url"]}
    try:
        body = _fetch(src["url"])
        items = PARSERS[src["kind"]](body, src)[:limit]
        rec.update(ok=True, count=len(items), items=items, ms=int((time.time() - t0) * 1000))
    except urllib.error.HTTPError as e:
        rec.update(ok=False, count=0, items=[], error="HTTP %s" % e.code)
    except Exception as e:
        rec.update(ok=False, count=0, items=[], error="%s: %s" % (type(e).__name__, str(e)[:80]))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default=None, help="只抓某一層")
    ap.add_argument("--health", action="store_true", help="只檢查健康度不寫檔")
    ap.add_argument("--limit", type=int, default=12, help="每源最多幾則")
    a = ap.parse_args()

    srcs = [s for s in SOURCES if s.get("enabled", True) and (not a.tier or s["tier"] == a.tier)]
    # Reddit 對本機 IP 限速極嚴（4 個 sub 併發或間隔 8 秒都只有一半成功）。
    # 改日期輪替：每天只抓一個 sub，四天涵蓋全部。hot 榜變化不快，這個延遲可接受。
    rd = [x for x in srcs if x["id"].startswith("r_")]
    if len(rd) > 1:
        pick = rd[datetime.date.today().toordinal() % len(rd)]
        srcs = [x for x in srcs if not x["id"].startswith("r_") or x["id"] == pick["id"]]
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(collect_one, s, a.limit): s for s in srcs}
        for f in as_completed(futs):
            results.append(f.result())
    results.sort(key=lambda r: (r["tier"], r["id"]))

    ok = [r for r in results if r["ok"]]
    total = sum(r["count"] for r in ok)
    rels = {}
    for r in ok:
        for it in r["items"]:
            k = it.get("rel", "raw")
            rels[k] = rels.get(k, 0) + 1
    print("來源 %d 個，成功 %d，訊號 %d 則（%s）"
          % (len(results), len(ok), total,
             "、".join("%s %d" % (k, v) for k, v in sorted(rels.items(), reverse=True))))
    cur = None
    for r in results:
        if r["tier"] != cur:
            cur = r["tier"]; print("\n[%s]" % cur)
        mark = "✓" if r["ok"] else "✗"
        print("  %s %-22s %3d 則  %s" % (mark, r["name"][:22], r["count"], r.get("error", "")))

    if a.health:
        return 0 if len(ok) == len(results) else 1

    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.datetime.now().astimezone()
    payload = {"generated_at": now.isoformat(timespec="seconds"),
               "source_count": len(results), "ok_count": len(ok), "signal_count": total,
               "sources": results}
    for p in (os.path.join(OUT_DIR, "latest.json"),
              os.path.join(OUT_DIR, now.strftime("%Y-%m-%d") + ".json")):
        tmp = p + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    print("\n✓ 已寫入 data/signals/latest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
