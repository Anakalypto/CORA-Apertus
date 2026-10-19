"""The website in the languages of Switzerland, translated by Apertus.

UI catalog: the interface text is read straight from the front end (site/index.html and site/*.js):
static text of HTML templates and string literals, with every ${…} turned into a {0}, {1} placeholder, plus
attribute text (placeholder, title, aria-label). Apertus translates the catalog once per language; the result is
stored in data/i18n/<lang>.json and strings added to the front end later are translated when first requested.
The page then translates only text that matches the catalog: record titles, archive metadata, names and quotes
never do, and stay in their original language. Text Apertus writes for the reader is generated in the reader's
language instead (see the `lang` parameter of the API).
"""
import html
import json
import re
import threading
import time
from pathlib import Path

LANGS = {"en": "English", "de": "Deutsch", "fr": "Français", "it": "Italiano", "rm": "Rumantsch"}
LANGUAGE_NAME = {"en": "English", "de": "German", "fr": "French", "it": "Italian",
                 "rm": "Romansh (Rumantsch Grischun, the standard written form)"}


def language(lang) -> str:
    """Prompt name of a UI language code (unknown codes fall back to English)."""
    return LANGUAGE_NAME[code(lang)]


def code(lang) -> str:
    """A supported language code; anything else (None, a FastAPI Query default when an endpoint is called as a
    function, an unknown code) is English."""
    lang = lang.lower() if isinstance(lang, str) else "en"
    return lang if lang in LANGS else "en"


# ----------------------------------------------------------------------------------------------- extraction
def _lex(src: str):
    """Yield ("template", parts) and ("string", text) tokens of JavaScript source; parts alternate text / expression."""
    i, n, prev = 0, len(src), ""
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            i = src.find("\n", i)
            i = n if i < 0 else i
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'":
            j, buf = i + 1, []
            while j < n and src[j] != c:
                if src[j] == "\\":
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                if src[j] == "\n":
                    break
                buf.append(src[j])
                j += 1
            yield "string", _unescape("".join(buf))
            i, prev = j + 1, "x"
            continue
        if c == "`":
            parts, i = _template(src, i + 1)
            yield "template", parts
            prev = "x"
            continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%<>~^" + "\n":  # a regular expression literal
            j, cls = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                elif src[j] == "/" and not cls:
                    break
                j += 1
            i, prev = j + 1, "x"
            continue
        if not c.isspace():
            prev = c if not (c.isalnum() or c in "_$") else ("x" if not src[max(0, i - 6):i + 1].endswith("return") else "(")
        i += 1


def _unescape(s: str) -> str:
    try:
        return json.loads('"' + s.replace('"', '\\"').replace("\\'", "'") + '"')
    except ValueError:
        return s


def _template(src: str, i: int):
    """Parse a template literal starting after the backtick; return (parts, index after the closing backtick)."""
    parts, buf, n = [], [], len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            buf.append(src[i + 1] if i + 1 < n else "")
            i += 2
        elif c == "`":
            parts.append("".join(buf))
            return parts, i + 1
        elif src.startswith("${", i):
            parts.append("".join(buf))
            buf, depth, j = [], 1, i + 2
            while j < n and depth:  # the expression may hold strings and nested templates
                if src[j] == "`":
                    _, j = _template(src, j + 1)
                    continue
                if src[j] in "\"'":
                    q, j = src[j], j + 1
                    while j < n and src[j] != q:
                        j += 2 if src[j] == "\\" else 1
                    j += 1
                    continue
                depth += {"{": 1, "}": -1}.get(src[j], 0)
                j += 1
            parts.append(src[i + 2:j - 1])
            i = j
        else:
            buf.append(c)
            i += 1
    return parts, i


ATTR = re.compile(r'\b(?:placeholder|title|aria-label|alt)="([^"]*)"')
CODEY = re.compile(r"^[#./]|^[a-z]+[A-Z]|[{}=;]|=>|^https?:|\.(js|css|json|png|ico|svg)$|^[\w-]+:[\w-]|^[a-z0-9_-]+$")


