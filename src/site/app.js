/* CORA front end — Gallica-inspired browsing of Apertus-classified records. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const app = $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

const MEDIUM_ICON = { "moving image": "🎞️", "still image": "📷", text: "📜", sound: "🎙️", mixed: "🗂️" };
const TYPE_ICON = {
  "TV news report": "📺", newsreel: "🎞️", "radio broadcast": "📻", film: "🎬", "audio recording": "🎙️",
  photograph: "📷", correspondence: "✉️", report: "📑", "minutes / protocol": "🖋️", "parliamentary record": "🏛️",
  "legislation / decree": "⚖️", "administrative file": "🗃️", "map / plan": "🗺️", "press article": "📰",
  "press release / communiqué": "📣", "register / index": "📇", "finding aid / inventory": "📇", "publication / book": "📕",
  speech: "🎤", other: "📄",
};
const EVENT_LABEL = { creation: "Created", depicted: "Depicted place", publication: "Published / broadcast", update: "Updated", accession: "Entered the Federal Archives", holding: "Kept today" };
const EVENT_EMOJI = { creation: "✍️", depicted: "👁️", publication: "📡", update: "🔁", accession: "📦", holding: "🏛️" };
const PREP_LABEL = {
  transcription_normalization: "Transcription normalization",
  structure_extraction: "Structure extraction",
  schema_harmonization: "Schema harmonization",
  linked_data_entity_linking: "Linked data & entity linking",
  date_geolocation_parsing: "Date & geolocation parsing",
  anonymization_verification: "Anonymization verification",
};

/* Institution favicons (stored locally) for map markers. */
function institutionIcon(text) {
  const t = (text || "").toLowerCase();
  if (/bundesarchiv|federal archives|archives fédérales/.test(t)) return "assets/icons/bar_admin_ch.png";
  if (/\bsrf\b|schweizer fernsehen|sf drs|sfdrs|\bsf\b|radio drs|schweizer radio/.test(t)) return "assets/icons/srf_ch.ico";
  if (/\btsr\b|\brts\b|télévision suisse romande|television suisse romande|radio suisse romande/.test(t)) return "assets/icons/rts_ch.ico";
  if (/\brsi\b|radiotelevisione svizzera/.test(t)) return "assets/icons/rsi_ch.png";
  if (/nationalrat|ständerat|national council|council of states|parlament|parliament|bundesversammlung/.test(t)) return "assets/icons/parlament_ch.png";
  if (/armee|army|armeestab|militär|military|vbs|generalstab|landesverteidigung/.test(t)) return "assets/icons/vbs_admin_ch.png";
  if (/filmwochenschau|ciné-journal|newsreel/.test(t)) return "assets/icons/memobase_ch.ico";
  if (/bundesamt|federal office|bundesrat|federal council|eidgenöss|confédération/.test(t)) return "assets/icons/admin_ch.ico";
  return null;
}

function eventIcon(ev, rec, n) {
  let src = null;
  const m = rec.metadata || {};
  if (ev.event === "accession" || ev.event === "holding") src = "assets/icons/bar_admin_ch.png";
  else if (ev.event === "publication") src = institutionIcon(`${m.publisher} ${m.creator}`);
  else if (ev.event === "creation") src = institutionIcon(`${m.creator} ${m.commissioner} ${rec.archival_location?.fonds}`);
  const inner = src ? `<img src="${src}" alt="">` : EVENT_EMOJI[ev.event] || "•";
  return L.divIcon({ className: "", html: `<div class="pin ev-${ev.event}">${inner}${n ? `<b>${n}</b>` : ""}</div>`, iconSize: [30, 30], iconAnchor: [15, 15], popupAnchor: [0, -14] });
}

function baseMap(el, opts = {}) {
  const map = L.map(el, { scrollWheelZoom: false, ...opts });
  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors" });
  const swiss = L.tileLayer("https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg",
    { maxZoom: 18, attribution: "© swisstopo" });
  osm.addTo(map);
  L.control.layers({ "OpenStreetMap": osm, "swisstopo (Swiss national map)": swiss }).addTo(map);
  return map;
}

function cover(r, big) {
  const medium = r.medium || r.classification?.medium;
  const type = r.document_type || r.classification?.document_type;
  const title = r.title_normalized || r.title || r.metadata?.title_normalized || r.metadata?.title;
  const ref = r.reference_code || r.source?.reference_code;
  return `<div class="cover m-${(medium || "mixed").replace(/\s+/g, "-")}">
    <div class="ic" aria-hidden="true">${TYPE_ICON[type] || MEDIUM_ICON[medium] || "📄"}</div>
    <div class="ct">${esc(title)}</div>
    <div class="cr">${esc(ref)}</div></div>`;
}

const pv = (k) => `<span class="pv pv-${k}" title="Source of this value: ${k}">${k}</span>`;
const fmtDate = (d) => (d ? esc(String(d).replace("/", " – ")) : "—");

function setNav(name) {
  document.querySelectorAll(".mainnav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
}

/* ---------------- Home ---------------- */
async function home() {
  setNav("");
  const s = await api("/api/stats");
  const q = s.qc || {};
  const all = (await api("/api/records?size=100&sort=date")).results;
  const byType = {};
  all.forEach((r) => (byType[r.document_type] ||= []).push(r));
  const featured = [];
  for (let i = 0; featured.length < 8 && i < 8; i++) Object.values(byType).forEach((g) => g[i] && featured.length < 8 && featured.push(g[i]));
  const pop = s.population || {};
  app.innerHTML = `
    <section class="hero">
      <div>
        <h1>${s.records} sources of the Swiss Federal Archives, read by Apertus</h1>
        <p>Every record was drawn at random from the item-level documents of the <em>Archive database of the Swiss Federal Archives</em>
        (opendata.swiss). Apertus v1.5, Switzerland's open language model, wrote a résumé of each, typed it as a primary,
        secondary or tertiary source, completed its metadata, assessed the preprocessing it needs and traced its story on a map.
        Each value shows where it came from: <span class="pv pv-record">record</span><span class="pv pv-derived">derived</span><span class="pv pv-apertus">apertus</span><span class="pv pv-gazetteer">gazetteer</span><span class="pv pv-wikidata">wikidata</span></p>
        <p class="small muted">A stratified random sample (seed 42) of 100 item-level documents from ${(pop.all_records || 263123).toLocaleString("en")}
        (40 audiovisual · 30 still images · 30 other), plus 200 textual dossiers chosen as secondary (60 press, 40 studies) and tertiary (100 registers, indexes) sources,
        85 % of them from before 1940.</p>
      </div>
      <div class="stats">
        <div class="stat"><b>${s.records}</b><span>documents classified</span></div>
        <div class="stat"><b>${q.processed_ok_pct ?? "–"}%</b><span>processed without error</span></div>
        <div class="stat"><b>${q.entity_grounding_strict_pct ?? "–"}%</b><span>named entities literally in the source (${q.entity_grounding_pct ?? "–"}% incl. translations)</span></div>
        <div class="stat"><b>${q.structural_error_pct ?? "–"}%</b><span>structural errors</span></div>
      </div>
    </section>
    <h2>Browse by document type</h2>
    <div class="tiles">${s.facets.document_type.map(([k, n]) => `<a class="tile" href="#/search?document_type=${encodeURIComponent(k)}"><b>${TYPE_ICON[k] || "📄"} ${esc(k)}</b><span>${n} document${n > 1 ? "s" : ""}</span></a>`).join("")}</div>
    <h2>By fonds</h2>
    <div class="tiles">${s.facets.fonds.slice(0, 8).map(([k, n]) => `<a class="tile" href="#/search?fonds=${encodeURIComponent(k)}"><b>${esc(k)}</b><span>${n} document${n > 1 ? "s" : ""}</span></a>`).join("")}</div>
    <h2>A few documents</h2>
    <div class="grid-cards">${featured.map((r) => `<a class="card" href="#/record/${r.id}">${cover(r)}<div class="t">${esc(r.title_en || r.title)}</div><div class="small muted">${fmtDate(r.date)}</div></a>`).join("")}</div>`;
}

/* ---------------- Search ---------------- */
const FACET_TITLES = { document_type: "Document type", source_level: "Source level", medium: "Medium", decade: "Period", fonds: "Fonds", language: "Language", preprocessing: "Preprocessing needed", qc: "Quality check", sample: "Sample group" };

async function search(params) {
  setNav("search");
  $("#q").value = params.get("q") || "";
  params.set("size", "20");
  const res = await api("/api/records?" + params.toString());
  const page = +(params.get("page") || 1);
  const link = (k, v) => { const p = new URLSearchParams(params); p.delete("page"); p.delete("size"); if (v === null || p.get(k) === v) p.delete(k); else p.set(k, v); return "#/search?" + p.toString(); };
  const active = [...params.entries()].filter(([k]) => FACET_TITLES[k]);
  const facetHtml = Object.entries(res.facets).map(([k, vals]) => !vals.length ? "" : `
      <h3>${FACET_TITLES[k]}</h3><ul>${vals.slice(0, 12).map(([v, n]) => `<li><a class="${params.get(k) === String(v) ? "on" : ""}" href="${link(k, String(v))}"><span>${esc(k === "preprocessing" ? PREP_LABEL[v] || v : v)}</span><span>${n}</span></a></li>`).join("")}</ul>`).join("");
  const pages = Math.ceil(res.total / 20);
  app.innerHTML = `
    <div class="layout">
      <aside class="facets"><h2 style="margin-top:0">Refine</h2>${facetHtml}</aside>
      <section>
        <div class="resbar">
          <div><b>${res.total}</b> result${res.total === 1 ? "" : "s"}${params.get("q") ? ` for “${esc(params.get("q"))}”` : ""}</div>
          <label class="small">Sort <select id="sort">${["relevance", "date", "title"].map((s) => `<option ${params.get("sort") === s ? "selected" : ""}>${s}</option>`).join("")}</select></label>
        </div>
        ${active.length ? `<div class="chips">${active.map(([k, v]) => `<a class="chip x" href="${link(k, null)}">${FACET_TITLES[k]}: ${esc(v)} ✕</a>`).join("")}</div>` : ""}
        ${res.results.map((r) => `
          <article class="result">
            <a href="#/record/${r.id}">${cover(r)}</a>
            <div>
              <h3><a href="#/record/${r.id}">${esc(r.title_normalized || r.title)}</a></h3>
              <div class="badges"><span class="badge">${esc(r.document_type)}</span><span class="badge lvl-${r.source_level}">${esc(r.source_level)} source</span>${r.qc_ok ? "" : `<span class="badge qc-bad">QC issue</span>`}${r.n_places ? `<span class="badge">📍 ${r.n_places}</span>` : ""}</div>
              <div class="meta-line"><b>Date</b> ${fmtDate(r.date)} · <b>Creator</b> ${esc(r.creator || "—")} · <b>Fonds</b> ${esc(r.fonds || "—")}</div>
              <div class="meta-line muted small">${esc(r.reference_code)}</div>
              ${r.resume ? `<p class="resume">${esc(r.resume)}</p>` : ""}
            </div>
          </article>`).join("") || `<p class="muted">No documents match.</p>`}
        ${pages > 1 ? `<div class="pager">${Array.from({ length: pages }, (_, i) => i + 1).map((p) => p === page ? `<span class="cur">${p}</span>` : `<a href="${(() => { const q = new URLSearchParams(params); q.delete("size"); q.set("page", p); return "#/search?" + q; })()}">${p}</a>`).join("")}</div>` : ""}
      </section>
    </div>`;
  $("#sort").onchange = (e) => { const p = new URLSearchParams(params); p.delete("size"); p.set("sort", e.target.value); location.hash = "#/search?" + p; };
}

/* ---------------- Record (notice) ---------------- */
function storyBlock(r, mapId) {
  const ev = r.story || [];
  return `
    <div class="legend">${Object.keys(EVENT_LABEL).map((k) => `<span><i style="background:var(--c)" class="ev-${k}"></i>${EVENT_LABEL[k]}</span>`).join("")}</div>
    <div id="${mapId}" class="map"></div>
    <ol class="timeline">${ev.map((e) => `<li class="ev-${e.event}"><span class="d">${e.event === "holding" ? "Today" : fmtDate(e.date)}</span> · <b>${EVENT_LABEL[e.event] || e.event}</b>${e.place ? ` — ${esc(e.place)}` : ""}${e.lat == null && e.event !== "holding" ? ` <span class="small muted">(no coordinates)</span>` : ""}
      <div class="small muted">${esc(e.description || "")} ${pv(e.source === "record" ? "derived" : "apertus")}</div></li>`).join("")}</ol>`;
}

function drawStory(r, mapId) {
  const el = document.getElementById(mapId);
  if (!el) return;
  const map = baseMap(el);
  const pts = [];
  let n = 0;
  const seen = new Map();
  (r.story || []).forEach((e) => {
    if (e.lat == null) return;
    n += 1;
    const key = `${e.lat.toFixed(4)},${e.lon.toFixed(4)}`;
    const k = seen.get(key) || 0; seen.set(key, k + 1);
    const ll = [e.lat + k * 0.0009, e.lon + k * 0.0012];  // nudge stacked points apart
    L.marker(ll, { icon: eventIcon(e, r, n) }).addTo(map)
      .bindPopup(`<b>${n}. ${EVENT_LABEL[e.event] || e.event}</b><br>${fmtDate(e.date)}${e.place ? " · " + esc(e.place) : ""}<br><span class="small">${esc(e.description || "")}</span>`);
    pts.push(ll);
  });
  if (pts.length > 1) {
    L.polyline(pts, { color: "#b5121b", weight: 2.5, dashArray: "6 6", opacity: 0.85 }).addTo(map);
  }
  if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.35), { maxZoom: 11 });
  else map.setView([46.8, 8.2], 7);
  setTimeout(() => map.invalidateSize(), 50);
}

