/* Year context drawer, History timeline and the "Oral tradition" page.
   Loaded after app.js and uses its helpers ($, esc, api, app, setNav, baseMap, icon). */

/* ---------------- Year context drawer ---------------- */
const YEAR_CACHE = {};

function yearDrawer() {
  let d = $("#yeardrawer");
  if (d) return d;
  d = document.createElement("div");
  d.id = "yeardrawer";
  d.innerHTML = `<div class="yd-backdrop"></div><aside class="yd-panel" role="dialog" aria-modal="true" aria-label="Year in context"><div class="yd-body"></div></aside>`;
  document.body.appendChild(d);
  d.querySelector(".yd-backdrop").onclick = closeYear;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && d.classList.contains("open")) closeYear(); });
  return d;
}
function closeYear() { $("#yeardrawer")?.classList.remove("open"); }

async function openYear(y) {
  y = Math.round(+y);
  if (!y) return;
  const d = yearDrawer(), body = d.querySelector(".yd-body");
  d.classList.add("open");
  const head = `<div class="yd-head"><button class="yd-nav" data-year="${y - 1}" title="Previous year">‹</button><h2>${y}</h2>
    <button class="yd-nav" data-year="${y + 1}" title="Next year">›</button><button class="yd-close" title="Close">✕</button></div>`;
  body.innerHTML = head + `<p class="small muted"><span class="spinner"></span> Looking up ${y} in the Federal Archives… (first look-up of an event can take up to a minute)</p>`;
  body.querySelector(".yd-close").onclick = closeYear;
  let r;
  try { r = YEAR_CACHE[y] ||= await api(`/api/years/${y}`); } catch (err) { body.innerHTML = head + `<p class="small">Could not load: ${esc(err.message)}</p>`; body.querySelector(".yd-close").onclick = closeYear; return; }
  if (!d.classList.contains("open") || !body.querySelector("h2") || body.querySelector("h2").textContent !== String(y)) return;  // user moved on
  const period = (e) => (e.end && e.end !== e.year ? `${e.year}–${e.end}` : `${e.year}`);
  const card = (x) => `<li><a href="#/record/${x.id}">${esc(x.title)}</a> <span class="muted small">${esc(x.date || "")}</span></li>`;
  const ev = r.events.map((e) => {
    const a = e.archive || {};
    return `<section class="yd-event">
      <h3>${esc(e.title)} <span class="yd-period">${period(e)}</span></h3>
      <p>${esc(e.summary)}</p>
      <p class="small"><a href="${e.hls}" target="_blank" rel="noopener">Historical Dictionary of Switzerland ↗</a></p>
      ${e.in_dataset.length ? `<h4>In this dataset</h4><ul class="yd-list">${e.in_dataset.map(card).join("")}</ul>` : ""}
      <h4>In the Federal Archives <span class="muted small">${a.kept ?? 0} units from the period, of ${a.found ?? 0} whose title names it</span></h4>
      ${(a.units || []).length ? `<ul class="yd-list">${a.units.map((u) => `<li><a href="${u.portal_url}" target="_blank" rel="noopener">${esc(u.title)}</a>
          <span class="muted small">${esc(u.date || "undated")}${u.reference_code ? ` · <code>${esc(u.reference_code)}</code>` : ""}</span></li>`).join("")}</ul>`
        : `<p class="small muted">${(a.failed || []).length ? "The archive did not answer in time; reopen the year to retry." : "No unit found."}</p>`}
      <p class="small muted">Searched for: ${e.terms.map((t) => `“${esc(t)}”`).join(", ")} in unit titles.</p>
    </section>`;
  }).join("");
  body.innerHTML = head + (ev || `<p class="muted">No key event is listed for ${y}.</p>`)
    + (r.records_dated.length ? `<section class="yd-event"><h3>Records of this dataset dated ${y}</h3><ul class="yd-list">${r.records_dated.map(card).join("")}</ul></section>` : "")
    + (r.nearby.length ? `<section class="yd-event"><h4>Nearby events</h4><div class="chips">${r.nearby.map((e) => `<button class="chip" data-year="${e.year}">${period(e)} · ${esc(e.title)}</button>`).join("")}</div></section>` : "")
    + `<p class="small muted yd-foot">Events are curated by hand (data/years/events.json); archive units are found by their title words and kept when dated within ten years of the event.</p>`;
  body.querySelector(".yd-close").onclick = closeYear;
  body.scrollTop = 0;
}

// Any element with data-year opens the drawer (year chips on any page).
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-year]");
  if (!t || t.tagName === "INPUT") return;
  e.preventDefault();
  openYear(t.dataset.year);
});

/* ---------------- History timeline (frise chronologique) ----------------
   A horizontal timeline whose reading line stays in the middle of the view: scrolling, dragging, the slider,
   the arrow keys or "Play" move history under it. Events behind the line are lit, the event under it is shown
   in the card below, events ahead are faded, so the frise fills up as time goes by. */
