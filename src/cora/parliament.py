"""Parliament view: National Council, Council of States and Federal Council since 1848.

Sources (official open data, attribution):
  - parlament.ch OData web service, MemberCouncilHistory (members of NR/SR since 1848, Federal Council = council 99)
  - BFS PX-Web px-x-1702020000_104: national party strengths (vote shares) since 1971
Legislatures snap to election years: 3-year terms 1848–1931, 4-year terms from 1931.
Party lineages are mapped to one continuous colour (BGB→SVP, KK→KVP→CVP→Mitte, …).
"""
import json
import re
import urllib.parse
import urllib.request

ODATA = "https://ws.parlament.ch/odata.svc/MemberCouncilHistory"
PX = "https://www.pxweb.bfs.admin.ch/api/v1/de/px-x-1702020000_104/px-x-1702020000_104.px"
FIELDS = ["PersonNumber", "FirstName", "LastName", "Council", "CantonAbbreviation", "PartyAbbreviation", "PartyName",
          "ParlGroupAbbreviation", "DateJoining", "DateLeaving"]

# lineage id -> (label, colour, abbreviations seen in parlament.ch / BFS)
LINEAGES = {
    "svp": ("BGB → SVP", "#2f7d32", ["BGB", "SVP", "UDC", "BGBP", "Bauern"]),
    "mitte": ("KK → KVP → CVP → Die Mitte (+BDP)", "#f28c28", ["KK", "KVP", "KCVP", "CVP", "PDC", "M-CEB", "Mitte", "Die Mitte", "BDP", "CSP-OW", "CVP-PCD", "Kons", "GKons", "M-E"]),
    "fdp": ("Freisinn → FDP (+LPS 2009)", "#1f5aa6", ["FDP", "PRD", "PLR", "FDP-Liberale", "RL", "FDP.Die Liberalen", "Freisinn", "Radikale", "FL"]),
    "lps": ("Liberale (LPS, merged into FDP 2009)", "#6f9ad6", ["LPS", "LDP", "PLS", "Lib", "Liberale", "L", "Liberal-Konservative", "LibK", "RKons"]),
    "sp": ("SP", "#d7191c", ["SP", "PS", "SPS", "Grüt"]),
    "gps": ("Grüne", "#8cc63f", ["GPS", "Grüne", "PES", "GRÜNE", "GB", "FGA", "Grünes Bündnis"]),
    "glp": ("GLP", "#b5d334", ["GLP", "glp", "pvl"]),
    "evp": ("EVP", "#f7d000", ["EVP", "PEV"]),
    "ldu": ("LdU", "#c08d4a", ["LdU", "AdI"]),
    "left": ("PdA / far left", "#8b0000", ["PdA", "PST", "KP", "POCH", "PSA", "Sol.", "SolidaritéS", "AL", "Sol", "AdG"]),
    "right": ("SD / Rep. / FPS / EDU / Lega / MCR", "#5a3d2b", ["SD", "NA", "Rep.", "FPS", "AP", "EDU", "UDF", "Lega", "MCR", "MCG", "UDE", "Vigilance", "Front"]),
    "csp": ("CSP", "#e0a96d", ["CSP", "PCS"]),
    "dem": ("Demokraten", "#9467bd", ["DP", "Dem", "Demokraten"]),
}


def lineage(abbr: str | None, name: str | None = None) -> str:
    a = (abbr or "").strip().rstrip("*").strip()
    for lid, (_, _, abbrs) in LINEAGES.items():
        if a in abbrs:
            return lid
    n = (name or "").lower()
    for key, lid in (("bauern", "svp"), ("volkspartei", "svp"), ("katholisch", "mitte"), ("christlichdemokr", "mitte"),
                     ("freisinn", "fdp"), ("radikal", "fdp"), ("liberal", "lps"), ("sozialdemokr", "sp"), ("grün", "gps"),
                     ("landesring", "ldu"), ("evangelisch", "evp"), ("kommun", "left"), ("arbeit", "left"), ("demokrat", "dem")):
        if key in n:
            return lid
    return "other"


def legislature_starts() -> list[int]:
    years = list(range(1848, 1932, 3))  # 1848 … 1928, 1931 (3-year terms)
    return years + list(range(1935, 2024, 4))  # 4-year terms from the 1931 election


def _date(s):
    m = re.search(r"/Date\((-?\d+)\)/", s or "")
    if not m:
        return None
    import datetime
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=int(m.group(1)))).date().isoformat()


def fetch_members() -> list[dict]:
    out, skip = [], 0
    while True:
        q = {"$filter": "Language eq 'DE'", "$select": ",".join(FIELDS), "$top": "1000", "$skip": str(skip), "$format": "json"}
        with urllib.request.urlopen(ODATA + "?" + urllib.parse.urlencode(q), timeout=120) as r:
            rows = json.load(r)["d"]
        rows = rows.get("results", rows) if isinstance(rows, dict) else rows
        for x in rows:
            out.append({"pn": x["PersonNumber"], "first": x["FirstName"], "last": x["LastName"], "council": x["Council"],
                        "canton": x["CantonAbbreviation"], "party": x["PartyAbbreviation"], "party_name": x["PartyName"],
                        "join": _date(x["DateJoining"]), "leave": _date(x["DateLeaving"]),
                        "lineage": lineage(x["PartyAbbreviation"], x["PartyName"])})
        if len(rows) < 1000:
            return out
        skip += 1000


def fetch_vote_shares() -> dict:
    body = {"query": [{"code": "Kanton", "selection": {"filter": "item", "values": ["CH"]}},
                      {"code": "Ergebnisse", "selection": {"filter": "item", "values": ["3"]}}],
            "response": {"format": "json-stat2"}}
    req = urllib.request.Request(PX, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    years = list(d["dimension"]["Jahr"]["category"]["label"].values())
    parties = list(d["dimension"]["Partei"]["category"]["label"].values())
    out = {}
    for i, y in enumerate(years):
        out[y] = {p: d["value"][i * len(parties) + j] for j, p in enumerate(parties) if d["value"][i * len(parties) + j] is not None}
    return out


def run(cfg) -> None:
    out_dir = cfg["paths"]["data_dir"] / "parliament"
    out_dir.mkdir(exist_ok=True)
    members = fetch_members()
    shares = fetch_vote_shares()
    data = {
        "sources": {"members": "parlament.ch OData MemberCouncilHistory (open data, attribution: Parlamentsdienste)",
                    "vote_shares": "BFS px-x-1702020000_104, national party strength in % since 1971 (attribution: BFS)"},
        "legislatures": legislature_starts(),
        "lineages": {k: {"label": v[0], "color": v[1]} | {"members": []} for k, v in LINEAGES.items()} | {"other": {"label": "other / unknown", "color": "#9e9e9e"}},
        "vote_shares": {y: {p: {"share": v, "lineage": lineage(p)} for p, v in ps.items()} for y, ps in shares.items()},
        "members": members,
    }
    for v in data["lineages"].values():
        v.pop("members", None)
    (out_dir / "parliament.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    print(f"  {len(members)} memberships, councils {dict(Counter(m['council'] for m in members))}, "
          f"lineage other: {sum(1 for m in members if m['lineage'] == 'other')}")
    print("  unmapped parties:", Counter(m["party"] for m in members if m["lineage"] == "other").most_common(15))