function noticeTable(r) {
  const m = r.metadata, c = r.classification, loc = r.archival_location, o = r.source.original;
  const ents = r.entities;
  const row = (label, value, src, orig) => value ? `<tr><th>${label}</th><td>${value}${src ? pv(src) : ""}${orig ? `<span class="orig">original: ${esc(orig)}</span>` : ""}</td></tr>` : "";
  const persons = ents.persons.map((p) => `${esc(p.display_name || p.name)}${p.role ? ` <span class="muted small">(${esc(p.role)})</span>` : ""}${p.wikidata ? ` <a href="${p.wikidata.url}" target="_blank" rel="noopener" title="${esc(p.wikidata.description || "")}">${p.wikidata.qid}</a>${pv("wikidata")}` : ""}`).join("<br>");
  const orgs = ents.organizations.map((p) => `${esc(p.name)}${p.role ? ` <span class="muted small">(${esc(p.role)})</span>` : ""}${p.wikidata ? ` <a href="${p.wikidata.url}" target="_blank" rel="noopener">${p.wikidata.qid}</a>${pv("wikidata")}` : ""}`).join("<br>");
  const places = ents.places.map((p) => `${esc(p.name)} <span class="muted small">(${esc(p.role)})</span>${p.lat != null ? ` <a href="${p.gazetteer}" target="_blank" rel="noopener">${p.lat.toFixed(3)}, ${p.lon.toFixed(3)}</a>${pv("gazetteer")}` : ` <span class="small muted">not located</span>`}`).join("<br>");
  return `<table class="dl">
    ${row("Title", esc(r.metadata.title), "record")}
    ${row("Normalized title", esc(m.title_normalized), "apertus")}
    ${row("Title (English)", esc(m.title_en), "apertus")}
    ${row("Document type", esc(c.document_type), "apertus")}
    ${row("Medium", esc(c.medium), "apertus")}
    ${row("Source level", `<b>${esc(c.source_level)}</b> — ${esc(c.source_level_rationale || "")}`, "apertus")}
    ${row("Creator", esc(m.creator), "apertus", o.author)}
    ${row("Publisher", esc(m.publisher), "apertus", o.publisher)}
    ${row("Commissioner", esc(m.commissioner), "apertus")}
    ${row("Date of content", fmtDate(m.content_date), "derived", o.date?.expressed)}
    ${row("Date created", fmtDate(m.date_created), "apertus")}
    ${row("Date published", fmtDate(m.date_published), "apertus")}
    ${row("Date updated", fmtDate(m.date_updated), "apertus")}
    ${row("Date archived", fmtDate(m.date_archived) + (m.date_archived ? "" : ""), "derived", (loc.accession_numbers || []).join(", "))}
    ${row("Languages", esc((m.languages || []).join(", ")), "apertus")}
    ${row("Subjects", esc((m.subjects || []).join(" · ")), "apertus")}
    ${row("Persons", persons, "apertus")}
    ${row("Organizations", orgs, "apertus")}
    ${row("Places", places, "apertus")}
    ${row("Holder", esc(loc.holder), "derived")}
    ${row("Fonds", esc(`${loc.fonds || ""} [${loc.fonds_reference || ""}]`), "record")}
    ${row("Location in the archive", esc((loc.path || []).join(" › ")), "record")}
    ${row("Reference code", `<code>${esc(loc.reference_code)}</code>`, "record")}
    ${row("Physical description", esc([o.form, o.format].filter(Boolean).join(" — ")), "record")}
  </table>`;
}

