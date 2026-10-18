"""Access to the Archive database of the Swiss Federal Archives through LINDAS.

The opendata.swiss dataset "Archive database of the Swiss Federal Archives" points to
LINDAS (https://culture.ld.admin.ch/.well-known/dataset/ais) for the current database.
We use its public SPARQL endpoint only as a transport for the ORIGINAL archive-database
fields (see 01-ReadMe.xlsx of the dump): tbs_vrzng_enht (ID, level, reference code, title,
BGN_DT/END_DT/ZT_RAUM_TXT), tbs_gsft_obj_bzhng_hrch (hierarchy), tbs_gsft_obj_dtl (detail
data elements) and tbs_ablfr (accession number/title).
Anything LINDAS adds on top (ISIL holder links, Wikimedia Commons instantiations, the
access-rule vocabulary, dates attached to accession events) is deliberately ignored.
"""
import json
import random
import re
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://lindas.admin.ch/query"
AIS = "https://culture.ld.admin.ch/ais/"
RICO = "https://www.ica.org/standards/RiC/ontology#"
SLD = "https://schema.ld.admin.ch/"
PREFIXES = f"PREFIX rico: <{RICO}>\nPREFIX sld: <{SLD}>\n"
STOCK_TYPE = AIS + "vocabularies/recordSetTypes/10003"
AV_REGEX = "video|film|ton|audio|kino"
IMAGE_REGEX = "foto|photo|glasplatte|dia|abzug|negativ|bild|plakat|zeichnung|karte|plan"


