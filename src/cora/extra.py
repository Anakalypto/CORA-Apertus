"""Add 200 secondary and tertiary sources to the demo set (original archive fields only).

The expected source level comes from archival evidence (form, title conventions), NOT from Apertus, so
these records test the source-level classification that the first 100 (all primary) could not test.
Most are old (end date before 1940) and textual: press articles and studies (secondary), registers,
indexes and repertories (tertiary). Pools mix item-level documents and dossiers; each record keeps its level.
"""
import json
import random

from . import lindas

DOSSIER = "<https://culture.ld.admin.ch/ais/vocabularies/recordSetTypes/10008>"
OLD = '?s rico:isAssociatedWithDate ?d . ?d rico:beginningDate ?b . OPTIONAL { ?d rico:endDate ?e } FILTER(STR(COALESCE(?e, ?b)) < "1940")'
NEW = '?s rico:isAssociatedWithDate ?d . ?d rico:beginningDate ?b FILTER(STR(?b) >= "1940")'
PRESS = 'FILTER(REGEX(?t, "Zeitungsartikel|Zeitungsausschnitt|Presseartikel|Pressestimmen|Zeitungsberichte|Presseberichte|Pressekommentare|articles de (presse|journaux)|coupures de presse", "i"))'
STUDY = 'FILTER(REGEX(?t, "(Studie[n ]|Abhandlung|Denkschrift|Geschichte des |Geschichte der |Darstellung de|Monographie|Dissertation|étude sur|mémoire sur)", "i"))'
REGISTER = 'FILTER(REGEX(?t, "^(Register|Verzeichnis|Index|Inventar|Katalog|Repertorium|Generalregister|Sachregister|Namensregister|Répertoire|Inventaire|Table des)", "i"))'

POOLS = {
    # name: (expected level, where-clause body using ?s/?t, n_old, n_new)
    "secondary_press": ("secondary", f'{{ ?s sld:form ?f FILTER(REGEX(?f, "Zeitung", "i")) ?s rico:title ?t }} UNION {{ ?s rico:hasRecordSetType {DOSSIER} ; rico:title ?t {PRESS} }}', 51, 9),
    "secondary_study": ("secondary", f'?s rico:title ?t {STUDY} FILTER NOT EXISTS {{ ?s rico:hasRecordSetType <https://culture.ld.admin.ch/ais/vocabularies/recordSetTypes/10017> }}', 34, 6),
    "tertiary_register": ("tertiary", f'{{ ?s rico:title ?t {REGISTER} ?s rico:hasRecordSetType {DOSSIER} }} UNION {{ ?s a rico:Record ; sld:form "Buch" ; rico:title ?t FILTER(REGEX(?t, "Repertorium|Register", "i")) }}', 85, 15),
}


def run(cfg, seed: int = 2026) -> None:
    data_dir = cfg["paths"]["data_dir"]
    raw_path = data_dir / "records_raw.json"
    existing = json.loads(raw_path.read_text(encoding="utf-8"))
    have = {r["id"] for r in existing}
    rng = random.Random(seed)
    picked, stats = [], {}
    for name, (level, body, n_old, n_new) in POOLS.items():
        old = sorted(lindas._ids(f"{body} . {OLD}") - have)
        new = sorted(lindas._ids(f"{body} . {NEW}") - have - set(old))
        stats[name] = {"old_pool": len(old), "new_pool": len(new)}
        take_old = rng.sample(old, min(n_old, len(old)))
        take_new = rng.sample(new, min(n_new + (n_old - len(take_old)), len(new)))
        picked += [{"id": i, "stratum": name, "expected_source_level": level, "pre_1940": True} for i in take_old]
        picked += [{"id": i, "stratum": name, "expected_source_level": level, "pre_1940": False} for i in take_new]
        have |= set(take_old) | set(take_new)
    recs = lindas.fetch_records([p["id"] for p in picked])
    meta = {p["id"]: p for p in picked}
    for r in recs:
        r.update({k: meta[r["id"]][k] for k in ("stratum", "expected_source_level", "pre_1940")})
    (data_dir / "sample_extra.json").write_text(json.dumps({"seed": seed, "pools": stats, "sample": picked}, indent=1), encoding="utf-8")
    raw_path.write_text(json.dumps(existing + recs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  added {len(recs)} records ({sum(1 for p in picked if p['pre_1940'])} ending before 1940); pools {stats}")
