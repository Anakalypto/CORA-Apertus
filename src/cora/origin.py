"""Places of origin beyond the Stapfer survey, and what they were in a given year.

Places: every current Swiss municipality, from the swisstopo search service (layer gg25, the official
municipal boundaries; BFS number, name, canton, centre coordinates). The 1799 Stapfer places stay first in
the suggestions because they carry the school survey; a municipality picked here gets the id "m<BFS number>".

Status: Apertus reads the sources below and says, for the chosen year, (1) whether the place already existed
(as a settlement; and whether the present municipality existed or was formed later, e.g. by a merger) and
(2) whether it was part of the Swiss Confederation then (full member canton, associate, subject territory,
part of the Helvetic Republic, or outside it, e.g. Geneva before 1815 or the Fricktal before 1802).
Sources it is given, numbered: [W1] the Wikipedia article on the municipality, [D1] its Wikidata inception /
dissolution dates, [K1] the curated history of its canton's membership (below, after the Historical
Dictionary of Switzerland). Apertus may only state what these say; otherwise it answers "uncertain".
"""
import json
import re
import time
import urllib.parse
from pathlib import Path

from . import topic
from .enrich import _get

SEARCH = "https://api3.geo.admin.ch/rest/services/api/SearchServer"
WD_API = "https://www.wikidata.org/w/api.php"
CANTONS = {"ZH": "Zürich", "BE": "Bern", "LU": "Luzern", "UR": "Uri", "SZ": "Schwyz", "OW": "Obwalden", "NW": "Nidwalden",
           "GL": "Glarus", "ZG": "Zug", "FR": "Fribourg", "SO": "Solothurn", "BS": "Basel-Stadt", "BL": "Basel-Landschaft",
           "SH": "Schaffhausen", "AR": "Appenzell Ausserrhoden", "AI": "Appenzell Innerrhoden", "SG": "St. Gallen",
           "GR": "Graubünden", "AG": "Aargau", "TG": "Thurgau", "TI": "Tessin", "VD": "Waadt", "VS": "Wallis",
           "NE": "Neuenburg", "GE": "Genf", "JU": "Jura"}
# The area of each present canton, by period (after the Historical Dictionary of Switzerland): what it was, as one of
# member | associate | subject territory | helvetic republic | outside. Parts of a canton may differ (e.g. the
# Fricktal of Aargau, the Jura of Bern): Apertus is told to prefer the place's own history in [W1] when it says more.
_OLD = [(1798, 1803, "helvetic republic", "a canton of the Helvetic Republic, which replaced the Confederation"),
        (1803, 9999, "member", "a member canton")]
