# Hack Apertus Liebefeld — Deciphering Archives with Apertus, Red Pandas

**Team Red Pandas:** Giovanni Yazbeck and Alfredo Pio Yazbeck

**CORAS** stands for **C**ollective **O**rigins, **R**emembrance & **A**rchives of the **S**wiss. Its aim is to make Swiss memory
more accessible and interactive for newer generations.

**CORA** turns records of the Swiss Federal Archives into AI-ready, provenance-tracked metadata with Apertus v1.5.
For each document Apertus writes a résumé of at most 3 sentences (can be turned off) and decides whether it is a primary, secondary or tertiary source and of which type.
It also completes Gallica-style metadata (creator, publisher, commissioner, dates of creation, publication, update and archiving, place in the archive),
assesses the preprocessing the record needs (transcription normalization, structure extraction, schema harmonization,
entity linking, date/geo parsing, anonymization verification) and traces the document's story on a map. Rules, a gazetteer
and Wikidata check and complete what the model says, and every field records where it came from. The demo covers 300 documents and is browsable
in a Gallica-inspired interface, together with a published quality check of the Apertus output.

CORA uses the Apertus v1.5 model family and complies with the [HackApertus T&C](https://hackapertus.ch/terms-and-conditions).

## 🎯 The Challenge

University of Bern: **Deciphering Archives with Apertus** — [challenge page](https://app.notion.com/p/hackapertus/University-of-Bern-0a7b4fec112a820a9a1181bc0b5d4d52)

## 🔧 Resources & Tools

| Models           | URL                                      | Used for in CORA |
|------------------|------------------------------------------|---|
| Apertus v1.5 8B  | [huggingface.co/swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)  | Classification, audit, Ask the archive, what-if explanations |
| Apertus v1.5 70B | [huggingface.co/swiss-ai/Apertus-v1.5-70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) | Source level, Stapfer extraction, "See more", consultations, subject panel, votes |

Each feature runs on the model that did better in our 8B vs 70B comparison ([docs/model_comparison.md](docs/model_comparison.md)); the choice is set per feature in `src/config.toml`.

## The structure

| Path | What it is |
| --- | --- |
| `README.md` | This page: the project, how to run it, its sources |
| `technical_report.md` | The deeper write-up: architecture, evaluation, limitations |
| `RedPandas_Report.pdf` | The technical report as submitted (built by `docs/build_report_pdf.py`) |
| `LICENSE` | Apache-2.0 |
| `src/` | The code: pipeline `src/cora/`, CLI `src/run.py`, settings `src/config.toml`, website `src/site/` |
| `data/` | The AI-ready dataset and every intermediate result |
| `docs/` | Quality check, model comparison, verifications, ethics assessment, API |
| `notebooks/demo.ipynb` | Demonstration notebook |
| `material/` | The challenge material |

### What is where

| What | Where |
|---|---|
| REST API (FastAPI, OpenAPI docs at `/docs`) | `src/cora/api.py` |
| Gallica-style front end (JS + MapLibre GL) | `src/site/` |
| AI-ready dataset (JSONL / CSV / TSV), schema, edit log | `data/dataset/` |
| Quality check of the Apertus output | `docs/quality_report.md`, `data/qc_report.json` |
| Ethical impact assessment | `docs/ethics_impact_assessment.md` |
| Verification against the Bern Stapfer-Enquête datafication | `docs/stapfer_verification.md`, `python src/run.py stapfer` |
| Ask the archive (cited Q&A) and read-only MCP server | `/api/ask`, `src/mcp_server.py`, `docs/api.md` |
| Trust card (Evidence / Context) | record pages, `python src/run.py narrative` |
| Map of the filtered records, on swisstopo historical maps | *Browse* → Show map |
| Federal consultations 1960–1991 with procedure chains | *Consultations* page, `python src/run.py consultations` |
| Parliament since 1848 and every federal vote: party-cue estimate, related votes and "what if voted in year Y" (Apertus), e.g. women's suffrage 1971 vs 1959 | *Parliament & votes* page, `/api/votes` |
| Subject of secondary/tertiary records: Wikipedia article, primary dossiers of the Federal Archives, news for current issues (Apertus-selected) | record pages, `/api/records/{id}/topic` |
| Swiss Tales: *A year in context* (timeline of Swiss history with the archive units of each year) and *Oral tradition* (a cited, imagined year in an ancestor's life; Apertus checks whether the place of origin existed and belonged to the Confederation then) | *Swiss Tales* menu, `/api/years`, `/api/oral/*` |
| Browse covers: period photos of the record's place or subject, never older than the record | `python src/run.py covers`, `data/covers.json` |
| Apertus 8B vs 70B on every AI feature | `docs/model_comparison.md`, `src/eval_features.py` |
| 1,000-record scale run (Apertus 8B, timed) | `src/scale_run.sh`, `data/scale1000/` |
| 10,000-record verification run over source tiers, record types and eras (Apertus 8B/70B, timed; not in the published dataset) | `src/batch_run.sh`, `src/cora/mixed.py`, `docs/batch10k_verification.md` |

## Environment

Set these environment variables in `.env` (see `.env.example`):
```
LLM_NAME — name and version of the model (e.g. apertus-v1-5-70b)
LLM_BASE_URL — endpoint base URL (e.g. https://gateway.keera.ch/api/v1)
LLM_API_KEY — your API key
```
The model of a single feature can be overridden with `LLM_NAME_<FEATURE>` (e.g. `LLM_NAME_CLASSIFY=apertus-v1-5-70b`).

### Quick start

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows; or: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # set LLM_API_KEY
python src/run.py serve                           # demo on http://127.0.0.1:8000 (prebuilt data in data/)
python src/run.py all                             # rebuild everything from scratch
```

Full instructions, hardware and seeds are in [technical_report.md](technical_report.md) §6.

## 📦 Deliverables

- **Git repo:** https://github.com/Anakalypto/CORA-Apertus
- **Technical report:** [RedPandas_Report.pdf](RedPandas_Report.pdf) (4 pages + references) and [technical_report.md](technical_report.md)
- **Demo video:** link to be added

## Sources

Everything CORA shows comes from the sources below. Apertus classifies, extracts and selects; it doesn't supply facts of its own.

**Model**
- Swiss AI Initiative, *Apertus v1.5* (8B and 70B), [huggingface.co/swiss-ai](https://huggingface.co/swiss-ai)

**Archives and open government data**
| Source | Used for | Licence |
|---|---|---|
| Swiss Federal Archives, *Archive database of the Swiss Federal Archives* ([opendata.swiss](https://opendata.swiss)), read through [LINDAS](https://lindas.admin.ch/query) (dataset [`ais`](https://culture.ld.admin.ch/.well-known/dataset/ais)) | The records CORA classifies (original archive-database fields only) | Open use |
| Swiss Federal Archives, [online search](https://www.recherche.bar.admin.ch/recherche) | Links to each record and primary dossiers on the same subject | Open use |
| Swiss Federal Archives, *The Stapfer-Enquête: schooling in Switzerland 1799* (opendata.swiss, [SQL dump](https://sfa-laboratory.ch/Hackathon/Stapfer/stapferappdb_final.sql.zip)), with the University of Bern datafication ([stapferenquete.ch](https://stapferenquete.ch/)) | Stapfer verification, places of origin on the Oral tradition page | Open use |
| Swiss Federal Archives, *Federal consultations 1960–1991* (opendata.swiss, [sfa-laboratory.ch](https://sfa-laboratory.ch/bar-ogd/bar-02/)) | Consultations page | Open use |
| Swiss Federal Archives, [Federal Gazette and official publications](https://www.amtsdruckschriften.bar.admin.ch) | Period sources on the Oral tradition page | Open use |
| [Swissvotes](https://swissvotes.ch/page/dataset) (Année politique suisse, University of Bern) | Every federal vote, procedure chains of consultations | CC BY 4.0 |
| Swiss Parliament, [parlament.ch OData service](https://ws.parlament.ch/odata.svc) | Members of the federal chambers since 1848 | Open use |
| Federal Statistical Office, [PX-Web](https://www.pxweb.bfs.admin.ch) (national vote shares since 1971) and *Bevölkerungsentwicklung nach institutionellen Gliederungen, 1850–2000* ([census](https://www.bfs.admin.ch/asset/de/px-x-4004000000_101)) | Parliament page; population figures on the Oral tradition page | Open use, with source |
| ETH Library image archive (E-Pics) on [Wikimedia Commons](https://commons.wikimedia.org) | Photos on the Oral tradition page | Public domain, CC0, CC BY, CC BY-SA |
| [Wikimedia Commons](https://commons.wikimedia.org) images linked from Wikidata | Cover illustrations in Browse | Licence of each file |

**Reference works and linked data**
| Source | Used for | Licence |
|---|---|---|
| [Wikidata](https://www.wikidata.org) | Entity linking, places, office holders | CC0 |
| [Wikipedia](https://en.wikipedia.org) | Context for linked entities, subjects of secondary/tertiary records, Ask the archive | CC BY-SA |
| [Historical Dictionary of Switzerland (HLS/DHS/DSS)](https://hls-dhs-dss.ch) | Context band of the trust card | Linked, not copied |
| [Dodis](https://dodis.ch) (Diplomatic Documents of Switzerland) | Search links on record pages | Linked, not copied |
| [e-newspaperarchives.ch](https://www.e-newspaperarchives.ch) | Newspaper search links on the Oral tradition page | Linked, not copied |
| [Google News RSS](https://news.google.com) and [GDELT](https://www.gdeltproject.org) | News for subjects still discussed today | Links and headlines only |

**Maps and places**
| Source | Used for | Licence |
|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org) and [Nominatim](https://nominatim.openstreetmap.org) | Gazetteer (geocoding) and base map abroad | ODbL |
| [swisstopo](https://www.swisstopo.admin.ch) ([vector tiles](https://vectortiles.geo.admin.ch), [WMTS](https://wmts.geo.admin.ch), relief shading, historical Dufour map) | Base maps | Free geodata of the Confederation |
| [MapLibre GL JS](https://maplibre.org) | Map rendering (vendored in `src/site/vendor/`) | BSD-3-Clause |

**Standards and inspiration**
- ICA, [*Records in Contexts – Ontology (RiC-O)*](https://www.ica.org/standards/RiC/ontology), used by the LINDAS archive data
- Dublin Core metadata terms, for the Gallica-style metadata fields
- BnF, [*Gallica*](https://gallica.bnf.fr), interface inspiration


## License

Apache-2.0, see [LICENSE](LICENSE). All Hack Apertus projects are open source ([T&C](https://hackapertus.ch/terms-and-conditions), section 6).
