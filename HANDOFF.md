# Lava IG 中介操控室 — 交接文件 (HANDOFF)

> 給下一個 context window / 下一位維護者。讀完這份就能接手，不需回溯對話。
> 最後更新：2026-07-22 · 維護者：Claude (為 Jesse / jesse@lava.tw)

> 🔴 **接手最優先（2026-07-22 發現）：IG 發文 token 失效。** WF12 Token 哨兵實測 `GET /{ig-id}?fields=username` 回 **OAuthException code 190**（"...permission(s) must be granted before impersonating a user's page"）。這是 WF10 發佈＋WF11 成效共用的同一顆 token → **IG 自動發佈與成效拉取目前皆中斷**。需重新產生粉專長效（不過期）token，更新 n8n 憑證 **`t44CUVrw6Bxkz6Do`（Query Auth account）**。修好前，排程到點的貼文會發佈失敗（現在會自動告警，不再靜默）。

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
| 03 | 過稿迴路 | `Dvs18yDdtTkPq96P` | — | **已退休（inactive）**：審核移到操控室，舊 待排版/退回重生 迴路作廢 |
| 04 | 素材搬運工 | `WxEcQ6qmFR04i7Vb` | URL→Drive | |
| 05 | 選題雷達 | `UPClEV6bFGAG2aFr` | 每日 | 產靈感卡 |
| 06 | 素材搜尋 v3 | `PD79ZwJkneQDCUxI` | | 劇照+slide 標示 |
| 07 | 靈感卡放行監聽 | `eeNh3PGpbAqAwoYY` | taskUpdated | 讀 checkbox **🚀放行 = `b0deb388`**（guard 認 選題待定 或 靈感審核）→ 觸發 01 → 卡設 **在製中** |
| 08 | 素材入庫 | `kHWvSfP5ZiGTLLtW` | taskUpdated | 讀 checkbox **📥入素材庫 = `10217a70`** → 複製底圖進黃金參考 |
| 09 | 操控室審核回寫 | `NKwZ8LtzXOMg3u1z` | — | **已退休（inactive）**：approve/reject 不再改 ClickUp 狀態（卡留在 在製中）；渲染改由 feed Part B 觸發 |
| 11 | 成效拉取 | `OF2Obz1kkjbM9gjt` | manual（feed 呼叫）| 拉 IG insights → Assemble 輸出（去 token）|
| 01 | （撰稿）狀態 | `v3HTRGmvWDa7JndZ` | — | Open ClickUp Card 現設 **在製中**（原 待過稿）；onError continue |
| 10 | （發佈）狀態 | `56znLZUEHamJVJjJ` | — | Card 現設 **發佈完成**（原 已發佈）|

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
| 狀態機（2026-07-17 精簡為 4） | **靈感審核** →(🚀放行,WF07)→ **在製中** →(操控室排程)→ **已排程** →(WF10發佈)→ **發佈完成** |
| 分工 | ClickUp＝決策層（只有「靈感審核」需人工放行）；**操控室＝生產層**（選底圖/退回底圖或排版/改文案/設排程時間全在操控室，ClickUp 不反映這些細節）|
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
**✅ 已全自動（2026-07-17）**：workflow 10 **已 active**。PT 在操控室排程任何貼文，到點自動發。目前排程中：`20260718-你知道weak-ties` → 2026-07-18 17:00 台灣（weak-ties 用修好引擎重發；舊的 `20260716-你知道weak-ties` 已發佈的舊圖仍在 IG，需 Jesse 手動刪）。
**排版引擎已統一修復（render_post_v5.py，非 git-tracked，在 排版引擎/）**：(1) 內文改**底部錨定＋自動縮字**，保證不壓到 footer（原 `bar_y=max(0.44H,…)` clamp 會讓長文出血）；(2) `strip_trailing_punct` 句尾標點（含 ——、句點）逐行省略；cover 與 content 都套。已在 weak-ties/已讀不回 重render 目視確認。
**token 教訓**：粉專 token 必須從「**已延長的長效 user token**」去 `me/accounts` 取，偵錯工具驗到期日＝**永不**才對；短效 user token 直接存會幾小時後過期（code 190）。
**發佈回寫（已補）**：自動發佈後 posts.json 不會被 n8n 直接翻 published（無 GitHub PAT），改由**本機 feed 排程 Part C 對帳**：`clickup_get_task` 查排程貼文卡片，狀態＝已發佈 → `sync_console set-status <id> published` → push。防重貼另有 workflow 10 的 static-data（production 執行持久化）。sync_console 亦有 `reconcile-published` 命令（同邏輯，但需 .sync.json 有**真的** clickup_token）。

