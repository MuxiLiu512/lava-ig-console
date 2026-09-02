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
  const wrap = el("div"); wrap.style.display = "grid"; wrap.style.gap = "10px";
  (doc.rituals || []).forEach(r => {
    const c = el("div", "card"); const pad = el("div", "pad");
    const row = el("div", "row");
    const mid = el("div", "grow");
    mid.appendChild(el("div", null, `<b>${esc(r.name)}</b>`));
    mid.appendChild(el("div", "sub", esc(r.what)));
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
    wrap.appendChild(c);
  });
  body.appendChild(wrap);
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