def _keep(text: str) -> bool:
    t = text.strip()
    if len(t) < 2 or len(t) > 400 or not re.search(r"[A-Za-zÀ-ÿ]{2}", re.sub(r"\{\d+\}", "", t)):
        return False
    if " " not in t and (CODEY.search(t) or re.search(r"[./()_…]|^[a-z]{2}-[A-Z]{2}$", t)):  # identifiers, selectors, CSS, URLs, MIME types
        return False
    return True


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _segments(parts: list[str]) -> list[str]:
    """Visible text segments of one template (text between tags), with ${…} as {0}, {1}…; attribute texts too."""
    marked = "".join(p if k % 2 == 0 else f"\x00{k // 2}\x00" for k, p in enumerate(parts))
    out = []
    for attr in ATTR.findall(marked):
        out.append(attr)
    for seg in re.split(r"<[^>]*>", marked):
        out.append(seg)
    keys = []
    for s in out:
        s = _norm(s)
        idx = {}
        s = re.sub(r"\x00(\d+)\x00", lambda m: "{%d}" % idx.setdefault(m.group(1), len(idx)), s)
        if re.fullmatch(r"(\{\d+\}\s*)+", s or "{0}"):
            continue
        if _keep(s):
            keys.append(s)
    return keys


def extract(site_dir: Path) -> list[str]:
    """Catalog of UI strings of the front end, in order of appearance."""
    keys = []
    for name in ["index.html", *sorted(x.name for x in site_dir.glob("*.js"))]:  # app.js, i18n.js, oral.js …
        p = site_dir / name
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        if name.endswith(".html"):
            body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<head>.*?</head>", " ", src, flags=re.S)
            keys += [k for k in _segments([body]) if k]
            continue
        keys += _js_keys(src)
    keys += vocabulary()
    return list(dict.fromkeys(k for k in keys if k and not JUNK.search(k) and k not in CODE_NAMES))


CODE_NAMES = {"$id", "$type", "Multi", "Feature", "FeatureCollection", "LineString", "Point", "Escape", "POST", "GET", "Enter"}


# single lowercase words the pages show as labels (the extractor skips such words as likely code)
SHOWN_WORDS = ["accepted", "rejected", "upcoming", "inferred", "unverified", "supported", "partial", "closed", "unknown",
               "generated", "imagined", "evidence", "context", "record", "derived", "apertus", "gazetteer", "wikidata"]


def vocabulary() -> list[str]:
    """Controlled vocabularies the pages display (document types, media, source levels, vote types …)."""
    from . import classify, consultations, referendum
    words = [*classify.DOCUMENT_TYPES, *classify.MEDIA, *classify.SOURCE_LEVELS, *classify.PLACE_ROLES,
             *classify.EVENT_TYPES, *sorted(classify.PERSON_ROLES), *referendum.LEGAL_FORM.values(),
             *referendum.REC_LABEL.values(), *consultations.TOPICS, *SHOWN_WORDS]
    return [w for w in words if isinstance(w, str) and w.strip()]


JUNK = re.compile(r"^(use strict|[.#!\[][^ ]*( [a-z.#\[\]=\"-]+)*)$|^[a-z]+\.[a-z]+$")


def _js_keys(src: str) -> list[str]:
    keys = []
    for kind, val in _lex(src):
        if kind == "string":
            if "<" in val:
                keys += _segments([val])
            elif _keep(val):
                keys.append(_norm(val))
        else:
            keys += _segments(val)
            for expr in val[1::2]:  # templates and strings nested in ${…}
                keys += _js_keys(expr)
    return keys


# ----------------------------------------------------------------------------------------------- translation
PROMPT = """You translate the user interface of CORA, a website of the Swiss Federal Archives (archive records classified
by Apertus), from English into {language}. Keep:
- the placeholders {{0}}, {{1}} … exactly (they stand for numbers, names or other texts);
- proper names unchanged: CORA, Apertus, swisstopo, OpenStreetMap, Wikipedia, Wikidata, Dodis, LINDAS, Swissvotes,
  Gallica, Keera, CSCS, BFS, HLS, MCP, API, JSON, CSV, TSV, BM25, and party names;
- symbols, arrows and emoji (↗ ▾ ▴ ‹ › ★ 📷 …) and the same punctuation style;
- the tone: short, plain, as on an archive website. Archive terms as the Swiss Federal Archives use them.
Return one JSON object {{"t": {{"<id>": "<translation>"}}}} with every id."""

PLURAL_PROMPT = """Translate user-interface texts of CORA, a website of the Swiss Federal Archives, from English into {language}.
In each text, a placeholder glued to the end of a word and marked with ⟨ ⟩ (like "file⟨{{1}}⟩") is only the English
plural ending. For every text give two complete {language} translations: "one" (for exactly one) and "other" (for
several), each WITHOUT the marked placeholder, with nouns, adjectives and verbs in the right singular or plural form.
Keep every other placeholder ({{0}}, {{2}} …) exactly, proper names (CORA, Apertus, Wikipedia …), symbols and punctuation.
Example into German: "{{0}} file⟨{{1}}⟩ cited" -> {{"one": "{{0}} Datei zitiert", "other": "{{0}} Dateien zitiert"}}.
The texts must be in {language}, not English. Return one JSON object {{"t": {{"<id>": {{"one": "…", "other": "…"}}}}}}."""

