"""Year context drawer: curated key events of a year and everything in the archive that references them.

Events are hand-curated (data/years/events.json). For each event, the Federal Archives are searched by the
event's title words (LINDAS, any unit level) and kept when the unit's date overlaps the event's period
(10 years either side; undated units are kept and marked). Records of the CORA dataset that mention an event
or are dated in the year are listed first. Archive look-ups are cached per event.
"""
import json
import re
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import topic

HLS_SEARCH = "https://hls-dhs-dss.ch/de/search/?text="


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _years(s) -> list[int]:
    return [int(y) for y in re.findall(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)", str(s or ""))]


def load_events(data_dir: Path) -> list[dict]:
    evs = json.loads((data_dir / "years" / "events.json").read_text(encoding="utf-8"))["events"]
    for e in evs:
        e.setdefault("end", e["year"])
        e["hls"] = HLS_SEARCH + urllib.parse.quote_plus(e.get("hls_q") or e["terms"][0].title())
    return evs


def events_in(evs: list[dict], y: int) -> list[dict]:
    return [e for e in evs if e["year"] <= y <= e["end"]]


def _archive(e: dict, cache_dir: Path) -> dict:
    path = cache_dir / f"{e['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    units, failed = {}, []
    for term in e["terms"]:
        try:
            for u in topic.archive_dossiers(term, limit=60):
                units.setdefault(u["id"], u)
        except Exception as err:  # LINDAS timeouts: report, retry on the next request
            failed.append(f"{term}: {type(err).__name__}")
    # Federal records start in 1848: older events are only referenced later (commemorations, research), so all
    # units naming them are kept; for later events, units dated within ten years of the event.
    lo, hi = (e["year"] - 10, e["end"] + 10) if e["year"] >= 1848 else (0, 9999)
    kept = []
    for u in units.values():
        ys = _years(u.get("date"))
        if not ys:
            kept.append(u | {"undated": True})
        elif min(ys) <= hi and max(ys) >= lo:
            kept.append(u)
    def rank(u):  # inside the event's own years first, then by the event's main title word, then by date
        ys = _years(u.get("date"))
        inside = bool(ys) and min(ys) <= e["end"] and max(ys) >= e["year"]
        term = e["terms"].index(u["stem"]) if u.get("stem") in e["terms"] else 9
        return (not inside, u.get("undated", False), term, min(ys or [9999]))
    kept.sort(key=rank)
    out = {"id": e["id"], "units": kept[:25], "found": len(units), "kept": len(kept), "failed": failed}
    if not failed:
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _local_mentions(e: dict, records: dict) -> list[dict]:
    terms = [_fold(t) for t in e["terms"]]
    out = []
    for r in records.values():
        if any(t in r["_text"] for t in terms):
            ys = _years(r["metadata"].get("content_date"))
            if not ys or (min(ys) <= e["end"] + 10 and max(ys) >= e["year"] - 10):
                out.append(r)
    return out


def _card(r: dict) -> dict:
    m = r["metadata"]
    return {"id": r["id"], "title": m.get("title_normalized") or m["title"], "date": m.get("content_date"),
            "document_type": r["classification"]["document_type"], "cover": r.get("cover")}


def year_context(y: int, records: dict, data_dir: Path) -> dict:
    evs = load_events(data_dir)
    here = events_in(evs, y)
    cache_dir = data_dir / "years" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        arch = dict(zip([e["id"] for e in here], pool.map(lambda e: _archive(e, cache_dir), here)))
    events = [e | {"in_dataset": [_card(r) for r in _local_mentions(e, records)][:12], "archive": arch[e["id"]]} for e in here]
    dated = [r for r in records.values() if y in _years((r["metadata"].get("content_date") or "")[:4])]
    near = sorted(evs, key=lambda e: min(abs(e["year"] - y), abs(e["end"] - y)))
    return {"year": y, "events": events, "records_dated": [_card(r) for r in dated][:30],
            "nearby": [{"id": e["id"], "year": e["year"], "end": e["end"], "title": e["title"]} for e in near if e not in here][:6]}


def timeline(data_dir: Path) -> list[dict]:
    return [{"id": e["id"], "year": e["year"], "end": e["end"], "title": e["title"]} for e in load_events(data_dir)]
