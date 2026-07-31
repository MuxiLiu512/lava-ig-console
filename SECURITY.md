# 金鑰守則（universal harness · 跨專案共用）

> 適用：lava-ig-console、海巡機器人（SGE），以及日後任何 Lava 的自動化專案。
> 這份是**規範層**，配套工具＝`scripts/scan_secrets.py` + `.githooks/pre-commit`。

## 事故與學到的事（2026-07-30）

**發生什麼**：GitHub PAT 被寫進 git remote URL（`.git/config`）。它**沒有**進 repo、
`.sync.json` 也一直被 `.gitignore` 正確擋住——但 `git remote -v` 的輸出把 PAT 原樣印了出來，
於是洩進了對話紀錄。同一次操作也把 `.sync.json` 的 ClickUp token 一併印出。

**核心教訓（違反直覺、值得記住）**：

> **金鑰不是只有「進版控」才叫外洩，「被印出來」也是外洩。**
> 對話紀錄、終端 log、CI log、截圖、螢幕分享——都是外洩管道。
> 防線不能只有 `.gitignore`，還要有「輸出遮蔽」。

第二個教訓：**遮蔽規則要用白名單思維**。當時的遮蔽只處理 `token`/`pat` 兩個鍵名，
`clickup_token` 因為鍵名不同就漏了。**應該預設遮蔽所有值，只放行已知安全的鍵**。

## 四條規則

1. **憑證只存一個地方**：`.sync.json`（git-ignored），推送時才組出來用
   （`push_files.sh` 就是這個設計——remote URL 保持乾淨、不帶憑證）。
2. **任何輸出都先遮蔽**：印設定、印 remote、印 debug 前，一律過遮蔽函式。
   遮蔽用**白名單**（只放行 owner/repo/branch 這類非敏感鍵），不要用黑名單列鍵名。
3. **提交前自動掃描**：`.githooks/pre-commit` 會跑 `scan_secrets.py --staged`，
   偵測到疑似真實金鑰即中止提交。啟用：`git config core.hooksPath .githooks`。
4. **曝光即輪替**：金鑰只要出現在任何 log／對話／截圖，就當作已外洩，立刻重新產生。
   不要賭「應該沒人看到」。

## 檢查清單（新專案 / 定期）

```bash
python3 scripts/scan_secrets.py     # 四項檢查：remote／檔案／敏感檔隔離／git 歷史
git config core.hooksPath .githooks # 啟用提交守門
```

- [ ] `.gitignore` 有 `.sync.json`、`.env`
- [ ] `git remote -v` 不含 `x-access-token:` 或 `github_pat_`
- [ ] 敏感檔從未進過 git 歷史（`git log --all -- .sync.json` 應為空）
- [ ] 所有印出設定的程式都有遮蔽
- [ ] 文件裡的金鑰一律寫成明顯佔位符（`github_pat_xxx`、`pk_xxx`），掃描器會自動略過

## 遮蔽函式參考實作

```bash
# bash（push_files.sh 既有做法）
mask(){ sed -e "s/${TOKEN}/***/g" -e "s#x-access-token:[^@]*@#x-access-token:***@#g"; }
```

```python
# python：白名單思維——預設遮蔽，只放行已知安全鍵
SAFE_KEYS = {"owner", "repo", "branch", "list_id", "assignee_id"}
def safe_dump(cfg):
    return {k: (v if k in SAFE_KEYS else "***") for k, v in cfg.items()}
```
