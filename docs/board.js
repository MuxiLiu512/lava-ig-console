/* 工作台〔藍圖 UI 規格 §3〕— 四區塊：A 全域狀態列、B 待你處理、C 系統處理中、D 已完成。
   它回答的唯一問題：「我現在要做什麼」。
   收錄鐵則：B 區只放你能動的事（白名單），動不了的永遠不進佇列。 */
(() => {
"use strict";
const { $, el, esc, MODE, setImg, saveJson, STATE, FILES, loadAll, toast, modal, nowISO, tfetch, postEvent, patModal,
        stageOf, gatesOf, alertOf, lacksMaterial, slidesDone } = window.LavaCore;
const { t, tip, SCHEDULE, statusView } = window.LavaTerms;
const { icon, ago, dur, ActionButton, StatusLine, Section } = window.LavaUI;

const DRAFT_HOOK = "https://lavadating.app.n8n.cloud/webhook/lava-ig-draft";

// ── 小工具 ──────────────────────────────────────────────────────────
const setCover = (im, p) => {
  const s0 = (p.slides || [])[0] || {};
  if (s0.public_url) { im.src = s0.public_url; return; }
  const path = s0.final_src || ((s0.candidates || [])[0] || {}).src;
  if (path) setImg(im, path); else im.classList.add("ph");
};
const sinceOf = p => p.status_since || p.rendered_at || p.candidates_since || p.created_at;
const latestReviewOf = id => {
  const rs = ((STATE.reviews && STATE.reviews.reviews) || []).filter(r => r.post_id === id);
  return rs.length ? rs[rs.length - 1] : null;
};
function gatesNode(p) {
  const g = el("div", "gates");
  gatesOf(p).forEach(([name, st]) => {
    const d = el("span", "gate " + st, esc(name));
    d.title = name + "：" + (st === "ok" ? "通過" : st === "bad" ? "未過" : st === "warn" ? "有提醒" : "未跑");
    g.appendChild(d);
  });
  return g;
}

// 標題剝掉系統後綴（｜病毒分…），人只看主題
const cleanTitle = s => String(s || "").replace(/^靈感｜/, "").split("｜病毒分")[0];

// ── 撰稿中（放行後、入板前的隱形期）——沿用既有 SLA 邏輯 ─────────────
const _tkey = s => String(s || "")
  .replace(/^靈感｜|^IG貼文｜/, "").split("｜病毒分")[0]
  .replace(/[\s\/\\【】〖〗「」『』，。：！？——–\-…()（）]/g, "").slice(0, 22);

function draftingIdeas(posts) {
  const ideas = ((STATE.ideas && STATE.ideas.ideas) || []).filter(x => x.decision === "approve");
  // 以 id 比對為主〔2026-09-01〕：靈感 id → WF01 taskId → 貼文 id 是同一顆，
  // 比對零歧義。原本只比主題字串，標點稍有出入（「——這件事」vs「：這件事」）
  // 就對不上，於是稿早就入板了、看板還在畫「撰稿中，超過 45 分」的幻影卡，
  // 旁邊同時列著同一篇的製作中狀態。這是字串比對 bug 家族的最後一隻。
  const ids = new Set();
  posts.forEach(p => { ids.add(p.id); if (p.clickup_task_id) ids.add(p.clickup_task_id); });
  const topics = new Set(posts.map(p => _tkey(p.topic || p.id)));   // 舊資料的過渡備援
  return ideas.filter(i => {
    const tid = i.task_id || i.id;
    if (tid && ids.has(tid)) return false;
    return !topics.has(_tkey(i.title));
  }).sort((a, b) => String(a.decided_at || "").localeCompare(String(b.decided_at || "")));
}

// ── A 區：全域狀態列（誠實心跳）────────────────────────────────────
function globalStatus(posts) {
  const zone = $("#zoneA"); zone.innerHTML = "";
  const hb = STATE.heartbeat && !STATE.heartbeat._error ? STATE.heartbeat : null;
  let line;
  if (!hb || !hb.ts) {
    line = StatusLine({ who: "系統", stage: "還沒開始運作", next: "不用動，第一輪跑完這裡會亮", tone: "warn" });
  } else {
    const min = Math.round((Date.now() - new Date(hb.ts)) / 60000);
    const errs = (hb.errors || []).length;
    if (min > SCHEDULE.HEARTBEAT_BAD_MIN) {
      line = StatusLine({ who: "系統", stage: `內容團隊停了 ${Math.round(min / 60)} 小時`, next: "點此複製狀態、貼給 Claude 查", tone: "bad" });
      line.style.cursor = "pointer";
      line.onclick = () => { navigator.clipboard.writeText(JSON.stringify(hb, null, 1)); toast("已複製。貼到對話裡，Claude 會直接查。"); };
    } else if (min > SCHEDULE.HEARTBEAT_WARN_MIN || errs) {
      line = StatusLine({ who: "系統", stage: `${min} 分前還在動` + (errs ? ` · 有 ${errs} 件要看一眼` : ""),
        next: errs ? "點開看是什麼事" : "不用動，再觀察一下", tone: "warn",
        detail: (hb.errors || []).join("\n") });
      if (errs) { line.style.cursor = "pointer"; line.onclick = () => modal("這一輪要看一眼的事",
        el("div", "small", (hb.errors || []).map(e => `<div style="margin:4px 0">${esc(e)}</div>`).join("")),
        [{ label: "關閉", value: 1 }]); }
    } else {
      const next = posts.filter(p => p.status === "scheduled" && p.publish_at > nowISO())
                        .map(p => p.publish_at).sort()[0];
      const nextTxt = next ? "下篇 " + next.slice(5, 16).replace("T", " ") + " 自動發佈" : "沒有已排程的貼文";
      line = StatusLine({ who: "系統", stage: "一切正常 · " + min + " 分前還在動", next: nextTxt, tone: next ? "ok" : "warn" });
    }
  }
  zone.appendChild(line);
}

// ── B 區：待你處理（佇列卡）─────────────────────────────────────────
function queueCard(p, view) {
  const c = el("article", "qcard");
  c.tabIndex = 0; c.setAttribute("role", "button");
  const im = el("img", "cover"); im.alt = ""; im.loading = "lazy"; setCover(im, p);
  c.appendChild(im);
  const mid = el("div", "grow");
  mid.appendChild(el("h3", null, esc(p.topic || p.id)));
  const rv = latestReviewOf(p.id);
  const sub = el("div", "sub");
  sub.innerHTML = `<b>${esc(view.label)}</b> · ${esc(dur(sinceOf(p)))}`;
  mid.appendChild(sub);
  if (p.redo_note) {
    // 〔Stanley §3〕助手報告自己做了什麼，不是系統宣告狀態變更
    const rn = el("div", "meta", "內容團隊：" + esc(String(p.redo_note).slice(0, 90)));
    rn.style.marginTop = "3px";
    mid.appendChild(rn);
  }
  const gz = gatesNode(p); gz.style.marginTop = "6px"; mid.appendChild(gz);
  c.appendChild(mid);
  const act = el("div", "act");
  const go = el("span", "btn primary", p.status === "approved" ? "排時間" : "開始審");
  go.appendChild(icon("arrowRight", 14));
  act.appendChild(go);
  c.appendChild(act);
  const open = () => { location.href = "review.html#" + encodeURIComponent(p.id); };
  c.onclick = open;
  c.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
  return c;
}

// 靈感卡：放行＝寫事件，哨兵折疊後直接觸發撰稿（脫離 ClickUp，2026-08-30）
function ideaCard(idea) {
  const c = el("article", "qcard idea");
  c.tabIndex = 0; c.setAttribute("role", "button");
  const ph = el("div", "cover ph"); ph.appendChild(icon("lightbulb", 20)); c.appendChild(ph);
  const mid = el("div", "grow");
  mid.appendChild(el("h3", null, esc(cleanTitle(idea.title))));
  const sub = el("div", "sub");
  sub.innerHTML = `<b>靈感待放行</b> · ${esc(ago(idea.created_at))}`;
  mid.appendChild(sub);
  c.appendChild(mid);
  const act = el("div", "act");
  const go = el("span", "btn", "看內容");
  act.appendChild(go); c.appendChild(act);
  const open = () => openIdeaDrawer(idea);
  c.onclick = open;
  c.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
  return c;
}

function openIdeaDrawer(idea) {
  const d = $("#bdDrawer"); d.innerHTML = "";
  d.appendChild(el("h3", null, esc(cleanTitle(idea.title))));
  const body = el("div", "small"); body.style.cssText = "white-space:pre-wrap;color:var(--text-2);margin-bottom:12px";
  body.textContent = idea.desc || "（無描述）";
  d.appendChild(body);
  const row = el("div", "btnrow"); row.style.marginTop = "14px";
  row.appendChild(ActionButton({
    id: "idea-approve-" + idea.task_id, groupId: "idea-" + idea.task_id,
    label: "放行、開始撰稿", kind: "primary", doneLabel: "已放行",
    run: () => postEvent("idea.approve", idea.task_id, { feedback: "" }),
    onDone: () => {
      idea.decision = "approve"; idea.decided_at = nowISO();
      toast(`已放行。哨兵 ${SCHEDULE.SENTINEL_MIN} 分內啟動撰稿，完成前這篇會在「系統處理中」。`);
      d.classList.remove("open"); boot();
    },
  }));
  row.appendChild(ActionButton({
    id: "idea-reject-" + idea.task_id, groupId: "idea-" + idea.task_id,
    label: "退回", kind: "danger", doneLabel: "已退回",
    run: async () => {
      const ta = el("textarea"); ta.rows = 2;
      const r = await modal("退回原因", ta, [{ label: "取消", value: null }, { label: "退回", value: 1, cls: "primary" }]);
      if (!r) { const e = new Error("已取消"); e.silent = true; throw e; }
      await postEvent("idea.reject", idea.task_id, { feedback: ta.value.trim() });
      idea.decision = "reject"; idea.decided_at = nowISO();
    },
    onDone: () => { toast("已退回"); d.classList.remove("open"); boot(); },
  }));
  const close = el("button", "btn ghost", "關閉");
  close.onclick = () => d.classList.remove("open");
  row.appendChild(close);
  d.appendChild(row);
  d.classList.add("open");
}

// ── C 區：系統處理中（唯讀列：在做什麼 · 已多久 · 預計何時回來）──────
function sysRow(o) {
  // o: {img?, title, what, since, eta, late, onReport?, action?}
  const r = el("div", "sysrow" + (o.late ? " late" : ""));
  if (o.img) { r.appendChild(o.img); }
  const mid = el("div", "grow");
  mid.appendChild(el("div", "ellip", esc(o.title)));
  mid.appendChild(el("div", "what", esc(o.what)));
  r.appendChild(mid);
  const when = el("div", "when");
  when.innerHTML = esc(dur(o.since)) + (o.eta ? "<br>" + esc(o.eta) : "");
  r.appendChild(when);
  if (o.action) r.appendChild(o.action);
  else if (o.late && o.postId) {
    // 按下＝寫事件，哨兵跑診斷並把「卡在哪、下一步」推 LINE。
    // 〔2026-09-01 Jesse：複製狀態能不能直接變成自動回報〕不必再自己貼給我。
    r.appendChild(ActionButton({
      id: "diagnose-" + o.postId, label: "回報這一篇", kind: "ghost", doneLabel: "已送出診斷",
      run: () => postEvent("post.diagnose", o.postId, {}),
      onDone: () => toast(`已送出。哨兵 ${SCHEDULE.SENTINEL_MIN} 分內診斷完，結果推到你的 LINE。`),
    }));
  }
  return r;
}

function draftingRow(idea) {
  const mins = idea.decided_at ? Math.round((Date.now() - new Date(idea.decided_at)) / 60000) : 0;
  const late = mins > SCHEDULE.DRAFT_SLA_MIN;
  const rushMin = idea.rushed_at ? Math.round((Date.now() - new Date(idea.rushed_at)) / 60000) : null;
  const rushing = rushMin !== null && rushMin < SCHEDULE.RUSH_ETA_MIN;
  let what, action = null;
  if (rushing) {
    what = `已重跑撰稿（${rushMin} 分前），進行中，不用再按`;
  } else if (late) {
    what = `超過正常的 ${SCHEDULE.DRAFT_SLA_MIN} 分，稿可能寫好了但沒進來`;
    action = ActionButton({
      id: "rush-" + idea.task_id, label: "重跑撰稿", kind: "primary", doneLabel: "已觸發",
      confirm: "跳過排程節奏，現在就重寫這一篇。若其實已在寫，會多一份草稿（無害，多花一次額度）。",
      run: async () => {
        let angle = ""; const m = /\*\*切角\*\*：([\s\S]*?)(\n\n|$)/.exec(idea.desc || "");
        if (m) angle = m[1].trim();
        const r = await tfetch(DRAFT_HOOK, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic: cleanTitle(idea.title), type: "知識型", slides: 9, angle,
                                 taskId: idea.task_id, writer: "claude" }) }, 20000);
        if (!r.ok) throw new Error("觸發失敗 (" + r.status + ")");
        await saveJson(FILES.ideas, doc => {
          const x = (doc.ideas || []).find(y => y.task_id === idea.task_id);
          if (x) x.rushed_at = nowISO();
        }, "rush draft: " + idea.task_id).catch(() => {});
      },
      onDone: () => { toast(`已觸發。最晚 ${SCHEDULE.RUSH_ETA_MIN} 分後出現在「待你處理」。`); boot(); },
    });
  } else {
    what = `撰稿中，正常 ${SCHEDULE.DRAFT_SLA_MIN} 分內回來`;
  }
  return sysRow({ title: cleanTitle(idea.title), what, since: idea.decided_at,
    eta: rushing ? `約 ${SCHEDULE.RUSH_ETA_MIN - rushMin} 分後` : late ? "" : "今天內",
    late, action });
}

