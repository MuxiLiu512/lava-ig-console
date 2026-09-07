#!/usr/bin/env python3
"""事實查核閘門 — 把「涉及事實的內容必須再三確認」變成機器擋得住的東西。

為什麼需要這支：
  2026-08-23 的 Jason Arday 靈感卡是活教材。它宣稱「今天台灣熱搜」，但實查當日熱搜
  榜上沒有他；卡片建立於 8 天前，熱度早就過了。它還宣稱「26 歲才學會閱讀」，
  英國媒體的說法是十八歲。整張卡唯一的熱度證明連結是 trends 首頁——那個頁面每天
  變，任何人點進去都驗證不了原本的宣稱。Jesse 因此要求：只要涉及事實，一律再三確認。

  操控室的四個閘門裡「事實」一直是空的（core.js gatesOf 回傳空字串），
  也就是有格子沒有人填。本檔負責填它。

這支能做什麼、不能做什麼（先講清楚，免得把它當成真理機）：
  能做（純機械，不需要 LLM，哨兵每輪都跑得起）：
    1. 抓出文案裡的事實宣稱：年份、年齡、金額、百分比、人數、研究/學者引用。
    2. 檢查每一條宣稱有沒有對應的來源（posts.json 的 facts 陣列）。沒有＝block。
    3. 檢查來源連結是否還活著（HTTP 200）。死連結＝block。
    4. 把宣稱裡的數字拿去比對來源頁面的實際內容。數字對不上＝block；
       抓不到頁面文字（JS 渲染、付費牆）＝warn，交給人看。
    5. 擋掉「首頁型」來源：trends 首頁、某站首頁這種每天會變的網址＝block，
       因為它明天就證明不了今天的宣稱。
  不能做：判斷來源本身可不可信、判斷推論合不合理。那是人的工作，
    本檔只保證「有出處、出處活著、數字對得上」。

用法：
  python3 scripts/fact_check.py            # 檢查所有未發佈貼文，結果寫回 posts.json
  python3 scripts/fact_check.py --post ID  # 只檢查一篇
  python3 scripts/fact_check.py --dry      # 只印報告，不寫檔
"""
import os, re, argparse, urllib.request, urllib.error, importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 LavaFactCheck/1.0"

# 每天都會變的網址：拿它當出處等於沒有出處（Jason Arday 那張卡的病灶）
VOLATILE = re.compile(
    r"^https?://[^/]*(trends\.google|news\.google|/hot|/trending|/rss)[^/]*/?$"
    r"|^https?://[^/]+/?$",                      # 純網域首頁
    re.I)

# 事實宣稱的樣態。抓得寬一點，寧可多問一句，也不要漏掉沒出處的數字。
# \d 前面統一加 (?<![\d.,]) ：否則「31.1歲」會被讀成「1 歲」、「2,843 名」被讀成「843 名」，
# 然後系統要求你為一個根本不存在的宣稱提供出處〔2026-09-03 實測 2 例〕。
_B = r"(?<![\d.,])"
CLAIM_PATTERNS = [
    (_B + r"\d{4}\s*年", "年份"),
    (_B + r"\d+(?:\.\d+)?\s*歲", "年齡"),
    (r"(?:NT\$|新台幣|US\$|\$)\s*[\d,]+", "金額"),
    (_B + r"\d+(?:\.\d+)?\s*%", "百分比"),
    (_B + r"\d[\d,]*\s*(?:人|位|名|場|次|篇|本|個研究)", "數量"),
    (r"(?:研究|調查|實驗|統合分析|報告)(?:顯示|指出|發現|說)", "研究引用"),
    (r"[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+\s*(?:說|認為|指出|提出)", "人物引述"),
]


