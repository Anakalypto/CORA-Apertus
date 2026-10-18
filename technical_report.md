# Technical report — CORA, `team name`

An Apertus-powered classifier and Gallica-style explorer for the Archive database of the Swiss Federal Archives.

- **Challenge:** University of Bern — Deciphering Archives with Apertus
- **Event:** On-site Liebefeld
- **Team:** `team name` — `member`, `member`, `member`
- **Demo:** `link to video`

## 1. Summary

The Archive database of the Swiss Federal Archives describes 263,123 item-level documents with dense German, French or Italian cataloguing prose. Its metadata is rich but not AI-ready: encoding damage, labelled sub-fields packed into free text, dotted dates, author fields that mix roles, and no source typing or geography.

CORA runs each record through **Apertus v1.5 70B** in two passes:
1. A **classification** pass: a résumé of at most 3 sentences (can be turned off), document type and medium, a primary/secondary/tertiary source level with its rationale, Gallica/Dublin-Core-like metadata (creator, publisher, commissioner, dates of creation / publication / update / archiving, languages, subjects), and persons, organizations and places.
2. An **evidence-based audit** of the six preprocessing needs and of personal data.

Rules, a gazetteer and Wikidata then add the archival location, the accession date, coordinates and entity links. Each document's story is traced on a map, from where it was made to the Federal Archives in Bern. On a stratified random sample of 100 documents, 99 % are processed without structural or critical error and 1 % have structural errors. A manual review of 25 records rates 88 % of them usable (32 % fully correct, 56 % minor errors) and 12 % with a major error. The full quality check is in [docs/quality_report.md](docs/quality_report.md).

## 2. Architecture

```
opendata.swiss dataset ──► LINDAS SPARQL (original fields only)
        │
        ▼
 sample ─► fetch ─► classify (Apertus pass 1) ─► audit (Apertus pass 2 + rule detectors)
                                                        │
                    compare (Apertus 8B) ◄──────────────┤
                                                        ▼
                         enrich (Nominatim gazetteer, Wikidata, story trail)
                                                        ▼
                         qc (automatic checks + manual review) ─► export (JSONL/CSV/TSV, schema, edit log)
                                                        ▼
                         FastAPI backend (/api, /docs) + Gallica-style JS front end (Leaflet map)
```

| Component | File | Runs |
|---|---|---|
| Configuration (`config.toml` + `.env`) | `src/cora/config.py` | local |
| Sampling and record fetch (original fields only) | `src/cora/lindas.py` | local → LINDAS SPARQL |
| Apertus client (OpenAI-compatible, JSON mode, retries) | `src/cora/apertus.py` | local → Keera Gateway → CSCS |
| Prompts, schema, normalisation, rule detectors | `src/cora/classify.py` | local |
| Geocoding, entity linking, story trail | `src/cora/enrich.py` | local → Nominatim, Wikidata |
| Quality check | `src/cora/qc.py` | local |
| Dataset export (pandas) | `src/cora/export.py` | local |
| REST API + front end | `src/cora/api.py`, `src/site/` | local server |
| Demo notebook | `notebooks/demo.ipynb` | Jupyter |

Each field carries its **provenance**: `record`, `derived`, `apertus`, `gazetteer` or `wikidata`. Conflicts are resolved by fixed rules, and every override is logged:
- The accession year comes from the accession number, not from Apertus.
- Coordinates come from the gazetteer, not from Apertus.

### Target architecture (mandatory)

CORA is deployable **on-premise (a)** and on a **sovereign Swiss cloud (c)**. It can be made **air-gapped (b)** with the changes listed below.

- **Runtime dependencies:**
  - an OpenAI-compatible Apertus endpoint: the CSCS-hosted one, or Apertus weights served with vLLM on-premise
  - optionally, Nominatim and Wikidata, both of which can be self-hosted, or the cache can be shipped
- **The front end** uses vendored Leaflet. Map tiles come from OpenStreetMap, or from swisstopo for Switzerland.
- **Python packages:** pandas, FastAPI, uvicorn; Jupyter only for the notebook.
- **Build time vs runtime:** the 100-record demo runs fully offline once `data/` is built, except for the map tiles. Only the *Live classify* page needs the model endpoint at runtime.
- **For air-gapped use:** serve Apertus locally, self-host Nominatim or ship the enrichment cache, serve the tiles locally, and load records from the opendata.swiss bulk dump instead of LINDAS.

## 3. Use of Apertus

