"""Oral tradition: an imagined, source-based day in the life of a user's ancestor.

Input: family name + place of origin (Heimatort), optionally a year and family stories ("oral tradition").
Sources, numbered and cited sentence by sentence:
  S#  Stapfer-Enquête 1799 (University of Bern datafication): the place, its schools, teachers, lessons, wages
  A#  Federal Archives units whose title names the family or the place (LINDAS)
  W#  Wikipedia article on the place (CC BY-SA)
  O#  oral tradition given by the user: kept apart from archive evidence, never sent to the server cache
Sentences without a valid source are kept and marked imagined: imagining is the point, but it is always visible.
Stops of the story are placed on a map from the Stapfer gazetteer (1799 places, swisstopo coordinates) or
Nominatim, never from the model. Photos: see photos.py; Apertus only chooses among the candidates it is given.
"""
import json
import math
import re
import unicodedata
import zipfile
from pathlib import Path

from . import enrich, origin, period, photos, stapfer, topic, years


def fold(s) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()).strip()


def lv03_to_wgs84(e: float, n: float) -> tuple[float, float]:
    """swisstopo approximate formulas (accuracy ~1 m), LV03 (E, N) -> WGS84 (lat, lon)."""
    y, x = (e - 600000) / 1e6, (n - 200000) / 1e6
    lon = 2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x - 0.0436 * y ** 3
    lat = 16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x - 0.0447 * y * y * x - 0.0140 * x ** 3
    return round(lat * 100 / 36, 5), round(lon * 100 / 36, 5)


def km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# --- Stapfer gazetteer and schools ------------------------------------------------------------------------
_INDEX: dict | None = None


def _clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v if v and not v.startswith("\x00") and v not in ("\x01",) else None
    return v


# Survey questions that say most about daily life, in the order they are quoted: other work of the teacher, his
# previous trade, schoolhouse, lessons, school terms, books, pupils, the way to school, income, remarks, free text.
QUOTE_ORDER = [29, 28, 40, 41, 15, 16, 19, 17, 30, 31, 32, 8, 45, 55, 57, 58, 59, 60, 61]


