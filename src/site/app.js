/* CORA front end — Gallica-inspired browsing of Apertus-classified records. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const app = $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts) => {
  const r = await fetch(withLang(path), opts);  // ?lang=: Apertus writes in the reader's language
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

/* Icons: inline SVG (Lucide-style strokes), so they render the same on every OS and browser,
   with no dependency on an emoji font. */
const SVG = {
  tv: '<rect x="2" y="7" width="20" height="15" rx="2"/><path d="m17 2-5 5-5-5"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 7.5h4M3 12h18M3 16.5h4M17 7.5h4M17 16.5h4"/>',
  radio: '<rect x="2" y="8" width="20" height="13" rx="2"/><path d="M6 8 17 3"/><circle cx="15" cy="14.5" r="3"/><path d="M6 12h4M6 16h4"/>',
  clapper: '<path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"/><path d="m6.2 5.3 3.1 3.9M12.4 3.4l3.1 4"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M19 10v1a7 7 0 0 1-14 0v-1M12 18v4M8 22h8"/>',
  camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
  doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  landmark: '<path d="M3 22h18M6 18v-7M10 18v-7M14 18v-7M18 18v-7M12 2l8 5H4z"/>',
  scale: '<path d="m16 16 3-8 3 8c-.9.6-1.9 1-3 1s-2.1-.4-3-1Z"/><path d="m2 16 3-8 3 8c-.9.6-1.9 1-3 1s-2.1-.4-3-1Z"/><path d="M7 21h10M12 3v18M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
  archive: '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8M10 12h4"/>',
  map: '<path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z"/><path d="M9 3v15M15 6v15"/>',
  news: '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8M15 18h-5M10 6h8v4h-8z"/>',
  megaphone: '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
  index: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h10M7 17h6"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
  layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
  tower: '<path d="M4.9 16.1C1 12.2 1 5.8 4.9 1.9M7.8 4.7a6.1 6.1 0 0 0-.8 7.5M16.2 4.8c2 2 2.3 5 .8 7.5M19.1 1.9a10 10 0 0 1 0 14.1"/><circle cx="12" cy="9" r="2"/><path d="m8.5 21 3.5-8 3.5 8M9.5 18h5"/>',
  refresh: '<path d="M21 12a9 9 0 0 1-15 6.7L3 16M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M3 21v-5h5"/>',
  package: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  check: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  play: '<path d="M6 4l14 8-14 8z" fill="currentColor"/>',
  pause: '<path d="M7 4h3v16H7zM14 4h3v16h-3z" fill="currentColor"/>',
};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SVG[name] || SVG.file}</svg>`;

/* Vote titles: official titles stay in their language (German or French); Apertus' English title only in English. */
function voteTitle(v, en) {
  if (LANG === "en") return en || v.title_en || v.title_de;
  return (LANG === "fr" || LANG === "it") ? (v.title_fr || v.title_de) : v.title_de;
}

const MEDIUM_ICON = { "moving image": "film", "still image": "camera", text: "doc", sound: "mic", mixed: "layers" };
const TYPE_ICON = {
  "TV news report": "tv", newsreel: "film", "radio broadcast": "radio", film: "clapper", "audio recording": "mic",
  photograph: "camera", correspondence: "mail", report: "doc", "minutes / protocol": "pen", "parliamentary record": "landmark",
  "legislation / decree": "scale", "administrative file": "archive", "map / plan": "map", "press article": "news",
  "press release / communiqué": "megaphone", "register / index": "index", "finding aid / inventory": "list", "publication / book": "book",
  speech: "mic", other: "file",
};
const EVENT_LABEL = { creation: "Created", depicted: "Depicted place", publication: "Published / broadcast", update: "Updated", accession: "Entered the Federal Archives", holding: "Kept today" };
const EVENT_ICON = { creation: "pen", depicted: "eye", publication: "tower", update: "refresh", accession: "package", holding: "landmark" };
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
  const inner = src ? `<img src="${src}" alt="">` : (EVENT_ICON[ev.event] ? icon(EVENT_ICON[ev.event]) : "•");
  const el = document.createElement("div");  // MapLibre positions this wrapper; the pin keeps its own layout
  el.innerHTML = `<div class="pin ev-${ev.event}">${inner}${n ? `<b>${n}</b>` : ""}</div>`;
  return el;
}

// Base maps. The swisstopo vector tiles (vectortiles.geo.admin.ch) only carry detailed data for Switzerland and
// Liechtenstein, so the swisstopo options are composites: OpenStreetMap underneath everywhere, swisstopo on top inside
// its coverage (assets/swisstopo_coverage.json) and swisstopo features lying entirely outside it dropped.
const OSM_STYLE = {
  version: 8,
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors" } },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};
const BASEMAPS = {
  "swisstopo light + OSM abroad": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.lightbasemap.vt/style.json",
  "swisstopo + OSM abroad": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.basemap.vt/style.json",
  "OpenStreetMap": OSM_STYLE,
};
let COVERAGE = null;
const STYLE_CACHE = {};

// Legacy filter syntax (["==", "class", "lake"], ["!in", …]) cannot be combined with expressions such as `within`;
// convert it the way the style specification does. Expression filters are returned unchanged.
function isExpressionFilter(f) {
  if (f === true || f === false) return true;
  if (!Array.isArray(f) || !f.length) return false;
  switch (f[0]) {
    case "has": return f.length >= 2 && f[1] !== "$id" && f[1] !== "$type";
    case "in": return f.length >= 3 && (typeof f[1] !== "string" || Array.isArray(f[2]));
    case "!in": case "!has": case "none": return false;
    case "==": case "!=": case ">": case ">=": case "<": case "<=": return f.length !== 3 || Array.isArray(f[1]) || Array.isArray(f[2]);
    case "any": case "all": return f.slice(1).every((x) => typeof x === "boolean" || isExpressionFilter(x));
    default: return true;
  }
}
function legacyToExpression(f) {
  const [op, k, ...v] = f;
  const geomTypes = (vals) => ["literal", vals.flatMap((t) => [t, "Multi" + t])];  // legacy $type also matches Multi*
  const get = (key) => (key === "$type" ? ["geometry-type"] : key === "$id" ? ["id"] : ["get", key]);
  switch (op) {
    case "all": case "any": return [op, ...f.slice(1).map(legacyToExpression)];
    case "none": return ["!", ["any", ...f.slice(1).map(legacyToExpression)]];
    case "has": return k === "$id" ? ["!=", ["id"], null] : ["has", k];
    case "!has": return ["!", legacyToExpression(["has", k])];
    case "in": return ["in", get(k), k === "$type" ? geomTypes(v) : ["literal", v]];
    case "!in": return ["!", legacyToExpression(["in", k, ...v])];
    case "==": return k === "$type" ? ["in", ["geometry-type"], geomTypes(v)] : ["==", get(k), v[0]];
    case "!=": return ["!", legacyToExpression(["==", k, v[0]])];
    default:  // < <= > >=: legacy only compares values of the same type
      return ["all", ["==", ["typeof", get(k)], typeof v[0]], [op, get(k), v[0]]];
  }
}

// Relief: the vector relief tiles shade far beyond the border with large polygons that cannot be cut client-side;
// the swisstopo raster hillshades cover Switzerland and Liechtenstein only and are transparent elsewhere.
const RELIEF_RASTER = {
  light: { layer: "ch.swisstopo.leichte-basiskarte_reliefschattierung", opacity: 0.3 },
  color: { layer: "ch.swisstopo.swissalti3d-reliefschattierung", opacity: 0.4 },
};
async function swissHybrid(url) {
  COVERAGE ||= await fetch("assets/swisstopo_coverage.json").then((r) => r.json());
  const style = await fetch(url).then((r) => r.json());
  // Keep only features touching the coverage (coarse outline, ~1 km buffer); `distance` handles points, lines and
  // polygons (`within` ignores polygons).
  const keep = ["<=", ["distance", COVERAGE.filter], 0];
  const relief = RELIEF_RASTER[url.includes("lightbasemap") ? "light" : "color"];
  const reliefSources = new Set(Object.keys(style.sources).filter((k) => style.sources[k].url?.includes("relief")));
  const layers = [];
  for (const l of style.layers) {
    if (l.type === "background") {  // swisstopo's ground colour, painted inside its coverage only
      layers.push({ id: "swisstopo-ground", type: "fill", source: "swisstopo-coverage", paint: { "fill-color": l.paint?.["background-color"] || "#fcfcfc" } });
      continue;
    }
    if (reliefSources.has(l.source)) {  // replaced by the raster hillshade, drawn where the first relief layer was
      if (!layers.some((x) => x.id === "swisstopo-relief")) layers.push({ id: "swisstopo-relief", type: "raster", source: "swisstopo-relief", paint: { "raster-opacity": relief.opacity } });
      continue;
    }
    const own = l.filter == null ? null : isExpressionFilter(l.filter) ? l.filter : legacyToExpression(l.filter);
    layers.push({ ...l, filter: own ? ["all", own, keep] : keep });
  }
  const { center, zoom, bearing, pitch, ...rest } = style;  // keep the map's own view on a base-map switch
  const sources = Object.fromEntries(Object.entries(style.sources).filter(([k]) => !reliefSources.has(k)));
  return { ...rest,
    sources: { ...OSM_STYLE.sources, ...sources,
      "swisstopo-coverage": { type: "geojson", data: COVERAGE.inside },
      "swisstopo-relief": { type: "raster", tileSize: 256, maxzoom: 17, bounds: [5.9, 45.8, 10.5, 47.85], attribution: "© swisstopo",
        tiles: [`https://wmts.geo.admin.ch/1.0.0/${relief.layer}/default/current/3857/{z}/{x}/{y}.png`] } },
    layers: [...OSM_STYLE.layers, ...layers] };
}

