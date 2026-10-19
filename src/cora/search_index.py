"""Persistent search index over the AI-ready records (SQLite FTS5), used by every Apertus retrieval step.

The old index rebuilt BM25 term counts in memory at each server start and scored every record for every
query. This one is built once by `run.py export` (data/dataset/cora_search.sqlite) and answers from the
inverted index, so a query only touches the records that contain its words.

Three things help Apertus find the right record rather than a merely wordy one:
  fields   – a hit in the title or a named entity weighs more than a hit in long cataloguing prose,
  entities – person / organisation / place names (as written, display form, Wikidata label) are a table
             of their own; a question naming "Indira Gandhi" gets her records first, with a bonus,
  cards    – each record's compact source card (title, date, type, résumé, people, places) is stored
             with it, and the passage of the original description that matched is cut out by FTS5,
             so the model reads the relevant lines instead of the first 400 characters.
"""
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from .qa import STOP

# bm25() column weights, in the order of the fts columns below (id is unindexed)
WEIGHTS = {"title": 3.0, "entities": 4.0, "subjects": 2.0, "summary": 1.0, "original": 0.7}
SCALE = 0.9            # brings scores to the scale of the former in-memory BM25 (relevance bars of 2-3 still hold)
ENTITY_BONUS = 8.0     # a full entity name in the question


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# question filler that says nothing about the subject ("what does the archive say about …")
QUERY_STOP = set("""does do did can could would should tell say says said about any there their them they his her its
me my show shows find give know want please archive archives record records document documents
gibt hat haben welche welcher archiv dokumente quoi sur ont""".split())


def terms(text: str) -> list[str]:
    return [w for w in fold(text).split() if w not in STOP and w not in QUERY_STOP and len(w) > 1]


def _names(e: dict, kind: str) -> set[str]:
    wd = e.get("wikidata") or {}
    out = {e.get("name"), e.get("display_name"), wd.get("label"), e.get("as_written")}
    if e.get("name") and "," in e["name"]:                       # "Gandhi, Indira" -> "Indira Gandhi"
        last, first = e["name"].split(",", 1)
        out.add(f"{first.strip()} {last.strip()}")
    if kind == "persons":                                        # the surname alone ("Gandhi")
        full = e.get("display_name") or e["name"]
        out.add(e["name"].split(",")[0] if "," in e["name"] else full.split()[-1])
    return {fold(n) for n in out if n and len(fold(n)) > 2}


def card(r: dict) -> dict:
    """What Apertus is shown about a record (the matched passage is added at query time)."""
    m, c, e = r["metadata"], r["classification"], r["entities"]
    return {"id": r["id"], "title": m.get("title_normalized") or m["title"], "title_en": m.get("title_en"),
            "date": m.get("content_date") or m.get("date_created"), "type": c["document_type"],
            "source_level": c["source_level"], "resume": c.get("resume"),
            "persons": [p.get("display_name") or p["name"] for p in e["persons"]][:12],
            "organizations": [o["name"] for o in e["organizations"]][:8],
            "places": [p["name"] for p in e["places"]][:8],
            "reference_code": r["source"]["reference_code"], "fonds": r["archival_location"].get("fonds")}


def _columns(r: dict) -> dict:
    m, c, e, o = r["metadata"], r["classification"], r["entities"], r["source"]["original"]
    ents = []
    for kind in ("persons", "organizations", "places"):
        for x in e[kind]:
            wd = x.get("wikidata") or {}
            ents += [x.get("display_name") or x["name"], x["name"], x.get("as_written"), wd.get("label"), wd.get("description")]
    return {
        "title": " ".join(filter(None, [m["title"], m.get("title_normalized"), m.get("title_en")])),
        "entities": " ".join(filter(None, ents + [m.get("creator"), m.get("publisher")])),
        "subjects": " ".join(filter(None, list(m.get("subjects") or []) + [c["document_type"], o.get("thema"),
                                                                        r["archival_location"].get("fonds")])),
        "summary": " ".join(filter(None, [c.get("resume"), str(m.get("content_date") or "")])),
        "original": " ".join(filter(None, [o.get("scope_and_content"), o.get("coverage"), o.get("involved"), o.get("author")])),
    }


