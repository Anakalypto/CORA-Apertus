"""Quality check of what Apertus produced.

Automatic checks (per record, then aggregated):
  structure   – valid JSON, schema/enums respected, ISO dates, résumé <= 3 sentences
  grounding   – every person/organisation/place named by Apertus appears in the source metadata
  dates       – date_created inside the record's date range; date_archived == accession year
  agreement   – creator/publisher vs the record's author/publisher fields
  geo         – gazetteer resolution rate; distance between Apertus' and the gazetteer's coordinates
  consistency – agreement between Apertus 70B and Apertus 8B on the categorical fields
  flags       – preprocessing flags vs observable evidence in the record
Plus the verdicts of a manual review (data/manual_review.json) when present.
"""
import json
import re
import statistics
import unicodedata
from collections import Counter

from . import store

ISO = re.compile(r"^(\d{4}(-\d{2}(-\d{2})?)?(/(\d{4}(-\d{2}(-\d{2})?)?|\.\.))?|\.\./\d{4}(-\d{2}(-\d{2})?)?)$")  # date, interval, or open interval "X/.."
SPECULATION = re.compile(r"\b(likely|possibly|probably|presumably|may contain|might|perhaps|apparently)\b", re.I)


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _source_text(rec: dict) -> str:
    parts = [str(v) for k, v in rec.items() if isinstance(v, str) and k not in ("uri", "portal_url")]
    parts += [h["title"] or "" for h in rec.get("hierarchy", [])]
    parts += [a.get("title") or "" for a in rec.get("accessions", [])]
    return _fold(" ".join(parts))


# Apertus writes English names; the records are in German/French/Italian. A translation-aware
# check maps the common institutional names and accepts shared word stems (Kantonspolizist ->
# Kantonspolizei). Both the strict and the translation-aware grounding rates are reported.
ALIASES = {
    "nationalrat": "national council conseil national", "standerat": "council of states conseil des etats",
    "bundesversammlung": "federal assembly parliament", "parlament": "parliament parliamentary",
    "armee": "army swiss army military", "armeestab": "army staff swiss army", "landesverteidigung": "national defence army",
    "schweiz": "switzerland swiss suisse", "ch ": "switzerland swiss", "deutschland": "germany german",
    "frankreich": "france", "italien": "italy", "osterreich": "austria", "griechenland": "greece",
    "bundesrat": "federal council", "bundesamt": "federal office", "democra": "dimokratia",
    "srg": "swiss broadcasting corporation", "fernsehen": "television tv", "sf drs": "swiss television",
}


def _with_aliases(src: str) -> str:
    return src + " " + " ".join(v for k, v in ALIASES.items() if k in src)


def grounded(name: str, src: str, alt: str | None = None, lenient: bool = False) -> bool:
    if lenient:
        src = _with_aliases(src)
        name = re.sub(r"[()]", " ", name or "")
    for cand in filter(None, (name, alt)):
        f = _fold(cand)
        if not f:
            continue
        if f in src:
            return True
        toks = [t for t in f.split() if len(t) > 3]
        hit = (lambda t: t in src or (len(t) >= 6 and t[:max(5, len(t) - 3)] in src)) if lenient else (lambda t: t in src)
        if toks and sum(map(hit, toks)) / len(toks) >= 0.5:
            return True
    return False


