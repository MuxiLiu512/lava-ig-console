# 操控室 v2 改造計劃

產出方式：五個面向並行分析（資訊架構／技術架構／成本與能力分化／驗證機制／遷移風險）
→ 綜合計劃 → 兩輪對抗審查（過度工程／風險盲點）→ 定案。9 個 agent，2026-08-12。

狀態：**討論用文件，尚未執行**。決策問題見第五節。

---

# Lava 操控室改造計劃（最終版）

2026-08-12 16:20 · 吸收兩份批評後重寫 · 原計劃 4 週 4 階段，現在 3 段約 6 個工作天

---

## 〇、我錯了什麼

三處被說中，我全部接受，並且自己覆核過。

| 原計劃寫的 | 實測 | 影響 |
|---|---|---|
| 0 候選 slide 14/72 = 19%，全域供給不足 | CTA 是公版無候選（`app.js:303`），27 張 0 候選裡 21 張是 CTA。**非 CTA 只有 6 張，集中在 3 篇**（Laa、HelenFisher、DanAri），待審非 CTA 佔比 7.5% | D7「開閘」裁決作廢 |
| 改 `forage_shots.py:651` 的 `keep >= 2` 提到 5 | 我多查一層：那是**單輪 per-slide 上限**，候選跨多輪多來源累積，實際 per-slide 最高 12。改成 5 是乘法不是加法 | 這一項比批評說的更該砍 |
| EDEADLK 根因難查，要加 timeout | 是 `sync_console.py:1275` 被 `except` 吞掉的 per-post 例外，log 每輪跑完。**沒有 hang，timeout 永遠不觸發**。且 15:52 起已自行恢復，佇列 8 → 6 | 治法換成印 traceback ＋「連續 N 輪 0 產出告警」 |

批評二的 R2 我實地重現了，這是全案最重要的發現：

```
stash pop 衝突 → git checkout --theirs -- .   取到的是 stash（哨兵舊版）
                → git checkout -- data/       error: path is unmerged（被 || true 吞掉）
                → 結果檔案 = {"v":"sentinel-local"}
```

`--theirs` 在 stash pop 情境指的是 stash 那一側，不是遠端。程式碼註解寫「一律以遠端為準」，行為相反。後面 `git add -A; commit; push` 會把 Jesse 的核准、排程、文案編輯無聲推回舊版，**產出的 JSON 完全合法，沒有 `<<<<<<<`，schema 檢查抓不到**。

D3 把併發降級的依據是「已修」。這個「已修」不成立。這是目前唯一還活著的資料損毀管道。

---

## 一、我不接受的兩點

**1. 批評一 A2「候選 8-70 張不存在，最大 12」只對一半。**

per-slide 中位數 4、最大 12，這部分對。但 Jesse 講的是**每篇總量**，實測待審 10 篇的 per-post 總候選是 15 到 74（今天 16:02 入料的兩篇分別是 74 和 44）。所以「一篇要看 15 到 74 張縮圖」是真的。

推論修正：不需要 contact sheet 專用模式，不需要 `1-9` 熱鍵，不需要 220px + 360px 三欄骨架。需要的是「一篇的候選在一屏內不用捲」。這是一條 CSS grid 加一個 `Space` 鍵，不是一套佈局系統。方向跟批評一一致，程度不同。

**2. 批評二說「qa 改 fail-closed 會把發佈綁回 Mac，與保留 IG 發佈在 n8n 自相矛盾」。**

矛盾成立，但兩份批評給的都不是解法。正確做法是**把閘門從發佈端前移到人審端**：操控室的「排程」按鈕要求 `qa.pass === true` 才能按。閘門落在 Jesse 手上，不動 WF10，不綁 Mac 在線，不會出現「Mac 睡了所以永遠發不出去」。

支撐證據：`20260728-AzizAnsari` 是 `published` 且 `qa.pass=false`，但 `qa.ts=08-05`，`publish_at=08-03`。qa 是發完兩天後才跑的。**現況不是閘門漏放，是閘門根本沒站在路口上。**

---

## 二、核心命題（收斂）

原計劃三個問題，現在剩兩個。

1. **資料會被無聲回退**（stash 復原反向、archived 有兩篇過期 `scheduled` 隨時可能被重貼、5 篇 8 月貼文 `media_id=None` 狀態不明）
2. **Jesse 是唯一瓶頸，而沒人量過他一篇花幾分鐘**