# 這幾種行不是宣稱，是排版：整串 hashtag、來源標註、裸網址。
# 〔2026-09-03〕舊版把 caption（含 hashtag 與來源行）跟九張投影片黏成一坨，
# 再用「前後 14 字」的滑動窗切出片語去要出處。後果實測：
#   「#社交焦慮 #台灣單身 #30歲 #心理健康 #」→ 被當成沒有出處的「年齡」宣稱
#   「來源：衛生福利部保護服務司，2020 年…」→ 來源行本身被要求提供來源
#   「灣交友 #KaiCenat Tom Holland 說他沒有」→ 跨越兩個段落、開頭還缺字
# 51 個 block 裡多數出自這裡。判讀的單位要跟讀者眼睛看到的一塊一致。
NOISE_LINE = re.compile(
    r"^\s*(?:資料來源|圖片來源|影片來源|來源|出處|參考|延伸閱讀|Source|Credit|Photo|Image)\s*[:：]"
    r"|^\s*https?://\S+\s*$", re.I)

# 作者自己承認出處還沒查實。只有 1/119 條，但那一條正是「95.1% 拿 UCSD 新聞稿佔位」，
# 不抓出來就會以「數字對不上」的錯誤理由被擋，人看了不知道真正該做什麼。
UNVERIFIED = re.compile(r"注意】|尚待|暫以|待補|待查|查證中|佔位|暫代|自行確認")


def _strip_noise(t):
    """去掉排版記號、hashtag、來源行、裸網址，剩下真正在對讀者說話的字。"""
    t = re.sub(r"[【】〖〗]", "", t or "")
    t = re.sub(r"#\S+", " ", t)
    keep = [ln for ln in t.split("\n") if ln.strip() and not NOISE_LINE.match(ln)]
    return re.sub(r"[ \t]+", " ", "\n".join(keep)).strip()


def claim_units(p):
    """把一篇拆成「可以獨立判讀的一塊」：文案一段一塊、投影片一張一塊。
    出處對不對得上要在同一塊裡判斷——同一張投影片的來源行就在它自己底下。"""
    units = []
    if p.get("topic"):
        units.append(("主題", _strip_noise(p["topic"])))
    for i, para in enumerate((p.get("caption") or "").split("\n\n")):
        units.append(("文案第 %d 段" % (i + 1), _strip_noise(para)))
    for s in p.get("slides", []):
        units.append(("第 %s 張" % s.get("n"),
                      _strip_noise((s.get("heading") or "") + "\n" + (s.get("display_copy") or ""))))
    return [(w, t) for w, t in units if t]


def find_claims(units):
    """回傳 [{claim, kind, where, unit}]。同一個宣稱在同一塊裡只算一次；
    「2003年」與「2003 年」是同一個宣稱，正規化後才去重（舊版當成兩條，各擋一次）。"""
    out, seen = [], set()
    for where, text in units:
        for pat, kind in CLAIM_PATTERNS:
            for m in re.finditer(pat, text):
                key = (where, kind, re.sub(r"\s+", "", m.group(0)))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"claim": re.sub(r"\s+", " ", m.group(0)).strip(), "kind": kind,
                            "where": where, "unit": text})
    return out


def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        # 上限從 400KB 提到 8MB〔2026-09-03〕：Netflix 官方 TSV 的台灣區資料
        # 落在第 2,700 萬個位元組附近，400KB 永遠讀不到，出處等於形同虛設。
        # 8MB 是折衷——大到吃得下榜單型檔案，小到不會被單一巨檔拖垮整輪。
        raw = r.read(8_000_000)
    enc = "utf-8"
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:2000], re.I)
    if m:
        enc = m.group(1).decode("ascii", "ignore")
    html = raw.decode(enc, "ignore")
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