function loadBase(name) {
  const b = BASEMAPS[name];
  return typeof b === "string" ? (STYLE_CACHE[name] ||= swissHybrid(b)) : Promise.resolve(b);
}

function setBase(map, name) {
  loadBase(name).then((s) => map.setStyle(s, { diff: false }))
    .catch((err) => { console.warn("swisstopo base map unavailable, using OpenStreetMap", err); map.setStyle(OSM_STYLE, { diff: false }); });
}

class BaseSwitch {
  onAdd(map) {
    this.el = document.createElement("div");
    this.el.className = "maplibregl-ctrl maplibregl-ctrl-group basemap-switch";
    this.el.innerHTML = `<select title="Base map">${Object.keys(BASEMAPS).map((k) => `<option>${k}</option>`).join("")}</select>`;
    this.el.firstChild.onchange = (e) => setBase(map, e.target.value);
    return this.el;
  }
  onRemove() { this.el.remove(); }
}

// Overlays (sources/layers) must be re-added after every base-map switch: pass them as onStyle.
// The map opens on OpenStreetMap and switches to the swisstopo composite as soon as it is built.
function baseMap(el, onStyle, opts = {}) {
  const map = new maplibregl.Map({ container: el, style: OSM_STYLE, scrollZoom: false, dragRotate: false, pitchWithRotate: false,
    attributionControl: { compact: true }, ...opts });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }));
  map.addControl(new BaseSwitch(), "top-left");
  if (onStyle) map.on("style.load", () => onStyle(map));
  setBase(map, Object.keys(BASEMAPS)[0]);
  return map;
}

const lineGeo = (lls) => ({ type: "Feature", geometry: { type: "LineString", coordinates: lls.map(([la, lo]) => [lo, la]) } });

const COVER_KIND = { place: "place in this record", subject: "subject of this record" };

/* Covers: a period photograph of the record's place or subject, taken in the record's year or up to 20 years
   later, never before (covers.py; labelled as an illustration, with credit), else a typed facsimile cover. */
function cover(r, big) {
  const medium = r.medium || r.classification?.medium;
  const type = r.document_type || r.classification?.document_type;
  const title = r.title_normalized || r.title || r.metadata?.title_normalized || r.metadata?.title;
  const ref = r.reference_code || r.source?.reference_code;
  const c = r.cover;
  const img = c ? `<img class="ill" src="${esc(c.thumb)}" alt="Photo: ${esc(c.label)}, ${c.year}" loading="lazy"
      onerror="this.parentElement.classList.remove('has-img');this.nextElementSibling?.remove();this.remove()">
    <div class="cap">${esc(c.label)} · ${c.year}</div>` : "";
  const credit = c && big ? `<p class="credit small muted">Illustration, not the document: a photograph of ${esc(c.label)} (${COVER_KIND[c.kind] || c.kind})
      taken in ${c.year}${c.year > c.record_year ? `, ${c.year - c.record_year} years after the record` : ", the record's year"}${c.distance_km != null ? `, ${c.distance_km} km away` : ""}.
      Photo: <a href="${esc(c.page)}" target="_blank" rel="noopener">${esc(c.author || c.credit || "Wikimedia Commons")}</a>${c.license ? `, ${esc(c.license)}` : ""},
      ${c.credit && c.author ? `${esc(c.credit)}, ` : ""}via Wikimedia Commons.</p>` : "";
  return `<div class="cover m-${(medium || "mixed").replace(/\s+/g, "-")}${c ? " has-img" : ""}">${img}
    <div class="ic" aria-hidden="true">${icon(TYPE_ICON[type] || MEDIUM_ICON[medium] || "file")}</div>
    <div class="ct">${esc(title)}</div>
    <div class="cr">${esc(ref)}</div></div>${credit}`;
}

const pv = (k) => `<span class="pv pv-${k}" title="Source of this value: ${k}">${k}</span>`;
const fmtDate = (d) => (d ? esc(String(d).replace("/..", " –").replace("../", "– ").replace("/", " – ")) : "—");

