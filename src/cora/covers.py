"""Cover illustrations for the browse view, from Wikimedia Commons.

The archive database holds descriptions, not scans, so a record has no picture of its own.
This picks an ILLUSTRATION of what the record is about, from entities already linked in
enrich.py, in this order:
  1. a person named in the record (Wikidata P18 image; only links that passed the life-date check)
  2. a place the record depicts or was made in (OpenStreetMap -> Wikidata P18)
  3. an organization involved (Wikidata P18 image or P154 logo)
Every cover keeps the Commons file page, author and licence, and the front end labels it as an
illustration, never as the document itself. Output: data/covers.json
"""
import json
import re
import time
import urllib.parse

from .enrich import _get

WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OSM_TYPE = {"relation": "R", "way": "W", "node": "N"}
PLACE_ROLES = ("depicted", "created", "published")


def _chunks(xs, n):
    xs = list(xs)
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _strip_html(s: str | None) -> str | None:
    return re.sub(r"<[^>]+>", "", s).strip() if s else s


def wikidata_images(qids, ua) -> dict[str, str]:
    """QID -> Commons file name (P18 image, else P154 logo)."""
    out = {}
    for chunk in _chunks(sorted(set(qids)), 50):
        res = _get(WD_API + "?" + urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": "|".join(chunk), "props": "claims", "format": "json"}), ua)
        for qid, ent in res.get("entities", {}).items():
            for prop in ("P18", "P154"):
                claims = ent.get("claims", {}).get(prop)
                if claims:
                    out[qid] = claims[0]["mainsnak"]["datavalue"]["value"]
                    break
        time.sleep(0.5)
    return out


def osm_wikidata(osm_urls, ua) -> dict[str, str]:
    """OpenStreetMap object URL -> Wikidata QID, via the Nominatim lookup (50 per request, 1 req/s)."""
    ids = {}
    for u in set(osm_urls):
        m = re.search(r"openstreetmap\.org/(relation|way|node)/(\d+)", u or "")
        if m:
            ids[OSM_TYPE[m.group(1)] + m.group(2)] = u
    out = {}
    for chunk in _chunks(ids, 50):
        res = _get("https://nominatim.openstreetmap.org/lookup?" + urllib.parse.urlencode(
            {"osm_ids": ",".join(chunk), "extratags": 1, "format": "json"}), ua)
        for hit in res:
            key = OSM_TYPE.get(hit.get("osm_type"), "?") + str(hit.get("osm_id"))
            qid = (hit.get("extratags") or {}).get("wikidata")
            if qid and key in ids:
                out[ids[key]] = qid
        time.sleep(1.1)
    return out


def commons_meta(files, ua) -> dict[str, dict]:
    """Commons file name -> thumbnail URL, file page, author, licence."""
    out = {}
    for chunk in _chunks(sorted(set(files)), 50):
        res = _get(COMMONS_API + "?" + urllib.parse.urlencode({
            "action": "query", "titles": "|".join("File:" + f for f in chunk), "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": 400, "format": "json"}), ua)
        norm = {n["to"]: n["from"] for n in res.get("query", {}).get("normalized", [])}
        for page in res.get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [None])[0]
            if not info:
                continue
            meta = info.get("extmetadata", {})
            name = norm.get(page["title"], page["title"]).removeprefix("File:")
            out[name] = {"thumb": info.get("thumburl") or info["url"], "page": info.get("descriptionurl"),
                         "author": _strip_html(meta.get("Artist", {}).get("value")),
                         "license": meta.get("LicenseShortName", {}).get("value")}
        time.sleep(0.5)
    return out


def _candidates(rec: dict, place_qid: dict) -> list[tuple[str, str, str]]:
    """(kind, label, qid) in order of preference."""
    e, out = rec["entities"], []
    for p in e["persons"]:
        wd = p.get("wikidata") or {}
        if wd.get("qid") and (p.get("life_date_check") or {}).get("verdict", "ok") == "ok":
            out.append(("person", p.get("display_name") or p["name"], wd["qid"]))
    for role in PLACE_ROLES:
        for p in e["places"]:
            if p.get("role") == role and place_qid.get(p.get("gazetteer")):
                out.append(("place", p["name"], place_qid[p["gazetteer"]]))
    for o in e["organizations"]:
        wd = o.get("wikidata") or {}
        if wd.get("qid"):
            out.append(("organization", o["name"], wd["qid"]))
    return out


def run(cfg):
    data_dir, ua = cfg["paths"]["data_dir"], cfg["enrich"]["user_agent"]
    recs = [json.loads(l) for l in (data_dir / "dataset" / "cora_dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    osm = [p.get("gazetteer") for r in recs for p in r["entities"]["places"] if p.get("role") in PLACE_ROLES]
    place_qid = osm_wikidata(osm, ua)
    print(f"  {len(place_qid)} places linked to Wikidata via OpenStreetMap")
    cands = {r["id"]: _candidates(r, place_qid) for r in recs}
    images = wikidata_images({q for cs in cands.values() for _, _, q in cs}, ua)
    print(f"  {len(images)} entities with a Commons image")
    meta = commons_meta(images.values(), ua)
    covers = {}
    for rid, cs in cands.items():
        for kind, label, qid in cs:
            f = images.get(qid)
            if f and f in meta:
                covers[rid] = {"kind": kind, "label": label, "qid": qid, "file": f, **meta[f]}
                break
    (data_dir / "covers.json").write_text(json.dumps(covers, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {k: sum(1 for c in covers.values() if c["kind"] == k) for k in ("person", "place", "organization")}
    print(f"  covers for {len(covers)}/{len(recs)} records {kinds}; wrote data/covers.json")
