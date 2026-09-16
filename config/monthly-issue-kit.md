# 月刊輪播工具包（Prompt ＋ 版面規格）

> 這是「每月一號」IG 輪播的可重複使用配方。2026-08 七夕月建立雛形、2026-09 中秋月定案。
> 三個部分：**一、生圖 Prompt**（封面照、圖素、紙質）｜**二、版面 Design System**（每一頁的數值）｜**三、產製與驗收流程**。
> 每個 `[方括號]` 是每期要換的變數，其他一字不動。
> 正本色值與字體以 `brain/products/lava/design-system.md` 為準；本檔只寫「月刊」這個型態怎麼用它。

---

## 〇、這一型的賭注

一期講完六件事，用雜誌的語言而不是簡報的語言。讀者滑完八張，記得的是「Lava 每個月出一本」，不是六個功能。
所以三件事不能省：**刊名固定版式**（每月一眼認得出是同一本）、**跨頁連續**（滑動時有東西接得上，證明這是一本不是八張）、**手工圖素**（AI 照片以外的一層人味）。

---

# 一、生圖 Prompt

工具：Higgsfield CLI。中文一律用 HTML 排，**不要叫模型寫任何文字**，所有 prompt 結尾固定接：
`No text, no letters, no logos, no watermark.`

## 1-1 封面照（人物）

模型：`nano_banana_pro`（穩、寫實）。
實測：`cinematic_studio_2_5` 在「seamless 深色棚背」這個要求上兩次都沒守住（一次給白底、一次給戶外實景），月刊封面不要再用它。

```
Editorial fashion magazine cover photography: a stylish East Asian couple in their
late twenties [互動動作與表情], each holding [成雙的節慶物件],
waist-up composition with their heads in the upper third of the frame,
a clear vertical gap between the two people at the centre of the frame,
seamless deep charcoal studio backdrop, hard direct on-camera flash with crisp shadows,
high-fashion styling ([服裝：暖色系，橘／酒紅／米]), high contrast, sharp focus,
premium magazine cover quality, natural candid [情緒].
No text, no letters, no logos, no watermark.
```

```bash
higgsfield generate create nano_banana_pro --prompt "<上面那段>" --aspect-ratio 4:5 --resolution 2k --json
```

**為什麼每一句都在**

| 句子 | 少了會怎樣 |
|---|---|
| `heads in the upper third` | 頭落到畫面中段，刊名壓不到人，變成漂在空中的字 |
| `clear vertical gap ... at the centre` | 中間那個字被臉擋掉 |
| `seamless deep charcoal studio backdrop` | 背景有東西，奶油色刊名讀不出來 |
| `hard direct on-camera flash with crisp shadows` | 變成糖水棚拍，失去編輯感 |
| `each holding [成雙物件]` | 節慶訊息沒有載體；物件成雙才呼應配對語意 |

**淘汰規則（生 4 張選 1，逐張放大看）**

1. 物件表面有浮雕花紋時，放大看是不是偽漢字。有就淘汰——這是最常見的失敗，縮圖看不出來。
2. 手指數量與關節。
3. 男方頭頂 y 要落在 **190–330**（版面 1080×1350 座標）。太高會蓋掉頁首細字列，太低刊名壓不到人。
4. 背景必須是無縫單色，有牆角、窗框、家具就淘汰。

**去背（做「刊名壓在人後面」的那一層）**

```bash
higgsfield generate create image_background_remover --image-references ./cover.png --json
higgsfield generate get <job_id> --json      # 輪詢，不要用 --wait
```

`--wait` 在去背這個 job 上實測會卡住十分鐘不回應；改用輪詢約一分鐘完成。
回來是 RGBA PNG。用 PIL 確認 `mode == "RGBA"`，再把 alpha 收 1px（`MinFilter(3)`）加 0.6px 柔邊，避免髮絲外圈一條半透明底色帶。

## 1-2 節慶圖素（版畫風，黑底可去背）

