/* Lava 操控室共用層 — 設定、GitHub API、狀態、UI 小工具。
   〔2026-08-17〕從 app.js 抽出：新審稿台要用同一套 API 層。
   兩份複本必然分歧，而分歧正是 self-check A9 那類錯誤（同一件事被算兩次）。
   載入順序：config.js → core.js → 頁面腳本。 */
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
function _unusedB64ToStr(b64) {
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

// 讀取一律走 raw media type，不走 base64 的 `content` 欄位。
// 〔2026-08-17，UIUX 總體架構 §7.1〕contents API 的 JSON 回應只在檔案 <1MB 時附 content，
// 超過就沒有 → posts.json 目前 490KB／27 篇（18.2KB／篇），再約 29 篇整個操控室會讀不到資料。
// raw media type 沒有這個限制。代價是拿不到 sha，所以寫入時另外用目錄列表取（見 shaOf）。
// PAT 失效時的降級 〔2026-08-19 事故〕
// PAT 過期後，每個讀取都帶著壞 token → GitHub 對任何資源一律回 401（即使是公開 repo），
// 整個操控室因此全滅。但 repo 是公開的（Pages 免費方案的前提），「讀」根本不需要憑證——
// 憑證只有「寫」需要。所以：讀到 401 → 標記 AUTH_BAD、掛橫幅、改無認證重讀。
// 無認證額度 60 次/小時/IP，JSON 每次載入 7 個檔，單人操作足夠；圖片走 publicRaw CDN 不計額。
let AUTH_BAD = false;

function authBanner() {
  if ($("#patBanner")) return;
  const b = el("div", null,
    '⚠ GitHub PAT 已失效：目前<b>唯讀</b>，核准／排程／文案儲存都無法寫入。 ');
  b.id = "patBanner";
  b.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:99;background:#B45309;" +
    "color:#fff;padding:6px 12px;font-size:13px;text-align:center";
  const btn = el("button", "btn", "更新 PAT");
  btn.style.cssText = "margin-left:8px;padding:1px 10px;font-size:12px";
  btn.onclick = patModal;
  b.appendChild(btn);
  document.body.prepend(b);
  document.body.style.paddingTop = "34px";
}

async function patModal() {
  const wrap = el("div");
  wrap.appendChild(el("div", "small muted",
    "貼上新的 fine-grained PAT（Contents 讀寫、僅授權 lava-ig-console）。只存這台瀏覽器的 localStorage，不會進 repo。"));
  const inp = el("input"); inp.type = "password"; inp.placeholder = "github_pat_…";
  inp.style.marginTop = "8px";
  wrap.appendChild(inp);
  const ok = await modal("更新 GitHub PAT", wrap,
    [{ label: "取消", value: null }, { label: "儲存並重載", value: 1, cls: "primary" }]);
  if (ok && inp.value.trim()) { S.pat = inp.value.trim(); location.reload(); }
}

async function apiGet(path) {
  if (MODE === "local") {
    const r = await fetch("../" + path + "?t=" + Date.now());
    if (!r.ok) throw new Error("本地讀取失敗 " + path);
    return { json: await r.json(), sha: null };
  }
  const url = `${apiBase()}/${path}?ref=${S.branch}&t=${Date.now()}`;
  if (S.pat && !AUTH_BAD) {
    const r = await fetch(url, { headers: { Accept: "application/vnd.github.raw", ...authHdr() } });
    if (r.ok) return { json: JSON.parse(await r.text()), sha: null };
    if (r.status !== 401) throw new Error(`讀取 ${path} 失敗 (${r.status})`);
    AUTH_BAD = true; authBanner();          // 壞 PAT：降級唯讀，往下走無認證
  }
  const r2 = await fetch(url, { headers: { Accept: "application/vnd.github.raw" } });
  if (!r2.ok) throw new Error(`讀取 ${path} 失敗 (${r2.status})`);
  return { json: JSON.parse(await r2.text()), sha: null };
}

// 取檔案的 blob sha（寫入時 PUT 需要）。走「目錄列表」而不是「單檔內容」——
// 目錄列表不含檔案內容，因此不受 1MB 限制。
async function shaOf(path) {
  const i = path.lastIndexOf("/");
  const dir = i < 0 ? "" : path.slice(0, i);
  const name = path.slice(i + 1);
  const r = await fetch(`${apiBase()}/${dir}?ref=${S.branch}&t=${Date.now()}`, {
    headers: { Accept: "application/vnd.github+json", ...authHdr() },
  });
  if (!r.ok) throw new Error(`取 sha 失敗 ${path} (${r.status})`);
  const hit = (await r.json()).find(x => x.name === name);
  if (!hit) throw new Error(`取 sha 失敗：${path} 不存在`);
  return hit.sha;
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
  if (AUTH_BAD) throw new Error("PAT 已失效：目前唯讀。點頂部橫幅「更新 PAT」換新的再試。");
  let lastErr;
  for (let i = 0; i < 3; i++) {
    const [{ json }, sha] = await Promise.all([apiGet(path), shaOf(path)]);
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
    if (r.status === 401) { AUTH_BAD = true; authBanner(); throw new Error("PAT 已失效：寫入被 GitHub 拒絕（401）。點頂部橫幅「更新 PAT」。"); }
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
const STATE = { posts: null, reviews: null, metrics: null, proposals: null, iterate_log: null, copy_edits: null, insights: null };
const FILES = {
  posts: "data/posts.json", reviews: "data/reviews.json", metrics: "data/metrics.json",
  proposals: "data/proposals.json", iterate_log: "data/iterate_log.json", copy_edits: "data/copy_edits.json",
  insights: "data/insights.json",
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


// ── 三維狀態模型（§3.1）——唯一正本，審稿台與工作台共用 ────────────────
// 維度 A 階段（單選）：品牌橘只給「等你」；維度 B 閘門四點（固定順序＝管線順序）；
// 維度 C 警示（最多一個）。一張卡最多 1 階段＋4 點＋0/1 警示，禁止其他標籤。
const slidesDone = p => (p.slides || []).every(sl => sl.final_src || sl.public_url || /CTA/i.test(String(sl.role || "")));
// 產品版型的 diagram/price/cta 是引擎繪製的設計版面，本來就沒照片——
// 2026-08-20 把它們誤判成「缺料 block」擋住核准，產品稿一進審稿台就被鎖死。
const DESIGN_LAYOUTS = ["diagram", "price", "cta"];
const lacksMaterial = sl => !/CTA/i.test(String(sl.role || ""))
  && !DESIGN_LAYOUTS.includes(String(sl.product_layout || ""))
  && !(sl.candidates || []).length && !(sl.final_src || sl.public_url);

function stageOf(p) {
  if (p.status === "published") return ["已發", "var(--stage-done)", "done"];
  if (p.status === "scheduled") return ["已排", "var(--stage-sched)", "sched"];
  if (p.status === "awaiting_review") return ["等你", "var(--stage-you)", "you"];
  if (p.status === "approved") {
    if (p.render_note) return ["等你", "var(--stage-you)", "you"];
    return slidesDone(p) ? ["待排", "var(--stage-wait)", "wait"] : ["製作中", "var(--stage-make)", "make"];
  }
  return ["候選", "#4b5057", "cand"];
}

function gatesOf(p) {
  const g = x => (x == null ? "" : x.pass === true ? "ok"
    : ((x.issues || []).some(i => i.severity === "block" || i.sev === "block") ? "bad" : "warn"));
  // 「事實」原本是空格子（有欄位沒有人填）。2026-08-23 起由 scripts/fact_check.py 填，
  // 檢查每個數字／研究引用有沒有活著且對得上的出處。
  return [["文案", ""], ["事實", g(p.fact)], ["視覺", g(p.qa)], ["排版", g(p.typography)]];
}

function alertOf(p) {
  if (p.render_note) return "卡住";
  if ((p.slides || []).some(lacksMaterial)) return "缺料";
  return null;
}

window.LavaCore = { C, LS, S, MODE, isLocalHost, $, el, esc, nfmt, strToB64, apiBase, rawUrl, authHdr, apiGet, shaOf, saveJson, patModal, setImg, stageOf, gatesOf, alertOf, slidesDone, lacksMaterial, DESIGN_LAYOUTS, img, STATE, FILES, loadAll, toast, modal, nowISO, rid };
})();
