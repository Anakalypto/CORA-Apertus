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
from cora.apertus import Apertus  # noqa: E402


def _read(path: Path):
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
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


def _client(cfg):
    l = cfg["llm"]
    return Apertus(l["base_url"], l["api_key"], l["model"], l["temperature"], l["max_tokens"], l["retries"])


def _classify_all(cfg, model: str, out_name: str):
    recs = _read(cfg["paths"]["data_dir"] / "records_raw.json")
    ap = _client(cfg)

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
        rows = list(pool.map(one, recs))
    print(f"  {len(rows)} records in {time.time() - t0:.0f}s")
    _write(cfg["paths"]["data_dir"] / out_name, rows)


def stage_classify(cfg):
    _classify_all(cfg, cfg["llm"]["model"], "classified.jsonl")


def stage_compare(cfg):
    _classify_all(cfg, cfg["llm"]["compare_model"], "classified_compare.jsonl")


def stage_audit(cfg):
    """Pass 2: evidence-based preprocessing / personal-data audit; keeps pass-1 flags as *_v1."""
    path = cfg["paths"]["data_dir"] / "classified.jsonl"
    rows = _read(path)
    recs = {r["id"]: r for r in _read(cfg["paths"]["data_dir"] / "records_raw.json")}
    ap = _client(cfg)

    def one(row):
        if not row.get("apertus"):
            return row
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


def stage_enrich(cfg):
    from cora import enrich
    enrich.run(cfg)


def stage_qc(cfg):
    from cora import qc
    qc.run(cfg)


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


def stage_export(cfg):
    from cora import export
    export.run(cfg)


def stage_serve(cfg):
    import uvicorn
    uvicorn.run("cora.api:app", host="127.0.0.1", port=8000)


STAGES = {"sample": stage_sample, "fetch": stage_fetch, "classify": stage_classify,
          "audit": stage_audit, "compare": stage_compare, "enrich": stage_enrich, "qc": stage_qc, "export": stage_export}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=[*STAGES, "all", "serve", "stapfer", "narrative", "consultations", "parliament"])
    ap.add_argument("--config", type=Path, default=None)
    args = ap.parse_args()
    cfg = config.load(args.config)
    if args.stage == "parliament":
        stage_parliament(cfg)
        sys.exit()
    if args.stage == "consultations":
        stage_consultations(cfg)
        sys.exit()
    if args.stage == "narrative":
        stage_narrative(cfg)
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
