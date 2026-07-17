# Lava IG 中介操控室 — 交接文件 (HANDOFF)

> 給下一個 context window / 下一位維護者。讀完這份就能接手，不需回溯對話。
> 最後更新：2026-07-17 · 維護者：Claude (為 Jesse / jesse@lava.tw)

---

## 0. 30 秒定位

**這是什麼**：Lava（台灣線下交友 App）的 IG 貼文半自動生產線。從「每日選題 → GPT 撰稿 → Claude 審查 → 生圖 → 人工過稿（操控室）→ 套版成品 → 歸檔 Drive → （待接）IG 自動發佈」一條龍。

**現在狀態**：主管線 **已上線運作**。操控室（審核台）live、10 支 n8n workflow 全 active、排程每日 3 次自動渲染+歸檔+留言。唯一未完成 = **IG 自動發佈串接**（卡在 Jesse 尚未備妥 Meta/IG 商業帳號，非技術問題）。

**一句話架構**：**repo 當資料庫**。操控室是純前端（GitHub Pages），讀寫同一個 repo 的 `data/*.json`；n8n 輪詢這些 JSON 與 ClickUp 卡片互相寫回；本機 Python 負責雲端跑不了的渲染。

---

## 1. 資料流（管線全貌）

```
每日選題雷達(05) ──→ ClickUp 靈感卡(選題待定)
                          │  PT 勾 🚀放行 checkbox
                          ▼
              放行監聽(07) ──→ 觸發 撰稿與審查(01)
                          │   GPT-5.6 撰稿 → Claude 審查 → 未過重寫一輪
                          │   同一張卡改名「IG貼文｜」+ 狀態→待過稿
                          ▼
                  生圖 Higgsfield(02) ──→ 底圖存 Drive 產出/<日期主題>底圖/
                          │
                          ▼
   排程 feed(11/16/20點) Part A ──→ from-drive ──→ 操控室 posts.json（候選底圖+文案）
                          │
                          ▼
              ┌─── 操控室 審核台（人工）───────────────┐
              │ · 選候選底圖 → IG Mockup 預覽            │
              │ · 編輯文案（heading/display_copy）→ 存    │
              │ · 核准 / 退回底圖 / 退回排版 → reviews.json│
              └───────────────────┬────────────────────┘
                                  │
        審核回寫(09, 每2分) ───────┼───→ ClickUp：核准→待排版 / 退回→退回重生 + 留言
                                  │
   排程 feed Part B（待排版）──────┘
        render_and_archive.py ──→ 成品 4:5 → 本機 成品/ + Drive 產文系統/成品/<id>/
                          │   attach 回操控室 + ClickUp 留言 @Jesse
                          ▼
                  ( 待接 ) IG 自動發佈 ── PT 排時間 → 到點自動貼文
```

**旁支**：
- **素材入庫(08)**：卡片勾 📥入素材庫 → 該篇底圖複製進 Drive 黃金參考（人工精選庫）。
- **迭代 harness**（`iterate_harness.py`）：吸收操控室的審核回饋 + **文案編輯語氣** → 增修 `config/style-notes.md`（風格增補層），版本化 commit。

---

## 2. 元件清單（含所有 ID）

### GitHub（repo 當資料庫）
| 項目 | 值 |
|---|---|
| Repo | `MuxiLiu512/lava-ig-console` |
| 操控室 live | https://muxiliu512.github.io/lava-ig-console/ |
| 生產首頁 live | https://muxiliu512.github.io/lava-ig-console/home.html |
| Pages source | `/docs`（**注意：Pages 服務時會 strip `/docs`，網址不帶 /docs**） |
| PAT 存放 | `.sync.json`（git-ignored）或操控室 ⚙︎ localStorage — **絕不貼進對話/commit** |
| commit 身分 | `git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512` |