function prepBlock(r) {
  const pre = r.preprocessing || {}, pd = r.personal_data || {};
  return `<div class="prep">${Object.entries(PREP_LABEL).map(([k, label]) => {
    const p = pre[k] || {};
    return `<div class="p ${p.needed ? "on" : ""}"><h4>${label}<span class="st">${p.needed ? `NEEDED · ${esc(p.priority)}` : "OK"}</span></h4>
      <p>${esc(p.reason || "No evidence in the record.")}</p></div>`;
  }).join("")}</div>
  <h3>Personal data ${pv("apertus")}</h3>
  <table class="dl">
    <tr><th>Names natural persons</th><td>${pd.contains_personal_data ? "yes" : "no"}</td></tr>
    <tr><th>Private individuals</th><td>${pd.private_individuals ? "yes" : "no"}</td></tr>
    <tr><th>Sensitive categories</th><td>${pd.sensitive_categories ? "yes" : "no"}</td></tr>
    <tr><th>Sensitivity</th><td>${esc(pd.sensitivity)}</td></tr>
    <tr><th>Note</th><td>${esc(pd.note || "—")}</td></tr>
  </table>
  <h3>Audit checks ${pv("apertus")} + rule detectors</h3>
  <table class="t"><tr><th>Check</th><th>Result</th><th>Apertus</th><th>Rule</th><th>Evidence</th></tr>
  ${Object.entries(r.audit_checks || {}).map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td>${v.answer ? "<b>yes</b>" : "no"}</td><td>${v.apertus ? "yes" : "no"}</td><td>${v.rule == null ? "–" : v.rule ? "yes" : "no"}</td><td class="small">${esc(v.evidence || "")}</td></tr>`).join("")}</table>`;
}

function qcBlock(r) {
  const q = r.qc || {};
  const list = (xs) => (xs && xs.length ? `<ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="muted">none</p>`);
  return `<div class="callout">${q.ok ? "✅ Passed the automatic checks (structure, dates)." : "⚠️ Did not pass every automatic check."}</div>
    <h3>Structural errors</h3>${list(q.structural_errors)}
    <h3>Critical issues</h3>${list(q.critical)}
    <h3>Warnings</h3>${list(q.warnings)}
    <h3>Entities not found in the source metadata (possible hallucinations)</h3>${list(q.ungrounded)}
    <p class="small muted">Model ${esc(r.processing.model)} · confidence ${r.processing.confidence ?? "–"} · ${r.processing.tokens} tokens · pipeline ${esc(r.processing.pipeline)}, prompts ${esc(JSON.stringify(r.processing.prompts))}</p>`;
}

function trustCard(r) {
  const t = r.trust_card;
  if (!t) return `<p class="muted">No trust card for this record.</p>`;
  const edits = r.edits || [];
  const conf = r.processing?.confidence;
  const ev = t.evidence.map((e) => `<tr id="ref-${e.ref}"><th><span class="fn">${e.ref}</span> ${esc(e.label)}</th><td style="white-space:pre-wrap">${esc(e.value)}</td></tr>`).join("");
  const ctx = t.context.length ? t.context.map((c) => `<li id="ref-${c.ref}"><span class="fn">${c.ref}</span> <b>${esc(c.name)}</b> — ${esc(c.description || "")}
      ${c.wikidata ? ` · <a href="${c.wikidata}" target="_blank" rel="noopener">Wikidata</a>` : ""}${c.wikipedia ? ` · <a href="${c.wikipedia}" target="_blank" rel="noopener">Wikipedia</a>` : ""}${c.hls ? ` · <a href="${c.hls}" target="_blank" rel="noopener">HLS</a>` : ""}${c.osm ? ` · <a href="${c.osm}" target="_blank" rel="noopener">OpenStreetMap</a>` : ""}
      <span class="tier">${esc(c.tier)}</span></li>`).join("") : `<li class="muted">No linked reference works.</li>`;
  const im = (t.imagination?.sentences || []).map((x) => `<span class="${x.inferred ? "inferred" : x.weakly_supported ? "weak" : ""}">${esc(x.text)}${x.refs.map((f) => `<a class="fnref" href="#ref-${f}" onclick="document.getElementById('ref-${f}')?.scrollIntoView({behavior:'smooth',block:'center'});return false;">${f}</a>`).join("")}${x.inferred ? ` <span class="badge qc-bad">inferred</span>` : x.weakly_supported ? ` <span class="badge" title="Few of its words occur in the cited items (support ${x.support})">weakly supported</span>` : ""}</span>`).join(" ");
  return `<div class="badges trust-badges">
      <span class="badge lvl-${r.classification.source_level}">${esc(r.classification.source_level)} source</span>
      <span class="badge">confidence ${conf != null ? conf : "–"}</span>
      <span class="badge" title="${esc(edits.map((e) => `${e.field}: ${e.actor} — ${e.reason}`).join(" | "))}">${edits.length} logged edit${edits.length === 1 ? "" : "s"}</span>
    </div>
    <section class="band band-evidence"><h3>Evidence <small>the record itself · Swiss Federal Archives</small></h3>
      <table class="dl">${ev}</table>
      <p class="small"><a href="${r.source.portal_url}" target="_blank" rel="noopener">Open in the archive's online search ↗</a></p></section>
    <section class="band band-context"><h3>Context <small>reference works · secondary / tertiary</small></h3><ul class="ctx">${ctx}</ul></section>
    <section class="band band-imagination"><h3>Imagination <small>generated by Apertus · every sentence footnoted</small></h3>
      <p class="narr">${im || '<span class="muted">No narrative.</span>'}</p>
      <p class="small muted">Footnotes E# point to evidence, C# to context. Sentences without a footnote are marked inferred; “weakly supported” means few of the sentence's words occur in the items it cites (an automatic check, weaker across languages).</p></section>
    ${edits.length ? `<details class="small"><summary>Edit log (${edits.length})</summary><table class="t"><tr><th>Field</th><th>Original</th><th>New</th><th>By</th><th>Why</th></tr>${edits.map((e) => `<tr><td>${esc(e.field)}</td><td>${esc(JSON.stringify(e.original))}</td><td>${esc(JSON.stringify(e.new))}</td><td>${esc(e.actor)}</td><td>${esc(e.reason)}</td></tr>`).join("")}</table></details>` : ""}`;
}

async function recordPage(id, tab) {
  setNav("search");
  const r = await api("/api/records/" + id);
  const loc = r.archival_location;
  const tabs = { trust: "Trust card", notice: "Notice", story: "Story map", prep: "Preprocessing & privacy", original: "Original record", quality: "Quality check", json: "JSON" };
  tab = tabs[tab] ? tab : "trust";
  app.innerHTML = `
    <div class="crumbs">${["Swiss Federal Archives", ...(loc.path || [])].map((p) => `<span>${esc(p)}</span>`).join("")}</div>
    <div class="notice">
      <aside>
        ${cover(r, true)}
        <div>
          <div class="side-box"><h4>Reference</h4><div><code>${esc(r.source.reference_code)}</code><br><span class="small muted">ID ${esc(r.id)}</span></div></div>
          <div class="side-box"><h4>Links</h4><div>
            <a href="${r.source.portal_url}" target="_blank" rel="noopener">Swiss Federal Archives online search ↗</a>
            <a href="${r.source.uri}" target="_blank" rel="noopener">Linked-data URI ↗</a>
            <a href="/api/records/${r.id}" target="_blank">This record as JSON</a></div></div>
          <div class="navpn">${r._nav.prev ? `<a href="#/record/${r._nav.prev}">‹ Previous</a>` : "<span></span>"}${r._nav.next ? `<a href="#/record/${r._nav.next}">Next ›</a>` : ""}</div>
        </div>
      </aside>
      <section>
        <div class="badges"><span class="badge">${esc(r.classification.document_type)}</span><span class="badge lvl-${r.classification.source_level}">${esc(r.classification.source_level)} source</span><span class="badge">${esc(r.classification.medium)}</span>${r.qc.ok ? "" : `<span class="badge qc-bad">QC issue</span>`}</div>
        <h1>${esc(r.metadata.title_normalized || r.metadata.title)}</h1>
        <div class="muted">${esc(r.metadata.title_en || "")}</div>
        ${r.classification.resume ? `<div class="resume-box">${esc(r.classification.resume)} ${pv("apertus")}
          <div><button class="more-btn" id="morebtn">See more ▾</button></div><div id="more"></div></div>` : `<p class="muted small">Résumé disabled in config.</p>`}
        ${r.classification.source_level !== "primary" ? `<div id="topic"></div>` : ""}
        <div class="tabs">${Object.entries(tabs).map(([k, v]) => `<button data-tab="${k}" class="${k === tab ? "on" : ""}">${v}</button>`).join("")}</div>
        <div class="tabpane" id="pane"></div>
      </section>
    </div>`;
  const panes = {
    trust: () => trustCard(r),
    notice: () => noticeTable(r),
    story: () => storyBlock(r, "storymap"),
    prep: () => prepBlock(r),
    original: () => `<table class="dl">${Object.entries(r.source.original).map(([k, v]) => `<tr><th>${esc(k)}</th><td style="white-space:pre-wrap">${esc(typeof v === "string" ? v : JSON.stringify(v, null, 1))}</td></tr>`).join("")}</table>
      <p class="small muted">Only fields of the original archive database are used (no LINDAS additions).</p>`,
    quality: () => qcBlock(r),
    json: () => `<pre class="json">${esc(JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k]) => !k.startsWith("_"))), null, 2))}</pre>`,
  };
  const show = (k) => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === k));
    $("#pane").innerHTML = panes[k]();
    if (k === "story") drawStory(r, "storymap");
    history.replaceState(null, "", `#/record/${id}/${k}`);
  };
  document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => show(b.dataset.tab)));
  const mb = $("#morebtn");
  if (mb) mb.onclick = async () => {
    const box = $("#more");
    if (box.dataset.loaded) { box.hidden = !box.hidden; mb.textContent = box.hidden ? "See more ▾" : "See less ▴"; return; }
    mb.disabled = true;
    box.innerHTML = `<p class="small muted"><span class="spinner"></span> Apertus is reading the record, related records, Wikipedia and Wikidata…</p>`;
    try {
      const m = await api(`/api/records/${id}/more`);
      const num = {}; m.sources.forEach((s, i) => (num[s.ref] = i + 1));
      const cite = (refs) => refs.length ? `<sup class="fns">[${[...new Set(refs)].sort((x, y) => num[x] - num[y]).map((f) => `<a href="#more-src-${f}" title="${esc(f)}" onclick="document.getElementById('more-src-${f}')?.scrollIntoView({behavior:'smooth',block:'center'});return false;">${num[f]}</a>`).join(",")}]</sup>` : "";
      box.innerHTML = `<div class="more">${m.paragraphs.map((p) => `<p>${p.map((s) => `<span class="${s.inferred ? "inferred" : ""}">${esc(s.text)}${cite(s.sources)}${s.inferred ? ` <span class="badge qc-bad">inferred</span>` : ""}</span>`).join(" ")}</p>`).join("")}
        <ol class="more-src small">${m.sources.map((s) => `<li id="more-src-${s.ref}"><b>${{ E: "This record", R: "Archive record", W: "Wikipedia", D: "Wikidata / gazetteer" }[s.kind]}</b> · ${esc(s.label)}
          ${s.url ? ` · <a href="${s.url}" ${s.url.startsWith("#") ? "" : 'target="_blank" rel="noopener"'}>${s.url.startsWith("#") ? "open" : "source ↗"}</a>` : ""}${s.portal_url ? ` · <a href="${s.portal_url}" target="_blank" rel="noopener">archive portal ↗</a>` : ""}
          <span class="tier">${esc(s.tier)}</span></li>`).join("")}</ol>
        <p class="small muted">Generated by Apertus (${esc(m.model || "")}) from ${m.offered.E} record fields, ${m.offered.R} related records, ${m.offered.W} Wikipedia summaries and ${m.offered.D} Wikidata/gazetteer facts.
        ${m.inferred_sentences ? `${m.inferred_sentences} sentence(s) cite no source and are marked inferred.` : "Every sentence cites a source."} Wikipedia text: CC BY-SA.</p></div>`;
      box.dataset.loaded = "1";
      mb.textContent = "See less ▴";
    } catch (err) {
      box.innerHTML = `<p class="small">Could not generate: ${esc(err.message)}</p>`;
    } finally { mb.disabled = false; }
  };
  show(tab);
  if ($("#topic")) topicPanel(r);
}