def stapfer_index(data_dir: Path) -> dict:
    """Compact index of the Stapfer database (built once from the SQL dump, ~5 s, then read from JSON)."""
    global _INDEX
    if _INDEX:
        return _INDEX
    path = data_dir / "stapfer" / "oral_index.json"
    if path.exists():
        _INDEX = json.loads(path.read_text(encoding="utf-8"))
        return _INDEX
    z = zipfile.ZipFile(data_dir / "stapfer" / "stapferappdb_final.sql.zip")
    t = stapfer.load_dump(z.read(z.namelist()[0]).decode("utf-8", "replace"))
    cat = {c["id_ortskategorie"]: c["ortskategorie"] for c in t["t_ort_kategorie"]}
    places = {}
    for o in t["t_ort"]:
        a, b = o.get("ort_breite"), o.get("ort_laenge")
        if not (a and b and o.get("ort_name")):
            continue
        lat, lon = lv03_to_wgs84(max(a, b), min(a, b))
        places[o["id_ort"]] = {
            "id": o["id_ort"], "name": o["ort_name"].strip(), "municipality": _clean(o.get("ort_gemeinde_aktuell")),
            "canton": _clean(o.get("ort_kanton_aktuell")), "canton_1799": _clean(o.get("ort_kanton_1799")),
            "district_1799": _clean(o.get("ort_distrikt")), "confession": _clean(o.get("ort_konfession")),
            "market": bool(o.get("ort_marktort_ist")), "category": cat.get(o.get("f_id_ortskategorie")),
            "population_1799": o.get("ort_einwohnerzahl_1799"), "altitude": o.get("ort_hoehenlage"), "lat": lat, "lon": lon, "schools": []}
    q = {f["id_frage"]: f for f in t["t_frage"]}
    answers = {}
    for a in t["t_antwort"]:
        if a.get("antwort"):
            answers.setdefault(a["f_id_transkription"], []).append(a)
    trans = {x["id_transkription"]: x for x in t["t_transkription"]}
    teachers = {l["id_lehrer"]: l for l in t["t_lehrer"]}
    jobs = {b["id_beruf"]: b["beruf_normiert"] for b in t["t_beruf"]}
    jobs_of, wages_of, t_of, subj_of = {}, {}, {}, {}
    for r in t["r_lehrer_beruf"]:
        if jobs.get(r["f_id_beruf"]):
            jobs_of.setdefault(r["f_id_lehrer"], []).append(jobs[r["f_id_beruf"]])
    for w in t["t_lohn_geld"]:
        if w.get("lohn_geld_betrag"):
            wages_of.setdefault((w["f_id_lehrer"], w["f_id_schule"]), []).append(f'{w["lohn_geld_betrag"]} {w.get("lohn_geld_waehrung") or ""}'.strip())
    for r in t["r_lehrer_schule"]:
        t_of.setdefault(r["f_id_schule"], []).append(r["f_id_lehrer"])
    for r in t["r_schule_schulfach"]:
        subj_of.setdefault(r["f_id_schule"], []).append(r["f_schulfach_name"])
    pupils = {p["id_schueler"]: p for p in t["t_schueler"]}
    periods = {p["id_schulperiode"]: p for p in t["t_schulperiode"]}
    for s in t["t_schule"]:
        pl = places.get(s.get("f_id_ort"))
        if not pl:
            continue
        p, per, tr = pupils.get(s.get("f_id_schueler")) or {}, periods.get(s.get("f_id_schulperiode")) or {}, trans.get(s.get("f_id_transkription")) or {}
        tl = []
        for lid in t_of.get(s["id_schule"], []):
            l = teachers.get(lid)
            if l and (l.get("lehrer_name") or l.get("lehrer_vorname")):
                tl.append({"name": " ".join(filter(None, [_clean(l.get("lehrer_vorname")), _clean(l.get("lehrer_name"))])),
                           "surname": _clean(l.get("lehrer_name")), "age": l.get("lehrer_alter"), "origin": _clean(l.get("lehrer_herkunft")),
                           "marital_status": _clean(l.get("lehrer_zivilstand")), "family_size": l.get("lehrer_familie_groesse"),
                           "teaching_years": l.get("lehrer_seit"), "other_work": list(dict.fromkeys(jobs_of.get(lid, []))),
                           "description": _clean(l.get("lehrer_beschreibung")), "wages": wages_of.get((lid, s["id_schule"]), [])})
        quotes = []
        for a in sorted(answers.get(s.get("f_id_transkription"), []), key=lambda a: QUOTE_ORDER.index(a["f_id_frage"]) if a["f_id_frage"] in QUOTE_ORDER else 99):
            f = q.get(a["f_id_frage"], {})
            txt = re.sub(r"\s+", " ", str(a["antwort"])).strip()
            if a["f_id_frage"] in QUOTE_ORDER and len(txt) > 25 and all(x["answer"] != txt[:260] for x in quotes):
                quotes.append({"q": f.get("frage_nummer"), "question": f.get("frage"), "answer": txt[:260]})
        pl["schools"].append({
            "name": _clean(s.get("schule_name")), "type": _clean(s.get("schule_schultypus")), "confession": _clean(s.get("schule_konfession")),
            "fee": _clean(s.get("schule_schulgeld")), "pupils_winter": p.get("schueler_anzahl_winter"), "pupils_summer": p.get("schueler_anzahl_sommer"),
            "winter_school_from": _clean(per.get("schulperiode_winterschule_von")), "hours_per_day_winter": per.get("schulperiode_schuldauer_tag_winter"),
            "hours_per_day_summer": per.get("schulperiode_schuldauer_tag_sommer"), "subjects": subj_of.get(s["id_schule"], []),
            "teachers": tl, "signature": _clean(tr.get("transkription_quelle_signatur")),
            "author": " ".join(filter(None, [_clean(tr.get("transkription_verfasser_vorname")), _clean(tr.get("transkription_verfasser_name"))])) or None,
            "quotes": quotes[:10]})
    _INDEX = {"places": list(places.values())}
    path.write_text(json.dumps(_INDEX, ensure_ascii=False), encoding="utf-8")
    return _INDEX


