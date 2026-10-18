"""'See more': an extended, cited explanation of one record, generated on demand by Apertus.

Sources, each numbered and cited sentence by sentence:
  E#  the record itself (original archive fields)                     – evidence
  R#  related records in the CORA dataset (BM25 over the database)    – evidence (other records)
  W#  Wikipedia article summaries of linked entities (REST API)       – context, tertiary
  D#  Wikidata facts (description, life dates) and gazetteer places   – context, tertiary
Sentences with no valid citation are kept and marked "inferred". The result is cached per record.
"""
import json
import time
import urllib.parse

from .enrich import Cache, _get, life_dates
from .narrative import evidence, fetch_context

SYSTEM = """You explain ONE record of the Swiss Federal Archives to a curious reader, in 2 to 3 short paragraphs.
Use only the numbered sources: [E#] the record itself, [R#] other records of the archive, [W#] Wikipedia, [D#] Wikidata or the gazetteer.
Paragraph 1: what the document is and what it shows or says [E#]. Paragraph 2: who and what it concerns, using the
Wikipedia [W#] and Wikidata [D#] sources. Paragraph 3: how it relates to other records of the archive [R#] and its wider
historical context. 2-4 sentences per paragraph. Every sentence lists the sources it relies on.
If you add something no source supports, give that sentence no sources. Do not speculate about private persons.
Answer in English. Return one JSON object."""


def wikipedia_summary(url: str, cache: Cache, cfg) -> dict | None:
    """Lead summary of a Wikipedia article through the official REST API (cached)."""
    key = "wpsum|" + url
    if key in cache.data:
        return cache.data[key]
    try:
        host = urllib.parse.urlparse(url).netloc
        title = url.rsplit("/wiki/", 1)[1]
        time.sleep(0.2)
        d = _get(f"https://{host}/api/rest_v1/page/summary/{title}", cfg["enrich"]["user_agent"])
        res = {"title": d.get("title"), "extract": (d.get("extract") or "")[:1200], "url": url,
               "lang": host.split(".")[0], "license": "CC BY-SA 4.0"}
    except Exception:
        res = None
    cache.data[key] = res
    return res


def sources(r: dict, index, cache: Cache, cfg) -> list[dict]:
    src = [dict(e, kind="E", tier="record") for e in evidence(r)]
    for e in src:
        e["text"] = f"{e['label']}: {e['value']}"
    if r["classification"].get("resume"):
        pass  # the résumé is itself generated: not offered as a source
    # related records from the database
    q = " ".join(filter(None, [r["metadata"].get("title_en"), r["metadata"]["title"], " ".join(r["metadata"].get("subjects") or [])]))
    rel = [h for h in index.search(q, 6) if h[0] != r["id"] and h[1] >= 2.5][:3]  # same relevance bar as Ask the archive
    for i, (rid, score, _) in enumerate(rel, 1):
        o = index.records[rid]
        src.append({"ref": f"R{i}", "kind": "R", "tier": "record (other)", "id": rid,
                    "label": o["metadata"].get("title_normalized") or o["metadata"]["title"],
                    "text": f'{o["metadata"]["title"]} ({o["metadata"].get("content_date") or ""}): {o["classification"].get("resume") or ""} '
                            f'{(o["source"]["original"].get("scope_and_content") or "")[:300]}',
                    "url": f"#/record/{rid}", "portal_url": o["source"]["portal_url"]})
    # Wikipedia + Wikidata for linked persons/organisations, gazetteer for places
    ents = [e for e in r["entities"]["persons"] + r["entities"]["organizations"] if e.get("wikidata")]
    fetch_context([e["wikidata"]["qid"] for e in ents], cache, cfg)
    w = d = 0
    for e in ents[:6]:
        wd = e["wikidata"]
        name = e.get("display_name") or e["name"]
        life = life_dates(wd["qid"], cache, cfg) if e in r["entities"]["persons"] else {}
        d += 1
        src.append({"ref": f"D{d}", "kind": "D", "tier": "tertiary (Wikidata)", "label": name, "url": wd["url"],
                    "text": f"{name}: {wd.get('description') or ''}" + (f" (born {life['born']}" + (f", died {life['died']})" if life.get("died") else ")") if life.get("born") else "")})
        wp = (cache.data.get("ctx|" + wd["qid"]) or {}).get("wikipedia")
        if wp and w < 4:
            s = wikipedia_summary(wp["url"], cache, cfg)
            if s and s["extract"]:
                w += 1
                src.append({"ref": f"W{w}", "kind": "W", "tier": "tertiary (Wikipedia, CC BY-SA)", "label": s["title"], "url": s["url"], "text": s["extract"]})
    for p in r["entities"]["places"]:
        if p.get("lat") is not None and d < 10:
            d += 1
            src.append({"ref": f"D{d}", "kind": "D", "tier": "tertiary (gazetteer)", "label": p["name"], "url": p.get("gazetteer"),
                        "text": f"{p['name']} ({p['role']} place), located at {p['lat']:.3f}, {p['lon']:.3f}"})
    return src


def explain(r: dict, index, cfg, ap) -> dict:
    cache_dir = cfg["paths"]["data_dir"] / "more_cache"
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir / f"{r['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    cache = Cache(cfg["paths"]["data_dir"] / "enrich_cache.json")
    src = sources(r, index, cache, cfg)
    cache.save()
    sent = {"text": "<sentence>", "sources": ["<E#|R#|W#|D#>"]}
    # Separate keys per paragraph: with a list of {"sentences": …} objects the model tends to repeat keys in one object.
    schema = {"paragraph_1_the_document": [sent, sent, sent],
              "paragraph_2_who_and_what_wikipedia_wikidata": [sent, sent, sent],
              "paragraph_3_related_records_and_context": [sent, sent]}
    user = ("Sources:\n" + "\n".join(f"[{s['ref']}] {s['text'][:900]}" for s in src) + "\n\nReturn:\n" + json.dumps(schema))
    raw, meta = ap.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    allowed = {s["ref"] for s in src}
    paras = []
    for key in sorted(k for k in raw if k.startswith("paragraph")):
        sents = []
        for s in raw[key] if isinstance(raw[key], list) else []:
            if isinstance(s, dict) and str(s.get("text", "")).strip():
                refs = [str(x).strip("[] ") for x in s.get("sources") or []]
                ok = [x for x in refs if x in allowed]
                sents.append({"text": s["text"].strip(), "sources": ok, "inferred": not ok})
        if sents:
            paras.append(sents)
    used = {x for p in paras for s in p for x in s["sources"]}
    out = {"id": r["id"], "generated": True, "model": meta.get("model"), "seconds": round(meta["seconds"], 1),
           "paragraphs": paras, "sources": [s for s in src if s["ref"] in used],
           "offered": {k: sum(1 for s in src if s["kind"] == k) for k in "ERWD"},
           "inferred_sentences": sum(s["inferred"] for p in paras for s in p)}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
