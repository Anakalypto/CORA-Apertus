"""Enrichment: geocoding, Wikidata entity linking and the document's story trail ("retracé").

Coordinates on the map come from a gazetteer (Nominatim / OpenStreetMap), never from the
model; Apertus' own coordinates are kept only to measure their accuracy in qc.py.
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request

from .classify import BAR_HOLDER

COUNTRY_NAMES = {"switzerland", "schweiz", "suisse", "svizzera", "ch"}


class Cache:
    def __init__(self, path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


def _get(url: str, ua: str):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def haversine_km(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def geocode(name: str, country: str | None, cache: Cache, cfg) -> dict | None:
    key = f"{name}|{(country or '').upper()}"
    if key in cache.data:
        return cache.data[key]
    params = {"q": name, "format": "jsonv2", "limit": 1, "addressdetails": 0}
    if country and re.fullmatch(r"[A-Za-z]{2}", country):
        params["countrycodes"] = country.lower()
    time.sleep(1.1)  # Nominatim usage policy: max 1 request per second
    try:
        hits = _get(cfg["enrich"]["geocoder_url"] + "?" + urllib.parse.urlencode(params), cfg["enrich"]["user_agent"])
    except Exception:
        return None
    res = None
    if hits:
        h = hits[0]
        res = {"lat": float(h["lat"]), "lon": float(h["lon"]), "display_name": h.get("display_name"),
               "osm": f'https://www.openstreetmap.org/{h.get("osm_type")}/{h.get("osm_id")}',
               "type": h.get("type"), "place_rank": h.get("place_rank")}
    cache.data[key] = res
    return res


def wikidata(name: str, cache: Cache, cfg) -> dict | None:
    key = "wd|" + name
    if key in cache.data:
        return cache.data[key]
    params = {"action": "wbsearchentities", "search": name, "language": "de", "uselang": "en",
              "limit": 3, "format": "json", "type": "item"}
    time.sleep(0.3)
    try:
        hits = _get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params),
                    cfg["enrich"]["user_agent"]).get("search", [])
    except Exception:
        return None
    res = None
    norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
    for h in hits:  # accept only an exact label/alias match; no fuzzy guesses
        if norm(h.get("label")) == norm(name) or norm(h.get("match", {}).get("text")) == norm(name):
            res = {"qid": h["id"], "label": h.get("label"), "description": h.get("description"),
                   "url": f'https://www.wikidata.org/wiki/{h["id"]}'}
            break
    cache.data[key] = res
    return res


SWISS = re.compile(r"\b(swiss|switzerland|schweiz\w*|suisse|svizzera|helvetic|federal assembly|confederation)\b", re.I)
OTHER_STATE = re.compile(r"\b(german states|germany|austria|austrian|bundestag|united states)\b", re.I)


def wikidata_org(name: str, cache: Cache, cfg) -> dict | None:
    """Organisation linking: exact label/alias match, preferring Swiss items; never a generic concept
    ('type of …') or an item explicitly about another state (German Bundesrat for the Swiss one)."""
    key = "wdorg|" + name
    if key in cache.data:
        return cache.data[key]
    time.sleep(0.3)
    try:
        hits = _get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbsearchentities", "search": name, "language": "de", "uselang": "en", "limit": 7,
             "format": "json", "type": "item"}), cfg["enrich"]["user_agent"]).get("search", [])
    except Exception:
        return None
    norm = lambda x: re.sub(r"\W+", " ", (x or "").lower()).strip()
    exact = [h for h in hits if norm(h.get("label")) == norm(name) or norm(h.get("match", {}).get("text")) == norm(name)]
    ok = [h for h in exact if not (h.get("description") or "").lower().startswith(("type of", "class of", "wikimedia"))
          and not OTHER_STATE.search(h.get("description") or "")]
    ok.sort(key=lambda h: not SWISS.search(h.get("description") or ""))
    if len(name.strip()) <= 4:  # bare acronyms (SRG, IPU, DRS) are too ambiguous unless the item is Swiss
        ok = [h for h in ok if SWISS.search(h.get("description") or "")]
    res = None
    if ok:
        h = ok[0]
        res = {"qid": h["id"], "label": h.get("label"), "description": h.get("description"),
               "url": f'https://www.wikidata.org/wiki/{h["id"]}'}
    cache.data[key] = res
    return res


def life_dates(qid: str, cache: Cache, cfg) -> dict:
    """Birth/death years (P569/P570) of a Wikidata item, cached."""
    key = "life|" + qid
    if key in cache.data:
        return cache.data[key]
    time.sleep(0.3)
    try:
        ent = _get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"}),
            cfg["enrich"]["user_agent"])["entities"][qid]["claims"]
    except Exception:
        return {"born": None, "died": None}

    def year(prop):
        for c in ent.get(prop, []):
            t = (c.get("mainsnak", {}).get("datavalue") or {}).get("value", {}).get("time")
            m = re.match(r"([+-]\d+)-", t or "")
            if m:
                return int(m.group(1))
        return None
    res = {"born": year("P569"), "died": year("P570")}
    cache.data[key] = res
    return res


def check_life_dates(life: dict, doc_from: int | None, doc_to: int | None) -> tuple[str, str | None]:
    """'ok' | 'reject' (born after the document) | 'flag' (dead > 50 years before it) | 'unknown'."""
    if not doc_from or not (life.get("born") or life.get("died")):
        return "unknown", None
    doc_to = doc_to or doc_from
    if life.get("born") and life["born"] > doc_to:
        return "reject", f"born {life['born']}, after the document ({doc_to})"
    if life.get("died") and life["died"] < doc_from - 50:
        return "flag", f"died {life['died']}, more than 50 years before the document ({doc_from})"
    return "ok", None


def person_display_name(name: str) -> str:
    """'Guhl, Bernhard: AUT' -> 'Bernhard Guhl' (archive authority form -> natural order)."""
    name = re.sub(r":\s*[A-Z]{2,4}$", "", name.strip())
    name = re.sub(r"^(General|Bundesrat|Nationalrat|Ständerat|Dr\.|Prof\.)\s+", "", name)
    parts = [p.strip() for p in name.split(",")]
    return f"{parts[1]} {parts[0]}" if len(parts) == 2 and parts[1] else name


def _year(d) -> int | None:
    m = re.match(r"\s*(\d{4})", str(d or ""))
    return int(m.group(1)) if m else None


def build_story(row: dict, rec: dict, places: list[dict]) -> list[dict]:
    """Chronological trail: creation/depiction/publication (Apertus + gazetteer) and the
    accession into the Federal Archives (deterministic, from the accession number)."""
    a, d = row["apertus"], row["derived"]
    by_name = {p["name"].lower(): p for p in places if p.get("geo")}
    by_name.update({(p.get("as_written") or "").lower(): p for p in places if p.get("geo")})

    def locate(name):
        if not name:
            return None
        p = by_name.get(name.lower())
        if p:
            return p
        for k, v in by_name.items():
            if k and (k in name.lower() or name.lower() in k):
                return v
        return None

    events = []
    for e in a.get("story") or []:
        if e["event"] == "accession":
            continue  # replaced by the deterministic accession event below
        p = locate(e.get("place"))
        events.append({"event": e["event"], "date": e.get("date"), "place": e.get("place"),
                       "lat": p["geo"]["lat"] if p else None, "lon": p["geo"]["lon"] if p else None,
                       "description": e.get("description"), "source": "apertus"})
    # Places with a role but no story event still belong on the map.
    told = {(e.get("place") or "").lower() for e in events}
    for p in places:
        if p.get("geo") and p["name"].lower() not in told and (p.get("as_written") or "").lower() not in told:
            ev = {"created": "creation", "published": "publication", "depicted": "depicted"}.get(p["role"])
            if ev:
                date = a.get("date_published") if ev == "publication" else a.get("date_created")
                events.append({"event": ev, "date": date, "place": p["name"], "lat": p["geo"]["lat"],
                               "lon": p["geo"]["lon"], "description": f"{p['role'].capitalize()} place", "source": "apertus"})
    events.append({"event": "accession", "date": d["date_archived"], "place": "Bern",
                   "lat": BAR_HOLDER["lat"], "lon": BAR_HOLDER["lon"],
                   "description": f"Accession {', '.join(n for n in d['accession_numbers'] if n)} into the Swiss Federal Archives"
                                  + ("" if d["date_archived"] else " (legacy holdings, year not recorded)"),
                   "source": "record"})
    events.append({"event": "holding", "date": None, "place": BAR_HOLDER["place"],
                   "lat": BAR_HOLDER["lat"], "lon": BAR_HOLDER["lon"],
                   "description": f"Kept at {d['archival_location']['reference_code']}", "source": "record"})
    order = {"creation": 0, "depicted": 1, "publication": 2, "update": 3, "accession": 4, "holding": 5}
    events.sort(key=lambda e: (order.get(e["event"], 9), _year(e["date"]) or 9999))
    return events


def run(cfg):
    data_dir = cfg["paths"]["data_dir"]
    rows = [json.loads(l) for l in (data_dir / "classified.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = {r["id"]: r for r in json.loads((data_dir / "records_raw.json").read_text(encoding="utf-8"))}
    cache = Cache(data_dir / "enrich_cache.json")
    out = []
    for i, row in enumerate(rows):
        if not row.get("apertus"):
            out.append(row)
            continue
        a = row["apertus"]
        places = []
        for p in a["places"]:
            if p["name"].strip().lower() in COUNTRY_NAMES:
                geo = None  # a whole country is not a meaningful map point
            else:
                geo = geocode(p["name"], p.get("country"), cache, cfg)
                if geo is None and p.get("as_written") and p["as_written"] != p["name"]:
                    geo = geocode(p["as_written"], p.get("country"), cache, cfg)
            if geo and (geo.get("place_rank") or 99) <= 4:
                geo = None  # country-level hit: a centroid is not a meaningful map point
            p = dict(p, geo=geo)
            if geo and p.get("lat") is not None:
                p["model_error_km"] = round(haversine_km((p["lat"], p["lon"]), (geo["lat"], geo["lon"])), 1)
            places.append(p)
        persons = []
        for p in a["persons"]:
            display = person_display_name(p["name"])
            wd = wikidata(display, cache, cfg) if cfg["enrich"]["wikidata"] else None
            if wd and not re.search(r"\b(politician|journalist|actor|athlete|footballer|player|singer|artist|writer|"
                                    r"photographer|official|diplomat|lawyer|judge|businessperson|presenter|"
                                    r"officer|general|economist|scientist|composer|director|minister|president|councillor|"
                                    r"industrialist|businessman|activist|leader|soldier|military|monarch|king|queen|human)\b",
                                    (wd.get("description") or "").lower()):
                wd = None  # label matched but the item is not a person
            check = None
            if wd:  # life-date plausibility against the record's own date range
                life = life_dates(wd["qid"], cache, cfg)
                rd = recs[row["id"]]["date"]
                verdict, why = check_life_dates(life, _year(rd.get("from")), _year(rd.get("to")))
                check = {"born": life.get("born"), "died": life.get("died"), "verdict": verdict, "reason": why}
                if verdict == "reject":
                    wd = dict(wd, rejected=True)
            persons.append(dict(p, display_name=display,
                                wikidata=None if wd and wd.get("rejected") else wd,
                                wikidata_rejected=wd if wd and wd.get("rejected") else None,
                                life_date_check=check))
        orgs = [dict(o, wikidata=wikidata_org(o["name"], cache, cfg) if cfg["enrich"]["wikidata"] else None)
                for o in a["organizations"]]
        row["enriched"] = {"places": places, "persons": persons, "organizations": orgs,
                           "story": build_story(row, recs[row["id"]], places) if cfg["classify"]["story_map"] else []}
        out.append(row)
        if i % 10 == 0:
            cache.save()
            print(f"  enriched {i + 1}/{len(rows)}")
    cache.save()
    (data_dir / "enriched.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(f"  wrote data/enriched.jsonl ({len(out)} records)")
