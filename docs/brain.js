/* 規則本〔學 Stanley 的 Brain，2026-09-03〕
   config/ 底下那幾份檔案一直是整套系統的行為正本：撰稿讀 style-notes 決定語氣、
   閘門讀 banned-words 決定擋什麼、排版讀 visual-rules 決定版面。內容不輸 Stanley，
   差別只在「你改不到」——它們是 repo 裡的檔案，只有工程師編輯得了。
   這一頁把它們變成你可以直接改的東西。價值不是介面好看，是規則的主人變成你。 */
(() => {
"use strict";
const { $, el, esc, MODE, loadText, saveText, patModal, toast, modal } = window.LavaCore;
const { icon, ActionButton } = window.LavaUI;

// 每一份的「它管什麼」要說清楚——你要知道改下去會影響哪一段流程，
// 否則編輯框只是個沒人敢動的黑箱。
const PAGES = [
  { id: "style", file: "config/style-notes.md", name: "文字風格",
    sub: "語氣、禁句、你退回時累積的規則",
    why: "撰稿模型每次寫稿前都會讀這份。你在審稿台退回的意見，每晚會被自動整理成規則追加到這裡——" +
         "所以這份會越來越長，最下面通常是最新的。想立刻改變文風，改這份最直接。" },
  { id: "banned", file: "config/banned-words.txt", name: "禁用詞",
    sub: "一行一個詞，命中就擋",
    why: "文案檢查逐字比對這份。命中的詞會讓那張圖不能確認，你必須改掉才過得了。" +
         "這是硬規則，不是建議——放進來的詞就等於「絕對不准出現」。" },
  { id: "visual", file: "config/visual-rules.md", name: "視覺規則",
    sub: "選圖與版面的判斷準則",
    why: "找圖與視覺檢查會參考這份。想改變「什麼樣的圖算合格」，改這裡。" },
  { id: "reel", file: "config/reel-prompts.md", name: "影片規則",
    sub: "Reels 各段落的生成指令正本",
    why: "影片的角色、分鏡、口播、空景各段的指令都在這份。改這裡＝改所有未來的影片。" +
         "不要在程式碼裡寫死影片指令，一律改這份。" },
  { id: "selfcheck", file: "config/self-check.md", name: "自我審查",
    sub: "封面文案的機械自檢規則",
    why: "撰稿完成後，封面會照這份逐條自檢。這份最長，多數是歷次事故累積下來的條款。" },
  { id: "qc", file: "config/qc-checklist.md", name: "發佈前檢查",
    sub: "成品發佈前的人工檢查清單",
    why: "這份是給人看的清單，不是機器讀的。放你希望自己每次發佈前都確認一遍的事。" },
  { id: "templates", file: "data/templates.json", name: "內容範本", kind: "templates",
    sub: "貼文與 Reels 的骨架，可新增可改",
    why: "每個範本是一種「文章怎麼鋪陳」的骨架。撰稿時會挑一個來用，審稿台也可以換。" +
         "改完立刻生效，下一篇就照新骨架寫——不必等我改程式。" +
         "狀態分兩種：驗證過的會優先被挑，候選的要你確認有效才升級。" },
  { id: "rituals", file: "data/rituals.json", name: "自動化慣例", kind: "rituals",
    sub: "系統每輪自己做的事，可開關",
    why: "系統每 17 分鐘會自己做一輪，這些是它做的事。過去全部寫死在腳本裡，你看不到也關不掉。" +
         "關掉的步驟哨兵會在日誌留一行說明，不是靜默跳過——靜默跳過的話你會以為它壞了。" },
];

let CUR = PAGES[0], ORIG = "", DIRTY = false;

function renderNav() {
  const nav = $("#bnNav"); nav.innerHTML = "";
  PAGES.forEach(p => {
    const b = el("button", p.id === CUR.id ? "on" : "");
    b.type = "button";
    b.innerHTML = `${esc(p.name)}<small>${esc(p.sub)}</small>`;
    b.onclick = () => {
      if (DIRTY && !confirm("這一份有還沒存的修改，切走會不見。要離開嗎？")) return;
      CUR = p; open();
    };
    nav.appendChild(b);
  });
}

async function open() {
  renderNav();
  const body = $("#bnBody"); body.innerHTML = "";
  const head = el("div", "bn-head");
  head.appendChild(el("h2", null, esc(CUR.name)));
  head.appendChild(el("span", "meta", esc(CUR.file)));
  body.appendChild(head);
  body.appendChild(el("div", "bn-why", esc(CUR.why)));

  const sk = el("div", "skel"); sk.style.height = "60vh";
  body.appendChild(sk);
  if (CUR.kind === "rituals") { sk.remove(); return openRituals(body); }
  if (CUR.kind === "templates") { sk.remove(); return openTemplates(body); }
  let text;
  try {
    text = await loadText(CUR.file);
  } catch (e) {
    sk.remove();
    const err = el("div", "empty");
    err.appendChild(el("div", null, "<b>讀不到這一份</b>"));
    err.appendChild(el("div", "small muted", esc(e.message)));
    body.appendChild(err);
    return;
  }
  sk.remove();
  ORIG = text; DIRTY = false;

  const ta = el("textarea", "bn-edit");
  ta.value = text;
  ta.spellcheck = false;
  body.appendChild(ta);

  const bar = el("div", "bn-bar");
  const save = ActionButton({
    id: "brain-save-" + CUR.id, label: "存檔", kind: "primary", doneLabel: "存好了",
    run: async () => {
      if (ta.value === ORIG) { const e = new Error("沒有變動"); e.silent = true; throw e; }
      await saveText(CUR.file, ta.value, "brain: 編輯 " + CUR.file);
      ORIG = ta.value; DIRTY = false; paint();
    },
    onDone: () => toast("存好了。下一輪撰稿與檢查就照新規則做。"),
  });
  const revert = el("button", "btn ghost", "還原");
  revert.type = "button";
  revert.onclick = () => { ta.value = ORIG; DIRTY = false; paint(); };
  const info = el("span", "meta");
  bar.appendChild(save); bar.appendChild(revert); bar.appendChild(info);
  body.appendChild(bar);

  const paint = () => {
    DIRTY = ta.value !== ORIG;
    const lines = ta.value.split("\n").length;
    info.textContent = `${ta.value.length} 字 · ${lines} 行` + (DIRTY ? " · 有還沒存的修改" : "");
    info.style.color = DIRTY ? "var(--warn)" : "var(--text-3)";
    save.disabled = !DIRTY;
  };
  ta.addEventListener("input", paint);
  ta.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); if (DIRTY) save.click(); }
  });
  paint();
}

