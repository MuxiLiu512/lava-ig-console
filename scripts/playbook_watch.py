#!/usr/bin/env python3
"""外部知識流入：每天去讀別人發表的 IG／Reels 曝光研究，跟我們的做法比對。

為什麼要有這支〔2026-09-10 Jesse：「需要 up to date 地去搜尋網路上有沒有
更多人發布這類領域的曝光及獲客知識點，這是我們現在沒做到的事」〕：

  盤點結果他是對的。系統有完整的內部學習迴路——
    learn_features.py   把每篇的 27 個特徵接上成效
    hypotheses.py       假說登記簿，樣本夠了才判定
    iterate_harness.py  每晚套用已核准的提案
  但那三支全部只吃**我們自己的 11 篇貼文**。11 篇做任何檢定都不顯著，
  等於用 11 筆資料重新發明別人用十萬筆驗證過的東西。

  外面每天有人在做這件事。不去讀是選擇性失明。

這支怎麼運作（四步，每一步都能單獨測）：
  1 抓    照 config/playbook-sources.md 的清單抓網頁純文字
  2 萃取  只留「帶數字的主張」——沒有數字就無法跟我們的設定比對，
          抓回來只是噪音（「要做出高品質內容」這種句子對系統沒有用）
  3 比對  把主張裡的數字跟我們現在的實際設定／實際資料比一比
  4 落地  不一致的寫成提案進 data/proposals.json，等你在操控台決定

  第 4 步是關鍵。知識流入如果只產出一份閱讀清單，等於沒有流入——
  它必須落成一個「要不要改」的決定，才會真的影響產出。

明確不做的事：
  不自動改設定。別人的帳號、受眾、市場都跟我們不同，
  「某研究說 7-15 秒最好」不等於「Lava 的 Reels 就該做 7-15 秒」。
  抓回來的是待驗證的假說，不是命令。

用法：
  python3 scripts/playbook_watch.py            # 抓、比對、寫提案
  python3 scripts/playbook_watch.py --dry      # 只印，不寫檔
  python3 scripts/playbook_watch.py --show     # 印出目前累積的知識庫
"""
import os, re, sys, json, argparse, importlib.util, html as _html
from urllib.request import Request, urlopen

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

REPO = os.path.abspath(os.path.join(_HERE, ".."))
SOURCES = os.path.join(REPO, "config", "playbook-sources.md")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0 Safari/537.36")

# 只有這些題目的數字對我們有用。抓「所有帶數字的句子」會撈回一堆
# 訂閱價、年份、電話號碼——實測第一版就是這樣，噪音佔了七成。
_N = r"\d[\d,.]*\s*"          # 數字（含千分位與小數）後面接空白
TOPICS = {
    "reels_length":  (r"(reel|video|clip)",                    _N + r"(second|sec\b|秒|minute|分鐘)"),
    "watch_time":    (r"(watch\s*time|retention|completion|replay|看完|完播)",
                                                               _N + r"(%|percent|second|秒)"),
    "shares_weight": (r"(share|send\b|dm\b|轉發|分享)",        _N + r"(x\b|times|倍|%|percent)"),
    "saves":         (r"(save|bookmark|收藏|儲存)",             _N + r"(%|percent|x\b|times|倍)"),
    "carousel":      (r"(carousel|slide|輪播|多圖)",            _N + r"(%|percent|x\b|times|倍|px)"),
    "first_slide":   (r"(first slide|hook|cover|第一張|開場)",  _N + r"(%|percent|second|秒)"),
    "posting_freq":  (r"(post|publish|發文|頻率)",              _N + r"(times?\s*)?(per week|per day|a week|a day|/week|/day|每週|每天)"),
    "dimensions":    (r"(1080|4:5|3:4|aspect ratio|尺寸|比例)", r"\b\d{3,4}\s*(x|×|by)\s*\d{3,4}\b|\b\d:\d\b"),
    "caption_len":   (r"(caption|文案|字數)",                   _N + r"(character|word|字元)"),
    "hashtag":       (r"hashtag|標籤",                          _N + r"(hashtag|標籤)"),
}

# 一句話最多這麼長。超過的多半是被抓壞的整段 HTML，不是一句主張。
MAX_CLAIM = 220
MIN_CLAIM = 25


def _fetch(url, timeout=25):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en,zh-TW;q=0.8"})
    with urlopen(req, timeout=timeout) as r:
        raw = r.read(3_000_000)
    enc = "utf-8"
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000], re.I)
    if m:
        enc = m.group(1).decode("ascii", "ignore")
    html = raw.decode(enc, "ignore")
    html = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", html)
    txt = _html.unescape(txt)          # 不解碼的話主張裡會留 &#x27; &amp; 之類的殘渣
    return re.sub(r"[ \t\xa0]+", " ", txt)