const ERAS = [
  { from: 1291, to: 1798, name: "Old Swiss Confederacy" }, { from: 1798, to: 1803, name: "Helvetic Republic" },
  { from: 1803, to: 1813, name: "Mediation" }, { from: 1813, to: 1848, name: "Restoration and Regeneration" },
  { from: 1848, to: 2100, name: "Federal state" },
];
let FRISE_STOP = null;  // stops the animation of the previous page visit

async function historyPage(params) {
  setNav("history");
  FRISE_STOP?.();
  const evs = (await api("/api/years")).sort((a, b) => a.year - b.year || a.end - b.end);
  const now = new Date().getFullYear();
  const start = Math.floor(Math.min(...evs.map((e) => e.year)) / 10) * 10 - 10, end = now;
  // two speeds: centuries before 1800 have few events, so they take less room
  const BEND = 1800, SLOW = 1.6, FAST = 11;
  const x = (y) => (Math.min(y, BEND) - start) * SLOW + Math.max(0, y - BEND) * FAST;
  const yearAt = (px) => (px <= x(BEND) ? start + px / SLOW : BEND + (px - x(BEND)) / FAST);
  const W = x(end);
  const period = (e) => (e.end !== e.year ? `${e.year}–${e.end}` : `${e.year}`);

  // lay the event labels out in lanes so none overlaps
  const lanes = [];
  const placed = evs.map((e) => {
    const x0 = x(e.year), x1 = Math.max(x(e.end), x0), w = Math.min(230, 54 + e.title.length * 6.4);
    let lane = lanes.findIndex((last) => last < x0 - 8);
    if (lane < 0) { lane = lanes.length; lanes.push(0); }
    lanes[lane] = Math.max(x0 + w, x1);
    return { ...e, x0, x1, lane };
  });
  const LANE_H = 34, top = 44, axisY = top + lanes.length * LANE_H + 14;
  const ticks = [];
  for (let y = Math.ceil(start / 50) * 50; y <= end; y += y < BEND ? 50 : 10)
    ticks.push(`<div class="fr-tick${y % 50 === 0 ? " major" : ""}" style="left:${x(y)}px;top:${axisY}px">${y % 50 === 0 ? `<span>${y}</span>` : ""}</div>`);

  app.innerHTML = `<h1>A year in context</h1>
    <p class="muted">Key events of Swiss history on a frise chronologique. Scroll, drag or press Play: the line in the middle travels through time,
      the events it passes light up and the card below follows it. Click an event, or any year chip on the site, to open that year with
      everything in the Federal Archives whose title references it.</p>
    <div class="fr-controls">
      <button type="button" class="fr-play" id="fr-play" aria-pressed="false">${icon("play")}<span>Play</span></button>
      <div class="fr-year" id="fr-year" aria-live="off">${start}</div>
      <input type="range" id="fr-slider" min="${start}" max="${end}" value="${start}" aria-label="Year on the timeline">
      <form class="yearform" id="yearform"><label>Go to year <input type="number" id="yearinput" min="1000" max="2100" placeholder="1847"></label><button>Open</button></form>
    </div>
    <div class="frise-wrap"><div class="frise" id="frise" tabindex="0" aria-label="Timeline of Swiss history; use the arrow keys to move through time">
      <div class="fr-track" id="fr-track" style="width:${W}px;height:${axisY + 40}px"><div class="fr-inner" id="fr-inner" style="width:${W}px">
        ${ERAS.filter((r) => r.to > start && r.from < end).map((r, i) => { const w = x(Math.min(r.to, end)) - x(Math.max(r.from, start));
          return `<div class="fr-era era-${i % 2}" style="left:${x(Math.max(r.from, start))}px;width:${w}px" title="${esc(r.name)} ${r.from}–${r.to > now ? "" : r.to}"><span style="max-width:${Math.max(0, w - 16)}px">${esc(r.name)}</span></div>`; }).join("")}
        <div class="fr-axis" style="top:${axisY}px"></div>
        <div class="fr-progress" id="fr-progress" style="top:${axisY}px"></div>
        ${ticks.join("")}
        ${placed.map((e, i) => `<button type="button" class="fr-ev future" data-i="${i}" data-year="${e.year}" style="left:${e.x0}px;top:${top + e.lane * LANE_H}px"
            title="${esc(period(e))} · ${esc(e.title)}">
            ${e.x1 > e.x0 + 2 ? `<i class="fr-span" style="width:${e.x1 - e.x0}px"></i>` : ""}<i class="fr-dot"></i>
            <b>${esc(period(e))}</b> <span>${esc(e.title)}</span></button>
          <i class="fr-stem future" data-i="${i}" style="left:${e.x0}px;top:${top + e.lane * LANE_H + 26}px;height:${axisY - top - e.lane * LANE_H - 26}px"></i>`).join("")}
      </div>
    </div></div><div class="fr-line" aria-hidden="true"></div></div>
    <div class="fr-now" id="fr-now"></div>`;

  const fr = $("#frise"), track = $("#fr-track"), slider = $("#fr-slider"), yearBox = $("#fr-year"), card = $("#fr-now");
  const evEls = [...track.querySelectorAll(".fr-ev")], stemEls = [...track.querySelectorAll(".fr-stem")];
  // the reading line is the middle of the view: pad the track by half a view on both sides
  const pad = () => { const p = Math.round(fr.clientWidth / 2); track.style.width = `${W + 2 * p}px`; $("#fr-inner").style.left = `${p}px`; };
  pad();
  let shown = -2;
  const render = () => {
    const y = Math.max(start, Math.min(end, yearAt(fr.scrollLeft)));
    const yr = Math.round(y);
    yearBox.textContent = yr;
    if (document.activeElement !== slider) slider.value = yr;
    $("#fr-progress").style.width = `${fr.scrollLeft}px`;
    let cur = -1;
    placed.forEach((e, i) => {
      const state = e.year > y ? "future" : (e.end >= Math.floor(y) ? "current" : "past");
      if (state !== "future") cur = state === "current" || cur < 0 || placed[cur].year <= e.year ? i : cur;
      evEls[i].className = `fr-ev ${state}`;
      stemEls[i].className = `fr-stem ${state}`;
    });
    const era = ERAS.find((r) => r.from <= y && y < r.to);
    if (cur === shown) { card.querySelector(".fr-era-name") && (card.querySelector(".fr-era-name").textContent = era ? era.name : ""); return; }
    shown = cur;
    const e = placed[cur];
    card.innerHTML = e ? `<div class="fr-now-period">${esc(period(e))}</div>
        <div class="fr-now-body"><h3>${esc(e.title)}</h3>${e.summary ? `<p>${esc(e.summary)}</p>` : ""}
        <p class="small"><span class="muted">Era: <span class="fr-era-name">${esc(era ? era.name : "")}</span> ·</span>
          <button type="button" class="linklike" data-year="${e.year}">Open ${e.year} in context →</button></p></div>`
      : `<p class="muted">Press Play or scroll to travel through time.</p>`;
  };
  const goTo = (y, smooth) => fr.scrollTo({ left: x(Math.max(start, Math.min(end, y))), behavior: smooth ? "smooth" : "auto" });
  fr.addEventListener("scroll", () => requestAnimationFrame(render), { passive: true });
  slider.oninput = () => { stop(); goTo(+slider.value); };
  fr.onkeydown = (e) => {
    const step = { ArrowRight: 1, ArrowLeft: -1, PageDown: 10, PageUp: -10 }[e.key];
    if (!step) return;
    e.preventDefault(); stop();
    goTo(Math.round(yearAt(fr.scrollLeft)) + step * (e.shiftKey ? 10 : 1));
  };
  // vertical wheel scrolls through time; drag with the mouse to move the frise
  fr.addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
    e.preventDefault(); stop();
    fr.scrollLeft += e.deltaY;
  }, { passive: false });
  let drag = null;
  fr.addEventListener("pointerdown", (e) => { if (e.pointerType === "mouse") { drag = { x: e.clientX, left: fr.scrollLeft, moved: false }; stop(); } });
  addEventListener("pointermove", (e) => {
    if (!drag) return;
    if (Math.abs(e.clientX - drag.x) > 4) { drag.moved = true; fr.classList.add("dragging"); }
    if (drag.moved) fr.scrollLeft = drag.left - (e.clientX - drag.x);
  });
  addEventListener("pointerup", () => { if (drag) { fr.classList.remove("dragging"); setTimeout(() => (drag = null), 0); } });
  fr.addEventListener("click", (e) => { if (drag?.moved) { e.stopPropagation(); e.preventDefault(); } }, true);  // a drag is not a click

  // Play: years per second, faster through the sparse early centuries
  let raf = null, last = 0, pos = start;
  const playBtn = $("#fr-play");
  function stop() {
    if (!raf) return;
    cancelAnimationFrame(raf); raf = null;
    playBtn.setAttribute("aria-pressed", "false"); playBtn.innerHTML = `${icon("play")}<span>Play</span>`;
  }
  const step = (t) => {
    if (!document.body.contains(fr)) { raf = null; return; }
    pos += ((t - last) / 1000) * (pos < BEND ? 60 : 9);
    last = t;
    if (pos >= end) { goTo(end); stop(); return; }
    fr.scrollLeft = x(pos);
    raf = requestAnimationFrame(step);
  };
  playBtn.onclick = () => {
    if (raf) { stop(); return; }
    pos = yearAt(fr.scrollLeft);
    if (pos >= end - 1) { pos = start; }
    last = performance.now();
    playBtn.setAttribute("aria-pressed", "true"); playBtn.innerHTML = `${icon("pause")}<span>Pause</span>`;
    raf = requestAnimationFrame(step);
  };
  FRISE_STOP = stop;
  addEventListener("resize", () => { if (document.body.contains(fr)) { const y = yearAt(fr.scrollLeft); pad(); goTo(y); } });

  $("#yearform").onsubmit = (e) => { e.preventDefault(); stop(); goTo(+$("#yearinput").value, true); openYear($("#yearinput").value); };
  const y0 = +params.get("y");
  goTo(y0 || 1848);
  render();
  if (y0) openYear(y0);
}

