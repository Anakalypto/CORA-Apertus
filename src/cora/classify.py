"""Apertus classification of one archival record.

Each output field carries its provenance:
  "record"  – copied from the Federal Archives metadata,
  "derived" – computed by a deterministic rule from the record,
  "apertus" – inferred by Apertus (and checked by qc.py).
"""
import json
import re

DOCUMENT_TYPES = [
    "TV news report", "newsreel", "radio broadcast", "film", "audio recording", "photograph",
    "correspondence", "report", "minutes / protocol", "parliamentary record", "legislation / decree",
    "administrative file", "map / plan", "press article", "press release / communiqué",
    "register / index", "finding aid / inventory", "publication / book", "speech", "other",
]
MEDIA = ["text", "still image", "moving image", "sound", "mixed"]
SOURCE_LEVELS = ["primary", "secondary", "tertiary"]
PREPROCESSING = [
    "transcription_normalization", "structure_extraction", "schema_harmonization",
    "linked_data_entity_linking", "date_geolocation_parsing", "anonymization_verification",
]
PLACE_ROLES = ["created", "depicted", "published", "mentioned"]
EVENT_TYPES = ["creation", "depicted", "publication", "update", "accession", "digitisation"]

BAR_HOLDER = {"name": "Swiss Federal Archives (Schweizerisches Bundesarchiv)",
              "place": "Archivstrasse 24, 3003 Bern", "lat": 46.94198, "lon": 7.44291}


def derived_fields(rec: dict) -> dict:
    """Facts we can compute without a model: archival location, accession date, access."""
    chain = rec.get("hierarchy", [])
    stock = next((h for h in chain if h["level"] == "Stock"), None)
    accession_years = []
    for acc in rec.get("accessions", []):
        m = re.match(r"(\d{4})/", acc.get("number") or "")
        if m and m.group(1) != "1000":       # "1000/…" = legacy pre-1970s holdings, no real year
            accession_years.append(int(m.group(1)))
    return {
        "archival_location": {
            "holder": BAR_HOLDER["name"],
            "fonds": stock["title"] if stock else None,
            "fonds_reference": stock["reference_code"] if stock else None,
            "path": [h["title"] for h in reversed(chain)][1:],
            "reference_code": rec.get("reference_code"),
            "portal_url": rec.get("portal_url"),
        },
        "date_archived": str(min(accession_years)) if accession_years else None,
        "accession_numbers": [a.get("number") for a in rec.get("accessions", [])],
        "content_date_range": rec.get("date"),
    }


# The role fields pack "Label: Name (CODE)" strings ("AutorIn: Strub, Edi (AUT)\nProduktionsgesellschaft: SF").
# Apertus copied the labels into its answers ("Produktion: TSI"), so they are parsed by rule into
# {name, role} pairs before the record is shown to the model (quality report §8, recommendation 1).
ROLE_EN = {
    "autorin": "author", "autor": "author", "verfasser": "author", "produktion": "production",
    "produktionsgesellschaft": "production company", "produktionsstudio": "production studio",
    "herausgeberin": "publisher", "herausgeber": "publisher", "fotograf": "photographer",
    "moderation": "presenter", "sprecher": "narrator / speaker", "teilnehmer": "participant",
}
ROLE_CODE = {"AUT": "author", "BEAR": "editor"}
PERSON_ROLES = {"author", "editor", "photographer", "presenter", "narrator / speaker", "participant"}
_PIECE = re.compile(r"(?:^|\n|,\s*)([A-ZÄÖÜ][\wäöüÄÖÜ/ -]{1,30}):\s*")
_CODE = re.compile(r"\s*\((AUT|BEAR)\)\s*$")
_PLACEHOLDER = {"rolle", "funktion"}            # empty template "Teilnehmer: Rolle; Funktion:"


def person_name(s: str) -> str:
    """'Strub, Edi' -> 'Edi Strub'; anything else (organisations, lists with '/') unchanged."""
    m = re.fullmatch(r"\s*([^,;/]+?)\s*,\s*([^,;/]+?)\s*", s)
    return f"{m.group(2)} {m.group(1)}" if m else s.strip()