### n8n Cloud（MCP server id：`f85f4517-31e5-45ac-9fea-880b696c9631`）
| # | 名稱 | Workflow ID | 觸發 | 備註 |
|---|---|---|---|---|
| 01 | 撰稿與審查 | `v3HTRGmvWDa7JndZ` | 被 07 呼叫 | **GPT-5.6 撰稿+重寫**（cred `73DXO5CKwdhD1NhX`，無 temperature）；Claude 審查 |
| 02 | 生圖 Higgsfield | `xoyAcXqUOF0OGXiv` | 被 01 呼叫 | 每 slide 生圖 → Drive |
| 03 | 過稿迴路 | `Dvs18yDdtTkPq96P` | ClickUp「決定」 | 舊迴路，含防迴圈 |
| 04 | 素材搬運工 | `WxEcQ6qmFR04i7Vb` | URL→Drive | |
| 05 | 選題雷達 | `UPClEV6bFGAG2aFr` | 每日 | 產靈感卡 |
| 06 | 素材搜尋 v3 | `PD79ZwJkneQDCUxI` | | 劇照+slide 標示 |
| 07 | 靈感卡放行監聽 | `eeNh3PGpbAqAwoYY` | taskUpdated | 讀 checkbox **🚀放行 = `b0deb388`** → 觸發 01 |
| 08 | 素材入庫 | `kHWvSfP5ZiGTLLtW` | taskUpdated | 讀 checkbox **📥入素材庫 = `10217a70`** → 複製底圖進黃金參考 |
| 09 | 操控室審核回寫 | `NKwZ8LtzXOMg3u1z` | 每 2 分 | 讀 reviews.json → ClickUp 改狀態+留言（static-data dedup）|

全部 `active: true`。改 workflow 用 `update_workflow` 原子操作（addNode/setNodeParameter…），不要整包重建。

### Google Drive（owner `service@lava.tw`，本機掛載自動同步雲端）
| 資料夾 | ID / 路徑 |
|---|---|
| Lava INC. Assets（根，預設存放） | `1R7d8eOUbZmreHsMpF6L4ZkKNza0ZSsTM` |
| 產出（底圖/文案來源） | 本機 `…/Lava INC. Assets/02_Marketing/98_Lava-IG-AI產文系統/產出`（= `DRIVE_PRODUCE`）|
| 成品歸檔 | `產文系統/成品/<post-id>/`（render_and_archive 自動建）|
| 黃金參考（素材庫） | `1uNPzvgSfvuH92BzrzEOSlJIRMGto2JVZ`（人工精選，08 寫入）|

### ClickUp
| 項目 | 值 |
|---|---|
| Jesse member id | `113529526`（留言 @ 用）|
| checkbox 🚀放行 | `b0deb388` |
| checkbox 📥入素材庫 | `10217a70` |
| 狀態機 | 選題待定 → 生成中 → 待過稿 → 退回重生 → 待排版 → 已排程 → 已發布 |
| 一卡到底原則 | **一張卡從靈感走到發佈**，不再開新卡。01 改名+改狀態沿用同卡。|

### 排程（本機 Claude Code scheduled task）
| taskId | cron | 做什麼 |
|---|---|---|
| `lava-ig-console-feed` | `0 11,16,20 * * *` | **Part A** 待過稿/待排版 feed 進操控室（from-drive）；**Part B** 待排版 → render_and_archive → Drive 歸檔 → attach 回操控室 → ClickUp 留言 @Jesse |

> 為何要本機排程：n8n Cloud 跑不了本機 Python 渲染引擎（Pillow）。這支排程補上「雲端做不到的最後一哩」。

---

## 3. 本機路徑 & 常用指令

```
專案根：/Users/mimo/Desktop/Claude/貼文製造機器人/
├── lava-ig-console/            # 操控室 repo（= 資料庫）
│   ├── docs/                   # 前端（app.js/index.html/home.html）→ Pages
│   ├── data/*.json             # posts / reviews / metrics / proposals / versions / copy_edits
│   ├── config/style-notes.md   # 風格增補層（harness 可改；正本在 Drive 不動）
│   ├── scripts/sync_console.py # 主同步 CLI
│   ├── scripts/iterate_harness.py # 迭代/吸收語氣
│   ├── guides/IG-自動發佈-設定教學.md
│   └── HANDOFF.md              # ← 你在讀這份
├── 排版引擎/
│   ├── render_post_v5.py       # Pillow 渲染，4:5 = 1950×2438，上下 padding 已加
│   ├── render_and_archive.py   # 渲染 → 本機成品/ + Drive 歸檔
│   └── 成品/<post-id>/
└── 操控室-PLAN.md              # 原始需求規格
```