def check_source(src):
    """回傳 (狀態, 訊息, 頁面文字或 None)。狀態 ∈ ok / dead / volatile / unreadable"""
    url = (src or "").strip()
    if not url.startswith("http"):
        return "dead", "不是有效網址", None
    if VOLATILE.match(url):
        return "volatile", "這是首頁或即時榜，內容每天會變，明天證明不了今天的宣稱", None
    try:
        txt = fetch(url)
    except urllib.error.HTTPError as e:
        # 403/429 多半是擋爬蟲（學術出版社、Cloudflare），連結本身是活的，
        # 人用瀏覽器開得起來——降為「人工看過」而不是判死（Wiley DOI 實測）。
        if e.code in (401, 403, 429):
            return "unreadable", "站方擋自動抓取（HTTP %s），請人工開啟確認" % e.code, None
        return "dead", "連結回 HTTP %s" % e.code, None
    except Exception as e:
        return "unreadable", "抓不到內容：%s" % str(e)[:60], None
    if len(txt) < 200:
        return "unreadable", "頁面幾乎沒有文字（可能需要 JS 或有付費牆）", None
    return "ok", "", txt


def numbers_in(s):
    """抽出數字，並把千分位正規化掉。
    〔2026-09-03〕原本原樣保留逗號，於是文案寫「41,427 次」、來源頁寫「41427」，
    交集為空 → 判成「數字在出處裡找不到」→ block → 那篇永遠排不了程。
    數值相同就是相同，逗號只是排版。同時保留原樣，來源頁若也帶逗號一樣對得上。"""
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s or ""):
        out.add(m)
        bare = m.replace(",", "")
        if bare != m:
            out.add(bare)
        # 「41427」也要能對上寫成「41,427」的來源
        if "," not in m and len(bare.split(".")[0]) > 3:
            ip, _, dp = bare.partition(".")
            out.add("{:,}".format(int(ip)) + (("." + dp) if dp else ""))
    return out


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def _shares_phrase(a, b, n=6):
    """a 裡有沒有任何 n 個字連續出現在 b。用來判斷「這條出處是不是在講這件事」。"""
    a, b = _norm(a), _norm(b)
    return any(a[i:i + n] in b for i in range(len(a) - n + 1))


