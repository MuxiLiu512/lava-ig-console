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


def fail(rule, detail):
    BAD.append((rule, detail))


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
        # I3 視覺總檢 block 的不得排程（閘門的意義）
        if st == "scheduled" and (p.get("qa") or {}).get("pass") is False:
            fail("I3", "%s qa 未過卻已排程" % pid)
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

    if BAD:
        print("🔴 不變量違反 %d 條：" % len(BAD))
        for r, d in BAD:
            print("  [%s] %s" % (r, d))
        return 1
    print("✅ 不變量 I1-I8 全過（posts %d、archived %d）" % (len(posts), len(arch)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