_LOCKS: dict[str, threading.Lock] = {}
_RUNNING: set[str] = set()


def catalog_path(data_dir: Path, lang: str) -> Path:
    return data_dir / "i18n" / f"{lang}.json"


def load(data_dir: Path, lang: str) -> dict:
    p = catalog_path(data_dir, lang)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# "file{1}", "inquir{2}": a placeholder glued to a lowercase word not already ending in s is an English plural ending
# ("Apertus{0}" holds a model name, "filters{0}" a count: not plurals)
GLUED = re.compile(r"(\b[a-z]*[a-rt-z])\{(\d+)\}")


def _valid(src: str, out) -> bool:
    """Same placeholders as the source; for plural strings ({"one", "other"}) the glued ones are left out."""
    if isinstance(out, dict):
        want = sorted(set(re.findall(r"\{\d+\}", src)) - {"{%s}" % m.group(2) for m in GLUED.finditer(src)})
        english = GLUED.sub(r"", src).strip()
        return all(isinstance(out.get(f), str) and out[f].strip() and sorted(set(re.findall(r"\{\d+\}", out[f]))) == want
                   for f in ("one", "other")) and out["one"].strip() != english  # not left in English
    return isinstance(out, str) and out.strip() != "" and sorted(re.findall(r"\{\d+\}", src)) == sorted(re.findall(r"\{\d+\}", out))


def translate_missing(data_dir: Path, site_dir: Path, lang: str, ap, batch: int = 40, log=print) -> int:
    """Translate the catalog strings that the language file lacks; returns how many were added."""
    if lang == "en":
        return 0
    lock = _LOCKS.setdefault(lang, threading.Lock())
    with lock:
        keys = extract(site_dir)
        have = load(data_dir, lang)
        todo = [k for k in keys if k not in have]
        added = 0
        plural = [k for k in todo if GLUED.search(k)]
        groups = [(PLURAL_PROMPT, plural), (PROMPT, [k for k in todo if k not in plural])]
        for prompt, keys_ in groups:
            for start in range(0, len(keys_), batch):
                chunk = keys_[start:start + batch]
                items = {str(i): k for i, k in enumerate(chunk)}
                shown = {i: GLUED.sub(lambda m: m.group(1) + "⟨{%s}⟩" % m.group(2), k) if prompt is PLURAL_PROMPT else k for i, k in items.items()}
                try:
                    raw, _ = ap.chat_json([{"role": "system", "content": prompt.format(language=language(lang))},
                                           {"role": "user", "content": json.dumps({"items": shown}, ensure_ascii=False)}])
                except Exception as e:  # keep what was done; the rest is tried on the next request
                    log(f"  {lang}: batch failed ({e!r})")
                    continue
                got = next((raw[k] for k in ("t", "items") if isinstance(raw.get(k), dict)), raw)  # some answers echo "items"
                for i, k in items.items():
                    out = got.get(i)
                    if _valid(k, out):
                        have[k] = {f: out[f].strip() for f in ("one", "other")} if isinstance(out, dict) else out.strip()
                        added += 1
                p = catalog_path(data_dir, lang)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(have, ensure_ascii=False, indent=1), encoding="utf-8")
                log(f"  {lang}: {len(have)}/{len(keys)} strings")
        return added


def ensure_background(data_dir: Path, site_dir: Path, lang: str, ap_factory) -> bool:
    """Start translating missing strings in the background (once at a time per language); True if work remains."""
    if lang == "en":
        return False
    missing = [k for k in extract(site_dir) if k not in load(data_dir, lang)]
    if missing and lang not in _RUNNING:
        _RUNNING.add(lang)

        def work():
            try:
                translate_missing(data_dir, site_dir, lang, ap_factory(), log=lambda *_: None)
            finally:
                _RUNNING.discard(lang)
        threading.Thread(target=work, daemon=True).start()
    return bool(missing)


# ----------------------------------------------------------------------------------------------- generated text
def localized(cache_path: Path, lang: str, make):
    """Per-language cache next to an entry's English cache: <id>.json (English) / <id>.<lang>.json."""
    p = cache_path if lang == "en" else cache_path.with_name(f"{cache_path.stem}.{lang}.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    out = make()
    if out is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
