/* 審稿台 v2 — 〔UIUX 總體架構 §2.2／§3.1／§4〕
   設計主張：把審稿從「逐張決定」改成「例外決定」。
   系統對每張都已有建議選擇，Jesse 只被要求處理系統沒把握的部分（待決項）。
   主舞台放的是**成品**不是候選圖——人要判斷的是「這張能不能發」，底圖只是手段。
   與舊介面並存，隨時可從左上角切回。 */
(() => {
"use strict";
const { S, MODE, $, el, esc, saveJson, patModal, setImg, img, STATE, FILES, loadAll, toast, modal, nowISO, rid } = window.LavaCore;

const FILE_EFFORT = "data/effort_log.json";
let QUEUE = [], IDX = 0, SLIDE = 1, PEND = [], PI = 0, CHOICE = {}, T0 = 0;

// ── 三維狀態（§3.1）：階段單選、閘門四點、警示最多一個 ──────────────
function stageOf(p) {
  if (p.status === "published") return ["已發", "var(--stage-done)"];
  if (p.status === "scheduled") return ["已排", "var(--stage-sched)"];
  if (p.status === "awaiting_review" || p.render_note) return ["等你", "var(--stage-you)"];
  if (p.status === "approved") {
    const done = (p.slides || []).every(s => s.final_src || s.public_url);
    return done ? ["待排", "var(--stage-wait)"] : ["製作中", "var(--stage-make)"];
  }
  return ["候選", "#4b5057"];
}
// 順序固定＝管線順序，位置固定才能被肌肉記憶（§3.1 維度 B）
function gatesOf(p) {
  const g = x => (x == null ? "" : x.pass === true ? "ok" : (x.issues || []).some(i => i.severity === "block") ? "bad" : "warn");
  return [["文案", ""], ["事實", ""], ["視覺", g(p.qa)], ["排版", g(p.typography)]];
}
function alertOf(p) {
  if (p.render_note) return "卡住";
  if ((p.slides || []).some(s => needsImg(s) && !(s.candidates || []).length)) return "缺料";
  return null;
}
// CTA／設計底不需要底圖；用「有沒有 candidates 欄位」判斷會把設計底誤判成缺料
const needsImg = s => !/CTA/i.test(String(s.role || "")) && !!(s.candidates || []).length || (!/CTA/i.test(String(s.role || "")) && s.n !== undefined && (s.candidates || []).length === 0 && !s.final_src);

// ── 待決項（§4.2）：只有系統沒把握的才進來 ───────────────────────────
function pendingOf(p) {
  const out = [];
  (p.slides || []).forEach(s => {
    if (needsImg(s) && !(s.candidates || []).length)
      out.push({ n: s.n, kind: "缺料", sev: "block", text: "這張沒有任何候選圖，補圖前無法出成品" });
  });
  // 一個問題算一項，不按受影響張數展開——同一個「四張版型雷同」被拆成 4 項會讓
  // 「本篇待決 N 項」失去意義（實測第一篇因此顯示 14 項）。
  ((p.qa && p.qa.issues) || []).forEach(i =>
    out.push({ n: (i.slides || [])[0] || 1, slides: i.slides || [], kind: "視覺",
               sev: i.severity || "warn", text: i.detail || i.type, fix: i.fix }));
  ((p.typography && p.typography.issues) || []).forEach(i =>
    out.push({ n: i.slide || 1, kind: "排版", sev: "block", text: i.rule + "：" + i.line }));
  if (p.render_note) out.push({ n: 1, kind: "卡住", sev: "block", text: p.render_note });
  return out.sort((a, b) => (a.sev === b.sev ? a.n - b.n : a.sev === "block" ? -1 : 1));
}

const cur = () => QUEUE[IDX];
const slideOf = (p, n) => (p.slides || []).find(s => String(s.n) === String(n));
const finalOf = s => s && (s.public_url || s.final_src);

// ── 版面 ────────────────────────────────────────────────────────────
function renderQueue() {
  const box = $("#rvQueue"); box.innerHTML = "";
  QUEUE.forEach((p, i) => {
    const [label, color] = stageOf(p);
    const c = el("div", "rv-q" + (i === IDX ? " on" : ""));
    c.style.borderLeftColor = color;
    c.appendChild(el("div", "t", esc((p.topic || p.id).slice(0, 34))));
    const row = el("div", "row", ""); row.style.justifyContent = "space-between";
    const g = el("div", "gates");
    gatesOf(p).forEach(([, st]) => { const d = el("i", "gate " + st); d.title = ""; g.appendChild(d); });
    row.appendChild(g);
    const a = alertOf(p);
    row.appendChild(el("span", "small muted", esc(a ? a : label)));
    c.appendChild(row);
    c.onclick = () => { IDX = i; openPost(); };
    box.appendChild(c);
  });
}

function renderStage() {
  const p = cur(); if (!p) return;
  const hero = $("#rvHero"); hero.innerHTML = "";
  const s = slideOf(p, SLIDE);
  const src = finalOf(s) || (CHOICE[SLIDE] && srcOfCand(s, CHOICE[SLIDE]));
  if (src && /^https?:/.test(src)) { const e = el("img"); e.src = src; hero.appendChild(e); }
  else if (src) hero.appendChild(img(src));
  else hero.appendChild(el("div", "empty", "第 " + SLIDE + " 張還沒有成品"));

  const film = $("#rvFilm"); film.innerHTML = "";
  const pendN = new Set(); PEND.forEach(x => { (x.slides && x.slides.length ? x.slides : [x.n]).forEach(n => pendN.add(String(n))); });
  (p.slides || []).forEach(sl => {
    const w = el("span", (String(sl.n) === String(SLIDE) ? "sel " : "") + (pendN.has(String(sl.n)) ? "pend" : ""));
    const src2 = finalOf(sl) || ((sl.candidates || [])[0] || {}).src;
    if (src2 && /^https?:/.test(src2)) { const e = el("img"); e.src = src2; w.appendChild(e); }
    else if (src2) w.appendChild(img(src2));
    else w.appendChild(el("img", "imgfail"));
    w.appendChild(el("b", null, esc(String(sl.n))));
    w.onclick = () => { SLIDE = Number(sl.n); renderStage(); renderSide(); };
    film.appendChild(w);
  });
}

const srcOfCand = (s, cid) => ((s && s.candidates) || []).find(c => c.cid === cid) ?
  ((s.candidates || []).find(c => c.cid === cid).src) : null;

function renderSide() {
  const p = cur(); const box = $("#rvSide"); box.innerHTML = "";
  if (!p) return;
  const s = slideOf(p, SLIDE);

  // 本張的待決項在最上面，J/K 跳的就是這個
  const mine = PEND.filter(x => (x.slides && x.slides.length ? x.slides : [x.n]).some(n => String(n) === String(SLIDE)));
  mine.forEach(x => {
    const d = el("div", "rv-pend" + (PEND[PI] === x ? " on" : ""));
    d.appendChild(el("div", "small", `<b style="color:${x.sev === "block" ? "var(--stage-you)" : "var(--stage-wait)"}">${esc(x.kind)}</b> · 第 ${esc((x.slides && x.slides.length ? x.slides : [x.n]).join("、"))} 張`));
    d.appendChild(el("div", "small muted", esc(x.text).slice(0, 300)));
    if (x.fix) d.appendChild(el("div", "small", "建議：" + esc(x.fix).slice(0, 200)));
    box.appendChild(d);
  });

  // 圖上實際呈現：主，原稿收摺疊（§段3-16，rendered_lines 早就有，只是主從搞反）
  const rl = (p.rendered_lines || {})[String(SLIDE)];
  if (rl && rl.length) {
    box.appendChild(el("div", "small muted", "圖上實際呈現"));
    const pre = el("div", "small"); pre.style.cssText = "background:#16181c;border-radius:6px;padding:8px;white-space:pre-wrap;margin:4px 0 10px";
    pre.textContent = (Array.isArray(rl) ? rl : []).join("\n");   // 引擎輸出就是逐行字串陣列
    box.appendChild(pre);
  }
  if (s) {
    const det = el("details"); det.appendChild(el("summary", "small muted", "原始文案"));
    const t = el("div", "small muted"); t.style.whiteSpace = "pre-wrap";
    t.textContent = (s.heading || "") + "\n\n" + (s.display_copy || "");
    det.appendChild(t); box.appendChild(det);
  }

  // 候選圖：預設只顯示前 6 張（策展分數最高者），看全部是次要按鈕
  const cands = (s && s.candidates) || [];
  if (cands.length) {
    box.appendChild(el("div", "small muted", `候選圖 ${cands.length} 張`));
    const grid = el("div", "rv-cand"); grid.style.margin = "6px 0";
    let shown = 6;
    const paint = () => {
      grid.innerHTML = "";
      cands.slice(0, shown).forEach(c => {
        const w = el("span", (CHOICE[SLIDE] || s.default_cid) === c.cid ? "on" : "");
        w.appendChild(img(c.src));
        w.onclick = () => { CHOICE[SLIDE] = c.cid; renderStage(); renderSide(); };
        grid.appendChild(w);
      });
    };
    paint(); box.appendChild(grid);
    if (cands.length > 6) {
      const more = el("button", "btn", `看全部 ${cands.length} 張`);
      more.onclick = () => { shown = cands.length; paint(); more.remove(); };
      box.appendChild(more);
    }
  }
}

function renderBar() {
  const p = cur();
  $("#rvPendCount").innerHTML = p
    ? `<b>${esc((p.topic || p.id).slice(0, 26))}</b> · 本篇待決 <b style="color:${PEND.length ? "var(--stage-you)" : "var(--stage-done)"}">${PEND.length}</b> 項 · ${IDX + 1}/${QUEUE.length}`
    : "";
  const bar = $("#rvActions"); bar.innerHTML = "";
  if (!p) return;
  const mk = (t, cls, fn) => { const b = el("button", "btn " + cls, t); b.onclick = fn; bar.appendChild(b); return b; };
  const blocked = PEND.some(x => x.sev === "block");
  // block 級不可被「全部採用建議」略過（§4.2）
  mk("全部採用建議", "", () => { PEND.filter(x => x.sev !== "block").forEach(x => { }); toast(blocked ? "仍有 block 項必須逐項處理" : "已採用系統建議"); });
  const a = mk("核准 A", "primary", () => decide("approve"));
  if (blocked) {
    a.disabled = true; a.style.opacity = ".38"; a.style.cursor = "not-allowed";
    a.textContent = "核准（被擋）";
    a.title = "有 block 級待決項，必須先處理或整篇退回";
  }
  mk("退回 R", "", () => decide("reject"));
}

// ── 決定 + 北極星埋點 ────────────────────────────────────────────────
async function decide(decision) {
  const p = cur(); if (!p) return;
  let feedback = "";
  if (decision === "reject") {
    const ta = el("textarea"); ta.rows = 3; ta.style.width = "100%";
    const ok = await modal("退回原因（必填）", ta, [{ label: "取消", value: null }, { label: "退回", value: 1, cls: "primary" }]);
    if (!ok || !ta.value.trim()) return toast("退回必須填寫回饋", true);
    feedback = ta.value.trim();
  }
  const choice = {};
  (p.slides || []).forEach(s => { const c = CHOICE[s.n] || s.default_cid; if (c) choice[s.n] = c; });
  const review = { id: rid("R"), post_id: p.id, ts: nowISO(), decision, slide_choices: choice,
                   scope: null, feedback, consumed: false, copy_choice: p.copy_choice || undefined };
  const secs = Math.round((Date.now() - T0) / 1000);
  try {
    await saveJson(FILES.reviews, d => { (d.reviews = d.reviews || []).push(review); }, `review: ${decision} ${p.id}`);
    if (decision === "approve")
      await saveJson(FILES.posts, d => { const q = (d.posts || []).find(x => x.id === p.id); if (q) q.status = "approved"; }, `approve: ${p.id}`);
    // 北極星：每篇消耗的分鐘數。晚一天埋就永久少一天資料（§6 B0）
    await saveJson(FILE_EFFORT, d => {
      (d.entries = d.entries || []).push({ post_id: p.id, ts: nowISO(), decision,
        seconds: secs, pending: PEND.length, slides: (p.slides || []).length });
    }, `effort: ${p.id} ${secs}s`).catch(() => {});
    toast(`已${decision === "approve" ? "核准" : "退回"} ✓（${secs} 秒）`);
    QUEUE.splice(IDX, 1); if (IDX >= QUEUE.length) IDX = 0;
    openPost();
  } catch (e) { toast(e.message, true); }
}

// ── 開一篇 ──────────────────────────────────────────────────────────
function openPost() {
  const p = cur();
  CHOICE = {}; SLIDE = 1; PI = 0; T0 = Date.now();
  PEND = p ? pendingOf(p) : [];
  if (PEND.length) SLIDE = Number(PEND[0].n) || 1;
  renderQueue(); renderBar(); renderStage(); renderSide();
}

// ── 鍵盤（§4.3，全站一致）────────────────────────────────────────────
const HELP = [["J / K", "下一個／上一個待決項"], ["[ / ]", "上一篇／下一篇"], ["1-9", "跳到第 N 張"],
              ["E", "編輯本張文案"], ["A", "核准"], ["R", "退回"], ["S", "排程"], ["?", "本表"]];
document.addEventListener("keydown", e => {
  if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName) || e.metaKey || e.ctrlKey) return;
  const k = e.key;
  if (k >= "1" && k <= "9") { SLIDE = Number(k); PI = PEND.findIndex(x => String(x.n) === k); renderStage(); renderSide(); return; }
  if (k === "j" || k === "J") { if (PEND.length) { PI = (PI + 1) % PEND.length; SLIDE = Number(PEND[PI].n); renderStage(); renderSide(); } return; }
  if (k === "k" || k === "K") { if (PEND.length) { PI = (PI - 1 + PEND.length) % PEND.length; SLIDE = Number(PEND[PI].n); renderStage(); renderSide(); } return; }
  if (k === "[") { if (IDX > 0) { IDX--; openPost(); } return; }
  if (k === "]") { if (IDX < QUEUE.length - 1) { IDX++; openPost(); } return; }
  if (k === "a" || k === "A") { if (!PEND.some(x => x.sev === "block")) decide("approve"); else toast("有 block 級待決項", true); return; }
  if (k === "r" || k === "R") { decide("reject"); return; }
  if (k === "?") showHelp();
});
function showHelp() {
  const b = el("div"); b.innerHTML = HELP.map(([a, c]) => `<div class="small" style="margin:3px 0"><kbd>${esc(a)}</kbd> ${esc(c)}</div>`).join("");
  modal("快捷鍵", b, [{ label: "關閉", value: 1 }]);
}
$("#btnHelp").onclick = showHelp;

