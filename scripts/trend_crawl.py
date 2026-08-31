#!/usr/bin/env python3
"""書榜與趨勢爬取 — 給選題雷達的第一手證據（crawl4ai，2026-08-31 上線）。

為什麼：雷達的「書與趨勢榜」題型一直靠 Google News 的二手報導猜榜單，
弱證據撐不起「出圈證明」門檻。直接爬榜單頁＝第一手、零 API 費用。
實測（2026-08-31）：博客來排行榜一次拿回完整書單含連結，每頁 2-4 秒。

架構位置：只能跑在哨兵層（需要完整 Chromium，n8n 雲端跑不了）。
輸出 data/trend_crawl.json → git push → WF05「Fetch trend_crawl 05」讀取
→「Append Trend Data」拼進 digest。來源壞了就少一段，不擋雷達主流程。

執行環境：repo 根的 .venv-c4ai（Python 3.14＋crawl4ai＋playwright chromium，
gitignored；建法見本檔尾註）。auto_render 每日一次呼叫。

尾註（重建環境）：
  /opt/homebrew/bin/python3.14 -m venv .venv-c4ai
  .venv-c4ai/bin/pip install crawl4ai && .venv-c4ai/bin/python -m playwright install chromium
"""
import os, sys, json, asyncio, datetime, re

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(REPO, "data", "trend_crawl.json")

# 來源清單：名稱、URL、每段字數上限。加來源只改這裡。
# 單來源失敗只損失該段（雷達還有其他熱度來源），所以清單可以放膽試新站。
SOURCES = [
    ("博客來即時榜（書榜題型的第一手證據）",
     "https://www.books.com.tw/web/sys_saletopb/books/", 3500),
    # 候選來源（2026-08-31 實測不合格，留座位待換 URL 再開）：
    # 誠品 /Search/BestSellers → SPA 404 空殼；Readmoo /bestsellers → 58 字空殼。
]
PER_PAGE_TIMEOUT_MS = 30000


def _clean(md, cap):
    """壓縮 markdown：去圖片、去 javascript 連結、去連續空行，裁到上限。"""
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
    md = re.sub(r"\(javascript:[^)]*\)", "()", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()[:cap]


async def crawl_all():
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, DefaultMarkdownGenerator
    from crawl4ai.content_filter_strategy import PruningContentFilter
    md_gen = DefaultMarkdownGenerator(content_filter=PruningContentFilter(threshold=0.45))
    sections = []
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        for name, url, cap in SOURCES:
            try:
                cfg = CrawlerRunConfig(page_timeout=PER_PAGE_TIMEOUT_MS, magic=True,
                                       remove_overlay_elements=True, markdown_generator=md_gen)
                r = await crawler.arun(url=url, config=cfg)
                md = _clean((r.markdown.fit_markdown or r.markdown.raw_markdown or ""), cap)
                links = len(re.findall(r"\]\(https?://", md))
                # 榜單頁的特徵是「一串連結」。字太少或連結太少＝同意牆、404 空殼
                # 或導覽殘渣（誠品 2026-08-31 實測回 256 字的「頁面不存在」）。
                if len(md) < 200 or links < 8:
                    print("⏭ %s：內容不合格（%d 字、%d 連結），跳過" % (name, len(md), links))
                    continue
                sections.append({"name": name, "url": url, "md": md})
                print("✓ %s：%d 字" % (name, len(md)))
            except Exception as e:
                print("⏭ %s：%s" % (name, str(e)[:120]))
    return sections


def main():
    sections = asyncio.run(crawl_all())
    doc = {
        "note": "書榜與趨勢爬取快照（scripts/trend_crawl.py，每日一次）。WF05 拼進選題 digest。",
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sections": sections,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("寫入 data/trend_crawl.json：%d 段" % len(sections))
    # 全滅要大聲：來源網站同時改版或本機 Chromium 壞了，都不該安靜地讓雷達吃舊資料
    if not sections:
        sys.exit(1)


if __name__ == "__main__":
    main()