def sentences(text: str) -> int:
    t = re.sub(r"\b(?:[A-Z]|No|Nr|Pkt|St|Dr|Prof|med|phil|jur|lic|Dipl|Ing|Hr|Fr|Mme|Mgr|ca|approx|e\.g|i\.e|vs|Mr|Mrs|Jr|Sr|etc)\.", "X", text or "")
    t = re.sub(r"\d\.\d", "0", t)
    t = re.sub(r"(^|[\s'\"(])\d{1,3}\.(?=\s)", r"\1N", t)  # ordinals such as "22. Chemische …"
    return len([s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", t.strip()) if s.strip()])


def _year(s) -> int | None:
    m = re.match(r"\s*(\d{4})", str(s or ""))
    return int(m.group(1)) if m else None


def _years(s) -> tuple[int | None, int | None]:
    ys = [int(y) for y in re.findall(r"\d{4}", str(s or ""))]
    return (min(ys), max(ys)) if ys else (None, None)


def expected_source_level(doc_type: str, rec: dict) -> str | None:
    t = (rec.get("title") or "").lower() + " " + " ".join(h["title"].lower() for h in rec.get("hierarchy", [])[:2])
    if re.search(r"\b(register|verzeichnis|index|repertori|inventar|findmittel)", t):
        return "tertiary"
    if doc_type in ("TV news report", "newsreel", "photograph", "minutes / protocol", "parliamentary record",
                    "correspondence", "administrative file", "radio broadcast", "audio recording"):
        return "primary"
    return None


def check_record(row: dict, rec: dict) -> dict:
    a, d = row.get("apertus"), row["derived"]
    if not a:
        return {"id": row["id"], "structural_errors": ["no_output"], "critical": ["no_output"], "ok": False}
    src = _source_text(rec)
    structural, critical, warnings = [], [], []

    optional = {"date_updated", "date_published", "commissioner", "creator", "publisher"}
    structural += [i for i in row.get("schema_issues", []) if not i.startswith("missing:preprocessing")
                   and not (i.startswith("missing:") and i.split(":", 1)[1] in optional)]
    if a.get("repairs"):
        warnings.append("repaired:" + ",".join(sorted({r.split(":")[0] for r in a["repairs"]})))
    for f in ("date_created", "date_published", "date_updated", "date_archived"):
        if a.get(f) and not ISO.match(str(a[f]).strip()):
            structural.append(f"non_iso:{f}")
    n_sent = sentences(a.get("resume") or "")
    if "resume" in a:
        if not a.get("resume"):
            structural.append("resume_empty")
        elif n_sent > 3:
            structural.append(f"resume_{n_sent}_sentences")
        if SPECULATION.search(a.get("resume") or ""):
            warnings.append("resume_speculative")

    # Grounding of named entities
    ent = [("person", p["name"], None) for p in a["persons"]] + \
          [("organization", o["name"], None) for o in a["organizations"]] + \
          [("place", p["name"], p.get("as_written")) for p in a["places"]]
    ungrounded_strict = [f"{k}:{n}" for k, n, alt in ent if not grounded(n, src, alt)]
    ungrounded = [f"{k}:{n}" for k, n, alt in ent if not grounded(n, src, alt, lenient=True)]
    if ungrounded:
        warnings.append("ungrounded_entities")

    # Dates
    rf, rt = _year(rec["date"].get("from")), _year(rec["date"].get("to")) or _year(rec["date"].get("from"))
    cf, ct = _years(a.get("date_created"))
    created_in_range = None
    if rf and cf:
        created_in_range = (rf - 1) <= cf and (ct or cf) <= (rt + 1)
        if not created_in_range:
            # A finding aid is usually written after the records it lists; that is not an error
            # when the record's own description states the later date ("Bern, den 11. Februar 1977").
            later_aid = a["source_level"] == "tertiary" and cf > rt and str(cf) in (rec.get("scope_and_content") or "")
            (warnings if later_aid else critical).append("date_created_outside_record_range")
    archived_ok = (_year(a.get("date_archived")) == _year(d["date_archived"]))
    if not archived_ok:
        warnings.append("date_archived_mismatch")
    if cf and _year(d["date_archived"]) and cf > _year(d["date_archived"]):
        critical.append("created_after_archived")

    # Creator / publisher agreement with explicit record fields
    agree = {}
    for field, recfield in (("creator", "author"), ("publisher", "publisher")):
        if rec.get(recfield):
            val = re.sub(r"^[^:]{1,25}:\s*", "", rec[recfield])  # strip "HerausgeberIn:" style labels
            agree[field] = bool(a.get(field)) and (grounded(a[field], _fold(val)) or grounded(val, _fold(a[field])))

    geo_conflicts = [f'{p["name"]} ({p["model_error_km"]} km)' for p in row.get("enriched", {}).get("places", [])
                     if (p.get("model_error_km") or 0) > 50]
    if geo_conflicts:
        warnings.append("geo_conflict_over_50km")

    exp = expected_source_level(a["document_type"], rec)
    if exp and exp != a["source_level"]:
        warnings.append(f"source_level_{a['source_level']}_expected_{exp}")

    # Preprocessing flags vs evidence
    evidence = {
        "transcription_normalization": "�" in json.dumps(rec, ensure_ascii=False)
        or bool(re.search(r"[A-ZÄÖÜÉÈ]{4,}\s*[/;,]", rec.get("title") or "")),
        "anonymization_verification": bool(a["persons"]) and (_year(rec["date"].get("to") or rec["date"].get("from")) or 0) > 1945,
    }
    flags = {k: v["needed"] for k, v in (a.get("preprocessing") or {}).items()}

    geo = [p for p in row.get("enriched", {}).get("places", [])]
    return {
        "id": row["id"], "stratum": rec["stratum"], "document_type": a["document_type"],
        "evidence_source_level": rec.get("expected_source_level"), "pre_1940": rec.get("pre_1940"),
        "source_level_v1": a.get("source_level_v1"),
        "source_level": a["source_level"], "structural_errors": structural, "critical": critical,
        "warnings": warnings, "geo_conflicts": geo_conflicts, "ungrounded": ungrounded, "ungrounded_strict": ungrounded_strict, "n_entities": len(ent),
        "resume_sentences": n_sent, "created_in_range": created_in_range, "archived_ok": archived_ok,
        "agreement": agree, "expected_source_level": exp, "flags": flags, "evidence": evidence,
        "places_total": len(geo), "places_resolved": sum(1 for p in geo if p.get("geo")),
        "model_error_km": [p["model_error_km"] for p in geo if p.get("model_error_km") is not None],
        "ok": not structural and not critical,
    }


def _kappa(pairs) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def consistency(rows, other_rows) -> dict:
    other = {r["id"]: r for r in other_rows if r.get("apertus")}
    res = {}
    for f in ("document_type", "medium", "source_level"):
        pairs = [(r["apertus"][f], other[r["id"]]["apertus"][f]) for r in rows if r.get("apertus") and r["id"] in other]
        res[f] = {"n": len(pairs), "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None,
                  "kappa": _kappa(pairs)}
    pairs = [(_year(r["apertus"]["date_created"]), _year(other[r["id"]]["apertus"]["date_created"]))
             for r in rows if r.get("apertus") and r["id"] in other]
    res["date_created_year"] = {"n": len(pairs), "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None}
    return res


def run(cfg):
    data_dir = cfg["paths"]["data_dir"]
    load = lambda n: [json.loads(l) for l in (data_dir / n).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = load("enriched.jsonl")
    recs = {r["id"]: r for r in store.read_entries(data_dir / "records_raw.json")}
    checks = [check_record(r, recs[r["id"]]) for r in rows]
    n = len(checks)
    pct = lambda k: round(100 * k / n, 1) if n else 0.0

    ents = sum(c.get("n_entities", 0) for c in checks)
    ungr = sum(len(c.get("ungrounded", [])) for c in checks)
    ungr_strict = sum(len(c.get("ungrounded_strict", [])) for c in checks)
    errs = [e for c in checks for e in c.get("model_error_km", [])]
    places_total = sum(c.get("places_total", 0) for c in checks)
    agree = Counter()
    for c in checks:
        for k, v in c.get("agreement", {}).items():
            agree[k + "_n"] += 1
            agree[k + "_ok"] += v
    # Apertus' answers on mechanical checks vs the deterministic detectors (classify.rule_checks).
    flag_eval = {}
    for k in ("encoding_damage", "uppercase_or_abbreviated_title", "labelled_subfields", "packed_role_fields", "nonstandard_dates"):
        pairs = [(r["apertus"]["audit_checks"][k]["apertus"], r["apertus"]["audit_checks"][k]["rule"])
                 for r in rows if r.get("apertus") and r["apertus"].get("audit_checks")]
        tp = sum(1 for m, g in pairs if m and g)
        fp = sum(1 for m, g in pairs if m and not g)
        fn = sum(1 for m, g in pairs if not m and g)
        flag_eval[k] = {"rule_positive": tp + fn, "apertus_positive": tp + fp,
                        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                        "precision": round(tp / (tp + fp), 3) if tp + fp else None}
    flag_rates = {k: pct(sum(1 for c in checks if c.get("flags", {}).get(k))) for k in
                  ("transcription_normalization", "structure_extraction", "schema_harmonization",
                   "linked_data_entity_linking", "date_geolocation_parsing", "anonymization_verification")}

    usage = [u for r in rows for u in r.get("meta", {}).get("usage", [])]
    secs = [r.get("meta", {}).get("seconds", 0) for r in rows if r.get("meta")]
    compare_path = data_dir / "classified_compare.jsonl"
    summary = {
        "records": n,
        "model": cfg["llm"]["model"],
        "processed_ok_pct": pct(sum(c["ok"] for c in checks)),
        "structural_error_pct": pct(sum(bool(c["structural_errors"]) for c in checks)),
        "critical_error_pct": pct(sum(bool(c.get("critical")) for c in checks)),
        "structural_error_types": Counter(e.split(":")[0] for c in checks for e in c["structural_errors"]).most_common(),
        "critical_types": Counter(e for c in checks for e in c.get("critical", [])).most_common(),
        "warning_types": Counter(re.sub(r"_expected_.*", "_mismatch", w) for c in checks for w in c.get("warnings", [])).most_common(),
        "resume_max_3_sentences_pct": pct(sum(1 for c in checks if c.get("resume_sentences", 99) <= 3)),
        "entity_grounding_pct": round(100 * (ents - ungr) / ents, 1) if ents else None,
        "entity_grounding_strict_pct": round(100 * (ents - ungr_strict) / ents, 1) if ents else None,
        "entities": ents, "ungrounded_entities": ungr,
        "date_created_in_range_pct": round(100 * sum(c.get("created_in_range") is True for c in checks)
                                           / max(1, sum(c.get("created_in_range") is not None for c in checks)), 1),
        "date_archived_correct_pct": pct(sum(c.get("archived_ok", False) for c in checks)),
        "creator_agreement": f'{agree["creator_ok"]}/{agree["creator_n"]}',
        "publisher_agreement": f'{agree["publisher_ok"]}/{agree["publisher_n"]}',
        "source_level_rule_agreement": f'{sum(1 for c in checks if c.get("expected_source_level") and c["expected_source_level"] == c["source_level"])}'
                                       f'/{sum(1 for c in checks if c.get("expected_source_level"))}',
        "places": places_total,
        "places_resolved_pct": round(100 * sum(c.get("places_resolved", 0) for c in checks) / places_total, 1) if places_total else None,
        "model_coords_given": len(errs),
        "model_coord_error_km_median": round(statistics.median(errs), 1) if errs else None,
        "model_coord_within_25km_pct": round(100 * sum(e <= 25 for e in errs) / len(errs), 1) if errs else None,
        "preprocessing_flag_rates_pct": flag_rates,
        "preprocessing_v1_rates_pct": {k: pct(sum(1 for r in rows if r.get("apertus") and
                                                  (r["apertus"].get("preprocessing_v1") or {}).get(k, {}).get("needed")))
                                       for k in flag_rates},
        "preprocessing_flag_vs_evidence": flag_eval,
        "personal_data": {"names_persons_pct": pct(sum(1 for r in rows if r.get("apertus") and r["apertus"]["personal_data"].get("contains_personal_data"))),
                          "private_individuals_pct": pct(sum(1 for r in rows if r.get("apertus") and r["apertus"]["personal_data"].get("private_individuals"))),
                          "sensitive_pct": pct(sum(1 for r in rows if r.get("apertus") and r["apertus"]["personal_data"].get("sensitive_categories"))),
                          "v1_flagged_pct": pct(sum(1 for r in rows if r.get("apertus") and (r["apertus"].get("preprocessing_v1") or {}).get("anonymization_verification", {}).get("needed")))},
        "distribution": {
            "document_type": Counter(c.get("document_type") for c in checks).most_common(),
            "source_level": Counter(c.get("source_level") for c in checks).most_common(),
        },
        "cost": {"prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
                 "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
                 "mean_seconds_per_record": round(statistics.mean(secs), 1) if secs else None,
                 "retries": sum(max(0, r.get("meta", {}).get("attempts", 1) - 1) for r in rows)},
        "consistency_70b_vs_8b": consistency(rows, load("classified_compare.jsonl")) if compare_path.exists() else None,
    }
    def review_summary(path):
        items = json.loads(path.read_text(encoding="utf-8"))["items"]
        return {
            "reviewed": len(items),
            "verdicts": Counter(i["verdict"] for i in items).most_common(),
            "field_accuracy": {f: round(100 * sum(1 for i in items if i["fields"].get(f) == "ok")
                                        / max(1, sum(1 for i in items if i["fields"].get(f) in ("ok", "error"))), 1)
                               for f in sorted({f for i in items for f in i["fields"]})},
            "error_types": Counter(e for i in items for e in i.get("errors", [])).most_common(),
        }

    # manual_review.json reviews prompt v1; manual_review_v2.json the same 25 records after the §8 fixes.
    # Source level vs the label set from archival evidence (only the 200 added secondary/tertiary sources have one)
    lab = [c for c in checks if c.get("evidence_source_level")]
    if lab:
        conf = Counter((c["evidence_source_level"], c["source_level"]) for c in lab)
        summary["source_level_vs_evidence"] = {
            "n": len(lab), "agreement_pct": round(100 * sum(c["evidence_source_level"] == c["source_level"] for c in lab) / len(lab), 1),
            "confusion": {f"{e}->{p}": n for (e, p), n in sorted(conf.items())},
            "by_stratum": {st: {"n": len(g), "agreement_pct": round(100 * sum(c["evidence_source_level"] == c["source_level"] for c in g) / len(g), 1),
                                "predicted": dict(Counter(c["source_level"] for c in g))}
                           for st in sorted({c["stratum"] for c in lab}) for g in [[c for c in lab if c["stratum"] == st]]},
        }
    if lab and any(c.get("source_level_v1") for c in lab):
        summary["source_level_vs_evidence"]["pass1_agreement_pct"] = round(
            100 * sum(c["evidence_source_level"] == (c.get("source_level_v1") or c["source_level"]) for c in lab) / len(lab), 1)
    prim = [c for c in checks if not c.get("evidence_source_level") and c.get("source_level")]
    if prim:
        summary["source_level_original_sample"] = dict(Counter(c["source_level"] for c in prim))
    adj = data_dir / "source_level_adjudication.json"
    if adj.exists():
        summary["source_level_adjudication"] = json.loads(adj.read_text(encoding="utf-8"))["summary"]
    v1, v2 = data_dir / "manual_review.json", data_dir / "manual_review_v2.json"
    if v2.exists():
        summary["manual_review"] = review_summary(v2)
        summary["manual_review"]["prompt_version"] = "v2"
        if v1.exists():
            summary["manual_review_v1"] = review_summary(v1)
    elif v1.exists():
        summary["manual_review"] = review_summary(v1)
    old = data_dir / "qc_report_v1.json"
    if old.exists():
        o = json.loads(old.read_text(encoding="utf-8"))["summary"]
        keys = ("processed_ok_pct", "structural_error_pct", "entity_grounding_strict_pct", "entity_grounding_pct",
                "entities", "creator_agreement", "publisher_agreement")
        summary["automatic_v1"] = {k: o.get(k) for k in keys}
        summary["automatic_v1"]["sensitive_pct"] = o.get("personal_data", {}).get("sensitive_pct")
        summary["automatic_v1"]["anonymization_flag_pct"] = o.get("preprocessing_flag_rates_pct", {}).get("anonymization_verification")
        summary["automatic_v1"]["resume_speculative"] = dict(o.get("warning_types", [])).get("resume_speculative", 0)
    (data_dir / "qc_report.json").write_text(json.dumps({"summary": summary, "records": checks},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("  wrote data/qc_report.json")
