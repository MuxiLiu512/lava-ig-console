# Lava Reels：從文案到影片的可重複方法

## 0. 先確立一個數字，其餘結論都從它推出

繁體中文字幕的閱讀上限：**Netflix 繁中成人節目 9 字/秒，每行 16 字**（[驗證] Netflix Partner Help Center 繁中 Timed Text Style Guide，Section I.1 與 I.14）。那是「有對白聲音同步、字幕只作輔助確認」的上限。純字幕無旁白時沒有語音冗餘，還要跟 IG 的 UI 與滑動衝動競爭，實務安全值我抓 **4 到 5 字/秒**（[推理]，未經繁中短影音實測，見第 7 節弱點）。

用這個數字檢查現行的投影片轉檔版：每張 60 到 110 字，停 2.6 秒，等於要求觀眾 **23 到 42 字/秒**，是 Netflix 上限的 2.6 到 4.7 倍。Jesse 說的「不能自己掌握閱讀節奏」在數學上是這樣：那支影片對任何人類都是不可讀的。他的判斷不需要再驗證，只需要換算。

由此推出本研究最重要的結構性結論：

> **一支 30 秒的 Reels，字幕總預算約 100 到 120 字（30 × 4.5 扣掉呼吸與 CTA）。一篇九張輪播的總字量是 540 到 990 字。壓縮比 5 到 10 倍。**
>
> 所以 Reels 不是輪播的另一種輸出格式，是**從同一個選題重新取一個點**。管線上的意義：分鏡不從九張成品轉出，從文案 JSON 的原始素材重新生成。九張成品在 Reels 流程裡只剩兩個用途，封面幀與 ref 底圖。

---

## 1. 文案改寫原則

### 1.1 六條硬規則

| # | 規則 | 數值 |
|---|---|---|
| 1 | 一鏡一句一資訊點 | 每鏡 12 到 20 字，3 到 5 秒 |
| 2 | 字幕密度閘門 | ≤ 4.5 字/秒，程式硬擋，超標不給過 |
| 3 | payoff 前置 | 結論放句首，鋪陳全刪（輪播能鋪陳，影片不能） |
| 4 | 刪書面連接詞 | 「因此」「然而」「換句話說」「也就是說」一律改成剪接點 |
| 5 | 核心命題講兩次 | 0 到 3 秒一次，收尾一次。replay 計入 watch time，重複是為了縫 loop |
| 6 | CTA 逐字鎖定不得改字 | 只調斷點與秒數分配 |

口語化程度的界線：**刪掉的是連接詞與修飾從句，不是觀點**。品牌禁忌（AI 味、說教、雞湯）在影片裡放大，因為觀眾逐字被餵。留住有立場的短句，砍掉解釋性的長句。風格規格第五條禁的「不是…而是…」在影片裡更明顯，因為它會佔掉兩個鏡頭去講一個轉折。

### 1.2 改寫前後對照

**A. Hook（已讀不回題）**

原（輪播第 1 張，68 字）：
> 你有沒有過這種經驗？訊息傳出去，對方明明上線，就是不回。你開始重讀自己那句話，想找出哪裡說錯了。這不是你太敏感，而是大腦在做一件很老的事。

改（3 鏡，共 6.0 秒，31 字，5.2 字/秒 → 仍超標，下修為 3 鏡 7.0 秒）：

| 鏡 | 秒 | 字幕 | 字數 | 字/秒 |
|---|---|---|---|---|
| S1 | 0.0 to 2.2 | 他上線了。沒回你。 | 9 | 4.1 |
| S2 | 2.2 to 4.6 | 你重讀自己那句話第三次。 | 12 | 5.0 |
| S3 | 4.6 to 7.0 | 大腦這時候在做一件很老的事。 | 14 | 5.8 |

S2 與 S3 仍偏快，正式生產時 S3 應拆成兩鏡或減到 11 字。這正是要用程式閘門的理由，人眼估不準。

**B. 知識段（weak ties 題）**

原（95 字）：
> 2022 年 Science 期刊一項橫跨 20 個國家、2000 萬人的實驗發現，幫你找到工作的，往往不是天天見面的好朋友，而是那些一年見一次的弱連結。因為好朋友的資訊圈跟你重疊，弱連結才會帶來新的東西。

改（4 鏡，共 14 秒，56 字，4.0 字/秒）：

