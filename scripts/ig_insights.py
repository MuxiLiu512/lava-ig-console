#!/usr/bin/env python3
"""IG 成效抓取：把 data/insights.json 的寫入端從 n8n 搬到本機。

為什麼搬到本機（2026-08-17 查出的停擺真因）：
  n8n WF11（`OF2Obz1kkjbM9gjt`）每天 10:00 確實會跑，也確實拉得到 insights，
  但**沒有任何程式把它的輸出寫進 repo**——過去都是有人在對話裡透過 n8n MCP
  手動執行、手動貼進 insights.json。所以只要沒人開工，成效就停在上次的日期
  （實際停在 2026-07-27，17 天）。這不是 n8n 壞了，是這條線根本沒有自動寫入端。
  改成本機抓 → 哨兵每天寫檔 → 與 collect_signals 同一個架構決定。

token 紀律：
  token 只從 `.sync.json.ig_token` 或環境變數 `LAVA_IG_TOKEN` 讀，兩者都不進 git。
  **絕不寫入 insights.json**：IG media 回應的 `paging.next` URL 內夾 access_token，
  本檔只取白名單欄位（permalink／timestamp／指標），不整包落檔。
  用的是 2026-07-22 重產的永不過期粉專 token（n8n 憑證 `t44CUVrw6Bxkz6Do` 同一支）。

用法：
  python3 scripts/ig_insights.py            # 抓並寫入 data/insights.json
  python3 scripts/ig_insights.py --dry-run  # 只印，不寫檔
  python3 scripts/ig_insights.py --limit 50
"""
import os, sys, json, argparse, datetime, urllib.request, urllib.error, urllib.parse

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA = os.path.join(REPO, "data")
sys.path.insert(0, os.path.join(REPO, "scripts"))

GRAPH = "https://graph.facebook.com/v21.0"
# period=lifetime 下實測可用的全部欄位（HANDOFF §271 已驗證）
METRICS = ["reach", "saved", "shares", "total_interactions",
           "likes", "comments", "profile_visits", "follows"]
