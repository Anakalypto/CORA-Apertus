"""Export the AI-ready dataset (JSONL / CSV / TSV), its JSON Schema and the edit log.

Conflict policy (documented in the edit log):
  - date_archived      : the accession-number rule wins over Apertus (Apertus got it right 24% of the time)
  - coordinates        : the gazetteer wins over Apertus (Apertus' coordinates are kept for QC only)
  - everything else    : Apertus' value, with the original record value preserved alongside
"""
import json
import re
from datetime import datetime, timezone

import pandas as pd

PIPELINE_VERSION = "cora-0.1.0"
PROMPT_VERSION = {"classify": "v2", "audit": "v3"}  # v2/v3: role labels parsed by rule, archival conventions (quality report §8)


def _iso_from_expressed(expr: str | None) -> str | None:
    """'1914.01.01-1918.12.31' -> '1914-01-01/1918-12-31'."""
    if not expr:
        return None
    parts = [p.strip().replace(".", "-") for p in expr.split("-") if p.strip()] if re.fullmatch(
        r"[\d.]+(\s*-\s*[\d.]+)?", expr.strip()) else None
    return "/".join(parts) if parts else None


def build_record(row: dict, rec: dict, qc: dict, now: str) -> tuple[dict, list[dict]]:
    a, d, e = row["apertus"], row["derived"], row.get("enriched", {})
    edits = []

    def log(field, before, after, actor, reason):
        if before != after:
            edits.append({"record_id": row["id"], "field": field, "original": before, "new": after,
                          "actor": actor, "reason": reason, "timestamp": now})

    log("title", rec["title"], a.get("title_normalized"), "apertus", "encoding/casing/abbreviation normalisation")
    log("date", rec["date"]["expressed"], _iso_from_expressed(rec["date"]["expressed"]), "rule", "ISO 8601 date normalisation")
    log("date_archived", a.get("date_archived"), d["date_archived"], "rule",
        "accession year taken from the accession number (overrides Apertus)")
    for p in e.get("places", []):
        if p.get("geo"):
            log(f"place:{p['name']}:coordinates", [p.get("lat"), p.get("lon")], [p["geo"]["lat"], p["geo"]["lon"]],
                "gazetteer", "coordinates from OpenStreetMap Nominatim (override Apertus)")
    for p in e.get("persons", []):
        log(f"person:{p['name']}:display_name", p["name"], p.get("display_name"), "rule", "authority form 'Last, First' -> natural order")

    out = {
        "id": row["id"],
        "source": {
            "uri": rec["uri"], "portal_url": rec["portal_url"], "reference_code": rec["reference_code"],
            "dataset": "Archive database of the Swiss Federal Archives (opendata.swiss)",
            "original": {k: rec[k] for k in ("title", "reference_number", "old_reference_code", "alternate_reference",
                                             "scope_and_content", "author", "publisher", "involved", "coverage",
                                             "form", "format", "thema", "country", "date", "accessions") if rec.get(k)},
        },
        "classification": {
            "document_type": a["document_type"], "medium": a["medium"],
            "source_level": a["source_level"], "source_level_rationale": a.get("source_level_rationale"),
            "resume": a.get("resume"),
        },
        "metadata": {
            "title": rec["title"], "title_normalized": a.get("title_normalized"), "title_en": a.get("title_en"),
            "creator": a.get("creator"), "publisher": a.get("publisher"), "commissioner": a.get("commissioner"),
            "date_created": a.get("date_created"), "date_published": a.get("date_published"),
            "date_updated": a.get("date_updated"), "date_archived": d["date_archived"],
            "content_date": _iso_from_expressed(rec["date"]["expressed"]) or rec["date"].get("from"),
            "languages": a.get("languages", []), "subjects": a.get("subjects", []),
        },
        "archival_location": d["archival_location"] | {"accession_numbers": d["accession_numbers"]},
        "entities": {
            "persons": [{k: p.get(k) for k in ("name", "display_name", "role", "wikidata")} for p in e.get("persons", [])],
            "organizations": [{k: o.get(k) for k in ("name", "role", "wikidata")} for o in e.get("organizations", [])],
            "places": [{"name": p["name"], "as_written": p.get("as_written"), "role": p["role"], "country": p.get("country"),
                        "lat": p["geo"]["lat"] if p.get("geo") else None, "lon": p["geo"]["lon"] if p.get("geo") else None,
                        "gazetteer": p["geo"]["osm"] if p.get("geo") else None,
                        "model_lat": p.get("lat"), "model_lon": p.get("lon")} for p in e.get("places", [])],
        },
        "preprocessing": a.get("preprocessing"),
        "audit_checks": a.get("audit_checks"),
        "personal_data": a.get("personal_data"),
        "story": e.get("story", []),
        "provenance": {
            "source.*": "record", "archival_location": "derived", "metadata.date_archived": "derived",
            "metadata.content_date": "derived", "metadata.title": "record",
            "classification.*": "apertus", "metadata.*": "apertus", "entities.*.name/role": "apertus",
            "entities.places.lat/lon": "gazetteer", "entities.*.wikidata": "wikidata",
            "preprocessing": "apertus (audit checks) + rule", "story": "apertus + derived",
        },
        "qc": {k: qc.get(k) for k in ("ok", "structural_errors", "critical", "warnings", "ungrounded")},
        "processing": {"pipeline": PIPELINE_VERSION, "prompts": PROMPT_VERSION, "model": row.get("model"),
                       "audit_model": row.get("audit_meta", {}).get("model"), "confidence": a.get("confidence"),
                       "tokens": sum(u.get("total_tokens", 0) for u in row.get("meta", {}).get("usage", []))
                                 + sum(u.get("total_tokens", 0) for u in row.get("audit_meta", {}).get("usage", [])),
                       "processed_at": now},
        "stratum": rec.get("stratum"),
    }
    return out, edits


