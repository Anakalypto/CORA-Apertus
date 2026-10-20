/* CORA in the languages of Switzerland. The interface text comes from a catalog that Apertus translated
   (GET /api/i18n/<lang>, built from the strings of this front end). Only text that matches the catalog is
   translated: record titles, archive metadata, names and quotes never match and stay in their original language.
   Text Apertus writes for the reader is generated in the reader's language (every API call carries ?lang=). */
"use strict";

const LANGS = { en: "EN", de: "DE", fr: "FR", it: "IT", rm: "RM" };
const LANG_NAMES = { en: "English", de: "Deutsch", fr: "Français", it: "Italiano", rm: "Rumantsch" };
const LANG = (() => {
  let saved = null;
  try { saved = localStorage.getItem("cora.lang"); } catch { /* storage blocked: use the browser language */ }
  const want = (saved || new URLSearchParams(location.search).get("lang") || navigator.language || "en").slice(0, 2).toLowerCase();
  return LANGS[want] ? want : "en";
})();
document.documentElement.lang = LANG;
const LOCALE = { en: "en-GB", de: "de-CH", fr: "fr-CH", it: "it-CH", rm: "rm-CH" }[LANG];  // dates in the reader's language

/* every API request carries the interface language, so Apertus answers in it */
function withLang(url) {
  if (LANG === "en" || !String(url).startsWith("/api/")) return url;
  return url + (String(url).includes("?") ? "&" : "?") + "lang=" + LANG;
}

const I18N = { exact: new Map(), patterns: [], ready: false };
// archive data that must stay in its original language, even if it happens to look like interface text
const KEEP = '[translate="no"], code, pre, script, style, textarea, .crumbs, table.dl td, .notice h1, .cover .ct, .json, .maplibregl-ctrl-attrib, .lang-switch, .topic-wp p';
const norm = (s) => s.replace(/\s+/g, " ").trim();
const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function compile(strings) {
  I18N.exact.clear();
  I18N.patterns = [];
  for (const [src, dst] of Object.entries(strings)) {
    if (!/\{\d+\}/.test(src) && typeof dst === "string") { I18N.exact.set(src, dst); continue; }
    const pieces = src.split(/(\{\d+\})/);
    const order = [];
    // spaces next to a placeholder are optional: a trailing {0} may render as a link (another node), leaving no space
    const rx = pieces.map((p) => { const m = p.match(/^\{(\d+)\}$/); if (m) { order.push(+m[1]); return "(.*?)"; } return reEsc(p).replace(/^ +| +$/g, "\\s*"); }).join("");
    const anchor = pieces.filter((p) => !/^\{\d+\}$/.test(p)).sort((a, b) => b.length - a.length)[0] || "";
    // a template needs real fixed text: "{0} of {1}" would match any sentence with " of " in it
    if ((src.replace(/\{\d+\}/g, "").match(/\p{L}/gu) || []).length < 3) continue;
    const glued = [...src.matchAll(/\b[a-z]*[a-rt-z]\{(\d+)\}/g)].map((g) => +g[1]);  // "file{1}": an English plural ending (same rule as i18n.py)
    I18N.patterns.push({ re: new RegExp("^" + rx + "$", "s"), order, dst, anchor, glued });
  }
  I18N.patterns.sort((a, b) => b.anchor.length - a.anchor.length);  // most specific template first
  I18N.ready = true;
}

function tr(text) {
  const key = norm(text);
  if (!key) return null;
  const hit = I18N.exact.get(key);
  if (hit !== undefined) return hit;
  for (const p of I18N.patterns) {
    if (p.anchor && !key.includes(p.anchor)) continue;
    const m = key.match(p.re);
    if (!m || m.slice(1).some((g) => g.length > 80)) continue;  // a dynamic part is a number, a name or a short label, never a paragraph
    const vals = {};
    p.order.forEach((n, i) => { const v = m[i + 1]; vals[n] = I18N.exact.get(norm(v)) ?? v; });  // "dated up to" inside a template
    // plural strings: the English ending in the glued placeholder ("" or "s") picks the singular or the plural form
    const many = p.glued.some((n) => /^(s|es|ies)$/.test(m[p.order.indexOf(n) + 1] || ""));
    const dst = typeof p.dst === "string" ? p.dst : (many ? p.dst.other : p.dst.one);
    for (const n of p.glued) vals[n] = typeof p.dst === "string" && !/^(|s|es|ies|y)$/.test(vals[n] || "") ? vals[n] : "";
    return dst.replace(/\{(\d+)\}/g, (_, n) => vals[n] ?? "");
  }
  if (key.includes(" · ")) {  // "1971-02-07 · mandatory referendum": parts joined by a middle dot
    const parts = key.split(" · "), out = parts.map((x) => tr(x) ?? x);  // each part may itself be a template
    if (out.some((x, i) => x !== parts[i])) return out.join(" · ");
  }
  return null;
}

