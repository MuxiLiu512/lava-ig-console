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
      b.disabled = false;
      if (e && e.silent) { idle(); return; }   // 使用者主動取消：安靜回原狀，不是錯誤
      b.classList.add("err");
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

// ── 即時文案檢查（輸入中提示）───────────────────────────────────────
// 規則正本在後端：禁用詞＝config/banned-words.txt、禁句式＝scripts/copy_check.py。
// 這裡只做打字時的即時提示；存檔後的裁決仍以文案閘門為準。
let BANNED = null;
async function loadBanned() {
  if (BANNED) return BANNED;
  try {
    const { tfetch, rawUrl, MODE } = window.LavaCore;
    const url = MODE === "local" ? "../config/banned-words.txt" : rawUrl("config/banned-words.txt");
    const r = await tfetch(url + "?t=" + Date.now());
    BANNED = (await r.text()).split("\n").map(s => s.trim()).filter(s => s && !s.startsWith("#"));
  } catch (e) { BANNED = []; }
  return BANNED;
}
const LINT_PATTERNS = [
  [/——/, "破折號（——）"],
  [/不是[^，。\n]{1,14}[，、]?\s*而是/, "「不是…而是…」句式"],
  [/欸[⋯…]*[，,]?\s*你|你有沒有發現|你知道嗎/, "對話式開場"],
];
function lintText(text) {
  const hits = [];
  (BANNED || []).forEach(w => { if (w && text.includes(w)) hits.push("禁用詞「" + w + "」"); });
  LINT_PATTERNS.forEach(([re, name]) => { if (re.test(text)) hits.push(name); });
  return [...new Set(hits)];
}

// ── InlineEdit（§6）— 就地文字編輯 ──────────────────────────────────
// textarea（非 contenteditable，避免貼上帶格式）＋即時檢查（300ms debounce）＋
// 儲存列。Esc 取消、Cmd+Enter 儲存。onSave 收 [{field, original, edited}]（只含有變動的）。
function InlineEdit(opt) {
  const box = el("div", "inedit");
  const tas = [];
  let saveBtnWrap;
  const dirty = () => tas.some(x => x.ta.value !== x.f.value);
  const paintBar = () => { saveBtnWrap.style.display = dirty() ? "flex" : "none"; };
  opt.fields.forEach(f => {
    if (f.label) box.appendChild(el("label", "fld", esc(f.label)));
    const ta = el("textarea");
    ta.value = f.value || "";
    ta.rows = Math.max(2, (f.value || "").split("\n").length + 1);
    const lint = el("div", "lintline");
    let deb;
    const runLint = () => {
      const hits = lintText(ta.value);
      lint.innerHTML = hits.length
        ? hits.map(h => `<span class="hit">${esc(h)}</span>`).join(" ")
        : "";
      lint.style.display = hits.length ? "block" : "none";
    };
    ta.addEventListener("input", () => {
      ta.rows = Math.max(2, ta.value.split("\n").length + 1);
      clearTimeout(deb); deb = setTimeout(runLint, 300);
      paintBar();
    });
    ta.addEventListener("keydown", e => {
      if (e.key === "Escape") { e.preventDefault(); opt.onCancel && opt.onCancel(); }
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); doSave.click(); }
    });
    runLint();
    box.appendChild(ta); box.appendChild(lint);
    tas.push({ f, ta });
  });
  saveBtnWrap = el("div", "btnrow"); saveBtnWrap.style.cssText = "margin-top:8px;display:none";
  const doSave = ActionButton({
    id: opt.saveId, label: "儲存修改", kind: "primary", doneLabel: "已儲存",
    run: async () => {
      const edits = tas.filter(x => x.ta.value !== x.f.value)
        .map(x => ({ field: x.f.field, original: x.f.value || "", edited: x.ta.value }));
      if (!edits.length) throw new Error("沒有變動");
      await opt.onSave(edits);
    },
    onDone: () => opt.onDone && opt.onDone(),
  });
  const revert = el("button", "btn ghost", "還原");
  revert.type = "button";
  revert.onclick = () => { tas.forEach(x => { x.ta.value = x.f.value || ""; x.ta.dispatchEvent(new Event("input")); }); };
  const cancel = el("button", "btn ghost", "取消");
  cancel.type = "button";
  cancel.onclick = () => opt.onCancel && opt.onCancel();
  saveBtnWrap.appendChild(doSave); saveBtnWrap.appendChild(revert); saveBtnWrap.appendChild(cancel);
  box.appendChild(saveBtnWrap);
  paintBar();
  const hint = el("div", "meta", "Esc 取消 · Cmd+Enter 儲存 · 檢查提示僅供參考，存檔後仍以文案閘門為準");
  hint.style.marginTop = "4px";
  box.appendChild(hint);
  if (tas[0]) setTimeout(() => tas[0].ta.focus(), 0);
  return box;
}

