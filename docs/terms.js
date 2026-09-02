/* 詞彙表 — 全站唯一字典〔藍圖 UI 規格 §8〕
   任何顯示字串必經 t(key)。內部術語（策展、缺料、SHOT、forage、QC、render、
   status 原文）一律不得直出 UI。新增介面字串必須先進此表；一詞一義。
   載入順序：config → core → terms → ui → 頁面。 */
(() => {
"use strict";

// key → [介面詞, tooltip 定義]
const TERMS = {
  // 狀態機
  awaiting_review: ["等你審", "系統做完了，等你點進去看"],
  approved:        ["等你排時間", "你已核准，選個發佈時間就完成"],
  scheduled:       ["已排程", "會在指定時間自動發佈"],
  published:       ["已發佈", "已上 IG"],
  rejected:        ["已退回", "你退回了，這一版不會再出現"],
  redoing:         ["重做中", "你退回了，系統正按你的原因重做"],
  making:          ["系統製作中", "撰稿與素材生成進行中，完成會回到佇列"],
  fixing_images:   ["系統補圖中", "有版位沒有可用的圖，系統正在補"],

  // 素材與產線
  missing_image:   ["缺圖", "這張沒有可用的圖，需要補圖或改用文字卡"],
  forage:          ["找圖", "系統從影劇畫面與圖庫幫這張找候選圖"],
  shot:            ["畫面截圖", "從影劇畫面截下來的候選圖"],
  apify:           ["網路參考圖", "從網路圖庫找到的候選圖"],
  generated:       ["AI 生成圖", "由 AI 依這張的文案生成"],
  still:           ["劇照", "出自影集／電影的畫面"],
  design_layout:   ["設計版面", "由引擎繪製的卡片，不需要照片"],
  render:          ["排版", "把文字壓上底圖做成成品"],
  qa:              ["品檢", "發佈前的自動檢查（錯字、排版、禁句）"],
  candidates:      ["候選圖", "同一張版位可選的底圖"],
  slide:           ["第 N 張", "carousel 的一頁"],
  caption:         ["貼文文案", "IG 貼文下方的文字"],
  display_copy:    ["圖上文字", "壓在圖上的那幾行字"],
  hook:            ["開頭鉤子", "第一張用來讓人停下滑動的句子"],
  credits:         ["點數", "生成的花費單位（重做會再花）"],
  proposals:       ["改進提案", "系統想調整產法，等你點頭"],
  iterate_log:     ["調整紀錄", "系統歷次調整的清單，可回滾"],
  heartbeat:       ["產線心跳", "系統最後一次正常運作的時間"],
  gate_copy:       ["文案檢查", "禁句與禁用詞的自動檢查"],
  gate_fact:       ["事實查核", "每個數字與引用都要有活的出處"],
  gate_visual:     ["視覺檢查", "撞主體、浮水印、不可讀的自動檢查"],
  gate_typo:       ["排版檢查", "溢字與斷行的自動檢查"],

  // 生活語言〔Stanley 介面語言研究 §6：面板標題用生活語言，術語只在 tooltip〕
  pipeline:        ["內容團隊", "幫你選題、寫稿、找圖、排版的那一套自動流程"],
  heartbeat_ok:    ["一切正常", "團隊剛剛還在動，沒有卡住的事"],
  queue_empty:     ["今天沒有你的事", "系統做完會自己送到這裡"],
  in_orbit:        ["跟你互動過的人", "近期按讚、留言、分享過的帳號"],

  // Reels
  seg_talk:        ["口播", "真人感主持人講話的段落"],
  seg_broll:       ["空景", "無人聲的情緒畫面"],
  seg_own:         ["自有畫面", "我們自己的素材，0 點"],
  seg_cards:       ["字卡", "純文字動態卡，0 點"],
  storyboard:      ["分鏡", "生影片前的預覽草圖，先確認才花點數"],
};

// 排程時刻表常數（§3C：「預計何時回來」的唯一數字來源）
const SCHEDULE = {
  DRAFT_SLA_MIN: 45,     // 放行 → 入板的正常上限（排程器 15 分收 2 篇＋撰稿 7 分＋入板 10 分輪）
  RUSH_ETA_MIN: 20,      // 手動重跑後的上限（撰稿 6 分＋入板 10 分輪＋餘裕）
  SENTINEL_MIN: 10,      // 哨兵折疊事件的週期
  HEARTBEAT_WARN_MIN: 25,  // 心跳落後：黃
  HEARTBEAT_BAD_MIN: 70,   // 心跳落後：紅（哨兵安靜時最長 55 分推一次）
  STUCK_HOURS: 24,       // 系統處理中超過此時數 → 黃標＋回報鍵
};

function t(key) { return (TERMS[key] || [String(key)])[0]; }
function tip(key) { return (TERMS[key] || [, ""])[1] || ""; }

// 候選圖來源 → 介面標籤。機器代號（source_kind、檔名前綴）只有這裡認得。
function candSourceLabel(c) {
  const f = String(c.src || ""), k = String(c.source_kind || "");
  // source_engine 是入料時固化的欄位；舊資料沒有就退回檔名比對（縮圖路徑通常認不出，
  // 因此只當備援）。〔2026-09-01：Apify 一直在跑，是標籤看不出來〕
  if (c.source_engine === "apify") return t("apify");
  if (c.source_engine === "ddg") return "DuckDuckGo 圖片";
  if (k === "SHOT") return /-SHOT-[a-z]-ap/.test(f) ? t("apify") : t("shot");
  if (k === "WM") return "Wikimedia";
  if (k === "OV") return "Open Library";
  if (k === "DESIGN") return t("design_layout");
  if (c.kind === "generated") return t("generated");
  return c.source_label ? t("still") + " · " + String(c.source_label).slice(0, 10) : t("still");
}


// 範本 PM 化顯名（§5）：hook_type → 介面名。沒對照的用 hook_type 原文。
const TPL_NAME_MAP = { "趨勢詞策展": "趨勢詞文字卡" };
function tplName(tp) { return TPL_NAME_MAP[tp.hook_type] || tp.hook_type || tp.id; }

// 狀態 → 介面詞（貼文物件 → {label, tone, zone}）
// tone: you=品牌橘（只給等你）/ ok / info / warn / neutral；zone: queue / system / done
function statusView(p, latestReview) {
  const st = p.status;
  // 決定記憶：你剛做的決定還在等哨兵折疊（最長 10 分）→ 先照決定顯示，
  // 加「同步中」標記，避免重整後看到稿跑回佇列（排時間無限迴圈的根治）。
  const pend = window.LavaCore.pendingDecisionOf(p.id, st);
  if (pend) {
    if (pend.type === "post.schedule")
      return { label: t("scheduled") + "（同步中）", tone: "info", zone: "done" };
    if (pend.type === "post.reject")
      return { label: t("rejected") + "（同步中）", tone: "neutral", zone: "gone" };
    if (pend.type === "post.approve")
      return { label: t("approved") + "（同步中）", tone: "you", zone: "queue" };
    if (pend.type === "post.unschedule")
      return { label: t("approved") + "（同步中）", tone: "you", zone: "queue" };
  }
  if (st === "published") return { label: t("published"), tone: "ok", zone: "done" };
  if (st === "scheduled") return { label: t("scheduled"), tone: "info", zone: "done" };
  if (st === "rejected")  return { label: t("rejected"), tone: "neutral", zone: "gone" };
  // §1.3 防護：最新 review 是 reject 且版本未前進 → 重做中，不進佇列。
  // 只認帶 version 欄的新制紀錄（2026-08-31 起）；舊紀錄沒有版本概念，
  // 套用防護會把「早退回過、已重做」的稿永遠判成重做中。
  if (latestReview && latestReview.decision === "reject" && latestReview.version != null
      && !(Number(p.version || 0) > Number(latestReview.version || 0)))
    return { label: t("redoing"), tone: "warn", zone: "system" };
  if (st === "awaiting_review") {
    const blocked = (p.slides || []).some(sl => window.LavaCore.lacksMaterial(sl));
    return blocked
      ? { label: t("fixing_images"), tone: "warn", zone: "system" }
      : { label: t("awaiting_review"), tone: "you", zone: "queue" };
  }
  if (st === "approved") {
    if (p.render_note) return { label: t("awaiting_review"), tone: "you", zone: "queue" };
    return window.LavaCore.slidesDone(p)
      ? { label: t("approved"), tone: "you", zone: "queue" }
      : { label: t("making"), tone: "neutral", zone: "system" };
  }
  return { label: t("making"), tone: "neutral", zone: "system" };
}

window.LavaTerms = { TERMS, SCHEDULE, t, tip, statusView, candSourceLabel, TPL_NAME_MAP, tplName };
})();
