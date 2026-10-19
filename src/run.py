"""CORA pipeline: sample -> fetch -> classify -> audit -> compare -> enrich -> qc -> export -> serve.

    python run.py all            # everything
    python run.py classify       # one stage (reads the previous stage's output from data/)
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cora import classify, config, lindas  # noqa: E402
from cora import store  # noqa: E402
from cora.apertus import Apertus  # noqa: E402


FORCE = False  # set by --force: redo records that were already processed


STORED = {"records_raw.json"}  # collections kept one file per entry (cora/store.py)


def _read(path: Path):
    if path.name in STORED:
        return store.read_entries(path)
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
    if path.name in STORED:
        store.write_entries(path, data)
        print(f"  wrote {store.entry_dir(path).relative_to(config.ROOT)}/ ({len(data)} entries)")
        return
    if path.suffix == ".jsonl":
        path.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in data), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  wrote {path.relative_to(config.ROOT)}")


def stage_sample(cfg):
    s = cfg["sample"]
    picked, stats = lindas.sample_ids(s["size"], s["seed"], s["strategy"], s["strata"])
    _write(cfg["paths"]["data_dir"] / "sample.json", {"seed": s["seed"], "strategy": s["strategy"],
                                                      "population": stats, "sample": picked})


def stage_fetch(cfg):
    sample = _read(cfg["paths"]["data_dir"] / "sample.json")["sample"]
    stratum = {p["id"]: p["stratum"] for p in sample}
    recs = lindas.fetch_records([p["id"] for p in sample])
    for r in recs:
        r["stratum"] = stratum[r["id"]]
    _write(cfg["paths"]["data_dir"] / "records_raw.json", recs)


def _client(cfg, feature: str):
    l = cfg["llm"]
    return Apertus(l["base_url"], l["api_key"], config.model_for(cfg, feature), l["temperature"], l["max_tokens"], l["retries"])


def _classify_all(cfg, model: str, out_name: str):
    recs = _read(cfg["paths"]["data_dir"] / "records_raw.json")
    out_path = cfg["paths"]["data_dir"] / out_name
    done = {r["id"]: r for r in _read(out_path)} if out_path.exists() and not FORCE else {}
    todo = [r for r in recs if r["id"] not in done or not done[r["id"]].get("apertus")]
    print(f"  {len(done)} already classified, {len(todo)} to do")
    ap = _client(cfg, "classify")

    def one(rec):
        msgs = classify.build_messages(rec, cfg)
        try:
            raw, meta = ap.chat_json(msgs, model=model)
            result, issues = classify.normalize(raw, rec, cfg)
            err = None
        except Exception as e:  # keep going; QC reports failures
            raw, meta, result, issues, err = None, {}, None, [], repr(e)
        print(f"  {rec['id']:>9} {model} {meta.get('seconds', 0):5.1f}s issues={len(issues)} {'ERROR ' + err if err else ''}")
        return {"id": rec["id"], "model": model, "apertus": result, "raw": raw, "schema_issues": issues,
                "meta": meta, "error": err, "derived": classify.derived_fields(rec)}

    t0 = time.time()
    with ThreadPoolExecutor(cfg["llm"]["workers"]) as pool:
        new = {r["id"]: r for r in pool.map(one, todo)}
    print(f"  {len(new)} records in {time.time() - t0:.0f}s")
    rows = [new.get(r["id"]) or done[r["id"]] for r in recs if r["id"] in new or r["id"] in done]
    _write(out_path, rows)


def stage_classify(cfg):
    _classify_all(cfg, config.model_for(cfg, "classify"), "classified.jsonl")


def stage_compare(cfg):
    _classify_all(cfg, cfg["llm"]["compare_model"], "classified_compare.jsonl")


def stage_audit(cfg):
    """Pass 2: evidence-based preprocessing / personal-data audit; keeps pass-1 flags as *_v1."""
    path = cfg["paths"]["data_dir"] / "classified.jsonl"
    rows = _read(path)
    recs = {r["id"]: r for r in _read(cfg["paths"]["data_dir"] / "records_raw.json")}
    ap = _client(cfg, "audit")

    def one(row):
        if not row.get("apertus") or (row["apertus"].get("audit_checks") and not FORCE):
            return row  # already audited (incremental); use --force to redo
        try:
            raw, meta = ap.chat_json(classify.build_audit_messages(recs[row["id"]]))
        except Exception as e:
            row["audit_error"] = repr(e)
            return row
        checks, pre, personal = classify.audit_to_flags(raw, recs[row["id"]])
        a = row["apertus"]
        a["audit_raw"] = raw
        a.setdefault("preprocessing_v1", a.get("preprocessing"))
        a.setdefault("personal_data_v1", a.get("personal_data"))
        a["preprocessing"], a["personal_data"], a["audit_checks"] = pre, personal, checks
        row["audit_meta"] = meta
        print(f"  {row['id']:>9} audit {meta['seconds']:5.1f}s flags={sum(v['needed'] for v in pre.values())}")
        return row

    with ThreadPoolExecutor(cfg["llm"]["workers"]) as pool:
        rows = list(pool.map(one, rows))
    _write(path, rows)


def stage_level(cfg):
    """Pass 3: source level from explicit archival definitions; pass-1 level kept as source_level_v1."""
    path = cfg["paths"]["data_dir"] / "classified.jsonl"
    rows = _read(path)
    recs = {r["id"]: r for r in _read(cfg["paths"]["data_dir"] / "records_raw.json")}
    ap = _client(cfg, "level")
    conv = cfg["classify"].get("press_convention", "secondary")

    def one(row):
        a = row.get("apertus")
        if not a or (a.get("source_level_pass3") and not FORCE):
            return row
        try:
            raw, meta = ap.chat_json(classify.build_level_messages(recs[row["id"]]))
        except Exception as e:
            row["level_error"] = repr(e)
            return row
        res = classify.level_from_answers(raw, conv)
        a.setdefault("source_level_v1", a["source_level"])
        a["source_level"], a["source_level_pass3"] = res["level"], res
        a["source_level_rationale"] = f'{res["rule"]}: {res["note"] or ""}'.strip(": ")
        print(f"  {row['id']:>9} level {a['source_level_v1']:>9} -> {res['level']:<9} ({res['rule']})")
        return row

    with ThreadPoolExecutor(cfg["llm"]["workers"]) as pool:
        rows = list(pool.map(one, rows))
    _write(path, rows)


def stage_repair(cfg):
    """Apply the rule-based repairs (ISO dates, control characters, optional keys) to existing output."""
    for name in ("classified.jsonl", "enriched.jsonl"):
        path = cfg["paths"]["data_dir"] / name
        if path.exists():
            _repair_file(path)


def _repair_file(path):
    rows = _read(path)
    n = 0
    for row in rows:
        a = row.get("apertus")
        if not a:
            continue
        rep = classify.repair(a)
        a["repairs"] = sorted(set(a.get("repairs", [])) | set(rep))
        row["schema_issues"] = [i for i in row.get("schema_issues", [])
                                if not (i.startswith("missing:") and i.split(":", 1)[1] in classify.OPTIONAL_KEYS)]
        n += bool(rep)
    print(f"  repaired {n} of {len(rows)} records")
    _write(path, rows)


def stage_enrich(cfg):
    from cora import enrich
    enrich.run(cfg)


def stage_qc(cfg):
    from cora import qc
    qc.run(cfg)


def stage_add_sources(cfg):
    from cora import extra
    extra.run(cfg)


def stage_mixed_sample(cfg):
    from cora import mixed
    mixed.run(cfg)


def stage_referendum(cfg):
    from cora import referendum
    referendum.run(cfg)


def stage_parliament(cfg):
    from cora import parliament
    parliament.run(cfg)


def stage_consultations(cfg):
    from cora import consultations
    consultations.run(cfg)


def stage_narrative(cfg):
    from cora import narrative
    narrative.run(cfg)


def stage_stapfer(cfg):
    from cora import stapfer
    stapfer.run(cfg)


def stage_i18n(cfg):
    """Apertus translates the interface catalog (strings of site/*.js and index.html) into German, French, Italian and
    Romansh; only strings missing from data/i18n/<lang>.json are sent, so a rerun picks up new interface text."""
    from cora import i18n
    l = cfg["llm"]
    site = cfg["paths"]["site_dir"]
    print(f"  catalog: {len(i18n.extract(site))} strings")
    with ThreadPoolExecutor(4) as pool:  # one worker per language
        added = dict(zip(["de", "fr", "it", "rm"], pool.map(lambda lang: i18n.translate_missing(
            cfg["paths"]["data_dir"], site, lang, Apertus(l["base_url"], l["api_key"], l["model"], 0.1, 4000, l["retries"])),
            ["de", "fr", "it", "rm"])))
    print("  added:", added)


def stage_split(cfg):
    """Split every single-file collection under data/ into one JSON file per entry (cora/store.py).
    Pages and stages also split entries lazily when they read them; this does it all at once."""
    from cora import stapfer
    data = cfg["paths"]["data_dir"]
    for p in sorted(data.rglob("records_raw.json")):
        print(f"  {p.relative_to(data)}: {store.Entries(p).split_all()} records")
    for p in sorted(data.rglob("cora_dataset.jsonl")):  # the .jsonl stays as the download
        print(f"  {p.relative_to(data)}: {store.Entries(p).split_all(keep_combined=True)} records")
    for p in sorted(data.rglob("enrich_cache.json")):
        print(f"  {p.relative_to(data)}: {store.EntryDict(p).split_all()} cache entries")
    sd = data / "stapfer"
    if (sd / "cases.json").exists():
        print(f"  stapfer/cases.json: {store.Entries(sd / 'cases.json').split_all()} response sheets")
    for name in ("comparison", "comparison_naive"):
        if (sd / f"{name}.json").exists():
            print(f"  stapfer/{name}.json: {len(stapfer.load_comparison(sd, name)[1])} results")


def stage_outcomes(cfg):
    """Outcome of each consultation: popular vote (Swissvotes) or adopted act (Fedlex), confirmed by Apertus."""
    from cora import outcomes
    outcomes.run(cfg)


def stage_export(cfg):
    from cora import export
    export.run(cfg)


def stage_covers(cfg):
    from cora import covers
    covers.run(cfg)


def stage_serve(cfg):
    import uvicorn
    uvicorn.run("cora.api:app", host="127.0.0.1", port=8000)


STAGES = {"sample": stage_sample, "fetch": stage_fetch, "classify": stage_classify,
          "audit": stage_audit, "repair": stage_repair, "level": stage_level, "compare": stage_compare, "enrich": stage_enrich, "qc": stage_qc, "export": stage_export, "covers": stage_covers}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=[*STAGES, "all", "serve", "stapfer", "narrative", "consultations", "parliament", "referendum", "add_sources", "split", "i18n", "mixed_sample", "outcomes"])
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--force", action="store_true", help="reprocess records that were already classified/audited")
    args = ap.parse_args()
    cfg = config.load(args.config)
    FORCE = args.force
    if args.stage == "add_sources":
        stage_add_sources(cfg)
        sys.exit()
    if args.stage == "mixed_sample":
        stage_mixed_sample(cfg)
        sys.exit()
    if args.stage == "referendum":
        stage_referendum(cfg)
        sys.exit()
    if args.stage == "parliament":
        stage_parliament(cfg)
        sys.exit()
    if args.stage == "consultations":
        stage_consultations(cfg)
        sys.exit()
    if args.stage == "outcomes":
        stage_outcomes(cfg)
        sys.exit()
    if args.stage == "narrative":
        stage_narrative(cfg)
        sys.exit()
    if args.stage == "i18n":
        stage_i18n(cfg)
        sys.exit()
    if args.stage == "split":
        stage_split(cfg)
        sys.exit()
    if args.stage == "stapfer":
        stage_stapfer(cfg)
        sys.exit()
    if args.stage == "serve":
        stage_serve(cfg)
        sys.exit()
    for name in (STAGES if args.stage == "all" else [args.stage]):
        print(f"[{name}]")
        STAGES[name](cfg)