| 鏡 | 秒 | 字幕 | 畫面 |
|---|---|---|---|
| S4 | 0.0 to 3.5 | 2022 年，一個 2000 萬人的實驗。 | Science 頁面截圖，極慢推近，出處灰字常駐 |
| S5 | 3.5 to 7.0 | 幫你找到工作的，很少是死黨。 | 辦公室午休側拍，淺景深 |
| S6 | 7.0 to 10.5 | 是一年見一次的那種人。 | 街口擦身而過的兩人，慢動作 |
| S7 | 10.5 to 14.0 | 死黨知道的，你早就知道了。 | 同一張桌子兩杯咖啡，靜止 |

原文 95 字壓到 56 字，語意零損失。被刪掉的全是解釋（「因為資訊圈重疊」被 S7 用具體句取代）。

**C. CTA（逐字鎖定，只改節奏）**

| 鏡 | 秒 | 字幕 | 處理 |
|---|---|---|---|
| C1 | 0.0 to 0.6 | 滑動 | 單字大字卡，硬切 |
| C2 | 0.6 to 1.2 | 配對 | 硬切 |
| C3 | 1.2 to 1.8 | 碰面 | 硬切 |
| C4 | 1.8 to 5.5 | Lava 為你選好地點<br>現場備有破冰卡牌與迎賓飲品 | 22 字拆兩行，6.0 字/秒但因為是既讀資訊可容忍 |
| C5 | 5.5 to 8.0 | 出現就好，其他交給我們。 | 定格，無運鏡 |

「滑動、配對、碰面」是全片唯一該用 0.6 秒硬切的地方。快切在別處會製造焦慮，在這裡製造節奏。

---

## 2. 時間軸模板

### 2.1 選長度的依據

[驗證] highviz.io Instagram Reels Report（2026-07-20，n=315 支 Reels／96 個帳號，中位觸及 341）：watch ratio 依長度 0 到 15 秒 66.9%，15 到 30 秒 31.6%，30 到 60 秒 20.3%，60 秒以上 15.9%。這份樣本的量級跟 Lava 現況（觸及 200 到 260）同一個級距，比大帳號基準可信。

[推理] 但 IG 第一排名訊號是 watch time 總量不是比例（[驗證] Mosseri 2025 年公開的三訊號：watch time、sends per reach、likes per reach）。換算平均觀看秒數：15 秒 × 66.9% = 10.0 秒；30 秒 × 31.6% = 9.5 秒。**總 watch time 幾乎相同**，但短版的完播與 replay 對 sends 有利。結論：主力做 **20 到 28 秒**，不做 45 秒以上，除非有真正的故事。

[驗證] 超過 3 分鐘的 Reels 不會被推薦給非追蹤者，對 Lava 不構成限制。

### 2.2 三個可直接套用的模板

**15 秒｜單點型（一個反直覺事實、時事橋接）**

| 秒 | 段落 | 內容 | 目的 |
|---|---|---|---|
| 0.0 to 1.5 | 冷開場 | 第一幀就有完整可讀句，畫面已在動 | 過 3 秒關卡 |
| 1.5 to 3.0 | 認領 | 「這是我」的具體情境 | 把觀看轉成自我指涉 |
| 3.0 to 8.0 | 知識點 ×1 | 只放一個點 | 給收藏理由 |
| 8.0 to 11.0 | Lava 觀點 | 一句立場 | 品牌 |
| 11.0 to 14.0 | CTA | 三字快切＋一句 | 轉換 |
| 14.0 to 15.0 | loop 縫合 | 回到第一鏡構圖 | 拉 replay |

字幕預算約 55 到 65 字。

**30 秒｜知識型主力（每週 2 支走這個）**

| 秒 | 段落 | 內容 | 目的 |
|---|---|---|---|
| 0.0 to 3.0 | Hook | 最強問句，一鏡到兩鏡 | 3 秒留存 |
| 3.0 to 7.0 | 共感場景 | 具體到動作層次 | 建立「他在講我」 |
| 7.0 to 19.0 | 知識 ×2 | 每點 6 秒，不放三點 | 資訊價值 |
| 19.0 to 23.0 | 品牌立場 | Lava 為什麼這樣設計 | 賦能不代勞 |
| 23.0 to 28.0 | CTA | 公版 | 轉換 |
| 28.0 to 30.0 | 收尾＋loop | 金句定格 | 截圖與 replay |

字幕預算 100 到 120 字。輪播的「知識×3」在這裡砍成 2 點，這是必然的取捨。

**60 秒｜人物誌／深度型（每月上限 1 支）**

