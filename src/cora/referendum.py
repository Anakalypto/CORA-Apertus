"""Referendum estimate from party cues, women's suffrage case (1959 vs 1971).

Data: Swissvotes (Année politique suisse, University of Bern, CC BY 4.0): for every federal vote the
party recommendations (p-*) and the parties' voter shares at the time (w-*, National Council vote
shares, not seats), and the result.
Model: cue = Σ w_p·s_p / Σ w_p over parties with a known recommendation (yes=1, no=0, free/none=0.5);
yes% = α + β·cue, fitted by least squares. Confidence = leave-one-out mean absolute error.
Note: the 1959 and the 1971 votes were both cast by men only; women first voted federally after 1971.
"""
import csv
import functools
import io
import json
import re
import statistics
from . import config

PARTY_PAIRS = {"fdp": "fdp", "sps": "sp", "svp": "svp", "cvp": "cvp", "kvp": "cvp", "mitte": "mitte", "evp": "evp",
               "gps": "gps", "glp": "glp", "pda": "pda", "sd": "sd", "edu": "edu", "fps": "fps", "lega": "lega",
               "lps": "lps", "ldu": "ldu", "poch": "poch", "rep": "rep", "bdp": "bdp", "csp": "csp", "mcg": "mcg"}
CUE = {"1": 1.0, "2": 0.0, "3": 0.5, "4": 0.5, "5": 0.5, "66": 0.5}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def cue(v: dict, recs: dict | None = None, shares: dict | None = None) -> tuple[float | None, dict]:
    num = den = 0.0
    used = {}
    for p, w in PARTY_PAIRS.items():
        rec = (recs or {}).get(p, v.get(f"p-{p}"))
        share = (shares or {}).get(w, _f(v.get(f"w-{w}")))
        if rec in CUE and share:
            num += share * CUE[rec]
            den += share
            used[p] = {"rec": rec, "share": share}
    return (num / den if den else None), used


