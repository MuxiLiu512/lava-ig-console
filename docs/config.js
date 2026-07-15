// 操控室設定。部署前把 owner/repo 改成實際值；PAT 於網頁「設定」貼入、存 localStorage，不寫在此。
window.LAVA_CONFIG = {
  owner: "muxiliu512",          // TODO: 確認 GitHub 帳號
  repo: "lava-ig-console",
  branch: "main",
  // mode: "auto" 會在 file:// 或 localhost 用本地檔預覽，部署到 github.io 則走 API。
  mode: "auto",                 // "auto" | "local" | "github"
  // 公開 repo 可設 true → 圖片走 raw.githubusercontent.com（快、不耗 API 額度）。
  // 私有 repo 保持 false → 圖片透過 Contents API 以 blob 載入（需 PAT）。
  publicRaw: false,
  ig_handle: "lava_dating",
  ig_name: "Lava",
};