/* Secondary / tertiary records: the subject they report on, with a Wikipedia article, primary sources and news. */
async function topicPanel(r) {
  const box = $("#topic");
  box.innerHTML = `<section class="band band-context topic"><p class="small muted"><span class="spinner"></span> Apertus is identifying the subject of this ${esc(r.classification.source_level)} source and checking Wikipedia, the archive and the news…</p></section>`;
  let t;
  try { t = await api(`/api/records/${r.id}/topic`); } catch (err) { box.innerHTML = `<p class="small muted">Subject lookup failed: ${esc(err.message)}</p>`; return; }
  if (!$("#topic") || !t.identifiable) { box.innerHTML = t.identifiable ? "" : `<p class="small muted">Apertus found no identifiable subject to read further on.</p>`; return; }
  const wp = t.wikipedia;
  const primary = [...t.primary_in_dataset.map((d) => `<li><a href="#/record/${d.id}">${esc(d.title)}</a> <span class="muted">${fmtDate(d.date)}</span> <span class="tier">in this dataset</span></li>`),
    ...t.primary.map((d) => `<li>${esc(d.title)} <span class="muted">${esc(d.date || "")}</span>${d.reference_code ? ` · <code>${esc(d.reference_code)}</code>` : ""} · <a href="${d.portal_url}" target="_blank" rel="noopener">archive portal ↗</a></li>`)];
  box.innerHTML = `<section class="band band-context topic">
    <h3>About the subject <small>selected by Apertus · Wikipedia CC BY-SA</small></h3>
    <div class="topic-head"><span class="small muted">Apertus reads this record as being about</span> <b>${esc(t.subject)}</b></div>
    ${wp ? `<div class="topic-wp">${wp.thumbnail ? `<img src="${esc(wp.thumbnail)}" alt="" loading="lazy">` : ""}<div>
        <b>${esc(wp.title)}</b>${wp.description ? ` <span class="muted small">· ${esc(wp.description)}</span>` : ""}
        <p>${esc(wp.extract || "")}</p><a href="${esc(wp.url)}" target="_blank" rel="noopener">Read the Wikipedia article ↗</a></div></div>`
      : `<p class="small muted">No Wikipedia article matched this subject.</p>`}
    ${t.note ? `<p class="small muted">${esc(t.note)} ${pv("apertus")}</p>` : ""}
    <button class="more-btn" id="topicbtn">See more about it ▾</button>
    <div id="topicmore" hidden>
      <h4>Primary sources about it</h4>
      ${primary.length ? `<ul class="topic-list">${primary.join("")}</ul>` : `<p class="small muted">Apertus kept no primary source among the ${t.offered?.primary ?? 0} archive dossiers found for this subject.</p>`}
      <p class="small muted">Dossiers of the Federal Archives whose original title contains ${(t.plan.archive_stems || []).map((s) => `“${esc(s)}”`).join(", ")}; Apertus kept those produced by the people and offices involved (no media reports).
      Search further: ${Object.entries(t.search_links || {}).map(([k, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(k)} ↗</a>`).join(" · ")}</p>
      ${t.contemporary ? `<h4>In the news</h4>
        ${t.news.length ? `<ul class="topic-list">${t.news.map((n) => `<li><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a> <span class="muted small">· ${esc(n.source || "")} · ${esc((n.date || "").slice(0, 16))}</span></li>`).join("")}</ul>`
          : `<p class="small muted">No current article kept by Apertus.</p>`}
        <p class="small muted">Apertus judged the subject still debated today; articles from a news search (“${esc(t.plan.news_query || t.subject)}”), filtered by Apertus for relevance.</p>` : ""}
    </div></section>`;
  const b = $("#topicbtn"), m = $("#topicmore");
  b.onclick = () => { m.hidden = !m.hidden; b.textContent = m.hidden ? "See more about it ▾" : "See less ▴"; };
}

/* ---------------- Overview map with time slider ---------------- */
async function mapPage() {
  setNav("map");
  const [{ points, archive }, zr] = await Promise.all([api("/api/map"), fetch("assets/zeitreihen_years.json").then((r) => r.json())]);
  const years = points.map((p) => p.year).filter(Boolean);
  const minY = Math.min(...years), maxY = Math.max(...years);
  app.innerHTML = `<h1>Where the documents come from</h1>
    <p class="muted">Every place Apertus identified as where a document was made, depicted or published, located with the OpenStreetMap gazetteer.
    Move the slider: documents appear by date, and inside Switzerland the base map becomes the swisstopo national map of that time.</p>
    <div class="slider-bar">
      <button id="play" title="Play">▶</button>
      <input type="range" id="year" min="${minY}" max="${maxY}" value="${maxY}" step="1">
      <b id="yearlab">${maxY}</b>
      <label class="small"><input type="checkbox" id="cumul" checked> show all documents up to this year</label>
    </div>
    <div class="small basemap-lab" id="baselab"></div>
    <div class="legend">${["creation", "depicted", "publication", "holding"].map((k) => `<span><i style="background:var(--c)" class="ev-${k}"></i>${EVENT_LABEL[k]}</span>`).join("")}</div>
    <div id="bigmap" class="map big"></div>
    <p class="small muted" id="countlab"></p>`;
  const map = L.map($("#bigmap"), { scrollWheelZoom: false });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors", opacity: 0.55 }).addTo(map);
  let hist = null;
  const histTile = (y) => L.tileLayer(`https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.zeitreihen/default/${y}1231/3857/{z}/{x}/{y2}.png`.replace("{y2}", "{y}"),
    { maxZoom: 16, attribution: `© swisstopo, Journey through time ${y}`, bounds: [[45.7, 5.8], [47.9, 10.6]] });
  const nearest = (y) => {
    const before = zr.years.filter((v) => v <= y);
    return before.length ? before[before.length - 1] : zr.years[0];
  };
  const bar = [archive.lat, archive.lon];
  L.marker(bar, { icon: eventIcon({ event: "holding" }, {}, 0), zIndexOffset: 1000 }).addTo(map).bindPopup(`<b>${esc(archive.name)}</b><br>${esc(archive.place)}`);
  const layer = L.layerGroup().addTo(map);
  const all = points.map((p) => {
    const ll = [p.lat, p.lon];
    const g = L.layerGroup([
      L.polyline([ll, bar], { color: "#b5121b", weight: 1, opacity: 0.3 }),
      L.circleMarker(ll, { radius: 6, weight: 2, color: "#fff", fillOpacity: 0.9, fillColor: { creation: "#8a1c7c", depicted: "#1d5fa6", publication: "#a05a00" }[p.event] || "#444" })
        .bindPopup(`<a href="#/record/${p.id}"><b>${esc(p.title)}</b></a><br>${EVENT_LABEL[p.event]} · ${esc(p.place || "")} · ${fmtDate(p.date)}`),
    ]);
    return { p, g };
  });
  map.setView([46.8, 8.2], 8);  // Switzerland, where the historical base maps exist; zoom out for the rest of the world
  let shownBase = null;
  const update = () => {
    const y = +$("#year").value, cum = $("#cumul").checked;
    $("#yearlab").textContent = y;
    layer.clearLayers();
    const vis = all.filter(({ p }) => p.year && (cum ? p.year <= y : Math.abs(p.year - y) <= 5));
    vis.forEach(({ g }) => layer.addLayer(g));
    const n = nearest(y);
    if (n !== shownBase) {
      if (hist) map.removeLayer(hist);
      hist = histTile(n).addTo(map);
      shownBase = n;
    }
    const note = y < zr.years[0] ? `earliest available (${zr.years[0]}); no national map exists for ${y}` : n === y ? `the map of ${n}` : `the nearest earlier map, ${n}`;
    $("#baselab").innerHTML = `Base map in Switzerland: <b>swisstopo “Journey through time”</b> (ch.swisstopo.zeitreihen), ${note}. Outside Switzerland: today's OpenStreetMap.`;
    $("#countlab").textContent = `${vis.length} located events from ${new Set(vis.map(({ p }) => p.id)).size} documents ${cum ? `dated up to ${y}` : `dated ${y - 5}–${y + 5}`} (${points.filter((p) => !p.year).length} undated not shown).`;
  };
  $("#year").oninput = update;
  $("#cumul").onchange = update;
  let timer = null;
  $("#play").onclick = () => {
    if (timer) { clearInterval(timer); timer = null; $("#play").textContent = "▶"; return; }
    if (+$("#year").value >= maxY) $("#year").value = minY;
    $("#play").textContent = "❚❚";
    timer = setInterval(() => {
      const v = +$("#year").value + 2;
      if (v > maxY) { clearInterval(timer); timer = null; $("#play").textContent = "▶"; return; }
      $("#year").value = v; update();
    }, 350);
  };
  update();
}

