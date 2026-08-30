/* 審稿台 v2 — 〔UIUX 總體架構 §2.2／§3.1／§4〕
   設計主張：把審稿從「逐張決定」改成「例外決定」。
   系統對每張都已有建議選擇，Jesse 只被要求處理系統沒把握的部分（待決項）。
   主舞台放的是**成品**不是候選圖——人要判斷的是「這張能不能發」，底圖只是手段。
   與舊介面並存，隨時可從左上角切回。 */
(() => {
"use strict";
const { S, MODE, $, el, esc, saveJson, tfetch, postEvent, patModal, setImg, img, STATE, FILES, loadAll, toast, modal, nowISO, rid, stageOf, gatesOf, alertOf, lacksMaterial, DESIGN_LAYOUTS } = window.LavaCore;

const FILE_EFFORT = "data/effort_log.json";
let QUEUE = [], IDX = 0, SLIDE = 1, PEND = [], PI = 0, CHOICE = {}, T0 = 0;

// ── 待決項（§4.2）：只有系統沒把握的才進來 ───────────────────────────
function pendingOf(p) {
  const out = [];
  (p.slides || []).forEach(s => {
    if (lacksMaterial(s))
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

// 候選圖的來源標籤。source_kind 是機器用的代號，這裡翻成人看得懂的字。
// -ap 檔名前綴＝Apify（Google 圖片）路線，其餘 SHOT 是策展截圖。
function srcTag(c) {
  const f = String(c.src || "");
  const k = String(c.source_kind || "");
  if (k === "SHOT") return /-SHOT-[a-z]-ap/.test(f)
    ? { text: "Google 圖片", color: "#1a73c7" }
    : { text: "策展截圖", color: "#4b5057" };
  if (k === "WM") return { text: "Wikimedia", color: "#5a6b3a" };
  if (k === "OV") return { text: "Open Library", color: "#5a6b3a" };
  if (k === "DESIGN") return { text: "設計底", color: "#4b5057" };
  if (c.kind === "generated") return { text: "生成圖", color: "#6b4a7a" };
  return { text: c.source_label ? String(c.source_label).slice(0, 12) : "劇照", color: "#7a4a2a" };
}

const srcOfCand = (s, cid) => (((s && s.candidates) || []).find(c => c.cid === cid) || {}).src || null;

// ── 裁切（2026-08-20 Jesse：底圖是 16:9 時要能直接裁）────────────────
// 無成品時主舞台不再滿版丟原始候選（看起來像壞掉），改成 4:5 裁切預覽：
// object-position 的數學與引擎 fit_bg(focus) 完全一致，拖到哪就裁到哪，預覽即成品。
let CROPDRAFT = {};   // {slide: [fx, fy]} 未儲存的拖曳；openPost 時清空

function frameAspectOf(s, im) {
  // 取景框比例只信 posts.json 存的數字（源頭是 render_product.frame_specs，A9）。
  const fa = s && s.frame_aspect;
  if (typeof fa === "number") return fa;
  if (fa && typeof fa === "object" && im && im.naturalWidth)
    return im.naturalHeight > im.naturalWidth ? fa.portrait : fa.landscape;
  return 4 / 5;               // 知識型：滿版 4:5
}

function cropPreview(p, s, path) {
  const wrap = el("div", "rv-cropwrap");
  const box = el("div", "rv-crop");
  const im = el("img"); im.draggable = false;
  const isProduct = !!(s && s.product_layout);
  const applyAspect = () => { box.style.aspectRatio = String(frameAspectOf(s, im)); };
  im.addEventListener("load", applyAspect); applyAspect();
  const focus = () => CROPDRAFT[SLIDE] || s.crop_focus || [0.5, 0.5];
  const paint = () => { const [fx, fy] = focus(); im.style.objectPosition = (fx * 100) + "% " + (fy * 100) + "%"; };
  setImg(im, path); paint();
  box.appendChild(im);
  box.appendChild(el("div", "crop-badge", isProduct
    ? "照片將置入卡片 · 拖曳調整取景"
    : "底圖候選 · 4:5 裁切預覽 · 拖曳調整"));
  const bar = el("div", "crop-bar");
  const save = el("button", "btn primary", "儲存裁切");
  const reset = el("button", "btn", "重設置中");
  const dirty = () => { bar.style.display = "flex"; };
  if (CROPDRAFT[SLIDE]) dirty();
  save.onclick = async () => {
    const v = [Math.round(focus()[0] * 1000) / 1000, Math.round(focus()[1] * 1000) / 1000];
    try {
      await saveJson(FILES.posts, d => {
        const q = (d.posts || []).find(x => x.id === p.id);
        const sl = q && (q.slides || []).find(x => String(x.n) === String(SLIDE));
        if (sl) sl.crop_focus = v;
      }, `crop: ${p.id} s${SLIDE}`);
      s.crop_focus = v; delete CROPDRAFT[SLIDE]; bar.style.display = "none";
      toast("裁切已儲存 ✓ 核准後重出成品生效");
    } catch (e) { toast(e.message, true); }
  };
  reset.onclick = () => { CROPDRAFT[SLIDE] = [0.5, 0.5]; paint(); dirty(); };
  bar.appendChild(save); bar.appendChild(reset);
  // 拖曳：位移換算成裁切窗在溢出量上的比例（cover 模式只有一軸有溢出）
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
    // 圖本身已是 4:5（無溢出）時拖曳不改變任何東西，儲存列不該跳出來
    if (Math.abs(nf[0] - focus()[0]) < 0.002 && Math.abs(nf[1] - focus()[1]) < 0.002) return;
    CROPDRAFT[SLIDE] = nf;
    paint(); dirty();
  };
  box.onpointerup = box.onpointercancel = () => { drag = null; };
  wrap.appendChild(box); wrap.appendChild(bar);
  return wrap;
}

function renderStage() {
  const p = cur(); if (!p) return;
  const hero = $("#rvHero"); hero.innerHTML = "";
  const s = slideOf(p, SLIDE);
  const fin = finalOf(s);
  const lay = String((s || {}).product_layout || "");
  const isDesign = DESIGN_LAYOUTS.includes(lay) || /CTA/i.test(String((s || {}).role || ""));
  const cand = srcOfCand(s, CHOICE[SLIDE] || (s || {}).default_cid) || (((s || {}).candidates || [])[0] || {}).src;
  if (fin) {
    if (/^https?:/.test(fin)) { const e = el("img"); e.src = fin; hero.appendChild(e); }
    else hero.appendChild(img(fin));
  } else if (isDesign) {
    const name = { diagram: "卡片圖解", price: "數字卡", cta: "CTA 尾板" }[lay] || "設計版面";
    hero.appendChild(el("div", "empty",
      name + "：由引擎繪製，不需要照片。文字內容見右欄，成品渲染後回來看。"));
  } else if (cand) {
    hero.appendChild(cropPreview(p, s, cand));
  } else {
    const box = el("div", "empty");
    const rg = p.regen_needed;
    box.appendChild(el("div", null, rg
      ? `第 ${SLIDE} 張補不到圖。哨兵已重試 ${(rg.slides || []).length ? "多輪" : ""}仍失敗，代表視覺企劃本身有問題。`
      : `第 ${SLIDE} 張沒有候選圖也沒有成品。哨兵每輪會嘗試補圖。`));
    const rw = el("div", "row"); rw.style.cssText = "gap:8px;justify-content:center;margin-top:10px";
    const rb = el("button", "btn primary", "♻ 重新生成這一篇");
    rb.onclick = () => regenFromReview(p, rb);
    rw.appendChild(rb);
    box.appendChild(rw);
    hero.appendChild(box);
  }

  const film = $("#rvFilm"); film.innerHTML = "";
  const pendN = new Set(); PEND.forEach(x => { (x.slides && x.slides.length ? x.slides : [x.n]).forEach(n => pendN.add(String(n))); });
  (p.slides || []).forEach(sl => {
    const w = el("span", (String(sl.n) === String(SLIDE) ? "sel " : "") + (pendN.has(String(sl.n)) ? "pend" : ""));
    const src2 = finalOf(sl) || ((sl.candidates || [])[0] || {}).src;
    if (src2 && /^https?:/.test(src2)) { const e = el("img"); e.src = src2; w.appendChild(e); }
    else if (src2) w.appendChild(img(src2));
    else if (DESIGN_LAYOUTS.includes(String(sl.product_layout || "")) || /CTA/i.test(String(sl.role || ""))) {
      const lbl = { diagram: "圖解", price: "數字卡", cta: "CTA<br>公版" }[String(sl.product_layout || "")] || "CTA<br>公版";
      w.appendChild(el("div", "cta-ph", lbl));
    }
    else w.appendChild(el("img", "imgfail"));
    w.appendChild(el("b", null, esc(String(sl.n))));
    w.onclick = () => { SLIDE = Number(sl.n); renderStage(); renderSide(); };
    film.appendChild(w);
  });
}

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
    // 說清楚點了會怎樣。原本只寫「候選圖 N 張」，能點但沒有任何說明，
    // 也看不出哪一張是目前選中的（Jesse 2026-08-25：點了要幹麻？）。
    box.appendChild(el("div", "small muted",
      `第 ${SLIDE} 張的候選底圖 ${cands.length} 張 · <b>點一張＝選它當這張的底圖</b>，核准後用它出成品`));
    const grid = el("div", "rv-cand"); grid.style.margin = "6px 0";
    let shown = 6;
    const paint = () => {
      grid.innerHTML = "";
      const picked = CHOICE[SLIDE] || s.default_cid;
      cands.slice(0, shown).forEach(c => {
        const on = picked === c.cid;
        const w = el("span", on ? "on" : "");
        w.appendChild(img(c.src));
        // 出處標在圖上，不只放在 hover〔Jesse 2026-08-27：請標注照片的來源〕。
        // 兩條取圖路線（n8n 劇照工作流／Apify Google 圖片）並存後，
        // 看得出哪張是誰找來的，才有辦法判斷哪個來源值得留。
        const src = srcTag(c);
        w.title = (c.source_label || c.source_kind || c.kind || "候選") +
                  (c.low_q ? "（畫質偏低）" : "") + (on ? "／目前選用" : "／點擊選用");
        const sb = el("b", null, esc(src.text));
        sb.style.cssText = "position:absolute;left:2px;top:2px;background:" + src.color +
          ";color:#fff;font-size:9px;padding:0 3px;border-radius:3px;line-height:13px;max-width:92%;" +
          "overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
        w.style.position = "relative";
        w.appendChild(sb);
        if (c.low_q) {
          const lq = el("b", null, "低畫質");
          lq.style.cssText = "position:absolute;right:2px;top:2px;background:#8a5a00;color:#fff;" +
            "font-size:9px;padding:0 3px;border-radius:3px;line-height:13px";
          w.appendChild(lq);
        }
        if (on) {
          const tag = el("b", null, "使用中");
          tag.style.cssText = "position:absolute;left:2px;bottom:2px;background:var(--stage-done,#3fa66a);" +
            "color:#fff;font-size:10px;padding:0 4px;border-radius:3px;line-height:14px";
          w.style.position = "relative";
          w.appendChild(tag);
        }
        w.onclick = () => {
          CHOICE[SLIDE] = c.cid;
          toast("第 " + SLIDE + " 張改用這張底圖，核准後生效");
          renderStage(); renderSide();
        };
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

  // 動作列要跟著貼文的階段走。原本不論狀態一律顯示「核准／退回」，
  // 於是從看板點「待排」（已核准）的稿進來，看到的是一顆停用的「核准（被擋）」——
  // 已經核准過的東西再問要不要核准，而真正該做的「排程」只綁在鍵盤 S、畫面上沒有按鈕
  //（Jesse 2026-08-25：點到待排程的貼文，沒看到哪裡可以上架排程）。
  if (p.status === "approved" && !p.render_note) {
    const factBlocks = ((p.fact && p.fact.issues) || []).filter(i => (i.severity || i.sev) === "block");
    if (factBlocks.length) {
      // 死路修正〔Jesse 2026-08-26：事實未過又在待排程裡面，我也沒辦法按任何下一步〕
      // 這些稿是在事實閘門上線「之前」核准的，之後才被驗出問題。
      // 只給一顆停用的按鈕等於把人鎖死——要嘛回審稿修，要嘛整篇退回。
      const back = mk("← 退回待審修正", "primary", async () => {
        try {
          await saveJson(FILES.posts, doc => {
            const q = (doc.posts || []).find(x => x.id === p.id);
            if (q) q.status = "awaiting_review";
          }, "reopen for fact fix: " + p.id);
          toast("已退回待審 ✓ 事實問題列在右欄待決項，逐項處理後再核准");
          location.reload();
        } catch (e) { toast(e.message, true); }
      });
      back.title = "事實查核有 " + factBlocks.length + " 項：" + (factBlocks[0].line || "");
      const w = el("span", "small muted", `事實未過 ${factBlocks.length} 項，不能排程`);
      w.style.cssText = "align-self:center;margin:0 8px;color:var(--stage-you)";
      bar.appendChild(w);
      mk("整篇退回重做 R", "", () => decide("reject"));
      return;
    }
    mk("📅 排程發佈", "primary", () => scheduleCur());
    mk("退回重做 R", "", () => decide("reject"));
    return;
  }

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
  const secs = Math.round((Date.now() - T0) / 1000);
  try {
    // 決定＝一個事件檔（永不撞 sha）。posts/reviews 由哨兵這個唯一寫者折疊，
    // rejected 是明確狀態，從此進不了佇列——結構性終結「退回又跑回來」。
    await postEvent("post." + decision, p.id,
      { feedback, slide_choices: choice, copy_choice: p.copy_choice, seconds: secs, pending: PEND.length });
    p.status = decision === "approve" ? "approved" : "rejected";
    if (location.hash) history.replaceState(null, "", location.pathname);
    toast(`已${decision === "approve" ? "核准" : "退回"} ✓（${secs} 秒）`);
    // 用 id 移除，不能用 IDX〔Jesse 2026-08-27：按退回後換下一篇，
    // 結果要退回的還在、下一篇卻不見了〕。退回要填原因、期間是可以點左欄
    // 換篇的，IDX 因此在 await 之間被改掉，splice(IDX) 砍到的是換過去的那一篇。
    const at = QUEUE.findIndex(x => x.id === p.id);
    if (at >= 0) QUEUE.splice(at, 1);
    if (IDX >= QUEUE.length) IDX = Math.max(0, QUEUE.length - 1);
    openPost();
  } catch (e) { toast(e.message, true); }
}

async function regenFromReview(p, btn) {
  const ok = await modal("重新生成這一篇？",
    el("div", "small muted",
      "會用同一個主題重跑撰稿與視覺企劃，並要求每張都給得出可取得的具體素材。舊版留在 Drive。約 6 分寫完，最晚 20 分入板。"),
    [{ label: "取消", value: null }, { label: "重新生成", value: 1, cls: "primary" }]);
  if (!ok) return;
  btn.disabled = true; btn.textContent = "已送出…";
  try {
    const r = await tfetch("https://lavadating.app.n8n.cloud/webhook/lava-ig-draft", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: p.topic || p.id, type: "知識型", slides: 9,
        angle: "重新生成：前一版有 slide 補不到合適圖片，請調整視覺企劃，每張都要給具體、公開可取得的素材（具名人物／具名作品／可截圖的頁面）",
        taskId: p.clickup_task_id || "", writer: "claude" }),
    }, 20000);
    if (!r.ok) throw new Error("觸發失敗 (" + r.status + ")");
    toast("已送出重新生成 ✓ 最晚 20 分後會有新版草稿");
  } catch (e) { btn.disabled = false; btn.textContent = "♻ 重新生成這一篇"; toast(e.message, true); }
}

// ── 排程（快捷鍵 S）────────────────────────────────────────────────
// 這個動作原本只寫在說明表裡、沒有實作，所以「待排」欄的稿點進來無事可做
// （Jesse 2026-08-25：點待排只會跳到審稿台，壞了？）。
// 閘門在這裡就要擋：I9 不變量會拒絕「事實查核有 block 卻排程」的稿，
// 若等到 CI 才擋，人已經以為排好了。
async function scheduleCur() {
  const p = cur(); if (!p) return;
  if (p.status !== "approved")
    return toast("只有已核准的稿能排程（目前：" + (p.status || "未知") + "）", true);
  const blocks = ((p.fact && p.fact.issues) || []).filter(i => (i.severity || i.sev) === "block");
  if (blocks.length)
    return toast(`事實查核有 ${blocks.length} 項未解決，不能排程：${blocks[0].line || ""}`.slice(0, 90), true);

  const d = new Date(); d.setSeconds(0, 0);
  d.setHours(21, 0);                                  // 預設今晚 21:00；過了就明晚
  if (d <= new Date()) d.setDate(d.getDate() + 1);
  const pad = n => String(n).padStart(2, "0");
  const localIso = x => `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}T${pad(x.getHours())}:${pad(x.getMinutes())}`;
  const wrap = el("div");
  wrap.appendChild(el("div", "small muted", esc((p.topic || p.id).slice(0, 40))));
  const inp = el("input"); inp.type = "datetime-local"; inp.value = localIso(d);
  inp.style.cssText = "margin-top:8px;width:100%";
  wrap.appendChild(inp);
  wrap.appendChild(el("div", "small muted", "發佈由 n8n WF10 執行，每 15 分檢查一次，實際時間可能晚幾分鐘。"));
  const ok = await modal("排程發佈", wrap,
    [{ label: "取消", value: null }, { label: "排定", value: 1, cls: "primary" }]);
  if (!ok || !inp.value) return;
  // datetime-local 沒有時區，補上本機偏移，避免存成 UTC 而早發八小時
  const t = new Date(inp.value);
  const off = -t.getTimezoneOffset();
  const iso = localIso(t) + ":00" + (off >= 0 ? "+" : "-") +
              pad(Math.floor(Math.abs(off) / 60)) + ":" + pad(Math.abs(off) % 60);
  try {
    await postEvent("post.schedule", p.id, { publish_at: iso });
    p.status = "scheduled"; p.publish_at = iso;
    toast("已排程 " + iso.slice(5, 16).replace("T", " ") + " ✓");
    QUEUE.splice(IDX, 1); if (IDX >= QUEUE.length) IDX = 0;
    QUEUE.length ? openPost() : location.reload();
  } catch (e) { toast(e.message, true); }
}

// ── 開一篇 ──────────────────────────────────────────────────────────
function openPost() {
  const p = cur();
  CHOICE = {}; CROPDRAFT = {}; SLIDE = 1; PI = 0; T0 = Date.now();
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
  if (k === "s" || k === "S") { scheduleCur(); return; }
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
  QUEUE = P.posts.filter(p => p.status !== "rejected" && (p.status === "awaiting_review" || (p.status === "approved" && p.render_note)));
  // 從看板點某張卡進來（review.html#<post id>）：那一篇不一定符合預設佇列條件，
  // 例如「待排」是 approved 且沒有 render_note。原本一律開佇列第一篇，
  // 使用者以為點錯或壞了（Jesse 2026-08-25）。這裡把它補進佇列並選中。
  const want = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (want) {
    let i = QUEUE.findIndex(p => p.id === want);
    if (i < 0) {
      const p = P.posts.find(x => x.id === want && x.status !== "rejected");
      if (p) { QUEUE.unshift(p); i = 0; }
    }
    if (i >= 0) IDX = i;
  }
  if (!QUEUE.length) { $("#rvHero").innerHTML = ""; $("#rvHero").appendChild(el("div", "empty", "佇列清空了 🎉")); renderBar(); return; }
  openPost();
}).catch(e => loadFail(e.message));
})();
