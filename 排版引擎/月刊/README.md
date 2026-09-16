# 月刊輪播生成器（中秋月 2026-09 定案版）

配方與版面數值在 [`config/monthly-issue-kit.md`](../../config/monthly-issue-kit.md)。
這裡是那份配方的可執行版本，存進 repo 是為了不讓它只活在某一期的資料夾裡。

## 檔案

| 檔 | 做什麼 |
|---|---|
| `build.py` | HTML → 無頭 Chrome → 精準 1080×1350 PNG，含三條「圖出得來但其實壞了」的自我檢查 |
| `gen_cover.py` | 封面（兩版共用）。八月圖層版式：底圖 → 刊名 → 去背人物層 → 底部資訊。內建 `measure()` 從出圖量字標間距與遮蔽比例 |
| `gen_B2.py` | 內頁版型 A「連續字帶」。字寬用無頭 Chrome 實測、`verify()` 擋溢出量、`check_layout()` 擋圖素間距 |
| `gen_C2.py` | 內頁版型 B「成對色塊」。成對 FL、括弧左右成對、色塊漸層切半、翻色 clip-path |
| `qa_sheets.py` | 跨頁並排圖與接縫圖，給圖像識別驗收用 |
| `copy.example.json` | 中秋月的文案結構，新一期照這個欄位填 |

## 開新一期

```bash
cp -r lava-ig-console/排版引擎/月刊 貼文製造機器人/十月號
```

然後在 `十月號/` 底下補兩個資料夾，生成器靠相對路徑找它們：

- `spec/copy.json` —— 由 `copy.example.json` 改寫
- `素材/` —— 字型、logo、封面照與去背層、`textures/`、`elements/`（含 `manifest.json`）

中秋月的八個節慶圖素可直接沿用，在
Drive `02_Marketing/05_貼文規劃/20260916 LAVA中秋月/素材/中秋圖素/`。

## 注意

- 生成器只用 PIL，不要引入 numpy（哨兵跑的 anaconda 3.7 x86_64 會 Illegal instruction）。
- 字型 HarmonyOS Sans TC 只有 Thin/Regular/Medium，沒有 Bold。
- 每個 assert 與 `SystemExit` 都是為了擋一種「圖出得來但其實壞了」。不要註解掉它們。
