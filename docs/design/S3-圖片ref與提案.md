# 環節 3 升級設計：圖片 ref 搜尋 & 圖片提案

## 0. 先校正一個前提

任務書寫「vision 呼叫是主要成本」。**用實際數字算，不成立。**

[驗證] Anthropic vision 計價公式：`⌈寬/28⌉ × ⌈高/28⌉` visual tokens（https://platform.claude.com/docs/en/build-with-claude/vision.md）。現行 `_b64_small()` 送 512px 長邊縮圖，4:5 約 410×512 → `15×19 = 285` tokens/張。

[驗證] 實測 `data/quality_metrics.jsonl`（n=29 有候選的執行）：候選數中位 17、最大 64、總計 640 張；策展均分中位 3.65（滿分 10，分數線 5）。

| 情境 | image tokens | 一篇成本（Opus 5 $5/$25） |
|---|---|---|
| 中位 17 張候選 | 4,845 | $0.024 + 輸出 |
| 最大 64 張候選 | 18,240 | $0.091 + 輸出 |

真正的成本在別處。`forage_shots.py:477 curate()` **逐 slide 分批呼叫**，9 次呼叫每次重送完整策展 rubric（估 2,000 tokens）＝ 18,000 tokens 的純重複。圖片本身只佔約 25%。

**結論：控制 vision 成本的第一槓桿不是換模型，是「合併呼叫 + 快取 rubric」。** 詳見 §5。

---

## 1. 素材來源擴充

### 1.1 可立即接的（免費、有 API、授權明確）

| 來源 | 端點 | 費率 [驗證] | 授權 | 適合 role | 優先序 |
|---|---|---|---|---|---|
| **Pexels** | `https://api.pexels.com/v1/search` | 200 req/hr、20,000/月；提供合規標注可**免費解除上限** | Pexels License，可商用免署名 | mood | **P0** |
| **Unsplash** | `https://api.unsplash.com/search/photos` | demo 50 req/hr；production 審核後 **1,000 req/hr** | 須標注攝影師＋Unsplash；**必須 hotlink 官方 URL**、每次下載須打 `/download` 端點 | mood | **P0** |
| **Pixabay** | `https://pixabay.com/api/` | 100 req/60s；**強制快取 24h**；**禁止永久 hotlink** | Pixabay Content License，須標示來源 | mood | P1 |
| **Openverse** | `https://api.openverse.org/v1/images/` | **實測 header**：匿名 20/min burst、200/day sustained；OAuth2 註冊免費提高 | 逐張帶 `license` 欄位，可過濾 `by`/`cc0` | mood、evidence | **P0** |
| **Wikimedia Commons** | `https://commons.wikimedia.org/w/api.php` | **實測可用，免金鑰**，回傳 `extmetadata` 含逐張授權 | CC/PD，須顯名 | person（公眾人物本人照）、evidence | **P0** |
| **Flickr** | `https://www.flickr.com/services/api/` | 3,600 queries/hr | 需過濾 `license=4,5,9,10`（商用可） | mood、person | P1 |
| **Europe PMC / PMC OA** | `https://www.ebi.ac.uk/europepmc/webservices/rest/` | 免費無金鑰 | OA subset 分三群，只取 Commercial Use Allowed（CC0/BY/BY-SA/BY-ND） | evidence（論文圖表） | P1 |
| **觀光署觀光多媒體開放資料** | `https://media.taiwan.net.tw/` ＋ `data.gov.tw` | 免費 | 政府資料開放授權，須顯名 | mood（**台灣在地場景**） | **P0** |

**Unsplash 的合約陷阱**：Unsplash API Guidelines 要求「直接使用 API 回傳的圖片 URL 嵌入應用」。Lava 的流程是抓下來、裁切、壓字、上傳到 IG，**這在字面上違反 hotlink 條款**。Pexels 沒有這條，所以 Pexels 優先於 Unsplash。

### 1.2 圖搜引擎（取代／補強 DuckDuckGo 單點）

[驗證] Bing Search API 全系列（含 Image Search）已於 **2025-08-11 退役**。DDG `i.js` 是非公開端點，隨時可能改，這是現行架構最大的單點故障。