// 內容範本：新增、編輯、升降狀態，改完立刻生效。
// 〔Jesse 2026-09-03：還要增加不同的 template，也希望能即時完成修改〕
const T_FIELDS = [
  { k: "hook_type", label: "名稱（開場類型）", ph: "例：數據反差、趨勢詞策展", req: true },
  { k: "skeleton", label: "骨架", ph: "用 → 分段，例：cover=大字標題 → 2-4張=展開 → 尾張=CTA", req: true, big: true },
  { k: "why_it_works", label: "為什麼有效", ph: "一段話說清楚它為什麼抓得住人", big: true },
  { k: "fit_for_lava", label: "為什麼適合 Lava", ph: "跟我們的定位怎麼扣上", big: true },
];

async function openTemplates(body) {
  const { saveJson, apiGet } = window.LavaCore;
  let doc;
  try { doc = (await apiGet("data/templates.json")).json; }
  catch (e) { body.appendChild(el("div", "empty", "讀不到範本庫：" + esc(e.message))); return; }
  const list = doc.templates || [];

  const bar = el("div", "btnrow"); bar.style.marginBottom = "12px";
  ["post", "reels"].forEach(tp => {
    const b = el("button", "btn", "＋ 新增" + (tp === "post" ? "貼文" : "Reels") + "範本");
    b.type = "button";
    b.onclick = () => editTemplate(null, tp, doc);
    bar.appendChild(b);
  });
  body.appendChild(bar);

  ["post", "reels"].forEach(tp => {
    const mine = list.filter(t => (t.type || "post") === tp);
    if (!mine.length) return;
    body.appendChild(el("div", "meta", (tp === "post" ? "貼文" : "Reels") + "範本 " + mine.length + " 個"));
    const grid = el("div", "tpl-grid"); grid.style.margin = "6px 0 16px";
    mine.sort((a, b) => (a.status === "validated" ? -1 : 1) - (b.status === "validated" ? -1 : 1));
    mine.forEach(t => grid.appendChild(templateCard(t, doc)));
    body.appendChild(grid);
  });
}

