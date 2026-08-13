# Lava Reels 視覺方向研究

## 0. 一句話結論

Jesse 的批評方向對，但推論的下一步可能錯。Reels 前三秒需要的是**資訊節奏的密度**，不是**畫面位移量**。而 Seedance 最強的能力（identity 一致、reference-driven 人物演出）恰好是 Lava 用不到的，它最弱的地方（手、臉、中文字、長敘事）恰好是最容易露餡的。

**建議方向：AI 只負責 4 到 6 秒的「無臉會呼吸的底」，動態主體交給程式化的文字與版面運動。** 這條路每篇約 170 credits，一週 3 篇在現有 Ultra 額度內有 30% buffer。全 AI 生成會超額約 2.3 倍。

---

## 1. Seedance 的實際能力邊界

### 1.1 帳號實測數據（最強證據，來自你們自己的 Higgsfield 交易與生成記錄）

**[驗證]** 這個 Higgsfield 帳號（Ultra，餘額 2,271.76 credits）在 8/12 到 8/13 已經跑過 Seedance 2.5：

| 生成 | 參數 | 扣款 |
|---|---|---|
| 手部 B-roll ×3 | 4s / 720p / 16:9 / bitrate high / generate_audio=false | 各 26 credits |
| 六拍一鏡到底 | 12s / 720p / 16:9 | 78 credits |
| 人物反應鏡頭 ×N | 4s / 720p，帶 start_image + end_image + image reference | 各 26 credits |

**計價完全線性：720p high-bitrate = 6.5 credits/秒**（4s→26，12s→78）。這是驗證數，不是網路二手資料。

配套：Nano Banana Pro 生圖 2 credits/張，Higgsfield Soul V2 生圖 **0.12 credits/張**（便宜 16 倍，草稿階段該用它）。

**[驗證]** `models_explore` 回報 `unlim.available: false`，代表這個帳號**目前沒有可用的 Seedance Unlimited 視窗**，所有生成都走扣點。

### 1.2 平台上的規格差異（Higgsfield MCP 直接回報）

**[驗證]**

