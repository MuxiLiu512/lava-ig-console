/* 工作台看板 〔UIUX 總體架構 §1.2／§2.1／§3.2〕
   它回答的唯一問題：「有東西可發嗎，卡在哪」。
   欄位的移動由系統決定，人不能手動改階段（避免狀態與資料不一致）——
   所以卡片點擊是「帶你去做那個動作的地方」，不是拖拉。 */
(() => {
"use strict";
const { $, el, esc, MODE, setImg, saveJson, STATE, FILES, loadAll, toast, modal, nowISO, tfetch,
        stageOf, gatesOf, alertOf } = window.LavaCore;

const COLS = [
  ["放行", "rel"], ["製作中", "make"], ["等你", "you"], ["待排", "wait"], ["已排", "sched"],
];
const WIP_LIMIT = 6;

// ── 小工具 ──────────────────────────────────────────────────────────
const ago = iso => {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 60) return m + " 分前";
  if (m < 48 * 60) return Math.round(m / 60) + " 小時前";
  return Math.round(m / 1440) + " 天前";
};
// 縮圖一律走 setImg——它處理 local／publicRaw 兩種模式；自己拼 rawUrl 在本地預覽會全破圖
const setCover = (im, p) => {
  const s0 = (p.slides || [])[0] || {};
  if (s0.public_url) { im.src = s0.public_url; return; }
  const path = s0.final_src || ((s0.candidates || [])[0] || {}).src;
  if (path) setImg(im, path);
};
// 「停在此欄多久」用該階段最可信的時間欄位，標「約」——沒有精確的階段進入時間戳
const sinceOf = (p, key) => {
  if (key === "sched") return p.publish_at ? "發佈於 " + p.publish_at.slice(5, 16).replace("T", " ") : "";
  if (key === "wait" || key === "make") return p.rendered_at ? "約 " + ago(p.rendered_at) : "";
  return "約 " + ago(p.candidates_since || p.created_at);
};

function gatesNode(p) {
  const g = el("div", "gates");
  gatesOf(p).forEach(([name, st]) => { const d = el("i", "gate " + st); d.title = name + (st ? "：" + st : "：未跑"); g.appendChild(d); });
  return g;
}

function postCard(p, key) {
  const [label, color] = stageOf(p);
  const c = el("div", "bd-card"); c.style.borderLeftColor = color;
  const top = el("div", "top");
  const im = el("img", "thumb"); im.loading = "lazy";
  setCover(im, p);
  top.appendChild(im);
  top.appendChild(el("div", "t", esc(p.topic || p.id)));
  c.appendChild(top);
  const meta = el("div", "meta");
  meta.appendChild(gatesNode(p));
  meta.appendChild(el("span", "age", esc(sinceOf(p, key))));
  c.appendChild(meta);
  c.onclick = () => { location.href = "review.html"; };
  return c;
}

// ── 靈感卡（data/ideas.json，來源 ClickUp 靈感審核）─────────────────────
// 放行只是寫下決定；實際勾 ClickUp 🚀放行 checkbox 的是哨兵 ideas-apply（最慢 10 分鐘），
// 之後 WF07 → 撰稿 → 入料全自動。介面上要把這個時間差講清楚，不能假裝即時。
function ideaCard(idea) {
  const c = el("div", "bd-card"); c.style.borderLeftColor = "#4b5057";
  c.appendChild(el("div", "t", "💡 " + esc(idea.title)));
  const meta = el("div", "meta");
  meta.appendChild(el("span", "age", "靈感 · 待放行"));
  meta.appendChild(el("span", "age", esc(ago(idea.created_at))));
  c.appendChild(meta);
  c.onclick = () => openIdeaDrawer(idea);
  return c;
}

function openIdeaDrawer(idea) {
  const d = $("#bdDrawer"); d.innerHTML = "";
  d.appendChild(el("h3", null, esc(idea.title)));
  const body = el("div", "small"); body.style.cssText = "white-space:pre-wrap;color:#c8ccd2;margin-bottom:10px";
  body.textContent = idea.desc || "（無描述）";
  d.appendChild(body);
  if (idea.url) { const a = el("a", "small muted", "在 ClickUp 開啟 ↗"); a.href = idea.url; a.target = "_blank"; d.appendChild(a); }
  const row = el("div", "row"); row.style.cssText = "gap:8px;margin-top:14px";
  const ok = el("button", "btn primary", "放行");
  const no = el("button", "btn", "退回");
  const close = el("button", "btn", "關閉");
  ok.onclick = () => decideIdea(idea, "approve", "");
  no.onclick = async () => {
    const ta = el("textarea"); ta.rows = 2; ta.style.width = "100%";
    const r = await modal("退回原因（會留言到卡上）", ta,
      [{ label: "取消", value: null }, { label: "退回", value: 1, cls: "primary" }]);
    if (r) decideIdea(idea, "reject", ta.value.trim());
  };
  close.onclick = () => d.classList.remove("open");
  row.appendChild(ok); row.appendChild(no); row.appendChild(close);
  d.appendChild(row);
  d.classList.add("open");
}

async function decideIdea(idea, decision, reason) {
  try {
    await saveJson(FILES.ideas, doc => {
      const t = (doc.ideas || []).find(x => x.task_id === idea.task_id);
      if (t) { t.decision = decision; t.decided_at = nowISO(); t.reason = reason || ""; t.applied = false; }
    }, `idea ${decision}: ${idea.task_id}`);
    toast(decision === "approve"
      ? "已放行 ✓ 哨兵 10 分鐘內回寫 ClickUp，之後自動撰稿入料"
      : "已退回，原因會留言到卡上");
    $("#bdDrawer").classList.remove("open");
    boot();
  } catch (e) { toast(e.message, true); }
}

// ── 撰稿中卡（放行後、入板前的隱形期）────────────────────────────────
// 放行的卡從放行欄消失後，要等 排程器觸發撰稿（每 15 分 2 篇）→ 撰稿（約 6 分）→
// 哨兵入板（每 10 分一輪）才會變成貼文出現。這段最長可到 40 分鐘，
// 之前看板完全不顯示，Jesse 重整再多次也只看到空欄（2026-08-24 錄影退件）。
// 這裡把「決定了但還沒入板」的卡畫在製作中欄，給預估時間與加速鈕。
const DRAFT_HOOK = "https://lavadating.app.n8n.cloud/webhook/lava-ig-draft";

const _tkey = s => String(s || "")
  .replace(/^靈感｜|^IG貼文｜/, "").split("｜病毒分")[0]
  .replace(/[\s【】〖〗「」『』，。：！？——–\-…()（）]/g, "").slice(0, 22);

function draftingIdeas(posts) {
  const ideas = ((STATE.ideas && STATE.ideas.ideas) || []).filter(x => x.decision === "approve");
  const have = new Set(posts.map(p => _tkey(p.topic || p.id)));
  return ideas.filter(i => !have.has(_tkey(i.title)))
              .sort((a, b) => String(a.decided_at || "").localeCompare(String(b.decided_at || "")));
}

// 正常情況下「放行 → 入板」的上限：排程器每 15 分收 2 篇、撰稿約 7 分、哨兵入板每 10 分一輪。
// 佇列再長也不該超過這個上限太多，超過就是卡住，不是還在排隊。
const DRAFT_SLA_MIN = 45;

function draftingCard(idea, pos) {
  const mins = idea.decided_at ? Math.round((Date.now() - new Date(idea.decided_at)) / 60000) : 0;
  const late = mins > DRAFT_SLA_MIN;
  const c = el("div", "bd-card");
  c.style.borderLeftColor = late ? "var(--stage-you, #e05c4b)" : "var(--stage-make, #d9a441)";
  c.appendChild(el("div", "t", (late ? "⚠ " : "✍ ") +
    esc(idea.title.replace(/^靈感｜/, "").split("｜病毒分")[0])));
  const meta = el("div", "meta");
  meta.appendChild(el("span", "age", "放行於 " + esc(ago(idea.decided_at))));
  c.appendChild(meta);
  // 時間只說已知的事：等多久、正不正常。原本印「預計 25 分內入板」是憑排隊位置推的，
  // 卡了 19 小時還照印，數字完全失真（Jesse 2026-08-25 退件）。超時就直說卡住與該做什麼。
  const note = el("div", "age");
  note.style.marginTop = "4px";
  note.textContent = late
    ? `已等 ${mins < 120 ? mins + " 分" : Math.round(mins / 60) + " 小時"}，超過正常的 ${DRAFT_SLA_MIN} 分。稿可能寫好了但沒進來，按加速重跑一次。`
    : `撰稿中，正常約 ${DRAFT_SLA_MIN} 分內入板`;
  c.appendChild(note);
  const b = el("button", "btn" + (late ? " primary" : ""), late ? "⚡ 重跑撰稿" : "⚡ 加速");
  b.style.marginTop = "6px";
  b.onclick = e => { e.stopPropagation(); rushDraft(idea, b); };
  c.appendChild(b);
  return c;
}

async function rushDraft(idea, btn) {
  const ok = await modal("立即觸發撰稿？",
    el("div", "small muted",
      "跳過排程器的分批節奏，現在就開始寫這一篇。若排程器其實已經在寫，會多寫出一份草稿（無害，但多花一次模型額度）。"),
    [{ label: "取消", value: null }, { label: "立即撰稿", value: 1, cls: "primary" }]);
  if (!ok) return;
  btn.disabled = true;
  let angle = "";
  const m = /\*\*切角\*\*：([\s\S]*?)(\n\n|$)/.exec(idea.desc || "");
  if (m) angle = m[1].trim();
  const topic = (idea.title || "").replace(/^靈感｜/, "").split("｜病毒分")[0];
  try {
    const r = await tfetch(DRAFT_HOOK, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, type: "知識型", slides: 9, angle, taskId: idea.task_id, writer: "claude" }),
    }, 20000);
    if (!r.ok) throw new Error("觸發失敗 (" + r.status + ")");
    toast("已觸發撰稿 ✓ 約 6 分寫完，哨兵 10 分內入板");
    try {
      await saveJson(FILES.ideas, doc => {
        const t = (doc.ideas || []).find(x => x.task_id === idea.task_id);
        if (t) t.rushed_at = nowISO();
      }, "rush draft: " + idea.task_id);
    } catch (e) { /* 標記失敗不影響已觸發的撰稿 */ }
    boot();
  } catch (e) { btn.disabled = false; toast(e.message, true); }
}