function setNav(name) {
  document.querySelectorAll(".mainnav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
  document.querySelectorAll(".navmenu").forEach((m) => m.classList.toggle("active", !!m.querySelector("a.active")));
  closeNavMenus();
}

/* Drop-down menus of the main navigation (Swiss Tales). The list is positioned under its button with fixed
   coordinates, so the phone layout's horizontally scrolling nav bar does not clip it. */
function closeNavMenus() {
  document.querySelectorAll(".navmenu.open").forEach((m) => { m.classList.remove("open"); m.querySelector(".navmenu-btn").setAttribute("aria-expanded", "false"); });
}
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".navmenu-btn");
  if (!btn) { if (!e.target.closest(".navmenu-list") || e.target.closest("a")) closeNavMenus(); return; }
  const m = btn.parentElement, open = !m.classList.contains("open");
  closeNavMenus();
  if (!open) return;
  const b = btn.getBoundingClientRect(), list = m.querySelector(".navmenu-list");
  list.style.top = `${b.bottom + 4}px`;
  list.style.left = `${Math.max(8, Math.min(b.left, innerWidth - 228))}px`;
  m.classList.add("open");
  btn.setAttribute("aria-expanded", "true");
  list.querySelector("a")?.focus({ preventScroll: true });
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeNavMenus(); });
addEventListener("scroll", closeNavMenus, { passive: true });
addEventListener("resize", closeNavMenus);

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
    <div class="tiles">${s.facets.document_type.map(([k, n]) => `<a class="tile" href="#/search?document_type=${encodeURIComponent(k)}"><b>${icon(TYPE_ICON[k] || "file")} ${esc(k)}</b><span>${n} document${n > 1 ? "s" : ""}</span></a>`).join("")}</div>
    <h2>By fonds</h2>
    <div class="tiles">${s.facets.fonds.slice(0, 8).map(([k, n]) => `<a class="tile" href="#/search?fonds=${encodeURIComponent(k)}"><b>${esc(k)}</b><span>${n} document${n > 1 ? "s" : ""}</span></a>`).join("")}</div>
    <h2>A few documents</h2>
    <div class="grid-cards">${featured.map((r) => `<a class="card" href="#/record/${r.id}">${cover(r)}<div class="t">${esc((LANG === "en" && r.title_en) || r.title)}</div><div class="small muted">${fmtDate(r.date)}</div></a>`).join("")}</div>`;
}

/* ---------------- Search: Gallica-style bar, filter flags and sort next to the search field ---------------- */
const FACET_TITLES = {
  flags: "Flags", document_type: "Document type", source_level: "Source level", medium: "Medium", century: "Century",
  level: "Level", decade: "Decade", fonds: "Fonds", language: "Language", creator: "Author / creator", publisher: "Publisher",
  subject: "Subject", person: "Person", place: "Place", preprocessing: "Preprocessing needed", qc: "Quality check", sample: "Sample group", batch: "Batch",
};
const PRIMARY_FACETS = ["document_type", "source_level", "medium", "century", "level", "flags"];
const FLAG_LABEL = { on_map: "Located on the map", story_map: "Has a story map", names_persons: "Names persons", wikidata_links: "Linked to Wikidata",
  personal_data: "Contains personal data", has_cover: "Has a cover image", has_description: "Has description text" };
const SEARCH_IN_LABEL = { all: "All fields", title: "Title", creator: "Author / creator", publisher: "Publisher", subject: "Subject",
  person: "Person", place: "Place", reference: "Reference code", resume: "Résumé & description" };
const SORT_LABEL = { relevance: "Relevance", date_asc: "Oldest first", date_desc: "Newest first", title: "Title A–Z", creator: "Author A–Z" };
const ADV_FIELDS = ["creator", "publisher", "subject", "person", "place"];
// the map's single-choice filters, also offered in the advanced panel; a choice replaces that facet's include flags
const ADV_SELECTS = ["document_type", "source_level", "medium", "century", "level", "fonds", "flags"];
const EVENT_COLORS = ["match", ["get", "event"], "creation", "#8a1c7c", "depicted", "#1d5fa6", "publication", "#a05a00", "#444"];
const facetLabel = (k, v) => (k === "preprocessing" ? PREP_LABEL[v] : k === "flags" ? FLAG_LABEL[v] : null) || v;
const centuryNum = (c) => parseInt(c, 10) || 99;

/* The header search keeps the current filters, field and sort when used on the search page (Gallica: refine within). */
function searchFromHeader(e) {
  e.preventDefault();
  const onSearch = location.hash.startsWith("#/search");
  const p = onSearch ? new URLSearchParams(location.hash.split("?")[1] || "") : new URLSearchParams();
  const q = $("#q").value.trim(), where = $("#qin").value;
  q ? p.set("q", q) : p.delete("q");
  where && where !== "all" ? p.set("in", where) : p.delete("in");
  p.delete("page");
  location.hash = "#/search?" + p.toString();
}

async function search(params) {
  setNav("search");
  window.__searchMap?.remove(); window.__searchMap = null;
  const size = [10, 20, 50].includes(+params.get("size")) ? +params.get("size") : 20;
  $("#q").value = params.get("q") || "";
  $("#qin").value = params.get("in") || "all";
  const mapOn = params.get("map") === "1";
  const api_p = new URLSearchParams(params); api_p.set("size", size); api_p.delete("adv"); api_p.delete("map");
  const map_p = new URLSearchParams(api_p); ["size", "page", "sort"].forEach((k) => map_p.delete(k));
  const [res, mapData] = await Promise.all([api("/api/records?" + api_p.toString()), mapOn ? api("/api/map?" + map_p.toString()) : null]);
  const page = +(params.get("page") || 1), sort = params.get("sort") === "date" ? "date_asc" : params.get("sort") || "relevance";
  const href = (fn) => { const p = new URLSearchParams(params); p.delete("page"); fn(p); return "#/search?" + p.toString(); };
  // Filter flags: each value cycles off -> include -> exclude ("!value"); groups AND-ed, values OR-ed (AND in flags/preprocessing).
  const state = (k, v) => { const vs = params.getAll(k); return vs.includes(v) ? "inc" : vs.includes("!" + v) ? "exc" : "off"; };
  const link = (k, v, to) => href((p) => {
    const rest = p.getAll(k).filter((x) => x !== v && x !== "!" + v); p.delete(k);
    rest.forEach((x) => p.append(k, x));
    if (to === "inc") p.append(k, v); else if (to === "exc") p.append(k, "!" + v);
  });
  const NEXT = { off: "inc", inc: "exc", exc: "off" };
  const TIP = { off: "Click to include", inc: "Included · click to exclude", exc: "Excluded · click to clear" };
  const active = [...params.entries()].filter(([k]) => FACET_TITLES[k]);
  const advOn = ["date_from", "date_to"].some((k) => params.get(k)) || params.get("adv") === "1";

  const values = (k) => {
    let vals = (res.facets[k] || []).map(([v, n]) => [String(v), n]);
    if (k === "century") vals.sort((a, b) => centuryNum(a[0]) - centuryNum(b[0]));
    if (k === "decade") vals.sort((a, b) => a[0].localeCompare(b[0]));
    params.getAll(k).map((x) => x.replace(/^!/, "")).forEach((v) => { if (!vals.some(([w]) => w === v)) vals.push([v, 0]); });
    return vals;
  };
  const row = (k) => ([v, n]) => { const st = state(k, v); return `<li data-v="${esc(facetLabel(k, v).toLowerCase())}"><a class="flag ${st}" href="${link(k, v, NEXT[st])}" title="${TIP[st]}" role="checkbox" aria-checked="${st === "inc" ? "true" : st === "exc" ? "mixed" : "false"}">
      <i class="box">${st === "inc" ? "✓" : st === "exc" ? "−" : ""}</i><span>${esc(facetLabel(k, v))}</span><span>${n}</span></a></li>`; };
  const pill = (k) => {
    const vals = values(k);
    if (!vals.length) return "";
    const on = vals.filter(([v]) => state(k, v) !== "off").length;
    const long = vals.length > 12;
    return `<details class="pill ${on ? "on" : ""}" data-k="${k}"><summary>${FACET_TITLES[k]}${on ? ` <b class="fcount">${on}</b>` : ""} <span class="caret">▾</span></summary>
      <div class="pop">${long ? `<input class="pfind" type="search" placeholder="Filter ${esc(FACET_TITLES[k].toLowerCase())}…" aria-label="Filter values">` : ""}
        <ul>${vals.map(row(k)).join("")}</ul></div></details>`;
  };
  const more = Object.keys(FACET_TITLES).filter((k) => !PRIMARY_FACETS.includes(k));
  const moreOn = more.reduce((n, k) => n + params.getAll(k).length, 0);
  const b = res.date_bounds || [1400, 2025];
  const options = (k) => (res.facets[k] || []).filter(([v]) => v !== "unknown").map(([v]) => `<option value="${esc(String(v))}">`).join("");
  const selectField = (k) => {
    const vals = values(k), inc = params.getAll(k).filter((v) => !v.startsWith("!"));
    if (!vals.length) return "";
    const keep = inc.length > 1 ? `<option value="__keep" selected>${inc.length} selected</option>` : "";
    return `<div class="adv-f"><label for="adv-${k}">${FACET_TITLES[k]}</label><select id="adv-${k}" name="${k}"><option value="">any</option>${keep}
      ${vals.map(([v, n]) => `<option value="${esc(v)}" ${inc.length === 1 && inc[0] === v ? "selected" : ""}>${esc(facetLabel(k, v))} (${n})</option>`).join("")}</select></div>`;
  };

  app.innerHTML = `
    <div class="filterbar" role="search" aria-label="Filters and sort">
      <div class="pills">${PRIMARY_FACETS.map(pill).join("")}
        <details class="pill morefilters ${moreOn ? "on" : ""}"><summary>More filters${moreOn ? ` <b class="fcount">${moreOn}</b>` : ""} <span class="caret">▾</span></summary>
          <div class="pop wide">${more.map((k) => { const vals = values(k); if (!vals.length) return ""; const on = vals.filter(([v]) => state(k, v) !== "off").length;
            return `<details class="fgroup" data-k="${k}" ${on ? "open" : ""}><summary>${FACET_TITLES[k]}${on ? ` <b class="fcount">${on}</b>` : ""}</summary>
              ${vals.length > 12 ? `<input class="pfind" type="search" placeholder="Filter…" aria-label="Filter values">` : ""}<ul>${vals.map(row(k)).join("")}</ul></details>`; }).join("")}</div></details>
        <a class="pill-link ${advOn ? "on" : ""}" href="${href((p) => (advOn ? (p.delete("adv"), p.delete("date_from"), p.delete("date_to")) : p.set("adv", "1")))}">${advOn ? "Hide advanced" : "Advanced search"}</a>
      </div>
      <div class="sortbar">
        <span class="small muted">Sort</span>
        <div class="seg" role="radiogroup" aria-label="Sort results">${Object.entries(SORT_LABEL).map(([k, l]) => `<a role="radio" aria-checked="${k === sort}" class="${k === sort ? "on" : ""}" href="${href((p) => (k === "relevance" ? p.delete("sort") : p.set("sort", k)))}">${l}</a>`).join("")}</div>
        <label class="small muted">Per page <select id="psize">${[10, 20, 50].map((n) => `<option ${n === size ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      </div>
    </div>
    ${advOn ? `<form class="advanced" id="advform">
      <div class="adv-grid">
        <div class="adv-f adv-words"><label for="adv-q">Words</label>
          <div class="adv-row"><select name="in" aria-label="Search in">${Object.entries(SEARCH_IN_LABEL).map(([k, l]) => `<option value="${k}" ${k === (params.get("in") || "all") ? "selected" : ""}>${l}</option>`).join("")}</select>
            <input id="adv-q" name="q" type="search" value="${esc(params.get("q") || "")}" placeholder="all of these words"></div></div>
        <div class="adv-f"><label for="adv-date_from">Date</label>
          <div class="adv-row"><input id="adv-date_from" name="date_from" type="number" inputmode="numeric" min="${b[0]}" max="${b[1]}" placeholder="${b[0]}" value="${esc(params.get("date_from") || "")}" aria-label="From year">
            <span class="muted">to</span> <input name="date_to" type="number" inputmode="numeric" min="${b[0]}" max="${b[1]}" placeholder="${b[1]}" value="${esc(params.get("date_to") || "")}" aria-label="To year"></div></div>
        ${ADV_SELECTS.map(selectField).join("")}
        ${ADV_FIELDS.map((k) => `<div class="adv-f"><label for="adv-${k}">${FACET_TITLES[k]}</label><input id="adv-${k}" name="${k}" list="dl-${k}" placeholder="any"><datalist id="dl-${k}">${options(k)}</datalist></div>`).join("")}
      </div>
      <div class="adv-actions"><button type="submit">Apply</button>
        <button type="submit" class="btn-map ${mapOn ? "on" : ""}" name="map" value="${mapOn ? "0" : "1"}" aria-pressed="${mapOn}">${icon("map")} ${mapOn ? "Hide map" : "Show map"}</button>
        <a href="#/search?adv=1${mapOn ? "&map=1" : ""}">Reset all</a>
        <span class="small muted">Dates match records whose date range overlaps the period. Document type to flags replace that filter's choice; author, publisher, subject, person and place add an include flag (pick a suggestion for an exact value). The map shows where the filtered records are located.</span></div>
    </form>` : ""}
    <div class="${mapOn ? "withmap" : ""}">
    ${mapOn ? `<aside class="resmap" aria-label="Map of the filtered records">
      <div class="resmap-head"><b>${icon("map")} Map of these results</b><a class="resmap-x" href="${href((p) => p.delete("map"))}" title="Hide map" aria-label="Hide map">${icon("x")}</a></div>
      <div id="resmap" class="resmap-map"></div>
      <div class="resmap-foot">
        <div class="legend">${["creation", "depicted", "publication"].map((k) => `<span><i style="background:var(--c)" class="ev-${k}"></i>${EVENT_LABEL[k]}</span>`).join("")}<span><i class="trip"></i>Journey to the Federal Archives</span></div>
        <p class="small muted" id="resmaplab"></p></div></aside>` : ""}
    <div class="rescol">
    <div class="resbar">
      <div><b>${res.total}</b> result${res.total === 1 ? "" : "s"}${params.get("q") ? ` for “${esc(params.get("q"))}”${params.get("in") && params.get("in") !== "all" ? ` in ${esc(SEARCH_IN_LABEL[params.get("in")] || params.get("in"))}` : ""}` : ""}
        ${params.get("date_from") || params.get("date_to") ? ` · dated ${esc(params.get("date_from") || "…")}–${esc(params.get("date_to") || "…")}` : ""} · sorted by ${SORT_LABEL[sort].toLowerCase()}</div>
      ${active.length || params.get("q") || params.get("date_from") || params.get("date_to") ? `<a class="small" href="#/search${advOn ? "?adv=1" : ""}">Clear search</a>` : ""}
    </div>
    ${active.length ? `<div class="chips">${active.map(([k, v]) => { const exc = v.startsWith("!"), w = exc ? v.slice(1) : v; return `<a class="chip x ${exc ? "exc" : ""}" href="${link(k, w, "off")}">${FACET_TITLES[k]}: ${exc ? "not " : ""}${esc(facetLabel(k, w))} ${icon("x")}</a>`; }).join("")}</div>` : ""}
    <section class="results">
      ${res.results.map((r) => `
        <article class="result">
          <a href="#/record/${r.id}">${cover(r)}</a>
          <div>
            <h3><a href="#/record/${r.id}">${esc(r.title_normalized || r.title)}</a></h3>
            <div class="badges"><span class="badge">${esc(r.document_type)}</span><span class="badge lvl-${r.source_level}">${esc(r.source_level)} source</span>${r.qc_ok ? "" : `<span class="badge qc-bad">QC issue</span>`}${r.n_places ? `<span class="badge">${icon("pin")} ${r.n_places}</span>` : ""}</div>
            <div class="meta-line"><b>Date</b> ${fmtDate(r.date)} · <b>Creator</b> ${esc(r.creator || "—")} · <b>Fonds</b> ${esc(r.fonds || "—")}</div>
            <div class="meta-line muted small">${esc(r.reference_code)}</div>
            ${r.resume ? `<p class="resume">${esc(r.resume)}</p>` : ""}
          </div>
        </article>`).join("") || `<p class="muted">No documents match.</p>`}
      ${pager(page, Math.ceil(res.total / size), (n) => href((p) => p.set("page", n)))}
    </section></div></div>`;

  // one popover open at a time; Escape or a click outside closes it
  const pills = [...document.querySelectorAll(".filterbar .pill")];
  pills.forEach((d) => d.addEventListener("toggle", () => { if (d.open) pills.forEach((o) => o !== d && (o.open = false)); }));
  if (!window.__pillsWired) {  // installed once; looks up the current pills at event time
    window.__pillsWired = true;
    const closeAll = () => document.querySelectorAll(".filterbar .pill[open]").forEach((d) => (d.open = false));
    document.addEventListener("click", (e) => { if (!e.target.closest(".filterbar .pill")) closeAll(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAll(); });
  }
  document.querySelectorAll(".pfind").forEach((inp) => (inp.oninput = () => {
    const t = inp.value.toLowerCase();
    inp.parentElement.querySelectorAll("li").forEach((li) => (li.hidden = t && !li.dataset.v.includes(t)));
  }));
  $("#psize").onchange = (e) => (location.hash = href((p) => p.set("size", e.target.value)));
  const form = $("#advform");
  if (form) form.onsubmit = (e) => {
    e.preventDefault();
    const f = new FormData(form);
    location.hash = href((p) => {
      p.set("adv", "1");
      for (const k of ["q", "in", "date_from", "date_to"]) { const v = (f.get(k) || "").trim(); v && !(k === "in" && v === "all") ? p.set(k, v) : p.delete(k); }
      for (const k of ADV_SELECTS) {
        const v = f.get(k);
        if (v == null || v === "__keep") continue;
        const exc = p.getAll(k).filter((x) => x.startsWith("!")); p.delete(k);
        exc.forEach((x) => x !== "!" + v && p.append(k, x));
        if (v) p.append(k, v);
      }
      for (const k of ADV_FIELDS) { const v = (f.get(k) || "").trim(); if (v && !p.getAll(k).includes(v)) p.append(k, v); }
      if (e.submitter?.name === "map") e.submitter.value === "1" ? p.set("map", "1") : p.delete("map");
    });
  };
  if (mapOn) resultsMap(mapData, new Set(res.results.map((r) => r.id)));
}

/* Map next to the search results: every located event of the filtered records (not only this page);
   the records on this page are drawn larger, and hovering a result highlights its places. */
function resultsMap(data, onPage) {
  const { points, archive } = data;
  const fc = (features) => ({ type: "FeatureCollection", features });
  const feats = fc(points.map((p, i) => ({ type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    properties: { i, id: p.id, event: p.event, cur: onPage.has(p.id) } })));
  // travel line per record: its located events in story order, then on to the Federal Archives
  const byRec = new Map();
  points.forEach((p) => byRec.set(p.id, [...(byRec.get(p.id) || []), [p.lon, p.lat]]));
  const trips = fc([...byRec].map(([id, ll]) => ({ type: "Feature", properties: { id, cur: onPage.has(id) },
    geometry: { type: "LineString", coordinates: [...ll, [archive.lon, archive.lat]] } })));
  const docs = new Set(points.map((p) => p.id)), here = [...docs].filter((id) => onPage.has(id)).length;
  $("#resmaplab").innerHTML = points.length
    ? `${points.length} located event${points.length === 1 ? "" : "s"} from <b>${docs.size}</b> of ${data.records} filtered record${data.records === 1 ? "" : "s"}
       (${here} on this page, drawn larger).`
    : `None of the ${data.records} filtered record${data.records === 1 ? "" : "s"} has a located place.`;
  const map = baseMap($("#resmap"), (m) => {
    m.addSource("trips", { type: "geojson", data: trips });
    m.addLayer({ id: "trips", type: "line", source: "trips", layout: { "line-join": "round" }, paint: {
      "line-color": "#b5121b", "line-dasharray": [2.4, 2.4],
      "line-width": ["case", ["get", "cur"], 2, 1.2], "line-opacity": ["case", ["get", "cur"], 0.8, 0.3] } });
    m.addLayer({ id: "trips-hl", type: "line", source: "trips", filter: ["==", ["get", "id"], ""], layout: { "line-join": "round" },
      paint: { "line-color": "#b5121b", "line-width": 3.5, "line-opacity": 1 } });
    m.addSource("pts", { type: "geojson", data: feats });
    m.addLayer({ id: "pts", type: "circle", source: "pts", paint: {
      "circle-radius": ["case", ["get", "cur"], 7, 4.5], "circle-color": EVENT_COLORS, "circle-opacity": ["case", ["get", "cur"], 0.95, 0.55],
      "circle-stroke-color": "#fff", "circle-stroke-width": ["case", ["get", "cur"], 2, 1] } });
    m.addLayer({ id: "hl", type: "circle", source: "pts", filter: ["==", ["get", "id"], ""], paint: {
      "circle-radius": 11, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#b5121b", "circle-stroke-width": 3 } });
  }, { center: [8.2, 46.8], zoom: 6 });
  window.__searchMap = map;
  if (points.length) {
    const b = new maplibregl.LngLatBounds();
    points.forEach((p) => b.extend([p.lon, p.lat]));
    map.fitBounds(b, { padding: 36, maxZoom: 10, duration: 0 });
  }
  new maplibregl.Marker({ element: eventIcon({ event: "holding" }, {}, 0) }).setLngLat([archive.lon, archive.lat])
    .setPopup(new maplibregl.Popup({ offset: 14 }).setHTML(`<b>${esc(archive.name)}</b><br>${esc(archive.place)}`)).addTo(map);
  map.on("click", "pts", (e) => {
    const p = points[e.features[0].properties.i];
    new maplibregl.Popup({ offset: 8 }).setLngLat([p.lon, p.lat])
      .setHTML(`<a href="#/record/${p.id}"><b>${esc(p.title)}</b></a><br>${EVENT_LABEL[p.event] || esc(p.event)} · ${esc(p.place || "")} · ${fmtDate(p.date || p.start)}`).addTo(map);
  });
  map.on("mouseenter", "pts", () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", "pts", () => { map.getCanvas().style.cursor = ""; });
  const hl = (id) => { if (!map.getLayer("hl")) return; map.setFilter("hl", ["==", ["get", "id"], id]); map.setFilter("trips-hl", ["==", ["get", "id"], id]); };
  document.querySelectorAll(".results .result").forEach((a) => {
    const id = a.querySelector("h3 a")?.getAttribute("href")?.split("/").pop() || "";
    a.addEventListener("mouseenter", () => hl(id));
    a.addEventListener("mouseleave", () => hl(""));
  });
}

function pager(page, pages, hrefFor) {
  if (pages <= 1) return "";
  const nums = [...new Set([1, page - 2, page - 1, page, page + 1, page + 2, pages])].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  let out = "", prev = 0;
  for (const n of nums) {
    if (n - prev > 1) out += `<span class="gap">…</span>`;
    out += n === page ? `<span class="cur">${n}</span>` : `<a href="${hrefFor(n)}">${n}</a>`;
    prev = n;
  }
  return `<nav class="pager" aria-label="Pages">${page > 1 ? `<a href="${hrefFor(page - 1)}">‹</a>` : ""}${out}${page < pages ? `<a href="${hrefFor(page + 1)}">›</a>` : ""}</nav>`;
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
  const pts = [], pins = [];
  let n = 0;
  const seen = new Map();
  (r.story || []).forEach((e) => {
    if (e.lat == null) return;
    n += 1;
    const key = `${e.lat.toFixed(4)},${e.lon.toFixed(4)}`;
    const k = seen.get(key) || 0; seen.set(key, k + 1);
    const ll = [e.lat + k * 0.0009, e.lon + k * 0.0012];  // nudge stacked points apart
    pins.push(new maplibregl.Marker({ element: eventIcon(e, r, n) }).setLngLat([ll[1], ll[0]])
      .setPopup(new maplibregl.Popup({ offset: 14 }).setHTML(`<b>${n}. ${EVENT_LABEL[e.event] || e.event}</b><br>${fmtDate(e.date)}${e.place ? " · " + esc(e.place) : ""}<br><span class="small">${esc(e.description || "")}</span>`)));
    pts.push(ll);
  });
  const view = pts.length
    ? { bounds: pts.reduce((b, [la, lo]) => b.extend([lo, la]), new maplibregl.LngLatBounds()), fitBoundsOptions: { padding: 50, maxZoom: 10 } }
    : { center: [8.2, 46.8], zoom: 6 };
  const map = baseMap(el, (m) => {
    if (pts.length < 2) return;
    m.addSource("route", { type: "geojson", data: lineGeo(pts) });
    m.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": "#b5121b", "line-width": 2.5, "line-dasharray": [2.4, 2.4], "line-opacity": 0.85 } });
  }, view);
  pins.forEach((p) => p.addTo(map));
  setTimeout(() => map.resize(), 50);
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
  return `<div class="callout">${q.ok ? `${icon("check")} Passed the automatic checks (structure, dates).` : `${icon("alert")} Did not pass every automatic check.`}</div>
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
  return `<div class="badges trust-badges">
      <span class="badge lvl-${r.classification.source_level}">${esc(r.classification.source_level)} source</span>
      <span class="badge">confidence ${conf != null ? conf : "–"}</span>
      <span class="badge" title="${esc(edits.map((e) => `${e.field}: ${e.actor} — ${e.reason}`).join(" | "))}">${edits.length} logged edit${edits.length === 1 ? "" : "s"}</span>
    </div>
    <section class="band band-evidence"><h3>Evidence <small>the record itself · Swiss Federal Archives</small></h3>
      <table class="dl">${ev}</table>
      <p class="small"><a href="${r.source.portal_url}" target="_blank" rel="noopener">Open in the archive's online search ↗</a></p></section>
    <section class="band band-context"><h3>Context <small>reference works · secondary / tertiary</small></h3><ul class="ctx">${ctx}</ul></section>
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
        ${LANG === "en" ? `<div class="muted">${esc(r.metadata.title_en || "")}</div>` : ""}
        ${r.classification.resume ? `<div class="resume-box"><span id="resume-text" translate="no">${esc(r.classification.resume)}</span> ${pv("apertus")}
          <div><button class="more-btn" id="morebtn">See more ▾</button></div><div id="more"></div></div>` : `<p class="muted small">Résumé disabled in config.</p>`}
        ${r.classification.source_level !== "primary" ? `<div id="topic"></div>` : ""}
        <div id="inquiry"></div>
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
  if (LANG !== "en" && $("#resume-text")) api(`/api/records/${id}/resume`).then((x) => { if ($("#resume-text") && x.resume) $("#resume-text").textContent = x.resume; }).catch(() => {});
  recordInquiry(r);
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
    ${Object.entries(qc.batches || {}).map(([name, b]) => {
      const mr = b.manual_review, sl = b.source_level_vs_evidence;
      return `<h2>Batch ${esc(name)}: ${(b.online ?? b.records).toLocaleString()} more records</h2>
      <p class="muted">Drawn over source tiers, record types and eras, processed by the same pipeline and verified before going online
      (<a href="https://github.com/Anakalypto/CORA-Apertus/blob/main/docs/batch10k_verification.md" target="_blank">verification report</a>).</p>
      <div class="kpis">
        ${kpi(b.processed_ok_pct, "processed correctly (no structural or critical error)", 80, 60)}
        ${kpi(b.structural_error_pct, "structural errors (target < 5%)", -1, -1)}
        ${kpi(b.entity_grounding_pct, `named entities in the source (${b.entities.toLocaleString()} entities)`)}
        ${kpi(b.date_created_in_range_pct, "creation dates inside the record's date range")}
        ${sl ? kpi(sl.agreement_pct, `source level = archival evidence (${sl.n.toLocaleString()} secondary/tertiary records)`) : ""}
        ${mr ? kpi(Math.round(100 * (mr.reviewed - verdict(mr, "major_errors")) / mr.reviewed), `manual review: no major error (${mr.reviewed} records, ${verdict(mr, "correct")} fully correct)`) : ""}
      </div>`;
    }).join("")}
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
const EXHIBIT = (i) => String.fromCharCode(65 + (i % 26)) + (i >= 26 ? Math.floor(i / 26) : "");
const caseNo = (q) => { let h = 7; for (const c of q) h = (h * 31 + c.charCodeAt(0)) >>> 0; return `CORA-${new Date().getFullYear()}-${String(h % 10000).padStart(4, "0")}`; };
const today = () => new Date().toLocaleDateString(LOCALE, { day: "2-digit", month: "long", year: "numeric" });
const CASELOG_KEY = "cora.caselog";
const caseLog = () => { try { return JSON.parse(localStorage.getItem(CASELOG_KEY) || "[]"); } catch { return []; } };
const logCase = (q, verdict) => {
  try { localStorage.setItem(CASELOG_KEY, JSON.stringify([{ q, verdict, at: Date.now() }, ...caseLog().filter((c) => c.q !== q)].slice(0, 8))); } catch { /* private mode: no case log */ }
};

/* Report + exhibits for one answer of /api/ask. `mini` is the compact form used on record pages. */
function caseReport(r, { mini = false, focus = null } = {}) {
  const ex = {}; (r.citations || []).forEach((c, i) => (ex[c.id] = EXHIBIT(i)));
  const verdict = !r.sentences.length ? "closed" : r.insufficient || !r.answered ? "partial" : "supported";
  const stamp = { supported: "Supported by the files", partial: "Partly answered", closed: "Case closed · no matching file" }[verdict];
  const findings = r.sentences.length
    ? r.sentences.map((s) => `<span class="inq-claim${s.uncited ? " unv" : ""}">${esc(s.text)}${s.sources.map((id) =>
        `<a class="exh-ref" href="#/record/${id}" title="${id === focus ? "This record" : "Exhibit " + ex[id]}">${id === focus && mini ? "★" : ex[id]}</a>`).join("")}${s.uncited ? `<span class="inq-unv" title="No pulled file supports this sentence">unverified</span>` : ""}</span>`).join(" ")
    : `<p>${esc(r.message || "The files pulled from the stacks do not answer this question.")}</p>`;
  const exhibits = (r.citations || []).map((c, i) => `<a class="inq-exhibit" href="#/record/${c.id}">
      <span class="inq-tag">${c.id === focus ? "This record" : "Exhibit " + EXHIBIT(i)}</span>
      <span class="inq-ex-type">${icon(TYPE_ICON[c.document_type] || "file")} ${esc(c.document_type || "")}${c.source_level ? ` · ${esc(c.source_level)}` : ""}</span>
      <b>${esc(c.title)}</b>
      <span class="inq-ex-meta">${fmtDate(c.date)} · <code>${esc(c.reference_code)}</code></span></a>`).join("");
  if (mini) return `<div class="inq-mini-report">${findings}
      <div class="inq-mini-foot"><span class="inq-stamp sm ${verdict}">${stamp}</span>
      ${(r.citations || []).filter((c) => c.id !== focus).map((c) => `<a href="#/record/${c.id}" class="small">Exhibit ${ex[c.id]}: ${esc(c.title)}</a>`).join(" · ")}</div></div>`;
  return `<article class="inq-report">
      <div class="inq-report-head"><span>Investigation report</span><span>Case Nº ${caseNo(r.question)}</span><span>${today()}</span></div>
      <p class="inq-q"><span>Inquiry</span>“${esc(r.question)}”</p>
      <div class="inq-findings">${findings}</div>
      <span class="inq-stamp ${verdict}">${stamp}</span>
      <p class="inq-report-foot">${r.sentences.length ? `Drafted by Apertus${r.model ? ` (${esc(r.model)})` : ""}${r.seconds ? ` in ${r.seconds} s` : ""} from ${(r.retrieved || []).length} files pulled from the stacks.
        Every claim points to an exhibit; a claim without one is marked unverified.` : `The archivist searched the catalogue and found no file relevant enough, so no report was drafted. No file, no claim.`}</p>
    </article>
    ${exhibits ? `<h2 class="inq-h">Exhibits <small>${(r.citations || []).length} file${(r.citations || []).length > 1 ? "s" : ""} cited</small></h2><div class="inq-exhibits">${exhibits}</div>` : ""}
    ${(r.retrieved || []).length ? `<details class="inq-drawer"><summary>Files pulled but not cited (${(r.retrieved || []).filter((h) => !ex[h.id]).length})</summary><ul>${(r.retrieved || []).filter((h) => !ex[h.id]).map((h) =>
      `<li><a href="#/record/${h.id}">${esc(h.id)}</a> <span class="muted">catalogue score ${h.score ?? "–"}${h.matched_terms?.length ? ` · matched ${esc(h.matched_terms.join(", "))}` : ""}</span></li>`).join("") || "<li class='muted'>None: every file pulled was cited.</li>"}</ul></details>` : ""}`;
}

/* Ask the archive: a conversation with Apertus, presented as a running case on the investigation desk.
   Cited records become lettered exhibits that keep their letter for the whole case; Wikipedia articles are references. */
const CHAT_KEY = "cora.chat", CASES_KEY = "cora.cases";
const newCase = (record = null) => ({ id: `${Date.now().toString(36)}`, record, turns: [], exhibits: {}, opened: Date.now() });
const loadChat = () => { try { const c = JSON.parse(sessionStorage.getItem(CHAT_KEY) || "null"); return c && c.turns ? { exhibits: {}, ...c } : newCase(); } catch { return newCase(); } };
const savedCases = () => { try { return JSON.parse(localStorage.getItem(CASES_KEY) || "[]"); } catch { return []; } };
const saveChat = (c) => {
  try {
    sessionStorage.setItem(CHAT_KEY, JSON.stringify(c));
    if (c.turns.some((t) => t.response)) localStorage.setItem(CASES_KEY, JSON.stringify([c, ...savedCases().filter((x) => x.id !== c.id)].slice(0, 8)));
  } catch { /* storage unavailable: the case lives for this page only */ }
};
const caseNumber = (c) => `CORA-${new Date(c.opened).getFullYear()}-${String(parseInt(c.id, 36) % 10000).padStart(4, "0")}`;
const openedOn = (c) => new Date(c.opened).toLocaleDateString(LOCALE, { day: "2-digit", month: "long", year: "numeric" });
const verdictOf = (r) => {
  if (!r || !r.paragraphs.length) return "closed";
  const sents = r.paragraphs.flat();
  if (sents.some((s) => s.own_knowledge)) return "partial";
  return r.sources.some((s) => s.kind === "record") ? "supported" : "context";
};
const STAMP = { supported: "Supported by the files", context: "Context from reference works", partial: "Partly Apertus' own knowledge", closed: "No answer drafted" };

function deskReport(t, n, c) {
  if (t.error) return `<article class="inq-report case-turn"><p class="inq-q"><span>Inquiry ${n}</span>“${esc(t.q)}”</p>
    <div class="inq-findings"><p>The archivist could not complete this inquiry: ${esc(t.error)}</p></div><span class="inq-stamp closed">${STAMP.closed}</span><p class="inq-report-foot"></p></article>`;
  if (!t.response) return `<article class="inq-report case-turn pending"><p class="inq-q"><span>Inquiry ${n}</span>“${esc(t.q)}”</p>
    <ol class="inq-progress">${["Reading the case so far", "Pulling files from the stacks", "Consulting reference works", "Apertus is drafting the report"].map((s, i) => `<li data-i="${i}">${s}</li>`).join("")}</ol></article>`;
  const r = t.response, refNo = {};
  r.sources.filter((s) => s.kind === "wikipedia").forEach((s, i) => (refNo[s.ref] = i + 1));
  const tagOf = (s) => (s.kind === "record" ? c.exhibits[s.id] : `Ref. ${refNo[s.ref]}`);
  const byRef = Object.fromEntries(r.sources.map((s) => [s.ref, s]));
  const card = (s) => s.kind === "record"
    ? `<span class="exh-card" hidden><span class="inq-tag">Exhibit ${c.exhibits[s.id]}</span>
        <span class="inq-ex-type">${icon(TYPE_ICON[s.document_type] || "file")} ${esc(s.document_type)} · ${esc(s.source_level)} source</span>
        <b>${esc(s.title)}</b><span class="inq-ex-meta">${fmtDate(s.date)} · ${esc(s.reference_code)}</span></span>`
    : `<span class="exh-card ref" hidden><span class="inq-tag">Reference ${refNo[s.ref]}</span>
        <span class="inq-ex-type">${icon("book")} Wikipedia (${esc(s.lang)}) · tertiary · CC BY-SA</span><b>${esc(s.title)}</b></span>`;
  const marks = (refs) => refs.map((f) => { const s = byRef[f]; if (!s) return "";
    return s.kind === "record" ? `<a class="exh-ref" href="#/record/${s.id}" aria-label="Exhibit ${c.exhibits[s.id]}: ${esc(s.title)}">${c.exhibits[s.id]}${card(s)}</a>`
      : `<a class="exh-ref ref" href="${s.url}" target="_blank" rel="noopener" aria-label="Reference ${refNo[f]}: ${esc(s.title)} (Wikipedia)">${refNo[f]}${card(s)}</a>`; }).join("");
  const findings = r.paragraphs.map((p) => `<p>${p.map((s) => `<span class="inq-claim${s.own_knowledge ? " unv" : s.weakly_supported ? " weak" : ""}"
      ${s.weakly_supported ? `title="Few of its words occur in the cited source (support ${s.support})"` : ""}>${esc(s.text)}${marks(s.sources)}${s.own_knowledge
      ? `<span class="inq-unv" title="No source of this inquiry states it: Apertus' own knowledge">unverified</span>` : ""}</span>`).join(" ")}</p>`).join("");
  const v = verdictOf(r);
  return `<article class="inq-report case-turn">
    <p class="inq-q"><span>Inquiry ${n}</span>“${esc(t.q)}”</p>
    <div class="inq-findings">${findings || "<p>No report could be drafted.</p>"}</div>
    <span class="inq-stamp ${v === "context" ? "partial" : v}">${STAMP[v]}</span>
    <p class="inq-report-foot">Drafted by Apertus${r.model ? ` (${esc(r.model)})` : ""}${r.seconds ? ` in ${r.seconds} s` : ""} from ${r.offered.records} file${r.offered.records === 1 ? "" : "s"} pulled
      from the stacks and ${r.offered.wikipedia} reference work${r.offered.wikipedia === 1 ? "" : "s"}. Letters point to exhibits, numbers to references (hover or tap one to see it);
      ${r.own_knowledge_sentences ? `${r.own_knowledge_sentences} claim${r.own_knowledge_sentences > 1 ? "s" : ""} with neither ${r.own_knowledge_sentences > 1 ? "are" : "is"} marked unverified.` : "every claim points to one."}</p>
  </article>`;
}

function wireExhibitCards() {
  if (window.__exhCards) return;
  window.__exhCards = true;
  const tip = document.createElement("div");
  tip.className = "exh-tip"; tip.hidden = true; tip.setAttribute("role", "tooltip");
  document.body.append(tip);
  let cur = null, touch = false;
  const hide = () => { tip.hidden = true; cur = null; };
  const show = (a) => {
    const cardEl = a.querySelector(".exh-card");
    if (!cardEl) return;
    cur = a; tip.className = "exh-tip" + (cardEl.classList.contains("ref") ? " ref" : ""); tip.innerHTML = cardEl.innerHTML; tip.hidden = false;
    const r = a.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    const top = r.top - h - 8 >= 8 ? r.top - h - 8 : r.bottom + 8;
    tip.style.left = left + "px"; tip.style.top = top + "px";
  };
  const refOf = (e) => e.target.closest?.(".exh-ref");
  document.addEventListener("pointerdown", (e) => { touch = e.pointerType !== "mouse"; if (!refOf(e) && !e.target.closest?.(".exh-tip")) hide(); });
  document.addEventListener("pointerover", (e) => { const a = refOf(e); if (a && e.pointerType === "mouse") show(a); });
  document.addEventListener("pointerout", (e) => { const a = refOf(e); if (a && e.pointerType === "mouse" && !a.contains(e.relatedTarget)) hide(); });
  document.addEventListener("focusin", (e) => { const a = refOf(e); if (a && !touch) show(a); });
  document.addEventListener("focusout", (e) => { if (refOf(e)) hide(); });
  document.addEventListener("click", (e) => { const a = refOf(e); if (a && touch && cur !== a) { e.preventDefault(); show(a); } });
  document.addEventListener("scroll", hide, true);
  addEventListener("hashchange", hide);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
}

async function askPage(params) {
  wireExhibitCards();
  setNav("ask");
  // the desk fits the screen under the top bar: the page itself does not scroll, the case and the board do
  const fitHdr = () => document.documentElement.style.setProperty("--hdr", $(".topbar").offsetHeight + "px");
  fitHdr(); document.body.classList.add("fit-page");
  if (!window.__fitWired) { window.__fitWired = true; addEventListener("resize", fitHdr); }
  let c = loadChat();
  const rec = params.get("record"), reopen = params.get("case");
  if (reopen) { const found = savedCases().find((x) => x.id === reopen); if (found) c = { exhibits: {}, ...found }; }
  else if (rec && c.record !== rec) c = newCase(rec);
  else if (!rec && c.record && params.get("q")) c = newCase();
  const starters = ["What do the photographs of the Swiss Active Service 1914–1918 show, and who commanded the army?",
    "Why did Swiss men reject women's suffrage in 1959?", "What did Swiss television report about Indira Gandhi?",
    "Welche Vorstösse gab es zur Kinderbetreuung?", "What was the Swissair trial about?"];
  app.innerHTML = `<div class="inq">
    <header class="inq-head">
      <div class="inq-kicker">Swiss Federal Archives · Investigation desk</div>
      <h1>Ask the archive</h1>
      <p>Open a case and keep asking. The archivist pulls the matching files from the stacks and the reference works,
      Apertus drafts a report for each inquiry, and every claim points to an exhibit (a record of the archive) or a reference (Wikipedia).
      A claim with neither is marked unverified. ${pv("apertus")}</p>
    </header>
    <div class="inq-desk">
      <section class="inq-folder case-file">
        <div class="case-top"><div class="inq-tab" id="casetab"></div><button type="button" class="btn-ghost" id="newcase">${icon("refresh")} New case</button></div>
        ${c.record ? `<p class="inq-focus">Case concerns record <a href="#/record/${esc(c.record)}">${esc(c.record)}</a>: it is always one of the files. · <a href="#/ask" id="unfocus">search the whole archive instead</a></p>` : ""}
        <div id="thread" aria-live="polite"></div>
        <form id="caseform" class="case-composer">
          <label for="caseq" id="caselabel">Line of inquiry</label>
          <textarea id="caseq" rows="2" placeholder="e.g. What do the records show about Swiss football abroad?"></textarea>
          <div class="inq-folder-foot"><span id="casefoot"></span><button id="casebtn">Ask</button></div>
        </form>
      </section>
      <aside class="inq-board" id="board"></aside>
    </div></div>`;
  const thread = $("#thread"), ta = $("#caseq");
  let tick = null;
  // the thread scrolls on its own, not the page: open on the latest inquiry (its question, then the answer below it)
  const toLatest = (smooth) => { const t = thread.querySelectorAll(".case-turn")[c.turns.length - 1];
    if (t) thread.scrollTo({ top: t.offsetTop - 6, behavior: smooth ? "smooth" : "auto" }); };
  const render = () => {
    $("#casetab").textContent = `Case file Nº ${c.turns.length ? caseNumber(c) : "— new —"}${c.turns.length ? ` · opened ${openedOn(c)} · ${c.turns.length} inquir${c.turns.length === 1 ? "y" : "ies"}` : ""}`;
    $("#caselabel").textContent = c.turns.length ? "Next line of inquiry" : "Line of inquiry";
    ta.placeholder = c.turns.length ? "Follow up: ask about a person, a place, the context…" : "e.g. What do the records show about Swiss football abroad?";
    $("#casefoot").textContent = c.turns.length ? "Follow-ups use the whole case so far" : `Opened ${openedOn(c)} · Investigator: you · Holdings: the classified records of CORA and Wikipedia`;
    thread.innerHTML = c.turns.map((t, i) => deskReport(t, i + 1, c)).join("");
    const last = c.turns.at(-1)?.response;
    const leads = last?.follow_ups?.length ? last.follow_ups : c.turns.length ? [] : starters;
    const allEx = Object.entries(c.exhibits).sort((a, b) => a[1].length - b[1].length || a[1].localeCompare(b[1]));
    const titles = {}; c.turns.forEach((t) => (t.response?.sources || []).forEach((s) => s.kind === "record" && (titles[s.id] = s.title)));
    const log = savedCases().filter((x) => x.id !== c.id);
    $("#board").innerHTML = `${leads.length ? `<h3>${last ? "Leads from the last report" : "Open leads"}</h3><div class="inq-leads">${leads.map((x) => `<button type="button" class="inq-lead">${esc(x)}</button>`).join("")}</div>` : ""}
      ${allEx.length ? `<h3>Exhibits in this case</h3><ol class="inq-log case-ex">${allEx.map(([id, L]) => `<li><a href="#/record/${id}"><b>${L}</b> ${esc(titles[id] || id)}</a></li>`).join("")}</ol>` : ""}
      ${log.length ? `<h3>Your case log</h3><ol class="inq-log">${log.map((x) => `<li><a href="#/ask?case=${x.id}">${esc(x.turns[0]?.q || "Case")}</a>
        <span class="inq-v ${(() => { const v = verdictOf(x.turns.at(-1)?.response); return v === "context" ? "partial" : v; })()}">${x.turns.length} inq.</span></li>`).join("")}</ol>
        <p class="small muted">Kept in this browser only.</p>` : ""}`;
    $("#board").querySelectorAll(".inq-lead").forEach((b) => (b.onclick = () => send(b.textContent)));
    const pending = thread.querySelector(".pending .inq-progress");
    clearInterval(tick);
    if (pending) { let i = 0; tick = setInterval(() => { if (!pending.isConnected) return clearInterval(tick);
      pending.querySelectorAll("li").forEach((li) => li.classList.toggle("on", +li.dataset.i <= i)); i = Math.min(i + 1, 3); }, 900); }
  };
  const busy = (on) => { $("#casebtn").disabled = on; ta.disabled = on; };
  async function send(q) {
    q = (q || "").trim();
    if (q.length < 2 || $("#casebtn").disabled) return;
    const turn = { q, response: null };
    c.turns.push(turn); render(); busy(true);
    toLatest(true);
    const messages = c.turns.flatMap((t) => [{ role: "user", content: t.q }, ...(t.response ? [{ role: "assistant", content: t.response.answer }] : [])]);
    try {
      turn.response = await api("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages, record: c.record }) });
      turn.response.sources.forEach((s) => { if (s.kind === "record" && !c.exhibits[s.id]) c.exhibits[s.id] = EXHIBIT(Object.keys(c.exhibits).length); });
    } catch (err) { turn.error = err.message; }
    saveChat(c);
    if (!$("#thread")) return;  // the user left the page; the case is saved
    render(); busy(false);
    toLatest(true);
    ta.focus({ preventScroll: true });
  }
  render();
  toLatest(false);
  ta.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#caseform").requestSubmit(); } };
  $("#caseform").onsubmit = (e) => { e.preventDefault(); const q = ta.value; ta.value = ""; send(q); };
  $("#newcase").onclick = () => { c = newCase(c.record); saveChat(c); history.replaceState(null, "", "#/ask"); render(); ta.focus(); };
  const unf = $("#unfocus"); if (unf) unf.onclick = () => { try { sessionStorage.removeItem(CHAT_KEY); } catch { /* ignore */ } };
  const q0 = params.get("q");  // links of the form #/ask?q=… (home page, record pages) start or continue the case with that question
  if (q0 && c.turns.at(-1)?.q !== q0) send(q0);
  try { sessionStorage.setItem(CHAT_KEY, JSON.stringify(c)); } catch { /* ignore */ }
}

/* "Investigate this record": the same desk, focused on the record in view. */
function recordInquiry(r) {
  const box = $("#inquiry");
  if (!box) return;
  const qs = ["Who appears in this record?", "Where and when was it made?", "How does it relate to other records of the archive?"];
  box.innerHTML = `<section class="inq-mini">
    <div class="inq-mini-head"><span class="inq-kicker">Investigate this record</span><span class="small muted">answers cite this record (★) and related files · Apertus ${pv("apertus")}</span></div>
    <form id="recask" class="inq-mini-form"><input id="recq" type="text" placeholder="Ask a question about this record…" autocomplete="off"><button>Ask</button></form>
    <div class="inq-mini-leads">${qs.map((x) => `<button type="button" class="inq-lead sm">${esc(x)}</button>`).join("")}</div>
    <div id="recaskout"></div></section>`;
  const run = async (q) => {
    const out = $("#recaskout");
    out.innerHTML = `<p class="small muted"><span class="spinner"></span> Pulling this file and related ones, Apertus is drafting…</p>`;
    try {
      const res = await api(`/api/ask?record=${encodeURIComponent(r.id)}&q=${encodeURIComponent(q)}`);
      if (!$("#recaskout")) return;
      out.innerHTML = `<p class="inq-mini-q">“${esc(q)}”</p>${caseReport(res, { mini: true, focus: r.id })}
        <a class="small" href="#/ask?record=${encodeURIComponent(r.id)}&q=${encodeURIComponent(q)}">Open a full case on the investigation desk →</a>`;
    } catch (err) { out.innerHTML = `<p class="small">Could not answer: ${esc(err.message)}</p>`; }
  };
  $("#recask").onsubmit = (e) => { e.preventDefault(); const q = $("#recq").value.trim(); if (q.length >= 3) run(q); };
  box.querySelectorAll(".inq-mini-leads button").forEach((b) => (b.onclick = () => { $("#recq").value = b.textContent; run(b.textContent); }));
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
        <div class="muted small">${LANG === "en" ? esc(r.title_en || "") : ""} ${r.tag_generated ? pv("apertus") : ""}</div>
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
      <datalist id="votelist">${VOTES.votes.map((v) => `<option value="${v.anr} · ${v.date.slice(0, 4)} · ${esc(voteTitle(v))}">`).join("")}</datalist>
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
      ${inLeg.map((v) => `<tr class="${vote && v.anr === vote.anr ? "on" : ""}"><td>${v.date}</td><td><a href="#/parliament?year=${y}&vote=${v.anr}">${esc(voteTitle(v))}</a> <span class="small muted">${esc(v.legal_form)}</span></td>
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
  box.innerHTML = `<section class="vote"><h2 translate="no">${esc(voteTitle(v))}</h2><p class="muted">${v.date} · ${esc(v.legal_form)} · ${voteBar(v.yes, v.accepted)}</p>
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
      <h2 translate="no">${esc(voteTitle(d, a.title_en))}</h2>
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
  wb.innerHTML = `<p class="small muted"><span class="spinner"></span> Collecting the parties' positions on related votes near ${whatifYear}…</p>`;
  let w;
  try { w = await api(`/api/votes/${d.anr}/whatif?year=${whatifYear}`); } catch (err) { wb.innerHTML = `<p class="small">Could not estimate: ${esc(err.message)}</p>`; return; }
  if (!$("#whatif")) return;
  const P = w.positions_then_strengths, rp = w.related_positions, an = w.anchor, bt = rp.backtest;
  const marks = { [d.anr]: { color: "#1f7a4d", label: d.title_de } };
  if (an) marks[an.anr] = { color: "#b5121b", label: an.title_de };
  wb.innerHTML = `<h3>The ${d.year} proposal under ${whatifYear} conditions</h3>
    <div class="two"><div>
      <table class="t"><tr><th>Scenario</th><th>Estimate</th><th>Actual</th></tr>
        <tr><td>${d.year} vote, its own positions and strengths</td><td>${d.estimate ?? "–"} %</td><td>${hasResult ? `${d.yes.toFixed(1)} %` : "–"}</td></tr>
        ${an ? `<tr><td>${an.date.slice(0, 4)} vote “${esc(an.title_de)}” (${esc(an.relation || "related")})</td><td>${an.estimate ?? "–"} %</td><td>${an.actual ?? "–"} %</td></tr>` : ""}
        <tr><td><b>${d.year} positions, ${whatifYear} party strengths</b></td><td><b>${P.estimate ?? "–"} %</b>${P.interval ? `<br><span class="small">${P.interval[0]}–${P.interval[1]} %</span>` : ""}</td><td>–</td></tr>
        ${P.corrected != null ? `<tr><td>… corrected by the model's miss on the ${an.date.slice(0, 4)} vote (${an.residual > 0 ? "+" : ""}${an.residual} pts)</td><td><b>${P.corrected} %</b></td><td>–</td></tr>` : ""}
        <tr><td>Positions on related votes near ${whatifYear}, ${whatifYear} strengths <span class="badge">evidence</span></td><td>${rp.estimate ?? "–"} %${rp.corrected != null ? `<br><span class="small">corrected ${rp.corrected} %</span>` : ""}</td><td>–</td></tr></table>
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
    <section class="band band-imagination"><h3>Party positions in ${whatifYear} <small>positions: evidence · explanations: generated by Apertus</small></h3>
      <p class="small">Each party's position is the one it took most often on the related votes nearest ${whatifYear}; Apertus only explains it.
        Why not let Apertus decide: on ${bt.votes} past votes this rule matched the real recommendation ${bt.rule_pct} % of the time,
        Apertus 70B predicting the positions itself ${bt.apertus_70b_pct} % and 8B ${bt.apertus_8b_pct} %.</p>
      <table class="t"><tr><th>Party</th><th>Position</th><th>From vote</th>${an ? `<th>Actual ${an.date.slice(0, 4)}</th>` : ""}<th>Explanation (generated)</th></tr>
      ${Object.entries(rp.parties || {}).map(([p, x]) => `<tr><td>${partyDot(p)}</td><td>${REC[x.rec] || x.rec}</td>
        <td class="small">${x.from.map((a) => `<a href="#/parliament?vote=${a}">${a}</a>`).join(", ")}</td>${an ? `<td>${REC[x.anchor_rec] || x.anchor_rec || "–"}</td>` : ""}
        <td class="small">${esc(x.reason || "")}${x.misstates_evidence ? ` <span class="badge qc-bad">misstates the record</span>` : ""}</td></tr>`).join("")}</table>
      ${rp.parties_without_evidence.length ? `<p class="small muted">No position on the related votes, so no estimate is made for: ${rp.parties_without_evidence.map((p) => esc(PARTY_LABEL[p] || p.toUpperCase())).join(", ")}.</p>` : ""}
    </section>`;
}

async function referendumPage() {
  location.replace("#/parliament?vote=224&whatif=1959");  // the 1959 vs 1971 page is now one case of the votes view
}

/* ---------------- Router ---------------- */
/* Heights of the header's navigation row and search band, for the sticky search bar on Browse (style.css). */
function measureHeader() {
  const s = document.documentElement.style;
  s.setProperty("--nav-h", `${$(".topbar-inner").offsetHeight}px`);
  s.setProperty("--band-h", `${$(".searchband").offsetHeight}px`);
}
new ResizeObserver(measureHeader).observe($(".topbar"));  // the language drop-down and translations change its height

async function route() {
  const h = location.hash.slice(1) || "/";
  const [path, query] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  document.body.classList.remove("fit-page");
  document.body.classList.toggle("browse", parts[0] === "search");
  measureHeader();
  app.innerHTML = `<p class="muted"><span class="spinner"></span> Loading…</p>`;
  try {
    if (!parts.length) await home();
    else if (parts[0] === "search") await search(new URLSearchParams(query || ""));
    else if (parts[0] === "record") await recordPage(parts[1], parts[2]);
    else if (parts[0] === "map") {  // the map page was folded into search; old links open search with the map and keep their filters
      const p = new URLSearchParams(query || ""); ["from", "to", "w"].forEach((k) => p.delete(k)); p.set("map", "1");
      location.replace("#/search?" + p.toString()); return;
    }
    else if (parts[0] === "quality") await qualityPage();
    else if (parts[0] === "live") await livePage();
    else if (parts[0] === "ask") await askPage(new URLSearchParams(query || ""));
    else if (parts[0] === "consultations") await consultationsPage(new URLSearchParams(query || ""));
    else if (parts[0] === "parliament") await parliamentPage(new URLSearchParams(query || ""));
    else if (parts[0] === "referendum") await referendumPage();
    else if (window.EXTRA_ROUTES?.[parts[0]]) await window.EXTRA_ROUTES[parts[0]](parts, new URLSearchParams(query || ""));  // oral.js
    else app.innerHTML = "<p>Not found.</p>";
  } catch (e) {
    app.innerHTML = `<p>Could not load: ${esc(e.message)}</p>`;
  }
  window.scrollTo(0, 0);
}
$("#searchform").onsubmit = searchFromHeader;
$(".advlink").onclick = (e) => {  // open the advanced panel on the current search instead of a blank one
  e.preventDefault();
  const p = location.hash.startsWith("#/search") ? new URLSearchParams(location.hash.split("?")[1] || "") : new URLSearchParams();
  p.set("adv", "1");
  location.hash = "#/search?" + p.toString();
};
$("#qin").onchange = () => { if (location.hash.startsWith("#/search")) $("#searchform").requestSubmit(); };
window.addEventListener("hashchange", route);
route();