/* ---------------- Quality ---------------- */
async function qualityPage() {
  setNav("quality");
  const qc = await api("/api/qc");
  const s = qc.summary || {};
  const kpi = (v, label, good = 90, mid = 70, suffix = "%") => {
    const n = parseFloat(v);
    const cls = isNaN(n) ? "" : n >= good ? "good" : n >= mid ? "mid" : "low";
    return `<div class="kpi ${cls}"><b>${v ?? "–"}${v != null && suffix ? suffix : ""}</b><span>${label}</span></div>`;
  };
  const inv = (v) => (v == null ? null : +(100 - v).toFixed(1));
  const bars = (pairs, total, red) => `<div class="bars">${pairs.map(([k, n]) => `<span>${esc(k)}</span><div class="bar ${red ? "red" : ""}"><i style="width:${(100 * n) / total}%"></i></div><span>${n}</span>`).join("")}</div>`;
  const cons = s.consistency_70b_vs_8b || {};
  const mr = s.manual_review;
  const mr1 = s.manual_review_v1;
  const a1 = s.automatic_v1;
  const verdict = (m, k) => (m.verdicts.find(([v]) => v === k) || [k, 0])[1];
  const flagRows = Object.entries(s.preprocessing_flag_rates_pct || {});
  app.innerHTML = `
    <h1>Quality check of the Apertus output</h1>
    <p class="muted">Automatic checks over all ${s.records} records, a cross-check between Apertus 70B and Apertus 8B, and a manual review.
    Challenge targets: ≥ 80% of documents processed correctly, &lt; 5% structural errors.</p>
    <div class="kpis">
      ${kpi(s.processed_ok_pct, "processed correctly (no structural or critical error)", 80, 60)}
      ${kpi(s.structural_error_pct, "structural errors (target < 5%)", -1, -1)}
      ${kpi(s.resume_max_3_sentences_pct, "résumés within 3 sentences")}
      ${kpi(s.entity_grounding_strict_pct, `named entities literally in the source metadata (${s.entities} entities)`)}
      ${kpi(s.entity_grounding_pct, "named entities in the source, counting translations (Nationalrat → National Council)")}
      ${kpi(s.date_created_in_range_pct, "creation dates inside the record's date range")}
      ${kpi(s.date_archived_correct_pct, "archival dates right before the rule override", 90, 50)}
      ${kpi(s.places_resolved_pct, `places located by the gazetteer (${s.places})`)}
      ${kpi(s.model_coord_within_25km_pct, `Apertus' own coordinates within 25 km (median error ${s.model_coord_error_km_median} km)`)}
    </div>
    <div class="two">
      <div>
        <h2>Agreement with explicit record fields</h2>
        <table class="t"><tr><th>Check</th><th>Agreement</th></tr>
          <tr><td>Creator vs record “author”</td><td>${s.creator_agreement}</td></tr>
          <tr><td>Publisher vs record “publisher”</td><td>${s.publisher_agreement}</td></tr>
          <tr><td>Source level vs rule (type → level)</td><td>${s.source_level_rule_agreement}</td></tr></table>
        <h2>Apertus 70B vs Apertus 8B</h2>
        <table class="t"><tr><th>Field</th><th>Agreement</th><th>Cohen's κ</th></tr>
          ${Object.entries(cons).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.agreement != null ? (100 * v.agreement).toFixed(0) + "%" : "–"}</td><td>${v.kappa ?? "–"}</td></tr>`).join("")}</table>
      </div>
      <div>
        <h2>What Apertus produced</h2>
        <h3>Document types</h3>${bars(s.distribution?.document_type || [], s.records)}
        <h3>Source level</h3>${bars(s.distribution?.source_level || [], s.records)}
      </div>
    </div>
    ${s.source_level_vs_evidence ? `<h2>Source level: Apertus vs archival evidence (${s.source_level_vs_evidence.n} added sources)</h2>
      <p class="small muted">The 200 added sources were chosen by archival evidence as secondary (press, studies) or tertiary (registers, indexes). Agreement of Apertus with that label: <b>${s.source_level_vs_evidence.agreement_pct} %</b>${s.source_level_vs_evidence.pass1_agreement_pct != null ? ` with the dedicated source-level pass (pass 1 alone: ${s.source_level_vs_evidence.pass1_agreement_pct} %)` : ""}.
      ${s.source_level_original_sample ? `On the original 100 records the pass gives ${esc(Object.entries(s.source_level_original_sample).map(([k, v]) => `${k} ${v}`).join(", "))}.` : ""}</p>
      <table class="t"><tr><th>Group</th><th>n</th><th>Agreement</th><th>Apertus said</th></tr>
      ${Object.entries(s.source_level_vs_evidence.by_stratum).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.n}</td><td>${v.agreement_pct} %</td><td>${esc(Object.entries(v.predicted).map(([a, b]) => `${a} ${b}`).join(", "))}</td></tr>`).join("")}</table>
      ${s.source_level_adjudication ? `<p class="small">Manual adjudication of ${s.source_level_adjudication.reviewed} disagreements: Apertus right ${s.source_level_adjudication.apertus_right}, evidence label right ${s.source_level_adjudication.label_right}, both defensible ${s.source_level_adjudication.both_defensible}.</p>` : ""}` : ""}
    <h2>Preprocessing flags: pass 1 vs evidence-based pass 2</h2>
    <div class="callout">Pass 1 asked Apertus directly whether each preprocessing step was needed: it said “yes” for nearly every record, which carries no information.
    Pass 2 asks concrete yes/no checks with a quoted piece of evidence and derives the flags by rule.</div>
    <table class="t"><tr><th>Preprocessing</th><th>Pass 1 (direct question)</th><th>Pass 2 (evidence-based)</th></tr>
      ${flagRows.map(([k, v]) => `<tr><td>${PREP_LABEL[k]}</td><td>${s.preprocessing_v1_rates_pct?.[k] ?? "–"}%</td><td><b>${v}%</b></td></tr>`).join("")}</table>
    <h3>Apertus vs deterministic detectors on mechanical checks</h3>
    <p class="small muted">Final flags are “Apertus OR rule”. This table shows how much Apertus alone would have caught.</p>
    <table class="t"><tr><th>Check</th><th>Rule detector positive</th><th>Apertus positive</th><th>Apertus precision</th><th>Apertus recall</th></tr>
      ${Object.entries(s.preprocessing_flag_vs_evidence || {}).map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td>${v.rule_positive}</td><td>${v.apertus_positive}</td><td>${v.precision ?? "–"}</td><td>${v.recall ?? "–"}</td></tr>`).join("")}</table>
    <div class="two">
      <div><h2>Warnings</h2>${bars((s.warning_types || []).map(([k, n]) => [k === "date_archived_mismatch" ? k + " (auto-corrected)" : k, n]), s.records, true)}</div>
      <div><h2>Errors</h2>${(s.structural_error_types || []).length + (s.critical_types || []).length ? bars([...(s.structural_error_types || []), ...(s.critical_types || [])], s.records, true) : "<p>None.</p>"}</div>
    </div>
    ${mr ? `<h2>Manual review (${mr.reviewed} records${mr1 ? ", prompt v1 → v2" : ""})</h2>
      ${mr1 ? `<div class="callout">The same ${mr.reviewed} records were reviewed again after applying recommendations 1–4 of the quality report:
      role labels parsed by rule, archival conventions in the prompt, no name completion from world knowledge, and a person-centred sensitivity question.</div>` : ""}
      <div class="two"><div><h3>Verdicts${mr1 ? " (v2)" : ""}</h3>${bars(mr.verdicts, mr.reviewed)}
      ${mr1 ? `<table class="t"><tr><th>Verdict</th><th>v1</th><th>v2</th></tr>${["correct", "minor_errors", "major_errors"].map((k) => `<tr><td>${k.replace("_", " ")}</td><td>${verdict(mr1, k)}</td><td><b>${verdict(mr, k)}</b></td></tr>`).join("")}</table>` : ""}</div>
      <div><h3>Field accuracy</h3><table class="t"><tr><th>Field</th>${mr1 ? "<th>v1</th><th>v2</th>" : "<th>Correct</th>"}</tr>${Object.entries(mr.field_accuracy).map(([k, v]) => `<tr><td>${esc(k)}</td>${mr1 ? `<td>${mr1.field_accuracy[k] ?? "–"}%</td>` : ""}<td><b>${v}%</b></td></tr>`).join("")}</table></div></div>
      ${a1 ? `<h3>Automatic checks, v1 → v2</h3><table class="t"><tr><th>Metric</th><th>v1</th><th>v2</th></tr>
        <tr><td>Processed correctly</td><td>${a1.processed_ok_pct}%</td><td><b>${s.processed_ok_pct}%</b></td></tr>
        <tr><td>Named entities literally in the source</td><td>${a1.entity_grounding_strict_pct}% (${a1.entities})</td><td><b>${s.entity_grounding_strict_pct}% (${s.entities})</b></td></tr>
        <tr><td>Creator vs record “author”</td><td>${a1.creator_agreement}</td><td><b>${s.creator_agreement}</b></td></tr>
        <tr><td>Speculative résumés</td><td>${a1.resume_speculative}</td><td><b>${(s.warning_types || []).find(([k]) => k === "resume_speculative")?.[1] || 0}</b></td></tr>
        <tr><td>Records flagged for anonymization verification</td><td>${a1.anonymization_flag_pct}%</td><td><b>${s.preprocessing_flag_rates_pct?.anonymization_verification}%</b></td></tr>
        <tr><td>Sensitive category (identifiable person)</td><td>${a1.sensitive_pct}%</td><td><b>${s.personal_data?.sensitive_pct}%</b></td></tr></table>` : ""}
      <h3>Error types found${mr1 ? " (v2)" : ""}</h3>${(mr.error_types || []).length ? bars(mr.error_types, mr.reviewed, true) : "<p>None.</p>"}` : ""}
    <h2>Records with open issues</h2>
    <p class="small muted">“date_archived_mismatch” is left out: the accession-number rule overrides Apertus on that field.</p>
    <table class="t"><tr><th>Record</th><th>Type</th><th>Issues</th></tr>
      ${qc.records.map((r) => ({ ...r, open: [...(r.structural_errors || []), ...(r.critical || []), ...(r.warnings || []).filter((w) => w !== "date_archived_mismatch"), ...(r.geo_conflicts || []).map((g) => "gazetteer vs Apertus: " + g), ...(r.ungrounded_strict || []).map((u) => "not literally in source: " + u)] }))
        .filter((r) => r.open.length).map((r) => `<tr><td><a href="#/record/${r.id}/quality">${r.id}</a></td><td>${esc(r.document_type)}</td><td class="small">${esc(r.open.join(" · "))}</td></tr>`).join("")}</table>
    <h2>Cost</h2>
    <p>${(s.cost?.prompt_tokens || 0).toLocaleString("en")} prompt + ${(s.cost?.completion_tokens || 0).toLocaleString("en")} completion tokens for the classification pass;
    ${s.cost?.mean_seconds_per_record}s per record with Apertus 70B (6 parallel requests); ${s.cost?.retries} JSON retries.</p>`;
}

/* ---------------- Live classification ---------------- */
async function livePage() {
  setNav("live");
  app.innerHTML = `<h1>Classify any record live</h1>
    <p class="muted">Enter the ID of any unit of description in the Archive database (the number at the end of a
    <code>recherche.bar.admin.ch/…/einheit/<b>ID</b></code> link). The server reads its original fields, runs both Apertus passes and locates its places (≈30–40 s).</p>
    <form class="live-form" id="liveform">
      <input type="text" id="liveid" placeholder="e.g. 3237439" inputmode="numeric" pattern="\\d+" required>
      <label><input type="checkbox" id="opt-resume" checked> Résumé</label>
      <label><input type="checkbox" id="opt-story" checked> Story map</label>
      <button id="livebtn">Classify with Apertus</button>
      <span id="livestatus" class="small muted"></span>
    </form>
    <div id="liveout"></div>`;
  $("#liveform").onsubmit = async (e) => {
    e.preventDefault();
    const id = $("#liveid").value.trim();
    $("#livebtn").disabled = true;
    $("#livestatus").innerHTML = `<span class="spinner"></span> Apertus is reading record ${esc(id)}…`;
    try {
      const res = await api(`/api/classify/${id}?resume=${$("#opt-resume").checked}&story_map=${$("#opt-story").checked}`, { method: "POST" });
      const a = res.classification, rec = res.record;
      const view = {
        id, metadata: { title: rec.title, title_normalized: a.title_normalized, title_en: a.title_en, creator: a.creator, publisher: a.publisher, commissioner: a.commissioner, date_created: a.date_created, date_published: a.date_published, date_updated: a.date_updated, date_archived: res.derived.date_archived, content_date: rec.date.expressed, languages: a.languages, subjects: a.subjects },
        classification: { document_type: a.document_type, medium: a.medium, source_level: a.source_level, source_level_rationale: a.source_level_rationale, resume: a.resume },
        archival_location: { ...res.derived.archival_location, accession_numbers: res.derived.accession_numbers },
        source: { reference_code: rec.reference_code, original: rec },
        entities: { persons: a.persons, organizations: a.organizations, places: res.places.map((p) => ({ ...p, lat: p.geo?.lat ?? null, lon: p.geo?.lon ?? null, gazetteer: p.geo?.osm })) },
        preprocessing: a.preprocessing, personal_data: a.personal_data, audit_checks: a.audit_checks, story: res.story,
      };
      $("#livestatus").textContent = `Done in ${res.seconds}s.`;
      $("#liveout").innerHTML = `<div class="badges"><span class="badge">${esc(a.document_type)}</span><span class="badge lvl-${a.source_level}">${esc(a.source_level)} source</span></div>
        <h2>${esc(a.title_normalized || rec.title)}</h2>
        ${a.resume ? `<div class="resume-box">${esc(a.resume)} ${pv("apertus")}</div>` : ""}
        ${noticeTable(view)}${view.story.length ? `<h2>Story map</h2>${storyBlock(view, "livemap")}` : ""}<h2>Preprocessing & privacy</h2>${prepBlock(view)}`;
      if (view.story.length) drawStory(view, "livemap");
    } catch (err) {
      $("#livestatus").textContent = "Error: " + err.message;
    } finally {
      $("#livebtn").disabled = false;
    }
  };
}

