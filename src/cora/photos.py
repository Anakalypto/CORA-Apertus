"""Photos of the ETH Library image archive (E-Pics) near a place, for the Oral tradition page.

The ETH Library publishes its image archive on Wikimedia Commons ("Media contributed by the ETH-Bibliothek",
listed by the ETH Library on opendata.swiss); Commons can be searched by coordinates without an API key.
Candidates: files whose page names the ETH-Bibliothek, near the coordinates (5, 15, 40 km), then by place name.
Only open licences are kept (public domain, CC0, CC BY, CC BY-SA). Every response is cached on disk and
requests are throttled, because Commons rate-limits bursts (HTTP 429).
"""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
OPEN = re.compile(r"^(public domain|pd\b|cc0|cc by(-sa)?\b)", re.I)
_last = [0.0]


def _get(params: dict, ua: str, cache_dir: Path) -> dict:
    params = params | {"format": "json", "formatversion": 2}
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        time.sleep(max(0.0, 1.0 - (time.time() - _last[0])))  # at most one request per second
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=60) as r:
                d = json.load(r)
            path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            return d
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    return {}


def _plain(html: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()


def _year(*texts) -> int | None:
    for t in texts:
        m = re.search(r"(?<!\d)(18[3-9]\d|19\d\d|20[0-2]\d)(?!\d)", t or "")
        if m:
            return int(m.group(1))
    return None


def _km(a, b) -> float:
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# German keywords of the ETH photo titles for what a story stop is about (activity/season words, English or German).
THEMES = [(r"school|lesson|teacher|schul", "Schulhaus"), (r"market|sell|trade|markt", "Markt"),
          (r"cheese|dairy|milk|butter|k[äa]se|alp", "Käserei"), (r"alp|pasture|cattle|cow|herd", "Alp"),
          (r"hay|harvest|field|farm|plough|grain|ernte|bauer", "Bauernhaus"), (r"church|sermon|pray|kirch", "Kirche"),
          (r"weav|spin|loom|linen|weber", "Weberei"), (r"mill|grind|mühle", "Mühle"), (r"wood|forest|timber|wald", "Wald"),
          (r"river|bridge|ferry|brücke", "Brücke"), (r"pass|mule|road|journey|travel|saum", "Passstrasse")]


def themes_for(text: str) -> list[str]:
    t = (text or "").lower()
    out = [kw for rx, kw in THEMES if re.search(rx, t)]
    return (out + ["Dorf", "Bauernhaus"])[:3]


def near(lat: float, lon: float, place: str, ua: str, cache_dir: Path, want: int = 12, about: str = "",
         also: list[tuple[str, float, float]] = (), year: int | None = None) -> list[dict]:
    """Open-licensed ETH Library photos for a story stop: the place by name first (then nearby places by name,
    `also`, when the stop's own name finds little), photos near the coordinates on the stop's themes (school,
    market, dairy...), then any photo near the coordinates. Photos found by a name are located at that place."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    titles, how, named = [], {}, {}

    def run(query, label, n=20, at=None):
        d = _get({"action": "query", "list": "search", "srnamespace": 6, "srlimit": n, "srsearch": query}, ua, cache_dir)
        k = 0
        for h in d.get("query", {}).get("search", []):
            if h["title"] not in how:
                titles.append(h["title"]); how[h["title"]] = label; k += 1
                if at:
                    named[h["title"]] = at
        return k

    got = run(f'"ETH-Bibliothek" "{place}"', "place name", 10, (place, lat, lon)) if place else 0
    for name, plat, plon in also:
        if got >= want // 2:
            break
        if name and name != place:
            got += run(f'"ETH-Bibliothek" "{name}"', f"place name: {name}", 10, (name, plat, plon))
    for kw in themes_for(about):
        run(f'"ETH-Bibliothek" {kw} nearcoord:40km,{lat:.4f},{lon:.4f}', f"theme: {kw}", 8)
    for km in (5, 15, 40):
        if len(titles) >= 2 * want:
            break
        run(f'"ETH-Bibliothek" nearcoord:{km}km,{lat:.4f},{lon:.4f}', "coordinates", 15)
    titles = titles[:40]
    out = []
    for i in range(0, len(titles), 20):
        d = _get({"action": "query", "titles": "|".join(titles[i:i + 20]), "prop": "imageinfo|coordinates",
                  "iiprop": "url|extmetadata", "iiurlwidth": 480}, ua, cache_dir)
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            m = ii.get("extmetadata") or {}
            v = lambda k: (m.get(k) or {}).get("value")
            lic = _plain(v("LicenseShortName"))
            if not OPEN.match(lic or ""):
                continue
            desc = _plain(v("ImageDescription"))[:400]
            co = (p.get("coordinates") or [{}])[0]
            plat, plon = co.get("lat"), co.get("lon")
            if plat is None and p["title"] in named:  # located by the place name it was found with
                plat, plon = named[p["title"]][1:]
            dist = round(_km((lat, lon), (plat, plon)), 1) if plat is not None else None
            out.append({"id": str(p.get("pageid")), "title": p["title"][5:].rsplit(".", 1)[0], "description": desc,
                        "year": _year(_plain(v("DateTimeOriginal")), p["title"], desc),
                        "artist": _plain(v("Artist"))[:120] or None, "license": lic, "credit": "ETH-Bibliothek Zürich, Bildarchiv",
                        "thumb": ii.get("thumburl"), "page": ii.get("descriptionurl"),
                        "lat": plat, "lon": plon, "distance_km": dist, "found_by": how.get(p["title"], "coordinates")})
    rank = lambda c: (0 if c["found_by"] == "place name" else 1 if c["found_by"].startswith("place name") else
                      2 if c["found_by"].startswith("theme") else 3,
                      abs((c["year"] or 3000) - year) // 10 if year else 0,  # closest decade to the story first
                      c["distance_km"] if c["distance_km"] is not None else 99, c["year"] or 3000)
    out.sort(key=rank)
    return out[:want]
