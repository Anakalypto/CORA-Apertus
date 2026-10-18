# CORA API

Start the server with `python src/run.py serve`. Interactive OpenAPI documentation is at `http://127.0.0.1:8000/docs`, and the machine-readable spec at `/openapi.json`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/records?q=&document_type=&source_level=&medium=&decade=&fonds=&language=&preprocessing=&qc=&sort=&page=&size=` | Full-text search with facets (counts returned for every facet) |
| GET | `/api/records/{id}` | Full AI-ready record: original fields, classification, metadata, archival location, entities, preprocessing, personal data, story, provenance, QC |
| GET | `/api/map` | Every located story event of every record (overview map) |
| GET | `/api/stats` | Collection statistics, facet counts, QC summary, sample population |
| GET | `/api/qc` | The full quality-check report (summary and per-record checks) |
| GET | `/api/schema` | JSON Schema of the AI-ready record |
| GET | `/api/export/{fmt}` | Download `jsonl`, `csv`, `tsv`, `edit_log` or `schema` |
| POST | `/api/classify/{id}?resume=true&story_map=true` | Live run on any record ID of the archive database: fetch the original fields, run both Apertus passes, geocode, build the story (~30 s) |

## Example

```bash
curl "http://127.0.0.1:8000/api/records?q=gandhi"
curl "http://127.0.0.1:8000/api/records/21681248"
curl -X POST "http://127.0.0.1:8000/api/classify/1632941?resume=false"
```

## Python (pipeline as a library)

```python
from cora import config, lindas, classify
from cora.apertus import Apertus

cfg = config.load()                       # config.toml + .env (LLM_NAME, LLM_BASE_URL, LLM_API_KEY)
rec = lindas.fetch_records(["3237439"])[0]
ap = Apertus(cfg["llm"]["base_url"], cfg["llm"]["api_key"], cfg["llm"]["model"])
raw, meta = ap.chat_json(classify.build_messages(rec, cfg))
result, issues = classify.normalize(raw, rec, cfg)
checks, preprocessing, personal = classify.audit_to_flags(ap.chat_json(classify.build_audit_messages(rec))[0], rec)
```

`[classify] resume = false` in `src/config.toml` turns off the résumé. `preprocessing` and `story_map` can be turned off the same way.
