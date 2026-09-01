#!/usr/bin/env python3
"""資料不變量檢查：列出「永遠不准發生」的狀態，每輪機器驗。

存在理由（2026-08-21 Jesse 核准修法 B）：
  31 條自我審查規則證明「出事後補規則」跟不上事故速度。
  改成先宣告不變量，哨兵每輪與 CI 每次提交都跑。
  違反 ＝ 退出碼 1 ＝ 哨兵告警／CI 變紅。

只用標準庫。資料檔正本：data/。posts.json 是唯一真相，其他檔案是投影。

用法：
  python3 scripts/verify_invariants.py            # 全部檢查
  python3 scripts/verify_invariants.py --prev x.json  # 加驗「published 不得變少」（CI 用）
"""
import os, sys, json, glob, datetime, argparse

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA = os.path.join(REPO, "data")
BAD = []
WARN = []


def fail(rule, detail):
    BAD.append((rule, detail))


def warn(rule, detail):
    """進度類問題：東西沒在前進，但資料本身沒壞。
    不擋 CI（會誤擋正常的製作中狀態），但一定要被印出來、被哨兵看到。"""
    WARN.append((rule, detail))


def _age_h(iso):
    if not iso:
        return None
    try:
        return (datetime.datetime.now().astimezone()
                - datetime.datetime.fromisoformat(iso)).total_seconds() / 3600
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", help="上一版 posts.json 路徑（驗 published 只增不減）")
    a = ap.parse_args()

    # I1 所有資料檔必須是合法 JSON，且不含 git 衝突標記
    docs = {}
    for fp in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        name = os.path.basename(fp)
        raw = open(fp, encoding="utf-8").read()
        if "<<<<<<<" in raw or ">>>>>>>" in raw:
            fail("I1-conflict", "%s 含 git 衝突標記" % name)
        try:
            docs[name] = json.loads(raw)
        except Exception as e:
            fail("I1-parse", "%s 不是合法 JSON：%s" % (name, e))

    posts = (docs.get("posts.json") or {}).get("posts", [])
    now = datetime.datetime.now().astimezone().isoformat()

    for p in posts:
        pid = p.get("id", "?")[:28]
        st = p.get("status")
        # I2 scheduled 必有 publish_at（沒有時間的排程＝WF10 永遠不會發）
        if st == "scheduled" and not p.get("publish_at"):
            fail("I2", "%s scheduled 但無 publish_at" % pid)
        # I3 視覺總檢 block 的不得排程（閘門的意義）。
        # 看的是「還沒被處理掉的 block」，不是 qa.pass——pass 只要有任何一項
        # warn 就會是 False，而且它不認得人工覆寫〔2026-09-02〕。
        # 覆寫要一致：排程守門、卡彈偵測、這裡都吃 gate_overrides，否則
        # 你在操控台按了「這項我已確認沒問題」，CI 還是紅的，等於那顆按鈕沒有用。
        if st == "scheduled":
            _ovk = {o.get("key") for o in (p.get("gate_overrides") or [])}
            _blk = [i for idx, i in enumerate((p.get("qa") or {}).get("issues", []))
                    if (i.get("severity") or i.get("sev")) == "block"
                    and "qa:" + str(i.get("line") or i.get("detail") or idx)[:60] not in _ovk]
            if _blk:
                fail("I3", "%s 視覺檢查有 %d 項未處理卻已排程：%s"
                     % (pid, len(_blk), str(_blk[0].get("detail") or "")[:50]))
        # I4 published 必有 published_at（成效對帳靠它）
        if st == "published" and not p.get("published_at"):
            fail("I4", "%s published 但無 published_at" % pid)
        # I5 crop_focus 值域 0..1
        for s in p.get("slides", []):
            cf = s.get("crop_focus")
            if cf is not None:
                okv = (isinstance(cf, list) and len(cf) == 2
                       and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in cf))
                if not okv:
                    fail("I5", "%s s%s crop_focus 非法：%r" % (pid, s.get("n"), cf))

    # I6 主檔與歸檔互斥；歸檔必帶 no_publish 保險
    arch = (docs.get("archived-posts.json") or {}).get("posts", [])
    live_ids = {p.get("id") for p in posts}
    for q in arch:
        if q.get("id") in live_ids:
            fail("I6", "%s 同時在主檔與歸檔" % q.get("id", "?")[:28])
        if not q.get("no_publish"):
            fail("I6", "歸檔 %s 缺 no_publish 保險" % q.get("id", "?")[:28])

    # I7 靈感決定值域（看板寫入、哨兵回寫 ClickUp，寫壞會靜默卡住）
    for x in (docs.get("ideas.json") or {}).get("ideas", []):
        if x.get("decision") not in (None, "approve", "reject"):
            fail("I7", "idea %s decision 非法：%r" % (x.get("task_id"), x.get("decision")))

    # I8 published 只增不減（防同步事故無聲回退；需要上一版）
    if a.prev and os.path.exists(a.prev):
        try:
            prev = {p["id"] for p in json.load(open(a.prev, encoding="utf-8")).get("posts", [])
                    if p.get("status") == "published"}
            cur = {p["id"] for p in posts if p.get("status") == "published"}
            lost = prev - cur - {q.get("id") for q in arch}
            if lost:
                fail("I8", "published 消失且不在歸檔：%s" % sorted(lost))
        except Exception as e:
            fail("I8", "無法比對上一版：%s" % e)

    # I9 事實查核未過的貼文不得排程（Jesse 2026-08-23：只要涉及事實就必須再三確認）。
    # 只看 scheduled：閘門要擋在「即將送出」那一刻。已發佈的是歷史，圖換不掉、
    # 回頭罰它只會讓這條不變量永遠是紅的，然後大家學會忽略紅燈（那才是真正的風險）。
    # 也只擋 block 級：warn（出處抓不到內容，需人工看）不擋，否則付費牆來源會永遠卡死。
    for p in posts:
        if p.get("status") != "scheduled":
            continue
        f = p.get("fact")
        if f is None:
            fail("I9", "%s 已排程/已發佈但從未跑過事實查核" % p["id"])
        elif not f.get("pass"):
            blk = [i for i in (f.get("issues") or [])
                   if (i.get("severity") or i.get("sev")) == "block"]
            if blk:
                fail("I9", "%s 事實查核有 %d 項 block：%s"
                     % (p["id"], len(blk), blk[0].get("line", "")[:60]))

    # ── I10-I15〔2026-09-01 新增〕──────────────────────────────────────
    # 為什麼補這幾條：I1-I9 全部在驗「資料長得對不對」，沒有一條在驗
    # 「東西有沒有在前進」或「兩份該一致的資料是否真的一致」。
    # 這三天抓到的 bug 全部落在後兩類，所以全部靠人來回試才找得到：
    #   稿檔壞掉讓整輪排版全滅（資料一直合法，只是永遠不動）
    #   圖上印著已被修掉的破折號（兩份記錄不一致）
    #   重生的稿沒人接手（狀態合法，就是不前進）
    # 規則：每次事故都要變成這裡的一條，否則同一類還會再來一次。
    import hashlib

    def _slide_hash(p):
        return {str(s.get("n")): hashlib.md5(
            ((s.get("heading") or "") + "\x1f" + (s.get("display_copy") or "")).encode("utf-8")
        ).hexdigest()[:12] for s in p.get("slides", [])}

    try:
        ce = json.load(open(os.path.join(DATA, "copy_edits.json"), encoding="utf-8")).get("edits", [])
    except Exception:
        ce = []
    try:
        ideas = json.load(open(os.path.join(DATA, "ideas.json"), encoding="utf-8")).get("ideas", [])
    except Exception:
        ideas = []

    BANNED_ON_IMAGE = ("——",)          # 圖是最終呈現，禁句在這裡出現＝已經上到成品
    pids = {p["id"] for p in posts} | {p.get("clickup_task_id") for p in posts}

    for p in posts:
        pid = p["id"]
        st = p.get("status")
        has_final = any(s.get("public_url") for s in p.get("slides", []))

        # I10 圖文一致：成品是用「現在這份文字」排的嗎（指紋比對，來源無關）
        if has_final and p.get("render_src_hash"):
            now_h = _slide_hash(p)
            drift = [n for n, h in now_h.items()
                     if p["render_src_hash"].get(n) and p["render_src_hash"][n] != h]
            if drift:
                (fail if st == "scheduled" else warn)(
                    "I10", "%s 第 %s 張的圖是用舊文字排的（文字已改、圖未更新）"
                    % (pid[:26], "、".join(sorted(drift))))

        # I11 禁句不得出現在成品上。閘門擋的是輸入，這條驗輸出——
        # 8/27 修好的破折號到 9/1 還印在圖上，就是因為沒有人驗過輸出。
        for n, lines in (p.get("rendered_lines") or {}).items():
            hit = [b for b in BANNED_ON_IMAGE if any(b in str(l) for l in (lines or []))]
            if hit:
                # scheduled 還來得及修 → 擋下；published 已上線收不回 → 只記錄，
                # 留給週報當「這條規則漏過幾次」的統計，不要每輪都紅著沒人能處理。
                (fail if st == "scheduled" else warn)(
                    "I11", "%s 第 %s 張圖上有禁句 %s%s"
                    % (pid[:26], n, "／".join(hit), "（已發佈，無法回收）" if st == "published" else ""))

        # I12 進度：核准且候選齊全，卻遲遲沒有成品（這次卡 6 天的那類）
        if st == "approved" and not p.get("render_note") and not has_final:
            ready = all(s.get("candidates") for s in p.get("slides", [])
                        if "CTA" not in str(s.get("role", ""))
                        and str(s.get("product_layout") or "") not in ("diagram", "price", "cta"))
            h = _age_h(p.get("status_since") or p.get("candidates_since"))
            if ready and h and h > 4:
                warn("I12", "%s 核准後 %.0f 小時仍無成品（排版可能整輪失敗）" % (pid[:26], h))

        # I13 文案修正要活著：copy_edits 的最新值必須等於現值。
        # 不相等＝有人寫錯層或被重餵沖掉（破折號復活的那個 bug）。
        latest = {}
        for e in sorted([x for x in ce if x.get("post_id") == pid], key=lambda x: x.get("ts", "")):
            for ed in e.get("edits", []):
                latest[(str(ed.get("n")), ed.get("field"))] = ed.get("edited")
        for (n, field), val in latest.items():
            if field == "caption":
                cur = p.get("caption")
            else:
                sl = next((s for s in p.get("slides", []) if str(s.get("n")) == n), None)
                cur = sl.get(field) if sl else None
            if cur is not None and val is not None and cur != val:
                warn("I13", "%s 第 %s 張 %s 的修改沒有生效（現值與 copy_edits 最新值不符）"
                     % (pid[:26], n, field))
                break

    # I14 放行對帳：放行的靈感必須變成貼文（幻影卡與撰稿斷線都在這裡現形）
    for i in ideas:
        if i.get("decision") != "approve":
            continue
        tid = i.get("task_id") or i.get("id")
        if tid in pids:
            continue
        h = _age_h(i.get("decided_at"))
        if h and h > 2:
            warn("I14", "靈感 %s 放行 %.0f 小時仍無對應貼文" % (str(tid)[:14], h))

    # I15 哨兵活著：心跳停了，上面所有檢查都是在驗一份不會再更新的資料
    try:
        hb = json.load(open(os.path.join(DATA, "heartbeat.json"), encoding="utf-8"))
        h = _age_h(hb.get("ts"))
        if h and h > 2:
            warn("I15", "哨兵心跳落後 %.1f 小時（產線可能停擺）" % h)
    except Exception:
        pass

    if WARN:
        print("🟡 進度警告 %d 條（不擋 CI，但要看）：" % len(WARN))
        for r, d in WARN:
            print("  [%s] %s" % (r, d))
    if BAD:
        print("🔴 不變量違反 %d 條：" % len(BAD))
        for r, d in BAD:
            print("  [%s] %s" % (r, d))
        return 1
    print("✅ 不變量 I1-I15 全過（posts %d、archived %d%s）"
          % (len(posts), len(arch), "；進度警告 %d 條" % len(WARN) if WARN else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
