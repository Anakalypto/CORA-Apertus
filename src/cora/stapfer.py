"""Stapfer-Enquête (1799): Apertus extraction vs the University of Bern datafication.

Source: opendata.swiss "The Stapfer-Enquête: schooling in Switzerland 1799" (Swiss Federal Archives,
open use), SQL dump stapferappdb_final.sql.zip. Apertus reads ONLY the transcribed answers of a
response sheet and extracts the fields the Bern team coded by hand; we compare field by field, across
historical spellings ("Tachsen" = Dachsen). Cases and results are stored one file per response sheet.
"""
import difflib
import json
import random
import re
import unicodedata
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from . import config

from . import store

DUMP_URL = "https://sfa-laboratory.ch/Hackathon/Stapfer/stapferappdb_final.sql.zip"
_ESC = {"n": "\n", "r": "\r", "t": "\t", "0": "\0"}


def _parse_values(s: str, i: int):
    """Parse the tuples of one MySQL `INSERT ... VALUES (...),(...);` statement from position i."""
    rows, row, n = [], [], len(s)
    while i < n:
        c = s[i]
        if c == "(":
            row, i = [], i + 1
        elif c == ")":
            rows.append(row)
            i += 1
        elif c == "'":
            j, buf = i + 1, []
            while True:
                ch = s[j]
                if ch == "\\":
                    buf.append(_ESC.get(s[j + 1], s[j + 1]))
                    j += 2
                elif ch == "'" and s[j + 1] == "'":
                    buf.append("'")
                    j += 2
                elif ch == "'":
                    break
                else:
                    buf.append(ch)
                    j += 1
            row.append("".join(buf))
            i = j + 1
        elif c == ";":
            return rows, i + 1
        elif c in ", \n\r\t":
            i += 1
        else:
            m = re.match(r"[^,)]+", s[i:i + 200])
            tok = m.group(0).strip()
            if tok == "NULL":
                val = None
            elif re.fullmatch(r"-?\d+", tok):
                val = int(tok)
            elif re.fullmatch(r"-?\d+\.\d+", tok):
                val = float(tok)
            else:
                val = tok
            row.append(val)
            i += len(m.group(0))
    return rows, i


def load_dump(sql: str) -> dict[str, list[dict]]:
    cols = {m.group(1): re.findall(r"^\s+`(\w+)`", m.group(2), re.M)
            for m in re.finditer(r"CREATE TABLE `(\w+)` \((.*?)\n\) ENGINE", sql, re.S)}
    tables: dict[str, list[dict]] = {}
    for m in re.finditer(r"INSERT INTO `(\w+)` (?:\([^)]*\) )?VALUES\s*", sql):
        rows, _ = _parse_values(sql, m.end())
        tables.setdefault(m.group(1), []).extend(dict(zip(cols[m.group(1)], r)) for r in rows)
    return tables


def build_cases(t: dict) -> list[dict]:
    """One case per transcription describing exactly one school: answer text + Bern reference fields."""
    q = {f["id_frage"]: f for f in t["t_frage"]}
    answers, schools, lehrer_of = {}, {}, {}
    for a in t["t_antwort"]:
        if a.get("antwort"):
            answers.setdefault(a["f_id_transkription"], []).append(a)
    for s in t["t_schule"]:
        schools.setdefault(s["f_id_transkription"], []).append(s)
    ort = {o["id_ort"]: o for o in t["t_ort"]}
    typ = {x["id_schultyp"]: x["schultyp"] for x in t["t_schultyp"]}
    pupils = {p["id_schueler"]: p for p in t["t_schueler"]}
    teachers = {l["id_lehrer"]: l for l in t["t_lehrer"]}
    for r in t["r_lehrer_schule"]:
        lehrer_of.setdefault(r["f_id_schule"], []).append(teachers.get(r["f_id_lehrer"]))
    cases = []
    for tr in t["t_transkription"]:
        tid = tr["id_transkription"]
        if len(schools.get(tid, [])) != 1 or tid not in answers:
            continue
        s = schools[tid][0]
        o, p = ort.get(s["f_id_ort"]) or {}, pupils.get(s["f_id_schueler"]) or {}
        ls = [l for l in lehrer_of.get(s["id_schule"], []) if l]
        l = ls[0] if len(ls) == 1 else {}
        lines = []
        for a in sorted(answers[tid], key=lambda a: a["id_antwort"]):
            f = q.get(a["f_id_frage"], {})
            lines.append(f'[{f.get("frage_nummer", "?")}] {f.get("frage", "")}: {a["antwort"]}')
        cases.append({
            "id": tid,
            "signature": tr.get("transkription_quelle_signatur"),
            "text": "\n".join(lines),
            "reference": {
                "place": o.get("ort_name"),
                "canton_1799": o.get("ort_kanton_1799"),
                "school_type": typ.get(s.get("f_id_schultyp")),
                "confession": s.get("schule_konfession"),
                "teacher_name": " ".join(filter(None, [l.get("lehrer_vorname"), l.get("lehrer_name")])) or None,
                "teacher_age": l.get("lehrer_alter"),
                "teacher_marital_status": l.get("lehrer_zivilstand"),
                "teacher_since": l.get("lehrer_seit"),
                "pupils_winter": p.get("schueler_anzahl_winter"),
                "pupils_summer": p.get("schueler_anzahl_sommer"),
                "author_name": " ".join(filter(None, [tr.get("transkription_verfasser_vorname"),
                                                      tr.get("transkription_verfasser_name")])) or None,
                "date_written": str(tr.get("transkription_datum_schreiben") or "") or None,
            },
        })
    return cases