「管線靜默斷掉」降級成問題 1 的子項。既有監控其實有六種（`alert`、`verify_pipeline`、`check_typography`、n8n errorWorkflow、6 輪 pull 失敗自報、PIL 守門），缺的不是第七種，是沒人看，以及**告警管道跟被監控對象共用故障域**（`sync_console.py:1160` 沒 token 就 `print` 後 return）。

北極星不變：**每篇已發佈貼文消耗的 Jesse 分鐘數**。這個數字現在是零。所有 UI 取捨在它量出來之前都是猜的。

---

## 三、最終計劃

### 段 1｜止血（今天，約 3 小時，不寫任何 UI）

| # | 動作 | 依據 |
|---|---|---|
| 1 | `auto_render.sh:57` 改 `git checkout HEAD -- .`（pull 已完成，HEAD 即遠端），stash 保留供人工比對 | 上面的重現 |
| 2 | `git add -A` 收窄成 `git add data/ docs/finals/ assets/`。目前寫法會把半合併的 `docs/app.js` 推上 Pages，等於砍掉唯一介面 | 批評二 |
| 3 | `save()` 加寫入守門＋原子寫：`published` 篇數不得減少、不得出現新的「已過期 scheduled」、全文不得含 `<<<<<<<`，違反即中止告警。寫 tmp → `os.replace()` | 擋住 R1 重貼與 R2 回退 |
| 4 | 開 WF10 確認三件事：filter 表達式、去重讀 static data 還是 posts.json、當月執行數餘量 | 兩份批評與我的共同最弱環 |
| 5 | 今晚 21:00 那篇手動跑 `post-qa --post-id`，過了才發 | `qa=None`，全庫只有 2 篇跑過 |
| 6 | 人工開 @lava_dating 對照 5 篇 `media_id=None`（全部集中在 8 月，7 月 5 篇都有）。**這 5 篇到底發了沒，在確認前不做任何資料遷移** | 批評二 R3 |
| 7 | `ingest_new` 的 `except` 印 `traceback.format_exc()` | 批評一 A3 |
| 8 | `git mv` 排版引擎進 repo `engine/`，同時凍一批現有 finals 當比對基準 | 兩週改最多、事故最多的檔，不在版控 |
| 9 | 撰稿模型切 Opus 5 開 A/B（`writer_model` 欄位已存在，每篇 +$0.046） | 唯一影響「會不會紅」的環節，需 8 到 10 篇才看得出差異，越晚開始越晚有答案 |

驗收：在 clone 副本上人工製造一次 stash 衝突，Jesse 的編輯必須存活。守門必須擋下 archived 那兩篇過期 scheduled。5 篇狀態全部確定。

### 段 2｜看得見（第 2 天，半天）

| # | 動作 |
|---|---|
| 10 | `heartbeat.json` 只寫三個數字＋錯誤摘要：`{ts, ingested, rendered, qa_run, errors[]}`。操控室 header 一顆燈讀這一個檔。**不寫 liveness.py 七條斷言** |
| 11 | 「連續 3 輪入料 0 篇」→ `alert`。載重的是這條，不是 timeout |
| 12 | 日誌從 `/tmp` 搬進 `~/Library/Logs/`，加輪替。以靜默失敗為主故障模式的系統，鑑識軌跡不能重開機就消失 |
| 13 | **唯一動 n8n 的例外**：一支 cron，每 30 分讀 raw 的 `heartbeat.json`，時戳落後就開 ClickUp 告警卡。死掉的 Mac 無法回報自己死掉，dead man's switch 必須跑在 Mac 以外 |
| 14 | **錄一次完整處理一篇的過程，量出分鐘數，記下卡在哪一步。全案最高 ROI 的一項** |
| 15 | 重跑 Laa / HelenFisher / DanAri 三篇的 forage |

驗收：Mac 關機 40 分鐘，ClickUp 出現告警卡。有一個「每篇 X 分鐘」的基線，且知道那 X 分鐘怎麼分配。

### 段 3｜省時間（第 3 到 5 天，細節由段 2 的錄影決定）

