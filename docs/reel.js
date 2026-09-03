/* 影片審核〔藍圖 UI 規格 §7，2026-09-03〕
   與貼文審稿台共用整頁骨架，中段換成分段卡。

   這一頁存在的理由只有一個：影片是整條管線裡唯一「一按下去就燒錢」的東西。
   口播 9 點/秒、空景 6.5 點/秒，一支 30 秒混合片約 137 點；分鏡一張才 7 點。
   所以流程一定是「先看分鏡，再決定要不要生影片」——而且這件事不能只靠介面
   隱藏按鈕（介面會被繞過），狀態機層就沒有那條路（state_machine.REEL_TRANSITIONS）。
   這一頁要做的是把那個保護「顯示出來」，讓你看得見它在替你擋什麼。 */
(() => {
"use strict";
const { $, el, esc, MODE, img, setImg, STATE, FILES, loadAll, toast, modal, nowISO, postEvent, patModal } = window.LavaCore;
const { t, SCHEDULE } = window.LavaTerms;
const { icon, dur, ActionButton, StatusLine } = window.LavaUI;

// 單價與貼文管線同一份實測數字（scripts/reel_produce.py 的 RATE 表）
const RATE = { talk: 9.0, broll: 6.5, own: 0, cards: 0 };
const BOARD = 7.0;                       // 分鏡一張
const KIND = { talk: "口播", broll: "空景", own: "自有畫面", cards: "字卡" };
const HUE = { talk: "#e8442a", broll: "#6aabff", own: "#57bd7d", cards: "#d9a441" };

let LIST = [], IDX = 0, TAB = "script";

const cur = () => LIST[IDX];
const segCost = s => (RATE[s.type] || 0) * (Number(s.seconds) || 0) + (s.type === "talk" ? BOARD : 0);
const totalCost = r => (r.segments || []).reduce((a, s) => a + segCost(s), 0);
const totalSecs = r => (r.segments || []).reduce((a, s) => a + (Number(s.seconds) || 0), 0);
const st = r => r.status || "storyboard";

// ── 整支資訊：點數誠實帳〔藍圖 §7 ⑤〕 ──────────────────────────────
function infoCard(r) {
  const c = el("div", "card"); const pad = el("div", "pad");
  const spent = (r.segments || []).filter(s => s.video_src).reduce((a, s) => a + segCost(s), 0);
  const rest = totalCost(r) - spent;
  const row = el("div", "rl-cost");
  row.innerHTML = `<b>${totalSecs(r)}</b> 秒 · <b>${Math.round(totalCost(r))}</b> 點`
    + (spent ? ` <span class="meta">（已花 ${Math.round(spent)}，還要 ${Math.round(rest)}）</span>` : "");
  pad.appendChild(row);
  const meta = el("div", "meta"); meta.style.marginTop = "4px";
  meta.textContent = (r.segments || []).length + " 段 · 指令版本 " + (r.prompt_version || "未記錄");
  pad.appendChild(meta);

  // 分段時間軸：一眼看出節奏，也看出哪一段最貴
  const tl = el("div", "rl-timeline");
  (r.segments || []).forEach((s, i) => {
    const w = ((Number(s.seconds) || 0) / Math.max(1, totalSecs(r))) * 100;
    const b = el("span", null, esc(KIND[s.type] || s.type));
    b.style.cssText = `width:${w}%;background:${HUE[s.type] || "#555"}`;
    b.title = `第 ${i + 1} 段 ${KIND[s.type] || s.type} ${s.seconds} 秒 · ${Math.round(segCost(s))} 點`;
    tl.appendChild(b);
  });
  pad.appendChild(tl);
  c.appendChild(pad);
  return c;
}

// ── 分段卡：兩階段，先分鏡再影片 ────────────────────────────────────
function segCard(r, s, i) {
  const okBoard = !!s.storyboard_ok;
  const hasVideo = !!s.video_src;
  const free = s.type === "own" || s.type === "cards";     // 0 點的段不必鎖
  const card = el("section", "segcard" + (s.confirmed ? " done" : ""));

  const head = el("div", "sg-head");
  head.appendChild(el("span", "n", "第 " + (i + 1) + " 段"));
  head.appendChild(el("span", "kind", esc(KIND[s.type] || s.type)));
  head.appendChild(el("span", "meta", (s.seconds || 0) + " 秒"));
  const cost = el("span", "cost", segCost(s) ? Math.round(segCost(s)) + " 點" : "0 點");
  head.appendChild(cost);
  card.appendChild(head);

  // 階段一：分鏡
  const board = el("div", "sg-board");
  if (s.storyboard_src) {
    if (/^https?:/.test(s.storyboard_src)) { const e = el("img"); e.src = s.storyboard_src; board.appendChild(e); }
    else board.appendChild(img(s.storyboard_src));
  } else if (free) {
    board.appendChild(el("div", "ph", (s.type === "own" ? "自有素材" : "字卡") + "：不需要分鏡，也不花點數"));
  } else {
    board.appendChild(el("div", "ph", "分鏡還沒畫。分鏡一張 " + BOARD + " 點，比直接生影片便宜得多。"));
  }
  card.appendChild(board);

  const body = el("div", "sg-body");
  if (s.note) body.appendChild(el("div", "meta", esc(s.note)));
  if (TAB === "script" && s.script) {
    const pre = el("div", "sg-script"); pre.style.marginTop = "6px";
    pre.textContent = s.script;
    body.appendChild(pre);
  }
  if (TAB === "script" && s.prompt_hint) {
    const d = el("details", "drawer"); d.style.marginTop = "6px";
    d.appendChild(el("summary", null, "生成指令（改這裡會影響這一段長什麼樣）"));
    const inner = el("div", "inner small muted"); inner.style.whiteSpace = "pre-wrap";
    inner.textContent = s.prompt_hint;
    d.appendChild(inner); body.appendChild(d);
  }
  card.appendChild(body);

  // 階段二：影片。分鏡沒確認前整格鎖住——這是省錢關卡的介面呈現。
  if (!free) {
    const vf = el("div", "sg-body"); vf.style.borderTop = "1px solid var(--line)";
    if (hasVideo) {
      const v = el("video"); v.controls = true; v.style.cssText = "width:100%;max-width:300px;border-radius:8px";
      v.src = s.video_src; if (s.storyboard_src) v.poster = s.storyboard_src;
      vf.appendChild(v);
    } else if (!okBoard) {
      const lk = el("div", "sg-lock");
      lk.appendChild(icon("alert", 14));
      lk.appendChild(el("span", null,
        `先確認分鏡才會生影片。這一段生下去約 ${Math.round(segCost(s))} 點，分鏡只要 ${BOARD} 點。`));
      vf.appendChild(lk);
      card.classList.add("locked");
    } else {
      vf.appendChild(el("div", "meta", "分鏡已確認，等生成。"));
    }
    card.appendChild(vf);
  }

  // 卡尾：兩顆鍵，對應兩個階段
  const foot = el("div", "sg-foot");
  if (!free && !okBoard) {
    foot.appendChild(ActionButton({
      id: "sb-ok-" + r.id + "-" + i, label: "分鏡沒問題", kind: "primary", doneLabel: "確認了",
      run: () => postEvent("reel.segment_storyboard_ok", r.id, { segment: i }),
      onDone: () => { s.storyboard_ok = true; toast(`確認了。哨兵 ${SCHEDULE.SENTINEL_MIN} 分內生這一段的影片。`); render(); },
    }));
    foot.appendChild(ActionButton({
      id: "sb-redo-" + r.id + "-" + i, label: "重畫分鏡", kind: "ghost", doneLabel: "已送出",
      cost: { credits: BOARD },
      confirm: "重畫這一段的分鏡。可以順便寫一句你想要的方向。",
      run: async () => {
        const ta = el("textarea"); ta.rows = 2; ta.placeholder = "想改成什麼樣子？（選填，會併進下次的生成指令）";
        const okc = await modal("重畫第 " + (i + 1) + " 段的分鏡", ta,
          [{ label: "取消", value: null }, { label: "重畫", value: 1, cls: "primary" }]);
        if (!okc) { const e = new Error("已取消"); e.silent = true; throw e; }
        await postEvent("reel.segment_redo_storyboard", r.id, { segment: i, note: ta.value.trim() });
      },
      onDone: () => toast("已送出。重畫一張 " + BOARD + " 點。"),
    }));
  } else if (hasVideo && !s.confirmed) {
    foot.appendChild(ActionButton({
      id: "seg-ok-" + r.id + "-" + i, label: "這段可以", kind: "primary", doneLabel: "確認了",
      run: () => postEvent("reel.segment_confirm", r.id, { segment: i }),
      onDone: () => { s.confirmed = true; toast("確認了。"); render(); },
    }));
    foot.appendChild(ActionButton({
      id: "seg-redo-" + r.id + "-" + i, label: "重做這段", kind: "danger", doneLabel: "已送出",
      cost: { credits: Math.round(segCost(s)) },
      confirm: "重做這一段會重新生成影片，原因會併進下次的指令。已確認的其他段不受影響、不重扣點。",
      run: async () => {
        const ta = el("textarea"); ta.rows = 2; ta.placeholder = "為什麼要重做？（必填，會併進下次的生成指令）";
        const okc = await modal("重做第 " + (i + 1) + " 段", ta,
          [{ label: "取消", value: null }, { label: "重做", value: 1, cls: "primary" }]);
        if (!okc) { const e = new Error("已取消"); e.silent = true; throw e; }
        if (ta.value.trim().length < 4) throw new Error("請寫一句原因，下次才改得對");
        await postEvent("reel.segment_redo_video", r.id, { segment: i, note: ta.value.trim() });
      },
      onDone: () => toast("已送出重做。"),
    }));
  } else if (s.confirmed) {
    const d = el("span", "dotlbl ok"); d.innerHTML = "<i></i>已確認";
    foot.appendChild(d);
  } else if (free) {
    foot.appendChild(ActionButton({
      id: "seg-ok-" + r.id + "-" + i, label: "這段可以", kind: "primary", doneLabel: "確認了",
      run: () => postEvent("reel.segment_confirm", r.id, { segment: i }),
      onDone: () => { s.confirmed = true; toast("確認了。"); render(); },
    }));
  }
  card.appendChild(foot);
  return card;
}

// ── 決策列 ──────────────────────────────────────────────────────────
function bar(r) {
  const b = $("#rlBar"); b.innerHTML = ""; b.style.display = "flex";
  const segs = r.segments || [];
  const done = segs.filter(s => s.confirmed).length;
  const boardsLeft = segs.filter(s => !s.storyboard_ok && s.type !== "own" && s.type !== "cards").length;
  const prog = el("span", "progress");
  prog.innerHTML = st(r) === "storyboard"
    ? `分鏡待確認 <b>${boardsLeft}</b> 段`
    : `<b>${done}</b>/${segs.length} 段已確認`;
  b.appendChild(prog);
  b.appendChild(el("span", "grow"));

  if (st(r) === "storyboard") {
    b.appendChild(el("span", "meta", `全部確認後才會生影片（約 ${Math.round(totalCost(r))} 點）`));
    b.appendChild(ActionButton({
      id: "reel-sb-all-" + r.id, label: "分鏡全部確認", kind: "primary", doneLabel: "送出了",
      cost: { credits: Math.round(totalCost(r)) },
      confirm: `確認之後系統會開始生影片，這一支約 ${Math.round(totalCost(r))} 點。分鏡有疑慮請先逐段重畫。`,
      run: () => postEvent("reel.approve_storyboard", r.id, {}),
      onDone: () => toast("送出了。生影片需要幾分鐘，好了會回到這裡。"),
    }));
  } else if (st(r) === "video_review") {
    const ab = ActionButton({
      id: "reel-approve-" + r.id, label: "核准整支", kind: "primary", doneLabel: "已核准",
      run: () => postEvent("reel.approve", r.id, {}),
      onDone: () => toast("已核准。到工作台排時間。"),
    });
    if (done < segs.length) { ab.disabled = true; ab.title = "還有 " + (segs.length - done) + " 段沒確認"; }
    b.appendChild(ab);
  } else if (st(r) === "approved") {
    b.appendChild(el("span", "meta", "已核准，等你排時間"));
  }
  const rj = el("button", "btn danger", "退回");
  rj.type = "button";
  rj.onclick = () => rejectPanel(r);
  b.appendChild(rj);
}

// 退回：只重做勾選的段〔藍圖 §7 ⑤：已確認段不重生、不重扣點〕
function rejectPanel(r) {
  if ($("#rlRej")) return;
  const p = el("div", "rejectpanel"); p.id = "rlRej";
  p.appendChild(el("h3", null, "退回這一支"));
  p.appendChild(el("div", "meta", "只勾要重做的段。沒勾的維持原樣，不重生也不重扣點。"));
  const scopes = el("div", "scopes"); scopes.style.flexWrap = "wrap";
  const boxes = (r.segments || []).map((s, i) => {
    const lab = el("label");
    const cb = el("input"); cb.type = "checkbox";
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(`第 ${i + 1} 段 ${KIND[s.type] || s.type}（${Math.round(segCost(s))} 點）`));
    scopes.appendChild(lab);
    return cb;
  });
  p.appendChild(scopes);
  const cost = el("div", "meta"); cost.style.margin = "6px 0";
  const paint = () => {
    const sum = boxes.reduce((a, cb, i) => a + (cb.checked ? segCost(r.segments[i]) : 0), 0);
    cost.textContent = sum ? `重做這些段大約 ${Math.round(sum)} 點` : "還沒勾任何一段";
  };
  boxes.forEach(cb => cb.addEventListener("change", paint));
  paint();
  p.appendChild(cost);
  const ta = el("textarea"); ta.rows = 3; ta.placeholder = "退回原因（必填，至少 10 字）——會併進下次的生成指令";
  p.appendChild(ta);
  const err = el("div", "field-err"); err.style.display = "none";
  p.appendChild(err);
  const row = el("div", "btnrow"); row.style.marginTop = "10px";
  row.appendChild(ActionButton({
    id: "reel-reject-" + r.id, label: "送出退回", kind: "danger", doneLabel: "已退回",
    run: async () => {
      const reason = ta.value.trim();
      if (reason.length < 10) {
        err.textContent = "原因太短（" + reason.length + " 字）。寫清楚哪裡不對，下一版才改得對。";
        err.style.display = "block"; ta.focus();
        throw new Error("原因至少 10 字");
      }
      const segs = boxes.map((cb, i) => cb.checked ? i : -1).filter(i => i >= 0);
      await postEvent("reel.reject", r.id, { feedback: reason, segments: segs });
    },
    onDone: () => { p.remove(); toast("已退回。只有勾選的段會重做。"); location.reload(); },
  }));
  const cancel = el("button", "btn ghost", "取消");
  cancel.onclick = () => p.remove();
  row.appendChild(cancel);
  p.appendChild(row);
  document.body.appendChild(p);
  ta.focus();
}

// ── 渲染 ────────────────────────────────────────────────────────────
function render() {
  const r = cur();
  const main = $("#rlMain"); main.innerHTML = "";
  if (!r) {
    const box = el("div", "empty");
    box.appendChild(el("div", null, "<b>目前沒有影片要審</b>"));
    box.appendChild(el("div", "small muted", "影片的分鏡出來之後會出現在這裡。"));
    const a = el("a", "btn", "回工作台"); a.href = "index.html"; a.style.marginTop = "10px";
    box.appendChild(a);
    main.appendChild(box);
    $("#rlBar").style.display = "none";
    return;
  }
  $("#rlTitle").textContent = (r.title || r.id).slice(0, 38);
  $("#rlPos").textContent = LIST.length > 1 ? (IDX + 1) + " / " + LIST.length : "";

  const STAGE = { storyboard: ["你", "分鏡等你確認", "逐段看過，確認後才會生影片"],
                  storyboard_ok: ["系統", "生影片中", "不用動，好了會回到這裡"],
                  video_review: ["你", "影片等你審", "逐段確認後核准整支"],
                  approved: ["你", "等你排時間", "到工作台排發佈時間"],
                  scheduled: ["系統", "已排程", "到點自動發佈"] }[st(r)]
                  || ["系統", "製作中", "不用動"];
  main.appendChild(StatusLine({ who: STAGE[0], stage: STAGE[1], next: STAGE[2],
                                since: r.status_since, tone: STAGE[0] === "你" ? "you" : "neutral" }));
  main.appendChild(infoCard(r));

  // Stanley 的 Script｜Caption 分頁模型
  const tabs = el("div", "rl-tabs");
  [["script", "腳本"], ["caption", "貼文文案"]].forEach(([k, label]) => {
    const b = el("button", TAB === k ? "on" : ""); b.type = "button"; b.textContent = label;
    b.onclick = () => { TAB = k; render(); };
    tabs.appendChild(b);
  });
  main.appendChild(tabs);

  if (TAB === "caption") {
    const c = el("div", "card"); const pad = el("div", "pad");
    const pre = el("div", "sg-script");
    pre.textContent = r.caption || "（還沒有貼文文案。影片核准後可以在這裡寫。）";
    pad.appendChild(pre);
    pad.appendChild(el("div", "meta", (r.caption || "").length + " 字"));
    c.appendChild(pad); main.appendChild(c);
  } else {
    const list = el("div"); list.style.marginTop = "12px";
    (r.segments || []).forEach((s, i) => list.appendChild(segCard(r, s, i)));
    main.appendChild(list);
  }
  bar(r);
}

$("#backBtn").appendChild(icon("arrowLeft", 17));
$(".topbar").appendChild(window.LavaUI.themeToggle());
FILES.reels = "data/reels.json";
loadAll().then(() => {
  $("#modeTag").textContent = MODE === "local" ? "· 本地預覽" : "";
  const R = STATE.reels;
  if (!R || R._error) {
    $("#rlMain").innerHTML = "";
    $("#rlMain").appendChild(el("div", "empty", "reels.json 讀不到：" + esc(String(R && R._error || ""))));
    return;
  }
  // 只列還需要你看的：分鏡待確認、影片待審、已核准待排
  LIST = (R.reels || []).filter(x => ["storyboard", "storyboard_ok", "video_review", "approved"].includes(st(x)));
  const want = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (want) {
    let i = LIST.findIndex(x => x.id === want);
    if (i < 0) { const x = (R.reels || []).find(y => y.id === want); if (x) { LIST.unshift(x); i = 0; } }
    if (i >= 0) IDX = i;
  }
  render();
}).catch(e => { $("#rlMain").innerHTML = ""; $("#rlMain").appendChild(el("div", "empty", "載入失敗：" + esc(e.message))); });
})();