def _latin_names(s):
    return re.findall(r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+", s or "")


def _match_facts(c, facts):
    """回傳 (數字對得上的出處, 只是在講同一件事的出處)。
    兩者要分開〔2026-09-03〕：舊版混在一起，於是「95.1%」跟一條只是主題相近的
    出處配成一對，再拿那條的網址去找 95.1%，當然找不到，就報「數字對不上」。
    真正的問題是「95.1% 這個數字任何一條出處都沒提到」——講錯理由，人就修錯地方。"""
    want = numbers_in(c["claim"])
    num, topic = [], []
    for f in facts:
        said = "%s %s" % (f.get("claim", ""), f.get("quote", ""))
        blob = "%s %s" % (said, f.get("source", ""))
        # 數字只跟「作者寫下的宣稱與引文」比對，不跟網址比對——
        # 網址裡出現同樣的數字是巧合，不是證據。人名則可以在網址裡（作者頁）。
        if want and (want & numbers_in(said)):
            num.append(f); continue
        if c["kind"] == "人物引述" and any(_norm(n) in _norm(blob) for n in _latin_names(c["claim"])):
            topic.append(f); continue
        if _shares_phrase(f.get("claim", ""), c["unit"]):
            topic.append(f)
    return num, topic


def check_post(p, verbose=False):
    units = claim_units(p)
    claims = find_claims(units)
    facts = p.get("facts") or []          # [{claim, source, quote?}]
    issues, seen = [], set()

    def add(sev, rule, line):
        k = (rule, line)
        if k not in seen:
            seen.add(k)
            issues.append({"severity": sev, "rule": rule, "line": line})

    if not claims:
        return {"ts": SC._now_iso(), "pass": True, "claims": 0,
                "issues": [], "note": "文案未偵測到數字或研究引用"}

    cache = {}

    def verdict(c, f):
        """單一出處撐不撐得住這條宣稱。回傳 None＝撐得住，否則 (severity, rule, 說明)。"""
        note = str(f.get("quote", ""))
        if UNVERIFIED.search(note):
            return ("block", "placeholder_source",
                    "「%s」的出處是暫代的，作者自己註明還沒查證：%s" % (c["claim"], note.strip()[:70]))
        url = f.get("source", "")
        if url not in cache:
            cache[url] = check_source(url)
        st, msg, txt = cache[url]
        if st in ("dead", "volatile"):
            return ("block", st, "「%s」的出處不合格：%s（%s）" % (c["claim"], msg, url))
        want = numbers_in(c["claim"])
        if not want:
            return None if st == "ok" else ("warn", "unreadable",
                    "「%s」的出處無法自動核對，請人工看過：%s" % (c["claim"], url))
        if want & numbers_in(note):
            return None                    # 作者抄回來的原文裡就有這個數字
        if st != "ok":
            return ("warn", "unreadable",
                    "「%s」的出處無法自動核對，請人工看過：%s" % (c["claim"], url))
        if want & numbers_in(txt):
            return None
        return ("block", "number_mismatch",
                "「%s」（%s）的數字在出處原文與頁面都找不到：%s" % (c["claim"], c["where"], url))

    # 報哪一條問題：先報最能指出下一步的。「出處是暫代的」比「數字對不上」有用得多，
    # 因為前者說得出要做什麼（去補真出處），後者只會讓人反覆核對一個本來就不對的網址。
    RANK = {"placeholder_source": 0, "dead": 1, "volatile": 1,
            "number_mismatch": 2, "unreadable": 3}

    for c in claims:
        num_hits, topic_hits = _match_facts(c, facts)
        if numbers_in(c["claim"]) and not num_hits:
            add("block", "no_source",
                "%s的「%s」沒有任何一條出處提到這個數字（%s）" % (c["where"], c["claim"], c["kind"]))
            continue
        matched = num_hits or topic_hits
        if not matched:
            # 「研究指出…」這種沒有數字的訴諸權威，本身無從查核；擋它只會全線停住，
            # 而且它旁邊的數字已經另外成為一條可查核的宣稱。降為提醒，仍然會顯示。
            if c["kind"] == "研究引用":
                add("warn", "vague_authority",
                    "%s寫「%s」但沒有指名是哪一個研究" % (c["where"], c["claim"]))
            else:
                add("block", "no_source",
                    "%s的「%s」沒有對應出處（%s）" % (c["where"], c["claim"], c["kind"]))
            continue
        vs = [verdict(c, f) for f in matched]
        if any(v is None for v in vs):
            continue                       # 只要有一條出處撐得住，這條宣稱就過
        sev, rule, line = sorted([v for v in vs if v], key=lambda v: RANK.get(v[1], 9))[0]
        add(sev, rule, line)

    return {"ts": SC._now_iso(), "pass": not [i for i in issues if i["severity"] == "block"],
            "claims": len(claims), "issues": issues}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--post"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    doc = SC.load("posts.json")
    changed = 0
    for p in doc.get("posts", []):
        if a.post and p["id"] != a.post:
            continue
        if not a.post and p.get("status") == "published":
            continue
        r = check_post(p)
        bad = [i for i in r["issues"] if i["severity"] == "block"]
        mark = "✅" if r["pass"] else ("🔴" if bad else "⚠")
        print("%s %-32s 宣稱 %d 項，問題 %d 項" % (mark, p["id"][:32], r["claims"], len(r["issues"])))
        for i in r["issues"][:6]:
            print("    [%s] %s" % (i["severity"], i["line"][:110]))
        if p.get("fact") != r:
            p["fact"] = r; changed += 1
    if changed and not a.dry:
        SC.save("posts.json", doc)
        print("\n已寫回 posts.json（%d 篇）" % changed)
    elif a.dry:
        print("\n--dry：未寫檔")


if __name__ == "__main__":
    main()