function makingRow(p, view) {
  const im = el("img", "thumb"); im.alt = ""; setCover(im, p);
  const rv = latestReviewOf(p.id);
  let what = "素材與排版製作中";
  if (view.label === t("fixing_images")) {
    const ns = (p.slides || []).filter(lacksMaterial).map(s => s.n);
    what = `第 ${ns.join("、")} 張沒有可用的圖，系統每輪補圖`;
  } else if (view.label === t("redoing")) {
    what = "按你的退回原因重做中" + (rv && rv.feedback ? `：「${String(rv.feedback).slice(0, 30)}」` : "");
  }
  const hours = (Date.now() - new Date(sinceOf(p))) / 36e5;
  const late = hours > SCHEDULE.STUCK_HOURS;
  let action = null;
  if (p.regen_needed) {
    what = `第 ${(p.regen_needed.slides || []).join("、")} 張連兩輪補不到圖，企劃本身有問題`;
    action = ActionButton({
      id: "regen-" + p.id, label: "重新生成這篇", kind: "primary", doneLabel: "已送出",
      confirm: "用同一主題重跑撰稿與視覺企劃，產生新一版草稿。舊版留在 Drive。約 6 分寫完，最晚 20 分回來。",
      run: async () => {
        const r = await tfetch(DRAFT_HOOK, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic: p.topic || p.id, type: "知識型", slides: 9,
            angle: "重新生成：前一版有版位補不到合適圖片，請調整視覺企劃讓每張都有可取得的具體素材",
            taskId: p.clickup_task_id || "", writer: "claude" }) }, 20000);
        if (!r.ok) throw new Error("觸發失敗 (" + r.status + ")");
        await saveJson(FILES.posts, doc => {
          const q = (doc.posts || []).find(x => x.id === p.id);
          if (q) { q.regen_requested_at = nowISO(); delete q.regen_needed; }
        }, "regen: " + p.id).catch(() => {});
      },
      onDone: () => { toast("已送出重新生成，最晚 20 分後有新版"); boot(); },
    });
  }
  return sysRow({ img: im, title: p.topic || p.id, what, since: sinceOf(p),
    eta: late ? "" : "補完自動回佇列", late,
    postId: p.id, action });
}