/* ---------------- Ask the archive ---------------- */
async function askPage(params) {
  setNav("ask");
  const q = params.get("q") || "";
  app.innerHTML = `<h1>Ask the archive</h1>
    <p class="muted">Questions are answered only from the 100 classified records. Every sentence cites the records it relies on;
    when nothing relevant is found, CORA says so instead of answering. Answers are generated by Apertus ${pv("apertus")}.</p>
    <form class="live-form" id="askform"><input type="text" id="askq" style="width:min(560px,100%)" value="${esc(q)}" placeholder="e.g. What do the records show about Swiss football abroad?">
    <button id="askbtn">Ask</button><span id="askstatus" class="small muted"></span></form>
    <div class="chips">${["Which records concern the Swissair trial?", "What do the photographs of the 1914-1918 active service show?", "Welche Vorstösse gab es zur Kinderbetreuung?", "Who won the 1966 World Cup?"].map((x) => `<a class="chip x" href="#/ask?q=${encodeURIComponent(x)}">${esc(x)}</a>`).join("")}</div>
    <div id="askout"></div>`;
  $("#askform").onsubmit = (e) => { e.preventDefault(); location.hash = "#/ask?q=" + encodeURIComponent($("#askq").value.trim()); };
  if (!q) return;
  $("#askstatus").innerHTML = `<span class="spinner"></span> Searching and asking Apertus…`;
  try {
    const r = await api("/api/ask?q=" + encodeURIComponent(q));
    $("#askstatus").textContent = r.seconds ? `Answered in ${r.seconds}s.` : "";
    const n = {}; (r.citations || []).forEach((c, i) => (n[c.id] = i + 1));
    $("#askout").innerHTML = !r.sentences.length
      ? `<div class="callout">${esc(r.message || "The retrieved records do not answer this question.")}</div>`
      : `<div class="resume-box">${r.insufficient ? `<p class="small"><b>The sources only partly answer this.</b></p>` : ""}${r.sentences.map((s) => `${esc(s.text)}${s.sources.map((id) => ` <a href="#/record/${id}" title="${esc(id)}"><sup>[${n[id]}]</sup></a>`).join("")}${s.uncited ? ` <span class="badge qc-bad" title="No retrieved record supports this sentence">uncited</span>` : ""}`).join(" ")} ${pv("apertus")}</div>
        <h3>Sources</h3><ol>${(r.citations || []).map((c) => `<li><a href="#/record/${c.id}">${esc(c.title)}</a> · <code>${esc(c.reference_code)}</code> · <a href="${c.portal_url}" target="_blank" rel="noopener">archive portal ↗</a></li>`).join("")}</ol>`;
    $("#askout").innerHTML += `<details class="small muted"><summary>Retrieved records (BM25)</summary><ul>${(r.retrieved || []).map((h) => `<li><a href="#/record/${h.id}">${h.id}</a> score ${h.score} — ${esc(h.matched_terms.join(", "))}</li>`).join("")}</ul></details>`;
  } catch (err) {
    $("#askstatus").textContent = "Error: " + err.message;
  }
}

/* ---------------- Federal consultations 1960-1991 ---------------- */
async function consultationsPage(params) {
  setNav("consultations");
  const rows = await api("/api/consultations");
  const types = [...new Set(rows.map((r) => r.type).filter(Boolean))]
    .sort((a, b) => rows.filter((r) => r.type === b).length - rows.filter((r) => r.type === a).length);
  const years = Array.from({ length: 32 }, (_, i) => 1960 + i);
  const count = (t, y) => rows.filter((r) => r.type === t && r.year === y).length;
  const max = Math.max(...types.flatMap((t) => years.map((y) => count(t, y))));
  const selT = params.get("type"), selY = params.get("year") ? +params.get("year") : null, topic = params.get("topic");
  const topics = [...new Set(rows.flatMap((r) => r.topics))].sort();
  const list = rows.filter((r) => (!selT || r.type === selT) && (!selY || r.year === selY) && (!topic || r.topics.includes(topic)));
  const href = (o) => {
    const p = new URLSearchParams(params);
    Object.entries(o).forEach(([k, v]) => (v == null ? p.delete(k) : p.set(k, v)));
    return "#/consultations?" + p;
  };
  const matched = rows.filter((r) => r.match).length;
  const stepName = { consultation: "Consultation", message: "Message", parliament: "Parliament", vote: "Popular vote" };
  const step = (c) => `<div class="step ${c.date ? "on" : "off"}"><b>${stepName[c.step]}</b>
     <span>${c.date ? esc(c.date) : "not found"}</span>${c.detail ? `<small>${esc(c.detail)}</small>` : ""}${c.link ? `<a href="${c.link}" target="_blank" rel="noopener">source ↗</a>` : ""}</div>`;
  const cell = (t, y) => {
    const n = count(t, y);
    const on = selT === t && selY === y;
    return `<td><a href="${on ? href({ type: null, year: null }) : href({ type: t, year: y })}" title="${esc(t)} ${y}: ${n}" class="cell ${on ? "sel" : ""}"
      style="background:${n ? `rgba(181,18,27,${(0.15 + (0.85 * n) / max).toFixed(2)})` : "transparent"}"></a></td>`;
  };
  app.innerHTML = `<h1>Federal consultations 1960–1991</h1>
    <p class="muted">${rows.length} consultation procedures from the Swiss Federal Archives' metadata database (opendata.swiss).
    Topics and entities are tagged by Apertus ${pv("apertus")}. ${matched} procedures are linked to the popular vote they led to, using Swissvotes (CC BY 4.0) as the source:
    a title-overlap candidate is accepted only when Apertus confirms it with confidence ≥ 0.99 (a manual check found weaker confirmations mostly wrong). Steps that could not be matched say “not found”.</p>
    <h3>Timeline: year × type of act <small class="muted">(click a cell or a row)</small></h3>
    <div class="strip"><table><tr><th></th>${years.map((y) => `<th class="yr">${y % 5 === 0 ? y : ""}</th>`).join("")}</tr>
      ${types.map((t) => `<tr><th class="ty"><a href="${href({ type: selT === t ? null : t, year: null })}">${esc(t)}</a></th>${years.map((y) => cell(t, y)).join("")}</tr>`).join("")}</table></div>
    <div class="chips">${topics.map((t) => `<a class="chip x ${topic === t ? "on" : ""}" href="${href({ topic: topic === t ? null : t })}">${esc(t)} (${rows.filter((r) => r.topics.includes(t)).length})</a>`).join("")}</div>
    <div class="resbar" style="margin-top:14px"><div><b>${list.length}</b> procedures${selT ? ` · ${esc(selT)}` : ""}${selY ? ` · ${selY}` : ""}${topic ? ` · ${esc(topic)}` : ""}</div>
      ${selT || selY || topic ? `<a href="#/consultations">clear</a>` : ""}</div>
    ${list.slice(0, 60).map((r) => `<article class="result cons"><div>
        <h3>${esc(r.title)}</h3>
        <div class="muted small">${esc(r.title_en || "")} ${r.tag_generated ? pv("apertus") : ""}</div>
        <div class="badges"><span class="badge">${esc(r.type)}</span><span class="badge">${r.year}</span><span class="badge">${esc(r.dept_abbr)}</span>
          ${r.topics.map((t) => `<span class="badge lvl-secondary">${esc(t)}</span>`).join("")}${r.tag_confidence != null ? `<span class="badge">confidence ${r.tag_confidence}</span>` : ""}</div>
        ${r.entities.length ? `<div class="small">Entities: ${r.entities.map((e) => esc(e.name)).join(" · ")}</div>` : ""}
        ${r.archive_records ? `<div class="small muted">Archive records: ${esc(r.archive_records.slice(0, 240))}</div>` : ""}
        <div class="chain">${r.chain.map(step).join('<span class="arrow">→</span>')}</div>
        ${r.possible_vote ? `<div class="small muted">Possible (unconfirmed) vote: ${esc(r.possible_vote.title)}, ${esc(r.possible_vote.date)}, Apertus confidence ${r.possible_vote.confidence} (below the 0.99 bar)</div>` : ""}
        ${r.match ? `<div class="small muted">Vote match: title overlap ${r.match.title_similarity}, Apertus confidence ${r.match.confidence} — ${esc(r.match.reason || "")}</div>` : ""}
      </div></article>`).join("")}
    ${list.length > 60 ? `<p class="muted small">Showing 60 of ${list.length}; narrow with the timeline or a topic.</p>` : ""}`;
}

/* ---------------- Parliament: three bodies on a legislature timeline ---------------- */
const LINEAGE_ORDER = ["left", "sp", "gps", "glp", "ldu", "evp", "csp", "dem", "mitte", "lps", "fdp", "svp", "right", "other"];
let PARL = null;

