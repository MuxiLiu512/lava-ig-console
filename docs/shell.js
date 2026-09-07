/* 應用外殼〔2026-09-07 Jesse：「UI 並沒有符合實際電腦螢幕的寬度，
   導致左右兩側的空間都浪費掉了」〕

   實測的浪費（1512px MacBook Pro）：
     工作台  body 880px，左右各空 316px → 42% 的螢幕是空的
     審稿台  內容欄 720px，左空 396px   → 52%
   27 吋 2560px 螢幕上分別是 66% 與 72%。

   為什麼不是直接把 max-width 拿掉：
     一行文字超過 90 個字，眼睛回到下一行開頭時會找錯行（typographic measure）。
     把 720px 的欄拉成 1500px 會更難讀，不是更好用。
     多出來的寬度要拿去「多開一欄」，讓空間承載資訊，不是承載空氣。

   結構抄 Linear／Notion／Stanley 共用的那一套 app shell：
     左欄 常駐導覽（全高、sticky）
     中欄 工作區（頁首只蓋中欄，不橫跨整個視窗）
     右欄 決策面板（Stanley 把「我做了什麼／為什麼／我沒動什麼」放這裡）

   這支只做外殼，不碰任何一頁的內容——各頁的節點是「搬進來」不是「重建」，
   所以既有的 document.getElementById 全部照舊有效。 */
(() => {
"use strict";

const PAGES = [
  { key: "board",  href: "index.html",  name: "工作台",  hint: "等你處理的都在這" },
  { key: "review", href: "review.html", name: "審稿台",  hint: "一篇一篇審完" },
  { key: "reel",   href: "reel.html",   name: "影片",    hint: "Reels 分鏡與成片" },
  { key: "brain",  href: "brain.html",  name: "規則本",  hint: "系統照什麼規則做事" },
];

const here = (location.pathname.split("/").pop() || "index.html").toLowerCase();
const CUR = (PAGES.find(p => p.href === here) || PAGES[0]).key;

const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};

function buildRail() {
  const rail = el("aside", "rail");
  rail.setAttribute("aria-label", "主導覽");

  const head = el("div", "rail-head");
  head.appendChild(el("span", "rail-mark", "LAVA"));
  rail.appendChild(head);

  const nav = el("nav");
  PAGES.forEach(p => {
    const a = el("a", p.key === CUR ? "on" : "");
    a.href = p.href;
    a.id = "rail-" + p.key;
    a.title = p.hint;
    a.appendChild(el("span", null, p.name));
    if (p.key === CUR) a.setAttribute("aria-current", "page");
    nav.appendChild(a);
  });
  rail.appendChild(nav);

  rail.appendChild(el("div", "rail-sep"));

  const foot = el("div", "rail-foot");
  const health = el("div", "rail-health");
  health.id = "railHealth";
  health.innerHTML = '<span class="dot"></span>讀取中';
  foot.appendChild(health);
  rail.appendChild(foot);
  return rail;
}

/** 把 <body> 現有的東西整批搬進 .work，不重建節點——重建會斷掉各頁抓到的參照。 */
function mount() {
  if (document.querySelector(".app")) return;
  const body = document.body;
  const moved = Array.from(body.children).filter(n => n.tagName !== "SCRIPT");

  const app = el("div", "app");
  const rail = buildRail();
  const work = el("div", "work");
  const aside = el("aside", "aside");
  aside.id = "asideSlot";

  moved.forEach(n => work.appendChild(n));
  app.appendChild(rail);
  app.appendChild(work);
  app.appendChild(aside);
  body.insertBefore(app, body.firstChild);

  // 頁首裡跟左欄重複的導覽拿掉：同一個目的地出現兩次會讓人以為是兩個東西。
  // 只在左欄真的看得到（≥1000px 直欄／窄螢幕橫向列）時才拿掉，兩種都看得到。
  // 返回鍵：隱藏而不是移除。review.js／brain.js／reel.js 都有
  // $("#backBtn").appendChild(icon(...))，直接移除會讓那三頁整個掛掉
  // （第一次改就踩到了：Cannot read properties of null）。
  const back = document.getElementById("backBtn");
  if (back) { back.hidden = true; back.setAttribute("aria-hidden", "true"); }
  work.querySelectorAll('.topbar a.btn[href$=".html"]').forEach(a => a.remove());

  // 主題切換移到左欄底部：它是設定，不是每一頁的動作。
  const foot = rail.querySelector(".rail-foot");
  if (window.LavaUI && window.LavaUI.themeToggle && foot) {
    try { foot.appendChild(window.LavaUI.themeToggle()); } catch (e) { /* 沒有就算了 */ }
  }
}

/** 各頁拿到資料後回報數字。0 或 null＝不顯示，不要印一個灰色的 0 佔位。 */
function setBadge(key, n, quiet) {
  const a = document.getElementById("rail-" + key);
  if (!a) return;
  const old = a.querySelector(".badge");
  if (old) old.remove();
  if (!n) return;
  const b = el("span", "badge" + (quiet ? " quiet" : ""), String(n));
  a.appendChild(b);
}

/** 產線健康。文字用生活語言，術語留給 tooltip〔學 Stanley 第六條〕。 */
function setHealth(text, bad, title) {
  const h = document.getElementById("railHealth");
  if (!h) return;
  h.className = "rail-health" + (bad ? " bad" : "");
  h.innerHTML = '<span class="dot"></span>' + String(text || "");
  if (title) h.title = title;
}

/** 右欄：填了才會出現。沒有內容就不佔寬度——空欄比沒有欄更糟。 */
function aside(nodes) {
  const slot = document.getElementById("asideSlot");
  const app = document.querySelector(".app");
  if (!slot || !app) return null;
  slot.innerHTML = "";
  const list = Array.isArray(nodes) ? nodes : (nodes ? [nodes] : []);
  list.forEach(n => n && slot.appendChild(n));
  app.classList.toggle("has-aside", list.length > 0);
  return slot;
}

/** 右欄是否真的在畫面上（<1360px 時不顯示，這時內容要留在中欄）。 */
const asideVisible = () => window.matchMedia("(min-width: 1360px)").matches;

// 立刻掛，不等 DOMContentLoaded。
// shell.js 是由 body 最後一個 <script> 動態載入的，所以它執行時 body 的內容
// 一定已經解析完畢——readyState 還是 "loading" 只是因為那些動態腳本本身還沒跑完。
// 等 DOMContentLoaded 會製造競速：本機預覽讀檔很快，review.js 的 loadAll() 會
// 在 mount 之前就完成並開始畫，於是它找不到外殼的節點。線上因為要走網路
// 反而每次都是 mount 先到，所以這個 bug 只在本機出現、上線後才會被發現。
if (document.body) mount();
else document.addEventListener("DOMContentLoaded", mount);

window.LavaShell = { setBadge, setHealth, aside, asideVisible, CUR, mount };
})();
