# Reels 生成 prompt 正本

這份檔案是 Reels 各段落 prompt 的**唯一真相**。`scripts/reel_produce.py` 讀它組 prompt，
`scripts/iterate_harness.py` 依 Jesse 的退回意見在末尾追加規則（與 `style-notes.md` 同一套機制）。

改這裡＝改所有未來的 Reels。不要在 Python 裡寫死 prompt。

---

## §角色（character）

角色一次生成、長期重用。除非 Jesse 要求換人，否則永遠沿用 `data/reels_cast.json` 裡的既有角色。
重生成一次只要 0.12 點，但**換人會讓帳號的臉不連續**，這比省下的錢重要。

骨架（soul_2、3:4、2k）：

```
A [年齡帶] [woman/man], [中途表情], [髮色長度與層次], [體型], with high model facial features,
symmetrical features, well-proportioned figure, natural skin texture, [五官特徵描述，不要直接寫族裔],
standing in [具體場景與建材細節].
Cool neutral overcast daylight falls across the face from [方向] — neutral, clean, no warm cast,
no retouched glow, no golden hour, no amber tone. Skin texture is real, with visible pores and
natural unevenness.
[He/She] wears [服裝；高領、不露胸腹、不透、full coverage、modest neckline].
Body in a calm neutral pose. The background features [具體物件].
Color palette dominated by [冷色中性調].
Self-portrait selfie shot on iPhone front-facing camera held by the subject at arm's length —
head and shoulders fill the frame, casual handheld framing, slight natural tilt, slightly off-center,
slightly imperfect, not posed. Phone-sensor grain and realistic skin texture preserved, no retouch,
no smooth-skin filter. No fisheye lens, no ultra-wide distortion. Authentic UGC creator phone selfie,
NOT editorial portrait, NOT fashion magazine.
```

## §分鏡（board）

gpt_image_2、21:9、2k、high。八個等寬 9:16 直式格子排成**一橫排**，不是兩排也不是格狀。
`@Image1` 是角色參考，必須明寫「同一個人出現在八格裡，臉型髮長服裝完全一致」。
場景與光線八格一致。八格＝一支 clip 內的八個敘事節拍。
禁止任何文字、數字、標題、邊框。

## §口播段（talk）

seedance_2_5、9:16、1080p、`mode: omni_reference`、`generate_audio: true`。
medias 順序：分鏡 job id、角色 job id。

台詞規則（**這段是 Jesse 退回意見會累積的地方**）：
- 台灣中文口語，Taipei accent，relaxed everyday speech，**不要新聞主播腔、不要配音腔**
- 一句話一個意思，不要子句套子句
- 禁用破折號、「不是…而是…」（與貼文同一套禁句，見 style-notes.md §絕對禁止句式）
- 角色是**主持人不是用戶**：可以介紹 Lava 是什麼，不可以宣稱自己用過、約成功、認識了誰。
  捏造證言是平台紅線，也是廣告法紅線。

## §空景段（broll）

seedance_2_5、9:16、**720p、`generate_audio: false`**、`mode: t2v`。
沒有講話就不需要 1080p 與語音，單價從 9 點/秒降到 6.5 點/秒。
用途：情緒空鏡、街景、餐桌、手部特寫。**不要出現人臉**（會與主角撞臉）。

## §自有素材段（own）

我們自己的檔案：品牌照片、App 螢幕錄影、產品原型。**零成本**。
Reels 裡混入自有素材是降低成本最有效的一招，也是 breeze 那支的做法
（產品畫面只閃過一秒，不是廣告畫面，是使用畫面）。

## §字卡段（cards）

走 `scripts/render_reel.py`，零成本。
支援螢光筆標記（`hl` / `hl_frac`）：關鍵詞下半部掃過半透明色帶，字保持原色，
可逐字推進做出「講到哪標到哪」（參考 morning.jason 2026-08-27）。

---

## §依回饋累積的規則

（`iterate_harness.py` 會把 Jesse 退回 Reels 的意見追加到這裡。手動編輯也可以。）