// ── TemplatePicker（§5）— 範本選擇器（全螢幕彈層）───────────────────
// 範本卡：骨架示意（skeleton 以「→」分段畫小條）＋為什麼有效＋證據標籤＋使用數。
// 不得把 unverified 的互動數據標成「高互動」——一律灰標「互動數據未查證」。
const tplName = tp => window.LavaTerms.tplName(tp);   // 顯名對照在 terms.js

function skeletonViz(skeleton) {
  const wrap = el("div", "tpl-skel");
  String(skeleton || "").split("→").map(s => s.trim()).filter(Boolean).slice(0, 6).forEach(seg => {
    const b = el("div", "seg");
    b.appendChild(el("i"));
    b.appendChild(el("span", null, esc(seg.slice(0, 26))));
    wrap.appendChild(b);
  });
  return wrap;
}

function openTemplatePicker(opt) {
  // opt: {templates, currentId, typeFilter:"post"|"reels", onPick(tpl)}
  const bg = el("div", "tplpicker");
  bg.setAttribute("role", "dialog");
  const head = el("div", "tp-head");
  head.appendChild(el("b", null, "選擇範本"));
  const close = el("button", "icon-btn");
  close.setAttribute("aria-label", "關閉");
  close.appendChild(icon("x", 17));
  close.onclick = () => bg.remove();
  head.appendChild(el("span", "grow"));
  head.appendChild(close);
  bg.appendChild(head);
  document.addEventListener("keydown", function escClose(e) {
    if (e.key === "Escape") { bg.remove(); document.removeEventListener("keydown", escClose); }
  });

  const body = el("div", "tp-body");
  const all = (opt.templates || []).filter(tp => !opt.typeFilter || tp.type === opt.typeFilter);
  const main = all.filter(tp => tp.status === "validated");
  const rest = all.filter(tp => tp.status !== "validated");

  const card = tp => {
    const c = el("div", "tpl-card" + (tp.id === opt.currentId ? " on" : ""));
    c.appendChild(skeletonViz(tp.skeleton));
    c.appendChild(el("h3", null, esc(tplName(tp))));
    const why = el("details");
    why.appendChild(el("summary", "small muted", esc(String(tp.why_it_works || "").slice(0, 60)) + "…"));
    why.appendChild(el("div", "small muted", esc(tp.why_it_works || "")));
    c.appendChild(why);
    const meta = el("div", "tpl-meta");
    const ev = tp.evidence || {};
    if (String(ev.engagement || "").includes("unverified"))
      meta.appendChild(el("span", "gate", "互動數據未查證"));
    if (ev.source_account) {
      const a = el("a", "meta", esc(ev.source_account));
      if (ev.post_url) { a.href = ev.post_url; a.target = "_blank"; a.rel = "noopener"; }
      meta.appendChild(a);
    }
    meta.appendChild(el("span", "meta", "已用 " + ((tp.used_by || []).length) + " 篇"));
    c.appendChild(meta);
    c.appendChild(ActionButton({
      id: "pick-tpl-" + tp.id, label: tp.id === opt.currentId ? "目前使用中" : "用這個範本",
      kind: tp.id === opt.currentId ? "ghost" : "primary", doneLabel: "已選定",
      run: async () => {
        if (tp.id === opt.currentId) throw new Error("已是目前範本");
        await opt.onPick(tp);
      },
      onDone: () => bg.remove(),
    }));
    return c;
  };

  const grid = el("div", "tpl-grid");
  main.forEach(tp => grid.appendChild(card(tp)));
  if (!main.length) grid.appendChild(el("div", "empty", "這個類型還沒有可用的範本"));
  body.appendChild(grid);
  if (rest.length) {
    const det = el("details", "drawer");
    det.appendChild(el("summary", null, `候選與停用範本（${rest.length}）`));
    const g2 = el("div", "tpl-grid inner");
    rest.forEach(tp => g2.appendChild(card(tp)));
    det.appendChild(g2);
    body.appendChild(det);
  }
  bg.appendChild(body);
  document.body.appendChild(bg);
}

window.LavaUI = { icon, ago, dur, ActionButton, StatusLine, Section, inFlight,
                  loadBanned, lintText, InlineEdit, openTemplatePicker, tplName };
})();
