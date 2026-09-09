# Lava IG 中介操控室（Console）— 實作計畫 v1

> 給 Claude Code 執行的完整規格。閱讀完本檔後依「執行階段」順序實作。
> 撰於 2026-07-15。決策已由 Jesse 確認：部署走「靜態站＋GitHub repo 當資料庫」折衷；迭代 loop 用排程 harness 獨立跑、分級生效；必須有 iterate log 與版本回滾；每週六出成效＋迭代報告。

---

## 0. 背景（現況）

- 本地資料夾 ``：
  - `排版引擎/底圖/<主題>/slide-N.(png|jpg)` — 生成圖(png)與劇照(jpg)
  - `排版引擎/文案/<主題>.json` — 各 slide 文案＋visual_concept_en＋mood
  - `排版引擎/成品/<主題>/` — render_post.py 渲染後成品
  - `風格規格-v1.0.md` — 風格規格（Google Drive 上有版本化的規格 Doc，資料夾 ID `1pEEL61YW_YzW2vrujy_4lUFKLT6Y6DyB`）
- ClickUp 清單 `901819351278`：卡片狀態驅動生產（退回重生／待排版）。
- 每日排程 `lava-ig-daily-pipeline`（10:00）：讀規格 → 生圖（Higgsfield seedream_v4_5, 3:4）→ QC → n8n 上傳 Drive → 渲染。
- 既有 GitHub 推送模式可複製：`lava-live` repo 的 `scripts/push_json.sh` ＋ `.sync.json`（token 遮蔽、fetch+rebase 防撞）。

## 1. 目標

一個部署在 GitHub Pages 的操控室網頁，Jesse 在任何裝置上：

1. **審核**每則貼文：每個靈感（主題）的候選底圖並排比較、點選中意版本。
2. **IG Mockup 預覽**：成品圖嵌入模擬 IG 介面（carousel 滑動、帳號列、讚/留言列、caption），貼近真實觀感再 approve。
3. 每次 approve／退回都可附 **feedback 文字**（必填於退回、選填於 approve）。
4. **成效監測**：先手動輸入各貼文成效（觸及、讚、珍藏、分享、留言、追蹤增量），儀表板呈現趨勢；預留 IG Graph API 接口。
5. **迭代提案審批**：每日迭代 harness 產的高風險提案在此按 approve/reject。
6. **版本歷史**：檢視 iterate log、一鍵發起回滾到任一版本。

## 2. 架構

```
┌─ Mac 本地 ──────────────────────────────┐      ┌─ GitHub repo: lava-ig-console ─┐
│ 貼文製造機器人/（底圖、成品、文案）        │      │ /docs        ← GitHub Pages 前端│
│ 排程A lava-ig-daily-pipeline（生產）      │─推→ │ /data/posts.json    待審清單    │
│ 排程B lava-ig-iterate（迭代 harness）     │─推→ │ /data/reviews.json  審核結果 ←──┼─ 瀏覽器寫回
│ 排程C lava-ig-weekly-report（週六報告）   │      │ /data/metrics.json  成效        │  (GitHub API
│        ↑ 每次執行先 pull reviews/metrics  │←拉─ │ /data/proposals.json 迭代提案   │   + fine-grained
│ config/（prompt、規格、渲染設定，git 版本化）│      │ /data/iterate_log.json 迭代日誌 │   PAT)
└─────────────────────────────────────────┘      │ /assets/<主題>/…    縮圖        │
                                                  └────────────────────────────────┘
```

- **repo 私有**，Pages 用私有 Pages（GitHub Pro 支援）或公開 repo 但 assets 僅縮圖＋浮水印（由 Jesse 決定；預設私有）。
- **前端寫回**：瀏覽器直接呼叫 GitHub Contents API 更新 `data/*.json`。PAT 為 fine-grained、僅限此 repo、僅 contents:write，首次使用貼入、存 localStorage。所有寫入帶 retry（409 時 refetch sha 重試）。
- **本地是 source of truth 的生產端**；repo 是「審核與回饋的交換所」。排程每次執行先拉 reviews/proposals，再推新的 posts/assets。

## 3. 資料模型（`/data/`）

### posts.json（排程A產，前端唯讀）
```json
{ "posts": [ {
  "id": "20260715-已讀不回的心理學-v2",
  "topic": "已讀不回的心理學", "version": 2,
  "status": "awaiting_review",   // awaiting_review | approved | rejected | published
  "clickup_task_id": "…",
  "caption": "…IG caption 全文…",
  "slides": [ {
    "n": 1, "role": "cover",
    "candidates": [               // 同一 slide 的多張候選底圖
      { "cid": "a", "src": "assets/…/slide-1a.webp", "kind": "generated", "prompt_hash": "…" },
      { "cid": "b", "src": "assets/…/slide-1b.webp", "kind": "still" } ],
    "final_src": "assets/…/final/slide-1.webp"   // 渲染成品（供 mockup）
  } ]
} ] }
```