**巡查發現並修正的 bug（2026-07-17）**：
1. **ClickUp 狀態字不符**：workflow 10 原送「已發**布**」，但 ClickUp 實際狀態是「已發**佈**」（佈）→ 卡片狀態更新靜默失敗（onError:continue 吞掉）。已改 workflow 10 送「已發佈」。**狀態名雷區**：發佈用「已發佈」(佈)、排程狀態叫「已排程**.**」(含句點)。
2. **操控室對已發佈貼文仍顯示改期 UI** → 已修（published 顯示「✅ 已發佈」不再給 picker）。
3. **重餵防洗只保護 scheduled** → 已擴及 published（連 publish_at/published_at/media_id 一起保）。
4. **`.sync.json` 的 `clickup_token` 是 placeholder**（值含中文「…個人…供回寫卡片狀態」非真 token）→ 本機 `apply-reviews`/`reconcile-published` 用它會失敗。已加防呆（非 ASCII 就略過）。**真正的 ClickUp 寫回是靠 n8n OAuth（workflow 09/10）与 feed 排程的 ClickUp MCP，不靠這把 token**，故不影響線上。若要用本機 ClickUp 命令，需在 .sync.json 換成真的 ClickUp API token。

測試工具 `1QPt4MakN5VCFwkt`（手動/不發佈，留作「token＋抓圖／insights」健康檢查，或刪）。App Review 自家帳號免。

### 渲染管線 v2：render-approved（2026-07-17，Fable 5 重構）
**PT 在操控室選的圖從此真正生效**。單一指令 `python3 scripts/sync_console.py render-approved`（feed Part B 呼叫；`--dry-run` 可預演）：
1. 讀每篇**最新** review（approve／退回排版）＋文案編輯 → 冪等 gate：`rendered_at ≥ max(review ts, copy_edit ts)` 就跳過。
2. **圖源解析**：`data/.local_sources.json`（git-ignored；from-drive 時寫入 cid→原圖絕對路徑）；舊貼文無對照則復刻掃描重建並以 (cid,kind) 序列驗證，不符即拒渲染（絕不瞎猜）。
3. **選定圖檢查**：近純色破圖（`_flat_image`，stddev<8）攔下；intake 端 `_collect_slide_imgs` 也自動剔除破圖（prune）。
4. 文案：Drive 正本 JSON ＋ 操控室 copy_edits 最新值 → 渲染與 posts.json 同步反映。
5. 渲染 → Drive 歸檔 → from-drive 附回（finals＋public_url）→ `last_render_choices` 存檔（文案微調重渲染沿用同組圖）。
**狀態機防護**：候選圖序列變動 → `candidates_since` 戳記，未出成品的 approved **自動退回待審**（舊審核 cid 已失效）；scheduled/published 永不被重餵動到。
**測試**：`scripts/selftest.py` 14 項（句尾標點、破圖偵測、copy_edits 合併、topic 比對）全綠；實測 Pitch/已讀 用 PT 確切選圖渲染成功（視覺驗證 final-03=選定劇照）。
**佇列 UI**：待審核底圖 → ✅已核准（渲染中/待排程）→ 📅已排程；核准不再消失；底圖預覽有「文字渲染時合成」提示。

### 撰稿研究步驟＋封面版面防護（2026-07-17 晚，Fable 5）
- **WF01 新增「Research Topic (Claude+Web)」→「Parse Research」**（Extract Spec Text 之後、Write Draft 之前）：Claude sonnet-4-6 + `web_search_20250305`（Anthropic cred `9Cci7CUN8iYsJxEB`，直接打 api.anthropic.com，header `anthropic-version: 2023-06-01`）查證主題起源/具名人物/數據/在地化 → 筆記餵給 GPT 撰稿與重寫。研究失敗 onError continue（空筆記時囑咐不得捏造引用）。
- **撰稿 prompt 加密度規則**：display_copy 目標 **80–140 字**（原「上限140、寧可少」導致文字太少的風格退化）；具體人名/年份/地點/數據至少擇二；起源故事講清楚。
- **⚠️ 撰稿目前停擺：Jesse 的 OpenAI key（cred `73DXO5CKwdhD1NhX`）`insufficient_quota` 額度耗盡**（2026-07-17 中午 Pitch 那篇是最後一筆成功）。已測 n8n 免費 credits（`8rtJ704d7Zu06B7l`）：**不允許 gpt-5.6**（"Model not allowed with n8n AI credits"）。WF01 兩個 GPT 節點已還原掛 Jesse 的 key——**Jesse 到 platform.openai.com 儲值後即恢復**，屆時重觸發 Pitch 重寫（webhook lava-ig-draft，taskId 86ey8fn7j）。研究步驟不受影響（Claude 真 key 可直打）。實測研究輸出品質極高（起源/創辦人/城市數/Pew·SAGE 數據全帶出處）。
- **render_post_v5 封面版面防護**（原副標**完全沒換行**導致左右爆框）：副標逐行換行＋footer 安全區塞不下逐級縮字（0.032W→0.68×）；主標 >3 行自動縮字；eyebrow 過長縮字。content 頁先前已有底部錨定＋縮字。**版面安全規則現已全 slide 型別覆蓋**。
- render-approved 加 `--force`（忽略 rendered_at 閘門，引擎修復後重出成品）與 `--only <pid>`。

