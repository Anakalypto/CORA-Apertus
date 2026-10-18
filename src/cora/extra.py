"""Add 200 secondary and tertiary sources (v2, strict selection) to the demo set (original archive fields only).

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
# v2 (strict): the title must BE the thing, not mention it. The first, keyword-based draw is kept in
# data/extra_v1/: there "Verzeichnis/Inventar/Studie" mostly turned out to be primary administrative records.
PRESS = 'FILTER(REGEX(?t, "^(Zeitungsausschnitte|Zeitungsartikel|Presseartikel|Presseausschnitte|Pressestimmen|Pressekommentare|Pressebericht|Zeitungsberichte|Coupures de presse|Articles de (presse|journaux)|Ritagli)", "i"))'
OBIT = 'FILTER(REGEX(?t, "(Nachruf|Nachrufe|Nekrolog|n[ée]crolog|Gedenkrede|Gedenkschrift)", "i"))'
HIST = 'FILTER(REGEX(?t, "(^Geschichte (des|der)|Festschrift|Jubil[äa]umsschrift|Chronik (des|der)|R[üu]ckblick auf|histoire (de|du|des) |Historique)", "i"))'
BOOK = '?s a rico:Record ; sld:form "Buch" ; rico:title ?t FILTER(!REGEX(?t, "^(Band|Jahr|Register|Repertorium)", "i"))'
INDEX = 'FILTER(REGEX(?t, "^(Register zu|Register über|Register der (Akten|Gesch[äa]fte|Beschl[üu]sse|Protokolle|Verf[üu]gungen|Bundesratsbeschl[üu]sse|Vertr[äa]ge|Kreisschreiben|Eing[äa]nge)|Generalregister|Sachregister|Namenregister|Namensregister|Personenregister|Ortsregister|Index zu|Repertorium|Findmittel|Aktenverzeichnis|Inhaltsverzeichnis|Registraturplan|Ablieferungsverzeichnis|Verzeichnis der (Akten|Dossiers|Gesch[äa]fte|Protokolle|Beschl[üu]sse|Kreisschreiben|Eing[äa]nge)|Table des mati[èe]res|R[ée]pertoire|Inventaire des (archives|dossiers|actes|pi[èe]ces))", "i"))'

POOLS = {
    # name: (expected level, where-clause body using ?s/?t, n_old, n_new)
    "secondary_press": ("secondary", f'?s rico:title ?t {PRESS}', 43, 7),
    "secondary_obituary": ("secondary", f'?s rico:title ?t {OBIT}', 17, 3),
    "secondary_history": ("secondary", f'{{ ?s rico:title ?t {HIST} }} UNION {{ {BOOK} }}', 25, 5),
    "tertiary_index": ("tertiary", f'{{ ?s rico:title ?t {INDEX} }} UNION {{ ?s a rico:Record ; sld:form "Buch" ; rico:title ?t FILTER(REGEX(?t, "^(Register|Repertorium)", "i")) }}', 85, 15),
}


def run(cfg, seed: int = 2026) -> None:
    data_dir = cfg["paths"]["data_dir"]
    raw_path = data_dir / "records_raw.json"
    # replace any earlier added sources: keep only the original stratified sample
    existing = [r for r in json.loads(raw_path.read_text(encoding="utf-8")) if not r.get("expected_source_level")]
    have = {r["id"] for r in existing}
    v1 = data_dir / "extra_v1" / "sample_extra.json"
    if v1.exists():  # never re-draw a unit of the first draw
        have |= {p["id"] for p in json.loads(v1.read_text(encoding="utf-8"))["sample"]}
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