def parse_roles(text: str) -> list[dict]:
    """'AutorIn: Strub, Edi (AUT)\\nProduktion: SF' -> [{name: Edi Strub, role: author}, {name: SF, role: production}]."""
    text = re.sub(r":\s*(AUT|BEAR)\b", r" (\1)", text)     # "Trütsch, Hanspeter: AUT" -> "... (AUT)"
    marks = list(_PIECE.finditer(text))
    if not marks:
        return [{"name": text.strip(), "role": None}]
    out = []
    for m, nxt in zip(marks, marks[1:] + [None]):
        label = m.group(1).strip()
        value = text[m.end(): nxt.start() if nxt else len(text)]
        role = ROLE_EN.get(label.lower(), label.lower())
        for name in value.split(";"):
            code = _CODE.search(name)
            name = _CODE.sub("", name).strip(" ,")
            r = ROLE_CODE[code.group(1)] if code else role
            if name and not name.endswith(":") and name.lower() not in _PLACEHOLDER:
                out.append({"name": person_name(name) if r in PERSON_ROLES else name, "role": r})
    return out


def parse_speakers(text: str) -> list[str] | None:
    """Parliamentary records: 'Autor: Sprecher/Sprecherinnen: Graf, Maya;' lists who SPOKE, not who wrote."""
    if not re.match(r"\s*(?:Autor:\s*)?Sprecher/Sprecherinnen:", text):
        return None
    names = re.split(r"\s*;\s*|,\s*(?=Autor:)", re.sub(r"(?:Autor:\s*)?Sprecher/Sprecherinnen:", ";", text))
    seen = []
    for n in names:
        n = person_name(n.strip(" ,").replace(",", ", ").replace(",  ", ", "))
        if n and n not in seen:
            seen.append(n)
    return seen


def compact_record(rec: dict) -> dict:
    """What Apertus sees: every descriptive field, no URIs, role labels parsed by rule."""
    keep = ["title", "reference_code", "reference_number", "old_reference_code", "alternate_reference",
            "scope_and_content", "author", "publisher", "involved", "coverage", "form", "format",
            "thema", "country"]
    out = {k: rec[k] for k in keep if rec.get(k)}
    for k in ("author", "publisher", "involved"):
        if k in out:
            out[k] = parse_roles(out[k])
    speakers = parse_speakers(out.get("scope_and_content") or "")
    if speakers is not None:
        out.pop("scope_and_content")
        if speakers:
            out["speakers_in_debate"] = speakers
    out["date"] = rec.get("date")
    out["accessions"] = [{k: a[k] for k in ("number", "title")} for a in rec.get("accessions", [])]
    out["hierarchy_top_down"] = [f'{h["level"]}: {h["title"]} [{h["reference_code"]}]'
                                 for h in reversed(rec.get("hierarchy", []))]
    return out