模型：`gpt_image_2`。
`nano_banana_pro` 對「paper / texture / print」這類字眼會誤判成 nsfw 連續退件，紙質與圖素都走 gpt_image_2。

```
[圖素主體描述，例：a full moon with visible maria], risograph two-color screen print,
only two inks: cream #FFE6A9 and orange #E84224, pure black #000000 background,
coarse halftone grain, slight ink misregistration, flat shapes, no gradients,
no realism, centred composition.
No text, no letters, no logos, no watermark.
```

```bash
higgsfield generate create gpt_image_2 --prompt "<上面那段>" --aspect-ratio 1:1 --resolution 2k --json
```

**黑底不是美觀選擇，是技術選擇**：疊到深色版面時用 `mix-blend-mode: screen`，純黑會變全透明，不必再去背。所以 `pure black #000000 background` 這句不能刪。

**驗收（自動，不合格就重生）**

- 四角各取 64×64，RGB 每通道平均 < 12。超過表示背景不是純黑，screen 之後會出現方塊。
- 非黑像素的色相只能落在 cream／orange 兩桶，其他色 = 0。
- 放大看有沒有文字。

**再用 PIL 做一個 `_trim` 版**（裁掉四周純黑空白、留 8px 黑邊），排版時才好抓尺寸。
`manifest.json` 每筆記 `file / trim_file / name / ink / size / trim_size / bbox_ratio / notes`。

**中秋月已有的八個**（可直接重用）：滿月、三個月相、紙燈籠、玉兔、桂花枝、月餅（切一角）、柚子、星點。
下一期只要生該節慶缺的，風格字串照抄就會同調。

## 1-3 紙質

```
dark warm charcoal recycled paper texture, subtle visible fibers and fine grain,
evenly lit, flat, edge-to-edge, no objects, no vignette.
No text, no letters, no logos, no watermark.
```

```
warm cream uncoated paper texture, subtle fibers, evenly lit, flat, edge-to-edge,
no objects, no vignette.
No text, no letters, no logos, no watermark.
```

驗收：深色紙平均亮度 30–70（0–255），奶油紙 200–235。奶油紙生出來多半偏黃，用 PIL 逐通道位移對齊 `#FFE6A9` 再存。

---

# 二、版面 Design System

畫布 **1080×1350**。出圖走 HTML/CSS → 無頭 Chrome，`build.py` 的 `build_one()`。

## 2-0 全域

| 項目 | 值 |
|---|---|
| 底色 | Olive Dark `#0C0E08` |
| 主文字 | Cream `#FFE6A9`；封面刊名用 `#F5E6C8`（八月取樣值，略淡） |
| 強調 | Lava Orange `#E84224` |
| 尾板底 | Wine `#741017` |
| 中文 | HarmonyOS Sans TC，只有 Thin / Regular / Medium。**沒有 Bold**，重量靠字級與對比做，不要指望字重 |
| 英文與數字 | Inter |
| 中文大標 | `text-indent:-.045em`，左緣才對得齊小字 |
| 字級跳幅 | 相鄰層級至少 2 倍 |
| 線 | 同一視覺區最多一條 hairline |
| 紙質 | `mix-blend-mode: screen`，**不要用 overlay**（overlay 在暗底是 2ab，會更黑）。透明度反算：合成亮度 = 底 12 + 64α，目標 18–33 → α 取 .22 |
| 圖素 | `mix-blend-mode: screen`，opacity .62–.70。透明度與混色模式要寫在**同一個 `<img>`** 上；放在外層 div 會讓它變成獨立合成群組，黑底整塊露出來 |

## 2-1 封面（每期唯一不可重新設計的一頁）

圖層由下到上，順序就是雜誌感的來源：

```
底圖 → 上 scrim → 頁首細字列 ＋ hairline → Lava 字標 → 中文刊名 → 【去背人物層】 → 下 scrim → 顆粒 → 目錄行 → 橘圓箭頭 → 往右滑
```

去背人物層**壓在刊名之上**。這一層就是「標題壓在圖裡」的全部機制，用漸層把底圖推開不算數。

