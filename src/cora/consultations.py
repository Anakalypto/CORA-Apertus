"""Federal consultations 1960–1991: Apertus topic/entity tagging + procedure chains.

Sources (both bulk downloads):
  - opendata.swiss "Federal consultations 1960-1991" (Swiss Federal Archives, open use), CSV + codebook
  - Swissvotes dataset (Année politique suisse, University of Bern, CC BY 4.0), swissvotes.ch/page/dataset
Chain per consultation: consultation (record) → Federal Council message → parliament → popular vote.
Message, parliament and vote come from the matched Swissvotes row; a match is proposed by title overlap
and accepted only if Apertus confirms it. Unmatched steps stay empty ("not found"), never guessed.
"""
import csv
import io
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .qa import tokens

BASE = "https://sfa-laboratory.ch/bar-ogd/bar-02/"
CSV_NAME = "Metadatenbank-Vernehmlassungen-OGD-V1-3.csv"
SWISSVOTES = "https://swissvotes.ch/page/dataset/swissvotes_dataset.csv"
TOPICS = ["state & institutions", "foreign policy", "security & army", "economy", "agriculture", "public finance & tax",
          "energy", "transport", "environment & spatial planning", "social policy & insurance", "health", "education & research",
          "culture, media & language", "justice & police", "migration", "labour", "housing"]
COLS = ["nr", "type", "title", "department", "dept_abbr", "office", "year", "start", "end", "bbl", "br_protocol",
        "addressees", "archive_records", "document_types"]


def _download(url, path):
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    return path


def load_consultations(data_dir) -> list[dict]:
    raw = _download(BASE + CSV_NAME, data_dir / CSV_NAME).read_bytes().decode("latin-1")
    rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip().isdigit():
            continue
        d = dict(zip(COLS, (c.strip() for c in r + [""] * (len(COLS) - len(r)))))
        d["year"] = int(d["year"]) if d["year"].isdigit() else None
        out.append(d)
    return out


def load_swissvotes(data_dir) -> list[dict]:
    raw = _download(SWISSVOTES, data_dir / "swissvotes_dataset.csv").read_bytes().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw), delimiter=";"))
    keep = ["anr", "datum", "titel_kurz_d", "titel_off_d", "titel_kurz_e", "rechtsform", "swissvoteslink", "dat-message",
            "dat-parl", "nrja", "nrnein", "srja", "srnein", "annahme", "volkja-proz", "gesch_nr", "curiavista-de"]
    return [{k: r.get(k) for k in keep} for r in rows]


def _year(s):
    m = re.search(r"(\d{4})", s or "")
    return int(m.group(1)) if m else None


def candidates(c: dict, votes: list[dict], k: int = 3) -> list[tuple[float, dict]]:
    ct = {w for w in tokens(c["title"]) if len(w) > 4}
    if not ct or not c["year"]:
        return []
    out = []
    for v in votes:
        vy = _year(v["datum"])
        if not vy or not (c["year"] <= vy <= c["year"] + 15):
            continue
        vt = {w for w in tokens(f'{v["titel_kurz_d"]} {v["titel_off_d"]}') if len(w) > 4}
        # stems: compare 7-letter prefixes so "Filmwesen"/"Filmwesens" or "Zivilschutz"/"Zivilschutzes" meet
        a, b = {w[:7] for w in ct}, {w[:7] for w in vt}
        sim = len(a & b) / len(a) if a else 0
        if sim >= 0.34:
            out.append((round(sim, 2), v))
    out.sort(key=lambda x: -x[0])
    return out[:k]


TAG_SYSTEM = """You tag Swiss federal consultation procedures (1960-1991) for an archive dataset. For each numbered item give:
a short English title, 1-2 topics from the fixed list, the named entities (laws, organisations, places) as written,
and your confidence (0-1). Use only what the title and fields say. Return one JSON object."""

MATCH_SYSTEM = """Decide whether a Swiss federal consultation procedure led to a given popular vote (same legislative project).
Answer only from the titles and dates. Return one JSON object {"same_project": true|false, "confidence": 0-1, "reason": "<short>"}."""