### 四項優化（2026-07-18，Jesse 對照 The Weekend Club 提出）
1. **遮罩/排版**（render_post_v5 v5.3）：MAX_ALPHA 216→198、封面全域壓暗 120→88＋overlay 205→190；段落間距減半（空行 0.55×行高）、內文行高 1.72→1.60 → 文字塊變矮、背景可辨識。`lines_height()` 同步高度計算。
2. **A/B 寫手**（WF01，30 節點）：Parse Research → **AB Router**（staticData 輪替 gpt-5.6 / claude-sonnet-4-6）→ Writer Is GPT? 分流 → Write Draft (GPT)/(Claude)；重寫同寫手（Rewrite With GPT? 分流）。`writer_model` 注入 draft JSON（Parse Draft/Parse Rewrite）→ posts.json → insights → harness 成效行帶「寫手 GPT/Claude」標籤。審查加第 8 條：**密度（80–140字）與擴散力檢核**。
3. **說明欄整潔**：`_clean_caption`（去【】〖〗、——→逗號、空白正規化、CJK 換行接合）；caption 改優先取 body（散文體）。selftest 18 項。
4. **人物志/書摘題材＋授權**：
   - WF05 選題加**題型 D 人物志/書摘**（每日至少 1 張，Weekend Club 風格；suggested_show 填「人物照片：人名」/「書封：書名」）。
   - WF06 加 **person/book 搜尋線**：Wikipedia pageimages（人物照，自由授權）＋ Open Library covers（書封）；檔名前綴 WM-/OL-。WF01 Build Stills Request 路由 photo_direction.type 人物照片優先/書封優先；兩寫手 schema 已更新。
   - **授權三層**：圖上 credit 小字（引擎 `draw_credit`，render-approved 依實選候選注入 `render_credit`：WM→Wikimedia Commons、OL→Open Library、劇照→《劇名》劇照）＋ posts.json `image_credits` ＋ **WF10 發佈後自動留言**（Build Credits Msg → POST /{media}/comments，token 同 cred）。
   - 已知：WF06 Giphy/TMDB API key 硬編碼（歷史遺留，warning 已標）；person 搜尋僅取 Wikipedia 主圖 1 張（保守授權策略）。

### 雙引擎選題＋雙寫手比稿（2026-07-18 第二輪，Jesse 需求）
- **WF05 雙選題引擎**：Topic Scout (Claude) ＋ Topic Scout (GPT) 平行選題（各 2-4 張/日），卡名帶 `｜🧠GPT/Claude`、內文有「選題來源」。兩 Parse 皆軟失敗（單引擎掛不影響另一個）。
- **WF07 放行 → 雙寫手**：連打兩次 lava-ig-draft webhook（writer=gpt / claude）。**WF01** Normalize 收 writer 參數強制指定；檔名 `-文案初稿-GPT.json`/`-Claude.json`（易讀版同）；**圖像搜尋只由 GPT 輪觸發**（Should Gen Images? gate + Build Stills Request 首行擋 claude，不重複生圖）。
- **操控室比稿**：from-drive 同日同主題雙檔 → post `copy_versions`{gpt,claude}（heading/display_copy/caption）＋ `.local_sources.draft_jsons`；文案編輯卡有「比稿版本 ✍️GPT/✍️Claude」切換；核准寫入 `copy_choice`（review＋posts.json）；**render-approved 依 copy_choice 取對應 JSON 渲染**，`writer_model` 以選定版計（A/B 成效以「被選中率＋發佈成效」雙指標裁決）。copy_edits 帶 version 欄，只套用到對應版本。
- **人物圖源擴充**：WF06 person 線 = Wikipedia 主圖 ＋ **Wikimedia Commons 檔案搜尋**（gsrlimit 8、取 jpg/png、去重、上限 count+1 張，皆 WM- 前綴＝自由授權標示）；book 線 Open Library 3 張。
- feed SKILL 4b：awaiting_review 的卡每輪冪等重餵（吃晚到的比稿版）。