SYSTEM = """You are an expert archivist at the Swiss Federal Archives (BAR/AFS) cataloguing records for an AI-ready open dataset.
You receive the metadata of ONE archival record (German, French or Italian, sometimes with broken accents shown as �).
Classify it and return ONE JSON object, nothing else. Rules:
- Only state what the metadata supports. Use null or [] when unknown. Never invent names, dates or places.
- Dates in ISO 8601 (YYYY, YYYY-MM or YYYY-MM-DD; an interval as "YYYY-MM-DD/YYYY-MM-DD").
- Source level: primary = created at the time of the events by a participant/witness/institution (footage, photographs, minutes, letters, administrative files, original broadcasts); secondary = later analysis or synthesis of primary sources (studies, retrospectives, documentaries about the past); tertiary = finding aids, indexes, registers, catalogues, compilations that point to other sources.
- Coordinates: decimal WGS84, only for places you can identify unambiguously, otherwise null.
- The archive itself (Swiss Federal Archives, Bern) is NOT a place of the document; do not list it in places nor as an organization.
- Accession numbers have the form YEAR/SERIAL (e.g. "1998/317" = entered the archives in 1998); "1000/..." marks legacy holdings whose accession year is unknown.
- Preprocessing: set needed=true ONLY if this specific record shows the problem, and cite the evidence (e.g. "title in capitals with abbreviations", "accents lost (�)", "free-text coverage field mixes places and dates", "names a private person"). Records that are already clean must get needed=false.
- The résumé must be at most 3 sentences and must not speculate: never write "likely", "possibly", "probably", "perhaps" or "may"; if something is not stated, leave it out. Describe what the record IS (e.g. an audio recording of a debate), not contents it does not show.
- Names: copy person names exactly as the metadata gives them. Never complete, expand or correct a name from your own knowledge (no added first names, titles or parties).
- Persons are named individuals only. Unnamed people or groups ("Offiziere", "soldiers of battalion 24", "a man in a bathrobe") are NOT persons; mention them in the résumé if relevant.
- Creator: when the record has an "author" field, the creator comes from it: the named author(s) if any, otherwise the production entry ("Agenturen" = news agencies, "SF", "TSI", "Visnews" ...). The "publisher" field gives the publisher, never the creator.
Archival conventions of the Swiss Federal Archives (apply them strictly):
- Parliamentary records: "speakers_in_debate" (Sprecher/Sprecherinnen) are the members who SPOKE in the debate. A speaker is not the author of the item. The author of a Motion/Postulat/Interpellation/parlamentarische Initiative is the member named in the title after the item type; a Petition of the Youth Session (Jugendsession) is authored by the Youth Session; a Federal Council bill (Geschäft des Bundesrates) by the Federal Council. The creator of the record itself is the Council (Nationalrat/Ständerat), which recorded the debate.
- Postulat, Motion, Interpellation, Anfrage/Fragestunde, parlamentarische Initiative, Standesinitiative and Petition are distinct instruments: keep the term (English: postulate, motion, interpellation, question, parliamentary initiative, cantonal initiative, petition), never translate one as another.
- The date of a parliamentary recording is the date of the debate, not the date the item was submitted.
- The fonds (Stock) and the accession title name the agency that DEPOSITED the records. It is not the creator when it postdates the record (e.g. "Nachrichtendienst des Bundes (2010-)" for a 1939-1945 photograph): then the creator is null unless the metadata names one.
- TSR/SF card-catalogue abbreviations in titles and descriptions: OPP. = opposition (Opposition), INT. = interview, DUPLEX = live link with a reporter. Expand them in title_normalized and use their meaning in the résumé."""

SCHEMA_HINT = {
    "resume": "<at most 3 sentences in {lang}, what the document is and what it shows/says>",
    "title_normalized": "<original-language title with fixed encoding/casing/abbreviations>",
    "title_en": "<English translation of the title>",
    "document_type": f"<one of {DOCUMENT_TYPES}>",
    "medium": f"<one of {MEDIA}>",
    "source_level": "<primary|secondary|tertiary>",
    "source_level_rationale": "<one sentence>",
    "creator": "<person or organisation that produced it, or null>",
    "publisher": "<who published/broadcast it, or null>",
    "commissioner": "<who ordered/commissioned it (commanditaire), or null>",
    "date_created": "<ISO date or interval when the document was made, or null>",
    "date_published": "<ISO date of publication/broadcast, or null>",
    "date_updated": "<ISO date of a later revision, or null>",
    "date_archived": "<year the record entered the Federal Archives, from the accession number, or null>",
    "languages": ["<ISO 639-1 codes of the document content>"],
    "subjects": ["<3-6 English subject keywords>"],
    "persons": [{"name": "<exactly as written in the metadata>", "role": "<role in the document>"}],
    "organizations": [{"name": "<name>", "role": "<role>"}],
    "places": [{"name": "<modern name>", "as_written": "<as in record>", "role": f"<one of {PLACE_ROLES}>",
                "country": "<ISO 3166 alpha-2>", "lat": 0.0, "lon": 0.0}],
    "preprocessing": {p: {"needed": True, "priority": "<low|medium|high>", "reason": "<short>"} for p in PREPROCESSING},
    "personal_data": {"contains_personal_data": False, "sensitivity": "<none|low|medium|high>",
                      "note": "<why; mention living private persons, health, criminal, political opinions>"},
    "story": [{"event": f"<one of {EVENT_TYPES}>", "date": "<ISO or null>", "place": "<place name or null>",
               "description": "<short>"}],
    "confidence": "<0.0-1.0 overall confidence>",
}


