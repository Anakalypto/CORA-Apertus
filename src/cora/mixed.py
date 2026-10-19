"""Draw a large mixed sample across record types, source tiers and eras (original archive fields only).

Types are the form strata of lindas.sample_ids (audiovisual / still_image / other); tiers are the evidence pools of
extra.py (secondary: press, obituaries, histories; tertiary: registers and indexes); eras split on the beginning date.
Each tier gets a share of the sample, each stratum of a tier and each era of a stratum an equal share, capped at what
the archive holds; whatever a small cell cannot fill goes to the cells that still have records (water-filling).
Records already in data/ (demo, extra draws, eval200, scale1000) are never drawn again.

    python run.py mixed_sample --config src/config_batch10k.toml
"""
import json
import random

from . import extra, lindas

ERAS = {"pre1900": ("", "1900"), "1900-1939": ("1900", "1940"), "1940-1969": ("1940", "1970"),
        "1970-1999": ("1970", "2000"), "2000+": ("2000", "9999")}
FORM = {
    "audiovisual": f'?s a rico:Record ; sld:form ?f FILTER(REGEX(?f, "{lindas.AV_REGEX}", "i"))',
    "still_image": f'?s a rico:Record ; sld:form ?f FILTER(REGEX(?f, "{lindas.IMAGE_REGEX}", "i") && !REGEX(?f, "{lindas.AV_REGEX}", "i"))',
    "other": f'?s a rico:Record OPTIONAL {{ ?s sld:form ?f }} FILTER(!BOUND(?f) || !REGEX(?f, "{lindas.AV_REGEX}|{lindas.IMAGE_REGEX}", "i"))',
}
TIERS = {  # tier: (expected source level from archival evidence, strata)
    "primary": (None, FORM),
    "secondary": ("secondary", {k: extra.POOLS[k][1] for k in ("secondary_press", "secondary_obituary", "secondary_history")}),
    "tertiary": ("tertiary", {"tertiary_index": extra.POOLS["tertiary_index"][1]}),
}


def waterfill(n: int, caps: dict) -> dict:
    """Split n as evenly as possible over the keys of caps without exceeding any cap."""
    out, left = {k: 0 for k in caps}, n
    open_ = sorted(caps, key=lambda k: caps[k])
    while left > 0 and open_:
        share = max(1, left // len(open_))
        k = open_.pop(0)
        out[k] = min(caps[k], share if open_ else left)
        left -= out[k]
    return out


def _excluded(data_root, own) -> set[str]:
    """Ids of every earlier draw under data/, except this batch's own (so a re-run draws the same sample)."""
    have = set()
    for p in data_root.rglob("*.json"):
        if own in p.parents or p.name not in ("records_raw.json", "sample.json", "sample_extra.json"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        have |= {r["id"] for r in (d if isinstance(d, list) else d.get("sample", []))}
    for d in data_root.rglob("records_raw"):  # one file per record (store.py)
        if d.is_dir() and own not in d.parents:
            have |= {p.stem for p in d.glob("*.json") if not p.name.startswith("_")}
    return have


def run(cfg) -> None:
    m = cfg["mixed"]
    data_dir = cfg["paths"]["data_dir"]
    have = _excluded(data_dir.parent, data_dir)
    rng = random.Random(m["seed"])

    pools = {}  # (tier, stratum, era) -> sorted candidate ids
    for tier, (_, strata) in TIERS.items():
        for st, body in strata.items():
            for era, (lo, hi) in ERAS.items():
                f = (f'STR(?b) >= "{lo}" && ' if lo else "") + f'STR(?b) < "{hi}"'
                ids = lindas._ids(f"{body} . ?s rico:isAssociatedWithDate ?d . ?d rico:beginningDate ?b FILTER({f})")
                pools[tier, st, era] = sorted(ids - have)
                print(f"  pool {tier:9} {st:18} {era:9} {len(pools[tier, st, era]):>7}", flush=True)

    # a record matching several pools (e.g. a press clipping with form "Text") counts once, in the rarer tier
    seen = set()
    for key in sorted(pools, key=lambda k: ["tertiary", "secondary", "primary"].index(k[0])):
        pools[key] = [i for i in pools[key] if i not in seen]
        seen |= set(pools[key])

    cap = lambda t, s=None: sum(len(v) for k, v in pools.items() if k[0] == t and (s is None or k[1] == s))
    tier_n = waterfill(m["size"], {t: min(cap(t), m["size"] * m["tiers"][t] // 100) for t in TIERS})
    tier_n["primary"] += m["size"] - sum(tier_n.values())  # rounding / small tiers: the rest goes to the largest
    picked, plan = [], {}
    for tier, (level, strata) in TIERS.items():
        st_n = waterfill(tier_n[tier], {s: cap(tier, s) for s in strata})
        for st in strata:
            era_n = waterfill(st_n[st], {e: len(pools[tier, st, e]) for e in ERAS})
            for era, n in era_n.items():
                plan[f"{tier}/{st}/{era}"] = {"pool": len(pools[tier, st, era]), "drawn": n}
                picked += [{"id": i, "tier": tier, "stratum": st, "era": era, "expected_source_level": level}
                           for i in rng.sample(pools[tier, st, era], n)]
    print(f"  drew {len(picked)} records: " + ", ".join(f"{t} {n}" for t, n in tier_n.items()))
    (data_dir / "sample.json").write_text(json.dumps({"seed": m["seed"], "strategy": "mixed: tier x type x era",
                                                      "plan": plan, "sample": picked}, indent=1), encoding="utf-8")

    meta = {p["id"]: p for p in picked}
    recs = []
    ids = [p["id"] for p in picked]
    for i in range(0, len(ids), 500):  # in chunks, so a LINDAS hiccup costs one chunk, not the whole fetch
        recs += lindas.fetch_records(ids[i:i + 500])
        print(f"  fetched {len(recs)}/{len(ids)}", flush=True)
    for r in recs:
        p = meta[r["id"]]
        r.update({"stratum": p["stratum"], "tier": p["tier"], "era": p["era"], "batch": cfg["mixed"]["batch"]})
        if p["expected_source_level"]:
            r["expected_source_level"] = p["expected_source_level"]
            r["pre_1940"] = p["era"] in ("pre1900", "1900-1939")
    (data_dir / "records_raw.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  wrote records_raw.json ({len(recs)} records)")