const done = new WeakMap();  // node -> text we wrote, so our own changes are not translated again
function translateText(node) {
  const el = node.parentElement;
  if (!el || el.closest(KEEP) || (el.matches('a[href^="#/record/"]') && el.childElementCount === 0)) return;
  if (done.get(node) === node.data) return;
  const out = tr(node.data);
  if (out == null) return;
  const lead = node.data.match(/^\s*/)[0], tail = node.data.match(/\s*$/)[0];
  node.data = lead + out + tail;
  done.set(node, node.data);
}

const doneAttr = new WeakMap();  // element -> {attribute: text we wrote}
function translateAttrs(el) {
  if (el.closest(KEEP)) return;
  const mine = doneAttr.get(el) || {};
  for (const a of ["placeholder", "title", "aria-label", "alt"]) {
    const v = el.getAttribute(a);
    if (!v || mine[a] === v) continue;
    const out = tr(v);
    if (out != null) { mine[a] = out; doneAttr.set(el, mine); el.setAttribute(a, out); }
  }
}

function translateTree(root) {
  if (LANG === "en" || !I18N.ready || !root) return;
  if (root.nodeType === Node.TEXT_NODE) { translateText(root); return; }
  if (root.nodeType !== Node.ELEMENT_NODE) return;
  translateAttrs(root);
  root.querySelectorAll("[placeholder], [title], [aria-label], [alt]").forEach(translateAttrs);
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) translateText(n);
}

new MutationObserver((muts) => {
  if (LANG === "en" || !I18N.ready) return;
  for (const m of muts) {
    if (m.type === "characterData") translateText(m.target);
    else if (m.type === "attributes") translateAttrs(m.target);
    else m.addedNodes.forEach(translateTree);
  }
}).observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["placeholder", "title", "aria-label", "alt"] });

async function loadCatalog(attempt = 0) {
  if (LANG === "en") return;
  try {
    const r = await fetch(`/api/i18n/${LANG}`).then((x) => x.json());
    compile(r.strings || {});
    translateTree(document.body);
    document.title = tr(document.title) || document.title;
    // Apertus is still translating strings added since the last run: pick them up as they arrive
    if (r.pending && attempt < 20) setTimeout(() => loadCatalog(attempt + 1), 15000);
  } catch { /* offline: the page stays in English */ }
}

function languageSwitch() {
  const host = document.querySelector(".mainnav");
  if (!host || host.querySelector(".lang-switch")) return;
  // a menu of the main navigation like the others (app.js opens it), at the end of the row; each language is
  // named in its own language, so the menu is never translated (.lang-switch is in KEEP)
  const box = document.createElement("div");
  box.className = "navmenu lang-switch";
  box.innerHTML = `<button type="button" class="navmenu-btn" aria-haspopup="true" aria-expanded="false" aria-label="Language: ${LANG_NAMES[LANG]}">
      <span class="lang-globe" aria-hidden="true">🌐</span> ${LANGS[LANG]} <span class="caret" aria-hidden="true">▾</span></button>
    <div class="navmenu-list lang-list" role="menu">${Object.entries(LANGS).map(([k, v]) =>
      `<a href="#" role="menuitemradio" data-lang="${k}" lang="${k}" aria-checked="${k === LANG}" class="${k === LANG ? "on" : ""}"><b>${v}</b> ${LANG_NAMES[k]}</a>`).join("")}</div>`;
  box.querySelector(".lang-list").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-lang]");
    if (!a) return;
    e.preventDefault();
    if (a.dataset.lang === LANG) return;
    try { localStorage.setItem("cora.lang", a.dataset.lang); } catch { /* not remembered */ }
    location.reload();
  });
  host.appendChild(box);
}

document.addEventListener("DOMContentLoaded", languageSwitch);
if (document.readyState !== "loading") languageSwitch();
loadCatalog();