function hemicycle(seats, lineages, onClick, small) {
  const n = seats.length;
  if (!n) return `<p class="muted small">No members recorded.</p>`;
  const W = small ? 260 : 420, H = W / 2 + 14, cx = W / 2, cy = H - 6, R = W / 2 - 8;
  const rows = Math.max(1, Math.round(Math.sqrt(n / 2.2)));
  const r0 = R * (rows > 1 ? 0.38 : 0.6);
  const radii = Array.from({ length: rows }, (_, i) => r0 + ((R - r0) * i) / Math.max(1, rows - 1));
  const tot = radii.reduce((a, b) => a + b, 0);
  let counts = radii.map((r) => Math.max(1, Math.round((n * r) / tot)));
  let diff = n - counts.reduce((a, b) => a + b, 0);
  for (let i = counts.length - 1; diff !== 0; i = (i - 1 + counts.length) % counts.length) { counts[i] += Math.sign(diff); diff -= Math.sign(diff); }
  const pos = [];
  radii.forEach((r, i) => { const k = counts[i]; for (let j = 0; j < k; j++) { const a = Math.PI - (Math.PI * (j + 0.5)) / k; pos.push({ a, x: cx + r * Math.cos(a), y: cy - r * Math.sin(a) }); } });
  pos.sort((p, q) => q.a - p.a);
  const dot = Math.min(10, (R - r0) / Math.max(1, rows) * 0.42 + (small ? 3 : 2), (Math.PI * r0) / Math.max(...counts) * 0.45);
  return `<svg viewBox="0 0 ${W} ${H}" class="hemi" role="img">${pos.map((p, i) => {
    const s = seats[i];
    return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${Math.max(2.2, dot).toFixed(1)}" fill="${lineages[s.lineage].color}" data-l="${s.lineage}"><title>${esc(`${s.first} ${s.last} (${s.party || "?"}, ${s.canton || ""})`)}</title></circle>`;
  }).join("")}<text x="${cx}" y="${cy - 4}" text-anchor="middle" class="hemi-n">${n}</text></svg>`;
}

async function parliamentPage(params) {
  setNav("parliament");
  [PARL, VOTES] = await Promise.all([PARL || api("/api/parliament"), VOTES || api("/api/votes")]);
  const legs = PARL.legislatures;
  const legStart = (L) => (L === 1848 ? "1848-11-01" : `${L}-12-01`);  // elections in autumn, new councils sit from December
  const vote = VOTES.votes.find((v) => v.anr === params.get("vote"));
  let y = +(params.get("year") || (vote ? legs.filter((L) => legStart(L) <= vote.date).pop() : 1971));
  if (!legs.includes(y)) y = legs.reduce((a, b) => (Math.abs(b - y) < Math.abs(a - y) ? b : a));
  const sel = params.get("lineage");
  // with a vote selected, show who sat in the councils on the day of the vote
  const d = vote ? vote.date : y === 1848 ? "1848-11-20" : `${y}-12-15`;
  const dFC = vote ? vote.date : `${y + 1}-01-15`;  // the Federal Council is elected in December and takes office on 1 January
  const active = (c) => [...new Map(PARL.members.filter((m) => { const t = c === 99 ? dFC : d; return m.council === c && m.join && m.join <= t && (!m.leave || m.leave >= t); })
      .map((m) => [m.pn, m])).values()]  // one seat per person (the source has repeated rows)
    .sort((a, b) => LINEAGE_ORDER.indexOf(a.lineage) - LINEAGE_ORDER.indexOf(b.lineage) || (a.party || "").localeCompare(b.party || ""));
  const bodies = [["National Council", 1], ["Council of States", 2], ["Federal Council", 99]].map(([name, c]) => ({ name, seats: active(c) }));
  const idx = legs.indexOf(y);
  const shares = PARL.vote_shares[String(y)];
  const legend = (seats) => {
    const c = {}; seats.forEach((s) => (c[s.lineage] = (c[s.lineage] || 0) + 1));
    return LINEAGE_ORDER.filter((l) => c[l]).map((l) => `<a class="lg ${sel === l ? "on" : ""}" href="#/parliament?year=${y}&lineage=${l}"><i style="background:${PARL.lineages[l].color}"></i>${esc(PARL.lineages[l].label)} <b>${c[l]}</b></a>`).join("");
  };
  const inLeg = VOTES.votes.filter((v) => v.date >= legStart(y) && (idx + 1 >= legs.length || v.date < legStart(legs[idx + 1])));
  app.innerHTML = `<h1>Parliament, government and votes, ${y}${idx + 1 < legs.length ? `–${legs[idx + 1]}` : "–"}</h1>
    <p class="muted">Members in office on ${d}${vote ? " (day of the selected vote)" : ` (Federal Council: ${dFC})`}, from the parlament.ch open-data service (all members since 1848),
    and every federal vote from Swissvotes. Legislatures snap to election years: 3-year terms until 1931, 4-year terms after. Party lineages keep one colour across renamings and mergers
    (BGB → SVP, KK → KVP → CVP → Die Mitte, LPS → FDP in 2009).</p>
    <div class="vote-find">
      <input id="votefind" list="votelist" placeholder="Find any federal vote since 1848 (title or year)…" autocomplete="off">
      <datalist id="votelist">${VOTES.votes.map((v) => `<option value="${v.anr} · ${v.date.slice(0, 4)} · ${esc(v.title_en || v.title_de)}">`).join("")}</datalist>
      <span class="small muted">Featured: <a href="#/parliament?vote=224&whatif=1959">women's suffrage, 1971 vs 1959</a></span>
    </div>
    ${vote ? `<div id="votepanel"></div>` : ""}
    <div class="slider-bar">
      <a class="btn" href="#/parliament?year=${legs[Math.max(0, idx - 1)]}">‹</a>
      <input type="range" id="leg" min="0" max="${legs.length - 1}" value="${idx}" step="1">
      <a class="btn" href="#/parliament?year=${legs[Math.min(legs.length - 1, idx + 1)]}">›</a>
      <b>${y}</b><span class="small muted">${idx < 28 ? "3-year term" : "4-year term"}</span>
    </div>
    <div class="parl">${bodies.map((b) => `<section class="body"><h3>${b.name} <small>${b.seats.length} seats</small></h3>${hemicycle(b.seats, PARL.lineages, null, b.name === "Federal Council")}
      <div class="legend2">${legend(b.seats)}</div></section>`).join("")}</div>
    <h3>National vote shares (BFS), ${y}</h3>
    ${shares ? `<div class="shares">${Object.entries(shares).filter(([, v]) => v.share >= 0.5).sort((a, b) => b[1].share - a[1].share).map(([p, v]) => `<div class="sh"><span>${esc(p)}</span><div class="bar"><i style="width:${(v.share * 2.5).toFixed(1)}%;background:${(PARL.lineages[v.lineage] || PARL.lineages.other).color}"></i></div><b>${v.share.toFixed(1)} %</b></div>`).join("")}</div>
      <p class="small muted">Vote shares, not seats. Source: BFS px-x-1702020000_104.</p>`
      : `<p class="muted small">No national vote shares for ${y} in the BFS series used here (it starts in 1971). Seats above come from parlament.ch.</p>`}
    <h3>Federal votes in this legislature <small class="muted">${inLeg.length}</small></h3>
    ${inLeg.length ? `<table class="t votes"><tr><th>Date</th><th>Vote</th><th>Yes</th><th>Party-cue estimate</th></tr>
      ${inLeg.map((v) => `<tr class="${vote && v.anr === vote.anr ? "on" : ""}"><td>${v.date}</td><td><a href="#/parliament?year=${y}&vote=${v.anr}">${esc(v.title_en || v.title_de)}</a> <span class="small muted">${esc(v.legal_form)}</span></td>
        <td>${voteBar(v.yes, v.accepted)}</td><td>${v.estimate != null ? `${v.estimate} %` : `<span class="muted">–</span>`}</td></tr>`).join("")}</table>`
      : `<p class="small muted">No federal vote in this legislature.</p>`}
    <div id="members"></div>`;
  $("#leg").oninput = (e) => (location.hash = `#/parliament?year=${legs[+e.target.value]}`);
  $("#votefind").onchange = (e) => { const anr = e.target.value.split(" · ")[0].trim(); if (VOTES.votes.some((v) => v.anr === anr)) location.hash = `#/parliament?vote=${anr}`; };
  if (vote) votePanel(vote, +params.get("whatif") || null, y);
  if (sel) {
    const ms = bodies.flatMap((b) => b.seats.filter((s) => s.lineage === sel).map((s) => ({ ...s, body: b.name })));
    $("#members").innerHTML = `<h3>${esc(PARL.lineages[sel].label)}: ${ms.length} members in ${y}</h3><p class="small muted"><span class="spinner"></span> Looking up Wikipedia articles via Wikidata…</p>`;
    const links = await api("/api/parliament/links", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(ms.map((m) => ({ pn: m.pn, name: `${m.first} ${m.last}` }))) }).catch(() => ({}));
    $("#members").innerHTML = `<h3>${esc(PARL.lineages[sel].label)}: ${ms.length} members in ${y}</h3>
      <table class="t"><tr><th>Name</th><th>Body</th><th>Party</th><th>Canton</th><th>In office</th><th>Wikipedia</th></tr>
      ${ms.map((m) => { const l = links[m.pn]; return `<tr><td>${esc(m.first)} ${esc(m.last)}</td><td>${m.body}</td><td>${esc(m.party || "")}</td><td>${esc(m.canton || "")}</td><td>${esc(m.join || "")} – ${esc(m.leave || "")}</td>
        <td>${l?.wikipedia ? `<a href="${l.wikipedia}" target="_blank" rel="noopener">article ↗</a>` : l?.wikidata ? `<a href="${l.wikidata}" target="_blank" rel="noopener">Wikidata</a>` : `<span class="muted">–</span>`}</td></tr>`; }).join("")}</table>
      <p class="small muted">Links: Wikidata exact name match whose description names a Swiss politician, with birth before the term (${pv("wikidata")}).</p>`;
  }
}

/* ---------------- Federal votes: estimate and "what if it had been voted in another year" ---------------- */
const REC = { "1": "yes", "2": "no", "3": "none", "4": "empty", "5": "free vote", "66": "neutral" };
const PARTY_LINEAGE = { fdp: "fdp", sp: "sp", svp: "svp", cvp: "mitte", mitte: "mitte", bdp: "mitte", evp: "evp", gps: "gps", glp: "glp", pda: "left", poch: "left",
  sd: "right", edu: "right", fps: "right", lega: "right", rep: "right", mcg: "right", lps: "lps", ldu: "ldu", csp: "csp" };
const PARTY_LABEL = { sp: "SP", svp: "SVP (BGB)", cvp: "CVP (KVP)", mitte: "Die Mitte", gps: "Grüne", ldu: "LdU", pda: "PdA" };
const partyDot = (p) => `<i class="pdot" style="background:${(PARL.lineages[PARTY_LINEAGE[p]] || PARL.lineages.other).color}"></i>${esc(PARTY_LABEL[p] || p.toUpperCase())}`;
let VOTES = null;

function voteBar(yes, accepted) {
  if (yes == null) return `<span class="small muted">upcoming</span>`;
  return `<span class="vbar"><i style="width:${yes}%" class="${accepted ? "acc" : "rej"}"></i></span> <b>${yes.toFixed(1)} %</b>`;
}

