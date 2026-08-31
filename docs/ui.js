/* 共用 UI 元件〔藍圖 UI 規格 §2〕— ActionButton、StatusLine、SVG 圖示、摺疊區。
   規則：所有會寫資料或花錢的按鈕只能用 ActionButton，禁止裸 <button onclick>。
   載入順序：config → core → terms → ui → 頁面。 */
(() => {
"use strict";
const { el, esc, modal } = window.LavaCore;

// ── SVG 圖示（Lucide 線稿，stroke 1.75）——取代 emoji 圖示 ─────────────
// 圖示永遠伴隨文字標籤或 aria-label，不做 icon-only 的關鍵操作。
const ICONS = {
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  chevron: '<polyline points="6 9 12 15 18 9"/>',
  arrowLeft: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
  arrowRight: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h0a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2-9.4L23 10"/>',
  lightbulb: '<path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.4 1 2.3h6c0-.9.4-1.8 1-2.3A7 7 0 0 0 12 2z"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  edit: '<path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
};
function icon(name, size) {
  const s = size || 15;
  const span = el("span", "ic");
  span.innerHTML = `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  return span;
}

// ── 時間工具（全站同一種說法）──────────────────────────────────────────
function ago(iso) {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "剛剛";
  if (m < 60) return m + " 分前";
  if (m < 48 * 60) return Math.round(m / 60) + " 小時前";
  return Math.round(m / 1440) + " 天前";
}
function dur(iso) {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 60) return "已 " + Math.max(1, m) + " 分";
  if (m < 48 * 60) return "已 " + Math.round(m / 60) + " 小時";
  return "已 " + Math.round(m / 1440) + " 天";
}

// ── ActionButton（§2.1）— 四態＋防重複觸發＋群組互斥 ────────────────────
// 同 id 的鎖寫入模組級 inFlight：即使畫面重繪也不會生出第二顆可點的同名按鈕。
const inFlight = new Set();
const groups = {};   // groupId → Set<button element>

function ActionButton(opt) {
  const kind = opt.kind || "default";
  const b = el("button", "btn " + (kind === "primary" ? "primary" : kind === "danger" ? "danger" : kind === "ghost" ? "ghost" : ""));
  b.type = "button";
  const label = opt.cost ? `${opt.label} · 約 ${opt.cost.credits} 點` : opt.label;
  const paint = (html) => { b.innerHTML = html; };
  const idle = () => { b.disabled = false; b.classList.remove("err"); paint(esc(label)); };
  idle();
  if (opt.groupId) { (groups[opt.groupId] = groups[opt.groupId] || new Set()).add(b); }
  if (inFlight.has(opt.id)) { b.disabled = true; paint('<span class="spin"></span> 處理中…'); }

  b.onclick = async () => {
    if (inFlight.has(opt.id) || b.disabled) return;
    if (opt.confirm) {
      const body = el("div", "small muted", esc(opt.confirm)
        + (opt.cost ? `<div style="margin-top:6px"><b>費用：約 ${opt.cost.credits} 點</b></div>` : ""));
      const ok = await modal(opt.label, body,
        [{ label: "取消", value: null }, { label: "確定", value: 1, cls: "primary" }]);
      if (!ok) return;
    }
    inFlight.add(opt.id);
    b.disabled = true; paint('<span class="spin"></span> 處理中…');
    const peers = opt.groupId ? [...groups[opt.groupId]] : [];
    peers.forEach(x => { if (x !== b) x.disabled = true; });
    try {
      await opt.run();
      paint("✓ " + esc(opt.doneLabel || "完成"));
      b.classList.add("done");
      setTimeout(() => {
        inFlight.delete(opt.id);
        if (opt.onDone) opt.onDone(); else { idle(); peers.forEach(x => { x.disabled = false; }); }
      }, 1200);
    } catch (e) {
      inFlight.delete(opt.id);
      peers.forEach(x => { x.disabled = false; });
      b.disabled = false; b.classList.add("err");
      paint("重試：" + esc(String(e.message || e).slice(0, 60)));
    }
  };
  return b;
}

// ── StatusLine（§2.2）— 誠實狀態列，固定句式 ───────────────────────────
// 卡在【誰】｜{階段} · 已 {時長} · 下一步：{動作}
function StatusLine(opt) {
  const box = el("div", "statusline " + (opt.tone || "neutral"));
  box.setAttribute("role", "status");
  const who = el("b", null, "卡在【" + esc(opt.who) + "】");
  box.appendChild(who);
  box.appendChild(el("span", "sl-stage", "｜" + esc(opt.stage) + (opt.since ? " · " + esc(dur(opt.since)) : "")));
  box.appendChild(el("span", "sl-next", "下一步：" + esc(opt.next)));
  if (opt.detail) box.title = opt.detail;
  return box;
}

// ── 摺疊區塊（§3 的 B/C/D 區容器）─────────────────────────────────────
function Section(opt) {
  const wrap = el("section", "zone");
  const head = el("button", "zone-head");
  head.type = "button";
  head.setAttribute("aria-expanded", String(!opt.collapsed));
  const count = opt.count != null ? `<span class="zone-n">${opt.count}</span>` : "";
  head.innerHTML = `<span class="zone-t">${esc(opt.title)}</span>${count}`;
  head.appendChild(icon("chevron", 14));
  const body = el("div", "zone-body");
  if (opt.collapsed) { wrap.classList.add("closed"); }
  head.onclick = () => {
    wrap.classList.toggle("closed");
    head.setAttribute("aria-expanded", String(!wrap.classList.contains("closed")));
  };
  wrap.appendChild(head); wrap.appendChild(body);
  return { wrap, body, head };
}

window.LavaUI = { icon, ago, dur, ActionButton, StatusLine, Section, inFlight };
})();
