# 訊號源

`collect_signals.py` 每日抓一次，輸出 `latest.json` 與當日快照。

## 為什麼在本機而不在 n8n
來源清單是易變的（今天 26 個，明天可能 30 個）。放 n8n 每改一次要重新發布，
而 n8n 連線不穩。改成本機抓 → 產出 JSON → push，n8n 只要讀這一個檔。

## 分層
| 層 | 內容 | 源數 |
|---|---|---|
| `tw_local` | PTT×3、中央社×2、自由、ETtoday、女人迷、Google News×2、Google Trends | 11 |
| `global_pop` | GQ、Vogue、The Cut、Dazed、i-D、Highsnobiety、Hypebeast、Refinery29、PAPER、Interview、Cosmopolitan、ELLE、Psyche | 13 |
| `global_forum` | Reddit 四個 sub（日期輪替，見下） | 4 |
| `research` | PsyArXiv 預印本 | 1 |
| `competitor` | App Store 評論（**停用**，見下） | 2 |

## 相關度標記
每則訊號帶 `rel` 欄位，下游選題引擎據此權衡：
- `strong` 標題或摘要命中強訊號詞（dating／situationship／劈腿／已讀不回…）
- `weak` 僅標題命中弱訊號詞（love／single／單身…）
- `raw` 該來源不過濾（Google Trends、Reddit、女人迷等本身就對題）

過濾不追求零雜訊。實測發現單一寬鬆清單會把時裝週報導判成相關，
而收得太緊又會漏掉「BTS ARMY 男友」這種有價值的文化現象。

## 已知限制
- **Reddit**：對本機 IP 限速極嚴（4 個 sub 併發或間隔 8 秒都只有一半成功）。
  改為日期輪替，每天抓一個 sub，四天涵蓋全部。hot 榜變化不快，此延遲可接受。
- **App Store 評論**：2026-08-12 實測 Tinder(547702041)、Bumble(930441707) 的
  customerreviews JSON 皆回 200 但 feed 無 entry 欄位。已停用，待查替代路徑。
- **Dcard**：官方 API 403（Cloudflare），改走 Google News 搜尋 Dcard 熱帖的二手路徑。
- **Threads**：官方 API 需過 App Review 才能搜公開貼文，未接。

## mind 層（人物／書籍／概念）
〔Jesse 2026-08-12 指定，佐證：@heavenravenofficial 的 Tom Holland 顯化篇 27.7k 讚〕

| 來源 | 供什麼題型 |
|---|---|
| Farnam Street | 人物志（Rockefeller 的原則、創辦人心法） |
| Next Big Idea | 書摘（1500 篇訃聞教會我的事、比 IQ 更重要的腦力） |
| The Marginalian | 概念＋人物（Nick Cave 談有意義人生的兩根支柱） |
| Aeon／Big Think | 概念拆解（哲學與心理學長文） |
| TED Talks | 人物觀點 |
| Literary Hub | 書籍與作家 |

**判準另立一組**：這一層要的是心靈、做事風格、魅力，
用約會關鍵字去濾會把 Aeon、Farnam Street 的好文章全部濾掉。
改用 `KW_MIND`（habit／discipline／charisma／meaning／manifest／resilience…）。

對應的 swipe 庫模板（`data/templates.json`）：
- `tpl-manifest-proof-chain` 人物證言鏈，先堆證據再自我翻轉
- `tpl-persona-column` 固定欄目制人物誌
- `tpl-concept-decode` 概念拆解，含反例張
