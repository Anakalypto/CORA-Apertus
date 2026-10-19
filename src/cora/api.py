"""CORA REST API + Gallica-style front end.

    python run.py serve        ->  http://127.0.0.1:8000      (front end)
                                   http://127.0.0.1:8000/docs (OpenAPI documentation)
"""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import classify, config, enrich, i18n, lindas, more, qa, referendum, search_index, store, topic
from .apertus import Apertus

CFG = config.load()
DATA = CFG["paths"]["data_dir"]
DATASET = DATA / "dataset"
SITE = CFG["paths"]["site_dir"]


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


# one file per record in dataset/records/; records still only in cora_dataset.jsonl are split out when read
RECORD_STORE = store.Entries(DATASET / "cora_dataset.jsonl")


def _load():
    recs = RECORD_STORE.all()
    for r in recs:
        m, c = r["metadata"], r["classification"]
        r["_text"] = _fold(" ".join(filter(None, [
            m["title"], m.get("title_normalized"), m.get("title_en"), c.get("resume"), m.get("creator"), m.get("publisher"),
            " ".join(m.get("subjects", [])), r["archival_location"].get("fonds"), r["source"]["reference_code"],
            " ".join(p.get("display_name") or p["name"] for p in r["entities"]["persons"]),
            " ".join(p["name"] for p in r["entities"]["places"]),
            " ".join(o["name"] for o in r["entities"]["organizations"]),
            json.dumps(r["source"]["original"], ensure_ascii=False)])))
        y = re.match(r"(\d{4})", m.get("content_date") or m.get("date_created") or "")
        r["_decade"] = f"{y.group(1)[:3]}0s" if y else "unknown"
        c_ = int(y.group(1)) // 100 + 1 if y else None
        r["_century"] = f"{c_}{'st' if c_ % 10 == 1 and c_ != 11 else 'nd' if c_ % 10 == 2 and c_ != 12 else 'rd' if c_ % 10 == 3 and c_ != 13 else 'th'} century" if y else "unknown"
        years = [int(x) for x in re.findall(r"\d{4}", m.get("content_date") or m.get("date_created") or "")]
        r["_years"] = (min(years), max(years)) if years else None
        # Gallica-style field search ("Search in"): one folded string per field
        persons = [p.get("display_name") or p["name"] for p in r["entities"]["persons"]]
        r["_fields"] = {k: _fold(" ".join(filter(None, v))) for k, v in {
            "title": [m["title"], m.get("title_normalized"), m.get("title_en")],
            "creator": [m.get("creator"), r["source"]["original"].get("author")],
            "publisher": [m.get("publisher"), r["source"]["original"].get("publisher")],
            "subject": list(m.get("subjects") or []) + [r["source"]["original"].get("thema")],
            "person": persons + [p["name"] for p in r["entities"]["persons"]],
            "place": [p["name"] for p in r["entities"]["places"]] + [p.get("as_written") for p in r["entities"]["places"]]
                     + [r["source"]["original"].get("coverage")],
            "reference": [r["source"]["reference_code"], r["id"], r["source"]["original"].get("old_reference_code")]
                         + list(r["archival_location"].get("accession_numbers") or []),
            "resume": [c.get("resume"), r["source"]["original"].get("scope_and_content")],
        }.items()}
    return {r["id"]: r for r in recs}


RECORDS = _load()


def _attach_trust():
    cards = DATASET / "trust_cards.jsonl"
    if cards.exists():
        for l in cards.read_text(encoding="utf-8").splitlines():
            if l.strip():
                c = json.loads(l)
                if c["id"] in RECORDS:
                    RECORDS[c["id"]]["trust_card"] = c
    log = DATASET / "edit_log.jsonl"
    if log.exists():
        for l in log.read_text(encoding="utf-8").splitlines():
            if l.strip():
                e = json.loads(l)
                if e["record_id"] in RECORDS:
                    RECORDS[e["record_id"]].setdefault("edits", []).append(e)


_attach_trust()


