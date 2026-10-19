"""Side-by-side test of Apertus 70B and 8B on the same records (classification / parsing pass only).

    python src/run.py sample   --config src/config_eval200.toml   # pick 200 new records
    python src/run.py fetch    --config src/config_eval200.toml   # download them (no API key needed)
    python src/run.py classify --config src/config_eval200.toml   # 70B  -> classified.jsonl
    python src/run.py compare  --config src/config_eval200.toml   # 8B   -> classified_compare.jsonl
    python src/eval_models.py  --config src/config_eval200.toml   # score both -> model_comparison.json

Each model is scored on its own with the automatic checks of cora/qc.py (no ground truth needed),
then the two are compared field by field. Agreement is not accuracy: it says how often 8B gives
the same answer as 70B, which is the target if 8B is fine-tuned to imitate 70B.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cora import config, qc  # noqa: E402
from cora import store  # noqa: E402


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _pct(k: int, n: int) -> float | None:
    return round(100 * k / n, 1) if n else None


def score_model(rows: list[dict], recs: dict) -> dict:
    """Automatic checks on one model's output."""
    checks = [qc.check_record(r, recs[r["id"]]) for r in rows if r["id"] in recs]
    n = len(checks)
    valid = [c for c in checks if "no_output" not in c["structural_errors"]]
    ents = sum(c.get("n_entities", 0) for c in valid)
    ungr = sum(len(c.get("ungrounded_strict", [])) for c in valid)
    in_range = [c["created_in_range"] for c in valid if c.get("created_in_range") is not None]
    agree = {f: [c["agreement"][f] for c in valid if f in c.get("agreement", {})] for f in ("creator", "publisher")}
    secs = [r["meta"]["seconds"] for r in rows if r.get("meta", {}).get("seconds")]
    return {
        "records": n,
        "valid_json_pct": _pct(len(valid), n),
        "processed_ok_pct": _pct(sum(c["ok"] for c in checks), n),
        "date_created_in_range_pct": _pct(sum(in_range), len(in_range)),
        "creator_matches_record_pct": _pct(sum(agree["creator"]), len(agree["creator"])),
        "publisher_matches_record_pct": _pct(sum(agree["publisher"]), len(agree["publisher"])),
        "entities_found_in_source_pct": _pct(ents - ungr, ents),
        "resume_speculative_pct": _pct(sum("resume_speculative" in c.get("warnings", []) for c in valid), len(valid)),
        "mean_seconds_per_record": round(statistics.mean(secs), 1) if secs else None,
        "errors": [c["id"] for c in checks if not c["ok"]],
    }


def _names(items: list[dict]) -> set[str]:
    return {qc._fold(i["name"]) for i in items or [] if i.get("name")}


def _f1(a: set, b: set) -> float | None:
    if not a and not b:
        return None  # both empty: nothing to compare
    tp = len(a & b)
    return 2 * tp / (len(a) + len(b))


def head_to_head(big: dict, small: dict) -> dict:
    """How often the small model gives the same answer as the big one, per field."""
    ids = [i for i in big if big[i].get("apertus") and small.get(i, {}).get("apertus")]
    res = {"records_both_valid": len(ids)}
    for f in ("document_type", "medium", "source_level"):
        pairs = [(big[i]["apertus"][f], small[i]["apertus"][f]) for i in ids]
        res[f] = {"agreement_pct": _pct(sum(a == b for a, b in pairs), len(pairs)), "kappa": qc._kappa(pairs)}
    for f in ("date_created", "date_published"):
        res[f] = {"agreement_pct": _pct(sum((big[i]["apertus"].get(f) or None) == (small[i]["apertus"].get(f) or None)
                                            for i in ids), len(ids))}
    for f in ("creator", "publisher"):
        res[f] = {"agreement_pct": _pct(sum(qc._fold(big[i]["apertus"].get(f) or "") == qc._fold(small[i]["apertus"].get(f) or "")
                                            for i in ids), len(ids))}
    for f in ("persons", "organizations", "places"):
        scores = [s for i in ids if (s := _f1(_names(big[i]["apertus"][f]), _names(small[i]["apertus"][f]))) is not None]
        res[f] = {"name_overlap_f1_pct": round(100 * statistics.mean(scores), 1) if scores else None, "records": len(scores)}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None)
    args = ap.parse_args()
    cfg = config.load(args.config)
    d = cfg["paths"]["data_dir"]
    recs = {r["id"]: r for r in store.read_entries(d / "records_raw.json")}
    big_rows, small_rows = _read_jsonl(d / "classified.jsonl"), _read_jsonl(d / "classified_compare.jsonl")
    if not big_rows or not small_rows:
        raise SystemExit("run the classify and compare stages first (see the docstring)")
    big_name, small_name = cfg["llm"]["model"], cfg["llm"]["compare_model"]
    report = {
        "records": len(recs),
        big_name: score_model(big_rows, recs),
        small_name: score_model(small_rows, recs),
        f"{small_name}_vs_{big_name}": head_to_head({r["id"]: r for r in big_rows}, {r["id"]: r for r in small_rows}),
    }
    out = d / "model_comparison.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'automatic check':<34}{big_name:>18}{small_name:>18}")
    for k in report[big_name]:
        if k != "errors":
            print(f"{k:<34}{str(report[big_name][k]):>18}{str(report[small_name][k]):>18}")
    print(f"\n{small_name} gives the same answer as {big_name}:")
    for f, v in report[f"{small_name}_vs_{big_name}"].items():
        print(f"  {f:<32}{v}")
    print(f"\n  wrote {out.relative_to(config.ROOT)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