| 元件 | 數值 |
|---|---|
| 頁首細字列 | y 66，左 x 66、右 x 71；Inter 600 / 22px / 字距 .22em |
| 頁首 hairline | y 105，x 64–1015，奶油色 alpha .27（很淡，量得到但幾乎看不見） |
| Lava 字標 | top 112，高 36，置中 |
| 中文刊名 | 三字**墨寬 552px**（不是字級 552）；字距 .04em、負縮排 .045em；墨頂 y≈191 |
| 字標底 → 刊名墨頂 | **≥ 40px**（八月 22px，九月拉到 43px；Jesse 明確要求比八月寬） |
| 人物遮住第一個字 | 30–45%，且三字都要認得出來。比例是手段，legibility 才是判準 |
| 目錄行 | y 1058，置中，32px，項目間 `·` |
| 橘圓箭頭 | 圓心 (540, 1192)，直徑 94 |
| 往右滑 | y 1254，置中，24px |
| 底部 | **沒有** hairline、**沒有**資訊列 |

底部 scrim 只壓 y ≥ 900，且要壓到目錄行的最差對比 ≥ 4.5:1（做法：另出一張隱藏目錄行的圖，量墨底下的背景亮度）。

**三字墨寬要量不要猜**：字級與墨寬不是線性直覺。中秋月第一次用 172px 得到 479px 墨寬，比八月小 13%，刊名就「浮在畫面上」。放大到 198px 才對齊 552。每期換字一定重量一次。

## 2-2 內頁版型 A：連續字帶（B2）

七張內頁共用**同一份**英文字帶 DOM，總寬 7×1080，第 k 張把它往左推 k×1080 再用畫布裁掉。連續性是結構保證的，不是對出來的。

| 元件 | 數值 |
|---|---|
| 唯一左軸 | x = 96（細字、章節標、字帶、中文全部貼這條線） |
| hairline | y 96 / 904 / 1206 |
| 頁首細字 | y 56；頁尾細字 y 1230 |
| 章節標 | x 96, y 144；Inter 600 24px，橘色，`<b>02</b>` 後留 32px |
| 字帶視窗 | bottom 828，兩行，行高 .80 |
| 上排長字 | 一律 **8 個字母**，逐字微調字距讓每個字寬 = 1032px → 每張剛好溢出 48px 到下一張左緣，下一張的字從 96 開始，中間留 48 |
| 下排關鍵字 | 自然字距，右緣必須 < 984 |
| 中文區 | x 96, top 944；h1 72/92，內文 32/50 |
| 圖素 A 區 | 章節標與字帶之間；bottom = 430（離字帶 48），右緣貼 984，高 250–280 |

**字寬一定用無頭 Chrome 量**（`--dump-dom` + `getBoundingClientRect`）。第一版用「每字母 0.478em」估，實際是 0.55–0.58em，長字溢出 300px 直接壓在下一張的字上。生成器要內建 `verify()`：溢出量不在 48±3 就中止出圖。

**每張的長字＋關鍵字要跟那張的內容對得上**，不要湊成一句話——湊出來的句子讀者看不出來，只會讓選詞遷就句法。

## 2-3 內頁版型 B：成對色塊（C2）

六張內頁分三組：(1,2) (3,4) (5,6)。同組共用色塊下緣 FL，奇數張色塊靠右出血、偶數張靠左出血，滑過去是一塊 1392px 寬的奶油紙橫跨兩張。

