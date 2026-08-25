#!/usr/bin/env python3
"""陳舊稽核：系統的每個輸出都要有退場條件（2026-08-25 Jesse 指定）。

存在理由——這條紀律來自海巡機器人的實際事故，Jesse 要求同樣在這裡執行：

  模型 A/B 在 2026-07-31 就判出勝者並寫進設定檔，落敗方從此沒再產出過內容。
  但面板每天用「全期資料」重算成「差異不顯著」，然後要求人裁決——**問了 25 天**。
  同期還有：功能完成了但「待完成」的文案留在畫面上、錯誤分類漏了一類
  導致建議指錯方向。

  共同結構：**產生訊號有人做，讓訊號退場沒人做。**
  過期的訊號會從資訊退化成噪音，甚至持續要求人做早已無意義的決定。

與 `verify_invariants.py` 的分工：
  不變量問「現在的狀態合法嗎」——違反就是壞掉，退出碼 1、哨兵告警。
  這支問「畫面與文件上的宣稱還成立嗎」——陳舊不是壞掉，是會慢慢腐蝕信任。
  所以**預設不讓 CI 變紅**（退出碼 0），只列清單；`--strict` 才回非 0。

檢查三件事（都是 Jesse 點名的）：
  ① 有沒有垃圾：宣稱「待完成／即將／TODO」的東西是不是其實已經完成
  ② 討論的項目有沒有被實作：決策日誌與 issue 裡講過的，程式裡找不找得到
  ③ 到底有沒有推進：關鍵資料檔多久沒動了

用法：
  python3 scripts/verify_staleness.py            # 列清單，永遠退出 0
  python3 scripts/verify_staleness.py --strict   # 有發現就退出 1（CI 用）
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FINDINGS = []

# 這些詞代表「還沒好」。如果它旁邊的東西其實已經好了，那就是陳舊文案。
PENDING_RE = re.compile(
    r"(待接上|待完成|待補|待實作|尚未|即將|規劃中|TODO|FIXME|coming soon|暫時|先不做|之後再)")

# 掃這些副檔名的文字檔；資料檔與快取不掃
SCAN_EXT = (".md", ".py", ".sh", ".html", ".js", ".json")
SKIP_DIRS = {".git", "node_modules", "__pycache__", "data", "outputs", "素材庫"}


def _rel(p):
    return os.path.relpath(p, REPO)


def _walk():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f.endswith(SCAN_EXT):
                yield os.path.join(root, f)


def check_pending_claims(days=14):
    """① 有沒有垃圾：帶「待完成」字樣、但檔案很久沒動的地方。

    邏輯：一句「待接上 GA4」若寫下之後 14 天沒人碰過那個檔案，
    只有兩種可能——真的沒做（那該進待辦，不是躺在註解裡），
    或已經做了但文案沒改（那就是垃圾）。兩種都需要人看一眼。"""
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    for fp in _walk():
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
            if mtime > cutoff:
                continue                      # 最近改過，還在動，先不管
            with open(fp, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    m = PENDING_RE.search(line)
                    if m and len(line.strip()) > 8:
                        FINDINGS.append(
                            ("陳舊宣稱", "%s:%d 「%s」（檔案 %d 天沒動）"
                             % (_rel(fp), i, line.strip()[:56],
                                (datetime.datetime.now() - mtime).days)))
                        break                 # 一個檔只報一次，不洗版
        except OSError:
            continue


def check_decisions_landed(days=30):
    """② 討論的項目有沒有被實作：決策日誌提到的檔案，之後有沒有被改過。

    只查「決策裡點名了具體檔案」的情況——那是可驗證的。
    純策略決策（例如「先做 A 不做 B」）無法自動驗，留給人的復盤。"""
    dec_dir = os.path.expanduser("~/Claude/brain/workspace/decisions")
    if not os.path.isdir(dec_dir):
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    for fp in sorted(glob.glob(os.path.join(dec_dir, "*.md"))):
        try:
            date = datetime.datetime.strptime(os.path.basename(fp)[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if date < cutoff:
            continue
        body = open(fp, encoding="utf-8", errors="replace").read()
        # 抓決策文裡提到的本 repo 檔案路徑
        for path in set(re.findall(r"`([\w./-]+\.(?:py|sh|md|json|html))`", body)):
            full = os.path.join(REPO, path)
            if not os.path.exists(full):
                continue
            if datetime.datetime.fromtimestamp(os.path.getmtime(full)) < date:
                FINDINGS.append(
                    ("決策未落地", "%s 提到 %s，但該檔在決策日之後沒有被改過"
                     % (os.path.basename(fp), path)))


def check_progress(days=7):
    """③ 到底有沒有推進：關鍵資料檔多久沒動。

    這條刻意只看**產出物**而不是程式碼——程式沒改可能只是穩定，
    但產出物停滯就是真的停了。"""
    watch = ["data/posts.json", "data/heartbeat.json"]
    now = datetime.datetime.now()
    for rel in watch:
        fp = os.path.join(REPO, rel)
        if not os.path.exists(fp):
            FINDINGS.append(("推進停滯", "%s 不存在" % rel))
            continue
        age = (now - datetime.datetime.fromtimestamp(os.path.getmtime(fp))).days
        if age > days:
            FINDINGS.append(("推進停滯", "%s 已 %d 天沒有更新" % (rel, age)))
    # git 也看一眼：本 repo 多久沒有提交
    try:
        out = subprocess.run(["git", "-C", REPO, "log", "-1", "--format=%ct"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        if out:
            age = (now - datetime.datetime.fromtimestamp(int(out))).days
            if age > days:
                FINDINGS.append(("推進停滯", "最後一次提交在 %d 天前" % age))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="有發現就回非 0（CI 用）。預設只列清單不擋。")
    ap.add_argument("--days", type=int, default=14, help="陳舊門檻天數")
    a = ap.parse_args()

    check_pending_claims(a.days)
    check_decisions_landed()
    check_progress()

    if not FINDINGS:
        print("✅ 陳舊稽核：沒有發現。")
        return 0

    groups = {}
    for kind, detail in FINDINGS:
        groups.setdefault(kind, []).append(detail)
    print("陳舊稽核：%d 項待看" % len(FINDINGS))
    for kind, items in groups.items():
        print("\n【%s】%d 項" % (kind, len(items)))
        for d in items[:12]:
            print("  ・%s" % d)
        if len(items) > 12:
            print("  …另外 %d 項" % (len(items) - 12))
    print("\n這些不是錯誤，是「需要有人看一眼」。"
          "\n處理方式二選一：把宣稱改成現況，或把它變成待辦。放著不動就會變噪音。")
    return 1 if a.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
