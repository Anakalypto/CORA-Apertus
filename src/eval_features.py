"""Apertus 70B vs 8B on every AI feature of CORA: same inputs, same prompts, scored the same way.

    python src/eval_features.py                    # all features
    python src/eval_features.py stapfer qa         # some features

Each feature calls the pipeline's own prompt builders and post-processing, so what is measured is what
the site runs. Raw outputs and metrics go to data/model_eval/<feature>.json (re-runs are incremental per
model; --force redoes them). Reference data, strongest first:
  stapfer     University of Bern hand coding of the Stapfer-Enquete (ground truth)
  level       30 source levels adjudicated by hand (ground truth) + 200 keyword-drawn labels (weak)
  whatif      backtest: real party recommendations of past votes (ground truth), with a naive baseline
  audit       deterministic rule detectors for the 5 mechanical checks (exact for those checks)
  qa          question set with the record that answers it, and questions the sample cannot answer
  parsing     see src/eval_models.py (automatic checks on 200 new records)
  more        model-independent citation/support checks of more.py
  topic, consultations   agreement between the two models (no reference available)
"""
import argparse
import json
import random
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cora import classify, config  # noqa: E402
from cora.apertus import Apertus  # noqa: E402

MODELS = ("apertus-v1-5-70b", "apertus-v1-5-8b")
CFG = config.load()
DATA = CFG["paths"]["data_dir"]
OUT = DATA / "model_eval"
FORCE = False


# ---------------------------------------------------------------- helpers
def client(model: str, temperature: float, max_tokens: int) -> Apertus:
    l = CFG["llm"]
    return Apertus(l["base_url"], l["api_key"], model, temperature, max_tokens, l["retries"])


def pmap(fn, items, workers: int = 6) -> list:
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(fn, items))


def timed(fn, *a):
    t0 = time.time()
    try:
        return fn(*a), None, round(time.time() - t0, 1)
    except Exception as e:  # a failed call is a result too (counted as an error)
        return None, repr(e)[:300], round(time.time() - t0, 1)


def pct(k, n):
    return round(100 * k / n, 1) if n else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 1) if xs else None


def prf(pairs) -> dict:
    """pairs of (model_says, reference_says) booleans."""
    tp = sum(1 for m, g in pairs if m and g)
    fp = sum(1 for m, g in pairs if m and not g)
    fn = sum(1 for m, g in pairs if not m and g)
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"positives": tp + fn, "precision": round(p, 3) if p is not None else None,
            "recall": round(r, 3) if r is not None else None, "f1": round(f1, 3) if f1 is not None else None}


def run_models(name: str, inputs: list, one) -> dict:
    """one(model, item) -> dict with an "id". Keeps earlier outputs per model unless --force."""
    path = OUT / f"{name}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() and not FORCE else {}
    outs = {}
    for m in MODELS:
        prev = {o["id"]: o for o in old.get("outputs", {}).get(m, [])}
        todo = [x for x in inputs if x["id"] not in prev]
        print(f"  [{name}] {m}: {len(prev)} cached, {len(todo)} to run")
        new = {o["id"]: o for o in pmap(lambda x: one(m, x), todo)}
        outs[m] = [prev.get(x["id"]) or new[x["id"]] for x in inputs]
    return outs