// ── D 區：已完成 ────────────────────────────────────────────────────
function doneRow(p) {
  const r = el("div", "donerow");
  const lbl = p.status === "published"
    ? `<span class="dotlbl ok"><i></i>已發佈</span>`
    : `<span class="dotlbl info"><i></i>已排程</span>`;
  const s = el("span"); s.innerHTML = lbl; r.appendChild(s);
  const title = el("span", "grow ellip", esc(p.topic || p.id));
  r.appendChild(title);
  if (p.status === "scheduled") {
    r.appendChild(el("span", "when", esc((p.publish_at || "").slice(5, 16).replace("T", " ") + " 發佈")));
    r.appendChild(ActionButton({
      id: "unsched-" + p.id, label: "取消排程", kind: "ghost", doneLabel: "已取消",
      confirm: "取消後回到「等你排時間」，不會發佈。",
      run: () => postEvent("post.unschedule", p.id, {}),
      onDone: () => { p.status = "approved"; toast(`已取消。哨兵 ${SCHEDULE.SENTINEL_MIN} 分內生效。`); boot(); },
    }));
  } else {
    r.appendChild(el("span", "when", esc((p.published_at || p.publish_at || "").slice(5, 16).replace("T", " "))));
    const a = el("a", "btn ghost", "看 IG");
    a.href = "https://www.instagram.com/lava_dating/"; a.target = "_blank"; a.rel = "noopener";
    r.appendChild(a);
  }
  return r;
}