### 成效追蹤（#4，2026-07-17 完成）
零新憑證架構：token 只在 n8n，不外流。
- **workflow 11 成效拉取**（`OF2Obz1kkjbM9gjt`，manual trigger）：GET IG media（近8天圖文/輪播）→ 逐篇 `/insights`（**period=lifetime**：reach, saved, shares, total_interactions, likes, comments, profile_visits, follows，全部實測可用）→ Assemble 輸出**乾淨陣列（不含 token）**。⚠️ 原始 media 回應的分頁 URL 夾 token，但 Assemble 不輸出它。
- **粉絲/非粉絲**：per-post `reach` 的 `follow_type` breakdown 在此 API 版本**不相容**（Meta 限制）→ 改用 profile_visits＋follows＋reach 當受眾轉換訊號。
- **本機 feed 排程 Part D**：`execute_workflow(11)`→`get_execution`(Assemble) → 寫 `data/insights.json`（每篇每日一 snapshot，同日覆蓋，留最近~10 筆；比對 media_id↔posts.json 補 post_id/topic）→ push。
- **操控室「成效」分頁**：頂部「📊 IG 自動成效」讀 insights.json（觸及/互動/互動率/讚留珍分/個檔瀏覽/追蹤+／觸及趨勢 sparkline）；下方保留手動輸入。
- **iterate_harness step 6**：insights 中 reach≥30 的貼文按互動率排序，≥3 篇時把高/低成效主題寫進 style-notes（拆解 hook/切角/情緒）供選題 looping。
- IG 剛發的貼文有**建索引延遲**（subcode 33，通常<1天），指標會延後出現；已建索引的貼文（如 7/11）即時可讀（實測 reach 408）。

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

## 6.5 維運強化（2026-07-22，Jesse「清單照做」七項）

**新增 n8n 工作流**
- **錯誤告警 `2z8gkB27paoSjT5K`**（Error Trigger → ClickUp 留言）。已掛為 **9 支 active 生產工作流的 errorWorkflow**（01/02/04/05/06/07/08/10/11）。任一失敗 → 在告警卡 **`86eyckbur`（🔧 Lava IG 系統告警日誌）** 自動留言 @Jesse（不污染內容看板）。
- **WF12 Token 哨兵 `NGJVZ1i1mL76YamA`**（每日 08:30 cron）→ `GET /{ig-id}?fields=username`；失敗即在 `86eyckbur` 告警。**實測已抓到 code 190 token 失效並成功告警**（見頂部紅字）。

**修 latent bug**
- **WF11 成效 `OF2Obz1kkjbM9gjt`**：原本只有 Manual Trigger → 無法 publish/execute via API，**feed Part D 一直靜默失敗**。已改 **Schedule Trigger（每日 10:00）**，可啟用可執行。⚠️ 但 token 失效時 Get Media 仍回 190（成效需 token 修好才有數據）。

**WF10 發佈守門**：Pick Due Slides 加 `!p.no_publish && !/demo/i.test(clickup_task_id)` — demo/測試卡與標記 no_publish 的貼文永不自動發佈。

**sync_console.py 新指令**
- `archive-post <ids...> [--note]`：把 demo/廢棄貼文移出 posts.json → `data/archived-posts.json`（不動 IG，只讓自動化不再碰）。
- `archive-data [--days 90]`：reviews/copy_edits 過期且已處理者搬 `data/archive/*.jsonl`；insights 每篇只留 N 天內快照。→ feed 【E】每日跑。
- `archive-drive-rounds <post_id>`：**發佈後**把該主題舊輪 Drive 產出搬 `產出/ZZ-歸檔/`（`_scan_dirs` 本就跳過 ZZ）。已發佈＝舊輪全歸檔留最新；在製中＝保護渲染來源。Drive 未掛載自動略過。→ feed 【C】發佈對帳後跑。

**已清掉的髒資料**（→ `data/archived-posts.json`，附 note）
- `20260712-已讀不回的心理學-v5`（demo-01，scheduled）：WF10 靜態資料顯示 **約 07-18 已自動發佈到 IG**，假 id 無法對帳。**Jesse 請到 IG 確認、若不需要手動典藏。**
- `20260711-母胎單身…`（demo-02，awaiting_review，未渲染）：測試殘留。
- `20260718-你知道weak-ties`（scheduled）：**與已發佈的 `20260716-你知道weak-ties` 同一 clickup id、同主題 → re-feed 重複卡**。歸檔避免 token 修復後重發相同內容。**Jesse 請確認 IG 是否已有兩則 weak-ties。**