0 to 3 Hook｜3 to 8 反直覺主張｜8 to 20 證據 1｜20 to 32 證據 2｜32 to 42 對台灣讀者的意義｜42 to 52 品牌段｜52 to 58 CTA｜58 to 60 收尾。字幕預算 210 到 250 字。只在題材本身有敘事弧線時用，watch ratio 只剩 20%。

---

## 3. Lava 分鏡表格式

設計原則：**欄位切成「生成層」與「合成層」**。生成層餵 Higgsfield，合成層在本機 ffmpeg／PIL 做。中文字**絕對不進生成層**（生成模型渲染中文必壞，這是硬規則）。

### 3.1 Schema（`shots.json`，一支影片一檔）

```json
{
  "post_id": "20260813-已讀不回",
  "duration": 30.0,
  "template": "knowledge_30s",
  "music_slot": "meta_sound_collection",
  "shots": [
    {
      "shot_id": "S1",
      "role": "hook",
      "t_in": 0.0, "t_out": 3.0,
      "layer": "gen",
      "model": "seedance_2_0",
      "params": {"mode": "std", "resolution": "1080p",
                 "aspect_ratio": "9:16", "duration": 4,
                 "generate_audio": false},
      "ref": {"path": "docs/finals/<pid>/bg-01.png", "role": "start_image"},
      "visual_prompt": "extreme close-up of a phone screen at night, chat bubble glowing, rest of frame out of focus, cool blue hour tones, cinematic clean shadows, photorealistic, no text, no watermark",
      "camera": "very slow push in",
      "subtitle": [{"t": 0.2, "text": "他上線了。沒回你。", "style": "main"}],
      "safe_zone": "mid",
      "sfx": "notification_soft@0.3",
      "credit": null,
      "gate": {"cps_max": 4.5, "status": "pending"}
    },
    {
      "shot_id": "S4",
      "role": "insight",
      "t_in": 7.0, "t_out": 12.5,
      "layer": "ffmpeg",
      "model": null,
      "ref": {"path": "docs/finals/<pid>/shot-science.jpg", "role": "still"},
      "motion": "zoompan z=1.00->1.06, drift x+18px",
      "subtitle": [{"t": 7.2, "text": "心理學有個詞：模糊趨避。", "style": "main"}],
      "credit": "Science, 2022",
      "gate": {"cps_max": 4.5, "status": "pending"}
    }
  ]
}
```

### 3.2 欄位定義

| 欄位 | 用途 | 誰產 |
|---|---|---|
| `role` | hook / scene / insight / brand / cta / loop | LLM |
| `t_in` `t_out` | 時間軸，由模板決定 | 程式 |
| `layer` | `gen`（Higgsfield）或 `ffmpeg`（程式動態） | 人＋LLM |
| `model` `params` | 直接對應 Higgsfield MCP 參數 | 程式 |
| `ref` `visual_prompt` `camera` | 生成指令，英文，禁中文字 | LLM，人審 |
| `motion` | ffmpeg zoompan／drift 參數 | 程式 |
| `subtitle` | 繁中，字數受 `cps_max` 硬擋 | LLM，人審 |
| `safe_zone` | top / mid / low，避開上 108px 下 320px | 程式 |
| `sfx` `music_cue` | 音效點位 | LLM 建議，人選 |
| `credit` | 劇照／文獻出處，至少停留 1.5 秒 | 人 |
| `gate` | 閘門結果 | 程式 |

[驗證] Reels 安全區為 1080×1920 畫布內，上 108px、下 320px、左 60px、右 120px 留空（二手來源由實際 UI 量測，Meta 未發布官方單一規格表）。**下 320px 是硬約束**，字幕不得進入。

### 3.3 visual_prompt 寫法（餵 Seedance）

固定六段式：`subject + action + camera + lighting + mood + technical`。沿用既有風格規格第九條的 mood 後綴（lively／warm／dark），含人物時追加 `photorealistic, anatomically correct`。永遠加 `no text, no watermark, no on-screen typography`。

---

## 4. 旁白 vs 字幕

**結論：純字幕 ＋ 音效，不做 AI 中文旁白。至少在前 10 支不做。**

證據：

