"""Context of one federal consultation, explained on demand by Apertus from numbered sources.

Sources, each cited sentence by sentence:
  C#  the consultation record itself (Federal Chancellery metadata, opendata.swiss)          – evidence
  O#  its outcome: popular vote (Swissvotes) or act of the Official Compilation (Fedlex)      – evidence
  A#  Federal Archives dossiers whose title names the project (LINDAS)                       – evidence (other units)
  Y#  key events of Swiss history around that year (data/years/events.json, curated)         – context
  W#  English Wikipedia articles found for the project (REST summary, CC BY-SA)              – context, tertiary
Sentences with no valid citation are kept and marked "inferred". The result is cached per consultation and language.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import i18n, topic, years
from .outcomes import GENERIC

SYSTEM = """You explain ONE Swiss federal consultation procedure (Vernehmlassung) to a curious reader, in 3 short paragraphs.
Use only the numbered sources: [C#] the consultation record, [O#] what became of it, [A#] files of the Federal Archives,
[Y#] events of the period, [W#] Wikipedia. Ignore any source that is not about this project.
Paragraph 1: what the proposal was about and who was consulted. Paragraph 2: the context of the time: why this came up
then, which debates or events it belongs to. Paragraph 3: what became of it, and, if it failed or no act was found, what
the sources say about why; if they say nothing, say that the reason is not documented here.
1-3 sentences per paragraph. Every sentence lists the sources it relies on. If you add something no source supports,
give that sentence no sources. Never call a project failed unless a source says so. Answer in {language}.
Return one JSON object."""
VERSION = 1


def _stems(title: str) -> list[str]:
    """The two most specific words of the title, as written (umlauts kept), for the archive title search."""
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ]{7,}", title) if w.lower() not in GENERIC
             and not w.lower().startswith(("änderung", "aenderung", "bundes", "teilrevision", "verordnung", "entwurf"))]
    words = sorted(dict.fromkeys(words), key=len, reverse=True)[:2]
    return [re.sub(r"(es|en|s)$", "", w) if len(w) > 9 else w for w in words]


def sources(c: dict, data_dir, ua: str) -> list[dict]:
    src = []
    fields = [("Title", c.get("title")), ("Type of act", c.get("type")), ("Year", c.get("year")),
              ("Department", c.get("department")), ("Office", c.get("office")),
              ("Consultation period", " – ".join(x for x in (c.get("start"), c.get("end")) if x)),
              ("Consulted", (c.get("addressees") or "").replace("\n", "; ")), ("Federal Gazette", c.get("bbl")),
              ("Federal Council protocol", c.get("br_protocol")), ("Archive records", c.get("archive_records")),
              ("Documents", c.get("document_types"))]
    src.append({"ref": "C1", "kind": "C", "tier": "record (Federal Chancellery)", "label": f"Consultation no. {c['nr']}",
                "text": "; ".join(f"{k}: {v}" for k, v in fields if v)})
    o = c.get("outcome") or {}
    if o.get("status") in ("accepted_by_vote", "rejected_by_vote"):
        src.append({"ref": "O1", "kind": "O", "tier": "evidence (Swissvotes)", "label": "Popular vote", "url": o.get("url"),
                    "text": f"{o['label']}. {o.get('detail') or ''}"})
    elif o.get("status") == "adopted":
        a = o["act"]
        src.append({"ref": "O1", "kind": "O", "tier": "evidence (Fedlex, Official Compilation)", "label": a["title"], "url": a["url"],
                    "text": f"Act of the Official Compilation: {a['title']}, dated {a['date']}"
                            + (f", in force from {a['in_force']}" if a.get("in_force") else "") + (f" ({a['as_ref']})" if a.get("as_ref") else "")})
    else:
        src.append({"ref": "O1", "kind": "O", "tier": "search result", "label": "Outcome",
                    "text": (o.get("label") or "Outcome not determined") + ". " + (o.get("detail") or "")})
    stems = _stems(c.get("title") or "")
    title_en = c.get("title_en") or ""

    def wiki():
        try:
            cands = topic.wikipedia_candidates(f"{title_en} Switzerland", ua, 3) if title_en else []
        except Exception:
            return []
        return [p for p in (topic.wikipedia_page(x["title"], ua) for x in cands[:2]) if p and p.get("extract")]

    def dossiers():
        out = []
        for s in stems:
            try:
                out += topic.archive_dossiers(s, 8)
            except Exception:
                pass
        return out

    with ThreadPoolExecutor(2) as pool:
        wf, df = pool.submit(wiki), pool.submit(dossiers)
        wp, units = wf.result(), df.result()
    near = sorted((e for e in years.load_events(data_dir) if c.get("year") and e["year"] - 3 <= c["year"] <= e["end"] + 3),
                  key=lambda e: abs(e["year"] - c["year"]))[:4]
    for i, u in enumerate(units[:6], 1):
        src.append({"ref": f"A{i}", "kind": "A", "tier": "Federal Archives unit", "label": u["title"], "url": u["portal_url"],
                    "text": f"{u['title']} ({u.get('date') or 'undated'}; {u.get('reference_code') or ''})"})
    for i, e in enumerate(near, 1):
        src.append({"ref": f"Y{i}", "kind": "Y", "tier": "context (curated events)", "label": f"{e['year']}: {e['title']}",
                    "url": e.get("hls"), "text": f"{e['year']}" + (f"–{e['end']}" if e["end"] != e["year"] else "") + f": {e['title']}. {e.get('summary') or ''}"})
    for i, p in enumerate(wp, 1):
        src.append({"ref": f"W{i}", "kind": "W", "tier": "tertiary (Wikipedia, CC BY-SA)", "label": p["title"], "url": p["url"],
                    "text": f"{p['title']}: {(p.get('extract') or '')[:1000]}"})
    return src


def explain(c: dict, cfg, ap, lang: str = "en") -> dict:
    cache_dir = cfg["paths"]["data_dir"] / "consultations" / "context_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{c['nr']}.{lang}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("version") == VERSION:
            return cached
    src = sources(c, cfg["paths"]["data_dir"], cfg["enrich"]["user_agent"])
    sent = {"text": "<sentence>", "sources": ["<C#|O#|A#|Y#|W#>"]}
    schema = {"paragraph_1_the_proposal": [sent, sent], "paragraph_2_context_of_the_time": [sent, sent, sent],
              "paragraph_3_what_became_of_it": [sent, sent]}
    user = "Sources:\n" + "\n".join(f"[{s['ref']}] {s['text'][:1000]}" for s in src) + "\n\nReturn:\n" + json.dumps(schema)
    raw, meta = ap.chat_json([{"role": "system", "content": SYSTEM.format(language=i18n.language(lang))},
                              {"role": "user", "content": user}])
    allowed = {s["ref"] for s in src}
    paras = []
    for key in sorted(k for k in raw if k.startswith("paragraph")):
        sents = []
        for s in raw[key] if isinstance(raw[key], list) else []:
            if isinstance(s, dict) and str(s.get("text", "")).strip():
                ok = [x for x in (str(r).strip("[] ") for r in s.get("sources") or []) if x in allowed]
                sents.append({"text": s["text"].strip(), "sources": ok, "inferred": not ok})
        if sents:
            paras.append(sents)
    used = {x for p in paras for s in p for x in s["sources"]}
    out = {"nr": c["nr"], "lang": lang, "version": VERSION, "generated": True, "model": meta.get("model"),
           "seconds": round(meta.get("seconds", 0), 1), "paragraphs": paras,
           "sources": [s for s in src if s["ref"] in used], "offered": len(src),
           "inferred_sentences": sum(s["inferred"] for p in paras for s in p)}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