| 選項 | 費率 | 判斷 |
|---|---|---|
| Google Custom Search JSON API | 免費 100 query/day，超過 $5/1,000（上限 10k/day）；支援 `searchType=image` | **已對新客戶關閉，現有用戶須於 2027-01-01 前轉移**。不要新接 |
| Brave Search API | $5/1,000，含每月 $5 免費額度（約 1,000 次） | 官方定價頁未把 Image Search 列入 Search plan 功能表，**是否含圖片端點待查**（需實測金鑰） |
| SerpApi | 二手來源數字衝突：一說 free 250/月、$25/月 1,000 次；官方定價頁另列 $75/月 5,000 次。**以官方頁為準，待實測** | 最貴但最穩，作為 DDG 失效時的付費備援 |
| DuckDuckGo `i.js`（現況） | 免費 | 保留為第一順位，但**必須加降級鏈** |

**建議**：不換掉 DDG，改成 `DDG → Brave（若含圖搜） → SerpApi` 的降級鏈，並把「DDG 連續 3 次回空」寫進 `forage_learnings.json` 觸發告警。每月付費預算上限抓 $10。

### 1.3 影音平台影格

| 平台 | 可行性 |
|---|---|
| YouTube（現況） | 保留。`yt-dlp + ffmpeg` 抽影格，是 person role 的主力（實測 `source_mix` 中 `yt_frame` 39 張、`yt_thumb` 21 張） |
| **Vimeo** | 不建議。[驗證] oEmbed 對非公開影片已不回傳縮圖，且 Vimeo Developer Addendum 保留「額外註冊、驗證或核准」的權利。ROI 太低 |
| **TikTok** | 不建議。無公開影格 API，抓取違反 ToS，且 TikTok 內容本身極少符合 person/evidence 的畫質下限 |

### 1.4 社群內容（IG／Threads）

[驗證，二手來源] 2026-06-15 起 Meta 反轉決策，Instagram／Facebook／Threads 的 oEmbed 端點**可免 access token 呼叫，不再需要 App Review**，僅限公開內容（https://developers.facebook.com/docs/instagram-platform/oembed/）。

**但這對 Lava 沒用。** oEmbed 回傳的是 iframe 嵌入碼，不是可下載、可裁切、可壓字的圖檔。要拿到像素只能截圖，那就回到現有的 `grab_browser()` 路徑，法律位置也回到「引用式使用」。

**可行的用法只有一種**：`evidence` role 抓競品／對標帳號貼文截圖當「證據張」，自動標注來源帳號 handle。這是現況已支援的能力，不需要新接 API。

### 1.5 付費圖庫：不值得

[驗證] Adobe Stock / Shutterstock / iStock 年約 10 張/月方案均約 **$29-30/月**（約 $2.90/張）。

Lava 月成本現在是 $15 級距。加 $30 讓月成本翻倍，換來每月 10 張 mood 圖。而 mood role 佔實測 `source_mix` 的 **482/640 = 75%**，一個月需要的 mood 圖遠超 10 張。**單位經濟不划算，且 Pexels/Unsplash 的 mood 品質對 IG 尺寸已經夠用。**

唯一值得考慮的付費項是**當 Lava 有一次性的品牌視覺需求**（例如活動主視覺），那時買單張授權（約 $10-15/張）比訂閱划算。

### 1.6 電影電視劇照與新聞照：法遵紅線

| 來源 | 狀態 |
|---|---|
| **TMDB**（repo 已有金鑰，見任務 #3） | [驗證] 非商業免費，須標注 TMDB。**商業使用需授權，年營收 < $1M 為 $149/月**。Lava 是交友 App 的官方 IG，屬商業推廣。**用了就是無授權商業使用** |
| **Getty Images Embed** | [驗證] 免費 70M＋張，但僅限**編輯性、非商業**用途，且 iframe 不可裁切、不可改尺寸。排版引擎完全無法使用 |
| **AP / Reuters** | 企業授權，年費級距，不在討論範圍 |

**建議做法（對齊 Jesse「引用式使用＋出處標注，拒絕過度合規」）**：
1. TMDB **只用於 `evidence` role**（作品資訊卡截圖），不用於滿版 mood 底圖，並保留 TMDB 標注。理由：資訊性引用的合理使用主張比裝飾性使用強得多。
2. **禁止** 把劇照當滿版情緒底圖。這是最容易被 DMCA 的用法，且 IG 對重複侵權帳號會停權，風險與 200 追蹤的收益不成比例。
3. 劇照的替代方案：`mood` 用 Pexels/Unsplash 的真實攝影，或走環節 4 的生成路線。