def save(name: str, outputs: dict, metrics: dict, note: str) -> dict:
    OUT.mkdir(exist_ok=True)
    res = {"feature": name, "note": note, "metrics": metrics, "outputs": outputs}
    (OUT / f"{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"feature": name, "metrics": metrics}, ensure_ascii=False, indent=1))
    return res


def common(outs: list[dict]) -> dict:
    return {"n": len(outs), "errors": sum(1 for o in outs if o.get("error")), "mean_seconds": mean(o.get("seconds") for o in outs)}


# ---------------------------------------------------------------- 1. Stapfer (ground truth: Bern hand coding)
def f_stapfer(n: int = 100):
    from cora import stapfer
    cases_path = DATA / "stapfer" / "cases.json"
    if not cases_path.exists():  # builds cases.json from the public dump, as `run.py stapfer` does
        import urllib.request
        import zipfile
        zpath = DATA / "stapfer" / "stapferappdb_final.sql.zip"
        if not zpath.exists():
            urllib.request.urlretrieve(stapfer.DUMP_URL, zpath)
        z = zipfile.ZipFile(zpath)
        cases_path.write_text(json.dumps(stapfer.build_cases(stapfer.load_dump(z.read(z.namelist()[0]).decode("utf-8", "replace"))),
                                         ensure_ascii=False), encoding="utf-8")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    sample = random.Random(42).sample(sorted(cases, key=lambda c: c["id"]), n)  # seed 42: first 40 = the published run
    items = [{"id": str(c["id"]), "case": c} for c in sample]

    def one(m, x):
        got, err, s = timed(lambda: client(m, 0.0, 1500).chat_json(stapfer.messages(x["case"]))[0])
        res = {f: stapfer.compare(x["case"]["reference"].get(f), (got or {}).get(f)) for f in stapfer.FIELDS} if got else None
        return {"id": x["id"], "error": err, "seconds": s, "extracted": {f: (got or {}).get(f) for f in stapfer.FIELDS}, "result": res}

    outs = run_models("stapfer", items, one)
    metrics = {}
    for m, os_ in outs.items():
        ok = [o for o in os_ if o["result"]]
        fields = {}
        for f in stapfer.FIELDS:
            rs = [o["result"][f] for o in ok]
            scored = sum(rs.count(k) for k in ("match", "mismatch", "missed"))
            fields[f] = pct(rs.count("match"), scored)
        allm = sum(sum(o["result"][f] == "match" for f in stapfer.FIELDS) for o in ok)
        alls = sum(sum(o["result"][f] in ("match", "mismatch", "missed") for f in stapfer.FIELDS) for o in ok)
        metrics[m] = common(os_) | {"accuracy_all_fields_pct": pct(allm, alls), "accuracy_by_field_pct": fields,
                                    "invented_values": sum(sum(o["result"][f] == "extra" for f in stapfer.FIELDS) for o in ok)}
    return save("stapfer", outs, metrics, f"{n} response sheets of the Stapfer-Enquete (1799); accuracy = share of the fields "
                "the Bern team coded that the model extracted identically (stapfer.compare). invented_values = model gave a value Bern left empty.")


# ---------------------------------------------------------------- 2. Source level (ground truth: 30 adjudicated)
def f_level():
    recs = {r["id"]: r for r in json.loads((DATA / "records_raw.json").read_text(encoding="utf-8"))}
    adj = {a["id"]: a for a in json.loads((DATA / "extra_v1" / "source_level_adjudication.json").read_text(encoding="utf-8"))["items"]}
    # the adjudicated records come from the first draw of extra sources (only their IDs are stored): fetch them once
    cache = OUT / "adjudicated_records.json"
    if not cache.exists():
        from cora import lindas
        OUT.mkdir(exist_ok=True)
        cache.write_text(json.dumps(lindas.fetch_records([i for i in adj if i not in recs]), ensure_ascii=False), encoding="utf-8")
    first = {e["id"]: e for e in json.loads((DATA / "extra_v1" / "sample_extra.json").read_text(encoding="utf-8"))["sample"]}
    for r in json.loads(cache.read_text(encoding="utf-8")):
        recs.setdefault(r["id"], r | {"expected_source_level": first.get(r["id"], {}).get("expected_source_level")})
    items = [{"id": rid, "rec": r} for rid, r in recs.items() if r.get("expected_source_level") or rid in adj]
    conv = CFG["classify"].get("press_convention", "secondary")

    def one(m, x):
        raw, err, s = timed(lambda: client(m, CFG["llm"]["temperature"], 800).chat_json(classify.build_level_messages(x["rec"]))[0])
        lvl = classify.level_from_answers(raw, conv) if raw else None
        return {"id": x["id"], "error": err, "seconds": s, "level": lvl and lvl["level"], "rule": lvl and lvl["rule"]}

    outs = run_models("level", items, one)
    metrics = {}
    for m, os_ in outs.items():
        gold = [(o["level"], adj[o["id"]]) for o in os_ if o["id"] in adj and adj[o["id"]]["verdict"] != "neither"]
        right = sum(1 for lv, a in gold if lv == a["correct"] or (a["verdict"] == "both_defensible"
                                                                  and lv in (a["correct"], recs[a["id"]].get("expected_source_level"))))
        weak = [(o["level"], recs[o["id"]]["expected_source_level"]) for o in os_ if recs[o["id"]].get("expected_source_level")]
        metrics[m] = common(os_) | {
            "adjudicated_accuracy_pct": pct(right, len(gold)), "adjudicated_n": len(gold),
            "keyword_label_agreement_pct": pct(sum(a == b for a, b in weak), len(weak)), "keyword_labels_n": len(weak),
            "by_keyword_label": {g: pct(sum(a == b for a, b in weak if b == g), sum(1 for _, b in weak if b == g)) for g in ("secondary", "tertiary")}}
    return save("level", outs, metrics, "Pass 3 (source level). Reference: 30 records adjudicated by hand (data/extra_v1/source_level_adjudication.json; "
                "'both defensible' accepts either level, 'neither' excluded). Keyword labels come from how the 200 extra sources were drawn "
                "and were often wrong in that adjudication, so they are a weak signal only.")


# ---------------------------------------------------------------- 3. Audit (reference: rule detectors)
def f_audit(n: int = 200):
    recs = json.loads((DATA / "eval200" / "records_raw.json").read_text(encoding="utf-8"))[:n]
    items = [{"id": r["id"], "rec": r} for r in recs]

    def one(m, x):
        raw, err, s = timed(lambda: client(m, CFG["llm"]["temperature"], 1500).chat_json(classify.build_audit_messages(x["rec"]))[0])
        if not raw:
            return {"id": x["id"], "error": err, "seconds": s}
        checks, pre, personal = classify.audit_to_flags(raw, x["rec"])
        return {"id": x["id"], "error": None, "seconds": s, "apertus": {k: v["apertus"] for k, v in checks.items()},
                "rule": {k: v["rule"] for k, v in checks.items() if v["rule"] is not None}, "personal": personal}

    outs = run_models("audit", items, one)
    metrics = {}
    ok = {m: {o["id"]: o for o in os_ if not o.get("error")} for m, os_ in outs.items()}
    both = set.intersection(*(set(v) for v in ok.values()))
    for m, os_ in outs.items():
        good = [o for o in os_ if not o.get("error")]
        metrics[m] = common(os_) | {"vs_rule_detector": {k: prf([(o["apertus"][k], o["rule"][k]) for o in good]) for k in classify.RULE_CHECKS},
                                    "flags_private_individuals_pct": pct(sum(o["personal"]["private_individuals"] for o in good), len(good)),
                                    "flags_sensitive_pct": pct(sum(o["personal"]["sensitive_categories"] for o in good), len(good))}
    a, b = MODELS
    metrics["agreement_on_judgement_checks_pct"] = {k: pct(sum(ok[a][i]["apertus"][k] == ok[b][i]["apertus"][k] for i in both), len(both))
                                                    for k in classify.AUDIT_CHECKS if k not in classify.RULE_CHECKS}
    return save("audit", outs, metrics, f"Pass 2 (preprocessing / personal-data audit) on the {n} eval200 records. The five mechanical checks "
                "are scored against the deterministic detectors of classify.rule_checks (the pipeline flags = Apertus OR rule); "
                "the judgement checks (persons, places, sensitivity) have no reference and are compared between models.")


# ---------------------------------------------------------------- 4. Ask the archive (question set)
QA_ANSWERABLE = [  # (question, record that answers it)
    ("What happened with milk prices in 2007?", "22365692"),
    ("When was the Flims bypass opened?", "29672818"),
    ("How did the Green Party assess the outgoing legislature in 2007?", "22371890"),
    ("How was the new hall of the Basel fair built?", "30695400"),
    ("What do the records show about the Saffa exhibition in 1989?", "21901313"),
    ("How did Ticino take part in the 1939 National Exhibition?", "5751758"),
    ("What do the First World War photographs show about telegraph pioneers?", "3240019"),
    ("Is there a finding aid about the neutrality of Savoy and the free zones?", "32685311"),
    ("What did the states bordering Lake Constance discuss?", "32684760"),
    ("What did the AlpTransit directors' committee discuss in December 2007?", "30704186"),
    ("Which record is about the history of the Lerber family?", "6627612"),
    ("What did the Swiss press write about Argentina in 1998?", "4541508"),
    ("Which newspaper clippings did the Federal Office of Civil Aviation collect in the late 1920s?", "5471797"),
    ("Who was Dr. med. Felix Schenk?", "29383476"),
    ("Welche Fotos zeigen Soldaten des Bataillons 24 in der Ruhe?", "3237334"),
    ("Quelles archives concernent la condamnation de Dogu Perincek à Lausanne?", "29668237"),
]
QA_UNANSWERABLE = [  # the sample contains related records but not the answer
    "What was the price of a litre of milk in Switzerland in 1985?",
    "Who won the 1966 football World Cup?",
    "Which party won the 2011 Swiss federal election?",
    "How many visitors did the 1939 National Exhibition have in total?",
    "What did the Federal Council decide about the Gotthard base tunnel opening in 2016?",
    "How much did the Flims bypass cost in Swiss francs?",
    "Who was the director of the Swiss Federal Archives in 1990?",
    "What is the population of Leukerbad today?",
]


def f_qa():
    from cora import api  # builds the same BM25 index as the site
    items = [{"id": f"a{i}", "q": q, "expect": rid} for i, (q, rid) in enumerate(QA_ANSWERABLE)] + \
            [{"id": f"u{i}", "q": q, "expect": None} for i, q in enumerate(QA_UNANSWERABLE)]
    from cora import qa

    def one(m, x):
        res, err, s = timed(lambda: qa.ask(api.QA_INDEX, client(m, 0.0, 1500), x["q"]))
        if not res:
            return {"id": x["id"], "error": err, "seconds": s}
        cited = [c["id"] for c in res.get("citations", [])]
        sents = res.get("sentences", [])
        return {"id": x["id"], "error": None, "seconds": s, "question": x["q"], "expect": x["expect"], "answered": res["answered"],
                "gated": not sents and not res.get("insufficient") and "message" in res, "cited": cited,
                "retrieved": [h["id"] for h in res.get("retrieved", [])], "sentences": [t["text"] for t in sents],
                "uncited": sum(t["uncited"] for t in sents), "dropped": sum(len(t["dropped_sources"]) for t in sents)}

    outs = run_models("qa", items, one)
    metrics = {}
    for m, os_ in outs.items():
        ans = [o for o in os_ if o["id"].startswith("a") and not o.get("error")]
        reach = [o for o in ans if o["expect"] in o["retrieved"]]  # retrieval found the answer: the model's part starts here
        un = [o for o in os_ if o["id"].startswith("u") and not o.get("error")]
        un_model = [o for o in un if not o["gated"]]
        sents = sum(len(o["sentences"]) for o in os_ if not o.get("error"))
        metrics[m] = common(os_) | {
            "answerable_answered_pct": pct(sum(o["answered"] for o in ans), len(ans)),
            "answerable_cites_right_record_pct": pct(sum(o["expect"] in o["cited"] for o in reach), len(reach)),
            "answerable_retrieval_found_record": f"{len(reach)}/{len(ans)}",
            "unanswerable_refused_pct": pct(sum(not o["answered"] for o in un), len(un)),
            "unanswerable_refused_by_model_pct": pct(sum(not o["answered"] for o in un_model), len(un_model)),
            "unanswerable_reaching_model": len(un_model),
            "uncited_sentences_pct": pct(sum(o["uncited"] for o in os_ if not o.get("error")), sents),
            "invalid_citations_dropped": sum(o.get("dropped", 0) for o in os_)}
    return save("qa", outs, metrics, f"{len(QA_ANSWERABLE)} questions whose answer is in a known record and {len(QA_UNANSWERABLE)} the sample "
                "cannot answer (related records exist). Retrieval (BM25) is identical for both models; 'cites right record' counts only "
                "questions where retrieval offered that record. A refusal of an unanswerable question is either the retrieval gate or the model.")


# ---------------------------------------------------------------- 6. See more
def _eval_cfg(m: str) -> dict:
    """A config whose data_dir is a per-model scratch dir, so the features' own caches never mix models or touch data/."""
    import copy
    import shutil
    cfg = copy.deepcopy(CFG)
    d = OUT / "cache" / m
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "enrich_cache.json").exists() and (DATA / "enrich_cache.json").exists():
        shutil.copy(DATA / "enrich_cache.json", d / "enrich_cache.json")
    if not (d / "topic_cache").exists() and (DATA / "topic_cache").exists():  # more.shown_text reads the subject panel cache
        shutil.copytree(DATA / "topic_cache", d / "topic_cache", dirs_exist_ok=True)
    cfg["paths"]["data_dir"] = d
    return cfg


