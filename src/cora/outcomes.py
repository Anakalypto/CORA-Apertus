"""Outcome of each federal consultation 1960–1991: did the project become law?

Evidence, in this order:
  1. the popular vote already matched in consultations.py (Swissvotes): accepted or rejected by the people;
  2. an act of the Official Compilation (AS/RO) in Fedlex (fedlex.data.admin.ch SPARQL endpoint, Federal Chancellery,
     open data) dated from the consultation year to 12 years later. Candidates come from title overlap weighted by
     rarity (so "Bundesgesetz" or "Änderung" count for little), and Apertus confirms a candidate as the same
     project with the same 0.99 bar as the vote matching. Weaker confirmations are shown as "possible".
No evidence is never read as failure: "not found" says what was searched. Only a rejected vote is "did not succeed".
Output: an "outcome" field added to data/consultations/consultations_tagged.json.
"""
import json
import math
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config
from .qa import tokens

ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"
JOLUX = "http://data.legilux.public.lu/resource/ontology/jolux#"
DEU = "http://publications.europa.eu/resource/authority/language/DEU"
WINDOW = 12  # years after the consultation in which the act is searched
NO_ACT_TYPES = {"Rest", "Umfrage", "unbekannt", ""}  # reports and surveys: no act is expected

MATCH_SYSTEM = """Decide whether a Swiss federal consultation procedure (Vernehmlassung) led to a given act of the
Official Compilation of federal law (same legislative project: the act the consultation prepared). Amendments of the
same law in other years are a different project. Answer only from the titles, types and dates.
Return one JSON object {"same_project": true|false, "confidence": 0-1, "reason": "<short>"}."""


