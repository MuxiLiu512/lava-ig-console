#!/usr/bin/env python3
"""文案禁句閘門 — 把「不要出現的 AI 用語」變成機器擋得住的東西。

為什麼需要這支〔2026-08-25〕：
  禁句規則早就寫在 config/style-notes.md，WF01 的審查節點也逐條列了要檢查，
  但實測八篇未發佈稿**全部**違規：59 個破折號、7 個「不是…而是…」。
  查 WF01 的流程才發現結構性破口——審查不過 → 重寫一輪 → **直接存檔**，
  重寫的結果從來沒有被重新審查過。等於「審查」只是延後一輪，不是閘門。

  更根本的問題是：靠 LLM 判斷「有沒有破折號」本來就是錯的工具選擇。
  這種規則是確定性的，正則表達式一次就抓到，不會漏、不會有脾氣、不花錢。
  LLM 該做的是判斷「這句話有沒有人味」，不是數符號。

  操控室四個閘門裡「文案」一直是空格子（core.js gatesOf 回傳空字串），
  跟「事實」當初一樣。本檔負責填它。

用法：
  python3 scripts/copy_check.py            # 檢查所有未發佈貼文，寫回 posts.json
  python3 scripts/copy_check.py --dry      # 只印報告
  python3 scripts/copy_check.py --post ID
"""
import os, re, json, argparse, importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sc", os.path.join(_HERE, "sync_console.py"))
SC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(SC)

# (規則名, 正則, 嚴重度, 怎麼改)
RULES = [
    ("破折號", r"——", "block",
     "刪掉破折號。前半句收句號，後半句自己成句；或改成冒號。"),
    ("不是…而是…", r"不是[^，。！？\n]{1,14}而是", "block",
     "這是最典型的 AI 句式。直接講你要說的那一半，不要先否定一個沒人主張的東西。"),
    ("不只是…而是", r"不只是[^，。！？\n]{1,14}而是", "block", "同上。"),
    ("對話式開場", r"^\s*(欸|誒)[…\.、，]|你有沒有發現|你知道嗎", "block",
     "標題禁用對話式開場（Jesse 2026-08-23）。改成具體的人、作品、數字或事件。"),
    ("赦免式安慰", r"這不是你(太|不夠|的錯)|不是你的問題", "warn",
     "替讀者說出自我懷疑再赦免，是 AI 腔的第二名。拿掉，讓讀者自己認領。"),
    # 產品用語合規（lava-product-context 明列的禁用詞）
    ("產品禁用詞", r"加價|手續費|漲價|買到對象", "block",
     "改用「平日優惠場／精選時段／店家加碼／黃金場」等既定說法。"),
]


def post_text_parts(p):
    """回傳 [(位置說明, 文字)]，讓報告能指出是哪一格出問題。"""
    out = [("標題", p.get("topic", "")), ("貼文文案", p.get("caption", ""))]
    for s in p.get("slides", []):
        if s.get("heading"):
            out.append(("第%s張主標" % s.get("n"), s["heading"]))
        if s.get("display_copy"):
            out.append(("第%s張內文" % s.get("n"), s["display_copy"]))
    return [(w, t) for w, t in out if t]


def check_post(p):
    issues = []
    for where, txt in post_text_parts(p):
        # 標題類規則只驗標題與主標，內文出現對話式開場不算違規
        is_head = where in ("標題",) or where.endswith("主標")
        for name, pat, sev, fix in RULES:
            if name == "對話式開場" and not is_head:
                continue
            for m in re.finditer(pat, txt, re.M):
                a = max(0, m.start() - 10); b = min(len(txt), m.end() + 10)
                issues.append({
                    "severity": sev, "rule": name, "where": where,
                    "line": "%s：…%s…" % (where, txt[a:b].replace("\n", " ")),
                    "fix": fix,
                })
    return {"ts": SC._now_iso(), "pass": not issues,
            "counts": {n: sum(1 for i in issues if i["rule"] == n)
                       for n, *_ in RULES if any(i["rule"] == n for i in issues)},
            "issues": issues[:40]}


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
        blocks = [i for i in r["issues"] if i["severity"] == "block"]
        mark = "✅" if r["pass"] else ("🔴" if blocks else "⚠")
        print("%s %-32s %s" % (mark, p["id"][:32],
                               "乾淨" if r["pass"] else r["counts"]))
        for i in r["issues"][:4]:
            print("    [%s] %s" % (i["severity"], i["line"][:100]))
        if p.get("copy") != r:
            p["copy"] = r; changed += 1
    if changed and not a.dry:
        SC.save("posts.json", doc)
        print("\n已寫回 posts.json（%d 篇）" % changed)
    elif a.dry:
        print("\n--dry：未寫檔")


if __name__ == "__main__":
    main()