def suggest(data_dir: Path, q: str, n: int = 8) -> list[dict]:
    f = fold(q)
    if len(f) < 2:
        return []
    scored = []
    for p in stapfer_index(data_dir)["places"]:
        names = [fold(p["name"]), fold(p["municipality"])]
        s = 0 if f in names else 1 if any(x.startswith(f) for x in names) else 2 if any(f in x for x in names) else None
        if s is not None:
            scored.append((s, -len(p["schools"]), p["name"], p))
    out = [{"id": p["id"], "name": p["name"], "municipality": p["municipality"], "canton": p["canton"],
            "schools": len(p["schools"]), "source": "stapfer"} for *_, p in sorted(scored, key=lambda x: x[:3])[:n]]
    # every current municipality too (swisstopo), unless a 1799 place of the same name and canton is already listed
    seen = {(fold(x["name"]), x["canton"]) for x in out} | {(fold(x["municipality"]), x["canton"]) for x in out}
    for m in origin.search(data_dir, q, n):
        if (fold(m["name"]), m["canton"]) not in seen:
            out.append({"id": m["id"], "name": m["name"], "municipality": m["name"], "canton": m["canton"], "schools": 0,
                        "source": "municipality"})
    exact = lambda x: 0 if fold(x["name"]) == f else 1 if fold(x["name"]).startswith(f) else 2
    return sorted(out, key=lambda x: (exact(x), x["source"] != "stapfer"))[:n + 4]


def _place(data_dir: Path, pid) -> dict:
    if isinstance(pid, str) and pid.startswith("m"):  # a current municipality (origin.py), not a 1799 place
        return origin.place(data_dir, pid)
    for p in stapfer_index(data_dir)["places"]:
        if p["id"] == pid:
            return p
    raise KeyError(pid)


# --- Language of the place --------------------------------------------------------------------------------
SPOKEN = {"de": "German (as spoken in Switzerland, written in standard German)", "fr": "French", "it": "Italian", "rm": "Romansh"}
FRENCH_CANTONS = {"Waadt", "Vaud", "Genf", "Genève", "Neuenburg", "Neuchâtel", "Jura"}
ITALIAN_CANTONS = {"Tessin", "Ticino"}
_STOP = {"fr": r"\b(le|la|les|et|des|du|est|une|qui|dans|il|sont|pour)\b",
         "de": r"\b(der|die|das|und|ist|ein|eine|nicht|mit|von|zu|sind|hat)\b",
         "it": r"\b(il|di|che|della|nel|una|sono|per|gli|scuola|maestro)\b",
         "rm": r"\b(ils|las|cun|ina|nus|dad|scola|ei|ein|vegn)\b"}


