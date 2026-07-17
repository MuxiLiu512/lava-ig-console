/* Lava IG 操控室 — 純 vanilla JS，無框架依賴。
   資料層：GitHub Contents API 讀寫 data/*.json（PAT 存 localStorage）；file://或localhost 走本地預覽。 */
(() => {
"use strict";
const C = window.LAVA_CONFIG;
const LS = window.localStorage;
const $ = (s, r = document) => r.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const esc = s => (s == null ? "" : String(s)).replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const nfmt = n => (n == null ? "–" : Number(n).toLocaleString("en-US"));

// ── 設定（localStorage 覆蓋 config.js） ──────────────────────────────
const S = {
  get pat() { return LS.getItem("lava_pat") || ""; },
  set pat(v) { v ? LS.setItem("lava_pat", v) : LS.removeItem("lava_pat"); },
  get owner() { return LS.getItem("lava_owner") || C.owner; },
  get repo() { return LS.getItem("lava_repo") || C.repo; },
  get branch() { return LS.getItem("lava_branch") || C.branch; },
};
const isLocalHost = location.protocol === "file:" || /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
let MODE = C.mode === "auto" ? (isLocalHost ? "local" : "github") : C.mode;

// ── base64 / UTF-8 ──────────────────────────────────────────────────
function b64ToStr(b64) {
  const bin = atob((b64 || "").replace(/\s/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder("utf-8").decode(bytes);
}
function strToB64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = ""; const CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return btoa(bin);
}

// ── GitHub API ──────────────────────────────────────────────────────
const apiBase = () => `https://api.github.com/repos/${S.owner}/${S.repo}/contents`;
const rawUrl = p => `https://raw.githubusercontent.com/${S.owner}/${S.repo}/${S.branch}/${p}`;
const authHdr = () => (S.pat ? { Authorization: "Bearer " + S.pat } : {});

async function apiGet(path) {
  if (MODE === "local") {
    const r = await fetch("../" + path + "?t=" + Date.now());
    if (!r.ok) throw new Error("本地讀取失敗 " + path);
    return { json: await r.json(), sha: null };
  }
  const r = await fetch(`${apiBase()}/${path}?ref=${S.branch}&t=${Date.now()}`, {
    headers: { Accept: "application/vnd.github+json", ...authHdr() },
  });
  if (!r.ok) throw new Error(`讀取 ${path} 失敗 (${r.status})`);
  const j = await r.json();
  return { json: JSON.parse(b64ToStr(j.content)), sha: j.sha };
}

// 寫回：GET sha → mutate → PUT，409 重試 3 次
async function saveJson(path, mutateFn, message) {
  if (MODE === "local") {
    // 本地預覽：只改記憶體，不寫 repo
    const key = path.split("/").pop().replace(".json", "");
    mutateFn(STATE[key]);
    return { local: true };
  }
  if (!S.pat) throw new Error("尚未設定 PAT，無法寫入。請點右上角 ⚙︎ 設定。");
  let lastErr;
  for (let i = 0; i < 3; i++) {
    const { json, sha } = await apiGet(path);
    mutateFn(json);
    const body = {
      message: message || `console: update ${path}`,
      content: strToB64(JSON.stringify(json, null, 2) + "\n"),
      sha, branch: S.branch,
    };
    const r = await fetch(`${apiBase()}/${path}`, {
      method: "PUT",
      headers: { Accept: "application/vnd.github+json", "Content-Type": "application/json", ...authHdr() },
      body: JSON.stringify(body),
    });
    if (r.ok) { const key = path.split("/").pop().replace(".json", ""); STATE[key] = json; return await r.json(); }
    if (r.status === 409) { lastErr = new Error("409 撞車，重試"); continue; }
    const t = await r.text().catch(() => "");
    throw new Error(`寫入 ${path} 失敗 (${r.status}) ${t.slice(0, 120)}`);
  }
  throw lastErr || new Error("寫入重試失敗");
}

// ── 圖片載入（私有 repo 走 blob） ────────────────────────────────────
const imgCache = {};
async function setImg(node, path) {
  if (!path) { node.classList.add("imgfail"); return; }
  if (MODE === "local") { node.src = "../" + path; return; }
  if (C.publicRaw) { node.src = rawUrl(path); return; }
  if (imgCache[path]) { node.src = imgCache[path]; return; }
  try {
    const r = await fetch(`${apiBase()}/${path}?ref=${S.branch}`, { headers: { Accept: "application/vnd.github.raw", ...authHdr() } });
    if (!r.ok) throw 0;
    const u = URL.createObjectURL(await r.blob());
    imgCache[path] = u; node.src = u;
  } catch (e) { node.classList.add("imgfail"); node.alt = "圖片載入失敗"; }
}
const img = path => { const e = el("img"); setImg(e, path); return e; };

// ── State ───────────────────────────────────────────────────────────
const STATE = { posts: null, reviews: null, metrics: null, proposals: null, iterate_log: null, copy_edits: null };
const FILES = {
  posts: "data/posts.json", reviews: "data/reviews.json", metrics: "data/metrics.json",
  proposals: "data/proposals.json", iterate_log: "data/iterate_log.json", copy_edits: "data/copy_edits.json",
};
async function loadAll() {
  const keys = Object.keys(FILES);
  const res = await Promise.allSettled(keys.map(k => apiGet(FILES[k])));
  res.forEach((r, i) => { STATE[keys[i]] = r.status === "fulfilled" ? r.value.json : { _error: String(r.reason) }; });
}

// ── Toast / Modal ───────────────────────────────────────────────────
let toastT;
function toast(msg, err) {
  clearTimeout(toastT); const old = $(".toast"); if (old) old.remove();
  const t = el("div", "toast" + (err ? " err" : ""), esc(msg)); document.body.appendChild(t);
  toastT = setTimeout(() => t.remove(), err ? 4200 : 2400);
}
function modal(title, bodyNode, actions) {
  return new Promise(resolve => {
    const bg = el("div", "modal-bg");
    const m = el("div", "modal");
    m.appendChild(el("h3", null, esc(title)));
    if (bodyNode) m.appendChild(bodyNode);
    const bar = el("div", "btnrow"); bar.style.marginTop = "14px";
    actions.forEach(a => {
      const b = el("button", "btn " + (a.cls || ""), esc(a.label));
      b.onclick = () => { bg.remove(); resolve(a.value); };
      bar.appendChild(b);
    });
    m.appendChild(bar);
    bg.appendChild(m); bg.onclick = e => { if (e.target === bg) { bg.remove(); resolve(null); } };
    document.body.appendChild(bg);
  });
}
const nowISO = () => { const d = new Date(); const z = -d.getTimezoneOffset(); const p = n => String(Math.floor(Math.abs(n))).padStart(2, "0");
  const s = z >= 0 ? "+" : "-"; return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds()) + s + p(z / 60) + ":" + p(z % 60); };
const rid = pfx => pfx + "-" + Date.now().toString(36);

// ── Router ──────────────────────────────────────────────────────────
let TAB = "review", DETAIL = null;
const app = $("#app");
function render() {
  app.innerHTML = "";
  updateBadges();
  if (TAB === "review") DETAIL ? renderDetail(DETAIL) : renderQueue();
  else if (TAB === "metrics") renderMetrics();
  else if (TAB === "proposals") renderProposals();
  else if (TAB === "versions") renderVersions();
  window.scrollTo(0, 0);
}
function updateBadges() {
  const posts = (STATE.posts && STATE.posts.posts) || [];
  const nR = posts.filter(p => p.status === "awaiting_review").length;
  const nP = ((STATE.proposals && STATE.proposals.proposals) || []).filter(p => p.status === "pending").length;
  const bR = $("#cntReview"), bP = $("#cntProp");
  bR.textContent = nR; bR.classList.toggle("hidden", !nR);
  bP.textContent = nP; bP.classList.toggle("hidden", !nP);
}
function noPatBanner() {
  if (MODE === "github" && !S.pat)
    return el("div", "banner", "唯讀模式：尚未設定 PAT。點右上角 ⚙︎ 貼入 fine-grained token 才能送出審核／提案／回滾。");
  if (MODE === "local")
    return el("div", "banner", "本地預覽模式：所有操作只改瀏覽器記憶體，不會 commit 到 repo（部署到 Pages 後才會寫回）。");
  return null;
}

// ── 1. 審核佇列 ─────────────────────────────────────────────────────
function renderQueue() {
  const b = noPatBanner(); if (b) app.appendChild(b);
  const err = STATE.posts && STATE.posts._error;
  if (err) { app.appendChild(el("div", "empty", "載入 posts.json 失敗：<br>" + esc(err))); return; }
  const all = STATE.posts.posts || [];
  const posts = all.filter(p => p.status === "awaiting_review");
  const scheduled = all.filter(p => p.status === "scheduled").sort((a, b) => (a.publish_at || "").localeCompare(b.publish_at || ""));
  if (!posts.length && !scheduled.length) { app.appendChild(el("div", "empty", "🎉 審核佇列已清空")); return; }
  posts.forEach(p => app.appendChild(qcard(p, `v${p.version} · ${p.slides.length} slides · ${totalCands(p)} 候選底圖`, `<span class="tag">待審核</span>`)));
  if (scheduled.length) {
    const hdr = el("div", "small muted", "📅 已排程發佈"); hdr.style.margin = "16px 0 4px"; app.appendChild(hdr);
    scheduled.forEach(p => app.appendChild(qcard(p, `${p.slides.filter(s => s.public_url).length} 張成品 · 發佈於 ${fmtLocal(p.publish_at)}`, `<span class="tag" style="background:#1f7a4d;color:#fff">已排程</span>`)));
  }
}
function qcard(p, subtitle, tagHtml) {
  const c = el("div", "card qcard"); const pad = el("div", "pad row");
  const cover = img(coverSrc(p)); cover.className = "cover";
  const info = el("div", "grow");
  info.appendChild(el("h3", null, esc(p.topic)));
  info.appendChild(el("div", "small muted", subtitle));
  const tags = el("div", null, tagHtml); tags.style.marginTop = "6px";
  info.appendChild(tags);
  pad.appendChild(cover); pad.appendChild(info); pad.appendChild(el("div", "muted", "›"));
  c.appendChild(pad); c.onclick = () => { DETAIL = p.id; render(); };
  return c;
}
const coverSrc = p => { const s = p.slides.find(s => s.n === 1) || p.slides[0]; return (s && s.final_src) || (s && s.candidates[0] && s.candidates[0].src); };
const totalCands = p => p.slides.reduce((a, s) => a + s.candidates.length, 0);

// 每篇的選圖狀態（暫存於 memory，送出時寫入 review）
const CHOICES = {};
function choicesFor(p) {
  if (!CHOICES[p.id]) { const o = {}; p.slides.forEach(s => { if (s.candidates.length) o[s.n] = s.default_cid || s.candidates[0].cid; }); CHOICES[p.id] = o; }
  return CHOICES[p.id];
}

function renderDetail(pid) {
  const p = (STATE.posts.posts || []).find(x => x.id === pid);
  if (!p) { DETAIL = null; return render(); }
  const choice = choicesFor(p);
  const back = el("button", "detail-back", "‹ 返回佇列"); back.onclick = () => { DETAIL = null; render(); };
  app.appendChild(back);
  app.appendChild(el("h2", null, esc(p.topic) + ` <span class="muted small">v${p.version}</span>`));

  // IG Mockup
  app.appendChild(buildMockup(p, choice));

  // 文案編輯（改動 → copy_edits.json → 迭代 harness 吸收語氣）
  app.appendChild(buildCopyEditor(p));

  // 排程發佈到 IG（成品就緒時才顯示）
  app.appendChild(buildScheduler(p));

  // 候選底圖挑選
  const picker = el("div"); picker.appendChild(el("div", "small muted", "為每張 slide 挑一張底圖（點選＝標記）"));
  p.slides.forEach(s => picker.appendChild(slideBlock(p, s, choice)));
  app.appendChild(picker);

  // 動作列
  app.appendChild(actionBar(p, choice));
}

function slideBlock(p, s, choice) {
  const wrap = el("div", "slide-block");
  const hd = el("div", "hd");
  hd.appendChild(el("div", "n", String(s.n)));
  hd.appendChild(el("div", "small muted grow", esc(s.role || "")));
  wrap.appendChild(hd);
  const cands = el("div", "cands");
  if (!s.candidates.length) {
    const none = el("div", "cand none"); none.appendChild(el("div", "imwrap", "CTA 公版<br>無候選"));
    cands.appendChild(none);
  }
  s.candidates.forEach(cd => {
    const cc = el("div", "cand" + (choice[s.n] === cd.cid ? " sel" : ""));
    const iw = el("div", "imwrap"); const im = img(cd.src); iw.appendChild(im);
    iw.appendChild(el("div", "chk", "✓")); cc.appendChild(iw);
    const meta = el("div", "meta");
    meta.innerHTML = `<span class="tag ${cd.kind === "still" ? "still" : "gen"}">${cd.kind === "still" ? "劇照" : "生成"}</span><span class="tiny muted">${cd.cid.toUpperCase()}</span>`;
    cc.appendChild(meta);
    if (cd.source_label) cc.appendChild(el("div", "src", "出處：" + esc(cd.source_label)));
    cc.onclick = () => {
      choice[s.n] = cd.cid;
      // 就地更新選取狀態，不整頁重繪（避免長列表點選後跳回頂端）
      [...cands.children].forEach(x => x.classList.remove("sel"));
      cc.classList.add("sel");
    };
    cands.appendChild(cc);
  });
  wrap.appendChild(cands);
  return wrap;
}

function actionBar(p, choice) {
  const bar = el("div", "actionbar");
  const fb = el("textarea"); fb.placeholder = "回饋（退回必填；approve 選填）— 例：第2張手指壞掉；封面光線太冷";
  bar.appendChild(fb);
  const row = el("div", "btnrow"); row.style.marginTop = "8px";
  const mk = (label, cls, fn) => { const b = el("button", "btn " + cls, label); b.onclick = fn; return b; };
  const submit = async (decision, scope) => {
    const feedback = fb.value.trim();
    if (decision === "reject" && !feedback) { toast("退回必須填寫回饋", true); fb.focus(); return; }
    const review = {
      id: rid("R"), post_id: p.id, ts: nowISO(), decision,
      slide_choices: { ...choice }, scope: scope || null, feedback, consumed: false,
    };
    try {
      disableBar(bar, true);
      await saveJson(FILES.reviews, d => { (d.reviews = d.reviews || []).push(review); }, `review: ${decision} ${p.id}`);
      // 本地反映：把該貼文標記為已處理（github 模式下由排程再更新，但 UI 先移出佇列）
      p.status = decision === "approve" ? "approved" : "rejected";
      toast(decision === "approve" ? "已核准 ✓" : "已退回，排程下次處理");
      DETAIL = null; render();
    } catch (e) { toast(e.message, true); disableBar(bar, false); }
  };
  row.appendChild(mk("退回底圖", "warn", () => submit("reject", "base_image")));
  row.appendChild(mk("退回排版", "warn", () => submit("reject", "mockup")));
  row.appendChild(mk("核准 ✓", "primary", () => submit("approve", null)));
  bar.appendChild(row);
  return bar;
}
function disableBar(bar, on) { bar.querySelectorAll("button").forEach(b => b.disabled = on); }

// ── 文案編輯 ─────────────────────────────────────────────────────────
function buildCopyEditor(p) {
  const withCopy = p.slides.filter(s => s.heading != null || s.display_copy != null);
  if (!withCopy.length) return el("div");
  const card = el("div", "card"); const pad = el("div", "pad");
  pad.appendChild(el("div", null, '<b>✏️ 文案編輯</b> <span class="tiny muted">改動會餵給迭代 harness 學你的語氣</span>'));
  const fields = [];
  withCopy.forEach(s => {
    pad.appendChild(el("div", "small muted", "slide " + s.n + " · " + esc(s.role || "")));
    [["heading", "主標"], ["display_copy", "圖面文案"]].forEach(([f, label]) => {
      if (s[f] == null) return;
      pad.appendChild(el("label", "fld", label));
      const ta = el("textarea"); ta.value = s[f];
      if (f === "heading") ta.style.minHeight = "42px";
      ta.dataset.n = s.n; ta.dataset.field = f; ta.dataset.orig = s[f];
      pad.appendChild(ta); fields.push(ta);
    });
  });
  const btn = el("button", "btn primary block", "儲存文案修改"); btn.style.marginTop = "12px";
  btn.onclick = async () => {
    const edits = fields.filter(t => t.value !== t.dataset.orig)
      .map(t => ({ n: Number(t.dataset.n), field: t.dataset.field, original: t.dataset.orig, edited: t.value.trim() }));
    if (!edits.length) { toast("沒有變更"); return; }
    try {
      btn.disabled = true;
      await saveJson(FILES.copy_edits, d => { (d.edits = d.edits || []).push({ post_id: p.id, ts: nowISO(), consumed: false, edits }); }, "copy-edit: " + p.id);
      toast("已儲存 " + edits.length + " 處修改");
      edits.forEach(e => { const t = fields.find(f => Number(f.dataset.n) === e.n && f.dataset.field === e.field); if (t) t.dataset.orig = e.edited; });
    } catch (e) { toast(e.message, true); }
    btn.disabled = false;
  };
  pad.appendChild(btn); card.appendChild(pad); return card;
}

// ── 排程發佈到 IG ────────────────────────────────────────────────────
const _p2 = n => String(n).padStart(2, "0");
function defaultWhen() { const d = new Date(Date.now() + 864e5); return `${d.getFullYear()}-${_p2(d.getMonth() + 1)}-${_p2(d.getDate())}T20:00`; }
function localToISO(v) { if (!v || v.length < 16) return null; return (v.length === 16 ? v + ":00" : v) + "+08:00"; } // datetime-local 視為台灣時間
function fmtLocal(iso) { const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/); return m ? `${m[1]}/${m[2]}/${m[3]} ${m[4]}:${m[5]}` : (iso || ""); }
function buildScheduler(p) {
  const ready = p.slides.filter(s => s.public_url);
  if (!ready.length) return el("div"); // 只有出成品（有公開圖）才排得了
  const card = el("div", "card"); const pad = el("div", "pad");
  pad.appendChild(el("div", null, '<b>📅 排程發佈到 IG</b> <span class="tiny muted">' + ready.length + ' 張成品就緒</span>'));
  if (p.status === "scheduled" && p.publish_at) {
    pad.appendChild(el("div", "small", "✓ 已排程：<b>" + fmtLocal(p.publish_at) + "</b>（台灣時間）到點自動發佈"));
    const cancel = el("button", "btn warn", "取消排程"); cancel.style.marginTop = "10px";
    cancel.onclick = async () => {
      try {
        cancel.disabled = true;
        await saveJson(FILES.posts, d => { const pp = (d.posts || []).find(x => x.id === p.id); if (pp) { pp.status = "awaiting_review"; delete pp.publish_at; } }, "unschedule: " + p.id);
        toast("已取消排程"); p.status = "awaiting_review"; delete p.publish_at; render();
      } catch (e) { toast(e.message, true); cancel.disabled = false; }
    };
    pad.appendChild(cancel);
  } else {
    pad.appendChild(el("label", "fld", "發佈時間（台灣時間）"));
    const inp = el("input"); inp.type = "datetime-local"; inp.value = defaultWhen();
    pad.appendChild(inp);
    const btn = el("button", "btn primary block", "排程發佈"); btn.style.marginTop = "10px";
    btn.onclick = async () => {
      const iso = localToISO(inp.value);
      if (!iso) { toast("請先選發佈時間", true); return; }
      try {
        btn.disabled = true;
        await saveJson(FILES.posts, d => { const pp = (d.posts || []).find(x => x.id === p.id); if (pp) { pp.publish_at = iso; pp.status = "scheduled"; } }, "schedule: " + p.id + " @ " + iso);
        toast("已排程 ✓ 到點自動發佈"); p.status = "scheduled"; p.publish_at = iso; DETAIL = null; render();
      } catch (e) { toast(e.message, true); btn.disabled = false; }
    };
    pad.appendChild(btn);
  }
  card.appendChild(pad); return card;
}

// ── IG Mockup ───────────────────────────────────────────────────────
const IG_ICONS = {
  heart: '<svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.7-10-9.3C.7 9 1.9 5.7 5 5c2-.4 3.5.8 4.4 2 .3.4.9.4 1.2 0C11.5 5.8 13 4.6 15 5c3.1.7 4.3 4 3 6.7C19.5 16.3 12 21 12 21z"/></svg>',
  comment: '<svg viewBox="0 0 24 24"><path d="M21 11.5a8.5 8.5 0 0 1-12.4 7.5L3 21l2-5.6A8.5 8.5 0 1 1 21 11.5z"/></svg>',
  share: '<svg viewBox="0 0 24 24"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/></svg>',
  save: '<svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>',
};
function buildMockup(p, choice) {
  const wrap = el("div");
  const phone = el("div", "phone"); const ig = el("div", "ig");
  // top
  const top = el("div", "ig-top");
  top.innerHTML = `<div class="ig-av">L</div><div class="nm">${esc(C.ig_handle)}</div><div class="more">⋯</div>`;
  ig.appendChild(top);
  // media
  const media = el("div", "ig-media");
  const track = el("div", "ig-track");
  // 有成品用成品；尚未渲染（如 Drive 來源）則退回顯示該 slide 選中的候選底圖
  const finals = p.slides.map(s => {
    if (s.final_src) return s.final_src;
    const cand = (s.candidates || []).find(c => c.cid === choice[s.n]) || (s.candidates || [])[0];
    return cand ? cand.src : null;
  }).filter(Boolean);
  finals.forEach(src => { const sl = el("div", "ig-slide"); sl.appendChild(img(src)); track.appendChild(sl); });
  media.appendChild(track);
  const count = el("div", "ig-count", "1/" + finals.length); media.appendChild(count);
  ig.appendChild(media);
  // dots
  const dots = el("div", "ig-dots"); finals.forEach((_, i) => dots.appendChild(el("i", i === 0 ? "on" : "")));
  ig.appendChild(dots);
  track.addEventListener("scroll", () => {
    const i = Math.round(track.scrollLeft / track.clientWidth);
    count.textContent = (i + 1) + "/" + finals.length;
    [...dots.children].forEach((d, j) => d.classList.toggle("on", j === i));
  }, { passive: true });
  // actions
  const act = el("div", "ig-actions");
  act.innerHTML = IG_ICONS.heart + IG_ICONS.comment + IG_ICONS.share + '<span class="sp"></span>' + IG_ICONS.save;
  ig.appendChild(act);
  // likes + caption
  ig.appendChild(el("div", "ig-likes", "1,024 個讚"));
  const cap = el("div", "ig-cap");
  const bodyId = "cap" + p.id.replace(/[^a-z0-9]/gi, "");
  cap.innerHTML = `<span class="nm">${esc(C.ig_handle)}</span><span class="body clamp" id="${bodyId}">${esc(p.caption)}</span> <span class="more">…更多</span>`;
  const more = cap.querySelector(".more"); const body = cap.querySelector(".body");
  more.onclick = () => { const c = body.classList.toggle("clamp"); more.textContent = c ? "…更多" : " 收合"; };
  ig.appendChild(cap);
  phone.appendChild(ig); wrap.appendChild(phone);
  return wrap;
}

// ── 2. 成效 ─────────────────────────────────────────────────────────
function renderMetrics() {
  const b = noPatBanner(); if (b) app.appendChild(b);
  const entries = (STATE.metrics && STATE.metrics.entries) || [];
  const posts = (STATE.posts && STATE.posts.posts) || [];
  // 表單
  const card = el("div", "card"); const pad = el("div", "pad");
  pad.appendChild(el("div", null, "<b>手動輸入成效</b>"));
  const optPosts = posts.map(p => `<option value="${esc(p.id)}">${esc(p.topic)} v${p.version}</option>`).join("");
  pad.innerHTML += `
    <label class="fld">貼文</label><select id="mPost">${optPosts}</select>
    <div class="row" style="gap:8px">
      <div class="grow"><label class="fld">快照</label><select id="mDay"><option>D1</option><option>D3</option><option>D7</option></select></div>
      <div class="grow"><label class="fld">發布日</label><input id="mPub" type="date"></div>
    </div>
    <div class="row" style="gap:8px">
      <div class="grow"><label class="fld">觸及</label><input id="mReach" type="number" inputmode="numeric"></div>
      <div class="grow"><label class="fld">讚</label><input id="mLikes" type="number" inputmode="numeric"></div>
      <div class="grow"><label class="fld">珍藏</label><input id="mSaves" type="number" inputmode="numeric"></div>
    </div>
    <div class="row" style="gap:8px">
      <div class="grow"><label class="fld">分享</label><input id="mShares" type="number" inputmode="numeric"></div>
      <div class="grow"><label class="fld">留言</label><input id="mComments" type="number" inputmode="numeric"></div>
      <div class="grow"><label class="fld">追蹤+</label><input id="mFollows" type="number" inputmode="numeric"></div>
    </div>
    <label class="fld">備註</label><input id="mNote" placeholder="選填">`;
  const save = el("button", "btn primary block", "儲存成效"); save.style.marginTop = "10px";
  save.onclick = async () => {
    const g = id => $("#" + id).value;
    const num = id => { const v = g(id); return v === "" ? 0 : Number(v); };
    if (!g("mPost")) { toast("請選貼文", true); return; }
    const entry = { post_id: g("mPost"), published_at: g("mPub") || null, day: g("mDay"),
      reach: num("mReach"), likes: num("mLikes"), saves: num("mSaves"), shares: num("mShares"),
      comments: num("mComments"), follows: num("mFollows"),
      topic_type: (posts.find(p => p.id === g("mPost")) || {}).topic_type || "A-知識型", note: g("mNote") };
    try { save.disabled = true; await saveJson(FILES.metrics, d => { (d.entries = d.entries || []).push(entry); }, `metrics: ${entry.post_id} ${entry.day}`);
      toast("已儲存"); render(); } catch (e) { toast(e.message, true); save.disabled = false; }
  };
  pad.appendChild(save); card.appendChild(pad); app.appendChild(card);

  if (!entries.length) { app.appendChild(el("div", "empty", "尚無成效資料")); return; }

  // KPI 總覽
  const sum = (k) => entries.reduce((a, e) => a + (e[k] || 0), 0);
  const kpi = el("div", "kpi");
  kpi.innerHTML = `<div class="k"><b>${nfmt(sum("reach"))}</b><span>總觸及</span></div>
    <div class="k"><b>${nfmt(sum("saves"))}</b><span>總珍藏</span></div>
    <div class="k"><b>${nfmt(sum("follows"))}</b><span>追蹤增量</span></div>`;
  app.appendChild(kpi);

  // 長條：各貼文 reach / saves
  const nameOf = id => { const p = posts.find(x => x.id === id); return p ? p.topic : id; };
  const maxReach = Math.max(1, ...entries.map(e => e.reach || 0));
  const barsCard = el("div", "card"); const bp = el("div", "pad");
  bp.appendChild(el("div", "small muted", "各貼文 觸及（橘）／珍藏（黃）"));
  entries.forEach(e => {
    ["reach", "saves"].forEach(k => {
      const bar = el("div", "bar");
      bar.innerHTML = `<div class="lb ellip">${esc(nameOf(e.post_id))}·${k === "reach" ? "觸及" : "珍藏"}</div>
        <div class="track"><div class="fill" style="width:${Math.max(3, (e[k] || 0) / maxReach * 100)}%;background:${k === "reach" ? "var(--orange)" : "var(--yellow)"}"></div></div>
        <div class="vv">${nfmt(e[k])}</div>`;
      bp.appendChild(bar);
    });
  });
  barsCard.appendChild(bp); app.appendChild(barsCard);

  // 折線：追蹤增量
  app.appendChild(followsChart(entries, nameOf));

  // 分組平均（依 topic_type）
  const groups = {};
  entries.forEach(e => { const t = e.topic_type || "未分類"; (groups[t] = groups[t] || []).push(e); });
  const gCard = el("div", "card"); const gp = el("div", "pad");
  gp.appendChild(el("div", "small muted", "依題型 平均觸及／珍藏"));
  Object.keys(groups).forEach(t => {
    const arr = groups[t]; const avg = k => Math.round(arr.reduce((a, e) => a + (e[k] || 0), 0) / arr.length);
    gp.appendChild(el("div", "row", `<div class="grow">${esc(t)} <span class="muted tiny">(${arr.length})</span></div>
      <div class="small">觸及 <b>${nfmt(avg("reach"))}</b> · 珍藏 <b>${nfmt(avg("saves"))}</b></div>`));
  });
  gCard.appendChild(gp); app.appendChild(gCard);
}
function followsChart(entries, nameOf) {
  const card = el("div", "card"); const pad = el("div", "pad");
  pad.appendChild(el("div", "small muted", "追蹤增量趨勢"));
  const W = 320, H = 120, pad_ = 24;
  const pts = entries.map((e, i) => ({ x: entries.length === 1 ? W / 2 : pad_ + i * (W - 2 * pad_) / (entries.length - 1), v: e.follows || 0, e }));
  const maxV = Math.max(1, ...pts.map(p => p.v));
  const y = v => H - pad_ - v / maxV * (H - 2 * pad_);
  const line = pts.map((p, i) => (i ? "L" : "M") + p.x.toFixed(1) + " " + y(p.v).toFixed(1)).join(" ");
  const dots = pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="3.5" fill="var(--orange)"/>
    <text x="${p.x.toFixed(1)}" y="${(y(p.v) - 8).toFixed(1)}" fill="var(--text)" font-size="10" text-anchor="middle">${p.v}</text>`).join("");
  pad.innerHTML += `<svg class="chart" viewBox="0 0 ${W} ${H}"><line x1="${pad_}" y1="${H - pad_}" x2="${W - pad_}" y2="${H - pad_}" stroke="var(--line)"/>
    <path d="${line}" fill="none" stroke="var(--orange)" stroke-width="2"/>${dots}</svg>`;
  card.appendChild(pad); return card;
}

// ── 3. 迭代提案 ─────────────────────────────────────────────────────
function renderProposals() {
  const b = noPatBanner(); if (b) app.appendChild(b);
  const props = (STATE.proposals && STATE.proposals.proposals) || [];
  const pending = props.filter(p => p.status === "pending");
  const decided = props.filter(p => p.status !== "pending");
  if (!pending.length) app.appendChild(el("div", "empty", "沒有待審提案"));
  pending.forEach(pr => app.appendChild(proposalCard(pr, true)));
  if (decided.length) {
    app.appendChild(el("div", "small muted", "已決策"));
    decided.slice().reverse().forEach(pr => app.appendChild(proposalCard(pr, false)));
  }
}
function proposalCard(pr, actionable) {
  const c = el("div", "card"); const pad = el("div", "pad");
  pad.appendChild(el("div", "row", `<div class="grow"><b>${esc(pr.title)}</b></div>
    <span class="tag ${pr.risk}">${pr.risk === "high" ? "高風險" : "低風險"}</span>`));
  pad.appendChild(el("div", "small muted", "PID " + esc(pr.pid)));
  pad.appendChild(el("div", "small", "<br><b>變更：</b>" + esc(pr.diff_summary)));
  if (pr.evidence && pr.evidence.length) {
    const ul = el("ul", "changes small"); pr.evidence.forEach(e => ul.appendChild(el("li", null, esc(e))));
    pad.appendChild(el("div", "small", "<br><b>依據：</b>")); pad.appendChild(ul);
  }
  if (!actionable) pad.appendChild(el("div", "tiny muted", `<br>${pr.status === "approved" ? "✓ 已核准" : "✕ 已駁回"} · ${esc(pr.decided_at || "")}`));
  c.appendChild(pad);
  if (actionable) {
    const row = el("div", "pad"); const g = el("div", "btnrow"); g.style.gridTemplateColumns = "1fr 1fr";
    const rej = el("button", "btn danger", "駁回");
    const app_ = el("button", "btn primary", "核准套用");
    rej.onclick = () => decideProposal(pr, "rejected");
    app_.onclick = () => decideProposal(pr, "approved");
    g.appendChild(rej); g.appendChild(app_); row.appendChild(g); c.appendChild(row);
  }
  return c;
}
async function decideProposal(pr, status) {
  let reason = "";
  if (status === "rejected") {
    const ta = el("textarea"); ta.placeholder = "駁回理由（會併入 iterate log）";
    const ok = await modal("駁回提案：" + pr.title, ta, [{ label: "取消", value: false }, { label: "確認駁回", cls: "danger", value: true }]);
    if (!ok) return; reason = ta.value.trim();
  } else {
    const ok = await modal("核准提案", el("div", "small muted", pr.title + "\n\n核准後，排程B（每日 21:30）下次執行會套用此變更並產生 config commit。"),
      [{ label: "取消", value: false }, { label: "確認核准", cls: "primary", value: true }]);
    if (!ok) return;
  }
  try {
    await saveJson(FILES.proposals, d => {
      const t = (d.proposals || []).find(x => x.pid === pr.pid); if (t) { t.status = status; t.decided_at = nowISO(); if (reason) t.reject_reason = reason; }
    }, `proposal: ${status} ${pr.pid}`);
    toast(status === "approved" ? "已核准，排程將套用" : "已駁回"); render();
  } catch (e) { toast(e.message, true); }
}

// ── 4. 版本 ─────────────────────────────────────────────────────────
function renderVersions() {
  const b = noPatBanner(); if (b) app.appendChild(b);
  const log = STATE.iterate_log || {}; const versions = (log.versions || []).slice().reverse();
  const reqs = (log.rollback_requests || []).filter(r => !r.consumed);
  if (reqs.length) {
    const c = el("div", "card"); const pad = el("div", "pad");
    pad.innerHTML = `<b>⏳ 待處理回滾</b>`;
    reqs.forEach(r => pad.appendChild(el("div", "small muted", `回滾至 ${esc(r.target_v)} · 送出於 ${esc(r.ts)}（排程B下次執行）`)));
    c.appendChild(pad); app.appendChild(c);
  }
  if (!versions.length) { app.appendChild(el("div", "empty", "尚無版本記錄")); return; }
  const tl = el("div", "timeline card"); const pad = el("div", "pad");
  versions.forEach(v => {
    const node = el("div", "v" + (v.rollback_of ? " rollback" : ""));
    node.appendChild(el("div", "row", `<div class="grow"><b>${esc(v.v)}</b> <span class="muted tiny">${esc(v.date)}</span></div>
      <span class="chip">${v.auto_applied ? "自動" : "人工核准"}</span> <span class="tag ${v.risk}">${v.risk === "high" ? "高" : "低"}</span>`));
    if (v.commit) node.appendChild(el("div", "tiny muted", "commit " + esc(v.commit) + (v.rollback_of ? " · 回滾自 " + esc(v.rollback_of) : "")));
    const ul = el("ul", "changes small"); (v.changes || []).forEach(ch => ul.appendChild(el("li", null, esc(ch)))); node.appendChild(ul);
    if (v.trigger && (v.trigger.reviews?.length || v.trigger.metrics_window))
      node.appendChild(el("div", "tiny muted", "觸發：" + [(v.trigger.reviews || []).join(","), v.trigger.metrics_window].filter(Boolean).join(" · ")));
    const rb = el("button", "btn ghost", "回滾至此版"); rb.style.marginTop = "8px"; rb.style.fontSize = "12.5px"; rb.style.padding = "7px 12px";
    rb.onclick = () => requestRollback(v);
    node.appendChild(rb);
    pad.appendChild(node);
  });
  tl.appendChild(pad); app.appendChild(tl);
}
async function requestRollback(v) {
  const ok = await modal("回滾到 " + v.v, el("div", "small muted", `將寫入回滾請求。排程B下次執行會用 git revert（保留歷史）回到 ${v.v} 的 config 狀態，並產生新版本記錄。`),
    [{ label: "取消", value: false }, { label: "確認回滾", cls: "warn", value: true }]);
  if (!ok) return;
  try {
    await saveJson(FILES.iterate_log, d => { (d.rollback_requests = d.rollback_requests || []).push({ target_v: v.v, ts: nowISO(), consumed: false }); }, `rollback request → ${v.v}`);
    toast("已送出回滾請求"); render();
  } catch (e) { toast(e.message, true); }
}

// ── 設定 modal（自訂：需在關閉前讀取表單值） ────────────────────────
function openSettings2() {
  const bg = el("div", "modal-bg"); const m = el("div", "modal");
  m.innerHTML = `<h3>設定</h3>
    <div class="small muted">PAT 只存在此瀏覽器（localStorage），不寫進 repo。需 fine-grained token，僅授權此 repo 的 Contents 讀寫。</div>
    <label class="fld">GitHub 帳號 owner</label><input id="sOwner" value="${esc(S.owner)}">
    <label class="fld">Repo</label><input id="sRepo" value="${esc(S.repo)}">
    <label class="fld">Branch</label><input id="sBranch" value="${esc(S.branch)}">
    <label class="fld">Fine-grained PAT</label><input id="sPat" type="password" placeholder="${S.pat ? "（已設定，留空不變）" : "github_pat_..."}">
    <div class="tiny muted" style="margin-top:6px" id="sMode">目前模式：${MODE}</div>`;
  const bar = el("div", "btnrow"); bar.style.marginTop = "14px"; bar.style.gridTemplateColumns = "1fr 1fr 1fr";
  const bCancel = el("button", "btn ghost", "取消");
  const bTest = el("button", "btn", "測試連線");
  const bSave = el("button", "btn primary", "儲存");
  const readVals = () => ({ owner: $("#sOwner").value.trim(), repo: $("#sRepo").value.trim(), branch: $("#sBranch").value.trim(), pat: $("#sPat").value.trim() });
  const persist = () => { const v = readVals();
    if (v.owner) LS.setItem("lava_owner", v.owner); if (v.repo) LS.setItem("lava_repo", v.repo);
    if (v.branch) LS.setItem("lava_branch", v.branch); if (v.pat) S.pat = v.pat; };
  bCancel.onclick = () => bg.remove();
  bTest.onclick = async () => {
    persist(); if (C.mode === "auto") MODE = isLocalHost ? "local" : "github";
    bTest.disabled = true; bTest.textContent = "測試中…";
    try { await apiGet(FILES.posts); toast("連線成功 ✓"); } catch (e) { toast("連線失敗：" + e.message, true); }
    bTest.disabled = false; bTest.textContent = "測試連線";
  };
  bSave.onclick = () => { persist(); bg.remove(); toast("已儲存設定"); loadAll().then(render); };
  bar.appendChild(bCancel); bar.appendChild(bTest); bar.appendChild(bSave); m.appendChild(bar);
  bg.appendChild(m); bg.onclick = e => { if (e.target === bg) bg.remove(); };
  document.body.appendChild(bg);
}

// ── init ────────────────────────────────────────────────────────────
$("#modeTag").textContent = MODE === "local" ? "· 本地預覽" : "";
$("#btnSettings").onclick = openSettings2;
document.querySelectorAll("nav.tabbar button").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll("nav.tabbar button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active"); TAB = btn.dataset.tab; DETAIL = null; render();
  };
});
loadAll().then(render).catch(e => { app.innerHTML = ""; app.appendChild(el("div", "empty", "初始化失敗：" + esc(e.message))); });
})();
