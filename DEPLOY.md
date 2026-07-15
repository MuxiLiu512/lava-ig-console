# 部署指南

> 決策已定：**公開 repo、帳號 muxiliu512**。`config.js` 已設 `publicRaw:true`。

## 什麼是 PAT？

PAT（Personal Access Token，個人存取權杖）＝一組給「程式／腳本」用的專用密碼，讓它們代你操作 GitHub。它比帳號密碼安全，因為可以**限縮權限**（只授權這一個 repo、只給讀寫檔案與建 issue）、**設到期日**、隨時撤銷。我們用它讓：① 操控室網頁把你的審核寫回 repo；② 上線腳本把程式碼推上去。

## 步驟一：在 GitHub 網站建立空 repo

1. 登入 GitHub（帳號 `muxiliu512`）→ 右上「＋」→ **New repository**。
2. Repository name 填 `lava-ig-console`；選 **Public**；**不要**勾 Add a README；按 **Create repository**。

（fine-grained PAT 必須指定一個「已存在」的 repo，所以要先建。）

## 步驟二：建立 fine-grained PAT

1. 右上頭像 → **Settings** → 左下 **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**。
2. 填：**Token name** = `lava-ig-console`；**Expiration** = 90 days；**Resource owner** = `muxiliu512`。
3. **Repository access** → 選 **Only select repositories** → 勾 `lava-ig-console`。
4. **Permissions** → 展開 **Repository permissions**，設：
   - **Contents** → **Read and write**
   - **Issues** → **Read and write**
   -（Metadata 會自動變 Read，正常）
5. 按 **Generate token** → **複製那串 `github_pat_...`**（只會顯示一次，關掉就看不到）。

## 步驟三：把 token 填進本機 .sync.json

```bash
cd "貼文製造機器人/lava-ig-console"
cp .sync.json.example .sync.json
open -e .sync.json          # 用文字編輯器打開，把 "token" 那格換成剛複製的 github_pat_...（owner/repo 已是對的）
```
`.sync.json` 已被 `.gitignore` 忽略，**不會進 repo**。

## 步驟四：首推 + 開 Pages + 建 issue

```bash
bash scripts/bootstrap_github.sh     # repo 已存在 → 直接推程式碼 + 嘗試開 Pages
bash scripts/create_issues.sh        # 建立待決 issue（冪等，重跑不會重複）
```
若腳本的「開 Pages」那步沒成功（token 未含 Pages 權限屬正常），到 repo **Settings → Pages → Source = Deploy from a branch → 選 `main` 分支、`/docs` 資料夾 → Save** 手動開即可。

完成後 Pages 網址：`https://muxiliu512.github.io/lava-ig-console/docs/`（首次 1–2 分鐘）。

## 步驟五：手機開 Pages、貼入同一枚 PAT

開上面的 Pages 網址 → 右上 ⚙︎ **設定** → 貼入同一枚 `github_pat_...` → **測試連線** → **儲存**。PAT 只存在你這台手機/瀏覽器（localStorage）。之後審核、輸入成效、審批提案、回滾——每個動作都會 commit 回 `data/*.json`。

> 到期（90 天）後：回步驟二重建一枚，更新本機 `.sync.json` 與手機設定即可。

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