1. [驗證，2026-08-13 以 `list_voices` 實測] Higgsfield 預設音色前 60 個全部是英文名（Grady、Ainsley、Holden…），沒有標示中文音色。可走的中文路徑只有 `qwen_audio_tts`（`language: zh` ＋ `instruction` 指定口音）與 `inworld_text_to_speech` 的 Yichen／Xiaoyin／Xinyi／Jing，但後者在模型描述裡標明 `Game pipeline only`。**用 Higgsfield 做台灣腔旁白沒有現成路徑。**
2. [驗證] 台灣工具評測普遍指出多數 TTS「號稱支援中文，實際輸出是中國語調普通話」。對 25 到 34 歲台灣都會受眾，中國腔配音是即時的品牌傷害，正好命中品牌禁忌第一條。
3. [驗證] highviz n=315：silent／music-only 的 Reels watch ratio 最高（48.4%），但 engagement per view 最低（3.3%）；face-to-camera 的 engagement 最高（9.0%）。Lava 拿不到 face-to-camera，剩下的兩個選項裡，靜音路線在留存上占優。
4. [驗證] Verizon Media ＋ Publicis Media（2019，n=5,616 美國成人）：80% 表示有字幕時更可能看完整支影片；69% 在公共場合靜音觀看。字幕的留存效益有一手研究支撐，AI 旁白沒有。
5. 成本：字幕在本機用 PIL／ffmpeg 疊，0 credits、可程式化、可 A/B、改字 3 秒完成。AI 旁白要額外 credits、人工聽測，且台灣腔不可控，改一個字要重生成整段。

**例外條款**：60 秒人物誌型別若之後要試旁白，不要走 Higgsfield，單獨用 ElevenLabs 的台灣中文音色做 1 支對照，且必須 A/B 而非直接換掉主線。

[待查] 我找不到台灣受眾對中文 AI 語音接受度的可信量化研究。市面流通的數字（例如「43% 消費者 10 秒內能辨識 AI 語音」「42% 更高跳出率」）全部出自 SEO 內容農場（digen.ai、echovox 等），無原始研究可追，**不可用來做決策**。唯一可引用的相關一手數字是 YouTube 官方稱每日超過 600 萬觀眾觀看至少 10 分鐘自動配音內容，但那是外語配母語的場景，跟本案不同。

---

## 5. 音樂與音效

### 5.1 商業帳號的硬限制

[驗證] Lava 是商業帳號，音樂庫被限制在 **Meta Sound Collection**（約 14,000 首，明確清到商用）。Reels 一般音樂庫的熱門曲授權範圍是個人非商業使用，商業帳號的介面通常直接看不到。

[驗證] Meta Sound Collection 只清到 Facebook 與 Instagram，**不可搬到 TikTok／YouTube**。一稿多投必須換音軌，這是跨平台計畫的硬成本。

### 5.2 原生音訊 vs 平台音樂

[驗證，部分] 使用平台音訊會拿到 audio page 的額外曝光面（別人點「使用此音訊」的瀏覽路徑），這對 5 萬追蹤以下的帳號增量較明顯。
[待查] 「原生音訊有排名加權」「原創內容多 40 到 60% 分發」這類說法我只找到二手部落格，沒有 Meta 一手聲明，不可作為決策依據。

### 5.3 操作結論（具體到參數）

- **Seedance 的 `generate_audio` 一律設 `false`**（預設是 `true`）。原生 AI 音訊會佔掉要留給平台音樂的空間，且中文語境下常生出無意義的人聲呢喃。
- 影片檔輸出時**帶一條只有音效與 room tone 的音軌**，不含音樂。音樂在 IG app 內套 Meta Sound Collection，這樣才吃得到平台音樂的分發面，而且換曲不用重打影片。
- 一定要 mux 一條音軌出來（哪怕是靜音 AAC）。現行 `make_reel.py` 產出的檔案完全沒有音訊串流，這在部分上傳路徑會出狀況 [推理，未實測]。
- **自建音效庫，一次做完永久複用**（5 到 7 個元素即可覆蓋 Lava 所有題型）：訊息提示音、鍵盤打字、杯子放桌、椅子拉動、腳步、whoosh 轉場、低頻 impact（數據落地時打一下）。放 `assets/sfx/`，分鏡表用 `sfx: "name@offset"` 引用。

---

## 6. 自動化管線

### 6.1 三層切分

| 層 | 內容 | 誰做 |
|---|---|---|
| **全自動** | 時間軸配置、字幕斷句與 4.5 字/秒閘門、安全區檢查、禁句檢查（破折號／「不是…而是…」）、字卡渲染、Higgsfield 批次生成與輪詢、拼接混音、loop 縫合、封面幀輸出、規格與成本檢查 | 程式 |
| **半自動（AI 產、人審）** | 輪播文案 → 分鏡 JSON、visual_prompt 英文化、音效點位建議、鏡頭 layer 分配（gen vs ffmpeg） | LLM |
| **必須人工** | 選題與觀點、hook 是否真的有勾、生成畫面是否穿幫或尷尬、引用正確性、最終 approve | Jesse |

