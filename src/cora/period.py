"""Period sources of the Oral tradition page for 1800-1950 (beyond the Stapfer survey of 1799).

C#  Federal population census by municipality, 1850-2000 (Federal Statistical Office, "Bevölkerungsentwicklung nach
    institutionellen Gliederungen, 1850-2000", PX file, open use with source; data/oral/bfs_population_1850_2000.px)
G#  Federal Gazette and other official publications (Swiss Federal Archives, amtsdruckschriften.bar.admin.ch):
    documents naming the family or the place within 15 years of the story, with the passage that names them
    (the site serves the full OCR text of each document). Results and passages are cached on disk.
Newspapers (e-newspaperarchives.ch) sit behind a bot check: they are offered as search links, not as sources.
"""
import hashlib
import html
import http.cookiejar
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ADS = "https://www.amtsdruckschriften.bar.admin.ch"
ADS_LANG = {"de": "DE", "fr": "FR", "it": "IT", "rm": "DE"}


def _fold(s) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()).strip()


# --- Census -------------------------------------------------------------------------------------------------
_CENSUS: dict | None = None


def _census(data_dir: Path) -> dict:
    """{folded municipality name: {"name", "bfs", "series": {year: population}}} from the BFS PX file."""
    global _CENSUS
    if _CENSUS is None:
        px = (data_dir / "oral" / "bfs_population_1850_2000.px").read_bytes().decode("latin-1")
        years = [int(y) for y in re.findall(r'"(\d{4})"', re.search(r'VALUES\("Jahr"\)=(.*?);', px, re.S).group(1))]
        regions = re.findall(r'"([^"]*)"', re.search(r'VALUES\("Kanton[^"]*"\)=(.*?);', px, re.S).group(1))
        nums = re.findall(r"-?\d+|\"\.+\"|\.\.", px.split("DATA=", 1)[1])
        _CENSUS = {}
        for i, reg in enumerate(regions):
            m = re.match(r"\.{6}(\d+)\s+(.*)", reg)
            if not m:
                continue
            row = nums[i * len(years):(i + 1) * len(years)]
            series = {y: int(v) for y, v in zip(years, row) if re.fullmatch(r"-?\d+", v) and int(v) > 0}
            _CENSUS.setdefault(_fold(m.group(2)), {"name": m.group(2), "bfs": m.group(1), "series": series})
    return _CENSUS


def census_lines(data_dir: Path, municipality: str, year: int) -> list[str]:
    c = _census(data_dir).get(_fold(municipality))
    if not c or not c["series"]:
        return []
    ys = sorted(c["series"])
    near = [y for y in ys if y <= max(year, ys[0])][-1:] + [y for y in ys if y > year][:1]
    first, s = ys[0], c["series"]
    lines = [f'{c["name"]} (municipality no. {c["bfs"]}) had {s[y]:,} inhabitants at the federal census of {y}.'.replace(",", "'") for y in near]
    if year >= 1860 and near and near[0] != first:
        ch = round(100 * (s[near[0]] - s[first]) / s[first])
        lines.append(f'Between the census of {first} and that of {near[0]}, the population of {c["name"]} {"grew" if ch >= 0 else "fell"} by {abs(ch)}%.')
    return lines