FIELDS = ["place", "canton_1799", "school_type", "confession", "teacher_name", "teacher_age",
          "teacher_marital_status", "teacher_since", "pupils_winter", "pupils_summer", "author_name", "date_written"]

SYSTEM = """You are a historian datafying the Stapfer-Enquête (1799), a survey of Swiss schools.
You receive the transcribed answers of ONE response sheet (German or French, 1799 spelling).
Extract only what the text states. Use null when the text does not say it. Never guess.
Return one JSON object."""

SCHEMA = {
    # Coding scheme of the University of Bern datafication (t_schultyp, konfession, zivilstand).
    "place": "<modern municipality or hamlet name of the school place, in today's spelling>",
    "place_as_written": "<as in the text>",
    "canton_1799": "<Helvetic canton of 1799, e.g. Bern, Léman, Waldstätten, Säntis, or null>",
    "school_type": "<one of: Niedere Schule | Höhere Schule/Lateinschule | Vermengte Schule/niedere Schule | Vermengte Schule/höhere Schule>",
    "confession": "<Reformiert | Katholisch, from the parish or the text>",
    "teacher_name": "<first and last name>", "teacher_age": "<integer years>",
    "teacher_marital_status": "<ledig | verheiratet | verwitwet | Zölibat | keine Angabe — only if stated, else keine Angabe>",
    "teacher_since": "<integer: number of years he has been teaching (convert 'since 1789' to 1799-1789; under a year = 1)>",
    "pupils_winter": "<integer>", "pupils_summer": "<integer>", "author_name": "<who wrote the answers>",
    "date_written": "<YYYY-MM-DD>", "evidence": {"<field>": "<short quote>"},
}


def messages(case: dict) -> list[dict]:
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Answers:\n" + case["text"][:9000] + "\n\nReturn:\n"
             + json.dumps(SCHEMA, ensure_ascii=False)}]


def _fold(v) -> str:
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# 1799 spelling vs today's: "Tachsen" = Dachsen, "Riggispärg" = Riggisberg, "Oberweil" = Oberwil, "Bubenreüthi" = Bubenrüti.
_HIST = [(r"ß", "ss"), (r"[äæ]|ae", "e"), (r"[öœ]|oe", "e"), (r"e[uü]|äu", "ü"), (r"ue", "ü"), (r"y", "i")]
_HIST_ASCII = [(r"(?<=[a-z])h(?![aeiou])|(?<=[aeiou])h", ""), (r"th", "t"), (r"rh", "r"), (r"ph", "f"), (r"dt", "t"), (r"ck", "k"),
               (r"tz", "z"), (r"c(?=[aou])", "k"), (r"qu", "kw"), (r"v", "f"), (r"ei|ai", "i"), (r"p", "b"), (r"t", "d"),
               (r"k", "g"), (r"(.)\1+", r"\1")]


def historical_key(v) -> str:
    """Spelling-independent key: umlauts, ß, th/rh/ph/ck/dt, ei/ai/y, eu/ue, voiced/voiceless consonants
    (p/b, t/d, k/g), silent h and doubled letters folded; spaces, hyphens and dots removed."""
    s = str(v).lower()
    for a, b in _HIST:
        s = re.sub(a, b, s)
    s = re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode())
    for a, b in _HIST_ASCII:
        s = re.sub(a, b, s)
    return s


def _tokens_match(ref: str, got: str, key) -> bool:
    """Names of 2+ words: at least half of the reference's words appear in the extraction; "J." or "Joh."
    stands for Johann. (A one-word place must match as a whole: "Wil" is not "Weil am Rhein".)"""
    ta, tb = [key(t) for t in _fold(ref).split()], [key(t) for t in _fold(got).split()]
    ta, tb = [t for t in ta if t], [t for t in tb if t]
    if len(ta) < 2:
        return False
    hit = sum(1 for a in ta if any(a == b or (len(b) <= 3 and a.startswith(b)) for b in tb))
    return bool(ta) and hit / len(ta) >= 0.5


