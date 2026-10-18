"""Trust card: Evidence / Context / Imagination for each record.

Evidence    – original archive fields, reference code, portal link (tier: the record itself)
Context     – Wikidata items of linked persons/organisations with Wikipedia and HLS links (tier: secondary/tertiary)
Imagination – a short Apertus narrative; every sentence must footnote evidence [E#] or context [C#] items.
              Sentences with no valid footnote are kept but marked "inferred". All of it is labelled generated.
"""
import json
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .enrich import Cache, _get
from .qa import tokens

ORIGINAL_LABELS = {"title": "Title", "scope_and_content": "Scope and content", "author": "Author", "publisher": "Publisher",
                   "involved": "Involved", "coverage": "Coverage", "form": "Form", "format": "Physical format",
                   "thema": "Subject terms", "country": "Country", "alternate_reference": "Alternate reference",
                   "old_reference_code": "Old reference code"}


def evidence(r: dict) -> list[dict]:
    o, loc = r["source"]["original"], r["archival_location"]
    items = [{"key": k, "label": lab, "value": o[k]} for k, lab in ORIGINAL_LABELS.items() if o.get(k)]
    if o.get("date"):
        items.append({"key": "date", "label": "Date", "value": o["date"].get("expressed")})
    items.append({"key": "reference_code", "label": "Reference code", "value": r["source"]["reference_code"]})
    items.append({"key": "archive_path", "label": "Place in the archive", "value": " › ".join(loc.get("path") or [])})
    if loc.get("accession_numbers"):
        items.append({"key": "accession", "label": "Accession", "value": ", ".join(a for a in loc["accession_numbers"] if a)})
    for i, it in enumerate(items, 1):
        it["ref"] = f"E{i}"
    return items


def fetch_context(qids: list[str], cache: Cache, cfg) -> None:
    """Sitelinks (de/fr/it/en Wikipedia) and HLS id (P902) for Wikidata items, cached as 'ctx|Q…'."""
    todo = [q for q in dict.fromkeys(qids) if "ctx|" + q not in cache.data]
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        time.sleep(0.5)
        try:
            ents = _get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
                {"action": "wbgetentities", "ids": "|".join(chunk), "props": "claims|sitelinks", "format": "json"}),
                cfg["enrich"]["user_agent"])["entities"]
        except Exception:
            continue
        for q, e in ents.items():
            sl = e.get("sitelinks", {})
            wp = next(({"lang": l, "url": f"https://{l}.wikipedia.org/wiki/{urllib.parse.quote(sl[l + 'wiki']['title'].replace(' ', '_'))}"}
                       for l in ("de", "fr", "it", "en") if l + "wiki" in sl), None)
            hls = None
            for c in e.get("claims", {}).get("P902", []):
                v = (c.get("mainsnak", {}).get("datavalue") or {}).get("value")
                if v:
                    hls = f"https://hls-dhs-dss.ch/de/articles/{v}/"
                    break
            cache.data["ctx|" + q] = {"wikipedia": wp, "hls": hls}


def context(r: dict, cache: Cache) -> list[dict]:
    items = []
    for kind, ents in (("person", r["entities"]["persons"]), ("organization", r["entities"]["organizations"])):
        for e in ents:
            wd = e.get("wikidata")
            if not wd:
                continue
            ctx = cache.data.get("ctx|" + wd["qid"], {})
            items.append({"kind": kind, "name": e.get("display_name") or e["name"], "description": wd.get("description"),
                          "wikidata": wd["url"], "wikipedia": (ctx.get("wikipedia") or {}).get("url"), "hls": ctx.get("hls"),
                          "tier": "tertiary" if not ctx.get("hls") else "secondary (HLS) / tertiary (Wikipedia, Wikidata)"})
    for p in r["entities"]["places"]:
        if p.get("lat") is not None:
            items.append({"kind": "place", "name": p["name"], "description": f"{p['role']} place, located by OpenStreetMap",
                          "osm": p.get("gazetteer"), "tier": "tertiary (gazetteer)"})
    for i, it in enumerate(items, 1):
        it["ref"] = f"C{i}"
    return items