- **Model:** `swiss-ai/Apertus-v1.5-70B` (`apertus-v1-5-70b` on the gateway) as the classifier; `Apertus-v1.5-8B` for the consistency check.
- **How it is used:** inference with structured JSON output, in two prompted passes, plus evaluation (70B vs 8B agreement).
- **Where it runs:** CSCS inference, reached through the Keera Gateway at `https://gateway.keera.ch/api/v1` (OpenAI-compatible). It's configured with `LLM_NAME`, `LLM_BASE_URL` and `LLM_API_KEY`.
- **Settings:** temperature 0.1, `response_format: json_object`, max 2,500 tokens, 6 parallel requests, up to 3 retries with the parse error fed back (none were needed).
- **Pass 1 prompt (classification):** archivist persona; strict grounding rules ("never invent names, dates or places"); a definition of primary/secondary/tertiary; the accession-number convention; and a JSON schema with the controlled vocabularies (20 document types, 5 media, 6 story-event types).
- **Pass 2 prompt (audit):** eleven yes/no checks, each requiring a quoted piece of evidence. The six preprocessing flags are derived from the answers by rule and combined with deterministic detectors for the mechanical checks. Pass 2 replaced asking for the flags directly, which returned "yes" for about 100 % of records.
- **Cost for 100 records:** about 325k prompt and 124k completion tokens on 70B, and about 9 minutes wall-clock.

## 4. Data

- *Archive database of the Swiss Federal Archives*, opendata.swiss, terms "open use" (`https://opendata.swiss/terms-of-use#terms_open`). We read it through LINDAS (`https://lindas.admin.ch/query`, dataset `https://culture.ld.admin.ch/.well-known/dataset/ais`) and use only the original archive-database fields, as documented in `01-ReadMe.xlsx` of the dump.
- **Sample:** stratified random, seed 42, over the 263,123 `rico:Record` units: 40 audiovisual, 30 still images, 30 other. See `data/sample.json`.
- **Outputs** in `data/`:
  - `records_raw.json` (originals)
  - `classified*.jsonl` (raw model output)
  - `enriched.jsonl`, `qc_report.json`, `manual_review.json`
  - `dataset/cora_dataset.{jsonl,csv,tsv}`, `dataset/schema.json`, `dataset/edit_log.jsonl`
- **Personal data:** names of persons appear in the source metadata, mostly public figures. Nothing personal was added beyond Wikidata links to public figures. See [docs/ethics_impact_assessment.md](docs/ethics_impact_assessment.md).
- Gazetteer: © OpenStreetMap contributors (ODbL). Wikidata: CC0.

## 5. Limitations

- **Content accuracy:**
  - The weakest fields are the résumé (68 % fully correct in the manual review) and entities (76 %).
  - All three major errors come from archival conventions the model doesn't know: speaker ≠ author, depositing agency ≠ creator, *Postulat* ≠ motion.
- **Model blind spots:**
  - Apertus doesn't notice encoding damage (recall 0 / 38), so rules cover it.
  - Apertus rarely fills the accession year (24 %), so a rule covers it.
  - Apertus adds first names from world knowledge, which led to one wrong Wikidata link.
- **Anonymization:** the flag has about 40 % precision (it confuses sensitive topics with sensitive persons) and at least one miss. It is a triage aid only.
- **Geography:** 83 % of places were located. There is one known gazetteer error (Simplon), and small hamlets and military points (e.g. "Pkt 706") are not resolved.
- **Coverage:** all 100 records are primary sources. Secondary and tertiary classification is untested on real examples, and the source-level agreement of 100 % is partly because the task was easy.
- The manual review was done by one reviewer (an AI assistant) on 25 records. Archivists should repeat it.
- The University of Bern reference structure was not available to us, so there is no comparison against it.

## 6. Reproducibility

```bash
python -m venv .venv && .venv/Scripts/activate       # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                  # set LLM_API_KEY
python src/run.py all                                 # sample → fetch → classify → audit → compare → enrich → qc → export
python src/run.py serve                               # http://127.0.0.1:8000 (API docs at /docs)
jupyter notebook notebooks/demo.ipynb
```

- **Hardware:** any laptop (the model runs remotely); about 15 minutes for 100 records, dominated by the API and the 1 req/s geocoder.
- **Seeds:** sample seed 42 over a sorted population. Model temperature is 0.1, so reruns vary slightly.
- **Pinned facts:** Python 3.12, Apertus v1.5 on vLLM 0.23 (gateway fingerprint), LINDAS data of 2026-01-08.
- Each stage reads the previous stage's file in `data/`, so any stage can be rerun alone (`python src/run.py qc`).

## License

Creative Commons Attribution 4.0 (CC-BY-4.0). All HackApertus projects are open-sourced.

## References

- Swiss Federal Archives, *Archive database of the Swiss Federal Archives*, opendata.swiss (2026).
- LINDAS — Linked Data Service of the Swiss Confederation, dataset `ais`.
- Swiss AI Initiative, *Apertus v1.5* model family, huggingface.co/swiss-ai.
- ICA, *Records in Contexts – Ontology (RiC-O)*.
- OpenStreetMap Nominatim; Wikidata.
- BnF, *Gallica* (interface inspiration).