function loadFail(msg) {
  // 空狀態與失敗狀態必須是兩個畫面：載入失敗時畫「佇列清空🎉」等於對使用者說謊
  const h = $("#rvHero"); h.innerHTML = "";
  const card = el("div", "empty");
  card.appendChild(el("div", null, "<b>posts.json 載入失敗</b>"));
  card.appendChild(el("div", "small muted", esc(msg)));
  const row = el("div", "row"); row.style.cssText = "gap:8px;justify-content:center;margin-top:10px";
  const b1 = el("button", "btn primary", "更新 PAT"); b1.onclick = patModal;
  const b2 = el("button", "btn", "重新載入"); b2.onclick = () => location.reload();
  row.appendChild(b1); row.appendChild(b2); card.appendChild(row);
  h.appendChild(card);
}

loadAll().then(() => {
  $("#modeTag").textContent = MODE === "local" ? "· 本地預覽" : "";
  const P = STATE.posts;
  if (!P || P._error || !Array.isArray(P.posts)) { loadFail(String((P && P._error) || "資料不是預期格式")); return; }
  QUEUE = P.posts.filter(p => p.status === "awaiting_review" || (p.status === "approved" && p.render_note));
  if (!QUEUE.length) { $("#rvHero").innerHTML = ""; $("#rvHero").appendChild(el("div", "empty", "佇列清空了 🎉")); renderBar(); return; }
  openPost();
}).catch(e => loadFail(e.message));
})();
