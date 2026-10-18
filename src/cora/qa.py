"""Ask the archive: BM25 retrieval over the AI-ready records + cited answers from Apertus.

Every answer sentence must cite record IDs that were retrieved; citations to anything else are
dropped and sentences left without a valid citation are returned flagged as uncited. When the
retrieval finds nothing relevant, the endpoint says so and does not call the model.
"""
import json
import math
import re
import unicodedata
from collections import Counter

STOP = set("""a an and are as at be by for from has have how in is it of on or that the this to was were what when where which who whom why with
der die das und ist im in den des dem ein eine zu von mit auf fur für als bei aus le la les des du de et en un une est dans pour qui que il""".split())


def tokens(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return [w for w in re.findall(r"[a-z0-9]+", t) if w not in STOP and len(w) > 1]


def _doc_text(r: dict) -> str:
    m, c, e, o = r["metadata"], r["classification"], r["entities"], r["source"]["original"]
    parts = [m["title"], m.get("title_en"), m.get("title_normalized"), c.get("resume"), c["document_type"],
             " ".join(m.get("subjects") or []), m.get("creator"), m.get("publisher"),
             " ".join(p.get("display_name") or p["name"] for p in e["persons"]),
             " ".join(o["name"] for o in e["organizations"]), " ".join(p["name"] for p in e["places"]),
             r["archival_location"].get("fonds"), o.get("scope_and_content"), o.get("thema"), o.get("coverage"),
             str(m.get("content_date") or "")]
    return " ".join(p for p in parts if p)


class Index:
    def __init__(self, records: dict, k1: float = 1.4, b: float = 0.75):
        self.records = records
        self.docs = {rid: tokens(_doc_text(r)) for rid, r in records.items()}
        self.tf = {rid: Counter(toks) for rid, toks in self.docs.items()}
        self.avgdl = sum(map(len, self.docs.values())) / max(1, len(self.docs))
        df = Counter(w for toks in self.docs.values() for w in set(toks))
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int = 6) -> list[tuple[str, float, list[str]]]:
        q = [w for w in tokens(query) if w in self.idf]
        out = []
        for rid, tf in self.tf.items():
            dl, s, hit = len(self.docs[rid]), 0.0, []
            for w in q:
                f = tf.get(w, 0)
                if f:
                    hit.append(w)
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if s > 0:
                out.append((rid, round(s, 3), hit))
        out.sort(key=lambda x: -x[1])
        return out[:k]


SYSTEM = """You answer questions about records of the Swiss Federal Archives using ONLY the numbered sources given.
Every sentence must cite the record IDs it relies on. If the sources do not answer the question, set insufficient=true
and say what the sources do contain instead. Never use outside knowledge. Answer in the language of the question.
Return one JSON object."""


def ask(index: Index, ap, question: str, k: int = 6, min_score: float = 2.5) -> dict:
    hits = index.search(question, k)
    relevant = [h for h in hits if h[1] >= min_score]
    if not relevant:
        return {"question": question, "answered": False,
                "message": "Nothing in the archive sample matches this question, so CORA does not answer it.",
                "retrieved": [{"id": h[0], "score": h[1], "matched_terms": h[2]} for h in hits], "sentences": []}
    sources = []
    for rid, score, hit in relevant:
        r = index.records[rid]
        m, c, o = r["metadata"], r["classification"], r["source"]["original"]
        sources.append({"id": rid, "title": m.get("title_normalized") or m["title"], "title_en": m.get("title_en"),
                        "date": m.get("content_date") or m.get("date_created"), "type": c["document_type"],
                        "resume": c.get("resume"), "content": (o.get("scope_and_content") or "")[:600],
                        "reference_code": r["source"]["reference_code"]})
    schema = {"insufficient": False, "sentences": [{"text": "<one sentence>", "sources": ["<record id>"]}]}
    user = ("Question: " + question + "\n\nSources:\n" + "\n".join(
        f"[{s['id']}] {json.dumps(s, ensure_ascii=False)}" for s in sources) + "\n\nReturn:\n" + json.dumps(schema))
    raw, meta = ap.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    allowed = {s["id"] for s in sources}
    sentences = []
    for sent in raw.get("sentences") or []:
        if not isinstance(sent, dict) or not str(sent.get("text", "")).strip():
            continue
        cited = [str(x).strip("[] ") for x in (sent.get("sources") or [])]
        valid = [x for x in cited if x in allowed]
        sentences.append({"text": sent["text"].strip(), "sources": valid,
                          "dropped_sources": [x for x in cited if x not in allowed], "uncited": not valid})
    cites = {x for s in sentences for x in s["sources"]}
    return {
        "question": question, "answered": not raw.get("insufficient") and any(not s["uncited"] for s in sentences),
        "insufficient": bool(raw.get("insufficient")), "sentences": sentences,
        "citations": [{"id": rid, "title": index.records[rid]["metadata"].get("title_normalized") or index.records[rid]["metadata"]["title"],
                       "record_url": f"#/record/{rid}", "portal_url": index.records[rid]["source"]["portal_url"],
                       "reference_code": index.records[rid]["source"]["reference_code"]}
                      for rid in [s["id"] for s in sources] if rid in cites],
        "retrieved": [{"id": h[0], "score": h[1], "matched_terms": h[2]} for h in relevant],
        "model": meta.get("model"), "seconds": round(meta["seconds"], 1), "generated": True,
    }