| | Seedance 2.0 | Seedance 2.0 Mini | Seedance 2.5 |
|---|---|---|---|
| 長度 | 4 到 15s | 4 到 15s | 4 到 **30s** |
| 解析度 | 480p/720p/1080p/**4K**（1080p 以上需 mode=std） | 480p/720p only | **480p/720p only** |
| 參考輸入 | start/end image、image/video/audio refs | 同左 | 同左，另有 video_edit、video_extension |
| 特殊 | genre hint、fast/std 雙模 | 便宜 | 影片續接、影片編輯 |

**這個對照很重要**：Seedance 2.5 在 Higgsfield 上**沒有 1080p**。你們現有實驗全部跑 2.5，等於自己把畫質天花板壓在 720p。9:16 的 720p 是 720×1280，IG Reels 推薦 1080×1920，會被上採樣。

### 1.3 它擅長什麼

**[驗證]** 官方與第三方評測一致指向：
- 首次可用率高，一次生成約 90% 可用（廠商宣稱，見 VERTU 評測，屬廠商數字需打折）
- 多主體互動不崩肢體，群體編舞、對打、球類運動可用（Designkit）
- 12 檔參考檔案系統，reference-driven 的控制力優於純 prompt
- 原生同步音訊、beat-aware sync
- **中文語音生成優於 Veo 3.1**（Seedance 1.5 pro 論文，arXiv 2512.13507）

**[推理]** 對 Lava 真正有用的只有第三項（reference 控制）與 locked-off 靜態場景的穩定度。identity 一致性對你們是**沉沒能力**，因為沒有代言人、沒有連續角色。

### 1.4 它不擅長什麼（這才是決策依據）

**[驗證]**
- **手指仍會出錯**。你們的 prompt 已經寫了 `exactly five fingers and one thumb`，這代表你們踩過坑。MindStudio 的 2.5 評測直接寫：五指以上、需要雙手協調時測試不可靠
- **快速動作會 morphing 與 decoherence**，即使 prompt 結構良好
- **ByteDance 官方承認兩個未解問題**：複雜運動的物理合理性、大量主體互動時的穩定度
- **細小文字、精確產品幾何、小物件持續性、複雜遮擋**仍脆弱
- **影片內文字渲染，全模型都不可靠**。Kling 3.0 在短文字（1 到 3 字）上最好，Seedance 2.0 與 Veo 3.1 並列其次。**中文絕對不要交給它渲染**
- 語音會依參考圖推測角色而配錯口音，需 prompt 明確修正
- 官方 demo 全部是廠商挑選過的，丟棄率未知（seedance.tv 評測明確點出這件事）

### 1.5 4 到 15 秒對敘事的影響

**[推理]** 你們現有內容結構是 Hook → 共感 → 知識×3 → 品牌 → 應用 → 立場 → CTA，共 9 拍，換算成影片需要 22 到 35 秒。**Seedance 沒有一鏡到底做完的能力。**

你們 8/13 那支 12 秒六拍的 prompt（「ONE SINGLE CONTINUOUS UNBROKEN TAKE, twelve seconds, no cuts」，六個 beat 按秒分配）是註定要打折的，因為它同時要求：長時間佈局零漂移、六個依序執行的動作、多隻手交替進出畫面、倒酒與碰杯的物理互動。這剛好命中 Seedance 三個公開弱點的交集。

**必須靠剪接。而剪接點正是 AI 影片最容易露餡的地方**：前後鏡頭的色溫、顆粒、景深、光源方向不一致，人眼在 0.3 秒內就抓得到。對策見第 6 節。

---

## 2. 從靜圖到動態的路徑比較

你們手上有：9 張 1079×1350 已排版成品、原始底圖、素材抓取管線。

| 路徑 | 做法 | 成本 | 效果 | 適用 |
|---|---|---|---|---|
| **A. Ken Burns** | ffmpeg zoompan | 0 | 弱。單軸線性位移，觀眾 1 秒內辨識為「投影片」。這正是 Jesse 批評的東西 | 只當底層墊底 |
| **B. 2.5D parallax** | 深度圖 + displace/remap 分層推移 | 0（但需修環境，見下） | 中上。前後景差速移動，人眼讀為「空間」而非「圖片」。單張劇照可撐 3 到 4 秒不膩 | 劇照、街景、有明顯前後景的圖 |
| **C. image-to-video** | Seedance start_image + 微動 prompt | 26 credits/4s | 上。局部真動態（燭火、水面、髮絲、雨、蒸汽、虛焦人流） | 環境底層 |
| **D. motion control** | Kling 3.0 把參考影片動作轉到靜圖角色 | 未實測 | 對 Lava **不適用**。它的價值全在角色表演，而 Lava 不放臉 | 略過 |
| **E. 局部動態遮罩** | PIL 切出區域 → 只讓該區域動 | 0 到 26 credits | 中上。成本可控，露餡面積小 | 混合用 |
| **F. 版面運動** | PIL 逐幀渲染文字/卡片/線條 | 0 | **這是主力**。完全可控、零 AI 味、可綁閱讀節奏 | 全篇 |

### 2.1 本機環境實測（重要，會影響可行性）

**[驗證]** 我剛在你的機器上跑過：

```
ffmpeg 8.1.2 (homebrew)
有：zoompan / xfade / gblur / displace / geq / remap 類 / perspective /
    scroll / shear / rotate / blend / maskedmerge / alphamerge / minterpolate
沒有：drawtext（libfreetype 未編入）
沒有：subtitles / ass（libass 未編入）
```

**所有文字必須走 PIL 渲染，不能用 ffmpeg drawtext。** 這其實是好事，PIL 對中文字距、標點懸掛、行首禁則的控制遠優於 drawtext。

**[驗證]** Python 環境有問題：
- `python3` 解析到 `/Users/mimo/opt/anaconda3/bin/python3`，PIL 9.5.0 可用
- **`import numpy` 直接 Illegal instruction 崩潰**
- homebrew python3 與系統 python3 都沒有 PIL 與 numpy

**這是一個現在就會擋路的問題。** 路徑 B（2.5D parallax）需要 numpy 做逐像素 displace map，PIL 純迴圈做 1080×1920×30fps 會慢到不能用。**修 numpy 是第一件該做的事**，不是選配。

---

## 3. 哪些效果不需要 AI

### 3.1 零成本能做到什麼

| 效果 | 實作 | 說得夠不夠 |
|---|---|---|
| 逐字浮現 | PIL 逐幀 + alpha ramp | **夠，而且是主力**。中文舒適閱讀約 5 到 7 字/秒，逐字浮現讓觀眾**被迫跟著節奏走**，直接解掉 Jesse 說的「不能自己掌握閱讀節奏」 |
| 逐行推入 | PIL translate + ease-out cubic | 夠 |
| 遮罩擦除 | ffmpeg maskedmerge / alphamerge | 夠 |
| 數字翻牌 | PIL 序列 | 夠，資料型 hook 很有效 |
| 卡片堆疊/翻頁 | PIL + perspective | 夠 |
| 圖層視差 | numpy displace（需修環境） | 夠 |
| Ken Burns | zoompan | **不夠，單獨用等於現在的對照組** |
| 底層呼吸感 | 需要真動態 | **不夠，這就是要用 AI 的地方** |

### 3.2 分界線在哪

**程式化夠用的判準：畫面裡沒有「應該會自己動的東西」。**

一張純設計底（漸層、色塊、排版）用 PIL 動起來完全沒問題，觀眾不會期待它有其他動態。

但一張咖啡廳劇照裡有蠟燭、有窗外人流、有杯裡的液體，**這些東西不動，大腦會判定為「靜止照片被硬推」**。這時候才需要 AI 補上局部真動態。

**[推理]** 這條界線給出一個很乾淨的產能規則：**設計底 → 全程式化，零成本；實景底 → 需要一支 4 秒 AI loop。** 一篇 Reels 通常只需要 1 到 2 個實景底。

### 3.3 ping-pong loop：把 4 秒變 8 到 12 秒

**[推理]** ffmpeg 正放接倒放可以把一支 4 秒 clip 變成 8 秒無縫循環，再接一次變 12 秒，成本不變。

**但只對「無方向性動態」有效**：燭火、水面反光、光斑、雨、蒸汽、虛焦人流、布料飄動。

有明確方向的動作（手把手機推過去、倒酒、走路）倒放會立刻穿幫。你們 8/13 生的三支手部 B-roll，全部是有方向性的，**不能 loop**。

**這是素材規劃的關鍵決策：底層 loop 素材一律拍無方向性動態，敘事性動作留給少數不 loop 的關鍵鏡頭。**

---

## 4. 成本模型

### 4.1 計價基礎

**[驗證]** 你們的實際扣款：Seedance 2.5 @ 720p high-bitrate = **6.5 credits/秒**
**[驗證]** Higgsfield Ultra = 3,000 credits/月，$99（年繳）到 $129（月繳）
**[推理]** 換算 **1 credit ≈ $0.033 到 $0.043**，一支 4 秒 720p clip ≈ **$0.86 到 $1.12**

**[驗證]** 網路二手資料（未在你帳號實測）：Seedance **2.0** 720p 5s = 22 credits（4.4 credits/秒），1080p 5s = 45 credits（9 credits/秒）。若屬實，**2.0 比 2.5 便宜約 32%，而且能出 1080p**。這值得用 20 credits 打一次實驗確認。

### 4.2 三種方案，每月 12 篇（每週 3 篇）

假設每篇成片 28 秒，**AI 生成需要 3 倍 retry 才有 1 個可用**（這個係數是保守推理，你們自己的記錄顯示同一個鏡頭確實打了 3 個變體）。

| 方案 | 每篇 AI 秒數 | 含 retry 生成秒數 | credits/篇 | credits/月 | 超額 | 月增額外成本 |
|---|---|---|---|---|---|---|
| **全 AI 生成** | 28 | 84 | 546 + 圖 12 = **558** | **6,700** | +3,700 | 約 **$185**（top-up $5/100 credits） |
| **混合（建議）** | 8（2 支 4 秒，ping-pong 撐 16 到 24 秒畫面） | 24 | 156 + 圖 12 = **168** | **2,016** | 0 | **$0**，留 33% buffer |
| **純程式化** | 0 | 0 | **0** | 0 | 0 | **$0** |

**[驗證]** 若考慮 Unlimited 視窗：Higgsfield 對既有訂閱者的加購價是 1 天 $35 / 7 天 $170 / 14 天 $299，涵蓋 Seedance 2.0 Fast，480p 到 720p，Ultra 可到 15 秒。

**[推理]** 加購不划算。$170 買 7 天，同樣的錢在 top-up 是 3,400 credits，等於 523 秒的 720p 生成。除非你們要做一次性的大量素材囤積（例如一口氣建 30 支底層 loop 素材庫），否則走扣點。

**但「一次性囤 30 支 loop」正是值得做的事**，見第 6 節。

### 4.3 素材複用會大幅改變模型

**[推理]** 混合方案的 168 credits/篇是「每篇都新生」的算法。如果建一個 20 到 30 支的 loop 素材庫（燭火、雨窗、街燈虛焦、咖啡蒸汽、地鐵人流、書頁翻動…），第一個月投入約 30 × 78 = 2,340 credits，之後每篇只需要 0 到 1 支新素材，邊際成本掉到 **50 credits/篇以下**。

**這是唯一能撐住「每週 3 篇、可重複流程」約束的算法。**

---

## 5. 品質風險：AI 味從哪裡露

### 5.1 觀眾實際辨識的線索

**[驗證]** 2026 年公開整理的 AI slop 判準：

| 線索 | Lava 的曝險 | 對策 |
|---|---|---|
| 手指合併、六指 | **高**（你們已經在 prompt 防守） | 手部鏡頭一律人工逐格檢查，或直接不拍手 |
| 皮膚蠟感、過度磨皮 | **高，且觀眾負面反應最強** | 不放臉 |
| 滑步、眨眼太規律或不眨 | 高 | 不放全身、不放臉 |
| 物件在幀間改變形狀/數量/顏色 | 中 | locked-off 鏡頭、簡化桌面物件數 |
| 背景無端漂移 | 中 | prompt 明寫 zero drift，且短鏡頭 |
| 口型對不上 | 高 | **不做人聲，不做 talking head** |
| AI 旁白平板、無換氣 | 高 | 不做 AI 中文旁白 |
| **缺環境音** | 中 | 真實環境不會安靜。你們現在 `generate_audio=false`，**必須自己補環境音層** |
| BGM 與畫面情緒不合 | 中 | 用 IG 音樂庫，順便吃演算法 |
| 畫面內文字錯亂 | **極高** | **所有中文一律 PIL 疊上去，prompt 明寫 no text, no signage, no writing** |

**[驗證]** 只有 9.5% 的人能穩定分辨 AI 影片與實拍。但這不代表可以放心：分辨不出來的是**好的 AI 影片**，Lava 的品牌禁忌是「AI 味」，而 AI 味是低品質 AI 的特徵，不是 AI 本身的特徵。

### 5.2 一個結構性風險：C2PA 標籤

**[驗證]** Meta 讀取 C2PA provenance metadata，命中就在 Reels 掛「AI info」標籤。OpenAI、Midjourney、Adobe Firefly、Leonardo 都已在 2026 年生成物寫入 C2PA。

**[驗證]** 平台本身**不降觸及**。但**當觀眾被告知內容是 AI 生成，52% 的人自述參與意願下降**。

**[待查]** Higgsfield 的 Seedance 輸出是否帶 C2PA。可以用 `exiftool` 或 `ffprobe` 檢查已下載的 mp4，5 分鐘可驗。

**[推理]** 這是個政策決定不是技術決定。Lava 的成片是混合製作（AI 底 + 人工排版 + 引用素材），本來就不是純 AI 生成。建議 Jesse 自己定一個明確標註政策，例如「使用 AI 輔助生成的畫面時在 caption 註明」，而不是靠重新編碼把 metadata 洗掉。品牌禁忌是「AI 味」，不是「用了 AI」，這兩件事混在一起處理反而危險。

### 5.3 你們現有 prompt 的評價

**[驗證]** 我讀過 8/12 到 8/13 的實際 prompt，寫得比市面上多數教學好。做對的：
- `No faces and no bodies, only a forearm and hand`（正確迴避最大風險）
- `camera locked off on a tripod and never moving`（正確，減少 drift）
- `Anatomically correct hand with exactly five fingers and one thumb`（負向約束）
- `no beauty smoothing`、`visible skin pores`（正確反制蠟感）
- `Shot on 35mm film, natural grain`（正確，顆粒掩蓋 AI 平滑感）
- `no yellow color cast`（正確，AI 影片的暖調偏移是隱性 tell）

做錯的：
- **12 秒六拍一鏡到底**，超出模型能力邊界
- **16:9 而不是 9:16**，Reels 用會浪費 44% 的畫面或需二次裁切
- **全部跑 2.5 而不是 2.0**，自己把畫質壓在 720p
- `generate_audio=false` 但沒有規劃補環境音，會落入「缺環境音」這條 tell

---

## 6. 工作流建議

### 前置（一次性，本週該做）

| 步驟 | 工具 | 說明 |
|---|---|---|
| P1 修 numpy | conda / brew | 解掉 Illegal instruction，否則 parallax 與逐幀合成走不了 |
| P2 建 motion primitive 函式庫 | PIL + Python | 逐字浮現、逐行推入、遮罩擦除、卡片堆疊、數字翻牌、視差推移，各一個可參數化函式。**這是可重複流程的核心資產** |
| P3 囤 loop 素材庫 | Soul V2 生圖 + Seedance 2.0 fast | 20 到 30 支 4 秒無方向性動態，9:16。約 2,000 credits 一次投入 |
| P4 統一 LUT + grain 配方 | ffmpeg lut3d + noise | 所有 AI 素材過同一組色彩與顆粒，解決剪接點色溫不一致的露餡 |
| P5 驗 C2PA | ffprobe / exiftool | 5 分鐘，決定標註政策 |

### 每篇（目標 90 分鐘內）

| 步驟 | 工具 | 產出 |
|---|---|---|
| 1. 文案 → 節拍表 | Claude（改寫現有 WF01） | 不再是 9 張 slide，改成 **10 到 14 個節拍**，每拍 1.5 到 3 秒，總長 24 到 32 秒。每拍標：文字內容、進場方式、底層素材 ID、音效點 |
| 2. 底層調度 | 查素材庫 | 能複用就複用。缺的才生成 |
| 3.（需要時）生底 | Soul V2 → Seedance **2.0** fast，720p，**9:16**，4s，generate_audio=false，locked-off，無方向性動態，prompt 明寫 no text | 3 變體選 1 |
| 4. loop 加工 | ffmpeg ping-pong + LUT + grain | 4s → 8 到 12s |
| 5. 文字層 | PIL 逐幀 → 透明 PNG 序列 | 1080×1920。**節奏綁閱讀速度，中文 5 到 7 字/秒** |
| 6. 合成 | ffmpeg overlay + xfade | 1080×1920 / 30fps / H.264 |
| 7. 音 | **IG 內建音樂庫**，不用 AI 人聲 | 零成本，且進入該曲 feed 有額外分發 |
| 8. QA | lava-ig-critic skill + Higgsfield `virality_predictor` | 後者你們帳號已有，可當第二意見。前三秒逐幀看 |

### 前三秒的具體規格

**[驗證]** Reels 3 秒留存率的分發門檻：>70% 觸發第二階段分發（推給非追蹤者）。>60% 的貼文總觸及比 <40% 的高 5 到 10 倍。平均跳出率 20% 到 35%，>40% 代表 hook 有問題。

**[驗證]** 各類 hook 的 3 秒留存：Pattern Interrupt 72% 到 84%，Curiosity Gap 65% 到 78%，Direct Question 58% 到 72%，Bold Claim 55% 到 70%。

**[推理]** 對 Lava 這代表：**前 3 秒必須是 Pattern Interrupt 或 Curiosity Gap，且第 0 幀就要有文字。** 不要用 0.5 秒的品牌動畫開場，不要用淡入。第 1 幀就是完整的鉤子文字，畫面在動。

---

## 7. 我方案裡最弱的一環

**最弱的是驗證迴圈比迭代速度慢，這一點無解，只能繞。**

@lava_dating 200 追蹤、單篇觸及 200 到 260。以每週 3 篇的產能，要判斷「動起來有沒有用」，用觸及當指標，需要累積 8 到 12 週才有可讀訊號，而那時候市場已經換過一輪。**投影片轉檔版跑兩篇當對照組，樣本量小到單篇差異幾乎全是噪音，這個對照組實際上不會給出可信結論。**

繞法：**不要看觸及，只看 IG Reels 分析裡的 3 秒留存率。** 它是演算法的直接輸入，對樣本量的要求遠低於觸及（觸及本身受分發階段跳躍影響，方差極大），而且它直接對應 Jesse 擔心的那件事。設一個硬門檻：3 秒留存 <55% 的做法直接砍掉，不用等觸及數據。

其他弱點，依嚴重度排序：

2. **剪接點是最大的技術風險，我的對策（統一 LUT + grain）只是遮蓋不是解決。** 真正的解法是全篇共用同一個 start_image 家族，但那會犧牲視覺變化。這個 trade-off 我沒有好答案。

3. **ping-pong loop 是成本模型的支柱，但它限制了素材類型。** 一旦內容需要敘事性動作（例如「兩個人交換手機」這種具體場景），成本模型立刻回到 168 credits/篇甚至更高。我的成本表假設「大多數篇章只需要氛圍底」，這個假設沒有驗證過。

4. **numpy 壞掉，2.5D parallax 這條零成本路徑現在是空頭支票。** 我把它列在方案裡，但沒有實測過修好之後的算繪速度。1080×1920×30fps×30 秒 = 900 幀逐像素 displace，即使有 numpy 也可能要幾分鐘，會不會拖垮每週 3 篇的節奏，我不知道。

5. **Seedance 2.0 的計價是二手資料。** 我建議改用 2.0（更便宜、能 1080p），但 4.4 credits/秒這個數字來自網路評測，不是你們帳號的交易記錄。花 20 credits 打一次 4 秒 720p 就能驗證，做決策前應該先驗。

6. **對標帳號的數據我沒有查證。** @thewknd.club 46K、breeze.social 64.6K、heavenraven 那篇 27.7k 讚，這些是你們給的，我沒有獨立驗證，也沒有看過他們的 Reels 實際做法。**如果要真的抄結構，需要單獨一輪把這三個帳號的 Reels 逐支拆解**，那是另一個任務。

---

## 8. 建議的下一步（依序，不要跳）

1. 修 numpy，驗 Seedance 2.0 計價，驗 C2PA。三件事加起來不到 1 小時、不到 30 credits
2. 用**一篇既有貼文**做兩個版本：純程式化版（0 credits）vs 混合版（約 170 credits）。不發，先給 Jesse 看
3. Jesse 選定方向後，才建 motion primitive 函式庫與 loop 素材庫
4. 前 4 篇只追蹤 3 秒留存率，不看觸及

**Sources:**
- [Seedance 2.0 Review | VERTU](https://vertu.com/ai-tools/bytedance-seedance-2-0-ai-video-revolution-disrupting-film-and-advertising-industries)
- [Seedance 2.5 Review: Morphing Bugs | MindStudio](https://www.mindstudio.ai/blog/seedance-2-5-review-guide)
- [Seedance 2.5 Review 2026 | Seedance.tv](https://www.seedance.tv/blog/seedance-2-5-review-2026)
- [Seedance 2.5 vs 2.0 | PixVerse](https://pixverse.ai/en/blog/seedance-2-5-vs-seedance-2-0)
- [Seedance 2.0 Pricing on Higgsfield](https://higgsfield.ai/blog/seedance-2-0-pricing-2026)
- [Seedance 2.5 Pricing on Higgsfield](https://higgsfield.ai/blog/seedance-2-5-pricing-2026)
- [Higgsfield Seedance 2 Unlimited](https://geo.higgsfield.ai/task/blog/higgsfield-seedance-2-unlimited-worth-it)
- [Higgsfield Pricing 2026 | Scopeful](https://www.scopeful.org/tools/higgsfield)
- [Best AI Video Models 2026 | Teamday](https://www.teamday.ai/blog/best-ai-video-models-2026)
- [Seedance 1.5 pro 論文 | arXiv 2512.13507](https://arxiv.org/pdf/2512.13507)
- [AI Slop: 12 Tells | OpusClip](https://www.opus.pro/blog/ai-slop-aesthetic-12-tells)
- [55 AI-Generated Video Statistics | Kapwing](https://www.kapwing.com/resources/55-ai-generated-video-statistics-disclosure-detection-and-trust/)
- [Instagram Reels Skip Rate Benchmarks 2026 | Retensis](https://retensis.com/blog/instagram-reels-skip-rate-benchmarks-2026)
- [Hook Rate, Hold Rate, Completion Rate | CreatorHouse](https://creatorhouse.app/blog/instagram-reel-hook-rate-hold-rate-completion-rate-benchmarks)
- [Will AI Content Hurt Your Reach in 2026 | Getix](https://getixgroup.com/blog/does-ai-content-hurt-social-reach-2026)
- [Platform AI Labeling in 2026 | Billo](https://billo.app/blog/ai-labeling/)
- [Ken Burns Effect with FFmpeg | mko.re](https://mko.re/blog/ken-burns-ffmpeg/)
- [Depth Anything](https://depthanything.org/)
- [Kling 3.0 Motion Control | Media.io](https://www.media.io/ai/motion-control/kling-3-0)