def _text_language(text: str) -> str | None:
    t = (text or "").lower()
    scores = {k: len(re.findall(rx, t)) for k, rx in _STOP.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else None


def place_language(data_dir: Path, home: dict) -> tuple[str, str]:
    """(language code, how it was decided): the language the place's own 1799 answers were written in, else that of
    the nearest schools within 15 km, else the canton's language. Decided from data, never by the model."""
    if home.get("canton") in FRENCH_CANTONS:
        return "fr", f"canton {home['canton']}"
    if home.get("canton") in ITALIAN_CANTONS:
        return "it", f"canton {home['canton']}"
    here = (home["lat"], home["lon"])
    near = sorted(((km(here, (p["lat"], p["lon"])), p) for p in stapfer_index(data_dir)["places"] if p["schools"]), key=lambda x: x[0])
    votes = {}
    for d, p in [(d, p) for d, p in near if d <= 15][:5]:
        lang = _text_language(" ".join(q["answer"] for s in p["schools"] for q in s["quotes"]))
        if lang:
            if d < 0.5:
                return lang, f"1799 survey answers of {p['name']}"
            votes[lang] = votes.get(lang, 0) + 1
    if votes:
        return max(votes, key=votes.get), "1799 survey answers of the nearest schools"
    return "de", "default (no language evidence)"


# --- Sources ----------------------------------------------------------------------------------------------
def _school_lines(p: dict, s: dict) -> list[str]:
    out = [f'{p["name"]} 1799: {s.get("type") or "school"}'
           + (f', {s["confession"].lower()}' if s.get("confession") else "")
           + (f', {s["pupils_winter"]} pupils in winter' if s.get("pupils_winter") else "")
           + (f', {s["pupils_summer"]} in summer' if s.get("pupils_summer") else "")
           + (f', winter school from {s["winter_school_from"]}' if s.get("winter_school_from") else "")
           + (f', {s["hours_per_day_winter"]} hours a day in winter' if s.get("hours_per_day_winter") else "")
           + (f'; subjects: {", ".join(s["subjects"])}' if s.get("subjects") else "")]
    for t in s["teachers"]:
        out.append(f'{p["name"]} 1799, teacher {t["name"]}'
                   + (f', aged {t["age"]}' if t.get("age") else "") + (f', from {t["origin"]}' if t.get("origin") else "")
                   + (f', {t["marital_status"]}' if t.get("marital_status") else "")
                   + (f', family of {t["family_size"]}' if t.get("family_size") else "")
                   + (f', teaching for {t["teaching_years"]} years' if t.get("teaching_years") else "")
                   + (f'; also works as: {", ".join(t["other_work"])}' if t.get("other_work") else "")
                   + (f'; paid {", ".join(t["wages"])}' if t.get("wages") else "")
                   + (f'; {t["description"]}' if t.get("description") else ""))
    for qu in s["quotes"][:6]:
        out.append(f'{p["name"]} 1799, answer to "{qu["question"]}": "{qu["answer"]}"')
    return out


def sources(data_dir: Path, cfg: dict, surname: str, place_id: int, year: int) -> dict:
    """Evidence pack for one family and place (cached; contains no user stories)."""
    cache = data_dir / "oral" / "sources"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{fold(surname).replace(' ', '_')}_{place_id}_{year}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    ua = cfg["enrich"]["user_agent"]
    idx = stapfer_index(data_dir)
    home = _place(data_dir, place_id)
    here = (home["lat"], home["lon"])
    near = sorted(((km(here, (p["lat"], p["lon"])), p) for p in idx["places"] if p["id"] != home["id"]), key=lambda x: x[0])
    src, places = [], {}

    def add(kind, text, **extra):
        src.append({"ref": f"{kind}{sum(1 for s in src if s['kind'] == kind) + 1}", "kind": kind, "text": text, **extra})

    def keep_place(p, role, d=0.0):
        places.setdefault(p["name"], {"name": p["name"], "lat": p["lat"], "lon": p["lon"], "role": role, "km": round(d, 1)})

    keep_place(home, "home")
    if home.get("today_only"):  # a current municipality that the 1799 survey does not list
        nearest = ", ".join(f'{p["name"]} ({round(d)} km)' for d, p in near[:3])
        add("S", f'{home["name"]} ({home.get("canton") or "?"}) is not among the places of the 1799 survey; the nearest surveyed places '
                 f'are {nearest}.', label="Stapfer-Enquête 1799", url="https://stapferenquete.ch/")
    else:
        add("S", f'{home["name"]} in 1799: {home.get("category") or "place"} in the canton of {home.get("canton_1799") or "?"} '
                 f'(district {home.get("district_1799") or "?"}), today {home.get("municipality") or home["name"]} ({home.get("canton") or "?"}); '
                 f'confession {home.get("confession") or "not recorded"}' + ("; a market town" if home.get("market") else "")
                 + (f'; {home["population_1799"]} inhabitants in 1799' if home.get("population_1799") else ""),
            label=f'Stapfer-Enquête 1799 · {home["name"]}', url="https://stapferenquete.ch/")
    # The 1799 school survey describes the time of the story only until about 1830; later it is background.
    school_places = [(0.0, home)] if home["schools"] else [(d, p) for d, p in near if p["schools"]][:1]
    for d, p in school_places if year <= 1830 else []:
        keep_place(p, "school", d)
        for s in p["schools"][:2]:
            for line in _school_lines(p, s):
                add("S", line, label=f'Stapfer-Enquête 1799 · {p["name"]}' + (f' · {s["signature"]}' if s.get("signature") else ""),
                    url="https://stapferenquete.ch/")
    markets = [(d, p) for d, p in near if p["market"] and d <= 30][:3]
    for d, p in markets:
        keep_place(p, "market town", d)
        add("S", f'{p["name"]}, {round(d)} km from {home["name"]}, was a market town in 1799 (canton {p.get("canton_1799") or "?"}).',
            label=f'Stapfer-Enquête 1799 · {p["name"]}', url="https://stapferenquete.ch/")
    for d, p in near[:6]:
        keep_place(p, "neighbouring place", d)
    sf = fold(surname)
    namesakes = []
    for p in idx["places"]:
        for s in p["schools"]:
            for t in s["teachers"]:
                if fold(t.get("surname")) == sf:
                    namesakes.append((km(here, (p["lat"], p["lon"])), p, t))
    for d, p, t in sorted(namesakes, key=lambda x: x[0])[:4] if year <= 1850 else []:
        keep_place(p, "namesake", d)
        add("S", f'In 1799 a teacher with the family name {surname}, {t["name"]}'
                 + (f', aged {t["age"]}' if t.get("age") else "") + f', taught at {p["name"]} ({round(d)} km away)'
                 + (f'; also: {", ".join(t["other_work"])}' if t.get("other_work") else "") + ".",
            label=f'Stapfer-Enquête 1799 · {p["name"]}', url="https://stapferenquete.ch/")
    for term, why in ((surname, "family name"), (home["name"], "place")):
        try:
            units = topic.archive_dossiers(term, limit=40)
        except Exception:
            units = []
        units = [u for u in units if re.search(rf"\b{re.escape(fold(term))}\b", fold(u["title"]))]
        # privacy: keep units begun before 1950 (beyond the protection period for personal data), nearest in time first
        units = [u for u in units if (m := re.search(r"\d{4}", u.get("date") or "")) and int(m.group(0)) < 1950]
        units.sort(key=lambda u: abs((int(m.group(0)) if (m := re.search(r"\d{4}", u.get("date") or "")) else 3000) - year))
        for u in units[:5]:
            add("A", f'Federal Archives unit ({why}): "{u["title"]}"' + (f', {u["date"]}' if u.get("date") else ""),
                label=u["title"], url=u["portal_url"], reference_code=u.get("reference_code"), date=u.get("date"))
    wp = None
    try:
        cands = topic.wikipedia_candidates(f'{home.get("municipality") or home["name"]} {home.get("canton") or ""} Switzerland', ua, 3)
        wp = topic.wikipedia_page(cands[0]["title"], ua) if cands else None
    except Exception:
        pass
    if wp and wp.get("extract"):
        add("W", wp["extract"][:900], label=f'Wikipedia · {wp["title"]}', url=wp.get("url"), license="CC BY-SA 4.0")
    # Period sources (period.py): census 1850-2000, Federal Gazette, key events of the years around the story
    muni = home.get("municipality") or home["name"]
    for line in period.census_lines(data_dir, muni, year):
        add("C", line, label=f"Federal population census · {muni}", url="https://www.bfs.admin.ch/asset/de/px-x-4004000000_101")
    gaz_lang, _ = place_language(data_dir, home)
    for g in period.gazette(ua, data_dir / "oral" / "gazette_cache", surname, muni, year, gaz_lang):
        add("G", f'{g["series"] or "Federal Gazette"} {g["year"]}, "{g["title"]}" (names the {g["why"]}): {g["passage"]}',
            label=f'{g["series"] or "Federal Gazette"} {g["year"]}' + (f', vol. {g["volume"]}, p. {g["page"]}' if g.get("page") else "") + f' · {g["title"][:90]}',
            url=g["url"], pdf=g["pdf"], date=str(g["year"]))
    for e in years.load_events(data_dir):
        if e["year"] <= year <= e["end"] + 12:  # what had happened by the story year, up to a dozen years before
            add("E", f'{e["title"]} ({e["year"]}' + (f'–{e["end"]}' if e["end"] != e["year"] else "") + f'): {e["summary"]}',
                label=f'Key event · {e["title"]}', url=e["hls"], event_year=e["year"])
    out = {"surname": surname, "home": {k: home[k] for k in ("id", "name", "municipality", "canton", "canton_1799", "lat", "lon", "confession")},
           "sources": src, "places": list(places.values()), "namesakes": len(namesakes),
           "newspapers": period.newspaper_links(muni, year), "map": period.map_layer(year, cfg["paths"]["site_dir"])}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# --- Story ------------------------------------------------------------------------------------------------
SYSTEM = """You are a historian who helps a person imagine the daily life of an ancestor in Switzerland.
You write an evocative but careful reconstruction from numbered sources: [S#] the Stapfer school survey of 1799,
[C#] the federal population census, [G#] the Federal Gazette and other official publications (passages that name
the family or the place), [E#] key events of Swiss history in those years, [A#] units of the Swiss Federal Archives,
[W#] Wikipedia, [O#] the family's own oral tradition.
Rules:
- The ancestor is an ordinary person of the given family name living in the given place around the given year.
  Never claim that a source is about the ancestor unless it names them; namesakes are only "perhaps relatives".
- Every sentence lists the sources it relies on. A sentence that imagines details no source supports gets no
  sources: that is allowed, it will be shown as imagined. Keep imagined details plausible for the period and place.
- Oral tradition [O#] is the family's memory: use it, cite it, but do not present it as archival fact.
- The story is set in the given year: describe that period (work, transport, schooling, prices, events of [E#]);
  sources from other periods (the 1799 survey for a later story) are background and must be dated as such.
- People named in [G#] or [A#] passages are at most "perhaps relatives" or neighbours; never invent private details
  about named people.
- The sources inform you, the narrator: the characters never read, quote or talk about them (no one reads the
  Gazette or the census about their own family).
- Write the story sentences in {reader} (quotes from the sources may stay in their language).
- Organise the story as 4 to 6 stops of the ancestor's year, in the order they would be visited, starting at home.
  Each stop's place MUST be exactly one of the "Places" names listed (without the role), or a place named in the
  oral tradition. Prefer stops in different places, so the map shows a route.
- Also write a short first-person monologue (90-140 words) of the ancestor IN {spoken}, the language of the home
  place (whatever language the sources are in), in simple words a person of that time could have used, plus a
  translation into {reader}. No anachronisms.
Return one JSON object."""


def story(data_dir: Path, cfg: dict, ap, surname: str, place_id: int, year: int, first_name: str | None, oral: list[str],
          lang: str = "en") -> dict:
    from . import i18n
    reader = i18n.language(lang)
    pack = sources(data_dir, cfg, surname, place_id, year)
    src = list(pack["sources"])
    for i, o in enumerate([o.strip() for o in oral if o and o.strip()][:12], 1):
        src.append({"ref": f"O{i}", "kind": "O", "text": o[:600], "label": "Oral tradition (given by you)"})
    places = list(pack["places"])
    sent = {"text": f"<sentence in {reader}>", "sources": ["<S#|C#|G#|E#|A#|W#|O#>"]}
    home_lang, lang_how = place_language(data_dir, _place(data_dir, place_id))
    spoken = SPOKEN[home_lang]
    schema = {"title": "<short title>",
              "stops": [{"place": "<one of the Places>", "season": "<season or month>", "activity": "<a few words>",
                         "sentences": [sent, sent]}],  # sentences in the reader's language
              "monologue": f"<first person, in {spoken}>", "monologue_en": f"<translation into {reader}>"}
    who = " ".join(filter(None, [first_name, surname]))
    user = (f"Ancestor: {who}, from {pack['home']['name']} ({pack['home'].get('municipality') or ''}, {pack['home'].get('canton') or ''}), around {year}.\n\n"
            "Places (name, role, km from home):\n" + "\n".join(f"- {p['name']} ({p['role']}, {p['km']} km)" for p in places)
            + "\n\nSources:\n" + "\n".join(f"[{s['ref']}] {s['text']}" for s in src)
            + "\n\nReturn:\n" + json.dumps(schema, ensure_ascii=False))
    raw, meta = ap.chat_json([{"role": "system", "content": SYSTEM.format(reader=reader, spoken=spoken)}, {"role": "user", "content": user}])
    allowed = {s["ref"] for s in src}
    by_name = {fold(p["name"]): p for p in places}
    gaz = {fold(p["name"]): p for p in stapfer_index(data_dir)["places"]}
    geo = _GeoCache(data_dir / "oral" / "geocode.json")
    stops = []
    for st in raw.get("stops") or []:
        if not isinstance(st, dict):
            continue
        sents = []
        for s in st.get("sentences") or []:
            if isinstance(s, dict) and str(s.get("text", "")).strip():
                refs = [x for x in (str(r).strip("[] ") for r in s.get("sources") or []) if x in allowed]
                sents.append({"text": s["text"].strip(), "sources": refs, "imagined": not refs})
        name = re.sub(r"\s*\((home|school|market town|neighbouring place|namesake)[^)]*\)\s*$", "", str(st.get("place") or "")).strip()
        p = by_name.get(fold(name)) or gaz.get(fold(name))
        where = {"lat": p["lat"], "lon": p["lon"], "located_by": "Stapfer gazetteer (swisstopo coordinates)"} if p else None
        if not where and name:
            g = enrich.geocode(name, "ch", geo, cfg)
            geo.save()
            if g:
                where = {"lat": g["lat"], "lon": g["lon"], "located_by": "OpenStreetMap (Nominatim)"}
        if sents:
            stops.append({"place": name, "season": st.get("season"), "activity": st.get("activity"), "sentences": sents, **(where or {"lat": None, "lon": None})})
    used = {r for st in stops for s in st["sentences"] for r in s["sources"]}
    return {"generated": True, "model": meta.get("model"), "seconds": round(meta.get("seconds", 0), 1),
            "title": raw.get("title"), "ancestor": who, "year": year, "home": pack["home"], "language": home_lang, "language_by": lang_how,
            "stops": stops, "monologue": raw.get("monologue"), "monologue_en": raw.get("monologue_en"),  # monologue_en: translation into the reader's language
            "reader_lang": lang,
            "sources": [s for s in src if s["ref"] in used], "offered": {k: sum(1 for s in src if s["kind"] == k) for k in "SCGEAWO"},
            "newspapers": pack.get("newspapers", []), "map": pack.get("map"),
            "imagined_sentences": sum(s["imagined"] for st in stops for s in st["sentences"]),
            "namesakes": pack["namesakes"]}


class _GeoCache:
    """Minimal stand-in for enrich.Cache (geocode() only reads and writes .data)."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


# --- Photos -----------------------------------------------------------------------------------------------
PICK = """You choose photographs from the image archive of the ETH Library to illustrate the stops of an imagined
story of a Swiss ancestor around a given year. The photos are much later than the story; that is expected, and each
caption will say how many years lie in between. A photo illustrates the PLACE and its landscape (the village, its
houses, fields, valley, river, market square), not the exact scene of the story: a school-day stop can show the
village where the school stood. For each stop pick one id from THAT stop's candidates: a photo of the stop's place
or of the place it was found by, then a similar landscape nearby; prefer the photo closest in time to the
story year, then the closest in distance; avoid
photos dominated by modern things (cars, trolleybuses, power plants, quarries, military sites) when another fits.
Stops at the same place get different photos (each id at most once). Use null only when every candidate is
unsuitable. Answer for every stop listed, with a one-sentence reason. Return one JSON object."""


def pick_photos(data_dir: Path, cfg: dict, ap, year: int, stops: list[dict], home: dict | None = None) -> dict:
    ua = cfg["enrich"]["user_agent"]
    cands = {}
    for i, st in enumerate(stops):
        if st.get("lat") is None:
            continue
        about = " ".join([st.get("activity") or "", st.get("season") or ""] + [s["text"] for s in st.get("sentences", [])])
        others = sorted((s2 for s2 in stops if s2.get("lat") is not None and s2.get("place") != st.get("place")),
                        key=lambda s2: km((st["lat"], st["lon"]), (s2["lat"], s2["lon"])))
        also = [(home["name"], home["lat"], home["lon"])] if home else []
        also += [(s2["place"], s2["lat"], s2["lon"]) for s2 in others[:2]]
        cands[i] = photos.near(st["lat"], st["lon"], st.get("place") or "", ua, data_dir / "oral" / "commons_cache",
                               want=12, about=about, also=also, year=year)
    if not cands:
        return {"picks": []}
    lines = []
    for i, cs in cands.items():
        st = stops[i]
        lines.append(f"Stop {i}: {st.get('place')} — {st.get('season') or ''}, {st.get('activity') or ''}. "
                     + " ".join(s["text"] for s in st.get("sentences", [])[:2]))
        lines += [f"  id {c['id']}: {c['year'] or 'undated'}; {c['title']}; {c['description'][:160]}; "
                  f"{c['distance_km'] if c['distance_km'] is not None else '?'} km" for c in cs]
    schema = {"stops": [{"stop": i, "photo": "<id or null>", "reason": "<one sentence>"} for i in cands]}
    raw, meta = ap.chat_json([{"role": "system", "content": PICK},
                              {"role": "user", "content": f"Year of the story: {year}\n\n" + "\n".join(lines) + "\n\nReturn:\n" + json.dumps(schema)}])
    picks = []
    for x in raw.get("stops") or []:
        try:
            i = int(x.get("stop"))
        except (TypeError, ValueError):
            continue
        # any offered candidate may illustrate the stop (stops share nearby photos); distance is to this stop
        c = next((c for cs in ([cands.get(i, [])] + list(cands.values())) for c in cs if c["id"] == str(x.get("photo"))), None)
        if c and i in cands and all(p["photo"]["id"] != c["id"] for p in picks):  # one photo illustrates one stop
            st = stops[i]
            c = c | {"distance_km": round(km((st["lat"], st["lon"]), (c["lat"], c["lon"])), 1) if c.get("lat") is not None else None}
            picks.append({"stop": i, "photo": c, "reason": x.get("reason"), "years_apart": (c["year"] - year) if c.get("year") else None})
    return {"picks": picks, "candidates": {i: len(c) for i, c in cands.items()}, "model": meta.get("model")}
