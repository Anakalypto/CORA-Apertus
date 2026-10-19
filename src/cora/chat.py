"""Ask the archive as a conversation: Apertus answers from archive records and Wikipedia.

Each turn retrieves
  R#  records of the CORA dataset (BM25 over the question and the previous question, for follow-ups),
  W#  Wikipedia articles found with Wikipedia's search API (English, plus German for Swiss topics),
and gives them to Apertus with the recent conversation. Every sentence lists its sources; citations to
anything not offered are dropped. Sentences with no source are kept but marked as the model's own
knowledge (not checked against a source). Everything returned is labelled as generated.
"""
import json
import re
import time
import urllib.parse

from .enrich import Cache, _get
from .more import wikipedia_summary
from .qa import tokens

SYSTEM = """You are the historian of CORA, a research assistant for the Swiss Federal Archives. You talk with a user
about Swiss and world history and the records of the archive. Use the numbered sources of this turn:
[R#] records of the Swiss Federal Archives (the evidence: prefer them, and say which record shows what),
[W#] Wikipedia articles (for historical context, people, places and events).
Give historical context when it helps: who, what, when, why it mattered. Every sentence lists ONLY the sources that
actually state what the sentence says (never cite a record for a fact it does not contain).
You may add widely known context that no source states, but then give that sentence no sources (it will be shown as
your own knowledge). Never invent records, quotes, dates or numbers. Never name who held an office, command or role
unless a source of THIS turn states it; otherwise say the sources do not name them. Your earlier answers in this
conversation are not evidence: if this turn's sources contradict one of them, say so and correct it. If the archive has nothing on the question, say so
in one sentence and then answer from Wikipedia. Answer in the language of the user's last message, in 1 to 3 short
paragraphs, and propose 3 short follow-up questions the archive could help with. Never write source tags such as
"R1" or "(W2)" inside the sentence text: list them only in "sources". Return one JSON object."""

_TAGS = re.compile(r"\s*\((?:[RW]\d+(?:\s*(?:,|–|-|bis|to|and|und|et)\s*[RW]?\d+)*)\)")  # bracketed tags only


def wiki_candidates(queries: list[tuple[str, str]], focus: str, cache: Cache, cfg, k: int = 4) -> list[dict]:
    """Top-3 search hits per (lang, query), ranked by overlap with the user's questions, best k kept."""
    want = {w[:6] for w in tokens(focus) if len(w) > 3}
    cands, seen = [], set()
    for qi, (lang, q) in enumerate(queries):
        for rank, w in enumerate(wiki_search(q, lang, cache, cfg, k=3)):
            if w["url"] in seen:
                continue
            seen.add(w["url"])
            have = {t[:6] for t in tokens(w["title"] + " " + w["extract"][:600])}
            title_hit = sum(t[:6] in want for t in tokens(w["title"]))
            score = len(want & have) + 2 * title_hit - 0.5 * rank - 0.2 * qi
            cands.append((score, w))
    cands.sort(key=lambda x: -x[0])
    return [w for _, w in cands[:k]]


def wiki_search(query: str, lang: str, cache: Cache, cfg, k: int = 2) -> list[dict]:
    key = f"wpsearch|{lang}|{query}"
    if key not in cache.data:
        time.sleep(0.2)
        try:
            hits = _get(f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
                {"action": "query", "list": "search", "srsearch": query, "srlimit": 4, "format": "json"}),
                cfg["enrich"]["user_agent"])["query"]["search"]
            cache.data[key] = [h["title"] for h in hits]
        except Exception:
            cache.data[key] = []
    out = []
    for title in cache.data[key][:k]:
        url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
        s = wikipedia_summary(url, cache, cfg)
        if s and s.get("extract") and "may refer to" not in s["extract"][:200]:
            out.append(s)
    return out


PLAN = """Turn the user's last message into self-contained search queries, resolving pronouns and follow-ups from the
conversation (e.g. "and who commanded the army?" after a question on Swiss mobilisation 1914-1918 becomes
"commander-in-chief Swiss Army 1914-1918 General"). When the user asks WHO held a role (a commander, a minister, an
author), one Wikipedia query must name that role precisely (e.g. "General (Switzerland)", "List of members of the Swiss
Federal Council") or the person if you know it. Return one JSON object:
{"archive_query": "<keywords in German and English for the Swiss Federal Archives catalogue>",
 "wikipedia_en": ["<1-2 English Wikipedia search queries, ideally article names>"],
 "wikipedia_de": ["<0-1 German Wikipedia query if the topic is Swiss>"],
 "asks_who": {"role": "<the office/role the user asks about, e.g. 'General of the Swiss Army'>", "period": "<years>",
              "candidate": "<the person you believe held it, or null>"} or null when the user does not ask who}"""


