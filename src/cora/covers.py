"""Cover photos for the browse view: a historical photograph of the record's place or subject, of its time.

The archive database holds descriptions, not scans, so a record has no picture of its own. This picks a
PERIOD PHOTO of what the record is about, from Wikimedia Commons, under one rule: the photo was taken in the
record's year or up to MAX_GAP years later, never before (a 1910 street must not illustrate a 1950 file).
A photo without a year is never used. Candidates, best first:
  1. ETH Library image archive (E-Pics, on Commons) near a place of the record (5, 15, 40 km) or by its name
  2. any open-licensed Commons photo near that place, dated by the camera / original date
  3. Commons photos found by the record's subjects (as Apertus wrote them), dated the same way
Among them the photo closest in time wins (by decade), then the better source, then the nearer one.
Every cover keeps the Commons file page, author, licence and year, and the front end labels it as an
illustration, never as the document itself. Records with no dated photo keep the typed cover.
Output: data/covers.json
"""
import json
import re
from pathlib import Path

from . import store
from .photos import OPEN, _get, _km, _plain

MAX_GAP = 20
PLACE_ROLES = ("depicted", "created", "published")
YEAR = re.compile(r"(?<!\d)(18[3-9]\d|19\d\d|20[0-2]\d)(?!\d)")


def record_year(rec: dict) -> int | None:
    m = rec["metadata"]
    years = [int(x) for x in re.findall(r"\d{4}", m.get("content_date") or m.get("date_created") or "")]
    return min(years) if years else None


def _photo_year(meta: dict, title: str, eth: bool) -> int | None:
    """The year the photo was taken. ETH titles and descriptions carry it reliably; for other files only the
    original/camera date counts (their titles often name the subject's year, not the photo's)."""
    v = lambda k: _plain((meta.get(k) or {}).get("value"))
    m = YEAR.search(v("DateTimeOriginal"))
    if m:
        return int(m.group(1))
    if eth:
        m = YEAR.search(title) or YEAR.search(v("ImageDescription"))
        return int(m.group(1)) if m else None
    return None


def _search(query: str, ua: str, cache: Path, n: int = 30) -> list[str]:
    d = _get({"action": "query", "list": "search", "srnamespace": 6, "srlimit": n, "srsearch": query}, ua, cache)
    return [h["title"] for h in d.get("query", {}).get("search", [])
            if re.search(r"\.(jpe?g|png|tiff?)$", h["title"], re.I)]


def _info(titles: list[str], ua: str, cache: Path) -> dict[str, dict]:
    out = {}
    for i in range(0, len(titles), 20):  # longer title lists overflow the URL (HTTP 414)
        d = _get({"action": "query", "titles": "|".join(titles[i:i + 20]), "prop": "imageinfo|coordinates",
                  "iiprop": "url|extmetadata", "iiurlwidth": 400}, ua, cache)
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            if ii:
                out[p["title"]] = {"ii": ii, "coord": (p.get("coordinates") or [{}])[0]}
    return out


def candidates(rec: dict, ua: str, cache: Path) -> list[dict]:
    """(title, how found, tier, place) for one record; `place` is (name, lat, lon) or None."""
    found, seen = [], set()

    def add(titles, how, tier, place=None, label=None):
        for t in titles:
            if t not in seen:
                seen.add(t)
                found.append({"title": t, "how": how, "tier": tier, "place": place, "label": label or (place or ("",))[0]})

    places = [p for role in PLACE_ROLES for p in rec["entities"]["places"]
              if p.get("role") == role and p.get("lat") is not None]
    for p in places[:2]:
        at = (p["name"], p["lat"], p["lon"])
        add(_search(f'"ETH-Bibliothek" "{p["name"]}"', ua, cache, 20), f"ETH photo of {p['name']}", 0, at)
        for km in (5, 15, 40):
            add(_search(f'"ETH-Bibliothek" nearcoord:{km}km,{p["lat"]:.4f},{p["lon"]:.4f}', ua, cache, 30),
                f"ETH photo near {p['name']}", 0, at)
        add(_search(f'filetype:bitmap nearcoord:10km,{p["lat"]:.4f},{p["lon"]:.4f}', ua, cache, 40),
            f"photo near {p['name']}", 1, at)
    year = record_year(rec)
    for s in (rec["metadata"].get("subjects") or [])[:3]:
        add(_search(f'filetype:bitmap "{s}" {year}', ua, cache, 20), f"photo of “{s}”", 2, label=s)
        add(_search(f'filetype:bitmap "{s}"', ua, cache, 30), f"photo of “{s}”", 2, label=s)
    return found