**#3 完成（2026-07-22）**：Jesse 在 n8n UI 建了 2 個 httpQueryAuth 憑證 —— **Giphy Key `vPjtxajHhvqRvLDO`**、**TMDB Key `fKV5BFJaJ66IXrxN`**（Name 欄皆 `api_key`）。WF06 `PD79ZwJkneQDCUxI` 的 3 個節點（Giphy Search／TMDB Search／TMDB Scene Stills）已改 `genericCredentialType→httpQueryAuth` 綁憑證、query 內明文 api_key 全刪、已 publish。**Giphy 路徑目前不可達**（Build Stills Request 只發 tv/person/book，從不送 `source:giphy`）→ Giphy Key 憑證是「已備好但休眠」，未來若要做迷因梗圖題材，讓 WF01 Build Stills Request 對該題型送 `source:'giphy'` 即可啟用；不需要就留著無害，或刪 Giphy Search/Collect Giphy 兩節點＋該憑證。

**#7（公開 repo 可見未發佈內容）**：Jesse 拍板**接受現狀**，不處理。

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

## 9. 優化與擴充藍圖（2026-07-17 全面檢核＋業界對照後）

**已對齊業界最佳實踐**：兩段式 container→publish、發佈前 status_code=FINISHED 檢查（WF10 已加 Wait 12s→Check→Assert，未就緒中止、attempting 冷卻後自動重試）、JPEG-only＋4:5 驗證（公開 finals 即 JPEG）、HITL 審核台、品牌語氣學習（copy_edits→style-notes，多數市售工具沒有）、成效回饋迴路、git 原生審計軌跡。

**近期優化（低工／高值）**：
1. **失敗告警**：WF10/01 掛錯誤 errorWorkflow → ClickUp/LINE 通知（現在失敗只躺在 n8n executions）。
2. **429/暫時性錯誤退避**：發佈節點加 retryOnFail＋exponential backoff（現量 1-2 篇/日離 100 篇/24h 上限很遠，先低優）。
3. **容器輪詢升級**：單次檢查 → 迴圈輪詢至 FINISHED（影片/Reels 上線前必做）。
4. **資料可見性決策（Jesse 拍板）**：public repo 上 insights.json（商業數據）與**未發佈的排程內容**任何人可讀。選項：接受（風險低）／repo 轉 private＋Pages 付費／敏感資料改私有儲存。

**擴充路線（依 ROI 排序）**：
1. **最佳發文時段**：用累積 insights 的時段×互動率回歸，操控室排程器預設建議時段。
2. **重複主題防呆**：選題雷達比對歷史 posts（05 已有雛形可強化 embedding 比對）。
3. **Reels/影片**：管線天然支援（換 media_type＋輪詢），業界流量紅利區。
4. **A/B caption**：同圖兩版 caption 輪替發佈，insights 對照回饋撰稿。
5. **贏家重製**：高成效貼文自動進「repurpose 佇列」（改切角/改視覺重跑）。
6. **留言自動化**：IG webhooks（Meta app 已能訂）→ 常見問題自動回＋高意圖留言推 ClickUp。
7. **Threads 交叉發佈**：同素材一鍵雙發（Meta app 加 Threads API use case 即可）。

參考來源：[n8n IG Graph API 指南](https://www.keyapi.ai/blog/n8n-instagram-graph-api-node-guide/)、[IG Graph API 2026 開發指南](https://elfsight.com/blog/instagram-graph-api-complete-developer-guide-for-2026/)、[n8n IG 錯誤處理](https://www.weblineglobal.com/blog/fix-instagram-api-errors-n8n-workflows/)、[n8n 全內容型發佈模板](https://n8n.io/workflows/4498-schedule-and-publish-all-instagram-content-types-with-facebook-graph-api/)、[HITL agent 工作流設計](https://towardsdatascience.com/building-human-in-the-loop-agentic-workflows/)、[AI 社群 agent 架構](https://fast.io/resources/ai-agent-social-media-automation/)。

---
*若需更深脈絡：完整對話 transcript 在 `/Users/mimo/.claude/projects/-Users-mimo-Desktop-Claude--------/2ccb55fb-85a1-4969-9366-0bcc01f3d747.jsonl`*