**常用指令**（都在 `lava-ig-console/`）：
```bash
# 把某篇從 Drive 餵進操控室（含候選底圖+文案+finals）
python3 scripts/sync_console.py from-drive --topic <關鍵字> --clickup <taskId> \
  --post-id <日期-主題> --finals-dir "../排版引擎/成品/<日期-主題>"

# 取未處理審核 / 標記已處理 / 改狀態
python3 scripts/sync_console.py pull-reviews
python3 scripts/sync_console.py apply-reviews      # 核准→待排版, 退回→退回重生（寫回 ClickUp）
python3 scripts/sync_console.py set-status --post-id <id> --status 待排版

# 渲染成品 + 歸檔 Drive
python3 ../排版引擎/render_and_archive.py <文案.json> <底圖資料夾> <post-id>

# 迭代（吸收審核回饋 + 文案語氣）→ 改 style-notes，版本化
python3 scripts/iterate_harness.py            # 加 --dry-run 先試

# 語法檢查（改完必跑）
node --check docs/app.js
python3 -m py_compile scripts/sync_console.py scripts/iterate_harness.py
```

**PAT 寫法**（Jesse 已加入）：`.sync.json`（git-ignored）
```json
{ "github_token": "github_pat_xxx", "clickup_token": "pk_xxx" }
```

---

## 4. 五項需求進度（2026-07-16 Jesse 指定）

| # | 需求 | 狀態 |
|---|---|---|
| 1 | 文案改用 **ChatGPT 5.6** 撰寫 | ✅ workflow 01 已換 GPT-5.6，draftOk 驗證通過 |
| 2 | 操控室加**文案編輯** + **吸收語氣** | ✅ 本輪完成並測試（見 §5）|
| 3 | 成品輸出何處 + 歸檔 Drive | ✅ 本機 `成品/<id>/` + Drive `產文系統/成品/<id>/`，render_and_archive 自動 |
| 4 | **IG 自動發佈**（PT 排時間→到點自動貼） | ⏳ **教學已寫**（`guides/IG-自動發佈-設定教學.md`）；**串接待 Jesse 備妥 Meta 資產**（見 §6）|
| 5 | 4:5 成品上下 **padding 舒服**（logo/bottom bar 不裁） | ✅ render_post_v5：logo margin `H*0.052`、footer `H*0.052`、content anchor `H*0.10` |

---

## 5. 本輪完成 & 測試結果（#2 文案編輯 + 吸收語氣）

**改了 4 處**：
1. `scripts/sync_console.py` — `_build_and_write` 與 `from_drive` 都把 slide 的 `heading`/`display_copy` 帶進 posts.json（供操控室編輯）。
2. `docs/app.js` — STATE/FILES 加 `copy_edits`；審核頁 mockup 後加 `buildCopyEditor(p)`，逐 slide 可編輯 heading/display_copy，存回 `data/copy_edits.json`（append `{post_id, ts, consumed:false, edits:[...]}`）。
3. `data/copy_edits.json` — 新建 `{"edits": []}`。
4. `scripts/iterate_harness.py` — 新增 step 5：讀 copy_edits 未 consumed 的編輯 → 把 Jesse 改後句子當「語氣範例」append 進 `config/style-notes.md` → 版本化 commit（cfg-NNN）→ 標記 consumed。summary 加 `copy_absorbed`。

**測試（本輪實跑，已還原乾淨）**：
- ✅ `node --check` + `py_compile` 全過。
- ✅ from-drive 重跑，posts.json weak-ties slide1 帶入 heading/display_copy/final_src。
- ✅ 注入一筆測試 copy_edit → 跑 harness → `copy_absorbed: 1`、style-notes 新增 1 行語氣範例、copy_edits `consumed: true` → `git reset --hard` 還原。
- ✅ commit `2576ed7` 已 push main。

**系統健康檢查（本輪）**：
- ✅ 操控室 home.html / index 皆 200；posts.json 帶文案；copy_edits.json 200。
- ✅ 10 支 n8n workflow 全 active。
- ✅ 排程 lava-ig-console-feed enabled，下次 2026-07-17 11:01（台灣）。

---

## 6. 待辦 / 卡關（給下一個 window 接手點）

### #4 IG 自動發佈 — 進行中（2026-07-17 更新）
教學已備：`guides/IG-自動發佈-設定教學.md`。**已決定走 Instagram API with Facebook Login 路徑**（因需 insights 回拉「成效」分頁）。

**已確認的固定值（非機密，可直接用）**：
| 項目 | 值 |
|---|---|
| Meta App（lava inc.-IG）App ID | `917196600877456`（IG 產品編號另有 `894283759842674`）|
| 企業管理平台 | half_waystudio，business_id `603190274427730`（Lava 資產在此）|
| **IG Business Account ID（發文目標）** | `17841474839208540` |
| App 管理員 | 楊子義（= Jesse 的 FB） |
| 需要的權限 | `instagram_basic` `instagram_content_publish` `instagram_manage_insights` `pages_show_list` `pages_read_engagement` `business_management` |