function proposalRow(pr) {
  const r = el("div", "donerow");
  const s = el("span"); s.innerHTML = `<span class="dotlbl warn"><i></i>${esc(t("proposals"))}</span>`;
  r.appendChild(s);
  r.appendChild(el("span", "grow ellip", esc(pr.title)));
  r.appendChild(el("span", "when", esc(ago(pr.created_at))));
  const b = el("button", "btn ghost", "看內容");
  b.onclick = () => openProposalDrawer(pr);
  r.appendChild(b);
  return r;
}

function openProposalDrawer(pr) {
  const d = $("#bdDrawer"); d.innerHTML = "";
  d.appendChild(el("h3", null, esc(pr.title)));
  d.appendChild(el("div", "small muted", esc(pr.diff_summary || "")));
  (pr.evidence || []).forEach(ev => {
    const li = el("div", "small");
    li.style.cssText = "margin:6px 0;padding:8px 10px;background:var(--surface-2);border-radius:6px";
    li.textContent = ev; d.appendChild(li);
  });
  const row = el("div", "btnrow"); row.style.marginTop = "14px";
  row.appendChild(ActionButton({
    id: "prop-ok-" + pr.pid, groupId: "prop-" + pr.pid, label: "放行", kind: "primary", doneLabel: "已放行",
    run: () => saveJson(FILES.proposals, doc => {
      const x = (doc.proposals || []).find(y => y.pid === pr.pid);
      if (x) { x.status = "approved"; x.decided_at = nowISO(); }
    }, "proposal approved: " + pr.pid),
    onDone: () => { toast("已放行"); d.classList.remove("open"); boot(); },
  }));
  row.appendChild(ActionButton({
    id: "prop-no-" + pr.pid, groupId: "prop-" + pr.pid, label: "否決", kind: "danger", doneLabel: "已否決",
    run: async () => {
      const ta = el("textarea"); ta.rows = 2;
      const r = await modal("否決原因", ta, [{ label: "取消", value: null }, { label: "否決", value: 1, cls: "primary" }]);
      if (!r) { const e = new Error("已取消"); e.silent = true; throw e; }
      await saveJson(FILES.proposals, doc => {
        const x = (doc.proposals || []).find(y => y.pid === pr.pid);
        if (x) { x.status = "rejected"; x.decided_at = nowISO(); if (ta.value.trim()) x.reject_reason = ta.value.trim(); }
      }, "proposal rejected: " + pr.pid);
    },
    onDone: () => { toast("已否決"); d.classList.remove("open"); boot(); },
  }));
  const close = el("button", "btn ghost", "關閉");
  close.onclick = () => d.classList.remove("open");
  row.appendChild(close);
  d.appendChild(row);
  d.classList.add("open");
}