def f_more(n: int = 30):
    from cora import api, more
    ids = [rid for rid in api.RECORDS][::max(1, len(api.RECORDS) // n)][:n]
    items = [{"id": rid} for rid in ids]

    def one(m, x):
        res, err, s = timed(lambda: more.explain(api.RECORDS[x["id"]], api.QA_INDEX, _eval_cfg(m), client(m, 0.0, 1500)))
        ss = [t for p in (res or {}).get("paragraphs", []) for t in p]
        return {"id": x["id"], "error": err, "seconds": s, "sentences": [t["text"] for t in ss], "inferred": sum(t["inferred"] for t in ss),
                "sources_used": len((res or {}).get("sources", [])), "kinds_used": sorted({src["kind"] for src in (res or {}).get("sources", [])})}

    outs = run_models("more", items, one)
    metrics = {}
    for m, os_ in outs.items():
        ss = sum(len(o.get("sentences", [])) for o in os_)
        metrics[m] = common(os_) | {"sentences_per_text": round(ss / len(os_), 1), "unsourced_sentences_pct": pct(sum(o.get("inferred", 0) for o in os_), ss),
                                    "mean_sources_cited": mean(o.get("sources_used") for o in os_),
                                    "texts_using_wikipedia_pct": pct(sum("W" in o.get("kinds_used", []) for o in os_), len(os_))}
    return save("more", outs, metrics, f"'See more' explanation for {n} records spread over the dataset; same sources offered to both models. "
                "unsourced = sentence without a valid E/R/W/D citation (more.explain).")


# ---------------------------------------------------------------- 7. Subject panel (agreement only)
def f_topic(n: int = 20):
    from cora import api, topic
    ids = [rid for rid, r in api.RECORDS.items() if r["classification"]["source_level"] in ("secondary", "tertiary")]
    ids = random.Random(1).sample(ids, min(n, len(ids)))
    items = [{"id": rid} for rid in ids]

    def one(m, x):
        res, err, s = timed(lambda: topic.build(api.RECORDS[x["id"]], api.QA_INDEX, _eval_cfg(m), client(m, 0.0, 1500)))
        res = res or {}
        return {"id": x["id"], "error": err, "seconds": s, "subject": res.get("subject"), "identifiable": res.get("identifiable"),
                "wikipedia": (res.get("wikipedia") or {}).get("title"), "primary": [p.get("id") for p in res.get("primary", [])]}

    outs = run_models("topic", items, one)
    a, b = (dict((o["id"], o) for o in outs[m]) for m in MODELS)
    both = [i for i in a if not a[i].get("error") and not b[i].get("error")]
    jac = lambda x, y: len(set(x) & set(y)) / len(set(x) | set(y)) if set(x) | set(y) else None
    metrics = {m: common(outs[m]) | {"identifiable_pct": pct(sum(bool(o.get("identifiable")) for o in outs[m]), len(outs[m])),
                                     "wikipedia_found_pct": pct(sum(bool(o.get("wikipedia")) for o in outs[m]), len(outs[m]))} for m in MODELS}
    metrics["agreement"] = {"same_wikipedia_article_pct": pct(sum(a[i]["wikipedia"] == b[i]["wikipedia"] for i in both if a[i]["wikipedia"] or b[i]["wikipedia"]),
                                                              sum(1 for i in both if a[i]["wikipedia"] or b[i]["wikipedia"])),
                            "primary_dossier_overlap_pct": mean([100 * j for i in both if (j := jac(a[i]["primary"], b[i]["primary"])) is not None])}
    return save("topic", outs, metrics, f"Subject panel for {n} secondary/tertiary records (plan + vet passes, live Wikipedia and archive search). "
                "No reference exists; the models are compared with each other. Examples are in the outputs for a human look.")


# ---------------------------------------------------------------- 8. Consultations tagging (agreement only)
def f_consultations(n: int = 100):
    from cora import consultations as C
    cons = C.load_consultations(DATA / "consultations")[:n]
    batches = [cons[i:i + 10] for i in range(0, len(cons), 10)]
    items = [{"id": f"b{i}", "batch": b} for i, b in enumerate(batches)]

    def one(m, x):
        its = [{"n": c["nr"], "type": c["type"], "title": c["title"], "department": c["dept_abbr"], "year": c["year"],
                "addressees": c["addressees"][:200]} for c in x["batch"]]
        schema = {"items": [{"n": "<nr>", "title_en": "<short English title>", "topics": [f"<one of {C.TOPICS}>"],
                             "entities": [{"name": "<as written>", "type": "<law|organisation|place>"}], "confidence": 0.0}]}
        raw, err, s = timed(lambda: client(m, 0.0, 3000).chat_json([{"role": "system", "content": C.TAG_SYSTEM},
                            {"role": "user", "content": json.dumps(its, ensure_ascii=False) + "\n\nReturn:\n" + json.dumps(schema)}])[0])
        tags = {str(t.get("n")): {"topics": [x for x in t.get("topics") or [] if x in C.TOPICS], "invalid_topics": [x for x in t.get("topics") or [] if x not in C.TOPICS],
                                  "title_en": t.get("title_en")} for t in (raw or {}).get("items", []) if isinstance(t, dict)}
        return {"id": x["id"], "error": err, "seconds": s, "tags": tags, "asked": [c["nr"] for c in x["batch"]]}

    outs = run_models("consultations", items, one)
    tags = {m: {k: v for o in outs[m] for k, v in o.get("tags", {}).items()} for m in MODELS}
    asked = [nr for o in outs[MODELS[0]] for nr in o["asked"]]
    a, b = tags[MODELS[0]], tags[MODELS[1]]
    both = [k for k in asked if a.get(k, {}).get("topics") and b.get(k, {}).get("topics")]
    metrics = {m: common(outs[m]) | {"procedures_tagged_pct": pct(sum(1 for k in asked if tags[m].get(k, {}).get("topics")), len(asked)),
                                     "invalid_topic_labels": sum(len(v["invalid_topics"]) for v in tags[m].values())} for m in MODELS}
    metrics["agreement"] = {"same_first_topic_pct": pct(sum(a[k]["topics"][0] == b[k]["topics"][0] for k in both), len(both)),
                            "topic_set_overlap_pct": mean([100 * len(set(a[k]["topics"]) & set(b[k]["topics"])) / len(set(a[k]["topics"]) | set(b[k]["topics"])) for k in both]),
                            "n": len(both)}
    return save("consultations", outs, metrics, f"Topic tagging of the first {n} consultation procedures (batches of 10, as in the pipeline). "
                "No reference exists; topics outside the fixed list count as invalid.")


# ---------------------------------------------------------------- 9. Referendum what-if (backtest, ground truth)
WHATIF = """You know Swiss party history. A federal proposal is described. For EACH party listed, give the recommendation it most
plausibly issued for this vote ("1" yes, "2" no, "5" free vote), grounded in the evidence given (the party's recommendations
on related votes) or in the party's profile at the time. Return {"parties": {"<party>": {"rec": "1|2|5", "reason": "<sentence>"}}}."""


def _rec_code(x) -> str:
    """Models answer with the code ("1") or, echoing the evidence, with its label ("yes"): both mean the same."""
    x = str(x).strip().strip('"').lower()
    return {"yes": "1", "no": "2", "free vote": "5", "free": "5", "none": "3", "empty": "4", "neutral": "66"}.get(x, x)


def _most_frequent(seen: list) -> str | None:
    """Most frequent recommendation; ties go to the one seen first (the most similar related vote)."""
    return min(seen, key=lambda r: (-seen.count(r), seen.index(r))) if seen else None


def f_whatif(n: int = 40):
    from cora import referendum as R
    pool_ = []
    for v in R.rows(CFG):
        recs = {p: r for p, r in R.recs_of(v).items() if r in ("1", "2", "5")}
        if v["_year"] >= 1971 and len(recs) >= 5:
            pool_.append(v)
    votes = random.Random(7).sample(pool_, n)
    items = []
    for v in votes:
        rel = [o for o in R._related_candidates(CFG, v) if o["titel_kurz_d"].strip().lower() != v["titel_kurz_d"].strip().lower()][:3]
        truth = {p: r for p, r in R.recs_of(v).items() if r in ("1", "2", "5")}
        evidence = {f"{o['_iso']} {o['titel_kurz_d']}": {p: R.REC_LABEL.get(r, r) for p, r in R.recs_of(o).items() if p in truth} for o in rel}
        # naive baseline: each party repeats its most frequent recommendation on the related votes
        base = {}
        for p in truth:
            seen = [R.recs_of(o).get(p) for o in rel if R.recs_of(o).get(p) in ("1", "2", "5")]
            base[p] = _most_frequent(seen)
        prompt = (WHATIF + f"\n\nProposal: {v['titel_kurz_d']} / {v['titel_kurz_f']} ({v['titel_off_d'][:300]}), voted {v['_iso']}.\n"
                  f"Parties: {json.dumps(sorted(truth))}\nEvidence, recommendations on related votes: {json.dumps(evidence, ensure_ascii=False)}")
        items.append({"id": v["anr"], "prompt": prompt, "truth": truth, "baseline": base})

    def one(m, x):
        raw, err, s = timed(lambda: client(m, 0.3, 1200).chat_json([{"role": "user", "content": x["prompt"]}])[0])
        got = {p: _rec_code(y.get("rec")) for p, y in ((raw or {}).get("parties") or {}).items() if isinstance(y, dict)}
        return {"id": x["id"], "error": err, "seconds": s, "predicted": got, "truth": x["truth"], "baseline": x["baseline"]}

    outs = run_models("whatif", items, one)
    for os_ in outs.values():
        for o in os_:
            o["predicted"] = {p: _rec_code(r) for p, r in o["predicted"].items()}
    metrics = {}
    for m, os_ in outs.items():
        pairs = [(o["predicted"].get(p), t) for o in os_ for p, t in o["truth"].items()]
        bp = [(o["baseline"].get(p), t) for o in os_ for p, t in o["truth"].items() if o["baseline"].get(p)]
        mp = [(o["predicted"].get(p), t) for o in os_ for p, t in o["truth"].items() if o["baseline"].get(p)]
        metrics[m] = common(os_) | {"party_positions": len(pairs), "accuracy_pct": pct(sum(a == b for a, b in pairs), len(pairs)),
                                    "missing_parties": sum(1 for a, _ in pairs if a is None),
                                    "accuracy_where_baseline_applies_pct": pct(sum(a == b for a, b in mp), len(mp)),
                                    "naive_baseline_accuracy_pct": pct(sum(a == b for a, b in bp), len(bp))}
    return save("whatif", outs, metrics, f"Backtest of the 'what if' imagination on {n} real federal votes since 1971: the model sees the proposal and "
                "the parties' recommendations on up to 3 related votes (never this vote's own) and predicts each party's recommendation; "
                "compared with the real Swissvotes recommendation. Baseline: each party repeats its most frequent related-vote recommendation.")


ANCHORED = """You know Swiss party history. A federal proposal is described, with each party's recommendations on related
votes. For each party a DEFAULT is given: the recommendation it issued most often on those related votes. Keep the default
unless this proposal differs from the related votes in a way that would clearly change that party's position; only then
change it, and say in one sentence what difference makes the party change. Codes: "1" yes, "2" no, "5" free vote.
Return {"parties": {"<party>": {"rec": "1|2|5", "changed": true|false, "reason": "<sentence>"}}}."""


def f_whatif_fix(n: int = 40):
    """Variants for the what-if positions, on the same votes as f_whatif: two evidence rules and an anchored prompt."""
    from cora import referendum as R
    base_run = json.loads((OUT / "whatif.json").read_text(encoding="utf-8"))
    votes = {v["anr"]: v for v in R.rows(CFG)}
    items = []
    for o in base_run["outputs"][MODELS[0]][:n]:
        v = votes[o["id"]]
        rel = [x for x in R._related_candidates(CFG, v) if x["titel_kurz_d"].strip().lower() != v["titel_kurz_d"].strip().lower()][:3]
        truth = o["truth"]
        seen = {p: [R.recs_of(x).get(p) for x in rel if R.recs_of(x).get(p) in ("1", "2", "5")] for p in truth}
        freq = {p: _most_frequent(seen[p]) for p in truth}
        nearest = {p: (seen[p][0] if seen[p] else None) for p in truth}
        evidence = {f"{x['_iso']} {x['titel_kurz_d']}": {p: R.REC_LABEL.get(r, r) for p, r in R.recs_of(x).items() if p in truth} for x in rel}
        prompt = (ANCHORED + f"\n\nProposal: {v['titel_kurz_d']} / {v['titel_kurz_f']} ({v['titel_off_d'][:300]}), voted {v['_iso']}.\n"
                  f"Evidence, recommendations on related votes: {json.dumps(evidence, ensure_ascii=False)}\n"
                  f"Defaults: {json.dumps({p: freq[p] for p in sorted(truth) if freq[p]})}\n"
                  f"Parties without related-vote evidence (no default, decide from the party's profile): {json.dumps(sorted(p for p in truth if not freq[p]))}")
        items.append({"id": o["id"], "prompt": prompt, "truth": truth, "freq": freq, "nearest": nearest})

    def one(m, x):
        raw, err, s = timed(lambda: client(m, 0.0, 1500).chat_json([{"role": "user", "content": x["prompt"]}])[0])
        got = {p: _rec_code(y.get("rec")) for p, y in ((raw or {}).get("parties") or {}).items() if isinstance(y, dict)}
        return {"id": x["id"], "error": err, "seconds": s, "predicted": got, "truth": x["truth"], "freq": x["freq"], "nearest": x["nearest"]}

    outs = run_models("whatif_fix", items, one)
    acc = lambda pairs: pct(sum(a == b for a, b in pairs), len(pairs))
    allp = [(p, t, x) for x in items for p, t in x["truth"].items()]
    metrics = {"positions": len(allp),
               "rule_most_frequent_pct": acc([(x["freq"][p], t) for p, t, x in allp]),
               "rule_nearest_vote_pct": acc([(x["nearest"][p], t) for p, t, x in allp]),
               "positions_with_evidence": sum(1 for p, t, x in allp if x["freq"][p])}
    for m, os_ in outs.items():
        by = {o["id"]: o for o in os_}
        pairs = [(by[x["id"]]["predicted"].get(p), t) for p, t, x in allp]
        changed = [(by[x["id"]]["predicted"].get(p), t) for p, t, x in allp if x["freq"][p] and by[x["id"]]["predicted"].get(p) not in (None, x["freq"][p])]
        kept_wrong = sum(1 for p, t, x in allp if x["freq"][p] and x["freq"][p] != t)
        no_ev = [(by[x["id"]]["predicted"].get(p), t) for p, t, x in allp if not x["freq"][p]]
        # hybrid: rule where evidence exists, the anchored model only where it does not
        hybrid = [((x["freq"][p] or by[x["id"]]["predicted"].get(p)), t) for p, t, x in allp]
        metrics[m] = common(os_) | {"anchored_accuracy_pct": acc(pairs), "changes": len(changed), "changes_right_pct": acc(changed),
                                    "defaults_that_were_wrong": kept_wrong, "no_evidence_accuracy_pct": acc(no_ev), "no_evidence_n": len(no_ev),
                                    "hybrid_rule_plus_model_pct": acc(hybrid)}
    return save("whatif_fix", outs, metrics, "What-if variants on the same votes as 'whatif'. Rules: each party repeats its most frequent "
                "(ties: most similar vote) or its most similar related-vote recommendation. Anchored: the model gets the most-frequent rule "
                "as a default and may change it with a reason (temperature 0). Hybrid: the rule where a party has related-vote evidence, the "
                "anchored model's answer where it has none.")


FEATURES = {"stapfer": f_stapfer, "level": f_level, "audit": f_audit, "qa": f_qa,
            "more": f_more, "topic": f_topic, "consultations": f_consultations, "whatif": f_whatif, "whatif_fix": f_whatif_fix}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("features", nargs="*", help=" ".join(FEATURES))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    FORCE = args.force
    unknown = set(args.features) - set(FEATURES)
    if unknown:
        raise SystemExit(f"unknown feature(s) {sorted(unknown)}; choose from {list(FEATURES)}")
    for name in args.features or FEATURES:
        print(f"[{name}]")
        FEATURES[name]()
