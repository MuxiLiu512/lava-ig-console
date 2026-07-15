# Lava IG 中介操控室（Console）

Jesse 在任何裝置審核每則 IG 貼文（並排選底圖 → IG Mockup 預覽 → approve／退回）、監測成效、審批迭代提案、檢視版本並一鍵回滾。

部署形態：**靜態站（GitHub Pages）＋ GitHub repo 當資料庫**。前端直接以 GitHub Contents API 讀寫 `data/*.json`；本機生產管線與迭代排程透過 git 推拉交換。

## 目錄結構

```
docs/                 GitHub Pages 前端（純 vanilla JS，零外部依賴）
  index.html app.js style.css config.js
data/                 資料庫（JSON）
  posts.json          待審清單（排程A產，前端唯讀）
  reviews.json        審核結果（前端寫，排程讀）
  metrics.json        成效（前端寫；Phase4 後改排程寫）
  proposals.json      迭代提案（排程B寫，前端審批）
  iterate_log.json    迭代日誌＋回滾請求（排程寫，前端唯讀＋發起回滾）
config/               風格規格「機器可改」增補層（git 版本化，每次迭代=一 commit）
  gen-prompt-template.md style-notes.md render-config.json banned-words.txt qc-checklist.md
assets/<post-id>/     縮圖（長邊 1080）：候選底圖 + final/ 成品
週報/YYYY-Wnn.md      排程C 週報
scripts/              本機工具（見下）
github/issues.json    待建 GitHub issues（優化點與待決策）
```

## 前端四分頁

1. **審核**：佇列 → 進單則 → 每 slide 候選底圖並排點選（標生成/劇照/出處）＋ **IG Mockup**（帳號列、3:4 carousel 可滑、動作列、caption、4:5/3:4 裁切切換）→ `核准`／`退回底圖`／`退回排版`（退回強制填回饋）。
2. **成效**：手動輸入 D1/D3/D7 快照 → 儀表板（各貼文觸及/珍藏長條、追蹤增量折線、依題型平均）。
3. **提案**：pending 提案卡（title／依據／diff）→ 核准套用／駁回。
4. **版本**：iterate_log 時間軸（changes／觸發／commit／自動或人工）→ 一鍵回滾至任一版。

寫回統一走 `saveJson(path, mutateFn)`：GET 取 sha → mutate → PUT，409 撞車自動 refetch-sha 重試 3 次。

## 執行階段對照

| Phase | 內容 | 狀態 |
|---|---|---|
| 1 | Repo＋前端骨架＋data/config＋假資料驗收 | ✅ 完成（本 repo） |
| 2 | 生產管線接軌（`sync_console.py`、修改排程A頭尾） | 🟡 腳本完成，排程A改動待接 |
| 3 | 迭代 harness（`iterate_harness.py` 分級/回滾/護欄） | ✅ 邏輯完成並測試 |
| 4 | 成效＋週報（`weekly_report.py`）＋IG API（`ig_insights.py` 空殼） | ✅ 週報完成／IG API 待接 |

## scripts

| 檔 | 用途 |
|---|---|
| `_thumbs.py` | 縮圖共用（有 `cwebp` 走 webp，否則 JPEG） |
| `build_demo.py` | 用既有兩篇成品造 Phase1 驗收假資料 |
| `sync_console.py` | 排程A 橋接：`pull-reviews` / `add-post` / `mark-consumed` / `set-status` / `push` |
| `iterate_harness.py` | 排程B（21:30）：回滾→套用提案→分級改 config→寫 log。`--dry-run` 可預演 |
| `weekly_report.py` | 排程C（週六 10:00）：產 `週報/YYYY-Wnn.md` |
| `ig_insights.py` | Phase4 IG Graph API 空殼（含所需權限註解） |
| `push_files.sh` | 安全推指定路徑（token 遮蔽、無變更跳過、撞車 rebase 重試） |
| `bootstrap_github.sh` | 一鍵建 repo＋首推＋開 Pages |
| `create_issues.sh` | 依 `github/issues.json` 建 issues |

## 部署與設定

見 [DEPLOY.md](DEPLOY.md)。核心三步：① 建 repo、給 fine-grained PAT；② `bootstrap_github.sh` 首推＋開 Pages；③ 手機開 Pages，於『設定』貼入 PAT。

## 護欄（不做的事）

不自動發布貼文；不改 Drive 規格正本；不刪本機檔案；高風險設定不經核准不生效；PAT 只存 localStorage 與本機 `.sync.json`（git-ignored），絕不進 repo。