/* ---------------- Oral tradition ---------------- */
const ORAL_KEY = "cora-oral-v1";
const loadOral = () => { try { return JSON.parse(localStorage.getItem(ORAL_KEY)) || {}; } catch { return {}; } };
const saveOral = (s) => { try { localStorage.setItem(ORAL_KEY, JSON.stringify(s)); } catch { /* private mode: keep in memory */ } };
const KIND = { S: "Stapfer-Enquête 1799", C: "Federal census", G: "Federal Gazette", E: "Key event", A: "Federal Archives", W: "Wikipedia", O: "Oral tradition (yours)" };
const SPEECH_LANG = { de: "de-CH", fr: "fr-CH", it: "it-CH", rm: "de-CH" };
const LANG_NAME = { de: "German", fr: "French", it: "Italian", rm: "Romansh" };

async function oralPage() {
  setNav("oral");
  const st = loadOral();
  st.oral ||= [];
  app.innerHTML = `<h1>Oral tradition</h1>
    <p class="muted">Give your family name and your place of origin (Heimatort). Apertus reads what the sources say about that place and that time (the 1799 Stapfer school
      survey, the federal censuses from 1850, the Federal Gazette, the key events of those years, the Federal Archives and Wikipedia)
      and imagines your ancestor's year, citing every source. Add what your family tells
      (oral tradition) and the story, the map and the photographs follow.</p>
    <div class="callout small">${icon("alert")} A reconstruction, not a genealogy: sentences without a source are marked <i>imagined</i>; photographs illustrate the
      places, they do not show your family. Your family stories stay in this browser and are sent only to generate the text; the server keeps no copy.</div>
    <form class="oral-form" id="oralform" autocomplete="off">
      <label>Family name <input id="o-surname" required maxlength="60" placeholder="e.g. Bärtschi" value="${esc(st.surname || "")}"></label>
      <label><span>First name <span class="muted small">(optional)</span></span><input id="o-first" maxlength="40" value="${esc(st.first || "")}"></label>
      <label class="o-place">Place of origin <input id="o-place" required placeholder="e.g. Langnau im Emmental" value="${esc(st.placeName || "")}">
        <ul class="o-suggest" id="o-suggest" hidden></ul></label>
      <label>Around the year <input id="o-year" type="number" min="1700" max="1950" value="${st.year || 1799}"></label>
      <button type="submit" class="o-go">Imagine their life</button>
    </form>
    <div id="o-status" class="o-status" aria-live="polite"></div>
    <p class="small muted">Places: the 2,142 places of the Stapfer survey of 1799, and every current Swiss municipality (swisstopo). For the place and year you choose,
      Apertus checks whether the place already existed and whether it belonged to the Confederation then. Choose any year from 1700 to 1950:
      around 1799 the school survey speaks; from 1850 the censuses, the Federal Gazette and photographs closer in time take over, and the map is the swisstopo map of that year.</p>
    <div id="oralout"></div>`;
  let placeId = st.placeId || null, timer = null;
  const inp = $("#o-place"), sug = $("#o-suggest");
  inp.oninput = () => {
    placeId = null; clearTimeout(timer);
    timer = setTimeout(async () => {
      const xs = await api(`/api/oral/places?q=${encodeURIComponent(inp.value)}`).catch(() => []);
      sug.innerHTML = xs.map((x) => `<li><button type="button" data-id="${x.id}" data-name="${esc(x.name)}">${esc(x.name)} <span class="muted small">${esc([x.municipality !== x.name ? x.municipality : "", x.canton].filter(Boolean).join(", "))}${x.schools ? ` · ${x.schools} school${x.schools > 1 ? "s" : ""} in 1799` : ""}</span>
          <span class="o-src ${x.source === "stapfer" ? "s1799" : "today"}">${x.source === "stapfer" ? "1799 survey" : "municipality today"}</span></button></li>`).join("")
        || `<li class="muted small">No Swiss place of that name.</li>`;
      sug.hidden = !inp.value.trim();
    }, 200);
  };
  sug.onclick = (e) => {
    const b = e.target.closest("button[data-id]");
    if (!b) return;
    placeId = asPlaceId(b.dataset.id); inp.value = b.dataset.name; sug.hidden = true;
    checkPlace();
  };
  // What the place was in the chosen year (Apertus, cited): did it exist, was it part of the Confederation?
  let ytimer = null, asked = "";
  async function checkPlace() {
    const year = +$("#o-year").value, box = $("#o-status");
    if (!placeId || !(year >= 1000 && year <= 2100)) { box.innerHTML = ""; asked = ""; return; }
    const key = `${placeId}|${year}`;
    if (key === asked) return;
    asked = key;
    box.innerHTML = `<p class="small muted"><span class="spinner"></span> Apertus is checking what ${esc(inp.value)} was in ${year}…</p>`;
    let r;
    try { r = await api(`/api/oral/status?place_id=${encodeURIComponent(placeId)}&year=${year}`); }
    catch (err) { if (asked === key) box.innerHTML = `<p class="small muted">Could not check the place: ${esc(err.message)}</p>`; return; }
    if (asked === key) box.innerHTML = statusHtml(r);
  }
  $("#o-year").addEventListener("input", () => { clearTimeout(ytimer); ytimer = setTimeout(checkPlace, 500); });
  if (placeId) checkPlace();
  $("#oralform").onsubmit = async (e) => {
    e.preventDefault();
    if (!placeId) {
      const xs = await api(`/api/oral/places?q=${encodeURIComponent(inp.value)}`).catch(() => []);
      if (!xs.length) { inp.setCustomValidity("Pick a place from the list"); inp.reportValidity(); inp.setCustomValidity(""); return; }
      placeId = asPlaceId(xs[0].id); inp.value = xs[0].name;
      checkPlace();
    }
    Object.assign(st, { surname: $("#o-surname").value.trim(), first: $("#o-first").value.trim(), placeId, placeName: inp.value, year: +$("#o-year").value || 1799 });
    saveOral(st);
    runOral(st);
  };
  if (st.last && st.last.surname === st.surname && st.last.home?.id === st.placeId) renderOral(st, st.last, st.lastPhotos);
}