def run(cfg) -> None:
    from .apertus import Apertus
    out_dir = cfg["paths"]["data_dir"] / "consultations"
    out_dir.mkdir(exist_ok=True)
    cons, votes = load_consultations(out_dir), load_swissvotes(out_dir)
    l = cfg["llm"]
    ap = Apertus(l["base_url"], l["api_key"], l["model"], 0.0, 3000, l["retries"])

    def tag(batch):
        items = [{"n": c["nr"], "type": c["type"], "title": c["title"], "department": c["dept_abbr"], "year": c["year"],
                  "addressees": c["addressees"][:200]} for c in batch]
        schema = {"items": [{"n": "<nr>", "title_en": "<short English title>", "topics": [f"<one of {TOPICS}>"],
                             "entities": [{"name": "<as written>", "type": "<law|organisation|place>"}], "confidence": 0.0}]}
        try:
            raw, _ = ap.chat_json([{"role": "system", "content": TAG_SYSTEM},
                                   {"role": "user", "content": json.dumps(items, ensure_ascii=False) + "\n\nReturn:\n" + json.dumps(schema)}])
            return {str(x.get("n")): x for x in raw.get("items", []) if isinstance(x, dict)}
        except Exception:
            return {}

    batches = [cons[i:i + 10] for i in range(0, len(cons), 10)]
    with ThreadPoolExecutor(l["workers"]) as pool:
        tags = {}
        for t in pool.map(tag, batches):
            tags.update(t)

    def match(c):
        best = None
        for sim, v in candidates(c, votes):
            q = {"consultation": {"title": c["title"], "year": c["year"], "type": c["type"], "department": c["dept_abbr"]},
                 "vote": {"title": v["titel_off_d"] or v["titel_kurz_d"], "date": v["datum"], "message_date": v["dat-message"]}}
            try:
                raw, _ = ap.chat_json([{"role": "system", "content": MATCH_SYSTEM},
                                       {"role": "user", "content": json.dumps(q, ensure_ascii=False)}])
            except Exception:
                continue
            # Manual check of 12 matches: all with confidence 1.0 were right, 6 of 7 below were wrong.
            if raw.get("same_project") is True and float(raw.get("confidence") or 0) < 0.99:
                best = best or {"candidate_only": True, "vote": v, "title_similarity": sim,
                                "confidence": raw.get("confidence"), "reason": raw.get("reason")}
                continue
            if raw.get("same_project") is True:
                best = {"vote": v, "title_similarity": sim, "confidence": raw.get("confidence"), "reason": raw.get("reason")}
                break
        return best

    with ThreadPoolExecutor(l["workers"]) as pool:
        matches = list(pool.map(match, cons))

    out = []
    for c, m in zip(cons, matches):
        t = tags.get(c["nr"], {})
        topics = [x for x in (t.get("topics") or []) if x in TOPICS]
        cand = m if m and m.get("candidate_only") else None
        m = None if cand else m
        v = (m or {}).get("vote") or {}
        chain = [
            {"step": "consultation", "date": str(c["year"] or ""), "detail": f'{c["type"]} · {c["dept_abbr"]}'
             + (f' · BBl {c["bbl"]}' if c["bbl"] else "") + (f' · Federal Council protocol {c["br_protocol"]}' if c["br_protocol"] else ""),
             "source": "record"},
            {"step": "message", "date": v.get("dat-message") or None, "detail": "Federal Council message (Botschaft)" if v.get("dat-message") else None,
             "source": "swissvotes" if v.get("dat-message") else None},
            {"step": "parliament", "date": v.get("dat-parl") or None,
             "detail": (f'National Council {v.get("nrja")}:{v.get("nrnein")}, Council of States {v.get("srja")}:{v.get("srnein")}'
                        if v.get("dat-parl") else None), "source": "swissvotes" if v.get("dat-parl") else None,
             "link": v.get("curiavista-de") or None},
            {"step": "vote", "date": v.get("datum") or None,
             "detail": (f'{v.get("titel_kurz_d")}: {"accepted" if v.get("annahme") == "1" else "rejected"}, {v.get("volkja-proz")} % yes'
                        if v else None), "source": "swissvotes" if v else None, "link": v.get("swissvoteslink") or None},
        ]
        out.append({**c, "title_en": t.get("title_en"), "topics": topics, "entities": t.get("entities") or [],
                    "tag_confidence": t.get("confidence"), "tag_generated": bool(t),
                    "match": {k: m[k] for k in ("title_similarity", "confidence", "reason")} | {"anr": v.get("anr")} if m else None,
                    "possible_vote": {"anr": cand["vote"]["anr"], "title": cand["vote"]["titel_kurz_d"], "date": cand["vote"]["datum"],
                                      "confidence": cand["confidence"], "reason": cand["reason"]} if cand else None,
                    "chain": chain})
    (out_dir / "consultations_tagged.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {len(out)} consultations, {sum(1 for o in out if o['topics'])} tagged, {sum(1 for o in out if o['match'])} matched to a popular vote, "
          f"{sum(1 for o in out if o['possible_vote'])} possible matches below the confidence bar")
