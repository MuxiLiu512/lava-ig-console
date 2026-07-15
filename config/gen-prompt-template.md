# 生圖 Prompt 模板（機器可改層）

> 迭代 harness（排程B）可增修本檔。正本風格規格在 Google Drive，不動。
> 每張 slide 的 `visual_concept_en` 由撰稿產生；本檔提供全域前後綴與負面清單。

## 全域正向後綴（依 mood 追加）
- lively → `bright natural daylight, vibrant fresh`
- warm → `soft warm daylight, airy bright interior, gentle warmth`（禁 heavy golden hour）
- dark → `cool blue hour, cinematic clean shadows, muted but readable`（禁 pitch-black gloom）
- 含人物一律追加 → `photorealistic, anatomically correct`

## 全域負面 prompt（每張都帶）
```
deformed fingers, extra fingers, fused fingers, mutated hands, bad anatomy,
extra limbs, missing limbs, distorted face, asymmetric eyes, watermark,
signature, text overlay, logo, lowres, jpeg artifacts, oversaturated,
pitch-black shadows, plastic skin
```

## 生成參數（現行）
- 引擎：Higgsfield `seedream_v4_5`
- 比例：3:4（1950×2600 對齊版型）
- 每張候選張數：預設 2（供操控室並排選圖）

## 高風險姿勢迴避（硬規則）
禁手持物特寫；改物件靜物／背影剪影／遠景／手藏。