### reviews.json（前端寫，排程讀）
```json
{ "reviews": [ {
  "post_id": "…", "ts": "2026-07-15T21:03:00+08:00",
  "decision": "approve" | "reject",
  "slide_choices": { "1": "b", "2": "a" },       // 每 slide 選中的候選 cid
  "scope": "base_image" | "mockup",              // 退回的是底圖還是排版
  "feedback": "第2張手指又壞掉；封面光線太冷",
  "consumed": false                               // 排程處理後標 true
} ] }
```

### metrics.json（前端寫；未來排程接 IG API 後改為排程寫）
```json
{ "entries": [ { "post_id": "…", "published_at": "…", "day": "D1|D3|D7",
  "reach": 0, "likes": 0, "saves": 0, "shares": 0, "comments": 0, "follows": 0,
  "note": "" } ] }
```

### proposals.json（排程B寫，前端審批）
```json
{ "proposals": [ {
  "pid": "P-20260716-01", "risk": "high",
  "title": "封面光線配比改 暖:冷 = 7:3",
  "diff_summary": "config/style-notes.md §光線 …",
  "evidence": ["review R-…feedback", "metrics: 冷色封面 3 篇 reach 平均低 38%"],
  "status": "pending" | "approved" | "rejected", "decided_at": null } ] }
```

### iterate_log.json（排程B/C寫，前端唯讀＋可發起回滾）
```json
{ "versions": [ {
  "v": "cfg-014", "date": "2026-07-16", "commit": "abc1234",
  "risk": "low|high", "auto_applied": true,
  "changes": ["負面 prompt 追加 'deformed fingers'", "禁用詞 +2"],
  "trigger": { "reviews": ["R-…"], "metrics_window": "07/09–07/15" },
  "rollback_of": null } ],
  "rollback_requests": [ { "target_v": "cfg-011", "ts": "…", "consumed": false } ] }
```

## 4. config 版本化與回滾（關鍵需求）

- 新建本地 `貼文製造機器人/config/` 並 **git init**（或併入 console repo 的 `/config`，推薦後者：單一 repo、單一歷史）：
  - `gen-prompt-template.md` — 生圖 prompt 模板＋負面 prompt 清單
  - `style-notes.md` — 風格規格的「機器可改」增補層（正本規格 Doc 不動，符合現有護欄）
  - `render-config.json` — 渲染引擎參數（版型 v5 之上的可調項）
  - `banned-words.txt`、`qc-checklist.md`
- **每次迭代 = 一個 git commit**，message 格式 `cfg-NNN: <摘要> [risk:low|high] [auto|approved:P-xxx]`，同步寫 iterate_log.json。
- **回滾**：操控室版本頁按「回滾到 cfg-011」→ 寫入 `rollback_requests` → 排程B下次執行時 `git revert`（不是 reset，保留歷史）→ 產生新 entry `rollback_of: cfg-014`。任何時刻 `git log config/` 即完整審計軌跡。

## 5. 前端規格（`/docs`，純靜態，無框架依賴或用 Preact/htm 單檔）

單頁四分頁，手機優先（Jesse 會用手機審）：

1. **審核佇列**：卡片列出 awaiting_review 貼文 → 點入：
   - 底圖選擇：每 slide 的候選圖橫向並排、點選即標記 `slide_choices`；標示 kind（生成/劇照）。
   - **IG Mockup**：手機殼框內模擬 IG 貼文——頂欄（lava 頭像＋帳號名）、3:4 carousel（可滑、有頁點）、動作列、caption（前兩行＋「更多」展開）。純 CSS/JS，用 final_src 圖。
   - 底部三鍵：`Approve`／`退回底圖`／`退回排版`，退回強制填 feedback，approve 選填。寫入 reviews.json。
2. **成效**：貼文清單＋手動輸入表單（D1/D3/D7 快照）；儀表板：各貼文 reach/saves 長條、追蹤增量折線、依主題類型分組平均。之後接 IG Graph API 時此頁只讀。
3. **迭代提案**：pending proposals 卡片（title、evidence、diff 摘要）→ approve/reject 寫回。
4. **版本**：iterate_log 時間軸，每版列 changes/trigger/commit，附「回滾至此版」鍵。

寫回統一封裝 `saveJson(path, mutateFn)`：GET 取 sha → mutate → PUT，409 重試 3 次。

## 6. 排程任務改動

