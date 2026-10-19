"""Topic panel for secondary / tertiary records: the subject the record reports on, read further.

Apertus does the reading in two passes:
  1. plan   – from the original record fields it names the subject (e.g. "Sonderbund War"), a Wikipedia
              query, archive search stems in the archive's languages, and whether the subject is still
              discussed today (then a news query).
  2. vet    – it sees the candidates fetched for that plan and keeps only those about the same subject:
              one Wikipedia article (or none), primary dossiers of the Federal Archives, news articles.
Candidates come from:
  Wikipedia   MediaWiki search + REST summary (CC BY-SA)                    – tertiary
  Primary     Federal Archives dossiers whose ORIGINAL title contains a stem (LINDAS transport only),
              plus records of the CORA dataset that Apertus classified as primary
  News        Google News RSS search (GDELT as a fallback), only for contemporary subjects
Nothing is invented: every item shown is a fetched candidate; Apertus only selects. Cached per record.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import unescape

from . import i18n, lindas
from .enrich import _get

PLAN = """You help a reader go further from ONE record of the Swiss Federal Archives that reports on, or indexes, an event or issue.
Name the historical subject the record is about, as specifically as the record allows (an event, a debate, a law, an affair,
a person's case), not the medium (not "Tagesschau", not "newsreel"). If the record shows nothing identifiable, say so.
Return one JSON object:
{"subject": "<short English name, e.g. 'Sonderbund War'>",
 "identifiable": true|false,
 "wikipedia_query": "<query for the English Wikipedia article on that subject>",
 "wikipedia_broader": "<query for a broader English Wikipedia article that covers the subject, e.g. 'Banking in Switzerland'>",
 "archive_stems": ["<1 to 3 single words or short stems as they would appear in German or French file titles of the
                    Federal Archives, e.g. 'Sonderbund', 'Frauenstimmrecht', 'suffrage féminin'. Specific to the subject:
                    never a country, city or institution name alone>"],
 "contemporary": true|false,   // true only if the subject is still debated or reported in the news today
 "news_query": "<short news search query in English, no year, or empty>"}"""

VET = """You check candidate links for a reader of ONE archive record. The record's subject is given.
Keep ONLY candidates that are about that same subject (not merely the same country, year, word or medium).
Primary sources are documents produced by the people and offices involved (files, correspondence, minutes, reports,
decisions, petitions); television, radio or newsreel reports are NOT primary sources.
Return one JSON object:
{"wikipedia": "<W# of the article on the subject, else of the closest broader article that covers it, or null>",
 "primary": ["<P# or A# of primary sources about the subject, most relevant first, at most 8>"],
 "news": ["<N# of recent news articles about the subject itself, at most 6>"],
 "note": "<one sentence: how the subject connects the record to these sources>"}"""


def _record_text(r: dict) -> str:
    m, o = r["metadata"], r["source"]["original"]
    lines = [f"Title: {m['title']}", f"Title (English): {m.get('title_en') or ''}",
             f"Date: {m.get('content_date') or m.get('date_created') or ''}",
             f"Document type: {r['classification']['document_type']} ({r['classification']['source_level']} source)",
             f"Subjects: {', '.join(m.get('subjects') or [])}",
             f"Persons: {', '.join(p.get('display_name') or p['name'] for p in r['entities']['persons'][:8])}",
             f"Places: {', '.join(p['name'] for p in r['entities']['places'][:8])}",
             f"Scope and content: {(o.get('scope_and_content') or '')[:1500]}"]
    if r["classification"].get("resume"):
        lines.append(f"Summary (generated): {r['classification']['resume']}")
    return "\n".join(l for l in lines if not l.endswith(": "))


def wikipedia_candidates(query: str, ua: str, n: int = 5) -> list[dict]:
    d = _get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": n}), ua)
    return [{"title": x["title"], "snippet": re.sub(r"<[^>]+>", "", unescape(x.get("snippet") or "")),
             "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(x["title"].replace(" ", "_"))}
            for x in d.get("query", {}).get("search", [])]


def wikipedia_page(title: str, ua: str, wiki: str = "en") -> dict | None:
    try:
        d = _get(f"https://{wiki}.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_")), ua)
    except Exception:
        return None
    return {"title": d.get("title"), "description": d.get("description"), "extract": d.get("extract"),
            "url": (d.get("content_urls") or {}).get("desktop", {}).get("page"),
            "thumbnail": (d.get("thumbnail") or {}).get("source"), "license": "CC BY-SA 4.0", "lang": wiki}


def wikipedia_in(title: str, lang: str, ua: str) -> dict | None:
    """The same article in the reader's Wikipedia (de, fr, it, rm), through the English article's language links."""
    try:
        d = _get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "titles": title, "prop": "langlinks", "lllang": lang, "format": "json", "redirects": 1}), ua)
        links = next(iter(d["query"]["pages"].values())).get("langlinks") or []
    except Exception:
        return None
    return wikipedia_page(links[0]["*"], ua, lang) if links else None


def archive_dossiers(stem: str, limit: int = 10) -> list[dict]:
    """Units of the Federal Archives whose original title contains the stem (any level, any date)."""
    s = stem.lower().replace("\\", "").replace('"', "")
    # Dossiers (rico:RecordSet) first: item-level records of the database are mostly television clips.
    rows = lindas.sparql(f"""SELECT ?s ?t ?rc ?d WHERE {{ ?s a rico:RecordSet ; rico:title ?t . FILTER(CONTAINS(LCASE(STR(?t)), "{s}"))
        OPTIONAL {{ ?s sld:referenceCode ?rc }} OPTIONAL {{ ?s rico:isAssociatedWithDate/rico:expressedDate ?d }} }} LIMIT {limit}""",
                         timeout=90, retries=1)
    out = {}
    for x in rows:
        i = x["s"].rsplit("/", 1)[1]
        out.setdefault((x["t"].strip().lower(), x.get("d")), {
            "id": i, "title": x["t"], "reference_code": x.get("rc"), "date": x.get("d"), "stem": stem,
            "portal_url": f"https://www.recherche.bar.admin.ch/recherche/#/de/archiv/einheit/{i}"})
    return list(out.values())


def news(query: str, ua: str, n: int = 10) -> list[dict]:
    try:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en", "gl": "CH", "ceid": "CH:en"})
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=30) as r:
            xml = r.read().decode("utf-8", "replace")
        items = []
        for it in re.findall(r"<item>(.*?)</item>", xml, re.S)[:n]:
            g = lambda tag: unescape((re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1]).strip()
            src = g("source")
            title = g("title")
            if src and title.endswith(" - " + src):
                title = title[: -len(src) - 3]
            items.append({"title": title, "url": g("link"), "source": src, "date": g("pubDate")})
        if items:
            return items
    except Exception:
        pass
    try:  # fallback: GDELT DOC API (last months only)
        d = _get("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
            {"query": query, "mode": "artlist", "format": "json", "maxrecords": n}), ua)
        return [{"title": a["title"], "url": a["url"], "source": a.get("domain"), "date": a.get("seendate")} for a in d.get("articles", [])]
    except Exception:
        return []


def _for_reader(out: dict) -> dict:
    """Result as served: internal candidate refs (P8, W2…) removed from the note, search links added."""
    note = re.sub(r"\s*\(?\[?\b[WPAN]\d+\]?\)?", "", str(out.get("note") or "")).strip() or None
    return out | {"note": note, "search_links": search_links(out)}


LOCALIZE = """You write two short texts for a reader of an archive website, in {language}.
Given the subject of an archive record and an English note on how the record connects to its sources, return one
JSON object {{"subject": "<the subject, as a reader in {language} would name it>",
"note": "<the note, written in {language}, same meaning, one or two sentences>"}}. Keep names of people, places and
archive units as they are."""


def _in_language(out: dict, path, lang: str, ap, ua: str = "CORA-Apertus/0.1") -> dict:
    """Subject label and note written by Apertus in the reader's language (cached per record and language)."""
    if lang == "en" or not out.get("identifiable"):
        return out | {"lang": "en"}

    def make():
        wp = wikipedia_in(out["wikipedia"]["title"], lang, ua) if out.get("wikipedia") else None
        try:
            raw, _ = ap.chat_json([{"role": "system", "content": LOCALIZE.format(language=i18n.language(lang))},
                                   {"role": "user", "content": json.dumps({"subject": out["subject"], "note": out.get("note") or ""},
                                                                          ensure_ascii=False)}])
        except Exception:
            return None
        return {"subject": str(raw.get("subject") or "").strip() or None, "note": str(raw.get("note") or "").strip() or None,
                "wikipedia": wp}
    loc = i18n.localized(path, lang, make) or {}
    return out | {"lang": lang if loc else "en", "subject_en": out["subject"],
                  "subject": loc.get("subject") or out["subject"], "note": loc.get("note") or out.get("note"),
                  "wikipedia": loc.get("wikipedia") or out.get("wikipedia")}  # the reader's Wikipedia when the article exists there


def search_links(out: dict) -> dict:
    """Ready-made searches for the reader to go further (Federal Archives portal, Dodis)."""
    if not out.get("identifiable"):
        return {}
    found = [d["stem"] for d in out["primary"]]  # prefer the stem that found the dossiers Apertus kept
    stem = max(found, key=found.count) if found else (out["plan"].get("archive_stems") or [out["subject"]])[0]
    q = json.dumps({"searchGroups": [{"searchFields": [{"key": "allData", "value": stem}], "fieldOperator": 1}], "groupOperator": 1},
                   ensure_ascii=False, separators=(",", ":"))
    return {f"Swiss Federal Archives: “{stem}”": "https://www.recherche.bar.admin.ch/recherche/#/de/suche/resultat?q=" + urllib.parse.quote(q, safe=":,"),
            f"Dodis (diplomatic documents): “{out['subject']}”": "https://dodis.ch/search?q=" + urllib.parse.quote(out["subject"])}


def _picked(refs, prefix: str, items: list, k: int) -> list:
    """Candidates Apertus kept, by reference (W3, P1, …); unknown references are dropped."""
    out = []
    for x in dict.fromkeys(str(x).strip("[] ") for x in (refs if isinstance(refs, list) else []) if x):
        if re.fullmatch(prefix + r"\d+", x) and 0 < int(x[1:]) <= len(items):
            out.append(items[int(x[1:]) - 1])
    return out[:k]


def build(r: dict, index, cfg, ap, lang: str = "en") -> dict:
    cache_dir = cfg["paths"]["data_dir"] / "topic_cache"
    cache_dir.mkdir(exist_ok=True)
    path = cache_dir / f"{r['id']}.json"
    if path.exists():
        return _in_language(_for_reader(json.loads(path.read_text(encoding="utf-8"))), path, lang, ap, cfg["enrich"]["user_agent"])
    ua = cfg["enrich"]["user_agent"]
    t0 = time.time()
    plan, _ = ap.chat_json([{"role": "system", "content": PLAN}, {"role": "user", "content": _record_text(r)}])
    subject = str(plan.get("subject") or "").strip()
    out = {"id": r["id"], "generated": True, "subject": subject, "identifiable": bool(plan.get("identifiable")) and bool(subject),
           "contemporary": bool(plan.get("contemporary")), "plan": plan, "wikipedia": None, "primary": [], "primary_in_dataset": [],
           "news": [], "note": None}
    if out["identifiable"]:
        stems = [s for s in (plan.get("archive_stems") or []) if isinstance(s, str) and 3 <= len(s.strip()) <= 40][:3]
        with ThreadPoolExecutor(5) as pool:
            f_wp = [pool.submit(wikipedia_candidates, q, ua, 4) for q in dict.fromkeys(
                filter(None, [str(plan.get("wikipedia_query") or subject), str(plan.get("wikipedia_broader") or "")]))]
            f_ar = [pool.submit(archive_dossiers, s.strip()) for s in stems]
            f_nw = pool.submit(news, str(plan.get("news_query") or subject), ua) if out["contemporary"] else None
            wps = list({w["title"]: w for f in f_wp if not f.exception() for w in f.result()}.values())
            dossiers = list({d["id"]: d for f in f_ar if not f.exception() for d in f.result()}.values())
            items = f_nw.result() if f_nw else []
        # records of the CORA dataset that Apertus classified as primary (offered to the vet pass as A#)
        own = [{"id": rid, "title": index.records[rid]["metadata"].get("title_normalized") or index.records[rid]["metadata"]["title"],
                "date": index.records[rid]["metadata"].get("content_date"), "resume": index.records[rid]["classification"].get("resume") or "",
                "url": f"#/record/{rid}"}
               for rid, score, _ in index.search(" ".join([subject] + stems), 12)
               if rid != r["id"] and score >= 2.5 and index.records[rid]["classification"]["source_level"] == "primary"][:5]
        dossiers = [d for d in dossiers if d["id"] != r["id"]]
        cands = ["Subject: " + subject, "", "Record:", _record_text(r), "", "Wikipedia candidates:"]
        cands += [f"[W{i}] {w['title']}: {w['snippet'][:200]}" for i, w in enumerate(wps, 1)]
        cands += ["", "Archive dossiers (title, date):"] + [f"[P{i}] {d['title'][:200]} ({d.get('date') or 'n.d.'})" for i, d in enumerate(dossiers, 1)]
        cands += [f"[A{i}] {d['title'][:160]} ({d.get('date') or 'n.d.'}): {d['resume'][:200]}" for i, d in enumerate(own, 1)]
        if items:
            cands += ["", "News articles:"] + [f"[N{i}] {n['title']} ({n['source']}, {n['date'][:16]})" for i, n in enumerate(items, 1)]
        vet, _ = ap.chat_json([{"role": "system", "content": VET}, {"role": "user", "content": "\n".join(cands)}])
        w = _picked([vet.get("wikipedia")], "W", wps, 1)
        out["wikipedia"] = wikipedia_page(w[0]["title"], ua) if w else None
        out["primary"] = _picked(vet.get("primary"), "P", dossiers, 8)
        out["primary_in_dataset"] = _picked(vet.get("primary"), "A", own, 5)
        out["news"] = _picked(vet.get("news"), "N", items, 6)
        out["note"] = vet.get("note")
        out["offered"] = {"wikipedia": len(wps), "primary": len(dossiers), "primary_in_dataset": len(own), "news": len(items)}
    out["seconds"] = round(time.time() - t0, 1)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return _in_language(_for_reader(out), path, lang, ap, ua)