// ── 放行欄：規則提案（repo 有的）＋ ClickUp 靈感卡（誠實地說在哪）───────
function proposalCard(pr) {
  const c = el("div", "bd-card"); c.style.borderLeftColor = "#4b5057";
  c.appendChild(el("div", "t", "⚙ " + esc(pr.title)));
  const meta = el("div", "meta");
  meta.appendChild(el("span", "age", "規則提案 · " + esc(pr.risk || "")));
  meta.appendChild(el("span", "age", esc(ago(pr.created_at))));
  c.appendChild(meta);
  c.onclick = () => openDrawer(pr);
  return c;
}

function openDrawer(pr) {
  const d = $("#bdDrawer"); d.innerHTML = "";
  d.appendChild(el("h3", null, esc(pr.title)));
  d.appendChild(el("div", "small muted", esc(pr.diff_summary || "")));
  (pr.evidence || []).forEach(ev => {
    const li = el("div", "small"); li.style.cssText = "margin:6px 0;padding:6px 8px;background:#1a1d21;border-radius:6px";
    li.textContent = ev; d.appendChild(li);
  });
  const row = el("div", "row"); row.style.cssText = "gap:8px;margin-top:14px";
  const ok = el("button", "btn primary", "放行");
  const no = el("button", "btn", "否決");
  const close = el("button", "btn", "關閉");
  ok.onclick = () => decideProposal(pr, "approved", "");
  no.onclick = async () => {
    const ta = el("textarea"); ta.rows = 2; ta.style.width = "100%";
    const r = await modal("否決原因", ta, [{ label: "取消", value: null }, { label: "否決", value: 1, cls: "primary" }]);
    if (r) decideProposal(pr, "rejected", ta.value.trim());
  };
  close.onclick = () => d.classList.remove("open");
  row.appendChild(ok); row.appendChild(no); row.appendChild(close);
  d.appendChild(row);
  d.classList.add("open");
}