### 排程A：修改現有 `lava-ig-daily-pipeline`
在現有流程頭尾各加一段（不動中段生產邏輯）：
- **開頭**：pull console repo → 讀 `reviews.json` 未 consumed 條目 → 「退回底圖」的比照現行「退回重生」處理（feedback 併入 prompt 修正；只重生被退的 slide，尊重 slide_choices 已選定者）；「退回排版」的重跑渲染；「approve」的把成品 zip 標記可發布並在 ClickUp 留言。處理完標 consumed、更新 ClickUp 卡片狀態。讀 config/（取代散落在 prompt 裡的規則來源之一）。
- **結尾**：候選底圖與渲染成品轉 webp 縮圖（長邊 1080）推到 repo `/assets/<post-id>/`，組 `posts.json` 條目，push。

### 排程B：新增 `lava-ig-iterate`（每日 21:30，避開 pipeline）
1. Pull repo，收集：當日新 reviews（含 feedback 全文）、metrics 近 7 天、proposals 中剛 approved 的、rollback_requests。
2. **先執行回滾請求**（git revert → log entry）。
3. **套用已 approve 的提案**（改 config → commit → log entry，status→applied）。
4. 分析 feedback＋成效 → 產出改動，**分級**：
   - **低風險（自動生效）**：負面 prompt 追加、禁用詞增補、QC 檢查點新增、單一主題的 prompt 微調。直接改 config、commit、寫 log（auto_applied:true）。
   - **高風險（出提案）**：版型變動、光線/風格配比、文案語氣規則、任何影響全部貼文的規則。只寫 proposals.json，等操控室核准。
5. Push repo。輸出摘要：本日消化幾條 feedback、自動生效幾項、新提案幾項、是否有回滾。
6. 護欄：不動 Google Drive 規格正本；單日自動生效上限 3 項；同一設定 7 天內被回滾過則該類改動一律降為提案。

### 排程C：新增 `lava-ig-weekly-report`（每週六 10:00）
- 彙整本週（週日–週五）：發布貼文成效表＋WoW 對比、審核統計（approve 率、退回原因分類）、迭代 changelog（cfg-NNN 列表、哪些自動/哪些人工核准/有無回滾）、**迭代邏輯說明**（本週的改動各基於哪些 feedback 與數據，因果寫清楚）、下週建議實驗。
- 產出 `週報/YYYY-Wnn.md` 推 repo（操控室加「週報」入口讀取），同時存本地 `貼文製造機器人/週報/`。

## 7. 執行階段（Claude Code 依序做，每階段可獨立驗收）

**Phase 1 — Repo 與前端骨架**
建 `lava-ig-console` repo（私有）＋ Pages；建 `/data` 空 schema、`/config` 初始檔（從現有 pipeline prompt 與風格規格萃取）；實作四分頁前端＋saveJson 寫回；用 2 篇既有成品（已讀不回、星座）手工造 posts.json 假資料驗收 mockup 與審核流。
✅ 驗收：手機開 Pages 能滑 mockup、選底圖、送出 review 並在 repo 看到 commit。

**Phase 2 — 生產管線接軌**
寫 `scripts/sync_console.py`（本地）：縮圖轉檔、posts.json 組裝、push/pull 封裝（複用 push_json.sh 模式）。修改排程A prompt 加頭尾兩段。
✅ 驗收：跑一次 pipeline，新貼文自動出現在操控室；退回一張底圖，隔次執行只重生該張。

**Phase 3 — 迭代 harness**
建排程B（含分級規則、git revert 回滾、單日上限護欄）＋操控室提案/版本分頁串接。
✅ 驗收：造一條 feedback → 隔日 config 出現 commit＋log；發起回滾 → 產生 revert commit。

**Phase 4 — 成效與週報**
成效輸入表單＋儀表板；建排程C；預留 `scripts/ig_insights.py` 空殼（IG Graph API 接口，含所需權限註解）。
✅ 驗收：輸入兩篇假成效 → 週六手動觸發排程C → 週報出現在操控室。

## 8. 待 Jesse 提供／決定

1. GitHub：新 repo 建在哪個帳號/org；是否有 GitHub Pro（私有 Pages）。
2. Fine-grained PAT 一枚（僅 lava-ig-console、contents:read/write）。
3. 縮圖上公開 repo 是否可接受（若無 Pro）；不可則 repo 私有＋Pages 私有或改 Cloudflare Pages。
4. IG 帳號未來接 Graph API：需 IG 專業帳號綁 FB 粉專（Phase 4 之後才需要）。

## 9. 不做的事（護欄）

- 不自動發布貼文；不改 Drive 規格正本；不刪任何本地檔案；高風險設定不經核准不生效；PAT 不寫進 repo（只存瀏覽器 localStorage 與本地 .sync.json，git-ignored）。