---

## 2. 策展標準升級

### 2.1 現行問題定位

| 症狀 | 根因 |
|---|---|
| 同篇撞主體（四張同一本書封） | `apply_quota()` 只擋 `yt_thumb` 數量，**沒有任何主體層級的去重** |
| 候選品質參差（浮水印、離題） | 過濾全在**抓取端**（網域黑名單、畫質閘門），策展端只有一個 5 分線 |
| 分數不穩（同篇兩次判定不同） | 每 slide 獨立呼叫，模型看不到「整篇」，無法做相對排序 |

### 2.2 role 制升級為 role + subject_key + composition

現行 role（person／mood／evidence／book）保留，**新增兩個由 vision 產出、由 Python 執法的欄位**：

```json
{
  "cid": "is-a1b2c3",
  "role": "mood",
  "subject_key": "book:attached_cover",   // 正規化主體識別碼
  "composition": "close_up",              // close_up|medium|wide|flat_lay|screenshot|graphic
  "luma": 0.28,                           // 0-1，Python 端算，不問模型
  "score": 6.5,
  "flags": ["watermark_suspect"]
}
```

**`subject_key` 詞表必須是封閉的**，不能讓模型自由命名（否則同一本書會被叫成 `attached_book` 和 `book_cover`，去重失效）。作法：策展 prompt 帶入一份 canonical 前綴表 `person:` / `book:` / `place:` / `object:` / `screen:` / `scene:`，並要求 `snake_case` 英文；Python 端做 fuzzy 合併（Levenshtein ≤ 2 視為同一主體）。

### 2.3 可機器驗證的策展規則

寫進 `config/visual-rules.md`，由 `forage_shots.py` 與新增的 `check_rhythm.py` 執法：

| 規則 | 判準 | 動作 |
|---|---|---|
| R1 主體不重複 | 同一 `subject_key` 在整篇首選中出現 > 2 次 | 第 3 次起強制換次選 |
| R2 role 合規 | `person` 張的 `subject_key` 前綴必須是 `person:`；`evidence` 必須是 `screen:` | 不合即淘汰，不進候選池 |
| R3 分數線 | `score < 5` | 淘汰（現況已有，保留） |
| R4 浮水印 | vision `flags` 含 `watermark_suspect`，或網域在黑名單 | 淘汰。黑名單維持現有 22 個，新增 `mindframe/magnific/canva/envato/pond5/bigstock/photodune/stocksy`（已在 code 中） |
| R5 明暗交替 | 相鄰兩張的 `luma` 差 < 0.08 且連續 3 張同帶 | 警告，UI 標旗標 |
| R6 構圖配額 | 九張中同一 `composition` > 4 張 | 警告 |
| R7 人物比例 | 九張中含人臉的張數 < 2 或 > 6 | 警告 |
| R8 同源去重 | 同一 `domain` 首選 > 3 張 | 強制換次選 |

**R1／R2／R3／R4／R8 是硬淘汰（機器自動），R5／R6／R7 是軟旗標（進 UI 給 Jesse 判）。** 這個分界是為了 §6 的 2 分鐘目標：硬規則不需要人看，軟規則才需要。

### 2.4 兩段式策展流程

```
抓取端（現況保留）
  ↓ 網域黑名單、畫質閘門、近白頁偵測
S1 粗篩｜Haiku 4.5｜全部候選、256px 縮圖
  ↓ 輸出 {cid, role_ok, subject_key, composition, watermark, keep:bool}
  ↓ 硬規則 R2/R4 在此淘汰，通常砍掉 40-60%
S2 精排｜Opus 5｜每 slide 保留 top-4、512px 縮圖、整篇一次呼叫
  ↓ 輸出 {ranking, scores, focus_x, rationale}
  ↓ 硬規則 R1/R3/R8 執法 + 軟旗標 R5/R6/R7 標記
成篇總檢（WF15，現況保留但改判準）
```