function templateCard(t, doc) {
  const { tplName } = window.LavaTerms;
  const c = el("div", "tpl-card");
  c.appendChild(skeletonMini(t.skeleton));
  c.appendChild(el("h3", null, esc(tplName(t))));
  c.appendChild(el("div", "small muted", esc(String(t.why_it_works || "").slice(0, 70)) + "…"));
  const meta = el("div", "tpl-meta");
  meta.appendChild(el("span", "gate " + (t.status === "validated" ? "ok" : ""),
                      t.status === "validated" ? "驗證過" : "候選"));
  meta.appendChild(el("span", "meta", "已用 " + ((t.used_by || []).length) + " 篇"));
  c.appendChild(meta);
  const row = el("div", "btnrow");
  const edit = el("button", "btn ghost", "編輯");
  edit.type = "button"; edit.onclick = () => editTemplate(t, t.type || "post", doc);
  row.appendChild(edit);
  row.appendChild(window.LavaUI.ActionButton({
    id: "tpl-status-" + t.id,
    label: t.status === "validated" ? "降回候選" : "標為驗證過",
    kind: "ghost", doneLabel: "改好了",
    run: () => window.LavaCore.saveJson("data/templates.json", d => {
      const x = (d.templates || []).find(y => y.id === t.id);
      if (x) x.status = t.status === "validated" ? "candidate" : "validated";
    }, `template: ${t.id} 狀態`),
    onDone: () => { toast("改好了。撰稿優先挑驗證過的範本。"); open(); },
  }));
  c.appendChild(row);
  return c;
}

function skeletonMini(sk) {
  const w = el("div", "tpl-skel");
  String(sk || "").split("→").map(x => x.trim()).filter(Boolean).slice(0, 6).forEach(seg => {
    const b = el("div", "seg");
    b.appendChild(el("i"));
    b.appendChild(el("span", null, esc(seg.slice(0, 26))));
    w.appendChild(b);
  });
  return w;
}

async function editTemplate(t, type, doc) {
  const isNew = !t;
  const wrap = el("div");
  const inputs = {};
  T_FIELDS.forEach(f => {
    wrap.appendChild(el("label", "fld", esc(f.label) + (f.req ? " *" : "")));
    const i = f.big ? el("textarea") : el("input");
    if (f.big) i.rows = 3;
    i.placeholder = f.ph;
    i.value = (t && t[f.k]) || "";
    inputs[f.k] = i;
    wrap.appendChild(i);
  });
  const ok = await modal(isNew ? "新增範本" : "編輯範本", wrap,
    [{ label: "取消", value: null }, { label: isNew ? "新增" : "儲存", value: 1, cls: "primary" }]);
  if (!ok) return;
  for (const f of T_FIELDS) {
    if (f.req && !inputs[f.k].value.trim()) return toast(f.label + " 一定要填", true);
  }
  try {
    await window.LavaCore.saveJson("data/templates.json", d => {
      const arr = d.templates = d.templates || [];
      if (isNew) {
        const id = "tpl-" + Date.now().toString(36);
        const o = { id, type, status: "candidate", used_by: [],
                    evidence: { engagement: "unverified（新增時未查證）" } };
        T_FIELDS.forEach(f => { o[f.k] = inputs[f.k].value.trim(); });
        arr.push(o);
      } else {
        const x = arr.find(y => y.id === t.id);
        if (x) T_FIELDS.forEach(f => { x[f.k] = inputs[f.k].value.trim(); });
      }
    }, isNew ? "template: 新增" : "template: 編輯 " + t.id);
    toast(isNew ? "新增好了。狀態是候選，用過覺得有效再標為驗證過。" : "存好了。下一篇撰稿就吃得到。");
    open();
  } catch (e) { toast(e.message, true); }
}

