"""Referendum estimate from party cues, women's suffrage case (1959 vs 1971).

Data: Swissvotes (Année politique suisse, University of Bern, CC BY 4.0): for every federal vote the
party recommendations (p-*) and the parties' voter shares at the time (w-*, National Council vote
shares, not seats), and the result.
Model: cue = Σ w_p·s_p / Σ w_p over parties with a known recommendation (yes=1, no=0, free/none=0.5);
yes% = α + β·cue, fitted by least squares. Confidence = leave-one-out mean absolute error.
Note: the 1959 and the 1971 votes were both cast by men only; women first voted federally after 1971.
"""
import csv
import io
import json
import statistics

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
    rows = list(csv.DictReader(io.StringIO((data_dir / "consultations" / "swissvotes_dataset.csv").read_bytes().decode("utf-8-sig")), delimiter=";"))
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
    ap = Apertus(l["base_url"], l["api_key"], l["model"], 0.3, 1200, l["retries"])
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