**總檢 block 判準不穩的修法**：現在讓 vision 自由判斷「該不該擋」，所以同篇兩次結果不同。改成 **vision 只回報事實、Python 決定 block**：

```json
{ "duplicate_subjects": ["book:attached_cover"], "watermark_slides": [4],
  "unreadable_text_slides": [], "monotone_run": [2,3,4] }
```
Python 用固定門檻決定 block／warn。**同樣的輸入必然得到同樣的判定。**

---

## 3. 自有素材庫

### 3.1 現況

`/Users/mimo/Desktop/Lava/Marketing/可商用圖片素材庫/` 目前**只有 1 個檔案**（一張 Higgsfield 產出）。`anthropic-skills:lava-ig-asset-intake` skill 已定義了入庫語意，但沒有實際庫存。等於綠地。

實測：29 次執行抓了 640 張候選，實際用掉 210 張（`composed` 總和），**430 張被丟掉且沒有留下**。這是最明顯的浪費。

### 3.2 什麼該入庫

| 類別 | 入庫條件 | 為什麼 |
|---|---|---|
| **A 級 mood** | 策展分 ≥ 7 且通過成篇總檢且已發佈 | 已被雙重驗證，可重複調用 |
| **B 級 mood** | 策展分 5-7，未被選用但無旗標 | 下次同主題可省一次抓取 |
| **person 本人照** | 任何通過 R2 的公眾人物照 | 同一個作者會反覆出現（Attached/Aziz 已重打三次），這是最高 ROI 的快取 |
| **evidence 截圖** | 任何成功截圖（非近白頁） | 截圖成本最高（headless Chrome），且頁面會改版，抓到就是資產 |
| **自家 final 圖** | 每篇發佈成品 | 對標分析、版型參考、避免自我重複 |
| 不入庫 | 分數 < 5、有旗標、離題 | 存了也不會用 |

### 3.3 索引 schema

`data/asset_library.jsonl`（一行一資產，append-only，git 可 diff）：

```json
{
  "aid": "a_7f3c9e21",
  "sha256": "…",
  "phash": "e3f1a8c2…",
  "path": "assets/library/mood/2026/08/a_7f3c9e21.jpg",
  "role": "mood", "subject_key": "scene:cafe_two_people",
  "composition": "medium", "luma": 0.34, "w": 1600, "h": 2000,
  "source": {"provider":"pexels","id":"3184465","url":"…","photographer":"…"},
  "license": {"type":"pexels","commercial":true,"attribution_required":false},
  "grade": "A", "curator_score": 7.8,
  "tags": ["約會","咖啡廳","台北","兩人","室內","暖色"],
  "used_in": [{"post":"20260803-…","slide":3,"published_at":"2026-08-03"}],
  "cooldown_until": "2026-11-03",
  "created_at": "2026-08-03T14:00:00+08:00"
}
```

### 3.4 檢索

素材庫先於外部抓取執行：

1. **標籤檢索**：`visual_refs` 的 `query` 斷詞後對 `tags` 做 BM25（純本機，`rank_bm25` 套件，零 AI 成本）。
2. **主體檢索**：`subject_key` 精確匹配（person role 幾乎必中）。
3. **命中門檻**：若某 slide 從庫內找到 ≥ 2 張 grade A/B 且不在冷卻期，**跳過該 slide 的外部抓取**。

實測預估：person role 41 張中，Attached/Aziz 相關被重打三次，命中率應該很高。這直接減少 §5 的候選張數，也就是直接減少 vision 成本。

### 3.5 避免重複使用

三層：

| 機制 | 規則 |
|---|---|
| **冷卻期** | A 級用過後 `cooldown_until = 發佈日 + 90 天`；B 級 + 180 天。冷卻期內不進候選池 |
| **pHash 去重** | 入庫時算 pHash（`imagehash` 套件），Hamming 距離 ≤ 5 視為同一張，不重複入庫；抓取端也用同一組 hash 擋掉「換了網域的同一張圖」 |
| **subject_key 節流** | 同一 `subject_key` 在近 5 篇已發佈貼文中出現 ≥ 3 次，降權 2 分（不淘汰，因為品牌重複的主體有時是刻意的） |

### 3.6 授權標注是強制欄位

`license` 欄位缺失的資產**不得進庫**。理由：現在不記，三個月後沒有人知道那張圖能不能商用，整個庫就變成不可用的負債。這條要在 `intake` 腳本裡硬性 assert。

