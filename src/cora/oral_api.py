"""API routes of the year context drawer and the Oral tradition page (included by api.py)."""
from fastapi import APIRouter, Body, HTTPException, Query

from . import ancestry, i18n, years

router = APIRouter()


def _app():
    from . import api  # imported at call time: api.py includes this router while it is still loading
    return api


def _llm(temperature: float, max_tokens: int):
    from .apertus import Apertus
    l = _app().CFG["llm"]
    return Apertus(l["base_url"], l["api_key"], l["model"], temperature, max_tokens, l["retries"])


@router.get("/api/years", summary="Curated key events of Swiss history (year context drawer)")
def year_list():
    return years.timeline(_app().DATA)


@router.get("/api/years/{year}", summary="A year in context: its key events, Federal Archives units that reference them, "
                                         "and records of the dataset from that year (archive look-ups cached per event)")
def year_detail(year: int):
    if not 1000 <= year <= 2100:
        raise HTTPException(400, "year out of range")
    a = _app()
    return years.year_context(year, a.RECORDS, a.DATA)


@router.get("/api/oral/places", summary="Places of origin known to the Stapfer-Enquête 1799 (autocomplete)")
def oral_places(q: str = Query("", min_length=0)):
    return ancestry.suggest(_app().DATA, q)


@router.post("/api/oral/story", summary="Oral tradition: a cited, partly imagined day in the life of an ancestor "
                                         "(body: {surname, place_id, year?, first_name?, oral?: [stories]}); "
                                         "family stories are used for this answer only and never stored")
def oral_story(body: dict = Body(...), lang: str = Query("en")):
    surname = str(body.get("surname") or "").strip()
    if not 2 <= len(surname) <= 60:
        raise HTTPException(400, "give a family name")
    try:
        place_id = int(body.get("place_id"))
        year = int(body.get("year") or 1799)
    except (TypeError, ValueError):
        raise HTTPException(400, "place_id and year must be numbers")
    if not 1700 <= year <= 1950:
        raise HTTPException(400, "choose a year between 1700 and 1950")
    oral = [str(o)[:600] for o in (body.get("oral") or []) if str(o).strip()][:12]
    a = _app()
    try:
        return ancestry.story(a.DATA, a.CFG, _llm(0.4, 3000), surname, place_id, year,
                              (str(body.get("first_name") or "").strip() or None), oral, lang=i18n.code(lang))
    except KeyError:
        raise HTTPException(404, "unknown place")


@router.post("/api/oral/photos", summary="Apertus picks one ETH Library photo per story stop among the open-licensed photos "
                                          "taken closest to it (body: {year, stops, home})")
def oral_photos(body: dict = Body(...)):
    stops = [s for s in (body.get("stops") or []) if isinstance(s, dict)][:8]
    a = _app()
    return ancestry.pick_photos(a.DATA, a.CFG, _llm(0.2, 1500), int(body.get("year") or 1799), stops, body.get("home"))
