#!/usr/bin/env python3
"""scan_secrets.py — 金鑰外洩守門（2026-07-30）。

為什麼有這支：一次真實事故——PAT 被寫進 git remote URL（.git/config），
雖然沒進 repo，但**任何 `git remote -v` 的輸出都會把它印出來**，於是洩進了
對話紀錄／終端 log／截圖。金鑰不是只有「進 repo」才叫外洩，「被印出來」也是。

檢查四件事（任一紅燈就非 0 退出，可掛 pre-push / CI）：
  1. git remote URL 是否含明文憑證
  2. 待提交(staged)與已追蹤檔案是否含疑似真實金鑰
  3. 敏感檔（.sync.json / .env）是否被 git 追蹤或未被 ignore
  4. git 歷史中是否曾提交過敏感檔

用法：
  python3 scripts/scan_secrets.py            # 掃描並報告
  python3 scripts/scan_secrets.py --staged   # 只掃 staged（給 pre-commit 用）
"""
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SENSITIVE_FILES = [".env", ".env.local", ".sync.json", "credentials.json"]

# 疑似真實金鑰：前綴 + 足夠長度 + 字元夠雜（避開 github_pat_xxx 這種文件佔位符）
PATTERNS = {
    "GitHub PAT": r"\b(?:github_pat_[A-Za-z0-9_]{30,}|ghp_[A-Za-z0-9]{30,})\b",
    "ClickUp":    r"\bpk_\d{6,}_[A-Z0-9]{25,}\b",
    "OpenAI":     r"\bsk-[A-Za-z0-9_-]{30,}\b",
    "Anthropic":  r"\bsk-ant-[A-Za-z0-9_-]{30,}\b",
    "PostHog":    r"\bphc_[A-Za-z0-9]{30,}\b",
    "Google API": r"\bAIza[0-9A-Za-z_-]{33,}\b",
    "Slack":      r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b",
}
PLACEHOLDER = re.compile(r"(REPLACE|YOUR_|XXXX|<[^>]*>|\.\.\.|範例|佔位|placeholder|example)", re.I)


def _git(*args):
    try:
        return subprocess.run(["git"] + list(args), cwd=REPO, capture_output=True,
                              text=True, timeout=20).stdout
    except Exception:
        return ""


def mask(s):
    """顯示金鑰時一律遮蔽——報告本身不能變成第二次外洩。"""
    return (s[:10] + "…" + s[-3:]) if len(s) > 16 else "***"


def scan_text(txt, where, out):
    for name, pat in PATTERNS.items():
        for m in re.finditer(pat, txt or ""):
            s = m.group(0)
            line_start = txt.rfind("\n", 0, m.start()) + 1
            line_end = txt.find("\n", m.end())
            line = txt[line_start:line_end if line_end > 0 else len(txt)]
            if PLACEHOLDER.search(line):
                continue          # 文件裡的佔位符不算
            out.append("  ⛔ %s：疑似 %s（%s）" % (where, name, mask(s)))


def main():
    staged_only = "--staged" in sys.argv
    problems = []

    # 1) remote URL 明文憑證
    for line in _git("remote", "-v").splitlines():
        if re.search(r"(github_pat_|ghp_|x-access-token:|://[^/]*:[^@/]+@)", line):
            problems.append("  ⛔ git remote URL 含明文憑證 → 執行："
                            "git remote set-url origin https://github.com/<owner>/<repo>.git")
            break

    # 2) 檔案內容
    if staged_only:
        files = [f for f in _git("diff", "--cached", "--name-only").split("\n") if f.strip()]
    else:
        files = [f for f in _git("ls-files").split("\n") if f.strip()]
    # --staged 且暫存區為空＝沒有東西要提交，直接放行。
    # 2026-08-30 實案：與哨兵的 git 動作撞在同一工作樹，暫存被清空後
    # 走到下面的檔案系統後備掃描，把 gitignore 隔離中的 .sync.json 當外洩擋下。
    # 後備掃描只留給「非 git repo」的情境（如海巡）。
    if not files and staged_only:
        files = []
    elif not files:    # 非 git repo（如海巡）：掃描原始碼與文件
        for root, dirs, fs in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in
                       {".git", "node_modules", "__pycache__", "data", "inbox", "eval"}]
            for fn in fs:
                if fn.endswith((".py", ".mjs", ".js", ".sh", ".md", ".json", ".html", ".command")):
                    files.append(os.path.relpath(os.path.join(root, fn), REPO))
    for f in files:
        p = os.path.join(REPO, f)
        if not os.path.isfile(p) or os.path.getsize(p) > 2_000_000:
            continue
        try:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                scan_text(fh.read(), f, problems)
        except OSError:
            continue

    # 3) 敏感檔是否被追蹤 / 未被 ignore
    tracked = set(_git("ls-files").split("\n"))
    for sf in SENSITIVE_FILES:
        if sf in tracked:
            problems.append("  ⛔ %s 正被 git 追蹤 → git rm --cached %s 並加進 .gitignore" % (sf, sf))
        elif os.path.exists(os.path.join(REPO, sf)):
            # git check-ignore 在非 git 專案會失效 → 退回直接讀 .gitignore（避免誤報）
            gi = os.path.join(REPO, ".gitignore")
            ignored = False
            if os.path.isdir(os.path.join(REPO, ".git")):
                ignored = subprocess.run(["git", "check-ignore", "-q", sf],
                                         cwd=REPO).returncode == 0
            elif os.path.exists(gi):
                with open(gi, encoding="utf-8", errors="ignore") as fh:
                    rules = {ln.strip().rstrip("/") for ln in fh if ln.strip()
                             and not ln.startswith("#")}
                ignored = sf in rules or sf.lstrip("./") in rules
            if not ignored:
                problems.append("  ⛔ %s 存在但未被 .gitignore 擋 → 加進 .gitignore" % sf)

    # 4) 歷史中曾提交敏感檔
    for sf in SENSITIVE_FILES:
        if _git("log", "--oneline", "--all", "--", sf).strip():
            problems.append("  ⛔ %s 曾進過 git 歷史 → 需輪替金鑰並考慮清理歷史" % sf)

    if problems:
        print("金鑰守門：發現 %d 項問題" % len(problems))
        print("\n".join(problems))
        return 1
    print("金鑰守門：✅ 全部通過（remote 乾淨、無疑似金鑰、敏感檔已隔離）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