---

## 4. 視覺一致性：九張的節奏合約

總檢多次指出「節奏停滯」。根因是**九張都用同一套上下分割版式**，且沒有任何跨張的變化規則。

### 4.1 節奏合約（寫死在 `config/rhythm-contract.json`）

以現行 9 張結構（Hook → 共感 → 知識×3 → 品牌 → 應用 → 立場 → CTA）為基準：

| slide | role 建議 | composition 建議 | luma 帶 | 版型 |
|---|---|---|---|---|
| 1 封面 | mood / person | close_up 或 collage | 暗（≤0.35） | hero 或 collage |
| 2 共感場景 | mood | wide | 亮（≥0.55） | 頂錨漸層 |
| 3 知識 A | evidence / mood | medium | 暗 | 滿版 |
| 4 知識 B | evidence / graphic | screenshot / graphic | 亮 | 上下分割 |
| 5 知識 C | mood / book | close_up | 暗 | 滿版 |
| 6 品牌輕置入 | mood | medium | 亮 | 頂錨漸層 |
| 7 應用 | mood | wide | 暗 | 滿版 |
| 8 品牌立場 | graphic / mood | flat_lay / graphic | 亮 | 上下分割 |
| 9 CTA | 公版 | graphic | 品牌色 | CTA 公版 |

### 4.2 三條可機器驗證的硬規則

```python
# scripts/check_rhythm.py，零 AI 成本，PIL 直接算成品
def check_rhythm(final_images):
    lumas = [mean_luma(im) for im in final_images]
    # RH1 明暗交替：不得連續 3 張同帶（以 0.45 為界）
    bands = ['d' if l < 0.45 else 'l' for l in lumas]
    assert not any(bands[i:i+3] in (['d']*3, ['l']*3) for i in range(7)), "RH1 明暗停滯"
    # RH2 構圖配額：同一 composition 不得 > 4 張
    assert max(Counter(comps).values()) <= 4, "RH2 構圖單調"
    # RH3 人物比例：含人臉的張數落在 2-6
    assert 2 <= sum(has_face) <= 6, "RH3 人物比例失衡"
```

`has_face` 用 OpenCV Haar cascade 即可（本機、免費、夠準），不需要呼叫 vision。

### 4.3 版型變化必須先做

節奏規則只能約束「選哪張圖」，**不能解決「九張都是同一套版式」**。RH1-3 全過，但九張都是上下分割，總檢還是會判停滯。

**這是排版引擎（環節 5）的工作，不是本環節能解的。** 本環節能做的是：策展時輸出 `suggested_layout`（hero / 滿版 / 頂錨 / 上下分割 / collage），交給 `render_post_v5.py` 執行。若環節 5 沒有實作多版型，本環節的節奏規則只能拿到一半效果。**這個依賴必須明講。**

---

## 5. 任務配置與成本

### 5.1 分工

| 階段 | 執行者 | 模型 | 輸入 | 為什麼 |
|---|---|---|---|---|
| **檢索** | 本機 `forage_shots.py` | 無 | 素材庫 BM25 + 外部 API | 零成本，先掏庫存 |
| **抓取** | 本機 | 無 | 多來源降級鏈 | 現況架構保留 |
| **過濾** | 本機 | 無 | 畫質閘門、pHash、網域黑名單 | 機械規則不該花錢 |
| **S1 粗篩** | API | **Haiku 4.5** | 全候選、256px | 只判 role_ok / subject_key / watermark，屬分類任務 |
| **S2 精排** | API | **Opus 5** | 每 slide top-4、512px、**整篇一次呼叫** | 相對排序需要看整篇，且要判「這張放在第 5 張好不好」 |
| **執法** | 本機 `check_rhythm.py` | 無 | 成品 PNG | 明暗／構圖／人臉全部本機算 |
| **總檢** | API | Sonnet 5 | 九張成品、512px | 只回報事實，Python 決定 block |

### 5.2 成本試算（每篇，中位 17 候選）

[驗證] 模型單價：Haiku 4.5 $1/$5、Sonnet 5 $3/$15（2026-08-31 前導入價 $2/$10）、Opus 5 $5/$25 per MTok。Batch API 五折。Prompt caching 寫入 1.25×、讀取 0.1×，Opus 5 最小可快取前綴 512 tokens。