| # | 動作 |
|---|---|
| 16 | 「圖上實際呈現」升為主編輯區，原稿收摺疊區（`rendered_lines` 資料早就有，只是主從搞反） |
| 17 | 候選改 `grid-template-columns: repeat(auto-fill, 96px)`，一篇 15 到 74 張一屏看完。熱鍵只留 `Space`（確認並跳下一張） |
| 18 | 排程按鈕要求 `qa.pass === true`。閘門前移到人審端，零 n8n 改動 |
| 19 | 0 候選 slide 主區直接給補圖面板，帶上次拒收原因 |
| 20 | `gates: {}` 一個欄位收攏 qa / copy_flags / typography / render_note。**`status` 不動，不做三軸** |
| 21 | `verify_pipeline.py` 加 6 條資料不變量，對真實 posts.json 跑，零 fixture：scheduled 必有 publish_at、approved 必有 slide_choices、rendered_at < candidates_since 必須標 stale、qa.pass=false 不得為 scheduled、copy_edits 最新版本須等於 copy_choice、archived 不得有未過期 scheduled |
| 22 | 若段 2 錄影顯示載圖是主要耗時：256px 縮圖進 git、原圖出 git。**原圖直接移出 git 不可行**，`app.js:91-98` 的 `setImg` 走 GitHub blob，assets 離開 repo 等於非 Mac 環境全部破圖 |

### 全期程守則（三條，寫進 HANDOFF）

1. **發佈凍結窗**：有 scheduled 在 60 分鐘內到期時，哨兵不 push、不改 `data/`
2. **緊急發文冒煙測**：每段開工前三分鐘，開操控室 → 看得到成品 → 排程 → 確認 WF10 讀得到
3. **後備路徑**：`docs/finals/` 成品可直接下載用 IG App 手動發。這是唯一不經過任何一層的路徑
4. **不重寫 git 歷史**。`.git` 222MB，`filter-repo` 會讓 CAS 的 sha 全失效、Pages 重建、備份消失。「停止增長」和「變小」是兩件事，只做前者

---

## 四、砍掉的清單

| 項目 | 理由 |
|---|---|
| `liveness.py` 七條斷言 | 第二個要維護的規則庫，會像 `_HOLLOW` regex 一樣誤報後被關掉。其中「n8n workflow 停擺」根本寫不出來 |
| 三軸狀態 stage/activity/gates | 四處要同時對齊，任一處漏改就是靜默失敗。它的失敗模式和它要解決的問題是同一個 |
| L2 pytest 8 條劇本 | `sync_console.py` 1513 行零依賴注入，要 monkeypatch 整層。過去 6 次事故沒有一次是狀態機邏輯錯，全部是外部環境 |
| `docs/store.js` 抽離 | `saveJson` 已是單一入口，mutateFn 已是純函式。抽出來不會更純 |
| `data/posts/<id>.json` 拆檔 + derived | 為已修好的問題永久維護兩份真相。且 derived 由哨兵產生，Mac 睡著時 WF10 讀到舊檔，會製造「排程了沒發」和「取消了還是發了」兩種相反事故 |
| `config/roles/` + `model-routes.yaml` + `call_role.py` + `api_costs.jsonl` + `max_input_tokens` | 為每月 $15 蓋路由層。角色檔已經是 `config/self-check.md`、`visual-rules.md`。成本看 Anthropic Console 用量頁，一個月一次 |
| 開閘 `keep >= 2` → 5、`MIN_SCORE` 改標記 | 供給沒有不足，且那是單輪 per-slide 上限，改動是乘法效果。同時會對 n8n WF14 加壓，而 n8n 有 0723 自動停用 WF01/WF02 的前科 |
| 兩段式策展、golden image 像素回歸、桌面三欄骨架、contact sheet、`1-9`/`C`/`X`/`G` 熱鍵 | 效益不存在或為不存在的規模設計 |
| 副駕會議室 + FastAPI 常駐後端 | **門關死，不是排最後**。維護成本永久，收益是不用切視窗。而 Jesse 已經在 Claude Code 做同一件事，且工具存取更好 |
| 戰情室 | 成效資料 10 篇裡 5 篇 media_id 缺失。基於 2 個樣本的洞察比沒有洞察危險 |
| 日曆 / 看板 / 拆檔 / React | 觸發式，不排期。觸發條件：posts.json > 2MB 或 > 100 篇；面板數 > 4 |

---

## 五、要 Jesse 決策的五題

**Q1｜今晚 21:00 那篇怎麼辦？**
建議：先跑 `post-qa --post-id`，過了才發，沒過推遲一天。20 分鐘的事，`qa` 目前是 `None`。

**Q2｜副駕會議室，關死還是留門？**
建議：**關死**。留在 Claude Code 談，產出用現有 skill 落檔。操控室維持純靜態，永遠打得開。這同時砍掉 API key 管理、session 管理、task_budget 閘門四件永久維護。