const asPlaceId = (v) => (/^\d+$/.test(String(v)) ? +v : String(v));  // a 1799 place (number) or a municipality ("m" + BFS number)
const EXISTED = { yes: ["ok", "Existed"], no: ["no", "Not founded yet"], uncertain: ["unsure", "Existence uncertain"] };
const CONFED = { member: ["ok", "Part of the Confederation"], associate: ["unsure", "Associate of the Confederation"],
  "subject territory": ["unsure", "Subject territory of the Confederates"], "helvetic republic": ["unsure", "Helvetic Republic"],
  outside: ["no", "Outside the Confederation"], uncertain: ["unsure", "Membership uncertain"] };
function statusHtml(r) {
  const [ec, el] = EXISTED[r.existed] || EXISTED.uncertain, [cc, cl] = CONFED[r.confederation] || CONFED.uncertain;
  return `<div class="o-status-card"><div class="o-status-head"><b>${esc(r.place)} in ${r.year}</b>
      <span class="o-flag ${ec}">${el}${r.existed === "yes" && r.founded ? ` · ${esc(String(r.founded))}` : ""}</span><span class="o-flag ${cc}">${cl}</span>
      <span class="muted small">checked by Apertus${r.seconds ? ` in ${r.seconds} s` : ""}</span></div>
    <p>${esc(r.existence_note || "")} ${esc(r.municipality_note || "")}</p><p>${esc(r.confederation_note || "")}</p>
    <p class="small muted">Sources: ${r.sources.map((x) => (x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.label)}</a>` : esc(x.label))).join(" · ")}</p>
    ${r.existed === "no" ? `<p class="small">${icon("alert")} The place did not exist yet in ${r.year}: the story will describe the area around it.</p>` : ""}</div>`;
}

async function runOral(st) {
  const out = $("#oralout");
  out.innerHTML = `<p class="muted"><span class="spinner"></span> Apertus is reading the Stapfer survey, the Federal Archives and Wikipedia for ${esc(st.placeName)}… (about a minute)</p>`;
  let story;
  try {
    story = await api("/api/oral/story", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ surname: st.surname, first_name: st.first, place_id: st.placeId, year: st.year, oral: st.oral }) });
  } catch (err) { out.innerHTML = `<p>Could not imagine the story: ${esc(err.message)}</p>`; return; }
  story.surname = st.surname;
  st.last = story; st.lastPhotos = null; saveOral(st);
  renderOral(st, story, null);
}

function renderOral(st, s, photos) {
  const out = $("#oralout");
  const num = {}; s.sources.forEach((x, i) => (num[x.ref] = i + 1));
  const cite = (refs) => (refs.length ? `<sup class="fns">[${[...new Set(refs)].sort((a, b) => num[a] - num[b]).map((f) =>
    `<a href="#src-${f}" class="${f[0] === "O" ? "fn-oral" : ""}" title="${esc(KIND[f[0]] || f)}" onclick="document.getElementById('src-${f}')?.scrollIntoView({behavior:'smooth',block:'center'});return false;">${num[f]}</a>`).join(",")}]</sup>` : "");
  const pick = Object.fromEntries((photos?.picks || []).map((p) => [p.stop, p]));
  out.innerHTML = `
    <div class="oral-head"><h2>${esc(s.title || `${s.ancestor} of ${s.home.name}`)}</h2>
      <div class="badges"><button class="chip" data-year="${s.year}">${icon("calendar")} ${s.year} in context</button>
        <span class="badge">${s.stops.length} stops</span><span class="badge">${s.sources.length} sources cited</span>
        <span class="badge ${s.imagined_sentences ? "imagined-badge" : ""}">${s.imagined_sentences} imagined sentence${s.imagined_sentences === 1 ? "" : "s"}</span>
        ${s.namesakes ? `<span class="badge" title="Teachers of your family name in the 1799 survey">${s.namesakes} namesake${s.namesakes > 1 ? "s" : ""} in 1799</span>` : ""}</div></div>
    <div class="oral-grid">
      <div class="oral-map-wrap"><div id="oralmap" class="map oral-map"></div>
        <div class="oral-layers small"><label><input type="checkbox" id="l-dufour" checked> ${esc((s.map || DUFOUR).label)}</label>
          <label><input type="checkbox" id="l-ivs" checked> Historical routes (IVS)</label></div>
        <p class="small muted">Numbered stops on your ancestor's route (dashed); photo pins show where each photograph was taken. Map: ${esc((s.map || DUFOUR).label)} (swisstopo) and Inventory of Historical Traffic Routes (ASTRA).</p></div>
      <div class="oral-story">
        ${s.stops.map((p, i) => `<section class="oral-stop" id="stop-${i}">
          <h3><span class="stopnum">${i + 1}</span> ${esc(p.place)} <span class="muted small">· ${esc([p.season, p.activity].filter(Boolean).join(" · "))}</span></h3>
          <p>${p.sentences.map((x) => `<span class="${x.imagined ? "imagined" : ""}" ${x.imagined ? 'title="Imagined: no source supports this sentence"' : ""}>${esc(x.text)}${cite(x.sources)}</span>`).join(" ")}</p>
          <div class="stop-photo" id="photo-${i}">${photoHtml(pick[i], s)}</div>
        </section>`).join("")}
      </div>
    </div>
    <section class="oral-voice">
      <h3>${icon("volume")} Hear your ancestor <span class="muted small">· ${LANG_NAME[s.language] || s.language}</span></h3>
      <p class="mono-text" id="mono">${esc(s.monologue || "")}</p>
      <details class="small"><summary>Translation</summary><p>${esc(s.monologue_en || "")}</p></details>
      <div class="voice-bar"><button id="speak">▶ Listen</button><select id="voice" title="Voice"></select>
        <span class="small muted" id="voicenote"></span></div>
      <p class="small muted">Imagined monologue written by Apertus, read by your browser's speech synthesis. Swiss German dialects and Romansh have no synthetic voice yet: the text is read in standard ${s.language === "rm" ? "German" : LANG_NAME[s.language] || "German"}.</p>
    </section>
    <section class="oral-add">
      <h3>Add oral tradition</h3>
      <p class="small muted">What does your family tell about them? A trade, a journey, a place, a habit. Each story becomes a source [O#] and the life is imagined again.</p>
      <ol class="oral-stories">${st.oral.map((o, i) => `<li>${esc(o)} <button class="linkbtn" data-del="${i}" title="Remove">✕</button></li>`).join("")}</ol>
      <form id="oraladd"><textarea id="o-story" rows="2" maxlength="600" placeholder="e.g. My grandmother said they carried cheese to the market in Burgdorf every autumn."></textarea>
        <button>Add and imagine again</button></form>
    </section>
    <section><h3>Sources</h3><ol class="more-src small">${s.sources.map((x) => `<li id="src-${x.ref}"><b>${esc(KIND[x.kind] || x.kind)}</b> · ${esc(x.label || "")}
      ${x.url ? ` · <a href="${esc(x.url)}" target="_blank" rel="noopener">source ↗</a>` : ""}${x.pdf ? ` · <a href="${esc(x.pdf)}" target="_blank" rel="noopener">PDF ↗</a>` : ""}${x.reference_code ? ` · <code>${esc(x.reference_code)}</code>` : ""}
      <div class="muted">${esc(x.text.length > 320 ? x.text.slice(0, 320) + "…" : x.text)}</div></li>`).join("")}</ol>
      <p class="small muted">Generated by Apertus (${esc(s.model || "")}) from ${Object.entries(s.offered).filter(([, n]) => n).map(([k, n]) => `${n} × ${KIND[k] || k}`).join(", ")}.
      Stops are placed with the Stapfer gazetteer (swisstopo coordinates) or OpenStreetMap, never by the model. Archive units begun after 1950 are left out, as they may name private people;
      people named in Gazette passages are namesakes, not necessarily your family.</p>
      ${(s.newspapers || []).length ? `<p class="small"><b>Read the newspapers of the time</b> (Swiss National Library, opens in a new tab; not used by Apertus):
        ${s.newspapers.map((n) => `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.label)} ↗</a>`).join(" · ")}</p>` : ""}</section>`;
  drawOralMap(s, photos);
  setupVoice(s);
  $("#oraladd").onsubmit = (e) => {
    e.preventDefault();
    const t = $("#o-story").value.trim();
    if (!t) return;
    st.oral.push(t); saveOral(st); runOral(st);
  };
  out.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { st.oral.splice(+b.dataset.del, 1); saveOral(st); renderOral(st, s, photos); }));
  if (!photos) loadPhotos(st, s);
}

function photoHtml(p, s) {
  if (p === undefined) return `<p class="small muted"><span class="spinner"></span> Apertus is choosing a photograph from the ETH Library…</p>`;
  if (!p) return "";
  const c = p.photo;
  const gap = p.years_apart != null ? `${Math.abs(p.years_apart)} years ${p.years_apart >= 0 ? "after" : "before"} the story` : "undated";
  return `<figure><a href="${esc(c.page)}" target="_blank" rel="noopener"><img src="${esc(c.thumb)}" alt="${esc(c.title)}" loading="lazy"></a>
    <figcaption><b>Illustrative, not your family.</b> ${esc(c.title)}${c.year ? `, ${c.year}` : ""} · ${gap} ·
      ${c.distance_km != null ? `${c.distance_km} km from ${esc(s.stops[p.stop]?.place || "the stop")}` : "place not recorded"}
      · ${esc(c.credit)}${c.artist ? `, ${esc(c.artist)}` : ""} · ${esc(c.license)}
      <span class="muted">· Apertus: ${esc(p.reason || "")}</span></figcaption></figure>`;
}

async function loadPhotos(st, s) {
  let ph;
  try {
    ph = await api("/api/oral/photos", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year: s.year, stops: s.stops, home: s.home }) });
  } catch (err) { ph = { picks: [], error: err.message }; }
  if (st.last !== s) return;
  st.lastPhotos = ph; saveOral(st);
  const pick = Object.fromEntries(ph.picks.map((p) => [p.stop, p]));
  s.stops.forEach((_, i) => { const el = $(`#photo-${i}`); if (el) el.innerHTML = photoHtml(pick[i] || null, s); });
  drawOralMap(s, ph);
}