# --- Federal Gazette ------------------------------------------------------------------------------------------
class _Ads:
    """Small client for the official publications site (session cookie holds the language)."""

    def __init__(self, ua: str, lang: str, cache_dir: Path):
        self.ua, self.lang, self.cache = ua, ADS_LANG.get(lang, "DE"), cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.ready = False

    def _get(self, path: str, timeout: int = 90, cache: bool = True) -> str:
        """Documents are cached; searches are not, because the site serves a document only to the session
        whose search listed it."""
        key = self.cache / (hashlib.sha1(f"{self.lang}|{path}".encode()).hexdigest()[:20] + ".html")
        if cache and key.exists():
            return key.read_text(encoding="utf-8")
        if not self.ready:
            self.op.open(urllib.request.Request(f"{ADS}/setLanguage.do?lang={self.lang}&currWebPage=searchHome", headers={"User-Agent": self.ua}), timeout=timeout).read()
            self.ready = True
        time.sleep(1.0)
        with self.op.open(urllib.request.Request(f"{ADS}/{path}", headers={"User-Agent": self.ua}), timeout=timeout) as r:
            text = r.read().decode("utf-8", "replace")
        if cache and len(text) > 40000:  # error pages are short: never cache them
            key.write_text(text, encoding="utf-8")
        return text

    def search(self, query: str, y0: int, y1: int) -> list[dict]:
        s = self._get("execQuery.do?" + urllib.parse.urlencode({"context": "home", "searchMode": "simple", "queryString": query,
                                                              "daterange_from": f"01.01.{y0}", "daterange_to": f"31.12.{y1}"}), cache=False)
        out = []
        for m in re.finditer(r'<tr class="docsRow">(.*?)</tr>', s, re.S):
            i = re.search(r"detailView\.do\?id=(\d+)", m.group(1))
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
            # columns vary with the site language: title, [series], year, volume, first page, last page, ...
            y = next((k for k in (1, 2) if k < len(cells) and re.fullmatch(r"\d{4}", cells[k])), None)
            if i and y:
                out.append({"id": i.group(1), "title": cells[0], "series": cells[1] if y == 2 else None, "year": int(cells[y]),
                            "volume": cells[y + 1] if len(cells) > y + 1 else None, "page": cells[y + 2] if len(cells) > y + 2 else None,
                            "url": f"{ADS}/detailView.do?id={i.group(1)}", "pdf": f"{ADS}/viewOrigDoc/{i.group(1)}.pdf?ID={i.group(1)}"})
        return out

    def passage(self, doc_id: str, terms: list[str], width: int = 260) -> str | None:
        s = self._get(f"detailView.do?id={doc_id}")
        t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))
        for term in terms:
            m = re.search(re.escape(term), t, re.I)
            if m:
                a = max(0, m.start() - width // 2)
                return ("…" if a else "") + t[a:m.end() + width // 2].strip() + "…"
        return None


def gazette(ua: str, cache_dir: Path, surname: str, place: str, year: int, lang: str, limit: int = 5) -> list[dict]:
    """Official publications naming the family (first) or the place within 15 years of `year` (1849-1950)."""
    if year < 1835:
        return []
    y0, y1 = max(1849, year - 15), min(1965, year + 15)
    ads = _Ads(ua, lang, cache_dir)
    found, seen = [], set()
    for query, why, need in ((f"{surname} {place}", "family name and place", [surname]), (surname, "family name", [surname]), (place, "place", [place])):
        try:
            rows = ads.search(query, y0, y1)
        except Exception:
            continue
        # documents whose title names the term first (a pardon request, a naturalisation), then by closeness in time
        rows.sort(key=lambda r: (not any(_fold(n) in _fold(r["title"]) for n in need), abs(r["year"] - year)))
        for r in rows[:6]:
            if r["id"] in seen or len(found) >= limit:
                continue
            try:
                text = ads.passage(r["id"], need)  # the passage must name what the document was found for
            except Exception:
                text = None
            if not text:
                continue
            seen.add(r["id"])
            found.append(r | {"why": why, "passage": text})
        if len(found) >= limit:
            break
    return found


def newspaper_links(place: str, year: int) -> list[dict]:
    """Search links into the Swiss National Library's newspaper archive (opened by the reader, not fetched)."""
    q = urllib.parse.quote_plus(place)
    base = "https://www.e-newspaperarchives.ch/?a=q&hs=1&r=1&results=1&txq="
    return [{"label": f"Newspapers mentioning {place}, {y0}–{y1}", "url": f"{base}{q}&dafyq={y0}&datyq={y1}&e=-------de-20--1--img-txIN--------0-----"}
            for y0, y1 in ((year - 2, year + 2), (year - 10, year + 10))]


def map_layer(year: int, data_dir_site: Path) -> dict:
    """The swisstopo base map that matches the story year: the Dufour map before 1844, else the
    'Journey through time' sheet of the nearest earlier year."""
    years = json.loads((data_dir_site / "assets" / "zeitreihen_years.json").read_text(encoding="utf-8"))["years"]
    if year < years[0]:
        return {"layer": "ch.swisstopo.hiks-dufour", "time": "current", "label": "Dufour map (1845–1865), the oldest national map", "year": None}
    y = max(v for v in years if v <= year)
    return {"layer": "ch.swisstopo.zeitreihen", "time": f"{y}1231", "label": f"swisstopo 'Journey through time', map of {y}", "year": y}