def build_messages(rec: dict, cfg: dict) -> list[dict]:
    opts = cfg["classify"]
    lang = {"en": "English", "fr": "French", "de": "German", "it": "Italian"}.get(opts["output_language"], "English")
    schema = json.loads(json.dumps(SCHEMA_HINT).replace("{lang}", lang))
    if not opts["resume"]:
        schema.pop("resume")
    if not opts["preprocessing"]:
        schema.pop("preprocessing")
    if not opts["story_map"]:
        schema.pop("story")
    user = ("Record metadata:\n" + json.dumps(compact_record(rec), ensure_ascii=False, indent=1)
            + "\n\nReturn a JSON object with exactly these keys:\n" + json.dumps(schema, ensure_ascii=False, indent=1))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _enum(value, allowed, default):
    if not isinstance(value, str):
        return default, False
    v = value.strip().lower()
    for a in allowed:
        if v == a.lower():
            return a, True
    for a in allowed:
        if v in a.lower() or a.lower() in v:
            return a, False
    return default, False


def normalize(raw: dict, rec: dict, cfg: dict) -> tuple[dict, list[str]]:
    """Coerce the model output into the schema; return (result, schema issues)."""
    issues = []
    out = {}
    for key in ("resume", "title_normalized", "title_en", "source_level_rationale", "creator",
                "publisher", "commissioner", "date_created", "date_published", "date_updated", "date_archived"):
        v = raw.get(key)
        if key not in raw:
            issues.append(f"missing:{key}")
        out[key] = v.strip() if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none", "unknown", "n/a") else None
    if not cfg["classify"]["resume"]:
        out.pop("resume")
    out["document_type"], ok = _enum(raw.get("document_type"), DOCUMENT_TYPES, "other")
    ok or issues.append("enum:document_type")
    out["medium"], ok = _enum(raw.get("medium"), MEDIA, "mixed")
    ok or issues.append("enum:medium")
    out["source_level"], ok = _enum(raw.get("source_level"), SOURCE_LEVELS, "primary")
    ok or issues.append("enum:source_level")

    def strlist(v):
        return [s.strip() for s in v if isinstance(s, str) and s.strip()] if isinstance(v, list) else []

    def objlist(v, keys):
        if not isinstance(v, list):
            return []
        res = []
        for o in v:
            if isinstance(o, str):
                o = {"name": o}
            if isinstance(o, dict) and isinstance(o.get("name"), str) and o["name"].strip():
                res.append({k: o.get(k) for k in keys})
        return res

    out["languages"] = [l.lower()[:2] for l in strlist(raw.get("languages"))]
    out["subjects"] = strlist(raw.get("subjects"))[:8]
    out["persons"] = objlist(raw.get("persons"), ["name", "role"])
    out["organizations"] = objlist(raw.get("organizations"), ["name", "role"])
    places = objlist(raw.get("places"), ["name", "as_written", "role", "country", "lat", "lon"])
    for p in places:
        p["role"], _ = _enum(p.get("role"), PLACE_ROLES, "mentioned")
        for c in ("lat", "lon"):
            try:
                p[c] = float(p[c]) if p.get(c) not in (None, "", 0, 0.0) else None
            except (TypeError, ValueError):
                p[c] = None
        if p["lat"] is not None and not (-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180):
            p["lat"] = p["lon"] = None
    out["places"] = places

    if cfg["classify"]["preprocessing"]:
        pre = raw.get("preprocessing") if isinstance(raw.get("preprocessing"), dict) else {}
        out["preprocessing"] = {}
        for k in PREPROCESSING:
            v = pre.get(k) if isinstance(pre.get(k), dict) else {}
            if not v:
                issues.append(f"missing:preprocessing.{k}")
            out["preprocessing"][k] = {
                "needed": bool(v.get("needed")),
                "priority": _enum(v.get("priority"), ["low", "medium", "high"], "low")[0],
                "reason": v.get("reason") if isinstance(v.get("reason"), str) else None,
            }
    pd = raw.get("personal_data") if isinstance(raw.get("personal_data"), dict) else {}
    out["personal_data"] = {
        "contains_personal_data": bool(pd.get("contains_personal_data")),
        "sensitivity": _enum(pd.get("sensitivity"), ["none", "low", "medium", "high"], "none")[0],
        "note": pd.get("note") if isinstance(pd.get("note"), str) else None,
    }
    if cfg["classify"]["story_map"]:
        story = []
        for e in raw.get("story") or []:
            if isinstance(e, dict):
                ev, _ = _enum(e.get("event"), EVENT_TYPES, "creation")
                story.append({"event": ev, "date": e.get("date"), "place": e.get("place"),
                              "description": e.get("description")})
        out["story"] = story
    try:
        out["confidence"] = max(0.0, min(1.0, float(raw.get("confidence"))))
    except (TypeError, ValueError):
        out["confidence"] = None
        issues.append("type:confidence")
    return out, issues