def _sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={"Accept": "application/sparql-results+json",
                                                              "User-Agent": "CORA-Apertus/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return [{k: v["value"] for k, v in b.items()} for b in json.load(r)["results"]["bindings"]]


def fetch_acts(path, start: int = 1960, end: int = 2005) -> list[dict]:
    """Every act of the Official Compilation dated start..end with its German title (cached in `path`)."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    acts = {}
    for year in range(start, end + 1):  # one query per year: deep OFFSET pages make the endpoint fail
        rows = _sparql(f"""PREFIX jolux: <{JOLUX}>
SELECT DISTINCT ?act ?title ?date ?force ?as WHERE {{
  ?act a jolux:Act ; jolux:dateDocument ?date ; jolux:isRealizedBy ?e .
  ?e jolux:language <{DEU}> ; jolux:title ?title .
  OPTIONAL {{ ?act jolux:dateEntryInForce ?force }}
  OPTIONAL {{ ?act <http://cogni.internal.system/model#historicalId> ?as }}
  FILTER(?date >= "{year}-01-01"^^xsd:date && ?date <= "{year}-12-31"^^xsd:date)
}} LIMIT 20000""")
        for r in rows:
            acts.setdefault(r["act"], {"uri": r["act"], "title": r["title"], "date": r["date"],
                                       "in_force": r.get("force"), "as_ref": r.get("as")})
        print(f"  fedlex {year}: {len(acts)} acts")
    out = sorted(acts.values(), key=lambda a: a["date"])
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# Words that name the kind of act or the procedure, not the project: they would match thousands of titles.
GENERIC = {"bundesgesetz", "gesetz", "gesetze", "verordnung", "verordnungen", "bundesbeschluss", "bundesbeschlusses",
           "bundesratsbeschluss", "aenderung", "anderung", "änderung", "änderungen", "aenderungen", "revision",
           "teilrevision", "totalrevision", "entwurf", "vorentwurf", "botschaft", "bundesrat", "bundesrates",
           "schweizerischen", "eidgenossischen", "eidgenössischen", "betreffend", "ueber", "sowie"}
# The act must be of the consulted kind: a consultation on a federal act is not answered by an ordinance.
KIND = {  # matched at the start of the act's title ("Bundesgesetz über …", "Eisenbahngesetz (EBG), Änderung")
    "Bundesgesetz": r"^(\S+\s){0,2}\S*gesetz\b|^\S*gesetz\w*\s*\(",
    "Verordnung": r"^(\S+\s){0,1}\S*(verordnung|reglement)",
    "Bundesbeschluss": r"^bundesbeschluss",
    "Bundesratsbeschluss": r"^(bundesratsbeschluss|\S*verordnung)",
    "Teilrevision der Bundesverfassung": r"^(bundesbeschluss|bundesverfassung)",
    "Völkerrechtlicher Vertrag": r"^(\S+\s){0,3}\S*(abkommen|übereinkommen|vertrag|protokoll|konvention|vereinbarung|statut|charta)",
    "Konkordat": r"^(\S+\s){0,2}\S*(konkordat|vereinbarung)",
}


def _terms(text: str) -> set[str]:
    """Content words of a title, without endings, so 'Eisenbahngesetzes' carries 'eisenbahngesetz'."""
    out = set()
    for w in tokens(text):
        stem = re.sub(r"(es|en|er|s|n|e)$", "", w) if len(w) > 6 else w
        if len(w) < 5 or w in GENERIC or stem in GENERIC:
            continue
        out.add(stem)
    return out


class ActIndex:
    """Candidate acts by rarity-weighted term overlap; a term matches inside compounds ('Eisenbahn-Grossprojekte'
    meets 'Eisenbahngrossprojekte') but not as a loose prefix ('Eisenbahngesetz' never meets 'Eisenbahndepartement')."""

    def __init__(self, acts: list[dict]):
        self.acts = acts
        self.flat = [re.sub(r"[\s\-–]+", "", a["title"].lower()) for a in acts]
        self.df: dict[str, float] = {}

    def idf(self, term: str) -> float:
        if term not in self.df:
            n = sum(term in t for t in self.flat)
            self.df[term] = math.log((len(self.acts) + 1) / (n + 1))
        return self.df[term]

    def candidates(self, title: str, year: int, kind: str = "", k: int = 4, bar: float = 0.6) -> list[tuple[float, dict]]:
        q = _terms(title)
        weight = sum(self.idf(w) for w in q)
        if not q or not year or weight <= 0:
            return []
        want = re.compile(KIND[kind], re.I) if kind in KIND else None
        out = []
        for a, flat in zip(self.acts, self.flat):
            if not (year <= int(a["date"][:4]) <= year + WINDOW) or (want and not want.search(a["title"])):
                continue
            sim = sum(self.idf(w) for w in q if w in flat) / weight
            if sim >= bar:
                out.append((round(sim, 2), a))
        out.sort(key=lambda x: (-x[0], x[1]["date"]))
        return out[:k]


def _act(a: dict) -> dict:
    eli = a["uri"].split("/eli/", 1)[-1]
    return {"title": a["title"], "date": a["date"], "in_force": a.get("in_force"), "as_ref": a.get("as_ref"),
            "url": f"https://www.fedlex.admin.ch/eli/{eli}/de"}


def outcome_of(c: dict, act: dict | None, possible: dict | None) -> dict:
    vote = (c.get("chain") or [{}] * 4)[3]
    if c.get("match") and vote.get("detail"):
        ok = ": accepted" in vote["detail"]
        return {"status": "accepted_by_vote" if ok else "rejected_by_vote", "succeeded": ok,
                "label": ("Accepted by the people" if ok else "Did not succeed: rejected by the people") + f" ({vote['date']})",
                "detail": vote["detail"], "source": "Swissvotes", "url": vote.get("link")}
    if act:
        return {"status": "adopted", "succeeded": True,
                "label": f"Adopted: in the Official Compilation {act['date'][:4]}"
                         + (f", in force {act['in_force']}" if act.get("in_force") else ""),
                "act": act, "source": "Fedlex (Official Compilation)", "url": act["url"]}
    if c.get("type", "") in NO_ACT_TYPES:
        return {"status": "no_act_expected", "succeeded": None, "label": "Report or survey: no act expected",
                "possible_act": possible, "source": None}
    return {"status": "not_found", "succeeded": None,
            "label": f"No adopted act found ({c['year']}–{(c['year'] or 0) + WINDOW})",
            "detail": "Searched the Official Compilation (Fedlex) and the popular votes (Swissvotes). The project may "
                      "have been abandoned, merged into another act, or adopted under a title the matching missed.",
            "possible_act": possible, "source": None}


def run(cfg) -> None:
    from .apertus import Apertus
    out_dir = cfg["paths"]["data_dir"] / "consultations"
    path = out_dir / "consultations_tagged.json"
    cons = json.loads(path.read_text(encoding="utf-8"))
    index = ActIndex(fetch_acts(out_dir / "fedlex_acts.json"))
    l = cfg["llm"]
    ap = Apertus(l["base_url"], l["api_key"], config.model_for(cfg, "consultations"), 0.0, 400, l["retries"])
    cache_path = out_dir / "outcome_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    def check(c, a):
        key = f'{c["nr"]}|{a["uri"]}'
        if key not in cache:
            q = {"consultation": {"title": c["title"], "type": c["type"], "year": c["year"], "department": c["dept_abbr"]},
                 "act": {"title": a["title"], "date": a["date"]}}
            try:
                raw, _ = ap.chat_json([{"role": "system", "content": MATCH_SYSTEM},
                                       {"role": "user", "content": json.dumps(q, ensure_ascii=False)}])
                cache[key] = {"same": raw.get("same_project") is True, "confidence": float(raw.get("confidence") or 0),
                              "reason": raw.get("reason")}
            except Exception as e:
                cache[key] = {"same": False, "confidence": 0.0, "reason": None, "error": repr(e)}
        return cache[key]

    def one(c):
        if c.get("match"):  # already decided by the popular vote
            return None, None
        best = possible = None
        for sim, a in index.candidates(c["title"], c["year"], c["type"]):
            v = check(c, a)
            if v["same"] and v["confidence"] >= 0.99:
                best = _act(a) | {"title_similarity": sim, "confidence": v["confidence"], "reason": v["reason"]}
                break
            if v["same"] and not possible:
                possible = _act(a) | {"title_similarity": sim, "confidence": v["confidence"], "reason": v["reason"]}
        return best, possible

    with ThreadPoolExecutor(l["workers"]) as pool:
        found = list(pool.map(one, cons))
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    for c, (act, possible) in zip(cons, found):
        c["outcome"] = outcome_of(c, act, possible)
    path.write_text(json.dumps(cons, ensure_ascii=False, indent=1), encoding="utf-8")
    counts: dict[str, int] = {}
    for c in cons:
        counts[c["outcome"]["status"]] = counts.get(c["outcome"]["status"], 0) + 1
    print(f"  outcomes: {counts}")