| 項目 | tokens | 成本 |
|---|---|---|
| **現況**（9 次呼叫，rubric 重送 9 次，模型待查） | in 23,780 / out 1,080 | 以 Sonnet 5 計 ≈ **$0.087** |
| S1 粗篩 Haiku，17 張 @256px（80 tok/張）+ rubric 800 快取 | in 1,440 / out 400 | $0.0034 |
| S2 精排 Opus 5，24 張 @512px（285 tok/張）+ rubric 2,000 快取 | in 7,040 / out 700 | $0.0525 |
| 總檢 Sonnet 5，9 張 @512px | in 3,065 / out 300 | $0.0137 |
| **升級後合計** | | **$0.070** |
| 升級後 + Batch API（forage 在前一晚跑） | | **$0.035** |

**月成本（30 篇）：現況 $2.6 → 升級後 $2.1 → 走 batch $1.05。** 在 $15 月預算裡完全可控，而且**升級到 Opus 5 精排反而比現在便宜**。

### 5.3 控制 vision 成本的四個槓桿（依效果排序）

1. **合併呼叫**：9 次 → 1 次，省掉 8 份重複 rubric。省約 60%。
2. **Prompt caching rubric**：策展 rubric 是穩定前綴，`cache_control: {type:"ephemeral"}` 放在 rubric 最後一個 block。省約 15%。
3. **素材庫命中**：庫內找到就不抓不看，直接減少候選數。長期效果最大（person role 預估命中率高）。
4. **Haiku 粗篩 + 小縮圖**：256px 是 80 tokens，512px 是 285 tokens，差 3.5 倍。粗篩不需要 512px。

**不要做的：** 為省錢降到 Haiku 做精排。實測策展均分中位只有 3.65，分數線是 5，代表現在的策展品質本身就在及格邊緣。省 $0.05/篇換品質下降，違反北極星（Jesse 分鐘數）。

### 5.4 合併呼叫的風險

現況註解寫「整包 30+ 張會逾時；單批 ≤8 張穩定」。合併後最大 64 張候選一次送。

- [驗證] API 限制：1M context 模型每請求最多 600 張圖，Opus 5 是 1M context，64 張無壓力。
- 逾時風險：改用 streaming（`client.messages.stream()` + `get_final_message()`），並把 `max_tokens` 設 8,000。若仍逾時，退化成「每 3 個 slide 一批」（3 次呼叫）而不是回到 9 次。

---

## 6. UI 設計：桌面版選圖台

### 6.1 痛點與目標

現況：`docs/app.js:288` 逐 slide 縱向排列候選，手機單欄。一篇 15-74 張候選要捲很久。

目標：**一篇九張的選圖在 2 分鐘內完成。**

### 6.2 核心設計原則：Jesse 不是在「選圖」，是在「改掉不對的」

AI 已經排好序，top-1 預設選中。Jesse 的工作應該是**只處理有旗標的 2-3 張**，而不是逐張審 9 次。

2 分鐘的算術拆解：
```
載入 + 掃視九張軌道       20s
處理 2-3 張旗標張（每張 30s）  90s
確認送出                  10s
                        = 120s
```
**這個預算只有在「預設可信」的前提下成立。** 若 AI top-1 命中率低於 70%，Jesse 就得逐張改，2 分鐘不可能。所以 §2 的策展升級是 UI 目標的前置條件，不是平行工作。

