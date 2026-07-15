// 操控室設定。部署前把 owner/repo 改成實際值；PAT 於網頁「設定」貼入、存 localStorage，不寫在此。
window.LAVA_CONFIG = {
  owner: "muxiliu512",          // 已確認（2026-07-15）
  repo: "lava-ig-console",
  branch: "main",
  // mode: "auto" 會在 file:// 或 localhost 用本地檔預覽，部署到 github.io 則走 API。
  mode: "auto",                 // "auto" | "local" | "github"
  // 公開 repo：圖片走 raw.githubusercontent.com（快、不耗 API 額度）。
  publicRaw: true,
  ig_handle: "lava_dating",
  ig_name: "Lava",
};