def flatten(r: dict) -> dict:
    join = lambda xs: "; ".join(x for x in xs if x)
    m, c, loc = r["metadata"], r["classification"], r["archival_location"]
    return {
        "id": r["id"], "reference_code": r["source"]["reference_code"], "uri": r["source"]["uri"],
        "portal_url": r["source"]["portal_url"], "title": m["title"], "title_normalized": m["title_normalized"],
        "title_en": m["title_en"], "document_type": c["document_type"], "medium": c["medium"],
        "source_level": c["source_level"], "resume": c["resume"], "creator": m["creator"], "publisher": m["publisher"],
        "commissioner": m["commissioner"], "date_created": m["date_created"], "date_published": m["date_published"],
        "date_updated": m["date_updated"], "date_archived": m["date_archived"], "content_date": m["content_date"],
        "languages": join(m["languages"]), "subjects": join(m["subjects"]),
        "persons": join(p.get("display_name") or p["name"] for p in r["entities"]["persons"]),
        "persons_wikidata": join((p.get("wikidata") or {}).get("qid") for p in r["entities"]["persons"]),
        "organizations": join(o["name"] for o in r["entities"]["organizations"]),
        "places": join(p["name"] for p in r["entities"]["places"]),
        "fonds": loc["fonds"], "archive_path": " > ".join(loc["path"]),
        **{f"pre_{k}": v["needed"] for k, v in (r["preprocessing"] or {}).items()},
        "personal_data": (r["personal_data"] or {}).get("contains_personal_data"),
        "sensitivity": (r["personal_data"] or {}).get("sensitivity"),
        "qc_ok": r["qc"]["ok"], "qc_warnings": join(r["qc"]["warnings"] or []),
        "stratum": r["stratum"],
    }


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/Anakalypto/CORA-Apertus/data/dataset/schema.json",
    "title": "CORA AI-ready archival record",
    "type": "object",
    "required": ["id", "source", "classification", "metadata", "archival_location", "entities", "provenance", "processing"],
    "properties": {
        "id": {"type": "string", "description": "VRZNG_ENHT_ID of the unit of description"},
        "source": {"type": "object", "description": "Original record, untouched (reference code, URIs, original fields)"},
        "classification": {"type": "object", "properties": {
            "document_type": {"type": "string"}, "medium": {"type": "string"},
            "source_level": {"enum": ["primary", "secondary", "tertiary"]},
            "source_level_rationale": {"type": ["string", "null"]},
            "resume": {"type": ["string", "null"], "description": "At most 3 sentences; null when disabled"}}},
        "metadata": {"type": "object", "description": "Dublin-Core-like descriptive metadata (Gallica-style)", "properties": {
            k: {"type": ["string", "null"]} for k in ("title", "title_normalized", "title_en", "creator", "publisher",
                                                      "commissioner", "date_created", "date_published", "date_updated",
                                                      "date_archived", "content_date")}},
        "archival_location": {"type": "object", "description": "Holder, fonds, path in the archive plan, reference code"},
        "entities": {"type": "object", "properties": {
            "persons": {"type": "array"}, "organizations": {"type": "array"}, "places": {"type": "array"}}},
        "preprocessing": {"type": "object", "description": "Six preprocessing needs, each {needed, priority, reason, based_on}"},
        "personal_data": {"type": "object"},
        "story": {"type": "array", "description": "Chronological provenance trail with coordinates"},
        "provenance": {"type": "object", "description": "Which component produced each field"},
        "qc": {"type": "object"},
        "processing": {"type": "object"},
    },
}


def run(cfg):
    data_dir = cfg["paths"]["data_dir"]
    out_dir = data_dir / "dataset"
    out_dir.mkdir(exist_ok=True)
    rows = [json.loads(l) for l in (data_dir / "enriched.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    recs = {r["id"]: r for r in json.loads((data_dir / "records_raw.json").read_text(encoding="utf-8"))}
    qc_path = data_dir / "qc_report.json"
    qc = {c["id"]: c for c in json.loads(qc_path.read_text(encoding="utf-8"))["records"]} if qc_path.exists() else {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records, edits = [], []
    for row in rows:
        if not row.get("apertus"):
            continue
        r, e = build_record(row, recs[row["id"]], qc.get(row["id"], {}), now)
        records.append(r)
        edits += e
    (out_dir / "cora_dataset.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    df = pd.DataFrame([flatten(r) for r in records])
    df.to_csv(out_dir / "cora_dataset.csv", index=False, encoding="utf-8")
    df.to_csv(out_dir / "cora_dataset.tsv", index=False, sep="\t", encoding="utf-8")
    pd.DataFrame(edits).to_json(out_dir / "edit_log.jsonl", orient="records", lines=True, force_ascii=False)
    (out_dir / "schema.json").write_text(json.dumps(SCHEMA, indent=1), encoding="utf-8")
    print(f"  {len(records)} records, {len(df.columns)} flat columns, {len(edits)} logged edits -> data/dataset/")
