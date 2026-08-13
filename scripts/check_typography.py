#!/usr/bin/env python3
"""排版回歸檢查：用「引擎本身的斷行函式」重算每一張的實際行，逐行驗規則。

存在的理由：修好排版不能靠肉眼看一兩張圖確認（Jesse 2026-08-11 質疑「是不是真的修好」）。
這支腳本直接載入 render_post_v5，用同一套 wrap/strip 邏輯重算，違規即列出檔案與行內容。

檢查項目
  1. line_end_punct  行尾殘留分隔標點（，、；：。）
  2. mid_word_break  行尾停在修飾詞（最／不／太／很…），代表詞被拆兩行
  3. missing_glyph   主字型與備援字型都畫不出來的字（會變空白吞字）

用法：
  python3 scripts/check_typography.py            # 掃 posts.json 內未發佈的稿
  python3 scripts/check_typography.py <post-id>  # 只掃一篇
"""
import sys, os, json, re, glob
from PIL import Image, ImageDraw, ImageFont
import importlib.util

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENGINE = os.path.abspath(os.path.join(REPO, "..", "排版引擎", "render_post_v5.py"))
sys.path.insert(0, os.path.join(REPO, "scripts"))

spec = importlib.util.spec_from_file_location("rp5", ENGINE)
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)
import sync_console as sc

_D = ImageDraw.Draw(Image.new("RGB", (10, 10)))

# 檢查用的嚴格子集：只列「單獨出現在行尾幾乎必定是詞被拆開」的字。
# 引擎的 NO_TRAIL 刻意放寬（多回退一格無害），但拿來當檢查標準會誤報——
# 例如「威奇托等地」的「地」是名詞不是助詞，「真正值得問的是」的「是」是句子結尾。
CHECK_NO_TRAIL = set("最不很更太些又再還就才把被讓和與及跟並而但因如若則於")


def _lines_for(text, font, max_w, semantic):
    if semantic:
        out = []
        for t in [l.strip() for l in text.split("\n") if l.strip()]:
            out += E.wrap_semantic(t, (255, 255, 255), font, max_w, _D)
        return E.strip_line_ends(out)
    return E.strip_line_ends(E.wrap_segments(E.parse_highlight(text), font, max_w, _D))


def check_slide(s):
    """回傳 [(規則, 行內容)]。字級／寬度取引擎實際使用的值。"""
    bad = []
    head = E.strip_trailing_punct(re.sub(r"[【】〖〗]", "", s.get("heading") or ""))
    body = E.strip_trailing_punct(s.get("display_copy") or "")
    idx = int(s.get("index") or 0)
    checks = []
    if idx == 1:
        # 封面主標必須走引擎的 cover_title_lines（含動態縮字），不可自行猜字級。
        # 2026-08-13 事故：本檢查原本寫死 W*0.043 / W*0.86，引擎實際 W*0.075 起跳 / W*0.89，
        # 字級只有 57%，算出的斷點與印出來的完全不同，導致「9 篇全過」是假的。
        cov_lines, cov_font, _fs = E.cover_title_lines(s.get("heading") or "", _D)
        for i, line in enumerate(cov_lines):
            t = "".join(tok for tok, _ in line).rstrip()
            if not t:
                continue
            if t[-1] in E.LINE_END_STRIP:
                bad.append(("line_end_punct", t))
            elif i < len(cov_lines) - 1 and t[-1] in CHECK_NO_TRAIL:
                bad.append(("mid_word_break", t))
        checks.append((body, ImageFont.truetype(E.F_MED, int(E.W * E.COVER_SUB_FS)),
                       int(E.W * 0.78), True))
    else:
        checks.append((head, ImageFont.truetype(E.F_MED, int(E.W * E.BODY_TITLE_FS)),
                       E.content_width(), False))
        checks.append((body, ImageFont.truetype(E.F_REG, int(E.W * E.BODY_FS)),
                       E.content_width(), False))
    for text, font, max_w, semantic in checks:
        if not text.strip():
            continue
        # 逐「段」檢查：文案自帶的換行是刻意分行（條列、節奏），其行尾本來就是句子結尾，
        # 只有「同一段被寬度拆成多行」時，非末行的行尾才代表句子被硬切開。
        for para in [x for x in text.split("\n") if x.strip()]:
            lines = _lines_for(para, font, max_w, semantic)
            for i, line in enumerate(lines):
                t = "".join(tok for tok, _ in line).rstrip()
                if not t:
                    continue
                if t[-1] in E.LINE_END_STRIP:
                    bad.append(("line_end_punct", t))
                elif i < len(lines) - 1 and t[-1] in CHECK_NO_TRAIL:
                    bad.append(("mid_word_break", t))
        for ch in text:
            if not ch.strip() or ch in "\n":
                continue
            if not E._has_glyph(font, ch):
                fb = E._fb_of(font)
                if not fb or not E._has_glyph(fb, ch):
                    bad.append(("missing_glyph", "字元「%s」兩種字型皆缺" % ch))
    return bad


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    posts = sc.load("posts.json").get("posts", [])
    ls = sc._load_local_sources()
    total_bad, checked = 0, 0
    for p in posts:
        if only and p["id"] != only:
            continue
        if not only and p.get("status") == "published":
            continue
        e = ls.get(p["id"]) or {}
        jf = e.get("draft_json") or (e.get("draft_jsons") or {}).get("claude")
        if not jf or not os.path.exists(jf):
            print("⏭ %s：找不到文案" % p["id"][:26]); continue
        try:
            d = sc._read_json_retry(jf)
        except Exception as ex:
            print("⏭ %s：讀稿失敗 %s" % (p["id"][:26], ex)); continue
        # 套用操控室的文案編輯，檢查的才是實際會印出來的版本
        edits = sc._latest_copy_edits(p["id"], sc.load("copy_edits.json").get("edits", []),
                                      version=p.get("copy_choice"))
        for s in d.get("slides", []):
            for field in ("heading", "display_copy"):
                k = (int(s.get("index", -1)), field)
                if k in edits:
                    s[field] = edits[k]
        checked += 1
        issues = []
        for s in d.get("slides", []):
            for rule, line in check_slide(s):
                issues.append((s.get("index"), rule, line))
        if issues:
            total_bad += len(issues)
            print("🔴 %s（%d 處）" % (p["id"][:30], len(issues)))
            for n, rule, line in issues[:8]:
                print("   第%s張 [%s] %s" % (n, rule, line[-34:]))
        else:
            print("✅ %s" % p["id"][:30])
    print("\n檢查 %d 篇，違規 %d 處" % (checked, total_bad))
    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