def _attach_covers():
    """Commons illustrations picked by covers.py (python src/run.py covers); records without one keep the typed cover."""
    path = DATA / "covers.json"
    if path.exists():
        for rid, c in json.loads(path.read_text(encoding="utf-8")).items():
            if rid in RECORDS:
                RECORDS[rid]["cover"] = c


_attach_covers()
QC = json.loads((DATA / "qc_report.json").read_text(encoding="utf-8")) if (DATA / "qc_report.json").exists() else {}
for _b in CFG["paths"].get("batches", []):  # verified batches merged by export.py: their own QC summary
    _p = (config.SRC / _b / "qc_report.json").resolve()
    if _p.exists():
        QC.setdefault("batches", {})[Path(_b).name] = json.loads(_p.read_text(encoding="utf-8"))["summary"] | {
            "online": sum(r.get("batch") == Path(_b).name for r in RECORDS.values())}

app = FastAPI(title="CORA — Apertus classifier for the Swiss Federal Archives",
              description="AI-ready metadata for records of the Swiss Federal Archives, classified by Apertus v1.5. "
                          "Every field carries its provenance (record / derived / apertus / gazetteer / wikidata).",
              version="0.1.0")


@app.middleware("http")
async def _revalidate_front_end(request, call_next):
    """Browsers revalidate the page and its scripts and styles (cheap, via ETag), so an update is never hidden by a cache."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


FACETS = {
    "document_type": lambda r: r["classification"]["document_type"],
    "source_level": lambda r: r["classification"]["source_level"],
    "medium": lambda r: r["classification"]["medium"],
    "decade": lambda r: r["_decade"],
    "century": lambda r: r["_century"],
    "level": lambda r: r["source"].get("level") or "Document",
    "fonds": lambda r: r["archival_location"].get("fonds") or "unknown",
    # Gallica's author / publisher / subject / place facets
    "creator": lambda r: r["metadata"].get("creator") or "unknown",
    "publisher": lambda r: r["metadata"].get("publisher") or "unknown",
    "subject": lambda r: list(dict.fromkeys(r["metadata"].get("subjects") or [])),
    "person": lambda r: list(dict.fromkeys(p.get("display_name") or p["name"] for p in r["entities"]["persons"])),
    "place": lambda r: list(dict.fromkeys(p["name"] for p in r["entities"]["places"])),
    "language": lambda r: (r["metadata"].get("languages") or ["unknown"])[0],
    "preprocessing": lambda r: [k for k, v in (r.get("preprocessing") or {}).items() if v["needed"]],
    "qc": lambda r: "passed" if r["qc"].get("ok") else "issues",
    "sample": lambda r: r.get("stratum") or "unknown",
    "batch": lambda r: r.get("batch") or "demo",
    "flags": lambda r: [f for f, on in (
        ("on_map", any(p.get("lat") is not None for p in r["entities"]["places"])),
        ("story_map", any(e.get("lat") is not None and e.get("event") not in ("holding", "accession") for e in r.get("story") or [])),
        ("names_persons", bool(r["entities"]["persons"])),
        ("wikidata_links", any(e.get("wikidata") for e in r["entities"]["persons"] + r["entities"]["organizations"])),
        ("personal_data", (r.get("personal_data") or {}).get("contains_personal_data")),
        ("has_cover", bool(r.get("cover"))),
        ("has_description", bool(r["source"]["original"].get("scope_and_content"))),  # Gallica's "mode texte"
    ) if on],
}
SEARCH_IN = ["all", "title", "creator", "publisher", "subject", "person", "place", "reference", "resume"]
SORTS = ["relevance", "date_asc", "date_desc", "title", "creator"]


def _public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _summary(r: dict) -> dict:
    m, c = r["metadata"], r["classification"]
    return {"id": r["id"], "title": m["title"], "title_normalized": m.get("title_normalized"), "title_en": m.get("title_en"),
            "document_type": c["document_type"], "medium": c["medium"], "source_level": c["source_level"],
            "resume": c.get("resume"), "date": m.get("content_date") or m.get("date_created"), "creator": m.get("creator"),
            "publisher": m.get("publisher"), "fonds": r["archival_location"].get("fonds"),
            "reference_code": r["source"]["reference_code"], "qc_ok": r["qc"].get("ok"),
            "n_places": sum(1 for p in r["entities"]["places"] if p.get("lat") is not None), "cover": r.get("cover")}


ALL_OF = {"flags", "preprocessing"}  # a record can carry several of these at once: ticked values must all apply


def _matches(r: dict, filters: dict, skip: str | None = None) -> bool:
    """Each filter is a list of flags: plain values are OR-ed within a facet (AND-ed in ALL_OF facets),
    "!value" excludes; facets are AND-ed."""
    for k, vs in filters.items():
        if not vs or k == skip:
            continue
        val = FACETS[k](r)
        have = {str(x) for x in (val if isinstance(val, list) else [val])}
        inc = {v for v in vs if not v.startswith("!")}
        exc = {v[1:] for v in vs if v.startswith("!")}
        if inc and not (inc <= have if k in ALL_OF else have & inc) or have & exc:
            return False
    return True


@app.get("/api/records", summary="Search records: full text or one field (in=), date range, filter flags "
                                  "(repeat a parameter to OR values, prefix '!' to exclude)")
def search(q: str = "", in_: str = Query("all", alias="in", enum=SEARCH_IN),
           date_from: int | None = Query(None, ge=1000, le=2100), date_to: int | None = Query(None, ge=1000, le=2100),
           document_type: list[str] = Query([]), source_level: list[str] = Query([]), medium: list[str] = Query([]),
           decade: list[str] = Query([]), century: list[str] = Query([]), level: list[str] = Query([]),
           fonds: list[str] = Query([]), language: list[str] = Query([]), creator: list[str] = Query([]),
           publisher: list[str] = Query([]), subject: list[str] = Query([]), person: list[str] = Query([]),
           place: list[str] = Query([]), preprocessing: list[str] = Query([]), qc: list[str] = Query([]),
           sample: list[str] = Query([]), flags: list[str] = Query([]),
           sort: str = Query("relevance", enum=SORTS + ["date"]), page: int = 1, size: int = Query(20, ge=0, le=100),
           lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    filters = dict(document_type=document_type, source_level=source_level, medium=medium, decade=decade, century=century,
                   level=level, fonds=fonds, language=language, creator=creator, publisher=publisher, subject=subject,
                   person=person, place=place, preprocessing=preprocessing, qc=qc, sample=sample, flags=flags)
    # direct calls get the Query defaults; "document_type=" (empty) means no filter, as before
    filters = {k: [x for x in v if x and x != "!"] if isinstance(v, list) else [] for k, v in filters.items()}
    in_ = in_ if isinstance(in_, str) and in_ in SEARCH_IN else "all"
    date_from = date_from if isinstance(date_from, int) else None
    date_to = date_to if isinstance(date_to, int) else None
    size = size if isinstance(size, int) else 20
    sort = sort if isinstance(sort, str) else "relevance"
    terms = _fold(q).split()
    text = (lambda r: r["_text"]) if in_ == "all" else (lambda r: r["_fields"][in_])

    def in_range(r):  # Gallica's "date de … à …": the record's date range overlaps the requested one
        if date_from is None and date_to is None:
            return True
        if not r["_years"]:
            return False
        return (date_from is None or r["_years"][1] >= date_from) and (date_to is None or r["_years"][0] <= date_to)

    found = [r for r in RECORDS.values() if (not terms or all(t in text(r) for t in terms)) and in_range(r)]
    hits = [(sum(text(r).count(t) for t in terms), r) for r in found if _matches(r, filters)]
    if sort in ("date", "date_asc"):
        hits.sort(key=lambda h: h[1]["_years"] or (9999, 9999))
    elif sort == "date_desc":
        hits.sort(key=lambda h: h[1]["_years"] or (-1, -1), reverse=True)
    elif sort == "title":
        hits.sort(key=lambda h: _fold(h[1]["metadata"].get("title_normalized") or h[1]["metadata"]["title"]))
    elif sort == "creator":
        hits.sort(key=lambda h: (not h[1]["metadata"].get("creator"), _fold(h[1]["metadata"].get("creator") or "")))
    else:
        hits.sort(key=lambda h: -h[0])
    # Counts per OR facet ignore that facet's own flags, so every value shows how many results ticking it would add;
    # in ALL_OF facets ticking narrows, so their counts are taken within the current results.
    facets = {k: Counter() for k in FACETS}
    for k, f in FACETS.items():
        for r in found:
            if _matches(r, filters, skip=None if k in ALL_OF else k):
                v = f(r)
                for x in (v if isinstance(v, list) else [v]):
                    facets[k][x] += 1
    start = (max(1, page) - 1) * size
    yrs = [r["_years"] for r in RECORDS.values() if r["_years"]]
    return {"total": len(hits), "page": page, "size": size,
            "results": [_localized_summary(r, i18n.code(lang)) for _, r in hits[start:start + size]],
            "facets": {k: c.most_common() for k, c in facets.items()},
            "date_bounds": [min(y[0] for y in yrs), max(y[1] for y in yrs)] if yrs else None,
            "search_in": SEARCH_IN, "sorts": SORTS}


@app.get("/api/records/{record_id}", summary="Full record: original metadata, classification, provenance, story")
def record(record_id: str):
    r = RECORDS.get(record_id)
    if not r:
        raise HTTPException(404, "record not in the demo set; use POST /api/classify/{id} for a live run")
    if not (RECORD_STORE.dir / store.file_name(record_id)).exists():
        RECORD_STORE.get(record_id)  # opening a record that is not split yet splits it
    ids = list(RECORDS)
    i = ids.index(record_id)
    return _public(r) | {"_nav": {"prev": ids[i - 1] if i else None, "next": ids[i + 1] if i + 1 < len(ids) else None}}


def _day_range(s: str | None) -> tuple[str, str] | None:
    """'1914' -> (1914-01-01, 1914-12-31); '1985-10' -> month; '1985-10-22' -> that day; 'a/b' -> start of a, end of b."""
    import calendar
    if not s:
        return None
    parts = [p.strip() for p in str(s).split("/") if p.strip()]

    def bounds(p):
        m = re.match(r"^(\d{4})(?:-(0[1-9]|1[0-2])(?:-(\d{2}))?(?!\d))?", p)  # "1919-1947" is a year range, not month 19
        if not m:
            return None
        y, mo, d = int(m.group(1)), m.group(2), m.group(3)
        if d:
            return f"{y:04d}-{mo}-{d}", f"{y:04d}-{mo}-{d}"
        if mo:
            return f"{y:04d}-{mo}-01", f"{y:04d}-{mo}-{calendar.monthrange(y, int(mo))[1]:02d}"
        return f"{y:04d}-01-01", f"{y:04d}-12-31"
    b = [x for x in map(bounds, parts) if x]
    return (b[0][0], b[-1][1]) if b else None


MAP_LISTS = ["document_type", "source_level", "medium", "decade", "century", "level", "fonds", "language", "creator",
             "publisher", "subject", "person", "place", "preprocessing", "qc", "sample", "flags"]


@app.get("/api/map", summary="Located story events for the overview map, with the same filters as /api/records "
                             "(q, in, date_from/date_to and every facet); each point has an exact start/end day")
def map_points(request: Request):
    qp = request.query_params
    year = lambda k: int(qp[k]) if qp.get(k, "").isdigit() else None
    kw = {k: qp.getlist(k) for k in MAP_LISTS}
    keep = {r["id"] for r in search(q=qp.get("q", ""), in_=qp.get("in", "all"), date_from=year("date_from"),
                                     date_to=year("date_to"), size=100000, **kw)["results"]}
    pts = []
    for r in RECORDS.values():
        if r["id"] not in keep:
            continue
        rec_range = _day_range(r["metadata"].get("content_date") or r["metadata"].get("date_created"))
        for e in r.get("story", []):
            if e.get("lat") is not None and e["event"] not in ("accession", "holding"):
                rng = _day_range(e.get("date")) or rec_range
                pts.append({"id": r["id"], "title": r["metadata"].get("title_normalized") or r["metadata"]["title"],
                            "year": int(rng[0][:4]) if rng else None, "start": rng[0] if rng else None, "end": rng[1] if rng else None,
                            "document_type": r["classification"]["document_type"], **e})
    return {"points": pts, "archive": classify.BAR_HOLDER, "records": len(keep)}


@app.get("/api/stats", summary="Collection statistics")
def stats():
    return {"records": len(RECORDS), "facets": search(size=0)["facets"],
            "qc": QC.get("summary", {}), "population": json.loads((DATA / "sample.json").read_text(encoding="utf-8"))
            .get("population") if (DATA / "sample.json").exists() else None}


@app.get("/api/qc", summary="Quality-check report of the Apertus output")
def qc_report():
    return QC


@app.get("/api/schema", summary="JSON Schema of the AI-ready records")
def schema():
    return json.loads((DATASET / "schema.json").read_text(encoding="utf-8"))


EXPORTS = {"jsonl": "cora_dataset.jsonl", "csv": "cora_dataset.csv", "tsv": "cora_dataset.tsv",
           "edit_log": "edit_log.jsonl", "schema": "schema.json"}


@app.get("/api/export/{fmt}", summary="Download the dataset (jsonl, csv, tsv, edit_log, schema)")
def export(fmt: str):
    if fmt not in EXPORTS:
        raise HTTPException(404, f"choose one of {list(EXPORTS)}")
    return FileResponse(DATASET / EXPORTS[fmt], filename=EXPORTS[fmt])


@app.post("/api/classify/{record_id}", summary="Live: fetch any record of the archive database and classify it with Apertus")
def classify_live(record_id: str, resume: bool = True, story_map: bool = True, lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    if not record_id.isdigit():
        raise HTTPException(400, "record id must be numeric (VRZNG_ENHT_ID)")
    recs = lindas.fetch_records([record_id])
    if not recs:
        raise HTTPException(404, "unknown record id")
    rec = recs[0] | {"stratum": "live"}
    cfg = json.loads(json.dumps(CFG, default=str))
    cfg["classify"]["resume"], cfg["classify"]["story_map"] = resume, story_map
    cfg["classify"]["output_language"] = i18n.code(lang)  # résumé and normalised fields in the reader's language
    l = CFG["llm"]
    ap = lambda feature: Apertus(l["base_url"], l["api_key"], config.model_for(CFG, feature), l["temperature"], l["max_tokens"], l["retries"])
    raw, meta = ap("classify").chat_json(classify.build_messages(rec, cfg))
    result, issues = classify.normalize(raw, rec, cfg)
    araw, ameta = ap("audit").chat_json(classify.build_audit_messages(rec))
    checks, pre, personal = classify.audit_to_flags(araw, rec)
    result["preprocessing"], result["personal_data"], result["audit_checks"] = pre, personal, checks
    # pass 3, as in the pipeline: the source level from explicit archival definitions
    lraw, lmeta = ap("level").chat_json(classify.build_level_messages(rec))
    lvl = classify.level_from_answers(lraw, CFG["classify"].get("press_convention", "secondary"))
    result["source_level_v1"], result["source_level"], result["source_level_pass3"] = result["source_level"], lvl["level"], lvl
    result["source_level_rationale"] = f'{lvl["rule"]}: {lvl["note"] or ""}'.strip(": ")
    result["models"] = {"classify": meta.get("model"), "audit": ameta.get("model"), "level": lmeta.get("model")}
    row = {"id": record_id, "apertus": result, "derived": classify.derived_fields(rec)}
    places = []
    cache = enrich.Cache(DATA / "enrich_cache.json")
    for p in result["places"]:
        geo = None if p["name"].lower() in enrich.COUNTRY_NAMES else enrich.geocode(p["name"], p.get("country"), cache, CFG)
        places.append(dict(p, geo=geo))
    cache.save()
    story = enrich.build_story(row, rec, places) if story_map else []
    return {"record": rec, "classification": result, "derived": row["derived"], "places": places, "story": story,
            "schema_issues": issues, "seconds": round(meta["seconds"] + ameta["seconds"] + lmeta["seconds"], 1)}


# persistent FTS5 index built by `run.py export` (rebuilt here if missing or older than the dataset)
QA_INDEX = search_index.Index(RECORDS, DATASET / "cora_search.sqlite")


def _llm(feature: str = ""):
    """Apertus for one feature: the model chosen per feature in config.toml [llm.models] (default: llm.model)."""
    l = CFG["llm"]
    return Apertus(l["base_url"], l["api_key"], config.model_for(CFG, feature), 0.0, 1500, l["retries"])


@app.get("/api/ask", summary="Ask the archive: cited answer from the dataset (BM25 + Apertus); refuses when nothing relevant is found")
def ask(q: str = Query(..., min_length=3), k: int = 6, record: str = Query("", description="ask about this record (it is always a source)"),
        lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    if record and record not in RECORDS:
        raise HTTPException(404, "unknown record")
    return qa.ask(QA_INDEX, _llm("qa"), q, k, focus=record or None, lang=i18n.code(lang))


@app.post("/api/chat", summary="Ask the archive as a conversation: Apertus answers from archive records and Wikipedia "
                              "(body: {messages: [{role, content}], record?}); every sentence cites R#/W# or is marked own knowledge")
def chat_turn(body: dict = Body(...), lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    from . import chat as chat_mod
    msgs = body.get("messages") or []
    record = body.get("record") or None
    if record and record not in RECORDS:
        raise HTTPException(404, "unknown record")
    try:
        return chat_mod.chat(QA_INDEX, _llm_chat(), msgs, CFG, DATA, record=record, lang=i18n.code(lang))
    except ValueError as e:
        raise HTTPException(400, str(e))


def _llm_chat():
    l = CFG["llm"]
    return Apertus(l["base_url"], l["api_key"], l["model"], 0.1, 2000, l["retries"])


@app.get("/api/consultations", summary="Federal consultations 1960-1991 with Apertus topics/entities and procedure chains")
def consultations():
    path = DATA / "consultations" / "consultations_tagged.json"
    if not path.exists():
        raise HTTPException(404, "run `python src/run.py consultations` first")
    return json.loads(path.read_text(encoding="utf-8"))


PARL_PATH = DATA / "parliament" / "parliament.json"


@app.get("/api/parliament", summary="Members of the National Council, Council of States and Federal Council since 1848, party lineages, BFS vote shares")
def parliament():
    if not PARL_PATH.exists():
        raise HTTPException(404, "run `python src/run.py parliament` first")
    return json.loads(PARL_PATH.read_text(encoding="utf-8"))


@app.post("/api/parliament/links", summary="Wikidata/Wikipedia links for council members (exact name match, Swiss politician, born before the term)")
def parliament_links(people: list[dict]):
    from concurrent.futures import ThreadPoolExecutor
    from . import narrative
    cache = enrich.Cache(DATA / "enrich_cache.json")
    members = {m["pn"]: m for m in json.loads(PARL_PATH.read_text(encoding="utf-8"))["members"]}

    def one(p):
        name = p["name"]
        wd = enrich.wikidata(name, cache, CFG)
        if not wd or not re.search(r"swiss|switzerland|schweiz", (wd.get("description") or ""), re.I) \
                or not re.search(r"politician|federal council|councillor|statesman|lawyer|jurist", wd.get("description") or "", re.I):
            return p["pn"], None
        life = enrich.life_dates(wd["qid"], cache, CFG)
        join = (members.get(p["pn"]) or {}).get("join") or ""
        if life.get("born") and join[:4].isdigit() and life["born"] > int(join[:4]) - 18:
            return p["pn"], None  # implausible: not of age when entering office
        narrative.fetch_context([wd["qid"]], cache, CFG)
        ctx = cache.data.get("ctx|" + wd["qid"], {})
        return p["pn"], {"wikidata": wd["url"], "wikipedia": (ctx.get("wikipedia") or {}).get("url"), "hls": ctx.get("hls")}

    with ThreadPoolExecutor(6) as pool:
        res = dict(pool.map(one, people[:150]))
    cache.save()
    return res


@app.get("/api/referendum", summary="Party-cue referendum model, backtest and the women's-suffrage 1959/1971 estimate")
def referendum_suffrage():
    path = DATA / "referendum" / "suffrage.json"
    if not path.exists():
        raise HTTPException(404, "run `python src/run.py referendum` first")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/votes", summary="Every federal vote since 1848 with its result and the party-cue estimate (Swissvotes)")
def votes():
    return referendum.votes(CFG)


@app.get("/api/votes/{anr}", summary="One federal vote: result, estimate, parliament's vote, party positions; Apertus English title, summary and related votes (cached)")
def vote(anr: str, lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    try:
        return referendum.detail(CFG, anr, _llm("votes"), i18n.code(lang))
    except KeyError:
        raise HTTPException(404, "unknown vote number (anr)")


@app.get("/api/votes/{anr}/whatif", summary="The proposal under the conditions of another year: real positions with that year's strengths, and Apertus-imagined positions (cached)")
def vote_whatif(anr: str, year: int = Query(..., ge=1848, le=2100), lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    try:
        return referendum.whatif(CFG, anr, year, _llm("votes"), i18n.code(lang), _llm("whatif"))
    except KeyError:
        raise HTTPException(404, "unknown vote number (anr)")


@app.get("/api/records/{record_id}/more", summary="See more: Apertus explains the record from the record, related records, Wikipedia and Wikidata (cited, cached)")
def record_more(record_id: str, lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    r = RECORDS.get(record_id)
    if not r:
        raise HTTPException(404, "unknown record")
    return more.explain(r, QA_INDEX, CFG, _llm("more"), i18n.code(lang))


@app.get("/api/records/{record_id}/topic", summary="Topic of a secondary/tertiary record: Wikipedia article, primary dossiers of the archive, news (Apertus-selected, cached)")
def record_topic(record_id: str, lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    r = RECORDS.get(record_id)
    if not r:
        raise HTTPException(404, "unknown record")
    return topic.build(r, QA_INDEX, CFG, _llm("topic"), i18n.code(lang))


@app.get("/api/records/{record_id}/resume", summary="The record's résumé written by Apertus in the reader's language from its original fields (cached)")
def record_resume(record_id: str, lang: str = Query("en", description="interface language (en, de, fr, it, rm): Apertus writes in it")):
    r = RECORDS.get(record_id)
    if not r:
        raise HTTPException(404, "unknown record")
    return more.resume(r, CFG, _llm("more"), i18n.code(lang))


@app.get("/api/i18n/{lang}", summary="Interface text in one of the languages of Switzerland (translated by Apertus; "
                                     "strings not translated yet are translated in the background)")
def interface_text(lang: str):
    code = i18n.code(lang)
    pending = i18n.ensure_background(DATA, SITE, code, _llm_translate)
    return {"lang": code, "languages": i18n.LANGS, "strings": i18n.load(DATA, code), "pending": pending}


def _llm_translate():
    l = CFG["llm"]
    return Apertus(l["base_url"], l["api_key"], l["model"], 0.1, 4000, l["retries"])


def _localized_summary(r: dict, lang: str) -> dict:
    s = _summary(r)
    if lang != "en":
        s["resume"] = more.cached_resume(r, CFG, lang) or s["resume"]
        s["resume_lang"] = lang if more.cached_resume(r, CFG, lang) else "en"
    return s


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(SITE / "index.html")


from . import oral_api  # noqa: E402  year context drawer + Oral tradition (own module; must come before the static mount)
app.include_router(oral_api.router)

app.mount("/", StaticFiles(directory=SITE), name="site")