def plan_queries(ap, turns: list[dict]) -> dict:
    # Only the user's questions: an earlier (possibly wrong) answer must not steer the search.
    convo = "\n".join(f"user: {m['content'][:600]}" for m in turns if m["role"] == "user")
    temp, ap.temperature = ap.temperature, 0.0  # deterministic planning
    try:
        raw, _ = ap.chat_json([{"role": "system", "content": PLAN}, {"role": "user", "content": convo}])
    except Exception:
        raw = {}
    finally:
        ap.temperature = temp
    strs = lambda v: [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str) and x.strip()]
    who = raw.get("asks_who") if isinstance(raw.get("asks_who"), dict) else {}
    who = {k: who.get(k).strip() for k in ("role", "period", "candidate") if isinstance(who.get(k), str) and who.get(k).strip()
           and who.get(k).strip().lower() not in ("null", "none", "unknown")}
    return {"archive_query": raw.get("archive_query") if isinstance(raw.get("archive_query"), str) else "",
            "wikipedia_en": strs(raw.get("wikipedia_en"))[:2], "wikipedia_de": strs(raw.get("wikipedia_de"))[:1], "asks_who": who or None}


re_words = re.compile(r"[a-zàâäéèêëîïôöùûüç]+")
LANG_HINTS = {
    "German": {"der", "die", "das", "und", "warum", "wer", "wie", "was", "wann", "nicht", "ist", "sind", "mit", "von", "zu", "den", "im",
               "welche", "welcher", "welches", "gab", "es", "zur", "zum", "dem", "über", "für", "auf", "eine", "ein", "gibt", "wurde"},
    "French": {"le", "la", "les", "et", "pourquoi", "qui", "quand", "comment", "est", "des", "une", "du", "dans", "que", "quel"},
    "Italian": {"il", "lo", "gli", "perché", "chi", "quando", "come", "della", "delle", "che", "nel", "sono", "una", "degli"},
}


def detect_language(text: str) -> str:
    words = set(re_words.findall(text.lower()))
    best = max(LANG_HINTS, key=lambda l: len(words & LANG_HINTS[l]))
    return best if len(words & LANG_HINTS[best]) >= 2 else "English"


def _support(text: str, cited: list[str]) -> float:
    """Share of the sentence's content words found in the sources it cites (independent of the model)."""
    words = [w for w in tokens(text) if len(w) > 4]
    pool = set(tokens(" ".join(cited)))
    if not words:
        return 1.0
    return round(sum(w in pool or any(w[:5] == p[:5] for p in pool if len(p) > 4) for w in words) / len(words), 2)


def _rec_source(r: dict, ref: str, index=None, query: str = "") -> dict:
    m, c, o = r["metadata"], r["classification"], r["source"]["original"]
    # with the search index: the people/places of the record and the passage that matched, not the first 400 characters
    passage = index.passage(r["id"], query) if hasattr(index, "passage") and query else None
    card = index.card(r["id"]) if hasattr(index, "card") else {}
    who = "; ".join(filter(None, [", ".join(card.get("persons") or []), ", ".join(card.get("places") or [])]))
    return {"ref": ref, "kind": "record", "id": r["id"], "title": m.get("title_normalized") or m["title"], "title_en": m.get("title_en"),
            "date": m.get("content_date") or m.get("date_created"), "document_type": c["document_type"], "source_level": c["source_level"],
            "reference_code": r["source"]["reference_code"], "portal_url": r["source"]["portal_url"],
            "text": f'{m.get("title_en") or m["title"]} ({m.get("content_date") or ""}, {c["document_type"]}): '
                    f'{c.get("resume") or ""}' + (f" People/places: {who}." if who else "")
                    + f' {passage or (o.get("scope_and_content") or "")[:400]}'}