### 6.3 版面（桌面 1440px 三欄）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 貼文標題         [節奏儀表]  ●○●○●○●○▲  [全部接受] [送審] [退回底圖] │
├────────┬──────────────────────────────────┬──────────────────────────┤
│ 軌道    │  當前 slide 候選網格              │  節奏檢查                 │
│ (180px)│  (auto, 4 欄)                    │  (280px)                 │
│        │                                  │                          │
│ ①🖼 ✓  │  ┌────┐┌────┐┌────┐┌────┐        │ ▸ 明暗帶                  │
│ ②🖼 ✓  │  │ ★  ││    ││    ││    │        │   ●○●●●○●○▲ ← 3-5 連暗   │
│ ③🖼 ⚠  │  │7.8 ││7.1 ││6.4 ││5.9 │        │   RH1 警告                │
│ ④🖼 ✓  │  └────┘└────┘└────┘└────┘        │                          │
│ ⑤🖼 ⚠  │  ┌────┐┌────┐┌────┐┌────┐        │ ▸ 構圖配額                │
│ ⑥🖼 ✓  │  │    ││    ││    ││    │        │   close_up 5/4 ⚠         │
│ ⑦🖼 ✓  │  └────┘└────┘└────┘└────┘        │                          │
│ ⑧🖼 ✓  │                                  │ ▸ 主體衝突                │
│ ⑨ CTA  │  [ ] 只看未淘汰  [x] 合成預覽     │   book:attached ×3 ⚠     │
│        │                                  │   → 建議 slide 5 換       │
│        │  候選 17 張 · 淘汰 8 · 顯示 9     │                          │
└────────┴──────────────────────────────────┴──────────────────────────┘
```

### 6.4 關鍵互動

| 元素 | 行為 |
|---|---|
| **軌道欄** | 九張縮圖直排，顯示已選圖。`✓` = 無旗標、`⚠` = 有軟旗標、`✗` = 無合格候選。**點軌道切換中欄** |
| **旗標優先** | 進入頁面時自動跳到第一個 `⚠` slide，不是 slide 1。Jesse 直接落在需要處理的地方 |
| **合成預覽** | 預設**開啟**。顯示的是文字壓上去的樣子，不是裸底圖。現況 `app.js:595` 已有提示但預設關閉，這是錯的（視覺鐵律第 7 條說「驗收看合成品」） |
| **卡片資訊** | 縮圖 + 分數 + `subject_key` + `composition` + luma 條。滑鼠移入顯示 vision 的一句 rationale |
| **淘汰不隱藏** | 被硬規則淘汰的候選預設收起，但可展開查看（附淘汰原因）。理由：AI 誤淘汰時 Jesse 要能救回來 |
| **節奏儀表即時更新** | 換一張圖，右欄立刻重算 RH1/RH2/RH3。這是把「總檢」從發佈前提早到選圖時 |
| **全部接受** | 一鍵套用所有 AI top-1。無旗標的貼文應該可以 15 秒完成 |

### 6.5 鍵盤（決定能不能達成 2 分鐘）

| 鍵 | 動作 |
|---|---|
| `1`-`9` | 跳到該 slide |
| `Tab` / `Shift+Tab` | 跳到下一個／上一個有旗標的 slide |
| `←` `→` | 在候選網格移動 |
| `Enter` / `Space` | 選定當前候選 |
| `F` | 放大檢視（合成品全尺寸） |
| `X` | 排除此候選（寫回 `curation_log` 當負樣本） |
| `A` | 全部接受 AI 建議 |
| `Cmd+Enter` | 送審 |

**`Tab` 跳旗標是這個設計裡最關鍵的一鍵。** 它把「捲 74 張」變成「按 3 次 Tab」。

### 6.6 手機降級

依已定案決策，手機只讀。手機版顯示：九張成品預覽 + 節奏儀表 + 「在桌面開啟」按鈕。不提供選圖。

---

## 7. 我方案裡最弱的一環

**最弱的是：整套策展標準沒有任何成效資料校準，是美學共識偽裝成評分系統。**

具體：
- 實測 `insights.json` 只有 5 篇 7 月貼文有成效快照，reach 200-260、saved 1-2、shares 2-3。**變異太小，n 太少，任何「哪種圖有效」的推論都是雜訊。**
- 我在 §2 提出的 R1-R8、§4 的 RH1-RH3、§4.1 的節奏合約，**全部是從 wknd 對標和 Jesse 的裁決推導的，沒有一條有 Lava 自己的成效證據。**
- 更糟的是這套規則會**自我封閉**：一旦寫死「明暗交替」「同主體 ≤2」，就永遠不會產生違反規則但可能更有效的貼文，也就永遠測不出規則是錯的。

**緩解（但不是解決）**：
1. 每 10 篇留 1 篇當「不執法軟規則」的對照組，只跑硬規則。90 天後至少有 3 個對照樣本可以看趨勢。
2. `curation_log.jsonl` 已在記錄，補記 `chosen_cid` 與 `ai_top1_cid` 是否一致。**「Jesse 改掉 AI 選擇的比率」是唯一現在就能量、且立刻有訊號的指標**，比 IG reach 快得多。目標：改動率從基線降到 < 25%。
3. 誠實標註：`visual-rules.md` 每一條規則加上 `[裁決]` 或 `[成效驗證]` 標籤。現在全部是 `[裁決]`。

**次弱的兩點：**
- `subject_key` 由 vision 自產。封閉詞表 + Levenshtein 合併能擋大部分，但「同一本書的兩張不同角度照」是否算同一主體，模型判斷會不穩。**這是 R1 最可能失效的地方，需要 golden set 校準。**
- **台灣在地素材覆蓋率完全沒查證。** 我沒有 Pexels／Unsplash 金鑰，無法實測「台北 咖啡廳 兩人」這類查詢能撈到什麼。歐美圖庫的亞洲都會場景通常偏少且偏刻板。**這是 P0 來源接入前必須先做的 spike，不是接完再說。** 標記為**待查**。

---

## 8. 落地順序

| 批次 | 內容 | 依賴 | 產出 |
|---|---|---|---|
| **V23-A** | 合併 curate 呼叫（9→1）+ prompt caching + Opus 5 精排 | 無 | 成本降七成、分數穩定性提升 |
| **V23-B** | `subject_key` / `composition` / `luma` 欄位 + R1-R8 執法 + `check_rhythm.py` | A | 撞主體消失、節奏可量測 |
| **V23-C** | Pexels / Openverse / Wikimedia / 觀光署接入 + DDG 降級鏈。**先做台灣覆蓋率 spike** | 無 | 來源不再單點 |
| **V23-D** | `asset_library.jsonl` + intake 腳本 + BM25 檢索 + pHash 去重 + 冷卻期 | B、C | 候選數下降、成本再降 |
| **V23-E** | 桌面選圖台（三欄 + 鍵盤 + 節奏儀表 + 合成預覽預設開） | B | 選圖 2 分鐘、量出 Jesse 分鐘數基線 |
| **V23-F** | 總檢改為「回報事實 + Python 判定」 | B | block 判準可重現 |

**建議先做 A 和 E。** A 立刻省錢且讓分數穩定，E 立刻量出北極星指標的基線。C 和 D 是投資，效果要 4-6 週後才看得到。

---

### 主要出處

- [Unsplash API Documentation](https://unsplash.com/documentation) · [Pexels API](https://www.pexels.com/api/documentation/) · [Pixabay API](https://pixabay.com/api/docs/) · [Openverse API](https://api.openverse.org/v1/)（rate limit 為 response header 實測）· [Wikimedia Commons API](https://commons.wikimedia.org/w/api.php)（實測）· [Flickr API](https://www.flickr.com/services/developer/api/)
- [Google Custom Search JSON API](https://developers.google.com/custom-search/v1/overview) · [Brave Search API](https://brave.com/search/api/) · [SerpApi Pricing](https://serpapi.com/pricing) · [Bing Search API 退役](https://cloro.dev/blog/bing-search-api-key/)
- [TMDB API Terms of Use](https://www.themoviedb.org/api-terms-of-use) · [TMDB Image Basics](https://developer.themoviedb.org/docs/image-basics) · [Getty Images Embed](https://www.gettyimages.com/resources/embed) · [Instagram oEmbed](https://developers.facebook.com/docs/instagram-platform/oembed/)
- [Europe PMC Developers](https://europepmc.org/developers) · [觀光多媒體開放資料](https://media.taiwan.net.tw/zh-tw/portal) · [政府資料開放平臺](https://data.gov.tw/dataset/52790)
- [Anthropic Vision（token 公式與上限）](https://platform.claude.com/docs/en/build-with-claude/vision.md) · [Vimeo oEmbed](https://developer.vimeo.com/api/oembed) · [Adobe/Shutterstock/iStock 訂閱比較](https://photutorial.com/best-stock-image-subscriptions/)
- 本機實測檔案：`/Users/mimo/Claude/貼文製造機器人/lava-ig-console/data/quality_metrics.jsonl`、`data/forage_learnings.json`、`scripts/forage_shots.py`、`config/visual-rules.md`、`docs/app.js`