# --- Pass 2: evidence-based preprocessing / personal-data audit -------------------------------
# Pass 1 asked directly "is preprocessing X needed?" and Apertus answered yes for ~100% of records
# (see docs/quality_report.md). Pass 2 asks concrete, checkable yes/no questions with a quoted
# piece of evidence, and the preprocessing flags are derived from the answers by fixed rules.

AUDIT_CHECKS = {
    "encoding_damage": "Some text has broken characters (� or mangled accents such as 'GenÃ¨ve').",
    "uppercase_or_abbreviated_title": "The title is written in CAPITALS or uses cryptic abbreviations (e.g. 'OPP.LIGNE').",
    "labelled_subfields": "A free-text field packs several labelled sub-fields (e.g. 'Inhaltsangabe: … Sequenzbeschrieb: …').",
    "packed_role_fields": "The author/publisher/format field mixes several roles or key:value pairs in one string.",
    "multilingual": "The record mixes languages (e.g. a German and a French title).",
    "nonstandard_dates": "Dates are written in a non-ISO form (e.g. '1985.10.22', '15.10.1985-29.10.1985', inside free text).",
    "free_text_places": "Places are only given inside free text or in a coded/abbreviated way.",
    "named_persons": "Natural persons are named.",
    "named_organizations_or_places": "Organisations or places are named that could be linked to an authority file.",
    "private_individuals": "A named person is a private individual (not a politician, official, artist, athlete or other public figure acting publicly).",
    "sensitive_categories": "An identifiable, named person is personally concerned by health, criminal or police proceedings, intelligence files, an asylum case, religion, sexual life or political opinions (e.g. a named defendant, patient or asylum seeker). A debate, law or report ABOUT such a topic is false, and so is a politician speaking in a parliamentary debate.",
}

AUDIT_SYSTEM = """You are a data-quality auditor for the Swiss Federal Archives.
You receive the metadata of ONE archival record. For each check answer true or false and quote the
exact evidence from the metadata (max 12 words) or null when false. Be strict: answer true only when
you can quote evidence. For personal data, ask whether an identifiable PERSON is concerned, not whether
the TOPIC is sensitive: a parliamentary debate on asylum policy names no asylum seeker; an agency that
deposited the records is not a person. Set "sensitivity" by the same rule (none when no identifiable
person is concerned). Return ONE JSON object only."""


def build_audit_messages(rec: dict) -> list[dict]:
    schema = {"checks": {k: {"answer": "<true|false>", "evidence": "<quote or null>"} for k in AUDIT_CHECKS},
              "sensitivity": "<none|low|medium|high>", "note": "<one sentence on personal data>"}
    user = ("Checks:\n" + "\n".join(f"- {k}: {v}" for k, v in AUDIT_CHECKS.items())
            + "\n\nRecord metadata:\n" + json.dumps(compact_record(rec), ensure_ascii=False, indent=1)
            + "\n\nReturn:\n" + json.dumps(schema, ensure_ascii=False, indent=1))
    return [{"role": "system", "content": AUDIT_SYSTEM}, {"role": "user", "content": user}]


def _truthy(v) -> bool:
    if isinstance(v, dict):
        v = v.get("answer")
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))


# Mechanical evidence is cheaper and more reliable with rules than with a model (Apertus caught
# encoding damage in ~13% of affected records in pass 2). Final flags = Apertus OR rule.
RULE_CHECKS = ("encoding_damage", "uppercase_or_abbreviated_title", "labelled_subfields",
               "packed_role_fields", "nonstandard_dates")