SYSTEM = """You write the short story of ONE archival record of the Swiss Federal Archives for a general audience.
Use only the numbered evidence [E#] (the record itself) and context [C#] (reference works) items given.
Every sentence must end with the footnotes it relies on, e.g. [E2][C1]. If you add an interpretation that no item
supports, still write it but give it no footnote. 3 to 5 sentences, in English, no speculation about private persons.
Return one JSON object."""


def imagine(r: dict, ev: list, ctx: list, ap) -> dict:
    schema = {"sentences": [{"text": "<sentence without the footnote markers>", "refs": ["E1", "C2"]}]}
    user = ("Evidence:\n" + "\n".join(f"[{e['ref']}] {e['label']}: {e['value']}" for e in ev)
            + "\n\nContext:\n" + ("\n".join(f"[{c['ref']}] {c['name']}: {c.get('description') or ''}" for c in ctx) or "(none)")
            + "\n\nReturn:\n" + json.dumps(schema))
    raw, meta = ap.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    allowed = {e["ref"] for e in ev} | {c["ref"] for c in ctx}
    text_of = {e["ref"]: f"{e['label']} {e['value']}" for e in ev} | {c["ref"]: f"{c['name']} {c.get('description') or ''}" for c in ctx}
    out = []
    for s in raw.get("sentences") or []:
        if isinstance(s, dict) and str(s.get("text", "")).strip():
            refs = [str(x).strip("[] ") for x in s.get("refs") or []]
            valid = [x for x in refs if x in allowed]
            # Support check independent of the model: share of the sentence's content words found in the cited items.
            words = [w for w in tokens(s["text"]) if len(w) > 4]
            cited = set(tokens(" ".join(text_of[x] for x in valid)))
            support = round(sum(w in cited or any(w[:5] == c[:5] for c in cited if len(c) > 4) for w in words) / len(words), 2) if words else 0.0
            out.append({"text": s["text"].strip(), "refs": valid, "inferred": not valid,
                        "support": support, "weakly_supported": bool(valid) and support < 0.2})
    return {"sentences": out, "model": meta.get("model"), "generated": True,
            "inferred_share": round(sum(s["inferred"] for s in out) / len(out), 2) if out else None}


def run(cfg) -> None:
    from .apertus import Apertus
    data = cfg["paths"]["data_dir"]
    recs = [json.loads(l) for l in (data / "dataset" / "cora_dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cache = Cache(data / "enrich_cache.json")
    fetch_context([e["wikidata"]["qid"] for r in recs for e in r["entities"]["persons"] + r["entities"]["organizations"]
                   if e.get("wikidata")], cache, cfg)
    cache.save()
    l = cfg["llm"]
    ap = Apertus(l["base_url"], l["api_key"], l["model"], 0.3, 1200, l["retries"])

    def one(r):
        ev, ctx = evidence(r), context(r, cache)
        try:
            im = imagine(r, ev, ctx, ap)
        except Exception as e:
            im = {"error": repr(e), "sentences": [], "generated": True}
        return {"id": r["id"], "evidence": ev, "context": ctx, "imagination": im}

    path = data / "dataset" / "trust_cards.jsonl"
    old = {}
    if path.exists():  # incremental: keep the cards already generated
        old = {c["id"]: c for c in map(json.loads, filter(None, path.read_text(encoding="utf-8").splitlines()))}
    with ThreadPoolExecutor(l["workers"]) as pool:
        new = {c["id"]: c for c in pool.map(one, [r for r in recs if r["id"] not in old])}
    cards = [old.get(r["id"]) or new[r["id"]] for r in recs]
    (data / "dataset" / "trust_cards.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards), encoding="utf-8")
    sents = [s for c in cards for s in c["imagination"]["sentences"]]
    print(f"  {len(cards)} trust cards, {len(sents)} narrative sentences, "
          f"{sum(s['inferred'] for s in sents)} inferred, {sum(1 for c in cards for x in c['context'] if x.get('hls'))} HLS links,"
          f" {sum(1 for c in cards for x in c['context'] if x.get('wikipedia'))} Wikipedia links,"
          f" {sum(s.get('weakly_supported', False) for s in sents)} weakly supported")