async function decideProposal(pr, status, reason) {
  try {
    // 與 app.js 版本頁相同的寫入形狀，兩邊互通
    await saveJson(FILES.proposals, d => {
      const t = (d.proposals || []).find(x => x.pid === pr.pid);
      if (t) { t.status = status; t.decided_at = nowISO(); if (reason) t.reject_reason = reason; }
    }, `proposal ${status}: ${pr.pid}`);
    toast(status === "approved" ? "已放行 ✓" : "已否決");
    $("#bdDrawer").classList.remove("open");
    boot();
  } catch (e) { toast(e.message, true); }
}

// ── 頂欄健康列（§3.2：哨兵心跳 · Drive · 待跑 · 下篇發佈 · 本週體檢）────
function healthBar(posts, hb) {
  const bar = $("#bdHealth"); bar.innerHTML = "";
  const item = (color, html) => {
    const s = el("span", null, `<span class="dot" style="background:${color}"></span>${html}`);
    bar.appendChild(s); return s;
  };
  if (hb && hb.ts) {
    const min = Math.round((Date.now() - new Date(hb.ts)) / 60000);
    // 哨兵安靜時最長 55 分才推送一次心跳，>70 分＝真的斷了
    item(min > 70 ? "var(--stage-you)" : min > 25 ? "var(--stage-wait)" : "var(--stage-done)",
         `哨兵心跳 ${min} 分前`);
    item(hb.drive ? "var(--stage-done)" : "var(--stage-you)", hb.drive ? "Drive 掛載中" : "Drive 未掛載");
    if ((hb.errors || []).length)
      item("var(--stage-wait)", `上輪告警 ${hb.errors.length} 則`).title = hb.errors.join("\n");
  } else {
    item("var(--stage-wait)", "哨兵心跳：尚無資料（heartbeat.json 未產出）");
  }
  const todo = posts.filter(p => p.status === "approved" && stageOf(p)[2] === "make").length;
  item(todo ? "var(--stage-make)" : "var(--stage-done)", `待渲染 ${todo}`);
  // 撰稿卡住：放行超過 SLA 還沒入板的張數。這是最容易靜默的一段，健康列要直接說。
  const late = draftingIdeas(posts).filter(
    i => i.decided_at && (Date.now() - new Date(i.decided_at)) / 60000 > DRAFT_SLA_MIN).length;
  if (late) item("var(--stage-you)", `撰稿卡住 ${late}`).title = "放行超過 " + DRAFT_SLA_MIN + " 分仍未入板，到製作中欄按「重跑撰稿」";
  const next = posts.filter(p => p.status === "scheduled" && p.publish_at > nowISO())
                    .map(p => p.publish_at).sort()[0];
  if (next) {
    const h = Math.round((new Date(next) - Date.now()) / 3600000);
    item("var(--stage-sched)", `距下篇發佈 ${h}h`);
  } else {
    item("var(--stage-wait)", "⚠ 無已排程貼文");
  }
  // 本週體檢：近 7 天發佈＋排程的型式組合
  const wk = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
  const week = posts.filter(p => ((p.publish_at || p.published_at || "").slice(0, 10)) >= wk);
  const cnt = k => week.filter(p => (p.topic_type || "").includes(k)).length;
  const mix = [["知識", cnt("知識")], ["時事", cnt("熱點") + cnt("時事")], ["品牌", cnt("品牌") + cnt("產品")]];
  bar.appendChild(el("span", "small muted",
    "本週：" + mix.map(([k, n]) => `${k}${n ? "●" : "○"}${n || ""}`).join(" ")));
}