**已完成（2026-07-17 全部打通）**：app 建好、6 權限授權、換到**不過期粉專 token** 存進 n8n credential、n8n 實測發文 token 有效。
- n8n credential：**`t44CUVrw6Bxkz6Do`**（type `httpQueryAuth`，name「Query Auth account」，query 參數名必須是 `access_token`）——**token 只在此，不在 chat/repo**。
- 驗證 workflow：`Lava IG｜Token 測試`（`1QPt4MakN5VCFwkt`，一次性，可留作 token 健康檢查）。實測 `GET /17841474839208540?fields=username` → 回 `{"username":"lava_dating"}`。
- 踩雷：Query Auth 參數名一開始掛錯 → FB 回 `(#200) Provide valid app ID`（= 沒收到 token 參數，非 token 壞）；把 Name 改成 `access_token` 即通。

**3 塊已完成並實測（2026-07-17）**：
1. ✅ **圖片公開 URL**：`sync_console._publish_final` 把成品降到 1350 長邊 JPEG 存 `docs/finals/<pid>/slide-N.jpg`，Pages 公開成 `https://muxiliu512.github.io/lava-ig-console/finals/<pid>/slide-N.jpg`（pid 的中文用 percent-encode）。posts.json 每 slide 多一個 `public_url`。`push` 已含 `docs/finals`。**實測 IG 能抓此圖建容器成功**。
2. ✅ **操控室排程 UI**：`app.js buildScheduler(p)`——貼文有 `public_url`（＝出過成品）才顯示 datetime picker →「排程發佈」寫 posts.json `publish_at`(＋08:00)＋`status:"scheduled"`；佇列多「📅 已排程」分組可取消/改期。`sync_console._build_and_write` 加保護：重餵不洗掉已 scheduled 的排程。
3. ✅ **workflow 10 IG 自動發佈**：**`56znLZUEHamJVJjJ`（目前 inactive）**。每 5 分讀 posts.json raw → `Pick Due Slides`（status=scheduled & publish_at<=now，static-data `published`/`attempting` 去重）fan 出 slides → `Create Item Container`(逐張) → `Collect Children` → `Create Carousel` → `Publish Carousel`(media_publish) → `Mark Published`(寫 static data) → ClickUp `Card 已發布` + `Notify Jesse`。cred：Graph API 用 `t44CUVrw6Bxkz6Do`、ClickUp 用 `Dx6ZhUm7eiha59p3`。

**✅ 首發成功（2026-07-17）**：weak-ties 六張輪播已真實發佈到 @lava_dating（**media_id `18170712478446850`**）。workflow 10 全鏈路（讀排程→建容器→組輪播→media_publish→ClickUp 已發布→留言）跑通。posts.json 該篇已手動標 `status:"published"`＋media_id（防重貼）。
**要開全自動**：n8n 把 workflow 10 **設為 active** 即可——之後 PT 在操控室排程任何貼文，到點就自動發（static-data 去重在 production 執行會持久化，不會重貼）。
**token 教訓**：粉專 token 必須從「**已延長的長效 user token**」去 `me/accounts` 取，偵錯工具驗到期日＝**永不**才對；短效 user token 直接存會幾小時後過期（code 190）。
**發佈回寫（已補）**：自動發佈後 posts.json 不會被 n8n 直接翻 published（無 GitHub PAT），改由**本機 feed 排程 Part C 對帳**：`clickup_get_task` 查排程貼文卡片，狀態＝已發佈 → `sync_console set-status <id> published` → push。防重貼另有 workflow 10 的 static-data（production 執行持久化）。sync_console 亦有 `reconcile-published` 命令（同邏輯，但需 .sync.json 有**真的** clickup_token）。

**巡查發現並修正的 bug（2026-07-17）**：
1. **ClickUp 狀態字不符**：workflow 10 原送「已發**布**」，但 ClickUp 實際狀態是「已發**佈**」（佈）→ 卡片狀態更新靜默失敗（onError:continue 吞掉）。已改 workflow 10 送「已發佈」。**狀態名雷區**：發佈用「已發佈」(佈)、排程狀態叫「已排程**.**」(含句點)。
2. **操控室對已發佈貼文仍顯示改期 UI** → 已修（published 顯示「✅ 已發佈」不再給 picker）。
3. **重餵防洗只保護 scheduled** → 已擴及 published（連 publish_at/published_at/media_id 一起保）。
4. **`.sync.json` 的 `clickup_token` 是 placeholder**（值含中文「…個人…供回寫卡片狀態」非真 token）→ 本機 `apply-reviews`/`reconcile-published` 用它會失敗。已加防呆（非 ASCII 就略過）。**真正的 ClickUp 寫回是靠 n8n OAuth（workflow 09/10）与 feed 排程的 ClickUp MCP，不靠這把 token**，故不影響線上。若要用本機 ClickUp 命令，需在 .sync.json 換成真的 ClickUp API token。

