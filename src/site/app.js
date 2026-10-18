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
        <h1>100 documents of the Swiss Federal Archives, read by Apertus</h1>
        <p>Every record was drawn at random from the item-level documents of the <em>Archive database of the Swiss Federal Archives</em>
        (opendata.swiss). Apertus v1.5, Switzerland's open language model, wrote a résumé of each, typed it as a primary,
        secondary or tertiary source, completed its metadata, assessed the preprocessing it needs and traced its story on a map.
        Each value shows where it came from: <span class="pv pv-record">record</span><span class="pv pv-derived">derived</span><span class="pv pv-apertus">apertus</span><span class="pv pv-gazetteer">gazetteer</span><span class="pv pv-wikidata">wikidata</span></p>
        <p class="small muted">Stratified random sample (seed 42) from ${(pop.all_records || 263123).toLocaleString("en")} documents:
        40 audiovisual · 30 still images · 30 other records.</p>
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
const FACET_TITLES = { document_type: "Document type", source_level: "Source level", medium: "Medium", decade: "Period", fonds: "Fonds", language: "Language", preprocessing: "Preprocessing needed", qc: "Quality check" };

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

async function recordPage(id, tab) {
  setNav("search");
  const r = await api("/api/records/" + id);
  const loc = r.archival_location;
  const tabs = { notice: "Notice", story: "Story map", prep: "Preprocessing & privacy", original: "Original record", quality: "Quality check", json: "JSON" };
  tab = tabs[tab] ? tab : "notice";
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
        ${r.classification.resume ? `<div class="resume-box">${esc(r.classification.resume)} ${pv("apertus")}</div>` : `<p class="muted small">Résumé disabled in config.</p>`}
        <div class="tabs">${Object.entries(tabs).map(([k, v]) => `<button data-tab="${k}" class="${k === tab ? "on" : ""}">${v}</button>`).join("")}</div>
        <div class="tabpane" id="pane"></div>
      </section>
    </div>`;
  const panes = {
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
  show(tab);
}

/* ---------------- Overview map ---------------- */
async function mapPage() {
  setNav("map");
  const { points, archive } = await api("/api/map");
  app.innerHTML = `<h1>Where the documents come from</h1>
    <p class="muted">Every place Apertus identified as where a document was made, depicted or published, located with the OpenStreetMap gazetteer.
    All roads lead to the Swiss Federal Archives in Bern. Click a point to open the document.</p>
    <div class="legend">${["creation", "depicted", "publication", "holding"].map((k) => `<span><i style="background:var(--c)" class="ev-${k}"></i>${EVENT_LABEL[k]}</span>`).join("")}</div>
    <div id="bigmap" class="map big"></div>
    <p class="small muted">${points.length} located events across ${new Set(points.map((p) => p.id)).size} documents.</p>`;
  const map = baseMap($("#bigmap"));
  const bar = [archive.lat, archive.lon];
  L.marker(bar, { icon: eventIcon({ event: "holding" }, {}, 0), zIndexOffset: 1000 }).addTo(map).bindPopup(`<b>${esc(archive.name)}</b><br>${esc(archive.place)}`);
  const bounds = [bar];
  points.forEach((p) => {
    const ll = [p.lat, p.lon];
    bounds.push(ll);
    L.polyline([ll, bar], { color: "#b5121b", weight: 1, opacity: 0.25 }).addTo(map);
    L.circleMarker(ll, { radius: 6, weight: 2, color: "#fff", fillOpacity: 0.9, fillColor: { creation: "#8a1c7c", depicted: "#1d5fa6", publication: "#a05a00" }[p.event] || "#444" })
      .addTo(map).bindPopup(`<a href="#/record/${p.id}"><b>${esc(p.title)}</b></a><br>${EVENT_LABEL[p.event]} · ${esc(p.place || "")} · ${fmtDate(p.date)}`);
  });
  map.fitBounds(L.latLngBounds(bounds).pad(0.1));
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
    else app.innerHTML = "<p>Not found.</p>";
  } catch (e) {
    app.innerHTML = `<p>Could not load: ${esc(e.message)}</p>`;
  }
  window.scrollTo(0, 0);
}
$("#searchform").onsubmit = (e) => { e.preventDefault(); location.hash = "#/search?q=" + encodeURIComponent($("#q").value.trim()); };
window.addEventListener("hashchange", route);
route();