# 只有圖文與輪播走這條；Reels 的指標欄位不同（plays/ig_reels_*），日後另開
KINDS = ("IMAGE", "CAROUSEL_ALBUM")
# 落檔白名單：除此之外的欄位一律不寫，避免把夾 token 的 URL 帶進 repo
SNAP_KEYS = tuple(METRICS)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "lava-ig-console/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _token():
    tok = os.environ.get("LAVA_IG_TOKEN")
    if tok:
        return tok.strip()
    p = os.path.join(REPO, ".sync.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("ig_token") or "").strip() or None
    return None


def _discover_user_id(token):
    """用粉專 token 反查 IG Business Account ID，省掉一個要人工填的欄位。"""
    p = os.path.join(REPO, ".sync.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cached = (json.load(f).get("ig_user_id") or "").strip()
        if cached:
            return cached
    d = _get("%s/me/accounts?fields=name,instagram_business_account&access_token=%s"
             % (GRAPH, urllib.parse.quote(token)))
    for pg in d.get("data", []):
        iba = (pg.get("instagram_business_account") or {}).get("id")
        if iba:
            return iba
    raise RuntimeError("粉專底下找不到 instagram_business_account（檢查 IG 是否為專業帳號且已綁粉專）")


def _parse_ts(s):
    """IG 的 2026-07-19T06:01:09+0000 與本機的 2026-07-17T17:45:07+08:00 都要吃。"""
    if not s:
        return None
    s = s.strip()
    if s.endswith("+0000"):
        s = s[:-5] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def _match_post(m, posts, known):
    """media → post_id。三段式，前面命中就不往下走。
    ③ 用時間吻合是因為 posts.json 只有 5/10 篇已發佈稿留了 media_id，
    caption 比對不可靠（IG 會截斷、我們也會在 IG 端手改 caption）。"""
    mid = m["id"]
    for p in posts:                                    # ① 已存的 media_id
        if p.get("media_id") == mid:
            return p, "media_id"
    if mid in known:                                   # ② insights.json 舊映射
        pid = known[mid]
        hit = next((p for p in posts if p["id"] == pid), None)
        # 舊映射指向的 id 可能已改名（重做會換 id，見 self-check D4）或已歸檔。
        # 查不到就往下走 ③，不要卡在這裡——否則那篇的成效永遠對不回貼文。
        if hit:
            return hit, "insights"
    mt = _parse_ts(m.get("timestamp"))                 # ③ 發佈時間吻合（±30 分）
    if mt:
        for p in posts:
            pt = _parse_ts(p.get("published_at") or p.get("publish_at"))
            if pt and abs((mt - pt).total_seconds()) < 1800:
                return p, "timestamp"
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    token = _token()
    if not token:
        print("！缺 ig_token（.sync.json 或 LAVA_IG_TOKEN）→ 略過成效抓取。"
              "\n   一次性設定：把 n8n 憑證 t44CUVrw6Bxkz6Do 的粉專 token 貼進 .sync.json 的 \"ig_token\"。"
              "\n   .sync.json 已在 .gitignore，token 不會進 repo。")
        return 0

    try:
        uid = _discover_user_id(token)
        media = _get("%s/%s/media?fields=id,caption,timestamp,permalink,media_type"
                     "&limit=%d&access_token=%s" % (GRAPH, uid, args.limit, urllib.parse.quote(token)))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        # code 190 = token 失效（2026-07-22 那次就是缺 pages_read_engagement／pages_show_list）
        bad_token = '"code":190' in body or "OAuthException" in body
        print("✗ IG API 失敗（HTTP %s）：%s" % (e.code, body))
        if bad_token and not args.dry_run:
            try:
                import sync_console as sc
                sc.alert(argparse.Namespace(
                    message="IG token 失效（code 190），成效停止更新。照 HANDOFF「token 重產流程」重產並更新 .sync.json.ig_token 與 n8n t44CUVrw6Bxkz6Do。"))
            except Exception as ex:
                print("! 告警送出失敗：%s" % ex)
        return 1

    ins_path = os.path.join(DATA, "insights.json")
    with open(ins_path, encoding="utf-8") as f:
        ins = json.load(f)
    ins.setdefault("media", {})
    known = {mid: e.get("post_id") for mid, e in ins["media"].items() if e.get("post_id")}

    pj_path = os.path.join(DATA, "posts.json")
    with open(pj_path, encoding="utf-8") as f:
        pj = json.load(f)
    posts = pj.get("posts", [])

    today = datetime.date.today().isoformat()
    rows = [m for m in media.get("data", []) if m.get("media_type") in KINDS]
    updated, backfilled, failed = 0, [], 0

    for m in rows:
        mid = m["id"]
        try:
            got = _get("%s/%s/insights?metric=%s&period=lifetime&access_token=%s"
                       % (GRAPH, mid, ",".join(METRICS), urllib.parse.quote(token)))
        except urllib.error.HTTPError as e:
            # 單篇失敗不該讓整輪掛掉：新發佈的貼文 IG 還沒建 insights 索引就會 400
            failed += 1
            print("  ⏭ %s insights 取不到（HTTP %s）" % (mid, e.code))
            continue

        snap = {"day": today}
        for row in got.get("data", []):
            name = row.get("name")
            if name not in SNAP_KEYS:
                continue
            vals = row.get("values") or [{}]
            snap[name] = vals[0].get("value", 0)

        post, how = _match_post(m, posts, known)
        e = ins["media"].setdefault(mid, {})
        e["permalink"] = m.get("permalink", "")          # 白名單欄位，不夾 token
        e["timestamp"] = m.get("timestamp", "")
        if post:
            e["post_id"] = post["id"]
            e["topic"] = post.get("topic") or post.get("title") or ""
            if how == "timestamp" and not post.get("media_id"):
                post["media_id"] = mid                   # 順手補回，下次就走 ① 路徑
                backfilled.append((post["id"], mid))
        snaps = [s for s in e.get("snapshots", []) if s.get("day") != today]
        snaps.append(snap)                               # 同日重跑覆寫，不重複堆
        e["snapshots"] = sorted(snaps, key=lambda s: s.get("day", ""))
        updated += 1
        print("  ✓ %-20s reach %-5s 互動 %-4s %s" % (
            (e.get("topic") or mid)[:20], snap.get("reach", "-"),
            snap.get("total_interactions", "-"), "[補 media_id]" if how == "timestamp" else ""))

    ins["updated_at"] = today
    ins["note"] = ("IG 成效由本機 scripts/ig_insights.py 每日抓取（哨兵掛載）。"
                   "每篇每日一筆 snapshot，archive-data 裁切 90 天。token 不進此檔。")

    if args.dry_run:
        print("\n（dry-run 不寫檔）媒體 %d 篇、更新 %d、失敗 %d" % (len(rows), updated, failed))
        return 0

    with open(ins_path, "w", encoding="utf-8") as f:
        json.dump(ins, f, ensure_ascii=False, indent=2)
    if backfilled:
        with open(pj_path, "w", encoding="utf-8") as f:
            json.dump(pj, f, ensure_ascii=False, indent=2)

    print("\n✓ 成效更新 %d 篇（媒體 %d、失敗 %d）%s"
          % (updated, len(rows), failed,
             "，補 media_id %d 篇" % len(backfilled) if backfilled else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