def sparql(query: str, timeout: int = 300, retries: int = 3) -> list[dict]:
    data = urllib.parse.urlencode({"query": PREFIXES + query}).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={
        "Accept": "application/sparql-results+json", "User-Agent": "CORA-Apertus/0.1"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                res = json.load(r)
            return [{k: v["value"] for k, v in b.items()} for b in res["results"]["bindings"]]
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    return []


def _ids(where: str, page: int = 100_000) -> set[str]:
    out, offset = set(), 0
    while True:
        rows = sparql(f"SELECT DISTINCT ?s WHERE {{ {where} }} ORDER BY ?s LIMIT {page} OFFSET {offset}")
        out.update(r["s"].rsplit("/", 1)[1] for r in rows)
        if len(rows) < page:
            return out
        offset += page


def sample_ids(size: int, seed: int, strategy: str, strata: dict) -> list[dict]:
    """Return [{id, stratum}] drawn reproducibly (sorted population + seeded RNG)."""
    everything = _ids("?s a rico:Record")
    rng = random.Random(seed)
    if strategy == "uniform":
        return [{"id": i, "stratum": "uniform"} for i in rng.sample(sorted(everything), size)], {"all_records": len(everything)}
    av = _ids(f'?s a rico:Record ; sld:form ?f FILTER(REGEX(?f, "{AV_REGEX}", "i"))')
    images = _ids(f'?s a rico:Record ; sld:form ?f FILTER(REGEX(?f, "{IMAGE_REGEX}", "i"))') - av
    other = everything - av - images
    pools = {"audiovisual": av, "still_image": images, "other": other}
    picked = []
    for name, n in strata.items():
        picked += [{"id": i, "stratum": name} for i in rng.sample(sorted(pools[name]), n)]
    stats = {k: len(v) for k, v in pools.items()} | {"all_records": len(everything)}
    return picked, stats


_IRI = re.compile(r'^https?://[^\s<>"{}|\^`]+$')


def _values(uris) -> str:
    return " ".join(f"<{u}>" for u in uris if _IRI.match(u))


def _props(uris: list[str]) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for i in range(0, len(uris), 80):
        chunk = uris[i:i + 80]
        rows = sparql(f"SELECT ?s ?p ?o (LANG(?o) AS ?l) WHERE {{ VALUES ?s {{ {_values(chunk)} }} ?s ?p ?o }}")
        for r in rows:
            p = r["p"].replace(RICO, "rico:").replace(SLD, "sld:")
            val = r["o"] if not r.get("l") else f'{r["o"]}@{r["l"]}'
            out.setdefault(r["s"], {}).setdefault(p, []).append(val)
    return out


def _name(props: dict, lang: str = "en") -> str | None:
    names = props.get("rico:name", [])
    for n in names:
        if n.endswith("@" + lang):
            return n.rsplit("@", 1)[0]
    return names[0].rsplit("@", 1)[0] if names else None


def _clean(v: str | None) -> str | None:
    return v.strip().strip('"').strip() if v else v


def fetch_records(ids: list[str]) -> list[dict]:
    """Fetch each record with its date, accession, access rule, hierarchy and digital copies."""
    uris = [AIS + i for i in ids]
    base = _props(uris)

    linked = set()
    for p in base.values():
        for key in ("rico:isAssociatedWithDate", "rico:resultsOrResultedFrom"):
            linked.update(p.get(key, []))
    details = _props(sorted(linked))

    # Ancestors: every RecordSet above the record, with its own parent to rebuild the chain.
    anc: dict[str, set[str]] = {}
    for i in range(0, len(uris), 40):
        rows = sparql(f"SELECT ?s ?a WHERE {{ VALUES ?s {{ {_values(uris[i:i + 40])} }} ?s rico:isOrWasIncludedIn+ ?a }}")
        for r in rows:
            anc.setdefault(r["s"], set()).add(r["a"])
    anc_props = _props(sorted(set().union(*anc.values())) if anc else [])
    type_uris = sorted({t for p in anc_props.values() for t in p.get("rico:hasRecordSetType", [])})
    type_names = {u: _name(p) for u, p in _props(type_uris).items()}

    records = []
    for uri in uris:
        p = base.get(uri)
        if not p:
            continue
        first = lambda k: _clean(p.get(k, [None])[0])
        date = details.get(first("rico:isAssociatedWithDate") or "", {})
        accessions = []
        for ev in p.get("rico:resultsOrResultedFrom", []):
            e = details.get(ev, {})
            accessions.append({
                "uri": ev,
                "number": _clean(e.get("rico:name", [None])[0]),
                "title": _clean(e.get("rico:title", [None])[0]),
            })

        # Rebuild hierarchy chain from the direct parent upwards.
        chain, cur, seen = [], first("rico:isOrWasIncludedIn"), set()
        while cur and cur not in seen and cur in anc_props:
            seen.add(cur)
            ap = anc_props[cur]
            chain.append({
                "uri": cur,
                "title": _clean(ap.get("rico:title", [None])[0]),
                "level": type_names.get(ap.get("rico:hasRecordSetType", [""])[0]),
                "reference_code": _clean(ap.get("sld:referenceCode", [None])[0]),
            })
            cur = _clean(ap.get("rico:isOrWasIncludedIn", [None])[0])

        records.append({
            "id": uri.rsplit("/", 1)[1],
            "uri": uri,
            "portal_url": f"https://www.recherche.bar.admin.ch/recherche/#/de/archiv/einheit/{uri.rsplit('/', 1)[1]}",
            "title": first("rico:title"),
            "reference_code": first("sld:referenceCode"),
            "reference_number": first("sld:referenceNumber"),
            "old_reference_code": first("sld:oldReferenceCode"),
            "alternate_reference": first("sld:alternateReference"),
            "scope_and_content": first("rico:scopeAndContent"),
            "author": first("sld:author"),
            "publisher": first("sld:publisher"),
            "involved": first("sld:involve"),
            "coverage": first("sld:coverture"),
            "form": first("sld:form"),
            "format": first("sld:format"),
            "thema": first("sld:thema"),
            "country": first("sld:country"),
            "date": {
                "from": _clean(date.get("rico:beginningDate", [None])[0]),
                "to": _clean(date.get("rico:endDate", [None])[0]),
                "expressed": _clean(date.get("rico:expressedDate", [None])[0]),
            },
            "accessions": accessions,
            "hierarchy": chain,
        })
    return records