測試工具 `1QPt4MakN5VCFwkt`（手動/不發佈，留作「token＋抓圖」健康檢查，或刪）。App Review 自家帳號免。

**Jesse 最後回覆「還沒，需要協助設定」** → 下一步是**陪 Jesse 走完 Meta 設定**，拿到：
- IG Business account id
- FB Page id
- Meta app id/secret
- long-lived access token（存 n8n credential，**不進 chat/repo**）

拿到後**串接工作**（技術面已想清楚）：
1. 新 n8n workflow「10 IG 自動發佈」：schedule 輪詢 → 讀操控室 posts.json 中 `status=已排程` 且 `publish_at <= now` 的貼文。
2. 6 張輪播：先 `POST /{ig-id}/media`（每張 `is_carousel_item=true`，圖片需公開 URL — 用 Drive 直鏈或 raw）→ 再 `POST /{ig-id}/media`（`media_type=CAROUSEL` + children）→ `POST /{ig-id}/media_publish`。
3. caption 用 `_assemble_caption`（sync_console 已有）。
4. 發佈後改狀態 → 已發布，ClickUp 留言 @Jesse。
5. **guardrail 已解除**：Jesse 明確要「自動發佈」，原「不自動發布」限制對 #4 作廢。仍建議首篇人工確認。

> ⚠️ 操控室需先能設「排程發佈時間」（`publish_at` 欄位 + status `已排程`）。目前 posts.json/操控室尚未有這個 UI，串接前要補：app.js 加排程時間 picker → 寫 posts.json `publish_at` + status。這是 #4 的**第一個實作步驟**。

### 其他可優化（非阻塞）
- render_and_archive 目前靠排程觸發；若要「核准即渲染」可再收斂（Jesse 曾問全自動，已用排程滿足）。
- Console↔home 導覽、素材入庫、退回底圖只重生被退 slide — 皆已完成，若回報問題從對應 workflow/JS 查。

---

## 7. Guardrails（務必遵守）

- **不改 Drive 風格正本**：`style-notes.md` 是增補層可改；Drive 上的 v1.0/v1.1 規格 Doc 是正本，機器不碰。
- **不刪本機檔案**：除非 Jesse 明確授權（如先前刪 8+13 個測試檔）。
- **Token 絕不進 chat / commit**：PAT/ClickUp/IG token 一律 `.sync.json` 或 n8n credential 或操控室 localStorage。
- **高風險 config 改動需 Jesse 核准**；低風險（如吸收語氣）可自動並版本化。
- **一卡到底**：不要為同一篇貼文開多張 ClickUp 卡。
- **commit 身分**：`git -c user.email=jesse@lava.tw -c user.name=MuxiLiu512`（＋依系統要求補 `Co-Authored-By: Claude` trailer）。
- **可用工具是 deferred**：n8n / ClickUp / scheduled-tasks / Drive MCP 工具需先 `ToolSearch` 載入 schema 再呼叫。

---

## 8. 一分鐘健康檢查（接手先跑這段）

```bash
# 操控室 live + 資料層
curl -s -o /dev/null -w "%{http_code}\n" https://muxiliu512.github.io/lava-ig-console/home.html   # 期望 200
curl -s https://raw.githubusercontent.com/MuxiLiu512/lava-ig-console/main/data/posts.json | python3 -c "import sys,json;print('posts:',len(json.load(sys.stdin)['posts']))"

# 語法
cd lava-ig-console && node --check docs/app.js && python3 -m py_compile scripts/*.py && echo OK
```
n8n 用 `search_workflows(query:"Lava")` 確認全 active；排程用 `list_scheduled_tasks` 確認 `lava-ig-console-feed` enabled。

---
*若需更深脈絡：完整對話 transcript 在 `/Users/mimo/.claude/projects/-Users-mimo-Desktop-Claude--------/2ccb55fb-85a1-4969-9366-0bcc01f3d747.jsonl`*