TIMELINE = {
    "ZH": [(1351, 1798, "member", "a member of the Confederation since 1351")] + _OLD,
    "BE": [(1353, 1798, "member", "a member since 1353 (its Jura districts, Bernese only from 1815, were then in the Prince-Bishopric of Basel and French 1793/97-1813)")] + _OLD,
    "LU": [(1332, 1798, "member", "a member since 1332")] + _OLD,
    "UR": [(1291, 1798, "member", "a founding member (1291)")] + _OLD,
    "SZ": [(1291, 1798, "member", "a founding member (1291)")] + _OLD,
    "OW": [(1291, 1798, "member", "a founding member (Unterwalden, 1291)")] + _OLD,
    "NW": [(1291, 1798, "member", "a founding member (Unterwalden, 1291)")] + _OLD,
    "GL": [(1352, 1798, "member", "a member since 1352")] + _OLD,
    "ZG": [(1352, 1798, "member", "a member since 1352")] + _OLD,
    "FR": [(1481, 1798, "member", "a member since 1481")] + _OLD,
    "SO": [(1481, 1798, "member", "a member since 1481")] + _OLD,
    "BS": [(1501, 1798, "member", "a member since 1501 (Basel)")] + _OLD,
    "BL": [(1501, 1798, "member", "part of Basel, a member since 1501; its own half-canton only from 1833")] + _OLD,
    "SH": [(1501, 1798, "member", "a member since 1501")] + _OLD,
    "AR": [(1513, 1798, "member", "part of Appenzell, a member since 1513")] + _OLD,
    "AI": [(1513, 1798, "member", "part of Appenzell, a member since 1513")] + _OLD,
    "SG": [(1451, 1798, "associate", "the Prince-Abbey and the city of St. Gallen were associates (Zugewandte Orte); other parts were common lordships (subject territories)")] + _OLD,
    "GR": [(1497, 1798, "associate", "the Three Leagues (Drei Bünde), an associate of the Confederation, not a member"),
           (1798, 1799, "outside", "the Three Leagues, not yet part of the Helvetic Republic"),
           (1799, 1803, "helvetic republic", "the canton Rätien of the Helvetic Republic"), (1803, 9999, "member", "a member canton")],
    "AG": [(1415, 1798, "subject territory", "subject territories of Bern and common lordships of the Confederates (the Fricktal was Austrian until 1802)")] + _OLD,
    "TG": [(1460, 1798, "subject territory", "a common lordship (subject territory) of the Confederates")] + _OLD,
    "TI": [(1512, 1798, "subject territory", "subject territories (ennetbirgische Vogteien) of Uri and of the Confederates")] + _OLD,
    "VD": [(1536, 1798, "subject territory", "a subject territory of Bern")] + _OLD,
    "VS": [(1416, 1798, "associate", "an associate of the Confederation (Zugewandter Ort)"),
           (1798, 1802, "helvetic republic", "a canton of the Helvetic Republic"), (1802, 1810, "outside", "the independent Rhodanic Republic"),
           (1810, 1813, "outside", "the French département of Simplon"), (1813, 1815, "outside", "under Allied occupation, not yet a canton"),
           (1815, 9999, "member", "a member canton (since 1815)")],
    "NE": [(1406, 1798, "associate", "an associate of the Confederation (Zugewandter Ort) and a principality"),
           (1798, 1806, "outside", "a Prussian principality, outside the Helvetic Republic"),
           (1806, 1814, "outside", "a principality under Napoleon (Berthier)"),
           (1814, 1815, "outside", "a Prussian principality, not yet a canton"),
           (1815, 1848, "member", "a member canton (since 1815) and at the same time a Prussian principality"),
           (1848, 9999, "member", "a member canton (a republic since 1848)")],
    "GE": [(1526, 1798, "associate", "an independent republic and an associate of some cantons (Zugewandter Ort)"),
           (1798, 1813, "outside", "annexed by France (département du Léman)"),
           (1813, 1815, "outside", "an independent republic again, not yet a canton"),
           (1815, 9999, "member", "a member canton (since 1815)")],
    "JU": [(999, 1793, "outside", "the Prince-Bishopric of Basel (its southern parts associated with the Confederation)"),
           (1793, 1815, "outside", "annexed by France"), (1815, 1979, "member", "part of the canton of Bern"),
           (1979, 9999, "member", "the canton of Jura (since 1979)")],
}


def canton_status(code: str, year: int) -> tuple[str, str] | None:
    """(status, sentence) of the area of today's canton in that year, from TIMELINE; None before its first period."""
    for a, b, st, note in TIMELINE.get(code, []):
        if a <= year < b:
            return st, note
    return None


_MEM: dict[str, list] = {}


def _store(data_dir: Path) -> Path:
    return data_dir / "oral" / "municipalities.json"


