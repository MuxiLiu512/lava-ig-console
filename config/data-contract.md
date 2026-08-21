# 資料契約（修法 B，Jesse 核准 2026-08-21）

## 唯一真相

**`data/posts.json` 是貼文狀態的唯一真相。** 其他所有地方都是投影：

| 位置 | 角色 | 同步方向 |
|---|---|---|
| ClickUp 卡狀態 | 決策層介面（放行）與通知 | posts.json → ClickUp（回寫），例外：發佈完成由 reconcile 拉回 |
| n8n static data | WF10 去重記憶 | 只讀 posts.json；重做換新 id（self-check D4） |
| Drive 檔案 | 素材與成品的儲存 | 入料時讀進 posts.json，之後以 posts.json 為準 |
| data/*.json 其他檔 | 各自領域的真相（reviews、ideas、insights…） | 互相引用靠 id，不複製欄位 |

規則：要改貼文狀態，只能改 posts.json。任何「直接改投影」的捷徑都是未來的事故。

## 不變量（機器每輪驗）

清單與實作：`scripts/verify_invariants.py`（I1 到 I8）。
執行點：哨兵每輪、GitHub Actions 每次提交。違反＝告警／紅燈。
新增不變量的門檻：曾經真實發生過，或代價不可逆。

## 主動觀測（修法 C，2026-08-21 Jesse 修訂）

不設固定凍結期。改為：v2 上線後主動觀測（監工、不變量、effort_log、你的實際使用），
**使用無誤即恢復優化與功能迭代**。Reels 樣片立即開做。
觀測期間的判準：monitor 連續綠、不變量零違反、你審稿流程沒有卡點回報。
