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
import os, sys, re, json, argparse, urllib.request, urllib.error, importlib.util

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
CLAIM_PATTERNS = [
    (r"\d{4}\s*年", "年份"),
    (r"\d+\s*歲", "年齡"),
    (r"(?:NT\$|新台幣|US\$|\$)\s*[\d,]+", "金額"),
    (r"\d+(?:\.\d+)?\s*%", "百分比"),
    (r"\d[\d,]*\s*(?:人|位|名|場|次|篇|本|個研究)", "數量"),
    (r"(?:研究|調查|實驗|統合分析|報告)(?:顯示|指出|發現|說)", "研究引用"),
    (r"[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+\s*(?:說|認為|指出|提出)", "人物引述"),
]


def post_text(p):
    """一篇貼文裡所有會被讀者看到的字。事實錯在哪一格都是錯。
    先剝掉排版用的重點標記【】〖〗——它們會把「追蹤 134 對伴侶」切成
    「追蹤【134 對伴侶】」，字串比對整組失靈（2026-08-24 首篇實測 5 項誤報 3 項）。"""
    parts = [p.get("topic", ""), p.get("caption", "")]
    for s in p.get("slides", []):
        parts += [s.get("heading") or "", s.get("display_copy") or ""]
    return re.sub(r"[【】〖〗]", "", "\n".join(x for x in parts if x))


def find_claims(text):
    """回傳 [(片語, 類型)]。片語取宣稱前後的一小段，讓人看得懂在講什麼。"""
    out, seen = [], set()
    for pat, kind in CLAIM_PATTERNS:
        for m in re.finditer(pat, text):
            a, b = max(0, m.start() - 14), min(len(text), m.end() + 14)
            frag = text[a:b].replace("\n", " ").strip()
            key = (m.group(0), kind)
            if key in seen:
                continue
            seen.add(key)
            out.append({"claim": m.group(0), "kind": kind, "context": frag})
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


def check_post(p, verbose=False):
    text = post_text(p)
    claims = find_claims(text)
    facts = p.get("facts") or []          # [{claim, source, quote?}]
    issues = []

    if not claims:
        return {"ts": SC._now_iso(), "pass": True, "claims": 0,
                "issues": [], "note": "文案未偵測到數字或研究引用"}

    # 建索引：宣稱片語 → 出處
    byclaim = {}
    for f in facts:
        byclaim.setdefault(str(f.get("claim", "")).strip(), []).append(f)

    def _fact_hits(c):
        """出處條目與宣稱的對應：字串包含，或數字交集（作者在 facts 裡的措辭
        跟文案不必逐字相同——「20% 至 30%」對「20–30%」也該算對上）。"""
        hits = [f for k, v in byclaim.items() if k and re.sub(r"[【】〖〗]", "", k) in c["context"] for f in v]
        if hits:
            return hits
        # 「研究發現」這類宣稱本身沒有數字，改拿前後文的數字去對
        #（「追蹤 134 對伴侶的縱向研究發現」→ 134 對得上 facts 裡的 134）
        want = numbers_in(c["claim"]) or numbers_in(c["context"])
        if want:
            return [f for f in facts
                    if want & numbers_in(str(f.get("claim", "")) + str(f.get("quote", "")))]
        return []

    cache = {}
    for c in claims:
        matched = _fact_hits(c)
        if not matched:
            issues.append({"severity": "block", "rule": "no_source",
                           "line": "「%s」沒有對應出處（%s）" % (c["context"], c["kind"])})
            continue
        for f in matched:
            url = f.get("source", "")
            if url not in cache:
                cache[url] = check_source(url)
            st, msg, txt = cache[url]
            if st in ("dead", "volatile"):
                issues.append({"severity": "block", "rule": st,
                               "line": "「%s」的出處不合格：%s（%s）" % (c["claim"], msg, url)})
            elif st == "unreadable":
                issues.append({"severity": "warn", "rule": "unreadable",
                               "line": "「%s」的出處無法自動核對，請人工看過：%s" % (c["claim"], url)})
            else:
                want = numbers_in(c["claim"])
                if want and not (want & numbers_in(txt)):
                    issues.append({"severity": "block", "rule": "number_mismatch",
                                   "line": "「%s」的數字在出處頁面裡找不到：%s" % (c["claim"], url)})

    return {"ts": SC._now_iso(), "pass": not issues, "claims": len(claims), "issues": issues}


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