### 6.2 管線設計

```
文案 JSON（既有，排版引擎/文案/*.json）
  ↓ scripts/reel_script.py     LLM 依模板產出 shots.json
  ↓ scripts/reel_lint.py       硬閘門：字/秒、安全區、禁句、總長、CTA 逐字比對
  ↓ ★ 人工審 shots.json（Jesse，約 10 分鐘）
  ↓ scripts/reel_gen.py        Higgsfield MCP 批次生成 layer=gen 的鏡頭
  ↓ scripts/reel_qc.py         自動品檢：黑幀、長度、解析度、首幀非空
  ↓ scripts/reel_build.py      ffmpeg：ffmpeg 動態鏡＋生成鏡＋字幕＋音效＋轉場＋loop
  ↓ ★ 人工審成片（Jesse，2 分鐘）
  ↓ 發布，IG app 內套 Meta Sound Collection
```

**關鍵設計決策：人工審門放在 `shots.json` 這一層，不放在成片層。** 改分鏡是改文字（秒級、0 成本），改成片是重新生成（分鐘級、燒 credits）。這是把一人團隊的人審成本壓到最低的槓桿點，也是這套方法能撐每週 3 支的唯一理由。

### 6.3 成本模型（實測）

[驗證，2026-08-13 用 `get_cost` 實測，9:16]：

| 設定 | 5 秒 | 換算 |
|---|---|---|
| seedance_2_0 std 1080p | 45 credits | 9 credits/秒（10 秒 = 90，線性已驗證） |
| seedance_2_0 fast 720p | 17.5 credits | 3.5 credits/秒 |
| seedance_2_0_mini 720p | 12.5 credits | 2.5 credits/秒 |
| flux_3_video 1080p | 45 credits | 9 credits/秒 |

[驗證] 目前餘額 2,271.76 credits，方案 ultra。[待查] ultra 月配額，二手來源稱 3,000/月，需自行確認。

三種打法的每支成本（30 秒，8 鏡）：

| 打法 | 組成 | credits／支 | 含 1.5 倍重生成 | 每月 12 支 |
|---|---|---|---|---|
| 全生成 std | 8 × 4 秒 × 9 | 288 | 432 | 5,184（爆） |
| **混合檔位** | hook＋CTA std（2×4 秒×9＝72）＋6 鏡 fast（6×4 秒×3.5＝84） | 156 | 234 | 2,808（勉強） |
| **推薦：3 生成 ＋ 5 程式** | hook std（36）＋2 payoff fast（28）＋5 鏡 ffmpeg zoompan（0） | 64 | 96 | 1,152（寬裕） |

推薦第三種。既有九張成品的原始底圖是現成靜圖，用 ffmpeg 的 `zoompan` 加緩慢位移做「假動態」成本為零，而且畫面風格跟輪播完全一致。真正需要 Seedance 的只有 hook 與一到兩個 payoff 鏡。省下的預算拿去做「同一個 hook 生四版挑一版」，那才是留存的真正槓桿。

---

## 7. 我這套方案最弱的三環

**第一弱，也是真正致命的：我沒有任何 Lava 自己的 Reels 留存資料。** 所有時間軸建議建立在 highviz（n=315，非台灣樣本，中位觸及 341）與通用基準上。Lava 單支觸及 200 到 260，任何 A/B 在 5 支以內測不出 20% 以下的差異。所以**第一階段不該追求「找出最佳結構」，只該追求「證明動態版的 3 秒留存高於投影片版」**。那個效果量如果真的存在會很大（Jesse 的假設是「馬上離開」），大到 n=4 就看得出來。若第一階段測出來兩者差不多，這整套方法的前提就要重估，而不是繼續往下做分鏡優化。

指標用 `reels_skip_rate`（3 秒內跳出比例）與留存曲線，兩者在 app 內 Reels 洞察都看得到。[待查] 二手來源稱 engagement insights 需 1,000 追蹤以上才開放，Lava 約 200，**必須先在 app 內親自確認拿不拿得到留存曲線**，拿不到的話整個測量計畫要改用外部代理指標。