def chat(index, ap, messages: list[dict], cfg, data_dir, record: str | None = None, k: int = 5) -> dict:
    turns = [m for m in messages if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()][-8:]
    if not turns or turns[-1]["role"] != "user":
        raise ValueError("the last message must be the user's")
    question = turns[-1]["content"].strip()
    prev_q = next((m["content"] for m in reversed(turns[:-1]) if m["role"] == "user"), "")
    cache = Cache(data_dir / "enrich_cache.json")

    # 1. Apertus turns the turn into self-contained queries (follow-ups resolved from the conversation)
    plan = plan_queries(ap, turns)
    # 2. archive records: the planned query and the question itself
    scored = {}
    for q_, bar in ((plan["archive_query"], 2.5), (question, 2.0), ((prev_q + " " + question) if prev_q else "", 3.0)):
        for rid, sc, _ in index.search(q_, k) if q_ else []:
            if sc >= bar:
                scored[rid] = max(scored.get(rid, 0), sc)
    ranked = sorted(scored, key=lambda x: -scored[x])
    ids = ([record] if record and record in index.records else []) + [x for x in ranked if x != record]
    sources = [_rec_source(index.records[rid], f"R{i}", index, f'{plan["archive_query"]} {question}')
               for i, rid in enumerate(ids[:k], 1)]
    # 3. Wikipedia: the planned queries (English, plus German for Swiss topics), falling back to the question's words
    user_qs = " ".join(m["content"] for m in turns if m["role"] == "user")
    keywords = " ".join(w for w in tokens(prev_q + " " + question) if len(w) > 3)  # questions only, as a fallback query
    who = plan.get("asks_who") or {}
    who_q = ([("en", who["role"])] if who.get("role") else []) + \
            ([("en", who["candidate"]), ("de", who["candidate"])] if who.get("candidate") else [])  # checked by the article text
    queries = who_q + [("en", q_) for q_ in plan["wikipedia_en"]] + [("de", q_) for q_ in plan["wikipedia_de"]] + [("en", keywords)]
    wiki = wiki_candidates(queries, question + " " + user_qs, cache, cfg)
    cache.save()
    for i, w in enumerate(wiki[:4], 1):
        sources.append({"ref": f"W{i}", "kind": "wikipedia", "title": w["title"], "url": w["url"], "lang": w["lang"],
                        "text": w["extract"][:900], "license": "CC BY-SA 4.0"})

    lang = detect_language(question)
    sent = {"text": "<sentence>", "sources": ["<R#|W#>"]}
    schema = {"paragraph_1": [sent, sent], "paragraph_2": [sent, sent], "paragraph_3": [sent],
              "follow_ups": ["<question>", "<question>", "<question>"]}
    history = [{"role": m["role"], "content": m["content"][:1500]} for m in turns[:-1]]
    user = ("Sources for this turn:\n" + ("\n".join(f"[{s['ref']}] {s['text']}" for s in sources) or "(none found)")
            + f"\n\nUser: {question}\n\nWrite the paragraphs and the follow-up questions in {lang}.\nReturn:\n" + json.dumps(schema))
    raw, meta = ap.chat_json([{"role": "system", "content": SYSTEM}, *history, {"role": "user", "content": user}])

    allowed = {s["ref"] for s in sources}
    text_of = {s["ref"]: f'{s["title"]} {s["text"]}' for s in sources}
    paragraphs = []
    for key in sorted(x for x in raw if x.startswith("paragraph")):
        sents = []
        for s in raw[key] if isinstance(raw[key], list) else []:
            if isinstance(s, dict) and str(s.get("text", "")).strip():
                refs = [str(x).strip("[] ") for x in s.get("sources") or []]
                ok = list(dict.fromkeys(x for x in refs if x in allowed))
                sup = _support(_TAGS.sub("", s["text"]), [text_of[x] for x in ok]) if ok else None
                clean = re.sub(r"\s+([.,;:])", r"\1", _TAGS.sub("", s["text"])).strip()  # stray "R1"/"(W2)" tags in the prose
                sents.append({"text": clean, "sources": ok, "own_knowledge": not ok,
                              "support": sup, "weakly_supported": bool(ok) and sup < 0.2,
                              "dropped_sources": [x for x in refs if x not in allowed]})
        if sents:
            paragraphs.append(sents)
    used = {x for p in paragraphs for s in p for x in s["sources"]}
    text = " ".join(s["text"] for p in paragraphs for s in p)
    return {"answer": text, "paragraphs": paragraphs, "generated": True, "model": meta.get("model"),
            "seconds": round(meta["seconds"], 1),
            "sources": [s | {"text": None} for s in sources if s["ref"] in used],
            "offered": {"records": sum(1 for s in sources if s["kind"] == "record"), "wikipedia": sum(1 for s in sources if s["kind"] == "wikipedia")},
            "own_knowledge_sentences": sum(s["own_knowledge"] for p in paragraphs for s in p),
            "weak_sentences": sum(s["weakly_supported"] for p in paragraphs for s in p), "queries": plan, "language": lang,
            "follow_ups": [f for f in (raw.get("follow_ups") or []) if isinstance(f, str) and f.strip()][:3]}