// ── 組版 ────────────────────────────────────────────────────────────
function boot() {
  const posts = ((STATE.posts && STATE.posts.posts) || []);
  const props = ((STATE.proposals && STATE.proposals.proposals) || []).filter(x => x.status === "pending");
  const main = $("#bdMain"); main.innerHTML = "";

  const stuck = posts.filter(p => p.status !== "published" && alertOf(p));
  const by = key => posts.filter(p => !alertOf(p) && stageOf(p)[2] === key);

  COLS.forEach(([name, key]) => {
    const col = el("div", "bd-col");
    const cards = el("div", "bd-cards");
    let list = [];
    if (key === "rel") {
      const ideas = (((STATE.ideas && STATE.ideas.ideas) || [])).filter(x => !x.decision);
      ideas.forEach(idea => cards.appendChild(ideaCard(idea)));
      props.forEach(pr => cards.appendChild(proposalCard(pr)));
      if (!ideas.length && !props.length) cards.appendChild(el("div", "small muted", "（今天沒有待放行的靈感）"));
      list = ideas.concat(props);
    } else if (key === "make") {
      list = by(key);
      const drafting = draftingIdeas(posts);
      drafting.forEach((idea, i) => cards.appendChild(draftingCard(idea, i)));
      list.forEach(p => cards.appendChild(postCard(p, key)));
      if (!list.length && !drafting.length) cards.appendChild(el("div", "small muted", "（空）"));
      list = list.concat(drafting);
    } else {
      list = by(key);
      list.forEach(p => cards.appendChild(postCard(p, key)));
      if (!list.length) cards.appendChild(el("div", "small muted", "（空）"));
    }
    const h = el("h4", key === "you" && list.length > WIP_LIMIT ? "over" : "");
    h.innerHTML = `${esc(name)} <span class="n">${key === "you" && list.length > WIP_LIMIT
      ? `<b style="color:var(--stage-you)">${list.length}/${WIP_LIMIT}</b>` : list.length}</span>`;
    col.appendChild(h); col.appendChild(cards);
    main.appendChild(col);
  });

  // 卡住側欄：虛線框、原因、一顆導向修復的按鈕（§3.3：發生什麼→影響什麼→怎麼做）
  const sb = el("div", "bd-stuck");
  sb.appendChild(el("h4", null, `卡住 <span class="n">${stuck.length}</span>`));
  stuck.forEach(p => {
    const c = el("div", "bd-card");
    c.appendChild(el("div", "t", esc(p.topic || p.id)));
    const why = alertOf(p) === "缺料"
      ? "有 slide 沒有任何候選圖。這篇無法出成品。等哨兵補圖，或到審稿台看是哪幾張。"
      : "渲染卡住：" + (p.render_note || "") + "。這篇不會前進。到審稿台處理。";
    c.appendChild(el("div", "age", esc(why)));
    const b = el("button", "btn", "去審稿台"); b.style.marginTop = "6px";
    b.onclick = e => { e.stopPropagation(); location.href = "review.html"; };
    c.appendChild(b);
    sb.appendChild(c);
  });
  if (!stuck.length) sb.appendChild(el("div", "small muted", "（沒有卡住的貼文）"));
  main.appendChild(sb);

  healthBar(posts, STATE.heartbeat && !STATE.heartbeat._error ? STATE.heartbeat : null);

  // 著陸例外（§1.2）：等你 ≥ WIP 上限 → 提示先清積壓
  const you = by("you").length;
  if (you > WIP_LIMIT && !$("#wipBanner")) {
    const b = el("div", null,
      `積壓 ${you} 篇「等你」，超過上限 ${WIP_LIMIT}。先清到 ${WIP_LIMIT} 篇再看別的。 `);
    b.id = "wipBanner";
    b.style.cssText = "background:#E84224;color:#fff;padding:6px 12px;font-size:13px;text-align:center";
    const a = el("a", null, "去審稿台 →"); a.href = "review.html"; a.style.color = "#fff";
    b.appendChild(a);
    document.body.insertBefore(b, $(".bd-main"));
  }
}

FILES.heartbeat = "data/heartbeat.json";
FILES.ideas = "data/ideas.json";   // 可能還沒產出，loadAll 會塞 _error，healthBar 誠實顯示
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