def build(records: dict | list, path: Path) -> Path:
    recs = list(records.values()) if isinstance(records, dict) else records
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(f"""
        CREATE TABLE cards (n INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, card TEXT NOT NULL);  -- n = fts rowid
        CREATE TABLE entities (name TEXT NOT NULL, kind TEXT NOT NULL, qid TEXT, record_id TEXT NOT NULL);
        CREATE INDEX entities_name ON entities(name);
        CREATE VIRTUAL TABLE fts USING fts5(id UNINDEXED, {", ".join(WEIGHTS)},
                                            tokenize = 'unicode61 remove_diacritics 2');
    """)
    for n, r in enumerate(recs, 1):
        db.execute("INSERT INTO cards VALUES (?, ?, ?)", (n, r["id"], json.dumps(card(r), ensure_ascii=False)))
        cols = _columns(r)
        db.execute(f"INSERT INTO fts(rowid, id, {', '.join(WEIGHTS)}) VALUES (?, ?, {', '.join('?' * len(WEIGHTS))})",
                   (n, r["id"], *[cols[k] for k in WEIGHTS]))
        for kind in ("persons", "organizations", "places"):
            for x in r["entities"][kind]:
                qid = (x.get("wikidata") or {}).get("qid")
                db.executemany("INSERT INTO entities VALUES (?, ?, ?, ?)", [(n, kind, qid, r["id"]) for n in _names(x, kind)])
    db.execute("INSERT INTO fts(fts) VALUES ('optimize')")
    db.commit()
    db.close()
    tmp.replace(path)
    return path


class Index:
    """Drop-in replacement of qa.Index: `.records` and `.search(query, k) -> [(id, score, matched_terms)]`."""

    def __init__(self, records: dict, path: Path):
        self.records = records
        if not path.exists() or path.stat().st_mtime < max((Path(p).stat().st_mtime for p in self._sources(path)), default=0):
            try:
                build(records, path)
            except PermissionError:      # another process still has the old file open: use it, rebuild at next start
                if not path.exists():
                    raise
                print(f"  {path.name} is in use; serving the existing index")
        self.path = path
        # lookups go by rowid: the id column of an FTS5 table is not indexed
        self.rowid = dict(self._q("SELECT id, n FROM cards"))
        self.ids = {n: rid for rid, n in self.rowid.items()}
        # entity names up to 5 words, for matching n-grams of the question
        self.entity_names = {}
        for name, rid in self._q("SELECT name, record_id FROM entities"):
            self.entity_names.setdefault(name, set()).add(rid)

    def _q(self, sql: str, args=()) -> list:
        # a short-lived read-only connection per query: thread-safe, and the file is never held open, so
        # `run.py export` can replace it while the server runs (Windows refuses to replace an open file)
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    @staticmethod
    def _sources(path: Path):
        ds = path.parent / "cora_dataset.jsonl"
        return [ds] if ds.exists() else []

    def entity_hits(self, query: str) -> dict[str, list[str]]:
        """Entity names (2+ words, or one rare word of 5+ letters) that appear in the question -> record ids."""
        words = fold(query).split()
        found = {}
        for n in range(min(5, len(words)), 0, -1):
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i:i + n])
                ids = self.entity_names.get(gram)
                if ids and (n > 1 or (len(gram) >= 5 and gram not in STOP and len(ids) <= 5)) \
                        and not any(gram in f for f in found):
                    found[gram] = sorted(ids)
        return found

    def search(self, query: str, k: int = 6) -> list[tuple[str, float, list[str]]]:
        q = list(dict.fromkeys(terms(query)))
        scores, matched = {}, {}
        if q:
            match = " OR ".join(f'"{t}"' for t in q)
            weights = ", ".join(str(w) for w in WEIGHTS.values())
            for n, s in self._q(
                    f"SELECT rowid, -bm25(fts, 0, {weights}) FROM fts WHERE fts MATCH ? ORDER BY bm25(fts, 0, {weights}) LIMIT ?",
                    (match, max(50, k * 5))):
                scores[self.ids[n]] = s * SCALE
        for name, ids in self.entity_hits(query).items():
            for rid in ids:
                scores[rid] = scores.get(rid, 0) + ENTITY_BONUS
                matched.setdefault(rid, []).append(f"entity:{name}")
        top = sorted(scores, key=lambda x: -scores[x])[:k]
        out = []
        for rid in top:
            row = self._q(f"SELECT {', '.join(WEIGHTS)} FROM fts WHERE rowid = ?", (self.rowid[rid],))[0]
            have = set(fold(" ".join(row)).split())
            out.append((rid, round(scores[rid], 3), matched.get(rid, []) + [t for t in q if t in have]))
        return out

    def card(self, rid: str) -> dict:
        row = next(iter(self._q("SELECT card FROM cards WHERE n = ?", (self.rowid.get(rid),))), None)
        return json.loads(row[0]) if row else card(self.records[rid])

    def passage(self, rid: str, query: str, tokens: int = 48) -> str | None:
        """The part of the original description that matches the question (FTS5 snippet), or None."""
        q = list(dict.fromkeys(terms(query)))
        if not q or rid not in self.rowid:
            return None
        row = next(iter(self._q(
            f"SELECT snippet(fts, 5, '', '', ' … ', ?) FROM fts WHERE fts MATCH ? AND rowid = ?",
            (tokens, "original : (" + " OR ".join(f'"{t}"' for t in q) + ")", self.rowid[rid]))), None)
        return re.sub(r"\s+", " ", row[0]).strip() if row and row[0] else None
