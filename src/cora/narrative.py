"""Trust card: Evidence / Context for each record.

Evidence    – original archive fields, reference code, portal link (tier: the record itself)
Context     – Wikidata items of linked persons/organisations with Wikipedia and HLS links (tier: secondary/tertiary)
"""
import json
import time
import urllib.parse

from .enrich import Cache, _get

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


def run(cfg) -> None:
    data = cfg["paths"]["data_dir"]
    recs = [json.loads(l) for l in (data / "dataset" / "cora_dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cache = Cache(data / "enrich_cache.json")
    fetch_context([e["wikidata"]["qid"] for r in recs for e in r["entities"]["persons"] + r["entities"]["organizations"]
                   if e.get("wikidata")], cache, cfg)
    cache.save()
    cards = [{"id": r["id"], "evidence": evidence(r), "context": context(r, cache)} for r in recs]
    (data / "dataset" / "trust_cards.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards), encoding="utf-8")
    print(f"  {len(cards)} trust cards, {sum(1 for c in cards for x in c['context'] if x.get('hls'))} HLS links,"
          f" {sum(1 for c in cards for x in c['context'] if x.get('wikipedia'))} Wikipedia links")