// ── 組版 ────────────────────────────────────────────────────────────
function boot() {
  const posts = ((STATE.posts && STATE.posts.posts) || []);
  const main = $("#bdMain"); main.innerHTML = "";
  globalStatus(posts);

  // 分區（statusView 是唯一分類器；§1.3 防護在其中）
  const views = posts.map(p => ({ p, v: statusView(p, latestReviewOf(p.id)) }));
  const queue = views.filter(x => x.v.zone === "queue")
    .sort((a, b) => String(sinceOf(a.p)).localeCompare(String(sinceOf(b.p))));   // 卡最久在最上
  const system = views.filter(x => x.v.zone === "system");
  const ideas = ((STATE.ideas && STATE.ideas.ideas) || []).filter(x => !x.decision);
  const drafting = draftingIdeas(posts);
  const scheduled = views.filter(x => x.p.status === "scheduled").map(x => x.p)
    .sort((a, b) => String(a.publish_at).localeCompare(String(b.publish_at)));
  const published = views.filter(x => x.p.status === "published").map(x => x.p)
    .sort((a, b) => String(b.published_at || b.publish_at).localeCompare(String(a.published_at || a.publish_at)))
    .slice(0, 10);
  const props = ((STATE.proposals && STATE.proposals.proposals) || []).filter(x => x.status === "pending");

  // B 待你處理
  const nYou = queue.length + ideas.length;
  const B = Section({ title: "待你處理", count: nYou, collapsed: false });
  B.body.classList.add("two-col");
  queue.forEach(x => B.body.appendChild(queueCard(x.p, x.v)));
  ideas.forEach(i => B.body.appendChild(ideaCard(i)));
  if (!nYou) {
    const n = system.length + drafting.length;
    B.body.appendChild(el("div", "empty",
      `目前沒有需要你的事。系統處理中有 ${n} 件，完成後會出現在這裡。`));
  }
  main.appendChild(B.wrap);

  // C 系統處理中
  const nSys = system.length + drafting.length;
  const C = Section({ title: "系統處理中", count: nSys, collapsed: nYou > 0 });
  drafting.forEach(i => C.body.appendChild(draftingRow(i)));
  system.forEach(x => C.body.appendChild(makingRow(x.p, x.v)));
  if (!nSys) C.body.appendChild(el("div", "meta", "（沒有進行中的工作）"));
  main.appendChild(C.wrap);

  // D 已完成
  const D = Section({ title: "已完成", count: scheduled.length + published.length, collapsed: true });
  scheduled.forEach(p => D.body.appendChild(doneRow(p)));
  published.forEach(p => D.body.appendChild(doneRow(p)));
  props.forEach(pr => D.body.appendChild(proposalRow(pr)));
  if (!scheduled.length && !published.length && !props.length)
    D.body.appendChild(el("div", "meta", "（還沒有排程或發佈的貼文）"));
  main.appendChild(D.wrap);
}

$("#btnSettings").insertAdjacentElement("beforebegin", window.LavaUI.themeToggle());
$("#btnSettings").appendChild(window.LavaUI.icon("settings", 17));
$("#btnSettings").onclick = patModal;

FILES.heartbeat = "data/heartbeat.json";
FILES.ideas = "data/ideas.json";
loadAll().then(() => {
  $("#modeTag").textContent = MODE === "local" ? "· 本地預覽" : "";
  const P = STATE.posts;
  if (!P || P._error || !Array.isArray(P.posts)) {
    $("#bdMain").innerHTML = "";
    $("#bdMain").appendChild(el("div", "empty", "posts.json 載入失敗：" + esc(String((P && P._error) || ""))));
    return;
  }
  boot();
}).catch(e => { $("#bdMain").innerHTML = ""; $("#bdMain").appendChild(el("div", "empty", "載入失敗：" + esc(e.message))); });
})();
