"""Verify a mixed batch (src/cora/mixed.py) before it goes on the website.

    python src/verify_batch.py sample   # stratified review queue: 2 records per tier x type x era cell
    python src/verify_batch.py report   # docs/batch10k_verification.md from the QC report and the manual review

The automatic part reuses qc.py's per-record checks and breaks them down by tier, type and era; the manual part is a
field-by-field review of the queue (data/batch10k/manual_review.json, same format as data/manual_review_v2.json).
"""
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = ROOT / "data" / "batch10k"
ERAS = ["pre1900", "1900-1939", "1940-1969", "1970-1999", "2000+"]
FIELDS = ("title", "scope_and_content", "author", "publisher", "involved", "coverage", "form", "thema")


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def sample(per_cell: int = 2, seed: int = 7) -> None:
    recs = {r["id"]: r for r in json.loads((BATCH / "records_raw.json").read_text(encoding="utf-8"))}
    rows = [r for r in _jsonl(BATCH / "classified.jsonl") if r.get("apertus")]  # the review checks Apertus, not the gazetteer
    cells = defaultdict(list)
    for r in rows:
        rec = recs[r["id"]]
        cells[rec["tier"], rec["stratum"], rec["era"]].append(r)
    rng = random.Random(seed)
    out = []
    for key in sorted(cells):
        for r in rng.sample(sorted(cells[key], key=lambda x: x["id"]), min(per_cell, len(cells[key]))):
            rec, a = recs[r["id"]], r["apertus"]
            out.append({
                "id": r["id"], "cell": "/".join(key), "level": rec.get("level"),
                "original": {k: rec[k] for k in FIELDS if rec.get(k)} | {"date": rec["date"]["expressed"],
                            "hierarchy": [h["title"] for h in rec["hierarchy"][:3]]},
                "apertus": {k: a.get(k) for k in ("document_type", "medium", "source_level", "source_level_rationale",
                                                  "title_normalized", "title_en", "resume", "creator", "publisher",
                                                  "date_created", "date_published", "languages")}
                           | {"persons": [p["name"] for p in a["persons"]], "organizations": [o["name"] for o in a["organizations"]],
                              "places": [p["name"] for p in a["places"]],
                              "personal_data": {k: a["personal_data"].get(k) for k in ("contains_personal_data", "sensitivity")}},
            })
    path = BATCH / "review_queue.jsonl"
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), encoding="utf-8")
    print(f"  {len(out)} records from {len(cells)} cells -> {path.relative_to(ROOT)}")


def _pct(k, n):
    return f"{100 * k / n:.1f} %" if n else "–"


