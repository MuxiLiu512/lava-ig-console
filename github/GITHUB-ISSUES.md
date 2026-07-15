# 待建 GitHub Issues（優化點與待決策）

來源檔：[issues.json](issues.json)。用 `bash scripts/create_issues.sh` 建立（需 PAT 具 Issues:write）。
以下為摘要——完整內容（選項/建議）在 issues.json 的 `body`。

## ✅ 已決策（2026-07-15）

- **可見性＝公開 repo**、**帳號＝`muxiliu512`**。`config.js` 已設 `publicRaw:true`，圖片走 raw、免 GitHub Pro。

## 🚫 Blocker（擋住上線）

| # | 標題 | 需 Jesse 動作 |
|---|---|---|
| 1 | 提供 fine-grained PAT | 建 token（Contents+Issues 讀寫，僅此 repo），放本機 `.sync.json` → 跑 `bootstrap_github.sh` |

## ⚠️ 風險 / 架構

| # | 標題 | 重點 |
|---|---|---|
| 2 | 3:4 成品 vs IG 4:5 裁切 | 3:4 發文會被上下裁切 ~6–7%，hook/footer 有風險；Mockup 已可切換預覽。建議渲染改對 4:5 安全框 |
| 3 | data/*.json 單一寫手原則 | proposals/iterate_log 有雙寫手；附擁有權矩陣待 review，建議欄位級不重疊＋排程先 pull --rebase |
| 7 | 前端零依賴 + 建議加 CSP | 現況良好（無外部 script）；建議加嚴格 CSP meta 永久防護 |

## 💡 優化

| # | 標題 | 重點 |
|---|---|---|
| 4 | assets/ 無限成長 | approve 後刪未選候選、published N 天後移出 final；需定保留窗口 |
| 5 | 縮圖 webp vs jpg | 本機無 webp 編碼器，暫用 JPEG；公開 repo 體積不敏感，建議 `brew install webp` 後自動走 webp |
| 6 | ClickUp 狀態回寫 | 排程A 需接：approve 留言＋改卡片狀態；待確認狀態機對應 |

---

### 我在實作中發現、已直接處理的事（不另開 issue）

- **候選選圖跳頁**：原本點選候選會整頁重繪跳回頂端 → 已改為就地更新選取狀態。
- **母胎資料夾 Unicode**：底圖資料夾含全形「」，macOS NFD 正規化導致字面路徑找不到 → 改前綴掃描定位。
- **本地預覽模式**：file://或 localhost 自動讀本機檔、只改記憶體，讓 UI 免 repo/PAT 即可驗收。