_LABEL = re.compile(r"(?:^|\n|/\s)\s*[A-ZÄÖÜ][A-Za-zÄÖÜäöüéèà /-]{2,30}:\s")


def rule_checks(rec: dict) -> dict:
    text_fields = {k: rec.get(k) for k in ("title", "scope_and_content", "author", "publisher", "involved",
                                            "coverage", "format", "thema") if rec.get(k)}
    blob = json.dumps(rec, ensure_ascii=False)
    title = rec.get("title") or ""
    letters = [c for c in title if c.isalpha()]
    out = {}
    m = re.search(r".{0,20}(\ufffd|Ã[\x80-\xbf]).{0,20}", blob)
    out["encoding_damage"] = m.group(0) if m else None
    out["uppercase_or_abbreviated_title"] = title[:60] if len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.6 else None
    lab = next((f"{k}: {v[:50]}" for k, v in text_fields.items() if k != "title" and len(_LABEL.findall(v)) >= 2), None)
    out["labelled_subfields"] = lab
    packed = next((f"{k}: {rec[k][:50]}" for k in ("author", "publisher", "format") if rec.get(k)
                   and ("\n" in rec[k] or len(re.findall(r"\w:\s", rec[k])) >= 2)), None)
    out["packed_role_fields"] = packed
    exp = (rec.get("date") or {}).get("expressed") or ""
    out["nonstandard_dates"] = exp if re.search(r"\d{4}\.\d{2}\.\d{2}|\d{2}\.\d{2}\.\d{4}", exp) else None
    return out


def audit_to_flags(raw: dict, rec: dict | None = None) -> tuple[dict, dict, dict]:
    """Return (checks, preprocessing flags, personal_data) from the audit answers (+ rule checks)."""
    rc = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
    rules = rule_checks(rec) if rec else {}
    checks = {}
    for k in AUDIT_CHECKS:
        v = rc.get(k)
        ev = v.get("evidence") if isinstance(v, dict) else None
        ev = ev if isinstance(ev, str) and ev.strip().lower() not in ("null", "") else None
        model = v.get("apertus", _truthy(v)) if isinstance(v, dict) and "apertus" in v else _truthy(v)
        rule = (rules.get(k) is not None) if k in RULE_CHECKS and rec else None
        checks[k] = {"answer": bool(model or rule), "apertus": bool(model), "rule": rule,
                     "evidence": ev or (rules.get(k) if rule else None)}
    yes = lambda *ks: [k for k in ks if checks[k]["answer"]]

    def flag(keys, high=()):
        hits = yes(*keys)
        prio = "high" if any(h in hits for h in high) else ("medium" if len(hits) > 1 else "low")
        reason = "; ".join(f"{k.replace('_', ' ')} ({'rule' if checks[k]['rule'] and not checks[k]['apertus'] else 'apertus'}): "
                           f"{checks[k]['evidence'] or 'yes'}" for k in hits)
        return {"needed": bool(hits), "priority": prio if hits else "low", "reason": reason or None, "based_on": list(keys)}

    pre = {
        "transcription_normalization": flag(("encoding_damage", "uppercase_or_abbreviated_title"), high=("encoding_damage",)),
        "structure_extraction": flag(("labelled_subfields",)),
        "schema_harmonization": flag(("packed_role_fields", "multilingual")),
        "linked_data_entity_linking": flag(("named_persons", "named_organizations_or_places")),
        "date_geolocation_parsing": flag(("nonstandard_dates", "free_text_places")),
        "anonymization_verification": flag(("private_individuals", "sensitive_categories"), high=("sensitive_categories",)),
    }
    sens = _enum(raw.get("sensitivity"), ["none", "low", "medium", "high"], "none")[0]
    personal = {"contains_personal_data": checks["named_persons"]["answer"], "sensitivity": sens,
                "private_individuals": checks["private_individuals"]["answer"],
                "sensitive_categories": checks["sensitive_categories"]["answer"],
                "note": raw.get("note") if isinstance(raw.get("note"), str) else None}
    return checks, pre, personal
