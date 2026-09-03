/* 審稿台 v3 — 單欄審核流〔藍圖 UI 規格 §4〕
   一張 slide 一卡，逐張確認；全部確認才可核准。成品為主、候選收抽屜。
   決定＝事件檔（postEvent），哨兵折疊；rejected 永不回佇列。 */
(() => {
"use strict";
const { S, MODE, $, el, esc, saveJson, tfetch, postEvent, patModal, setImg, img, STATE, FILES, loadAll,
        toast, modal, nowISO, gatesOf, lacksMaterial, DESIGN_LAYOUTS, slidesDone } = window.LavaCore;
const { t, SCHEDULE, statusView, candSourceLabel } = window.LavaTerms;
const { icon, ago, dur, ActionButton, StatusLine, loadBanned, lintText, InlineEdit, openTemplatePicker, tplName } = window.LavaUI;

let QUEUE = [], IDX = 0, CHOICE = {}, CONFIRMED = new Set(), CROPDRAFT = {}, T0 = 0;
let EDITING = null;   // 目前展開編輯的目標："s<n>" 或 "caption"，同時間只開一個

// ── 文案的有效值：copy_edits 最新編輯優先（與後端 _latest_copy_edits 同一套規則）──
// 不變量（藍圖 v2 第 21 項）：copy_edits 最新版 = 目前顯示值。
function latestEditsOf(p) {
  const out = {}, ts = {};
  const list = ((STATE.copy_edits && STATE.copy_edits.edits) || [])
    .filter(e => e.post_id === p.id)
    .sort((a, b) => String(a.ts || "").localeCompare(String(b.ts || "")));
  let newestTs = null;
  list.forEach(e => (e.edits || []).forEach(ed => {
    if (ed.version && p.copy_choice && ed.version !== p.copy_choice) return;
    const k = String(ed.n) + ":" + ed.field;
    out[k] = ed.edited;
    ts[k] = e.ts;              // 逐欄位時間：判定「這一張」有沒有比閘門新，不能用全篇最新
    newestTs = e.ts;
  }));
  out._ts = newestTs;
  out._fieldTs = ts;
  return out;
}
const effField = (p, n, field, fallback) => {
  const v = latestEditsOf(p)[String(n) + ":" + field];
  return v != null ? v : (fallback || "");
};

const cur = () => QUEUE[IDX];
const finalOf = s => s && (s.public_url || s.final_src);
const isDesign = s => DESIGN_LAYOUTS.includes(String((s || {}).product_layout || "")) || /CTA/i.test(String((s || {}).role || ""));
const latestReviewOf = id => {
  const rs = ((STATE.reviews && STATE.reviews.reviews) || []).filter(r => r.post_id === id);
  return rs.length ? rs[rs.length - 1] : null;
};

// ── 待決項〔2026-09-01 重寫〕：閘門結果是「當時」對「當時內容」的判定。
// 內容改過（換圖／改字）之後，舊判定就是過期的——過期的判定不該再擋人。
// 三條解結路徑：改內容 → 自動轉「待重驗」；重新檢查 → 閘門重跑；標記已處理 → 記錄後放行。
// 這是「只能退回、退回又回到同一批內容」死循環的根治。
function issueKey(gate, i, idx) {
  return gate + ":" + String(i.line || i.detail || i.rule || i.type || idx).slice(0, 60);
}
function overriddenKeys(p) {
  return new Set(((p.gate_overrides) || []).map(o => o.key));
}
// 這張 slide 的內容在閘門跑完之後被改過嗎
function touchedAfterGate(p, n) {
  if (CHOICE[n] != null) return "換過底圖";      // 這一輪剛換的，最即時
  const fts = latestEditsOf(p)._fieldTs || {};
  const gateTs = p.rechecked_at || p.rendered_at || "";
  const mine = ["heading", "display_copy", "caption"]
    .map(f => fts[String(n) + ":" + f]).filter(Boolean);
  if (mine.length && mine.sort().slice(-1)[0] > gateTs) return "改過文字";
  return null;
}
// 事實查核的問題屬於哪一張：用引文比對 slide 文字；找不到就掛在文案卡（n=0）
function slideOfFactIssue(p, line) {
  const frag = String(line || "").replace(/[「」『』]/g, "").slice(0, 12);
  if (!frag) return 0;
  const hit = (p.slides || []).find(s => {
    const txt = [effField(p, Number(s.n), "heading", s.heading),
                 effField(p, Number(s.n), "display_copy", s.display_copy)].join("\n");
    return txt && txt.includes(frag);
  });
  return hit ? Number(hit.n) : 0;
}

function pendingOf(p) {
  const out = [];
  const ov = overriddenKeys(p);
  const push = o => {
    if (ov.has(o.key)) return;                       // 你標記過「這項沒問題」
    const why = touchedAfterGate(p, o.n);
    if (why && o.sev === "block") { o.sev = "warn"; o.stale = why; }
    out.push(o);
  };
  (p.slides || []).forEach(s => {
    if (lacksMaterial(s))
      push({ n: Number(s.n), kind: "缺圖", sev: "block", gate: "material",
             key: "material:" + s.n, text: "這張沒有可用的圖。補圖前無法出成品。" });
  });
  ((p.qa && p.qa.issues) || []).forEach((i, idx) =>
    push({ n: Number((i.slides || [])[0] || 1), slides: i.slides || [], kind: t("gate_visual"),
           sev: i.severity || "warn", gate: "qa", key: issueKey("qa", i, idx),
           text: i.detail || i.type, fix: i.fix }));
  ((p.typography && p.typography.issues) || []).forEach((i, idx) =>
    push({ n: Number(i.slide || 1), kind: t("gate_typo"), sev: "block", gate: "typography",
           key: issueKey("typo", i, idx), text: i.rule + "：" + i.line }));
  // 事實查核原本完全不顯示在審稿流程裡——只有頂端一顆紅點，你看不到問題是什麼、
  // 更沒有處理它的地方。這是死循環最深的一層。
  ((p.fact && p.fact.issues) || []).forEach((i, idx) => {
    const line = i.line || i.detail || "";
    push({ n: slideOfFactIssue(p, line), kind: t("gate_fact"),
           sev: (i.severity || i.sev) === "block" ? "block" : "warn",
           gate: "fact", key: issueKey("fact", i, idx), text: line,
           fix: "改掉這句沒有出處的說法，或標記為已確認（下方兩顆鍵）" });
  });
  return out;
}

// 待決項卡片：問題 + 兩顆解結鍵
function pendNode(p, x) {
  const d = el("div", "pend" + (x.sev === "block" ? " block" : ""));
  const head = el("div");
  // 〔Stanley 介面語言研究 §3〕「我看到什麼」而不是「你哪裡錯了」。
  // 判決句讓人只能接受或抗辯；提議句讓人可以協作。
  head.innerHTML = `<b class="k">${esc(x.kind)}</b>${x.stale ? ` <span class="edited-tag">你已${esc(x.stale)} · 我要重看一次</span>` : ""} · 我看到：${esc(String(x.text).slice(0, 220))}`;
  d.appendChild(head);
  if (x.fix) d.appendChild(el("div", "fix", "我建議：" + esc(String(x.fix).slice(0, 180))));
  if (x.gate === "material") return d;          // 缺圖只能等補圖或重新生成
  const row = el("div", "btnrow"); row.style.marginTop = "8px";
  row.appendChild(ActionButton({
    id: "resolve-" + p.id + "-" + x.key, label: "這項沒問題，記下來", kind: "ghost", doneLabel: "記下了",
    run: async () => {
      const ta = el("textarea"); ta.rows = 2;
      ta.placeholder = "為什麼沒問題？（例：99% 是修辭不是數據；出處頁面改版但內容仍在）";
      const okc = await modal("標記為已處理", ta,
        [{ label: "取消", value: null }, { label: "確認", value: 1, cls: "primary" }]);
      if (!okc) { const e = new Error("已取消"); e.silent = true; throw e; }
      if (ta.value.trim().length < 4) throw new Error("請寫一句原因（會留存紀錄）");
      await postEvent("post.resolve_issue", p.id,
        { key: x.key, gate: x.gate, reason: ta.value.trim() });
      (p.gate_overrides = p.gate_overrides || []).push({ key: x.key, gate: x.gate, reason: ta.value.trim() });
    },
    onDone: () => { toast("記下了。這項我不再提，理由留在紀錄裡。"); render(); },
  }));
  d.appendChild(row);
  return d;
}
const pendOfSlide = (pend, n) =>
  pend.filter(x => (x.slides && x.slides.length ? x.slides : [x.n]).some(m => String(m) === String(n)));

const srcLabel = candSourceLabel;   // 機器代號的判讀在 terms.js
const srcOfCand = (s, cid) => (((s && s.candidates) || []).find(c => c.cid === cid) || {}).src || null;

// ── 裁切預覽（沿用：object-position 數學＝引擎 fit_bg(focus)）──────────
function frameAspectOf(s, im) {
  const fa = s && s.frame_aspect;
  if (typeof fa === "number") return fa;
  if (fa && typeof fa === "object" && im && im.naturalWidth)
    return im.naturalHeight > im.naturalWidth ? fa.portrait : fa.landscape;
  return 4 / 5;
}
function cropPreview(p, s, path) {
  const n = Number(s.n);
  const wrap = el("div", "rv-cropwrap");
  const box = el("div", "rv-crop");
  const im = el("img"); im.draggable = false; im.alt = "候選底圖裁切預覽";
  const applyAspect = () => { box.style.aspectRatio = String(frameAspectOf(s, im)); };
  im.addEventListener("load", applyAspect); applyAspect();
  const focus = () => CROPDRAFT[n] || s.crop_focus || [0.5, 0.5];
  const paint = () => { const [fx, fy] = focus(); im.style.objectPosition = (fx * 100) + "% " + (fy * 100) + "%"; };
  setImg(im, path); paint();
  box.appendChild(im);
  box.appendChild(el("div", "crop-badge", s.product_layout
    ? "照片將置入卡片 · 拖曳調整取景" : "候選底圖 · 4:5 裁切預覽 · 拖曳調整"));
  const bar = el("div", "crop-bar");
  const save = el("button", "btn primary", "儲存裁切");
  const reset = el("button", "btn", "重設置中");
  const dirty = () => { bar.style.display = "flex"; };
  if (CROPDRAFT[n]) dirty();
  save.onclick = async () => {
    const v = [Math.round(focus()[0] * 1000) / 1000, Math.round(focus()[1] * 1000) / 1000];
    try {
      await saveJson(FILES.posts, d => {
        const q = (d.posts || []).find(x => x.id === p.id);
        const sl = q && (q.slides || []).find(x => String(x.n) === String(n));
        if (sl) sl.crop_focus = v;
      }, `crop: ${p.id} s${n}`);
      s.crop_focus = v; delete CROPDRAFT[n]; bar.style.display = "none";
      toast("裁切已儲存。核准後重出成品生效。");
    } catch (e) { toast(e.message, true); }
  };
  reset.onclick = () => { CROPDRAFT[n] = [0.5, 0.5]; paint(); dirty(); };
  bar.appendChild(save); bar.appendChild(reset);
  let drag = null;
  box.onpointerdown = e => { drag = { x: e.clientX, y: e.clientY, f: focus().slice() }; box.setPointerCapture(e.pointerId); };
  box.onpointermove = e => {
    if (!drag || !im.naturalWidth) return;
    const r = box.getBoundingClientRect();
    const sc = Math.max(r.width / im.naturalWidth, r.height / im.naturalHeight);
    const ox = im.naturalWidth * sc - r.width, oy = im.naturalHeight * sc - r.height;
    const nf = [
      Math.min(1, Math.max(0, drag.f[0] + (ox > 2 ? (drag.x - e.clientX) / ox : 0))),
      Math.min(1, Math.max(0, drag.f[1] + (oy > 2 ? (drag.y - e.clientY) / oy : 0))),
    ];
    if (Math.abs(nf[0] - focus()[0]) < 0.002 && Math.abs(nf[1] - focus()[1]) < 0.002) return;
    CROPDRAFT[n] = nf; paint(); dirty();
  };
  box.onpointerup = box.onpointercancel = () => { drag = null; };
  wrap.appendChild(box); wrap.appendChild(bar);
  return wrap;
}

// ── 文案編輯寫入：copy_edits.json 追加一筆（瀏覽器是這個檔的唯一寫者）──
// 圖上字由渲染引擎在排版時折入（_latest_copy_edits）；caption 由哨兵折回 posts.json。
async function saveCopyEdits(p, n, edits) {
  const entry = {
    post_id: p.id, ts: nowISO(), consumed: false,
    edits: edits.map(e => ({ n, field: e.field, original: e.original, edited: e.edited,
                             ...(p.copy_choice ? { version: p.copy_choice } : {}) })),
  };
  await saveJson(FILES.copy_edits, doc => {
    (doc.edits = doc.edits || []).push(entry);
  }, `copy edit: ${p.id} s${n}`);
  // 樂觀更新本地 STATE，畫面立即反映新字
  ((STATE.copy_edits = STATE.copy_edits || { edits: [] }).edits =
    STATE.copy_edits.edits || []).push(entry);
  CONFIRMED.delete(n);   // 改了字＝這張要重新看過
  toast("已儲存 ✓ " + (n === 0 ? "貼文文案 10 分內同步，發佈用新字。" : "排版時用新字。")
    + "你的改法今晚會進學習迴路（語氣範例）。");
}

// ── ① 整體資訊卡 ────────────────────────────────────────────────────
let TPLCACHE = null;
async function loadTemplates() {
  if (TPLCACHE) return TPLCACHE;
  try { TPLCACHE = ((await window.LavaCore.apiGet("data/templates.json")).json.templates) || []; }
  catch (e) { TPLCACHE = null; throw new Error("範本庫暫時讀不到，可先照預設骨架繼續"); }
  return TPLCACHE;
}

function infoCard(p) {
  const c = el("div", "card"); const pad = el("div", "pad");
  const row = el("div", "row");
  row.appendChild(el("b", null, esc(p.topic_type || "知識型")));
  row.appendChild(el("span", "meta", (p.slides || []).length + " 張"));
  if (p.template_id) {
    const tag = el("span", "meta", "範本 " + esc(p.template_id));
    if (TPLCACHE) { const tp = TPLCACHE.find(x => x.id === p.template_id); if (tp) tag.textContent = "範本：" + tplName(tp); }
    row.appendChild(tag);
  }
  const chg = el("button", "btn ghost", p.template_id ? "換範本" : "選範本");
  chg.type = "button"; chg.style.cssText = "min-height:28px;padding:3px 10px;font-size:12px";
  chg.onclick = async () => {
    let tpls;
    try { tpls = await loadTemplates(); } catch (e) { return toast(e.message, true); }
    openTemplatePicker({
      templates: tpls, currentId: p.template_id, typeFilter: "post",
      onPick: async tp => {
        await saveJson(FILES.posts, doc => {
          const q = (doc.posts || []).find(x => x.id === p.id);
          if (q) q.template_id = tp.id;
        }, `template: ${p.id} → ${tp.id}`);
        p.template_id = tp.id;
        toast("已選定範本「" + tplName(tp) + "」。重做或重寫這篇時，產線會照它的骨架。");
        render();
      },
    });
  };
  row.appendChild(chg);
  const gz = el("div", "gates"); gz.style.marginLeft = "auto";
  gatesOf(p).forEach(([name, st]) => {
    const d = el("span", "gate " + st, esc(name));
    d.title = name + "：" + (st === "ok" ? "通過" : st === "bad" ? "未過" : st === "warn" ? "有提醒" : "未跑");
    gz.appendChild(d);
  });
  row.appendChild(gz);
  pad.appendChild(row);
  c.appendChild(pad);
  return c;
}

// ── ② 逐張審核卡（SlideCard）────────────────────────────────────────
function slideCard(p, s, pend) {
  const n = Number(s.n);
  const card = el("section", "slidecard" + (CONFIRMED.has(n) ? " confirmed" : ""));
  card.id = "slide-" + n;

  // 卡頭
  const head = el("div", "sc-head");
  head.appendChild(el("span", "n", "第 " + n + " 張"));
  if (s.role) head.appendChild(el("span", "role", esc(String(s.role).slice(0, 24))));
  const st = el("span", "state dotlbl " + (CONFIRMED.has(n) ? "ok" : ""));
  st.innerHTML = CONFIRMED.has(n) ? "<i></i>已確認" : "<i></i>待確認";
  head.appendChild(st);
  // 退路必須自己說話〔2026-09-03 Jesse：不要寫垃圾 cover 錯誤，導致全部都查不出錯誤〕
  // 系統為了不讓整篇卡住而擅自換過圖時，那不是「修好了」，是「我替你做了決定」。
  // 只寫進資料不顯示，等於把問題藏起來——那正是最該避免的一種修法。
  const fb = (p.choice_fallback || []).filter(x => Number(x.slide) === n);
  if (fb.length) {
    const w = el("div", "pend");
    w.innerHTML = `<b class="k">我替你換了圖</b> · 你原本選的 ${esc(String(fb[fb.length - 1].wanted || "?"))} 找不到原檔，` +
      `我改用現在拿得到的最好的一張（${esc(String(fb[fb.length - 1].used || "?"))}）。請確認這張你能接受。`;
    card.appendChild(w);
  }
  card.appendChild(head);

  // 主圖：成品 > 候選裁切 > 設計版面 > 缺圖面板
  const hero = el("div", "sc-hero");
  const fin = finalOf(s);
  const candSrc = srcOfCand(s, CHOICE[n] || s.default_cid) || (((s.candidates || [])[0]) || {}).src;
  const _fts0 = latestEditsOf(p)._fieldTs || {};
  const _myTs0 = ["heading", "display_copy"].map(f => _fts0[String(n) + ":" + f]).filter(Boolean).sort().slice(-1)[0];
  const _stale = !!_myTs0 && _myTs0 > (p.rendered_at || "");
  if (fin) {
    const w0 = el("div"); w0.style.cssText = "position:relative;display:flex;justify-content:center;width:100%";
    if (/^https?:/.test(fin)) { const e = el("img"); e.src = fin; e.alt = "第 " + n + " 張成品"; w0.appendChild(e); }
    else w0.appendChild(img(fin));
    if (_stale) w0.appendChild(el("div", "crop-badge", "圖上仍是舊字 · 最新文字在下方"));
    hero.appendChild(w0);
  } else if (isDesign(s)) {
    const name = { diagram: "卡片圖解", price: "數字卡", cta: "CTA 尾板" }[String(s.product_layout || "")] || "CTA 公版";
    hero.appendChild(el("div", "design-ph", name + "：由引擎繪製，不需要照片。文字內容在下方，成品排版後回來看。"));
  } else if (candSrc) {
    const w = el("div"); w.style.cssText = "padding:12px;width:100%;display:flex;justify-content:center";
    w.appendChild(cropPreview(p, s, candSrc));
    hero.appendChild(w);
  } else {
    const boxp = el("div", "design-ph");
    boxp.appendChild(el("div", null, "這張我還沒找到能用的圖。我每一輪都在找；連兩輪找不到就會整篇重寫視覺企劃。"));
    hero.appendChild(boxp);
  }
  card.appendChild(hero);

  // 內文：有效文字為主（最新編輯優先＝目前顯示值不變量）、就地可改；
  // 排版後的逐行實況與 AI 原稿各收一個摺疊。
  const body = el("div", "sc-body");
  const effH = effField(p, n, "heading", s.heading);
  const effC = effField(p, n, "display_copy", s.display_copy);
  const effTxt = [effH, effC].filter(Boolean).join("\n");
  const edits = latestEditsOf(p);
  const _fts = edits._fieldTs || {};
  const _myTs = ["heading", "display_copy"].map(f => _fts[String(n) + ":" + f]).filter(Boolean).sort().slice(-1)[0];
  const hasEdit = !!_myTs;
  if (effTxt || !isDesign(s)) {
    const hd = el("div", "row");
    hd.appendChild(el("span", "meta", t("display_copy")));
    if (hasEdit && fin && _myTs > (p.rendered_at || "")) {
      const approvedFlow = p.status === "approved";
      const tag = el("span", "edited-tag", approvedFlow
        ? "文字已改 · 15 分內自動重出成品" : "文字已改 · 核准後排版用新字");
      tag.title = approvedFlow
        ? "哨兵偵測到文案比成品新，會自動重排這一篇" : "圖上還是舊字；排版時一定用最新文字";
      hd.appendChild(tag);
    }
    hd.appendChild(el("span", "grow"));
    const eb = el("button", "btn ghost", "");
    eb.type = "button"; eb.style.cssText = "min-height:28px;padding:3px 10px;font-size:12px";
    eb.appendChild(icon("edit", 13));
    eb.appendChild(document.createTextNode(" 改文字"));
    hd.appendChild(eb);
    body.appendChild(hd);
    if (EDITING === "s" + n) {
      body.appendChild(InlineEdit({
        saveId: "edit-" + p.id + "-s" + n,
        fields: [
          { field: "heading", label: "標題行", value: effH },
          { field: "display_copy", label: "內文", value: effC },
        ],
        onSave: edits2 => saveCopyEdits(p, n, edits2),
        onDone: () => { EDITING = null; render(); },
        onCancel: () => { EDITING = null; render(); },
      }));
      eb.style.display = "none";
    } else {
      const pre = el("div", "sc-lines"); pre.textContent = effTxt || "（無文字）";
      pre.style.marginTop = "4px";
      body.appendChild(pre);
      const hits = lintText(effTxt);
      if (hits.length) {
        const d = el("div", "pend block");
        d.innerHTML = `<b class="k">${esc(t("gate_copy"))}</b> · 含 ${hits.map(esc).join("、")}——改完才能確認這張`;
        body.appendChild(d);
      }
      eb.onclick = () => { EDITING = "s" + n; render();
        const e2 = $("#slide-" + n); if (e2) e2.scrollIntoView({ block: "center" }); };
    }
  }
  const rl = (p.rendered_lines || {})[String(n)];
  if (Array.isArray(rl) && rl.length) {
    const det0 = el("details");
    det0.appendChild(el("summary", "meta", "排版後的逐行實況"));
    const pre0 = el("div", "sc-lines"); pre0.textContent = rl.join("\n");
    pre0.style.marginTop = "4px";
    det0.appendChild(pre0);
    det0.style.marginTop = "8px";
    body.appendChild(det0);
  }
  if (!fin && candSrc && !isDesign(s)) {
    const note = el("div", "sc-note");
    note.appendChild(icon("alert", 13));
    note.appendChild(el("span", null, "排版後才是最終樣子"));
    body.appendChild(note);
  }
  // 本張待決項就地展開
  pendOfSlide(pend, n).forEach(x => body.appendChild(pendNode(p, x)));
  card.appendChild(body);

  // 原始文案摺疊
  if (s.heading || s.display_copy) {
    const det = el("details", "drawer");
    det.appendChild(el("summary", null, "查看原稿（AI 初稿）"));
    const inner = el("div", "inner small muted");
    inner.style.whiteSpace = "pre-wrap";
    inner.textContent = [s.heading, s.display_copy].filter(Boolean).join("\n\n");
    det.appendChild(inner);
    card.appendChild(det);
  }

  // 候選圖抽屜
  const cands = s.candidates || [];
  if (cands.length) {
    const det = el("details", "drawer");
    det.appendChild(el("summary", null, `換底圖（${cands.length} 張候選）· 點一張＝選它出成品`));
    const inner = el("div", "inner");
    const grid = el("div", "cand-grid");
    const paint = () => {
      grid.innerHTML = "";
      const picked = CHOICE[n] || s.default_cid;
      cands.forEach(cd => {
        const on = picked === cd.cid;
        const w = el("button", "cand" + (on ? " on" : ""));
        w.type = "button";
        w.setAttribute("aria-label", srcLabel(cd) + (on ? "（使用中）" : "，點擊選用"));
        w.appendChild(img(cd.src));
        w.appendChild(el("span", "srclbl", esc(srcLabel(cd))));
        if (cd.low_q) w.appendChild(el("span", "lowq", "低畫質"));
        if (cd.dup_of_other_slide) {
          const dp = el("span", "lowq", "與別張重複");
          dp.style.background = "rgba(90,70,140,.9)"; dp.style.left = "auto"; dp.style.right = "4px";
          dp.title = "這張圖在其他版位也用了。系統為了不讓這張變成缺圖才保留它，你多半該換一張。";
          w.appendChild(dp);
        }
        if (on) w.appendChild(el("span", "onlbl", "使用中"));
        w.onclick = () => {
          CHOICE[n] = cd.cid; CONFIRMED.delete(n);
          toast("第 " + n + " 張改用這張底圖，核准後生效");
          render();
          const elc = $("#slide-" + n); if (elc) elc.scrollIntoView({ block: "center" });
        };
        grid.appendChild(w);
      });
    };
    paint();
    inner.appendChild(grid);
    det.appendChild(inner);
    card.appendChild(det);
  }

  // 卡尾：確認本張。block 級待決項或含禁詞的文字都擋確認（可存檔但不可確認，§6）。
  const foot = el("div", "sc-foot");
  const blocked = pendOfSlide(pend, n).some(x => x.sev === "block");
  const lintBlocked = lintText(effTxt).length > 0;
  const cb = el("button", "btn " + (CONFIRMED.has(n) ? "ghost" : "primary"));
  cb.type = "button";
  cb.textContent = CONFIRMED.has(n) ? "取消確認" : "確認這張";
  if ((blocked || lintBlocked) && !CONFIRMED.has(n)) {
    cb.disabled = true;
    foot.appendChild(el("span", "meta", lintBlocked ? "文字含禁用詞，改完才能確認" : "先處理上面的待決項才能確認"));
  }
  cb.onclick = () => {
    if (CONFIRMED.has(n)) CONFIRMED.delete(n); else { CONFIRMED.add(n); }
    render();
    if (CONFIRMED.has(n)) scrollToNextUnconfirmed(n);
  };
  foot.appendChild(cb);
  foot.appendChild(el("span", "meta", "Space＝確認並跳下一張"));
  card.appendChild(foot);
  return card;
}

function scrollToNextUnconfirmed(after) {
  const p = cur(); if (!p) return;
  const ns = (p.slides || []).map(s => Number(s.n)).sort((a, b) => a - b);
  const next = ns.find(m => m > after && !CONFIRMED.has(m)) ?? ns.find(m => !CONFIRMED.has(m));
  const target = next != null ? $("#slide-" + next) : $("#rvBar");
  if (target) target.scrollIntoView({ behavior: "smooth", block: next != null ? "start" : "end" });
}

// ── ③ 貼文文案卡（caption 就地編輯：n=0；哨兵折回 posts.json 後發佈用新字）──
function captionCard(p) {
  const c = el("div", "card"); const pad = el("div", "pad");
  const effCap = effField(p, 0, "caption", p.caption);
  const hd = el("div", "row");
  hd.appendChild(el("span", "meta", t("caption")));
  if (effCap !== (p.caption || "")) {
    const tag = el("span", "edited-tag", "已改、待哨兵同步");
    tag.title = "哨兵每 " + SCHEDULE.SENTINEL_MIN + " 分把新文案寫回正式資料，發佈用新字";
    hd.appendChild(tag);
  }
  hd.appendChild(el("span", "grow"));
  const eb = el("button", "btn ghost", "");
  eb.type = "button"; eb.style.cssText = "min-height:28px;padding:3px 10px;font-size:12px";
  eb.appendChild(icon("edit", 13));
  eb.appendChild(document.createTextNode(" 改文字"));
  hd.appendChild(eb);
  pad.appendChild(hd);
  if (EDITING === "caption") {
    eb.style.display = "none";
    pad.appendChild(InlineEdit({
      saveId: "edit-" + p.id + "-caption",
      fields: [{ field: "caption", label: null, value: effCap }],
      onSave: edits2 => saveCopyEdits(p, 0, edits2),
      onDone: () => { EDITING = null; render(); },
      onCancel: () => { EDITING = null; render(); },
    }));
  } else {
    eb.onclick = () => { EDITING = "caption"; render(); };
    const pre = el("div", "sc-lines"); pre.style.marginTop = "4px";
    pre.textContent = effCap || "（無文案）";
    pad.appendChild(pre);
    const hits = lintText(effCap);
    if (hits.length) {
      const d = el("div", "pend");
      d.innerHTML = `<b class="k">${esc(t("gate_copy"))}</b> · 含 ${hits.map(esc).join("、")}`;
      pad.appendChild(d);
    }
  }
  const info = el("div", "meta"); info.style.marginTop = "6px";
  const tags = (String(effCap || "").match(/#[^\s#]+/g) || []).length;
  info.textContent = `${String(effCap || "").length} 字 · ${tags} 個 hashtag`;
  pad.appendChild(info);
  // 對不到特定張數的待決項（多為事實查核的整篇引文）掛在這裡，不再無處可去
  pendOfSlide(pendingOf(p), 0).forEach(x => pad.appendChild(pendNode(p, x)));
  const copyIssues = ((p.copy && p.copy.issues) || []);
  copyIssues.slice(0, 4).forEach(i => {
    const d = el("div", "pend" + ((i.severity || i.sev) === "block" ? " block" : ""));
    d.innerHTML = `<b class="k">${esc(t("gate_copy"))}</b> · ${esc(String(i.line || i.detail || i.type || "").slice(0, 120))}`;
    pad.appendChild(d);
  });
  c.appendChild(pad);
  return c;
}

// ── ④ IG 預覽（摺疊）────────────────────────────────────────────────
function igPreview(p) {
  const det = el("details", "drawer card");
  det.appendChild(el("summary", null, "IG 預覽（點開載入）"));
  const inner = el("div", "inner");
  let loaded = false;
  det.addEventListener("toggle", () => {
    if (!det.open || loaded) return;
    loaded = true;
    const phone = el("div", "phone");
    const ig = el("div", "ig");
    const top = el("div", "ig-top");
    top.appendChild(el("div", "ig-av", "L"));
    top.appendChild(el("div", "nm", "lava_dating"));
    top.appendChild(el("div", "more", "⋯"));
    ig.appendChild(top);
    const media = el("div", "ig-media");
    const track = el("div", "ig-track");
    (p.slides || []).forEach(s => {
      const sl = el("div", "ig-slide");
      const src = finalOf(s) || srcOfCand(s, CHOICE[Number(s.n)] || s.default_cid) || (((s.candidates || [])[0]) || {}).src;
      if (src && /^https?:/.test(src)) { const e = el("img"); e.src = src; sl.appendChild(e); }
      else if (src) sl.appendChild(img(src));
      track.appendChild(sl);
    });
    media.appendChild(track);
    media.appendChild(el("div", "ig-count", "1/" + (p.slides || []).length));
    ig.appendChild(media);
    const cap = el("div", "ig-cap");
    cap.innerHTML = `<span class="nm">lava_dating</span><span class="body clamp">${esc(effField(p, 0, "caption", p.caption))}</span>`;
    ig.appendChild(cap);
    phone.appendChild(ig);
    inner.appendChild(phone);
  });
  det.appendChild(inner);
  return det;
}

// ── ⑤ 決策列 ────────────────────────────────────────────────────────
function decisionBar(p, pend) {
  const bar = $("#rvBar"); bar.innerHTML = ""; bar.style.display = "flex";
  const photoNs = (p.slides || []).map(s => Number(s.n));
  const total = photoNs.length;
  const done = photoNs.filter(n => CONFIRMED.has(n)).length;
  const prog = el("span", "progress");
  prog.innerHTML = `<b>${done}</b>/${total} 張已確認`;
  bar.appendChild(prog);
  bar.appendChild(el("span", "grow"));

  const blocked = pend.some(x => x.sev === "block");

  if (p.status === "approved" && !p.render_note) {
    // 已核准 → 排時間（事實閘門前置）。用 pendingOf 的結果，才吃得到
    // 「已標記處理」與「內容改過待重驗」——否則就是死循環的來源。
    const factBlocks = pend.filter(x => x.gate === "fact" && x.sev === "block");
    if (factBlocks.length) {
      bar.appendChild(el("span", "meta", `${t("gate_fact")}未過 ${factBlocks.length} 項`));
      bar.appendChild(recheckButton(p));
      bar.appendChild(ActionButton({
        id: "reopen-" + p.id, label: "回到逐張審核", kind: "ghost", doneLabel: "已回到待審",
        run: () => saveJson(FILES.posts, doc => {
          const q = (doc.posts || []).find(x => x.id === p.id);
          if (q) q.status = "awaiting_review";
        }, "reopen for fact fix: " + p.id),
        onDone: () => location.reload(),
      }));
    } else {
      bar.appendChild(ActionButton({
        id: "sched-" + p.id, groupId: "decide-" + p.id, label: "排時間", kind: "primary", doneLabel: "已排程",
        run: () => scheduleFlow(p),
        onDone: () => afterDecision(p),
      }));
    }
    bar.appendChild(rejectButton(p));
    return;
  }

  // 待審 → 核准（全部確認才可點）／退回
  const ab = ActionButton({
    id: "approve-" + p.id, groupId: "decide-" + p.id, label: "核准這篇", kind: "primary", doneLabel: "已核准",
    run: async () => {
      const secs = Math.round((Date.now() - T0) / 1000);
      const choice = {};
      (p.slides || []).forEach(s => { const c2 = CHOICE[Number(s.n)] || s.default_cid; if (c2) choice[s.n] = c2; });
      await postEvent("post.approve", p.id, { feedback: "", slide_choices: choice, copy_choice: p.copy_choice, seconds: secs });
      p.status = "approved";
      if (location.hash) history.replaceState(null, "", location.pathname);
    },
    onDone: () => afterDecision(p),
  });
  if (blocked || done < total) {
    ab.disabled = true;
    const missing = photoNs.filter(n => !CONFIRMED.has(n));
    ab.title = blocked ? "有待決項必須先處理或整篇退回"
      : "還有第 " + missing.join("、") + " 張未確認";
  }
  if (blocked) bar.appendChild(recheckButton(p));
  bar.appendChild(ab);
  bar.appendChild(rejectButton(p));
}

// 重新檢查：內容改過之後讓閘門重跑一次，取代「只能退回」。
// 事件由哨兵接手實跑 fact_check／copy_check（每 10 分一輪）。
function recheckButton(p) {
  return ActionButton({
    id: "recheck-" + p.id, label: "請我再看一次", kind: "ghost", doneLabel: "排進去了",
    run: () => postEvent("post.recheck", p.id, {}),
    onDone: () => toast(`好，我 ${SCHEDULE.SENTINEL_MIN} 分內用現在的文字重看一次事實與文案，結果直接更新在這頁。`),
  });
}

function rejectButton(p) {
  const b = el("button", "btn danger", "退回");
  b.type = "button";
  b.onclick = () => openRejectPanel(p);
  return b;
}

// 退回面板：就地展開，退什麼（多選）＋原因必填（<10 字不可送）
function openRejectPanel(p) {
  if ($("#rejPanel")) return;
  const panel = el("div", "rejectpanel"); panel.id = "rejPanel";
  panel.appendChild(el("h3", null, "退回這一篇"));
  const scopes = el("div", "scopes");
  const scopeDefs = [["底圖", "image"], ["排版", "layout"], ["文字", "copy"]];
  const checks = scopeDefs.map(([lbl]) => {
    const lab = el("label");
    const cb = el("input"); cb.type = "checkbox";
    lab.appendChild(cb); lab.appendChild(document.createTextNode(lbl));
    scopes.appendChild(lab);
    return { lbl, cb };
  });
  panel.appendChild(scopes);
  const ta = el("textarea"); ta.rows = 3; ta.placeholder = "退回原因（必填，至少 10 字）——會直接餵給下一版重做";
  panel.appendChild(ta);
  const errLine = el("div", "field-err"); errLine.style.display = "none";
  panel.appendChild(errLine);
  const row = el("div", "btnrow"); row.style.marginTop = "10px";
  row.appendChild(ActionButton({
    id: "reject-" + p.id, groupId: "decide-" + p.id, label: "送出退回", kind: "danger", doneLabel: "已退回",
    run: async () => {
      const reason = ta.value.trim();
      if (reason.length < 10) {
        errLine.textContent = "原因太短（" + reason.length + " 字）。寫清楚退什麼，下一版才改得對。";
        errLine.style.display = "block"; ta.focus();
        throw new Error("原因至少 10 字");
      }
      const scopeTxt = checks.filter(c => c.cb.checked).map(c => c.lbl).join("、");
      const secs = Math.round((Date.now() - T0) / 1000);
      const choice = {};
      (p.slides || []).forEach(s => { const c2 = CHOICE[Number(s.n)] || s.default_cid; if (c2) choice[s.n] = c2; });
      await postEvent("post.reject", p.id,
        { feedback: (scopeTxt ? "【退" + scopeTxt + "】" : "") + reason, slide_choices: choice, seconds: secs });
      p.status = "rejected";
      if (location.hash) history.replaceState(null, "", location.pathname);
    },
    onDone: () => { panel.remove(); toast("已退回。這篇轉入「系統處理中 · 重做」，完成會回到佇列。"); afterDecision(p); },
  }));
  const cancel = el("button", "btn ghost", "取消");
  cancel.onclick = () => panel.remove();
  row.appendChild(cancel);
  panel.appendChild(row);
  document.body.appendChild(panel);
  ta.focus();
}

// 排程：預設下一個 21:00，datetime-local 補時區偏移（避免早發八小時）
async function scheduleFlow(p) {
  const blocks = ((p.fact && p.fact.issues) || []).filter(i => (i.severity || i.sev) === "block");
  if (blocks.length) throw new Error(`${t("gate_fact")}有 ${blocks.length} 項未解決，不能排程`);
  const d = new Date(); d.setSeconds(0, 0); d.setHours(21, 0);
  if (d <= new Date()) d.setDate(d.getDate() + 1);
  const pad = n => String(n).padStart(2, "0");
  const localIso = x => `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}T${pad(x.getHours())}:${pad(x.getMinutes())}`;
  const wrap = el("div");
  wrap.appendChild(el("div", "small muted", esc((p.topic || p.id).slice(0, 40))));
  const inp = el("input"); inp.type = "datetime-local"; inp.value = localIso(d);
  inp.style.marginTop = "8px";
  wrap.appendChild(inp);
  wrap.appendChild(el("div", "meta", "發佈每 15 分檢查一次，實際時間可能晚幾分鐘。"));
  const ok = await modal("排程發佈", wrap, [{ label: "取消", value: null }, { label: "排定", value: 1, cls: "primary" }]);
  if (!ok || !inp.value) { const e = new Error("已取消"); e.silent = true; throw e; }
  const t2 = new Date(inp.value);
  const off = -t2.getTimezoneOffset();
  const iso = localIso(t2) + ":00" + (off >= 0 ? "+" : "-") + pad(Math.floor(Math.abs(off) / 60)) + ":" + pad(Math.abs(off) % 60);
  await postEvent("post.schedule", p.id, { publish_at: iso });
  p.status = "scheduled"; p.publish_at = iso;
  if (location.hash) history.replaceState(null, "", location.pathname);
}

function afterDecision(p) {
  const at = QUEUE.findIndex(x => x.id === p.id);
  if (at >= 0) QUEUE.splice(at, 1);
  if (IDX >= QUEUE.length) IDX = Math.max(0, QUEUE.length - 1);
  QUEUE.length ? openPost() : renderEmpty();
}

// ── 整頁渲染 ────────────────────────────────────────────────────────
function render() {
  const p = cur(); if (!p) return renderEmpty();
  const main = $("#rvMain"); main.innerHTML = "";
  $("#rvTitle").textContent = (p.topic || p.id).slice(0, 40);
  $("#rvPos").textContent = QUEUE.length > 1 ? (IDX + 1) + " / " + QUEUE.length : "";

  const pend = pendingOf(p);
  const view = statusView(p, latestReviewOf(p.id));
  main.appendChild(StatusLine({
    who: view.zone === "queue" ? "你" : "系統",
    stage: view.label,
    since: p.status_since || p.created_at,
    next: p.status === "approved" && !p.render_note
      ? "確認沒問題就按「排時間」"
      : pend.some(x => x.sev === "block")
        ? "處理卡片裡的待決項，或整篇退回"
        : "逐張確認後核准",
    tone: view.tone === "you" ? "you" : view.tone,
  }));

  main.appendChild(infoCard(p));
  const list = el("div"); list.style.marginTop = "14px";
  (p.slides || []).slice().sort((a, b) => Number(a.n) - Number(b.n))
    .forEach(s => list.appendChild(slideCard(p, s, pend)));
  main.appendChild(list);
  main.appendChild(captionCard(p));
  const ig = igPreview(p); ig.style.marginTop = "14px";
  main.appendChild(ig);
  decisionBar(p, pend);
}

function renderEmpty() {
  $("#rvMain").innerHTML = "";
  $("#rvBar").style.display = "none";
  $("#rvTitle").textContent = "審稿台";
  $("#rvPos").textContent = "";
  const box = el("div", "empty");
  box.appendChild(el("div", null, "<b>佇列清空了</b>"));
  box.appendChild(el("div", "small muted", "沒有等你審的貼文。"));
  const a = el("a", "btn", "回工作台"); a.href = "index.html"; a.style.marginTop = "10px";
  box.appendChild(a);
  $("#rvMain").appendChild(box);
}

function openPost() {
  const p = cur();
  CHOICE = {}; CROPDRAFT = {}; CONFIRMED = new Set(); EDITING = null; T0 = Date.now();
  window.scrollTo(0, 0);
  render();
}

// 確認資格：block 級待決項與禁詞文字都不可確認（按鈕與 Space 走同一條規則）
function canConfirmSlide(p, n) {
  const pend = pendingOf(p);
  if (pendOfSlide(pend, n).some(x => x.sev === "block")) return "先處理待決項";
  const s = (p.slides || []).find(x => Number(x.n) === n) || {};
  const eff = [effField(p, n, "heading", s.heading), effField(p, n, "display_copy", s.display_copy)]
    .filter(Boolean).join("\n");
  if (lintText(eff).length) return "文字含禁用詞";
  return null;
}

// ── 鍵盤 ────────────────────────────────────────────────────────────
const HELP = [["Space", "確認目前這張並跳下一張"], ["E", "改目前這張的文字"], ["1-9", "跳到第 N 張"],
              ["[ / ]", "上一篇／下一篇"], ["A", "核准"], ["R", "退回"], ["S", "排時間"], ["?", "本表"]];
function slideInView() {
  const p = cur(); if (!p) return null;
  const mid = window.innerHeight / 2;
  let best = null, bd = Infinity;
  (p.slides || []).forEach(s => {
    const e = $("#slide-" + Number(s.n)); if (!e) return;
    const r = e.getBoundingClientRect();
    const d = Math.abs((r.top + r.bottom) / 2 - mid);
    if (d < bd) { bd = d; best = Number(s.n); }
  });
  return best;
}
document.addEventListener("keydown", e => {
  if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName) || e.metaKey || e.ctrlKey) return;
  const p = cur(); if (!p) return;
  const k = e.key;
  if (k === " ") {
    e.preventDefault();
    const n = slideInView();
    if (n != null) {
      const why = canConfirmSlide(p, n);
      if (why) return toast("第 " + n + " 張不能確認：" + why, true);
      CONFIRMED.add(n); render(); scrollToNextUnconfirmed(n);
    }
    return;
  }
  if (k === "e" || k === "E") {
    const n = slideInView();
    if (n != null) { EDITING = "s" + n; render();
      const e2 = $("#slide-" + n); if (e2) e2.scrollIntoView({ block: "center" }); }
    return;
  }
  if (k >= "1" && k <= "9") { const e2 = $("#slide-" + k); if (e2) e2.scrollIntoView({ behavior: "smooth" }); return; }
  if (k === "[") { if (IDX > 0) { IDX--; openPost(); } return; }
  if (k === "]") { if (IDX < QUEUE.length - 1) { IDX++; openPost(); } return; }
  if (k === "a" || k === "A") { const btn = $(".decisionbar .btn.primary"); if (p.status === "awaiting_review" && btn && !btn.disabled) btn.click(); return; }
  if (k === "r" || k === "R") { openRejectPanel(p); return; }
  if (k === "s" || k === "S") { const btn = $(".decisionbar .btn.primary"); if (p.status === "approved" && btn && !btn.disabled) btn.click(); return; }
  if (k === "?") showHelp();
});
function showHelp() {
  const b = el("div");
  b.innerHTML = HELP.map(([a, c]) => `<div class="small" style="margin:3px 0"><kbd>${esc(a)}</kbd> ${esc(c)}</div>`).join("");
  modal("快捷鍵", b, [{ label: "關閉", value: 1 }]);
}

function loadFail(msg) {
  const main = $("#rvMain"); main.innerHTML = "";
  const card = el("div", "empty");
  card.appendChild(el("div", null, "<b>posts.json 載入失敗</b>"));
  card.appendChild(el("div", "small muted", esc(msg)));
  const row = el("div", "btnrow"); row.style.cssText = "justify-content:center;margin-top:10px";
  const b1 = el("button", "btn primary", "更新 PAT"); b1.onclick = patModal;
  const b2 = el("button", "btn", "重新載入"); b2.onclick = () => location.reload();
  row.appendChild(b1); row.appendChild(b2); card.appendChild(row);
  main.appendChild(card);
}

$("#backBtn").appendChild(icon("arrowLeft", 17));
$("#btnHelp").insertAdjacentElement("beforebegin", window.LavaUI.themeToggle());
$("#btnHelp").appendChild(icon("help", 17));
$("#btnHelp").onclick = showHelp;

loadBanned();   // 禁詞表先載，即時檢查才有料（失敗＝空表，閘門仍在後端把關）
loadAll().then(() => {
  $("#modeTag").textContent = MODE === "local" ? "· 本地預覽" : "";
  const P = STATE.posts;
  if (!P || P._error || !Array.isArray(P.posts)) { loadFail(String((P && P._error) || "資料不是預期格式")); return; }
  const gone = p => { const d = window.LavaCore.pendingDecisionOf(p.id, p.status);
    return d && (d.type === "post.schedule" || d.type === "post.reject"); };
  QUEUE = P.posts.filter(p => p.status !== "rejected" && !gone(p)
    && (p.status === "awaiting_review" || (p.status === "approved" && p.render_note)));
  const want = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (want) {
    let i = QUEUE.findIndex(p => p.id === want);
    if (i < 0) {
      const p = P.posts.find(x => x.id === want && x.status !== "rejected" && !gone(x));
      if (p) { QUEUE.unshift(p); i = 0; }
    }
    if (i >= 0) IDX = i;
  }
  if (!QUEUE.length) { renderEmpty(); return; }
  openPost();
}).catch(e => loadFail(e.message));
})();