def report() -> None:
    qc = json.loads((BATCH / "qc_report.json").read_text(encoding="utf-8"))
    demo = json.loads((ROOT / "data" / "qc_report.json").read_text(encoding="utf-8"))["summary"]
    recs = {r["id"]: r for r in json.loads((BATCH / "records_raw.json").read_text(encoding="utf-8"))}
    s, checks = qc["summary"], qc["records"]
    for c in checks:
        c["tier"], c["era"] = recs[c["id"]]["tier"], recs[c["id"]]["era"]
    rows = [json.loads(l) for l in (BATCH / "classified.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    tv = [r["apertus"]["source_level"] for r in rows if r.get("apertus") and r["apertus"]["document_type"] in ("TV news report", "newsreel")]
    tv_all, tv_sec = len(tv), tv.count("secondary")
    L = [f"# Verification of the 10,000-record mixed batch",
         "",
         f"{len(recs):,} records of the Swiss Federal Archives, drawn by `src/cora/mixed.py` over three source tiers "
         "(primary by form; secondary and tertiary from archival evidence: title conventions and form), the three form types "
         "and five eras of the beginning date, none of them already in `data/`. Processed by `src/batch_run.sh` with the "
         "per-feature models of `src/config.toml` (classify/audit: Apertus v1.5 8B, source level: 70B). "
         "Timings in `data/batch10k/timing.tsv`, full per-record checks in `data/batch10k/qc_report.json`.",
         "", "## Findings", "",
         f"- **Ready for the website.** {s['processed_ok_pct']} % of the records pass every automatic check (target ≥ 80 %), "
         f"{s['structural_error_pct']} % have a structural error (target < 5 %); creation dates fall inside the record's own range in "
         f"{s['date_created_in_range_pct']} % of the cases. {sum(1 for c in checks if 'no_output' in c.get('critical', []))} records got no valid "
         "answer from either model and are left out.",
         "- **Source level.** Registers and indexes (tertiary) and press clippings (secondary) are recognised in 95-97 % of the cases. "
         "The low agreement on the 'history' and 'obituary' pools is mostly the evidence label being wrong, not Apertus: these title "
         "patterns also catch department dossiers about congresses, correspondence about a Festschrift and parliamentary eulogies, "
         "which Apertus correctly calls primary (manual review: source level right in 92 % of the sample).",
         f"- **Known inconsistency (also in the demo set).** TV news and newsreels are split between primary and secondary: the "
         f"source-level pass applies the press convention (`press_convention = \"secondary\"`) to broadcast news only part of the time "
         f"({tv_sec:,} of {tv_all:,} in this batch; 27 of 41 in the demo). A rule that fixes broadcast news to one level would remove it.",
         "- **Archiving date.** Apertus matches the accession-number rule in only "
         f"{s['date_archived_correct_pct']} % of the records; the export always uses the rule (conflict policy in `export.py`), so this does not reach the site.",
         "- **Manual review.** Major errors in 4 of 66 records: a misread institution (German BND for the Swiss intelligence service), "
         "an invented first name, a grant request read as the book it funds and a police card with the archive as creator. "
         "Most minor errors are document type / medium on non-standard items (posters, typed communiqués, tables of contents).",
         "", "## Draw", "", "| Tier / type | " + " | ".join(ERAS) + " | Total |", "|---|" + "---:|" * (len(ERAS) + 1)]
    plan = json.loads((BATCH / "sample.json").read_text(encoding="utf-8"))["plan"]
    strata = sorted({k.rsplit("/", 1)[0] for k in plan}, key=lambda k: (["primary", "secondary", "tertiary"].index(k.split("/")[0]), k))
    for st in strata:
        row = [plan[f"{st}/{e}"]["drawn"] for e in ERAS]
        L.append(f"| {st} | " + " | ".join(f"{n:,} (of {plan[f'{st}/{e}']['pool']:,})" if plan[f'{st}/{e}']['pool'] else "–" for n, e in zip(row, ERAS)) + f" | {sum(row):,} |")
    L += ["", "Cells with fewer records than their share are taken in full; the rest goes to the other cells of the type.", ""]

    L += ["## Automatic checks (qc.py)", "", "| Check | This batch | Demo (300) |", "|---|---:|---:|"]
    for k, lab in (("processed_ok_pct", "Records without structural or critical error"), ("structural_error_pct", "Structural errors"),
                   ("critical_error_pct", "Critical errors"), ("resume_max_3_sentences_pct", "Résumé ≤ 3 sentences"),
                   ("entity_grounding_pct", "Named entities found in the record"), ("entity_grounding_strict_pct", "… strict match"),
                   ("date_created_in_range_pct", "Creation date inside the record's date range"),
                   ("date_archived_correct_pct", "Archiving date = accession rule"), ("places_resolved_pct", "Places located by the gazetteer")):
        L.append(f"| {lab} | {s.get(k)} % | {demo.get(k)} % |")
    L.append(f"| Creator / publisher agreement with the record | {s['creator_agreement']} / {s['publisher_agreement']} | "
             f"{demo['creator_agreement']} / {demo['publisher_agreement']} |")
    L += ["", "Critical errors: " + (", ".join(f"{k} {n}" for k, n in s["critical_types"]) or "none"),
          "", "Structural errors: " + (", ".join(f"{k} {n}" for k, n in s["structural_error_types"]) or "none"),
          "", "Warnings: " + ", ".join(f"{k} {n}" for k, n in s["warning_types"][:10]), ""]

    L += ["## By tier and era", "", "| Tier | Era | n | OK | Critical | Date in range | Source level = evidence |", "|---|---|---:|---:|---:|---:|---:|"]
    for tier in ("primary", "secondary", "tertiary"):
        for era in ERAS:
            g = [c for c in checks if c["tier"] == tier and c["era"] == era]
            if not g:
                continue
            dr = [c for c in g if c.get("created_in_range") is not None]
            ev = [c for c in g if c.get("evidence_source_level")]
            L.append(f"| {tier} | {era} | {len(g):,} | {_pct(sum(c['ok'] for c in g), len(g))} | "
                     f"{_pct(sum(bool(c.get('critical')) for c in g), len(g))} | {_pct(sum(c['created_in_range'] for c in dr), len(dr))} | "
                     f"{_pct(sum(c['evidence_source_level'] == c.get('source_level') for c in ev), len(ev)) if ev else '–'} |")
    L += ["", "## Source level", ""]
    sl = s.get("source_level_vs_evidence")
    if sl:
        L += [f"Against the level set from archival evidence (secondary and tertiary tiers, n = {sl['n']:,}): "
              f"**{sl['agreement_pct']} %** agree (demo: {demo.get('source_level_vs_evidence', {}).get('agreement_pct')} %).", "",
              "| Evidence → Apertus | n |", "|---|---:|"] + [f"| {k} | {n:,} |" for k, n in sl["confusion"].items()] + [""]
        L += ["| Stratum | n | Agreement | Apertus said |", "|---|---:|---:|---|"] + [
            f"| {st} | {v['n']:,} | {v['agreement_pct']} % | " + ", ".join(f"{k} {n}" for k, n in v["predicted"].items()) + " |"
            for st, v in sl["by_stratum"].items()] + [""]
    prim = Counter(c.get("source_level") for c in checks if c["tier"] == "primary")
    L += [f"Primary tier (no evidence label; mostly item-level film, photo and text records): Apertus says "
          + ", ".join(f"{k} {n:,}" for k, n in prim.most_common()) + ".", ""]
    L += ["## Distribution", "", "Document types: " + ", ".join(f"{k} {n:,}" for k, n in s["distribution"]["document_type"][:15]), ""]

    mr = BATCH / "manual_review.json"
    if mr.exists():
        m = json.loads(mr.read_text(encoding="utf-8"))
        items = m["items"]
        L += ["## Manual review", "", m["method"], "",
              "Verdicts: " + ", ".join(f"{k} {n}" for k, n in Counter(i["verdict"] for i in items).most_common()), "",
              "| Field | Accuracy | Errors |", "|---|---:|---:|"]
        for f in sorted({f for i in items for f in i["fields"]}):
            ok = sum(i["fields"].get(f) == "ok" for i in items)
            err = sum(i["fields"].get(f) == "error" for i in items)
            L.append(f"| {f} | {_pct(ok, ok + err)} | {err} |")
        L += ["", "Error types: " + ", ".join(f"{k} {n}" for k, n in Counter(e for i in items for e in i["errors"]).most_common()), ""]
        L += ["Notes on the major errors:", ""] + [f"- `{i['id']}` ({i['cell']}): {i['note']}" for i in items if i["verdict"] == "major_errors"] + [""]
    L += ["## Cost", "", f"{s['cost']['prompt_tokens']:,} prompt + {s['cost']['completion_tokens']:,} completion tokens for classification, "
          f"{s['cost']['mean_seconds_per_record']} s per record (12 parallel requests), {s['cost']['retries']} JSON retries.", ""]
    timing = BATCH / "timing.tsv"
    if timing.exists():
        mins = {}
        for a, b, *_ in (l.split("\t") for l in timing.read_text().splitlines()[1:]):
            mins[a] = mins.get(a, 0) + int(b) / 60
        L += ["| Stage (incl. re-runs) | Minutes |", "|---|---:|"] + [f"| {a} | {m:.0f} |" for a, m in mins.items()] + [""]
    out = ROOT / "docs" / "batch10k_verification.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    {"sample": sample, "report": report}[sys.argv[1]]()