let ORAL_MAP = null;
const DUFOUR = { layer: "ch.swisstopo.hiks-dufour", time: "current", label: "Dufour map (1845–1865)" };
function drawOralMap(s, photos) {
  const el = $("#oralmap");
  if (!el) return;
  ORAL_MAP?.remove();
  const stops = s.stops.map((p, i) => ({ ...p, i })).filter((p) => p.lat != null);
  const picks = (photos?.picks || []).filter((p) => p.photo.lat != null && stops.some((x) => x.i === p.stop));
  const pts = [...stops.map((p) => [p.lon, p.lat]), ...picks.map((p) => [p.photo.lon, p.photo.lat])];
  const view = pts.length > 1 ? { bounds: pts.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds()), fitBoundsOptions: { padding: 60, maxZoom: 12 } }
    : { center: [s.home.lon, s.home.lat], zoom: 10 };
  const hist = { dufour: $("#l-dufour")?.checked !== false, ivs: $("#l-ivs")?.checked !== false };
  const map = ORAL_MAP = baseMap(el, (m) => {
    const hm = s.map || DUFOUR;  // the swisstopo map of the story year (period.map_layer)
    m.addSource("dufour", { type: "raster", tileSize: 256, maxzoom: 16, bounds: [5.9, 45.8, 10.5, 47.85], attribution: `© swisstopo, ${hm.label}`,
      tiles: [`https://wmts.geo.admin.ch/1.0.0/${hm.layer}/default/${hm.time}/3857/{z}/{x}/{y}.png`] });
    m.addLayer({ id: "dufour", type: "raster", source: "dufour", paint: { "raster-opacity": 0.75 }, layout: { visibility: hist.dufour ? "visible" : "none" } });
    m.addSource("ivs", { type: "raster", tileSize: 256, maxzoom: 17, bounds: [5.9, 45.8, 10.5, 47.85], attribution: "© ASTRA, IVS",
      tiles: ["https://wmts.geo.admin.ch/1.0.0/ch.astra.ivs-nat/default/current/3857/{z}/{x}/{y}.png"] });
    m.addLayer({ id: "ivs", type: "raster", source: "ivs", layout: { visibility: hist.ivs ? "visible" : "none" } });
    m.addSource("photolinks", { type: "geojson", data: { type: "FeatureCollection", features: picks.map((p) => {
      const st = stops.find((x) => x.i === p.stop);
      return { type: "Feature", geometry: { type: "LineString", coordinates: [[st.lon, st.lat], [p.photo.lon, p.photo.lat]] } };
    }) } });
    m.addLayer({ id: "photolinks", type: "line", source: "photolinks", paint: { "line-color": "#555", "line-width": 1, "line-dasharray": [1, 2] } });
    if (stops.length > 1) {
      m.addSource("route", { type: "geojson", data: { type: "Feature", geometry: { type: "LineString", coordinates: stops.map((p) => [p.lon, p.lat]) } } });
      m.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": "#b5121b", "line-width": 3, "line-dasharray": [2, 1.5], "line-opacity": 0.9 } });
    }
  }, view);
  const seen = {};
  stops.forEach((p) => {
    const k = `${p.lat.toFixed(4)},${p.lon.toFixed(4)}`;
    const n = seen[k] = (seen[k] || 0) + 1;  // several stops at one place: fan the pins out a little
    const elp = document.createElement("div");
    elp.innerHTML = `<div class="pin stoppin">${p.i + 1}</div>`;
    new maplibregl.Marker({ element: elp, offset: [(n - 1) * 22, 0] }).setLngLat([p.lon, p.lat])
      .setPopup(new maplibregl.Popup({ offset: 14 }).setHTML(`<b>${p.i + 1}. ${esc(p.place)}</b><br>${esc([p.season, p.activity].filter(Boolean).join(" · "))}<br><span class="small">${esc(p.located_by || "")}</span>`))
      .addTo(map);
    elp.addEventListener("click", () => document.getElementById(`stop-${p.i}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  });
  picks.forEach((p) => {
    const elp = document.createElement("div");
    elp.innerHTML = `<div class="photopin"><img src="${esc(p.photo.thumb)}" alt=""></div>`;
    new maplibregl.Marker({ element: elp }).setLngLat([p.photo.lon, p.photo.lat])
      .setPopup(new maplibregl.Popup({ offset: 22, maxWidth: "260px" }).setHTML(`<img src="${esc(p.photo.thumb)}" alt="" style="width:100%"><br><b>${esc(p.photo.title)}</b>${p.photo.year ? `, ${p.photo.year}` : ""}<br><span class="small">Illustrates stop ${p.stop + 1} · ETH-Bibliothek · ${esc(p.photo.license)}</span>`))
      .addTo(map);
  });
  const toggle = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none"); };
  $("#l-dufour").onchange = (e) => toggle("dufour", e.target.checked);
  $("#l-ivs").onchange = (e) => toggle("ivs", e.target.checked);
  setTimeout(() => map.resize(), 60);
}

function setupVoice(s) {
  const btn = $("#speak"), sel = $("#voice"), note = $("#voicenote");
  if (!("speechSynthesis" in window)) { btn.disabled = true; note.textContent = "This browser has no speech synthesis."; return; }
  const want = SPEECH_LANG[s.language] || "de-CH", base = want.slice(0, 2);
  const fill = () => {
    const vs = speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(base));
    vs.sort((a, b) => (b.lang === want) - (a.lang === want));
    sel.innerHTML = vs.map((v, i) => `<option value="${i}">${esc(v.name)} (${esc(v.lang)})</option>`).join("");
    sel.hidden = !vs.length;
    note.textContent = vs.length ? (vs.some((v) => v.lang === want) ? "" : `No ${want} voice here; using ${vs[0].lang}.`) : `No ${LANG_NAME[s.language] || base} voice installed; your browser's default voice will read it.`;
    sel._voices = vs;
  };
  fill();
  speechSynthesis.onvoiceschanged = fill;
  btn.onclick = () => {
    if (speechSynthesis.speaking) { speechSynthesis.cancel(); btn.textContent = "▶ Listen"; return; }
    const u = new SpeechSynthesisUtterance(s.monologue || "");
    u.lang = want;
    const v = sel._voices?.[+sel.value];
    if (v) { u.voice = v; u.lang = v.lang; }
    u.rate = 0.92;
    u.onend = u.onerror = () => { btn.textContent = "▶ Listen"; };
    speechSynthesis.speak(u);
    btn.textContent = "■ Stop";
  };
}

window.EXTRA_ROUTES = { oral: () => oralPage(), history: (parts, q) => historyPage(q) };
// Icons used here (the shared set lives in app.js)
SVG.calendar ||= '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>';
SVG.volume ||= '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>';
// app.js routed the first page before this file loaded: route again when it is one of ours.
if (/^#\/(oral|history)\b/.test(location.hash)) route();
window.addEventListener("hashchange", closeYear);
