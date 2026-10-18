"""CORA REST API + Gallica-style front end.

    python run.py serve        ->  http://127.0.0.1:8000      (front end)
                                   http://127.0.0.1:8000/docs (OpenAPI documentation)
"""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import classify, config, enrich, lindas, qa
from .apertus import Apertus

CFG = config.load()
DATA = CFG["paths"]["data_dir"]
DATASET = DATA / "dataset"
SITE = CFG["paths"]["site_dir"]


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _load():
    path = DATASET / "cora_dataset.jsonl"
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
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
QC = json.loads((DATA / "qc_report.json").read_text(encoding="utf-8")) if (DATA / "qc_report.json").exists() else {}

app = FastAPI(title="CORA — Apertus classifier for the Swiss Federal Archives",
              description="AI-ready metadata for records of the Swiss Federal Archives, classified by Apertus v1.5. "
                          "Every field carries its provenance (record / derived / apertus / gazetteer / wikidata).",
              version="0.1.0")

FACETS = {
    "document_type": lambda r: r["classification"]["document_type"],
    "source_level": lambda r: r["classification"]["source_level"],
    "medium": lambda r: r["classification"]["medium"],
    "decade": lambda r: r["_decade"],
    "fonds": lambda r: r["archival_location"].get("fonds") or "unknown",
    "language": lambda r: (r["metadata"].get("languages") or ["unknown"])[0],
    "preprocessing": lambda r: [k for k, v in (r.get("preprocessing") or {}).items() if v["needed"]],
    "qc": lambda r: "passed" if r["qc"].get("ok") else "issues",
}


def _public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _summary(r: dict) -> dict:
    m, c = r["metadata"], r["classification"]
    return {"id": r["id"], "title": m["title"], "title_normalized": m.get("title_normalized"), "title_en": m.get("title_en"),
            "document_type": c["document_type"], "medium": c["medium"], "source_level": c["source_level"],
            "resume": c.get("resume"), "date": m.get("content_date") or m.get("date_created"), "creator": m.get("creator"),
            "publisher": m.get("publisher"), "fonds": r["archival_location"].get("fonds"),
            "reference_code": r["source"]["reference_code"], "qc_ok": r["qc"].get("ok"),
            "n_places": sum(1 for p in r["entities"]["places"] if p.get("lat") is not None)}


def _matches(r: dict, filters: dict) -> bool:
    for k, v in filters.items():
        if not v:
            continue
        val = FACETS[k](r)
        if isinstance(val, list) and v not in val or not isinstance(val, list) and val != v:
            return False
    return True


@app.get("/api/records", summary="Search records (full text + facets)")
def search(q: str = "", document_type: str = "", source_level: str = "", medium: str = "", decade: str = "",
           fonds: str = "", language: str = "", preprocessing: str = "", qc: str = "",
           sort: str = Query("relevance", enum=["relevance", "date", "title"]), page: int = 1, size: int = 20):
    filters = dict(document_type=document_type, source_level=source_level, medium=medium, decade=decade,
                   fonds=fonds, language=language, preprocessing=preprocessing, qc=qc)
    terms = _fold(q).split()
    hits = []
    for r in RECORDS.values():
        if terms and not all(t in r["_text"] for t in terms):
            continue
        if _matches(r, filters):
            hits.append((sum(r["_text"].count(t) for t in terms), r))
    if sort == "date":
        hits.sort(key=lambda h: h[1]["metadata"].get("content_date") or "9999")
    elif sort == "title":
        hits.sort(key=lambda h: _fold(h[1]["metadata"]["title"]))
    else:
        hits.sort(key=lambda h: -h[0])
    facets = {k: Counter() for k in FACETS}
    for _, r in hits:
        for k, f in FACETS.items():
            v = f(r)
            for x in (v if isinstance(v, list) else [v]):
                facets[k][x] += 1
    start = (max(1, page) - 1) * size
    return {"total": len(hits), "page": page, "size": size,
            "results": [_summary(r) for _, r in hits[start:start + size]],
            "facets": {k: c.most_common() for k, c in facets.items()}}


@app.get("/api/records/{record_id}", summary="Full record: original metadata, classification, provenance, story")
def record(record_id: str):
    r = RECORDS.get(record_id)
    if not r:
        raise HTTPException(404, "record not in the demo set; use POST /api/classify/{id} for a live run")
    ids = list(RECORDS)
    i = ids.index(record_id)
    return _public(r) | {"_nav": {"prev": ids[i - 1] if i else None, "next": ids[i + 1] if i + 1 < len(ids) else None}}


@app.get("/api/map", summary="All story points of all records (for the overview map)")
def map_points():
    pts = []
    for r in RECORDS.values():
        for e in r.get("story", []):
            if e.get("lat") is not None and e["event"] not in ("accession", "holding"):
                y = re.match(r"(\d{4})", r["metadata"].get("content_date") or r["metadata"].get("date_created") or "")
                pts.append({"id": r["id"], "title": r["metadata"].get("title_normalized") or r["metadata"]["title"],
                            "year": int(y.group(1)) if y else None,
                            "document_type": r["classification"]["document_type"], **e})
    return {"points": pts, "archive": classify.BAR_HOLDER}


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
def classify_live(record_id: str, resume: bool = True, story_map: bool = True):
    if not record_id.isdigit():
        raise HTTPException(400, "record id must be numeric (VRZNG_ENHT_ID)")
    recs = lindas.fetch_records([record_id])
    if not recs:
        raise HTTPException(404, "unknown record id")
    rec = recs[0] | {"stratum": "live"}
    cfg = json.loads(json.dumps(CFG, default=str))
    cfg["classify"]["resume"], cfg["classify"]["story_map"] = resume, story_map
    l = CFG["llm"]
    ap = Apertus(l["base_url"], l["api_key"], l["model"], l["temperature"], l["max_tokens"], l["retries"])
    raw, meta = ap.chat_json(classify.build_messages(rec, cfg))
    result, issues = classify.normalize(raw, rec, cfg)
    araw, ameta = ap.chat_json(classify.build_audit_messages(rec))
    checks, pre, personal = classify.audit_to_flags(araw, rec)
    result["preprocessing"], result["personal_data"], result["audit_checks"] = pre, personal, checks
    row = {"id": record_id, "apertus": result, "derived": classify.derived_fields(rec)}
    places = []
    cache = enrich.Cache(DATA / "enrich_cache.json")
    for p in result["places"]:
        geo = None if p["name"].lower() in enrich.COUNTRY_NAMES else enrich.geocode(p["name"], p.get("country"), cache, CFG)
        places.append(dict(p, geo=geo))
    cache.save()
    story = enrich.build_story(row, rec, places) if story_map else []
    return {"record": rec, "classification": result, "derived": row["derived"], "places": places, "story": story,
            "schema_issues": issues, "seconds": round(meta["seconds"] + ameta["seconds"], 1)}


QA_INDEX = qa.Index(RECORDS)


def _llm():
    l = CFG["llm"]
    return Apertus(l["base_url"], l["api_key"], l["model"], 0.0, 1500, l["retries"])


@app.get("/api/ask", summary="Ask the archive: cited answer from the dataset (BM25 + Apertus); refuses when nothing relevant is found")
def ask(q: str = Query(..., min_length=3), k: int = 6):
    return qa.ask(QA_INDEX, _llm(), q, k)


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


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(SITE / "index.html")


app.mount("/", StaticFiles(directory=SITE), name="site")
