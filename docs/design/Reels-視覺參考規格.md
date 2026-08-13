# Reels 視覺參考規格

來源：Jesse 2026-08-13 提供的參考影片
`Icons - Sunday Times Adverts & Commercials Archive`（50 秒，1280×720，h264）

Jesse 的指示原文：
> 運鏡感強，但其實不需要是真人，一鏡到底比較吸引人（這只是意向參考）
> 工具用 seedance 2.5 instead of 2.0

---

## 1. 參考影片在做什麼

**電影經典場景的符號化重演，拍成刻意露出燈架的棚內感。**

抽格分析（8 個時間點）看到的內容：
- 阿甘正傳：長凳＋米色西裝背影＋腳邊行李箱
- Matrix：兩隻手交遞手槍，人物只到胸口以下
- Daft Punk：兩個頭盔人側身對望
- 每個場景都露出攝影棚元素：燈架、腳架、空白背景牆、水泥地

### 五個可移植的手法

| # | 手法 | 為什麼對 Lava 有用 |
|---|---|---|
| 1 | **人物出現但不需要臉**：背影、手部、剪影、頭盔 | 直接破解「無真人出鏡」的硬限制。不是避開人，是讓人成為符號 |
| 2 | **道具敘事**：長凳＋行李箱就是阿甘，兩把槍就是 Matrix | 用最少元素建立場景，生成難度低、識別度高 |
| 3 | **刻意的棚內感**：露出燈架、空白背景 | 形成「這是被建構的」後設感，與 Lava 反表演式社交的主張同構 |
| 4 | **一鏡到底的環繞運鏡** | 空間感與連續性是留住人的關鍵，勝過快剪 |
| 5 | **極簡色調**：白／米／黑／灰，低飽和 | 與滿街的高飽和情侶照形成對比，是視覺上的空白位 |

### 為什麼「人不需要臉」是這份參考最值錢的一點

三個層面同時解決：
- **製作面**：AI 生成不必處理臉部 identity 一致性，這是 AI 影片最容易露餡的環節
- **品牌面**：Lava 主張不表演，用網紅臉本身就違背主張
- **法務面**：不涉及真人肖像

---

## 2. Lava 的對應場景庫（初稿）

把上述手法套到 Lava 的內容主題，每個場景都是「符號化、無臉、可生成」：

| 主題 | 符號化場景 | 道具 |
|---|---|---|
| 只聊天不見面 | 長椅兩端各坐一人，中間隔著兩支發亮的手機 | 長椅、手機 |
| 已讀不回 | 一隻手伸向對面，對面的手在滑手機 | 兩隻手、手機 |
| 選擇過載 | 一個人站在無限延伸的門廊，每扇門都半開 | 門、走廊 |
| 見面才算數 | 空的雙人餐桌，兩支手機面朝下疊在桌角 | 餐桌、手機 |
| 輕蔑的表情（Gottman） | 兩張椅子對放，其中一張微微轉開 | 椅子 |
| 塩顏／不表演 | 空白背景前一個背影，肩線放鬆 | 無 |

原則：**畫面上不出現臉，情緒由姿態、距離、道具承載。**

---

## 3. Seedance 2.5 能力（2026-08-13 從 Higgsfield 目錄實查）

| 項目 | 規格 |
|---|---|
| 模式 | `t2v`／`omni_reference`／`video_edit`／`video_extension` |
| 時長 | **4 到 30 秒**（2.0 只有 4 到 15） |
| 解析度 | 480p／720p（2.0 有 1080p／4K，但 Reels 用不到） |
| 比例 | 含 9:16 |
| 參考輸入 | start_image／end_image／image_references／video_references／audio_references |
| 音訊 | `generate_audio` 可開關 |
| 延長 | `video_extension` 支援 `backward`／`forward` |

**對「一鏡到底」的意義**：30 秒單次生成 ＋ video_extension 前後延長，
是唯一能做出連續長鏡頭的組合。2.0 的 15 秒上限做不到。

**待驗證 [待查]**
- 單支實際成本（用 `get_cost: true` 預檢，尚未跑）
- 720p 上到 IG 後的實際畫質
- 環繞運鏡的可控程度（prompt 能指定到什麼精細度）
- video_extension 接縫是否自然

---

## 4. 與現有輪播的關係

參考影片是 50 秒的品牌片，Reels 的甜蜜點更短。
但這份參考的價值不在長度，在**視覺語言**：符號化、無臉、棚內感、一鏡到底、低飽和。

這套語言與現有輪播（滿版劇照＋文字疊加）是兩種不同的東西。
需要在後續方向文件裡明確定義兩者的分工，不能只是把輪播動起來。

---

## 5. 實測驗證（2026-08-13）

**一次生成即達標，成本 65 credits。**

| 項目 | 結果 |
|---|---|
| 模型 | `seedance_2_5`，t2v，10 秒，9:16，720×1280，無音訊 |
| 成本 | 65 credits（30 秒為 195，線性 6.5/秒）。餘額 2269，Ultra 方案 |
| 生成時間 | 約 3 分鐘 |
| 重試次數 | **0**（首次即可用） |

### 驗到的五件事

1. **一鏡到底成立**：鏡頭從側面環繞至正後方，連續無剪接，弧線平順
2. **無臉成立**：全程只有背影與側後方，沒有任何一幀露臉
3. **棚內感成立**：白色 cyclorama、右側 C-stand 與器材推車、頂部燈桁架都照 prompt 出現
4. **色調成立**：白／米／黑，低飽和，柔和方向光
5. **敘事自己長出來了**：第 9 秒時一人已放下手機望向前方，另一人仍在滑。
   這不在 prompt 裡，是模型自己補的動作差異，而它剛好就是 Lava 的主張

### Prompt 有效結構（可複用）

```
Cinematic single continuous take, slow orbital camera arc.
[主體與姿態，強調 seen from behind]
Vast empty white cyclorama studio background.
Visible studio lighting stands, C-stands and rigging at the edges of frame, deliberately exposed.
Muted palette: beige, black, warm white, low saturation.
Soft directional key light from the left.
No faces visible at any point.
Camera slowly arcs from side profile toward three-quarter front while keeping constant distance.
Shallow depth of field, subtle 35mm film grain.
No text, no captions, no logos.
```

關鍵是四個約束詞組：`single continuous take` 鎖一鏡到底、
`seen from behind` + `No faces visible at any point` 雙重鎖無臉、
`deliberately exposed` 鎖棚內感、`No text` 避免模型自己加字。

### 尚未驗證 [待查]

- 30 秒單次生成的一致性（10 秒沒問題，長鏡頭是否會漂移未知）
- `video_extension` 的接縫自然度
- 文字疊上去之後的可讀性（生成片是滿版影像，字要疊哪裡還沒設計）
- 音訊：本次關閉，Lava 的 Reels 要不要原生音效待定
- 多支之間的視覺一致性（同一組 prompt 結構是否產出同一個世界觀）