def fit(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, b


def run(cfg) -> None:
    from .apertus import Apertus
    data_dir = cfg["paths"]["data_dir"]
    rows = list(csv.DictReader(io.StringIO(open(_csv(cfg), "rb").read().decode("utf-8-sig")), delimiter=";"))
    pts = []
    for v in rows:
        y = _f(v.get("volkja-proz"))
        recs = [v.get(f"p-{p}") for p in PARTY_PAIRS]
        if y is None or any(r in ("8", "9") for r in recs):  # skip initiative/counter-proposal preference votes
            continue
        c, used = cue(v)
        if c is not None and len(used) >= 3:
            pts.append({"anr": v["anr"], "date": v["datum"], "title": v["titel_kurz_d"], "cue": round(c, 4), "yes": y})
    xs, ys = [p["cue"] for p in pts], [p["yes"] for p in pts]
    a, b = fit(xs, ys)
    loo = []
    for i in range(len(pts)):
        ai, bi = fit(xs[:i] + xs[i + 1:], ys[:i] + ys[i + 1:])
        loo.append(abs(ai + bi * xs[i] - ys[i]))
        pts[i]["predicted_loo"] = round(ai + bi * xs[i], 2)
    mae = statistics.mean(loo)
    era = lambda lo, hi: round(statistics.mean([e for p, e in zip(pts, loo) if lo <= int(p["date"][-4:]) < hi]), 2)

    v59 = next(v for v in rows if v["anr"] == "191")
    v71 = next(v for v in rows if v["anr"] == "224")
    pred = lambda c: round(a + b * c, 1)
    c59, u59 = cue(v59)
    c71, u71 = cue(v71)
    shares59 = {w: _f(v59.get(f"w-{w}")) for w in set(PARTY_PAIRS.values()) if _f(v59.get(f"w-{w}"))}
    recs71 = {p: v71.get(f"p-{p}") for p in PARTY_PAIRS}
    c_cf, u_cf = cue(v71, recs=recs71, shares=shares59)

    # Imagination: Apertus proposes 1959 positions on the 1971 proposal (labelled generated, not evidence).
    l = cfg["llm"]
    ap = Apertus(l["base_url"], l["api_key"], config.model_for(cfg, "votes"), 0.3, 1200, l["retries"])
    parties59 = [p for p, w in PARTY_PAIRS.items() if w in shares59]
    prompt = ("In February 1959 Swiss men rejected women's suffrage (33.1 % yes). Party recommendations then: "
              + json.dumps({p: v59.get(f"p-{p}") for p in parties59}) + " (1=yes, 2=no, 5=free vote). "
              "Imagine the 1971 proposal had been put to the vote in 1959. For each party give the recommendation it would "
              "most plausibly have issued (1, 2 or 5) and one sentence of reasoning grounded in its 1959 position. "
              'Return {"parties": {"<party>": {"rec": "1|2|5", "reason": "<sentence>"}}}.')
    try:
        raw, _ = ap.chat_json([{"role": "user", "content": prompt}])
        imagined = {p: x for p, x in (raw.get("parties") or {}).items() if p in parties59 and isinstance(x, dict) and str(x.get("rec")) in CUE}
    except Exception as e:
        imagined = {"error": repr(e)}
    # Check the imagined reasoning against the evidence: does it misstate the party's real 1959 recommendation?
    said = {"1": r"recommended an? ['\"]?yes", "2": r"recommended an? ['\"]?no", "5": r"free vote"}
    import re
    for p, x in (imagined.items() if "error" not in imagined else []):
        real = v59.get(f"p-{p}")
        claims = [k for k, rx in said.items() if re.search(rx, x.get("reason") or "", re.I)]
        x["real_1959_rec"] = real
        x["misstates_evidence"] = bool(claims) and real not in claims
    c_im, u_im = cue(v59, recs={p: str(x["rec"]) for p, x in imagined.items() if isinstance(x, dict)}, shares=shares59) if imagined and "error" not in imagined else (None, {})

    out = {
        "source": "Swissvotes dataset (Année politique suisse, University of Bern), CC BY 4.0",
        "method": "yes% = a + b·cue; cue = voter-share-weighted mean of party recommendations (yes 1, no 0, free 0.5)",
        "fit": {"a": round(a, 2), "b": round(b, 2), "n_votes": len(pts), "loo_mae": round(mae, 2),
                "loo_mae_by_era": {"1894-1945": era(1894, 1946), "1946-1970": era(1946, 1971), "1971-1999": era(1971, 2000), "2000-": era(2000, 2100)}},
        "backtest": pts,
        "suffrage": {
            "note": "Both the 1959 and the 1971 federal votes were cast by men only; women first voted federally after the 1971 decision.",
            "actual_1959": _f(v59["volkja-proz"]), "actual_1971": _f(v71["volkja-proz"]),
            "model_1959": {"cue": round(c59, 3), "estimate": pred(c59), "parties": u59},
            "model_1971": {"cue": round(c71, 3), "estimate": pred(c71), "parties": u71},
            "counterfactual_1971_positions_1959_strengths": {"cue": round(c_cf, 3), "estimate": pred(c_cf), "parties": u_cf,
                                                            "interval": [round(pred(c_cf) - mae, 1), round(pred(c_cf) + mae, 1)]},
            "imagination_apertus_positions_1959": {"generated": True, "parties": imagined,
                                                   "cue": round(c_im, 3) if c_im is not None else None,
                                                   "estimate": pred(c_im) if c_im is not None else None},
        },
    }
    miss59 = round(out["suffrage"]["actual_1959"] - out["suffrage"]["model_1959"]["estimate"], 1)
    out["suffrage"]["corrected_counterfactual"] = {
        "method": "counterfactual estimate shifted by the model's 1959 residual (issue-specific gap of the 1959 male electorate)",
        "residual_1959": miss59, "estimate": round(pred(c_cf) + miss59, 1)}
    (data_dir / "referendum").mkdir(exist_ok=True)
    (data_dir / "referendum" / "suffrage.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    s = out["suffrage"]
    print(f"  backtest n={len(pts)}, LOO MAE {mae:.2f} pts; 1959 actual {s['actual_1959']} model {s['model_1959']['estimate']}; "
          f"1971 actual {s['actual_1971']} model {s['model_1971']['estimate']}; 1971 positions with 1959 strengths "
          f"{s['counterfactual_1971_positions_1959_strengths']['estimate']}; Apertus 1959 positions {s['imagination_apertus_positions_1959']['estimate']}")


# ---------------------------------------------------------------------------------------------------------------
# Every federal vote: estimate, related votes and "what if it had been voted in year Y" (generalises 1959 vs 1971).
# ---------------------------------------------------------------------------------------------------------------
LEGAL_FORM = {"1": "mandatory referendum", "2": "optional referendum", "3": "popular initiative", "4": "counter-proposal", "5": "tie-break question"}
REC_LABEL = {"1": "yes", "2": "no", "3": "none", "4": "empty", "5": "free vote", "66": "neutral"}
SAID = {"1": r"recommended an? ['\"]?yes", "2": r"recommended an? ['\"]?no", "5": r"free vote"}


@functools.lru_cache(maxsize=1)
def _rows(path: str) -> tuple:
    rows = list(csv.DictReader(io.StringIO(open(path, "rb").read().decode("utf-8-sig")), delimiter=";"))
    for v in rows:
        d, m, y = v["datum"].split(".")
        v["_iso"], v["_year"] = f"{y}-{m}-{d}", int(y)
    return tuple(rows)


def _csv(cfg) -> str:
    """Swissvotes dataset (CC BY 4.0); not in git, downloaded on first use."""
    from .consultations import SWISSVOTES, _download
    path = cfg["paths"]["data_dir"] / "consultations" / "swissvotes_dataset.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(_download(SWISSVOTES, path))


def rows(cfg) -> tuple:
    return _rows(_csv(cfg))


def _by_anr(cfg, anr: str) -> dict:
    v = next((v for v in rows(cfg) if v["anr"] == anr), None)
    if not v:
        raise KeyError(anr)
    return v


def _bool(x):
    return {"1": True, "0": False}.get(x)


def recs_of(v: dict) -> dict:
    """Party recommendations keyed like the vote-share columns (KVP and CVP both feed 'cvp')."""
    out = {}
    for p, w in PARTY_PAIRS.items():
        r = v.get(f"p-{p}")
        if r in CUE and w not in out:
            out[w] = r
    return out


def shares_of(v: dict) -> dict:
    return {w: s for w in set(PARTY_PAIRS.values()) if (s := _f(v.get(f"w-{w}")))}


def strict_cue(recs: dict, shares: dict) -> tuple[float | None, dict]:
    """Cue over parties that have both a recommendation and a vote share (no fallback to another year's shares)."""
    used = {w: {"rec": recs[w], "share": s} for w, s in shares.items() if w in recs}
    den = sum(x["share"] for x in used.values())
    return (sum(x["share"] * CUE[x["rec"]] for x in used.values()) / den if den else None), used


def _day(iso: str) -> int:
    return int(iso[:4]) * 372 + int(iso[5:7]) * 31 + int(iso[8:10])


def conditions(cfg, year: int, near: str | None = None) -> dict:
    """Party strengths of a year: the vote-share columns of the federal vote closest to it (at least 3 parties)."""
    target = _day(near or f"{year}-06-30")
    v = min((v for v in rows(cfg) if len(shares_of(v)) >= 3), key=lambda v: abs(_day(v["_iso"]) - target))
    return {"anr": v["anr"], "date": v["_iso"], "shares": shares_of(v)}


@functools.lru_cache(maxsize=1)
def _model(path: str) -> dict:
    pts = []
    for v in _rows(path):
        y = _f(v.get("volkja-proz"))
        if y is None or any(v.get(f"p-{p}") in ("8", "9") for p in PARTY_PAIRS):
            continue
        c, used = cue(v)
        if c is not None and len(used) >= 3:
            pts.append((v["anr"], c, y))
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]
    a, b = fit(xs, ys)
    loo = []
    for i in range(len(pts)):
        ai, bi = fit(xs[:i] + xs[i + 1:], ys[:i] + ys[i + 1:])
        loo.append(abs(ai + bi * xs[i] - ys[i]))
    return {"a": a, "b": b, "mae": statistics.mean(loo), "n": len(pts), "points": {p[0]: {"cue": round(p[1], 4), "yes": p[2]} for p in pts}}


def model(cfg) -> dict:
    return _model(_csv(cfg))


def estimate(cfg, c: float | None) -> float | None:
    m = model(cfg)
    return None if c is None else round(m["a"] + m["b"] * c, 1)


def _own_cue(cfg, v: dict) -> tuple[float | None, dict, dict | None]:
    """Cue of a vote with its own vote shares, or those of the closest vote when the row has none (e.g. upcoming votes)."""
    own = shares_of(v)
    cond = None if own else conditions(cfg, v["_year"], v["_iso"])
    c, used = strict_cue(recs_of(v), own or cond["shares"])
    return c, used, cond


def votes(cfg) -> dict:
    m = model(cfg)
    out = []
    for v in rows(cfg):
        c, used, _ = _own_cue(cfg, v)
        out.append({"anr": v["anr"], "date": v["_iso"], "year": v["_year"], "title_de": v["titel_kurz_d"], "title_fr": v["titel_kurz_f"],
                    "title_en": v["titel_kurz_e"] if v["titel_kurz_e"] not in ("", ".") else None,
                    "legal_form": LEGAL_FORM.get(v["rechtsform"], v["rechtsform"]), "yes": _f(v.get("volkja-proz")),
                    "accepted": _bool(v.get("annahme")), "estimate": estimate(cfg, c) if len(used) >= 3 else None})
    return {"model": {"a": round(m["a"], 2), "b": round(m["b"], 2), "loo_mae": round(m["mae"], 2), "n_votes": m["n"],
                      "points": m["points"]},
            "votes": out, "source": "Swissvotes dataset (Année politique suisse, University of Bern), CC BY 4.0"}


RELATED = """You know Swiss direct democracy. Given ONE federal vote and a list of candidate votes, return one JSON object:
{"title_en": "<English short title of the vote>",
 "summary": "<two sentences: what was decided and why it mattered, from general knowledge>",
 "related": [{"anr": "<anr of a candidate>", "relation": "same proposal|earlier attempt|later attempt|counter-proposal|same issue"}]}
List at most 6 related votes, only candidates that are truly about the same issue, closest first."""


def _related_candidates(cfg, v: dict, k: int = 30) -> list[dict]:
    from .qa import tokens
    tv = set(tokens(v["titel_kurz_d"] + " " + v["titel_off_d"]))
    scored = []
    for o in rows(cfg):
        if o["anr"] == v["anr"]:
            continue
        to = set(tokens(o["titel_kurz_d"] + " " + o["titel_off_d"]))
        s = len(tv & to) / (len(tv | to) or 1) + 0.5 * (o["d1e3"] == v["d1e3"] != ".") + 0.2 * (o["d1e2"] == v["d1e2"] != ".")
        if s > 0.15:
            scored.append((s, o))
    return [o for _, o in sorted(scored, key=lambda x: -x[0])[:k]]


def _detail(cfg, anr: str, ap) -> dict:
    """One vote: result, party-cue estimate, parliament's vote, and (Apertus, cached) English title, summary, related votes."""
    v = _by_anr(cfg, anr)
    cache_dir = cfg["paths"]["data_dir"] / "referendum" / "votes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{anr}.json"
    gen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if gen is None:
        cands = _related_candidates(cfg, v)
        user = (f"Vote {v['anr']} on {v['_iso']}: {v['titel_kurz_d']} / {v['titel_kurz_f']}\nOfficial title: {v['titel_off_d']}\n"
                f"Type: {LEGAL_FORM.get(v['rechtsform'])}; yes {v.get('volkja-proz')} %\n\nCandidates (anr | date | title | yes):\n"
                + "\n".join(f"{o['anr']} | {o['_iso']} | {o['titel_kurz_d']} | {o.get('volkja-proz')} %" for o in cands))
        try:
            raw, meta = ap.chat_json([{"role": "system", "content": RELATED}, {"role": "user", "content": user}])
        except Exception as e:
            raw, meta = {"error": repr(e)}, {}
        ok = {o["anr"] for o in cands}
        # votes with the same short title are the same proposal voted again; Apertus tends to skip them as "itself"
        rel = {o["anr"]: {"anr": o["anr"], "relation": "same proposal", "by": "title"} for o in cands
               if o["titel_kurz_d"].strip().lower() == v["titel_kurz_d"].strip().lower()}
        rel |= {str(x.get("anr")): {"anr": str(x.get("anr")), "relation": x.get("relation"), "by": "apertus"} for x in raw.get("related") or []
                if isinstance(x, dict) and str(x.get("anr")) in ok and str(x.get("anr")) not in rel}
        gen = {"generated": True, "model": meta.get("model"), "title_en": raw.get("title_en"), "summary": raw.get("summary"),
               "related": list(rel.values())[:6], "candidates": len(cands)}
        if "error" not in raw:
            path.write_text(json.dumps(gen, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in gen["related"]:
        o = _by_anr(cfg, x["anr"])
        x.update(date=o["_iso"], year=o["_year"], title_de=o["titel_kurz_d"], yes=_f(o.get("volkja-proz")), accepted=_bool(o.get("annahme")))
    c, used, cond = _own_cue(cfg, v)
    links = {k: v[col] for k, col in (("Swissvotes", "swissvoteslink"), ("BFS map", "bfsmap-de"), ("Année politique", "anneepolitique"))
             if v.get(col, ".") not in ("", ".")}
    return {"anr": anr, "date": v["_iso"], "year": v["_year"], "title_de": v["titel_kurz_d"], "title_fr": v["titel_kurz_f"],
            "title_official": v["titel_off_d"], "legal_form": LEGAL_FORM.get(v["rechtsform"], v["rechtsform"]),
            "yes": _f(v.get("volkja-proz")), "accepted": _bool(v.get("annahme")),
            "parliament": {"National Council": {"yes": _f(v.get("nrja")), "no": _f(v.get("nrnein"))},
                           "Council of States": {"yes": _f(v.get("srja")), "no": _f(v.get("srnein"))}},
            "links": links, "cue": round(c, 3) if c is not None else None, "estimate": estimate(cfg, c) if len(used) >= 3 else None,
            "loo_mae": round(model(cfg)["mae"], 1), "parties": used, "shares_from": cond, "apertus": gen}


EXPLAIN = """You explain, for a general reader, why each Swiss party would most plausibly have taken the position given
on a federal proposal had it been voted in {year}. The positions are FIXED: each comes from the party's own recommendations
on related federal votes near {year}, listed as evidence. Do not change or question them. For each party write ONE sentence
grounded in that evidence or in the party's profile at the time. Return {{"parties": {{"<party>": "<sentence>"}}}}."""
WHATIF_VERSION = 2  # 2: positions from related votes, Apertus only explains them (cached version-1 results are redone)


def rule_positions(cfg, near: list[dict], parties) -> dict:
    """Each party's most frequent recommendation on the related votes nearest the year (up to 3; ties go to the nearest).
    Backtest on 40 votes since 1971 (data/model_eval/whatif_fix.json): 68 % of positions right, as many as Apertus 70B
    predicting them itself (68 %) and more than 8B (64 %); neither model improved on it when given it as a default."""
    out = {}
    for p in parties:
        seen = [(r, x["anr"]) for x in near[:3] if (r := recs_of(_by_anr(cfg, x["anr"])).get(p)) in ("1", "2", "5")]
        if seen:
            recs = [r for r, _ in seen]
            best = min(recs, key=lambda r: (-recs.count(r), recs.index(r)))
            out[p] = {"rec": best, "from": [a for r, a in seen if r == best]}
    return out


def _whatif(cfg, anr: str, year: int, ap, ap_explain=None) -> dict:
    """The proposal of vote `anr` under the conditions of `year`, two evidence-based rows: its own party positions with
    that year's strengths, and the positions the parties of that year took on related votes near it (rule_positions),
    each explained in one sentence by Apertus (generated). When a related vote lies within 6 years of `year`, its model
    residual corrects both (issue-specific gap of that electorate). `ap` serves the vote detail, `ap_explain` the
    explanations (config: [llm.models] votes / whatif)."""
    v = _by_anr(cfg, anr)
    cache_dir = cfg["paths"]["data_dir"] / "referendum" / "whatif"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{anr}_{year}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("version") == WHATIF_VERSION:
            return cached
    d = _detail(cfg, anr, ap)
    cond = conditions(cfg, year)
    recs = recs_of(v)
    c_a, u_a = strict_cue(recs, cond["shares"])
    near = sorted(d["apertus"]["related"], key=lambda x: abs(x["year"] - year))
    anchor = None
    if near and abs(near[0]["year"] - year) <= 6:
        o = _by_anr(cfg, near[0]["anr"])
        c_o, u_o, _ = _own_cue(cfg, o)
        est_o, act_o = estimate(cfg, c_o), _f(o.get("volkja-proz"))
        anchor = {"anr": o["anr"], "date": o["_iso"], "title_de": o["titel_kurz_d"], "relation": near[0]["relation"],
                  "actual": act_o, "estimate": est_o, "parties": u_o,
                  "residual": round(act_o - est_o, 1) if act_o is not None and est_o is not None else None}
    evidence = {}
    for x in near[:3]:
        o = _by_anr(cfg, x["anr"])
        evidence[f"{o['_iso']} {o['titel_kurz_d']}"] = {w: REC_LABEL.get(r, r) for w, r in recs_of(o).items() if w in cond["shares"]}
    rule = rule_positions(cfg, near, cond["shares"])
    explained, meta = {}, {}
    if rule:
        prompt = (EXPLAIN.format(year=year) + "\n\n"
                  + f"Proposal: {v['titel_kurz_d']} ({d['apertus'].get('title_en') or v['titel_kurz_f']}), voted {v['_iso']}, yes {v.get('volkja-proz')} %.\n"
                  + "Positions: " + json.dumps({p: REC_LABEL[x["rec"]] for p, x in rule.items()}) + "\n"
                  + "Evidence, recommendations on related votes: " + json.dumps(evidence, ensure_ascii=False))
        try:
            raw, meta = (ap_explain or ap).chat_json([{"role": "user", "content": prompt}])
            explained = {p: x.get("reason") if isinstance(x, dict) else x for p, x in (raw.get("parties") or {}).items()}
            explained = {p: x.strip() for p, x in explained.items() if p in rule and isinstance(x, str) and x.strip()}
        except Exception:
            explained, meta = {}, {}
    real_anchor = recs_of(_by_anr(cfg, anchor["anr"])) if anchor else {}
    positions = {}
    for p, x in rule.items():
        reason = explained.get(p)
        claims = [k for k, rx in SAID.items() if re.search(rx, reason or "", re.I)]
        # does the generated explanation misstate the party's real position on the anchor vote, or the position itself?
        positions[p] = {"rec": x["rec"], "from": x["from"], "reason": reason, "anchor_rec": real_anchor.get(p),
                        "misstates_evidence": bool(claims and any(c not in (x["rec"], real_anchor.get(p)) for c in claims))}
    c_r, _ = strict_cue({p: x["rec"] for p, x in positions.items()}, cond["shares"])
    mae, res = model(cfg)["mae"], (anchor or {}).get("residual")
    est_a, est_r = (estimate(cfg, c_a) if len(u_a) >= 2 else None), (estimate(cfg, c_r) if len(positions) >= 2 else None)
    shift = lambda e: round(e + res, 1) if e is not None and res is not None else None
    out = {"anr": anr, "year": year, "version": WHATIF_VERSION, "conditions": cond, "anchor": anchor,
           "positions_then_strengths": {"cue": round(c_a, 3) if c_a is not None else None, "estimate": est_a, "parties": u_a,
                                        "interval": [round(est_a - mae, 1), round(est_a + mae, 1)] if est_a is not None else None,
                                        "corrected": shift(est_a), "parties_without_position": sorted(set(cond["shares"]) - set(u_a))},
           "related_positions": {"method": "each party's most frequent recommendation on the related votes nearest the year",
                                 "votes": [x["anr"] for x in near[:3]], "parties": positions,
                                 "parties_without_evidence": sorted(set(cond["shares"]) - set(positions)),
                                 "cue": round(c_r, 3) if c_r is not None else None, "estimate": est_r, "corrected": shift(est_r),
                                 "explained_by": meta.get("model"), "backtest": {"votes": 40, "rule_pct": 68.3, "apertus_70b_pct": 67.8,
                                                                                 "apertus_8b_pct": 64.4}}}
    if positions and len(explained) == len(positions):
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ------------------------------------------------------------------ the reader's language
VOTE_TEXT = """For a reader in {language}, write a two-sentence summary of this Swiss federal vote: what was decided and
why it mattered, in {language}. Keep names of laws, parties and places. (The title is not translated: the page shows
the official title.) Return one JSON object {{"summary": "<two sentences in {language}>"}}."""

REASONS = """Write each party's reasoning below in {language}, keeping the meaning and the party abbreviations.
Return one JSON object {{"<party>": "<reasoning in {language}>"}} with the same keys."""


def detail(cfg, anr: str, ap, lang: str = "en") -> dict:
    """`_detail` with the vote's summary written by Apertus in the reader's language (cached per vote)."""
    from . import i18n
    d = _detail(cfg, anr, ap)
    if lang == "en":
        return d | {"lang": "en"}
    a = d["apertus"]

    def make():
        try:
            raw, _ = ap.chat_json([{"role": "system", "content": VOTE_TEXT.format(language=i18n.language(lang))},
                                   {"role": "user", "content": json.dumps({"date": d["date"], "title_de": d["title_de"], "title_fr": d["title_fr"],
                                                                           "official_title": d["title_official"], "summary_en": a.get("summary")},
                                                                          ensure_ascii=False)}])
        except Exception:
            return None
        return {"summary": raw.get("summary")} if raw.get("summary") else None
    loc = i18n.localized(cfg["paths"]["data_dir"] / "referendum" / "votes" / f"{anr}.json", lang, make) or {}
    return d | {"lang": lang if loc else "en", "apertus": a | {"summary": loc.get("summary") or a.get("summary")}}


def whatif(cfg, anr: str, year: int, ap, lang: str = "en", ap_explain=None) -> dict:
    """`_whatif` with the parties' explanations in the reader's language. The positions themselves are those of the
    one cached run, so the estimates do not depend on the language."""
    from . import i18n
    w = _whatif(cfg, anr, year, ap, ap_explain)
    parties = (w.get("related_positions") or {}).get("parties") or {}
    if lang == "en" or not parties:
        return w | {"lang": "en"}

    def make():
        try:
            raw, _ = (ap_explain or ap).chat_json([{"role": "system", "content": REASONS.format(language=i18n.language(lang))},
                                                   {"role": "user", "content": json.dumps({p: x.get("reason") for p, x in parties.items()}, ensure_ascii=False)}])
        except Exception:
            return None
        return {p: str(raw[p]) for p in parties if isinstance(raw.get(p), str) and raw[p].strip()}
    loc = i18n.localized(cfg["paths"]["data_dir"] / "referendum" / "whatif" / f"{anr}_{year}.json", lang, make) or {}
    rp = w["related_positions"] | {"parties": {p: x | {"reason": loc.get(p, x.get("reason"))} for p, x in parties.items()}}
    return w | {"lang": lang if loc else "en", "related_positions": rp}