// 自動化慣例：一張卡一件事，開關即存。
// 〔Stanley 的 Rituals 命名法：動詞＋受詞，一句話說完它做什麼〕
async function openRituals(body) {
  const { saveJson, FILES, STATE, apiGet } = window.LavaCore;
  let doc;
  try {
    doc = (await apiGet("data/rituals.json")).json;
  } catch (e) {
    body.appendChild(el("div", "empty", "讀不到慣例清單：" + esc(e.message))); return;
  }
  // 分組呈現〔Stanley 的 Rituals 頁：Daily rhythm 與各平台分開〕
  // 它的標題是「Set Stanley's rhythm. / Things Stanley does when you're not looking.」
  // ——慣例是你養成的節奏，不是機器的排程。這個用字差別決定誰是主人。
  const hd = el("div", "bn-why");
  hd.style.cssText = "margin:-4px 0 14px";
  hd.innerHTML = "<b>設定內容團隊的節奏。</b><br>這些是你不在看的時候，它自己會做的事。";
  body.appendChild(hd);
  const wrap = el("div"); wrap.style.display = "grid"; wrap.style.gap = "10px";
  const groups = {};
  (doc.rituals || []).forEach(r => { (groups[r.group || "其他"] = groups[r.group || "其他"] || []).push(r); });
  Object.entries(groups).forEach(([g, rs]) => {
    const h = el("div", "meta", g + "（" + rs.length + "）");
    h.style.cssText = "margin-top:8px;font-weight:600;color:var(--text-2)";
    wrap.appendChild(h);
    rs.forEach(r => wrap.appendChild(ritualCard(r)));
  });
  body.appendChild(wrap);
}

function ritualCard(r) {
  const { el, esc, toast } = window.LavaCore;
  {
    const c = el("div", "card"); const pad = el("div", "pad");
    const row = el("div", "row");
    const mid = el("div", "grow");
    mid.appendChild(el("div", null, `<b>${esc(r.name)}</b>`));
    mid.appendChild(el("div", "sub", esc(r.what)));
    if (r.flow) {
      const fl = el("div", "meta");
      fl.style.cssText = "margin-top:3px;font-variant-numeric:tabular-nums;color:var(--info)";
      fl.textContent = r.flow;                 // 一眼看出這張卡在搬什麼
      mid.appendChild(fl);
    }
    const meta = el("div", "meta"); meta.style.marginTop = "4px";
    meta.textContent = r.cadence + (r.note ? " · " + r.note : "");
    mid.appendChild(meta);
    row.appendChild(mid);
    const st = el("span", "dotlbl " + (r.enabled ? "ok" : ""));
    st.innerHTML = r.enabled ? "<i></i>開著" : "<i></i>關著";
    row.appendChild(st);
    row.appendChild(ActionButton({
      id: "ritual-" + r.id, label: r.enabled ? "關掉" : "打開",
      kind: r.enabled ? "ghost" : "primary", doneLabel: r.enabled ? "關了" : "開了",
      confirm: r.enabled ? ("關掉之後系統就不會再做這件事。" + (r.note || "")) : null,
      run: async () => {
        await saveJson("data/rituals.json", d => {
          const t = (d.rituals || []).find(x => x.id === r.id);
          if (t) t.enabled = !r.enabled;
        }, `ritual: ${r.id} → ${r.enabled ? "off" : "on"}`);
      },
      onDone: () => { toast(r.enabled ? "關了。下一輪起系統不再做這件事。" : "開了。下一輪起會恢復。"); open(); },
    }));
    pad.appendChild(row);
    c.appendChild(pad);
    if (!r.enabled) c.style.opacity = ".62";
    return c;
  }
}

// 沒存就離開會不見——瀏覽器層再擋一次
window.addEventListener("beforeunload", e => {
  if (DIRTY) { e.preventDefault(); e.returnValue = ""; }
});

$("#backBtn").appendChild(icon("arrowLeft", 17));
$("#modeTag").textContent = MODE === "local" ? "· 本地預覽" : "";
if (MODE === "local") $("#bnHint").textContent = "本地預覽：可以看，存檔要在正式站";
open();
})();