function backtestSvg(points, f, marks) {
  const W = 520, H = 280, px = (c) => 40 + c * (W - 60), py = (y) => H - 30 - (y / 100) * (H - 50);
  const dots = Object.entries(points).map(([anr, p]) => marks[anr] ? "" : `<circle cx="${px(p.cue).toFixed(1)}" cy="${py(p.yes).toFixed(1)}" r="2.2" fill="rgba(60,60,60,.3)"/>`).join("");
  const big = Object.entries(marks).filter(([anr]) => points[anr]).map(([anr, m]) => `<circle cx="${px(points[anr].cue).toFixed(1)}" cy="${py(points[anr].yes).toFixed(1)}" r="6" fill="${m.color}"><title>${esc(m.label)}</title></circle>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="scatter"><line x1="40" y1="${H - 30}" x2="${W - 20}" y2="${H - 30}" stroke="#999"/><line x1="40" y1="20" x2="40" y2="${H - 30}" stroke="#999"/>
    <text x="${W / 2}" y="${H - 6}" text-anchor="middle" class="ax">party cue (0 = all parties say no, 1 = all say yes)</text>
    <text x="12" y="${H / 2}" transform="rotate(-90 12 ${H / 2})" text-anchor="middle" class="ax">yes %</text>${dots}
    <line x1="${px(0)}" y1="${py(f.a)}" x2="${px(1)}" y2="${py(f.a + f.b)}" stroke="#1d5fa6" stroke-width="2"/>${big}</svg>`;
}

async function votePanel(v, whatifYear, legYear) {
  const box = $("#votepanel");
  const f = VOTES.model;
  box.innerHTML = `<section class="vote"><h2>${esc(v.title_en || v.title_de)}</h2><p class="muted">${v.date} · ${esc(v.legal_form)} · ${voteBar(v.yes, v.accepted)}</p>
    <p class="small muted"><span class="spinner"></span> Apertus is reading the vote and looking for related votes…</p></section>`;
  let d;
  try { d = await api(`/api/votes/${v.anr}`); } catch (err) { box.innerHTML = `<p class="small">Could not load the vote: ${esc(err.message)}</p>`; return; }
  if (!$("#votepanel")) return;
  const a = d.apertus;
  const rel = a.related || [];
  const years = [...new Set([...rel.map((x) => x.year), ...PARL.legislatures.filter((L) => L >= 1896)])].filter((yy) => yy !== d.year).sort((p, q) => p - q);
  const partyRows = (u, extra = () => "") => Object.entries(u).sort((p, q) => q[1].share - p[1].share).map(([p, x]) => `<tr><td>${partyDot(p)}</td><td>${REC[x.rec] || x.rec}</td><td>${x.share.toFixed(1)} %</td>${extra(p, x)}</tr>`).join("");
  const hasResult = d.yes != null;
  box.innerHTML = `<section class="vote">
    <div class="vote-head"><div>
      <h2>${esc(a.title_en || d.title_de)}</h2>
      <p class="muted">${esc(d.title_de)} · ${esc(d.title_fr)}<br>${d.date} · ${esc(d.legal_form)}${d.cantons_accepting && d.cantons_accepting !== "." ? ` · cantons: ${esc(d.cantons_accepting)} % yes` : ""}</p>
    </div><div class="vote-result">
      <div><span class="small muted">${hasResult ? "Result" : "Upcoming"}</span><b class="${hasResult ? (d.accepted ? "acc" : "rej") : ""}">${hasResult ? `${d.yes.toFixed(1)} % yes` : "–"}</b>${hasResult ? `<span class="small">${d.accepted ? "accepted" : "rejected"}</span>` : ""}</div>
      <div><span class="small muted">${hasResult ? "Party-cue estimate" : "Party-cue forecast"}</span><b>${d.estimate != null ? `${d.estimate} %` : "–"}</b><span class="small">± ${d.loo_mae} pts</span></div>
    </div></div>
    ${a.summary ? `<p class="small">${esc(a.summary)} ${pv("apertus")}</p>` : ""}
    <div class="two"><div>
      <h3>Party recommendations</h3>
      ${Object.keys(d.parties).length ? `<table class="t">${partyRows(d.parties)}</table>` : `<p class="small muted">No party recommendations recorded.</p>`}
      <p class="small muted">Weights: National Council vote shares ${d.shares_from ? `of the closest vote with data (${d.shares_from.date})` : "at the time"}. Parliament: ${Object.entries(d.parliament).filter(([, x]) => x.yes != null).map(([k, x]) => `${k} ${x.yes}–${x.no}`).join(", ") || "no recorded vote"}.
      ${Object.entries(d.links).map(([k, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(k)} ↗</a>`).join(" · ")}</p>
    </div><div>
      <h3>Related votes</h3>
      ${rel.length ? `<ul class="topic-list">${rel.map((x) => `<li><a href="#/parliament?vote=${x.anr}">${x.date.slice(0, 4)} · ${esc(x.title_de)}</a> <span class="small muted">${esc(x.relation || "")}${x.by === "title" ? " (same title)" : ""} · ${x.yes != null ? `${x.yes.toFixed(1)} % yes` : "upcoming"}</span>
          ${x.year !== d.year ? ` · <a class="small" href="#/parliament?vote=${d.anr}&whatif=${x.year}">what if voted in ${x.year}?</a>` : ""}</li>`).join("")}</ul>` : `<p class="small muted">Apertus found no related vote among ${a.candidates} candidates.</p>`}
      <p class="small muted">Related votes: same short title, or chosen by Apertus among votes of the same policy area or with similar titles ${pv("apertus")}.</p>
      <div class="whatif-form"><label>What if this proposal had been voted in
        <select id="wfyear">${years.map((yy) => `<option ${yy === whatifYear ? "selected" : ""}>${yy}</option>`).join("")}</select></label>
        <input id="wfcustom" type="number" min="1848" max="2030" placeholder="or year" value="${whatifYear && !years.includes(whatifYear) ? whatifYear : ""}">
        <button id="wfgo" class="btn">Estimate</button></div>
    </div></div>
    <div id="whatif"></div></section>`;
  $("#wfgo").onclick = () => { const yy = +$("#wfcustom").value || +$("#wfyear").value; if (yy) location.hash = `#/parliament?vote=${d.anr}&whatif=${yy}`; };
  if (!whatifYear) {
    $("#whatif").innerHTML = backtestSvg(f.points, f, { [d.anr]: { color: "#b5121b", label: `${d.date} ${d.title_de}` } })
      + `<p class="small muted">Backtest of the party-cue model on ${f.n_votes} votes: yes % = ${f.a} + ${f.b} × cue, leave-one-out error ±${f.loo_mae} points. <span style="color:#b5121b">●</span> this vote.</p>`;
    return;
  }
  const wb = $("#whatif");
  wb.innerHTML = `<p class="small muted"><span class="spinner"></span> Apertus is imagining the ${whatifYear} party positions…</p>`;
  let w;
  try { w = await api(`/api/votes/${d.anr}/whatif?year=${whatifYear}`); } catch (err) { wb.innerHTML = `<p class="small">Could not estimate: ${esc(err.message)}</p>`; return; }
  if (!$("#whatif")) return;
  const P = w.positions_then_strengths, im = w.imagination, an = w.anchor;
  const marks = { [d.anr]: { color: "#1f7a4d", label: d.title_de } };
  if (an) marks[an.anr] = { color: "#b5121b", label: an.title_de };
  wb.innerHTML = `<h3>The ${d.year} proposal under ${whatifYear} conditions</h3>
    <div class="two"><div>
      <table class="t"><tr><th>Scenario</th><th>Estimate</th><th>Actual</th></tr>
        <tr><td>${d.year} vote, its own positions and strengths</td><td>${d.estimate ?? "–"} %</td><td>${hasResult ? `${d.yes.toFixed(1)} %` : "–"}</td></tr>
        ${an ? `<tr><td>${an.date.slice(0, 4)} vote “${esc(an.title_de)}” (${esc(an.relation || "related")})</td><td>${an.estimate ?? "–"} %</td><td>${an.actual ?? "–"} %</td></tr>` : ""}
        <tr><td><b>${d.year} positions, ${whatifYear} party strengths</b></td><td><b>${P.estimate ?? "–"} %</b>${P.interval ? `<br><span class="small">${P.interval[0]}–${P.interval[1]} %</span>` : ""}</td><td>–</td></tr>
        ${P.corrected != null ? `<tr><td>… corrected by the model's miss on the ${an.date.slice(0, 4)} vote (${an.residual > 0 ? "+" : ""}${an.residual} pts)</td><td><b>${P.corrected} %</b></td><td>–</td></tr>` : ""}
        <tr><td>Apertus-imagined ${whatifYear} positions, ${whatifYear} strengths <span class="badge">generated</span></td><td>${im.estimate ?? "–"} %${im.corrected != null ? `<br><span class="small">corrected ${im.corrected} %</span>` : ""}</td><td>–</td></tr></table>
      <div class="callout small">Strengths of ${whatifYear}: National Council vote shares from the vote of ${w.conditions.date}.
        ${P.parties_without_position.length ? `Parties of ${whatifYear} without a position in ${d.year} (left out of the evidence row): ${P.parties_without_position.map((p) => esc(PARTY_LABEL[p] || p.toUpperCase())).join(", ")}.` : ""}
        ${an && an.residual != null ? `On the related ${an.date.slice(0, 4)} vote the model was off by ${an.residual} points: that is the issue-specific gap of that electorate, carried over in the corrected rows.` : `No related vote within 6 years of ${whatifYear}, so no issue-specific correction.`}
        The estimates are model outputs, not facts.</div>
      ${backtestSvg(f.points, f, marks)}
      <p class="small muted"><span style="color:#1f7a4d">●</span> ${d.year} vote ${an ? `&nbsp;<span style="color:#b5121b">●</span> ${an.date.slice(0, 4)} vote` : ""} · grey: all other votes (yes % = ${f.a} + ${f.b} × cue, ±${f.loo_mae} pts)</p>
    </div><div>
      <h4>Party positions used (${d.year} positions, ${whatifYear} strengths)</h4>
      <table class="t">${partyRows(P.parties)}</table>
      ${an ? `<h4>Actual positions on the ${an.date.slice(0, 4)} vote</h4><table class="t">${partyRows(an.parties)}</table>` : ""}
    </div></div>
    <section class="band band-imagination"><h3>Imagination <small>generated by Apertus · counterfactual party positions, not evidence</small></h3>
      <p class="small">Asked: “Had this proposal been voted in ${whatifYear}, what would each party of ${whatifYear} most plausibly have recommended?”, with the parties' recommendations on related votes as evidence.</p>
      <table class="t"><tr><th>Party</th><th>Imagined</th>${an ? `<th>Actual ${an.date.slice(0, 4)}</th>` : ""}<th>Reasoning (generated)</th></tr>
      ${Object.entries(im.parties || {}).map(([p, x]) => `<tr><td>${partyDot(p)}</td><td>${REC[x.rec] || x.rec}</td>${an ? `<td>${REC[x.anchor_rec] || x.anchor_rec || "–"}</td>` : ""}
        <td class="small">${esc(x.reason || "")}${x.misstates_evidence ? ` <span class="badge qc-bad">misstates the record</span>` : ""}</td></tr>`).join("")}</table>
    </section>`;
}

async function referendumPage() {
  location.replace("#/parliament?vote=224&whatif=1959");  // the 1959 vs 1971 page is now one case of the votes view
}

/* ---------------- Router ---------------- */
async function route() {
  const h = location.hash.slice(1) || "/";
  const [path, query] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  app.innerHTML = `<p class="muted"><span class="spinner"></span> Loading…</p>`;
  try {
    if (!parts.length) await home();
    else if (parts[0] === "search") await search(new URLSearchParams(query || ""));
    else if (parts[0] === "record") await recordPage(parts[1], parts[2]);
    else if (parts[0] === "map") await mapPage();
    else if (parts[0] === "quality") await qualityPage();
    else if (parts[0] === "live") await livePage();
    else if (parts[0] === "ask") await askPage(new URLSearchParams(query || ""));
    else if (parts[0] === "consultations") await consultationsPage(new URLSearchParams(query || ""));
    else if (parts[0] === "parliament") await parliamentPage(new URLSearchParams(query || ""));
    else if (parts[0] === "referendum") await referendumPage();
    else app.innerHTML = "<p>Not found.</p>";
  } catch (e) {
    app.innerHTML = `<p>Could not load: ${esc(e.message)}</p>`;
  }
  window.scrollTo(0, 0);
}
$("#searchform").onsubmit = (e) => { e.preventDefault(); location.hash = "#/search?q=" + encodeURIComponent($("#q").value.trim()); };
window.addEventListener("hashchange", route);
route();
