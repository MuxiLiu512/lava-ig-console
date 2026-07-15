# 部署指南

## 前置：兩個待辦（見 GitHub issues 的 blocker）

1. **決定 repo 可見性**：private（需 GitHub Pro 開私有 Pages）或 public（縮圖公開）。
2. **建立 fine-grained PAT**：
   - GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token
   - Repository access：**Only select repositories → `lava-ig-console`**
   - Permissions：`Contents` = **Read and write**、`Issues` = **Read and write**、`Metadata` = Read
   - 有效期建議 90 天

## 步驟一：本機設定 .sync.json

```bash
cd lava-ig-console
cp .sync.json.example .sync.json
# 編輯 .sync.json，填入 owner / repo / branch / token
```
`.sync.json` 已被 `.gitignore` 忽略，不會進 repo。

## 步驟二：建 repo ＋首推＋開 Pages

```bash
bash scripts/bootstrap_github.sh            # public
# 或
bash scripts/bootstrap_github.sh --private  # private（需 Pro）
```
完成後 Pages 網址約為 `https://<owner>.github.io/lava-ig-console/docs/`（首次 1–2 分鐘）。

> 若偏好手動：GitHub 網站建空 repo → 本機 `git remote add` 後 `git push` → repo Settings → Pages → Source 選 `main` 分支、`/docs` 資料夾。

## 步驟三：確認前端設定

編輯 `docs/config.js`：`owner` 改成實際帳號；public repo 設 `publicRaw: true`（圖片走 raw、較快）、private 保持 `false`。改完 push。

## 步驟四：手機開 Pages、貼入 PAT

開 Pages 網址 → 右上 ⚙︎ **設定** → 填 owner/repo/branch、貼 PAT → **測試連線** → **儲存**。PAT 存在瀏覽器 localStorage。

之後即可審核、輸入成效、審批提案、回滾——每個動作都會 commit 到 `data/*.json`。

## 步驟五（可選）：建立 GitHub issues

```bash
bash scripts/create_issues.sh --dry-run   # 先看要建哪些
bash scripts/create_issues.sh             # 實際建立（冪等，已存在則略過）
```

## 排程掛載（Phase 2/3/4）

| 排程 | 時間 | 指令（cron 內先 `cd lava-ig-console && git pull --rebase`） |
|---|---|---|
| A `lava-ig-daily-pipeline` | 10:00 | 頭：`python3 scripts/sync_console.py pull-reviews`；尾：`add-post --manifest …` → `push "…"` |
| B `lava-ig-iterate` | 21:30 | `python3 scripts/iterate_harness.py` → `bash scripts/push_files.sh "iterate $(date +%F)" config data` |
| C `lava-ig-weekly-report` | 週六 10:00 | `python3 scripts/weekly_report.py --local-copy ../週報` → `push_files.sh "weekly" 週報` |

排程 B/C 可用本機 cron 或既有 harness；每次執行前 `git pull --rebase` 避免與前端寫入撞車。

## 本機預覽（免 repo/PAT）

```bash
cd lava-ig-console && python3 -m http.server 8765
# 瀏覽器開 http://localhost:8765/docs/index.html
```
localhost/file:// 會自動進「本地預覽模式」：讀本機 `data/`、`assets/`，所有操作只改記憶體不 commit——用於 UI 驗收。
