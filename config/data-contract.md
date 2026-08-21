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

## 面凍結（修法 C）

**2026-08-21 起兩週（至 09-04）：不加新運行面、不加新功能。**
只允許：修接縫、補閘門、修 bug。Reels 樣片屬於已核准項目，不受此限。
理由：31 條事故規則證明接縫成長速度超過修復速度，先止血再擴張。