def read_sources():
    """讀 config/playbook-sources.md 裡的網址。分區標題保留，方便標註來源類型。"""
    out, sec = [], ""
    try:
        for ln in open(SOURCES, encoding="utf-8"):
            t = ln.strip()
            if t.startswith("## "):
                sec = t[3:].strip(); continue
            if t.startswith("http"):
                out.append((t, sec))
    except Exception as e:
        sys.stderr.write("讀不到來源清單：%s\n" % e)
    return out


def extract_claims(text, url, section):
    """從純文字裡挑出「帶數字、且講到我們在意的題目」的句子。"""
    claims, seen = [], set()
    for raw in re.split(r"(?<=[.。!?！？])\s+", text):
        s = raw.strip()
        if not (MIN_CLAIM <= len(s) <= MAX_CLAIM):
            continue
        if not re.search(r"\d", s):
            continue
        low = s.lower()
        for topic, (subj, num) in TOPICS.items():
            if re.search(subj, low) and re.search(num, low):
                key = re.sub(r"\W+", "", low)[:80]
                if key in seen:
                    break
                seen.add(key)
                claims.append({"topic": topic, "text": s, "source": url,
                               "section": section, "seen_at": SC._now_iso()[:10]})
                break
    return claims


# ── 比對：抓回來的主張 vs 我們現在真的在做什麼 ────────────────────────
def our_state():
    """我們現在的實際做法。每一項都從真實資料讀，不是從記憶寫死。"""
    st = {}
    try:
        posts = SC.load("posts.json").get("posts", [])
        pub = [p for p in posts if p.get("status") == "published"]
        st["published_count"] = len(pub)
        st["slides_typical"] = max(set(len(p.get("slides") or []) for p in pub),
                                   key=[len(p.get("slides") or []) for p in pub].count) if pub else 0
    except Exception:
        pass
    try:
        m = SC.load("metrics.json").get("entries", [])
        st["metrics_rows"] = len(m)
        if m:
            st["avg_save_rate"] = round(sum(float(x.get("save_rate") or 0) for x in m) / len(m), 4)
            st["avg_share_rate"] = round(sum(float(x.get("share_rate") or 0) for x in m) / len(m), 4)
    except Exception:
        pass
    # 畫布尺寸從排版引擎讀，不要用記憶中的數字
    try:
        fs = open(os.path.join(_HERE, "forage_shots.py"), encoding="utf-8").read()
        mm = re.search(r"^W,\s*H\s*=\s*(\d+),\s*(\d+)", fs, re.M)
        if mm:
            w, h = int(mm.group(1)), int(mm.group(2))
            st["canvas"] = "%dx%d" % (w, h)
            st["aspect"] = "%.3f" % (w / h)
    except Exception:
        pass
    # Reels 有沒有在量觀看時長
    try:
        ins = open(os.path.join(_HERE, "ig_insights.py"), encoding="utf-8").read()
        st["tracks_watch_time"] = bool(re.search(r"watch_time|video_view_total_time", ins))
    except Exception:
        st["tracks_watch_time"] = False
    return st