def _load(data_dir: Path) -> dict:
    p = _store(data_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def search(data_dir: Path, q: str, n: int = 8) -> list[dict]:
    """Current Swiss municipalities matching q (swisstopo), remembered on disk so a chosen one can be found again."""
    key = q.strip().lower()
    if key in _MEM:
        return _MEM[key]
    try:
        d = _get(SEARCH + "?" + urllib.parse.urlencode({"type": "locations", "origins": "gg25", "limit": n, "sr": 4326, "searchText": q}),
                 "CORA/1.0 (hackathon demo)")
    except Exception:
        return []
    out = []
    for r in d.get("results", []):
        a = r.get("attrs") or {}
        m = re.match(r"(.+?)\s*\((\w\w)\)$", re.sub(r"<[^>]+>", "", a.get("label") or ""))
        if not m or not a.get("featureId"):
            continue
        out.append({"id": f"m{a['featureId']}", "bfs": int(a["featureId"]), "name": m.group(1), "canton_code": m.group(2),
                    "canton": CANTONS.get(m.group(2), m.group(2)), "municipality": m.group(1),
                    "lat": round(a["lat"], 5), "lon": round(a["lon"], 5)})
    if out:
        known = _load(data_dir)
        if any(p["id"] not in known for p in out):
            known.update({p["id"]: p for p in out})
            _store(data_dir).parent.mkdir(parents=True, exist_ok=True)
            _store(data_dir).write_text(json.dumps(known, ensure_ascii=False, indent=0), encoding="utf-8")
    _MEM[key] = out
    return out


def place(data_dir: Path, pid: str) -> dict:
    p = _load(data_dir).get(pid)
    if not p:
        raise KeyError(pid)
    return {**p, "schools": [], "category": "municipality", "canton_1799": None, "district_1799": None,
            "confession": None, "market": False, "population_1799": None, "today_only": True}


def _article(name: str, code: str | None, ua: str) -> dict | None:
    """The English Wikipedia article about this Swiss place: an exact title ("Glarus Nord", "Rüti, Zürich",
    "Bulle"), else a search hit whose title starts with the name; never a neighbouring place's article."""
    canton = CANTONS.get(code or "", "")
    for t in filter(None, [name, f"{name}, {canton}", f"{name} {code}" if code else None, f"{name}, Switzerland"]):
        try:
            wp = topic.wikipedia_page(t, ua)
        except Exception:
            wp = None
        ex = (wp or {}).get("extract") or ""
        if wp and "Switzerland" in ex and "may refer to" not in ex:
            return wp
    try:
        for c in topic.wikipedia_candidates(f"{name} {canton} Switzerland", ua, 5):
            if c["title"].split(",")[0].split(" (")[0] == name:
                wp = topic.wikipedia_page(c["title"], ua)
                if wp and "Switzerland" in (wp.get("extract") or ""):
                    return wp
    except Exception:
        pass
    return None


def _history_text(title: str, ua: str, limit: int = 3200) -> str | None:
    """What the article says about the place's past: its introduction, every sentence on a first mention, a
    foundation or a merger, then the start of its History section (the summary alone rarely dates anything)."""
    try:
        d = _get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "format": "json", "formatversion": 2}), ua)
        t = d["query"]["pages"][0].get("extract") or ""
    except Exception:
        return None
    if not t:
        return None
    intro = t.split("\n==", 1)[0].strip()
    key = [re.sub(r"\s*=+[^=]+=+\s*", " ", x).strip() for x in re.split(r"(?<=[.!?])\s+", t)
           if re.search(r"first (mentioned|recorded|attested)|founded|merg|incorporat|became part of|annex", x, re.I)][:8]
    m = re.search(r"\n==+\s*History\s*==+\n(.*?)(?=\n==[^=])", t, re.S)
    hist = re.sub(r"\n=+[^=\n]+=+\n", "\n", m.group(1)).strip() if m else ""
    out = "\n".join(filter(None, [intro[:900], " ".join(dict.fromkeys(key)), hist]))
    return re.sub(r"\n{2,}", "\n", out)[:limit]


