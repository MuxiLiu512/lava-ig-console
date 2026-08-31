/* 審稿台 v3 — 單欄審核流〔藍圖 UI 規格 §4〕
   一張 slide 一卡，逐張確認；全部確認才可核准。成品為主、候選收抽屜。
   決定＝事件檔（postEvent），哨兵折疊；rejected 永不回佇列。 */
(() => {
"use strict";
const { S, MODE, $, el, esc, saveJson, tfetch, postEvent, patModal, setImg, img, STATE, FILES, loadAll,
        toast, modal, nowISO, gatesOf, lacksMaterial, DESIGN_LAYOUTS, slidesDone } = window.LavaCore;
const { t, SCHEDULE, statusView, candSourceLabel } = window.LavaTerms;
const { icon, ago, dur, ActionButton, StatusLine } = window.LavaUI;

let QUEUE = [], IDX = 0, CHOICE = {}, CONFIRMED = new Set(), CROPDRAFT = {}, T0 = 0;

const cur = () => QUEUE[IDX];
const finalOf = s => s && (s.public_url || s.final_src);
const isDesign = s => DESIGN_LAYOUTS.includes(String((s || {}).product_layout || "")) || /CTA/i.test(String((s || {}).role || ""));
const latestReviewOf = id => {
  const rs = ((STATE.reviews && STATE.reviews.reviews) || []).filter(r => r.post_id === id);
  return rs.length ? rs[rs.length - 1] : null;
};

// ── 待決項：只有系統沒把握的才進來，掛在所屬的 slide 卡裡 ─────────────
function pendingOf(p) {
  const out = [];
  (p.slides || []).forEach(s => {
    if (lacksMaterial(s))
      out.push({ n: Number(s.n), kind: "缺圖", sev: "block", text: "這張沒有可用的圖。補圖前無法出成品。" });
  });
  ((p.qa && p.qa.issues) || []).forEach(i =>
    out.push({ n: Number((i.slides || [])[0] || 1), slides: i.slides || [], kind: t("gate_visual"),
               sev: i.severity || "warn", text: i.detail || i.type, fix: i.fix }));
  ((p.typography && p.typography.issues) || []).forEach(i =>
    out.push({ n: Number(i.slide || 1), kind: t("gate_typo"), sev: "block", text: i.rule + "：" + i.line }));
  return out;
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

// ── ① 整體資訊卡 ────────────────────────────────────────────────────
function infoCard(p) {
  const c = el("div", "card"); const pad = el("div", "pad");
  const row = el("div", "row");
  row.appendChild(el("b", null, esc(p.topic_type || "知識型")));
  row.appendChild(el("span", "meta", (p.slides || []).length + " 張"));
  if (p.template_id) row.appendChild(el("span", "meta", "範本 " + esc(p.template_id)));
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
  card.appendChild(head);

  // 主圖：成品 > 候選裁切 > 設計版面 > 缺圖面板
  const hero = el("div", "sc-hero");
  const fin = finalOf(s);
  const candSrc = srcOfCand(s, CHOICE[n] || s.default_cid) || (((s.candidates || [])[0]) || {}).src;
  if (fin) {
    if (/^https?:/.test(fin)) { const e = el("img"); e.src = fin; e.alt = "第 " + n + " 張成品"; hero.appendChild(e); }
    else hero.appendChild(img(fin));
  } else if (isDesign(s)) {
    const name = { diagram: "卡片圖解", price: "數字卡", cta: "CTA 尾板" }[String(s.product_layout || "")] || "CTA 公版";
    hero.appendChild(el("div", "design-ph", name + "：由引擎繪製，不需要照片。文字內容在下方，成品排版後回來看。"));
  } else if (candSrc) {
    const w = el("div"); w.style.cssText = "padding:12px;width:100%;display:flex;justify-content:center";
    w.appendChild(cropPreview(p, s, candSrc));
    hero.appendChild(w);
  } else {
    const boxp = el("div", "design-ph");
    boxp.appendChild(el("div", null, "這張還沒有可用的圖。系統每輪會補圖；連兩輪補不到會轉為待重新生成。"));
    hero.appendChild(boxp);
  }
  card.appendChild(hero);

  // 內文：圖上文字為主、原稿收摺疊
  const body = el("div", "sc-body");
  const rl = (p.rendered_lines || {})[String(n)];
  const linesTxt = (Array.isArray(rl) && rl.length) ? rl.join("\n")
    : [s.heading, s.display_copy].filter(Boolean).join("\n");
  if (linesTxt) {
    body.appendChild(el("div", "meta", Array.isArray(rl) && rl.length ? "圖上實際呈現" : "圖上文字（尚未排版）"));
    const pre = el("div", "sc-lines"); pre.textContent = linesTxt;
    pre.style.marginTop = "4px";
    body.appendChild(pre);
  }
  if (!fin && candSrc && !isDesign(s)) {
    const note = el("div", "sc-note");
    note.appendChild(icon("alert", 13));
    note.appendChild(el("span", null, "排版後才是最終樣子"));
    body.appendChild(note);
  }
  // 本張待決項就地展開
  pendOfSlide(pend, n).forEach(x => {
    const d = el("div", "pend" + (x.sev === "block" ? " block" : ""));
    d.innerHTML = `<b class="k">${esc(x.kind)}</b> · ${esc(String(x.text).slice(0, 200))}`;
    if (x.fix) d.appendChild(el("div", "fix", "建議：" + esc(String(x.fix).slice(0, 160))));
    body.appendChild(d);
  });
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

  // 卡尾：確認本張
  const foot = el("div", "sc-foot");
  const blocked = pendOfSlide(pend, n).some(x => x.sev === "block");
  const cb = el("button", "btn " + (CONFIRMED.has(n) ? "ghost" : "primary"));
  cb.type = "button";
  cb.textContent = CONFIRMED.has(n) ? "取消確認" : "確認這張";
  if (blocked && !CONFIRMED.has(n)) {
    cb.disabled = true;
    foot.appendChild(el("span", "meta", "先處理上面的待決項才能確認"));
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

// ── ③ 貼文文案卡 ────────────────────────────────────────────────────
function captionCard(p) {
  const c = el("div", "card"); const pad = el("div", "pad");
  pad.appendChild(el("div", "meta", t("caption")));
  const pre = el("div", "sc-lines"); pre.style.marginTop = "4px";
  pre.textContent = p.caption || "（無文案）";
  pad.appendChild(pre);
  const info = el("div", "meta"); info.style.marginTop = "6px";
  const tags = (String(p.caption || "").match(/#[^\s#]+/g) || []).length;
  info.textContent = `${String(p.caption || "").length} 字 · ${tags} 個 hashtag`;
  pad.appendChild(info);
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
    cap.innerHTML = `<span class="nm">lava_dating</span><span class="body clamp">${esc(p.caption || "")}</span>`;
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
    // 已核准 → 排時間（事實閘門前置）
    const factBlocks = ((p.fact && p.fact.issues) || []).filter(i => (i.severity || i.sev) === "block");
    if (factBlocks.length) {
      bar.appendChild(el("span", "meta", `${t("gate_fact")}未過 ${factBlocks.length} 項，不能排程`));
      bar.appendChild(ActionButton({
        id: "reopen-" + p.id, label: "退回待審修正", kind: "primary", doneLabel: "已退回待審",
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
  bar.appendChild(ab);
  bar.appendChild(rejectButton(p));
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
  if (!ok || !inp.value) throw new Error("已取消");
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
  CHOICE = {}; CROPDRAFT = {}; CONFIRMED = new Set(); T0 = Date.now();
  window.scrollTo(0, 0);
  render();
}

// ── 鍵盤 ────────────────────────────────────────────────────────────
const HELP = [["Space", "確認目前這張並跳下一張"], ["1-9", "跳到第 N 張"],
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
    if (n != null) { CONFIRMED.add(n); render(); scrollToNextUnconfirmed(n); }
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
$("#btnHelp").appendChild(icon("help", 17));
$("#btnHelp").onclick = showHelp;

loadAll().then(() => {
  $("#modeTag").textContent = MODE === "local" ? "· 本地預覽" : "";
  const P = STATE.posts;
  if (!P || P._error || !Array.isArray(P.posts)) { loadFail(String((P && P._error) || "資料不是預期格式")); return; }
  QUEUE = P.posts.filter(p => p.status !== "rejected"
    && (p.status === "awaiting_review" || (p.status === "approved" && p.render_note)));
  const want = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (want) {
    let i = QUEUE.findIndex(p => p.id === want);
    if (i < 0) {
      const p = P.posts.find(x => x.id === want && x.status !== "rejected");
      if (p) { QUEUE.unshift(p); i = 0; }
    }
    if (i >= 0) IDX = i;
  }
  if (!QUEUE.length) { renderEmpty(); return; }
  openPost();
}).catch(e => loadFail(e.message));
})();