def compare(ref, got, historical: bool = True) -> str:
    """match | mismatch | missed (Bern has it, Apertus null) | extra (only Apertus) | both_empty.
    Text fields match across historical spellings unless historical=False (exact spelling)."""
    empty = lambda v: v in (None, "", 0) or (isinstance(v, str) and v.strip().lower() in ("null", "none", "keine angabe"))
    if empty(ref) and empty(got):
        return "both_empty"
    if empty(ref):
        return "extra"
    if empty(got):
        return "missed"
    if isinstance(ref, (int, float)):
        m = re.search(r"-?\d+(\.\d+)?", str(got))
        if not m:
            return "mismatch"
        return "match" if abs(float(m.group(0)) - float(ref)) <= max(1, 0.05 * float(ref)) else "mismatch"
    a, b = _fold(ref), _fold(got)
    if a == b or (a and a in b) or (b and b in a):
        return "match"
    ka, kb = historical_key(ref), historical_key(got)
    if not historical or not ka or not kb:  # exact spelling, or no letters to compare (dates, codes)
        ta, tb = set(a.split()), set(b.split())
        return "match" if ta and len(ta & tb) / len(ta) >= 0.5 else "mismatch"
    if ka and (ka == kb or min(len(ka), len(kb)) >= 5 and (ka in kb or kb in ka)):  # "Wil" is not "Weil am Rhein"
        return "match"
    if min(len(ka), len(kb)) >= 6 and difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.8:  # one letter dropped or added
        return "match"
    return "match" if _tokens_match(ref, got, historical_key) else "mismatch"


def load_cases(out_dir) -> list[dict]:
    """The 1,562 single-school response sheets, one file per sheet in stapfer/cases/ (built from the dump once)."""
    cases = store.Entries(out_dir / "cases.json")
    if not cases.ids():
        zpath = out_dir / "stapferappdb_final.sql.zip"
        if not zpath.exists():
            urllib.request.urlretrieve(DUMP_URL, zpath)
        z = zipfile.ZipFile(zpath)
        cases.write_all(build_cases(load_dump(z.read(z.namelist()[0]).decode("utf-8", "replace"))))
    return cases.all()


def summarize(rows: list[dict], **meta) -> dict:
    summary = meta | {"errors": sum(1 for r in rows if "error" in r), "fields": {}}
    for f in FIELDS:
        rs = [r["result"][f] for r in rows if "result" in r]
        cnt = {k: rs.count(k) for k in ("match", "mismatch", "missed", "extra", "both_empty")}
        scored = cnt["match"] + cnt["mismatch"] + cnt["missed"]
        cnt["accuracy_where_bern_has_value"] = round(cnt["match"] / scored, 3) if scored else None
        exact = sum(compare(r["reference"].get(f), r["apertus"].get(f), historical=False) == "match" for r in rows if "result" in r)
        cnt["accuracy_exact_spelling"] = round(exact / scored, 3) if scored else None
        summary["fields"][f] = cnt
    return summary


def save_comparison(out_dir, name: str, summary: dict, rows: list[dict]) -> None:
    """Results: one file per response sheet in stapfer/<name>/, the summary in stapfer/<name>_summary.json."""
    store.write_entries(out_dir / f"{name}.json", [r for r in rows if "id" in r])
    (out_dir / f"{name}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


def load_comparison(out_dir, name: str) -> tuple[dict, list[dict]]:
    path = out_dir / f"{name}.json"
    if path.exists():  # not split yet: the old single file {"summary", "rows"}
        old = json.loads(path.read_text(encoding="utf-8"))
        save_comparison(out_dir, name, old["summary"], old["rows"])
    return json.loads((out_dir / f"{name}_summary.json").read_text(encoding="utf-8")), store.read_entries(path)


def rescore(cfg, name: str = "comparison") -> dict:
    """Score stored extractions again (no model call), e.g. after a change to compare()."""
    out_dir = cfg["paths"]["data_dir"] / "stapfer"
    old, rows = load_comparison(out_dir, name)
    for r in rows:
        if "result" in r:
            r["result"] = {f: compare(r["reference"].get(f), r["apertus"].get(f)) for f in FIELDS}
    summary = summarize(rows, **{k: v for k, v in old.items() if k not in ("errors", "fields")})
    save_comparison(out_dir, name, summary, rows)
    return summary


def run(cfg, n: int = 40, seed: int = 42) -> None:
    from .apertus import Apertus
    out_dir = cfg["paths"]["data_dir"] / "stapfer"
    out_dir.mkdir(exist_ok=True)
    cases = load_cases(out_dir)
    sample = random.Random(seed).sample(sorted(cases, key=lambda c: c["id"]), n)
    l = cfg["llm"]
    ap = Apertus(l["base_url"], l["api_key"], config.model_for(cfg, "stapfer"), 0.0, 1500, l["retries"])

    def one(c):
        try:
            got, meta = ap.chat_json(messages(c))
        except Exception as e:
            return {"id": c["id"], "error": repr(e)}
        return {"id": c["id"], "signature": c["signature"], "reference": c["reference"],
                "apertus": {f: got.get(f) for f in FIELDS} | {"place_as_written": got.get("place_as_written")},
                "evidence": got.get("evidence"),
                "result": {f: compare(c["reference"].get(f), got.get(f)) for f in FIELDS},
                "seconds": meta["seconds"]}

    with ThreadPoolExecutor(l["workers"]) as pool:
        rows = list(pool.map(one, sample))
    summary = summarize(rows, cases_available=len(cases), sampled=n, seed=seed, model=config.model_for(cfg, "stapfer"))
    save_comparison(out_dir, "comparison", summary, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