def pick(rec: dict, ua: str, cache: Path) -> dict | None:
    year = record_year(rec)
    if year is None or year + MAX_GAP < 1839:  # no photograph can be of its time
        return None
    cands = candidates(rec, ua, cache)
    info = _info([c["title"] for c in cands], ua, cache)
    best = None
    for c in cands:
        x = info.get(c["title"])
        if not x:
            continue
        meta = x["ii"].get("extmetadata") or {}
        lic = _plain((meta.get("LicenseShortName") or {}).get("value"))
        if not OPEN.match(lic or ""):
            continue
        eth = "ETH-Bibliothek" in c["title"] or "ETH-Bibliothek" in _plain((meta.get("Credit") or {}).get("value")) \
            or "ETH-Bibliothek" in _plain((meta.get("Artist") or {}).get("value"))
        if not c["place"]:  # found by a subject: the file itself must name it (full-text hits can be anything)
            about = (c["title"] + " " + _plain((meta.get("ImageDescription") or {}).get("value"))).lower()
            if c["label"].lower() not in about:
                continue
        py = _photo_year(meta, c["title"], eth)
        if py is None or not year <= py <= year + MAX_GAP:  # same time or shortly after, never before
            continue
        dist = None
        if c["place"]:
            co = x["coord"]
            dist = round(_km(c["place"][1:], (co["lat"], co["lon"])), 1) if co.get("lat") is not None else None
            if dist is not None and dist > 60:
                continue
        key = ((py - year) // 10, c["tier"] if eth or c["tier"] else 1, dist if dist is not None else 99)
        if best is None or key < best[0]:
            best = (key, {"kind": "place" if c["place"] else "subject", "label": c["label"],
                          "found_by": c["how"], "year": py, "record_year": year, "file": c["title"][5:],
                          "thumb": x["ii"].get("thumburl") or x["ii"]["url"], "page": x["ii"].get("descriptionurl"),
                          "author": _plain((meta.get("Artist") or {}).get("value"))[:120] or None, "license": lic,
                          "credit": "ETH-Bibliothek Zürich, Bildarchiv" if eth else None, "distance_km": dist})
    return best[1] if best else None


def run(cfg):
    data_dir, ua = cfg["paths"]["data_dir"], cfg["enrich"]["user_agent"]
    cache = data_dir / "covers_cache"
    cache.mkdir(parents=True, exist_ok=True)
    recs = store.read_entries(data_dir / "dataset" / "cora_dataset.jsonl")
    covers = {}
    for i, r in enumerate(recs, 1):
        try:
            c = pick(r, ua, cache)
        except Exception as e:  # one failing look-up must not stop the run; the record keeps the typed cover
            print(f"  {r['id']}: {e}")
            c = None
        if c:
            covers[r["id"]] = c
        if i % 25 == 0:
            print(f"  {i}/{len(recs)} records, {len(covers)} period photos", flush=True)
    (data_dir / "covers.json").write_text(json.dumps(covers, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {k: sum(1 for c in covers.values() if c["kind"] == k) for k in ("place", "subject")}
    print(f"  period photos for {len(covers)}/{len(recs)} records {kinds}; wrote data/covers.json")