**Q3｜撰稿今天切 Opus 5 開 A/B 嗎？**
建議：**今天就切**。每篇 +$0.046，`writer_model` 欄位現成。這是全線唯一決定「貼文會不會紅」的環節，也是信心不足的真正來源。需要 8 到 10 篇才看得出差異，晚一週就晚一週有答案。

**Q4｜手機版還要不要維護？**
批評一提了一個好問題：git log 的操作時段（13:06、14:32、20:45、21:47）偏桌機。
建議：**桌面優先，手機降級為唯讀查看**。同時維護兩套佈局是段 3 最大的隱性成本，而選圖這件事在手機上本來就做不好。

**Q5｜產能目標？**
建議：**現在不定**。等段 2 量出每篇分鐘數再回推。在那之前先把單篇成本砍半（現在每 3 天 1 篇，佇列躺了 9 天，瓶頸是你不是產線）。若一定要一個數：維持 2 到 3 篇/週到 9 月。

---

## 六、第一步（下一個工作段就能開始）

按順序，前四項在同一個 commit 前完成，總計約 90 分鐘：

1. `scripts/auto_render.sh:57` `git checkout --theirs -- .` → `git checkout HEAD -- .`，刪掉無效的 `git checkout -- data/`
2. 同檔的兩處 `git add -A` → `git add data/ docs/finals/ assets/`
3. `scripts/sync_console.py` 的 `save()`：加三條寫入守門（published 不得減少、不得新增已過期 scheduled、不得含衝突標記）＋ `os.replace()` 原子寫
4. 在 repo 的 clone 副本上人工製造一次 stash 衝突，確認修法有效再 push

接著（不必等上面 review）：

5. 開 n8n WF10，抄下 filter 表達式、去重來源、當月執行數
6. `post-qa --post-id 20260803-欸你有沒有發現歐美正在流`，決定今晚發不發
7. 開 @lava_dating，對照 5 篇缺 media_id 的實際狀態

---

## 七、這份計劃最弱的三環

1. **我還是沒打開 n8n。** WF10 的去重若真的靠 n8n static data（`HANDOFF.md:218,224`），那 archived 那兩篇過期 scheduled 的重貼風險是真的，而 static data 在 workflow 重匯入時會清空。這條沒驗證前，任何碰 posts.json 結構的動作都不該做。段 1 第 4 項就是為了關掉這個盲點。

2. **每篇分鐘數仍然是零。** 段 3 全部建立在段 2 那一次錄影上。如果錄出來發現瓶頸是「4 張候選裡只有 1 張能用」而不是「翻頁太慢」，那我對供給端的裁決要翻，`MIN_SCORE` 就該動。**我現在的判斷是憑候選數量推的，不是憑可用率。**

3. **`git checkout HEAD -- .` 我驗證了症狀，沒驗證修法在真實 repo 的完整行為**（stash 是否保留、後續 commit 內容是否乾淨）。所以段 1 第 4 項寫成獨立驗收，不是順手做完就算。

**關鍵檔案**
- `/Users/mimo/Claude/貼文製造機器人/lava-ig-console/scripts/auto_render.sh`（:55-65 stash 復原反向，:100+ `git add -A` 過寬，:86 post-qa 觸發條件）
- `/Users/mimo/Claude/貼文製造機器人/lava-ig-console/scripts/sync_console.py`（:128 `save()` 非原子、:1160 `alert` 無 token 靜默 return、:1275 `except` 吞掉 EDEADLK、:318-341 reconcile 只看 ClickUp）
- `/Users/mimo/Claude/貼文製造機器人/lava-ig-console/scripts/forage_shots.py`（:646 `MIN_SCORE`、:651 `keep >= 2` 是單輪 per-slide 上限、:27 CURATOR_URL 打 n8n）
- `/Users/mimo/Claude/貼文製造機器人/lava-ig-console/docs/app.js`（:57-85 CAS 正確、:91-98 setImg 走 GitHub blob、:303 CTA 無候選是設計、:509 排程按鈕前置、:522 取消排程降級無回程）
- `/Users/mimo/Claude/貼文製造機器人/lava-ig-console/data/archived-posts.json`（兩篇過期 `scheduled`：weak-ties、已讀不回-v5）
- `/Users/mimo/Claude/貼文製造機器人/排版引擎/render_post_v5.py`（不在版控）