def gaps(claims, st):
    """哪些主張跟我們的現況對不上 → 值得變成提案。

    刻意只做少數幾條硬比對，不做通用的語意比對：
    通用比對會產生大量「看起來相關但無法行動」的提案，那正是噪音。
    每一條規則都對應一個我們真的能改的東西。
    """
    out = []
    topics = {c["topic"] for c in claims}

    if "watch_time" in topics and not st.get("tracks_watch_time"):
        out.append({
            "key": "track_reels_watch_time",
            "title": "Reels 上線前要先量觀看時長",
            "why": "外部研究把觀看時長列為 Reels 第一訊號，但 ig_insights.py 現在只抓 "
                   "reach／saved／shares／likes，沒有 watch time。沒有這個數字，"
                   "Reels 發出去之後我們無法判斷哪一支有效，等於重回盲測。",
            "do": "在 ig_insights.py 的 metric 清單加 ig_reels_avg_watch_time 與 "
                  "ig_reels_video_view_total_time（僅 Reels 型 media 適用）。",
        })

    if "dimensions" in topics and st.get("aspect"):
        # 4:5 = 0.800。有來源開始講 3:4（0.750）能佔更多版面。
        if abs(float(st["aspect"]) - 0.8) < 0.01 and any(
                "3:4" in c["text"] or "1440" in c["text"] for c in claims if c["topic"] == "dimensions"):
            out.append({
                "key": "test_3x4_canvas",
                "title": "測試 3:4 畫布（現在是 4:5）",
                "why": "我們的畫布是 %s（4:5）。有來源指出 2026 起 3:4 在動態牆佔更多"
                       "垂直空間、且在個人檔案格線不會被裁切。這是可 A/B 的改動。" % st["canvas"],
                "do": "以 3:4 出一批，跟現行 4:5 對照 reach 與看完率。改動範圍限排版引擎的 W,H。",
            })

    if "first_slide" in topics:
        out.append({
            "key": "first_slide_discipline",
            "title": "第一張的鉤子紀律要變成硬規則",
            "why": "多個來源指向「第一張承載大部分互動」。我們的範本有 cover 角色，"
                   "但沒有任何閘門在檢查第一張是否只講一件事、是否給出具體承諾。",
            "do": "在 copy_check 加一條 cover 專用規則（單一主張、要有具體名詞或數字），"
                  "先設 warn 觀察一週再決定要不要升成 block。",
        })

    if st.get("metrics_rows", 0) < 30:
        out.append({
            "key": "sample_size_warning",
            "title": "樣本數不足，內部結論先不要當定論",
            "why": "metrics.json 只有 %d 筆。任何「哪種做法比較好」的內部結論在這個"
                   "樣本量下都不顯著。這一條不是要你改什麼，是要系統在報告裡"
                   "誠實標注不確定性。" % st.get("metrics_rows", 0),
            "do": "weekly_report 與 hypotheses 的輸出加上樣本數與「尚不足以判定」標記。",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 個來源（測試用）")
    a = ap.parse_args()

    kb_path = "playbook.json"
    kb = SC.load(kb_path) if os.path.exists(os.path.join(SC.DATA, kb_path)) else {}
    kb.setdefault("note", "外部知識庫：每天從 config/playbook-sources.md 的來源抓回來的"
                          "可查核主張。這裡的東西是「別人說的」，不是我們驗證過的事實。")
    kb.setdefault("claims", [])

    if a.show:
        by = {}
        for c in kb["claims"]:
            by.setdefault(c["topic"], []).append(c)
        for t, rows in sorted(by.items(), key=lambda x: -len(x[1])):
            print("\n## %s（%d 條）" % (t, len(rows)))
            for r in rows[:4]:
                print("   %s" % r["text"][:150])
                print("     ← %s  %s" % (r["source"][:60], r["seen_at"]))
        return 0

    srcs = read_sources()
    if a.limit:
        srcs = srcs[:a.limit]
    print("來源 %d 個" % len(srcs))
    fresh, fails = [], []
    for url, sec in srcs:
        try:
            txt = _fetch(url)
        except Exception as e:
            fails.append((url, type(e).__name__)); continue
        if len(txt) < 500:
            fails.append((url, "頁面幾乎沒有文字（可能需要 JS）")); continue
        cs = extract_claims(txt, url, sec)
        fresh += cs
        print("  %-58s %d 條" % (url[:58], len(cs)))
    for u, why in fails:
        print("  ✗ %-56s %s" % (u[:56], why))

    # 去重：同一句話在多個來源轉述，只留第一次看到的
    known = {re.sub(r"\W+", "", c["text"].lower())[:80] for c in kb["claims"]}
    added = [c for c in fresh if re.sub(r"\W+", "", c["text"].lower())[:80] not in known]
    seen2 = set()
    added = [c for c in added
             if not (re.sub(r"\W+", "", c["text"].lower())[:80] in seen2
                     or seen2.add(re.sub(r"\W+", "", c["text"].lower())[:80]))]

    st = our_state()
    gp = gaps(kb["claims"] + added, st)

    print("\n新增主張 %d 條（庫存 %d → %d）" % (len(added), len(kb["claims"]), len(kb["claims"]) + len(added)))
    print("我們的現況：%s" % json.dumps(st, ensure_ascii=False))
    print("\n落差 %d 項：" % len(gp))
    for g in gp:
        print("  • %s\n      為什麼：%s\n      要做：%s" % (g["title"], g["why"][:110], g["do"][:110]))

    if a.dry:
        print("\n--dry：未寫檔")
        return 0

    kb["claims"] = kb["claims"] + added
    kb["updated_at"] = SC._now_iso()
    SC.save(kb_path, kb)

    # 落差寫成提案，等 Jesse 在操控台決定。key 相同就不重複開。
    pr = SC.load("proposals.json")
    have = {p.get("key") for p in pr.get("proposals", [])}
    new = 0
    for g in gp:
        if g["key"] in have:
            continue
        pr.setdefault("proposals", []).append({
            "id": "PB-" + g["key"], "key": g["key"], "status": "pending",
            "source": "playbook_watch", "ts": SC._now_iso(),
            "title": g["title"], "why": g["why"], "do": g["do"],
        })
        new += 1
    if new:
        SC.save("proposals.json", pr)
    print("\n✓ 知識庫已更新；新開提案 %d 件（到操控台決定要不要試）" % new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