| 元件 | 數值 |
|---|---|
| 深底文字軸 | x = 84 |
| 色塊內文字 | x = 84（左出血）或 480（右出血） |
| 色塊 | 寬 704，出血 8px；同組 FL 相同（中秋月用 600 / 620 / 640） |
| 幾何驗算 | B = FL + 300 + 130 × 主標行數，出圖前 assert |
| 引文區 | 寬 516，**bottom 錨定**（底 = FL − 120），離序號方塊 54px |
| 引文括弧 | 獨立一欄 72px，字級 160。左張括弧欄在左、右張在右 |
| 引文斷行 | 由人寫在 `copy.json` 的 `\n`，每行 ≤ 10 個全形字。**不要交給 `text-wrap:balance`**，它不認得「安然無恙」是一個詞，會從中間切 |
| 序號方塊 | 132×132 橘底，top = FL − 66 |
| 主標 | top = FL + 108；116/130 |
| 圖素 | 色塊旁的深底直欄（左張 x 84–300、右張 x 780–996，y 176–476），離頁首 ≥72、離序號方塊 ≥58 |
| 頁首翻色 | 細字列與 hairline 在色塊上翻成深色，用 clip-path。**inset 是相對元素**（left:84 right:84），不是相對畫布，要先減掉 84 |

**括弧成對**：同一組左張只有 `「`、右張只有 `」`，兩張並排讀起來是一句被引號括住的完整話。引文寫成「一組一句」：左半以逗號結尾、右半以句號結尾。

**色塊漸層**：同組共用一條 1392px 的 `linear-gradient`（`#FFE2A0 → #FFF3D6`），用 `background-size:1392px 100%` 切兩半，右張 `background-position:-688px`。紙質也要用同一組 size/position 切半，否則接縫會出現紙紋跳接。驗收：左張最右一欄 vs 右張最左一欄，RGB 差平均 ≤ 3。

## 2-4 尾板

- 版型 A：字帶的第 7 段 ＋ 中文「出來見面吧」＋ 免責。
- 版型 B：Wine 色塊 700px ＋ 176px 主標 ＋ 免責 ＋ slogan。
- 免責長句在「，」處手動斷行，不要讓最後一行只剩兩個字。

---

# 三、產製與驗收流程

1. **文案先定**：`spec/copy.json`。刊名、英文刊名、封面目錄行（3 項）、六張的 section / headline / sub[3]、caption、免責。
2. **生素材**：封面照 4 選 1 → 去背；缺的節慶圖素；紙質沿用。
3. **出圖**：生成器（`gen_cover.py` ＋ `gen_B2.py` / `gen_C2.py`）→ `build_one()`。
4. **自動驗收**（寫在生成器裡，不過就中止出圖）：
   - 字帶溢出量 48±3
   - 圖素框離任何文字 ≥ 48px、不超出 96–984
   - C 版 B = FL + 300 + 130n
   - 背景亮度 18–33
   - 色塊接縫 RGB 差 ≤ 3
5. **圖像識別驗收**（人或代理逐張讀 PNG，這一關不能跳）：
   - 跨頁並排圖（`qa_sheets.py`）：字帶接得上？色塊連續？括弧成對？
   - 封面與上一期並排：刊名墨寬、字標間距、遮蔽比例
   - 每張全解析度：有沒有壓字、斷行孤字、對齊跑掉
6. **交付**：Drive `02_Marketing/05_貼文規劃/<YYYYMMDD> LAVA<刊名>/`，含成品、素材、文案包。

## 踩過的坑（別再踩一次）

| 坑 | 症狀 | 解法 |
|---|---|---|
| 估字寬 | 圖出得來，但長字壓在下一張的字上 | 用無頭 Chrome 量，生成器內建驗證 |
| `--wait` 卡去背 | 十分鐘沒回應 | 送單後用 `generate get` 輪詢 |
| opacity 放外層 div | 圖素的黑底整塊露出來 | opacity 與 blend-mode 放同一個 `<img>` |
| overlay 疊暗底 | 越疊越黑 | 用 screen |
| `text-wrap:balance` | 「安然無恙」被切成兩半 | 斷行寫死在文案裡 |
| clip-path inset 用畫布座標 | 翻色位置整個偏掉 | inset 相對元素，先減掉元素左緣 |
| 用字數估行數 | 引文多一行就壓到序號方塊 | 改 bottom 錨定 |
| 刊名字級照抄上期 | 換字後墨寬不一樣，刊名浮起來 | 每期量墨寬對齊 552 |