def _wikidata_dates(title: str, ua: str) -> list[str]:
    """Inception / dissolution / 'replaces' of the Wikidata item of an English Wikipedia article."""
    d = _get(WD_API + "?" + urllib.parse.urlencode({"action": "wbgetentities", "sites": "enwiki", "titles": title,
                                                    "props": "claims", "format": "json"}), ua)
    lines = []
    for ent in (d.get("entities") or {}).values():
        c = ent.get("claims") or {}
        for prop, label in (("P571", "inception"), ("P576", "dissolved")):
            for cl in c.get(prop, [])[:2]:
                t = ((cl.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("time")
                if t:
                    lines.append(f"{label}: {t[1:5].lstrip('0')}")
        if c.get("P1365"):
            lines.append(f"replaces {len(c['P1365'])} earlier municipality item(s) (a merger)")
    return lines


SYSTEM = """You are a historian of Switzerland. For a place of origin and a year, you say from the numbered sources
whether the place existed then and whether it belonged to the Swiss Confederation then.
Rules:
- Distinguish the settlement (village, town) from the present political municipality: a municipality formed by
  a merger (e.g. in 2011) did not exist in 1850, but its villages usually did; say both.
- "existed" is "yes" if the settlement existed in that year, "no" if the sources say it was founded later,
  "uncertain" if the sources do not say. Most Swiss villages are medieval: say "yes" only when a source dates it
  (a first mention, a foundation) before the year, or calls it historic/medieval/old.
- "confederation": "member" (a full member canton, or part of one), "associate" (Zugewandter Ort), "subject
  territory" (ruled by Confederates), "helvetic republic" (1798-1803), "outside" (another state), "uncertain".
  Use [K1] for the canton and [W1] when it tells the place's own story (e.g. a district that changed hands).
- Name merged municipalities, dates of first mention or of foundation ONLY if a source states them; otherwise
  leave "founded" null and say the sources do not date it. Never add facts from memory.
- Take the confederation status from [K1] unless [W1] explicitly describes a different history for this very place.
- Cite every statement with the refs it relies on. Write the notes in {reader}, one or two sentences each.
Return one JSON object."""


def status(data_dir: Path, cfg: dict, ap, pid: str, year: int, lang: str = "en") -> dict:
    from . import ancestry, i18n
    cache = data_dir / "oral" / "status"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{pid}_{year}_{lang}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    p = place(data_dir, pid) if str(pid).startswith("m") else ancestry._place(data_dir, int(pid))
    code = p.get("canton_code") or next((k for k, v in CANTONS.items() if v == p.get("canton")), None)
    ua = cfg["enrich"]["user_agent"]
    src = []
    wp = _article(p["name"], code, ua) or (p.get("municipality") and p["municipality"] != p["name"] and _article(p["municipality"], code, ua))
    if wp and wp.get("extract"):
        src.append({"ref": "W1", "text": _history_text(wp["title"], ua) or wp["extract"][:1400], "label": f'Wikipedia · {wp["title"]}', "url": wp.get("url")})
        try:
            dates = _wikidata_dates(wp["title"], ua)
        except Exception:
            dates = []
        if dates:
            src.append({"ref": "D1", "text": "; ".join(dates), "label": f'Wikidata · {wp["title"]}', "url": None})
    cs = canton_status(code, year) if code else None
    src.append({"ref": "K1", "text": (f"In {year} the area of today's canton {CANTONS[code]} was {cs[1]} (status: {cs[0]})." if cs else
                                      f"In {year} the area of today's canton {CANTONS.get(code, '?')} was not yet linked to the Confederation (status: outside)."),
                "label": "Historical Dictionary of Switzerland · cantons", "url": "https://hls-dhs-dss.ch/"})
    if p.get("canton_1799"):
        src.append({"ref": "S1", "text": f'{p["name"]} is listed in the Stapfer school survey of 1799 (canton {p["canton_1799"]} of the Helvetic Republic).',
                    "label": "Stapfer-Enquête 1799", "url": "https://stapferenquete.ch/"})
    schema = {"existed": "yes|no|uncertain", "founded": "<year or period the settlement is first attested or founded, or null>",
              "existence_note": "<sentence>", "municipality_note": "<sentence on the present municipality: since when it exists as such>",
              "confederation": "member|associate|subject territory|helvetic republic|outside|uncertain",
              "confederation_note": "<sentence>", "sources": ["<W1|D1|K1|S1>"]}
    user = (f"Place: {p['name']} (municipality {p.get('municipality') or p['name']}, canton {CANTONS.get(code, p.get('canton') or '?')}), year {year}.\n\n"
            "Sources:\n" + "\n".join(f"[{s['ref']}] {s['text']}" for s in src) + "\n\nReturn:\n" + json.dumps(schema, ensure_ascii=False))
    t0 = time.time()
    raw, meta = ap.chat_json([{"role": "system", "content": SYSTEM.format(reader=i18n.language(lang))}, {"role": "user", "content": user}])
    allowed = {s["ref"] for s in src}
    pick = lambda v, opts: v if v in opts else "uncertain"
    out = {"place": p["name"], "year": year,
           "existed": pick(raw.get("existed"), {"yes", "no", "uncertain"}), "founded": raw.get("founded"),
           "existence_note": raw.get("existence_note"), "municipality_note": raw.get("municipality_note"),
           "confederation": pick(raw.get("confederation"), {"member", "associate", "subject territory", "helvetic republic", "outside", "uncertain"}),
           "confederation_note": raw.get("confederation_note"),
           "sources": src, "cited": sorted({str(r).strip("[] ") for r in raw.get("sources") or []} & allowed),
           "model": meta.get("model"), "seconds": round(time.time() - t0, 1)}
    # A place cannot be a full member when its whole canton area was not: "became part of the Confederation" in
    # an article often means a subject territory. Then the curated status of [K1] stands, and the note says so.
    if cs and out["confederation"] in ("member", "uncertain") and cs[0] != "member":
        out["confederation"] = cs[0]
        out["confederation_note"] = f"In {year} the area of today's canton {CANTONS[code]} was {cs[1]}."
        out["corrected"] = "confederation status taken from the cantons' history [K1]"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