**第二弱：trial reels 可能不能用。** [驗證] Instagram 官方創作者部落格只說「開放給所有符合資格的創作者」，資格條件指向 Help Center，該頁我抓不到內容。二手來源稱 2026 年初開放給 1,000 追蹤以上的創作者與商業帳號。Lava 約 200 追蹤。**如果 trial 不能用，就得靠正常發文做 A/B，取得 n 的週期從 1 週拉長到 3 到 4 週**，這會直接改變驗證計畫的節奏。這件事要在寫任何腳本之前先在手機上點開確認。

**第三弱：4.5 字/秒是我從 Netflix 9 CPS 折半推出來的**，沒有繁中短影音的實測依據。第一批片子應該自己測：同一段內容做 4 字/秒與 6 字/秒兩版，看留存曲線在哪裡開始分岔。這個數字一旦測準，整條管線的閘門就有了真實依據，而不是我的推理。

**另外一個要讓 Jesse 知道的風險**：[驗證] Meta 在 2026 年對**廣告**強制揭露 AI 生成內容，未揭露已成為第三大廣告拒登原因；自然貼文則由系統偵測 Content Credentials 後自動加上 AI info 標籤。Seedance 產出的素材若之後拿去投放，必須主動揭露；即使只發自然內容，標籤也可能自動出現在貼文上。對一個把「不要 AI 味」寫進品牌禁忌的帳號，這是實質風險，不是理論風險。這也是我推薦「3 生成鏡 ＋ 5 程式動態鏡」的第二個理由，AI 生成畫面的佔比越低，觸發標籤的機率越低。

---

## 8. 建議的下一步（兩週）

1. **本週先確認兩件事**：trial reels 在 Lava 帳號能不能開；Reels 洞察裡看不看得到留存曲線與 skip rate。兩題都是 5 分鐘在手機上點開就有答案，但會決定後面三週怎麼跑。
2. 用**已讀不回**這篇既有素材做第一支 30 秒（3 生成鏡＋5 程式鏡），跟現有的投影片轉檔版對照發。
3. 只看一個指標：3 秒留存。其餘全部先不看。
4. `reel_lint.py` 先寫，`reel_script.py` 後寫。閘門比生成器重要，因為閘門擋掉的是最貴的錯誤（人審完才發現字太多，等於整輪重來）。

---

**資料來源**

- [Chinese (Traditional) Timed Text Style Guide, Netflix Partner Help Center](https://partnerhelp.netflixstudios.com/hc/en-us/articles/215994807-Chinese-Traditional-Timed-Text-Style-Guide)
- [Instagram Reels Report 2026, highviz.io（n=315／96 帳號，2026-07-20）](https://www.highviz.io/instagram-reels-report)
- [Verizon Media and Publicis Media Find Viewers Want Captions, 3Play Media（n=5,616）](https://www.3playmedia.com/blog/verizon-media-and-publicis-media-find-viewers-want-captions/)
- [Instagram Sound Library Rules for Creators and Brands, Third Chair](https://usethirdchair.com/blog/instagram-sound-library-rules-for-creators-and-brands)
- [Why Your Instagram Business Account Can't Use Trending Music, MaaS](https://www.trymaas.com/blog/instagram-business-account-trending-music-risks/)
- [Trial reels, Instagram for Creators 官方](https://creators.instagram.com/blog/instagram-trial-reels)
- [Instagram algorithm tips for 2026, Hootsuite（Mosseri 三訊號）](https://blog.hootsuite.com/instagram-algorithm/)
- [Meta AI Content Labeling for Facebook & Instagram Ads 2026, Coinis](https://coinis.com/blog/meta-ai-content-labeling-facebook-instagram-ads-2026)
- [Meta Ads Safe Zones 2026, 1ClickReport](https://www.1clickreport.com/blog/meta-ads-creative-safe-zones-2026-guide)
- [2026 AI 配音工具推薦（台灣口音實測），領先時代](https://leadingmrk.com/ai-voice-tools/)
- Higgsfield MCP 實測（2026-08-13）：`models_explore`、`list_voices`、`generate_video get_cost`、`balance`

**相關檔案**
`/Users/mimo/Claude/貼文製造機器人/lava-ig-console/scripts/make_reel.py`（現行對照組產生器，DUR_BODY 2.6 秒是本文第 0 節的檢驗對象，且輸出無音訊串流）
`/Users/mimo/Claude/貼文製造機器人/lava-ig-console/scripts/ig_insights.py`（目前僅骨架，留存指標尚未接上，測量計畫要靠它）
`/Users/mimo/Claude/貼文製造機器人/風格規格-v1.0.md`（第五條禁句、第九條 mood 後綴、第三條 CTA 逐字鎖定，分鏡閘門直接沿用）